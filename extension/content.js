// memgraph, on every AI chat site: save what you send; Alt+M brings your memory into the message box.
// Live mode: the whole conversation (both sides) is kept in sync, a meter tracks how full the chat's context is, and when
// the chat hits its limit a banner hands it off to another AI — the pack is waiting in that AI's new chat when it opens.
(() => {
  const me = Math.random().toString(36).slice(2);
  document.documentElement.dataset.memgraph = me;          // a newer copy (after an update) takes over from this one
  const current = () => document.documentElement.dataset.memgraph === me;
  const BLOCK = /\[memgraph( handoff)?\][\s\S]*?(\[\/memgraph\1\]|$)/gi;  // our own inserted text is not the user speaking
  const isComposer = el => !!el && (el.tagName === "TEXTAREA" || el.isContentEditable);
  const deep = e => (e.composedPath ? e.composedPath()[0] : e.target);  // the real element, even inside shadow DOM
  let composer = null, last = "", lastAt = 0, warned = false;

  function alive() { try { return !!chrome.runtime?.id; } catch { return false; } }
  async function send(msg) {
    if (!alive()) {
      if (!warned && current()) { warned = true; toast("Mindbaton was updated — refresh this tab to keep saving"); }
      return null;
    }
    try { return await chrome.runtime.sendMessage(msg); } catch { return null; }
  }
  function active() {
    let a = document.activeElement;
    while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement;
    return a;
  }
  const COMPOSER = "#prompt-textarea, div[data-testid='chat-input'][contenteditable='true'], div.ProseMirror[contenteditable='true'], " +
    "rich-textarea .ql-editor[contenteditable='true'], #ask-input[contenteditable='true'], textarea#userInput, " +
    "div[contenteditable='true'][role='textbox'], .ql-editor[contenteditable='true'], div[contenteditable='true'], textarea";
  function box() {
    const a = active();
    if (isComposer(a) && !a.closest("#memgraph-live")) return a;
    if (composer && composer.isConnected) return composer;
    return document.querySelector(COMPOSER);
  }
  const draft = el => (el ? (el.value ?? el.innerText ?? "") : "").replace(BLOCK, "").trim();

  function grab() {
    if (!current()) return;
    const text = draft(box());
    const now = Date.now();
    if (text.length < 8 || (text === last && now - lastAt < 4000)) return;  // "ok", and Enter + click on the same message
    last = text; lastAt = now;
    send({ text, site: location.hostname, title: document.title, url: location.href });
    setTimeout(schedule, 1500);
  }

  addEventListener("focusin", e => { const el = deep(e); if (isComposer(el)) composer = el; }, true);
  addEventListener("keydown", e => {
    if (!current()) return;
    const el = deep(e);
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && isComposer(el)) grab();
    if (e.altKey && e.code === "KeyM") { e.preventDefault(); insertMemory(); }
  }, true);
  addEventListener("pointerdown", e => {
    if (!current()) return;
    const b = (e.composedPath ? e.composedPath() : [e.target]).find(n => n.tagName === "BUTTON");
    const name = b ? ((b.getAttribute("aria-label") || "") + " " + (b.dataset.testid || "") + " " + (b.title || "")).toLowerCase() : "";
    if (b && (b.type === "submit" || /send|submit/.test(name))) grab();
  }, true);
  addEventListener("submit", e => { if (current() && e.target.querySelector && isComposer(e.target.querySelector("textarea, [contenteditable='true']"))) grab(); }, true);
  chrome.runtime.onMessage.addListener((m, _s, reply) => {
    if (!current()) return;
    if (m.insert) insertMemory();
    if (m.meter) { reply(meter); }
    if (m.syncNow) { lastSig = ""; sync().then(() => reply(meter)); return true; }
  });

  function insertText(el, text) {
    el.focus();
    if (el.tagName === "TEXTAREA") {
      const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set;
      set.call(el, text + "\n\n" + el.value.replace(BLOCK, "").trimStart());
      el.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      const range = document.createRange();
      range.selectNodeContents(el); range.collapse(true);
      getSelection().removeAllRanges(); getSelection().addRange(range);
      document.execCommand("insertText", false, text + "\n\n");  // ProseMirror, Quill and Lexical all accept this
    }
  }

  async function insertMemory() {
    const el = box();
    if (!el) return toast("Click into the message box first");
    const r = await send({ context: draft(el) || document.title });
    if (!r || !r.text) return toast(r && r.error ? r.error : "Can't reach Mindbaton");
    insertText(el, r.text);
    toast(`Added what memgraph knows · ${r.text.split("\n").length - 2} lines`);
  }

  function toast(msg) {
    const t = document.createElement("div");
    t.textContent = msg;
    t.style.cssText = "position:fixed;z-index:2147483647;right:20px;bottom:20px;padding:9px 14px;background:#ededef;color:#0b0b0d;" +
      "font:500 13px system-ui,sans-serif;border-radius:9px;box-shadow:0 10px 30px rgba(0,0,0,.35);transition:opacity .3s";
    document.body.append(t);
    setTimeout(() => { t.style.opacity = "0"; setTimeout(() => t.remove(), 300); }, 3200);
  }

  // ---- Live mode ----------------------------------------------------------------------------------------------------
  // Where each site keeps its messages. Selectors are unions across the site's DOM generations; the outermost match wins.
  const ROLE_ATTR = { user: '[data-message-author-role="user"]', ai: '[data-message-author-role="assistant"]' };
  const CHATGPT = { user: '[data-message-author-role="user"], [data-turn="user"]', ai: '[data-message-author-role="assistant"], [data-turn="assistant"]' };
  const COPILOT = { user: '[data-content="user-message"], [data-testid="chat-turn-user"], [class*="group/user-message"]',
                    ai: '[data-content="ai-message"], [data-testid="chat-turn-assistant"], [class*="group/ai-message"]' };
  const READERS = {  // userText/aiText: the part of a message element that is the message (not its hidden headings)
    "chatgpt.com": CHATGPT, "chat.openai.com": CHATGPT, "chat.mistral.ai": ROLE_ATTR,
    "claude.ai": { user: '[data-testid="user-message"]', ai: '[data-testid="assistant-message"], .font-claude-response:not(#markdown-artifact), .font-claude-message' },
    "gemini.google.com": { user: "user-query", ai: "model-response", userText: ".query-text, div.query-content", aiText: "message-content" },
    "www.perplexity.ai": { user: '[class*="group/query"], [class*="group/user-bubble"]', ai: 'div[id^="markdown-content-"]' },
    "chat.deepseek.com": { user: ".ds-message:not(:has(.ds-markdown))", ai: ".ds-message:has(.ds-markdown)" },
    "grok.com": { user: '[data-testid="user-message"], div[id^="response-"].items-end', ai: '[data-testid="assistant-message"], div[id^="response-"].items-start' },
    "copilot.microsoft.com": COPILOT, "copilot.com": COPILOT, "www.copilot.com": COPILOT,
    "poe.com": { user: '[class*="Message_rightSideMessageBubble"], [class*="Message_humanMessageBubble"]', ai: '[class*="Message_leftSideMessageBubble"], [class*="Message_botMessageBubble"]' },
    "aistudio.google.com": { user: 'ms-chat-turn:has([data-turn-role="User"])', ai: 'ms-chat-turn:has([data-turn-role="Model"])' },
  };
  const READER = READERS[location.hostname];
  const ANY = READER ? READER.user + ", " + READER.ai : null;
  // "This chat is full" / "you're out of messages" across sites. Only text outside the messages is checked, so talking about limits doesn't trip it.
  const LIMIT = new RegExp([
    "conversation is too long", "maximum length for this conversation", "reached its maximum length", "hit the maximum length",
    "exceed(s|ed)? the length limit", "length limit reached", "end of this conversation", "couldn'?t load (the )?entire chat",
    "reached (my|your|our) (daily |weekly )?(chat |message )?limit", "(5-hour|weekly) limit reached", "out of free messages",
    "message limit reached", "hit the .{0,24}plan limit", "reached your limit for (chats|prompts)", "search limit reached",
    "grok questions per", "reached your (weekly )?usage limit"].join("|"), "i");
  const CLOCK = /^\s*\d{1,2}:\d{2}\s?([AaPp][Mm])?\s*$/;
  const clean = el => {
    const c = el.cloneNode(true);  // thinking panes, buttons, screen-reader headings and time labels are not the message
    c.querySelectorAll("button, svg, style, script, time, [class*='think'], [class*='reasoning'], .sr-only, .cdk-visually-hidden, " +
                       "[class*='visually-hidden']").forEach(n => n.remove());
    c.querySelectorAll("span, div").forEach(n => { if (!n.children.length && CLOCK.test(n.textContent)) n.remove(); });
    return (c.innerText || c.textContent || "").replace(/\n{3,}/g, "\n\n").trim();
  };

  // Which model answered. ChatGPT marks each reply; elsewhere the model picker shows the current choice.
  const PICKERS = {
    "chatgpt.com": 'button[data-testid="model-switcher-dropdown-button"], button.__composer-pill[aria-haspopup="menu"], button[aria-label*="model selector" i]',
    "claude.ai": '[data-testid="model-selector-dropdown"]',
    "gemini.google.com": '[data-test-id="bard-mode-menu-button"], button[aria-label*="mode picker" i]',
    "grok.com": 'button[aria-label="Model select"], button[aria-label*="model select" i]',
    "chat.mistral.ai": 'button[aria-label*="model" i]', "aistudio.google.com": "ms-model-selector button",
    "copilot.microsoft.com": 'button[aria-label*="mode" i]', "www.copilot.com": 'button[aria-label*="mode" i]',
  };
  PICKERS["chat.openai.com"] = PICKERS["chatgpt.com"];
  const MODEL_RX = /\b(GPT[-\s]?\d(?:\.\d)?(?:[-\s](?:mini|nano|pro|sol|codex))?(?:\s+(?:Instant|Thinking|Pro))?|o[1345](?:[-\s](?:mini|pro))?|(?:Claude\s+)?(?:Opus|Sonnet|Haiku|Fable)\s+\d(?:\.\d)?|Gemini\s+\d(?:\.\d)?\s+(?:Pro|Flash(?:[-\s]Lite)?|Ultra)|\d\.\d\s+(?:Pro|Flash(?:[-\s]Lite)?)|Grok\s+\d(?:\.\d)?(?:\s+(?:Fast|Heavy|mini))?|DeepSeek[-\s](?:V\d(?:\.\d)?|R\d)|Mistral\s+(?:Large|Medium|Small)(?:\s+\d(?:\.\d)?)?)\b/i;
  const MODE_RX = /^(Auto|Instant|Fast|Thinking|Pro|Expert|Heavy|Quick response|Think Deeper|Smart)$/i;
  function pickerModel() {
    const host = location.hostname;
    if (host === "chat.deepseek.com") {  // no label: the DeepThink toggle says which model answers
      const b = [...document.querySelectorAll("button, [role=button]")].find(x => /DeepThink/i.test(x.innerText || ""));
      return b ? (/active|selected|checked/i.test(b.className) || b.getAttribute("aria-pressed") === "true" ? "DeepSeek R1" : "DeepSeek V3") : null;
    }
    const el = PICKERS[host] && document.querySelector(PICKERS[host]);
    if (el) {
      const label = ((el.getAttribute("aria-label") || "") + " " + (el.innerText || "")).trim();
      const m = label.match(MODEL_RX);
      if (m) return m[0];
      const first = (el.innerText || "").trim().split("\n")[0];
      if (MODE_RX.test(first)) return first;  // the server names it with the app ("Gemini Thinking")
    }
    const form = box() && box().closest("form");  // anything model-like on the composer's buttons
    for (const b of form ? form.querySelectorAll("button") : []) {
      const m = ((b.getAttribute("aria-label") || "") + " " + (b.innerText || "")).match(MODEL_RX);
      if (m) return m[0];
    }
    return null;
  }
  const replyModel = el => el.getAttribute("data-message-model-slug") ||
    el.querySelector("[data-message-model-slug]")?.getAttribute("data-message-model-slug") || null;

  function readTurns() {
    if (!READER) return [];
    const els = [...document.querySelectorAll(ANY)];
    const outer = els.filter(e => !els.some(o => o !== e && o.contains(e)));
    outer.sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1));
    const turns = [];
    for (const el of outer) {
      const role = el.matches(READER.user) ? "user" : "assistant";
      const part = el.querySelector((role === "user" ? READER.userText : READER.aiText) || ":scope") || el;
      const text = (el.isConnected && part.innerText !== undefined) ? clean(part) : "";
      if (!text) continue;
      const prev = turns[turns.length - 1];
      if (prev && prev.role === role && prev.text === text) continue;  // the same bubble rendered twice
      turns.push({ role, text: text.slice(0, 60000), ...(role === "assistant" && replyModel(el) ? { model: replyModel(el) } : {}) });
    }
    return turns;
  }

  let meter = null, lastSig = "", limitText = null, timer = 0, firstChange = 0, added = [], dismissed = "";
  const live = async () => (await chrome.storage.local.get({ live: true, enabled: true, warnAt: 80 }));

  async function sync() {
    const s = await live();
    if (!s.live || !s.enabled || !current() || !alive()) return;
    for (const n of added.splice(0)) {  // limit banners appear outside the message list
      if (!n.isConnected || !n.closest || n.closest("[contenteditable='true'], textarea, #memgraph-live") || (ANY && n.closest(ANY))) continue;
      const t = (n.innerText || n.textContent || "").slice(0, 600);
      const m = t.match(LIMIT);
      if (m) limitText = t.trim().split("\n").find(l => LIMIT.test(l)) || m[0];
    }
    const turns = readTurns();
    if (turns.length < 2 && !limitText) return;  // a new, empty chat: nothing to keep yet
    const sig = turns.length + "|" + turns.map(t => t.text.length).join(",") + "|" + (limitText || "");
    if (sig === lastSig) return;
    lastSig = sig;
    const r = await send({ live: { url: location.href, site: location.hostname, title: document.title, turns, limit: limitText,
                                   model: pickerModel() } });
    if (r && r.id) { meter = r; banner(s.warnAt); }
  }
  function schedule() {  // quiet for 2.5s (a reply finished streaming), or at most every 15s while it streams
    clearTimeout(timer);
    const now = Date.now();
    firstChange = firstChange || now;
    timer = setTimeout(() => { firstChange = 0; sync(); }, now - firstChange > 15000 ? 0 : 2500);
  }
  if (READER) {
    new MutationObserver(ms => {
      if (!current()) return;
      for (const m of ms) for (const n of m.addedNodes) if (n.nodeType === 1 && added.length < 300) added.push(n);
      schedule();
    }).observe(document.body, { childList: true, subtree: true, characterData: true });
    setTimeout(sync, 1500);
  }

  // The banner: shown when the chat hit a limit, or its context is past the warning line. One click hands it off.
  const TARGETS = [["chatgpt.com", "ChatGPT"], ["claude.ai", "Claude"], ["gemini.google.com", "Gemini"], ["www.perplexity.ai", "Perplexity"],
                   ["chat.deepseek.com", "DeepSeek"], ["grok.com", "Grok"]];
  function banner(warnAt) {
    const old = document.getElementById("memgraph-live");
    const why = meter.limit ? "This chat hit its limit" : meter.pct >= warnAt ? `This chat is ${Math.round(meter.pct)}% full` : null;
    if (!why || dismissed === meter.key) { if (old) old.remove(); return; }
    if (old) { old.shadowRoot.querySelector(".why").textContent = why; return; }
    const host = document.createElement("div");
    host.id = "memgraph-live";
    const root = host.attachShadow({ mode: "open" });
    const here = location.hostname === "chat.openai.com" ? "chatgpt.com" : location.hostname;
    const L = h => `<img src="${chrome.runtime.getURL("logos/" + h + ".svg")}" alt="">`;
    const LOGO = { "chatgpt.com": "chatgpt", "claude.ai": "claude", "gemini.google.com": "gemini", "www.perplexity.ai": "perplexity",
                   "chat.deepseek.com": "deepseek", "grok.com": "grok" };
    root.innerHTML = `<style>
      .bar { position: fixed; z-index: 2147483647; left: 50%; bottom: 100px; transform: translateX(-50%); display: flex; align-items: center; gap: 6px;
        padding: 6px 6px 6px 12px; background: rgba(17,17,19,.92); backdrop-filter: blur(14px); color: #ededef; border: 1px solid rgba(255,255,255,.1);
        border-radius: 14px; box-shadow: 0 1px 0 rgba(255,255,255,.04) inset, 0 18px 44px rgba(0,0,0,.5); font: 500 13px/1 system-ui, -apple-system, sans-serif;
        max-width: calc(100vw - 32px); flex-wrap: wrap; animation: in .3s cubic-bezier(.2,.8,.2,1) }
      @keyframes in { from { opacity: 0; transform: translate(-50%, 10px) } }
      .mark { width: 20px; height: 20px; border-radius: 6px; background: #0a0a0b; border: 1px solid rgba(255,255,255,.35);
        display: grid; place-items: center; flex: none }
      .mark svg { width: 15px; height: 15px; color: #fff; fill: currentColor }
      .why { font-weight: 600 } .sub { color: #a1a1aa; margin: 0 4px 0 2px }
      button { height: 32px; padding: 0 11px 0 8px; display: inline-flex; align-items: center; gap: 7px; border-radius: 9px; border: 1px solid rgba(255,255,255,.08);
        background: #1c1c1f; color: #ededef; font: inherit; cursor: pointer; transition: background .15s, transform .1s }
      button img { width: 16px; height: 16px } button:hover { background: #27272a } button:active { transform: scale(.96) }
      button.copy { color: #fff; padding: 0 11px } button.x { border: 0; background: none; color: #71717a; padding: 0 8px } button.x:hover { color: #ededef }
      button:focus-visible { outline: 2px solid #fff; outline-offset: 1px }
      @media (prefers-reduced-motion: reduce) { .bar { animation: none } } </style>
      <div class="bar" role="status"><span class="mark"><svg viewBox="0 0 96 96" fill="currentColor"><path fill-rule="evenodd" d="M38.83 19.27A23 23 0 0 1 77.84 43.65L57.17 76.73A23 23 0 0 1 18.16 52.35ZM53.63 39.08A4.3 4.3 0 0 1 46.34 34.52L50 28.67A4.3 4.3 0 0 1 57.29 33.23ZM67.63 47.82A4.3 4.3 0 0 1 60.33 43.27L63.99 37.41A4.3 4.3 0 0 1 71.28 41.97Z"/></svg></span>
        <span class="why"></span><span class="sub">· continue in</span>${TARGETS.filter(([h]) => h !== here)
        .map(([h, n]) => `<button data-to="${h}" title="Continue in ${n}">${L(LOGO[h])}${n}</button>`).join("")}<button class="copy">Copy pack</button><button class="x" aria-label="Dismiss">✕</button></div>`;
    root.querySelector(".why").textContent = why;
    root.addEventListener("click", async e => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.classList.contains("x")) { dismissed = meter.key; host.remove(); return; }
      const r = await send({ handoff: { session: meter.id, to: b.dataset.to || null, open: !!b.dataset.to } });
      if (!r || !r.text) return toast(r && r.error ? r.error : "Can't reach Mindbaton");
      const by = r.summary_by ? ` · summarised by ${r.summary_by}` : "";
      if (b.classList.contains("copy")) { await navigator.clipboard.writeText(r.text); toast(`Hand-off copied · ~${r.tokens} tokens${by}`); }
      else toast(`Opening ${b.textContent} — the conversation will be waiting in the message box`);
    });
    document.body.append(host);
  }

  // A hand-off waiting for this AI: put it in the message box of the new chat (the user reviews it and presses Enter).
  async function pickUp() {
    if (!current() || readTurns().length) return;
    const r = await send({ pending: location.hostname });
    if (!r || !r.text) return;
    for (let i = 0; i < 40; i++) {  // the composer mounts late on most sites
      const el = box();
      if (el) { insertText(el, r.text); return toast(`Conversation from ${r.from || "another AI"} is ready — press Enter to continue it here`); }
      await new Promise(ok => setTimeout(ok, 250));
    }
  }
  setTimeout(pickUp, 1200);
  let href = location.href;
  setInterval(() => { if (location.href !== href) { href = location.href; lastSig = ""; limitText = null; meter = null;
    document.getElementById("memgraph-live")?.remove(); setTimeout(pickUp, 800); schedule(); } }, 1000);  // SPA navigation
})();
