// Captures wait in storage so nothing is lost off the LAN; every new message flushes the queue.
// The server does the understanding (which AI, chat title, facts, topics), so this stays simple.
const DEFAULT = "http://192.168.1.20:3004";
const server = async () => ((await chrome.storage.local.get({ server: DEFAULT })).server || DEFAULT).replace(/\/$/, "");
const SITES = chrome.runtime.getManifest().content_scripts[0].matches;

chrome.runtime.onMessage.addListener((m, _sender, reply) => {
  if (m.flush) { flush().then(() => reply({})); return true; }
  if (m.health) {
    server().then(s => fetch(s + "/health")).then(r => r.json()).then(reply).catch(() => reply({ ok: false }));
    return true;
  }
  if (m.context !== undefined) {  // Alt+M: a briefing relevant to what's being typed
    server().then(s => fetch(`${s}/context?budget=1800&q=${encodeURIComponent(String(m.context).slice(0, 300))}`))
      .then(r => r.json()).then(reply).catch(() => reply({ error: "Can't reach memgraph" }));
    return true;
  }
  if (m.live) {  // Live mode: the whole conversation, re-sent when it changes; the server keeps only what's new
    server().then(s => fetch(s + "/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(m.live) }))
      .then(r => r.json()).then(r => { if (r.limit) badge("!", "#ff6369"); reply(r); }).catch(() => reply(null));
    return true;
  }
  if (m.handoff) {  // pack the conversation; with a target AI, it waits for that AI's new chat, which opens now
    const h = m.handoff;
    server().then(s => fetch(`${s}/handoff?budget=${h.budget || 2500}&session=${encodeURIComponent(h.session || "")}` +
                             (h.to ? "&to=" + encodeURIComponent(h.to) : "")))
      .then(r => r.json()).then(r => {
        if (r.open && h.open) chrome.tabs.create({ url: r.open });
        reply(r);
      }).catch(() => reply({ error: "Can't reach memgraph" }));
    return true;
  }
  if (m.summary) {  // this chat's AI summary (made on the server, in the background, if it isn't ready yet)
    server().then(s => fetch(`${s}/session/summary?id=${encodeURIComponent(m.summary)}`)).then(r => r.json()).then(reply).catch(() => reply(null));
    return true;
  }
  if (m.pending) {
    server().then(s => fetch(`${s}/handoff/pending?host=${encodeURIComponent(m.pending)}`)).then(r => r.json()).then(reply).catch(() => reply(null));
    return true;
  }
  if (m.text) capture(m);
});

async function capture(m) {
  const s = await chrome.storage.local.get({ enabled: true, queue: [] });
  if (!s.enabled) return;
  s.queue.push({ text: m.text, site: m.site, chat: m.title, url: m.url, ts: Date.now() / 1000 });
  await chrome.storage.local.set({ queue: s.queue.slice(-500) });  // ponytail: 500-message cap while offline
  flush();
}

function badge(text, color) {
  chrome.action.setBadgeText({ text });
  if (color) chrome.action.setBadgeBackgroundColor({ color });
}

let flushing = false;
async function flush() {
  if (flushing) return;
  flushing = true;
  try {
    const base = await server();
    const { queue = [], sent = 0 } = await chrome.storage.local.get(["queue", "sent"]);
    let n = 0, lastSite = null;
    for (const body of queue) {
      const r = await fetch(base + "/capture", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (r.status >= 500 || r.status === 403) { await chrome.storage.local.set({ error: "Server error " + r.status }); break; }
      n++; lastSite = body.site;  // a 400 is a bad item: drop it
    }
    const now = (await chrome.storage.local.get({ queue: [] })).queue.slice(n);
    await chrome.storage.local.set({ queue: now, sent: sent + n, ...(n && { lastSaved: { ts: Date.now(), site: lastSite } }),
      ...(n === queue.length && { error: "" }) });
    if (now.length) badge(String(now.length), "#f59e0b");
    else if (n) { badge("+" + n, "#3dd68c"); setTimeout(() => badge(""), 2500); }
  } catch {
    await chrome.storage.local.set({ error: "Can't reach memgraph" });
    const { queue = [] } = await chrome.storage.local.get(["queue"]);
    if (queue.length) badge(String(queue.length), "#f59e0b");
  } finally { flushing = false; }
}

// After an install or update, tabs that were already open still run the old script (which can no longer talk to
// this extension). Put the new one into every open AI chat, so nobody has to refresh.
async function adopt() {
  const tabs = await chrome.tabs.query({ url: SITES });
  for (const t of tabs) chrome.scripting.executeScript({ target: { tabId: t.id }, files: ["content.js"] }).catch(() => {});
}
chrome.runtime.onInstalled.addListener(async ({ reason }) => {
  adopt(); flush();
  if (reason === "install") chrome.tabs.create({ url: (await server()) + "/#setup" });  // first install: the step-by-step page
});
chrome.runtime.onStartup.addListener(flush);
chrome.storage.onChanged.addListener(c => c.server && flush());
