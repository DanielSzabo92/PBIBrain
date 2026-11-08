import assert from "node:assert/strict";
import test from "node:test";
import { formatDaxName, formatObjectRef, readableText } from "../src/presentation.js";
import { formatOperationKind } from "../src/devcenter/phrases.js";
import { valueText, targetText } from "../src/devcenter/screens/log/logModel.js";

test("formatDaxName formats tables and table/measure/column references in DAX syntax", () => {
  assert.equal(formatDaxName("Sales", "Net Sales"), "'Sales'[Net Sales]");
  assert.equal(formatDaxName("Sales"), "'Sales'");
  assert.equal(formatDaxName("", "Net Sales"), "[Net Sales]");
  assert.equal(formatDaxName("'Sales'", "Net Sales"), "'Sales'[Net Sales]");
});

test("formatObjectRef formats raw URIs, kebab row keys, and relationship identifiers", () => {
  assert.equal(formatObjectRef("measure:Sales/Net Sales"), "'Sales'[Net Sales]");
  assert.equal(formatObjectRef("column:Sales/Amount"), "'Sales'[Amount]");
  assert.equal(formatObjectRef("table:Sales"), "'Sales'");
  assert.equal(formatObjectRef("row-gross-margin"), "Gross Margin");
  assert.equal(formatObjectRef("relationship-sales"), "Relationship (Sales)");
  assert.equal(formatObjectRef("plainText"), "plainText");
});

test("formatOperationKind maps raw engine plan opcodes to human readable phrases", () => {
  assert.equal(formatOperationKind("SET_EXPRESSION"), "Set expression");
  assert.equal(formatOperationKind("SET_PROPERTIES"), "Set properties");
  assert.equal(formatOperationKind("SET_FORMAT_STRING"), "Set format string");
  assert.equal(formatOperationKind("REBIND_FIELD"), "Rebind field");
  assert.equal(formatOperationKind("ADD_OBJECT"), "Add object");
  assert.equal(formatOperationKind("DELETE_OBJECT"), "Delete object");
  assert.equal(formatOperationKind("UNKNOWN_OP"), "Unknown op");
});

test("valueText and targetText format merge model logs into human readable summaries without raw JSON", () => {
  assert.equal(valueText({ choice: "donor", source_id: "src-2" }), "Take from src-2");
  assert.equal(valueText({ choice: "target" }), "Keep target");
  assert.equal(valueText({ policy: "cascade" }), "Remove dependents");
  assert.equal(valueText({ policy: "block" }), "Block removal");
  assert.equal(targetText("row-gross-margin"), "Gross Margin");
  assert.equal(targetText("measure:Sales/Net Sales"), "'Sales'[Net Sales]");
});

test("readableText sanitizes internal engine jargon into domain user friendly copy", () => {
  assert.equal(readableText("USES, FILTERS and page bindings"), "field usage and visual filters");
  assert.equal(
    readableText("Report bindings of the scanned reports (USES, FILTERS and page bindings)."),
    "Field usage and visual filters across scanned reports."
  );
  assert.equal(
    readableText("SCANNER_COVERAGE_UNKNOWN"),
    "Scanner coverage unknown: metadata incomplete for this source"
  );
  assert.equal(
    readableText("Explicit modification target"),
    "Directly modified object"
  );
  assert.equal(
    readableText("Consumes potentially affected object"),
    "Uses an object affected by this change"
  );
});
