// Project state is separate from personal pairing. Every mutation is serialized and persisted before networking.
let teamChain = Promise.resolve();
const teamHash = async text => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)))].map(x => x.toString(16).padStart(2, '0')).join('');
const teamState = async () => (await chrome.storage.local.get({ teamState: { connections: {}, bindings: {} } })).teamState;
function teamMutate(fn) {
  const operation = teamChain.then(async () => {
    const state = await teamState();
    const result = await fn(state);
    if (new TextEncoder().encode(JSON.stringify(state)).length > 5_000_000) throw new Error('Capture storage full; existing pending work preserved');
    await chrome.storage.local.set({ teamState: state });
    return result;
  });
  teamChain = operation.catch(() => {});
  return operation;
}
function teamHost(value, privateNetwork) {
  const u = new URL(value);
  if (!['http:', 'https:'].includes(u.protocol) || u.username || u.password || u.search || u.hash || u.pathname !== '/') throw new Error('Use a host origin without a path');
  if (u.protocol !== 'https:' && !['localhost', '127.0.0.1', '[::1]'].includes(u.hostname) && !privateNetwork) throw new Error('Project sharing requires HTTPS or an encrypted private network');
  return u.origin;
}
async function teamAPI(c, path, body, ms = 3000) {
  const response = await fetch(c.host + '/team/' + c.project + '/' + path, { method: body ? 'POST' : 'GET',
    headers: { Authorization: 'Bearer ' + c.token, 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(ms), redirect: 'error', credentials: 'omit' });
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(result.error || 'Project host error ' + response.status);
    error.stopped = [401, 403, 409].includes(response.status);
    throw error;
  }
  return result;
}
async function teamConnect(m) {
  const host = teamHost(m.host, m.privateNetwork);
  if (!/^[a-f0-9]{32}$/.test(m.project) || !m.token?.startsWith('tb_')) throw new Error('Use a project ID and a project device token');
  const scope = await teamHash(host + '\n' + m.project + '\n' + await teamHash(m.token));
  const c = { host, project: m.project, token: m.token };
  const view = await teamAPI(c, 'view');
  await teamMutate(state => { if (!state.connections[scope]) state.connections[scope] = { ...c, name: view.name, queue: [], cache: {}, seen: {}, retryAt: 0, backoff: 0 }; });
  return { scope, name: view.name, external: view.settings.external };
}
async function teamSelected(url) {
  const state = await teamState();
  const binding = state.bindings[url];
  return binding && state.connections[binding.scope] ? { ...binding, connection: state.connections[binding.scope] } : null;
}
async function teamCapture(live) {
  const selected = await teamSelected(live.url);
  if (!selected) return false;
  await teamMutate(async state => {
    const binding = state.bindings[live.url], c = state.connections[binding.scope];
    const seen = c.seen[binding.session] ||= {};
    const messages = [], occurrences = new Map();
    for (const turn of live.turns) {
      const content = turn.text.replace(/\[team-baton\][\s\S]*?(?:\[\/team-baton\]|$)/gi, '').trim();
      if (!content) continue;
      if (content.length > 60000) throw new Error('Visible message exceeds host limit; capture remains in the source conversation');
      const digest = await teamHash(JSON.stringify([content,live.site,turn.model || live.model || null]));
      const fallback = turn.role + ':' + digest;
      const occurrence = (occurrences.get(fallback) || 0) + 1;
      occurrences.set(fallback, occurrence);
      // shortcut: without site IDs, edits are additional reports; add a stable site-ID adapter when available.
      const source = turn.sourceId ? turn.role + ':' + turn.sourceId : fallback + ':' + occurrence;
      const old = seen[source];
      if (old?.digest === digest) continue;
      const item = { id: old?.id || crypto.randomUUID(), revision: (old?.revision || 0) + 1, timestamp: old?.timestamp || Date.now() / 1000, digest };
      seen[source] = item;
      messages.push({ message_id: item.id, revision: item.revision, timestamp: item.timestamp, speaker: turn.role,
        content, ai: live.site, ...(turn.model || live.model ? { model: turn.model || live.model } : {}) });
    }
    let batch = [];
    const payload = messages => ({ session_id: binding.session, title: live.title, ai: live.site, ...(live.model ? {model:live.model} : {}), messages });
    for (const message of messages) {
      const candidate = [...batch, message];
      if (batch.length && (candidate.length > 100 || new TextEncoder().encode(JSON.stringify(payload(candidate))).length > 900000)) {
        c.queue.push({id:crypto.randomUUID(),body:payload(batch)}); batch=[];
      }
      batch.push(message);
    }
    if (batch.length) c.queue.push({id:crypto.randomUUID(),body:payload(batch)});
    c.error = c.stopped || '';
  });
  teamFlush();
  return true;
}
let teamFlushing = false;
async function teamFlush() {
  if (teamFlushing) return;
  teamFlushing = true;
  try {
    const state = await teamState();
    for (const [scope, c] of Object.entries(state.connections)) {
      if (c.stopped || c.retryAt > Date.now()) continue;
      for (const entry of c.queue) {
        try {
          const ack = await teamAPI(c, 'upload', entry.body);
          const expected = entry.body.messages.map(m => m.message_id + '@' + m.revision).sort().join('|');
          const got = (ack.accepted || []).map(m => m.message_id + '@' + m.revision).sort().join('|');
          if (got !== expected) throw new Error('Unmatched acknowledgement; pending upload retained');
          await teamMutate(s => {
            const current = s.connections[scope];
            current.queue = current.queue.filter(x => x.id !== entry.id);
            current.error = ''; current.retryAt = 0; current.backoff = 0; current.lastRevision = ack.project_revision;
          });
        } catch (error) {
          await teamMutate(s => {
            const current = s.connections[scope];
            current.error = error.message;
            current.backoff = Math.min(60, Math.max(1, (current.backoff || 0) * 2));
            current.retryAt = Date.now() + current.backoff * 1000;
            if (error.stopped) { current.stopped = error.message; current.cache = {}; }
          });
          break;
        }
      }
    }
  } finally { teamFlushing = false; }
}
async function teamContext(url, query) {
  const selected = await teamSelected(url);
  if (!selected) return { private: true };
  const { scope, connection: c } = selected;
  if (c.stopped) return { text: '[team-baton]\nAccess stopped: ' + c.stopped + '\n[/team-baton]', outdated: true };
  const key = query.slice(0, 500);
  try {
    const result = await teamAPI(c, 'context?q=' + encodeURIComponent(key));
    await teamMutate(s => {
      s.connections[scope].contextOutdated = false;
      const cache = s.connections[scope].cache;
      cache[key] = result;
      const keys = Object.keys(cache);
      if (keys.length > 12) delete cache[keys[0]];
    });
    return result;
  } catch (error) {
    if (error.stopped) {
      await teamMutate(s => { s.connections[scope].stopped = error.message; s.connections[scope].cache = {}; });
      return { text: '[team-baton]\nProject access stopped. No shared context available.\n[/team-baton]', outdated: true };
    }
    await teamMutate(s => { s.connections[scope].contextOutdated = true; });
    const cached = c.cache[key] || Object.values(c.cache).slice(-1)[0];
    return { text: cached ? cached.text.replace('[team-baton]', '[team-baton]\nContext outdated; cached ' + new Date(cached.captured_at * 1000).toISOString() + '. Host unreachable.') :
      '[team-baton]\nHost unreachable; no shared context available. New messages remain queued.\n[/team-baton]', outdated: true };
  }
}
async function teamMessage(m) {
  if (m.action === 'connect') return teamConnect(m);
  if (m.action === 'select') {
    await teamMutate(state => {
      if (!m.scope) { delete state.bindings[m.url]; return; }
      if (!state.connections[m.scope]) throw new Error('Project connection missing');
      // A changed binding never reuses the previous project's conversation ID.
      const old = state.bindings[m.url];
      state.bindings[m.url] = { scope: m.scope, session: old?.scope === m.scope ? old.session : crypto.randomUUID() };
    });
    return { ok: true };
  }
  if (m.action === 'follow') {
    await teamMutate(state => {
      const from = new URL(m.from), to = new URL(m.url);
      if (from.origin === to.origin && ['/', '/new', '/chat', '/app', '/new-chat'].includes(from.pathname) && state.bindings[m.from] && !state.bindings[m.url]) {
        state.bindings[m.url] = state.bindings[m.from];
        delete state.bindings[m.from]; // future new chats stay Private
      }
    });
    return {ok:true};
  }
  if (m.action === 'context') return teamContext(m.url, m.query || '');
  if (m.action === 'status') {
    const state = await teamState(), selected = state.bindings[m.url];
    return { selected: selected?.scope || '', connections: Object.entries(state.connections).map(([scope, c]) => ({ scope, name: c.name,
      pending: c.queue.length, error: c.error, stopped: c.stopped, contextOutdated: c.contextOutdated || (c.lastRevision > (Object.values(c.cache).slice(-1)[0]?.project_revision || 0)), cachedAt: Object.values(c.cache).slice(-1)[0]?.captured_at })) };
  }
  throw new Error('Unknown project action');
}
chrome.runtime.onMessage.addListener((m, _sender, reply) => {
  if (!m.team) return;
  teamMessage(m.team).then(reply, e => { badge('!', '#ff6369'); reply({ error: e.message }); });
  return true;
});
chrome.alarms.create('team-baton-retry', { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === 'team-baton-retry') teamFlush().catch(() => badge('!', '#ff6369')); });
chrome.runtime.onStartup.addListener(() => teamFlush());
