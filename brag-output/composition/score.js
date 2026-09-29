// The score: music and effects written as one piece, in D minor at 120 BPM, rendered offline from timeline.js.
// Every keystroke, LED and impact in the film has its sound at the same number.
async function renderScore() {
  const SR = 48000, DUR = TL.DUR + 1.5, { T, BEAT } = TL;
  const ac = new OfflineAudioContext(2, Math.ceil(SR * DUR), SR);
  const r = TL.rng(2024);
  const hz = m => 440 * Math.pow(2, (m - 69) / 12);
  // ---- master: glue compressor → limiter-ish; a shared reverb ----
  const master = ac.createGain(); master.gain.value = .8;
  const comp = ac.createDynamicsCompressor(); Object.assign(comp, {}); comp.threshold.value = -16; comp.ratio.value = 3; comp.attack.value = .01; comp.release.value = .2;
  const lim = ac.createDynamicsCompressor(); lim.threshold.value = -3; lim.ratio.value = 20; lim.attack.value = .002; lim.release.value = .08;
  master.connect(comp).connect(lim).connect(ac.destination);
  const verb = ac.createConvolver(), irl = SR * 2.8, ir = ac.createBuffer(2, irl, SR);
  for (let c = 0; c < 2; c++) { const d = ir.getChannelData(c); for (let i = 0; i < irl; i++) d[i] = (r() * 2 - 1) * Math.pow(1 - i / irl, 3.2); }
  verb.buffer = ir; const vret = ac.createGain(); vret.gain.value = .32; verb.connect(vret).connect(master);
  const bus = (g, rev = 0) => { const n = ac.createGain(); n.gain.value = g; n.connect(master); if (rev) { const s = ac.createGain(); s.gain.value = rev; n.connect(s).connect(verb); } return n; };
  const noiseBuf = ac.createBuffer(1, SR * 2, SR); { const d = noiseBuf.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = r() * 2 - 1; }
  const noise = (t, d, out, { type = 'highpass', f = 6000, q = .7, g = .3, a = .001, f2 } = {}) => {
    const s = ac.createBufferSource(); s.buffer = noiseBuf; s.loop = true;
    const fl = ac.createBiquadFilter(); fl.type = type; fl.frequency.setValueAtTime(f, t); if (f2) fl.frequency.exponentialRampToValueAtTime(f2, t + d); fl.Q.value = q;
    const e = ac.createGain(); e.gain.setValueAtTime(0, t); e.gain.linearRampToValueAtTime(g, t + a); e.gain.exponentialRampToValueAtTime(.0001, t + d);
    s.connect(fl).connect(e).connect(out); s.start(t, r() * 1.5); s.stop(t + d + .05);
  };
  const tone = (t, d, freq, out, { type = 'sine', g = .2, a = .005, f, fq = 1, fend, detune = 0 } = {}) => {
    const o = ac.createOscillator(); o.type = type; o.frequency.setValueAtTime(freq, t); o.detune.value = detune;
    const e = ac.createGain(); e.gain.setValueAtTime(0, t); e.gain.linearRampToValueAtTime(g, t + a); e.gain.exponentialRampToValueAtTime(.0001, t + d);
    let n = o;
    if (f) { const fl = ac.createBiquadFilter(); fl.type = 'lowpass'; fl.frequency.setValueAtTime(f, t); if (fend) fl.frequency.exponentialRampToValueAtTime(fend, t + d); fl.Q.value = fq; n = o.connect(fl); }
    n.connect(e).connect(out); o.start(t); o.stop(t + d + .05);
  };
  // ---- harmony: Dm9 · Bbmaj9 · Fmaj7 · Cadd9, one chord per bar ----
  const CH = [[50, 57, 60, 64, 65], [46, 53, 57, 60, 62], [41, 53, 57, 60, 64], [48, 55, 60, 62, 64]];
  const chordAt = t => CH[Math.floor(t / 2) % 4];
  const ARP = [0, 2, 3, 4, 3, 2, 1, 2];
  // sections: which layers play [start, end, {pad, bass, hats, clap, arp, cutoff}]
  const SEC = [
    [8, 12, { pad: .9, bass: .6, arp: 0, hats: 0, clap: 0, cut: 1800 }], [12, 16, { pad: 1, bass: 1, arp: .6, hats: .4, clap: 0, cut: 2600 }],
    [16, 30, { pad: .7, bass: 1, arp: .8, hats: 1, clap: .7, cut: 2600 }], [30, 48, { pad: .8, bass: 1, arp: .9, hats: 1, clap: .8, cut: 3000 }],
    [48, 64, { pad: .8, bass: 1, arp: 1, hats: 1, clap: .8, cut: 3400 }], [64, 69, { pad: .7, bass: 1, arp: .6, hats: .8, clap: .6, cut: 1200 }],
    [74, 80, { pad: 1, bass: 1, arp: 1, hats: 1, clap: 1, cut: 4200 }], [80, 86, { pad: .9, bass: 0, arp: .35, hats: 0, clap: 0, cut: 1400 }],
    [86, 88, { pad: .8, bass: .5, arp: .5, hats: 0, clap: 0, cut: 2000 }], [88, 102, { pad: .8, bass: 1, arp: .9, hats: 1, clap: .8, cut: 3200 }],
    [102, 106, { pad: .8, bass: 1, arp: .9, hats: 1, clap: .8, cut: 3600 }]];
  const padB = bus(.11, .55), bassB = bus(.34, .05), arpB = bus(.075, .45), hatB = bus(.05, .1), clapB = bus(.14, .35), kickB = bus(.62), sfx = bus(.26, .3), keyB = bus(.13, .12), hitB = bus(.5, .6);
  for (const [a, b, L] of SEC) {
    for (let bar = a; bar < b - 1e-6; bar += 2) {
      const ch = chordAt(bar), d = Math.min(2, b - bar);
      if (L.pad) ch.forEach((m, k) => [-9, 9].forEach(dt => tone(bar, d + .6, hz(m + 12 * (k === 0 ? 0 : 0)), padB, { type: 'sawtooth', g: .05 * L.pad, a: .35, f: L.cut, fend: L.cut * .6, detune: dt })));
      for (let s = 0; s < d / BEAT * 2 - 1e-6; s++) {  // eighth notes
        const t = bar + s * BEAT / 2;
        if (L.bass && s % 2 === 0 || L.bass && s % 4 === 3) tone(t, .22, hz(ch[0] - 12), bassB, { type: 'triangle', g: .5 * L.bass, a: .004, f: 900 });
        if (L.hats && s % 2 === 1) noise(t, .06, hatB, { f: 8000, g: .5 * L.hats });
        if (L.arp) { const m = ch[1 + (ARP[s % 8] % 4)] + 12; tone(t, .28, hz(m), arpB, { type: 'square', g: .12 * L.arp, a: .003, f: 3200, fend: 700 }); }
      }
      if (L.clap) [1, 3].forEach(k => { const t = bar + k * BEAT; if (t < b) { noise(t, .18, clapB, { type: 'bandpass', f: 1600, q: 1.2, g: .8 * L.clap }); } });
    }
  }
  for (const k of T.kicks) { tone(k, .38, 130, kickB, { g: 1, a: .002 }); const o = kickB; const osc = ac.createOscillator(); osc.frequency.setValueAtTime(140, k); osc.frequency.exponentialRampToValueAtTime(42, k + .16); const e = ac.createGain(); e.gain.setValueAtTime(.9, k); e.gain.exponentialRampToValueAtTime(.0001, k + .4); osc.connect(e).connect(o); osc.start(k); osc.stop(k + .45); }
  // ---- the hook: a rising cluster over a swarm of keys, then silence at 7.6 ----
  [38, 45, 50, 51, 57].forEach((m, i) => { const o = ac.createOscillator(); o.type = 'sawtooth'; o.frequency.setValueAtTime(hz(m), 0); o.frequency.exponentialRampToValueAtTime(hz(m + 5), 7.55);
    const fl = ac.createBiquadFilter(); fl.type = 'lowpass'; fl.frequency.setValueAtTime(300, 0); fl.frequency.exponentialRampToValueAtTime(3500, 7.5);
    const e = ac.createGain(); e.gain.setValueAtTime(0, 0); e.gain.linearRampToValueAtTime(.022, 3); e.gain.linearRampToValueAtTime(.05, 7.5); e.gain.linearRampToValueAtTime(0, 7.6);
    o.connect(fl).connect(e).connect(master); o.start(0); o.stop(7.7); });
  noise(3.5, 4.1, sfx, { type: 'bandpass', f: 400, f2: 6000, q: 2, g: .25, a: 3.9 });
  const tick = (t, g = 1) => { noise(t, .025 + r() * .02, keyB, { type: 'bandpass', f: 2500 + r() * 2500, q: 1.5, g: .5 * g }); tone(t, .02, 180 + r() * 80, keyB, { g: .15 * g }); };
  T.hookType.at.forEach(t => t < 2.1 && tick(t, 1.1));
  for (let t = 2.0; t < 6.2; t += Math.max(.012, .09 - (t - 2) * .02)) tick(t + r() * .02, .35 + (t - 2) * .08);
  for (let t = 6.3; t < 7.4; t += .02) tick(t, .25);
  // ---- typing everywhere else ----
  for (const run of [T.gemType, T.ask1, T.ask2, T.ask3, T.ccType, T.cmd]) run.at.forEach(t => tick(t, .9));
  T.brief.at.forEach((t, i) => i % 6 === 0 && tick(t, .35));
  // ---- UI and story sounds, pitched into the key ----
  const pluck = (t, m, g = .25) => { tone(t, .5, hz(m), sfx, { type: 'triangle', g, a: .002 }); tone(t, .25, hz(m + 12), sfx, { type: 'sine', g: g * .4, a: .002 }); };
  const PENT = [62, 65, 67, 69, 72, 74, 77, 79, 81, 84];
  T.leds1.forEach((t, i) => pluck(t, PENT[i], .18)); T.leds2.forEach((t, i) => pluck(t, PENT[i] + 5, .15));
  T.cards.forEach((t, i) => pluck(t, PENT[i % 6] + 12, .12));
  T.messyAt.forEach((t, i) => pluck(t + .35, 74 + i * 3, .14));
  [T.ans1, T.ans2].forEach(t => { pluck(t, 81, .2); pluck(t + .08, 86, .15); }); pluck(T.ans3, 62, .18);
  T.rowsIn.forEach((t, i) => pluck(t, 69 + i * 2, .1)); pluck(T.topicPop, 86, .2); pluck(T.topicPop + .1, 81, .14);
  T.steps.forEach((t, i) => pluck(t, PENT[i] + 12, .1));
  T.rows.forEach((t, i) => pluck(t, 74 + i * 2, .08)); T.extraAt.forEach((t, i) => pluck(t, 79 + i * 2, .1));
  const click = t => { noise(t, .03, sfx, { type: 'bandpass', f: 3000, q: 2, g: .6 }); tone(t, .05, 900, sfx, { g: .15 }); };
  [T.gemSend, T.click1, T.click2, T.enter].forEach(click);
  const thud = (t, g = 1) => { const o = ac.createOscillator(); o.frequency.setValueAtTime(110, t); o.frequency.exponentialRampToValueAtTime(38, t + .3); const e = ac.createGain(); e.gain.setValueAtTime(.8 * g, t); e.gain.exponentialRampToValueAtTime(.0001, t + .6); o.connect(e).connect(hitB); o.start(t); o.stop(t + .65); noise(t, .12, hitB, { type: 'lowpass', f: 1500, g: .3 * g }); };
  const whoosh = (t, d = .5, g = .3) => noise(t, d, sfx, { type: 'bandpass', f: 500, f2: 5000, q: 1.2, g, a: d * .7 });
  const bell = (t, root = 62, g = .22) => [0, 7, 12, 16, 19].forEach((iv, i) => tone(t, 3.5 - i * .4, hz(root + iv), hitB, { type: 'sine', g: g / (1 + i * .6), a: .002 }));
  // chapter cards: a soft thud and an amber LED blip
  [16, 30, 48, 64, 80, 86].forEach(t => { thud(t, .45); pluck(t + .34, 86, .08); });
  whoosh(T.fall - .1, .3, .2); thud(T.land, 1.2); bell(T.land, 62, .16); bell(T.lockup + .3, 74, .12);
  whoosh(T.runOff, .6, .35); whoosh(T.batonIn, .5, .25); whoosh(T.batonOut + .1, .5, .3); pluck(T.highlight, 81, .15);
  pluck(T.memLines[0], 74, .15); [T.memTick, T.count].forEach(t => { pluck(t, 86, .16); click(t); });
  // the Baton chapter: the chat runs out of room → a drone; the key → silence → impact; the receipt prints; the relay drop
  const drone = ac.createOscillator(); drone.type = 'sawtooth'; drone.frequency.value = hz(38);
  const dfl = ac.createBiquadFilter(); dfl.type = 'lowpass'; dfl.frequency.value = 400; const dg = ac.createGain();
  dg.gain.setValueAtTime(0, 68.8); dg.gain.linearRampToValueAtTime(.06, 69.3); dg.gain.linearRampToValueAtTime(.08, 71.3); dg.gain.linearRampToValueAtTime(0, 71.45);
  dg.gain.setValueAtTime(0, 71.6); dg.gain.linearRampToValueAtTime(.05, 73.9); dg.gain.linearRampToValueAtTime(0, 74.0);
  drone.connect(dfl).connect(dg).connect(master); drone.start(68.8); drone.stop(74.1);
  noise(T.limit, .8, sfx, { type: 'lowpass', f: 900, g: .25 }); tone(T.limit, 1.2, hz(51), hitB, { type: 'triangle', g: .12 });
  click(T.press); thud(T.press, 1.3); bell(T.press + .02, 50, .12);
  for (let t = T.printAt; t < T.printEnd; t += .028) noise(t, .018, sfx, { type: 'bandpass', f: 2200 + r() * 900, q: 3, g: .22 });
  noise(T.tear, .25, sfx, { type: 'highpass', f: 2500, g: .35, a: .005 });
  noise(72.0, 2.0, sfx, { type: 'bandpass', f: 300, f2: 8000, q: 1.5, g: .3, a: 1.9 });
  thud(T.run, 1.5); bell(T.run, 62, .2); whoosh(T.run + .2, .8, .3); whoosh(T.run + .95, .4, .25);
  pluck(T.gptMsg, 74, .15); T.gptType.at.forEach((t, i) => i % 4 === 0 && tick(t, .3));
  // forget: a reverse swell into a dissolve
  noise(T.gone - .5, .6, sfx, { type: 'bandpass', f: 4000, f2: 400, q: 1, g: .25, a: .55 }); tone(T.gone, 1.4, hz(74), hitB, { type: 'sine', g: .1 });
  pluck(T.still, 81, .2); pluck(T.still + .1, 74, .16);
  for (let t = T.rows[4] + .9; t < T.rows[4] + 1.3; t += .03) noise(t, .02, sfx, { type: 'bandpass', f: 3000, q: 2, g: .12 });
  // the end card: the home chord rings out
  thud(T.end, 1.2); [50, 57, 60, 64, 65, 69].forEach((m, i) => [-7, 7].forEach(dt => tone(T.end, 6.5, hz(m), padB, { type: 'sawtooth', g: .07, a: .02, f: 2600, fend: 500, detune: dt })));
  bell(T.end, 62, .22); bell(T.endMark, 74, .1); pluck(T.blink2, 86, .08);
  const buf = await ac.startRendering();
  // 16-bit WAV
  const n = buf.length, L = buf.getChannelData(0), R = buf.getChannelData(1), ab = new ArrayBuffer(44 + n * 4), v = new DataView(ab);
  const ws = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  ws(0, 'RIFF'); v.setUint32(4, 36 + n * 4, true); ws(8, 'WAVE'); ws(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 2, true);
  v.setUint32(24, SR, true); v.setUint32(28, SR * 4, true); v.setUint16(32, 4, true); v.setUint16(34, 16, true); ws(36, 'data'); v.setUint32(40, n * 4, true);
  let peak = 0; for (let i = 0; i < n; i++) peak = Math.max(peak, Math.abs(L[i]), Math.abs(R[i]));
  const k = peak > .98 ? .98 / peak : 1;
  for (let i = 0, o = 44; i < n; i++, o += 4) { v.setInt16(o, clampS(L[i] * k) * 32767, true); v.setInt16(o + 2, clampS(R[i] * k) * 32767, true); }
  function clampS(x) { return Math.max(-1, Math.min(1, x)); }
  const b64 = await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result.split(',')[1]); fr.readAsDataURL(new Blob([ab])); });
  return { b64, peak };
}
