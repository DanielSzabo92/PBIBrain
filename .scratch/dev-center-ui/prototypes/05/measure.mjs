// Measure the ticket 05 prototype: page overflow, axe, pane mode, screenshots. Prototype only.
// Run: node measure.mjs <out-dir>
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
const req = createRequire('C:/Users/Daniel/Desktop/PBIBrain/frontend/package.json');
const { chromium } = req('playwright');
const AXE = readFileSync('C:/Users/Daniel/.claude/plugins/local/ux-ui-agent-skills/node_modules/axe-core/axe.min.js', 'utf8');
const OUT = process.argv[2] || 'shots'; mkdirSync(OUT, { recursive: true });
const FILE = pathToFileURL('C:/Users/Daniel/Desktop/PBIBrain/.scratch/dev-center-ui/prototypes/05/index.html').href;
const SCREENS = JSON.parse(readFileSync(new URL('./screens.json', import.meta.url), 'utf8'));
const SIZES = [[1024, 640], [1152, 900], [1279, 900], [1280, 900], [1366, 900], [1440, 900]];
const browser = await chromium.launch({ channel: 'chrome' });
const res = { browser: browser.version(), overflow: [], axe: {} };
for (const theme of ['dark', 'light']) {
  for (const [w, h] of SIZES) {
    const page = await browser.newPage({ viewport: { width: w, height: h } });
    for (const [id, qs] of Object.entries(SCREENS)) {
      await page.goto(`${FILE}?${qs}&theme=${theme}`);
      const m = await page.evaluate(() => {
        const over = document.documentElement.scrollWidth - window.innerWidth;
        const scrollers = (el) => { for (let p = el.parentElement; p; p = p.parentElement) { const s = getComputedStyle(p); if (/(auto|scroll|hidden)/.test(s.overflowX) && p !== document.body && p !== document.documentElement) return true; } return false; };
        const past = [...document.querySelectorAll('body *')].filter(e => { const r = e.getBoundingClientRect(); return r.width && r.right > window.innerWidth + 0.5 && !scrollers(e) && getComputedStyle(e).position !== 'fixed'; }).map(e => e.tagName + '.' + e.className).slice(0, 5);
        const pane = document.querySelector('.pane'); const pr = pane && pane.getBoundingClientRect();
        const small = [...document.querySelectorAll('button, input, [role=switch]')].filter(e => { const t = e.closest('label.cbwrap, label.search') || e; const r = t.getBoundingClientRect(); return r.width && (r.width < 24 || r.height < 24); }).map(e => (e.getAttribute('aria-label') || e.textContent).slice(0, 30));
        return { over, past, small, pane: pane ? { mode: getComputedStyle(pane).position === 'fixed' ? 'sheet' : 'column', width: Math.round(pr.width) } : null };
      });
      res.overflow.push({ theme, w, h, id, ...m });
      if (w === 1440 || w === 1024) await page.screenshot({ path: `${OUT}/${id}-${theme}-${w}.png`, fullPage: true });
      if (w === 1440) {
        await page.addScriptTag({ content: AXE });
        const r = await page.evaluate(() => axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'] }, resultTypes: ['violations'] }));
        res.axe[`${id}-${theme}`] = r.violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.slice(0, 4).map(n => n.target.join(' ') + ' :: ' + (n.failureSummary || '').split('\n').slice(1, 2).join('')) }));
      }
    }
    await page.close();
  }
}
await browser.close();
writeFileSync(`${OUT}/result.json`, JSON.stringify(res, null, 2));
const bad = res.overflow.filter(r => r.over > 0 || r.past.length);
console.log('browser', res.browser, '| measurements', res.overflow.length, '| overflow fails', bad.length);
bad.slice(0, 20).forEach(b => console.log('  FAIL', b.theme, b.w, b.id, b.over, b.past.join(',')));
const smalls = res.overflow.filter(r => r.small.length && r.theme === 'dark' && r.w === 1024);
smalls.forEach(s => console.log('  small targets', s.id, s.small.join(' | ')));
for (const [k, v] of Object.entries(res.axe)) console.log('axe', k, v.length ? JSON.stringify(v) : 0);
res.overflow.filter(r => r.pane && r.theme === 'dark').forEach(r => console.log('pane', r.w, r.id, r.pane.mode, r.pane.width));
