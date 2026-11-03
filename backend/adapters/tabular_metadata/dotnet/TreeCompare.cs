using Microsoft.AnalysisServices.Tabular;
using System.Text.Json.Nodes;
using Json = System.Text.Json.JsonSerializer;

// Bridge command "tree-compare" (DEV_CENTER_TECHNICAL_DESIGN.md section 9.1, ADR 0001).
// Compares two models object by object over the full TOM tree (including
// unmodeled objects: Perspectives, Cultures).
static class TreeCompare
{
    public sealed record DiffItem(
        string object_type,
        string object_name,
        string? table,
        string change_type,
        string? property = null,
        string? old_value = null,
        string? new_value = null
    );

    public static int Run(string[] args, TextReader input, TextWriter output)
    {
        string? baselinePath = null;
        string? candidatePath = null;

        if (args.Length >= 3)
        {
            baselinePath = args[1];
            candidatePath = args[2];
        }
        else if (Console.IsInputRedirected)
        {
            var content = input.ReadToEnd().TrimStart('\uFEFF');
            if (!string.IsNullOrWhiteSpace(content))
            {
                var parsed = JsonNode.Parse(content);
                if (parsed is JsonObject obj)
                {
                    baselinePath = obj["baseline"]?.GetValue<string>() ?? obj["baseline_path"]?.GetValue<string>();
                    candidatePath = obj["candidate"]?.GetValue<string>() ?? obj["candidate_path"]?.GetValue<string>();
                }
            }
        }

        if (string.IsNullOrWhiteSpace(baselinePath) || string.IsNullOrWhiteSpace(candidatePath))
        {
            output.WriteLine(Json.Serialize(new
            {
                adapter_version = 1,
                status = "FAILED",
                command = "tree-compare",
                code = "invalid_request",
                error = "Both baseline and candidate paths are required"
            }));
            return 2;
        }

        var baselineFull = Path.GetFullPath(baselinePath);
        var candidateFull = Path.GetFullPath(candidatePath);

        if (!Directory.Exists(baselineFull))
        {
            output.WriteLine(Json.Serialize(new
            {
                adapter_version = 1,
                status = "FAILED",
                command = "tree-compare",
                code = "not_found",
                error = $"Baseline directory not found: {baselineFull}"
            }));
            return 2;
        }

        if (!Directory.Exists(candidateFull))
        {
            output.WriteLine(Json.Serialize(new
            {
                adapter_version = 1,
                status = "FAILED",
                command = "tree-compare",
                code = "not_found",
                error = $"Candidate directory not found: {candidateFull}"
            }));
            return 2;
        }

        try
        {
            var baselineDb = TmdlSerializer.DeserializeDatabaseFromFolder(baselineFull);
            var candidateDb = TmdlSerializer.DeserializeDatabaseFromFolder(candidateFull);

            var diffs = CompareDatabases(baselineDb, candidateDb);

            output.WriteLine(Json.Serialize(new
            {
                adapter_version = 1,
                status = "PASSED",
                command = "tree-compare",
                identical = diffs.Count == 0,
                differences = diffs,
                difference_count = diffs.Count
            }));
            return 0;
        }
        catch (Exception ex)
        {
            output.WriteLine(Json.Serialize(new
            {
                adapter_version = 1,
                status = "FAILED",
                command = "tree-compare",
                code = "compare_failed",
                error = ex.Message
            }));
            return 2;
        }
    }

    private static List<DiffItem> CompareDatabases(Database bDb, Database cDb)
    {
        var diffs = new List<DiffItem>();
        var bModel = bDb.Model;
        var cModel = cDb.Model;

        if (bModel == null && cModel == null) return diffs;
        if (bModel == null || cModel == null)
        {
            diffs.Add(new DiffItem("model", "model", null, bModel == null ? "ADDED" : "DELETED"));
            return diffs;
        }

        // 1. Compare Tables
        var bTables = bModel.Tables.ToDictionary(t => t.Name, StringComparer.OrdinalIgnoreCase);
        var cTables = cModel.Tables.ToDictionary(t => t.Name, StringComparer.OrdinalIgnoreCase);

        foreach (var name in bTables.Keys.Except(cTables.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("table", name, null, "DELETED"));

        foreach (var name in cTables.Keys.Except(bTables.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("table", name, null, "ADDED"));

        foreach (var name in bTables.Keys.Intersect(cTables.Keys, StringComparer.OrdinalIgnoreCase))
        {
            var bTable = bTables[name];
            var cTable = cTables[name];
            CompareTable(bTable, cTable, diffs);
        }

        // 2. Compare Relationships
        CompareRelationships(bModel.Relationships, cModel.Relationships, diffs);

        // 3. Compare Roles
        CompareRoles(bModel.Roles, cModel.Roles, diffs);

        // 4. Compare Expressions (NamedExpressions)
        CompareExpressions(bModel.Expressions, cModel.Expressions, diffs);

        // 5. Compare Functions
        CompareFunctions(bModel.Functions, cModel.Functions, diffs);

        // 6. Compare Unmodeled: Perspectives
        ComparePerspectives(bModel.Perspectives, cModel.Perspectives, diffs);

        // 7. Compare Unmodeled: Cultures
        CompareCultures(bModel.Cultures, cModel.Cultures, diffs);

        return diffs;
    }

    private static void CompareTable(Table bTable, Table cTable, List<DiffItem> diffs)
    {
        var tName = bTable.Name;
        CheckProp("table", tName, null, "description", bTable.Description, cTable.Description, diffs);
        CheckProp("table", tName, null, "isHidden", bTable.IsHidden.ToString(), cTable.IsHidden.ToString(), diffs);
        CheckProp("table", tName, null, "dataCategory", bTable.DataCategory, cTable.DataCategory, diffs);

        // Columns
        var bCols = bTable.Columns.ToDictionary(c => c.Name, StringComparer.OrdinalIgnoreCase);
        var cCols = cTable.Columns.ToDictionary(c => c.Name, StringComparer.OrdinalIgnoreCase);

        foreach (var name in bCols.Keys.Except(cCols.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("column", name, tName, "DELETED"));

        foreach (var name in cCols.Keys.Except(bCols.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("column", name, tName, "ADDED"));

        foreach (var name in bCols.Keys.Intersect(cCols.Keys, StringComparer.OrdinalIgnoreCase))
        {
            var bCol = bCols[name];
            var cCol = cCols[name];
            CheckProp("column", name, tName, "dataType", bCol.DataType.ToString(), cCol.DataType.ToString(), diffs);
            CheckProp("column", name, tName, "isHidden", bCol.IsHidden.ToString(), cCol.IsHidden.ToString(), diffs);
            CheckProp("column", name, tName, "formatString", bCol.FormatString, cCol.FormatString, diffs);
            CheckProp("column", name, tName, "summarizeBy", bCol.SummarizeBy.ToString(), cCol.SummarizeBy.ToString(), diffs);
            CheckProp("column", name, tName, "displayFolder", bCol.DisplayFolder, cCol.DisplayFolder, diffs);
            CheckProp("column", name, tName, "lineageTag", bCol.LineageTag, cCol.LineageTag, diffs);
            CheckProp("column", name, tName, "sortByColumn", bCol.SortByColumn?.Name, cCol.SortByColumn?.Name, diffs);

            if (bCol is CalculatedColumn bCalc && cCol is CalculatedColumn cCalc)
                CheckProp("column", name, tName, "expression", bCalc.Expression, cCalc.Expression, diffs);
            else if (bCol.GetType() != cCol.GetType())
                CheckProp("column", name, tName, "type", bCol.GetType().Name, cCol.GetType().Name, diffs);
        }

        // Measures
        var bMeasures = bTable.Measures.ToDictionary(m => m.Name, StringComparer.OrdinalIgnoreCase);
        var cMeasures = cTable.Measures.ToDictionary(m => m.Name, StringComparer.OrdinalIgnoreCase);

        foreach (var name in bMeasures.Keys.Except(cMeasures.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("measure", name, tName, "DELETED"));

        foreach (var name in cMeasures.Keys.Except(bMeasures.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("measure", name, tName, "ADDED"));

        foreach (var name in bMeasures.Keys.Intersect(cMeasures.Keys, StringComparer.OrdinalIgnoreCase))
        {
            var bM = bMeasures[name];
            var cM = cMeasures[name];
            CheckProp("measure", name, tName, "expression", bM.Expression, cM.Expression, diffs);
            CheckProp("measure", name, tName, "formatString", bM.FormatString, cM.FormatString, diffs);
            CheckProp("measure", name, tName, "description", bM.Description, cM.Description, diffs);
            CheckProp("measure", name, tName, "isHidden", bM.IsHidden.ToString(), cM.IsHidden.ToString(), diffs);
            CheckProp("measure", name, tName, "displayFolder", bM.DisplayFolder, cM.DisplayFolder, diffs);
            CheckProp("measure", name, tName, "lineageTag", bM.LineageTag, cM.LineageTag, diffs);
        }

        // Hierarchies
        var bHi = bTable.Hierarchies.ToDictionary(h => h.Name, StringComparer.OrdinalIgnoreCase);
        var cHi = cTable.Hierarchies.ToDictionary(h => h.Name, StringComparer.OrdinalIgnoreCase);

        foreach (var name in bHi.Keys.Except(cHi.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("hierarchy", name, tName, "DELETED"));

        foreach (var name in cHi.Keys.Except(bHi.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("hierarchy", name, tName, "ADDED"));

        foreach (var name in bHi.Keys.Intersect(cHi.Keys, StringComparer.OrdinalIgnoreCase))
        {
            var bH = bHi[name];
            var cH = cHi[name];
            CheckProp("hierarchy", name, tName, "description", bH.Description, cH.Description, diffs);
            CheckProp("hierarchy", name, tName, "displayFolder", bH.DisplayFolder, cH.DisplayFolder, diffs);
            CheckProp("hierarchy", name, tName, "lineageTag", bH.LineageTag, cH.LineageTag, diffs);
            var bLevels = string.Join(",", bH.Levels.Select(l => l.Name));
            var cLevels = string.Join(",", cH.Levels.Select(l => l.Name));
            CheckProp("hierarchy", name, tName, "levels", bLevels, cLevels, diffs);
        }

        // Partitions
        var bParts = bTable.Partitions.ToDictionary(p => p.Name, StringComparer.OrdinalIgnoreCase);
        var cParts = cTable.Partitions.ToDictionary(p => p.Name, StringComparer.OrdinalIgnoreCase);

        foreach (var name in bParts.Keys.Except(cParts.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("partition", name, tName, "DELETED"));

        foreach (var name in cParts.Keys.Except(bParts.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("partition", name, tName, "ADDED"));

        foreach (var name in bParts.Keys.Intersect(cParts.Keys, StringComparer.OrdinalIgnoreCase))
        {
            var bP = bParts[name];
            var cP = cParts[name];
            CheckProp("partition", name, tName, "mode", bP.Mode.ToString(), cP.Mode.ToString(), diffs);
            CheckProp("partition", name, tName, "sourceType", bP.SourceType.ToString(), cP.SourceType.ToString(), diffs);
            string? bExpr = bP.Source is MPartitionSource bM ? bM.Expression : (bP.Source is CalculatedPartitionSource bC ? bC.Expression : null);
            string? cExpr = cP.Source is MPartitionSource cM ? cM.Expression : (cP.Source is CalculatedPartitionSource cC ? cC.Expression : null);
            CheckProp("partition", name, tName, "expression", bExpr, cExpr, diffs);
        }

        // Calculation Items
        if (bTable.CalculationGroup != null || cTable.CalculationGroup != null)
        {
            var bCalcItems = bTable.CalculationGroup?.CalculationItems.ToDictionary(ci => ci.Name, StringComparer.OrdinalIgnoreCase)
                ?? new Dictionary<string, CalculationItem>(StringComparer.OrdinalIgnoreCase);
            var cCalcItems = cTable.CalculationGroup?.CalculationItems.ToDictionary(ci => ci.Name, StringComparer.OrdinalIgnoreCase)
                ?? new Dictionary<string, CalculationItem>(StringComparer.OrdinalIgnoreCase);

            foreach (var name in bCalcItems.Keys.Except(cCalcItems.Keys, StringComparer.OrdinalIgnoreCase))
                diffs.Add(new DiffItem("calculation_item", name, tName, "DELETED"));

            foreach (var name in cCalcItems.Keys.Except(bCalcItems.Keys, StringComparer.OrdinalIgnoreCase))
                diffs.Add(new DiffItem("calculation_item", name, tName, "ADDED"));

            foreach (var name in bCalcItems.Keys.Intersect(cCalcItems.Keys, StringComparer.OrdinalIgnoreCase))
            {
                var bCi = bCalcItems[name];
                var cCi = cCalcItems[name];
                CheckProp("calculation_item", name, tName, "expression", bCi.Expression, cCi.Expression, diffs);
                CheckProp("calculation_item", name, tName, "ordinal", bCi.Ordinal.ToString(), cCi.Ordinal.ToString(), diffs);
                CheckProp("calculation_item", name, tName, "formatStringExpression",
                    bCi.FormatStringDefinition?.Expression, cCi.FormatStringDefinition?.Expression, diffs);
            }
        }
    }

    private static void CompareRelationships(RelationshipCollection bRels, RelationshipCollection cRels, List<DiffItem> diffs)
    {
        string RelKey(Relationship r) =>
            r is SingleColumnRelationship scr
                ? $"{scr.FromTable?.Name}[{scr.FromColumn?.Name}]->{scr.ToTable?.Name}[{scr.ToColumn?.Name}]"
                : r.Name;

        var bDict = bRels.ToDictionary(RelKey, StringComparer.OrdinalIgnoreCase);
        var cDict = cRels.ToDictionary(RelKey, StringComparer.OrdinalIgnoreCase);

        foreach (var key in bDict.Keys.Except(cDict.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("relationship", bDict[key].Name ?? key, null, "DELETED"));

        foreach (var key in cDict.Keys.Except(bDict.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("relationship", cDict[key].Name ?? key, null, "ADDED"));

        foreach (var key in bDict.Keys.Intersect(cDict.Keys, StringComparer.OrdinalIgnoreCase))
        {
            var bRel = bDict[key];
            var cRel = cDict[key];
            var name = bRel.Name ?? key;
            CheckProp("relationship", name, null, "isActive", bRel.IsActive.ToString(), cRel.IsActive.ToString(), diffs);
            CheckProp("relationship", name, null, "crossFilteringBehavior", bRel.CrossFilteringBehavior.ToString(), cRel.CrossFilteringBehavior.ToString(), diffs);
            if (bRel is SingleColumnRelationship bScr && cRel is SingleColumnRelationship cScr)
            {
                CheckProp("relationship", name, null, "fromCardinality", bScr.FromCardinality.ToString(), cScr.FromCardinality.ToString(), diffs);
                CheckProp("relationship", name, null, "toCardinality", bScr.ToCardinality.ToString(), cScr.ToCardinality.ToString(), diffs);
                CheckProp("relationship", name, null, "relyOnReferentialIntegrity", bScr.RelyOnReferentialIntegrity.ToString(), cScr.RelyOnReferentialIntegrity.ToString(), diffs);
            }
        }
    }

    private static void CompareRoles(ModelRoleCollection bRoles, ModelRoleCollection cRoles, List<DiffItem> diffs)
    {
        var bDict = bRoles.ToDictionary(r => r.Name, StringComparer.OrdinalIgnoreCase);
        var cDict = cRoles.ToDictionary(r => r.Name, StringComparer.OrdinalIgnoreCase);

        foreach (var name in bDict.Keys.Except(cDict.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("role", name, null, "DELETED"));

        foreach (var name in cDict.Keys.Except(bDict.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("role", name, null, "ADDED"));

        foreach (var name in bDict.Keys.Intersect(cDict.Keys, StringComparer.OrdinalIgnoreCase))
        {
            var bRole = bDict[name];
            var cRole = cDict[name];
            CheckProp("role", name, null, "modelPermission", bRole.ModelPermission.ToString(), cRole.ModelPermission.ToString(), diffs);
            var bPerms = string.Join(";", bRole.TablePermissions.OrderBy(p => p.Table?.Name).Select(p => $"{p.Table?.Name}:{p.FilterExpression}"));
            var cPerms = string.Join(";", cRole.TablePermissions.OrderBy(p => p.Table?.Name).Select(p => $"{p.Table?.Name}:{p.FilterExpression}"));
            CheckProp("role", name, null, "tablePermissions", bPerms, cPerms, diffs);
        }
    }

    private static void CompareExpressions(NamedExpressionCollection bExprs, NamedExpressionCollection cExprs, List<DiffItem> diffs)
    {
        var bDict = bExprs.ToDictionary(e => e.Name, StringComparer.OrdinalIgnoreCase);
        var cDict = cExprs.ToDictionary(e => e.Name, StringComparer.OrdinalIgnoreCase);

        foreach (var name in bDict.Keys.Except(cDict.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("expression", name, null, "DELETED"));

        foreach (var name in cDict.Keys.Except(bDict.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("expression", name, null, "ADDED"));

        foreach (var name in bDict.Keys.Intersect(cDict.Keys, StringComparer.OrdinalIgnoreCase))
        {
            var bE = bDict[name];
            var cE = cDict[name];
            CheckProp("expression", name, null, "expression", bE.Expression, cE.Expression, diffs);
            CheckProp("expression", name, null, "kind", bE.Kind.ToString(), cE.Kind.ToString(), diffs);
            CheckProp("expression", name, null, "lineageTag", bE.LineageTag, cE.LineageTag, diffs);
        }
    }

    private static void CompareFunctions(FunctionCollection bFuncs, FunctionCollection cFuncs, List<DiffItem> diffs)
    {
        var bDict = bFuncs.ToDictionary(f => f.Name, StringComparer.OrdinalIgnoreCase);
        var cDict = cFuncs.ToDictionary(f => f.Name, StringComparer.OrdinalIgnoreCase);

        foreach (var name in bDict.Keys.Except(cDict.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("function", name, null, "DELETED"));

        foreach (var name in cDict.Keys.Except(bDict.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("function", name, null, "ADDED"));

        foreach (var name in bDict.Keys.Intersect(cDict.Keys, StringComparer.OrdinalIgnoreCase))
        {
            var bF = bDict[name];
            var cF = cDict[name];
            CheckProp("function", name, null, "expression", bF.Expression, cF.Expression, diffs);
            CheckProp("function", name, null, "lineageTag", bF.LineageTag, cF.LineageTag, diffs);
        }
    }

    private static void ComparePerspectives(PerspectiveCollection bPers, PerspectiveCollection cPers, List<DiffItem> diffs)
    {
        var bDict = bPers.ToDictionary(p => p.Name, StringComparer.OrdinalIgnoreCase);
        var cDict = cPers.ToDictionary(p => p.Name, StringComparer.OrdinalIgnoreCase);

        foreach (var name in bDict.Keys.Except(cDict.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("perspective", name, null, "DELETED"));

        foreach (var name in cDict.Keys.Except(bDict.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("perspective", name, null, "ADDED"));

        foreach (var name in bDict.Keys.Intersect(cDict.Keys, StringComparer.OrdinalIgnoreCase))
        {
            var bP = bDict[name];
            var cP = cDict[name];
            CheckProp("perspective", name, null, "description", bP.Description, cP.Description, diffs);
            var bTables = string.Join(",", bP.PerspectiveTables.Select(t => t.Table?.Name).OrderBy(x => x));
            var cTables = string.Join(",", cP.PerspectiveTables.Select(t => t.Table?.Name).OrderBy(x => x));
            CheckProp("perspective", name, null, "tables", bTables, cTables, diffs);
        }
    }

    private static void CompareCultures(CultureCollection bCultures, CultureCollection cCultures, List<DiffItem> diffs)
    {
        var bDict = bCultures.ToDictionary(c => c.Name, StringComparer.OrdinalIgnoreCase);
        var cDict = cCultures.ToDictionary(c => c.Name, StringComparer.OrdinalIgnoreCase);

        foreach (var name in bDict.Keys.Except(cDict.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("culture", name, null, "DELETED"));

        foreach (var name in cDict.Keys.Except(bDict.Keys, StringComparer.OrdinalIgnoreCase))
            diffs.Add(new DiffItem("culture", name, null, "ADDED"));

        foreach (var name in bDict.Keys.Intersect(cDict.Keys, StringComparer.OrdinalIgnoreCase))
        {
            var bC = bDict[name];
            var cC = cDict[name];
            CheckProp("culture", name, null, "name", bC.Name, cC.Name, diffs);
        }
    }

    private static void CheckProp(string objType, string objName, string? table, string prop, string? oldVal, string? newVal, List<DiffItem> diffs)
    {
        if (oldVal == null && newVal == null) return;
        if (!string.Equals(oldVal, newVal, StringComparison.Ordinal))
        {
            diffs.Add(new DiffItem(objType, objName, table, "MODIFIED", prop, oldVal, newVal));
        }
    }
}
