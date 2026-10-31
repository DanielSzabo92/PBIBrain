// Repo lint for frontend/src/devcenter/** (UI design A3, A5, A20, and the CI gate list of section 10).
// Rules: no native <select>, no hex color, no emoji, no em dash or en dash, no one-sided colored border.
import test from "node:test";
import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DEVCENTER = fileURLToPath(new URL("../src/devcenter/", import.meta.url));
const EXTENSIONS = new Set([".js", ".jsx", ".mjs", ".css", ".json", ".html"]);

const SIDES = "(?:left|right|top|bottom|inline|block|inline-start|inline-end|block-start|block-end)";
const CAMEL_SIDES = "(?:Left|Right|Top|Bottom|Inline|Block|InlineStart|InlineEnd|BlockStart|BlockEnd)";
// A value with one of these words or functions has a color.
const COLOR_VALUE = /#[0-9a-f]{3,8}\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color|color-mix|var)\(|\b(?:currentcolor|black|white|red|green|blue|gray|grey|orange|yellow|purple)\b/i;
const NO_COLOR = /^\s*(?:0|none|transparent|inherit|initial|unset|revert)\s*(?:!important)?\s*$/i;

const RULES = [
  {
    id: "native-select",
    text: "Use the Select part, not a native <select> (A20).",
    find: (source) => [...source.matchAll(/<select[\s>/]|createElement\(\s*["'`]select["'`]/gi)],
  },
  {
    id: "hex-color",
    text: "Use a theme token, not a hex color.",
    find: (source) => [...source.matchAll(/(?<![\w&#/-])#(?:[0-9a-f]{8}|[0-9a-f]{6}|[0-9a-f]{3,4})(?![\w-])/gi)],
  },
  {
    id: "emoji",
    text: "Do not use an emoji (A20).",
    find: (source) => [...source.matchAll(/[\p{Extended_Pictographic}\u{1F1E6}-\u{1F1FF}\u{FE0F}]/gu)],
  },
  {
    id: "dash",
    text: "Do not use an em dash or an en dash (A20).",
    find: (source) => [...source.matchAll(/[\u2013\u2014]/g)],
  },
  {
    id: "one-sided-border",
    text: "Do not use a one-sided colored border (A5).",
    find: (source) => {
      const found = [];
      // CSS: border-left: 2px solid var(--bad); border-top-color: var(--ok);
      for (const match of source.matchAll(new RegExp(`(?<![\\w-])border-${SIDES}(-color)?\\s*:\\s*([^;}\\n]+)`, "gi"))) {
        const value = match[2];
        if (match[1] ? !NO_COLOR.test(value) : COLOR_VALUE.test(value)) found.push(match);
      }
      // Inline style: borderLeft: "2px solid var(--bad)", borderTopColor: "var(--ok)"
      for (const match of source.matchAll(new RegExp(`\\bborder${CAMEL_SIDES}(Color)?\\s*:\\s*(["'\`])([^"'\`]*)\\2`, "g"))) {
        const value = match[3];
        if (match[1] ? !NO_COLOR.test(value) : COLOR_VALUE.test(value)) found.push(match);
      }
      // Tailwind: border-l-bad, border-t-[var(--ok)], border-s-red-500. Width-only classes (border-l-2) are permitted.
      for (const match of source.matchAll(/(?<![\w-])border-[ltrbse]-(?!\d+(?![\w-])|\[\d)(?!px\b|transparent\b)[a-z[][\w[\]().%,-]*/g)) {
        found.push(match);
      }
      return found;
    },
  },
];

function lineOf(source, index) {
  return source.slice(0, index).split("\n").length;
}

export function lintSource(source, file = "<input>") {
  const findings = [];
  for (const rule of RULES) {
    for (const match of rule.find(source)) {
      findings.push({ rule: rule.id, file, line: lineOf(source, match.index), text: match[0], message: rule.text });
    }
  }
  return findings;
}

async function listFiles(folder) {
  const entries = await readdir(folder, { withFileTypes: true }).catch((error) => {
    if (error.code === "ENOENT") return [];
    throw error;
  });
  const files = [];
  for (const entry of entries) {
    const full = path.join(folder, entry.name);
    if (entry.isDirectory()) files.push(...(await listFiles(full)));
    else if (EXTENSIONS.has(path.extname(entry.name))) files.push(full);
  }
  return files;
}

const rulesOf = (source, file) => [...new Set(lintSource(source, file).map((finding) => finding.rule))];

// The bad inputs use escapes for the emoji and the dashes, so that this file passes its own rules.
const BAD_INPUTS = [
  ["native-select", "Picker.jsx", `export function Picker() { return <select aria-label="Source"><option>A</option></select>; }`],
  ["native-select", "picker.js", `const field = document.createElement("select");`],
  ["hex-color", "tone.css", `.badge { color: #f07f7f; }`],
  ["hex-color", "Badge.jsx", `export const Badge = () => <span style={{ color: "#fff" }}>New</span>;`],
  ["emoji", "copy.js", `export const done = "Plan applied \u{1F680}";`],
  ["emoji", "Status.jsx", `export const Ok = () => <span>\u2705 Valid</span>;`],
  ["dash", "copy.js", `export const text = "Sources \u2014 2 changed";`],
  ["dash", "range.js", `export const pages = "1\u20135";`],
  ["one-sided-border", "row.css", `.row { border-left: 3px solid var(--bad); }`],
  ["one-sided-border", "row.css", `.row { border-inline-start-color: var(--warn); }`],
  ["one-sided-border", "Row.jsx", `export const Row = () => <div style={{ borderLeft: "2px solid var(--ok)" }} />;`],
  ["one-sided-border", "Row.jsx", `export const Row = () => <div className="border-l-2 border-l-bad" />;`],
];

const CLEAN_INPUT = `
  .row { border: 1px solid var(--control-border); border-left-width: 2px; border-top: 0; color: var(--text); }
  .row:focus-visible { outline: 2px solid var(--brand); }
  export const Row = () => <div className="border border-l-2 rounded-md" style={{ borderTopColor: "transparent" }}>Sources: 2 changed, pages 1 to 5</div>;
  const anchor = "#root"; const id = "#add-source";
`;

test("the lint fails on each kind of bad input", () => {
  for (const [rule, file, source] of BAD_INPUTS) {
    assert.deepEqual(rulesOf(source, file), [rule], `${file}: ${source}`);
  }
});

test("the lint passes on clean input", () => {
  assert.deepEqual(lintSource(CLEAN_INPUT), []);
});

test("frontend/src/devcenter/** passes the lint", async () => {
  const files = await listFiles(DEVCENTER);
  assert.ok(files.length > 0, "frontend/src/devcenter/ must contain files");
  const findings = [];
  for (const file of files) findings.push(...lintSource(await readFile(file, "utf8"), path.relative(DEVCENTER, file)));
  assert.deepEqual(findings, [], findings.map((item) => `${item.file}:${item.line} ${item.rule} "${item.text}" ${item.message}`).join("\n"));
});
