// Screenshots and click test for the ticket 09 specimen. Run from the kit folder copy, or with NODE_PATH to the kit node_modules.
import { chromium } from 'playwright';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
const dir = path.dirname(fileURLToPath(import.meta.url));
fs.mkdirSync(path.join(dir, 'shots'), { recursive: true });
const b = await chromium.launch({ channel: 'chrome' });
const out = {};
for (const theme of ['light', 'dark']) {
  for (const w of [1440, 1024]) {
    const p = await b.newPage({ viewport: { width: w, height: 900 } });
    await p.goto(pathToFileURL(path.join(dir, 'index.html')).href + '?theme=' + theme);
    await p.addStyleTag({ content: '*{transition:none!important;animation:none!important}' });
    await p.mouse.move(2000, 2000);
    await p.screenshot({ path: path.join(dir, 'shots', `specimen-${theme}-${w}.png`), fullPage: true });
    if (w === 1440) {
      const cb = p.locator('label.cb input').first(); await p.locator('label.cb').first().click(); const c1 = await cb.isChecked();
      const sw = p.locator('.switch').first(); await sw.click(); const s1 = await sw.getAttribute('aria-checked');
      await p.locator('.choice label').first().click(); const r1 = await p.locator('.choice input').first().isChecked();
      await p.locator('.seg button').nth(1).click(); const g1 = await p.locator('.seg button').nth(1).getAttribute('aria-pressed');
      out[theme] = { checkboxToggles: c1, switchToggles: s1 === 'true', radioSelects: r1, segmentedPresses: g1 === 'true',
        overflowPx: await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth) };
    }
    await p.close();
  }
}
console.log(JSON.stringify(out));
await b.close();
