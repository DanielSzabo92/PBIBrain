// The app shell and its views as one text, for tests that check markup by reading the source.
// The views moved out of App.jsx into src/views/; a test reads them all, wherever a view now lives.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = path.join(path.dirname(fileURLToPath(import.meta.url)), "../src");

export function appSource() {
  const views = fs.readdirSync(path.join(SRC, "views")).filter((name) => name.endsWith(".jsx")).sort();
  return [path.join(SRC, "App.jsx"), ...views.map((name) => path.join(SRC, "views", name))]
    .map((file) => fs.readFileSync(file, "utf8"))
    .join("\n");
}

// app.css is a list of imports, one file per view or component; this returns the rules in cascade order.
export function appCss(file = path.join(SRC, "app.css")) {
  return fs.readFileSync(file, "utf8").replace(/@import "([^"]+)";/g, (_, name) => appCss(path.join(path.dirname(file), name)));
}
