// Measure the ticket 03 prototype: page overflow, axe, screenshots, render budget, keyboard. Prototype only.
// Run: node measure.mjs <out-dir>
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
const req = createRequire('C:/Users/Daniel/Desktop/PBIBrain/frontend/package.json');
const { chromium } = req('playwright');
const AXE = readFileSync('C:/Users/Daniel/.claude/plugins/local/ux-ui-agent-skills/node_modules/axe-core/axe.min.js', 'utf8');
const OUT = process.argv[2]; mkdirSync(OUT, { recursive: true });
const FILE = pathToFileURL('C:/Users/Daniel/Desktop/PBIBrain/.scratch/dev-center-ui/prototypes/03/index.html').href;
const SCREENS = {
  'grid': 'screen=grid', 'grid-tooltip': 'screen=grid&tip=1', 'grid-pane': 'screen=grid&pane=1',
  'filter-state': 'screen=grid&filter=state', 'bulk-selected': 'screen=grid&sel=all', 'bulk-all-matching': 'screen=grid&allm=1',
  'bulk-menu': 'screen=grid&sel=12&menu=1', 'bulk-confirm': 'screen=grid&sel=all&confirm=keep', 'bulk-confirm-remove': 'screen=grid&sel=12&confirm=remove',
  'code-diff': 'screen=grid&diff=1', 'loading': 'screen=loading', 'empty': 'screen=empty', 'error': 'screen=error', 'no-match': 'screen=nomatch', 'strict': 'screen=grid&strict=1',
};
const SIZES = [[1024, 640], [1152, 900], [1279, 900], [1280, 900], [1366, 900], [1440, 900]];
const browser = await chromium.launch({ channel: 'chrome' });
const res = { browser: browser.version(), overflow: [], axe: {}, budget: [], keyboard: {} };
const ready = (page) => page.waitForSelector('body[data-ready="1"]', { timeout: 10000 });
for (const theme of ['dark', 'light']) {
  for (const [w, h] of SIZES) {
    const page = await browser.newPage({ viewport: { width: w, height: h } });
    for (const [id, qs] of Object.entries(SCREENS)) {
      await page.goto(`${FILE}?${qs}&theme=${theme}`); await ready(page); await page.waitForTimeout(120);
      const m = await page.evaluate(() => {
        const over = document.documentElement.scrollWidth - window.innerWidth;
        const scrollers = (el) => { for (let p = el.parentElement; p; p = p.parentElement) { const s = getComputedStyle(p); if (/(auto|scroll|hidden)/.test(s.overflowX) && p !== document.body && p !== document.documentElement) return true; } return false; };
        const past = [...document.querySelectorAll('body *')].filter(e => { const r = e.getBoundingClientRect(); return r.width && r.right > window.innerWidth + 0.5 && !scrollers(e) && getComputedStyle(e).position !== 'fixed' && !e.closest('.sr-only'); }).length;
        const pane = document.querySelector('.pane'); const pr = pane && pane.getBoundingClientRect();
        const gs = document.getElementById('gs');
        return { over, past, rowsInDom: document.querySelectorAll('#body .row').length, gridScrollsX: gs ? gs.scrollWidth > gs.clientWidth : null,
          pane: pane ? { mode: getComputedStyle(pane).position === 'fixed' ? 'sheet' : 'column', width: Math.round(pr.width) } : null };
      });
      res.overflow.push({ theme, w, h, id, ...m });
      if (w === 1440 || w === 1024) await page.screenshot({ path: `${OUT}/${id}-${theme}-${w}.png` });
      if (w === 1440) {
        await page.addScriptTag({ content: AXE });
        const r = await page.evaluate(() => axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] }, resultTypes: ['violations'] }));
        res.axe[`${id}-${theme}`] = r.violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.slice(0, 3).map(n => n.target.join(' ') + ' :: ' + (n.failureSummary || '').split('\n').slice(1, 2).join('')) }));
      }
    }
    await page.close();
  }
}
// Render budget: 5,000 rows, 5 sources, 40 ms fake reply delay. 5 runs at 1440 x 900, dark.
for (let run = 0; run < 5; run++) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${FILE}?screen=grid&n=5000`); await ready(page); await page.waitForTimeout(150);
  const first = await page.evaluate(() => ({ replyToPaint: __perf.firstPaint - __perf.firstReply, rows: document.querySelectorAll('#body .row').length }));
  // Filter change: type in search, measure from debounce end (filterStart) to paint.
  await page.fill('#q', 'Total'); await page.waitForFunction(() => __perf.filterPaint > 0, null, { timeout: 5000 });
  const filt = await page.evaluate(() => __perf.filterPaint - __perf.filterStart);
  await page.fill('#q', ''); await page.waitForTimeout(400);
  // Clear the default "Not same" filter so the full 5,000 rows show, then scroll to the end and back.
  await page.click('#chips [data-k="state:notsame"]'); await page.waitForTimeout(300);
  const scrollRun = (step, limit) => page.evaluate(async ([step, limit]) => {
    const long = []; const po = new PerformanceObserver(l => l.getEntries().forEach(e => long.push(e.duration))); po.observe({ type: 'longtask', buffered: false });
    const gs = document.getElementById('gs'); gs.scrollTop = 0; await new Promise(r => setTimeout(r, 200)); let maxRows = 0; const frames = []; let last = performance.now();
    for (let y = 0; y <= Math.min(limit, gs.scrollHeight); y += step) { gs.scrollTop = y; await new Promise(r => requestAnimationFrame(r)); const now = performance.now(); frames.push(now - last); last = now; maxRows = Math.max(maxRows, document.querySelectorAll('#body .row').length); }
    await new Promise(r => setTimeout(r, 300)); po.disconnect(); frames.sort((a, b) => a - b);
    return { frames: frames.length, medFrame: +frames[frames.length >> 1].toFixed(1), p95Frame: +frames[Math.floor(frames.length * 0.95)].toFixed(1), longTasks: long.length, maxLong: Math.max(0, ...long), maxRows,
      total: +document.getElementById('grid').getAttribute('aria-rowcount') - 1, lastRowIndex: Math.max(...[...document.querySelectorAll('#body .row')].map(r => +r.getAttribute('aria-rowindex'))) };
  }, [step, limit]);
  const wheel = await scrollRun(120, 30000);
  const drag = await scrollRun(900, 1e9);
  const scroll = { wheel120: wheel, jump900: drag };
  res.budget.push({ run, firstReplyToPaintMs: +first.replyToPaint.toFixed(1), rowsAfterFirst: first.rows, filterToPaintMs: +filt.toFixed(1), ...scroll });
  await page.close();
}
// Keyboard: focus the first cell, then arrow, Space, Enter, D, Escape.
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${FILE}?screen=grid`); await ready(page);
  await page.focus('#body [tabindex="0"]');
  const k = {};
  await page.keyboard.press('ArrowDown'); await page.keyboard.press('ArrowDown');
  k.afterTwoDown = await page.evaluate(() => document.activeElement.dataset.r + ',' + document.activeElement.dataset.c);
  await page.keyboard.press('Space'); k.selectedAfterSpace = await page.evaluate(() => document.querySelectorAll('#body .row[aria-selected="true"]').length);
  await page.keyboard.press('Shift+ArrowDown'); await page.keyboard.press('Shift+ArrowDown'); k.selectedAfterShift = await page.evaluate(() => document.querySelectorAll('#body .row[aria-selected="true"]').length);
  k.bulkBar = await page.evaluate(() => !!document.querySelector('.bulkbar'));
  await page.keyboard.press('Escape'); k.selectedAfterEsc = await page.evaluate(() => document.querySelectorAll('#body .row[aria-selected="true"]').length);
  await page.keyboard.press('Enter'); k.paneAfterEnter = await page.evaluate(() => !!document.querySelector('.pane'));
  await page.keyboard.press('End'); k.endCol = await page.evaluate(() => document.activeElement.dataset.c);
  await page.keyboard.press('Control+End'); k.ctrlEndRow = await page.evaluate(() => document.activeElement.dataset.r + ' of ' + (document.getElementById('grid').getAttribute('aria-rowcount') - 1));
  await page.keyboard.press('Control+Home'); await page.keyboard.press('Home');
  for (let i = 0; i < 4; i++) await page.keyboard.press('ArrowRight');
  let found = false; for (let i = 0; i < 40 && !found; i++) { await page.keyboard.press('d'); found = await page.evaluate(() => !!document.querySelector('.diff')); if (!found) await page.keyboard.press('ArrowDown'); }
  k.diffByD = found; await page.keyboard.press('Escape'); k.diffClosed = await page.evaluate(() => !document.querySelector('.diff'));
  res.keyboard = k; await page.close();
}
await browser.close();
writeFileSync(`${OUT}/result.json`, JSON.stringify(res, null, 2));
const bad = res.overflow.filter(r => r.over > 0 || r.past > 0);
console.log('browser', res.browser, '| measurements', res.overflow.length, '| overflow fails', bad.length);
bad.forEach(b => console.log('  FAIL', b.theme, b.w, b.id, b.over, b.past));
const axeBad = Object.entries(res.axe).filter(([, v]) => v.length); console.log('axe screens', Object.keys(res.axe).length, '| with violations', axeBad.length);
axeBad.forEach(([k, v]) => console.log('  axe', k, JSON.stringify(v)));
console.log('max rows in DOM', Math.max(...res.overflow.map(r => r.rowsInDom)));
res.overflow.filter(r => r.pane && r.theme === 'dark').forEach(r => console.log('pane', r.w, r.id, r.pane.mode, r.pane.width));
res.budget.forEach(b => console.log('budget', JSON.stringify(b)));
console.log('keyboard', JSON.stringify(res.keyboard));
