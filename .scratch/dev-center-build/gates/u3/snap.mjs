// Write the U3 screen snapshots for the kit gates: one HTML file for each screen and theme, with the
// CSS inline and the gate script inline (classic script, so that it runs from file://).
// Fonts are left out (the kit gates measure color and geometry). Usage: node snap.mjs <build-dir> <out-dir>
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const [build, out] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const css = readFileSync(join(build, "u3.css"), "utf8").replace(/@font-face\s*\{[^}]*\}/g, "");
const js = readFileSync(join(build, "u3.js"), "utf8").replace(/<\/script/gi, "<\\/script");
for (const screen of ["list", "create", "work"]) {
  for (const theme of ["dark", "light"]) {
    const root = theme === "light" ? '<html lang="en" data-theme="light">' : '<html lang="en" class="dark">';
    const html = `<!doctype html>${root}<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Development Center ${screen}</title><style>${css}</style></head><body><div id="root"></div><script>window.__U3_SCREEN__ = ${JSON.stringify(screen)};</script><script>${js}</script></body></html>`;
    writeFileSync(join(out, `u3-${screen}-${theme}.html`), html);
  }
}
console.log("ok");
