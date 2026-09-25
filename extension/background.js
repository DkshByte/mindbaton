// Captures wait in storage so nothing is lost off the LAN; every new message flushes the queue.
// The server does the understanding (which AI, chat title, facts, topics), so this stays simple.
// Your own server's address and this browser's device token come from pairing (popup: Connect → approve the code).
const SITES = chrome.runtime.getManifest().content_scripts[0].matches;
const NOT_PAIRED = "Not connected — open the extension and press Connect";
const why = e => (e.message === "401" || e.message === NOT_PAIRED ? NOT_PAIRED : "Can't reach Mindbaton");
const conf = async () => {
  const s = await chrome.storage.local.get({ server: "", token: "" });
  return { base: s.server.replace(/\/$/, ""), token: s.token };
};
async function api(path, init = {}) {  // every call to your server carries this browser's token
  const { base, token } = await conf();
  if (!base) throw new Error(NOT_PAIRED);
  const r = await fetch(base + path, { ...init, headers: { ...init.headers, ...(token && { Authorization: "Bearer " + token }) } });
  if (r.status === 401) { await chrome.storage.local.set({ error: "This browser isn't connected any more — press Connect again" }); throw new Error("401"); }
  return r;
}

chrome.runtime.onMessage.addListener((m, _sender, reply) => {
  if (m.flush) { flush().then(() => reply({})); return true; }
  if (m.health) {
    api("/health").then(r => r.json()).then(reply).catch(e => reply({ ok: false, unpaired: why(e) === NOT_PAIRED }));
    return true;
  }
  if (m.pair) { pair(m.pair).then(reply, e => reply({ error: e.message })); return true; }
  if (m.unpair) { chrome.storage.local.set({ token: "", pairing: null, error: "" }).then(() => reply({})); return true; }
  if (m.context !== undefined) {  // Alt+M: a briefing relevant to what's being typed
    api(`/context?budget=1800&q=${encodeURIComponent(String(m.context).slice(0, 300))}`)
      .then(r => r.json()).then(reply).catch(e => reply({ error: why(e) }));
    return true;
  }
  if (m.live) {  // Live mode: the whole conversation, re-sent when it changes; the server keeps only what's new
    api("/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(m.live) })
      .then(r => r.json()).then(r => { if (r.limit) badge("!", "#ff6369"); reply(r); }).catch(() => reply(null));
    return true;
  }
  if (m.handoff) {  // pack the conversation; with a target AI, it waits for that AI's new chat, which opens now
    const h = m.handoff;
    api(`/handoff?budget=${h.budget || 2500}&session=${encodeURIComponent(h.session || "")}` +
        (h.to ? "&to=" + encodeURIComponent(h.to) : ""))
      .then(r => r.json()).then(r => {
        if (r.open && h.open) chrome.tabs.create({ url: r.open });
        reply(r);
      }).catch(e => reply({ error: why(e) }));
    return true;
  }
  if (m.summary) {  // this chat's AI summary (made on the server, in the background, if it isn't ready yet)
    api(`/session/summary?id=${encodeURIComponent(m.summary)}`).then(r => r.json()).then(reply).catch(() => reply(null));
    return true;
  }
  if (m.pending) {
    api(`/handoff/pending?host=${encodeURIComponent(m.pending)}`).then(r => r.json()).then(reply).catch(() => reply(null));
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
    const { base, token } = await conf();
    const { queue = [], sent = 0 } = await chrome.storage.local.get(["queue", "sent"]);
    if (!base || !token) {  // not paired yet: keep everything until it is
      if (queue.length) badge(String(queue.length), "#f59e0b");
      return;
    }
    let n = 0, lastSite = null;
    for (const body of queue) {
      const r = await api("/capture", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (r.status >= 500 || r.status === 403 || r.status === 429) { await chrome.storage.local.set({ error: "Server error " + r.status }); break; }
      n++; lastSite = body.site;  // a 400 is a bad item: drop it
    }
    const now = (await chrome.storage.local.get({ queue: [] })).queue.slice(n);
    await chrome.storage.local.set({ queue: now, sent: sent + n, ...(n && { lastSaved: { ts: Date.now(), site: lastSite } }),
      ...(n === queue.length && { error: "" }) });
    if (now.length) badge(String(now.length), "#f59e0b");
    else if (n) { badge("+" + n, "#3dd68c"); setTimeout(() => badge(""), 2500); }
  } catch (e) {
    if (e.message !== "401") await chrome.storage.local.set({ error: "Can't reach Mindbaton" });
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
  if (reason === "install") chrome.tabs.create({ url: chrome.runtime.getURL("popup.html?tab") });  // first install: connect it
  resumePairing();
});
chrome.runtime.onStartup.addListener(() => { flush(); resumePairing(); });
chrome.storage.onChanged.addListener(c => c.token && c.token.newValue && flush());

// Pairing: ask your server for a code, you approve it in Mindbaton (signed in), this browser gets its own token.
// Nothing but the device name is sent before you approve. Runs here, not in the popup, which closes when you switch tabs.
async function pair({ server, key }) {
  const base = server.replace(/\/$/, "");
  const h = await fetch(base + "/health").then(r => r.json()).catch(() => null);
  if (!h || h.name !== "mindbaton") throw new Error("Can't find Mindbaton at that address — check it's running and the address is right");
  if (key) {  // a key made in Settings → Devices, pasted in
    const r = await fetch(base + "/health", { headers: { Authorization: "Bearer " + key } }).then(r => r.json());
    if (!r.authed) throw new Error("That key isn't valid on this Mindbaton");
    await chrome.storage.local.set({ server: base, token: key, pairing: null, error: "" });
    return { ok: true };
  }
  const os = /Mac/.test(navigator.userAgent) ? "Mac" : /Windows/.test(navigator.userAgent) ? "Windows" : /CrOS/.test(navigator.userAgent) ? "Chromebook" : "Linux";
  const r = await fetch(base + "/api/pair/start", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: `Browser on ${os}`, kind: "extension" }) });
  if (r.status === 429) throw new Error("Too many tries — wait a minute");
  const p = await r.json();
  if (!p.code) throw new Error(p.error || "Pairing didn't start");
  const pairing = { server: base, code: p.code, poll: p.poll, approve_url: p.approve_url, until: Date.now() + p.expires_in * 1000 };
  await chrome.storage.local.set({ pairing, error: "" });
  chrome.tabs.create({ url: p.approve_url });
  poll(pairing);
  return { ok: true, code: p.code };
}
let polling = null;
async function poll(pr) {
  if (polling === pr.poll) return;
  polling = pr.poll;
  try {
    while (Date.now() < pr.until) {
      await new Promise(r => setTimeout(r, 2000));
      const { pairing } = await chrome.storage.local.get({ pairing: null });
      if (!pairing || pairing.poll !== pr.poll) return;  // cancelled or restarted
      const x = await fetch(`${pr.server}/api/pair/poll?poll=${encodeURIComponent(pr.poll)}`).then(r => r.json()).catch(() => null);
      if (!x || x.status === "pending") continue;
      if (x.status === "approved" && x.token) {
        await chrome.storage.local.set({ server: pr.server, token: x.token, pairing: null, error: "" });
        badge("✓", "#3dd68c"); setTimeout(() => badge(""), 3000);
      } else await chrome.storage.local.set({ pairing: null, error: x.status === "denied" ? "Connection was declined" : "The code expired — press Connect again" });
      return;
    }
    await chrome.storage.local.set({ pairing: null, error: "The code expired — press Connect again" });
  } finally { if (polling === pr.poll) polling = null; }
}
async function resumePairing() {  // the service worker can be stopped mid-pairing; pick the wait back up
  const { pairing } = await chrome.storage.local.get({ pairing: null });
  if (pairing && Date.now() < pairing.until) poll(pairing);
}
resumePairing();
