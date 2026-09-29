// Scenes 4–5: 02 Remember, 03 Recall. Real app captures (demo.py data) animated as layers.
const BOX = { kcards: [[564, 335.5, 338.7, 96], [564, 443.5, 338.7, 96], [564, 551.5, 338.7, 130], [914.7, 335.5, 338.7, 198], [914.7, 545.5, 338.7, 96], [914.7, 653.5, 338.7, 96], [1265.3, 335.5, 338.7, 198], [1265.3, 545.5, 338.7, 96]], hot: [564, 297.8, 340, 134.3] };
// a window onto a full-page capture with a camera: focus point (page px) and zoom
function PageWin(parent, file, x, y, w, hh) {
  const win = h('div', 'win', parent); place(win, x, y, w, hh);
  const cam = h('div', 'abs', win); cam.style.transformOrigin = '0 0'; cam.style.width = '1920px'; cam.style.height = '1080px';
  const img = shotImg(cam, file); img.style.width = '1920px'; img.style.height = '1080px';
  return { win, cam, img, look(fx, fy, z) { tf(cam, { x: w / 2 - fx * z, y: hh / 2 - fy * z, s: z }); } };
}
function scrim(parent) { const s = h('div', 'abs', parent); Object.assign(s.style, { left: 0, top: '560px', width: '1920px', height: '520px', zIndex: 29, background: 'linear-gradient(180deg, rgba(10,10,11,0), rgba(10,10,11,.88) 62%)' }); return s; }

// ============ 4 · 02 Remember ============
Scene('remember', (el, s) => {
  // You page, kind cards dropping in one per beat
  const you = PageWin(el, 'you_nokinds.png', 96, 54, 1728, 972);
  const cards = BOX.kcards.map(([x, y, w, hh], i) => { const c = shotImg(you.cam, `kcard_${i}.png`); place(c, x, y, w, hh); c.style.position = 'absolute'; return c; });
  const sc1 = scrim(el);
  const cap1 = Caption(el, '02 · Remember', 'Everything your AIs learn about you,\nsorted by kind. By itself.');
  // messy typing → real brain.py triples
  const messy = h('div', 'fill', el);
  const M = [["switched jobs, I'm at Stripe now", 'works at', 'Stripe'], ['not a coffee person tbh', 'dislikes', 'coffee'], ['bought the e-bike yesterday!', 'has', 'e-bike']];
  const mrows = M.map(([say, rel, obj], i) => {
    const b = h('div', 'bubble', messy, esc(say)); place(b, 150, 170 + i * 190);
    const tri = h('div', 'tri big abs', messy, `<span class="tch me">me</span><span class="arrow"></span><span class="tch rel">${rel}</span><span class="arrow"></span><span class="tch">${obj}</span>`);
    place(tri, 1010, 184 + i * 190);
    return { b, parts: [...tri.children] };
  });
  const tag = h('div', 'abs silk', messy, 'brain.py · plain rules · offline · no AI needed'); Object.assign(tag.style, { left: '1010px', top: '112px', fontSize: '15px', color: 'var(--silk3)' });
  const cap2 = Caption(el, '02 · Remember', 'It reads the way you actually type.');
  // what changed lately: the real card, before → after
  const chg = h('div', 'fill', el);
  const CW = 604, CH = 197, CS = 2.1, CX = (1920 - CW * CS) / 2, CY = 150;
  const cbox = h('div', 'shotcard', chg); place(cbox, CX, CY, CW * CS, CH * CS);
  const before = shotImg(cbox, 'you_changed_before.png'); before.style.position = 'absolute'; before.style.inset = '0';
  const after = [0, 1].map(() => { const i = shotImg(cbox, 'you_changed.png'); Object.assign(i.style, { position: 'absolute', inset: '0' }); return i; });
  const after2 = [0, 1].map(() => { const i = shotImg(cbox, 'you_changed.png'); Object.assign(i.style, { position: 'absolute', inset: '0' }); return i; });
  const strike = [0, 1].map(() => { const d = h('div', 'abs', cbox); Object.assign(d.style, { height: (1.3 * CS) + 'px', background: 'rgba(233,61,130,.85)', transformOrigin: 'left center' }); return d; });
  const ROWS = [{ was: [57, 67, 125], now: [57, 89.5] }, { was: [57, 132.5, 319], now: [57, 155] }];
  ROWS.forEach((r, i) => place(strike[i], r.was[0] * CS, (r.was[1] + 10.5) * CS, r.was[2] * CS));
  const cap3 = Caption(el, '02 · Remember', 'It keeps up when things change.\nThe old stays in history.');
  // same subject, different apps → one topic
  const top = h('div', 'fill', el);
  const rows = ['row_scaffold.png', 'row_recipe.png', 'row_shopping.png'].map((f, i) => { const c = h('div', 'shotcard', top); place(c, 110, 250 + i * 128, 915 * 1.12, 65 * 1.12); shotImg(c, f); return c; });
  const tcard = h('div', 'shotcard', top); place(tcard, 1180, 290, 339 * 1.9, 153 * 1.9); shotImg(tcard, 'tcard_2.png');
  const cap4 = Caption(el, '02 · Remember', 'Same subject, different apps: one topic.');
  // the map
  const map = PageWin(el, 'map.png', 0, 0, 1920, 1080); map.win.style.borderRadius = '0';
  const sc5 = scrim(el);
  const cap5 = Caption(el, '02 · Remember', 'All of it, on one map.');
  const chap = Chapter(el, { num: '02', name: 'Remember', line: 'It sorts itself.', section: 'Operation', page: 'p. 3', note: 'Part 5 · brain.py' });
  return (lt, t) => {
    chap.render(lt, 1.6);
    // You
    const yOn = t < T.messy; show(you.win, yOn); show(sc1, yOn);
    if (yOn) {
      const pi = E.outExpo(inv(T.youIn - .3, T.youIn + .5, t)), po = E.inCubic(inv(T.messy - .35, T.messy, t));
      tf(you.win, { y: (1 - pi) * 60 - po * 40, o: pi * (1 - po), s: .98 + .02 * pi });
      const m = E.soft(inv(T.youIn, T.messy, t));
      you.look(lerp(960, 1084, m), lerp(540, 520, m), lerp(.9, 1.32, m));
      cards.forEach((c, i) => { const p = E.outBack(inv(T.cards[i], T.cards[i] + .45, t)); tf(c, { y: (1 - p) * 26, o: clamp(inv(T.cards[i], T.cards[i] + .2, t)), s: .94 + .06 * p }); });
    }
    cap1.render(t, T.cards[2], T.messy - .35);
    // messy
    const mOn = t >= T.messy && t < T.change; show(messy, mOn);
    if (mOn) {
      const po = E.inCubic(inv(T.change - .3, T.change, t));
      tf(messy, { o: 1 - po, y: -po * 30 });
      tf(tag, { o: E.outCubic(inv(T.messy + .2, T.messy + .6, t)) });
      mrows.forEach((r, i) => {
        const a = T.messyAt[i], p = E.outBack(inv(a, a + .4, t));
        tf(r.b, { x: (1 - p) * -40, o: clamp(inv(a, a + .15, t)), s: .9 + .1 * p });
        r.parts.forEach((q, k) => { const b = a + .35 + k * .07, pp = E.outExpo(inv(b, b + .5, t)); tf(q, { x: (1 - pp) * -50, o: pp }); });
      });
    }
    cap2.render(t, T.messy + .15, T.change - .3);
    // change card
    const cOn = t >= T.change && t < T.topics; show(chg, cOn);
    if (cOn) {
      const pi = E.outExpo(inv(T.change, T.change + .6, t)), po = E.inCubic(inv(T.topics - .3, T.topics, t));
      tf(cbox, { y: (1 - pi) * 60 - po * 40, o: pi * (1 - po) });
      [0, 1].forEach(i => {
        const off = i * .45, st = E.inOutCubic(inv(T.strike + off, T.strike + off + .35, t));
        strike[i].style.transform = `scaleX(${st.toFixed(3)})`; tf(strike[i], { o: st > 0 ? 1 - inv(T.strike + off + .35, T.strike + off + .55, t) : 0 });
        const r = ROWS[i], wasP = inv(T.strike + off + .3, T.strike + off + .55, t);
        after[i].style.clipPath = `inset(${(r.was[1] - 4) / CH * 100}% 0 ${100 - (r.was[1] + 21) / CH * 100}% 0)`; tf(after[i], { o: wasP });
        const np = E.outExpo(inv(T.newLine + off, T.newLine + off + .6, t));
        after2[i].style.clipPath = `inset(${(r.now[1] - 3) / CH * 100}% ${100 - np * 100}% ${100 - (r.now[1] + 23) / CH * 100}% 0)`; tf(after2[i], { o: np > 0 ? 1 : 0 });
      });
    }
    cap3.render(t, T.change + .5, T.topics - .3);
    // topic
    const tOn = t >= T.topics && t < T.map; show(top, tOn);
    if (tOn) {
      const po = E.inCubic(inv(T.map - .3, T.map, t));
      rows.forEach((r, i) => {
        const p = E.outExpo(inv(T.rowsIn[i], T.rowsIn[i] + .55, t)), c = E.inOutCubic(inv(T.converge + i * .06, T.converge + .5 + i * .06, t));
        tf(r, { x: (1 - p) * -120 + c * 980, y: c * (100 - i * 128 + 60), s: 1 - .7 * c, o: p * (1 - c) });
      });
      const tp = E.outExpo(inv(T.rowsIn[0], T.rowsIn[0] + .6, t)), pop = T.topicPop <= t ? spring(t - T.topicPop, 3, .3) : 0;
      tf(tcard, { o: tp * (1 - po), s: 1 + .07 * Math.sin(pop * Math.PI) * (1 - inv(T.topicPop, T.topicPop + .8, t)), y: (1 - tp) * 40 });
      tcard.style.boxShadow = t >= T.topicPop ? `0 0 0 ${(2 * (1 - inv(T.topicPop, T.topicPop + 1, t))).toFixed(2)}px var(--amber), 0 30px 80px -10px rgba(0,0,0,.8)` : '';
    }
    cap4.render(t, T.rowsIn[2] + .1, T.map - .3);
    // map
    const mpOn = t >= T.map; show(map.win, mpOn); show(sc5, mpOn);
    if (mpOn) { const m = E.soft(inv(T.map, s.t1, t)); map.look(lerp(1060, 1010, m), lerp(560, 570, m), lerp(1.05, 1.42, m)); tf(map.win, { o: E.outCubic(inv(T.map, T.map + .4, t)) }); }
    cap5.render(t, T.map + .25, s.t1 - .25);
  };
});

// ============ 5 · 03 Recall ============
Scene('recall', (el, s) => {
  const pill = h('div', 'pill', el, `${ICON.search}<span class="q"></span><kbd>/</kbd>`); place(pill, 232, 100, 1456); pill.style.height = '96px'; pill.style.fontSize = '36px';
  const pq = pill.querySelector('.q');
  const res = h('div', 'fill', el);
  const card = (f, x, y, w, hh, parent = res) => { const c = h('div', 'shotcard', parent); place(c, x, y, w, hh); shotImg(c, f); return c; };
  const K = 1.4, CWD = 1040 * K, CX0 = (1920 - CWD) / 2;
  const a1 = card('ask_live_answer.png', CX0, 250, CWD, 90 * K), c1 = card('ask_live_card.png', CX0, 250 + 90 * K + 24, CWD, 80 * K);
  const note1 = h('div', 'badge', res, 'said in Gemini · replaces “I live in Porto for now.” (ChatGPT)'); place(note1, CX0, 250 + 170 * K + 50);
  const c2 = h('div', 'shotcard', res); place(c2, CX0, 250, CWD, 63 * K); const i2 = shotImg(c2, 'ask_exercise_card.png'); Object.assign(i2.style, { width: CWD + 'px', height: (131 * K) + 'px' });
  const note2 = h('div', 'badge', res, 'match: meaning · no shared words'); place(note2, CX0, 250 + 63 * K + 26);
  const sub3 = h('div', 'abs', res, 'Nothing remembered about that yet.'); Object.assign(sub3.style, { left: CX0 + 'px', top: '240px', fontSize: '30px', color: 'var(--fg2)' });
  const c3 = h('div', 'shotcard', res); place(c3, CX0, 300, CWD, 287 * K * .78); const i3 = shotImg(c3, 'ask_dog_card.png'); Object.assign(i3.style, { width: CWD + 'px', height: (287 * K) + 'px', marginTop: (-287 * K * .02) + 'px' });
  const sc = scrim(el);
  const cap1 = Caption(el, '03 · Recall', 'Ask it anything.\nIt answers from your own words.');
  const cap2 = Caption(el, '03 · Recall', 'It understands meaning, not just words.');
  const cap3 = Caption(el, '03 · Recall', "When it doesn't know, it says so.");
  // any AI: Alt+M in a web chat, MCP in a coding agent
  const split = h('div', 'fill', el);
  const gpt = h('div', 'chat', split, `<div class="chat-h">${logo('ChatGPT', 'logo')}<span class="who silk">ChatGPT</span><span class="title">New chat</span></div>
    <div class="composer" style="height:auto;min-height:72px;align-items:flex-start;padding:18px 26px;border-radius:24px;font-size:19px;line-height:1.45"><span class="tx" style="white-space:pre-wrap"></span></div>`);
  place(gpt, 80, 120, 860, 700);
  const gtx = gpt.querySelector('.tx');
  const alt = h('div', 'kbd', split, 'Alt'), mk = h('div', 'kbd', split, 'M'); place(alt, 330, 330); place(mk, 500, 330);
  const term = h('div', 'term', split, `<div class="th">${logo('Claude Code', '')}<span>Claude Code · ~/pantry</span></div><div class="tb"></div>`);
  place(term, 980, 120, 860, 700);
  const tb = term.querySelector('.tb');
  const cap4 = Caption(el, '03 · Recall', 'Alt+M in any web chat. MCP for coding agents.');
  const chap = Chapter(el, { num: '03', name: 'Recall', line: 'Any AI can ask.', section: 'Operation', page: 'p. 4', note: 'Parts 1 · 2' });
  const QS = [[T.ask1, T.ans1], [T.ask2, T.ans2], [T.ask3, T.ans3]];
  return (lt, t) => {
    chap.render(lt, 1.6);
    const aOn = t < T.split; show(pill, aOn); show(res, aOn); show(sc, aOn);
    if (aOn) {
      const pi = E.outExpo(inv(s.t0 + 1.3, s.t0 + 1.9, t)), po = E.inCubic(inv(T.split - .3, T.split, t));
      tf(pill, { y: (1 - pi) * -40, o: pi * (1 - po) });
      let q = QS[0]; for (const x of QS) if (t >= x[0].t0 - .3) q = x;
      const n = typed(q[0], t), done = t >= q[1];
      htm(pq, n ? esc(q[0].text.slice(0, n)) + (done ? '' : '<span class="caret"></span>') : '<span class="ph">Ask your memory — where do I live, my gpu…</span>');
      tf(pill, { s: 1 - .015 * Math.exp(-Math.max(0, t - q[1] + .1) * 10) * (t >= q[1] - .1 ? 1 : 0), y: (1 - pi) * -40, o: pi * (1 - po) });
      const grp = (els, at, until) => els.forEach((e, i) => { const p = E.outExpo(inv(at + i * .18, at + .6 + i * .18, t)), o = E.inCubic(inv(until - .25, until, t)); tf(e, { y: (1 - p) * 40 - o * 20, o: p * (1 - o), s: .97 + .03 * p }); });
      grp([a1, c1, note1], T.ans1, T.ask2.t0 - .15); grp([c2, note2], T.ans2, T.ask3.t0 - .15); grp([sub3, c3], T.ans3, T.split);
    }
    cap1.render(t, T.ans1 + .2, T.ask2.t0 - .2); cap2.render(t, T.ans2 + .15, T.ask3.t0 - .2); cap3.render(t, T.ans3 + .15, T.split - .25);
    const sOn = t >= T.split; show(split, sOn);
    if (sOn) {
      [gpt, term].forEach((w, i) => { const p = E.outExpo(inv(T.split + i * .1, T.split + .6 + i * .1, t)); tf(w, { y: (1 - p) * 60, o: p }); });
      [[alt, T.altKey], [mk, T.mKey]].forEach(([k, at]) => { const p = E.outBack(inv(at - .25, at, t)), dn = t >= at && t < at + .5 ? 1 : 0, o = 1 - inv(T.brief.t0 + .5, T.brief.t0 + .8, t); tf(k, { y: (1 - p) * 30 + dn * 6, o: clamp(p * 2) * o, s: .9 + .1 * p }); });
      const nb = typed(T.brief, t);
      htm(gtx, nb ? esc(T.brief.text.slice(0, nb)) : '<span class="ph">Ask anything</span>');
      const nc = typed(T.ccType, t);
      let o = `<span class="pr">❯</span> ${esc(T.ccType.text.slice(0, nc))}${t < T.ccTool ? '<span class="caret"></span>' : ''}`;
      if (t >= T.ccTool) o += `\n\n<span class="ok">●</span> mindbaton · recall <span class="dim">(query: "where do I live")</span>`;
      if (t >= T.ccAns) o += `\n  <span class="dim">⎿</span> Answer: You live in Lisbon.\n    <span class="dim">[47] I moved to Lisbon last weekend, the flat\n    is in Alcântara (event; Gemini; 3 Sep 2026)</span>`;
      htm(tb, o);
    }
    cap4.render(t, T.ccAns + .1, s.t1 - .25);
  };
});
