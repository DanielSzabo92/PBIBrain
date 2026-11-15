import { test, expect } from "@playwright/test";
import { axeViolations, setTheme } from "./axe.js";

// Review 21: every view passes axe (WCAG 2.2 AA rules) in both themes, not only Merge models.
const VIEWS = [
  ["Overview", "/#/", ".type-strip"],
  ["Search", "/#/search?q=Sales", ".search-result"],
  ["Graph", "/#/graph", ".react-flow__node"],
  ["Inspector", "/#/inspector", "[role=treeitem]"],
  ["Review queue", "/#/review", ".review-item"],
  ["Settings", "/#/settings", ".source-row, .add-source"],
];

for (const theme of ["dark", "light"]) {
  for (const [name, url, ready] of VIEWS) {
    test(`${name} has no serious accessibility violation in the ${theme} theme`, async ({ page, context }) => {
      await setTheme(context, theme);
      await page.goto(url);
      await expect(page.locator(ready).first()).toBeVisible();
      const violations = (await axeViolations(page)).filter((violation) => ["serious", "critical"].includes(violation.impact));
      expect(violations).toEqual([]);
    });
  }
}
