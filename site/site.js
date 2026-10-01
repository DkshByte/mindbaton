// Mindbaton's website: copy buttons and tabs. Everything works without it; nothing is fetched.
const status = document.getElementById("status");

async function copy(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch {}
  const t = Object.assign(document.createElement("textarea"), { value: text });
  t.setAttribute("readonly", ""); t.style.cssText = "position:fixed;opacity:0";
  document.body.append(t); t.select();
  const ok = document.execCommand("copy"); t.remove(); return ok;
}

document.querySelectorAll("[data-copy]").forEach((b) => {
  const label = b.querySelector("[data-label]"), was = label.textContent;
  b.addEventListener("click", async () => {
    const ok = await copy(document.querySelector(b.dataset.copy).textContent.trim());
    label.textContent = ok ? "Copied" : "Select and copy";
    b.classList.toggle("done", ok);
    status.textContent = ok ? "Copied to the clipboard." : "Couldn't copy. Select the text and copy it.";
    clearTimeout(b.t); b.t = setTimeout(() => { label.textContent = was; b.classList.remove("done"); }, 1800);
  });
});

// tabs: the app's segmented control, with arrow keys, Home and End
document.querySelectorAll('[role="tablist"]').forEach((list) => {
  const tabs = [...list.querySelectorAll('[role="tab"]')];
  const pick = (tab, focus) => {
    tabs.forEach((t) => {
      const on = t === tab;
      t.setAttribute("aria-selected", on); t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
    });
    if (focus) tab.focus();
  };
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => pick(t));
    t.addEventListener("keydown", (e) => {
      const j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
      if (j === undefined) return;
      e.preventDefault(); pick(tabs[(j + tabs.length) % tabs.length], true);
    });
  });
});

// Perspective mode (Human / Agent) toggle syncing
const setPerspective = (mode) => {
  const isAgent = mode === "agent";
  document.querySelectorAll('[data-mode="human"]').forEach((b) => {
    b.setAttribute("aria-selected", !isAgent);
    b.tabIndex = isAgent ? -1 : 0;
  });
  document.querySelectorAll('[data-mode="agent"]').forEach((b) => {
    b.setAttribute("aria-selected", isAgent);
    b.tabIndex = isAgent ? 0 : -1;
  });
  const vHuman = document.getElementById("view-human");
  const vAgent = document.getElementById("view-agent");
  if (vHuman) vHuman.hidden = isAgent;
  if (vAgent) vAgent.hidden = !isAgent;
  window.scrollTo(0, 0);
};

document.querySelectorAll("[data-mode]").forEach((btn) => {
  btn.addEventListener("click", () => setPerspective(btn.dataset.mode));
});

// Perspective mode URL trigger: ?mode=agent or #agent opens the Agent view immediately
try {
  const p = new URLSearchParams(location.search);
  if (p.get("mode") === "agent" || location.hash === "#agent") {
    setPerspective("agent");
  }
} catch {}

// ── Motion: the product doing its job. Plays only on screen; reduced motion keeps each demo's finished state. ──
const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const onScreen = (el, fn, once = true) => new IntersectionObserver((es, o) => es.forEach((e) => {
  e.target.inView = e.isIntersecting;
  if (e.isIntersecting) { fn(e.target); if (once) o.unobserve(e.target); }
}), { threshold: .35 }).observe(el);
const type = async (el, text, ms) => { el.classList.add("caret"); el.textContent = ""; for (const ch of text) { el.textContent += ch; await wait(ms); } el.classList.remove("caret"); };
const rise = (el) => { el.classList.remove("gone", "rise"); void el.offsetWidth; el.classList.add("rise"); };
const aurora = document.querySelector(".aurora");
const pulse = () => { aurora.classList.add("pulse"); setTimeout(() => aurora.classList.remove("pulse"), 1400); };

if (!still) {
  document.documentElement.classList.add("motion");
  document.querySelectorAll(".sec-h, .step, .tabs, .kinds, .facts, .inst, .qa, .hero-shot + .note").forEach((el) => {
    el.classList.add("reveal"); onScreen(el, (t) => t.classList.add("in"));
  });
  document.querySelectorAll(".kinds .chips").forEach((c) => { c.classList.add("reveal"); [...c.children].forEach((li, i) => li.style.setProperty("--n", i)); onScreen(c, (t) => t.classList.add("in")); });

  // hero relay: tell one AI → the baton carries it → another AI knows
  const R = document.querySelector(".relay");
  const S = [
    { f: ["ChatGPT", "openai.svg", "m", "GPT-5.5"], say: "I'm vegetarian, by the way.", k: "Fact", t: ["Claude", "claude-color.svg", "c", "Opus 5"],
      ask: "Plan my dinners for this week.", reply: "Seven vegetarian dinners, starting Monday with a chickpea and spinach curry." },
    { f: ["Gemini", "gemini-color.svg", "c", "Gemini 3 Pro"], say: "I prefer pnpm over npm.", k: "Preference", t: ["Cursor", "cursor.svg", "m", "Sonnet 5"],
      ask: "Add a date library to the app.", reply: "Running pnpm add date-fns, since this project uses pnpm." },
    { f: ["Claude", "claude-color.svg", "c", "Opus 5"], say: "I moved to Lisbon last weekend.", k: "Fact", t: ["Perplexity", "perplexity-color.svg", "c", "sonar-pro"],
      ask: "Find a running club near me.", reply: "Three running clubs in Lisbon meet on Saturday mornings, two along the river." },
  ];
  const q = (sel, root = R) => root.querySelector(sel);
  const [from, mem, to] = R.querySelectorAll(".rl-card"), links = R.querySelectorAll(".rl-link");
  const who = (card, [name, icon, kind, model]) => {
    card.querySelectorAll("[data-ai]").forEach((e) => (e.textContent = name));
    const lg = q("[data-logo]", card); lg.className = "lg " + kind; lg.style.setProperty("--i", `url(icons/${icon})`);
    const m = q("[data-model]", card); if (m) m.textContent = model;
  };
  const carry = async (l) => { l.classList.remove("go"); void l.offsetWidth; l.classList.add("go"); await wait(620); };
  const until = async () => { while (!R.inView || document.hidden) await wait(400); };
  let n = 0;
  onScreen(R, async () => {
    if (R.playing) return;
    R.playing = true;
    for (;;) {
      const s = S[n++ % S.length], say = q("[data-say]", from), row = q(".rl-row", mem);
      const ask = q("[data-ask]", to), reply = q("[data-reply]", to), used = q(".rl-used", to);
      [row, ask, reply, used].forEach((e) => e.classList.add("gone"));
      who(from, s.f); who(mem, s.f); who(to, s.t);
      q("[data-kind]", mem).textContent = s.k; q("[data-say]", mem).textContent = s.say;
      await until(); await wait(500);
      await type(say, s.say, 38); await wait(350);
      await carry(links[0]); rise(row); pulse(); await wait(1100);
      await carry(links[1]); ask.textContent = s.ask; rise(ask); await wait(700);
      reply.innerHTML = '<span class="dots"><i></i><i></i><i></i></span>'; rise(reply); await wait(900);
      reply.textContent = "";
      for (const w of s.reply.split(" ")) { reply.textContent += (reply.textContent ? " " : "") + w; await wait(55); }
      rise(used); await wait(3200);
      await until();
    }
  }, false);

  // recently: new memories arrive with the app's rise
  const list = document.querySelector("#how .rows");
  const NEW = [
    ["claude-color.svg", "c", "I prefer fewer modes and bigger touch targets over a dense UI", "Preference", "Wayfinder trip planner critique", "Opus 5"],
    ["cursor.svg", "m", "I prefer pnpm over npm", "Preference", "Pantry recipe import", "GPT-5 Codex"],
    ["openai.svg", "m", "I'm rebuilding my portfolio site with Astro", "Fact", "Portfolio site in Astro", "GPT-5.5"],
  ];
  onScreen(list, async () => {
    for (const [icon, kind, txt, k, chat, model] of NEW) {
      await wait(2200);
      const li = document.createElement("li"); li.className = "row";
      li.innerHTML = `<span class="lg ${kind}" style="--i:url(icons/${icon})"></span><div><p class="txt"></p><p class="meta"><span class="k"></span><span></span><span class="model"></span></p></div><time>now</time>`;
      li.querySelector(".txt").textContent = txt; const m = li.querySelectorAll(".meta span");
      m[0].textContent = k; m[1].textContent = chat; m[2].textContent = model;
      list.prepend(li); rise(li); list.lastElementChild.remove();
      [...list.querySelectorAll("time")].slice(1).forEach((t) => { if (t.textContent === "now") t.textContent = "1m"; });
    }
  });

  // every AI knows: the question types itself, the answer lands, the old fact is struck
  const ask = document.querySelector(".ask"), qtext = ask.querySelector(".search span"), ans = ask.querySelector(".answer");
  const rows = ans.querySelectorAll(".row");
  qtext.textContent = ""; ans.classList.add("gone", "fadeable");
  onScreen(ask, async () => {
    await wait(300); await type(qtext, "where do I live", 70); await wait(350);
    ans.classList.remove("gone"); rise(ans); rows.forEach((r) => r.classList.add("gone"));
    await wait(450); rise(rows[0]); await wait(500); rise(rows[1]); await wait(250); rows[1].classList.add("strike");
  });

  // pass the baton: the meter fills to red, then the baton hops to the next AI
  const pick = document.querySelector(".pick"), meter = pick.querySelector(".meter"), bar = meter.querySelector("b"), pct = meter.querySelector("[data-pct]");
  const hot = pick.querySelector(".meta .hot"), passed = pick.querySelector(".passed"), hop = pick.querySelector(".hop"), chip = pick.querySelector("[data-to]");
  meter.classList.add("cool"); bar.style.width = "58%"; pct.textContent = "58%"; hot.classList.add("gone"); passed.classList.add("gone");
  onScreen(pick, async () => {
    await wait(400); bar.style.width = "100%";
    const t0 = performance.now();
    while (performance.now() - t0 < 1600) {
      const p = Math.round(58 + 42 * Math.min(1, (performance.now() - t0) / 1600));
      pct.textContent = p + "%"; meter.classList.toggle("cool", p < 80); await wait(40);
    }
    pct.textContent = "full"; rise(hot); await wait(700);
    const a = pick.getBoundingClientRect(), b = chip.getBoundingClientRect();
    const dx = b.left - a.left - 14 + 8, dy = b.top - a.top - 14 + 5;
    await hop.animate([
      { opacity: 0, transform: "translate(0, 0) rotate(0)" },
      { opacity: 1, transform: `translate(${dx * .5}px, ${dy * .5 - 40}px) rotate(-25deg)`, offset: .5 },
      { opacity: 1, transform: `translate(${dx}px, ${dy}px) rotate(0)`, offset: .92 },
      { opacity: 0, transform: `translate(${dx}px, ${dy}px) scale(.6)` },
    ], { duration: 900, easing: "cubic-bezier(.4, 0, .2, 1)" }).finished;
    chip.classList.add("lit"); rise(passed);
  });
}
