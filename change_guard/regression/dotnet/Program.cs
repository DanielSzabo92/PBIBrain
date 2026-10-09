using Microsoft.AnalysisServices.Tabular;
using Microsoft.AnalysisServices.AdomdClient;
using System.Text.Json.Nodes;
using Json = System.Text.Json.JsonSerializer;
using TomJson = Microsoft.AnalysisServices.Tabular.JsonSerializer;

// Trusted evaluator only. Loading is distinct from the query-only adapter.
// Local endpoints are exact loopback ports; caller cannot inject connections.
Console.OutputEncoding = System.Text.Encoding.UTF8;
try
{
    var request = JsonNode.Parse(Console.In.ReadToEnd())!.AsObject();
    var port = request["port"]!.GetValue<int>();
    if (port < 1 || port > 65535) throw new ArgumentException("Invalid local port");
    var databaseId = request["database_id"]!.GetValue<string>();
    if (!System.Text.RegularExpressions.Regex.IsMatch(databaseId, "^guard_[a-f0-9]{32}$")) throw new ArgumentException("Isolated database identity required");
    var connection = $"Data Source=localhost:{port};Initial Catalog={databaseId};Locale Identifier=1033;Connect Timeout=10;Timeout=30;Application Name=PBIBrainTrustedEvaluator;";
    var operation = request["operation"]!.GetValue<string>();
    if (operation == "load")
    {
        var path = Path.GetFullPath(request["model_path"]!.GetValue<string>());
        var database = Directory.Exists(path) ? TmdlSerializer.DeserializeDatabaseFromFolder(path) : TomJson.DeserializeDatabase(File.ReadAllText(path));
        database.ID = databaseId; database.Name = databaseId;
        // The isolated copy receives an explicit query-only role. No source
        // roles are removed or edited; a conflicting reserved name fails.
        database.Model.Roles.Add(new ModelRole { Name = "PBIBrainGuardReader", ModelPermission = ModelPermission.Read });
        using var server = new Server();
        server.Connect($"Data Source=localhost:{port};Connect Timeout=10");
        if (server.Databases.Contains(databaseId)) throw new InvalidOperationException("Isolated database already exists");
        server.Databases.Add(database); database.Update(Microsoft.AnalysisServices.UpdateOptions.ExpandFull);
        database.Model.RequestRefresh(RefreshType.Full); database.Model.SaveChanges();
        database.Refresh();
        var failures = database.Model.Tables.SelectMany(table => table.Partitions.Select(partition => new { table = table.Name, partition = partition.Name, state = partition.State.ToString(), error = partition.ErrorMessage })).Where(item => !string.IsNullOrEmpty(item.error) || item.state != "Ready").ToArray();
        if (failures.Length > 0) throw new InvalidOperationException(Json.Serialize(failures));
        Console.WriteLine(Json.Serialize(new { status = "PASSED", database_id = databaseId, model_loaded = true, processed = true,
            metadata = JsonNode.Parse(TomJson.SerializeDatabase(database)), engine_version = server.Version }));
    }
    else if (operation == "permission_probe")
    {
        string table;
        using (var server = new Server())
        {
            server.Connect($"Data Source=localhost:{port};Connect Timeout=10");
            var model = server.Databases.Find(databaseId)?.Model ?? throw new InvalidOperationException("Owned database missing");
            if (model.Roles.Find("PBIBrainGuardReader")?.ModelPermission != ModelPermission.Read) throw new InvalidOperationException("Reader permission changed");
            table = model.Tables[0].Name.Replace("'", "''");
        }
        var command = Json.Serialize(new { refresh = new { type = "full", objects = new[] { new { database = databaseId } } } });
        // The identical command must work through the trusted loader first.
        // A syntax or model error therefore cannot masquerade as a denial.
        using (var administrator = new AdomdConnection(connection))
        {
            administrator.Open(); using var control = administrator.CreateCommand();
            control.CommandText = command; control.ExecuteNonQuery();
            using var data = administrator.CreateCommand(); data.CommandText = $"EVALUATE ROW(\"Rows\", COUNTROWS('{table}'))";
            using var reader = data.ExecuteReader();
            if (!reader.Read() || reader.IsDBNull(0)) throw new InvalidOperationException("Administrator model data is blank after full processing");
        }
        using var client = new AdomdConnection(connection + "Roles=PBIBrainGuardReader;"); client.Open();
        using var query = client.CreateCommand(); query.CommandText = $"EVALUATE ROW(\"Probe\", COUNTROWS('{table}'))";
        using (var reader = query.ExecuteReader()) { if (!reader.Read() || reader.IsDBNull(0) || Convert.ToInt64(reader.GetValue(0)) < 0) throw new InvalidOperationException("Model read probe failed"); }
        bool denied = false;
        using var mutation = client.CreateCommand();
        mutation.CommandText = command;
        try { mutation.ExecuteNonQuery(); }
        catch (AdomdErrorResponseException error)
        {
            // Record the engine error; only an actual permission denial can be
            // accepted by the Python adapter. Syntax/transport errors do not.
            Console.WriteLine(Json.Serialize(new { status = "DENIED", read_probe = true, administrator_control = "PASSED", model_permission = "Read", enforced_role = "PBIBrainGuardReader",
                command_hash = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(command))).ToLowerInvariant(),
                error = error.Message, errors = error.Errors.Cast<AdomdError>().Select(item => new { code = item.ErrorCode, message = item.Message }).ToArray() })); denied = true;
        }
        if (!denied) throw new InvalidOperationException("Mutating command succeeded through reader connection");
    }
    else if (operation == "query")
    {
        using var client = new AdomdConnection(connection + "Roles=PBIBrainGuardReader;"); client.Open();
        using var query = client.CreateCommand(); query.CommandTimeout = 30; query.CommandText = request["query"]!.GetValue<string>();
        using var reader = query.ExecuteReader();
        var columns = Enumerable.Range(0, reader.FieldCount).Select(index => new { name = reader.GetName(index), type = reader.GetFieldType(index).Name }).ToArray();
        var rows = new List<object?[]>();
        while (reader.Read()) rows.Add(Enumerable.Range(0, reader.FieldCount).Select(index => reader.IsDBNull(index) ? null :
            reader.GetValue(index) is decimal amount ? (object)amount.ToString(System.Globalization.CultureInfo.InvariantCulture) : reader.GetValue(index)).ToArray());
        Console.WriteLine(Json.Serialize(new { status = "PASSED", result = new { columns, rows } }));
    }
    else throw new ArgumentException("Unsupported evaluator operation");
}
catch (Exception error)
{
    Console.WriteLine(Json.Serialize(new { status = "FAILED", error = error.Message, error_type = error.GetType().Name }));
    Environment.ExitCode = 2;
}
