import { test, expect } from "@playwright/test";

test("overview exposes invalid graph issues separately from extraction", async ({ page }) => {
  await page.route("**/api/overview", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    return route.fulfill({ json: { ...data, validation_state: "invalid", validation_issues: [
      { code: "invalid_containment", severity: "ERROR", message: "MODEL cannot contain REPORT", object_id: data.report_ids[0] },
    ] } });
  });
  await page.goto("/");
  // The validation summary is its own widget beside "Sources indexed"; its first issues are listed inline.
  const validation = page.getByRole("region", { name: "Validation summary" });
  await expect(validation).toContainText("Graph validation failed");
  await expect(page.getByText("Sources indexed", { exact: true })).toBeVisible();
  await expect(validation.getByText("MODEL cannot contain REPORT", { exact: false })).toBeVisible();
  await validation.getByRole("button", { name: "Inspect", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sales report", exact: true })).toBeVisible();
});

test("review decisions show the exact table scope for duplicate columns", async ({ page }) => {
  // Two suggestions on columns of one name in two tables, as the review pages answer them.
  const nodes = [
    { id: "model:fixture", type: "MODEL", name: "Finance" },
    ...["Sales", "Date"].flatMap((name) => [
      { id: `table:${name}`, type: "TABLE", name, model_id: "model:fixture" },
      { id: `column:${name}`, type: "COLUMN", name: "DateKey", model_id: "model:fixture", properties: { table_id: `table:${name}` } },
    ]),
  ];
  const items = ["Sales", "Date"].map((name) => ({ id: `review:${name}`, candidate_id: `candidate:${name}`, target_id: `column:${name}`, value: "DateKey", assertion_type: "BUSINESS_CONCEPT", status: "candidate", issue: "candidate", pattern: "BUSINESS_CONCEPT|from a rule|COLUMN" }));
  await page.route("**/api/review/page**", async (route) => {
    const url = new URL(route.request().url());
    const facets = { types: ["COLUMN"], models: ["model:fixture"], reports: [], open: 2, reviewed: 0 };
    if (url.searchParams.get("tab") === "reviewed") return route.fulfill({ json: { tab: "reviewed", total: 0, has_more: false, items: [], nodes: [], facets } });
    const counts = { matching: 2, standard_total: 2, low_total: 0, approvable: 2, facets };
    if (url.searchParams.get("rows") === "0") return route.fulfill({ json: { ...counts, groups: [] } });
    const rows = url.searchParams.get("section") === "low" ? [] : items;
    return route.fulfill({ json: { ...counts, total: rows.length, has_more: false, items: rows, nodes, approvable_total: rows.length } });
  });
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: /^Review queue/ }).click();
  await expect(page.locator(".review-item")).toHaveCount(2);
  await expect(page.getByRole("button", { name: /DateKey Finance \/ Sales/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /DateKey Finance \/ Date/ })).toBeVisible();
});
