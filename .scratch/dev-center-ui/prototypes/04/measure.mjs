// Measure the ticket 04 prototype: page overflow, pane mode, axe, screenshots, static snapshots. Prototype only.
// Run: node measure.mjs <out-dir>
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
const req = createRequire('C:/Users/Daniel/Desktop/PBIBrain/frontend/package.json');
const { chromium } = req('playwright');
const AXE = readFileSync('C:/Users/Daniel/.claude/plugins/local/ux-ui-agent-skills/node_modules/axe-core/axe.min.js', 'utf8');
const TOKENS = readFileSync(new URL('./tokens.css', import.meta.url), 'utf8');
const OUT = process.argv[2]; mkdirSync(`${OUT}/snap`, { recursive: true });
const FILE = pathToFileURL('C:/Users/Daniel/Desktop/PBIBrain/.scratch/dev-center-ui/prototypes/04/index.html').href;
const SCREENS = {
  'take': 'screen=take', 'take-source-open': 'screen=take&open=src', 'take-folder-open': 'screen=take&open=folder',
  'props': 'screen=props', 'props-none': 'screen=props-none', 'newname-warn': 'screen=newname', 'newname-clash': 'screen=newname-clash',
  'rename': 'screen=rename', 'target-missing-saving': 'screen=missing', 'remove-block': 'screen=remove', 'remove-none': 'screen=remove-none',
  'remove-cascade': 'screen=remove-cascade', 'dlg-block': 'screen=dlg-block', 'dlg-cascade': 'screen=dlg-cascade', 'dlg-repoint': 'screen=dlg-repoint',
  'dlg-break': 'screen=dlg-break', 'report-measure': 'screen=report', 'locked': 'screen=locked', 'multi': 'screen=multi',
  'loading': 'screen=loading', 'error': 'screen=error', 'stale': 'screen=stale',
};
const SNAP = ['take', 'props-none', 'newname-clash', 'dlg-cascade', 'dlg-repoint', 'report-measure'];
const SIZES = [[1024, 640], [1152, 900], [1279, 900], [1280, 900], [1366, 900], [1440, 900]];
const browser = await chromium.launch({ channel: 'chrome' });
const res = { browser: browser.version(), overflow: [], axe: {} };
for (const theme of ['dark', 'light']) {
  for (const [w, h] of SIZES) {
    const page = await browser.newPage({ viewport: { width: w, height: h } });
    for (const [id, qs] of Object.entries(SCREENS)) {
      await page.goto(`${FILE}?${qs}&theme=${theme}`);
      await page.addStyleTag({ content: '*{animation:none!important;transition:none!important}' });
      const m = await page.evaluate(() => {
        const over = document.documentElement.scrollWidth - window.innerWidth;
        const clipped = (el) => { for (let p = el.parentElement; p; p = p.parentElement) { if (p === document.body || p === document.documentElement) return false; const s = getComputedStyle(p); if (/(auto|scroll|hidden)/.test(s.overflowX) || s.position === 'fixed') return true; } return false; };
        const past = [...document.querySelectorAll('body *')].filter(e => { const r = e.getBoundingClientRect(); return r.width && r.right > window.innerWidth + 0.5 && !clipped(e) && getComputedStyle(e).position !== 'fixed'; }).length;
        const pane = document.querySelector('.pane'); const pr = pane.getBoundingClientRect();
        // Pane content wider than the pane (horizontal overflow inside the pane).
        const body = pane.querySelector('.pane-body');
        const inner = body ? body.scrollWidth - body.clientWidth : 0;
        const dlg = document.querySelector('.dialog'); const dr = dlg && dlg.getBoundingClientRect();
        return { over, past, inner, pane: { mode: getComputedStyle(pane).position === 'fixed' ? 'sheet' : 'column', width: Math.round(pr.width) },
          dialog: dlg ? { width: Math.round(dr.width), fits: dr.right <= window.innerWidth && dr.bottom <= window.innerHeight + 0.5 } : null };
      });
      res.overflow.push({ theme, w, h, id, ...m });
      if (w === 1440 || w === 1024) await page.screenshot({ path: `${OUT}/${id}-${theme}-${w}.png` });
      if (w === 1440) {
        await page.addScriptTag({ content: AXE });
        const r = await page.evaluate(() => axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] }, resultTypes: ['violations'] }));
        res.axe[`${id}-${theme}`] = r.violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.map(n => n.target.join(' ') + ' :: ' + (n.failureSummary || '').split('\n').slice(1, 2).join('')) }));
        if (SNAP.includes(id) || process.env.SNAP_ALL) {
          const html = await page.evaluate((css) => { document.querySelectorAll('script').forEach(x => x.remove()); for (const l of [...document.querySelectorAll('link[rel=stylesheet]')]) { const s = document.createElement('style'); s.textContent = css; l.replaceWith(s); } return '<!doctype html>' + document.documentElement.outerHTML; }, TOKENS);
          writeFileSync(`${OUT}/snap/${id}-${theme}.html`, html);
        }
      }
    }
    await page.close();
  }
}
// Functional check: click each enabled radio and checkbox; the checked state must change.
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${FILE}?screen=props&theme=dark`);
  const clicks = [];
  for (const sel of ['#mc-keep', '#mc-take', '#mc-add', '#mc-skip']) { await page.locator(`label[for="${sel.slice(1)}"]`).click(); clicks.push([sel, await page.locator(sel).isChecked()]); }
  await page.goto(`${FILE}?screen=props&theme=dark`);
  const before = await page.locator('#pp-expression').isChecked(); await page.locator('label[for="pp-expression"]').click();
  clicks.push(['#pp-expression toggled', before !== await page.locator('#pp-expression').isChecked()]);
  res.clicks = clicks; await page.close();
}
await browser.close();
writeFileSync(`${OUT}/result.json`, JSON.stringify(res, null, 2));
const bad = res.overflow.filter(r => r.over > 0 || r.past > 0 || r.inner > 0 || (r.dialog && !r.dialog.fits));
console.log('browser', res.browser, '| measurements', res.overflow.length, '| fails', bad.length);
bad.forEach(b => console.log('  FAIL', b.theme, b.w, b.h, b.id, 'page', b.over, 'past', b.past, 'pane', b.inner, 'dialog', JSON.stringify(b.dialog)));
let axeBad = 0; for (const [k, v] of Object.entries(res.axe)) if (v.length) { axeBad++; console.log('axe', k, JSON.stringify(v)); }
console.log('axe pages with violations', axeBad, 'of', Object.keys(res.axe).length);
const modes = {}; res.overflow.filter(r => r.theme === 'dark' && r.id === 'take').forEach(r => modes[r.w] = `${r.pane.mode} ${r.pane.width}`); console.log('pane', JSON.stringify(modes));
console.log('dialog', JSON.stringify(res.overflow.filter(r => r.dialog && r.theme === 'dark' && r.id === 'dlg-cascade').map(r => [r.w, r.h, r.dialog.width, r.dialog.fits])));
console.log('clicks', JSON.stringify(res.clicks));
