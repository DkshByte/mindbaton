"""live — whole conversations (Live mode), hand-offs between AIs, and graph tools (history, paths, export).

Sessions are primary data like captures: the transcript of one chat (user and assistant turns), synced by the browser
extension, saved by an MCP client, or read from Claude Code's own transcript files on this machine. From them:
  - user turns that were never captured become captures, so the graph keeps learning;
  - each session becomes a node linked to the things it discusses and the memories said in it;
  - a hand-off pack lets another AI continue the conversation, delivered through a "pending" slot that the
    extension picks up when the target AI's new-chat page opens.
"""
import glob, html, json, math, os, re, threading, time
from datetime import datetime
from collections import Counter, deque
import brain, handoff

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL, site TEXT, chat TEXT, url TEXT, model TEXT,
  started REAL, updated REAL, tokens INTEGER DEFAULT 0, window INTEGER, limit_text TEXT, limit_at REAL, turns INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS turns(id INTEGER PRIMARY KEY, session INTEGER NOT NULL REFERENCES sessions ON DELETE CASCADE,
  n INTEGER NOT NULL, role TEXT, text TEXT, ts REAL, ents TEXT DEFAULT '[]', model TEXT, UNIQUE(session, n));
CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(text, tokenize='porter unicode61');
CREATE TABLE IF NOT EXISTS pending(id INTEGER PRIMARY KEY, host TEXT, text TEXT, created REAL, used REAL, source INTEGER);
"""
# Context windows of each app's default model, in tokens (what the conversation can hold before it is cut or refused).
WINDOWS = {"ChatGPT": 128_000, "Claude": 200_000, "Gemini": 1_000_000, "Perplexity": 128_000, "DeepSeek": 128_000,
           "Grok": 128_000, "Copilot": 128_000, "Mistral": 128_000, "Poe": 128_000, "Claude Code": 200_000, "Codex": 200_000,
           "Antigravity": 200_000, "Gemini CLI": 1_000_000, "Cursor": 200_000}
NEW_CHAT = {"chatgpt.com": "https://chatgpt.com/", "claude.ai": "https://claude.ai/new", "gemini.google.com": "https://gemini.google.com/app",
            "www.perplexity.ai": "https://www.perplexity.ai/", "chat.deepseek.com": "https://chat.deepseek.com/",
            "grok.com": "https://grok.com/", "copilot.microsoft.com": "https://copilot.microsoft.com/",
            "chat.mistral.ai": "https://chat.mistral.ai/chat", "poe.com": "https://poe.com/", "aistudio.google.com": "https://aistudio.google.com/prompts/new_chat"}
MAX_TURN = 60_000        # characters kept per turn (pasted logs can be enormous)
MAX_TURNS = 3000
PENDING_TTL = 600        # a hand-off waits 10 minutes for its new chat to open


def S():
    import server  # lazy: server imports this module
    return server


def setup(g):
    g.db.executescript(SCHEMA)
    if "model" not in [r[1] for r in g.db.execute("PRAGMA table_info(turns)")]:
        g.db.execute("ALTER TABLE turns ADD COLUMN model TEXT")  # which model wrote each reply (a chat can switch models)
    cols = [r[1] for r in g.db.execute("PRAGMA table_info(sessions)")]
    if "cwd" not in cols:
        g.db.execute("ALTER TABLE sessions ADD COLUMN cwd TEXT")  # where a coding agent ran: which project it was
    if "parent" not in cols:
        g.db.execute("ALTER TABLE sessions ADD COLUMN parent INTEGER")  # the chat this one was handed off from


T = lambda s: s[:1].upper() + s[1:]
MODEL_NAMES = [  # raw ids from transcripts, pages and APIs -> the name people use (first match wins)
    (r"claude-(opus|sonnet|haiku|fable)-(\d+)-(\d)(?!\d)", lambda m: f"{T(m[1])} {m[2]}.{m[3]}"),
    (r"claude-(opus|sonnet|haiku|fable)-(\d+)(?!\d|-\d(?!\d))", lambda m: f"{T(m[1])} {m[2]}"),
    (r"claude-(\d)-(\d)-(opus|sonnet|haiku)", lambda m: f"{T(m[3])} {m[1]}.{m[2]}"),
    (r"claude-(\d)-(opus|sonnet|haiku)", lambda m: f"{T(m[2])} {m[1]}"),
    (r"^(?:claude\s+)?(opus|sonnet|haiku|fable)\s+(\d+(?:\.\d)?)(\s*\(?thinking\)?)?", lambda m: f"{T(m[1].lower())} {m[2]}" + (" Thinking" if m[3] else "")),
    (r"^(opus|sonnet|haiku|fable)$", lambda m: T(m[1].lower())),
    (r"^claude(\d)(\d)?(opus|sonnet|haiku)(thinking)?$", lambda m: f"{T(m[3])} {m[1]}" + (f".{m[2]}" if m[2] else "") + (" Thinking" if m[4] else "")),
    (r"^(?:chatgpt[\s-]+)?gpt[-\s]?(\d+)(?:[.-](\d)(?!\d))?(o)?((?:[-\s](?:mini|nano|pro|sol|codex|thinking|instant|chat-latest))*)",
     lambda m: "GPT-" + m[1] + (f".{m[2]}" if m[2] else "") + (m[3] or "") + "".join(" " + T(w) for w in re.findall(r"mini|nano|pro|sol|codex|thinking|instant", m[4].lower()))),
    (r"^o(\d)(?:-(mini|pro))?(?:-\d{4}-\d\d-\d\d)?$", lambda m: "o" + m[1] + (" " + m[2] if m[2] else "")),
    (r"gemini-(\d+(?:\.\d)?)-(pro|flash-lite|flash|ultra)", lambda m: f"Gemini {m[1]} {m[2].replace('-', ' ').title()}"),
    (r"^gemini-(pro|flash)-latest$", lambda m: f"Gemini {T(m[1])}"),
    (r"^grok-(\d+(?:[.-]\d)?)(-fast|-heavy|-mini)?", lambda m: "Grok " + m[1].replace("-", ".") + (m[2] or "").replace("-", " ").title()),
    (r"^deepseek-(reasoner|r1)", lambda m: "DeepSeek R1"),
    (r"^deepseek-(chat|v\d[\w.]*)", lambda m: "DeepSeek " + ("V3" if m[1] == "chat" else m[1].upper())),
]
MODES = re.compile(r"^(auto|instant|fast|thinking|pro|expert|heavy|quick response|think deeper|smart|deep research)$", re.I)


def model_name(raw, ai=None):
    """'claude-opus-5-5' -> 'Opus 5.5', 'gpt-5-6-thinking' -> 'GPT-5.6 Thinking'. A bare mode a page shows ('Thinking')
    is named with its app ('Gemini Thinking'); unknown labels pass through."""
    raw = re.sub(r"\s+", " ", (raw or "").strip())
    if not raw or raw.startswith("<") or raw.lower() in ("default", "auto", "none", "null", "unknown"):
        return None
    for rx, fmt in MODEL_NAMES:
        m = re.search(rx, raw, re.I)
        if m:
            return fmt(m)
    if MODES.match(raw) and ai and ai not in ("agent", "Phone"):
        return f"{ai} {T(raw.lower())}"
    return raw[:40]


def _turn_ents(g, text):
    """Named things in a turn: known entities and recognisable tech. Assistant chatter doesn't mint new entities."""
    found = {}
    text = brain.MINDBATON_BLOCK.sub(" ", text)  # a pasted pack names everything Mindbaton knows, not what this chat is about
    for k, lab, typ in brain.entities(text[:8000]):
        if k in g.ekeys or typ == "tech":
            found[k] = (lab, typ)
    words = re.findall(r"[a-z0-9][a-z0-9.+#-]*", text[:8000].lower())
    for n in (1, 2, 3):
        for i in range(len(words) - n + 1):
            k = brain.key(" ".join(words[i:i + n]))
            if k in g.ekeys and k not in found and k != "me" and (" " in k or not brain.is_word(k)):
                found[k] = (k, "name")
    return [[k, l, t] for k, (l, t) in found.items()][:40]


# ---- sessions -------------------------------------------------------------------------------------------------------
def _ts(x):
    """A client-sent time, if it's a plausible epoch in seconds."""
    return float(x) if isinstance(x, (int, float)) and 1.5e9 < x <= time.time() + 60 else None


def sync(g, url, site, title, turns, limit=None, model=None, ts=None, key=None, capture_users=True, cwd=None, conv_id=None):
    """The current transcript of one chat (authoritative, in order). Returns the session's meter.
    turns: [{role, text, model?, ts?}]. conv_id: the app's own conversation id, the most stable key there is."""
    ts = ts or time.time()
    srv = S()
    ai = srv.ai_of(site)
    chat = srv.chat_title(title, ai)
    if conv_id and not key:
        key = f"{(site or 'chat').lower()}/{str(conv_id)[:120]}"
    key = key or srv.conv_key(url, chat) or f"{site}:{(title or 'chat')[:60]}"
    if g.forgotten("session", "session:" + key):
        return None  # forgotten on purpose: don't collect it again
    clean, parent, said = [], None, {}  # said: user turn n -> what the user typed (a pasted pack dropped)
    for t in turns[:MAX_TURNS]:
        role = "assistant" if str(t.get("role", "")).lower() in ("assistant", "ai", "model", "bot") else "user"
        raw = brain.redact(str(t.get("text") or "")[:MAX_TURN])
        if role == "user" and parent is None and (pf := brain.PACK_FROM.search(raw)):  # this chat continues a hand-off
            r = g.db.execute("SELECT id, site FROM sessions WHERE chat=? AND key!=? ORDER BY updated DESC", (pf[2], key)).fetchall()
            parent = next((i for i, s in r if srv.ai_of(s) == pf[1]), r[0][0] if r else None)
        text = brain.scrub(raw, pack="mark")  # wrappers, hidden headings, clocks go; a pasted pack becomes one line
        if text and role == "user":
            said[len(clean)] = brain.scrub(raw)
        if text:
            clean.append((role, text, model_name(t.get("model"), ai) if role == "assistant" else None, _ts(t.get("ts"))))
    model = next((m for _, _, m, _ in reversed(clean) if m), None) or model_name(model, ai)  # who answered beats the picker
    row = g.db.execute("SELECT id, limit_at FROM sessions WHERE key=?", (key,)).fetchone()
    if row:
        sid = row[0]
        g.db.execute("""UPDATE sessions SET chat=coalesce(?, chat), url=coalesce(?, url), model=coalesce(?, model), updated=?,
                        cwd=coalesce(?, cwd), parent=coalesce(parent, ?) WHERE id=?""", (chat, url, model, ts, cwd, parent, sid))
    else:
        sid = g.db.execute("INSERT INTO sessions(key, site, chat, url, model, started, updated, cwd, parent) VALUES(?,?,?,?,?,?,?,?,?)",
                           (key, site, chat, url, model, next((x for *_, x in clean if x), ts), ts, cwd, parent)).lastrowid
    have = {n: (i, r, x, md) for i, n, r, x, md in g.db.execute("SELECT id, n, role, text, model FROM turns WHERE session=?", (sid,))}
    new_user = []
    for n, (role, text, tmodel, tts) in enumerate(clean):
        old = have.get(n)
        tmodel = tmodel or (old[3] if old else None) or (model if role == "assistant" and n == len(clean) - 1 else None)
        if old and old[1] == role and old[2] == text:
            if tmodel and tmodel != old[3]:
                g.db.execute("UPDATE turns SET model=? WHERE id=?", (tmodel, old[0]))
            continue
        ents = json.dumps(_turn_ents(g, text))
        if old:  # a streaming reply grew, or a message was edited
            g.db.execute("UPDATE turns SET role=?, text=?, ents=?, model=? WHERE id=?", (role, text, ents, tmodel, old[0]))
            g.db.execute("DELETE FROM turns_fts WHERE rowid=?", (old[0],))
            g.db.execute("INSERT INTO turns_fts(rowid, text) VALUES(?,?)", (old[0], text))
        else:
            tid = g.db.execute("INSERT INTO turns(session, n, role, text, ts, ents, model) VALUES(?,?,?,?,?,?,?)",
                               (sid, n, role, text, tts or ts, ents, tmodel)).lastrowid
            g.db.execute("INSERT INTO turns_fts(rowid, text) VALUES(?,?)", (tid, text))
        if role == "user":
            reply = next((m for r2, _, m, _ in clean[n + 1:] if r2 == "assistant"), None) or model  # who answered it
            new_user.append((said.get(n, text), tts or ts, reply))
    for n, (i, *_) in have.items():
        if n >= len(clean):  # the chat got shorter (a regenerated branch): drop the tail
            g.db.execute("DELETE FROM turns_fts WHERE rowid=?", (i,))
            g.db.execute("DELETE FROM turns WHERE id=?", (i,))
    tokens = sum(handoff.tokens(t) for _, t, _, _ in clean)
    window = WINDOWS.get(ai, 128_000)
    lim_at = (row[1] if row and row[1] else ts) if limit else (row[1] if row else None)
    g.db.execute("UPDATE sessions SET tokens=?, window=?, turns=?, limit_text=coalesce(?, limit_text), limit_at=? WHERE id=?",
                 (tokens, window, len(clean), limit, lim_at, sid))
    if capture_users:  # the graph keeps learning: user turns it never saw (older history, other devices) become captures
        for text, when, reply in new_user:
            if len(text) < 8:
                continue
            seen = g.db.execute("SELECT id, url, chat, extra FROM captures WHERE text=? AND site IS ?", (text, site)).fetchall()
            for cid, curl, cchat, extra in seen:  # captured on its own (a new chat's first message, before the chat had a URL)
                x = json.loads(extra) if extra else {}
                if srv.conv_key(curl, None) is None and not x.get("session"):  # only true orphans, never another chat's
                    x.update(session=key, **({"model": reply} if reply and not x.get("model") else {}))
                    g.db.execute("UPDATE captures SET extra=? WHERE id=?", (json.dumps(x), cid))
                    g.db.execute("""UPDATE nodes SET ctx=? WHERE kind='memory' AND (ctx IS NULL OR ctx LIKE 'chat:%') AND EXISTS
                                    (SELECT 1 FROM json_each(nodes.sources) WHERE json_extract(value, '$.ts') = (SELECT ts FROM captures WHERE id=?))""",
                                 (key, cid))
                    g.dirty = True
            if not seen:
                g.ingest(text, site, title, url, when, meta={"session": key, "model": reply}, ctx=key)
    link_session(g, sid)
    return meter(g, sid)


def meter(g, sid):
    r = g.db.execute("SELECT id, key, site, chat, url, tokens, window, limit_text, limit_at, turns, updated, started, model, cwd, parent "
                     "FROM sessions WHERE id=?", (sid,)).fetchone()
    if not r:
        return None
    ai = S().ai_of(r[2])
    models = [m for (m,) in g.db.execute("SELECT model FROM turns WHERE session=? AND model IS NOT NULL GROUP BY model "
                                         "ORDER BY min(n)", (sid,))]
    return {"id": r[0], "key": r[1], "site": r[2], "ai": ai, "chat": r[3], "url": r[4], "tokens": r[5], "window": r[6],
            "pct": round(100 * r[5] / r[6], 1) if r[6] else None, "limit": r[7], "limit_at": r[8], "turns": r[9],
            "updated": r[10], "started": r[11], "model": model_name(r[12], ai) or (models[-1] if models else None), "models": models,
            "cwd": r[13], "parent": r[14]}


def link_session(g, sid):
    """The session as a node: linked to the things it discusses and the memories said in it."""
    r = g.db.execute("SELECT key, site, chat, started, updated FROM sessions WHERE id=?", (sid,)).fetchone()
    if not r:
        return
    key, site, chat, started, updated = r
    ai = S().ai_of(site)
    first = g.db.execute("SELECT text FROM turns WHERE session=? AND role='user' AND text NOT LIKE '[hand-off from%' ORDER BY n LIMIT 1",
                         (sid,)).fetchone()
    par = g.db.execute("SELECT p.chat FROM sessions s JOIN sessions p ON p.id = s.parent WHERE s.id=?", (sid,)).fetchone()
    label = S().chat_title(chat, ai) or (f"Continues “{par[0]}”" if par and par[0] else None) or \
        (handoff._clip(first[0], 80) if first else "a conversation")
    if not g.db.execute("SELECT model FROM sessions WHERE id=?", (sid,)).fetchone()[0]:  # the model its messages named
        m = g.db.execute("""SELECT json_extract(extra, '$.model') FROM captures WHERE json_extract(extra, '$.session') = ?
                            AND json_extract(extra, '$.model') IS NOT NULL ORDER BY ts DESC LIMIT 1""", (key,)).fetchone()
        if m:
            g.db.execute("UPDATE sessions SET model=? WHERE id=?", (model_name(m[0], ai), sid))
    nk = "session:" + key
    row = g.db.execute("SELECT id FROM nodes WHERE kind='session' AND key=?", (nk,)).fetchone()
    if row:
        nid = row[0]
        g.db.execute("UPDATE nodes SET label=?, updated=?, type=? WHERE id=?", (label, updated, ai, nid))
    else:
        nid = g.db.execute("INSERT INTO nodes(kind, key, label, type, created, updated, ctx) VALUES('session',?,?,?,?,?,?)",
                           (nk, label, ai, started, updated, key)).lastrowid
    count = Counter()
    for (ents,) in g.db.execute("SELECT ents FROM turns WHERE session=?", (sid,)):
        for k, lab, typ in json.loads(ents or "[]"):
            count[(k, lab, typ)] += 1
    g.db.execute("DELETE FROM edges WHERE src=? AND rel='discusses'", (nid,))
    for (k, lab, typ), c in count.most_common(25):
        if g.forgotten("entity", k):
            continue
        eid = g.ekeys.get(k) or (g.entity(k, lab, "tech", updated) if typ == "tech" else None)
        if eid:
            g.edge(nid, eid, "discusses", float(c))
    g.db.execute("DELETE FROM edges WHERE dst=? AND rel='said in'", (nid,))
    for (m,) in g.db.execute("""SELECT id FROM nodes WHERE kind='memory' AND (ctx=? OR EXISTS (SELECT 1 FROM json_each(nodes.sources)
                                WHERE json_extract(value, '$.ctx') = ?))""", (key, key)).fetchall():  # said here, even if first said elsewhere
        g.edge(m, nid, "said in")
    g.db.execute("DELETE FROM edges WHERE src=? AND rel='continues'", (nid,))
    par = g.db.execute("SELECT n.id FROM sessions s JOIN sessions p ON p.id = s.parent JOIN nodes n ON n.kind='session' AND n.key = 'session:' || p.key "
                       "WHERE s.id=?", (sid,)).fetchone()
    if par:
        g.edge(nid, par[0], "continues")
    g.dirty = True  # a new or grown chat can change what its topic is


def relink_all(g, reread=False):
    """reread: re-derive what each turn names (a rebuild: better rules, new entities) before linking."""
    if reread:
        for tid, text in g.db.execute("SELECT id, text FROM turns").fetchall():
            g.db.execute("UPDATE turns SET ents=? WHERE id=?", (json.dumps(_turn_ents(g, text)), tid))
    for (sid,) in g.db.execute("SELECT id FROM sessions ORDER BY parent IS NOT NULL, id").fetchall():
        link_session(g, sid)


def sessions(g, limit=40):
    return [meter(g, sid) for (sid,) in g.db.execute("SELECT id FROM sessions ORDER BY updated DESC LIMIT ?", (limit,)).fetchall()]


def transcript(g, sid):
    m = meter(g, sid)
    if m:
        m["messages"] = [{"n": n, "role": r, "text": t, "model": md, "ts": x} for n, r, t, md, x in
                         g.db.execute("SELECT n, role, text, model, ts FROM turns WHERE session=? ORDER BY n", (sid,))]
    return m


def find(g, ref=None):
    """A session by id, key, or words from its title/content; default: the most recently active."""
    if ref in (None, "", "latest", "last"):
        r = g.db.execute("SELECT id FROM sessions ORDER BY updated DESC LIMIT 1").fetchone()
        return r[0] if r else None
    if str(ref).isdigit():
        r = g.db.execute("SELECT id FROM sessions WHERE id=?", (int(ref),)).fetchone()
        if r:
            return r[0]
    r = g.db.execute("SELECT id FROM sessions WHERE key=? OR chat LIKE ? ORDER BY updated DESC LIMIT 1", (ref, f"%{ref}%")).fetchone()
    if r:
        return r[0]
    hits = search(g, str(ref), 1)
    return hits[0]["id"] if hits else None


def search(g, q, k=3):
    """Conversations whose turns match q, best first, with the matching snippet."""
    words = [w for w in re.findall(r"\w+", brain.expand(q).lower()) if w not in brain.STOP and len(w) > 1]
    if not words:
        return []
    try:
        rows = g.db.execute("""SELECT t.session, t.role, t.text, -bm25(turns_fts) FROM turns_fts JOIN turns t ON t.id = turns_fts.rowid
                               WHERE turns_fts MATCH ? ORDER BY bm25(turns_fts) LIMIT 60""",
                            (" OR ".join('"%s"' % w for w in dict.fromkeys(words)),)).fetchall()
    except Exception:
        return []
    best = {}
    for sid, role, text, score in rows:
        if sid not in best or score > best[sid][0]:
            best[sid] = (score, role, text)
    out = []
    for sid, (score, role, text) in sorted(best.items(), key=lambda x: -x[1][0])[:k]:
        m = meter(g, sid)
        low = text.lower()
        pos = min([low.find(w) for w in words if low.find(w) >= 0] or [0])
        m.update(snippet=handoff._clip(text[max(0, pos - 80):pos + 220], 240), role=role, score=round(score, 3))
        out.append(m)
    return out


# ---- hand-offs --------------------------------------------------------------------------------------------------------
def make_handoff(g, ref=None, budget=1500, to=None):
    sid = find(g, ref)
    if not sid:
        raise ValueError("no conversation to hand off yet — turn on Live mode in the extension, or save one over MCP")
    m = transcript(g, sid)
    turns = [{"role": t["role"], "text": t["text"]} for t in m["messages"]]
    about, _ = g.summary()
    seed = " ".join([m["chat"] or ""] + [t["text"][:300] for t in turns if t["role"] == "user"][-2:])
    said = {S().mkey(t["text"])[:200] for t in turns}
    related = [x["text"] for x in g.recall(seed, 8)["memories"] if S().mkey(x["text"])[:200] not in said][:5] if seed.strip() else []
    import ai
    summary = ai.cached(sid, turns)  # made outside the lock by ai.prepare; never a network call here
    pack = handoff.build({"ai": m["ai"], "chat": m["chat"]}, turns, about, related, budget_tokens=budget, summary=summary)
    pack["summary_by"] = summary and summary["by"]
    out = {**pack, "session": {k: m[k] for k in ("id", "ai", "chat", "url", "tokens", "window", "pct", "limit")}}
    if to:
        host = to if "." in to else {a.lower(): h for a, h in S().AI_SITE.items()}.get(to.lower(), to)
        g.db.execute("INSERT INTO pending(host, text, created, source) VALUES(?,?,?,?)", (host, pack["text"], time.time(), sid))
        out.update(to=host, open=NEW_CHAT.get(host))
    return out


def take_pending(g, host):
    """The newest hand-off waiting for this site's new chat, used once."""
    ai = S().SITES.get(host)  # chat.openai.com and chatgpt.com are the same AI
    same = [h for h, x in S().SITES.items() if ai and x == ai and "." in h] or [host]
    r = g.db.execute(f"SELECT id, text, source FROM pending WHERE host IN ({','.join('?' * len(same))}) AND used IS NULL AND created > ? "
                     "ORDER BY created DESC LIMIT 1", (*same, time.time() - PENDING_TTL)).fetchone()
    if not r:
        return {}
    g.db.execute("UPDATE pending SET used=? WHERE id=?", (time.time(), r[0]))
    src = meter(g, r[2]) if r[2] else None
    return {"text": r[1], "from": src and src["ai"], "chat": src and src["chat"]}


# ---- graph tools ------------------------------------------------------------------------------------------------------
STRUCT = ("similar", "about")  # hubs and soft links: not walked by default


def neighbors(g, nid, depth=1, limit=200):
    seen, frontier = {nid}, [nid]
    for _ in range(max(1, min(depth, 3))):
        nxt = []
        for x in frontier:
            for a, b, rel in g.db.execute("SELECT src, dst, rel FROM edges WHERE (src=? OR dst=?)", (x, x)):
                y = b if a == x else a
                if rel in STRUCT or y in seen:
                    continue
                seen.add(y)
                nxt.append(y)
                if len(seen) >= limit:
                    break
        frontier = nxt
    return g.subgraph(seen)


def path(g, a, b, max_depth=6):
    """Shortest chain of links between two nodes (breadth-first, both directions, hubs skipped)."""
    me = g.ekeys.get("me")
    prev, q = {a: None}, deque([(a, 0)])
    while q:
        x, d = q.popleft()
        if x == b:
            break
        if d >= max_depth:
            continue
        for s, t, rel in g.db.execute("SELECT src, dst, rel FROM edges WHERE src=? OR dst=?", (x, x)):
            y = t if s == x else s
            if y in prev or rel == "similar" or (y == me and b != me):
                continue
            prev[y] = (x, rel, s == x)
            q.append((y, d + 1))
    if b not in prev:
        return {"found": False, "steps": []}
    steps, y = [], b
    while prev[y]:
        x, rel, forward = prev[y]
        steps.append({"from": x, "to": y, "rel": rel, "forward": forward})
        y = x
    steps.reverse()
    ids = {a} | {s["to"] for s in steps}
    return {"found": True, "steps": steps, **g.subgraph(ids)}


def export(g, fmt="json"):
    nodes = g.db.execute("SELECT id, kind, key, label, type, created, updated, status, cluster, at FROM nodes").fetchall()
    edges = g.db.execute("SELECT src, dst, rel, weight FROM edges").fetchall()
    facts = g.db.execute("SELECT subj, rel, obj, valid_from, valid_to, memory FROM facts").fetchall()
    if fmt == "json":
        body = json.dumps({"nodes": [dict(zip(("id", "kind", "key", "label", "type", "created", "updated", "status", "topic", "at"), n)) for n in nodes],
                           "edges": [dict(zip(("src", "dst", "rel", "weight"), e)) for e in edges],
                           "facts": [dict(zip(("subject", "rel", "object", "valid_from", "valid_to", "memory"), f)) for f in facts]}, indent=1)
        return body.encode(), "application/json", "mindbaton.json"
    if fmt == "cypher":  # paste into Neo4j Browser or `cypher-shell < mindbaton.cypher`
        q = lambda s: json.dumps(s if s is not None else "")
        label = {"memory": "Memory", "entity": "Thing", "session": "Conversation"}
        lines = ["// Mindbaton export for Neo4j", "CREATE CONSTRAINT mb_id IF NOT EXISTS FOR (n:MB) REQUIRE n.mbid IS UNIQUE;"]
        for n in nodes:
            lines.append(f"CREATE (:MB:{label.get(n[1], 'Node')} {{mbid: {n[0]}, key: {q(n[2])}, text: {q(n[3])}, type: {q(n[4])}, "
                         f"created: {n[5] or 0}, status: {q(n[7])}}});")
        for s, d, rel, w in edges:
            r = re.sub(r"[^A-Z0-9]+", "_", rel.upper()).strip("_") or "LINK"
            lines.append(f"MATCH (a:MB {{mbid: {s}}}), (b:MB {{mbid: {d}}}) CREATE (a)-[:{r} {{weight: {w}}}]->(b);")
        return "\n".join(lines).encode(), "text/plain; charset=utf-8", "mindbaton.cypher"
    if fmt == "graphml":  # Gephi, yEd, Cytoscape, Neo4j APOC
        e = lambda s: html.escape(str(s if s is not None else ""), quote=True)
        out = ['<?xml version="1.0" encoding="UTF-8"?>', '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
               '<key id="kind" for="node" attr.name="kind" attr.type="string"/>', '<key id="label" for="node" attr.name="label" attr.type="string"/>',
               '<key id="type" for="node" attr.name="type" attr.type="string"/>', '<key id="rel" for="edge" attr.name="rel" attr.type="string"/>',
               '<key id="weight" for="edge" attr.name="weight" attr.type="double"/>', '<graph id="mindbaton" edgedefault="directed">']
        for n in nodes:
            out.append(f'<node id="n{n[0]}"><data key="kind">{e(n[1])}</data><data key="label">{e(n[3])}</data><data key="type">{e(n[4])}</data></node>')
        for s, d, rel, w in edges:
            out.append(f'<edge source="n{s}" target="n{d}"><data key="rel">{e(rel)}</data><data key="weight">{w}</data></edge>')
        out += ["</graph>", "</graphml>"]
        return "\n".join(out).encode(), "application/xml", "mindbaton.graphml"
    raise ValueError("format must be json, cypher or graphml")


# ---- Claude Code on this machine: its transcripts are Live sessions too -----------------------------------------------
NOISE = re.compile(r"<system-reminder>[\s\S]*?</system-reminder>|<local-command-[\w-]+>[\s\S]*?</local-command-[\w-]+>|"
                   r"<command-(?:name|message|args)>[\s\S]*?</command-(?:name|message|args)>|"
                   r"<(task-notification|bash-(?:input|stdout|stderr)|user-prompt-submit-hook)>[\s\S]*?</\1>", re.I)


def read_claude_code(path, tail_bytes=4_000_000):
    """User and assistant text from a Claude Code transcript (.jsonl); tool calls, tool output and harness notes dropped."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size > tail_bytes:
            f.seek(size - tail_bytes)
            f.readline()
        lines = f.read().decode("utf-8", "replace").splitlines()
    turns, title, cwds, ai_title = [], None, Counter(), None
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("type") == "summary" and r.get("summary"):
            title = r["summary"]
        if r.get("type") == "ai-title" and r.get("aiTitle"):
            ai_title = r["aiTitle"]  # the title Claude Code gives the session
        if r.get("type") not in ("user", "assistant") or r.get("isMeta") or r.get("isSidechain") or r.get("isCompactSummary"):
            continue
        if r["type"] == "user" and r.get("promptSource") == "system":
            continue  # sent by another session or the harness, not typed
        if r.get("cwd"):
            cwds[r["cwd"]] += 1
        msg = r.get("message") or {}
        content = msg.get("content")
        parts = [content] if isinstance(content, str) else [c.get("text", "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text"]
        text = NOISE.sub("", "\n".join(p for p in parts if p)).strip()
        if not text or text.startswith(("Caveat:", "[Request interrupted", "This session is being continued")):
            continue
        role = "assistant" if r["type"] == "assistant" else "user"
        model = msg.get("model") if role == "assistant" and not str(msg.get("model", "")).startswith("<") else None
        try:
            when = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")).timestamp() if r.get("timestamp") else None
        except ValueError:
            when = None
        if turns and turns[-1]["role"] == role:
            turns[-1]["text"] += "\n\n" + text  # one turn per speaker change
            turns[-1]["model"] = model or turns[-1].get("model")
        else:
            turns.append({"role": role, "text": text, "model": model, "ts": when})
    return turns, ai_title or title, project_dir(cwds)


def project_dir(cwds):
    """Where a coding session worked: the directory most of it ran in, preferring one inside a project over $HOME
    (sessions often start in ~ and cd into the project)."""
    home = os.path.expanduser("~").rstrip("/")
    inside = Counter({c: n for c, n in cwds.items() if c.rstrip("/") != home})
    return (inside or cwds).most_common(1)[0][0] if cwds else None


def watch_claude_code(g, lock, root=os.path.expanduser("~/.claude/projects"), every=30):
    """Keep Claude Code sessions on this machine in sync (a background thread in the server)."""
    seen = {}

    def scan():
        cutoff = time.time() - 7 * 86400
        for path in glob.glob(os.path.join(root, "*", "*.jsonl")):
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if mtime < cutoff or seen.get(path) == mtime:
                continue
            seen[path] = mtime
            turns, title, cwd = read_claude_code(path)
            if len(turns) < 2:
                continue
            sid = os.path.splitext(os.path.basename(path))[0]
            name = title or handoff._clip(next((t["text"] for t in turns if t["role"] == "user"), "Claude Code session"), 70)
            with lock:
                sync(g, None, "claude-code", name, turns, ts=mtime, key=f"claude-code/{sid}", cwd=cwd)

    def loop():
        while True:
            try:
                scan()
            except Exception as e:  # never take the server down over a transcript
                print("claude-code watcher:", e, flush=True)
            time.sleep(every)
    threading.Thread(target=loop, daemon=True, name="claude-code-watch").start()
