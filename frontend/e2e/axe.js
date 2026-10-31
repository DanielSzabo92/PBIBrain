// axe-core helper for the e2e specs (UI design A1: axe-core@4.10.2, WCAG 2.2 AA rule tags).
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const AXE_PATH = require.resolve("axe-core/axe.min.js");
export const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

// Run axe on the page and return the violations as short records.
export async function axeViolations(page, { include, rules } = {}) {
  const loaded = await page.evaluate(() => Boolean(window.axe));
  if (!loaded) await page.addScriptTag({ path: AXE_PATH });
  return page.evaluate(async ({ tags, include: scope, rules: only }) => {
    const options = only ? { runOnly: { type: "rule", values: only } } : { runOnly: { type: "tag", values: tags } };
    const result = await window.axe.run(scope ? document.querySelector(scope) : document, options);
    return result.violations.map((violation) => ({
      id: violation.id,
      impact: violation.impact,
      nodes: violation.nodes.map((node) => `${node.target.join(" ")}: ${node.failureSummary}`.slice(0, 400)),
    }));
  }, { tags: AXE_TAGS, include, rules });
}

export async function setTheme(context, theme) {
  await context.addInitScript((value) => {
    try { localStorage.setItem("pbibrain-theme", value); } catch { /* Storage can be unavailable. */ }
  }, theme);
}
