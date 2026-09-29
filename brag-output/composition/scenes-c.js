// Scenes 6–9: 04 Baton, 05 Forget, 06 Yours, install + end card.
const READY = [];
const PACK = `## Goal
- I'm building Pantry, a meal planner for flatmates… goal: a new flatmate joins the household and sees the shared pantry in under a minute

## Decisions and facts established
- let's decide: skip the household name step and generate one from the street name
- Flip it: let the new flatmate join with a link or code instead of waiting for an invite.

## Still open
- still open: how do we handle one person in two households?

## Latest messages
Claude: Print a short 6-letter code under the QR…
Me: still open: how do we handle one person in two households?`;
const CLAUDE_MSGS = ["I'm building Pantry, a meal planner for flatmates, as a side project.", "Great north star. Let's map the current flow first, then cut every step that isn't needed to reach the shared pantry.",
  "current flow: sign up, create household, name it, invite, scan a receipt.", "Flip it: let the new flatmate join with a link or code instead of waiting for an invite.",
  'what if the invite is a QR code on the fridge?', 'Love it — physical, shared, and it matches how flatmates actually coordinate.', 'I prefer progressive disclosure over long forms',
  'Then the join screen asks only for a name.', "let's decide: skip the household name step and generate one from the street name", 'Decided: household name = street name + door ("Rua da Esperança 12"), editable later.',
  'write the microcopy for the join screen. friendly, not cute', 'Title: "Join Rua da Esperança 12" · Button: "Join household"', 'the receipt scanner should be optional, put it after the first recipe',
  'Agreed — scanning is a power move, not an entry fee.', "what about accessibility for the QR flow? screen readers can't scan a fridge card",
  'Print a short 6-letter code under the QR and offer "Enter a code" on the join screen.', 'still open: how do we handle one person in two households? my friend Ana splits her week between two flats'];

// ============ 6 · 04 Baton ============
Scene('baton', (el, s) => {
  const chats = PageWin(el, 'chats.png', 96, 54, 1728, 972);
  const spot = h('div', 'spot', chats.cam); place(spot, BOX.hot[0] - 8, BOX.hot[1] - 8, BOX.hot[2] + 16, BOX.hot[3] + 16);
  const sc = scrim(el);
  const cap1 = Caption(el, '04 · Baton', 'Every chat from every AI, and how full it is.');
  // the Claude chat running out of room
  const cl = h('div', 'chat', el, `<div class="chat-h">${logo('Claude', 'logo')}<span class="who silk">Claude</span><span class="title">Pantry onboarding flow</span><span class="sp"></span>
      <span class="mono" style="font-size:17px;color:var(--fg3)">19 messages</span><span class="meter" style="width:150px;height:6px;border-radius:3px;background:var(--panel3);overflow:hidden"><i style="display:block;height:100%;width:0;background:var(--fg2)"></i></span><span class="chip-model">Opus 5</span></div>
    <div class="chat-b"><div class="msgs">${CLAUDE_MSGS.map((m, i) => i % 2 ? `<div class="msg ai">${logo('Claude', '')}<span>${esc(m)}</span></div>` : `<div class="msg me">${esc(m)}</div>`).join('')}</div></div>
    <div class="composer"><span class="tx"><span class="ph">Reply to Claude…</span></span><span class="send">${ICON.up}</span></div>`);
  place(cl, 90, 110, 1080, 860);
  const msgs = cl.querySelector('.msgs'), meter = cl.querySelector('.meter i'), comp = cl.querySelector('.composer');
  const sys = h('div', 'msg sys', cl, `${ICON.warn}<span>This conversation reached its maximum length. Start a new chat to continue.</span>`);
  Object.assign(sys.style, { position: 'absolute', left: '30px', right: '30px', bottom: '22px' });
  // the BATON key, the slot and the receipt
  const key = h('div', 'bkey', el, '<span class="led"></span><span class="cap">Baton</span><span class="bar"></span>'); place(key, 1270, 170);
  const kled = key.querySelector('.led');
  const slot = h('div', 'slotplate', el, '<div class="slit"></div><div class="lbl silk">Hand-off pack out</div>'); place(slot, 1210, 470);
  const rclip = h('div', 'abs', el); Object.assign(rclip.style, { left: '1260px', top: '516px', width: '540px', height: '580px', overflow: 'hidden' });
  const rec = h('div', 'receipt', rclip, `<div class="tear silk">Hand-off pack · 607 tokens<br>Claude → next AI</div><pre>${esc(PACK)}</pre><div class="zig"></div>`);
  const cur = h('div', 'abs', el, CURSOR);
  const kb = Baton(el);
  const cap2 = Caption(el, '04 · Baton', 'Hit Baton. The whole chat,\npacked for the next AI.');
  // the relay
  const relay = h('div', 'fill', el);
  const big = h('div', 'abs wordmark', relay, 'Pass the baton · Pass the baton · Pass the baton');
  Object.assign(big.style, { top: '120px', fontSize: '260px', whiteSpace: 'nowrap', color: 'transparent', WebkitTextStroke: '2px rgba(247,248,250,.13)' });
  const lane = h('div', 'lane', relay); lane.style.top = '600px';
  const world = h('div', 'abs', lane);
  for (let i = 0; i < 40; i++) { const hs = h('div', 'hash', world); hs.style.left = (i * 220) + 'px'; }
  const mkr = (name, x, note) => { const m = h('div', 'lbl silk', world, `${logo(name, '')}<span>${name}<br><span style="color:var(--silk3);font-size:15px">${note}</span></span>`); m.style.left = x + 'px'; return m; };
  mkr('Claude', 300, 'full · 19 messages'); const zone = h('div', 'zone', world); Object.assign(zone.style, { left: '1500px', width: '420px' });
  const zl = h('div', 'lbl silk', world, 'Hand-off zone'); Object.assign(zl.style, { left: '1560px', top: '-40px', transform: 'none', color: 'var(--amber)' });
  mkr('ChatGPT', 2500, 'picks it up');
  const speeds = Array.from({ length: 14 }, (_, i) => { const d = h('div', 'speed', relay); return { d, y: 470 + (i * 53) % 330, w: 120 + (i * 97) % 260, sp: 1600 + (i * 331) % 900, o: (i * 37) % 1920 }; });
  const rb = Baton(relay);
  const rpack = h('div', 'abs', relay); Object.assign(rpack.style, { width: '120px', height: '150px', background: 'var(--white)', borderRadius: '4px', transformOrigin: '0 0', boxShadow: '0 10px 20px rgba(0,0,0,.5)',
    backgroundImage: 'repeating-linear-gradient(180deg, transparent 0 14px, rgba(10,10,11,.35) 14px 16px)', backgroundPosition: '0 22px', backgroundSize: '100% 16px', backgroundRepeat: 'repeat-y', padding: '0' });
  // ChatGPT carries on
  const gp = h('div', 'chat', el, `<div class="chat-h">${logo('ChatGPT', 'logo')}<span class="who silk">ChatGPT</span><span class="title">Pantry onboarding, continued</span><span class="sp"></span><span class="chip-model">GPT-5.5</span></div>
    <div class="chat-b"><div class="msgs">
      <div class="msg me"><div style="display:flex;gap:14px;align-items:center;background:var(--panel);border:1px solid var(--line2);border-radius:14px;padding:12px 16px;margin-bottom:12px;font-size:20px">
        <span style="width:34px;height:40px;background:var(--white);border-radius:3px;flex:none;background-image:repeating-linear-gradient(180deg,transparent 0 6px,rgba(10,10,11,.4) 6px 7px);background-position:0 8px"></span>
        <span><b style="font-weight:600">[mindbaton handoff]</b><br><span style="color:var(--fg3)">Pantry onboarding flow · Claude · 607 tokens</span></span></div>Picking this up here — can you help with the two-households question?</div>
      <div class="msg ai">${logo('ChatGPT', '')}<span class="ans"></span></div>
    </div></div><div class="composer"><span class="tx"><span class="ph">Ask anything</span></span><span class="send">${ICON.up}</span></div>`);
  place(gp, 260, 110, 1400, 800);
  const ans = gp.querySelector('.ans'), gme = gp.querySelector('.msg.me');
  const perch = Baton(el);
  const cap3 = Caption(el, '04 · Baton', 'Pass the baton. Keep going.');
  const chap = Chapter(el, { num: '04', name: 'Baton', line: 'When a chat fills up.', section: 'Operation', page: 'p. 5', note: 'Part 6 · handoff.py' });
  let msgH = 0;
  return (lt, t) => {
    chap.render(lt, 1.6);
    const cOn = t < T.claude; show(chats.win, cOn); show(sc, cOn);
    if (cOn) {
      const pi = E.outExpo(inv(T.chats - .3, T.chats + .5, t)), po = E.inCubic(inv(T.claude - .3, T.claude, t));
      tf(chats.win, { y: (1 - pi) * 60, o: pi * (1 - po) });
      const m = E.soft(inv(T.chats, T.claude, t)); chats.look(lerp(960, 820, m), lerp(540, 420, m), lerp(.9, 1.35, m));
      tf(spot, { o: E.outCubic(inv(T.spot, T.spot + .4, t)) });
    }
    cap1.render(t, T.spot, T.claude - .3);
    const kOn = t >= T.claude && t < T.run; show(cl, kOn); show(key, kOn); show(slot, kOn); show(rclip, kOn); show(cur, kOn); show(kb.el, kOn);
    if (kOn) {
      if (!msgH) msgH = msgs.scrollHeight;
      const pi = E.outExpo(inv(T.claude, T.claude + .5, t)), dim = E.inOutCubic(inv(T.press, T.press + .5, t));
      tf(cl, { y: (1 - pi) * 60, o: pi * (1 - .55 * dim), s: 1 - .03 * dim });
      tf(msgs, { y: (1 - E.inOutCubic(inv(T.claude, T.limit, t))) * (msgH * .75) });
      const fill = lerp(.62, 1, E.inOutCubic(inv(T.claude + .2, T.limit, t)));
      meter.style.width = (fill * 100).toFixed(1) + '%'; meter.style.background = fill > .8 ? 'var(--danger)' : 'var(--fg2)';
      const sp = E.outBack(inv(T.limit, T.limit + .4, t)); tf(sys, { y: (1 - sp) * 40, o: clamp(sp * 2) }); tf(comp, { o: 1 - sp });
      const ku = E.outBack(inv(T.keyUp, T.keyUp + .5, t)), down = t >= T.press && t < T.press + .22 ? 1 : E.outCubic(inv(T.press - .06, T.press, t)) * (t < T.press ? 1 : 0);
      tf(key, { y: (1 - ku) * 700 + down * 12, o: clamp(ku * 3) }); tf(slot, { y: (1 - E.outExpo(inv(T.keyUp + .1, T.keyUp + .6, t))) * 500 });
      key.style.boxShadow = down > .5 ? 'inset 0 2px 0 #fff, 0 2px 0 #9c9ea3, 0 10px 20px -8px rgba(0,0,0,.8)' : '';
      kled.classList.toggle('on', t >= T.press);
      const cx = kf(t, [[T.keyUp + .2, 1900], [T.press - .1, 1520, E.inOutCubic]]), cy = kf(t, [[T.keyUp + .2, 900], [T.press - .1, 300, E.inOutCubic]]);
      tf(cur, { x: cx, y: cy + down * 10, o: inv(T.keyUp + .1, T.keyUp + .3, t) * (1 - inv(T.press + .4, T.press + .6, t)) });
      const pr = E.inOutQuart(inv(T.printAt, T.printEnd, t)), jit = t < T.printEnd && t > T.printAt ? Math.sin(t * 140) * 1.2 : 0;
      tf(rec, { y: -560 + pr * 560 + jit });
      // Baton pops up, rips the pack off and goes
      const up = inv(T.tear - .35, T.tear, t), rip = inv(T.tear, T.run, t);
      if (up > 0) {
        const rp = runPose(t);
        kb.set({ x: lerp(1950, 1640, E.outBack(up)) + E.inQuad(rip) * 500, y: lerp(1250, 1000, E.outBack(up)) - rip * 60 + (rip > 0 ? rp.bob : 0), size: 190, lean: rip > 0 ? rp.lean : -12, blur: rip * 10, o: 1 });
        const [px, py] = kb.pt(20, -60);
        if (t >= T.tear) { tf(rclip, { x: px - 1300, y: py - 560, o: 1 - rip * .3 }); rclip.style.transform += ` rotate(${(-8 * rip).toFixed(2)}deg)`; }
        else tf(rclip, {});
      } else { kb.set({ o: 0 }); tf(rclip, {}); }
    }
    cap2.render(t, T.printAt + .1, T.tear - .1);
    // relay
    const rOn = t >= T.run && t < T.gpt; show(relay, rOn);
    if (rOn) {
      const u = t - T.run, dist = 1300 * u + 180 * u * u;
      tf(world, { x: -dist + 400 });
      tf(big, { x: -dist * .35 - 200 });
      speeds.forEach(q => { const x = ((q.o - (u * q.sp)) % 2300 + 2300) % 2300 - 200; place(q.d, x, q.y, q.w); tf(q.d, { o: .5 }); });
      const rp = runPose(t, 1.3), hop = E.inOutCubic(inv(T.run + .9, T.run + 1.25, t));
      const ry = 700 + rp.bob - Math.sin(hop * Math.PI) * 120;
      rb.set({ x: 820 + Math.sin(u * 2) * 20, y: ry, size: 230, lean: rp.lean, sx: rp.sx, sy: rp.sy, blur: 6 });
      const [px, py] = rb.pt(22, -62); tf(rpack, { x: px - 10, y: py - 70, r: -10 + Math.sin(u * 20) * 3 });
      tf(relay, { o: 1 - inv(T.gpt - .15, T.gpt, t) });
    }
    // ChatGPT
    const gOn = t >= T.gpt; show(gp, gOn); show(perch.el, gOn);
    if (gOn) {
      const pi = E.outExpo(inv(T.gpt, T.gpt + .5, t)); tf(gp, { y: (1 - pi) * 60, o: pi });
      const pm = E.outBack(inv(T.gptMsg, T.gptMsg + .45, t)); tf(gme, { o: clamp(pm * 2), y: (1 - pm) * 40, s: .95 + .05 * pm });
      const n = typed(T.gptType, t); htm(ans, esc(T.gptType.text.slice(0, n)) + (n && n < T.gptType.text.length ? '<span class="caret"></span>' : ''));
      // Baton lands on the window's corner and watches the answer arrive
      const land = inv(T.gpt, T.gpt + .45, t), dt = t - T.gpt - .45, q = dt > 0 ? .25 * Math.exp(-dt * 7) * Math.cos(dt * 16) : 0;
      perch.set({ x: lerp(-200, 330, E.outCubic(land)), y: 912 - Math.sin(land * Math.PI) * 180, size: 150, lean: land < 1 ? 38 : kf(t, [[T.gpt + .45, 38], [T.gpt + .9, 32]]), sx: 1 + q, sy: 1 - q, ex: 2.5, ey: -1.5, blink: blinkAt(t, 78.2) });
    }
    cap3.render(t, 77.9, s.t1 - .25);
  };
});

// ============ 7 · 05 Forget ============
Scene('forget', (el, s) => {
  const PS = 1.4, PH = 680;
  const pan = h('div', 'shotcard', el); place(pan, 230, 60, 420 * PS, PH * PS);
  const p1 = shotImg(pan, 'mem104_panel.png'), p2 = shotImg(pan, 'mem104_panel_armed.png');
  for (const i of [p1, p2]) Object.assign(i.style, { position: 'absolute', left: 0, top: 0, width: 420 * PS + 'px', height: 1080 * PS + 'px' });
  const cur = h('div', 'abs', el, CURSOR);
  const lcd = h('div', 'lcd', el); place(lcd, 980, 110, 800, 560);
  lcd.innerHTML = `<div style="position:absolute;left:44px;top:44px" class="c"></div><div class="unit silk" style="position:absolute;left:44px;top:150px">Memories</div>
    <div class="ln" style="top:220px;font-size:24px"><span class="src">FORGET ›</span> I prefer dark mode in every app</div>
    <div class="ln" style="top:272px;font-size:24px">removed · memories 0067 → 0066</div>
    <div class="ln dim" style="top:324px;font-size:24px">rebuild from every saved chat…</div>
    <div class="abs" style="left:44px;top:376px;width:712px;height:8px;border-radius:4px;background:#1f1f23;overflow:hidden"><i class="bar" style="display:block;height:100%;width:0;background:var(--amber)"></i></div>
    <div class="ln" style="top:420px;font-size:40px;color:var(--amber)">still gone</div>`;
  const seg = Segs(lcd.querySelector('.c'), 4), lns = [...lcd.querySelectorAll('.ln')], bar = lcd.querySelector('.bar');
  const cap = Caption(el, '05 · Forget', 'Forget in one click.\nIt stays forgotten.'); cap.el.style.left = '980px'; cap.el.style.width = '860px';
  const chap = Chapter(el, { num: '05', name: 'Forget', line: 'One click. For good.', section: 'Operation', page: 'p. 6', note: 'Part 7 · memory database' });
  const B1 = [230 + (21 + 30) * PS, 60 + (549.6 + 14) * PS], B2 = [230 + (21 + 60) * PS, 60 + (549.6 + 14) * PS];
  return (lt, t) => {
    chap.render(lt, 1.2);
    const pi = E.outExpo(inv(T.panelIn, T.panelIn + .5, t)), gone = E.inOutCubic(inv(T.gone, T.gone + .6, t));
    tf(pan, { x: (1 - pi) * -80, o: pi * (1 - gone), blur: gone * 14, s: 1 - .04 * gone });
    tf(p2, { o: t >= T.click1 + .05 ? 1 : 0 });
    const cx = kf(t, [[T.panelIn + .3, 1200], [T.click1 - .08, B1[0], E.inOutCubic], [T.click2 - .25, B1[0]], [T.click2 - .08, B2[0], E.inOutCubic]]);
    const cy = kf(t, [[T.panelIn + .3, 1000], [T.click1 - .08, B1[1], E.inOutCubic], [T.click2 - .08, B2[1], E.inOutCubic]]);
    const press = (t >= T.click1 && t < T.click1 + .12) || (t >= T.click2 && t < T.click2 + .12) ? 4 : 0;
    tf(cur, { x: cx, y: cy + press, o: inv(T.panelIn + .3, T.panelIn + .5, t) * (1 - inv(T.click2 + .3, T.click2 + .5, t)) });
    const li = E.outExpo(inv(T.panelIn + .2, T.panelIn + .8, t)); tf(lcd, { y: (1 - li) * 50, o: li });
    seg.set(t >= T.count ? '0066' : '0067');
    const at = [T.gone, T.count, T.rebuild, T.still];
    lns.forEach((l, i) => { const p = E.outExpo(inv(at[i], at[i] + .45, t)); tf(l, { x: (1 - p) * -20, o: p }); });
    bar.style.width = (100 * E.inOutCubic(inv(T.rebuild + .1, T.still - .1, t))).toFixed(1) + '%';
    tf(el, { o: 1 - inv(s.t1 - .2, s.t1, t) });
    cap.render(t, T.count + .3, s.t1 - .3);
  };
});

// ============ 8 · 06 Yours ============
Scene('yours', (el, s) => {
  // the site's exploded drawing, fetched from site/index.html at load time
  const xw = h('div', 'abs', el); Object.assign(xw.style, { left: '1010px', top: '150px', width: '780px' });
  let layers = [];
  READY.push(async () => {
    const d = new DOMParser().parseFromString(await (await fetch('/site/index.html')).text(), 'text/html');
    const svg = d.querySelector('figure.xpl svg'); svg.classList.add('xpl'); svg.style.position = 'static'; svg.setAttribute('width', '780'); svg.setAttribute('height', String(780 * 720 / 672));
    xw.appendChild(document.importNode(svg, true));
    layers = [...xw.querySelectorAll('.layer')].map(g => { const m = g.getAttribute('transform').match(/translate\(([\d.]+)[ ,]([\d.]+)\)/); return { g, x: +m[1], y: +m[2], d: +g.dataset.d, l: +g.dataset.l, co: [...g.querySelectorAll('.co')] }; });
  });
  const PARTS = [['Browser extension', 'saves what you say'], ['MCP at /mcp', 'eight tools for your AIs'], ['server.py', 'standard library only'], ['Password + device tokens', 'revoke any'],
    ['brain.py', 'plain rules sort it all'], ['handoff.py', 'builds the baton'], ['memory.db', 'SQLite, one per person'], ['Your computer', 'not included']];
  const pl = h('ol', 'plist', el, PARTS.map(([a, b], i) => `<li><span class="n">${i + 1}</span><span><b>${a}</b> · ${b}</span></li>`).join('')); place(pl, 130, 150);
  const lis = [...pl.children];
  const cap1 = Caption(el, '06 · Yours', 'One Python program. One database file.\nYour computer.');
  // the datasheet
  const sh = h('div', 'sheet', el); place(sh, 160, 60, 1600, 1100);
  sh.innerHTML = `<div class="rh silk"><span>Mindbaton 0.1.0 · Owner's manual</span><span>Safety</span><span>p. 8</span></div><h2>What it will not do</h2>`;
  const ROWS = [['Cloud', 'None'], ['Account with us', 'None'], ['Telemetry', 'None'], ['Sent off this box', '<span class="hl">0 bytes</span>'], ['Keys you paste in a chat', '<code class="key">sk-proj-4fT9xQ2mLr8vWb7K</code>']];
  const srows = ROWS.map(([a, b], i) => { const r = h('div', 'srow', sh, `<dt class="silk">${a}</dt><dd>${b}</dd>`); r.style.top = (250 + i * 104) + 'px'; return r; });
  const key = sh.querySelector('code.key'), hl = sh.querySelector('.hl');
  // its own model
  const mdl = h('div', 'fill', el);
  const mh = h('div', 'abs', mdl, `<div class="silk" style="font-size:16px;color:var(--amber);margin-bottom:18px">Mindbaton's own model · runs on your computer</div><div style="font-size:64px;font-weight:600;letter-spacing:-.03em">Reads what the rules can't.</div>`);
  place(mh, 150, 170);
  const ST = [['28/30', 'facts caught in sentences it never saw'], ['0', 'made-up facts in that test'], ['1.3 GB', 'offline, at low priority']];
  const stats = ST.map(([n, l], i) => { const d = h('div', 'stat', mdl, `<b>${n}</b><span>${l}</span>`); place(d, 150 + i * 560, 470); return d; });
  // also in the box
  const ex = h('div', 'fill', el);
  const eh = h('div', 'abs silk', ex, 'Also in the box'); Object.assign(eh.style, { left: '120px', top: '200px', fontSize: '18px', color: 'var(--amber)' });
  const XS = [[ICON.people, 'A memory for everyone at home', 'Each account private and separate.'], [ICON.down, 'Bring your old memory', 'One prompt for ChatGPT, Claude, Gemini…'],
    [ICON.phone, 'On your phone', 'Install it, share into it.'], [ICON.box, 'Yours to take', 'JSON, Neo4j Cypher or GraphML.']];
  const xc = XS.map(([ic, a, b], i) => { const c = h('div', 'xcard', ex, `<div class="ic">${ic}</div><h4>${a}</h4><p>${b}</p>`); place(c, 120 + i * 430, 270); return c; });
  const chap = Chapter(el, { num: '06', name: 'Yours', line: 'It lives on your computer.', section: 'Parts', page: 'p. 7', note: 'Parts 3 · 4 · 7 · 8' });
  return (lt, t) => {
    chap.render(lt, 1.6);
    const xOn = t < T.sheet + .5; show(xw, xOn); show(pl, xOn);
    if (xOn) {
      const cl = E.inOutCubic(inv(T.close + 1.8, T.close + 2.6, t));
      layers.forEach(L => {
        const inP = E.outExpo(inv(T.xpl + (4 - L.l) * .1, T.xpl + .7 + (4 - L.l) * .1, t));
        L.g.setAttribute('transform', `translate(${L.x} ${(L.y + (1 - inP) * 500 + cl * L.d).toFixed(2)})`);
        L.g.style.opacity = clamp(inP * 2); L.co.forEach(c => c.style.opacity = 1 - cl);
      });
      lis.forEach((li, i) => { const p = E.outExpo(inv(T.xpl + .2 + i * .09, T.xpl + .8 + i * .09, t)); tf(li, { x: (1 - p) * -30, o: p * (1 - cl * .6) }); });
    }
    cap1.render(t, T.close + .3, T.sheet - .1);
    const sOn = t >= T.sheet && t < T.model + .5; show(sh, sOn);
    if (sOn) {
      const pi = E.outExpo(inv(T.sheet, T.sheet + .55, t)), po = E.inExpo(inv(T.model - .1, T.model + .4, t));
      tf(sh, { y: (1 - pi) * 1000 + po * 1100 });
      srows.forEach((r, i) => { const p = E.outExpo(inv(T.rows[i], T.rows[i] + .5, t)); tf(r, { x: (1 - p) * 40, o: p }); });
      hl.style.backgroundSize = ''; tf(hl, { o: 1 }); hl.style.background = t >= T.rows[3] + .5 ? 'var(--amber)' : 'transparent';
      const rd = inv(T.rows[4] + .9, T.rows[4] + 1.3, t), src = 'sk-proj-4fT9xQ2mLr8vWb7K', r = TL.rng(Math.floor(t * 30));
      txt(key, rd <= 0 ? src : rd >= 1 ? '[secret]' : src.split('').map(c => r() < rd ? '█' : c).join(''));
    }
    const mOn = t >= T.model && t < T.extras + .3; show(mdl, mOn);
    if (mOn) {
      const po = E.inCubic(inv(T.extras - .3, T.extras, t));
      tf(mh, { o: E.outCubic(inv(T.model + .2, T.model + .6, t)) * (1 - po), y: (1 - E.outExpo(inv(T.model + .2, T.model + .8, t))) * 30 });
      stats.forEach((d, i) => { const p = E.outExpo(inv(T.model + .45 + i * .15, T.model + 1.05 + i * .15, t)); tf(d, { y: (1 - p) * 60, o: p * (1 - po) }); });
      const c = E.outCubic(inv(T.model + .45, T.model + 1.4, t));
      txt(stats[0].querySelector('b'), Math.round(28 * c) + '/30'); txt(stats[2].querySelector('b'), (1.3 * c).toFixed(1) + ' GB');
    }
    const eOn = t >= T.extras; show(ex, eOn);
    if (eOn) {
      tf(eh, { o: E.outCubic(inv(T.extras, T.extras + .4, t)) });
      xc.forEach((c, i) => { const p = E.outBack(inv(T.extraAt[i], T.extraAt[i] + .5, t)), po = E.inCubic(inv(s.t1 - .3, s.t1, t)); tf(c, { y: (1 - p) * 60, o: clamp(p * 2) * (1 - po) }); });
    }
  };
});

// ============ 9 · install + end card ============
Scene('outro', (el, s) => {
  const term = h('div', 'term', el, `<div class="th"><span>Terminal · the computer that stays on</span></div><div class="tb" style="font-size:28px"></div>`);
  place(term, 180, 170, 1560, 420);
  const tb = term.querySelector('.tb');
  const STEPS = ['Welcome', 'Check', 'Account', 'AI keys', 'Your AI tools', 'Connect', 'Memories', 'Start', 'Done'];
  const st = h('div', 'steps', el, STEPS.map(n => `<span class="stp"><i></i>${n}</span>`).join('')); place(st, 180, 640);
  const stps = [...st.children];
  const cap = Caption(el, 'Install', 'One command. Docker works too.');
  const end = h('div', 'fill', el);
  const eb = Baton(end);
  const wm = h('div', 'abs wordmark', end, 'Mindbaton'); Object.assign(wm.style, { width: '1920px', textAlign: 'center', top: '520px', fontSize: '120px' });
  const tag = h('div', 'abs', end, words('Tell one AI. Every AI knows.')); Object.assign(tag.style, { width: '1920px', textAlign: 'center', top: '672px', fontSize: '58px', fontWeight: 600, letterSpacing: '-.03em' });
  const foot = h('div', 'abs', end, `<div class="silk" style="font-size:17px;color:var(--silk2)">Free and open source · AGPL-3.0 · no cloud · no account · no telemetry</div><div class="url" style="font-size:30px;margin-top:18px">github.com/DkshByte/mindbaton</div>`);
  Object.assign(foot.style, { width: '1920px', textAlign: 'center', top: '812px' });
  const tws = [...tag.querySelectorAll('.wi')];
  return (lt, t) => {
    const iOn = t < T.end; show(term, iOn); show(st, iOn);
    if (iOn) {
      const pi = E.outExpo(inv(T.install, T.install + .5, t)), po = E.inCubic(inv(T.end - .3, T.end, t));
      tf(term, { y: (1 - pi) * 50 - po * 30, o: pi * (1 - po) });
      const n = typed(T.cmd, t);
      let o = `<span class="pr">$</span> ${esc(T.cmd.text.slice(0, n))}${t < T.enter ? '<span class="caret"></span>' : ''}`;
      if (t >= T.enter + .15) o += `\n<span class="dim">Cloning into 'mindbaton'… checking Python… self-test passed</span>`;
      if (t >= T.steps[8] + .15) o += `\n<span class="ok">✓</span> Mindbaton is running. Open <span class="pr">http://192.168.1.20:3004/?code=4821-7730</span>`;
      htm(tb, o);
      stps.forEach((e, i) => { const p = E.outExpo(inv(T.enter + i * .04, T.enter + .4 + i * .04, t)); tf(e, { y: (1 - p) * 20, o: p * (1 - po) }); e.classList.toggle('on', t >= T.steps[i]); });
    }
    cap.render(t, T.steps[0], T.end - .3);
    const eOn = t >= T.end; show(end, eOn);
    if (eOn) {
      const FL = 470, fall = inv(T.end - .22, T.end, t), dt = t - T.end, q = .28 * Math.exp(-dt * 7) * Math.cos(dt * 16);
      const lean = kf(t, [[T.end + .5, 0], [T.end + .7, -8, E.outQuad], [T.end + 1.05, 32, E.outBack]]);
      eb.set({ x: 960 - 20, y: FL, size: 220, lean, sx: 1 + q, sy: 1 - q, blink: blinkAt(t, T.blink2) + blinkAt(t, T.end + .35), ex: kf(t, [[T.blink2 + .3, 0], [T.blink2 + .5, -3], [110.8, -3], [111, 0]]), o: 1 });
      eb.el.style.filter = `drop-shadow(0 0 ${(40 + 30 * Math.exp(-dt * 2)).toFixed(1)}px rgba(255,178,26,.3))`;
      const wp = E.outExpo(inv(T.endMark - .5, T.endMark + .3, t)); tf(wm, { y: (1 - wp) * 60, o: wp });
      tws.forEach((w, i) => { const p = E.outExpo(inv(T.endTag + .5 + i * .05, T.endTag + 1.3 + i * .05, t)); tf(w, { y: (1 - p) * 70, o: clamp(p * 2) }); });
      tf(foot, { o: E.outCubic(inv(T.endFoot, T.endFoot + .6, t)) });
      tf(end, { o: 1 - inv(T.fade, s.t1, t) });
    }
  };
});
