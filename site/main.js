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
