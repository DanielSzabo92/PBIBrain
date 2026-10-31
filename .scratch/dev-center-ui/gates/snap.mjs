// Save each screen as one static HTML file with inline CSS, so that the file-based kit gates can read it (ticket 01).
// Run from frontend/ with the fake server on :8765: node ../.scratch/dev-center-ui/gates/snap.mjs <out-dir>
import { createRequire } from 'node:module';
import { writeFileSync, mkdirSync } from 'node:fs';
const req = createRequire('C:/Users/Daniel/Desktop/PBIBrain/frontend/package.json');
const { chromium } = req('playwright');
const OUT = process.argv[2]; mkdirSync(OUT, { recursive: true });
const b = await chromium.launch({ channel: 'chrome' });
for (const theme of ['dark','light']) {
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript((t) => localStorage.setItem('pbibrain-theme', t), theme);
  const p = await ctx.newPage();
  for (const s of ['overview','inspector','review','settings']) {
    await p.goto('http://127.0.0.1:8765/'); await p.waitForLoadState('networkidle');
    const nav = (n) => p.getByRole('navigation').getByRole('button', { name: new RegExp('^' + n) }).click();
    if (s === 'inspector') { await nav('Search'); const box = p.getByRole('searchbox').or(p.getByRole('textbox')).first(); await box.fill('Net Sales'); await box.press('Enter'); await p.locator('.search-result').first().click(); }
    if (s === 'review') await nav('Review queue');
    if (s === 'settings') await nav('Settings');
    await p.waitForLoadState('networkidle'); await p.waitForTimeout(400);
    let html = await p.evaluate(() => { document.querySelectorAll('script').forEach(x => x.remove()); for (const l of [...document.querySelectorAll('link[rel=stylesheet]')]) { const st = document.createElement('style'); st.textContent = [...l.sheet.cssRules].map(r => r.cssText).join(' '); l.replaceWith(st); } return '<!doctype html>' + document.documentElement.outerHTML; });
    html = html.replace('<head>', '<head><base href="http://127.0.0.1:8765/">');
    writeFileSync(`${OUT}/${s}-${theme}.html`, html);
  }
  await ctx.close();
}
await b.close(); console.log('ok');
