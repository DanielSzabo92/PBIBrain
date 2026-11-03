// Unit tests for Row detail and Merge Choice model (step U6).
// All text follows ASD-STE100 rules.
import assert from "node:assert/strict";
import test from "node:test";
import {
  buildMergeChoiceSpec,
  buildPropertyPickerItems,
  formatMergeChoiceLabel,
  formatRemovalPolicySummary,
  getAlignmentStepText,
  getJoinCandidateRows,
  getPossibleRenameInfo,
  normalizeChoiceKind,
} from "../src/devcenter/components/rowDetailModel.js";

const DONORS = [
  { source_id: "src-2", display_name: "Finance model", role: "donor" },
  { source_id: "src-3", display_name: "Regional model", role: "donor" },
];

const BASE_SESSION = {
  target: {
    model: { source_id: "src-1" },
    report: { source_id: "src-1-rpt", mode: "existing" },
  },
};

test("normalizeChoiceKind normalizes S3 and UI choice aliases", () => {
  assert.equal(normalizeChoiceKind("keep_target"), "keep");
  assert.equal(normalizeChoiceKind("keep"), "keep");
  assert.equal(normalizeChoiceKind("take_from"), "take");
  assert.equal(normalizeChoiceKind("take"), "take");
  assert.equal(normalizeChoiceKind("take_selected_properties"), "take_properties");
  assert.equal(normalizeChoiceKind("add_as_new_name"), "add_new_name");
  assert.equal(normalizeChoiceKind("promote_to_model"), "promote");
  assert.equal(normalizeChoiceKind("copy_to_target_report"), "copy_to_report");
});

test("buildMergeChoiceSpec enables all 6 main choices when row is in target and donor", () => {
  const row = {
    row_key: "measure:Sales.Net Sales",
    object_type: "measure",
    name: "Net Sales",
    row_state: "different",
    cells: {
      "src-1": { state: "target" },
      "src-2": { state: "different", phrases: ["expression_changed"] },
    },
  };
  const spec = buildMergeChoiceSpec({ row, session: BASE_SESSION, donors: DONORS });
  assert.equal(spec.mainChoices.length, 6);
  for (const item of spec.mainChoices) {
    assert.equal(item.disabled, false, `Expected ${item.value} to be enabled`);
  }
  assert.equal(spec.reportMeasureChoices.length, 0);
});

test("buildMergeChoiceSpec sets disabled reasons when row is missing in target", () => {
  const row = {
    row_key: "measure:Sales.Budget",
    object_type: "measure",
    name: "Budget",
    row_state: "missing",
    cells: {
      "src-1": { state: "missing" },
      "src-2": { state: "different" },
    },
  };
  const spec = buildMergeChoiceSpec({ row, session: BASE_SESSION, donors: DONORS });
  const byVal = Object.fromEntries(spec.mainChoices.map((c) => [c.value, c]));

  assert.equal(byVal.keep.disabled, false);
  assert.equal(byVal.keep.label, "Do not add (keep target)");
  assert.equal(byVal.keep.reason, "The target stays without this object.");

  assert.equal(byVal.take_properties.disabled, true);
  assert.equal(byVal.take_properties.reason, "The target does not have this object. Nothing to change.");

  assert.equal(byVal.remove.disabled, true);
  assert.equal(byVal.remove.reason, "The target does not have this object.");

  assert.equal(byVal.take.disabled, false);
  assert.equal(byVal.add_new_name.disabled, false);
  assert.equal(byVal.skip.disabled, false);
});

test("buildMergeChoiceSpec disables donor choices when row is only in target", () => {
  const row = {
    row_key: "measure:Sales.Legacy",
    object_type: "measure",
    name: "Legacy",
    row_state: "missing",
    cells: {
      "src-1": { state: "target" },
      "src-2": { state: "missing" },
      "src-3": { state: "missing" },
    },
  };
  const spec = buildMergeChoiceSpec({ row, session: BASE_SESSION, donors: DONORS });
  const byVal = Object.fromEntries(spec.mainChoices.map((c) => [c.value, c]));

  assert.equal(byVal.take.disabled, true);
  assert.equal(byVal.take.reason, "No source has this object.");
  assert.equal(byVal.take_properties.disabled, true);
  assert.equal(byVal.take_properties.reason, "No source has this object.");
  assert.equal(byVal.add_new_name.disabled, true);
  assert.equal(byVal.add_new_name.reason, "No source has this object.");
  assert.equal(byVal.keep.disabled, false);
  assert.equal(byVal.remove.disabled, false);
});

test("buildMergeChoiceSpec disables take_properties for unsupported object types", () => {
  const row = {
    row_key: "table:Customer",
    object_type: "table",
    name: "Customer",
    row_state: "different",
    cells: {
      "src-1": { state: "target" },
      "src-2": { state: "different" },
    },
  };
  const spec = buildMergeChoiceSpec({ row, session: BASE_SESSION, donors: DONORS });
  const byVal = Object.fromEntries(spec.mainChoices.map((c) => [c.value, c]));

  assert.equal(byVal.take_properties.disabled, true);
  assert.equal(byVal.take_properties.reason, "Only for measures, columns, and relationships.");
});

test("buildMergeChoiceSpec includes report measure choices and disables copy when already in target report", () => {
  const rowMissingTarget = {
    row_key: "measure:Report.Variance",
    object_type: "measure",
    subtype: "report_measure",
    name: "Variance",
    row_state: "missing",
    cells: {
      "src-1": { state: "missing" },
      "src-2": { state: "different" },
    },
  };
  const specMissing = buildMergeChoiceSpec({
    row: rowMissingTarget,
    session: BASE_SESSION,
    donors: DONORS,
  });
  assert.equal(specMissing.reportMeasureChoices.length, 2);
  assert.equal(specMissing.reportMeasureChoices[0].value, "promote");
  assert.equal(specMissing.reportMeasureChoices[0].disabled, false);
  assert.equal(specMissing.reportMeasureChoices[1].value, "copy_to_report");
  assert.equal(specMissing.reportMeasureChoices[1].disabled, false);

  const rowInTarget = {
    ...rowMissingTarget,
    cells: {
      "src-1": { state: "target" },
      "src-2": { state: "different" },
    },
  };
  const specInTarget = buildMergeChoiceSpec({
    row: rowInTarget,
    session: BASE_SESSION,
    donors: DONORS,
  });
  assert.equal(specInTarget.reportMeasureChoices[1].disabled, true);
  assert.equal(
    specInTarget.reportMeasureChoices[1].reason,
    "This measure is already in the target report."
  );
});

test("buildPropertyPickerItems preselects different properties and disables same properties", () => {
  const row = {
    row_key: "measure:Sales.Net Sales",
    object_type: "measure",
    name: "Net Sales",
    properties: [
      { source_id: "src-2", property: "expression", phrase_id: "expression_changed" },
      {
        source_id: "src-2",
        property: "format_string",
        phrase_id: "format_string_changed",
        old: "#,0",
        new: "$#,0.00",
      },
    ],
  };
  const items = buildPropertyPickerItems(row, "src-2");
  const byId = Object.fromEntries(items.map((i) => [i.id, i]));

  assert.equal(byId.expression.different, true);
  assert.equal(byId.expression.disabled, false);
  assert.equal(byId.format_string.different, true);
  assert.equal(byId.format_string.summary, "#,0 -> $#,0.00");

  assert.equal(byId.display_folder.different, false);
  assert.equal(byId.display_folder.disabled, true);
  assert.equal(byId.display_folder.summary, "Same");
});

test("getPossibleRenameInfo detects possible_rename note on row or cell", () => {
  const row = {
    row_key: "measure:Sales.Net Sales",
    object_type: "measure",
    name: "Net Sales",
    cells: {
      "src-1": { state: "target" },
      "src-2": {
        state: "missing",
        notes: [
          {
            note_id: "possible_rename",
            other_row_key: "measure:Sales.Total Net Sales",
            other_name: "Total Net Sales",
          },
        ],
      },
    },
  };
  const info = getPossibleRenameInfo(row, [], DONORS);
  assert.ok(info);
  assert.equal(info.sourceId, "src-2");
  assert.equal(info.sourceName, "Finance model");
  assert.equal(info.otherRowKey, "measure:Sales.Total Net Sales");
  assert.equal(info.otherName, "Total Net Sales");
});

test("getJoinCandidateRows returns unmatched donor rows of the same object type", () => {
  const targetRow = {
    row_key: "measure:Sales.Net Sales",
    object_type: "measure",
    name: "Net Sales",
    cells: { "src-1": { state: "target" }, "src-2": { state: "missing" } },
  };
  const unmatchedMeasure = {
    row_key: "measure:Sales.Budget",
    object_type: "measure",
    table: "Sales",
    name: "Budget",
    cells: { "src-1": { state: "missing" }, "src-2": { state: "different" } },
  };
  const unmatchedTable = {
    row_key: "table:Region",
    object_type: "table",
    name: "Region",
    cells: { "src-1": { state: "missing" }, "src-2": { state: "different" } },
  };
  const candidates = getJoinCandidateRows(
    targetRow,
    [targetRow, unmatchedMeasure, unmatchedTable],
    DONORS,
    "src-1",
    null
  );
  assert.equal(candidates.length, 1);
  assert.equal(candidates[0].rowKey, "measure:Sales.Budget");
  assert.match(candidates[0].label, /Budget/);
  assert.match(candidates[0].label, /Finance model/);
});

test("formatMergeChoiceLabel and formatRemovalPolicySummary format copy strings", () => {
  assert.equal(formatMergeChoiceLabel(null, DONORS), "Not set");
  assert.equal(formatMergeChoiceLabel({ kind: "keep" }, DONORS), "Keep target");
  assert.equal(
    formatMergeChoiceLabel({ kind: "take", source_id: "src-2" }, DONORS),
    "Take from Finance model"
  );
  assert.equal(
    formatMergeChoiceLabel(
      { kind: "take_properties", source_id: "src-2", properties: ["expression", "description"] },
      DONORS
    ),
    "Take properties from Finance model (2)"
  );
  assert.equal(
    formatMergeChoiceLabel({ kind: "add_new_name", new_name: "Net Sales 2" }, DONORS),
    "Add as new name: Net Sales 2"
  );

  assert.equal(
    formatRemovalPolicySummary("block", null, { dependents: [{ id: "1" }, { id: "2" }] }, "measure"),
    "Removal policy: Block. 2 objects use this measure. The plan is not valid until you resolve each one."
  );
  assert.equal(
    formatRemovalPolicySummary("repoint", "Sales[Gross Margin]", { dependents: [{ id: "1" }] }),
    "Removal policy: Repoint. 1 references go to Sales[Gross Margin]."
  );
  assert.equal(
    formatRemovalPolicySummary("cascade", null, { cascade: { count: 3 } }),
    "Removal policy: Cascade. 3 other objects are removed with it."
  );
  assert.equal(
    getAlignmentStepText({ object_type: "measure", alignment_step: "lineage_tag" }),
    "Same lineage tag"
  );
});
