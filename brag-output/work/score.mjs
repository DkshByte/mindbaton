// Render the score to brag-output/work/score.wav
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import fs from 'fs';
const b = await chromium.launch();
const p = await b.newPage();
p.on('pageerror', e => console.log('pageerror', e.message));
await p.goto('http://127.0.0.1:8765/brag-output/composition/score.html');
const { b64, peak } = await p.evaluate(() => renderScore());
fs.writeFileSync(process.argv[2], Buffer.from(b64, 'base64'));
console.log('peak', peak);
await b.close();
