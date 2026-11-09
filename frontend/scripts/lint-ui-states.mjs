#!/usr/bin/env node
// Runs lintapple's checkPage over every main view of the app, in both app themes and every
// policy viewport, and writes one merged JSON report (same shape as `lintapple --json`'s summary).
//
// The plain `npm run lint:ui` only sees the default landing view in the default (dark) theme,
// because the theme is stored in localStorage, not driven by prefers-color-scheme.
//
// Usage (API + Vite running, see tests/ui_audit_server.py):
//   node scripts/lint-ui-states.mjs [--url http://localhost:5173] [--out report.json]
//                                   [--policy ui-policy.json] [--screenshots dir] [--only overview,graph] [--themes dark,light]
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { chromium } from "playwright";
import { checkPage, validatePolicy, summarizeFindings } from "lintapple";

const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, value, index, all) => {
  if (value.startsWith("--")) pairs.push([value.slice(2), all[index + 1]?.startsWith("--") ? "1" : all[index + 1] ?? "1"]);
  return pairs;
}, []));
const baseUrl = args.url || "http://localhost:5173";
const policy = validatePolicy(JSON.parse(await readFile(args.policy || new URL("../ui-policy.json", import.meta.url), "utf8")));
const themes = (args.themes || "dark,light").split(",");
const only = args.only ? new Set(args.only.split(",")) : null;

const nav = (label) => async (page) => {
  const button = page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: label, exact: false });
  await button.first().click();
};
const settle = (page, ms = 600) => page.waitForTimeout(ms);

// Each state starts from a fresh load of the app.
const STATES = [
  { name: "overview", run: async (page) => { await page.getByRole("heading", { level: 1 }).first().waitFor(); } },
  { name: "search", run: async (page) => {
    await nav("Search")(page);
    const input = page.locator(".search-field input").first();
    await input.fill("sales");
    await input.press("Enter");
    await page.waitForTimeout(1200);
  } },
  { name: "graph", run: async (page) => { await nav("Graph")(page); await page.locator(".react-flow__node").first().waitFor({ timeout: 15000 }); await settle(page, 1200); } },
  { name: "graph-details", run: async (page) => {
    await nav("Graph")(page);
    const node = page.locator(".react-flow__node").first();
    await node.waitFor({ timeout: 15000 });
    await settle(page, 800);
    await node.focus();
    await page.keyboard.press("Enter");
    await page.locator(".graph-detail-pane").first().waitFor({ timeout: 10000 });
    await settle(page, 1200);
  } },
  { name: "inspector-browse", run: async (page) => { await nav("Inspector")(page); await settle(page, 1500); } },
  { name: "inspector-object", run: async (page) => {
    await nav("Search")(page);
    const input = page.locator(".search-field input").first();
    await input.fill("Net Sales");
    await input.press("Enter");
    await page.waitForTimeout(1200);
    await page.locator("main").getByText("Net Sales", { exact: true }).first().click();
    await settle(page, 2000);
  } },
  { name: "review", run: async (page) => { await nav("Review queue")(page); await settle(page, 2000); } },
  { name: "devcenter", run: async (page) => { await nav("Merge models")(page); await settle(page, 2000); } },
  { name: "settings-project", run: async (page) => { await nav("Settings")(page); await settle(page, 1200); } },
  { name: "settings-colors", run: async (page) => { await nav("Settings")(page); await page.getByRole("tab", { name: "Graph colors" }).click(); await settle(page, 800); } },
  { name: "settings-summary", run: async (page) => { await nav("Settings")(page); await page.getByRole("tab", { name: "Model summary" }).click(); await settle(page, 1500); } },
];

const browser = await chromium.launch();
const findings = [];
const states = [];
const failures = [];
const suppressed = [];
try {
  for (const theme of themes) {
    for (const viewport of policy.viewports) {
      const context = await browser.newContext({ viewport, colorScheme: theme, reducedMotion: "reduce", locale: "en-US", timezoneId: "UTC", deviceScaleFactor: args.screenshots ? 2 : 1 });
      await context.addInitScript((value) => { try { localStorage.setItem("pbibrain-theme", value); } catch { /* ignore */ } }, theme);
      for (const state of STATES) {
        if (only && !only.has(state.name)) continue;
        const page = await context.newPage();
        const label = `${state.name}@${viewport.width}/${theme}`;
        try {
          await page.goto(baseUrl, { waitUntil: "networkidle" });
          await page.locator(".app-shell").waitFor();
          await state.run(page);
          await page.evaluate(() => {
            document.querySelectorAll("details:not([open])").forEach((d) => { d.open = true; });
          });
          await page.evaluate(() => document.fonts.ready);
          const report = await checkPage(page, policy);
          report.findings = await page.evaluate((findings) => {
            return findings.filter((finding) => {
              if (
                (finding.rule === "control-size" || finding.rule === "icon-size") &&
                (finding.actual.includes("× 0px") || finding.actual.startsWith("0 ×"))
              ) {
                let el = null;
                try { el = document.querySelector(finding.selector); } catch { return true; }
                if (!el) return true;
                const style = window.getComputedStyle(el);
                if (style.display === "none" || style.visibility === "hidden" || el.closest("details:not([open])")) {
                  return false;
                }
                const rect = el.getBoundingClientRect();
                if (el.offsetWidth > 0 || el.offsetHeight > 0 || rect.width > 0 || rect.height > 0) {
                  return false;
                }
              }
              if (finding.rule === "content-clipping" && finding.actual.includes("could not be measured")) {
                let el = null;
                try { el = document.querySelector(finding.selector); } catch { return true; }
                if (el && (el.closest("details:not([open])") || el.closest("[data-state=closed]"))) {
                  return false;
                }
              }
              return true;
            });
          }, report.findings);
          const hints = await page.evaluate((selectors) => selectors.map((selector) => {
            const describe = (el) => {
              if (!el) return "";
              const cls = typeof el.className === "string" ? el.className : el.getAttribute?.("class") || "";
              const classes = cls.split(/\s+/).filter((c) => c && !/^(hover|focus|data|aria|dark|has|\[)/.test(c) && !c.includes(":")).slice(0, 3);
              return el.tagName.toLowerCase() + (classes.length ? "." + classes.join(".") : "");
            };
            let el = null;
            try { el = document.querySelector(selector); } catch { return { hint: "" }; }
            if (!el) return { hint: "" };
            const chain = [];
            for (let node = el; node && chain.length < 3 && node !== document.body; node = node.parentElement) chain.unshift(describe(node));
            return { hint: chain.join(" > "), text: (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 40) };
          }), report.findings.map((finding) => finding.selector));
          report.findings.forEach((finding, index) => Object.assign(finding, hints[index]));
          states.push({ name: state.name, viewport, colorScheme: theme, elements: report.elements, controls: report.controls, numericElements: report.numericElements, alignmentGroups: report.alignmentGroups, radiusContracts: report.radiusContracts, findings: report.findings.length });
          suppressed.push(...report.suppressed.map((item) => ({ ...item, state: state.name, viewport, colorScheme: theme })));
          findings.push(...report.findings.map((finding) => ({ ...finding, state: state.name, viewport: finding.viewport ?? viewport, colorScheme: theme })));
          if (args.screenshots) {
            await mkdir(args.screenshots, { recursive: true });
            await page.screenshot({ path: `${args.screenshots}/${state.name}-${viewport.width}-${theme}.png`, fullPage: false });
          }
          console.error(`${label}: ${report.findings.length} findings`);
        } catch (error) {
          failures.push({ state: label, error: String(error?.message || error).split("\n")[0] });
          console.error(`${label}: FAILED ${String(error?.message || error).split("\n")[0]}`);
        } finally {
          await page.close();
        }
      }
      await context.close();
    }
  }
} finally {
  await browser.close();
}

const summary = summarizeFindings(findings);
const out = { url: baseUrl, generatedAt: new Date().toISOString(), policy, summary: { occurrences: summary.occurrences, problems: summary.problems, failed: summary.failed, unresolved: summary.unresolved, byRule: summary.byRule }, states, failures, suppressed: { total: suppressed.length, byRule: Object.entries(suppressed.reduce((acc, item) => { acc[item.rule] = (acc[item.rule] || 0) + 1; return acc; }, {})).map(([rule, count]) => ({ rule, count })), byReason: Object.entries(suppressed.reduce((acc, item) => { acc[item.reason] = (acc[item.reason] || 0) + 1; return acc; }, {})).map(([reason, count]) => ({ reason: reason.slice(0, 80), count })) }, groups: summary.groups };
if (args.out) await writeFile(args.out, JSON.stringify(out, null, 2));
console.log(`suppressed=${suppressed.length}`);
console.log(`occurrences=${summary.occurrences} problems=${summary.problems} failed=${summary.failed} unresolved=${summary.unresolved}`);
for (const rule of summary.byRule) console.log(`  ${rule.rule.padEnd(20)} problems=${String(rule.problems).padStart(4)} occurrences=${rule.occurrences}`);
process.exitCode = summary.occurrences || failures.length ? 1 : 0;
