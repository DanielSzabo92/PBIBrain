// Composited contrast of each status badge on its real backdrop (the kit state gate drops alpha). Prototype only.
import { createRequire } from 'node:module';
const req = createRequire('C:/Users/Daniel/Desktop/PBIBrain/frontend/package.json');
const { chromium } = req('playwright');
const b = await chromium.launch({ channel: 'chrome' });
const screens = ['agent', 'compare&card=conflict', 'acceptall', 'log&pf=1', 'plan&inc=1'];
for (const theme of ['dark', 'light']) {
  const out = {};
  for (const s of screens) {
    const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
    await p.goto(`file:///C:/Users/Daniel/Desktop/PBIBrain/.scratch/dev-center-ui/prototypes/06/index.html?screen=${s}&theme=${theme}`);
    const r = await p.evaluate(() => {
      const parse = c => { const m = c.match(/[\d.]+/g).map(Number); const k = c.startsWith('color(') ? 255 : 1; return { r: m[0] * k, g: m[1] * k, b: m[2] * k, a: m[3] ?? 1 }; };
      const over = (f, bk) => ({ r: f.r * f.a + bk.r * (1 - f.a), g: f.g * f.a + bk.g * (1 - f.a), b: f.b * f.a + bk.b * (1 - f.a), a: 1 });
      const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
      const bgOf = el => { const stack = []; for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor); if (c.a > 0) stack.push(c); if (c.a === 1) break; } let acc = stack.pop() || { r: 255, g: 255, b: 255, a: 1 }; while (stack.length) acc = over(stack.pop(), acc); return acc; };
      return [...document.querySelectorAll('.status')].map(el => { const fg = parse(getComputedStyle(el).color); const bg = bgOf(el); const L1 = lum(fg), L2 = lum(bg); return [el.textContent.trim(), +(((Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05)).toFixed(2))]; });
    });
    r.forEach(([t, v]) => { const k = t; out[k] = Math.min(out[k] ?? 99, v); });
    await p.close();
  }
  console.log(theme, JSON.stringify(out));
}
await b.close();
