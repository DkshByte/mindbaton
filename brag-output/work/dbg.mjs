import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
const b = await chromium.launch();
const p = await (await b.newContext({ viewport: { width: 1920, height: 1080 } })).newPage();
p.on('pageerror', e => console.log('pageerror', e.message)); p.on('console', m => console.log('console', m.type(), m.text()));
await p.goto('http://127.0.0.1:8765/brag-output/composition/index.html?t=0');
await p.evaluate(() => window.__ready);
const r = await p.evaluate(new Function('return (' + process.argv[2] + ')()'));
console.log(JSON.stringify(r, null, 1));
await b.close();
