"""``brain_guide``: what an agent needs to know to write a correct change before it proposes one.

Short, fixed authoring notes per topic: the syntax PBIBrain expects in an ``object_edit``, best
practice, and what the change does to the objects around it. They pair with the checks that run on
every proposal (``proposal_check``): the plan refuses what cannot work, the impact lists the
dependents, and the change rules (``backend/devcenter/session/change_rules.py``) name the breaks
that a type or signature change causes. The notes say what to do; the checks prove it.

No model or file data here: the tool needs no snapshot and costs no scan.
"""

from __future__ import annotations

from typing import Any

WORKFLOW = (
    "Change workflow: (1) session_get: a Merge models session must be open; if not, tell the user to open one in "
    "PBIBrain. (2) Find the row: compare_rows_list(q=...) gives the row_key. Read the object with brain_object and "
    "its users with brain_dependencies(direction='downstream', depth=2). (3) proposal_check(kind, target, payload) "
    "until valid and the rules are understood. (4) proposal_submit with the reason naming the Breaks you accept. "
    "Nothing is applied until the user accepts the proposal and applies the plan in PBIBrain."
)

TOPICS: dict[str, dict[str, Any]] = {
    "measure": {
        "title": "DAX measures",
        "payload": "object_edit {set: {expression, format_string, display_folder, description, is_hidden}}",
        "syntax": [
            "expression is the DAX after 'Measure =' (no name, no leading '=').",
            "Refer to a measure as [Measure] (no table prefix) and to a column as 'Table'[Column] (always the table).",
            "VAR name = ... RETURN expr for any value used twice or for readability; variables are evaluated once.",
        ],
        "best_practice": [
            "DIVIDE(a, b) instead of a / b: no division-by-zero error, returns BLANK.",
            "In CALCULATE, filter columns (Sales[Region] = \"West\", KEEPFILTERS(...)) instead of FILTER(Table, ...) over a whole table.",
            "Keep the result type: a measure that charts as a number must stay a number. Format with format_string, not FORMAT().",
            "Return BLANK() rather than 0 when there is nothing to show: 0 makes visuals list every row.",
            "Keep format_string matching the result (\"#,0\", \"0.0%\", \"$#,0.00\").",
        ],
        "impact": [
            "Number -> text (FORMAT, &, CONCATENATE): charts, cards with number formats, totals, conditional formatting, "
            "sorting and every measure that does arithmetic with it break. Rule result_type_change (breaks).",
            "A text result ignores the number format_string. Rule format_string_ignored.",
            "Number -> true/false or a mixed IF/SWITCH (number in one branch, text in another) breaks the same way.",
            "Renaming changes every [Measure] reference: PBIBrain rewrites them in the plan; visuals rebind.",
            "Deleting breaks every visual and measure that uses it; brain_dependencies lists them.",
        ],
    },
    "column": {
        "title": "Columns (data and calculated)",
        "payload": "object_edit {set: {expression (calculated only), format_string, display_folder, description, is_hidden, "
                   "data_category, summarize_by, is_key}}",
        "syntax": [
            "A calculated column's expression is row-by-row DAX: it sees the current row (Sales[Amount] * Sales[Qty]); use "
            "RELATED('Dim'[Col]) to read the one side of a relationship.",
            "summarize_by: default, none, sum, min, max, count, average, distinctcount.",
        ],
        "best_practice": [
            "Prefer a measure to a calculated column for anything aggregated: columns are stored and cost memory and refresh.",
            "Set summarize_by none on IDs, years and codes so visuals do not sum them.",
            "Hide key and technical columns (is_hidden) rather than deleting them.",
        ],
        "impact": [
            "A calculated column changing result type changes its data type: relationships on it need the same type on both "
            "sides, sort-by-column, hierarchies, slicers and visuals can break. Rule result_type_change.",
            "Removing or renaming a column breaks relationships, sort-by columns, hierarchies, measures, RLS filters and "
            "visual fields that use it.",
            "A data column reads source_column from the table's M query: renaming or dropping that column in the query "
            "breaks the refresh. Rule source_column_dropped.",
        ],
    },
    "function": {
        "title": "DAX user-defined functions (UDF)",
        "payload": "object_edit {set: {expression}} on a function row",
        "syntax": [
            "expression is the text after 'function Name =': (param : TYPEHINT, ...) => body",
            "Type hint: [type] [subtype] [mode]. Types: AnyVal (default), Scalar, Table, AnyRef, MeasureRef, ColumnRef, "
            "TableRef. Scalar subtypes: Variant, Int64, Decimal, Double, String, DateTime, Boolean, Numeric.",
            "Mode VAL (default): the argument is evaluated once at the call. EXPR: the argument is evaluated inside the "
            "function, in its filter context (use it for a measure-like argument used under CALCULATE). Reference types are always EXPR.",
            "Example: (amount : Scalar Numeric, rate : Scalar Numeric) => amount * (1 + rate)",
            "Call as Name(arg1, arg2); dotted names (Sales.AddTax) group functions. The model needs compatibility level 1702 or higher.",
        ],
        "best_practice": [
            "Give each parameter a type hint: callers get a clear error instead of a wrong result.",
            "Use EXPR only when the function must re-evaluate the argument in another context.",
            "Changing a signature changes every caller: add a new function, move the callers, then delete the old one.",
        ],
        "impact": [
            "A different parameter count breaks every call site with the old count. Rule function_signature (breaks).",
            "A different parameter type may break callers that pass the old type. Rule function_signature (warning).",
            "A different result type flows into every measure that calls it. Rule function_result_type.",
            "A body that does not parse is refused (dax_parse) before it becomes a proposal.",
        ],
    },
    "m_query": {
        "title": "Power Query (M): partitions and shared expressions",
        "payload": "object_edit {set: {expression}} on a partition row (a table's source query) or an expression row "
                   "(a shared query or parameter)",
        "syntax": [
            "let Step1 = ..., Step2 = ... in Step2. Every let needs an in; step names with spaces are #\"Step name\".",
            "Text is \"...\" with \"\" for a quote; comments are // and /* */.",
            "Common steps: Table.SelectColumns, Table.RenameColumns, Table.TransformColumnTypes, Table.SelectRows, "
            "Table.AddColumn. A shared query is used by name: Source = #\"Sales Base\".",
        ],
        "best_practice": [
            "Keep the output column names and types the model expects: each data column reads its source_column.",
            "Set types with Table.TransformColumnTypes at the end: an untyped column loads as text.",
            "Filter rows and remove columns early so the source can fold the query.",
            "Put server names and paths in parameters (shared expressions), not in each query.",
        ],
        "impact": [
            "Dropping or renaming an output column that a model column reads breaks the refresh of that column and "
            "everything built on it. Rule source_column_dropped (breaks).",
            "Changing a shared expression changes every query that uses it. Rule query_dependents (warning).",
            "A changed column type changes the model column's type: relationships, measures and visuals can break.",
            "Unbalanced brackets, open text or a let without in are refused (m_unbalanced_brackets, m_unclosed_text, m_let_without_in).",
            "PBIBrain does not run M: refresh in Power BI after applying to prove the query.",
        ],
    },
    "calculation_group": {
        "title": "Calculation groups and items",
        "payload": "object_edit {set: {expression}} on a calculation_item row",
        "syntax": [
            "An item's expression wraps the measure in context: CALCULATE(SELECTEDMEASURE(), DATESYTD('Date'[Date])).",
            "SELECTEDMEASURE(), SELECTEDMEASURENAME(), ISSELECTEDMEASURE([M1], [M2]) and SELECTEDMEASUREFORMATSTRING() refer to the measure in context.",
        ],
        "best_practice": [
            "Always use SELECTEDMEASURE(); an item without it returns the same value for every measure.",
            "Exclude measures that must not change (percentages, text) with IF(ISSELECTEDMEASURE(...), SELECTEDMEASURE(), ...).",
        ],
        "impact": [
            "An item applies to every measure in a visual filtered by the group: a change reaches every such visual.",
            "Rule calc_item_without_measure (warning) when SELECTEDMEASURE() is missing.",
        ],
    },
    "rename_delete": {
        "title": "Renames, deletes and new objects",
        "payload": "object_rename {new_name}; object_delete {}; object_create {object_type: measure|column, table, name, properties}",
        "syntax": [
            "new_name is the plain name, no brackets or quotes. name_propose gives a name that follows the confirmed naming rules.",
        ],
        "best_practice": [
            "Check brain_dependencies(direction='downstream', depth=2) first: a delete is always reviewed by the user.",
            "Prefer hiding (is_hidden) over deleting when other reports may use the object.",
        ],
        "impact": [
            "A rename is rewritten through the plan: DAX references and the visual fields of the session's reports follow. "
            "Report-level fields outside the session's reports do not.",
            "A delete breaks every dependent; the check lists them with severity.",
            "A name clash with an existing object is refused (name_clash).",
        ],
    },
}

ALIASES = {"measures": "measure", "dax": "measure", "columns": "column", "calculated_column": "column", "udf": "function",
           "functions": "function", "m": "m_query", "power_query": "m_query", "partition": "m_query", "expression": "m_query",
           "query": "m_query", "calculation_item": "calculation_group", "calc_group": "calculation_group",
           "rename": "rename_delete", "delete": "rename_delete", "create": "rename_delete"}


def guide(topic: str | None = None) -> dict[str, Any]:
    """The notes of one topic, or the topic list and the change workflow."""

    key = (topic or "").strip().lower().replace("-", "_").replace(" ", "_")
    key = ALIASES.get(key, key)
    if key in TOPICS:
        return {"topic": key, **TOPICS[key], "workflow": WORKFLOW}
    return {
        "topics": {name: value["title"] for name, value in TOPICS.items()},
        "workflow": WORKFLOW,
        "hint": "Call brain_guide(topic) before you write a change of that kind.",
        **({"unknown_topic": topic} if key else {}),
    }
