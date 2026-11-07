using Microsoft.AnalysisServices.Tabular;
using System.Text;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Json = System.Text.Json.JsonSerializer;

// Bridge command "canonical-check" (DEV_CENTER_TECHNICAL_DESIGN.md section 9.1).
// Serializes a model to an isolated temporary directory and reports each .tmdl
// file whose disk bytes differ from TOM canonical serialization.
static class CanonicalCheck
{
    public static int Run(string[] args, TextReader input, TextWriter output)
    {
        string? modelPath = null;
        if (args.Length >= 2)
        {
            modelPath = args[1];
        }
        else if (Console.IsInputRedirected)
        {
            var content = input.ReadToEnd().TrimStart('\uFEFF');
            if (!string.IsNullOrWhiteSpace(content))
            {
                var parsed = JsonNode.Parse(content);
                if (parsed is JsonObject obj)
                {
                    modelPath = obj["model"]?.GetValue<string>() ?? obj["model_path"]?.GetValue<string>();
                }
                else if (parsed is JsonValue val && val.TryGetValue<string>(out var str))
                {
                    modelPath = str;
                }
            }
        }

        if (string.IsNullOrWhiteSpace(modelPath))
        {
            output.WriteLine(Json.Serialize(new
            {
                adapter_version = 1,
                status = "FAILED",
                command = "canonical-check",
                code = "invalid_request",
                error = "Model path is required"
            }));
            return 2;
        }

        var fullPath = Path.GetFullPath(modelPath);
        if (!Directory.Exists(fullPath))
        {
            output.WriteLine(Json.Serialize(new
            {
                adapter_version = 1,
                status = "FAILED",
                command = "canonical-check",
                code = "not_found",
                error = $"Model directory not found: {fullPath}"
            }));
            return 2;
        }

        var tempDir = Path.Combine(Path.GetTempPath(), "pbibrain-canonical-" + Guid.NewGuid().ToString("N"));
        try
        {
            Database database = TmdlSerializer.DeserializeDatabaseFromFolder(fullPath);
            CanonicalTmdl.SerializeToFolder(database, tempDir);

            var sourceFiles = Directory.GetFiles(fullPath, "*.tmdl", SearchOption.AllDirectories)
                .OrderBy(f => f, StringComparer.Ordinal)
                .ToList();

            var nonCanonicalFiles = new List<object>();

            foreach (var srcFile in sourceFiles)
            {
                var relativePath = Path.GetRelativePath(fullPath, srcFile).Replace('\\', '/');
                var canonicalFile = Path.Combine(tempDir, relativePath);

                if (!File.Exists(canonicalFile))
                {
                    nonCanonicalFiles.Add(new
                    {
                        file = relativePath,
                        path = relativePath,
                        differences = new[] { "file missing in canonical serialization" }
                    });
                    continue;
                }

                var srcBytes = File.ReadAllBytes(srcFile);
                var canBytes = File.ReadAllBytes(canonicalFile);

                if (!srcBytes.SequenceEqual(canBytes))
                {
                    var diffs = DetectDifferences(srcBytes, canBytes);
                    nonCanonicalFiles.Add(new
                    {
                        file = relativePath,
                        path = relativePath,
                        differences = diffs
                    });
                }
            }

            output.WriteLine(Json.Serialize(new
            {
                adapter_version = 1,
                status = "PASSED",
                command = "canonical-check",
                is_canonical = nonCanonicalFiles.Count == 0,
                non_canonical_files = nonCanonicalFiles,
                total_files = sourceFiles.Count,
                non_canonical_count = nonCanonicalFiles.Count
            }));
            return 0;
        }
        catch (Exception ex)
        {
            output.WriteLine(Json.Serialize(new
            {
                adapter_version = 1,
                status = "FAILED",
                command = "canonical-check",
                code = "check_failed",
                error = ex.Message
            }));
            return 2;
        }
        finally
        {
            if (Directory.Exists(tempDir))
            {
                try { Directory.Delete(tempDir, true); } catch { }
            }
        }
    }

    private static List<string> DetectDifferences(byte[] srcBytes, byte[] canBytes)
    {
        var diffs = new List<string>();

        // 1. Line endings check: does source have LF not preceded by CR?
        bool hasLfOnly = false;
        for (int i = 0; i < srcBytes.Length; i++)
        {
            if (srcBytes[i] == (byte)'\n' && (i == 0 || srcBytes[i - 1] != (byte)'\r'))
            {
                hasLfOnly = true;
                break;
            }
        }
        if (hasLfOnly)
        {
            diffs.Add("LF line ends");
        }

        var srcText = Encoding.UTF8.GetString(srcBytes);
        var canText = Encoding.UTF8.GetString(canBytes);

        // 2. Quoted table name: e.g. table 'Budget' vs table Budget
        if (Regex.IsMatch(srcText, @"^\s*table\s+'[^']+'", RegexOptions.Multiline) &&
            Regex.IsMatch(canText, @"^\s*table\s+[a-zA-Z0-9_#]+", RegexOptions.Multiline))
        {
            diffs.Add("quoted table name");
        }

        // 3. Blank line before lineageTag
        if (Regex.IsMatch(srcText, @"(?:\r?\n)[ \t]*(?:\r?\n)[ \t]*lineageTag:", RegexOptions.None))
        {
            diffs.Add("blank line before lineageTag");
        }

        // 4. Fallback if no specific diff pattern matched
        if (diffs.Count == 0)
        {
            diffs.Add("formatting differences");
        }

        return diffs;
    }
}
