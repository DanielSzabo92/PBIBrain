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
  await page.route("**/api/brain**", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    const nodes = [
      { id: "model:fixture", type: "MODEL", name: "Finance" },
      ...["Sales", "Date"].flatMap((name) => [
        { id: `table:${name}`, type: "TABLE", name, model_id: "model:fixture" },
        { id: `column:${name}`, type: "COLUMN", name: "DateKey", model_id: "model:fixture", properties: { table_id: `table:${name}` } },
      ]),
    ];
    const review_items = ["Sales", "Date"].map((name) => ({ id: `review:${name}`, candidate_id: `candidate:${name}`, target_id: `column:${name}`, value: "DateKey", assertion_type: "BUSINESS_CONCEPT", status: "candidate" }));
    return route.fulfill({ json: { ...data, nodes, review_items, semantic_candidates: [], conflicts: [] } });
  });
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: /^Review queue/ }).click();
  await expect(page.locator(".review-item")).toHaveCount(2);
  await expect(page.getByRole("button", { name: /DateKey Finance \/ Sales/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /DateKey Finance \/ Date/ })).toBeVisible();
});
