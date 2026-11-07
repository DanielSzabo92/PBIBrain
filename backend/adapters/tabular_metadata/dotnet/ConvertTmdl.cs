using Microsoft.AnalysisServices.Tabular;
using Json = System.Text.Json.JsonSerializer;
using TomJson = Microsoft.AnalysisServices.Tabular.JsonSerializer;

// Bridge command "convert-tmdl <model.bim> <empty folder>" (issue #16). It reads a
// TMSL model with TOM and writes it as canonical TMDL into the folder. It then
// reads the TMDL again and proves that TOM gives the same database JSON, so the
// conversion loses nothing that TOM knows. The command never changes model.bim.
static class ConvertTmdl
{
    public static int Run(string[] args, TextWriter output)
    {
        try
        {
            if (args.Length != 3) return Fail(output, "invalid_request", "Use: convert-tmdl <model.bim> <empty folder>");
            var source = Path.GetFullPath(args[1]);
            var folder = Path.GetFullPath(args[2]);
            if (!File.Exists(source)) return Fail(output, "invalid_request", "The model.bim file does not exist");
            if (Directory.Exists(folder) && Directory.EnumerateFileSystemEntries(folder).Any())
                return Fail(output, "invalid_request", "The output folder must be empty");
            Database database;
            try { database = TomJson.DeserializeDatabase(File.ReadAllText(source)); }
            catch (Exception error) { return Fail(output, "model_load_failed", error.Message); }
            CanonicalTmdl.SerializeToFolder(database, folder);
            var before = TomJson.SerializeDatabase(database);
            var after = TomJson.SerializeDatabase(TmdlSerializer.DeserializeDatabaseFromFolder(folder));
            if (before != after)
            {
                Directory.Delete(folder, true);
                return Fail(output, "roundtrip_failed", "The TMDL copy does not give the same model");
            }
            output.WriteLine(Json.Serialize(new
            {
                adapter_version = 1,
                status = "PASSED",
                command = "convert-tmdl",
                table_count = database.Model.Tables.Count,
                file_count = Directory.EnumerateFiles(folder, "*.tmdl", SearchOption.AllDirectories).Count(),
            }));
            return 0;
        }
        catch (Exception error) { return Fail(output, "convert_failed", error.Message); }
    }

    static int Fail(TextWriter output, string code, string message)
    {
        output.WriteLine(Json.Serialize(new { adapter_version = 1, status = "FAILED", command = "convert-tmdl", code, error = message }));
        return 2;
    }
}
