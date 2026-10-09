using Microsoft.AnalysisServices.Tabular;
using System.Text.Json.Nodes;
using Json = System.Text.Json.JsonSerializer;
using TomJson = Microsoft.AnalysisServices.Tabular.JsonSerializer;

Console.OutputEncoding = System.Text.Encoding.UTF8;
System.Globalization.CultureInfo.CurrentUICulture = System.Globalization.CultureInfo.InvariantCulture;

// This executable accepts source metadata only. It has no server connections,
// mutation commands, generated-script execution, or deployment credentials.
try
{
    if (args.Length < 1 || args.Length > 2 || (args.Length == 2 && args[1] != "--documents")) throw new ArgumentException("One model path required");
    var path = Path.GetFullPath(args[0]);
    Database database = Directory.Exists(path)
        ? TmdlSerializer.DeserializeDatabaseFromFolder(path)
        : TomJson.DeserializeDatabase(File.ReadAllText(path));
    var serialized = TomJson.SerializeDatabase(database);
    var parsed = JsonNode.Parse(serialized)!;
    ExpandDefaults(parsed, database);
    // Unknown JSON properties must survive TOM. Structural property loss fails.
    if (File.Exists(path))
    {
        var original = JsonNode.Parse(File.ReadAllText(path))!;
        // TOM omits a database ID equal to its name. This is the only
        // permitted omitted property, explicitly restored in the evidence.
        if (original["id"] != null && parsed["id"] == null && JsonNode.DeepEquals(original["id"], parsed["name"]))
            parsed["id"] = original["id"]!.DeepClone();
        VerifySubset(original, parsed);
    }
    var temporary = Path.Combine(Path.GetTempPath(), "pbibrain-tom-" + Guid.NewGuid().ToString("N"));
    Dictionary<string, string>? documents = null;
    try
    {
        TmdlSerializer.SerializeDatabaseToFolder(database, temporary);
        var roundtrip = TomJson.SerializeDatabase(TmdlSerializer.DeserializeDatabaseFromFolder(temporary));
        var roundtripNode = JsonNode.Parse(roundtrip)!;
        ExpandDefaults(roundtripNode, TmdlSerializer.DeserializeDatabaseFromFolder(temporary));
        if (parsed["id"] != null && roundtripNode["id"] == null && JsonNode.DeepEquals(parsed["id"], roundtripNode["name"]))
            roundtripNode["id"] = parsed["id"]!.DeepClone();
        if (!JsonNode.DeepEquals(parsed, roundtripNode))
            throw new InvalidOperationException("TOM roundtrip changed properties");
        if (args.Length == 2)
            documents = Directory.GetFiles(temporary, "*.tmdl", SearchOption.AllDirectories)
                .OrderBy(file => file, StringComparer.Ordinal).ToDictionary(file => Path.GetRelativePath(temporary, file).Replace('\\', '/'), File.ReadAllText);
    }
    finally { if (Directory.Exists(temporary)) Directory.Delete(temporary, true); }
    Console.WriteLine(Json.Serialize(new { adapter_version = 1, status = "PASSED", roundtrip_verified = true,
        provenance = "Microsoft.AnalysisServices/19.114.12/TOM+TMDL", database = parsed, tmdl_documents = documents }));
}
catch (Exception error)
{
    Console.WriteLine(Json.Serialize(new { adapter_version = 1, status = "FAILED", error = error.Message }));
    Environment.ExitCode = 2;
}

static void VerifySubset(JsonNode? original, JsonNode? serialized)
{
    if (original is JsonObject properties)
    {
        if (serialized is not JsonObject result) throw new InvalidOperationException("Metadata type changed");
        foreach (var property in properties)
        {
            if (!result.ContainsKey(property.Key)) throw new InvalidOperationException("Unrecognized/dropped property: " + property.Key);
            VerifySubset(property.Value, result[property.Key]);
        }
    }
    else if (original is JsonArray array)
    {
        if (serialized is not JsonArray result || array.Count != result.Count)
            throw new InvalidOperationException("Metadata collection changed");
        // TOM collection order may normalize; retain every exact member.
        foreach (var item in array)
        {
            var matches = result.Where(value => item is JsonObject obj && obj["name"] != null
                ? JsonNode.DeepEquals(obj["name"], value?["name"]) : JsonNode.DeepEquals(item, value)).ToList();
            if (matches.Count != 1) throw new InvalidOperationException("Metadata collection identity ambiguous");
            VerifySubset(item, matches[0]);
        }
    }
    else if (!JsonNode.DeepEquals(original, serialized)) throw new InvalidOperationException("Metadata value normalized without permission");
}

static void ExpandDefaults(JsonNode node, Database database)
{
    var model = node["model"]!;
    foreach (var relation in database.Model.Relationships.OfType<SingleColumnRelationship>())
    {
        var item = model["relationships"]!.AsArray().Single(value => value!["name"]!.GetValue<string>() == relation.Name)!;
        item["isActive"] = relation.IsActive;
        item["crossFilteringBehavior"] = EnumText(relation.CrossFilteringBehavior);
        item["securityFilteringBehavior"] = EnumText(relation.SecurityFilteringBehavior);
        item["fromCardinality"] = EnumText(relation.FromCardinality);
        item["toCardinality"] = EnumText(relation.ToCardinality);
        item["relyOnReferentialIntegrity"] = relation.RelyOnReferentialIntegrity;
    }
    foreach (var table in database.Model.Tables)
    {
        var item = model["tables"]!.AsArray().Single(value => value!["name"]!.GetValue<string>() == table.Name)!;
        item["isHidden"] = table.IsHidden;
        foreach (var column in table.Columns)
        {
            var child = item["columns"]!.AsArray().Single(value => value!["name"]!.GetValue<string>() == column.Name)!;
            child["isHidden"] = column.IsHidden;
            child["summarizeBy"] = EnumText(column.SummarizeBy);
        }
        foreach (var measure in table.Measures)
        {
            var child = item["measures"]!.AsArray().Single(value => value!["name"]!.GetValue<string>() == measure.Name)!;
            child["isHidden"] = measure.IsHidden;
        }
    }
}

static string EnumText(object value)
{
    var text = value.ToString()!;
    return char.ToLowerInvariant(text[0]) + text.Substring(1);
}
