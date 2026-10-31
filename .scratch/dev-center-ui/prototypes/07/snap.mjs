// Save static snapshots of prototype 07 screens for the kit gates (they take a file, not a query). Prototype only.
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
const req = createRequire('C:/Users/Daniel/Desktop/PBIBrain/frontend/package.json');
const { chromium } = req('playwright');
const DIR = 'C:/Users/Daniel/Desktop/PBIBrain/.scratch/dev-center-ui/prototypes/07';
const CSS = readFileSync(`${DIR}/tokens.css`, 'utf8');
mkdirSync(`${DIR}/shots/static`, { recursive: true });
const IDS = ['rules', 'rules-menu', 'rules-editor', 'rules-editor-error', 'select-paste', 'pull-notempty', 'rules-copy', 'rules-delete', 'sign-out', 'select', 'access', 'result', 'report-refused', 'pull-confirm', 'signing', 'sign-fail', 'sign-fail&why=consent', 'sign-fail&why=network', 'select-nocap', 'select-none', 'testing', 'test-fail', 'pull-running', 'pull-done', 'pull-fail', 'rules-select', 'rules-empty', 'rules-notarget', 'rules-detecting', 'rules-locked', 'rules-stale'];
const b = await chromium.launch({ channel: 'chrome' });
const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
for (const theme of ['dark', 'light']) for (const id of IDS) {
  await p.goto(`${pathToFileURL(DIR + '/index.html').href}?screen=${id}&theme=${theme}`);
  let html = await p.content();
  html = html.replace(/<script>[\s\S]*?<\/script>/, '').replace('<link rel="stylesheet" href="tokens.css">', `<style>${CSS}</style>`);
  writeFileSync(`${DIR}/shots/static/${id.replace("&why=", "-")}-${theme}.html`, html);
}
await b.close(); console.log('snapshots', IDS.length * 2);
