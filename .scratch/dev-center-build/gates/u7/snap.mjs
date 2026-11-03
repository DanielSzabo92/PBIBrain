// Write the U7 Plan screen snapshots for the kit gates: one HTML file for light and dark themes.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const [build, out] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const css = readFileSync(join(build, "u7.css"), "utf8").replace(/@font-face\s*\{[^}]*\}/g, "");
const js = readFileSync(join(build, "u7.js"), "utf8").replace(/<\/script/gi, "<\\/script");

for (const theme of ["dark", "light"]) {
  const root = theme === "light" ? '<html lang="en" data-theme="light">' : '<html lang="en" class="dark">';
  const html = `<!doctype html>${root}<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Development Center Plan</title><style>${css}</style></head><body><div id="root"></div><script>${js}</script></body></html>`;
  writeFileSync(join(out, `u7-plan-${theme}.html`), html);
}
console.log("ok");
