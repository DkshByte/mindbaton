// Render frames [a, b) of the film at 3840×2160 and encode them: node render.mjs a b fps out.mp4
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import { spawn } from 'child_process';
const [a, b, fps, out] = [+process.argv[2], +process.argv[3], +process.argv[4], process.argv[5]];
const br = await chromium.launch({ args: ['--font-render-hinting=none', '--disable-lcd-text', '--force-color-profile=srgb'] });
const p = await (await br.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: +(process.env.SCALE || 2) })).newPage();
p.on('pageerror', e => console.log('pageerror', e.message));
await p.goto('http://127.0.0.1:8765/brag-output/composition/index.html?t=0');
await p.evaluate(() => window.__ready);
const SCALE = +(process.env.SCALE || 2);
const cdp = await p.context().newCDPSession(p);
const ff = spawn('ffmpeg', ['-loglevel', 'error', '-y', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
  '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-threads', '2', '-pix_fmt', 'yuv420p', '-r', String(fps), out], { stdio: ['pipe', 'inherit', 'inherit'] });
const t0 = Date.now();
for (let f = a; f < b; f++) {
  await p.evaluate(([t, f]) => seek(t, f), [f / fps, f]);
  const { data } = await cdp.send('Page.captureScreenshot', { format: 'jpeg', quality: 94, optimizeForSpeed: true, clip: { x: 0, y: 0, width: 1920, height: 1080, scale: SCALE } });
  if (!ff.stdin.write(Buffer.from(data, 'base64'))) await new Promise(r => ff.stdin.once('drain', r));
  if ((f - a) % 150 === 0) console.log(out, f, ((Date.now() - t0) / (f - a + 1)).toFixed(0) + 'ms/frame');
}
ff.stdin.end(); await new Promise(r => ff.on('close', r)); await br.close();
console.log('done', out, ((Date.now() - t0) / 1000).toFixed(0) + 's');
