import { test, expect } from "@playwright/test";

// Review 09: the cells of a review row never draw over each other, at any window width the app supports.
for (const width of [1024, 1280, 1440, 1920]) {
  test(`review rows keep their cells apart at ${width} px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/#/review");
    await expect(page.locator(".review-item").first()).toBeVisible();
    const overlaps = await page.evaluate(() => {
      let bad = 0;
      for (const row of document.querySelectorAll(".review-item")) {
        const cells = [...row.children].map((cell) => cell.getBoundingClientRect()).filter((rect) => rect.width);
        for (let index = 0; index < cells.length - 1; index += 1) {
          const sameLine = Math.abs(cells[index].top - cells[index + 1].top) < 20;
          if (sameLine && cells[index].right > cells[index + 1].left + 0.5) bad += 1;
        }
      }
      return bad;
    });
    expect(overlaps).toBe(0);
    const pageOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(pageOverflow).toBeLessThanOrEqual(0);
  });
}
