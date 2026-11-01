using Microsoft.AnalysisServices.Tabular;
using System.Text.Json.Nodes;
using Json = System.Text.Json.JsonSerializer;

// Bridge command "cloud-read" (technical design section 10.2). It reads one cloud
// model through XMLA with TOM and exports it as TMDL into an empty folder.
// The request comes on stdin, so that the access token is not in the process
// arguments. The bridge never stores the token and never writes it to stdout.
// It only reads: it calls no SaveChanges, no Update, and no script.
static class CloudRead
{
    sealed class CloudReadError : Exception
    {
        public string Code { get; }
        public CloudReadError(string code, string message) : base(message) { Code = code; }
    }

    public static int Run(TextReader input, TextWriter output)
    {
        try
        {
            var request = JsonNode.Parse(input.ReadToEnd().TrimStart('﻿')) as JsonObject
                ?? throw new CloudReadError("invalid_request", "The request must be one JSON object");
            var server = Text(request, "server");
            var database = Text(request, "database");
            var token = Text(request, "access_token");
            var folder = Path.GetFullPath(Text(request, "out"));
            if (!server.StartsWith("powerbi://", StringComparison.OrdinalIgnoreCase) || server.Contains(';'))
                throw new CloudReadError("invalid_request", "The server must be a powerbi:// workspace connection");
            var expiresOn = request["expires_on"] is JsonValue value && value.TryGetValue<long>(out var seconds)
                ? DateTimeOffset.FromUnixTimeSeconds(seconds)
                : throw new CloudReadError("invalid_request", "The request needs expires_on");
            // A token with less than one minute left fails with the fixed code, so that Python gets a new token.
            if (expiresOn <= DateTimeOffset.UtcNow.AddMinutes(1))
                throw new CloudReadError("token_expired", "The access token expired");
            if (Directory.Exists(folder) && Directory.EnumerateFileSystemEntries(folder).Any())
                throw new CloudReadError("invalid_request", "The export folder must be empty");

            using var tom = new Server();
            tom.AccessToken = new Microsoft.AnalysisServices.AccessToken(token, expiresOn);
            tom.OnAccessTokenExpired = _ => throw new CloudReadError("token_expired", "The access token expired");
            try { tom.Connect($"Data Source={server};"); }
            catch (CloudReadError) { throw; }
            catch (Exception error) when (IsTokenError(error)) { throw new CloudReadError("token_expired", "The access token expired"); }
            catch (Exception error) { throw new CloudReadError("connect_failed", error.Message); }
            var found = tom.Databases.Find(database) ?? tom.Databases.FindByName(database)
                ?? throw new CloudReadError("not_found", "The model is not in the workspace or you cannot read it");
            TmdlSerializer.SerializeDatabaseToFolder(found, folder);
            output.WriteLine(Json.Serialize(new
            {
                adapter_version = 1,
                status = "PASSED",
                command = "cloud-read",
                database_id = found.ID,
                database_name = found.Name,
                last_schema_update = found.LastSchemaUpdate.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"),
                table_count = found.Model.Tables.Count,
                measure_count = found.Model.Tables.Sum(table => table.Measures.Count),
            }));
            return 0;
        }
        catch (CloudReadError error) { return Fail(output, error.Code, error.Message); }
        catch (Exception error) when (IsTokenError(error)) { return Fail(output, "token_expired", "The access token expired"); }
        catch (Exception error) { return Fail(output, "read_failed", error.Message); }
    }

    static string Text(JsonObject request, string name) =>
        request[name] is JsonValue value && value.TryGetValue<string>(out var text) && !string.IsNullOrWhiteSpace(text)
            ? text : throw new CloudReadError("invalid_request", "The request needs " + name);

    static bool IsTokenError(Exception error)
    {
        for (var item = (Exception?)error; item != null; item = item.InnerException)
            if (item.Message.Contains("token", StringComparison.OrdinalIgnoreCase)
                && item.Message.Contains("expired", StringComparison.OrdinalIgnoreCase)) return true;
        return false;
    }

    static int Fail(TextWriter output, string code, string message)
    {
        output.WriteLine(Json.Serialize(new { adapter_version = 1, status = "FAILED", command = "cloud-read", code, error = message }));
        return 2;
    }
}
