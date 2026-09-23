// Regenerates every Mindbaton icon from assets/brand/mark.svg (swap the mark, run this, done).
// Needs Node 20+ and the `playwright` package with its Chromium:
//   npm i --no-save playwright && npx playwright install chromium
//   node assets/brand/make-icons.mjs          (any cwd; NODE_PATH pointing at a playwright install also works)
// Writes: assets/brand/{mark-white,app-icon,wordmark}.svg · assets/app-{,maskable-}{192,512}.png ·
//         extension/icon{16,48,128}.png · site/favicon.svg · site/favicon-32.png · site/apple-touch-icon.png
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const { chromium } = createRequire(import.meta.url)('playwright');
const brand = dirname(fileURLToPath(import.meta.url)), repo = join(brand, '../..');
const BG = '#0A0A0B', ACCENT = '#8B7CFF';

// The mark's own <svg> with its size/colour attributes replaced by `attrs` (its viewBox is kept).
const mark = readFileSync(join(brand, 'mark.svg'), 'utf8').replace(/<\?xml[^>]*>|<!--[\s\S]*?-->/g, '').replace(/\n\s*\n/g, '\n').trim();
const withAttrs = attrs => mark.replace(/<svg\b([^>]*)>/, (_, a) =>
  `<svg${a.replace(/\s(width|height|x|y|color|style)="[^"]*"/g, '')} ${attrs}>`);

// 512-unit tile: #0A0A0B square (rx 0 = full bleed) with the white mark at fraction k of its width.
const tile = (k, rx = 115, accent = ACCENT) => {
  const s = +(512 * k).toFixed(2), o = +((512 - s) / 2).toFixed(2);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" rx="${rx}" fill="${BG}"/>` +
    withAttrs(`x="${o}" y="${o}" width="${s}" height="${s}" color="#fff" style="--mb-accent:${accent}"`) + '</svg>\n';
};
const appIcon = tile(0.7);
const small = tile(0.8, 96);    // 32–48px: less padding so the strokes survive
const tiny = tile(0.9, 80, '#fff'); // 16px (and tab favicons): violet at 2px turns to mud, white nodes stay distinct
const square = tile(0.7, 0);    // iOS rounds it itself and paints transparency black
const maskable = tile(0.56, 0); // mark box ≤ 80% safe-zone circle (0.8/√2 ≈ 0.566), whatever the mark's shape

// Text is live <text>: it renders in Geist where the page has loaded it (index.html, site), else falls back.
const wordmark = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 121 24" fill="currentColor" role="img" aria-label="Mindbaton">' +
  withAttrs('width="24" height="24"') +
  '<text x="32" y="18.3" font-family="Geist, Inter, system-ui, sans-serif" font-size="18" font-weight="600" letter-spacing="-0.36">Mindbaton</text></svg>\n';

const out = (rel, data) => { mkdirSync(dirname(join(repo, rel)), { recursive: true }); writeFileSync(join(repo, rel), data); console.log('wrote', rel); };
out('assets/brand/mark-white.svg', withAttrs('color="#fff"') + '\n');
out('assets/brand/app-icon.svg', appIcon);
out('assets/brand/wordmark.svg', wordmark);
out('site/favicon.svg', tiny);

const pngs = [
  ['assets/app-192.png', appIcon, 192], ['assets/app-512.png', appIcon, 512],
  ['assets/app-maskable-192.png', maskable, 192], ['assets/app-maskable-512.png', maskable, 512],
  ['extension/icon16.png', tiny, 16], ['extension/icon48.png', small, 48], ['extension/icon128.png', appIcon, 128],
  ['site/favicon-32.png', small, 32], ['site/apple-touch-icon.png', square, 180],
];
const browser = await chromium.launch({ args: ['--no-sandbox'] }); // renders only our own local SVG
try {
  const page = await browser.newPage();
  for (const [rel, svg, px] of pngs) {
    await page.setViewportSize({ width: px, height: px });
    await page.setContent(`<style>*{margin:0}svg{display:block;width:${px}px;height:${px}px}</style>${svg}`);
    out(rel, await page.screenshot({ omitBackground: true }));
  }
} finally { await browser.close(); }
