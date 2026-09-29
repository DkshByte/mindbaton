// Motion toolkit for the film. No CSS animations anywhere: every property is set from t inside seek(t), so any frame
// can be rendered alone, in any order, on any machine.
const W = 1920, H = 1080;
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, p) => a + (b - a) * p;
const inv = (a, b, x) => clamp((x - a) / (b - a));

function bezier(x1, y1, x2, y2) {  // CSS cubic-bezier, solved by Newton + bisection
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx, cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const X = t => ((ax * t + bx) * t + cx) * t, Y = t => ((ay * t + by) * t + cy) * t, dX = t => (3 * ax * t + 2 * bx) * t + cx;
  return x => {
    if (x <= 0) return 0; if (x >= 1) return 1;
    let t = x;
    for (let i = 0; i < 8; i++) { const e = X(t) - x, d = dX(t); if (Math.abs(e) < 1e-6) return Y(t); if (Math.abs(d) < 1e-6) break; t -= e / d; }
    let lo = 0, hi = 1; t = x;
    for (let i = 0; i < 30; i++) { const v = X(t); if (Math.abs(v - x) < 1e-6) break; if (v < x) lo = t; else hi = t; t = (lo + hi) / 2; }
    return Y(t);
  };
}
const E = {
  lin: t => t,
  inQuad: t => t * t, outQuad: t => 1 - (1 - t) * (1 - t),
  inCubic: t => t * t * t, outCubic: t => 1 - Math.pow(1 - t, 3),
  inOutCubic: t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2,
  outQuart: t => 1 - Math.pow(1 - t, 4), inOutQuart: t => t < .5 ? 8 * t ** 4 : 1 - Math.pow(-2 * t + 2, 4) / 2,
  inExpo: t => t === 0 ? 0 : Math.pow(2, 10 * t - 10), outExpo: t => t === 1 ? 1 : 1 - Math.pow(2, -10 * t),
  inOutExpo: t => t === 0 ? 0 : t === 1 ? 1 : t < .5 ? Math.pow(2, 20 * t - 10) / 2 : (2 - Math.pow(2, -20 * t + 10)) / 2,
  outBack: t => { const c = 1.70158; return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); },
  inBack: t => { const c = 1.70158; return (c + 1) * t * t * t - c * t * t; },
  site: bezier(.16, 1, .3, 1),        // the site's --ease
  snap: bezier(.7, 0, .2, 1),         // camera moves: slow out, decisive in
  soft: bezier(.45, 0, .2, 1),
};
// damped spring 0→1 (f: Hz, z: damping ratio)
function spring(t, f = 2.2, z = .42) {
  if (t <= 0) return 0;
  const w = 2 * Math.PI * f, wd = w * Math.sqrt(1 - z * z);
  return 1 - Math.exp(-z * w * t) * (Math.cos(wd * t) + (z * w / wd) * Math.sin(wd * t));
}
const tw = (t, t0, d, e = E.outCubic) => e(inv(t0, t0 + d, t));
// keyframes: [[time, value, ease-into-this-key], ...]
function kf(t, keys) {
  if (t <= keys[0][0]) return keys[0][1];
  for (let i = 1; i < keys.length; i++) {
    const [t1, v1, e] = keys[i];
    if (t <= t1) { const [t0, v0] = keys[i - 1]; return lerp(v0, v1, (e || E.inOutCubic)(inv(t0, t1, t))); }
  }
  return keys[keys.length - 1][1];
}

// ---------- DOM ----------
function h(tag, cls, parent, html) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (html != null) el.innerHTML = html;
  if (parent) parent.appendChild(el);
  return el;
}
function place(el, x, y, w, hh) { el.style.left = x + 'px'; el.style.top = y + 'px'; if (w != null) el.style.width = w + 'px'; if (hh != null) el.style.height = hh + 'px'; return el; }
// transform + opacity in one call; skips identical writes
function tf(el, o) {
  const s = o.s ?? 1, sx = o.sx ?? s, sy = o.sy ?? s;
  const tr = `translate3d(${(o.x || 0).toFixed(2)}px,${(o.y || 0).toFixed(2)}px,0)` + (o.r ? ` rotate(${o.r.toFixed(3)}deg)` : '') +
    (o.rx ? ` rotateX(${o.rx.toFixed(3)}deg)` : '') + (o.ry ? ` rotateY(${o.ry.toFixed(3)}deg)` : '') +
    ((sx !== 1 || sy !== 1) ? ` scale(${sx.toFixed(4)},${sy.toFixed(4)})` : '');
  if (el._tr !== tr) { el.style.transform = tr; el._tr = tr; }
  const op = o.o == null ? 1 : clamp(o.o);
  if (el._op !== op) { el.style.opacity = op; el._op = op; }
  const vis = op > 0.001 && !o.hide;
  if (el._vis !== vis) { el.style.visibility = vis ? 'visible' : 'hidden'; el._vis = vis; }
  if (o.blur != null) { const f = o.blur > 0.05 ? `blur(${o.blur.toFixed(2)}px)` : 'none'; if (el._bl !== f) { el.style.filter = f; el._bl = f; } }
}
function show(el, on) { const v = on ? '' : 'none'; if (el._d !== v) { el.style.display = v; el._d = v; } }
function txt(el, s) { if (el._t !== s) { el.textContent = s; el._t = s; } }
function htm(el, s) { if (el._h !== s) { el.innerHTML = s; el._h = s; } }
const esc = s => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
// chars of a TL.typing() run that are on screen at t
const typed = (run, t) => { let n = 0; while (n < run.at.length && run.at[n] <= t) n++; return n; };
const words = s => s.split('\n').map(line => line.split(' ').map(w => `<span class="w"><span class="wi">${w}</span></span>`).join(' ')).join('<br>');

// ---------- logos (the repo's own files; one-colour marks are tinted white so they read on black) ----------
const LOGO_FILES = {
  ChatGPT: 'openai.svg', Claude: 'claude-color.svg', Gemini: 'gemini-color.svg', Perplexity: 'perplexity-color.svg',
  DeepSeek: 'deepseek-color.svg', Grok: 'grok.svg', Copilot: 'copilot-color.svg', Poe: 'poe-color.svg', Mistral: 'mistral-color.svg',
  'Claude Code': 'claudecode-color.svg', Codex: 'codex-color.svg', Cursor: 'cursor.svg', Windsurf: 'windsurf.svg',
  'VS Code': 'vscode.svg', 'Gemini CLI': 'gemini-color.svg', Antigravity: 'antigravity-color.svg', Zed: 'zedindustries.svg',
  OpenCode: 'opencode.svg', GitHub: 'github.svg', Docker: 'docker.svg',
};
const LOGO = {};
async function loadLogos() {
  await Promise.all(Object.entries(LOGO_FILES).map(async ([name, f]) => {
    let s = await (await fetch('/site/icons/' + f)).text();
    s = s.replace(/currentColor/g, '#F7F8FA');
    if (!/fill=/.test(s)) s = s.replace('<svg ', '<svg fill="#F7F8FA" ');
    LOGO[name] = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(s);
  }));
  const mark = await (await fetch('/assets/brand/mark.svg')).text();
  LOGO.mark = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(mark.replace('fill="currentColor"', 'fill="#F7F8FA"'));
}
// scenes are built before the logos finish loading, so a logo starts as a placeholder that __ready fills in
const logo = (name, cls = 'lg') => LOGO_FILES[name] ? `<img class="${cls}" data-logo="${name}" alt="">` : `<span class="${cls} blank"></span>`;

// ---------- Baton: the mark as a rig ----------
// mark.svg is a 46×85 capsule leaning 32° with two 8.6×15.5 capsule eyes. Rebuilt upright around its bottom point so it
// can lean, squash, look and blink; at lean 32 and rest it is the logo, pixel for pixel.
let _btn = 0;
function Baton(parent, opt = {}) {
  const id = 'bf' + (_btn++), color = opt.color || '#F7F8FA', eye = opt.eye || '#0A0A0B';
  const el = h('div', 'bt', parent);
  el.innerHTML = `<svg><defs><filter id="${id}" x="-80%" y="-40%" width="260%" height="180%" color-interpolation-filters="sRGB">
      <feGaussianBlur stdDeviation="0 0"/></filter></defs>
    <g filter="url(#${id})"><g class="rt">
      <rect x="-23" y="-85" width="46" height="85" rx="23" fill="${color}"/>
      <rect class="e" x="-8.55" y="-64.25" width="8.6" height="15.5" rx="4.3" fill="${eye}"/>
      <rect class="e" x="7.95" y="-64.25" width="8.6" height="15.5" rx="4.3" fill="${eye}"/>
    </g></g></svg>`;
  const rt = el.querySelector('.rt'), eyes = [...el.querySelectorAll('.e')], blurEl = el.querySelector('feGaussianBlur');
  const EC = [[-4.25, -56.5], [12.25, -56.5]];
  const st = {};
  return {
    el, st,
    set(o) {
      Object.assign(st, { x: 0, y: 0, size: 200, lean: 32, sx: 1, sy: 1, ex: 0, ey: 0, blink: 0, o: 1, blur: 0 }, o);
      const k = st.size / 85;
      tf(el, { x: st.x, y: st.y, o: st.o });
      const t = `scale(${k.toFixed(4)}) rotate(${st.lean.toFixed(3)}) scale(${st.sx.toFixed(4)} ${st.sy.toFixed(4)})`;
      if (rt._t !== t) { rt.setAttribute('transform', t); rt._t = t; }
      eyes.forEach((e, i) => {
        const [cx, cy] = EC[i], b = 1 - clamp(st.blink, 0, .92);
        const et = `translate(${(st.ex + cx).toFixed(3)} ${(st.ey + cy).toFixed(3)}) scale(1 ${b.toFixed(3)}) translate(${-cx} ${-cy})`;
        if (e._t !== et) { e.setAttribute('transform', et); e._t = et; }
      });
      const bl = `${st.blur.toFixed(2)} 0`;
      if (blurEl._t !== bl) { blurEl.setAttribute('stdDeviation', bl); blurEl._t = bl; }
    },
    // a point on the body (upright local units, origin at the bottom) → stage px
    pt(lx, ly) {
      const k = st.size / 85, a = st.lean * Math.PI / 180;
      const x = lx * st.sx * k, y = ly * st.sy * k;
      return [st.x + x * Math.cos(a) - y * Math.sin(a), st.y + x * Math.sin(a) + y * Math.cos(a)];
    },
  };
}
// run cycle: returns lean, bob, squash for a sprinting baton at time t
function runPose(t, speed = 1) {
  const ph = (t * 4.2 * speed) % 1, c = Math.abs(Math.sin(ph * Math.PI));
  return { lean: 38 + 3 * Math.sin(ph * Math.PI * 2), bob: -22 * c, sx: 1 + .06 * (1 - c), sy: 1 - .06 * (1 - c) };
}
const blinkAt = (t, t0, d = .16) => { const p = inv(t0, t0 + d, t); return p <= 0 || p >= 1 ? 0 : Math.sin(p * Math.PI); };

// ---------- caption ----------
function Caption(parent, label, text, cls = '') {
  const el = h('div', 'cap ' + cls, parent,
    `<div class="cap-l silk">${label ? '<i></i><span>' + label + '</span>' : ''}</div><div class="cap-t">${words(text)}</div>`);
  const ws = [...el.querySelectorAll('.wi')], rule = el.querySelector('.cap-l i'), lab = el.querySelector('.cap-l span');
  return {
    el,
    render(t, tIn, tOut) {
      const on = t > tIn - .05 && t < tOut + .45;
      show(el, on); if (!on) return;
      const q = E.inCubic(inv(tOut, tOut + .4, t));
      ws.forEach((w, i) => { const p = E.outExpo(inv(tIn + i * .035, tIn + i * .035 + .75, t)); tf(w, { y: (1 - p) * 72 - q * 26, o: (1 - q) * clamp(p * 3) }); });
      if (rule) { const p = E.outExpo(inv(tIn - .12, tIn + .5, t)); rule.style.transform = `scaleX(${(p * (1 - q)).toFixed(3)})`; tf(lab, { x: (1 - p) * -12, o: p * (1 - q) }); }
    },
  };
}

// ---------- chapter card: a manual page on a black plate ----------
const CHAPTERS = ['Capture', 'Remember', 'Recall', 'Baton', 'Forget', 'Yours'];
function Chapter(parent, c) {
  const el = h('div', 'chap', parent, `
    <div class="plate-edge"></div>
    <div class="screw" style="left:36px;top:36px"></div><div class="screw" style="right:36px;top:36px"></div>
    <div class="screw" style="left:36px;bottom:36px"></div><div class="screw" style="right:36px;bottom:36px"></div>
    <div class="runhead silk"><span>Mindbaton 0.1 · Owner's manual</span><span>${c.section}</span><span>${c.page}</span></div>
    <div class="num">${c.num}</div><div class="name silk">${c.name}</div><div class="line">${words(c.line)}</div>
    <div class="led"></div><div class="note silk">${c.note || ''}</div>
    <ol class="toc silk">${CHAPTERS.map((n, i) => `<li class="${String(i + 1).padStart(2, '0') === c.num ? 'cur' : ''}"><span>${String(i + 1).padStart(2, '0')}</span>${n}</li>`).join('')}</ol>`);
  const [edge] = el.getElementsByClassName('plate-edge'), rh = el.querySelector('.runhead'), num = el.querySelector('.num'),
    toc = [...el.querySelectorAll('.toc li')], name = el.querySelector('.name'), lineWs = [...el.querySelectorAll('.line .wi')], led = el.querySelector('.led'), note = el.querySelector('.note');
  const screws = [...el.querySelectorAll('.screw')];
  return {
    el,
    render(t, d) {  // t: seconds since the card began; d: its length
      const on = t >= 0 && t < d; show(el, on); if (!on) return;
      const out = E.inExpo(inv(d - .42, d, t));
      tf(el, { y: -out * H });
      const a = E.outExpo(inv(0, .6, t));
      tf(edge, { o: a, s: 1.015 - .015 * a });
      screws.forEach((s, i) => { const r = E.outBack(inv(.05 + i * .04, .45 + i * .04, t)); tf(s, { o: r, r: (1 - r) * -90 }); });
      rh.style.clipPath = `inset(0 ${(100 - 100 * E.outExpo(inv(.05, .7, t))).toFixed(2)}% 0 0)`;
      const pn = E.outExpo(inv(.02, .7, t));
      tf(num, { y: (1 - pn) * 140, o: clamp(pn * 2.5), s: 1.06 - .06 * pn });
      const pm = E.outExpo(inv(.14, .8, t));
      tf(name, { x: (1 - pm) * -60, o: pm });
      lineWs.forEach((w, i) => { const p = E.outExpo(inv(.3 + i * .045, 1.0 + i * .045, t)); tf(w, { y: (1 - p) * 80, o: clamp(p * 2) }); });
      led.classList.toggle('on', t > .34);
      tf(note, { o: E.outCubic(inv(.4, .9, t)) });
      toc.forEach((li, i) => { const p = E.outExpo(inv(.12 + i * .05, .7 + i * .05, t)); tf(li, { x: (1 - p) * 40, o: p }); });
    },
  };
}

// ---------- seven-segment digits (the site's amber counter) ----------
const SEG = { a: [5, 4, 35, 4, 'h'], g: [5, 36, 35, 36, 'h'], d: [5, 68, 35, 68, 'h'], f: [4, 5, 4, 35, 'v'], b: [36, 5, 36, 35, 'v'], e: [4, 37, 4, 67, 'v'], c: [36, 37, 36, 67, 'v'] };
const DIG = ['abcdef', 'bc', 'abged', 'abgcd', 'fgbc', 'afgcd', 'afgedc', 'abc', 'abcdefg', 'abcdfg'];
function segPoly([x1, y1, x2, y2, o]) {
  const w = 7, s = w / 2;
  return o === 'h' ? `${x1 + 1},${y1} ${x1 + 1 + s},${y1 - s} ${x2 - 1 - s},${y2 - s} ${x2 - 1},${y2} ${x2 - 1 - s},${y2 + s} ${x1 + 1 + s},${y1 + s}`
    : `${x1},${y1 + 1} ${x1 + s},${y1 + 1 + s} ${x2 + s},${y2 - 1 - s} ${x2},${y2 - 1} ${x2 - s},${y2 - 1 - s} ${x1 - s},${y1 + 1 + s}`;
}
function Segs(parent, n) {
  const el = h('div', 'segs', parent);
  const digs = Array.from({ length: n }, () => {
    const s = h('div', null, el, `<svg viewBox="-2 -2 44 76">${Object.entries(SEG).map(([k, v]) => `<polygon data-s="${k}" points="${segPoly(v)}"/>`).join('')}</svg>`);
    return [...s.querySelectorAll('polygon')];
  });
  return {
    el,
    set(str) {
      str = String(str).padStart(n, ' ');
      digs.forEach((ps, i) => { const ch = str[i], on = ch >= '0' && ch <= '9' ? DIG[+ch] : ''; ps.forEach(p => { const v = on.includes(p.dataset.s); if (p._v !== v) { p.classList.toggle('on', v); p._v = v; } }); });
    },
  };
}

const CURSOR = `<svg class="cursor" viewBox="0 0 34 46"><path d="M3 2 L3 36 L11.5 28.5 L17 42 L23 39.5 L17.5 26.5 L29 26.5 Z" fill="#fff" stroke="#0A0A0B" stroke-width="2.2" stroke-linejoin="round"/></svg>`;
const ICON = {
  search: `<svg viewBox="0 0 24 24" fill="none" stroke="#908E87" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/></svg>`,
  spark: `<svg viewBox="0 0 24 24" fill="none" stroke="#EEEEEC" stroke-width="1.7" stroke-linecap="round"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8"/></svg>`,
  up: `<svg viewBox="0 0 24 24" fill="none" stroke="#0A0A0B" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5.5 11.5L12 5l6.5 6.5"/></svg>`,
  people: `<svg viewBox="0 0 24 24" fill="none" stroke="#EEEEEC" stroke-width="1.6" stroke-linecap="round"><circle cx="9" cy="8" r="3.2"/><path d="M3.5 19c.6-3.2 2.8-5 5.5-5s4.9 1.8 5.5 5"/><circle cx="17" cy="9" r="2.4"/><path d="M16 14.2c2.4.1 4 1.7 4.5 4.3"/></svg>`,
  down: `<svg viewBox="0 0 24 24" fill="none" stroke="#EEEEEC" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11M7 10.5l5 5 5-5M5 20h14"/></svg>`,
  phone: `<svg viewBox="0 0 24 24" fill="none" stroke="#EEEEEC" stroke-width="1.6" stroke-linecap="round"><rect x="7" y="3" width="10" height="18" rx="2.5"/><path d="M11 18h2"/></svg>`,
  box: `<svg viewBox="0 0 24 24" fill="none" stroke="#EEEEEC" stroke-width="1.6" stroke-linejoin="round"><path d="M4 7.5L12 3l8 4.5v9L12 21l-8-4.5z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/></svg>`,
  warn: `<svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="#FF8FA3" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5M12 16.2v.3"/></svg>`,
};

// ---------- light and texture ----------
let AUR, GRAIN, FLASH;
function initGlobal(stage) {
  AUR = h('div', null, stage); AUR.id = 'aurora';
  const cols = [[229, 77, 46], [255, 178, 26], [233, 61, 130], [247, 107, 21]];
  AUR.glows = cols.map(([r, g, b], i) => {
    const d = h('div', 'glow', AUR);
    d.style.background = `radial-gradient(closest-side, rgba(${r},${g},${b},.55), rgba(${r},${g},${b},.2) 45%, rgba(${r},${g},${b},0) 74%)`;
    return d;
  });
  const vg = h('div', null, stage); vg.id = 'vig';
  FLASH = h('div', null, stage); FLASH.id = 'flash';
  GRAIN = h('div', null, stage); GRAIN.id = 'grain';
  const c = document.createElement('canvas'); c.width = c.height = 1024;
  const x = c.getContext('2d'), im = x.createImageData(1024, 1024), r = TL.rng(99);
  for (let i = 0; i < im.data.length; i += 4) { const v = 128 + (r() + r() + r() - 1.5) * 150; im.data[i] = im.data[i + 1] = im.data[i + 2] = clamp(v, 0, 255); im.data[i + 3] = 255; }
  x.putImageData(im, 0, 0);
  GRAIN.style.backgroundImage = `url(${c.toDataURL()})`; GRAIN.style.backgroundSize = '512px 512px';
}
// aurora level through the film (0 = off). It follows the app: bright on You, a wash elsewhere, off on the map.
const AUR_KEYS = [[0, 0], [7.5, .12], [7.6, 0], [11.9, 0], [12.4, .8], [15.8, .8], [16, .25], [31.4, .25], [31.8, .55], [35.6, .5], [36, .3],
  [45.8, .3], [46.2, .05], [48, .05], [48.2, .3], [68, .3], [69, .1], [73.9, .1], [74.1, .75], [76, .4], [80, .25], [81, .1], [86, .1],
  [87.6, .3], [101.8, .3], [102.2, .15], [105.8, .15], [106.2, .9], [111.5, .9], [112, 0]];
let FRAME = 0;
function renderGlobal(t, frame) {
  const lvl = kf(t, AUR_KEYS) * (1 + .22 * TL.T.kickEnv(t)), boost = FLASH_LVL(t);
  tf(AUR, { o: clamp(lvl + boost * .5) });
  const P = [[.12, 21, 0], [.4, 27, 1.3], [.66, 33, 2.1], [.9, 25, 3.7]];
  AUR.glows.forEach((g, i) => { const [cx, per, ph] = P[i]; tf(g, { x: cx * W + Math.sin(t * 2 * Math.PI / per + ph) * 140, y: Math.cos(t * 2 * Math.PI / (per * 1.3) + ph) * 60 - 40, s: 1 + .08 * Math.sin(t / per * 6 + ph) }); });
  const r = TL.rng(frame * 7919 + 13);
  GRAIN.style.backgroundPosition = `${Math.floor(r() * 512)}px ${Math.floor(r() * 512)}px`;
  tf(FLASH, { o: boost * .9 });
}
// white flashes on the two big impacts (the drop and the relay); kept brief and low
function FLASH_LVL(t) { return Math.max(.28 * Math.exp(-Math.max(0, t - 8.0) / .09) * (t >= 8.0 ? 1 : 0), .35 * Math.exp(-Math.max(0, t - 74.0) / .1) * (t >= 74.0 ? 1 : 0)); }
