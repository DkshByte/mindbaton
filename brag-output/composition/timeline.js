// One clock for picture and sound. 120 BPM: a beat is 0.5 s, a bar is 2 s, and every scene cut sits on a bar line.
// The film (index.html) and the score (score.html) both read this file, so a keystroke, a click and its sound share
// one number.
(function (root) {
  const BPM = 120, BEAT = 60 / BPM, BAR = 4 * BEAT, DUR = 112;

  function rng(seed) {  // mulberry32: the same "random" on every render
    return function () {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  // Human typing: each character gets its own time; spaces and punctuation breathe a little.
  function typing(text, t0, cps, seed = 1) {
    const r = rng(seed), at = [];
    let t = t0;
    for (const c of text) {
      at.push(t);
      let d = (1 / cps) * (0.55 + r() * 0.9);
      if (c === ' ') d *= 1.2;
      if (/[.,!?…:]/.test(c)) d *= 2.4;
      t += d;
    }
    return { text, at, t0, end: t };
  }

  const S = {  // scenes [start, end)
    hook: [0, 8], reveal: [8, 16], capture: [16, 30], remember: [30, 48], recall: [48, 64],
    baton: [64, 80], forget: [80, 86], yours: [86, 102], outro: [102, 112],
  };

  const T = {};
  // 1 · the wall of you
  T.hookType = typing("Hi! I'm Maya. I'm vegetarian, I live in Lisbon, I have a cat named Miso…", 0.3, 17, 7);
  T.hookZoom = [2.0, 2.5, 3.0, 3.5, 4.0];
  T.hookLine1 = 4.6; T.hookLine2 = 5.2; T.hookErase = 6.3; T.hookBlack = 7.6;
  // 2 · Baton
  T.fall = 7.78; T.land = 8.0; T.blink1 = 8.7; T.lean = 9.0; T.tell1 = 9.5; T.tell2 = 10.5;
  T.lockup = 12.0; T.sub = 13.0; T.runOff = 15.2;
  // 3 · capture
  T.cap = 16;
  T.gemType = typing("I'm vegetarian. what pastries are there besides pastel de nata?", 17.95, 33, 11);
  T.gemSend = T.gemType.end + 0.18;
  T.highlight = T.gemSend + 0.5; T.batonIn = T.highlight + 0.15; T.grab = T.batonIn + 0.5; T.batonOut = T.grab + 0.08;
  T.memIn = 22.4; T.memLines = [22.62, 22.9, 23.18, 23.46]; T.memTick = 23.5;
  T.sockets = 25.6; T.leds1 = Array.from({ length: 10 }, (_, i) => 26.0 + i * 0.125);
  T.leds2 = Array.from({ length: 10 }, (_, i) => 27.5 + i * 0.125);
  // 4 · remember
  T.rem = 30; T.youIn = 31.6; T.cards = Array.from({ length: 8 }, (_, i) => 32.0 + i * 0.25);
  T.messy = 35.6; T.messyAt = [36.2, 36.95, 37.7];
  T.change = 40.0; T.strike = 40.8; T.newLine = 41.3;
  T.topics = 43.6; T.rowsIn = [43.7, 43.85, 44.0]; T.converge = 44.6; T.topicPop = 45.05;
  T.map = 46.0;
  // 5 · recall
  T.rec = 48;
  T.ask1 = typing("where do I live?", 49.85, 17, 21); T.ans1 = T.ask1.end + 0.25;
  T.ask2 = typing("what exercise do I do?", 53.75, 22, 22); T.ans2 = T.ask2.end + 0.22;
  T.ask3 = typing("what's my dog's name?", 56.55, 22, 23); T.ans3 = T.ask3.end + 0.22;
  T.split = 59.6; T.altKey = 60.2; T.mKey = 60.36;
  T.brief = typing("[mindbaton] What I know about the user from their past chats with ChatGPT, Claude, Claude Code, Cursor, Gemini and Perplexity (their own words; newest wins):\n- Maya — vegetarian and product designer at Kestrel Mobility; lives in Lisbon\n- Working on: Wayfinder, Pantry (meal planner), onboarding, portfolio site\n- Uses: Raycast, Arc browser, Cloudflare Pages, Astro, Figma, Obsidian…", 60.5, 260, 31);
  T.ccType = typing("where do I live?", 60.4, 19, 32); T.ccTool = T.ccType.end + 0.15; T.ccAns = T.ccTool + 0.45;
  // 6 · baton
  T.bat = 64; T.chats = 65.6; T.spot = 66.2; T.claude = 68.0; T.limit = 69.0;
  T.keyUp = 70.4; T.press = 71.5; T.printAt = 71.7; T.printEnd = 73.3; T.tear = 73.6; T.run = 74.0; T.runEnd = 76.0;
  T.gpt = 76.0; T.gptMsg = 76.3;
  T.gptType = typing("Sure. Model membership as person ↔ household (many-to-many) instead of a single household per user.", 76.9, 48, 41);
  // 7 · forget
  T.fgt = 80; T.panelIn = 81.1; T.click1 = 82.0; T.click2 = 82.7; T.gone = 82.75; T.count = 83.0; T.rebuild = 83.45; T.still = 84.6;
  // 8 · yours
  T.yrs = 86; T.xpl = 87.6; T.close = 88.0; T.sheet = 91.6; T.rows = Array.from({ length: 5 }, (_, i) => 92.1 + i * 0.25);
  T.model = 95.6; T.extras = 98.4; T.extraAt = Array.from({ length: 4 }, (_, i) => 98.55 + i * 0.25);
  // 9 · install + end card
  T.install = 102; T.cmd = typing("git clone https://github.com/DkshByte/mindbaton && cd mindbaton && ./install.sh", 102.25, 58, 51);
  T.enter = T.cmd.end + 0.12; T.steps = Array.from({ length: 9 }, (_, i) => 104.0 + i * 0.125);
  T.end = 106; T.endTag = 106.5; T.endMark = 107.0; T.endFoot = 107.6; T.blink2 = 109.8; T.fade = 111.2;

  // The kick drum's schedule is the film's pulse: the score plays it, the picture breathes with it.
  const kicks = [];
  const every = (a, b, step) => { for (let t = a; t < b - 1e-6; t += step) kicks.push(+t.toFixed(3)); };
  every(8, 12, 1);            // reveal: half time
  every(12, 16, BEAT);
  every(16, 69, BEAT);        // the guide grooves
  every(74, 80, BEAT);        // the relay drop
  every(88, 106, BEAT);       // yours → install
  T.kicks = kicks;
  T.kickEnv = t => {          // 0..1, decays over 0.22 s after each kick
    let lo = 0, hi = kicks.length - 1, k = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (kicks[m] <= t) { k = m; lo = m + 1; } else hi = m - 1; }
    return k < 0 ? 0 : Math.exp(-(t - kicks[k]) / 0.22);
  };

  root.TL = { BPM, BEAT, BAR, DUR, S, T, rng, typing };
})(typeof window !== 'undefined' ? window : globalThis);
