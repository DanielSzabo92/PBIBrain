using Microsoft.AnalysisServices.Tabular;
using System.Text.Json.Nodes;
using Json = System.Text.Json.JsonSerializer;

// Bridge command "write-model" (DEV_CENTER_TECHNICAL_DESIGN.md section 9.1).
// Applies ordered Change Plan operations to a TOM model in memory, serializes
// canonical TMDL into a candidate folder, preserves non-TMDL files, verifies
// roundtrip integrity, and returns changed/added/removed files.
static class ModelWriter
{
    sealed class ModelWriterException : Exception
    {
        public string Code { get; }
        public ModelWriterException(string code, string message) : base(message) { Code = code; }
    }

    public static int Run(string[] args, TextReader input, TextWriter output)
    {
        string? modelPath = null;
        string? candidatePath = null;
        JsonArray? operations = null;

        var stdinText = Console.IsInputRedirected ? input.ReadToEnd().TrimStart('\uFEFF') : "";
        if (args.Length >= 3)
        {
            modelPath = args[1];
            candidatePath = args[2];
            if (!string.IsNullOrWhiteSpace(stdinText))
            {
                var parsed = JsonNode.Parse(stdinText);
                if (parsed is JsonArray arr) operations = arr;
                else if (parsed is JsonObject obj && obj["operations"] is JsonArray opsArr) operations = opsArr;
            }
        }
        else if (!string.IsNullOrWhiteSpace(stdinText))
        {
            var parsed = JsonNode.Parse(stdinText);
            if (parsed is JsonObject obj)
            {
                modelPath = obj["model"]?.GetValue<string>() ?? obj["model_path"]?.GetValue<string>();
                candidatePath = obj["candidate"]?.GetValue<string>() ?? obj["candidate_path"]?.GetValue<string>();
                operations = obj["operations"] as JsonArray;
            }
        }

        if (string.IsNullOrWhiteSpace(modelPath) || string.IsNullOrWhiteSpace(candidatePath))
        {
            return Fail(output, "invalid_request", "Both model path and candidate path are required");
        }

        var modelFull = Path.GetFullPath(modelPath).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        var candidateFull = Path.GetFullPath(candidatePath).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);

        // Safety guard: Destination must not be definition folder or inside it
        string defFolder;
        if (Path.GetFileName(modelFull).Equals("definition", StringComparison.OrdinalIgnoreCase))
        {
            defFolder = modelFull;
        }
        else if (Directory.Exists(Path.Combine(modelFull, "definition")))
        {
            defFolder = Path.Combine(modelFull, "definition");
        }
        else
        {
            defFolder = modelFull;
        }

        if (candidateFull.Equals(defFolder, StringComparison.OrdinalIgnoreCase) ||
            candidateFull.StartsWith(defFolder + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) ||
            candidateFull.StartsWith(defFolder + Path.AltDirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
        {
            return Fail(output, "destination_is_definition_folder",
                "Destination path cannot be the model definition folder or inside it.");
        }

        if (!Directory.Exists(modelFull))
        {
            return Fail(output, "not_found", $"Model directory not found: {modelFull}");
        }

        try
        {
            // 1. Collect non-TMDL files in model and candidate to ensure preservation
            var nonTmdlFiles = new Dictionary<string, byte[]>(StringComparer.OrdinalIgnoreCase);
            foreach (var file in Directory.GetFiles(modelFull, "*", SearchOption.AllDirectories))
            {
                if (!file.EndsWith(".tmdl", StringComparison.OrdinalIgnoreCase))
                {
                    var rel = Path.GetRelativePath(modelFull, file);
                    nonTmdlFiles[rel] = File.ReadAllBytes(file);
                }
            }
            if (Directory.Exists(candidateFull))
            {
                foreach (var file in Directory.GetFiles(candidateFull, "*", SearchOption.AllDirectories))
                {
                    if (!file.EndsWith(".tmdl", StringComparison.OrdinalIgnoreCase))
                    {
                        var rel = Path.GetRelativePath(candidateFull, file);
                        if (!nonTmdlFiles.ContainsKey(rel))
                            nonTmdlFiles[rel] = File.ReadAllBytes(file);
                    }
                }
            }

            // 2. Deserialize model to memory TOM
            var database = TmdlSerializer.DeserializeDatabaseFromFolder(modelFull);

            // 3. Apply ordered operations
            if (operations != null)
            {
                foreach (var node in operations)
                {
                    if (node is JsonObject opObj)
                    {
                        ApplyOperation(database, opObj);
                    }
                }
            }

            // 4. Validate lineage tags across the entire model
            ValidateModelLineageTags(database);

            // 5. Serialize candidate database to candidate folder
            if (!Directory.Exists(candidateFull))
            {
                Directory.CreateDirectory(candidateFull);
            }
            CanonicalTmdl.SerializeToFolder(database, candidateFull);

            // 6. Restore / preserve non-TMDL files
            foreach (var kvp in nonTmdlFiles)
            {
                var targetFile = Path.Combine(candidateFull, kvp.Key);
                var targetDir = Path.GetDirectoryName(targetFile);
                if (!string.IsNullOrEmpty(targetDir) && !Directory.Exists(targetDir))
                    Directory.CreateDirectory(targetDir);
                File.WriteAllBytes(targetFile, kvp.Value);
            }

            // 7. Verify roundtrip integrity by reloading candidate
            var roundtrip = TmdlSerializer.DeserializeDatabaseFromFolder(candidateFull);
            if (roundtrip?.Model == null)
                throw new ModelWriterException("roundtrip_failed", "Reloading candidate model failed");

            // 8. Compute changed, added, removed .tmdl files
            var baselineTmdl = Directory.GetFiles(modelFull, "*.tmdl", SearchOption.AllDirectories)
                .ToDictionary(f => Path.GetRelativePath(modelFull, f).Replace('\\', '/'), f => f, StringComparer.Ordinal);
            var candidateTmdl = Directory.GetFiles(candidateFull, "*.tmdl", SearchOption.AllDirectories)
                .ToDictionary(f => Path.GetRelativePath(candidateFull, f).Replace('\\', '/'), f => f, StringComparer.Ordinal);

            var added = candidateTmdl.Keys.Except(baselineTmdl.Keys, StringComparer.Ordinal).OrderBy(x => x).ToList();
            var removed = baselineTmdl.Keys.Except(candidateTmdl.Keys, StringComparer.Ordinal).OrderBy(x => x).ToList();
            var changed = new List<string>();

            foreach (var common in baselineTmdl.Keys.Intersect(candidateTmdl.Keys, StringComparer.Ordinal).OrderBy(x => x))
            {
                var bBytes = File.ReadAllBytes(baselineTmdl[common]);
                var cBytes = File.ReadAllBytes(candidateTmdl[common]);
                if (!bBytes.SequenceEqual(cBytes))
                {
                    changed.Add(common);
                }
            }

            output.WriteLine(Json.Serialize(new
            {
                adapter_version = 1,
                status = "PASSED",
                command = "write-model",
                changed_files = changed,
                added_files = added,
                removed_files = removed
            }));
            return 0;
        }
        catch (ModelWriterException ex)
        {
            return Fail(output, ex.Code, ex.Message);
        }
        catch (Exception ex)
        {
            return Fail(output, "write_failed", ex.Message);
        }
    }

    private static void ApplyOperation(Database database, JsonObject op)
    {
        var opType = op["op"]?.GetValue<string>();
        var objType = op["object_type"]?.GetValue<string>();
        var name = op["name"]?.GetValue<string>() ?? "";
        var tableName = op["table"]?.GetValue<string>();
        var properties = op["properties"] as JsonObject;
        var lineageTag = op["lineage_tag"]?.GetValue<string>();

        switch (opType)
        {
            case "CREATE":
                ApplyCreate(database, objType, name, tableName, properties, lineageTag, op);
                break;
            case "DELETE":
                ApplyDelete(database, objType, name, tableName);
                break;
            case "RENAME":
            case "RENAME_PAIR":
                var newName = op["new_name"]?.GetValue<string>() ?? name;
                ApplyRename(database, objType, name, tableName, newName);
                break;
            case "SET_PROPERTIES":
            case "REPLACE":
                ApplySetProperties(database, objType, name, tableName, properties, lineageTag);
                break;
            case "REWRITE_EXPRESSION":
                var propName = op["property"]?.GetValue<string>() ?? "expression";
                var newText = op["new_text"]?.GetValue<string>() ?? "";
                ApplyRewriteExpression(database, objType, name, tableName, propName, newText);
                break;
        }
    }

    private static void ApplyCreate(Database db, string? objType, string name, string? tableName, JsonObject? props, string? lineageTag, JsonObject op)
    {
        var model = db.Model;
        var subtype = op["subtype"]?.GetValue<string>();

        switch (objType)
        {
            case "table":
                var table = new Table { Name = name };
                if (props != null)
                {
                    if (props["description"] != null) table.Description = props["description"]?.GetValue<string>();
                    if (props["is_hidden"] != null) table.IsHidden = props["is_hidden"]!.GetValue<bool>();
                    if (props["data_category"] != null) table.DataCategory = props["data_category"]?.GetValue<string>();
                }
                if (!string.IsNullOrEmpty(lineageTag)) table.LineageTag = lineageTag;

                if (subtype == "calculation_group" || props?["calculation_group"] != null)
                {
                    table.CalculationGroup = new CalculationGroup();
                    table.Partitions.Add(new Partition
                    {
                        Name = name,
                        Mode = ModeType.Import,
                        Source = new CalculationGroupSource()
                    });
                }
                else if (props?["expression"] != null)
                {
                    table.Partitions.Add(new Partition
                    {
                        Name = name,
                        Source = new CalculatedPartitionSource { Expression = props["expression"]!.GetValue<string>() }
                    });
                }
                else
                {
                    var mExpr = props?["partition_expression"]?.GetValue<string>() ??
                                $"let\n    Source = #table({{\"{name}\"}}, {{}})\nin\n    Source";
                    table.Partitions.Add(new Partition
                    {
                        Name = name,
                        Mode = ModeType.Import,
                        Source = new MPartitionSource { Expression = mExpr }
                    });
                }
                model.Tables.Add(table);
                break;

            case "column":
                var colTable = model.Tables.Find(tableName)
                    ?? throw new ModelWriterException("table_not_found", $"Table not found: {tableName}");
                Column col;
                var isCalculated = subtype == "calculated" || props?["expression"] != null || props?["type"]?.GetValue<string>() == "calculated";
                if (isCalculated)
                {
                    col = new CalculatedColumn
                    {
                        Name = name,
                        Expression = props?["expression"]?.GetValue<string>() ?? ""
                    };
                }
                else
                {
                    var srcCol = props?["source_column"]?.GetValue<string>() ?? props?["sourceColumn"]?.GetValue<string>() ?? name;
                    col = new DataColumn
                    {
                        Name = name,
                        SourceColumn = srcCol
                    };
                }

                if (props != null)
                {
                    if (props["data_type"] != null || props["dataType"] != null)
                        col.DataType = ParseDataType(props["data_type"]?.GetValue<string>() ?? props["dataType"]?.GetValue<string>());
                    if (props["format_string"] != null || props["formatString"] != null)
                        col.FormatString = props["format_string"]?.GetValue<string>() ?? props["formatString"]?.GetValue<string>();
                    if (props["is_hidden"] != null || props["isHidden"] != null)
                        col.IsHidden = (props["is_hidden"] ?? props["isHidden"])!.GetValue<bool>();
                    if (props["display_folder"] != null || props["displayFolder"] != null)
                        col.DisplayFolder = props["display_folder"]?.GetValue<string>() ?? props["displayFolder"]?.GetValue<string>();
                    if (props["summarize_by"] != null || props["summarizeBy"] != null)
                        col.SummarizeBy = ParseSummarizeBy(props["summarize_by"]?.GetValue<string>() ?? props["summarizeBy"]?.GetValue<string>());
                    if (props["sort_by_column"] != null)
                    {
                        var sColName = props["sort_by_column"]?.GetValue<string>();
                        if (!string.IsNullOrEmpty(sColName))
                            col.SortByColumn = colTable.Columns.Find(sColName);
                    }
                }
                if (!string.IsNullOrEmpty(lineageTag)) col.LineageTag = lineageTag;
                colTable.Columns.Add(col);
                break;

            case "measure":
                var mTable = model.Tables.Find(tableName)
                    ?? throw new ModelWriterException("table_not_found", $"Table not found: {tableName}");
                var expr = props?["expression"]?.GetValue<string>() ?? "";
                var measure = new Measure { Name = name, Expression = expr };
                if (props != null)
                {
                    if (props["format_string"] != null || props["formatString"] != null)
                        measure.FormatString = props["format_string"]?.GetValue<string>() ?? props["formatString"]?.GetValue<string>();
                    if (props["description"] != null) measure.Description = props["description"]?.GetValue<string>();
                    if (props["is_hidden"] != null || props["isHidden"] != null)
                        measure.IsHidden = (props["is_hidden"] ?? props["isHidden"])!.GetValue<bool>();
                    if (props["display_folder"] != null || props["displayFolder"] != null)
                        measure.DisplayFolder = props["display_folder"]?.GetValue<string>() ?? props["displayFolder"]?.GetValue<string>();
                }
                if (!string.IsNullOrEmpty(lineageTag)) measure.LineageTag = lineageTag;
                mTable.Measures.Add(measure);
                break;

            case "relationship":
                var rel = new SingleColumnRelationship();
                rel.Name = name ?? Guid.NewGuid().ToString("N");
                if (props != null)
                {
                    if (props["ends"] is JsonArray endsArr && endsArr.Count >= 2)
                    {
                        var end0 = endsArr[0] as JsonArray;
                        var end1 = endsArr[1] as JsonArray;
                        if (end0 != null && end1 != null && end0.Count >= 2 && end1.Count >= 2)
                        {
                            var fTable = end0[0]?.GetValue<string>();
                            var fCol = end0[1]?.GetValue<string>();
                            var tTable = end1[0]?.GetValue<string>();
                            var tCol = end1[1]?.GetValue<string>();

                            rel.FromColumn = model.Tables.Find(fTable)?.Columns.Find(fCol);
                            rel.ToColumn = model.Tables.Find(tTable)?.Columns.Find(tCol);
                        }
                    }
                    else
                    {
                        var fromTable = props["from_table"]?.GetValue<string>() ?? props["fromTable"]?.GetValue<string>();
                        var fromCol = props["from_column"]?.GetValue<string>() ?? props["fromColumn"]?.GetValue<string>();
                        var toTable = props["to_table"]?.GetValue<string>() ?? props["toTable"]?.GetValue<string>();
                        var toCol = props["to_column"]?.GetValue<string>() ?? props["toColumn"]?.GetValue<string>();

                        rel.FromColumn = model.Tables.Find(fromTable)?.Columns.Find(fromCol);
                        rel.ToColumn = model.Tables.Find(toTable)?.Columns.Find(toCol);
                    }

                    if (props["is_active"] != null || props["isActive"] != null)
                        rel.IsActive = (props["is_active"] ?? props["isActive"])!.GetValue<bool>();
                    if (props["cross_filtering_behavior"] != null || props["crossFilteringBehavior"] != null)
                        rel.CrossFilteringBehavior = ParseCrossFilter(props["cross_filtering_behavior"]?.GetValue<string>() ?? props["crossFilteringBehavior"]?.GetValue<string>());
                }
                model.Relationships.Add(rel);
                break;

            case "hierarchy":
                var hTable = model.Tables.Find(tableName)
                    ?? throw new ModelWriterException("table_not_found", $"Table not found: {tableName}");
                var hierarchy = new Hierarchy { Name = name };
                if (props != null)
                {
                    if (props["description"] != null) hierarchy.Description = props["description"]?.GetValue<string>();
                    if (props["display_folder"] != null || props["displayFolder"] != null)
                        hierarchy.DisplayFolder = props["display_folder"]?.GetValue<string>() ?? props["displayFolder"]?.GetValue<string>();
                    if (props["levels"] is JsonArray levelsArr)
                    {
                        int ord = 0;
                        foreach (var lvlNode in levelsArr)
                        {
                            var lvlName = lvlNode?.GetValue<string>() ?? "";
                            var colObj = hTable.Columns.Find(lvlName);
                            hierarchy.Levels.Add(new Level { Name = lvlName, Ordinal = ord++, Column = colObj });
                        }
                    }
                }
                if (!string.IsNullOrEmpty(lineageTag)) hierarchy.LineageTag = lineageTag;
                hTable.Hierarchies.Add(hierarchy);
                break;

            case "calculation_item":
                var ciTable = model.Tables.Find(tableName)
                    ?? throw new ModelWriterException("table_not_found", $"Table not found: {tableName}");
                if (ciTable.CalculationGroup == null) ciTable.CalculationGroup = new CalculationGroup();
                var ci = new CalculationItem
                {
                    Name = name,
                    Expression = props?["expression"]?.GetValue<string>() ?? "",
                    Ordinal = props?["ordinal"]?.GetValue<int>() ?? 0
                };
                var fmtExpr = props?["format_string_expression"]?.GetValue<string>();
                if (!string.IsNullOrEmpty(fmtExpr))
                {
                    ci.FormatStringDefinition = new FormatStringDefinition { Expression = fmtExpr };
                }
                ciTable.CalculationGroup.CalculationItems.Add(ci);
                break;

            case "role":
                var role = new ModelRole { Name = name };
                if (props?["model_permission"] != null)
                    role.ModelPermission = ParseModelPermission(props["model_permission"]!.GetValue<string>());
                else
                    role.ModelPermission = ModelPermission.Read;

                if (props?["role_filters"] is JsonObject filtersObj)
                {
                    foreach (var kvp in filtersObj)
                    {
                        var targetTbl = model.Tables.Find(kvp.Key);
                        if (targetTbl != null)
                        {
                            role.TablePermissions.Add(new TablePermission
                            {
                                Table = targetTbl,
                                FilterExpression = kvp.Value?.GetValue<string>()
                            });
                        }
                    }
                }
                model.Roles.Add(role);
                break;

            case "partition":
                var pTable = model.Tables.Find(tableName)
                    ?? throw new ModelWriterException("table_not_found", $"Table not found: {tableName}");
                var part = new Partition
                {
                    Name = name,
                    Mode = ModeType.Import,
                    Source = new MPartitionSource { Expression = props?["expression"]?.GetValue<string>() ?? "" }
                };
                pTable.Partitions.Add(part);
                break;

            case "expression":
                var nExpr = new NamedExpression
                {
                    Name = name,
                    Expression = props?["expression"]?.GetValue<string>() ?? "",
                    Kind = ExpressionKind.M
                };
                if (!string.IsNullOrEmpty(lineageTag)) nExpr.LineageTag = lineageTag;
                model.Expressions.Add(nExpr);
                break;

            case "function":
                // TOM blocks UDF below compatibility level 1702
                if (db.CompatibilityLevel < 1702)
                {
                    throw new ModelWriterException("udf_compatibility",
                        $"User Defined Functions require compatibility level 1702 or higher (model is {db.CompatibilityLevel}).");
                }
                var func = new Function
                {
                    Name = name,
                    Expression = props?["expression"]?.GetValue<string>() ?? ""
                };
                if (!string.IsNullOrEmpty(lineageTag)) func.LineageTag = lineageTag;
                model.Functions.Add(func);
                break;
        }
    }

    private static void ApplyDelete(Database db, string? objType, string name, string? tableName)
    {
        var model = db.Model;
        switch (objType)
        {
            case "table":
                var t = model.Tables.Find(name);
                if (t != null) model.Tables.Remove(t);
                break;
            case "column":
                var colTable = model.Tables.Find(tableName);
                var c = colTable?.Columns.Find(name);
                if (c != null) colTable!.Columns.Remove(c);
                break;
            case "measure":
                var mTable = model.Tables.Find(tableName);
                var m = mTable?.Measures.Find(name);
                if (m != null) mTable!.Measures.Remove(m);
                break;
            case "relationship":
                var rel = model.Relationships.Find(name) ??
                          model.Relationships.FirstOrDefault(r => r is SingleColumnRelationship scr &&
                              $"{scr.FromTable?.Name}[{scr.FromColumn?.Name}]->{scr.ToTable?.Name}[{scr.ToColumn?.Name}]"
                              .Equals(name, StringComparison.OrdinalIgnoreCase));
                if (rel != null) model.Relationships.Remove(rel);
                break;
            case "hierarchy":
                var hTable = model.Tables.Find(tableName);
                var h = hTable?.Hierarchies.Find(name);
                if (h != null) hTable!.Hierarchies.Remove(h);
                break;
            case "calculation_item":
                var ciTable = model.Tables.Find(tableName);
                var ci = ciTable?.CalculationGroup?.CalculationItems.Find(name);
                if (ci != null) ciTable!.CalculationGroup!.CalculationItems.Remove(ci);
                break;
            case "role":
                var role = model.Roles.Find(name);
                if (role != null) model.Roles.Remove(role);
                break;
            case "partition":
                var pTable = model.Tables.Find(tableName);
                var part = pTable?.Partitions.Find(name);
                if (part != null) pTable!.Partitions.Remove(part);
                break;
            case "expression":
                var expr = model.Expressions.Find(name);
                if (expr != null) model.Expressions.Remove(expr);
                break;
            case "function":
                var func = model.Functions.Find(name);
                if (func != null) model.Functions.Remove(func);
                break;
        }
    }

    private static void ApplyRename(Database db, string? objType, string oldName, string? tableName, string newName)
    {
        var model = db.Model;
        switch (objType)
        {
            case "table":
                var t = model.Tables.Find(oldName);
                if (t != null) t.Name = newName;
                break;
            case "column":
                var colTable = model.Tables.Find(tableName);
                var c = colTable?.Columns.Find(oldName);
                if (c != null) c.Name = newName;
                break;
            case "measure":
                var mTable = model.Tables.Find(tableName);
                var m = mTable?.Measures.Find(oldName);
                if (m != null) m.Name = newName;
                break;
            case "hierarchy":
                var hTable = model.Tables.Find(tableName);
                var h = hTable?.Hierarchies.Find(oldName);
                if (h != null) h.Name = newName;
                break;
            case "calculation_item":
                var ciTable = model.Tables.Find(tableName);
                var ci = ciTable?.CalculationGroup?.CalculationItems.Find(oldName);
                if (ci != null) ci.Name = newName;
                break;
            case "role":
                var r = model.Roles.Find(oldName);
                if (r != null) r.Name = newName;
                break;
            case "expression":
                var e = model.Expressions.Find(oldName);
                if (e != null) e.Name = newName;
                break;
            case "function":
                var f = model.Functions.Find(oldName);
                if (f != null) f.Name = newName;
                break;
        }
    }

    private static void ApplySetProperties(Database db, string? objType, string name, string? tableName, JsonObject? props, string? lineageTag)
    {
        if (props == null && string.IsNullOrEmpty(lineageTag)) return;
        var model = db.Model;

        switch (objType)
        {
            case "table":
                var t = model.Tables.Find(name);
                if (t != null)
                {
                    if (props != null)
                    {
                        if (props["description"] != null) t.Description = props["description"]?.GetValue<string>();
                        if (props["is_hidden"] != null || props["isHidden"] != null)
                            t.IsHidden = (props["is_hidden"] ?? props["isHidden"])!.GetValue<bool>();
                        if (props["data_category"] != null || props["dataCategory"] != null)
                            t.DataCategory = (props["data_category"] ?? props["dataCategory"])?.GetValue<string>();
                    }
                    if (!string.IsNullOrEmpty(lineageTag)) t.LineageTag = lineageTag;
                }
                break;

            case "column":
                var colTable = model.Tables.Find(tableName);
                var c = colTable?.Columns.Find(name);
                if (c != null)
                {
                    if (props != null)
                    {
                        if (props["data_type"] != null || props["dataType"] != null)
                            c.DataType = ParseDataType((props["data_type"] ?? props["dataType"])?.GetValue<string>());
                        if (props["format_string"] != null || props["formatString"] != null)
                            c.FormatString = (props["format_string"] ?? props["formatString"])?.GetValue<string>();
                        if (props["is_hidden"] != null || props["isHidden"] != null)
                            c.IsHidden = (props["is_hidden"] ?? props["isHidden"])!.GetValue<bool>();
                        if (props["display_folder"] != null || props["displayFolder"] != null)
                            c.DisplayFolder = (props["display_folder"] ?? props["displayFolder"])?.GetValue<string>();
                        if (props["summarize_by"] != null || props["summarizeBy"] != null)
                            c.SummarizeBy = ParseSummarizeBy((props["summarize_by"] ?? props["summarizeBy"])?.GetValue<string>());
                        if (props["description"] != null) c.Description = props["description"]?.GetValue<string>();
                        if (props["data_category"] != null || props["dataCategory"] != null)
                            c.DataCategory = (props["data_category"] ?? props["dataCategory"])?.GetValue<string>();
                        if (props["is_key"] != null || props["isKey"] != null)
                            c.IsKey = (props["is_key"] ?? props["isKey"])!.GetValue<bool>();
                        if (props["expression"] != null && c is CalculatedColumn calc)
                            calc.Expression = props["expression"]!.GetValue<string>();
                        if (props["sort_by_column"] != null)
                        {
                            var sName = props["sort_by_column"]?.GetValue<string>();
                            c.SortByColumn = !string.IsNullOrEmpty(sName) ? colTable?.Columns.Find(sName) : null;
                        }
                    }
                    if (!string.IsNullOrEmpty(lineageTag)) c.LineageTag = lineageTag;
                }
                break;

            case "measure":
                var mTable = model.Tables.Find(tableName);
                var m = mTable?.Measures.Find(name);
                if (m != null)
                {
                    if (props != null)
                    {
                        if (props["expression"] != null) m.Expression = props["expression"]!.GetValue<string>();
                        if (props["format_string"] != null || props["formatString"] != null)
                            m.FormatString = (props["format_string"] ?? props["formatString"])?.GetValue<string>();
                        if (props["description"] != null) m.Description = props["description"]?.GetValue<string>();
                        if (props["is_hidden"] != null || props["isHidden"] != null)
                            m.IsHidden = (props["is_hidden"] ?? props["isHidden"])!.GetValue<bool>();
                        if (props["display_folder"] != null || props["displayFolder"] != null)
                            m.DisplayFolder = (props["display_folder"] ?? props["displayFolder"])?.GetValue<string>();
                    }
                    if (!string.IsNullOrEmpty(lineageTag)) m.LineageTag = lineageTag;
                }
                break;

            case "relationship":
                var rel = model.Relationships.Find(name);
                if (rel != null && props != null)
                {
                    if (props["is_active"] != null || props["isActive"] != null)
                        rel.IsActive = (props["is_active"] ?? props["isActive"])!.GetValue<bool>();
                    if (props["cross_filtering_behavior"] != null || props["crossFilteringBehavior"] != null)
                        rel.CrossFilteringBehavior = ParseCrossFilter((props["cross_filtering_behavior"] ?? props["crossFilteringBehavior"])?.GetValue<string>());
                }
                break;

            case "calculation_item":
                var ciTable = model.Tables.Find(tableName);
                var ci = ciTable?.CalculationGroup?.CalculationItems.Find(name);
                if (ci != null && props != null)
                {
                    if (props["expression"] != null) ci.Expression = props["expression"]!.GetValue<string>();
                    if (props["ordinal"] != null) ci.Ordinal = props["ordinal"]!.GetValue<int>();
                    if (props["format_string_expression"] != null)
                    {
                        if (ci.FormatStringDefinition == null) ci.FormatStringDefinition = new FormatStringDefinition();
                        ci.FormatStringDefinition.Expression = props["format_string_expression"]?.GetValue<string>();
                    }
                }
                break;

            case "role":
                var role = model.Roles.Find(name);
                if (role != null && props != null)
                {
                    if (props["model_permission"] != null)
                        role.ModelPermission = ParseModelPermission(props["model_permission"]!.GetValue<string>());
                    if (props["role_filters"] is JsonObject filters)
                    {
                        foreach (var kvp in filters)
                        {
                            var existing = role.TablePermissions.FirstOrDefault(p => p.Table?.Name == kvp.Key);
                            if (existing != null) existing.FilterExpression = kvp.Value?.GetValue<string>();
                            else
                            {
                                var tObj = model.Tables.Find(kvp.Key);
                                if (tObj != null) role.TablePermissions.Add(new TablePermission { Table = tObj, FilterExpression = kvp.Value?.GetValue<string>() });
                            }
                        }
                    }
                }
                break;

            case "expression":
                var expr = model.Expressions.Find(name);
                if (expr != null)
                {
                    if (props?["expression"] != null) expr.Expression = props["expression"]!.GetValue<string>();
                    if (!string.IsNullOrEmpty(lineageTag)) expr.LineageTag = lineageTag;
                }
                break;

            case "function":
                var func = model.Functions.Find(name);
                if (func != null)
                {
                    if (props?["expression"] != null) func.Expression = props["expression"]!.GetValue<string>();
                    if (!string.IsNullOrEmpty(lineageTag)) func.LineageTag = lineageTag;
                }
                break;
        }
    }

    private static void ApplyRewriteExpression(Database db, string? objType, string name, string? tableName, string property, string newText)
    {
        var model = db.Model;
        if (property == "expression")
        {
            switch (objType)
            {
                case "measure":
                    var m = model.Tables.Find(tableName)?.Measures.Find(name);
                    if (m != null) m.Expression = newText;
                    break;
                case "column":
                    var c = model.Tables.Find(tableName)?.Columns.Find(name);
                    if (c is CalculatedColumn calc) calc.Expression = newText;
                    break;
                case "table":
                    var t = model.Tables.Find(name);
                    var p = t?.Partitions.FirstOrDefault(pt => pt.Source is CalculatedPartitionSource);
                    if (p?.Source is CalculatedPartitionSource cp) cp.Expression = newText;
                    break;
                case "calculation_item":
                    var ci = model.Tables.Find(tableName)?.CalculationGroup?.CalculationItems.Find(name);
                    if (ci != null) ci.Expression = newText;
                    break;
                case "function":
                    var func = model.Functions.Find(name);
                    if (func != null) func.Expression = newText;
                    break;
                case "expression":
                    var expr = model.Expressions.Find(name);
                    if (expr != null) expr.Expression = newText;
                    break;
            }
        }
        else if (property == "format_string_expression")
        {
            var ci = model.Tables.Find(tableName)?.CalculationGroup?.CalculationItems.Find(name);
            if (ci != null)
            {
                if (ci.FormatStringDefinition == null) ci.FormatStringDefinition = new FormatStringDefinition();
                ci.FormatStringDefinition.Expression = newText;
            }
        }
        else if (property.StartsWith("role_filters/"))
        {
            var role = model.Roles.Find(name);
            var targetTable = property.Substring("role_filters/".Length);
            var perm = role?.TablePermissions.FirstOrDefault(tp => tp.Table?.Name.Equals(targetTable, StringComparison.OrdinalIgnoreCase) == true);
            if (perm != null)
            {
                perm.FilterExpression = newText;
            }
        }
    }

    private static void ValidateModelLineageTags(Database db)
    {
        var seenTags = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        void CheckTag(string? tag, string objDesc)
        {
            if (string.IsNullOrEmpty(tag)) return;
            if (!seenTags.Add(tag))
            {
                throw new ModelWriterException("duplicate_lineage_tag",
                    $"Duplicate lineageTag '{tag}' found on {objDesc}. LineageTags must be unique across the entire model.");
            }
        }

        var model = db.Model;
        foreach (var t in model.Tables)
        {
            CheckTag(t.LineageTag, $"Table '{t.Name}'");
            foreach (var c in t.Columns) CheckTag(c.LineageTag, $"Column '{t.Name}[{c.Name}]'");
            foreach (var m in t.Measures) CheckTag(m.LineageTag, $"Measure '{t.Name}[{m.Name}]'");
            foreach (var h in t.Hierarchies) CheckTag(h.LineageTag, $"Hierarchy '{t.Name}[{h.Name}]'");
        }
        foreach (var e in model.Expressions) CheckTag(e.LineageTag, $"Expression '{e.Name}'");
        foreach (var f in model.Functions) CheckTag(f.LineageTag, $"Function '{f.Name}'");
    }

    private static DataType ParseDataType(string? typeStr)
    {
        if (string.IsNullOrWhiteSpace(typeStr)) return DataType.String;
        return typeStr.ToLowerInvariant() switch
        {
            "int64" or "integer" or "int" => DataType.Int64,
            "double" or "float" => DataType.Double,
            "decimal" or "currency" => DataType.Decimal,
            "boolean" or "bool" => DataType.Boolean,
            "datetime" or "date" => DataType.DateTime,
            "binary" => DataType.Binary,
            _ => DataType.String
        };
    }

    private static AggregateFunction ParseSummarizeBy(string? val)
    {
        if (string.IsNullOrWhiteSpace(val)) return AggregateFunction.Default;
        return Enum.TryParse<AggregateFunction>(val, true, out var result) ? result : AggregateFunction.Default;
    }

    private static CrossFilteringBehavior ParseCrossFilter(string? val)
    {
        if (string.IsNullOrWhiteSpace(val)) return CrossFilteringBehavior.OneDirection;
        return Enum.TryParse<CrossFilteringBehavior>(val, true, out var result) ? result : CrossFilteringBehavior.OneDirection;
    }

    private static ModelPermission ParseModelPermission(string? val)
    {
        if (string.IsNullOrWhiteSpace(val)) return ModelPermission.Read;
        return Enum.TryParse<ModelPermission>(val, true, out var result) ? result : ModelPermission.Read;
    }

    private static int Fail(TextWriter output, string code, string message)
    {
        output.WriteLine(Json.Serialize(new
        {
            adapter_version = 1,
            status = "FAILED",
            command = "write-model",
            code = code,
            error = message
        }));
        return 2;
    }
}
