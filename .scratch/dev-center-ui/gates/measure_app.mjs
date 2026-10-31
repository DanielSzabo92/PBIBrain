// Measure axe and page overflow on the existing PBIBrain screens (fake server on :8765).
// Run from frontend/ with the fake server on :8765: node ../.scratch/dev-center-ui/gates/measure_app.mjs <out-dir>
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
const req = createRequire('C:/Users/Daniel/Desktop/PBIBrain/frontend/package.json');
const { chromium } = req('playwright');
const AXE = readFileSync('C:/Users/Daniel/.claude/plugins/local/ux-ui-agent-skills/node_modules/axe-core/axe.min.js', 'utf8');
const OUT = process.argv[2]; mkdirSync(OUT, { recursive: true });
const BASE = 'http://127.0.0.1:8765/';
const browser = await chromium.launch({ channel: 'chrome' });
console.log('browser', browser.version());

async function open(page, screen) {
  await page.goto(BASE); await page.getByRole('navigation').waitFor();
  await page.waitForLoadState('networkidle');
  const nav = (name) => page.getByRole('navigation').getByRole('button', { name: new RegExp('^' + name) }).click();
  if (screen === 'search' || screen === 'inspector') {
    await nav('Search');
    const box = page.getByRole('searchbox').or(page.getByRole('textbox')).first();
    await box.fill('Net Sales'); await box.press('Enter');
    await page.locator('.search-result').first().waitFor();
    if (screen === 'inspector') { await page.locator('.search-result').first().click(); await page.waitForLoadState('networkidle'); }
  } else if (screen === 'graph') { await nav('Graph'); await page.waitForTimeout(1500); }
  else if (screen === 'review') await nav('Review queue');
  else if (screen === 'settings') await nav('Settings');
  await page.waitForLoadState('networkidle'); await page.waitForTimeout(400);
}

const SCREENS = ['overview', 'search', 'graph', 'inspector', 'review', 'settings'];
const result = { axe: {}, overflow: {} };
for (const theme of ['dark', 'light']) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript((t) => { try { localStorage.setItem('pbibrain-theme', t); } catch {} }, theme);
  const page = await ctx.newPage();
  for (const s of SCREENS) {
    try {
      await open(page, s);
      await page.screenshot({ path: `${OUT}/${s}-${theme}-1440.png` });
      await page.addScriptTag({ content: AXE });
      const r = await page.evaluate(() => axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'] }, resultTypes: ['violations'] }));
      result.axe[`${s}/${theme}`] = r.violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, sample: v.nodes.slice(0, 3).map(n => n.target.join(' ')), why: v.nodes[0]?.any?.[0]?.message }));
      const n = r.violations.reduce((a, v) => a + v.nodes.length, 0);
      console.log(`axe ${s}/${theme}: ${r.violations.length} rule(s), ${n} node(s)`, r.violations.map(v => `${v.id}[${v.impact}]x${v.nodes.length}`).join(' '));
    } catch (e) { console.log(`axe ${s}/${theme}: ERROR ${e.message.split('\n')[0]}`); result.axe[`${s}/${theme}`] = 'ERROR ' + e.message.split('\n')[0]; }
  }
  // Responsive overflow, both themes give the same layout; measure in dark only.
  if (theme === 'dark') for (const [w, h] of [[1024, 640], [1024, 900], [1152, 900], [1280, 900], [1366, 900], [1440, 900]]) {
    await page.setViewportSize({ width: w, height: h });
    for (const s of SCREENS) {
      try {
        await open(page, s);
        const m = await page.evaluate(() => {
          const de = document.documentElement, vw = window.innerWidth;
          const clipped = (el) => { for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) { const ox = getComputedStyle(p).overflowX; if (ox !== 'visible') return true; } return false; };
          const off = [];
          for (const el of document.body.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            if (r.width && r.right > vw + 1 && !clipped(el)) off.push(`${el.tagName.toLowerCase()}${el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0,2).join('.') : ''} right=${Math.round(r.right)}`);
          }
          return { scrollWidth: de.scrollWidth, clientWidth: de.clientWidth, bodyScroll: document.body.scrollWidth, offenders: off.slice(0, 5), offenderCount: off.length };
        });
        const over = Math.max(m.scrollWidth, m.bodyScroll) - m.clientWidth;
        result.overflow[`${s}@${w}x${h}`] = { ...m, overflowPx: over };
        console.log(`overflow ${s}@${w}x${h}: ${over > 0 ? 'FAIL +' + over + 'px' : 'pass'} offenders=${m.offenderCount} ${m.offenders.join(' | ')}`);
        if (w === 1024) await page.screenshot({ path: `${OUT}/${s}-dark-${w}x${h}.png` });
      } catch (e) { console.log(`overflow ${s}@${w}: ERROR ${e.message.split('\n')[0]}`); }
    }
    await page.setViewportSize({ width: 1440, height: 900 });
  }
  await ctx.close();
}
writeFileSync(`${OUT}/result.json`, JSON.stringify(result, null, 2));
await browser.close();
