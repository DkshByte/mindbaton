// Render chosen frames of the film to PNG for review: node stills.mjs out-dir dpr t1 t2 …
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
const [out, dpr, ...ts] = process.argv.slice(2);
const b = await chromium.launch({ args: ['--font-render-hinting=none', '--disable-lcd-text'] });
const p = await (await b.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: +dpr })).newPage();
p.on('pageerror', e => console.log('pageerror', e.message)); p.on('console', m => { if (m.type() === 'error') console.log('console', m.text()); });
await p.goto('http://127.0.0.1:8765/brag-output/composition/index.html?t=0');
await p.evaluate(() => window.__ready);
for (const t of ts) {
  await p.evaluate(t => seek(+t), t);
  await p.screenshot({ path: `${out}/f_${(+t).toFixed(2).padStart(6, '0')}.png` });
}
await b.close();
