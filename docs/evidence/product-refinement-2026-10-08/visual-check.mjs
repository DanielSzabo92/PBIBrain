import { chromium } from "../../../frontend/node_modules/playwright/index.mjs";
import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const output = fileURLToPath(new URL("./", import.meta.url));
const browser = await chromium.launch({ channel: "chrome", headless: true });
const results = [];
const errors = [];
const rgb = (hex) => {
  const value = hex.replace("#", "");
  const expanded = value.length === 3 ? [...value].map((digit) => digit + digit).join("") : value;
  return expanded.match(/../g).map((part) => parseInt(part, 16) / 255);
};
const luminance = (hex) => rgb(hex).map((c) => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4).reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i], 0);
const contrast = (a, b) => (Math.max(luminance(a), luminance(b)) + 0.05) / (Math.min(luminance(a), luminance(b)) + 0.05);

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on("pageerror", (error) => errors.push(error.message));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("http://127.0.0.1:18766");
  await page.locator(".project-counts").waitFor();
  await page.screenshot({ path: `${output}home-dark.png` });
  await page.getByRole("navigation").getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("searchbox", { name: "Search the brain" }).fill("Net Sales");
  await page.locator(".search-result").first().waitFor();
  await page.screenshot({ path: `${output}search-dark.png` });
  await page.locator(".search-result").first().click();
  await page.locator(".object-expression").waitFor();
  await page.screenshot({ path: `${output}inspector-dark.png` });
  await page.getByRole("navigation").getByRole("button", { name: /^Review queue/ }).click();
  await page.locator(".review-item").first().waitFor();
  await page.screenshot({ path: `${output}review-dark.png` });
  await page.getByRole("navigation").getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByLabel("Project name", { exact: true }).waitFor();
  await page.screenshot({ path: `${output}settings-dark.png` });

  for (const theme of ["dark", "light"]) {
    if (theme === "light") await page.getByRole("button", { name: "Switch to light theme" }).click();
    const tokens = await page.evaluate(() => {
      const style = getComputedStyle(document.documentElement);
      return Object.fromEntries(["text", "text-2", "text-3", "surface", "surface-2", "surface-3", "control-border", "ok", "warn", "bad", "info"].map((key) => [key, style.getPropertyValue(`--${key}`).trim()]));
    });
    for (const foreground of ["text", "text-2", "text-3", "ok", "warn", "bad", "info"]) {
      for (const background of ["surface", "surface-2", "surface-3"]) {
        const ratio = contrast(tokens[foreground], tokens[background]);
        results.push({ theme, foreground, background, ratio: +ratio.toFixed(2), passed: ratio >= 4.5 });
      }
    }
    results.push({ theme, check: "input boundary", ratio: +contrast(tokens["control-border"], tokens["surface-2"]).toFixed(2), passed: contrast(tokens["control-border"], tokens["surface-2"]) >= 3 });
    for (const width of [320, 360, 768, 1024, 1200, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const name of ["Overview", "Search", "Inspector", "Review queue", "Settings", "Graph"]) {
        await page.getByRole("navigation").getByRole("button", { name: new RegExp(`^${name}`) }).click();
        if (name === "Graph") await page.locator(".react-flow__node-brain").first().waitFor();
        const sizing = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
        results.push({ theme, name, ...sizing, passed: sizing.scrollWidth <= sizing.width });
        if (sizing.scrollWidth > sizing.width) console.log(await page.locator(".graph-filter-card, .graph-canvas-toolbar, .graph-meta, .graph-filters, .graph-filter-top [data-slot=\"tabs-list\"], .graph-filter-top [data-slot=\"tabs-trigger\"]").evaluateAll((nodes) => nodes.map((node) => ({ element: node.className, text: node.innerText, right: node.getBoundingClientRect().right, width: node.getBoundingClientRect().width }))));
        if (theme === "dark" && width === 360 && name === "Review queue") await page.screenshot({ path: `${output}review-360.png` });
        if (theme === "light" && width === 1440 && name === "Overview") await page.screenshot({ path: `${output}home-light.png` });
        if (theme === "dark" && width === 1440 && name === "Graph") await page.screenshot({ path: `${output}graph-dark.png` });
      }
    }
  }
  await writeFile(`${output}visual-check.json`, JSON.stringify({ browser: "Google Chrome", results, errors }, null, 2));
  console.log(JSON.stringify({ checks: results.length, failures: results.filter((result) => !result.passed), errors }, null, 2));
  if (results.some((result) => !result.passed) || errors.length) process.exitCode = 1;
} finally {
  await browser.close();
}
