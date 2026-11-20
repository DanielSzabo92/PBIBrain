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

            // 2. Deserialize model to memory TOM (from definition/ when present so TMDLScripts/ is ignored)
            var database = TmdlSerializer.DeserializeDatabaseFromFolder(defFolder);

            // 3. Apply ordered operations, deferring cross-column references (sort_by_column) until all columns exist
            var deferredSortBy = new List<(string Table, string Column, string? SortBy)>();
            if (operations != null)
            {
                foreach (var node in operations)
                {
                    if (node is JsonObject opObj)
                    {
                        ApplyOperation(database, opObj, deferredSortBy);
                    }
                }
            }
            foreach (var (sTable, sCol, sTarget) in deferredSortBy)
            {
                var tbl = database.Model.Tables.Find(sTable);
                var colObj = tbl?.Columns.Find(sCol);
                if (colObj != null)
                {
                    colObj.SortByColumn = !string.IsNullOrEmpty(sTarget) ? tbl?.Columns.Find(sTarget) : null;
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

    private static void ApplyOperation(Database database, JsonObject op, List<(string Table, string Column, string? SortBy)> deferredSortBy)
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
                ApplyCreate(database, objType, name, tableName, properties, lineageTag, op, deferredSortBy);
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
                ApplySetProperties(database, objType, name, tableName, properties, lineageTag, deferredSortBy);
                break;
            case "REWRITE_EXPRESSION":
                var propName = op["property"]?.GetValue<string>() ?? "expression";
                var newText = op["new_text"]?.GetValue<string>() ?? "";
                ApplyRewriteExpression(database, objType, name, tableName, propName, newText);
                break;
        }
    }

    private static JsonNode? FirstProp(JsonObject? props, params string[] keys)
    {
        if (props == null) return null;
        foreach (var key in keys)
        {
            if (props.TryGetPropertyValue(key, out var val) && val != null)
                return val;
        }
        return null;
    }

    private static bool HasAnyProp(JsonObject? props, params string[] keys)
    {
        if (props == null) return false;
        foreach (var key in keys)
        {
            if (props.ContainsKey(key)) return true;
        }
        return false;
    }

    private static void ApplyAnnotations(ICollection<Annotation> target, JsonNode? node)
    {
        if (node is JsonObject obj)
        {
            foreach (var kvp in obj)
            {
                if (string.IsNullOrEmpty(kvp.Key)) continue;
                var val = kvp.Value?.GetValue<string>();
                var existing = target.FirstOrDefault(a => a.Name == kvp.Key);
                if (existing != null) existing.Value = val;
                else target.Add(new Annotation { Name = kvp.Key, Value = val });
            }
        }
        else if (node is JsonArray arr)
        {
            foreach (var item in arr)
            {
                if (item is JsonObject entry)
                {
                    var aName = entry["name"]?.GetValue<string>();
                    if (string.IsNullOrEmpty(aName)) continue;
                    var aVal = entry["value"]?.GetValue<string>();
                    var existing = target.FirstOrDefault(a => a.Name == aName);
                    if (existing != null) existing.Value = aVal;
                    else target.Add(new Annotation { Name = aName, Value = aVal });
                }
            }
        }
    }

    private static void ApplyCreate(Database db, string? objType, string name, string? tableName, JsonObject? props, string? lineageTag, JsonObject op, List<(string Table, string Column, string? SortBy)> deferredSortBy)
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
                    var hiddenNode = FirstProp(props, "is_hidden", "hidden", "isHidden");
                    if (hiddenNode != null) table.IsHidden = hiddenNode.GetValue<bool>();
                    var catNode = FirstProp(props, "data_category", "dataCategory");
                    if (catNode != null) table.DataCategory = catNode.GetValue<string>();
                    var privNode = FirstProp(props, "is_private", "isPrivate");
                    if (privNode != null) table.IsPrivate = privNode.GetValue<bool>();
                    var varOnlyNode = FirstProp(props, "show_as_variations_only", "showAsVariationsOnly");
                    if (varOnlyNode != null) table.ShowAsVariationsOnly = varOnlyNode.GetValue<bool>();
                    ApplyAnnotations(table.Annotations, props["annotations"]);
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
                    var mExpr = FirstProp(props, "partition_expression", "m_text")?.GetValue<string>() ??
                                $"let\n    Source = #table({{\"{name}\"}}, {{}})\nin\n    Source";
                    var partMode = ParseModeType(props?["mode"]?.GetValue<string>());
                    table.Partitions.Add(new Partition
                    {
                        Name = name,
                        Mode = partMode,
                        Source = new MPartitionSource { Expression = mExpr }
                    });
                }
                model.Tables.Add(table);
                break;

            case "column":
                var colTable = model.Tables.Find(tableName)
                    ?? throw new ModelWriterException("table_not_found", $"Table not found: {tableName}");
                Column col;
                var colTypeProp = FirstProp(props, "column_type", "type")?.GetValue<string>();
                var isCalculated = subtype == "calculated" || subtype == "calculated_column" || props?["expression"] != null || colTypeProp == "calculated";
                var isCalcTableCol = !isCalculated && (subtype == "calculated_table_column" || colTypeProp == "calculatedTableColumn");
                if (isCalculated)
                {
                    col = new CalculatedColumn
                    {
                        Name = name,
                        Expression = props?["expression"]?.GetValue<string>() ?? ""
                    };
                }
                else if (isCalcTableCol)
                {
                    var srcCol = FirstProp(props, "source_column", "sourceColumn")?.GetValue<string>();
                    var calcTblCol = new CalculatedTableColumn { Name = name };
                    if (!string.IsNullOrEmpty(srcCol)) calcTblCol.SourceColumn = srcCol;
                    var inferredNode = FirstProp(props, "is_name_inferred", "isNameInferred");
                    if (inferredNode != null) calcTblCol.IsNameInferred = inferredNode.GetValue<bool>();
                    col = calcTblCol;
                }
                else
                {
                    var srcCol = FirstProp(props, "source_column", "sourceColumn")?.GetValue<string>() ?? name;
                    col = new DataColumn
                    {
                        Name = name,
                        SourceColumn = srcCol
                    };
                }

                if (props != null)
                {
                    var dtNode = FirstProp(props, "data_type", "dataType");
                    if (dtNode != null) col.DataType = ParseDataType(dtNode.GetValue<string>());
                    var fmtNode = FirstProp(props, "format_string", "formatString");
                    if (fmtNode != null) col.FormatString = fmtNode.GetValue<string>();
                    var hiddenNode = FirstProp(props, "is_hidden", "hidden", "isHidden");
                    if (hiddenNode != null) col.IsHidden = hiddenNode.GetValue<bool>();
                    var dfNode = FirstProp(props, "display_folder", "displayFolder");
                    if (dfNode != null) col.DisplayFolder = dfNode.GetValue<string>();
                    var sumNode = FirstProp(props, "summarize_by", "summarizeBy");
                    if (sumNode != null) col.SummarizeBy = ParseSummarizeBy(sumNode.GetValue<string>());
                    if (props["description"] != null) col.Description = props["description"]?.GetValue<string>();
                    var catNode = FirstProp(props, "data_category", "dataCategory");
                    if (catNode != null) col.DataCategory = catNode.GetValue<string>();
                    var keyNode = FirstProp(props, "is_key", "key", "isKey");
                    if (keyNode != null) col.IsKey = keyNode.GetValue<bool>();
                    if (props["sort_by_column"] != null)
                    {
                        var sColName = props["sort_by_column"]?.GetValue<string>();
                        if (!string.IsNullOrEmpty(sColName) && !string.IsNullOrEmpty(tableName))
                            deferredSortBy.Add((tableName, name, sColName));
                    }
                    ApplyAnnotations(col.Annotations, props["annotations"]);
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
                    var fmtNode = FirstProp(props, "format_string", "formatString");
                    if (fmtNode != null) measure.FormatString = fmtNode.GetValue<string>();
                    var fmtExprNode = FirstProp(props, "format_string_expression", "formatStringExpression");
                    if (fmtExprNode != null)
                    {
                        var fmtExprStr = fmtExprNode.GetValue<string>();
                        if (!string.IsNullOrEmpty(fmtExprStr))
                            measure.FormatStringDefinition = new FormatStringDefinition { Expression = fmtExprStr };
                    }
                    if (props["description"] != null) measure.Description = props["description"]?.GetValue<string>();
                    var hiddenNode = FirstProp(props, "is_hidden", "hidden", "isHidden");
                    if (hiddenNode != null) measure.IsHidden = hiddenNode.GetValue<bool>();
                    var dfNode = FirstProp(props, "display_folder", "displayFolder");
                    if (dfNode != null) measure.DisplayFolder = dfNode.GetValue<string>();
                    var catNode = FirstProp(props, "data_category", "dataCategory");
                    if (catNode != null) measure.DataCategory = catNode.GetValue<string>();
                    ApplyAnnotations(measure.Annotations, props["annotations"]);
                }
                if (!string.IsNullOrEmpty(lineageTag)) measure.LineageTag = lineageTag;
                mTable.Measures.Add(measure);
                break;

            case "relationship":
                var rel = new SingleColumnRelationship();
                rel.Name = string.IsNullOrEmpty(name) ? Guid.NewGuid().ToString("N") : name;
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
                        var fromTable = FirstProp(props, "from_table", "fromTable")?.GetValue<string>();
                        var fromCol = FirstProp(props, "from_column", "fromColumn")?.GetValue<string>();
                        var toTable = FirstProp(props, "to_table", "toTable")?.GetValue<string>();
                        var toCol = FirstProp(props, "to_column", "toColumn")?.GetValue<string>();

                        rel.FromColumn = model.Tables.Find(fromTable)?.Columns.Find(fromCol);
                        rel.ToColumn = model.Tables.Find(toTable)?.Columns.Find(toCol);
                    }

                    ApplyRelationshipProperties(rel, props);
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
                    var hiddenNode = FirstProp(props, "is_hidden", "hidden", "isHidden");
                    if (hiddenNode != null) hierarchy.IsHidden = hiddenNode.GetValue<bool>();
                    var dfNode = FirstProp(props, "display_folder", "displayFolder");
                    if (dfNode != null) hierarchy.DisplayFolder = dfNode.GetValue<string>();
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
                    ApplyAnnotations(hierarchy.Annotations, props["annotations"]);
                }
                if (!string.IsNullOrEmpty(lineageTag)) hierarchy.LineageTag = lineageTag;
                hTable.Hierarchies.Add(hierarchy);
                break;

            case "calculation_item":
                var ciTable = model.Tables.Find(tableName)
                    ?? throw new ModelWriterException("table_not_found", $"Table not found: {tableName}");
                if (ciTable.CalculationGroup == null) ciTable.CalculationGroup = new CalculationGroup();
                var ordNode = FirstProp(props, "ordinal", "order");
                var ci = new CalculationItem
                {
                    Name = name,
                    Expression = props?["expression"]?.GetValue<string>() ?? "",
                    Ordinal = ordNode?.GetValue<int>() ?? 0
                };
                var fmtExpr = FirstProp(props, "format_string_expression", "formatStringExpression")?.GetValue<string>();
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
                ApplyAnnotations(role.Annotations, props?["annotations"]);
                model.Roles.Add(role);
                break;

            case "partition":
                var pTable = model.Tables.Find(tableName)
                    ?? throw new ModelWriterException("table_not_found", $"Table not found: {tableName}");
                var partExpr = FirstProp(props, "expression", "m_text", "partition_expression")?.GetValue<string>() ?? "";
                var modeVal = ParseModeType(props?["mode"]?.GetValue<string>());
                // Fold into an existing same-name partition (e.g. default placeholder created with the table)
                var existingPart = pTable.Partitions.Find(name);
                if (existingPart != null)
                {
                    existingPart.Mode = modeVal;
                    existingPart.Source = new MPartitionSource { Expression = partExpr };
                    ApplyAnnotations(existingPart.Annotations, props?["annotations"]);
                }
                else
                {
                    var part = new Partition
                    {
                        Name = name,
                        Mode = modeVal,
                        Source = new MPartitionSource { Expression = partExpr }
                    };
                    ApplyAnnotations(part.Annotations, props?["annotations"]);
                    pTable.Partitions.Add(part);
                }
                break;

            case "expression":
                var nExpr = new NamedExpression
                {
                    Name = name,
                    Expression = FirstProp(props, "expression", "m_text")?.GetValue<string>() ?? "",
                    Kind = ExpressionKind.M
                };
                if (props?["description"] != null) nExpr.Description = props["description"]?.GetValue<string>();
                if (!string.IsNullOrEmpty(lineageTag)) nExpr.LineageTag = lineageTag;
                ApplyAnnotations(nExpr.Annotations, props?["annotations"]);
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
                if (props?["description"] != null) func.Description = props["description"]?.GetValue<string>();
                var fHidden = FirstProp(props, "is_hidden", "hidden", "isHidden");
                if (fHidden != null) func.IsHidden = fHidden.GetValue<bool>();
                if (!string.IsNullOrEmpty(lineageTag)) func.LineageTag = lineageTag;
                ApplyAnnotations(func.Annotations, props?["annotations"]);
                model.Functions.Add(func);
                break;
        }
    }

    private static void ApplyRelationshipProperties(SingleColumnRelationship rel, JsonObject props)
    {
        var activeNode = FirstProp(props, "is_active", "active", "isActive");
        if (activeNode != null) rel.IsActive = activeNode.GetValue<bool>();

        var cfNode = FirstProp(props, "cross_filtering_behavior", "cross_filter_direction", "crossFilteringBehavior");
        if (cfNode != null) rel.CrossFilteringBehavior = ParseCrossFilter(cfNode.GetValue<string>());

        var sfNode = FirstProp(props, "security_filtering_behavior", "security_filter_direction", "securityFilteringBehavior");
        if (sfNode != null) rel.SecurityFilteringBehavior = ParseSecurityFilter(sfNode.GetValue<string>());

        var riNode = FirstProp(props, "rely_on_referential_integrity", "referential_integrity", "relyOnReferentialIntegrity");
        if (riNode != null) rel.RelyOnReferentialIntegrity = riNode.GetValue<bool>();

        var fromCard = FirstProp(props, "from_cardinality", "fromCardinality")?.GetValue<string>();
        var toCard = FirstProp(props, "to_cardinality", "toCardinality")?.GetValue<string>();
        var cardStr = props["cardinality"]?.GetValue<string>();
        if (!string.IsNullOrEmpty(cardStr) && cardStr.Contains(':'))
        {
            var parts = cardStr.Split(':', 2);
            fromCard ??= parts[0];
            toCard ??= parts[1];
        }
        if (!string.IsNullOrEmpty(fromCard)) rel.FromCardinality = ParseCardinality(fromCard);
        if (!string.IsNullOrEmpty(toCard)) rel.ToCardinality = ParseCardinality(toCard);

        ApplyAnnotations(rel.Annotations, props["annotations"]);
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

    private static void ApplySetProperties(Database db, string? objType, string name, string? tableName, JsonObject? props, string? lineageTag, List<(string Table, string Column, string? SortBy)> deferredSortBy)
    {
        if (props == null && string.IsNullOrEmpty(lineageTag)) return;
        var model = db.Model;

        switch (objType)
        {
            case "model":
                if (props != null)
                {
                    var cultureNode = FirstProp(props, "culture");
                    if (cultureNode != null) model.Culture = cultureNode.GetValue<string>();
                    var dsvNode = FirstProp(props, "default_power_bi_data_source_version", "defaultPowerBIDataSourceVersion");
                    if (dsvNode != null) model.DefaultPowerBIDataSourceVersion = ParseDataSourceVersion(dsvNode.GetValue<string>());
                    var sqcNode = FirstProp(props, "source_query_culture", "sourceQueryCulture");
                    if (sqcNode != null) model.SourceQueryCulture = sqcNode.GetValue<string>();
                    var daoNode = FirstProp(props, "data_access_options", "dataAccessOptions") as JsonObject;
                    if (daoNode != null)
                    {
                        model.DataAccessOptions ??= new DataAccessOptions();
                        var legacyNode = FirstProp(daoNode, "legacyRedirects", "legacy_redirects");
                        if (legacyNode != null) model.DataAccessOptions.LegacyRedirects = legacyNode.GetValue<bool>();
                        var errNullNode = FirstProp(daoNode, "returnErrorValuesAsNull", "return_error_values_as_null");
                        if (errNullNode != null) model.DataAccessOptions.ReturnErrorValuesAsNull = errNullNode.GetValue<bool>();
                    }
                    ApplyAnnotations(model.Annotations, props["annotations"]);
                }
                break;

            case "table":
                var t = model.Tables.Find(name);
                if (t != null)
                {
                    if (props != null)
                    {
                        if (props["description"] != null) t.Description = props["description"]?.GetValue<string>();
                        var hiddenNode = FirstProp(props, "is_hidden", "hidden", "isHidden");
                        if (hiddenNode != null) t.IsHidden = hiddenNode.GetValue<bool>();
                        var catNode = FirstProp(props, "data_category", "dataCategory");
                        if (catNode != null) t.DataCategory = catNode.GetValue<string>();
                        var privNode = FirstProp(props, "is_private", "isPrivate");
                        if (privNode != null) t.IsPrivate = privNode.GetValue<bool>();
                        var varOnlyNode = FirstProp(props, "show_as_variations_only", "showAsVariationsOnly");
                        if (varOnlyNode != null) t.ShowAsVariationsOnly = varOnlyNode.GetValue<bool>();
                        if (props["expression"] != null)
                        {
                            var calcPart = t.Partitions.FirstOrDefault(p => p.Source is CalculatedPartitionSource);
                            if (calcPart?.Source is CalculatedPartitionSource cps)
                                cps.Expression = props["expression"]!.GetValue<string>();
                        }
                        ApplyAnnotations(t.Annotations, props["annotations"]);
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
                        var dtNode = FirstProp(props, "data_type", "dataType");
                        if (dtNode != null) c.DataType = ParseDataType(dtNode.GetValue<string>());
                        var fmtNode = FirstProp(props, "format_string", "formatString");
                        if (fmtNode != null) c.FormatString = fmtNode.GetValue<string>();
                        var hiddenNode = FirstProp(props, "is_hidden", "hidden", "isHidden");
                        if (hiddenNode != null) c.IsHidden = hiddenNode.GetValue<bool>();
                        var dfNode = FirstProp(props, "display_folder", "displayFolder");
                        if (dfNode != null) c.DisplayFolder = dfNode.GetValue<string>();
                        var sumNode = FirstProp(props, "summarize_by", "summarizeBy");
                        if (sumNode != null) c.SummarizeBy = ParseSummarizeBy(sumNode.GetValue<string>());
                        if (props["description"] != null) c.Description = props["description"]?.GetValue<string>();
                        var catNode = FirstProp(props, "data_category", "dataCategory");
                        if (catNode != null) c.DataCategory = catNode.GetValue<string>();
                        var keyNode = FirstProp(props, "is_key", "key", "isKey");
                        if (keyNode != null) c.IsKey = keyNode.GetValue<bool>();
                        if (props["expression"] != null && c is CalculatedColumn calc)
                            calc.Expression = props["expression"]!.GetValue<string>();
                        if (HasAnyProp(props, "sort_by_column") && !string.IsNullOrEmpty(tableName))
                        {
                            var sName = props["sort_by_column"]?.GetValue<string>();
                            deferredSortBy.Add((tableName, name, sName));
                        }
                        ApplyAnnotations(c.Annotations, props["annotations"]);
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
                        var fmtNode = FirstProp(props, "format_string", "formatString");
                        if (fmtNode != null) m.FormatString = fmtNode.GetValue<string>();
                        var fmtExprNode = FirstProp(props, "format_string_expression", "formatStringExpression");
                        if (fmtExprNode != null)
                        {
                            var fmtExprStr = fmtExprNode.GetValue<string>();
                            if (string.IsNullOrEmpty(fmtExprStr)) m.FormatStringDefinition = null;
                            else
                            {
                                m.FormatStringDefinition ??= new FormatStringDefinition();
                                m.FormatStringDefinition.Expression = fmtExprStr;
                            }
                        }
                        if (props["description"] != null) m.Description = props["description"]?.GetValue<string>();
                        var hiddenNode = FirstProp(props, "is_hidden", "hidden", "isHidden");
                        if (hiddenNode != null) m.IsHidden = hiddenNode.GetValue<bool>();
                        var dfNode = FirstProp(props, "display_folder", "displayFolder");
                        if (dfNode != null) m.DisplayFolder = dfNode.GetValue<string>();
                        var catNode = FirstProp(props, "data_category", "dataCategory");
                        if (catNode != null) m.DataCategory = catNode.GetValue<string>();
                        ApplyAnnotations(m.Annotations, props["annotations"]);
                    }
                    if (!string.IsNullOrEmpty(lineageTag)) m.LineageTag = lineageTag;
                }
                break;

            case "relationship":
                var rel = model.Relationships.Find(name) as SingleColumnRelationship;
                if (rel != null && props != null)
                {
                    ApplyRelationshipProperties(rel, props);
                }
                break;

            case "hierarchy":
                var hTable = model.Tables.Find(tableName);
                var h = hTable?.Hierarchies.Find(name);
                if (h != null)
                {
                    if (props != null)
                    {
                        if (props["description"] != null) h.Description = props["description"]?.GetValue<string>();
                        var hiddenNode = FirstProp(props, "is_hidden", "hidden", "isHidden");
                        if (hiddenNode != null) h.IsHidden = hiddenNode.GetValue<bool>();
                        var dfNode = FirstProp(props, "display_folder", "displayFolder");
                        if (dfNode != null) h.DisplayFolder = dfNode.GetValue<string>();
                        if (props["levels"] is JsonArray levelsArr && hTable != null)
                        {
                            h.Levels.Clear();
                            int ord = 0;
                            foreach (var lvlNode in levelsArr)
                            {
                                var lvlName = lvlNode?.GetValue<string>() ?? "";
                                var colObj = hTable.Columns.Find(lvlName);
                                h.Levels.Add(new Level { Name = lvlName, Ordinal = ord++, Column = colObj });
                            }
                        }
                        ApplyAnnotations(h.Annotations, props["annotations"]);
                    }
                    if (!string.IsNullOrEmpty(lineageTag)) h.LineageTag = lineageTag;
                }
                break;

            case "partition":
                var pTable = model.Tables.Find(tableName);
                var part = pTable?.Partitions.Find(name);
                if (part != null && props != null)
                {
                    if (props["mode"] != null) part.Mode = ParseModeType(props["mode"]?.GetValue<string>());
                    var exprNode = FirstProp(props, "expression", "m_text", "partition_expression");
                    if (exprNode != null)
                    {
                        var exprText = exprNode.GetValue<string>() ?? "";
                        if (part.Source is MPartitionSource mp) mp.Expression = exprText;
                        else if (part.Source is CalculatedPartitionSource cp) cp.Expression = exprText;
                        else part.Source = new MPartitionSource { Expression = exprText };
                    }
                    ApplyAnnotations(part.Annotations, props["annotations"]);
                }
                break;

            case "calculation_item":
                var ciTable = model.Tables.Find(tableName);
                var ci = ciTable?.CalculationGroup?.CalculationItems.Find(name);
                if (ci != null && props != null)
                {
                    if (props["expression"] != null) ci.Expression = props["expression"]!.GetValue<string>();
                    var ordNode = FirstProp(props, "ordinal", "order");
                    if (ordNode != null) ci.Ordinal = ordNode.GetValue<int>();
                    var fmtExprNode = FirstProp(props, "format_string_expression", "formatStringExpression");
                    if (fmtExprNode != null)
                    {
                        if (ci.FormatStringDefinition == null) ci.FormatStringDefinition = new FormatStringDefinition();
                        ci.FormatStringDefinition.Expression = fmtExprNode.GetValue<string>();
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
                    ApplyAnnotations(role.Annotations, props["annotations"]);
                }
                break;

            case "expression":
                var expr = model.Expressions.Find(name);
                if (expr != null)
                {
                    var exprNode = FirstProp(props, "expression", "m_text");
                    if (exprNode != null) expr.Expression = exprNode.GetValue<string>() ?? "";
                    if (props?["description"] != null) expr.Description = props["description"]?.GetValue<string>();
                    if (!string.IsNullOrEmpty(lineageTag)) expr.LineageTag = lineageTag;
                    ApplyAnnotations(expr.Annotations, props?["annotations"]);
                }
                break;

            case "function":
                var func = model.Functions.Find(name);
                if (func != null)
                {
                    if (props?["expression"] != null) func.Expression = props["expression"]!.GetValue<string>();
                    if (props?["description"] != null) func.Description = props["description"]?.GetValue<string>();
                    var fHidden = FirstProp(props, "is_hidden", "hidden", "isHidden");
                    if (fHidden != null) func.IsHidden = fHidden.GetValue<bool>();
                    if (!string.IsNullOrEmpty(lineageTag)) func.LineageTag = lineageTag;
                    ApplyAnnotations(func.Annotations, props?["annotations"]);
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
                case "partition":
                    // The Power Query (M) source of an import or DirectQuery partition.
                    var part = model.Tables.Find(tableName)?.Partitions.Find(name);
                    if (part?.Source is MPartitionSource mp) mp.Expression = newText;
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

    private static SecurityFilteringBehavior ParseSecurityFilter(string? val)
    {
        if (string.IsNullOrWhiteSpace(val)) return SecurityFilteringBehavior.OneDirection;
        return Enum.TryParse<SecurityFilteringBehavior>(val, true, out var result) ? result : SecurityFilteringBehavior.OneDirection;
    }

    private static RelationshipEndCardinality ParseCardinality(string? val)
    {
        if (string.IsNullOrWhiteSpace(val)) return RelationshipEndCardinality.None;
        return Enum.TryParse<RelationshipEndCardinality>(val, true, out var result) ? result : RelationshipEndCardinality.None;
    }

    private static ModeType ParseModeType(string? val)
    {
        if (string.IsNullOrWhiteSpace(val) || val.Equals("default", StringComparison.OrdinalIgnoreCase)) return ModeType.Import;
        return Enum.TryParse<ModeType>(val, true, out var result) ? result : ModeType.Import;
    }

    private static PowerBIDataSourceVersion ParseDataSourceVersion(string? val)
    {
        if (string.IsNullOrWhiteSpace(val)) return PowerBIDataSourceVersion.PowerBI_V3;
        return Enum.TryParse<PowerBIDataSourceVersion>(val, true, out var result) ? result : PowerBIDataSourceVersion.PowerBI_V3;
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
