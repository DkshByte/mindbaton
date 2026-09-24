// Regenerates every Mindbaton icon from assets/brand/mark.svg (swap the mark, run this, done).
// Needs Node 20+ and the `playwright` package with its Chromium:
//   npm i --no-save playwright && npx playwright install chromium
//   node assets/brand/make-icons.mjs          (any cwd; NODE_PATH pointing at a playwright install also works)
// Writes: assets/brand/{mark-white,app-icon,wordmark}.svg · assets/app-{,maskable-}{192,512}.png ·
//         extension/icon{16,48,128}.png · site/favicon.svg · site/favicon-32.png · site/apple-touch-icon.png ·
//         assets/brand/terminal-logo.json (the installer's terminal art, drawn by mindbaton.py)
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
// Terminal art. A terminal cell is ~1:2, so one cell = two square pixels stacked (▀ with fg = top, bg = bottom),
// or 2×4 braille dots. Sizes are cell rows; width follows the art's own aspect. Colours are pre-blended (anti-aliased
// edges): `palette` = white ink over BG for dark terminals, `paletteLight` = BG-coloured ink over white for light ones
// (same indices). Fully clear pixels stay transparent (null) so the terminal's own background shows.
const TERM = { mark: [6, 8, 10, 12, 16], lockup: [5, 6, 8, 10, 12] };
const geist = readFileSync(join(repo, 'assets/fonts/Geist-Variable.woff2')).toString('base64');
const lockupSvg = wordmark.replace('<svg', '<svg width="121" height="24"');
const markSvg = withAttrs('width="24" height="24"');
const XTERM = [0, 95, 135, 175, 215, 255];
const hex = c => '#' + c.map(v => v.toString(16).padStart(2, '0')).join('');
const to256 = ([r, g, b]) => { // nearest xterm-256 colour (6×6×6 cube or grey ramp), plain RGB distance
  const d = c => (c[0] - r) ** 2 + (c[1] - g) ** 2 + (c[2] - b) ** 2;
  let best = 16, bd = Infinity;
  for (let i = 16; i < 256; i++) {
    const c = i < 232 ? [XTERM[((i - 16) / 36) | 0], XTERM[(((i - 16) / 6) | 0) % 6], XTERM[(i - 16) % 6]] : Array(3).fill(8 + 10 * (i - 232));
    if (d(c) < bd) bd = d(c), best = i;
  }
  return best;
};

const browser = await chromium.launch({ args: ['--no-sandbox'] }); // renders only our own local SVG
try {
  const page = await browser.newPage();
  for (const [rel, svg, px] of pngs) {
    await page.setViewportSize({ width: px, height: px });
    await page.setContent(`<style>*{margin:0}svg{display:block;width:${px}px;height:${px}px}</style>${svg}`);
    out(rel, await page.screenshot({ omitBackground: true }));
  }

  // RGBA pixels of `inner` (drawn in its own user units) cropped to viewBox `vb`, at w×h px.
  const raster = async (inner, vb, w, h, ink = '#fff') => {
    await page.setViewportSize({ width: w, height: h });
    await page.setContent(`<style>@font-face{font-family:Geist;src:url(data:font/woff2;base64,${geist});font-weight:100 900}
      *{margin:0}svg{display:block}</style><svg xmlns="http://www.w3.org/2000/svg" viewBox="${vb.join(' ')}" width="${w}" height="${h}"
      preserveAspectRatio="none" color="${ink}" style="--mb-accent:${ACCENT}">${inner}</svg>`);
    await page.evaluate(() => document.fonts.ready);
    const png = (await page.screenshot({ omitBackground: true })).toString('base64');
    return page.evaluate(async b64 => {
      const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
      const c = new OffscreenCanvas(img.width, img.height), x = c.getContext('2d');
      x.drawImage(img, 0, 0); return Array.from(x.getImageData(0, 0, img.width, img.height).data);
    }, png);
  };
  // Tight viewBox around what is actually painted (strokes included), found from a 16 px/unit render.
  const tight = async (inner, W, H) => {
    const k = 16, px = await raster(inner, [0, 0, W, H], W * k, H * k);
    let x0 = Infinity, y0 = Infinity, x1 = -1, y1 = -1;
    for (let i = 3; i < px.length; i += 4) if (px[i] > 8) {
      const p = (i - 3) / 4, x = p % (W * k), y = (p / (W * k)) | 0;
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
    }
    return [x0 / k, y0 / k, (x1 + 1 - x0) / k, (y1 + 1 - y0) / k];
  };
  const art = {};
  for (const [name, inner, W] of [['mark', markSvg, 24], ['lockup', lockupSvg, 121]]) {
    const vb = await tight(inner, W, 24);
    art[name] = [];
    for (const rows of TERM[name]) {
      const cols = Math.round(rows * 2 * vb[2] / vb[3]), W2 = cols * 2;
      const px = await raster(inner, vb, W2, rows * 2), pxL = await raster(inner, vb, W2, rows * 2, BG), keys = [];
      const blend = (p, i, bg) => [0, 1, 2].map(j => p[i + j] * p[i + 3] / 255 + bg[j] * (1 - p[i + 3] / 255));
      const mean = (s, f) => [0, 1, 2].map(j => Math.round(s.reduce((a, p) => a + p[f][j], 0) / s.length));
      const idx = s => { // palette index of the set's mean colour (dark + light variant under one index)
        const k = hex(mean(s, 'd')) + hex(mean(s, 'l'));
        return keys.includes(k) ? keys.indexOf(k) : keys.push(k) - 1;
      };
      // Each cell is 2×2 pixels drawn with a quadrant glyph (bit 1 top-left, 2 top-right, 4 bottom-left, 8 bottom-right)
      // in its best two-colour fit. Clear pixels stay the terminal's own background, so a cell with any clear pixel is
      // one ink colour over nothing; only fully inked cells get a second (bg) colour.
      const QUAD = ' ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█', cells = [];
      for (let y = 0; y < rows; y++) {
        const row = [];
        for (let x = 0; x < cols; x++) {
          const q = [[0, 0], [1, 0], [0, 1], [1, 1]].map(([dx, dy]) => {
            const i = ((2 * y + dy) * W2 + 2 * x + dx) * 4;
            return { a: px[i + 3], d: blend(px, i, [10, 10, 11]), l: blend(pxL, i, [255, 255, 255]) };
          });
          let m = q.reduce((m, p, b) => p.a >= 64 ? m | 1 << b : m, 0);
          if (m === 15) { // fully inked: the split with the least colour error (15 = one flat colour)
            const err = s => { const c = mean(s, 'd'); return s.reduce((e, p) => e + p.d.reduce((a, v, j) => a + (v - c[j]) ** 2, 0), 0); };
            const part = k => [q.filter((_, b) => k >> b & 1), q.filter((_, b) => !(k >> b & 1))];
            let best = Infinity;
            for (let k = 1; k <= 15; k++) {
              const [A, B] = part(k), e = err(A) + (B.length ? err(B) : 0) + (k < 15 ? 800 : 0); // a split must earn its seam
              if (e < best) best = e, m = k;
            }
            const [A, B] = part(m);
            row.push([QUAD[m], idx(A), B.length ? idx(B) : null]);
          } else row.push(m ? [QUAD[m], idx(q.filter((_, b) => m >> b & 1)), null] : [' ', null, null]);
        }
        cells.push(row);
      }
      // Monochrome: braille (2×4 dots per cell) and plain ASCII by ink coverage, from a 2×4-per-cell render.
      const hi = await raster(inner, vb, cols * 2, rows * 4), ink = (x, y) => hi[(y * cols * 2 + x) * 4 + 3] / 255;
      const DOTS = [[0, 0, 1], [0, 1, 2], [0, 2, 4], [1, 0, 8], [1, 1, 16], [1, 2, 32], [0, 3, 64], [1, 3, 128]];
      const RAMP = ' .:-=+*#%@', braille = [], ascii = [];
      for (let y = 0; y < rows; y++) {
        let br = '', as = '';
        for (let x = 0; x < cols; x++) {
          let bits = 0, sum = 0;
          for (const [dx, dy, bit] of DOTS) { const v = ink(2 * x + dx, 4 * y + dy); sum += v; if (v >= 0.5) bits |= bit; }
          br += String.fromCharCode(0x2800 + bits);
          as += RAMP[Math.min(9, Math.round(sum / 8 * 9))];
        }
        braille.push(br.replace(/\u2800+$/, '')); ascii.push(as.trimEnd());
      }
      const pal = o => keys.map(k => k.slice(o, o + 7)), q = p => p.map(h => to256(h.match(/\w\w/g).map(v => parseInt(v, 16))));
      const palette = pal(0), paletteLight = pal(7);
      art[name].push({ rows, cols, palette, palette256: q(palette), paletteLight, paletteLight256: q(paletteLight),
        cells, braille, ascii });
    }
  }
  out('assets/brand/terminal-logo.json', JSON.stringify({
    about: 'Generated by make-icons.mjs from mark.svg + wordmark.svg; drawn by mindbaton.py. Cells are [char, fg, bg] palette indices (null = terminal background).',
    ...art }) + '\n');
} finally { await browser.close(); }
