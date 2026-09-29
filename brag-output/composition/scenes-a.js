// Scenes 1–3: the wall of you, Baton, 01 Capture.
const T = TL.T;
const SHOT = f => '../work/real/' + f;
const IMGS = [];
function shotImg(parent, file, cls = 'shot') { const i = h('img', cls, parent); i.src = SHOT(file); IMGS.push(i); return i; }
const SCENES = [];
function Scene(name, build) {
  const [t0, t1] = TL.S[name], el = h('div', 'scene', STAGE);
  const s = { name, t0, t1, el };
  s.render = build(el, s);
  SCENES.push(s);
}
const AIS = ['ChatGPT', 'Claude', 'Gemini', 'Perplexity', 'DeepSeek', 'Grok', 'Copilot', 'Poe', 'Mistral', 'Claude Code', 'Codex',
  'Cursor', 'Windsurf', 'VS Code', 'Gemini CLI', 'Antigravity', 'Zed', 'OpenCode'];

// ============ 1 · the wall of you ============
Scene('hook', el => {
  const world = h('div', 'abs', el);
  const N = 13, C = 6, PX = 384, PY = 224, r = TL.rng(5);
  const HELLO = T.hookType.text;
  const zoomAt = T.hookZoom, zoomS = [4.3, 1.85, 1.16, .8, .58, .44];
  const cells = [];
  for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
    const d = Math.max(Math.abs(i - C), Math.abs(j - C));
    const ai = d === 0 ? 'ChatGPT' : AIS[Math.floor(r() * AIS.length)];
    const c = h('div', 'cell', world, `<div class="ch silk">${logo(ai, '')}<span>${ai}</span></div><div class="ct"></div>`);
    place(c, (i - C) * PX - 180, (j - C) * PY - 100);
    // a ring starts typing when the camera first reveals it
    const reveal = d === 0 ? 0 : zoomAt[Math.min(d, zoomAt.length) - 1] - .1 + r() * .35;
    const run = d === 0 ? T.hookType : TL.typing(HELLO, reveal, 15 + r() * 12, 100 + i * N + j);
    cells.push({ c, ct: c.querySelector('.ct'), run, d, erase: T.hookErase + r() * .3 + d * .015, rate: 70 + r() * 40 });
  }
  const dim = h('div', 'fill', el); dim.style.background = 'radial-gradient(ellipse 70% 60% at 50% 50%, rgba(10,10,11,.86), rgba(10,10,11,.6))';
  const l1 = h('div', 'abs', el, words('Every AI forgets you'));
  Object.assign(l1.style, { width: '1920px', top: '392px', textAlign: 'center', fontSize: '124px', fontWeight: 650, letterSpacing: '-.035em' });
  const l2 = h('div', 'abs', el, words('the moment you open another one.'));
  Object.assign(l2.style, { width: '1920px', top: '560px', textAlign: 'center', fontSize: '66px', fontWeight: 500, letterSpacing: '-.025em', color: 'var(--fg2)' });
  const w1 = [...l1.querySelectorAll('.wi')], w2 = [...l2.querySelectorAll('.wi')];
  return (lt, t) => {
    let s = zoomS[0];
    zoomAt.forEach((z, k) => { s = lerp(s, zoomS[k + 1], E.snap(inv(z - .02, z + .42, t))); });
    s *= (1 + .12 * E.inOutCubic(inv(0, 2.02, t)) * (1 - inv(1.98, 2.02, t))) * (1 - .05 * inv(4.4, 7.6, t));
    // open on the typed line itself, then let the grid take the frame
    const f = 1 - E.snap(inv(zoomAt[0] - .02, zoomAt[0] + .42, t));
    tf(world, { x: W / 2 - (-40 * f) * s, y: H / 2 + 8 - (-20 * f) * s, s });
    for (const q of cells) {
      if (q.d > 0 && s * (q.d - .5) * PX > W / 2 + 40) { show(q.c, false); continue; }
      show(q.c, true);
      let n = typed(q.run, t);
      if (t > q.erase) n = Math.max(0, n - Math.floor((t - q.erase) * q.rate));
      const typing = t >= q.run.t0 && t < q.run.end + .6 && t < q.erase;
      const blink = (t * 2) % 1 < .6;
      htm(q.ct, esc(HELLO.slice(0, n)) + ((typing || (q.d === 0 && t < q.run.t0)) && (n < HELLO.length ? true : blink) ? '<span class="caret"></span>' : ''));
    }
    tf(dim, { o: .92 * E.outCubic(inv(4.3, 4.9, t)) });
    w1.forEach((w, i) => { const p = E.outExpo(inv(T.hookLine1 + i * .06, T.hookLine1 + i * .06 + .8, t)); tf(w, { y: (1 - p) * 140, o: clamp(p * 2) }); });
    w2.forEach((w, i) => { const p = E.outExpo(inv(T.hookLine2 + i * .05, T.hookLine2 + i * .05 + .8, t)); tf(w, { y: (1 - p) * 90, o: clamp(p * 2) }); });
    tf(el, { o: 1 - inv(T.hookBlack - .06, T.hookBlack, t) });
  };
});

// ============ 2 · Baton ============
Scene('reveal', el => {
  const sh = h('div', 'shadow-ell', el);
  const b = Baton(el);
  const l1 = h('div', 'abs', el, words('Tell one AI.')), l2 = h('div', 'abs', el, words('Every AI knows.'));
  for (const [l, y] of [[l1, 596], [l2, 736]]) Object.assign(l.style, { width: '1920px', top: y + 'px', textAlign: 'center', fontSize: '118px', fontWeight: 650, letterSpacing: '-.04em' });
  l2.style.color = 'var(--fg2)';
  const w1 = [...l1.querySelectorAll('.wi')], w2 = [...l2.querySelectorAll('.wi')];
  const lock = h('div', 'fill', el);
  const wm = h('div', 'abs wordmark', lock, 'Mindbaton'); Object.assign(wm.style, { left: '0px', top: '404px', fontSize: '136px' });
  let LX = 0;  // lockup layout: Baton + 44px + wordmark, centred as one
  const sub = h('div', 'abs', lock, words('One private memory for every AI you use.'));
  Object.assign(sub.style, { width: '1920px', top: '600px', textAlign: 'center', fontSize: '50px', fontWeight: 500, letterSpacing: '-.02em', color: 'var(--fg2)' });
  const ws = [...sub.querySelectorAll('.wi')];
  const letters = wm; let lettersSplit = false;
  return (lt, t) => {
    if (!lettersSplit) {
      letters.innerHTML = [...'Mindbaton'].map(c => `<span class="w"><span class="wi">${c}</span></span>`).join(''); lettersSplit = true;
      const ww = letters.getBoundingClientRect().width * 1920 / STAGE.getBoundingClientRect().width, bw = 165 * 168 / 168;
      LX = (1920 - (bw + 44 + ww)) / 2; letters.style.left = (LX + bw + 44).toFixed(1) + 'px';
    }
    const lw = [...letters.querySelectorAll('.wi')];
    // --- Baton: fall, land, squash, blink, lean ---
    const FLOOR = 540;
    let y = FLOOR, sx = 1, sy = 1, x = 960, size = 300, lean = 0, ex = 0, ey = 0, blur = 0;
    if (t < T.land) { const p = E.inQuad(inv(T.fall, T.land, t)); y = lerp(-120, FLOOR, p); sy = 1.12; sx = .92; }
    else { const dt = t - T.land, q = .3 * Math.exp(-dt * 7.5) * Math.cos(dt * 2 * Math.PI * 2.6); sx = 1 + q; sy = 1 - q; }
    lean = kf(t, [[T.lean, 0], [T.lean + .2, -9, E.outQuad], [T.lean + .55, 32, E.outBack]]);
    ey = kf(t, [[T.tell1, 0], [T.tell1 + .15, 3], [T.tell2 + .3, 3], [T.tell2 + .5, 0]]);
    // lockup: shrink beside the wordmark
    const pl = E.snap(inv(T.lockup, T.lockup + .7, t));
    x = lerp(960, LX + 38, pl); size = lerp(300, 168, pl); y = lerp(FLOOR, 520, pl);
    // run off through the wordmark
    let run = inv(T.runOff, T.runOff + .75, t);
    if (run > 0) {
      const rp = runPose(t); lean = lerp(32, rp.lean, clamp(run * 4)); y += rp.bob * clamp(run * 4); sx *= rp.sx; sy *= rp.sy;
      x = lerp(LX + 38, 2300, E.inQuad(run)); blur = 14 * clamp(run * 3);
      const pre = E.outQuad(inv(T.runOff - .25, T.runOff, t)); lean -= 10 * pre * (1 - clamp(run * 5));
    }
    const blk = blinkAt(t, T.blink1) + blinkAt(t, T.lockup + 1.8) + blinkAt(t, T.lockup + 2.02);
    b.set({ x, y, size, lean, sx, sy, ex, ey, blink: blk, blur, o: t < T.fall ? 0 : 1 });
    tf(sh, { x, y: y + 4 - (y - FLOOR) * 0, s: (size / 300) * (t < T.land ? lerp(.3, 1, inv(T.fall, T.land, t)) : 1), o: (t < T.fall ? 0 : .9) * (1 - pl) });
    b.el.style.filter = `drop-shadow(0 0 ${(30 + 50 * TL.T.kickEnv(t)).toFixed(1)}px rgba(255,178,26,${(.18 + .22 * Math.exp(-Math.max(0, t - T.land) / .5)).toFixed(3)}))`;
    // --- words ---
    const out1 = E.inCubic(inv(T.lockup - .05, T.lockup + .3, t));
    w1.forEach((w, i) => { const p = E.outExpo(inv(T.tell1 + i * .07, T.tell1 + i * .07 + .8, t)); tf(w, { y: (1 - p) * 140 - out1 * 40, o: clamp(p * 2) * (1 - out1) }); });
    w2.forEach((w, i) => { const p = E.outExpo(inv(T.tell2 + i * .07, T.tell2 + i * .07 + .8, t)); tf(w, { y: (1 - p) * 140 - out1 * 40, o: clamp(p * 2) * (1 - out1) }); });
    lw.forEach((w, i) => { const p = E.outExpo(inv(T.lockup + .25 + i * .035, T.lockup + 1.0 + i * .035, t)); tf(w, { y: (1 - p) * 170, o: clamp(p * 3) }); });
    ws.forEach((w, i) => { const p = E.outExpo(inv(T.sub + i * .04, T.sub + .8 + i * .04, t)); tf(w, { y: (1 - p) * 70, o: clamp(p * 2) }); });
    // Baton wipes the lockup away as it runs through it
    const cut = run > 0 ? clamp(x - 20, 0, W) : 0;
    lock.style.clipPath = `inset(0 0 0 ${cut.toFixed(1)}px)`;
    tf(lock, { o: 1 });
  };
});

// ============ 3 · 01 Capture ============
Scene('capture', (el, s) => {
  const t0 = s.t0;
  // --- Gemini chat ---
  const cam = h('div', 'fill', el); cam.style.transformOrigin = '0 0';
  const chat = h('div', 'chat', cam); place(chat, 290, 190, 1340, 700);
  chat.innerHTML = `<div class="chat-h">${logo('Gemini', 'logo')}<span class="who silk">Gemini</span><span class="title">Portuguese café phrases</span><span class="sp"></span><span class="chip-model">Gemini 3 Pro</span></div>
    <div class="chat-b"><div class="msgs">
      <div class="msg me">I'm learning European Portuguese. give me 10 phrases for ordering at a café</div>
      <div class="msg ai">${logo('Gemini', '')}<span>Queria um galão, por favor · Um café (an espresso) · Uma meia de leite · Posso pagar com cartão? · Tem leite de aveia? · Para levar · Para comer aqui · A conta, se faz favor · Obrigada · Até amanhã!</span></div>
      <div class="msg me new"><span class="mark-hl"><span class="hlbg"></span><span class="hltx">I'm vegetarian.</span></span> what pastries are there besides pastel de nata?</div>
    </div></div>
    <div class="composer"><span class="tx"></span><span class="send">${ICON.up}</span></div>`;
  const msgs = chat.querySelector('.msgs'), nw = chat.querySelector('.msg.new'), hlbg = chat.querySelector('.hlbg'), hltx = chat.querySelector('.hltx');
  const ctx = chat.querySelector('.composer .tx'), send = chat.querySelector('.send');
  // the sentence, lifted out of the chat, carried by Baton
  const chip = h('div', 'abs', el, "I'm vegetarian.");
  Object.assign(chip.style, { transformOrigin: '0 0', background: 'var(--amber)', color: 'var(--ink)', fontSize: '26px', fontWeight: 600, padding: '6px 14px', borderRadius: '8px', zIndex: 25, whiteSpace: 'nowrap', boxShadow: '0 18px 40px -8px rgba(0,0,0,.7)' });
  const b = Baton(el);
  // --- the memory window ---
  const mem = h('div', 'abs', el);
  const lcd = h('div', 'lcd', mem); place(lcd, 150, 150, 1080, 520);
  lcd.innerHTML = `<div class="silk" style="position:absolute;left:44px;top:34px;font-size:14px;color:var(--silk3)">Memory · on this computer</div>
    <div class="ln" style="top:92px;font-size:34px"><span class="src">GEMINI ›</span> <span class="said" style="display:inline-block;min-width:10px"></span></div>
    <div class="ln" style="top:172px;font-size:30px">saved on this computer · memory #43</div>
    <div class="ln dim" style="top:226px;font-size:30px">fact · Gemini 3 Pro · “Portuguese café phrases”</div>
    <div class="ln" style="top:330px;font-family:var(--sans)"><div class="tri big"><span class="tch me">me</span><span class="arrow"></span><span class="tch rel">is</span><span class="arrow"></span><span class="tch">vegetarian</span></div></div>
    <div class="silk" style="position:absolute;left:44px;top:452px;font-size:14px;color:var(--silk3)">brain.py · plain rules, offline</div>`;
  const lns = [...lcd.querySelectorAll('.ln')], said = lcd.querySelector('.said');
  const ctr = h('div', 'lcd', mem); place(ctr, 1290, 150, 480, 520);
  ctr.innerHTML = `<div class="silk" style="position:absolute;left:40px;top:34px;font-size:14px;color:var(--silk3)">Counter</div>
    <div style="position:absolute;left:40px;top:96px" class="c1"></div><div class="unit silk" style="position:absolute;left:40px;top:206px">Memories</div>
    <div style="position:absolute;left:40px;top:290px" class="c2"></div><div class="unit silk" style="position:absolute;left:40px;top:400px">Bytes sent off this box</div>`;
  const seg1 = Segs(ctr.querySelector('.c1'), 4), seg2 = Segs(ctr.querySelector('.c2'), 4);
  const cap1 = Caption(el, '01 · Capture', 'Saved on your computer, stamped with where it came from.');
  // --- sockets ---
  const socks = h('div', 'fill', el);
  const rows = [
    ['In the browser · extension', ['ChatGPT', 'Claude', 'Gemini', 'Perplexity', 'DeepSeek', 'Grok', 'Copilot', 'Poe', 'Mistral', 'Google AI Studio'], 118],
    ['Coding agents and editors · MCP', ['Claude Code', 'Codex', 'Cursor', 'Windsurf', 'VS Code', 'Gemini CLI', 'Antigravity', 'Zed', 'OpenCode', 'Cline'], 452]];
  const bays = rows.map(([title, names, y]) => {
    const bay = h('div', 'bay', socks, `<h3 class="silk">${title}</h3>`); bay.style.top = y + 'px';
    const jks = names.map((n, i) => {
      const j = h('div', 'jk', bay, `<span class="led"></span>${logo(n === 'Google AI Studio' ? '' : n)}<span class="hole"></span><span class="nm silk">${n}</span>`);
      j.style.left = (40 + i * 164) + 'px';
      return { led: j.querySelector('.led'), hole: j.querySelector('.hole'), j };
    });
    return { bay, jks };
  });
  const cap2 = Caption(el, '01 · Capture', 'Web AIs through the browser extension.\nCoding agents over MCP.');
  const chap = Chapter(el, { num: '01', name: 'Capture', line: 'It listens.', section: 'Operation', page: 'p. 2', note: 'Parts 1 · 2 · 7' });
  let newH = 0, CAMS = 1;
  return (lt, t) => {
    chap.render(lt, 1.6);
    // chat
    const chatOn = t < T.memIn;
    show(cam, chatOn);
    if (chatOn) {
      if (!newH) newH = nw.getBoundingClientRect().height / (chat.getBoundingClientRect().width / 1340) + 22;
      const pin = E.outExpo(inv(t0 + 1.25, t0 + 2.0, t));
      const whip = E.inExpo(inv(T.batonOut + .15, T.batonOut + .6, t));
      tf(chat, { y: (1 - pin) * 60 + whip * -30, x: whip * -900, o: pin * (1 - whip * .9), s: .97 + .03 * pin, blur: whip * 22 });
      // camera: push into the composer while she types, ease back to the conversation when it's sent
      const zin = E.soft(inv(t0 + 1.7, T.gemType.t0 + .9, t)), zout = E.snap(inv(T.gemSend - .05, T.gemSend + .7, t));
      const cs = lerp(1, lerp(1.32, 1.14, zout), zin), fx = lerp(960, 960, zin), fy = lerp(540, lerp(800, 700, zout), zin);
      tf(cam, { x: 960 - fx * cs, y: 540 - fy * cs, s: cs }); CAMS = cs;
      const n = typed(T.gemType, t), sent = t >= T.gemSend;
      htm(ctx, sent ? '<span class="ph">Reply…</span>' : esc(T.gemType.text.slice(0, n)) + ((t * 2) % 1 < .6 || n < T.gemType.text.length ? '<span class="caret"></span>' : ''));
      tf(send, { s: 1 - .12 * Math.exp(-Math.max(0, t - T.gemSend) * 14) * (sent ? 1 : 0) });
      const ps = E.outExpo(inv(T.gemSend, T.gemSend + .55, t));
      tf(msgs, { y: (1 - ps) * newH });
      tf(nw, { o: sent ? 1 : 0, y: (1 - ps) * 30, s: .96 + .04 * ps });
      const hl = E.inOutCubic(inv(T.highlight, T.highlight + .3, t));
      hlbg.style.transform = `scaleX(${hl.toFixed(3)})`;
      hltx.style.color = hl > .5 ? 'var(--ink)' : '';
    }
    // chip + Baton
    const r = hltx.getBoundingClientRect(), k = 1920 / STAGE.getBoundingClientRect().width;
    const hx = (r.left - STAGE.getBoundingClientRect().left) * k - 8, hy = (r.top - STAGE.getBoundingClientRect().top) * k - 4;
    const lift = E.outBack(inv(T.highlight + .3, T.highlight + .6, t));
    const bx = lerp(-160, 2250, inv(T.batonIn, T.batonOut + .7, t));
    const run = t >= T.batonIn && t < T.batonOut + .75;
    if (run) { const rp = runPose(t); b.set({ x: bx, y: hy + 120 + rp.bob, size: 150 * CAMS, lean: rp.lean, sx: rp.sx, sy: rp.sy, blur: 10, o: 1 }); }
    else b.set({ o: 0 });
    let cx = hx, cy = hy - 46 * lift, cs = CAMS * (1 + .12 * lift), co = t >= T.highlight + .3 && t < T.memLines[0] + .02 && !(t > T.batonOut + .6 && t < T.memIn) ? 1 : 0;
    if (t >= T.grab && t < T.memIn - .2) { const [px, py] = b.pt(24, -58); cx = px; cy = py - 26; cs = CAMS * 1.12; }
    if (t >= T.batonOut + .75) {  // thrown in from the left, it lands on the memory's first line
      const sr = said.getBoundingClientRect(), sk = 1920 / STAGE.getBoundingClientRect().width, sl = STAGE.getBoundingClientRect();
      const tx = (sr.left - sl.left) * sk - 14, ty = (sr.top - sl.top) * sk - 6, pd = E.outExpo(inv(T.memIn, T.memLines[0], t));
      cx = lerp(-300, tx, pd); cy = lerp(ty + 120, ty, pd); cs = lerp(1.3, 1.23, pd);
    }
    tf(chip, { x: cx, y: cy, s: cs, o: co });
    // memory window
    const memOn = t >= T.memIn && t < T.sockets;
    show(mem, memOn);
    if (memOn) {
      const pm = E.outExpo(inv(T.memIn, T.memIn + .6, t)), po = E.inCubic(inv(T.sockets - .3, T.sockets, t));
      tf(lcd, { y: (1 - pm) * 50 - po * 40, o: pm * (1 - po) }); tf(ctr, { y: (1 - E.outExpo(inv(T.memIn + .1, T.memIn + .7, t))) * 50 - po * 40, o: clamp(inv(T.memIn + .1, T.memIn + .4, t)) * (1 - po) });
      txt(said, t >= T.memLines[0] ? "I'm vegetarian." : '');
      lns.forEach((l, i) => { const p = E.outExpo(inv(T.memLines[i], T.memLines[i] + .5, t)); tf(l, { x: (1 - p) * -24, o: i === 0 ? 1 : p }); });
      seg1.set(t >= T.memTick ? '0067' : '0066'); seg2.set('0');
      const fl = t >= T.memTick && t < T.memTick + .18 && ((t - T.memTick) * 30 % 2 < 1);
      ctr.querySelector('.c1').style.opacity = fl ? .35 : 1;
    }
    cap1.render(t, T.memLines[0] + .1, T.sockets - .35);
    // sockets
    const sOn = t >= T.sockets;
    show(socks, sOn);
    if (sOn) {
      bays.forEach((bb, k) => {
        const p = E.outExpo(inv(T.sockets + k * .15, T.sockets + .7 + k * .15, t)), po = E.inCubic(inv(s.t1 - .3, s.t1, t));
        tf(bb.bay, { y: (1 - p) * 70, o: p * (1 - po) });
        const at = k === 0 ? T.leds1 : T.leds2;
        bb.jks.forEach((j, i) => {
          const on = t >= at[i]; j.led.classList.toggle('on', on);
          const f = on ? Math.exp(-(t - at[i]) / .25) : 0;
          j.hole.style.borderColor = f > .05 ? `color-mix(in srgb, var(--amber) ${(f * 100).toFixed(0)}%, var(--white))` : '';
          j.hole.style.boxShadow = f > .05 ? `0 0 ${(30 * f).toFixed(1)}px rgba(255,178,26,${(.6 * f).toFixed(2)})` : '';
          tf(j.j, { y: -6 * f });
        });
      });
    }
    cap2.render(t, T.leds1[0] + .1, s.t1 - .3);
  };
});
