// Mindbaton landing: the front panel demo, the copy keys and the mode replays. No dependencies.
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const reduce = matchMedia('(prefers-reduced-motion: reduce)');
const wait = ms => new Promise(r => setTimeout(r, reduce.matches ? 0 : ms));
const status = $('#status');
const say = t => { status.textContent = ''; setTimeout(() => { status.textContent = t; }, 60); };

// ── copy keys ───────────────────────────────────────────────
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-copy]');
  if (!b) return;
  const src = $(b.dataset.copy), label = $('[data-label]', b);
  try { await navigator.clipboard.writeText(src.textContent); }
  catch { const r = document.createRange(); r.selectNodeContents(src); getSelection().removeAllRanges(); getSelection().addRange(r); document.execCommand('copy'); }
  label.dataset.was ??= label.textContent;
  label.textContent = 'Copied';
  b.classList.add('lit');
  say('Copied to the clipboard.');
  clearTimeout(b.t);
  b.t = setTimeout(() => { label.textContent = label.dataset.was; b.classList.remove('lit'); }, 1800);
});

// ── the panel ───────────────────────────────────────────────
// Every line below is from demo.py: Maya Haddad and her chats are made up.
const SAID = {
  'ChatGPT': ['I have a cat named Miso.', 'Relocating to Lisbon'],
  'Claude': ['I use a MacBook Air M3 with an external 27 inch monitor', 'Desk setup'],
  'Gemini': ["I'm vegetarian.", 'Portuguese café phrases'],
  'Perplexity': ['I want to run a half marathon under 1:55 by March', 'Lisbon half marathon'],
  'Claude Code': ['use TypeScript strict mode, I prefer server actions over API routes', 'Scaffold Pantry with Next.js and Supabase'],
  'Cursor': ['I use pnpm, not npm — update the scripts and the README', 'Pantry shopping list by aisle'],
};
const STREAM = [
  ['Gemini', "I'm vegetarian."], ['ChatGPT', 'I prefer Linear over Jira for tracking design work'], ['Cursor', 'I use pnpm, not npm'],
  ['Perplexity', 'I use Strava to track every run.'], ['Claude', 'I prefer fewer modes and bigger touch targets over a dense UI'],
  ['Gemini', 'I moved to Lisbon last weekend, the flat is in Alcântara'], ['Claude Code', 'use TypeScript strict mode'],
  ['ChatGPT', 'I love specialty coffee, usually an oat flat white'], ['Claude', 'I use Raycast and the Arc browser every day'],
];
const jacks = Object.fromEntries($$('.jack').map(j => [j.dataset.ai, j]));
const stream = $('#stream'), src = $('.src', stream), txt = $('.txt', stream);
const count = $('#memcount'), log = $('#log'), chan = $('#chan'), form = $('#tell'), input = $('#fact');
const baton = $('#baton'), bar = $('.hold i', baton), help = $('#baton-help');
const receipt = $('#receipt'), paper = $('#paper'), tear = $('#tear'), rbtns = $('#rbtns'), screen = $('.screen'), claude = jacks['Claude'];
const PACK = $('#pack-hero').content.textContent;
const START = { chan: chan.textContent, log: log.innerHTML, help: help.textContent, ph: input.placeholder };
let stage = 0, fact = '', frozen = null, tick = 0, memories = 67;

const blink = j => { j.classList.remove('blink'); void j.offsetWidth; j.classList.add('blink'); };
const show = (ai, text, hold) => { src.textContent = ai; txt.textContent = text; stream.classList.toggle('frozen', !!hold); };
// Seven-segment counter: lit segments in amber, unlit ones ghosted, as on a real LED display. Segments a–g, bit 0 = a.
const DIGIT = { ' ': 0, 0: 0x3f, 1: 0x06, 2: 0x5b, 3: 0x4f, 4: 0x66, 5: 0x6d, 6: 0x7d, 7: 0x07, 8: 0x7f, 9: 0x6f };
const H = (y, a, b) => `${a},${y} ${a + 2},${y - 2} ${b - 2},${y - 2} ${b},${y} ${b - 2},${y + 2} ${a + 2},${y + 2}`;
const V = (x, a, b) => `${x},${a} ${x + 2},${a + 2} ${x + 2},${b - 2} ${x},${b} ${x - 2},${b - 2} ${x - 2},${a + 2}`;
const SEGS = [H(2, 3, 19), V(20, 3, 19), V(20, 21, 37), H(38, 3, 19), V(2, 21, 37), V(2, 3, 19), H(20, 3, 19)];
const seg = el => {
  const s = el.dataset.seg;
  el.innerHTML = `<svg class="seg" viewBox="-6 0 ${s.length * 28 - 2} 41" aria-hidden="true">${[...s].map((c, i) =>
    `<g transform="translate(${i * 28} 0) skewX(-6)">${SEGS.map((p, k) => `<polygon points="${p}"${DIGIT[c] >> k & 1 ? ' class="on"' : ''}/>`).join('')}</g>`).join('')}</svg><span class="vh">${s.trim()}</span>`;
};
$$('[data-seg]').forEach(seg);
const setCount = n => { memories = n; count.dataset.seg = String(n).padStart(4, '0'); seg(count); };
const line = (who, text, cls) => {
  const li = document.createElement('li');
  if (who) { const b = document.createElement('b'); b.textContent = who; li.append(b); }
  li.append(text);
  if (cls) li.className = cls;
  log.append(li);
};

// Nothing on the panel moves unless it is data: the stream shows sample lines landing, each blinking its AI's light.
setInterval(() => {
  if (frozen || reduce.matches || document.hidden || stage) return;
  const [ai, t] = STREAM[tick++ % STREAM.length];
  show(ai, t);
  blink(jacks[ai]);
}, 2600);

const freeze = j => {
  frozen = j;
  const [t, chat] = SAID[j.dataset.ai];
  show(j.dataset.ai, `${t} · said in “${chat}”`, true);
};
const thaw = j => { if (frozen === j) { frozen = null; stream.classList.remove('frozen'); } };
for (const j of Object.values(jacks)) {
  j.addEventListener('pointerenter', () => freeze(j));
  j.addEventListener('pointerleave', () => thaw(j));
  j.addEventListener('focus', () => freeze(j));
  j.addEventListener('blur', () => thaw(j));
  j.addEventListener('click', () => {
    if (stage === 3 && j === claude) deliver();
    else if (stage === 3) say('This demo passes the baton to Claude. In Mindbaton you pick any AI.');
    else freeze(j);
  });
}

// 1 · tell ChatGPT something → every light comes on → ChatGPT's chat fills up
form.addEventListener('submit', async e => {
  e.preventDefault();
  if (stage) return;
  fact = input.value.trim();
  if (!fact) {
    input.placeholder = 'Type something first, like: I only drink oat milk';
    input.classList.add('nudge');
    input.focus();
    return say('Type something about you first, then press Send.');
  }
  stage = 1;
  input.classList.remove('nudge');
  input.value = '';
  input.disabled = true;
  line('Me', fact);
  show('ChatGPT', fact, true);
  blink(jacks.ChatGPT);
  jacks.ChatGPT.classList.add('on');
  setCount(memories + 1);
  await wait(700);
  for (const ai of ['Claude', 'Gemini', 'Perplexity', 'Claude Code', 'Cursor']) { jacks[ai].classList.add('on'); await wait(110); }
  say('Saved on this computer. Claude, Gemini, Perplexity, Claude Code and Cursor can all recall it now.');
  await wait(800);
  for (const seg of $$('.meter i', jacks.ChatGPT)) { seg.classList.add('f'); await wait(70); }
  jacks.ChatGPT.classList.add('is-full');
  line('ChatGPT', 'This conversation reached its maximum length. Start a new chat to continue.');
  baton.classList.add('armed');
  help.textContent = 'ChatGPT is full. Hold BATON to print the hand-off pack.';
  say("ChatGPT's chat is full. Hold the Baton key, or press Enter on it, to print a hand-off pack.");
  stage = 2;
});

// 2 · hold BATON → the receipt prints the real pack
let holding = null;
const nudge = () => {
  const t = stage < 2 ? 'Nothing to pass yet. Tell ChatGPT something first.' : stage === 3 ? 'The pack is out. Drag it onto Claude, or press Feed to Claude.' : 'Done. Press Run it again to start over.';
  help.textContent = t;
  say(t);
};
baton.addEventListener('contextmenu', e => e.preventDefault());
baton.addEventListener('pointerdown', e => {
  if (e.button) return;
  if (stage !== 2) return nudge();
  baton.setPointerCapture(e.pointerId);
  baton.classList.add('down');
  holding = bar.animate([{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], { duration: reduce.matches ? 1 : 900, easing: 'steps(12, end)', fill: 'forwards' });
  holding.onfinish = () => { holding = null; baton.classList.remove('down'); print(); };
});
const release = () => {
  baton.classList.remove('down');
  if (!holding) return;
  holding.cancel();
  holding = null;
  help.textContent = 'Keep holding until the bar fills. Or press Enter.';
};
baton.addEventListener('pointerup', release);
baton.addEventListener('pointercancel', release);
baton.addEventListener('click', e => { if (e.detail === 0) stage === 2 ? print() : nudge(); });  // keyboard and assistive tech

async function print() {
  if (stage !== 2) return;
  stage = 3;
  baton.classList.remove('armed');
  bar.getAnimations().forEach(a => a.cancel());
  const text = PACK.replace('@@FACT@@', fact);
  $('#ptok').textContent = Math.ceil(text.length / 4);  // handoff.py counts prose at 4 characters a token
  paper.textContent = '';
  receipt.hidden = false;
  rbtns.hidden = false;
  receipt.style.translate = '';
  help.textContent = 'Printed. Now drag the pack onto Claude.';
  if (reduce.matches) paper.textContent = text;
  else for (const l of text.split('\n')) {
    paper.textContent += l + '\n';
    paper.scrollTop = paper.scrollHeight;
    if (l) await wait(26);
  }
  paper.scrollTop = 0;
  claude.classList.add('target');
  say(`Hand-off pack printed, about ${$('#ptok').textContent} tokens. Drag it onto the Claude socket, or press Feed to Claude.`);
}

// 3 · drag the receipt onto Claude (or press Feed to Claude, or tap Claude's socket)
const over = e => { const r = claude.getBoundingClientRect(); return e.clientX > r.left - 16 && e.clientX < r.right + 16 && e.clientY > r.top - 16 && e.clientY < r.bottom + 16; };
tear.addEventListener('pointerdown', e => {
  if (stage !== 3) return;
  tear.setPointerCapture(e.pointerId);
  const x0 = e.clientX, y0 = e.clientY;
  receipt.classList.add('dragging');
  const move = ev => { receipt.style.translate = `${ev.clientX - x0}px ${ev.clientY - y0}px`; claude.classList.toggle('over', over(ev)); };
  const up = ev => {
    tear.removeEventListener('pointermove', move);
    tear.removeEventListener('pointerup', up);
    tear.removeEventListener('pointercancel', up);
    receipt.classList.remove('dragging');
    if (ev.type === 'pointerup' && over(ev)) return deliver();
    claude.classList.remove('over');
    receipt.animate([{ translate: receipt.style.translate || '0 0' }, { translate: '0 0' }], { duration: reduce.matches ? 0 : 260, easing: 'cubic-bezier(.16,1,.3,1)' });
    receipt.style.translate = '';
  };
  tear.addEventListener('pointermove', move);
  tear.addEventListener('pointerup', up);
  tear.addEventListener('pointercancel', up);
});
$('#feed').addEventListener('click', () => deliver());

async function deliver() {
  if (stage !== 3) return;
  stage = 4;
  claude.classList.remove('target', 'over');
  const a = receipt.getBoundingClientRect(), b = claude.querySelector('.hole').getBoundingClientRect();
  const [tx, ty] = (receipt.style.translate || '0px 0px').split(' ').map(parseFloat);
  const dx = b.left + b.width / 2 - (a.left + a.width / 2) + (tx || 0), dy = b.top + b.height / 2 - (a.top + 20) + (ty || 0);
  await receipt.animate([{ translate: `${tx || 0}px ${ty || 0}px`, scale: 1, opacity: 1 }, { translate: `${dx}px ${dy}px`, scale: .08, opacity: 0 }],
    { duration: reduce.matches ? 0 : 480, easing: 'cubic-bezier(.55,0,.8,.2)' }).finished;
  receipt.hidden = true;
  rbtns.hidden = true;
  receipt.style.translate = '';
  blink(claude);
  chan.textContent = 'CH 2 · Claude · new chat, started from the pack · demo';
  log.replaceChildren();
  form.hidden = true;
  screen.classList.add('passed');
  screen.scrollIntoView({ block: 'nearest', behavior: reduce.matches ? 'auto' : 'smooth' });
  line('Me', `[mindbaton handoff] … ${$('#ptok').textContent} tokens … [/mindbaton handoff]`);
  await wait(500);
  line('Claude', `Picking up from ChatGPT. Noted: “${fact}”.`);
  await wait(700);
  line('Claude', "For you and Miso, with a flat ride to Cais do Sodré, I'd start in Alcântara: the river bike lane runs through it, and landlords there tend to be more open to pets. Want a short list of streets to check on Idealista?");
  await wait(300);
  line('', 'Demo reply written for this page. With Mindbaton, the pack opens a new Claude chat and Claude answers for real.', 'note');
  const again = document.createElement('button');
  again.type = 'button';
  again.className = 'key key-small key-white';
  again.textContent = 'Run it again';
  again.addEventListener('click', reset);
  log.after(again);
  help.textContent = 'Passed. Claude carried on.';
  say('Claude picked up the pack and carried on the chat.');
}

function reset(e) {
  e.currentTarget.remove();
  stage = 0;
  for (const j of Object.values(jacks)) j.classList.remove('on', 'is-full', 'blink', 'target', 'over');
  $$('.meter i').forEach(s => s.classList.remove('f'));
  setCount(67);
  chan.textContent = START.chan;
  log.innerHTML = START.log;
  help.textContent = START.help;
  input.placeholder = START.ph;
  screen.classList.remove('passed');
  form.hidden = false;
  input.disabled = false;
  input.focus();
}

// ── modes 01–04: replay on the key, on arrival by link, and once when scrolled to ──
async function play(mode) {
  const lcd = $('.lcd', mode);
  if (!lcd || lcd.busy || reduce.matches) return;
  lcd.busy = true;
  const items = [...lcd.children];
  lcd.style.minHeight = lcd.offsetHeight + 'px';
  items.forEach(li => { li.style.visibility = 'hidden'; });
  for (const li of items) { await wait(420); li.style.visibility = ''; }
  lcd.busy = false;
}
for (const m of $$('.mode')) $('.replay', m).addEventListener('click', () => play(m));
const fromHash = () => { const m = document.getElementById(decodeURIComponent(location.hash.slice(1))); if (m?.classList.contains('mode')) play(m); };
addEventListener('hashchange', fromHash);
fromHash();
const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { io.unobserve(e.target); play(e.target); } }), { threshold: .6 });
$$('.mode').forEach(m => io.observe(m));

// ── the two pinned scroll stories: Parts (the exploded view) and New (the horizontal rail) ──
// Pinned only when motion is welcome and the screen is tall enough; otherwise both stay plain sections (the static
// drawing; a native snap scroller). Where scroll-driven animations exist (.sda) CSS moves the plates and the rail off the
// main thread and this loop only sets the steps; elsewhere it writes the same curves itself. Scrubbed, never eased behind.
const pinMQ = matchMedia('(prefers-reduced-motion: no-preference) and (min-height: 600px)');
const sda = CSS.supports('animation-timeline: view()');
const clamp01 = x => Math.min(1, Math.max(0, x)), smooth = t => t * t * (3 - 2 * t), lerp = (a, b, t) => a + (b - a) * t;
const prog = el => { const r = el.getBoundingClientRect(); return clamp01(-r.top / (r.height - innerHeight)); };
const pinned = el => el.classList.contains('pin');
const unstyle = els => els.forEach(e => { e.style.translate = e.style.scale = e.style.opacity = ''; });

// Parts: p 0–.12 lifts the plates apart, .12–.88 steps through parts 1–8 while the stack drifts with parallax, .88–1 closes it.
const E = .12, R = .88, SW = (R - E) / 8, PART_LAYER = [0, 0, 1, 1, 2, 2, 3, 4];
const parts = $('#parts'), ptext = $('.parts-text'), isos = $$('.xpl .iso'), items = $$('.partlist li'), cos = $$('.xpl .co');
const L = $$('.xpl .layer').map(g => ({ g, l: +g.dataset.l, d: +g.dataset.d, co: g.classList.contains('callout') }));
let amt = {}, lastP = -1, step = -1;
const stackAt = (p, v) => p < E ? [lerp(v.d, v.a, smooth(p / E)), lerp(1, v.s, smooth(p / E)), lerp(v.o0, v.o, smooth(p / E))]
  : p > R ? [lerp(-v.a, v.d, smooth((p - R) / (1 - R))), lerp(v.s, 1, smooth((p - R) / (1 - R))), lerp(v.o, v.o0, smooth((p - R) / (1 - R)))]
  : [lerp(v.a, -v.a, (p - E) / (R - E)), v.s, v.o];  // the same curve as @keyframes stack in style.css
function partsFrame() {
  const p = prog(parts);
  if (p === lastP) return;
  lastP = p;
  if (!sda) {
    for (const v of L) { const [y, s, o] = stackAt(p, v); Object.assign(v.g.style, { translate: `0 ${y}px`, scale: s, opacity: o }); }
    for (const t of isos) t.style.translate = `0 ${amt.fi * (1 - 2 * clamp01((p - E) / (R - E)))}px`;
    ptext.style.translate = `0 ${amt.ft * (1 - 2 * p)}px`;
  }
  const n = p < E ? 0 : p >= R ? 9 : Math.min(8, Math.floor((p - E) / SW) + 1);  // 0 closed, 1–8 a part, 9 closed again
  if (n === step) return;
  step = parts.dataset.step = n;
  const a = n % 9 ? PART_LAYER[n - 1] : -1;  // the plate being shown; the ones above it lift out of the way
  items.forEach((li, i) => li.classList.toggle('on', i + 1 === n));
  cos.forEach(c => c.classList.toggle('on', +c.dataset.n === n));
  for (const v of L) { v.g.classList.toggle('dim', a >= 0 && v.l !== a); v.g.classList.toggle('above', v.l < a); }
}
const partY = n => { const r = parts.getBoundingClientRect(); return r.top + scrollY + (E + SW * (n - .5)) * (r.height - innerHeight); };
document.addEventListener('click', e => {  // the Parts chips on the sheets land on their step, not on the closed box
  const a = e.target.closest('a[href^="#part-"]');
  if (!a || !pinned(parts)) return;
  e.preventDefault();
  history.pushState(null, '', a.hash);
  scrollTo({ top: partY(+a.hash.slice(6)) });
});
const toPart = () => { const n = +/^#part-([1-8])$/.exec(location.hash)?.[1]; if (n && pinned(parts)) scrollTo({ top: partY(n), behavior: 'instant' }); };

// New: pinned, 1px of scroll slides the rail 1px (the section is 100svh + that distance tall); the title drifts at .3.
const news = $('#new'), rail = $('#rail'), cards = $$('.card', rail), title = $('.new-title');
const rnum = $('#rnum'), rbar = $('#rbar'), [prev, next] = $$('.rbtn');
let geo = [], edge = 0, railW = 0, maxX = 0, lastX = -1, cur = -1;
const cardX = k => {  // the rail offset that shows card k: centred when pinned (where the parallax peaks), else at the snap edge
  const [l, w] = geo[k];
  return pinned(news) ? Math.max(0, Math.min(maxX, l + w / 2 - railW / 2)) : l + w <= railW ? 0 : l - edge;
};
function newsFrame() {
  const pin = pinned(news), x = pin ? prog(news) * maxX : rail.scrollLeft, m = pin ? maxX : rail.scrollWidth - rail.clientWidth, W = railW;
  if (x === lastX) return;
  lastX = x;
  if (pin && !sda) { rail.style.translate = `${-x}px 0`; title.style.translate = `${-.3 * x}px 0`; }
  if (!reduce.matches) {
    const g = innerWidth < 700 ? .5 : 1;  // gentler on phones
    geo.forEach(([l, w], i) => {
      const d = g * Math.max(-1, Math.min(1, (l + w / 2 - x - W / 2) / (W / 2)));  // -1 left edge … 0 centre … 1 right edge
      cards[i].style.setProperty('--dx', d.toFixed(3));
      cards[i].style.setProperty('--ax', Math.abs(d).toFixed(3));
    });
  }
  rbar.style.scale = `${m > 0 ? clamp01(x / m) : 0} 1`;
  const i = m > 2 && x >= m - 2 ? cards.length - 1 : geo.reduce((b, _, k) => Math.abs(cardX(k) - x) < Math.abs(cardX(b) - x) ? k : b, 0);
  if (i === cur) return;
  cur = i;
  rnum.textContent = String(i + 1).padStart(2, '0');
  prev.setAttribute('aria-disabled', i === 0);
  next.setAttribute('aria-disabled', i === cards.length - 1);
}
function goTo(k) {
  k = Math.max(0, Math.min(cards.length - 1, k));
  if (pinned(news)) scrollTo({ top: news.getBoundingClientRect().top + scrollY + Math.min(cardX(k), maxX) });
  else rail.scrollTo({ left: cardX(k), behavior: reduce.matches ? 'auto' : 'smooth' });
}
$$('.rbtn').forEach(b => b.addEventListener('click', () => { if (b.getAttribute('aria-disabled') !== 'true') goTo(cur + +b.dataset.go); }));
rail.addEventListener('focusin', e => { const k = cards.indexOf(e.target); if (k >= 0 && e.target.matches(':focus-visible')) goTo(k); });  // Tab never lands off-screen
rail.addEventListener('keydown', e => {
  const k = cards.indexOf(e.target), d = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
  if (k < 0 || !d || !cards[k + d]) return;
  e.preventDefault();
  cards[k + d].focus({ preventScroll: true });
});

function setPin() {
  const on = pinMQ.matches, small = innerWidth < 700;
  parts.classList.toggle('pin', on);
  news.classList.toggle('pin', on && innerWidth >= 900 && innerHeight >= 720);  // a card and the title need that much height
  for (const s of [parts, news]) s.classList.toggle('sda', sda && pinned(s));
  // Parts parallax: depth k = 1 for the top plate (nearest: drifts most, full size) … 0 for the computer (smaller, dimmer).
  amt = small ? { A: 10, S: .02, O: .1, fi: 2, ft: 0 } : { A: 20, S: .04, O: .2, fi: 5, ft: 14 };
  for (const v of L) {
    const k = (4 - v.l) / 4, [ox, oy] = v.g.getAttribute('transform').match(/[\d.]+/g);
    Object.assign(v, { a: amt.A * k * (v.co ? .8 : 1), s: 1 - amt.S * (1 - k), o: v.co ? 1 : 1 - amt.O * (1 - k), o0: v.co ? 0 : 1 });
    v.g.style.cssText = `--y0:${v.d}px;--ya:${v.a}px;--yb:${-v.a}px;--s:${v.s};--o:${v.o};--o0:${v.o0};transform-origin:${ox}px ${oy}px`;
  }
  parts.style.setProperty('--fi', amt.fi + 'px');
  parts.style.setProperty('--ft', amt.ft + 'px');
  unstyle([ptext, rail, title, ...isos]);
  cards.forEach(c => c.removeAttribute('style'));
  geo = cards.map(c => [c.offsetLeft, c.offsetWidth]);
  edge = rail.firstElementChild.offsetLeft;
  railW = rail.clientWidth;
  const [l, w] = geo.at(-1);
  maxX = pinned(news) ? Math.max(0, l + w + edge - rail.clientWidth) : 0;
  news.style.setProperty('--max', maxX);
  lastP = lastX = step = cur = -1;
  frame();
}
let raf = 0;
const frame = () => { raf = 0; if (pinned(parts)) partsFrame(); newsFrame(); };
const queue = () => { raf ||= requestAnimationFrame(frame); };
addEventListener('scroll', queue, { passive: true });
rail.addEventListener('scroll', queue, { passive: true });
addEventListener('resize', setPin);
pinMQ.addEventListener('change', setPin);
addEventListener('hashchange', toPart);
addEventListener('load', toPart);
setPin();
