// Regenerates every Mindbaton icon from assets/brand/mark.svg (swap the mark, run this, done).
// Needs Node 20+ and the `playwright` package with its Chromium:
//   npm i --no-save playwright && npx playwright install chromium
//   node assets/brand/make-icons.mjs          (any cwd; NODE_PATH pointing at a playwright install also works)
// Reads mark.svg + wordmark.svg (outlined lockup; update it with the mark).
// Writes: assets/brand/{mark-white,app-icon}.svg · assets/app-{,maskable-}{192,512}.png ·
//         extension/icon{16,48,128}.png · site/favicon.svg · site/favicon-32.png · site/apple-touch-icon.png ·
//         assets/brand/terminal-logo.json (the installer's terminal art, drawn by mindbaton.py; about 2 min)
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const { chromium } = createRequire(import.meta.url)('playwright');
const brand = dirname(fileURLToPath(import.meta.url)), repo = join(brand, '../..');
const BG = '#0A0A0B'; // the logo is one colour: white on this black

// The mark's own <svg> with its size/colour attributes replaced by `attrs` (its viewBox is kept).
const mark = readFileSync(join(brand, 'mark.svg'), 'utf8').replace(/<\?xml[^>]*>|<!--[\s\S]*?-->/g, '').replace(/\n\s*\n/g, '\n').trim();
const withAttrs = attrs => mark.replace(/<svg\b([^>]*)>/, (_, a) =>
  `<svg${a.replace(/\s(width|height|x|y|color|style)="[^"]*"/g, '')} ${attrs}>`);

// 512-unit tile: #0A0A0B square (rx 0 = full bleed) with the white mark at fraction k of its width.
const tile = (k, rx = 115) => {
  const s = +(512 * k).toFixed(2), o = +((512 - s) / 2).toFixed(2);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" rx="${rx}" fill="${BG}"/>` +
    withAttrs(`x="${o}" y="${o}" width="${s}" height="${s}" color="#fff"`) + '</svg>\n';
};
const appIcon = tile(0.7);
const small = tile(0.8, 96);    // 32–48px: less padding so the strokes survive
const tiny = tile(0.9, 80);    // 16px (and tab favicons)
const square = tile(0.7, 0);    // iOS rounds it itself and paints transparency black
const maskable = tile(0.56, 0); // mark box ≤ 80% safe-zone circle (0.8/√2 ≈ 0.566), whatever the mark's shape

const out = (rel, data) => { mkdirSync(dirname(join(repo, rel)), { recursive: true }); writeFileSync(join(repo, rel), data); console.log('wrote', rel); };
out('assets/brand/mark-white.svg', withAttrs('color="#fff"') + '\n');
out('assets/brand/app-icon.svg', appIcon);
out('site/favicon.svg', tiny);

const pngs = [
  ['assets/app-192.png', appIcon, 192], ['assets/app-512.png', appIcon, 512],
  ['assets/app-maskable-192.png', maskable, 192], ['assets/app-maskable-512.png', maskable, 512],
  ['extension/icon16.png', tiny, 16], ['extension/icon48.png', small, 48], ['extension/icon128.png', appIcon, 128],
  ['site/favicon-32.png', small, 32], ['site/apple-touch-icon.png', square, 180],
];
// Terminal art (assets/brand/terminal-logo.json, drawn by mindbaton.py). Each size is `rows` cells tall and as wide as
// the logo's true proportions need for a cell ASPECT wide per 1 tall (9×19 px: DejaVu Sans Mono 16 px; most terminals
// are 0.45–0.5). Every cell is supersampled from the SVG, and each size and mode gets its own sub-cell shift and scale:
// the one that keeps each hole of the logo a hole of about its size (the eyes first, then letter counters) and, among
// those, matches the logo best (IoU). Then the second eye is nudged by itself (under half a sub-cell) until it has the
// first eye's shape, so the two eyes always read as a pair. Rendered in a real terminal (xterm.js, 9×19 px cells) the
// quadrant art covers the SVG at IoU 0.83–0.96. Modes:
//   cells   quadrant glyphs ▘▝▖▗▀▄▌▐▛… (2×2 per cell) as [char, fg, bg] palette indices, null = terminal background;
//           `palette` is white ink for dark terminals, `paletteLight` BG ink for light ones (same indices). Ink is solid:
//           grey anti-aliased edge cells were tried and measure closer, but read as smudges at cell size.
//   braille 2×4 dots per cell.
//   ascii   (mark only) whole cells: each eye is blank cells walled by solid FILL, edges take the font glyph whose shape
//           matches the cell's ink best.
const TERM = { mark: [6, 8, 10, 12, 16], lockup: [6, 8, 10, 12] }; // 5 and 7 rows break letters up
const ASPECT = 0.474, ASCII = { set: " .,'`\"_|()dbPYo", fill: '@' }; // '@' reads as a solid body (it beat '8' and '#')
const XTERM = [0, 95, 135, 175, 215, 255];
const to256 = h => { // nearest xterm-256 colour (6×6×6 cube or grey ramp), plain RGB distance
  const [r, g, b] = h.match(/\w\w/g).map(v => parseInt(v, 16)), d = c => (c[0] - r) ** 2 + (c[1] - g) ** 2 + (c[2] - b) ** 2;
  let best = 16, bd = Infinity;
  for (let i = 16; i < 256; i++) {
    const c = i < 232 ? [XTERM[((i - 16) / 36) | 0], XTERM[(((i - 16) / 6) | 0) % 6], XTERM[(i - 16) % 6]] : Array(3).fill(8 + 10 * (i - 232));
    if (d(c) < bd) bd = d(c), best = i;
  }
  return best;
};

// Runs in the page (self-contained): { mark: [size…], lockup: [size…] }.
async function terminalArt({ svgs, TERM, BG, ASPECT, ASCII }) {
  const CW = 16; // supersampling: px per cell width
  const rgb = h => h.match(/\w\w/g).map(v => parseInt(v, 16));
  const hex = c => '#' + [...c].slice(0, 3).map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
  const dist = (a, b) => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2;
  const load = async (svg, ink) => { // 16 px per SVG unit
    const vb = svg.match(/viewBox="([^"]+)"/)[1].trim().split(/[\s,]+/).map(Number), W = Math.round(vb[2] * 16), H = Math.round(vb[3] * 16);
    const img = new Image();
    img.src = URL.createObjectURL(new Blob([svg.replace(/<svg\b([^>]*)>/, (_, a) =>
      `<svg${a.replace(/\s(width|height|color)="[^"]*"/g, '')} width="${W}" height="${H}" color="${ink}">`)], { type: 'image/svg+xml' }));
    await img.decode();
    const c = new OffscreenCanvas(W, H); c.getContext('2d').drawImage(img, 0, 0);
    return c;
  };
  // Background regions (4-connected) of a 0/1 grid; a hole is one that never touches the edge.
  const regions = (m, W, H) => {
    const lab = new Int32Array(W * H).fill(-1), list = [], st = [];
    for (let s = 0; s < W * H; s++) {
      if (m[s] || lab[s] >= 0) continue;
      const r = { id: list.length, n: 0, sx: 0, edge: false };
      list.push(r); lab[s] = r.id; st.push(s);
      while (st.length) {
        const p = st.pop(), x = p % W, y = (p / W) | 0;
        r.n++; r.sx += x;
        if (!x || !y || x === W - 1 || y === H - 1) r.edge = true;
        for (const q of [x > 0 && p - 1, x < W - 1 && p + 1, y > 0 && p - W, y < H - 1 && p + W])
          if (q !== false && !m[q] && lab[q] < 0) { lab[q] = r.id; st.push(q); }
      }
    }
    return { lab, list };
  };
  const art = {};
  for (const name of ['mark', 'lockup']) {
    const dark = await load(svgs[name], '#fff'), light = await load(svgs[name], BG);
    const a0 = dark.getContext('2d').getImageData(0, 0, dark.width, dark.height).data; // tight box of what is painted
    let x0 = Infinity, y0 = Infinity, x1 = -1, y1 = -1;
    for (let i = 0; i < a0.length / 4; i++) if (a0[i * 4 + 3] > 8) {
      const x = i % dark.width, y = (i / dark.width) | 0;
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
    }
    const bb = [x0, y0, x1 - x0 + 1, y1 - y0 + 1];
    // The art's solid colours (≥ 1 % of opaque pixels, near-duplicates merged), so a multi-colour logo keeps its colours.
    const solids = c => {
      const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data, n = {}; let total = 0;
      for (let i = 3; i < d.length; i += 4) if (d[i] > 250) { const h = hex(d.slice(i - 3, i)); n[h] = (n[h] || 0) + 1; total++; }
      const out = [];
      for (const h of Object.keys(n).sort((a, b) => n[b] - n[a])) if (n[h] >= total / 100 && !out.some(o => dist(o, rgb(h)) < 300)) out.push(rgb(h));
      return out;
    };
    const sd = solids(dark), sl = solids(light);
    // The eyes (holes left of the first empty column) as their own cut-outs over a body with the eyes filled in, so each
    // eye can be nudged (< ½ sub-cell) onto the grid by itself and both come out the same shape.
    const cuts = [], body = {}, Wc = dark.width, Hc = dark.height, A = a0, filled = new Uint8Array(Wc * Hc);
    {
      const m = Uint8Array.from({ length: Wc * Hc }, (_, i) => A[i * 4 + 3] >= 128);
      let gap = 0;
      for (let seen = false; gap < Wc; gap++) { let any = 0; for (let y = 0; y < Hc; y++) any |= m[y * Wc + gap]; if (any) seen = true; else if (seen) break; }
      const { lab, list } = regions(m, Wc, Hc);
      for (const r of list.filter(r => !r.edge && r.sx / r.n < gap)) {
        const cut = new ImageData(Wc, Hc), box = [Wc, Hc, 0, 0];
        for (let p = 0; p < Wc * Hc; p++) if (lab[p] === r.id) {
          const x = p % Wc, y = (p / Wc) | 0; // the hole and its anti-aliased rim
          for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) { const i = (y + dy) * Wc + x + dx; cut.data[i * 4 + 3] = 255 - A[i * 4 + 3]; filled[i] = 1; }
          box[0] = Math.min(box[0], x - 3); box[1] = Math.min(box[1], y - 3); box[2] = Math.max(box[2], x + 3); box[3] = Math.max(box[3], y + 3);
        }
        const c = new OffscreenCanvas(Wc, Hc);
        c.getContext('2d').putImageData(cut, 0, 0); cuts.push({ c, box: [box[0], box[1], box[2] - box[0], box[3] - box[1]] });
      }
    }
    for (const [k, src, ink] of [['dark', dark, sd[0]], ['light', light, sl[0]]]) {
      const d = src.getContext('2d').getImageData(0, 0, Wc, Hc), c = new OffscreenCanvas(Wc, Hc);
      for (let i = 0; i < Wc * Hc; i++) if (filled[i]) d.data.set([...ink, 255], i * 4);
      c.getContext('2d').putImageData(d, 0, 0); body[k] = c;
    }
    art[name] = [];
    for (const rows of TERM[name]) {
      const ch = Math.round(CW / ASPECT), cols = Math.round(rows * ch / CW * bb[2] / bb[3]), W = cols * CW, H = rows * ch;
      // RGBA of the logo in the W×H box at its true aspect, centred, scaled by s about the centre, shifted by (ox, oy) px
      // (ink 'dark' | 'light'; es[k] = extra [x, y] px shift of eye k)
      const draw = (ink, s = 1, ox = 0, oy = 0, es = []) => {
        const x = new OffscreenCanvas(W, H).getContext('2d', { willReadFrequently: true }), f = Math.min(W / bb[2], H / bb[3]) * s;
        x.imageSmoothingQuality = 'high';
        const at = (c, [sx, sy, sw, sh], ex = 0, ey = 0) =>
          x.drawImage(c, sx, sy, sw, sh, (W - bb[2] * f) / 2 + ox + ex + (sx - bb[0]) * f, (H - bb[3] * f) / 2 + oy + ey + (sy - bb[1]) * f, sw * f, sh * f);
        at(body[ink], bb);
        x.globalCompositeOperation = 'destination-out';
        cuts.forEach(({ c, box }, k) => at(c, box, ...(es[k] || [])));
        return x.getImageData(0, 0, W, H).data;
      };
      const ref = draw('dark'), R = new Uint8Array(W * H);
      let nR = 0; for (let i = 0; i < W * H; i++) nR += R[i] = ref[i * 4 + 3] >= 128;
      // The reference's holes; the eyes are the ones left of the first empty column (the rest: letter counters).
      let gap = 0;
      for (let seen = false; gap < W; gap++) { let any = 0; for (let y = 0; y < H; y++) any |= R[y * W + gap]; if (any) seen = true; else if (seen) break; }
      const rr = regions(R, W, H), holes = rr.list.filter(r => !r.edge && r.n >= CW * CW / 4).map(r => ({ ...r, eye: r.sx / r.n < gap }));
      const holeOf = Int8Array.from(rr.lab, l => l < 0 ? -1 : holes.findIndex(h => h.id === l));
      // gx×gy sub-cells per cell: pixel → sub-cell maps, sub-cell areas, reference ink and hole pixels per sub-cell
      const grid = (gx, gy) => {
        const gw = cols * gx, gh = rows * gy, sx = new Int32Array(W), sy = new Int32Array(H);
        for (let x = 0; x < W; x++) { const c = (x / CW) | 0, r = x - c * CW; let k = 0; while (k < gx - 1 && r >= Math.round((k + 1) * CW / gx)) k++; sx[x] = c * gx + k; }
        for (let y = 0; y < H; y++) { const c = (y / ch) | 0, r = y - c * ch; let k = 0; while (k < gy - 1 && r >= Math.round((k + 1) * ch / gy)) k++; sy[y] = c * gy + k; }
        const area = new Float32Array(gw * gh), rc = new Float32Array(gw * gh), hid = holes.map(() => new Float32Array(gw * gh));
        for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
          const i = y * W + x, g = sy[y] * gw + sx[x]; area[g]++; rc[g] += R[i];
          if (holeOf[i] >= 0) hid[holeOf[i]][g]++;
        }
        const mean = px => { const m = new Float32Array(gw * gh); for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) m[sy[y] * gw + sx[x]] += px[(y * W + x) * 4 + 3] / 255; return m.map((v, g) => v / area[g]); };
        return { gx, gy, gw, gh, sx, sy, area, rc, hid, mean };
      };
      // [eyes kept, other holes kept, IoU] of a sub-cell mask; a hole is kept if it maps to its own hole of 1/3..3× its area
      const score = (G, on) => {
        let I = 0, A = 0; for (let g = 0; g < on.length; g++) if (on[g]) { I += G.rc[g]; A += G.area[g]; }
        const { lab, list } = regions(on, G.gw, G.gh), used = new Set(), ids = holes.map(() => -1); let eyes = 0, other = 0;
        holes.forEach((h, k) => {
          const n = {}; for (let g = 0; g < on.length; g++) if (G.hid[k][g] && lab[g] >= 0 && !list[lab[g]].edge) n[lab[g]] = (n[lab[g]] || 0) + G.hid[k][g];
          const id = Object.keys(n).sort((a, b) => n[b] - n[a])[0];
          if (id === undefined || used.has(id)) return;
          used.add(id); ids[k] = +id;
          let px = 0; for (let g = 0; g < on.length; g++) if (lab[g] == id) px += G.area[g];
          if (px / h.n >= 1 / 3 && px / h.n <= 3) h.eye ? eyes++ : other++;
        });
        return Object.assign([eyes, other, I / (A + nR - I)], { lab, ids });
      };
      // How alike the eyes of a mask are: IoU of each eye's sub-cells with the first eye's (best of ±1 around their offset).
      const same = (G, r) => {
        const sets = r.ids.filter((_, k) => holes[k].eye).map(id => {
          const s = []; if (id >= 0) for (let g = 0; g < r.lab.length; g++) if (r.lab[g] === id) s.push([g % G.gw, (g / G.gw) | 0]);
          return s;
        });
        if (sets.length < 2 || sets.some(s => !s.length)) return 0;
        const mid = s => s.reduce((a, [x, y]) => [a[0] + x / s.length, a[1] + y / s.length], [0, 0]), [A0, ...rest] = sets, [ax, ay] = mid(A0);
        const inA = new Set(A0.map(([x, y]) => x + ',' + y));
        return rest.reduce((tot, B) => {
          const [bx, by] = mid(B); let best = 0;
          for (let ty = -1; ty <= 1; ty++) for (let tx = -1; tx <= 1; tx++) {
            const dx = Math.round(bx - ax) + tx, dy = Math.round(by - ay) + ty, n = B.filter(([x, y]) => inA.has((x - dx) + ',' + (y - dy))).length;
            best = Math.max(best, n / (A0.length + B.length - n));
          }
          return tot + best / rest.length;
        }, 0);
      };
      const better = (a, b) => { for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] > b[i]; return false; };
      // Best shift (± 3/8 sub-cell) and scale (± 3 %) for the whole art, then each further eye nudged by itself
      // (± ½ sub-cell) to take the first eye's shape. A sub-cell is ink when its coverage ≥ thr.
      const search = (G, thr = 0.5) => {
        const test = (t, alike) => {
          const on = G.mean(draw('dark', ...t)).map(v => v >= thr), sc = score(G, on);
          return { t, on, sc, key: [sc[0], sc[1], alike ? same(G, sc) : 0, sc[2]] };
        };
        let best = null;
        for (const s of [0.97, 0.985, 1, 1.015, 1.03]) for (const dx of [-3, -2, -1, 0, 1, 2, 3]) for (const dy of [-3, -2, -1, 0, 1, 2, 3]) {
          const c = test([s, dx / 8 * CW / G.gx, dy / 8 * ch / G.gy], false);
          if (!best || better(c.key, best.key)) best = c;
        }
        best = test(best.t, true);
        for (let k = 1; k < cuts.length; k++) {
          const t0 = best.t;
          for (let ex = -4; ex <= 4; ex++) for (let ey = -4; ey <= 4; ey++) {
            const es = [...(t0[3] || [])]; es[k] = [ex / 8 * CW / G.gx, ey / 8 * ch / G.gy];
            const c = test([...t0.slice(0, 3), es], true);
            if (better(c.key, best.key)) best = c;
          }
        }
        return best;
      };

      // Quadrant cells, each ink pixel snapped to the nearest solid colour of the art (dark and light pair).
      const Q = grid(2, 2), q = search(Q), pd = draw('dark', ...q.t), pl = draw('light', ...q.t);
      const col = Array.from({ length: Q.gw * Q.gh }, () => [0, 0, 0, 0, 0, 0, 0]);
      for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
        const i = (y * W + x) * 4, a = pd[i + 3] / 255, al = pl[i + 3] / 255, c = col[Q.sy[y] * Q.gw + Q.sx[x]];
        c[0] += pd[i] * a; c[1] += pd[i + 1] * a; c[2] += pd[i + 2] * a; c[3] += a; c[4] += pl[i] * al; c[5] += pl[i + 1] * al; c[6] += pl[i + 2] * al;
      }
      const snap = (S, c) => hex(S.length ? S.reduce((b, s) => dist(s, c) < dist(b, c) ? s : b) : c);
      const keys = [], idx = k => keys.includes(k) ? keys.indexOf(k) : keys.push(k) - 1; // palette index of a dark+light pair
      const rank = k => sd.findIndex(c => hex(c) === k.slice(0, 7));
      // Bits: 1 top-left, 2 top-right, 4 bottom-left, 8 bottom-right. A cell with a clear quadrant has one ink (its
      // majority colour; clear = terminal background); a fully inked cell can show two (fg for the glyph, bg for the rest).
      const QUAD = ' ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█', cells = [];
      for (let y = 0; y < rows; y++) {
        const row = [];
        for (let x = 0; x < cols; x++) {
          const k4 = [[0, 0], [1, 0], [0, 1], [1, 1]].map(([dx, dy]) => {
            const g = (2 * y + dy) * Q.gw + 2 * x + dx, c = col[g];
            return q.on[g] ? snap(sd, [c[0] / c[3], c[1] / c[3], c[2] / c[3]]) + snap(sl, [c[4] / c[3], c[5] / c[3], c[6] / c[3]]) : null;
          });
          const m = k4.reduce((m, k, b) => k ? m | 1 << b : m, 0), n = {};
          k4.forEach(k => k && (n[k] = (n[k] || 0) + 1));
          const [A, B] = Object.keys(n).sort((a, b) => n[b] - n[a] || rank(a) - rank(b)); // ties: the art's main colour
          if (!m) row.push([' ', null, null]);
          else if (m === 15 && B) row.push([QUAD[k4.reduce((f, k, b) => k === A ? f | 1 << b : f, 0)], idx(A), idx(B)]);
          else row.push([QUAD[m], idx(A), null]);
        }
        cells.push(row);
      }

      // Braille: 2×4 dots, its own search.
      const Bg = grid(2, 4), b = search(Bg), DOTS = [[0, 0, 1], [0, 1, 2], [0, 2, 4], [1, 0, 8], [1, 1, 16], [1, 2, 32], [0, 3, 64], [1, 3, 128]];
      const braille = [];
      for (let y = 0; y < rows; y++) {
        let s = '';
        for (let x = 0; x < cols; x++) s += String.fromCharCode(0x2800 + DOTS.reduce((m, [dx, dy, bit]) => b.on[(4 * y + dy) * Bg.gw + 2 * x + dx] ? m | bit : m, 0));
        braille.push(s.replace(/⠀+$/, ''));
      }
      const pal = o => keys.map(k => k.slice(o, o + 7)), v = { rows, cols, palette: pal(0), paletteLight: pal(7), cells, braille };
      const sc = r => `eyes ${r.sc[0]}/${holes.filter(h => h.eye).length} alike ${r.key[2].toFixed(2)} IoU ${r.sc[2].toFixed(3)}`;
      console.log(`${name} ${rows}×${cols}: quadrants ${sc(q)} · braille ${sc(b)}`);
      art[name].push(v);
      if (name !== 'mark') continue;

      // ASCII (mark only: the name is set in type beside it). Whole cells; a cell is ink at ≥ 0.7 coverage so the eyes
      // come out a little generous, which reads better in type.
      const C = grid(1, 1), a = search(C, 0.7), cr = regions(a.on, cols, rows), hole = i => cr.lab[i] >= 0 && !cr.list[cr.lab[i]].edge;
      const nearHole = (x, y) => [-1, 0, 1].some(dy => [-1, 0, 1].some(dx => x + dx >= 0 && x + dx < cols && y + dy >= 0 && y + dy < rows && hole((y + dy) * cols + x + dx)));
      // Glyph shapes on a 4×8 grid per cell, softened a little (as seen from a normal distance).
      const GX = 4, GY = 8, Ag = grid(GX, GY), am = Ag.mean(draw('dark', ...a.t));
      const soft = v => {
        let s = Float32Array.from(v);
        for (const [dx, dy, r] of [[1, 0, 1], [0, 1, 2]]) {
          const o = new Float32Array(s.length);
          for (let y = 0; y < GY; y++) for (let x = 0; x < GX; x++) {
            let t = 0, n = 0;
            for (let k = -r; k <= r; k++) { const X = x + dx * k, Y = y + dy * k; if (X >= 0 && X < GX && Y >= 0 && Y < GY) t += s[Y * GX + X], n++; }
            o[y * GX + x] = t / n;
          }
          s = o;
        }
        return s;
      };
      const gx = new OffscreenCanvas(CW, ch).getContext('2d', { willReadFrequently: true });
      gx.font = '100px "DejaVu Sans Mono", monospace'; gx.font = `${100 * CW / gx.measureText('M').width}px "DejaVu Sans Mono", monospace`;
      const fm = gx.measureText('M'), base = (ch - fm.fontBoundingBoxAscent - fm.fontBoundingBoxDescent) / 2 + fm.fontBoundingBoxAscent;
      const glyphs = [...ASCII.set + ASCII.fill].map(c => {
        gx.clearRect(0, 0, CW, ch); gx.fillStyle = '#fff'; gx.fillText(c, 0, base);
        const d = gx.getImageData(0, 0, CW, ch).data, s = new Float32Array(GX * GY), n = new Float32Array(GX * GY);
        for (let y = 0; y < ch; y++) for (let x = 0; x < CW; x++) { const g = Ag.sy[y] * GX + Ag.sx[x]; s[g] += d[(y * CW + x) * 4 + 3] / 255; n[g]++; }
        return { c, v: soft(s.map((t, i) => t / n[i])) };
      });
      const fillInk = glyphs.at(-1).v.reduce((s, t) => s + t) / (GX * GY); // coverage 1 = as dense as FILL
      v.ascii = [];
      for (let y = 0; y < rows; y++) {
        let s = '';
        for (let x = 0; x < cols; x++) {
          const L = [];
          for (let dy = 0; dy < GY; dy++) for (let dx = 0; dx < GX; dx++) L.push(am[(GY * y + dy) * Ag.gw + GX * x + dx]);
          const mean = L.reduce((s, t) => s + t) / L.length;
          if (hole(y * cols + x) || mean <= 0.1) { s += ' '; continue; }
          if (mean >= 0.9 || (a.on[y * cols + x] && nearHole(x, y))) { s += ASCII.fill; continue; }
          const T = soft(L.map(t => t * fillInk));
          s += glyphs.reduce((b, g) => { const d = g.v.reduce((e, t, i) => e + (T[i] - t) ** 2, 0); return d < b.d ? { c: g.c, d } : b; }, { d: Infinity }).c;
        }
        v.ascii.push(s.trimEnd());
      }
      console.log(`${name} ${rows}×${cols}: ascii ${sc(a)}`);
    }
  }
  return art;
}

const browser = await chromium.launch({ args: ['--no-sandbox'] }); // renders only our own local SVG
try {
  const page = await browser.newPage();
  for (const [rel, svg, px] of pngs) {
    await page.setViewportSize({ width: px, height: px });
    await page.setContent(`<style>*{margin:0}svg{display:block;width:${px}px;height:${px}px}</style>${svg}`);
    out(rel, await page.screenshot({ omitBackground: true }));
  }

  await page.setContent('<!doctype html><body>');
  page.on('console', m => console.log(m.text()));
  const svgs = { mark, lockup: readFileSync(join(brand, 'wordmark.svg'), 'utf8') };
  const art = await page.evaluate(terminalArt, { svgs, TERM, BG, ASPECT, ASCII });
  for (const v of [...art.mark, ...art.lockup]) Object.assign(v, { palette256: v.palette.map(to256), paletteLight256: v.paletteLight.map(to256) });
  out('assets/brand/terminal-logo.json', JSON.stringify({
    about: `Generated by make-icons.mjs from mark.svg + wordmark.svg for cells ${ASPECT} wide per 1 tall; drawn by mindbaton.py. Cells are [char, fg, bg] palette indices (null = terminal background); ascii is mark only.`,
    ...art }) + '\n');
} finally { await browser.close(); }
