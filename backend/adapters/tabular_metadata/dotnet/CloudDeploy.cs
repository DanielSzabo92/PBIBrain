using Microsoft.AnalysisServices.Tabular;
using System.Text.Json.Nodes;
using Json = System.Text.Json.JsonSerializer;

// Bridge command "cloud-deploy" (issue #16). It writes a TMDL folder to one cloud
// model through XMLA with TOM. TOM copies the folder model onto the model of the
// service and SaveChanges sends only the delta. The request comes on stdin, so the
// access token is not in the process arguments; the bridge never stores it or
// writes it to stdout.
//
// The request may give expected_last_schema_update: when the model in the service
// has another LastSchemaUpdate, someone changed it after the app read it, and the
// command stops with "target_changed" before it changes anything.
static class CloudDeploy
{
    sealed class CloudDeployError : Exception
    {
        public string Code { get; }
        public CloudDeployError(string code, string message) : base(message) { Code = code; }
    }

    const string Stamp = "yyyy-MM-ddTHH:mm:ssZ";

    public static int Run(TextReader input, TextWriter output)
    {
        try
        {
            var request = JsonNode.Parse(input.ReadToEnd().TrimStart('﻿')) as JsonObject
                ?? throw new CloudDeployError("invalid_request", "The request must be one JSON object");
            var server = Text(request, "server");
            var database = Text(request, "database");
            var token = Text(request, "access_token");
            var folder = Path.GetFullPath(Text(request, "folder"));
            var expected = request["expected_last_schema_update"] is JsonValue stamp && stamp.TryGetValue<string>(out var text) ? text : null;
            if (!server.StartsWith("powerbi://", StringComparison.OrdinalIgnoreCase) || server.Contains(';'))
                throw new CloudDeployError("invalid_request", "The server must be a powerbi:// workspace connection");
            var expiresOn = request["expires_on"] is JsonValue value && value.TryGetValue<long>(out var seconds)
                ? DateTimeOffset.FromUnixTimeSeconds(seconds)
                : throw new CloudDeployError("invalid_request", "The request needs expires_on");
            if (expiresOn <= DateTimeOffset.UtcNow.AddMinutes(1))
                throw new CloudDeployError("token_expired", "The access token expired");
            if (!Directory.Exists(folder))
                throw new CloudDeployError("invalid_request", "The TMDL folder does not exist");

            Database local;
            try { local = TmdlSerializer.DeserializeDatabaseFromFolder(folder); }
            catch (Exception error) { throw new CloudDeployError("model_load_failed", error.Message); }

            using var tom = new Server();
            tom.AccessToken = new Microsoft.AnalysisServices.AccessToken(token, expiresOn);
            tom.OnAccessTokenExpired = _ => throw new CloudDeployError("token_expired", "The access token expired");
            try { tom.Connect($"Data Source={server};"); }
            catch (CloudDeployError) { throw; }
            catch (Exception error) when (IsTokenError(error)) { throw new CloudDeployError("token_expired", "The access token expired"); }
            catch (Exception error) { throw new CloudDeployError("connect_failed", error.Message); }
            var found = tom.Databases.Find(database) ?? tom.Databases.FindByName(database)
                ?? throw new CloudDeployError("not_found", "The model is not in the workspace or you cannot read it");
            var before = found.LastSchemaUpdate.ToUniversalTime().ToString(Stamp);
            if (expected != null && expected != before)
                throw new CloudDeployError("target_changed", "The model in the service changed after the app read it");

            local.Model.CopyTo(found.Model);
            try { found.Model.SaveChanges(); }
            catch (Exception error) when (IsTokenError(error)) { throw new CloudDeployError("token_expired", "The access token expired"); }
            catch (Exception error) { throw new CloudDeployError("write_failed", error.Message); }
            found.Refresh();
            output.WriteLine(Json.Serialize(new
            {
                adapter_version = 1,
                status = "PASSED",
                command = "cloud-deploy",
                database_id = found.ID,
                database_name = found.Name,
                last_schema_update_before = before,
                last_schema_update = found.LastSchemaUpdate.ToUniversalTime().ToString(Stamp),
            }));
            return 0;
        }
        catch (CloudDeployError error) { return Fail(output, error.Code, error.Message); }
        catch (Exception error) when (IsTokenError(error)) { return Fail(output, "token_expired", "The access token expired"); }
        catch (Exception error) { return Fail(output, "write_failed", error.Message); }
    }

    static string Text(JsonObject request, string name) =>
        request[name] is JsonValue value && value.TryGetValue<string>(out var text) && !string.IsNullOrWhiteSpace(text)
            ? text : throw new CloudDeployError("invalid_request", "The request needs " + name);

    static bool IsTokenError(Exception error)
    {
        for (var item = (Exception?)error; item != null; item = item.InnerException)
            if (item.Message.Contains("token", StringComparison.OrdinalIgnoreCase)
                && item.Message.Contains("expired", StringComparison.OrdinalIgnoreCase)) return true;
        return false;
    }

    static int Fail(TextWriter output, string code, string message)
    {
        output.WriteLine(Json.Serialize(new { adapter_version = 1, status = "FAILED", command = "cloud-deploy", code, error = message }));
        return 2;
    }
}
