// Measure the ticket 07 prototype: page overflow, axe, pane mode, screenshots. Prototype only.
// Run: node measure.mjs <out-dir>
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
const req = createRequire('C:/Users/Daniel/Desktop/PBIBrain/frontend/package.json');
const { chromium } = req('playwright');
const AXE = readFileSync('C:/Users/Daniel/.claude/plugins/local/ux-ui-agent-skills/node_modules/axe-core/axe.min.js', 'utf8');
const OUT = process.argv[2]; mkdirSync(OUT, { recursive: true });
const FILE = pathToFileURL('C:/Users/Daniel/Desktop/PBIBrain/.scratch/dev-center-ui/prototypes/07/index.html').href;
const IDS = ['sign-out','signing','sign-fail','sign-fail&why=consent','sign-fail&why=network','select','select-nocap','select-none','select-paste','access','testing','result','test-fail','report-refused',
  'pull-confirm','pull-notempty','pull-running','pull-done','pull-fail',
  'rules','rules-select','rules-menu','rules-editor','rules-editor-error','rules-empty','rules-notarget','rules-detecting','rules-locked','rules-stale','rules-copy','rules-delete'];
const SIZES = [[1024, 640], [1152, 900], [1279, 900], [1280, 900], [1366, 900], [1440, 900]];
const browser = await chromium.launch({ channel: 'chrome' });
const res = { browser: browser.version(), overflow: [], axe: {} };
for (const theme of ['dark', 'light']) {
  for (const [w, h] of SIZES) {
    const page = await browser.newPage({ viewport: { width: w, height: h } });
    for (const id of IDS) {
      const name = id.replace('&why=', '-');
      await page.goto(`${FILE}?screen=${id}&theme=${theme}`);
      const m = await page.evaluate(() => {
        const over = document.documentElement.scrollWidth - window.innerWidth;
        const inScroller = (el) => { for (let p = el.parentElement; p; p = p.parentElement) { if (p === document.body || p === document.documentElement) return false; const s = getComputedStyle(p); if (/(auto|scroll|hidden)/.test(s.overflowX)) return true; } return false; };
        const past = [...document.querySelectorAll('body *')].filter(e => { const r = e.getBoundingClientRect(); return r.width && r.right > window.innerWidth + 0.5 && !inScroller(e) && getComputedStyle(e).position !== 'fixed'; }).length;
        const d = document.querySelector('.dialog'); const dr = d && d.getBoundingClientRect();
        const dialogOff = d ? (dr.right > window.innerWidth + 0.5 || dr.left < -0.5 || dr.bottom > window.innerHeight + 0.5) : false;
        const pane = document.querySelector('.pane'); const pr = pane && pane.getBoundingClientRect();
        return { over, past, dialogOff, pane: pane ? { mode: getComputedStyle(pane).position === 'fixed' ? 'sheet' : 'column', width: Math.round(pr.width) } : null };
      });
      res.overflow.push({ theme, w, h, id: name, ...m });
      if (w === 1440 || w === 1024) await page.screenshot({ path: `${OUT}/${name}-${theme}-${w}.png`, fullPage: !(await page.$('.scrim')) });
      if (w === 1440) {
        await page.addScriptTag({ content: AXE });
        const r = await page.evaluate(() => axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'] }, resultTypes: ['violations'] }));
        res.axe[`${name}-${theme}`] = r.violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.map(n => n.target.join(' ') + ' :: ' + (n.failureSummary || '').split('\n').slice(1, 2).join('')) }));
      }
    }
    await page.close();
  }
}
await browser.close();
writeFileSync(`${OUT}/result.json`, JSON.stringify(res, null, 2));
const bad = res.overflow.filter(r => r.over > 0 || r.past > 0 || r.dialogOff);
console.log('browser', res.browser, '| measurements', res.overflow.length, '| fails', bad.length);
bad.forEach(b => console.log('  FAIL', b.theme, b.w, b.h, b.id, b.over, b.past, b.dialogOff));
let ax = 0; for (const [k, v] of Object.entries(res.axe)) if (v.length) { ax++; console.log('axe', k, JSON.stringify(v)); }
console.log('axe pages with violations:', ax, 'of', Object.keys(res.axe).length);
res.overflow.filter(r => r.pane && r.theme === 'dark').forEach(r => console.log('pane', r.w, r.id, r.pane.mode, r.pane.width));
