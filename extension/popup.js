const $ = id => document.getElementById(id);
const DEFAULT = "http://192.168.1.20:3004";
const ago = ms => { const s = (Date.now() - ms) / 1000; return s < 60 ? "just now" : s < 3600 ? Math.floor(s / 60) + "m ago" : s < 86400 ? Math.floor(s / 3600) + "h ago" : Math.floor(s / 86400) + "d ago"; };
// host → [name, logo]; logos are the real marks, bundled in logos/
const AI = { "chatgpt.com": ["ChatGPT", "chatgpt"], "chat.openai.com": ["ChatGPT", "chatgpt"], "claude.ai": ["Claude", "claude"],
  "gemini.google.com": ["Gemini", "gemini"], "aistudio.google.com": ["Gemini", "gemini"], "www.perplexity.ai": ["Perplexity", "perplexity"],
  "chat.deepseek.com": ["DeepSeek", "deepseek"], "grok.com": ["Grok", "grok"], "copilot.microsoft.com": ["Copilot", "copilot"],
  "poe.com": ["Poe", "poe"], "chat.mistral.ai": ["Mistral", "mistral"], "copilot.com": ["Copilot", "copilot"], "www.copilot.com": ["Copilot", "copilot"] };
const TARGETS = ["chatgpt.com", "claude.ai", "gemini.google.com", "www.perplexity.ai", "chat.deepseek.com", "grok.com"];
const logo = host => `<img src="logos/${(AI[host] || [, "chatgpt"])[1]}.svg" alt="">`;
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const fmt = n => n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1000 ? Math.round(n / 1000) + "k" : String(n || 0);

function render() {
  chrome.storage.local.get({ live: true, enabled: true, server: DEFAULT, queue: [], sent: 0, error: "", lastSaved: null }, s => {
    if (document.activeElement.tagName !== "INPUT") { $("enabled").checked = s.enabled; $("live").checked = s.live; $("server").value = s.server; }
    const l = s.lastSaved;
    $("status").innerHTML = !s.enabled ? "Paused — nothing you send is saved." :
      `<b>${s.sent}</b> saved` + (l ? ` · last ${ago(l.ts)} from ${AI[l.site] ? logo(l.site) + " <b>" + AI[l.site][0] + "</b>" : "a chat"}` : "");
    $("warn").hidden = !(s.queue.length || s.error);
    $("warn").textContent = s.queue.length ? `${s.queue.length} waiting to send${s.error ? " — " + s.error : ""}` : s.error;
  });
}
function health() {
  chrome.runtime.sendMessage({ health: true }, r => {
    const ok = r && r.ok;
    $("dot").className = "dot " + (ok ? "on" : "off");
    $("conn").textContent = ok ? "Connected" : "Offline";
    $("conn").title = ok ? `${r.captures} captures on the server` : "Can't reach the Mindbaton server";
  });
}

// This tab's conversation: how full its context is, and where to continue it.
async function chat() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const host = tab && tab.url ? new URL(tab.url).hostname : "";
  let m = null;
  try { m = await chrome.tabs.sendMessage(tab.id, { syncNow: true }); } catch {}
  const box = $("chat");
  if (!m) {
    box.innerHTML = `<div class="empty"><span class="stack">${TARGETS.slice(0, 4).map(logo).join("")}</span><span>${AI[host]
      ? (($("live").checked) ? "Start chatting — this chat's meter appears after the first reply." : "Turn on Live mode to track this chat.")
      : "Open an AI chat to see how full it is and hand it off."}</span></div>`;
    return;
  }
  const pct = m.limit ? 100 : m.pct || 0, lit = Math.max(1, Math.round(pct / 100 * 24));
  const cls = m.limit || pct >= 90 ? "full" : pct >= 70 ? "warn" : "on";
  const here = host.replace("chat.openai.com", "chatgpt.com");
  box.innerHTML = `
    <div class="head"><span class="logo">${logo(host)}</span>
      <span class="who"><b>${esc(m.chat || m.ai)}</b><span>${esc(m.ai)}${m.model ? " · " + esc(m.model) : ""} · ${m.turns} messages</span></span>
      <span class="chip ${m.limit ? "full" : ""}"><i></i>${m.limit ? "Limit hit" : "Live"}</span></div>
    <div class="gauge"><div class="nums"><b>${m.limit ? "Full" : pct + "%"}</b><span>~${fmt(m.tokens)} / ${fmt(m.window)} tokens</span></div>
      <div class="segs">${Array.from({ length: 24 }, (_, i) => `<i class="${i < lit ? cls : ""}"></i>`).join("")}</div></div>
    <div class="sum" id="sum" hidden></div>
    <div class="cont"><div class="label">Continue in</div>
      <div class="grid">${TARGETS.filter(h => h !== here).slice(0, 6).map(h => `<button data-to="${h}">${logo(h)}${AI[h][0]}</button>`).join("")}</div>
      <button class="copy">Copy hand-off pack</button></div>`;
  summary(m.id);
  box.onclick = e => {
    const b = e.target.closest("button");
    if (!b) return;
    chrome.runtime.sendMessage({ handoff: { session: m.id, to: b.dataset.to || null, open: !!b.dataset.to } }, async r => {
      if (!r || !r.text) { $("warn").hidden = false; $("warn").textContent = (r && r.error) || "Can't reach Mindbaton"; return; }
      if (b.dataset.to) return window.close();
      await navigator.clipboard.writeText(r.text);
      b.textContent = `Copied · ~${fmt(r.tokens)} tokens${r.summary_by ? " · by " + r.summary_by : ""} ✓`;
    });
  };
}

function summary(id, tries = 0) {  // the AI summary of this chat; while it's being made, look again every few seconds
  chrome.runtime.sendMessage({ summary: id }, r => {
    const el = $("sum");
    if (!el || !r || r.enabled === false) return;
    if (r.summary) {
      el.hidden = false;
      el.innerHTML = `<span class="lab">Summary · ${esc(r.by || "AI")}</span><p>${esc(r.summary)}</p>${r.next ? `<p class="next">Next: ${esc(r.next)}</p>` : ""}`;
    } else if (r.pending && tries < 8) {
      el.hidden = false; el.innerHTML = `<span class="lab">Summary</span><p>Summarising this chat…</p>`;
      setTimeout(() => summary(id, tries + 1), 5000);
    }
  });
}

$("enabled").onchange = e => chrome.storage.local.set({ enabled: e.target.checked });
$("live").onchange = e => { chrome.storage.local.set({ live: e.target.checked }); setTimeout(chat, 100); };
$("server").oninput = e => chrome.storage.local.set({ server: e.target.value.trim() || DEFAULT });  // saved as you type: the popup can close first
$("server").onchange = health;
$("open").onclick = e => { e.preventDefault(); chrome.storage.local.get({ server: DEFAULT }, s => chrome.tabs.create({ url: s.server })); };
$("insert").onclick = async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  try { await chrome.tabs.sendMessage(tab.id, { insert: true }); window.close(); }
  catch { $("warn").hidden = false; $("warn").textContent = "Open ChatGPT, Claude, Gemini or another AI chat first."; }
};
chrome.storage.onChanged.addListener(render);
chrome.runtime.sendMessage({ flush: true }, () => { render(); health(); });  // retry anything waiting whenever the popup opens
render(); chat();
