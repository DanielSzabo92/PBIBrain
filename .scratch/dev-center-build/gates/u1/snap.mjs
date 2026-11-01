// Write the U1 specimen snapshots for the kit gates: one HTML file for each theme, with the
// CSS inline and the specimen script inline (classic script, so that it runs from file://).
// Fonts are left out (the kit gates measure color and geometry). Usage: node snap.mjs <build-dir> <out-dir>
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const [build, out] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const css = readFileSync(join(build, "specimen.css"), "utf8").replace(/@font-face\s*\{[^}]*\}/g, "");
const js = readFileSync(join(build, "specimen.js"), "utf8").replace(/<\/script/gi, "<\\/script");
for (const theme of ["dark", "light"]) {
  const root = theme === "light" ? '<html lang="en" data-theme="light">' : '<html lang="en" class="dark">';
  const html = `<!doctype html>${root}<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Part specimen</title><style>${css}</style></head><body><div id="root"></div><script>${js}</script></body></html>`;
  writeFileSync(join(out, `specimen-${theme}.html`), html);
}
console.log("ok");
