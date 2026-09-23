"""Mindbaton — long-term memory for all your AIs, on your own box. Stdlib only.

Every raw message is kept (secrets redacted) in `captures`; the graph — memories, entities, relations, topics — is
derived from them by brain.py, so improving the logic and bumping LOGIC_VERSION re-derives everything.

  POST   /capture   {"text", "site", "chat", "url", "ts"}                  <- browser extension
  POST   /remember  {"text", "entities": [..], "relations": [[a, rel, b]]}  <- agents
  GET    /recall?q=...&k=8      answer + ranked memories + the subgraph around them
  GET    /context?q=...         a briefing an AI can read: who the user is + what's relevant to q
  GET    /profile               everything known about the user, sorted
  GET    /graph                 all nodes, edges and topics (for the viewer)
  DELETE /node/<id>             forget (and stay forgotten across rebuilds)
  POST   /rebuild               re-derive the graph from captures
  POST   /mcp                   Model Context Protocol (streamable HTTP): the same, as tools for Claude, Cursor, …
Everything but the app's files, /health, login and pairing needs the owner's session cookie or a device token.

  python3 server.py [--check | --setup-code | --reset-password]
"""
import difflib, glob, hashlib, hmac, io, ipaddress, json, math, os, re, secrets, sqlite3, threading, time, uuid, zipfile
from datetime import datetime
from collections import deque, Counter, defaultdict
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))


def load_env(path=os.path.join(HERE, "mindbaton.env")):
    """KEY=value lines from mindbaton.env next to this file; the real environment wins."""
    try:
        for line in open(path, encoding="utf-8"):
            k, sep, v = line.strip().partition("=")
            if sep and k and not k.startswith("#"):
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
    except OSError:
        pass


load_env()
import ai, brain, handoff, live  # noqa: E402  (after the env file: ai.py reads its settings at import)

HOST = os.environ.get("MINDBATON_HOST", "127.0.0.1")
PORT = int(os.environ.get("MINDBATON_PORT", 3004))
DATA = os.path.expanduser(os.environ.get("MINDBATON_DATA") or os.path.join(HERE, "data"))  # db, ai_keys, access.log
DB = os.path.join(DATA, "mindbaton.db")
PUBLIC_URL = os.environ.get("MINDBATON_PUBLIC_URL", "").strip().rstrip("/") or None  # e.g. https://mindbaton.example.com
VERSION = "0.1.0"
LOCK = threading.Lock()  # one request touches the graph at a time; threads only keep idle sockets from blocking others
LOGIC_VERSION = "14"  # 14: hand-off packs and briefings are marked [mindbaton]
PERSONAL = brain.PERSONAL
AI_SITE = {}  # "ChatGPT" -> "chatgpt.com"
LINKISH = ("mentions", "about", "context")

SITES = {  # raw source (web host, local tool, MCP clientInfo.name) -> the AI's display name = its logo key in assets/icons
    "chatgpt.com": "ChatGPT", "chat.openai.com": "ChatGPT", "chat.com": "ChatGPT", "claude.ai": "Claude",
    "gemini.google.com": "Gemini", "aistudio.google.com": "Gemini", "www.perplexity.ai": "Perplexity", "perplexity.ai": "Perplexity",
    "chat.deepseek.com": "DeepSeek", "grok.com": "Grok", "copilot.microsoft.com": "Copilot", "copilot.com": "Copilot",
    "www.copilot.com": "Copilot", "poe.com": "Poe", "chat.mistral.ai": "Mistral",  # web hosts first: AI_SITE maps back to them
    "openai-mcp": "ChatGPT", "claude-ai": "Claude", "claude-desktop": "Claude",
    "claude-code": "Claude Code", "codex": "Codex", "codex-mcp-client": "Codex", "codex-cli": "Codex",
    "antigravity": "Antigravity", "antigravity-client": "Antigravity", "antigravity-cli": "Antigravity", "agy": "Antigravity",
    "cursor": "Cursor", "cursor-vscode": "Cursor", "windsurf": "Windsurf", "windsurf-client": "Windsurf",
    "visual-studio-code": "GitHub Copilot", "vscode": "GitHub Copilot", "github-copilot": "GitHub Copilot",
    "gemini-cli": "Gemini CLI", "gemini-cli-mcp-client": "Gemini CLI", "cline": "Cline", "zed": "Zed",
    "phone": "Phone", "agent": "agent", "mcp": "agent"}
for _host, _ai in SITES.items():
    AI_SITE.setdefault(_ai, _host)


def ai_of(site):
    """Any raw source -> one display name: 'antigravity-client', 'Antigravity' and 'agy' are all Antigravity."""
    raw = (site or "").strip()
    k = raw.lower()
    if k in SITES:
        return SITES[k]
    k = re.sub(r"^www\.", "", k)
    bare = re.sub(r"[-_ ](?:mcp[-_ ])?(?:client|cli|app|desktop|ide|extension)$", "", k)
    named = {v.lower(): v for v in SITES.values()}
    return SITES.get(k) or SITES.get(bare) or SITES.get("www." + k) or named.get(k) or named.get(bare) or raw or None
GENERIC_CHAT = re.compile(r"^(new chat|new thread|new conversation|untitled|chat|home|google ai studio|google gemini|le chat)$|^\[mindbaton|chat, work, create|^(chatgpt|claude|gemini|"
                          r"perplexity|deepseek|grok|copilot|poe|mistral)\b", re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS captures(id INTEGER PRIMARY KEY, ts REAL, text TEXT NOT NULL, site TEXT, chat TEXT, url TEXT, extra TEXT);
CREATE TABLE IF NOT EXISTS forgotten(kind TEXT, key TEXT, PRIMARY KEY(kind, key));
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS tokens(id INTEGER PRIMARY KEY, name TEXT, kind TEXT, scope TEXT, hash TEXT UNIQUE, created REAL,
  last_used REAL, revoked REAL);
CREATE TABLE IF NOT EXISTS logins(hash TEXT PRIMARY KEY, created REAL, expires REAL);
"""
DERIVED = """
CREATE TABLE IF NOT EXISTS nodes(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, key TEXT NOT NULL, label TEXT NOT NULL,
  type TEXT, importance REAL DEFAULT .5, created REAL, updated REAL, hits INTEGER DEFAULT 0, count INTEGER DEFAULT 1,
  status TEXT DEFAULT 'active', slots TEXT DEFAULT '[]', terms TEXT DEFAULT '{}', sources TEXT DEFAULT '[]', cluster INTEGER,
  rels TEXT DEFAULT '[]', sig TEXT, at REAL, conf REAL DEFAULT .5, ctx TEXT, cat TEXT, rank REAL, UNIQUE(kind, key));
CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY, subj TEXT, rel TEXT, obj TEXT, valid_from REAL, valid_to REAL,
  memory INTEGER, ended_by INTEGER);
CREATE INDEX IF NOT EXISTS facts_open ON facts(subj, rel, obj, valid_to);
CREATE TABLE IF NOT EXISTS edges(src INTEGER NOT NULL REFERENCES nodes ON DELETE CASCADE,
  dst INTEGER NOT NULL REFERENCES nodes ON DELETE CASCADE, rel TEXT NOT NULL, weight REAL DEFAULT 1, PRIMARY KEY(src, dst, rel));
CREATE INDEX IF NOT EXISTS edges_dst ON edges(dst);
CREATE INDEX IF NOT EXISTS nodes_sig ON nodes(sig);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(label, tokenize='porter unicode61');
"""
MEM_COLS = "id, label, type, importance, created, updated, hits, count, status, sources, cluster, at, conf, rels, ctx"


def covered_things(covered):
    """(rel, key) of the things the user has, uses, built or works on."""
    return [(r, b) for a, r, b in covered if a == "me" and r in ("has", "uses", "built", "working on")]


def mkey(text):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())


def chat_title(title, ai):
    title = brain.scrub(title or "").split("\n")[0]  # a harness wrapper or a pasted pack is not a title
    t = re.sub(r"\s*[-|–—]\s*(ChatGPT|Claude|Gemini|Google|Perplexity|Grok|DeepSeek|Copilot|Poe|Mistral).*$", "", title or "").strip()
    return None if not t or GENERIC_CHAT.search(t) or (ai and t.lower() == ai.lower()) else t[:120]


def conv_key(url, chat):
    """One conversation: the chat URL without query/fragment, else its title."""
    if url:
        u = urlparse(url)
        if u.path.strip("/") and u.path.rstrip("/") not in ("/new", "/app", "/chat", "/prompts/new_chat", "/search/new"):
            return (u.netloc + u.path)[:200]  # an app's new-chat page is no conversation yet
    return ("chat:" + chat.lower())[:200] if chat else None


def and_list(xs):
    xs = [x for x in xs if x]
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


def base_verb(v):
    """prefers -> prefer, spells -> spell, watches -> watch, tries -> try."""
    lem = brain.VERB.get(v.lower())
    if lem:
        return lem
    if re.search(r"[^aeiou]ies$", v):
        return v[:-3] + "y"
    if re.search(r"(ss|sh|ch|x|z|o)es$", v):
        return v[:-2]
    return v[:-1] if v.endswith("s") and not v.endswith("ss") else v


def third_to_first(text):
    """Agents write 'The user lives in Pune'; brain reads first person."""
    t = re.sub(r"\b(?:the user|user)'s\b", "my", text, flags=re.I)
    t = re.sub(r"\b(?:the user|user)\s+is\b", "I am", t, flags=re.I)
    t = re.sub(r"\b(?:the user|user)\s+has\b", "I have", t, flags=re.I)
    t = re.sub(r"\b(?:the user|user)\s+(\w+?s)\b", lambda m: "I " + base_verb(m[1]), t, flags=re.I)
    t = re.sub(r"\bthe user\b", "I", t, flags=re.I)                       # "the user" is a person; "user service" is not
    return re.sub(r"(^|[.!?]\s+)user\b(?=\s+\w+s\b)", r"\1I", t, flags=re.I)


class Graph:
    def __init__(self, path=DB):
        self.db = self.migrate(path)
        live.setup(self)
        self.db.executescript(DERIVED)
        self.topics, self.dirty = {}, True
        if self.meta("logic") != LOGIC_VERSION:
            self.rebuild()
        else:
            self.load()

    # ---- storage -------------------------------------------------------------------------------------------------
    @staticmethod
    def migrate(path):
        """v1 databases had no captures: keep their memories as captures and move the old file aside.
        v2 databases lack columns in the derived tables: drop them, a rebuild re-derives everything."""
        old = []
        if path != ":memory:" and os.path.exists(path):
            db = sqlite3.connect(path)
            cols = [r[1] for r in db.execute("PRAGMA table_info(nodes)")]
            if cols and "key" not in cols:
                old = db.execute("""SELECT n.label, n.created, (SELECT e.label FROM edges x JOIN nodes e ON e.id = x.dst
                    WHERE x.src = n.id AND e.label IN (%s)) FROM nodes n WHERE n.kind = 'memory'""" %
                                 ",".join("'%s'" % v for v in set(SITES.values()))).fetchall()
                db.close()
                for suffix in ("", "-wal", "-shm"):
                    if os.path.exists(path + suffix):
                        os.replace(path + suffix, path.replace(".db", ".v1.db") + suffix)
            else:
                if cols and ("rels" not in cols or "rank" not in cols):
                    db.executescript("DROP TABLE IF EXISTS edges; DROP TABLE IF EXISTS nodes; DROP TABLE IF EXISTS fts; DROP TABLE IF EXISTS facts;")
                db.close()
        db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)  # used under LOCK only
        db.executescript("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;" + SCHEMA)
        site_of = {v: k for k, v in SITES.items()}
        for text, ts, ai in old:
            db.execute("INSERT INTO captures(ts, text, site) VALUES(?,?,?)", (ts, text, site_of.get(ai)))
        return db

    def meta(self, k, v=None):
        if v is None:
            r = self.db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
            return r and r[0]
        self.db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (k, v))

    def load(self):
        self.vec, self.post = {}, defaultdict(set)
        for i, t in self.db.execute("SELECT id, terms FROM nodes WHERE kind='memory' AND status='active'"):
            self.index(i, json.loads(t))
        self.ekeys, self.ebucket = {}, defaultdict(set)
        for i, k in self.db.execute("SELECT id, key FROM nodes WHERE kind='entity'"):
            self.ekeys[k] = i
            self.ebucket[k[:1]].add(k)
        self.dirty = True

    def index(self, mid, terms):
        self.vec[mid] = terms
        for t in terms:
            self.post[t].add(mid)

    def unindex(self, mid):
        for t in self.vec.pop(mid, {}):
            self.post[t].discard(mid)

    def idf(self, t):
        return math.log((2 + len(self.vec)) / (1 + len(self.post.get(t, ()))))

    def sim(self, a, b):
        return brain.cosine(a, b, self.idf)

    def candidates(self, terms, limit=400):
        """Memories sharing the query's most specific terms (inverted index), instead of scanning everything."""
        rare = sorted((t for t in terms if t in self.post), key=lambda t: len(self.post[t]))[:8]
        out = set()
        for t in rare:
            out |= self.post[t]
            if len(out) > limit:
                break
        return out

    def forgotten(self, kind, key):
        """Forgetting outlives better understanding: a memory forgotten as 'my anme is maya' stays forgotten when a
        newer brain reads it as 'my name is maya'."""
        if kind == "memory":
            if getattr(self, "_forgot", None) is None:
                self._forgot = {k2 for (k,) in self.db.execute("SELECT key FROM forgotten WHERE kind='memory'")
                                for k2 in (k, mkey(brain.clean(k)))}
            return key in self._forgot or mkey(brain.clean(key)) in self._forgot
        return self.db.execute("SELECT 1 FROM forgotten WHERE kind=? AND key=?", (kind, key)).fetchone()

    def resolve(self, k):
        """Entity id for a key: exact, else a near spelling ('jellyfn' -> jellyfin). Model numbers match exactly."""
        if k in self.ekeys:
            return self.ekeys[k]
        if len(k) >= 5 and not any(ch.isdigit() for ch in k):
            best = None
            for c in self.ebucket.get(k[:1], ()):
                if abs(len(c) - len(k)) <= 2 and not any(ch.isdigit() for ch in c):
                    r = difflib.SequenceMatcher(None, k, c).ratio()
                    if r >= .88 and (best is None or r > best[0]):
                        best = (r, c)
            if best:
                return self.ekeys[best[1]]
        return None

    def entity(self, k, label, etype, ts):
        if k == "me":
            label, etype = "You", "self"
        i = self.resolve(k)
        if i:
            row = self.db.execute("SELECT label, type FROM nodes WHERE id=?", (i,)).fetchone()
            better = label if (row[0].islower() and not label.islower()) or row[1] in ("thing", "concept") and \
                etype in ("tech", "name", "person") and label.lower() == row[0].lower() else row[0]
            typ = etype if row[1] in ("thing", "concept") and etype in ("tech", "name", "person", "place", "org") else row[1]
            self.db.execute("UPDATE nodes SET count=count+1, updated=max(updated, ?), label=?, type=? WHERE id=?",
                            (ts, better, typ, i))
            return i
        i = self.db.execute("INSERT INTO nodes(kind, key, label, type, created, updated, cat) VALUES('entity',?,?,?,?,?,?)",
                            (k, label[:120], etype, ts, ts, brain.category_of(k))).lastrowid
        self.db.execute("INSERT INTO fts(rowid, label) VALUES(?,?)", (i, label))
        self.ekeys[k] = i
        self.ebucket[k[:1]].add(k)
        return i

    def edge(self, a, b, rel, w=1.0):
        self.db.execute("""INSERT INTO edges VALUES(?,?,?,?) ON CONFLICT(src, dst, rel)
                           DO UPDATE SET weight = weight + excluded.weight""", (a, b, rel, w))

    def asserting(self, triple, exclude=None):
        """Active memories that stated (subject, rel, object)."""
        return [r[0] for r in self.db.execute(
            "SELECT id FROM nodes WHERE kind='memory' AND status='active' AND rels LIKE ? AND id IS NOT ?",
            ('%' + json.dumps(list(triple)) + '%', exclude))]

    def when_of(self, mid, ts=None):
        """When a memory's facts became true: the event date it names if that's in the past, else when it was said."""
        r = self.db.execute("SELECT at, created FROM nodes WHERE id=?", (mid,)).fetchone() if mid else None
        said = (r[1] if r else None) or ts or time.time()
        return r[0] if r and r[0] and r[0] <= said else said

    def open_fact(self, a, rel, b, mid, when):
        if rel != "related" and not self.db.execute("SELECT 1 FROM facts WHERE subj=? AND rel=? AND obj=? AND valid_to IS NULL",
                                                    (a, rel, b)).fetchone():
            self.db.execute("INSERT INTO facts(subj, rel, obj, valid_from, memory) VALUES(?,?,?,?,?)", (a, rel, b, when, mid))

    def close_fact(self, a, rel, b, by, when):
        self.db.execute("""UPDATE facts SET valid_to=max(valid_from, ?), ended_by=? WHERE subj=? AND rel=? AND obj=?
                           AND valid_to IS NULL""", (when, by, a, rel, b))

    def retract(self, triple, by):
        """(subject, rel, object) is no longer true: drop the edge; memories that stated it retire only if nothing
        else they said is still true ("I'm a designer living in Mumbai" keeps the designer part after a move)."""
        ia, ib = self.ekeys.get(triple[0]), self.ekeys.get(triple[2])
        if ia and ib:
            self.db.execute("DELETE FROM edges WHERE src=? AND dst=? AND rel=?", (ia, ib, triple[1]))
        self.close_fact(*triple, by, self.when_of(by))
        for old in self.asserting(triple, exclude=by):
            live = [t for t in json.loads(self.db.execute("SELECT rels FROM nodes WHERE id=?", (old,)).fetchone()[0])
                    if tuple(t) != tuple(triple) and t[1] != "related" and self.edge_live(t)]
            if live:
                self.edge(by, old, "updates")
            else:
                self.retire(old, by)

    def retire(self, old, by):
        """A newer memory replaces an older one; relations only the old one stated go with it."""
        r = self.db.execute("SELECT rels, status FROM nodes WHERE id=?", (old,)).fetchone()
        if not r or r[1] != "active":
            return
        self.db.execute("UPDATE nodes SET status='superseded' WHERE id=?", (old,))
        self.edge(by, old, "replaces")
        self.unindex(old)
        for a, rel, b in json.loads(r[0]):
            if not self.asserting((a, rel, b)):
                ia, ib = self.ekeys.get(a), self.ekeys.get(b)
                if ia and ib:
                    self.db.execute("DELETE FROM edges WHERE src=? AND dst=? AND rel=?", (ia, ib, rel))
                self.close_fact(a, rel, b, by, self.when_of(by))

    # ---- ingest --------------------------------------------------------------------------------------------------
    def ingest(self, text, site=None, chat=None, url=None, ts=None, entities=None, relations=None, store=True, recluster=True,
               meta=None, ctx=None):
        """meta: where it came from beyond the site — session (conversation key), model, model_src, ai, client.
        Stored with the capture, so a rebuild re-derives the same attribution."""
        hint = brain.hints(text)
        text = brain.scrub(brain.redact(text))  # what the person typed: no harness wrappers, clocks or pasted packs
        if not text:
            return []
        ts = ts or hint["ts"] or time.time()
        meta = {k: v for k, v in dict(meta or {}, model=(meta or {}).get("model") or hint["model"]).items() if v}
        if site == "agent" and entities and not relations or site == "agent" and entities and all(r[1] == "on" for r in relations or []):
            ais = [e for e in entities if "." in AI_SITE.get(e, "")]  # the v1 extension named a web AI, not an agent's topic
            if ais and all(e in AI_SITE or e.startswith("chat: ") for e in entities):   # the v1 browser extension's shape
                site = AI_SITE[ais[0]]
                chat = next((e[6:] for e in entities if e.startswith("chat: ")), chat)
                entities = relations = None
        ai = meta.get("ai") or ai_of(site)
        chat = chat_title(chat, ai)
        ctx = ctx or meta.get("session") or conv_key(url, chat)
        if store and self.db.execute("SELECT 1 FROM captures WHERE text=? AND site IS ? AND ts=?", (text, site, ts)).fetchone():
            return []  # the same capture again (an import re-run, a retried send): nothing new
        if store:
            extra = {**({"entities": entities} if entities else {}), **({"relations": relations} if relations else {}), **meta}
            if ctx and ctx != conv_key(url, chat):
                extra["session"] = ctx
            self.db.execute("INSERT INTO captures(ts, text, site, chat, url, extra) VALUES(?,?,?,?,?,?)",
                            (ts, text, site, chat, url, json.dumps(extra) if extra else None))
        if entities or relations or site == "agent":   # an agent already understood it: keep its fact whole, add its structure
            me = ("me", "user", "i", "the user")
            first = third_to_first(text)
            mems = brain.analyse(first, ts)
            ents = [(brain.key(e), e, "name") for e in entities or []] + \
                   [(brain.key(x), x, "name") for a, _, b in relations or [] for x in (a, b) if x.lower() not in me]
            rels = [("me" if a.lower() in me else brain.key(a), r, brain.key(b)) for a, r, b in relations or []]
            if len(mems) != 1:
                t = brain.classify(first)
                mems = [dict(text=first[:2000], type="fact" if t in ("note", "question", "task") else t, entities=[],
                             relations=[r for m in mems for r in m["relations"]], retracts=[r for m in mems for r in m["retracts"]],
                             slots=[s for m in mems for s in m["slots"]], when=None, conf=.9, phrases=[], importance=.85)]
            m = mems[0]
            m["text"], m["conf"] = text[:2000], max(m["conf"], .85)
            m["type"] = m["type"] if m["type"] in PERSONAL else "fact"
            m["entities"] = list({e[0]: e for e in m["entities"] + ents}.values())
            m["relations"] = brain._dedupe(m["relations"] + rels)
            m["terms"] = brain.terms(text, m["entities"], m.get("phrases", []))
        else:
            mems = brain.analyse(text, ts, self.last_thing(ctx, ai, ts))
        src = {k: v for k, v in {"ai": ai, "chat": chat, "ts": ts, "ctx": ctx, "model": live.model_name(meta.get("model")),
                                 "note": 1 if (url or "").startswith("memory://") else None}.items() if v}
        for m in mems:
            self.link_known(m)
        self.db.execute("BEGIN")
        try:
            ids = []
            for m in mems:
                i = self.add(m, src, ts, ctx)
                if i:
                    ids.append(i)
                    if ctx and not [e for e in m["entities"] if e[2] not in ("value",)]:
                        self.context_links(i, ctx, ts)
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            self.load()
            raise
        self.dirty = True
        return ids

    def add(self, m, src, ts, ctx):
        k = mkey(m["text"])
        if not k or self.forgotten("memory", k):
            return None
        personal = m["type"] in PERSONAL
        rels = sorted({tuple(r) for r in m["relations"]})
        sig = json.dumps(sorted(r for r in rels if r[0] == "me")) if personal and any(r[0] == "me" for r in rels) else None
        # 1. the same thing said again -> reinforce: exact text, the same claims, or near-identical wording
        dup = self.db.execute("SELECT id FROM nodes WHERE kind='memory' AND key=?", (k,)).fetchone()
        if not dup and sig and not m["retracts"]:
            dup = self.db.execute("SELECT id FROM nodes WHERE kind='memory' AND status='active' AND sig=?", (sig,)).fetchone()
        if not dup and not m["slots"] and not m["retracts"]:
            best = max(((self.sim(m["terms"], self.vec[i]), i) for i in self.candidates(m["terms"]) if i in self.vec), default=(0, None))
            if best[0] >= .8 and self.same_side(best[1], personal):
                dup = (best[1],)
        if dup:
            row = self.db.execute("SELECT sources, status, conf FROM nodes WHERE id=?", dup).fetchone()
            if row[1] != "active" and not sig:
                return dup[0]
            sources = (json.loads(row[0]) + [src])[-20:]
            conf = 1 - (1 - (row[2] or .5)) * (1 - m["conf"] * .5)
            self.db.execute("""UPDATE nodes SET count=count+1, updated=max(updated, ?), importance=min(1, importance+.05),
                               sources=?, conf=? WHERE id=?""", (ts, json.dumps(sources), round(conf, 3), dup[0]))
            return dup[0]
        # 2. a new memory
        mid = self.db.execute("""INSERT INTO nodes(kind, key, label, type, importance, created, updated, slots, terms, sources,
                                 rels, sig, at, conf, ctx) VALUES('memory',?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                              (k, m["text"], m["type"], round(m["importance"], 3), ts, ts, json.dumps(m["slots"]),
                               json.dumps(m["terms"]), json.dumps([src]), json.dumps([list(r) for r in rels]), sig,
                               m.get("when"), m["conf"], ctx)).lastrowid
        self.db.execute("INSERT INTO fts(rowid, label) VALUES(?,?)", (mid, m["text"]))
        ent = {}
        for ek, label, etype in m["entities"]:
            if ek and not self.forgotten("entity", ek):
                ent[ek] = self.entity(ek, label, etype, ts)
                self.edge(mid, ent[ek], "mentions")
        if personal or any(a == "me" for a, _, _ in rels) or m["retracts"]:
            ent["me"] = self.entity("me", "You", "self", ts)
            self.edge(mid, ent["me"], "about")
        for a, rel, b in rels:
            for x in (a, b):
                if x not in ent and not self.forgotten("entity", x):
                    ent[x] = self.entity(x, x, "thing", ts)
            if a in ent and b in ent and ent[a] != ent[b]:
                if rel in brain.EXCLUSIVE:  # one value at a time: the stale value goes
                    for (old_dst,) in self.db.execute("SELECT dst FROM edges WHERE src=? AND rel=? AND dst!=?",
                                                      (ent[a], rel, ent[b])).fetchall():
                        old_key = self.db.execute("SELECT key FROM nodes WHERE id=?", (old_dst,)).fetchone()[0]
                        self.retract((a, rel, old_key), mid)
                self.edge(ent[a], ent[b], rel)
                self.open_fact(a, rel, b, mid, self.when_of(mid, ts))
        # 3. things taken back: "I don't use pihole anymore", "I left Infosys"
        for a, rel, b in m["retracts"]:
            ia, ib = (ent.get("me") or self.ekeys.get("me")), self.resolve(b)
            if not ia or not ib:
                continue
            b_key = self.db.execute("SELECT key FROM nodes WHERE id=?", (ib,)).fetchone()[0]
            for r in [rel] if rel else ["works at", "lives in", "uses", "has"]:
                if self.db.execute("SELECT 1 FROM edges WHERE src=? AND dst=? AND rel=?", (ia, ib, r)).fetchone():
                    self.retract(("me", r, b_key), mid)
        # 4. a newer value for the same slot ("my favourite movie is ...") replaces the older memory
        for slot in m["slots"]:
            if slot.startswith("me.") and slot[3:] in brain.EXCLUSIVE:
                continue  # handled above, fact by fact, so the rest of an older memory survives
            for (old,) in self.db.execute("""SELECT id FROM nodes WHERE kind='memory' AND status='active' AND id!=?
                                             AND slots LIKE ?""", (mid, '%' + json.dumps(slot) + '%')).fetchall():
                self.retire(old, mid)
        # 5. links to the most similar memories
        cands = [i for i in self.candidates(m["terms"]) if i in self.vec and i != mid]
        for s, other in sorted(((self.sim(m["terms"], self.vec[i]), i) for i in cands), reverse=True)[:3]:
            if s >= .2:
                self.edge(min(mid, other), max(mid, other), "similar", round(s, 3))
        self.index(mid, m["terms"])
        # 6. a phrase said in two memories becomes a concept ("thumbnail generator")
        for t in m["terms"]:
            if t.startswith("#") and len(self.post[t]) >= 2:
                p = t[1:]
                if p not in self.ekeys and not self.forgotten("entity", p) and len(p.split()) >= 2:
                    cid = self.entity(p, p, "concept", ts)
                    for other in self.post[t]:
                        self.edge(other, cid, "mentions")
                elif p in self.ekeys:
                    self.edge(mid, self.ekeys[p], "mentions")
        return mid

    def edge_live(self, triple):
        a, rel, b = triple
        ia, ib = self.ekeys.get(a), self.ekeys.get(b)
        return bool(ia and ib and self.db.execute("SELECT 1 FROM edges WHERE src=? AND dst=? AND rel=?", (ia, ib, rel)).fetchone())

    def last_thing(self, ctx, ai, ts):
        """What this conversation was last about: the named thing in its latest memory (same chat, else same AI within 15 min)."""
        row = self.db.execute("""SELECT e.key, e.label, e.type FROM nodes m JOIN edges x ON x.src = m.id AND x.rel = 'mentions'
            JOIN nodes e ON e.id = x.dst AND e.type IN ('name', 'project', 'tech')
            WHERE m.kind='memory' AND (m.ctx = ? OR (? IS NULL AND m.sources LIKE ? AND m.created > ?)) AND m.created <= ?
            ORDER BY m.created DESC, x.rowid LIMIT 1""", (ctx, ctx, '%"ai": ' + json.dumps(ai) + '%', ts - 900, ts)).fetchone()
        return tuple(row) if row else None

    def link_known(self, m):
        """Things already known are recognised when mentioned again, even lower-case or misspelt ("red car" ~ "rd car")."""
        have = {e[0] for e in m["entities"]}
        words = re.findall(r"[a-z0-9][a-z0-9.+#-]*", m["text"].lower())
        grams = {" ".join(words[i:i + n]) for n in (1, 2, 3) for i in range(len(words) - n + 1)}
        for g in grams:
            k = brain.key(g)
            if k in have or k == "me" or k in brain.STOP:
                continue
            i = self.ekeys.get(k)
            if not i and " " in g and len(g) >= 5:
                i = self.resolve(k)
            if i:
                row = self.db.execute("SELECT key, label, type FROM nodes WHERE id=?", (i,)).fetchone()
                if row and row[2] not in ("value", "self", "concept") and (" " in row[0] or not brain.is_word(row[0])):
                    m["entities"].append(tuple(row))
                    m["terms"]["@" + row[0]] = m["terms"].get("@" + row[0], 0) + 2
                    have.add(row[0])

    def context_links(self, mid, ctx, ts):
        """'make it without onion' names nothing; the conversation it belongs to does."""
        near = Counter()
        for (e,) in self.db.execute("""SELECT x.dst FROM nodes m JOIN edges x ON x.src = m.id AND x.rel = 'mentions'
                                       JOIN nodes e ON e.id = x.dst AND e.type NOT IN ('self', 'value')
                                       WHERE m.kind='memory' AND m.ctx=? AND m.id!=? AND m.created > ?""", (ctx, mid, ts - 86400)):
            near[e] += 1
        for e, _ in near.most_common(3):
            self.edge(mid, e, "context", .5)

    def same_side(self, mid, personal):
        t = self.db.execute("SELECT type FROM nodes WHERE id=?", (mid,)).fetchone()
        return t and (t[0] in PERSONAL) == personal

    # ---- sorting: topics = conversations, merged across apps by what they discuss -----------------------------------
    def ensure(self):
        if self.dirty:
            self.cluster()
            self.dirty = False

    TAU = 0.14  # average-linkage cosine to merge two conversations; F1 is flat from .10 to .20 on the owner's data
    HOME = os.path.basename(os.path.expanduser("~")).lower()
    PATH_DIR = re.compile(r"(?:/home/[^/\s]+|~)/([A-Za-z0-9][\w.-]*)")
    CODING = {"Claude Code", "Codex", "Antigravity", "Cursor", "Gemini CLI"}  # sessions run in a project directory

    def cluster(self):
        """1 unit = one conversation (a memory's ctx), else the memory alone. Its vector = its memories' terms + what the
        whole chat discusses (assistant turns name the project the user only implies). 2 units that ARE a project (an
        agent's memory file, a coding session run in ~/<dir>) own that name: same name -> pooled, different names -> never
        merged. 3 average-linkage agglomeration on tf-idf cosine. Every memory takes its conversation's topic."""
        db = self.db
        rows = db.execute("SELECT id, ctx, terms, importance, count FROM nodes WHERE kind='memory' AND status='active' ORDER BY id").fetchall()
        mems = [r[0] for r in rows]
        live_set = set(mems)
        unit, vec = {}, defaultdict(Counter)
        for m, ctx, terms, _, _ in rows:
            u = unit[m] = ctx or "m%d" % m
            vec[u].update({t: v for t, v in json.loads(terms).items() if not t.startswith("#")})
        for key, ent, w in db.execute("""SELECT s.ctx, e.key, x.weight FROM nodes s JOIN edges x ON x.src = s.id AND x.rel = 'discusses'
                                         JOIN nodes e ON e.id = x.dst WHERE s.kind = 'session'"""):
            if key in vec:
                vec[key]["@" + ent] += 1 + math.log(max(w, 1))
        # projects: memory files and coding sessions name them; units sharing a name are one project
        own, files = defaultdict(set), set()
        for (url,) in db.execute("SELECT DISTINCT url FROM captures WHERE url LIKE 'memory://%'"):
            n = url.rstrip("/").rsplit("/", 1)[-1].lower()
            files.add(n)
            own[conv_key(url, None)].add(n)
        for key, site, cwd in db.execute("SELECT key, site, cwd FROM sessions WHERE cwd IS NOT NULL"):
            rel = os.path.relpath(cwd, os.path.expanduser("~")) if cwd.startswith(os.path.expanduser("~")) else ""
            top = rel.split(os.sep)[0].lower() if rel and not rel.startswith("..") else ""
            if top and top != "." and not top.startswith(".") and ai_of(site) in self.CODING:
                own[key].add(top)
        dirs = defaultdict(Counter)
        for m, lab in db.execute("SELECT id, label FROM nodes WHERE kind='memory' AND status='active'"):
            dirs[unit[m]].update(d.lower() for d in self.PATH_DIR.findall(lab) if not d.startswith("."))
        alias = lambda u, ns: {d for d in [dirs[u].most_common(1)[0][0]] if d in ns or d not in files} if dirs[u] else set()
        own = {u: ns | alias(u, ns) for u, ns in own.items() if u in vec}  # a note naming ~/<another note's project> stays apart
        parent = {u: u for u in vec}

        def find(u):
            while parent[u] != u:
                parent[u] = parent[parent[u]]
                u = parent[u]
            return u
        first = {}
        for u in sorted(own):
            for n in own[u]:
                if n in first:
                    parent[find(u)] = find(first[n])
                else:
                    first[n] = u
        pooled, gown = defaultdict(Counter), defaultdict(set)
        for u in vec:
            pooled[find(u)].update(vec[u])
            gown[find(u)] |= own.get(u, set())
        unit_ctx = dict(unit)
        unit = {m: find(u) for m, u in unit.items()}
        # average-linkage merge over tf-idf cosine (sublinear tf, idf over units)
        names = sorted(pooled)
        df = Counter(t for u in names for t in pooled[u])
        idf = {t: math.log((1 + len(names)) / (1 + d)) for t, d in df.items()}
        post = defaultdict(list)
        for u in names:
            x = {t: (1 + math.log(v)) * idf[t] for t, v in pooled[u].items() if v > 0 and idf[t] > 0}
            norm = math.sqrt(sum(a * a for a in x.values())) or 1
            for t, a in x.items():
                post[t].append((u, a / norm))
        S = defaultdict(lambda: defaultdict(float))
        for lst in post.values():
            for i, (a, x) in enumerate(lst):
                for b, y in lst[i + 1:]:
                    S[a][b] += x * y
                    S[b][a] += x * y
        group = {u: [u] for u in names}
        while True:  # ponytail: full scan for the best pair per merge; a heap with lazy deletes past ~1000 conversations
            best, bp = self.TAU, None
            for a in group:
                for b, v in S[a].items():
                    if a < b and v >= best and not (gown[a] and gown[b] and not gown[a] & gown[b]):
                        best, bp = v, (a, b)
            if not bp:
                break
            a, b = bp
            na, nb = len(group[a]), len(group[b])
            for c in set(S[a]) | set(S[b]):
                if c not in (a, b):
                    S[a][c] = S[c][a] = (na * S[a].get(c, 0) + nb * S[b].get(c, 0)) / (na + nb)
                    S[c].pop(b, None)
            S[a].pop(b, None)
            S.pop(b, None)
            group[a] += group.pop(b)
            gown[a] |= gown.pop(b)
        top = {u: g for g, us in group.items() for u in us}
        groups = defaultdict(list)
        for m in mems:
            groups[top[unit[m]]].append(m)
        cid = {m: (min(g) if len(g) > 1 else None) for g in groups.values() for m in g}
        personal = {r[0] for r in db.execute("SELECT id FROM nodes WHERE kind='memory' AND type IN ('fact','preference','goal','event')")}
        for m in mems:  # facts about the user that fit no topic still belong together
            if cid[m] is None and m in personal:
                cid[m] = 0
        by_ent = defaultdict(list)
        for m, e, rel in db.execute("""SELECT x.src, x.dst, x.rel FROM edges x JOIN nodes n ON n.id = x.dst
                                       WHERE x.rel IN ('mentions','context') AND n.type NOT IN ('self','value')"""):
            by_ent[e].append((m, .5 if rel == "context" else 1))
        ent_topic = {}  # entities join the topic most of their memories are in
        for e, ms in by_ent.items():
            c = Counter(cid[m] for m, _ in ms if cid.get(m))
            if c:
                ent_topic[e] = c.most_common(1)[0][0]
        conv_topic = defaultdict(Counter)  # a conversation's topic: where most of its memories went
        for m, ctx, *_ in rows:
            if ctx:
                conv_topic[ctx][cid[m]] += 1
        db.execute("BEGIN")
        db.execute("UPDATE nodes SET cluster=NULL")
        db.executemany("UPDATE nodes SET cluster=? WHERE id=?",
                       [(c, m) for m, c in cid.items() if c is not None] + [(c, e) for e, c in ent_topic.items()])
        chat_topic = {k: c.most_common(1)[0][0] for k, c in conv_topic.items() if c.most_common(1)[0][0] is not None}
        # a chat with no memories of its own (only answers, a saved summary) takes the topic of what it discusses,
        # else of the chat it continues
        for key, par in db.execute("""SELECT s.key, p.key FROM sessions s LEFT JOIN sessions p ON p.id = s.parent
                                      ORDER BY s.parent IS NOT NULL""").fetchall():
            if key in chat_topic:
                continue
            votes = Counter()
            for e, w in db.execute("""SELECT x.dst, x.weight FROM nodes n JOIN edges x ON x.src = n.id AND x.rel = 'discusses'
                                      WHERE n.kind = 'session' AND n.ctx = ?""", (key,)):
                if ent_topic.get(e):
                    votes[ent_topic[e]] += w
            if votes and votes.most_common(1)[0][1] >= 2:
                chat_topic[key] = votes.most_common(1)[0][0]
            elif par in chat_topic:
                chat_topic[key] = chat_topic[par]
        db.executemany("UPDATE nodes SET cluster=? WHERE kind='session' AND ctx=?", [(c, k) for k, c in chat_topic.items()])
        db.execute("COMMIT")
        # names: the project it is, else the title an AI gave its main chat, else its most characteristic things
        self.topics = {}
        info = {r[0]: r[1:] for r in db.execute("SELECT id, label, type FROM nodes WHERE kind='entity' AND key!='me'")}
        elabel = dict(db.execute("SELECT key, label FROM nodes WHERE kind='entity'"))
        prefer = {"tech": 1.3, "name": 1.3, "project": 1.4, "concept": 1.2, "person": 1.1, "org": 1.1, "place": 1, "thing": .8}
        medium = {brain.key(v) for v in SITES.values()} | {w for v in SITES.values() for w in brain.key(v).split()}
        titled = {k: c for k, c in db.execute("SELECT key, chat FROM sessions WHERE chat IS NOT NULL")}
        members = defaultdict(list)
        for m, c in cid.items():
            if c is not None:
                members[c].append(m)
        weight = {r[0]: (r[3] or 0) + .05 * (r[4] or 1) for r in rows}
        mkeys = dict(db.execute("SELECT id, key FROM nodes WHERE kind='memory' AND status='active'"))
        ctx_of = {m: ctx for m, ctx, *_ in rows}
        named = json.loads(self.meta("topic_names") or "{}")  # AI names, keyed by what the topic is made of
        self._naming = {}
        for c, ms in members.items():
            rep = max(ms, key=lambda m: weight.get(m, 0))
            summ = (db.execute("SELECT label FROM nodes WHERE id=?", (rep,)).fetchone() or [""])[0][:200]
            owners = sorted(gown.get(top[unit[ms[0]]], ()), key=lambda n: (n not in files, -len(n), n))
            convs = Counter(unit_ctx[m] for m in ms if unit_ctx.get(m) in titled)
            if c == 0:
                name = "About you"
            elif owners:
                n = owners[0]
                name = elabel.get(n) or elabel.get(n.replace("-", " ")) or n
            elif convs and len(titled[convs.most_common(1)[0][0]]) <= 48:
                name = titled[convs.most_common(1)[0][0]]
            else:
                ents = Counter()
                for e, lst in by_ent.items():
                    k = sum(w for m, w in lst if cid.get(m) == c)
                    if k and e in info and brain.key(info[e][0]) not in medium:
                        ents[e] = k * math.log(1 + len(live_set) / len(lst)) * prefer.get(info[e][1], 1)
                nm = []
                for e, _ in ents.most_common(6):  # two names that don't repeat each other
                    n = info[e][0]
                    if not any(n.lower() in x.lower() or x.lower() in n.lower() for x in nm):
                        nm.append(n)
                    if len(nm) == 2:
                        break
                if not nm:
                    tc = Counter()
                    for m in ms:
                        for t, v in self.vec.get(m, {}).items():
                            if not t.startswith(("@", "#")):
                                tc[t] += v * self.idf(t)
                    nm = [t for t, _ in tc.most_common(2)]
                name = " · ".join(nm) or "misc"
            sig = hashlib.sha1("|".join(sorted({ctx_of.get(m) or "k:" + mkeys.get(m, "") for m in ms})).encode()).hexdigest()[:16]
            ai_name = named.get(sig) if c != 0 else None
            self.topics[c] = {"id": c, "name": ai_name["name"] if ai_name else name, "size": len(ms),
                              "summary": (ai_name or {}).get("summary") or summ, "by": "ai" if ai_name else "rules", "sig": sig}
            if c != 0 and not ai_name:
                self._naming[sig] = {"ref": f"t{c}", "sig": sig, "rule_name": name, "project": owners[0] if owners else None,
                                     "chats": [titled[k] for k, _ in convs.most_common(4)],
                                     "lines": [brain.redact(db.execute("SELECT label FROM nodes WHERE id=?", (m,)).fetchone()[0])[:160]
                                               for m in sorted(ms, key=lambda m: -weight.get(m, 0))[:6]]}
        self.pagerank(by_ent)
        if self._naming and getattr(self, "naming", False):
            ai.warm_topics(self, LOCK, apps=set(SITES.values()))

    def topics_to_name(self):
        self._asked_gen = getattr(self, "names_gen", 0)
        return list(getattr(self, "_naming", {}).values())[:30]

    def save_topic_names(self, got):
        """AI names for topics (keyed by membership signature); applied now and at every later re-sort."""
        if getattr(self, "_asked_gen", 0) != getattr(self, "names_gen", 0):
            return  # something was forgotten while the AI was naming: its answer may quote it
        named = json.loads(self.meta("topic_names") or "{}")
        named.update(got)
        self.meta("topic_names", json.dumps(dict(list(named.items())[-500:])))
        for t in self.topics.values():
            if t.get("sig") in got:
                t.update(name=got[t["sig"]]["name"], summary=got[t["sig"]]["summary"] or t["summary"], by="ai")
                self._naming.pop(t["sig"], None)

    def pagerank(self, by_ent, iters=30, d=.85):
        """How central each thing is: PageRank over relations and shared mentions (sizes things in the map)."""
        ents = {r[0] for r in self.db.execute("SELECT id FROM nodes WHERE kind='entity'")}
        if not ents:
            return
        w = defaultdict(lambda: defaultdict(float))
        for a, b, rel, wt in self.db.execute("SELECT src, dst, rel, weight FROM edges"):
            if a in ents and b in ents and rel not in ("related",):
                w[a][b] += wt
                w[b][a] += wt
        per_mem = defaultdict(list)
        for e, lst in by_ent.items():
            for m, _ in lst:
                per_mem[m].append(e)
        for es in per_mem.values():
            for i, a in enumerate(es):
                for b in es[i + 1:]:
                    w[a][b] += 1 / len(es)
                    w[b][a] += 1 / len(es)
        n = len(ents)
        rank = {e: 1 / n for e in ents}
        out = {e: sum(w[e].values()) for e in ents}
        for _ in range(iters):
            new = {e: (1 - d) / n for e in ents}
            for a in ents:
                if out[a]:
                    share = d * rank[a] / out[a]
                    for b, wt in w[a].items():
                        new[b] += share * wt
                else:
                    for b in ents:
                        new[b] += d * rank[a] / n
            rank = new
        top = max(rank.values()) or 1
        self.db.execute("BEGIN")
        self.db.executemany("UPDATE nodes SET rank=? WHERE id=?", [(round(v / top, 4), e) for e, v in rank.items()])
        self.db.execute("COMMIT")

    # ---- answering -----------------------------------------------------------------------------------------------
    TEMPLATES = {"lives in": "You live in {}.", "works at": "You work at {}.", "named": "Your name is {}.", "age": "You're {}.",
                 "is": "You're {}.", "uses": "You use {}.", "has": "You have {}.", "likes": "You like {}.",
                 "dislikes": "You dislike {}.", "working on": "You're working on {}.", "learning": "You're learning {}.",
                 "studies": "You study {}.", "allergic to": "You're allergic to {}.", "avoids": "You avoid {}.",
                 "wants": "You want {}.", "wants to visit": "You want to visit {}.", "wants to try": "You want to try {}.",
                 "wants to switch to": "You want to switch to {}.", "plans to move to": "You plan to move to {}.",
                 "from": "You're from {}."}

    def me_edges(self, rel):
        me = self.ekeys.get("me")
        if not me:
            return []
        return self.db.execute("""SELECT n.id, n.key, n.label, n.cat, x.weight FROM edges x JOIN nodes n ON n.id = x.dst
                                  WHERE x.src=? AND x.rel=? ORDER BY x.weight DESC, n.updated DESC""", (me, rel)).fetchall()

    PAST = {"lives in": "you lived in {}", "works at": "you worked at {}", "uses": "you used {}", "has": "you had {}",
            "likes": "you liked {}", "dislikes": "you disliked {}", "named": "your name was {}", "is": "you were {}",
            "working on": "you were working on {}", "learning": "you were learning {}", "from": "you were from {}"}

    def answer_at(self, Q):
        """'Where did I live in March?' — answered from the history of facts, not just the current ones."""
        at = Q["at"]
        for rel in Q["intent"]:
            rows = self.db.execute("""SELECT f.obj, f.memory, n.label FROM facts f LEFT JOIN nodes n ON n.kind='entity' AND n.key=f.obj
                                      WHERE f.subj='me' AND f.rel=? AND f.valid_from <= ? AND (f.valid_to IS NULL OR f.valid_to > ?)
                                      ORDER BY f.valid_from DESC""", (rel, at, at)).fetchall()
            if rows:
                names = and_list(list(dict.fromkeys(r[2] or r[0] for r in rows))[:5])
                date = datetime.fromtimestamp(at).strftime("%-d %b %Y")
                text = f"Around {date}, " + self.PAST.get(rel, "you " + rel + " {}").format(names) + "."
                return {"text": text, "relation": rel, "at": at, "sources": [r[1] for r in rows if r[1]][:5]}
        return None

    def answer(self, Q):
        """A direct answer when the question asks for a known relation: 'where do I live' -> 'You live in Lisbon.'"""
        if not self.ekeys.get("me"):
            return None
        if Q.get("at") and Q["intent"] and Q["at"] < time.time() - 86400:
            past = self.answer_at(Q)
            if past:
                return past
        for kin in Q["kin"]:
            people = self.me_edges(kin)
            if people:
                parts = []
                for pid, pkey, plabel, _, _ in people[:2]:
                    about = self.db.execute("""SELECT x.rel, n.label FROM edges x JOIN nodes n ON n.id = x.dst
                                               WHERE x.src=? AND x.rel IN ('is','lives in','works at','likes','studies')""", (pid,)).fetchall()
                    desc = "; ".join(("a " + l if r == "is" else f"{r} {l}") for r, l in about)
                    name = plabel if not plabel.startswith("your ") else ""
                    parts.append((f"Your {kin} is {name}" if name else f"Your {kin}") + (f" — {desc}" if desc else "") + ".")
                    src = [i for pk in [pkey] for i in self.asserting(("me", kin, pk))] + \
                          [i for r, l in about for i in self.asserting((pkey, r, brain.key(l)))]
                return {"text": " ".join(parts), "relation": kin, "sources": sorted(set(src))[-5:]}
        if Q["favourite"]:
            slot = "me.favourite " + Q["favourite"]
            row = self.db.execute("""SELECT id, rels FROM nodes WHERE kind='memory' AND status='active' AND slots LIKE ?
                                     ORDER BY updated DESC""", ('%' + json.dumps(slot) + '%',)).fetchone()
            if row:
                likes = [b for a, r, b in json.loads(row[1]) if a == "me" and r == "likes"]
                labels = [self.db.execute("SELECT label FROM nodes WHERE key=? AND kind='entity'", (b,)).fetchone() for b in likes]
                if labels and labels[0]:
                    return {"text": f"Your favourite {Q['favourite']} is {labels[0][0]}.", "relation": "likes", "sources": [row[0]]}
        for rel in Q["intent"]:
            if rel == "kin":
                continue
            rows = self.me_edges(rel)
            if Q["cats"]:
                keep = []
                for i, k, lab, cat, w in rows:
                    if cat in Q["cats"]:
                        keep.append((i, k, lab))
                    for j, k2, lab2, cat2 in self.db.execute("""SELECT n.id, n.key, n.label, n.cat FROM edges x JOIN nodes n
                                                               ON n.id = x.dst WHERE x.src=? AND x.rel='is'""", (i,)):
                        if cat2 in Q["cats"]:
                            keep.append((j, k2, lab2))
                rows = [(i, k, lab, None, 0) for i, k, lab in dict.fromkeys(keep)]
            if not rows:
                continue
            rows = rows[:1] if rel in brain.EXCLUSIVE else rows[:6]
            names = []
            for i, k, lab, _, _ in rows:
                desc = self.db.execute("""SELECT n.label FROM edges x JOIN nodes n ON n.id = x.dst WHERE x.src=? AND x.rel='is'
                                          LIMIT 1""", (i,)).fetchone()
                names.append(lab + (f" ({desc[0]})" if desc and rel not in ("is",) else ""))
            text = self.TEMPLATES.get(rel, "You " + rel + " {}.").format(and_list(names))
            if rel == "is":
                text = "You're " + and_list([("an " if n[:1].lower() in "aeiou" else "a ") + n for n in names]) + "."
            src = sorted({s for _, k, _, _, _ in rows for s in self.asserting(("me", rel, k))})
            return {"text": text, "relation": rel, "sources": src[-5:]}
        return None

    # ---- retrieval -----------------------------------------------------------------------------------------------
    def recall(self, q, k=8, include_old=False):
        self.ensure()
        Q = brain.query(q)
        words = {w for w in re.findall(r"[\w.+#-]+", Q["text"].lower()) if w not in brain.STOP and len(w) > 1}
        if not words and not Q["intent"] and not Q["about_me"] and not Q["kin"]:
            return {"answer": None, "memories": [], "nodes": [], "edges": []}
        hits = self.db.execute("""SELECT n.id, n.kind, -bm25(fts) FROM fts JOIN nodes n ON n.id = fts.rowid
                                  WHERE fts MATCH ? ORDER BY bm25(fts) LIMIT 120""",
                               (" OR ".join('"%s"' % w.replace('"', '') for w in words),)).fetchall() if words else []
        top_m = max([s for _, kind, s in hits if kind == "memory"], default=1) or 1
        top_e = max([s for _, kind, s in hits if kind == "entity"], default=1) or 1
        text = {i: s / top_m for i, kind, s in hits if kind == "memory"}
        act = {i: .8 * s / top_e for i, kind, s in hits if kind == "entity"}
        for ek, _, _ in Q["entities"]:
            if (i := self.resolve(ek)):
                act[i] = 1.0
        for w in words:  # typos: "jellyfn"
            if len(w) >= 5 and (i := self.resolve(w)) and i not in act:
                act[i] = .8
        for cat in Q["cats"]:
            for (i,) in self.db.execute("SELECT id FROM nodes WHERE kind='entity' AND cat=?", (cat,)):
                act[i] = max(act.get(i, 0), .7)
        me = self.ekeys.get("me")
        for kin in Q["kin"]:
            for i, *_ in self.me_edges(kin):
                act[i] = 1.0
        if me and Q["about_me"]:
            act[me] = 1.0
        graph = defaultdict(float)
        for e, a in act.items():  # spreading activation: entity -> its memories; 1 hop -> neighbours' memories
            for m, rel in self.db.execute("SELECT src, rel FROM edges WHERE dst=? AND rel IN ('mentions','about','context')", (e,)):
                graph[m] += a * (.5 if rel == "context" else 1)
            if e == me:
                continue  # "you" is a hub: spreading from it adds only noise
            for (n,) in self.db.execute("""SELECT dst FROM edges x JOIN nodes y ON y.id = x.dst WHERE x.src=? AND y.kind='entity'
                                           AND x.rel NOT IN ('mentions','about','context') AND y.key != 'me'
                                           UNION SELECT x.src FROM edges x JOIN nodes y ON y.id = x.src
                                           WHERE x.dst=? AND y.kind='entity' AND y.key != 'me'""", (e, e)).fetchall():
                for (m,) in self.db.execute("SELECT src FROM edges WHERE dst=? AND rel='mentions'", (n,)):
                    graph[m] += .4 * a
        ans = self.answer(Q)
        bonus = defaultdict(float)
        if ans:
            for i in ans["sources"]:
                bonus[i] += 1.2
        qwords = {t for t in Q["terms"] if not t.startswith(("@", "#"))}
        titled, title_terms = {}, {}  # conversations whose title shares the question's words
        for c, in self.db.execute("SELECT DISTINCT ctx FROM nodes WHERE kind='memory' AND ctx IS NOT NULL"):
            tw = {brain.stem(w) for w in re.findall(r"[a-z0-9]+", c.split("/")[-1].replace("chat:", "").lower()) if w not in brain.STOP}
            hit = {t for t in tw if t in qwords or len(t) >= 4 and any(q.startswith(t) or t.startswith(q) for q in qwords if len(q) >= 4)}
            if tw and (len(hit) >= min(2, len(tw)) or len(tw) <= 3 and any(len(t) >= 4 for t in hit)):
                titled[c] = len(hit) / len(tw)
                title_terms[c] = {t: 1 for t in tw} | {q: 1 for q in qwords if any(q.startswith(t) or t.startswith(q) for t in hit)}
        tboost = defaultdict(float)
        for c, share in titled.items():
            for (m,) in self.db.execute("SELECT id FROM nodes WHERE kind='memory' AND status='active' AND ctx=?", (c,)):
                tboost[m] += .6 * share
        pool = set(text) | set(graph) | set(tboost) | set(bonus) | self.candidates(Q["terms"])
        info = {r[0]: r for r in self.db.execute(
            f"SELECT {MEM_COLS} FROM nodes WHERE kind='memory' AND id IN ({','.join('?' * len(pool)) or 'NULL'})", list(pool))}
        now = time.time()

        qweight = sum(self.idf(t) for t in qwords)

        def score_all(qv):
            out = {}
            for m, r in info.items():
                if r[8] != "active" and not include_old:
                    continue
                vec, words = self.vec.get(m, {}), qwords
                if r[14] in title_terms:  # inside a conversation the question names, the rest of the question decides
                    rest = {t for t in Q["base"] if not t.startswith(("@", "#")) and t not in title_terms[r[14]]}
                    if rest:
                        words = rest
                wsum = sum(self.idf(t) for t in words)
                cover = sum(self.idf(t) for t in words if t in vec or brain.SYN_OF.get(t, set()) & vec.keys()) / wsum if wsum else 0
                damp = (.35 + .65 * cover) if words is not qwords else 1   # a sibling that misses the rest of the question fades
                sem = (self.sim(qv, vec) if vec else 0) * damp
                tx = text.get(m, 0) * damp
                rel = .45 * tx + .35 * sem + .3 * cover + .3 * (min(graph.get(m, 0), 1.5) * damp + tboost.get(m, 0)) + bonus.get(m, 0)
                if rel <= .08:
                    continue
                if Q["types"] and r[2] in Q["types"]:
                    rel *= 1.25
                if Q["first_person"] and r[2] in PERSONAL:
                    rel *= 1.15
                if Q["window"] and Q["window"][0] <= (r[11] or r[4]) <= Q["window"][1]:
                    rel += .3
                recency = math.exp(-(now - r[5]) / 86400 / 60)
                out[m] = rel * (.7 + .3 * r[3]) * (.85 + .15 * (r[12] or .5)) + .08 * recency + .04 * math.log1p(r[6] + r[7])
            return out

        score = score_all(Q["terms"])
        if score and not ans:  # pseudo-relevance feedback: the best hits suggest words the question didn't use
            fb = Counter()
            for m in sorted(score, key=score.get, reverse=True)[:3]:
                for t, v in self.vec.get(m, {}).items():
                    if t not in Q["terms"] and not t.startswith("#"):
                        fb[t] += v * self.idf(t)
            if fb:
                top = fb.most_common(6)
                mx = top[0][1]
                qv = dict(Q["terms"])
                for t, v in top:
                    qv[t] = qv.get(t, 0) + .35 * v / mx
                for m in self.candidates(dict(top)):
                    if m not in info:
                        r = self.db.execute(f"SELECT {MEM_COLS} FROM nodes WHERE id=?", (m,)).fetchone()
                        if r:
                            info[m] = r
                again = score_all(qv)
                score = {m: max(score.get(m, 0), .9 * s) for m, s in again.items()}
        for a, b, w in self.db.execute("SELECT src, dst, weight FROM edges WHERE rel='similar'").fetchall() if not Q["about_me"] else []:
            for x, y in ((a, b), (b, a)):  # a strong neighbour lends a little relevance
                if x in score and y not in score and y in self.vec:
                    score[y] = .25 * w * score[x]
                    if y not in info:
                        info[y] = self.db.execute(f"SELECT {MEM_COLS} FROM nodes WHERE id=?", (y,)).fetchone()
        # maximal marginal relevance: don't spend the top slots on three wordings of the same thing
        ranked = sorted(score, key=score.get, reverse=True)[:40]
        if ranked:  # drop the long tail; when there's an answer, a weak result tied to nothing the question names is noise
            best = score[ranked[0]]           # ("qr code" for "which code editor do I use")
            ranked = [m for m in ranked if score[m] >= max(.12, .2 * best) and not (ans and not graph.get(m) and score[m] < .45 * best)]
        top, mx = [], (score[ranked[0]] if ranked else 1)
        while ranked and len(top) < k:
            best = max(ranked, key=lambda m: .8 * score[m] / mx - .2 * max((self.sim(self.vec.get(m, {}), self.vec.get(t, {}))
                                                                             for t in top), default=0))
            top.append(best)
            ranked.remove(best)
        if top:
            self.db.executemany("UPDATE nodes SET hits=hits+1 WHERE id=?", [(i,) for i in top])
        ids = set(top)
        for i in top:
            ids.update(r[0] for r in self.db.execute("SELECT dst FROM edges WHERE src=? AND rel IN ('mentions','about')", (i,)))
        convs = live.search(self, q, 3)
        return {"answer": ans, "intent": Q["intent"], "memories": [self.mem(info[i], score[i]) for i in top],
                "conversations": convs, **self.subgraph(ids)}

    def mem(self, r, score=None):
        srcs = self.sources(r[9])
        d = {"id": r[0], "text": r[1], "type": r[2], "importance": r[3], "created": r[4], "updated": r[5], "count": r[7],
             "status": r[8], "at": r[11], "conf": r[12], "ais": sorted({s["ai"] for s in srcs if s.get("ai")}),
             "chats": sorted({s["chat"] for s in srcs if s.get("chat")}), "models": sorted({s["model"] for s in srcs if s.get("model")}),
             "srcs": srcs, "topic": self.topics.get(r[10], {}).get("name")}
        if score is not None:
            d["score"] = round(score, 3)
        return d

    # ---- the user, summarised --------------------------------------------------------------------------------------
    def summary(self):
        """What is known about the user as short lines, strongest first. Also the triples they cover."""
        covered, lines = set(), []

        def vals(rel, n=8, describe=True):
            out = []
            for i, k, lab, _, _ in self.me_edges(rel)[:n]:
                covered.add(("me", rel, k))
                desc = self.db.execute("""SELECT n.label, n.key FROM edges x JOIN nodes n ON n.id = x.dst WHERE x.src=? AND x.rel='is'
                                          LIMIT 1""", (i,)).fetchone() if describe else None
                if desc:
                    covered.add((k, "is", desc[1]))
                out.append(lab + (f" ({desc[0]})" if desc else ""))
            return out
        name, age, roles = vals("named", 1), vals("age", 1), vals("is", 3, False)
        work, home, origin = vals("works at", 1), vals("lives in", 1), vals("from", 1)
        who = ", ".join(x for x in (name[0] if name else "", age[0] if age else "") if x)
        role = and_list(roles) + (" at " + work[0] if work else "") if roles else ("works at " + work[0] if work else "")
        place = ("lives in " + home[0] if home else "") + (f" (from {origin[0]})" if origin else "")
        first = " — ".join(x for x in (who, "; ".join(y for y in (role, place) if y)) if x)
        if first:
            lines.append(first)
        for rel, title in (("working on", "Working on"), ("built", "Built"), ("learning", "Learning"), ("studies", "Studies"), ("uses", "Uses"),
                           ("has", "Has"), ("likes", "Likes"), ("dislikes", "Dislikes"), ("allergic to", "Allergic to"),
                           ("avoids", "Avoids"), ("wants", "Wants"), ("wants to visit", "Wants to visit"),
                           ("wants to try", "Wants to try"), ("plans to move to", "Plans to move to")):
            v = vals(rel, 10)
            if v:
                lines.append(f"{title}: {', '.join(v)}")
        me = self.ekeys.get("me")
        if me:
            people = []
            for rel, pid, pkey, plabel in self.db.execute("""SELECT x.rel, n.id, n.key, n.label FROM edges x JOIN nodes n ON n.id = x.dst
                                                             WHERE x.src=? AND n.type='person'""", (me,)).fetchall():
                covered.add(("me", rel, pkey))
                about = [("a " + l if r == "is" else l) for r, l in self.db.execute(
                    "SELECT x.rel, n.label FROM edges x JOIN nodes n ON n.id = x.dst WHERE x.src=? AND x.rel IN ('is','lives in','works at')", (pid,))]
                name = "" if plabel.startswith("your ") else " " + plabel
                people.append(f"{rel}{name}" + (f" ({', '.join(about)})" if about else ""))
            if people:
                lines.append("People: " + "; ".join(people))
        return lines, covered

    def profile(self):
        self.ensure()
        rows = self.db.execute(f"""SELECT {MEM_COLS} FROM nodes WHERE kind='memory' AND status='active'
            AND type IN ('preference','fact','goal','event') ORDER BY importance * (1 + .1 * count) * conf DESC, updated DESC""").fetchall()
        lines, _ = self.summary()
        out = {t: [self.mem(r) for r in rows if r[2] == t] for t in ("fact", "preference", "goal", "event")}
        me = self.ekeys.get("me")
        out["relations"] = [{"rel": r, "label": l, "id": i} for r, l, i in self.db.execute(
            """SELECT x.rel, n.label, n.id FROM edges x JOIN nodes n ON n.id = x.dst WHERE x.src=? ORDER BY x.weight DESC""", (me,))] if me else []
        out["summary"] = lines
        return out

    def context(self, q=None, budget=1800):
        """A briefing for an AI: who the user is, then what they've said that matters for q. Plain text, budgeted."""
        self.ensure()
        lines, covered = self.summary()
        ais = sorted({a for (s,) in self.db.execute("SELECT sources FROM nodes WHERE kind='memory' AND status='active'")
                      for a in (x.get("ai") for x in json.loads(s)) if a and a != "agent"})
        head = "[mindbaton] What I know about the user from their past chats" + (f" with {and_list(ais)}" if ais else "") + \
               " (their own words; newest wins):"
        out, used, ids = [head], len(head), []

        def put(line):
            nonlocal used
            if used + len(line) + 1 > budget - 12:
                return False
            out.append(line)
            used += len(line) + 1
            return True
        for l in lines:
            if not put("- " + l):
                break
        if q:
            mems = self.recall(q, 8)["memories"]
            title = f"Relevant to “{q[:60]}”:"
        else:  # personal statements, plus notes about their own things ("the red car has black alloys")
            mine = [k for _, k in covered_things(covered)]
            mems = [self.mem(r) for r in self.db.execute(f"""SELECT {MEM_COLS} FROM nodes m WHERE kind='memory' AND status='active'
                AND (type IN ('fact','preference','goal','event') OR (type = 'note' AND EXISTS (SELECT 1 FROM edges x JOIN nodes e
                ON e.id = x.dst WHERE x.src = m.id AND x.rel = 'mentions' AND e.key IN ({','.join('?' * len(mine)) or "''"}))))
                ORDER BY importance * conf * (1 + .1 * count) DESC, updated DESC LIMIT 40""", mine)]
            title = "Other things they've said:"
        extra = []
        for m in mems:
            r = self.db.execute("SELECT rels FROM nodes WHERE id=?", (m["id"],)).fetchone()
            said = [tuple(t) for t in json.loads(r[0]) if t[1] != "related"] if r else []
            if said and all(t in covered for t in said) and not m.get("at"):
                continue  # already said in the summary
            when = datetime.fromtimestamp(m["at"] or m["updated"]).strftime("%-d %b")
            src = f" ({m['ais'][0]}, {when})" if m["ais"] else f" ({when})"
            extra.append((m["id"], "- " + m["text"] + src))
        if extra:
            put(title)
            for i, l in extra:
                if not put(l):
                    break
                ids.append(i)
        out.append("[/mindbaton]")
        return {"text": "\n".join(out), "memories": ids}

    def sources(self, raw, sess=None):
        """A memory's sources as the viewer shows them: newest first, one per conversation, AI names canonical.
        [{ai, chat, model, ts, session (node id), note}]"""
        sess = sess if sess is not None else self.session_index()
        out, seen = [], set()
        for x in sorted(json.loads(raw or "[]"), key=lambda x: -(x.get("ts") or 0)):
            k = x.get("ctx") or x.get("chat") or x.get("ai")
            if k in seen:
                continue
            seen.add(k)
            sid, title = sess.get(x.get("ctx"), (None, None))
            out.append({k2: v for k2, v in {"ai": ai_of(x.get("ai")), "chat": title or x.get("chat"), "model": x.get("model"),
                                             "ts": x.get("ts"), "session": sid, "note": x.get("note")}.items() if v})
        return out

    def session_index(self):
        """session key -> (its node id, its current title): a memory shows the chat's title as the app names it now."""
        return {k[8:]: (i, lab) for i, k, lab in self.db.execute("SELECT id, key, label FROM nodes WHERE kind='session'")}

    def subgraph(self, ids=None):
        cols = "id, kind, label, type, importance, hits, count, status, cluster, updated, sources, at, conf, cat, created, key, rank, ctx"
        if ids is None:
            nodes = self.db.execute(f"SELECT {cols} FROM nodes").fetchall()
            edges = self.db.execute("SELECT src, dst, rel, weight FROM edges").fetchall()
        else:
            ph = ",".join("?" * len(ids)) or "NULL"
            nodes = self.db.execute(f"SELECT {cols} FROM nodes WHERE id IN ({ph})", list(ids)).fetchall()
            edges = self.db.execute(f"SELECT src, dst, rel, weight FROM edges WHERE src IN ({ph}) AND dst IN ({ph})",
                                    list(ids) * 2).fetchall()
        out = []
        sess = self.session_index()
        smeta = {k: m for k, m in ((r[0], r) for r in self.db.execute(
            "SELECT key, id, site, model, turns, tokens, window, limit_text, url, started, updated, parent, cwd FROM sessions"))}
        for n in nodes:
            d = dict(zip(("id", "kind", "label", "type", "importance", "hits", "count", "status", "cluster", "updated"), n))
            if n[1] == "memory":
                srcs = self.sources(n[10], sess)
                d.update(ais=sorted({x["ai"] for x in srcs if x.get("ai")}), chats=sorted({x["chat"] for x in srcs if x.get("chat")}),
                         models=sorted({x["model"] for x in srcs if x.get("model")}), srcs=srcs, at=n[11], conf=n[12])
            elif n[1] == "session":
                m = smeta.get(n[17]) or (None,) * 13
                models = [r[0] for r in self.db.execute("SELECT model FROM turns WHERE session=? AND model IS NOT NULL GROUP BY model "
                                                          "ORDER BY min(n)", (m[1],))] if m[1] else []
                ai_name = ai_of(m[2]) if m[2] else n[3]
                d.update(created=n[14], key=n[15], ctx=n[17], ai=ai_name, sid=m[1],
                         model=live.model_name(m[3], ai_name) or (models[-1] if models else None), models=models, turns=m[4], tokens=m[5], window=m[6],
                         pct=round(100 * m[5] / m[6], 1) if m[5] and m[6] else 0, limit=m[7], url=m[8], started=m[9],
                         parent=m[11], cwd=m[12])
            else:
                d.update(cat=n[13], created=n[14], key=n[15], rank=n[16])
            out.append(d)
        return {"nodes": out, "edges": [dict(zip(("src", "dst", "rel", "weight"), e)) for e in edges]}

    def graph(self):
        self.ensure()
        g = self.subgraph()
        g["topics"] = sorted(self.topics.values(), key=lambda t: -t["size"])
        live = [n for n in g["nodes"] if n["kind"] == "memory" and n["status"] == "active"]
        g["stats"] = {"captures": self.db.execute("SELECT count(*) FROM captures").fetchone()[0], "memories": len(live),
                      "entities": sum(1 for n in g["nodes"] if n["kind"] == "entity"),
                      "chats": sum(1 for n in g["nodes"] if n["kind"] == "session"),
                      "ais": dict(Counter(a for n in live for a in n["ais"])),
                      "models": dict(Counter(m for n in live for m in n["models"]))}
        g["summary"] = self.summary()[0]
        return g

    def timeline(self, subject="me"):
        """Every fact about a subject with when it became true and when it stopped (point-in-time history)."""
        rows = self.db.execute("""SELECT f.rel, f.obj, coalesce(n.label, f.obj), f.valid_from, f.valid_to, f.memory, m.label, f.ended_by
                                  FROM facts f LEFT JOIN nodes n ON n.kind='entity' AND n.key=f.obj LEFT JOIN nodes m ON m.id=f.memory
                                  WHERE f.subj=? ORDER BY f.valid_from DESC""", (subject,)).fetchall()
        return [{"rel": r, "key": k, "label": lab, "from": vf, "to": vt, "memory": mid, "said": said, "ended_by": eb}
                for r, k, lab, vf, vt, mid, said, eb in rows]

    # ---- forgetting and rebuilding -------------------------------------------------------------------------------
    def forget(self, nid):
        r = self.db.execute("SELECT kind, key, rels FROM nodes WHERE id=?", (nid,)).fetchone()
        if not r:
            return 0
        self.db.execute("BEGIN")
        self.db.execute("INSERT OR IGNORE INTO forgotten VALUES(?,?)", r[:2])
        self._forgot = None
        self.db.execute("DELETE FROM meta WHERE k='topic_names'")  # an AI summary may quote what was forgotten: re-name
        self.names_gen = getattr(self, "names_gen", 0) + 1  # and a naming call already in flight is discarded
        self.db.execute("DELETE FROM facts WHERE memory=?", (nid,))
        if r[0] == "session":
            sk = r[1][len("session:"):]
            for (sid,) in self.db.execute("SELECT id FROM sessions WHERE key=?", (sk,)).fetchall():
                self.db.execute("DELETE FROM turns_fts WHERE rowid IN (SELECT id FROM turns WHERE session=?)", (sid,))
                self.db.execute("DELETE FROM turns WHERE session=?", (sid,))
                self.db.execute("DELETE FROM sessions WHERE id=?", (sid,))
        self.unindex(nid)
        self.db.execute("DELETE FROM fts WHERE rowid=?", (nid,))
        self.db.execute("DELETE FROM nodes WHERE id=?", (nid,))
        for a, rel, b in json.loads(r[2] or "[]"):  # relations only this memory stated go with it
            if not self.asserting((a, rel, b)) and self.ekeys.get(a) and self.ekeys.get(b):
                self.db.execute("DELETE FROM edges WHERE src=? AND dst=? AND rel=?", (self.ekeys[a], self.ekeys[b], rel))
        orphans = [x for x in self.db.execute("""SELECT id, key FROM nodes n WHERE kind='entity' AND key!='me' AND NOT EXISTS
            (SELECT 1 FROM edges WHERE dst=n.id AND rel IN ('mentions','about','context')) AND NOT EXISTS
            (SELECT 1 FROM edges WHERE src=n.id OR dst=n.id)""")]
        for o, k in orphans:  # entities nothing mentions or links any more go too (not recorded as forgotten)
            self.db.execute("DELETE FROM fts WHERE rowid=?", (o,))
            self.db.execute("DELETE FROM nodes WHERE id=?", (o,))
            self.ekeys.pop(k, None)
            self.ebucket[k[:1]].discard(k)
        if r[0] == "entity":
            self.ekeys.pop(r[1], None)
            self.ebucket[r[1][:1]].discard(r[1])
        self.db.execute("COMMIT")
        self.dirty = True
        return 1

    def rebuild(self):
        self.db.executescript("DROP TABLE IF EXISTS edges; DROP TABLE IF EXISTS nodes; DROP TABLE IF EXISTS fts; "
                              "DROP TABLE IF EXISTS facts;" + DERIVED)
        self.vec, self.post, self.ekeys, self.ebucket = {}, defaultdict(set), {}, defaultdict(set)
        rows = self.db.execute("SELECT text, site, chat, url, ts, extra FROM captures ORDER BY ts, id").fetchall()
        for text, site, chat, url, ts, extra in rows:
            x = json.loads(extra) if extra else {}
            self.ingest(text, site, chat, url, ts, x.get("entities"), x.get("relations"), store=False, recluster=False,
                        meta={k: v for k, v in x.items() if k not in ("entities", "relations")})
        live.relink_all(self, reread=True)
        self.meta("logic", LOGIC_VERSION)
        self.dirty = True
        return {"captures": len(rows), **self.graph()["stats"]}


# ---- MCP: the same memory as tools for Claude Desktop, Claude Code, Cursor, … ----------------------------------------
MCP_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
MCP_TOOLS = [
    {"name": "context", "description": "Get a briefing about the user from their long-term memory: who they are, what they "
     "use, what they're working on, their preferences, and (if you pass a topic) what they've said before about it. Call this "
     "at the start of a conversation, and whenever the user's request might depend on their personal context.",
     "inputSchema": {"type": "object", "properties": {"topic": {"type": "string", "description": "What the conversation is about (optional)."}}},
     "annotations": {"readOnlyHint": True}},
    {"name": "recall", "description": "Search the user's long-term memory (everything they've told any AI: facts, preferences, "
     "projects, past questions). Returns a direct answer when one is known, plus the most relevant memories with ids. Use it "
     "before answering questions about the user or when they refer to something from the past.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "k": {"type": "integer", "minimum": 1, "maximum": 20}},
                     "required": ["query"]}, "annotations": {"readOnlyHint": True}},
    {"name": "remember", "description": "Save a durable fact about the user to long-term memory: who they are, where they "
     "live or work, what they use, like, dislike, own, are building or learning, or a change ('I switched from X to Y'). Write "
     "one self-contained sentence in the user's own first person ('I use Neovim'). Don't save one-off requests or secrets.",
     "inputSchema": {"type": "object", "properties": {"fact": {"type": "string"}, "model": {"type": "string", "description": "The model you are (e.g. 'Claude Opus 5.5'), if you know it."}}, "required": ["fact"]}},
    {"name": "profile", "description": "Everything known about the user, as a structured profile (summary, facts, preferences, goals).",
     "inputSchema": {"type": "object", "properties": {}}, "annotations": {"readOnlyHint": True}},
    {"name": "handoff", "description": "Continue a conversation the user had with another AI (ChatGPT, Claude, Gemini, Claude Code…) "
     "that hit its limit or that they want to pick up here. Returns a continuation pack: the goal, latest messages, decisions, key code, "
     "open questions and what you should know about the user. With no arguments it uses their most recent conversation; pass `session` "
     "(an id from `sessions`, or words from its title) for another. Read it, then carry on from where it left off.",
     "inputSchema": {"type": "object", "properties": {"session": {"type": "string"}, "budget": {"type": "integer", "minimum": 200, "maximum": 12000,
                     "description": "Size of the pack in tokens (default 2500)."}}}, "annotations": {"readOnlyHint": True}},
    {"name": "sessions", "description": "List the user's recent conversations across AIs (Live mode): id, AI, title, messages, how full each "
     "one's context is, and whether it hit a limit. Use with `handoff` to continue one here.",
     "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}}}, "annotations": {"readOnlyHint": True}},
    {"name": "save_conversation", "description": "Save THIS conversation to the user's memory so they can continue it in another AI or a new "
     "chat — call it when the conversation is long, when you're near your context limit, or when the user asks to hand it off. Pass the "
     "turns so far (most important first if you must shorten), or a summary as a single turn. Returns the id to hand off.",
     "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "turns": {"type": "array", "items": {"type": "object",
                     "properties": {"role": {"type": "string", "enum": ["user", "assistant"]}, "text": {"type": "string"}}, "required": ["role", "text"]}},
                     "summary": {"type": "string"}, "model": {"type": "string", "description": "The model you are (e.g. 'Claude Opus 5.5'), if you know it."}}, "required": ["title"]}},
    {"name": "forget", "description": "Permanently delete a memory (by the id recall returned) when the user asks you to forget "
     "it or it is wrong.", "inputSchema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
     "annotations": {"destructiveHint": True}},
]
MCP_INSTRUCTIONS = ("Mindbaton is the user's personal long-term memory, fed by their chats with every AI they use. Call `context` "
                    "at the start of a conversation. Use `recall` before answering anything personal. When the user tells you a "
                    "lasting fact about themselves, save it with `remember`. If they want to continue a chat from another AI, call "
                    "`handoff`. When this conversation grows long or nears your context limit, call `save_conversation` so it can be "
                    "continued elsewhere.")
MCP_CLIENT = {}  # the most recently initialised client: for clients that don't send Mcp-Session-Id back
MCP_SESSIONS = {}  # Mcp-Session-Id -> {name, version}: each connected app is credited with its own saves


def mcp_call(g, name, a, client=None):
    client = client or MCP_CLIENT
    if name == "context":
        return g.context(a.get("topic") or None)["text"]
    if name == "recall":
        r = g.recall(str(a.get("query", "")), max(1, min(int(a.get("k", 8)), 20)))
        lines = ([f"Answer: {r['answer']['text']}"] if r["answer"] else []) + [
            f"[{m['id']}] {m['text']} ({m['type']}; {', '.join(m['ais']) or 'agent'}{' · ' + ', '.join(m['models']) if m['models'] else ''}; "
            f"{datetime.fromtimestamp(m['updated']).strftime('%-d %b %Y')})" for m in r["memories"]]
        return "\n".join(lines) or "Nothing in memory about that yet."
    if name == "remember":
        fact = str(a.get("fact") or a.get("text") or "").strip()
        if not fact:
            raise ValueError("fact is required")
        who = client.get("name")
        ids = g.ingest(fact[:2000], "agent", meta={"ai": ai_of(who) if who and who != "mcp" else None, "model": a.get("model"),
                                                    "model_src": "self" if a.get("model") else None,
                                                    "client": f"{who}/{client.get('version')}" if who else None})
        return f"Saved as memory {', '.join(map(str, ids))}." if ids else "Nothing new to save (already known, or forgotten on purpose)."
    if name == "profile":
        p = g.profile()
        return json.dumps({"summary": p["summary"], **{t: [m["text"] for m in p[t]] for t in ("fact", "preference", "goal", "event")}}, indent=1)
    if name == "forget":
        return "Forgotten." if g.forget(int(a["id"])) else "No memory with that id."
    if name == "handoff":
        return live.make_handoff(g, a.get("session"), int(a.get("budget") or 2500))["text"]
    if name == "sessions":
        rows = live.sessions(g, int(a.get("limit") or 15))
        return "\n".join(f"[{s['id']}] {s['ai']} — {s['chat'] or 'untitled'} · {s['turns']} messages · {s['pct']}% of context"
                         + (" · HIT ITS LIMIT" if s["limit"] else "") + f" · {datetime.fromtimestamp(s['updated']).strftime('%-d %b %H:%M')}"
                         for s in rows) or "No conversations recorded yet."
    if name == "save_conversation":
        turns = a.get("turns") or []
        if a.get("summary"):
            turns = turns + [{"role": "assistant", "text": "Summary so far: " + str(a["summary"])}]
        if not turns:
            raise ValueError("pass turns or a summary")
        who = client.get("name") or "mcp"
        m = live.sync(g, None, who, str(a.get("title") or "MCP conversation"), turns, model=a.get("model"),
                      key=f"mcp/{who}/{mkey(str(a.get('title') or 'conversation'))[:60]}", capture_users=True)
        return f"Saved as conversation {m['id']} ({m['turns']} messages, ~{m['tokens']} tokens). Hand it off with handoff(session=\"{m['id']}\")."
    raise KeyError(name)


CONNECTOR_DENY = {"forget"}  # nothing is deleted through an internet-facing connector: forget it in the app


def mcp_handle(g, msg, connector=False, client=None):
    """One JSON-RPC message -> response dict (None for notifications). connector: sent with a connector-scope token.
    client: {name, version} of the app on this MCP session (initialize fills it in)."""
    if not isinstance(msg, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params")
    params = params if isinstance(params, dict) else {}
    if mid is None:
        return None  # notifications (initialized, cancelled, …) need no reply
    ok = lambda result: {"jsonrpc": "2.0", "id": mid, "result": result}
    if method == "initialize":
        info = params.get("clientInfo") or {}
        who = {"name": re.sub(r"[^a-z0-9-]+", "-", str(info.get("name") or "mcp").lower())[:40], "version": str(info.get("version") or "")[:20]}
        MCP_CLIENT.clear()
        MCP_CLIENT.update(who)
        if client is not None:
            client.update(who)
        want = params.get("protocolVersion")
        return ok({"protocolVersion": want if want in MCP_VERSIONS else MCP_VERSIONS[0],
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": "mindbaton", "version": VERSION}, "instructions": MCP_INSTRUCTIONS})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": [t for t in MCP_TOOLS if not (connector and t["name"] in CONNECTOR_DENY)]})
    if method == "tools/call":
        if connector and params.get("name") in CONNECTOR_DENY:
            return ok({"content": [{"type": "text", "text": "Not available through a connector — forget it in the "
                                    "Mindbaton app instead."}], "isError": True})
        try:
            text = mcp_call(g, params.get("name"), params.get("arguments") or {}, client)
            return ok({"content": [{"type": "text", "text": text}], "isError": False})
        except KeyError:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {params.get('name')!r}"}}
        except (ValueError, TypeError) as e:
            return ok({"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True})
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}


# ---- auth: one owner (a password and browser sessions) and device tokens ------------------------------------------------
KINDS = ("extension", "mcp", "agent", "phone", "connector", "other")
SESSION_S = 30 * 86400   # a browser session lasts 30 days from its last use
PAIR_S = 600             # a pairing request waits 10 minutes for the owner
CONN_LIMITS = ((60, 60), (600, 3600))  # a connector token: at most 60 requests a minute and 600 an hour
ACCESS_LOG = os.path.join(DATA, "access.log")
FAILS = {}                       # ip -> [misses in a row, locked until]
ATTEMPTS = deque()               # every password / setup-code attempt in the last minute, all IPs
PAIR_HITS = defaultdict(deque)   # ip -> pairing requests in the last minute
CONN_HITS = defaultdict(deque)   # connector token id -> requests in the last hour
PAIRS = {}  # code -> {poll (sha256), name, kind, created, status}. In memory: after a restart a device just pairs again.
sha = lambda s: hashlib.sha256(s.encode()).hexdigest()


def owner(db):
    r = db.execute("SELECT v FROM meta WHERE k='owner'").fetchone()
    return r and r[0]


def hash_password(pw, salt=None):
    salt = salt or os.urandom(16)
    return "scrypt$" + salt.hex() + "$" + hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32).hex()


def check_password(pw, stored):
    try:
        return hmac.compare_digest(hash_password(pw, bytes.fromhex(stored.split("$")[1])), stored)
    except (AttributeError, IndexError, ValueError):
        return False


def setup_code(db):
    """The one-time code that claims a fresh install (None once it has an owner). Made on first need, kept in meta."""
    if owner(db):
        return None
    r = db.execute("SELECT v FROM meta WHERE k='setup_code'").fetchone()
    if r:
        return r[0]
    n = f"{secrets.randbelow(10 ** 8):08d}"
    db.execute("INSERT OR REPLACE INTO meta VALUES('setup_code', ?)", (n[:4] + "-" + n[4:],))
    return n[:4] + "-" + n[4:]


def set_password(db, hashed, keep=None):
    """The owner's password (hashed by the caller, outside LOCK). Every browser session but `keep` is signed out."""
    db.execute("INSERT OR REPLACE INTO meta VALUES('owner', ?)", (hashed,))
    db.execute("DELETE FROM meta WHERE k='setup_code'")
    db.execute("DELETE FROM logins WHERE hash IS NOT ?", (keep,))


def reset_password(db):
    """`--reset-password`: whoever has this machine's shell is the owner. Device tokens keep working; the next visit
    to the app is first-run again (with a new setup code)."""
    db.execute("DELETE FROM meta WHERE k IN ('owner', 'setup_code')")
    db.execute("DELETE FROM logins")
    return setup_code(db)


def new_login(db):
    s, now = secrets.token_urlsafe(32), time.time()
    db.execute("DELETE FROM logins WHERE expires < ?", (now,))
    db.execute("INSERT INTO logins VALUES(?,?,?)", (sha(s), now, now + SESSION_S))
    return s


def issue_token(db, name, kind, scope=None):
    """A device token: returned once, stored only as its sha256."""
    if kind not in KINDS:
        raise ValueError("kind must be one of " + ", ".join(KINDS))
    scope = scope or ("connector" if kind == "connector" else "full")
    if scope not in ("full", "connector"):
        raise ValueError("scope must be full or connector")
    name = re.sub(r"\s+", " ", str(name or "")).strip()[:60] or kind
    tok = "mb_" + secrets.token_urlsafe(32)
    i = db.execute("INSERT INTO tokens(name, kind, scope, hash, created) VALUES(?,?,?,?,?)",
                   (name, kind, scope, sha(tok), time.time())).lastrowid
    return {"id": i, "token": tok, "name": name, "kind": kind, "scope": scope}


def recent(q, now, window=60):
    while q and q[0] < now - window:
        q.popleft()
    return len(q)


def wait_for(ip):
    """Seconds this IP must wait before another password or setup-code attempt; 0 = go ahead (the attempt counts)."""
    now = time.time()
    if recent(ATTEMPTS, now) >= 30:
        return 60
    f = FAILS.get(ip)
    if f and f[1] > now:
        return math.ceil(f[1] - now)
    ATTEMPTS.append(now)
    return 0


def failed(ip):
    """5 misses in a row lock the IP out for 60 s, doubling with each further miss up to 15 minutes."""
    if len(FAILS) > 10000:  # ponytail: forget IPs not locked right now; a real store if this ever faces a botnet
        for k in [k for k, f in FAILS.items() if f[1] < time.time()]:
            del FAILS[k]
    f = FAILS.setdefault(ip, [0, 0])
    f[0] += 1
    if f[0] >= 5:
        f[1] = time.time() + min(60 * 2 ** min(f[0] - 5, 10), 900)


def pair_code():
    c = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(8))  # no I or O: read aloud, typed on a phone
    return c[:4] + "-" + c[4:]


def norm_code(c):
    c = re.sub(r"[^A-Z]", "", str(c or "").upper())
    return c[:4] + "-" + c[4:] if len(c) == 8 else None


def access_log(entry):
    """One line per MCP message sent with a connector token: when, from where, which token and client, which tool."""
    try:
        if os.path.exists(ACCESS_LOG) and os.path.getsize(ACCESS_LOG) > 2_000_000:
            os.replace(ACCESS_LOG, ACCESS_LOG + ".1")
        fd = os.open(ACCESS_LOG, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


_ZIP = {}


def extension_zip():
    """extension/ as a zip, built on request and rebuilt whenever a file in it changes (no stale committed zip)."""
    root = os.path.join(HERE, "extension")
    files = sorted(p for p in glob.glob(os.path.join(root, "**"), recursive=True) if os.path.isfile(p))  # dotfiles skipped
    stamp = (tuple(files), max((os.path.getmtime(p) for p in files), default=0))
    if _ZIP.get("stamp") != stamp:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in files:
                z.write(p, os.path.relpath(p, root))
        _ZIP.update(stamp=stamp, body=buf.getvalue())
    return _ZIP["body"]


def setup_status(g, base):
    """What's connected, for the Setup page: each piece with a green tick once it has been seen working. Device tokens
    report their last use per kind, so a tick turns green by itself as soon as a paired device talks to the server."""
    q = lambda sql, *a: g.db.execute(sql, a).fetchone()
    week = time.time() - 7 * 86400
    dev = {k: {"tokens": 0, "last": None, "recent": False} for k in KINDS}
    for kind, n, last in g.db.execute("SELECT kind, count(*), max(last_used) FROM tokens WHERE revoked IS NULL GROUP BY kind"):
        if kind in dev:
            dev[kind] = {"tokens": n, "last": last, "recent": bool(last and last > week)}
    web = q("SELECT max(ts), count(*) FROM captures WHERE site LIKE '%.%' AND ts > ?", week)
    web_ai = [ai_of(s) for (s,) in g.db.execute("SELECT DISTINCT site FROM captures WHERE site LIKE '%.%' AND ts > ?", (week,))]
    live_web = q("SELECT max(updated) FROM sessions WHERE site LIKE '%.%'")[0]
    cc = q("SELECT max(updated), count(*) FROM sessions WHERE site='claude-code'")
    apps = {}
    for c in list(MCP_SESSIONS.values()):
        if c.get("name"):
            apps[ai_of(c["name"])] = max(apps.get(ai_of(c["name"]), 0), c.get("seen", 0))
    for s, t in g.db.execute("SELECT site, max(updated) FROM sessions WHERE key LIKE 'mcp/%' OR site LIKE 'antigravity%' GROUP BY site"):
        apps[ai_of(s)] = max(apps.get(ai_of(s), 0), t or 0)
    phone = q("SELECT max(ts) FROM captures WHERE site='phone'")[0] or q("SELECT max(updated) FROM sessions WHERE key LIKE '%/share-%'")[0]
    last = lambda *xs: max(x or 0 for x in xs) or None
    return {"server": {"ok": True, "base": base, "mcp": base + "/mcp", "public_url": PUBLIC_URL, "https": base.startswith("https://"),
                       "version": VERSION},
            "devices": dev,
            "extension": {"ok": bool(web[0] or live_web or dev["extension"]["recent"]), "last": last(web[0], live_web, dev["extension"]["last"]),
                          "ais": sorted(set(web_ai)), "live": bool(live_web)},
            "agents": {"ok": bool(cc[0] or apps or dev["mcp"]["recent"] or dev["agent"]["recent"]),
                       "claude_code": {"last": cc[0], "chats": cc[1]}, "apps": apps},
            "phone": {"ok": bool(phone or dev["phone"]["recent"]), "last": last(phone, dev["phone"]["last"]), "url": base},
            "connector": {"ok": dev["connector"]["recent"], "configured": dev["connector"]["tokens"] > 0, "last": dev["connector"]["last"]},
            "ai": ai.status()}


def save_ai_key(provider, key):
    """A free AI key pasted into the Setup page: tried once, then saved to <data>/ai_keys (600). Never read back."""
    var = {"gemini": "GEMINI_KEY", "groq": "GROQ_KEY"}.get(str(provider).lower())
    key = str(key or "").strip()
    if not var or not re.fullmatch(r"[A-Za-z0-9._\-]{20,200}", key):
        raise ValueError("that doesn't look like a Gemini or Groq key")
    import urllib.request, urllib.error
    url, model = ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-flash-lite-latest") if var == "GEMINI_KEY" \
        else ("https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-20b")
    req = urllib.request.Request(url, json.dumps({"model": model, "messages": [{"role": "user", "content": "ok"}], "max_tokens": 5}).encode(),
                                 {"Content-Type": "application/json", "Authorization": "Bearer " + key, "User-Agent": "mindbaton/1.0"})
    try:
        urllib.request.urlopen(req, timeout=20).read()
    except urllib.error.HTTPError as e:
        if e.code in (400, 401, 403):
            raise ValueError("the provider refused that key — copy it again from their site")
    except OSError:
        raise ValueError("couldn't reach the provider to test the key — check the internet connection")
    path = ai.KEYS
    lines = [l for l in (open(path).read().splitlines() if os.path.exists(path) else []) if not l.startswith(var + "=")]
    fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines + [f"{var}={key}"]) + "\n")
    os.replace(path + ".tmp", path)
    return {"saved": var.split("_")[0].title(), "ai": ai.status()}


FILES = {"/", "/index.html", "/manifest.webmanifest", "/sw.js", "/share.html", "/mcp_stdio.py"}  # public, served as files
ASSETS = os.path.join(HERE, "assets") + os.sep
OWNER_ONLY = {"/api/auth/logout", "/api/auth/logout-all", "/api/auth/password", "/api/tokens", "/api/pair/pending",
              "/api/pair/approve", "/api/pair/deny"}  # and /api/tokens/<id>: the signed-in owner, never a device token
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
SECURITY = (("Content-Security-Policy", CSP), ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer"),
            ("X-Frame-Options", "DENY"))
FORWARDED = ("X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto", "Forwarded", "X-Real-IP", "CF-Connecting-IP",
             "Tailscale-Funnel-Request")
SECRET_IN_URL = re.compile(r"(/t/|[?&](?:poll|code)=)[^/\s&]+")


def need_text(b):
    if not isinstance(b.get("text"), str) or not b["text"].strip():
        raise ValueError("need text:str")


class Handler(SimpleHTTPRequestHandler):
    timeout = 20  # a browser's pre-connected socket that never sends a request is dropped, not waited on forever
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".webmanifest": "application/manifest+json"}

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    # ---- plumbing ------------------------------------------------------------------------------------------------
    def end_headers(self):  # every response: security headers, and a (re)issued session cookie if there is one
        for k, v in SECURITY + tuple(getattr(self, "extra", ())):
            self.send_header(k, v)
        self.extra = []
        super().end_headers()

    def log_message(self, fmt, *args):  # tokens in paths and pairing secrets never reach the log
        super().log_message(fmt, *(SECRET_IN_URL.sub(r"\1…", a) if isinstance(a, str) else a for a in args))

    def list_directory(self, path):
        self.send_error(404)

    def static(self, p):
        return p in FILES or p.startswith("/assets/") and os.path.realpath(self.translate_path(p)).startswith(ASSETS)

    def reply(self, code, obj, ctype="application/json", headers=None):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def too_many(self, wait):
        self.reply(429, {"error": f"too many attempts — try again in {int(wait)} s", "retry_after": int(wait)},
                   headers={"Retry-After": str(int(wait))})

    def body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if not 0 <= n <= 1_000_000:
            raise ValueError("body too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def api(self, fn, lock=True):
        try:
            if lock:
                with LOCK:
                    out = fn()
            else:
                out = fn()
            self.reply(200, out)
        except (ValueError, TypeError, KeyError) as e:
            self.reply(400, {"error": str(e)})

    # ---- who is asking -------------------------------------------------------------------------------------------
    def foreign(self):
        """No cross-site access: another website must not read or change the memory from the owner's browser.
        The app is same-origin; the extension and MCP clients send no Origin (or the extension's own)."""
        o = self.headers.get("Origin")
        if not o or o.startswith(("chrome-extension://", "moz-extension://", "safari-web-extension://")):
            return False
        ours = {self.headers.get("Host"), self.headers.get("X-Forwarded-Host"), urlparse(PUBLIC_URL or "").netloc} - {None, ""}
        return urlparse(o).netloc not in ours

    def https(self):
        return self.headers.get("X-Forwarded-Proto", "").lower() == "https" or bool(
            PUBLIC_URL and PUBLIC_URL.startswith("https://") and urlparse(PUBLIC_URL).netloc == self.headers.get("Host"))

    def base(self):
        """The address clients should use: MINDBATON_PUBLIC_URL, else the one this request was sent to."""
        if PUBLIC_URL:
            return PUBLIC_URL
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or ""
        host = host if re.fullmatch(r"[A-Za-z0-9.:\[\]-]{1,255}", host) else f"127.0.0.1:{PORT}"
        return ("https" if self.https() else "http") + "://" + host

    def local(self):
        """Typed on this machine: a loopback peer asking for a loopback name, with no proxy in between (a tunnel or
        reverse proxy on this box connects from loopback too, but says so in its headers)."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        try:
            peer = ipaddress.ip_address(self.client_address[0]).is_loopback
        except ValueError:
            peer = False
        return peer and host in ("localhost", "127.0.0.1", "::1") and not any(self.headers.get(h) for h in FORWARDED)

    def ip(self):
        """The client, for throttling: behind a proxy on this box, the address the proxy saw."""
        xff = self.headers.get("X-Forwarded-For")
        return xff.split(",")[-1].strip()[:64] if xff and self.client_address[0] in ("127.0.0.1", "::1") else self.client_address[0]

    def bearer(self):
        a = self.headers.get("Authorization") or ""
        return (a[7:].strip() or None) if a[:7].lower() == "bearer " else None

    def cookie(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "mb_session" and v:
                return v
        return None

    def set_cookie(self, value, age=SESSION_S):
        self.extra.append(("Set-Cookie", f"mb_session={value}; Path=/; Max-Age={age}; HttpOnly; SameSite=Lax"
                                         + ("; Secure" if self.https() else "")))

    def who(self, tok):
        """{"via": "token", id, name, kind, scope} | {"via": "session", "login": hash} | None. A token, when one is
        sent, is the only credential looked at."""
        now = time.time()
        with LOCK:
            if tok:
                r = G.db.execute("SELECT id, name, kind, scope, last_used FROM tokens WHERE hash=? AND revoked IS NULL", (sha(tok),)).fetchone()
                if not r:
                    return None
                if (r[4] or 0) < now - 60:  # the Setup page's ticks; written at most once a minute
                    G.db.execute("UPDATE tokens SET last_used=? WHERE id=?", (now, r[0]))
                return {"via": "token", "id": r[0], "name": r[1], "kind": r[2], "scope": r[3]}
            s = self.cookie()
            r = s and G.db.execute("SELECT expires FROM logins WHERE hash=?", (sha(s),)).fetchone()
            if not r or r[0] < now:
                return None
            if r[0] < now + SESSION_S - 3600:  # sliding: a session in use keeps going (refreshed at most hourly)
                G.db.execute("UPDATE logins SET expires=? WHERE hash=?", (now + SESSION_S, sha(s)))
                self.set_cookie(s)
            return {"via": "session", "login": sha(s)}

    # ---- routing -------------------------------------------------------------------------------------------------
    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_DELETE(self):
        self.route("DELETE")

    def do_HEAD(self):
        if self.static(urlparse(self.path).path):
            return super().do_HEAD()
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def route(self, method):
        self.extra = []
        u = urlparse(self.path)
        p, qs = u.path, {k: v[0] for k, v in parse_qs(u.query).items()}
        ptok = None
        if p.startswith("/t/"):  # connectors that can't send headers carry their token in the path: /mcp and /health only
            m = re.fullmatch(r"/t/([\w-]{1,200})(/mcp|/health)", p)
            if not m:
                return self.reply(404, {"error": "not found"})
            ptok, p = m[1], m[2]
        elif method == "GET" and self.static(p):
            return super().do_GET()
        elif method == "GET" and p == "/mindbaton-extension.zip":
            return self.reply(200, extension_zip(), "application/zip",
                              {"Content-Disposition": 'attachment; filename="mindbaton-extension.zip"'})
        b = {}
        if method == "POST":  # read the body before any lock, so a slow sender holds up nobody
            try:
                b = self.body()
                if p != "/mcp" and not isinstance(b, dict):
                    raise ValueError("send a JSON object")
            except ValueError as e:
                return self.reply(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
                                  if p == "/mcp" else {"error": str(e)})
        tok = ptok or self.bearer()
        if not tok and self.foreign():  # a cookie rides along with cross-site requests; a token never does
            return self.reply(403, {"error": "cross-origin requests are not allowed"})
        who = self.who(tok)
        if ptok and not who:
            return self.reply(401, {"error": "login required"})
        if self.open_route(method, p, qs, b, who) is not False:
            return
        if not who:
            return self.reply(401, {"error": "login required"})
        if who.get("scope") == "connector":  # Claude.ai / ChatGPT connectors: the MCP tools (no forget), rate-limited
            if p != "/mcp":
                return self.reply(403, {"error": "a connector token only reaches /mcp"})
            now = time.time()
            with LOCK:
                q = CONN_HITS[who["id"]]
                recent(q, now, 3600)
                over = any(sum(1 for t in q if t > now - window) >= n for n, window in CONN_LIMITS)
                if not over:
                    q.append(now)
            if over:
                return self.too_many(60)
        if p in OWNER_ONLY or p.startswith("/api/tokens/"):
            if who["via"] != "session":
                return self.reply(403, {"error": "only the owner, signed in to the app, can do this"})
            return self.owner_route(method, p, b, who)
        if method == "GET":
            return self.get(p, qs)
        if method == "POST":
            return self.mcp(b, who) if p == "/mcp" else self.post(p, b)
        m = re.fullmatch(r"/node/(\d+)", p)
        if method == "DELETE" and m:
            return self.api(lambda: {"deleted": G.forget(int(m[1]))})
        self.reply(404, {"error": "not found"})

    def open_route(self, method, p, qs, b, who):
        """Routes anyone may call: health, sign-in state, first-run setup, login, pairing. False = not one of them."""
        if (method, p) == ("GET", "/health"):  # liveness for anyone; counts for the signed-in
            with LOCK:
                out = {"ok": True, "name": "mindbaton", "version": VERSION, "setup_needed": not owner(G.db), "authed": bool(who)}
                if who:
                    n, last = G.db.execute("SELECT count(*), max(ts) FROM captures").fetchone()
                    src = G.db.execute("SELECT site FROM captures ORDER BY ts DESC LIMIT 1").fetchone()
                    out.update(captures=n, last=last, last_ai=ai_of(src[0]) if src else None)
            return self.reply(200, out)
        if (method, p) == ("GET", "/api/auth/state"):
            with LOCK:
                need = not owner(G.db)
            return self.reply(200, {"setup_needed": need, "authed": bool(who), "code_required": need and not self.local()})
        if (method, p) == ("POST", "/api/auth/setup"):
            ip = self.ip()
            with LOCK:
                done = bool(owner(G.db))
                code, wait = (None, 0) if done else (setup_code(G.db), wait_for(ip))
            if done:
                return self.reply(409, {"error": "already set up — sign in instead"})
            if wait:
                return self.too_many(wait)
            if not self.local() and not hmac.compare_digest(re.sub(r"[^0-9]", "", str(b.get("code") or "")), code.replace("-", "")):
                with LOCK:
                    failed(ip)
                return self.reply(403, {"error": "wrong or missing setup code — the server prints it when it starts"})
            pw = b.get("password")
            if not isinstance(pw, str) or not 8 <= len(pw) <= 1024:
                return self.reply(400, {"error": "the password needs at least 8 characters"})
            h = hash_password(pw)  # ~50 ms of scrypt, outside the lock
            with LOCK:
                s = None if owner(G.db) else (set_password(G.db, h), FAILS.pop(ip, None), new_login(G.db))[2]
            if not s:
                return self.reply(409, {"error": "already set up — sign in instead"})
            self.set_cookie(s)
            return self.reply(200, {"ok": True})
        if (method, p) == ("POST", "/api/auth/login"):
            ip = self.ip()
            with LOCK:
                stored = owner(G.db)
                wait = wait_for(ip) if stored else 0
            if not stored:
                return self.reply(409, {"error": "not set up yet", "setup_needed": True})
            if wait:
                return self.too_many(wait)
            pw = b.get("password")
            ok = isinstance(pw, str) and len(pw) <= 1024 and check_password(pw, stored)
            with LOCK:
                if not ok:
                    failed(ip)
                else:
                    FAILS.pop(ip, None)
                    s = new_login(G.db)
            if not ok:
                return self.reply(401, {"error": "wrong password"})
            self.set_cookie(s)
            return self.reply(200, {"ok": True})
        if (method, p) == ("POST", "/api/pair/start"):
            name, kind = b.get("name"), b.get("kind")
            if kind not in KINDS or not isinstance(name, str) or not name.strip():
                return self.reply(400, {"error": "need name and kind (" + ", ".join(KINDS) + ")"})
            ip, now = self.ip(), time.time()
            with LOCK:
                for c in [c for c, x in PAIRS.items() if now - x["created"] > PAIR_S]:
                    del PAIRS[c]
                if len(PAIR_HITS) > 10000:  # ponytail: forget idle IPs wholesale; fine at home-server scale
                    PAIR_HITS.clear()
                busy = recent(PAIR_HITS[ip], now) >= 10 or len(PAIRS) >= 200
                if not busy:
                    PAIR_HITS[ip].append(now)
                    code, poll = pair_code(), secrets.token_urlsafe(24)
                    while code in PAIRS:
                        code = pair_code()
                    PAIRS[code] = {"poll": sha(poll), "name": re.sub(r"\s+", " ", name).strip()[:60], "kind": kind,
                                   "created": now, "status": "pending"}
            if busy:
                return self.too_many(60)
            return self.reply(200, {"code": code, "poll": poll, "expires_in": PAIR_S, "approve_url": f"{self.base()}/#pair/{code}"})
        if (method, p) == ("GET", "/api/pair/poll"):
            h, now = sha(qs.get("poll") or ""), time.time()
            with LOCK:
                code = next((c for c, x in PAIRS.items() if hmac.compare_digest(x["poll"], h)), None)
                x = PAIRS.get(code)
                if not x or now - x["created"] > PAIR_S:
                    PAIRS.pop(code, None)
                    out = {"status": "expired"}
                elif x["status"] == "pending":
                    out = {"status": "pending", "expires_in": int(x["created"] + PAIR_S - now)}
                else:  # answered: told once, then forgotten (so the token is handed out exactly once)
                    del PAIRS[code]
                    out = {"status": x["status"]}
                    if x["status"] == "approved":
                        t = issue_token(G.db, x["name"], x["kind"])
                        out.update(token=t["token"], id=t["id"], name=t["name"], kind=t["kind"], scope=t["scope"])
            return self.reply(200, out)
        return False

    def owner_route(self, method, p, b, who):
        if (method, p) in (("POST", "/api/auth/logout"), ("POST", "/api/auth/logout-all")):
            with LOCK:
                G.db.execute("DELETE FROM logins" + ("" if p.endswith("-all") else " WHERE hash=?"), () if p.endswith("-all") else (who["login"],))
            self.set_cookie("", 0)
            return self.reply(200, {"ok": True})
        if (method, p) == ("POST", "/api/auth/password"):
            new = b.get("new")
            if not isinstance(new, str) or not 8 <= len(new) <= 1024:
                return self.reply(400, {"error": "the new password needs at least 8 characters"})
            ip = self.ip()
            with LOCK:
                wait, stored = wait_for(ip), owner(G.db)
            if wait:
                return self.too_many(wait)
            if not (isinstance(b.get("current"), str) and check_password(b["current"], stored)):
                with LOCK:
                    failed(ip)
                return self.reply(403, {"error": "the current password is wrong"})
            h = hash_password(new)
            with LOCK:
                FAILS.pop(ip, None)
                set_password(G.db, h, keep=who["login"])
            return self.reply(200, {"ok": True})
        if (method, p) == ("GET", "/api/tokens"):
            with LOCK:
                rows = G.db.execute("SELECT id, name, kind, scope, created, last_used FROM tokens WHERE revoked IS NULL ORDER BY id").fetchall()
            return self.reply(200, [dict(zip(("id", "name", "kind", "scope", "created", "last_used"), r)) for r in rows])
        if (method, p) == ("POST", "/api/tokens"):
            return self.api(lambda: issue_token(G.db, b.get("name"), b.get("kind"), b.get("scope")))
        m = re.fullmatch(r"/api/tokens/(\d+)", p)
        if method == "DELETE" and m:
            with LOCK:
                n = G.db.execute("UPDATE tokens SET revoked=? WHERE id=? AND revoked IS NULL", (time.time(), int(m[1]))).rowcount
            return self.reply(200, {"revoked": n}) if n else self.reply(404, {"error": "no such token"})
        if (method, p) == ("GET", "/api/pair/pending"):
            now = time.time()
            with LOCK:
                out = [{"code": c, "name": x["name"], "kind": x["kind"], "created": x["created"], "expires_in": int(x["created"] + PAIR_S - now)}
                       for c, x in PAIRS.items() if x["status"] == "pending" and now - x["created"] < PAIR_S]
            return self.reply(200, out)
        if method == "POST" and p in ("/api/pair/approve", "/api/pair/deny"):
            with LOCK:
                x = PAIRS.get(norm_code(b.get("code")))
                ok = bool(x) and x["status"] == "pending" and time.time() - x["created"] < PAIR_S
                if ok:
                    x["status"] = "approved" if p.endswith("approve") else "denied"
            if not ok:
                return self.reply(404, {"error": "no such pairing request — it may have expired"})
            return self.reply(200, {"ok": True, "status": x["status"], "name": x["name"], "kind": x["kind"]})
        self.reply(404, {"error": "not found"})

    def get(self, p, qs):
        num = lambda k, d: int(qs.get(k, d)) if str(qs.get(k, d)).lstrip("-").isdigit() else d
        if p == "/export":
            try:
                with LOCK:
                    body, ctype, name = live.export(G, qs.get("format", "json"))
            except ValueError as e:
                return self.reply(400, {"error": str(e)})
            return self.reply(200, body, ctype, {"Content-Disposition": f'attachment; filename="{name}"'})
        if p == "/handoff" and qs.get("ai") != "0":
            ai.prepare(G, LOCK, qs.get("session"))  # the AI summary is made outside the lock
        if p == "/ask":  # the rules find what matters (under the lock); the AI words the answer (outside it)
            q = qs.get("q", "").strip()[:300]
            if not q:
                return self.reply(400, {"error": "need q"})
            with LOCK:
                r = G.recall(q, 10)
                notes = [{"id": m["id"], "text": m["text"], "where": " · ".join(x for x in [(m.get("srcs") or [{}])[0].get("ai"),
                          (m.get("srcs") or [{}])[0].get("chat"), datetime.fromtimestamp(m["updated"]).strftime("%-d %b %Y")] if x)}
                         for m in r["memories"]]
                notes += [{"id": None, "text": f"{c['role'] == 'assistant' and (c.get('model') or c['ai']) or 'You'}: {c['snippet']}",
                           "where": f"{c['ai']} chat “{c.get('chat') or ''}”"} for c in r.get("conversations", [])[:3]]
            got = ai.ask(q, notes) if ai.enabled() else None
            return self.reply(200, {"answer": got, "rules": r.get("answer"), "enabled": ai.enabled()})
        if p == "/session/summary":  # a chat's AI summary if it's ready; otherwise start making it
            with LOCK:
                sid = live.find(G, qs.get("id"))
                m = live.transcript(G, sid) if sid else None
            if not m:
                return self.reply(404, {"error": "no such chat"})
            turns = [{"role": t["role"], "text": t["text"]} for t in m["messages"]]
            got = ai.cached(sid, turns)
            if not got:
                if ai.enabled() and len(turns) >= 2:
                    ai.warm(G, LOCK, sid)
                return self.reply(200, {"pending": ai.enabled() and len(turns) >= 2, "enabled": ai.enabled()})
            sec = ai.sections(got["text"])
            return self.reply(200, {"summary": sec.get("Summary"), "next": sec.get("Next step"), "by": got["by"], "sections": sec})
        routes = {
            "/ai": ai.status,
            "/status": lambda: setup_status(G, self.base()),
            "/sessions": lambda: live.sessions(G, num("limit", 40)),
            "/session": lambda: live.transcript(G, live.find(G, qs.get("id"))) or {},
            "/handoff": lambda: live.make_handoff(G, qs.get("session"), max(200, min(num("budget", 1500), 12000)), qs.get("to")),
            "/handoff/pending": lambda: live.take_pending(G, qs.get("host", "")),
            "/timeline": lambda: G.timeline(qs.get("subject", "me")),
            "/neighbors": lambda: (G.ensure(), live.neighbors(G, num("id", 0), num("depth", 1)))[1],
            "/path": lambda: live.path(G, num("from", 0), num("to", 0)),
            "/recall": lambda: G.recall(qs.get("q", ""), max(1, min(num("k", 8), 50)), qs.get("all") == "1"),
            "/context": lambda: G.context(qs.get("q") or None, max(300, min(num("budget", 1800), 8000))),
            "/graph": G.graph, "/profile": G.profile,
        }
        if p in routes:
            return self.api(routes[p])
        if p == "/mcp":
            return self.reply(405, {"error": "use POST (streamable HTTP, JSON responses)"})
        if p == "/tools.json":  # the MCP tools, in the shape the Claude/OpenAI tool APIs take
            return self.reply(200, [{"name": t["name"], "description": t["description"], "input_schema": t["inputSchema"]}
                                    for t in MCP_TOOLS])
        if p == "/share":  # Android's Share menu opens the installed app here
            self.path = "/share.html" + ("?" + urlparse(self.path).query if urlparse(self.path).query else "")
            return super().do_GET()
        self.reply(404, {"error": "not found"})

    def post(self, p, b):
        s = lambda k, n: str(b.get(k) or "")[:n] or None

        def capture():
            need_text(b)
            ts = b.get("ts")  # queued offline: keep when it was really said
            ts = float(ts) if isinstance(ts, (int, float)) and 1.5e9 < ts <= time.time() + 60 else None
            return {"ids": G.ingest(b["text"][:20000], s("site", 100), s("chat", 300), s("url", 500), ts)}

        def remember():
            need_text(b)
            ents, rels = b.get("entities") or [], b.get("relations") or []
            if not (isinstance(ents, list) and all(isinstance(e, str) for e in ents) and isinstance(rels, list)
                    and all(isinstance(r, list) and len(r) == 3 and all(isinstance(x, str) for x in r) for r in rels)):
                raise ValueError("need entities:[str] and relations:[[a, rel, b], ...]")
            return {"ids": G.ingest(b["text"][:2000], "agent", entities=ents, relations=rels)}

        def session():
            turns = b.get("turns")
            if not isinstance(turns, list) or not all(isinstance(t, dict) for t in turns):
                raise ValueError("need turns: [{role, text}, ...]")
            m = live.sync(G, s("url", 500), s("site", 100), s("chat", 300) or s("title", 300), turns, s("limit", 400), s("model", 80),
                          cwd=s("cwd", 300), conv_id=s("id", 120)) or {}
            if m and (m["limit"] or (m["pct"] or 0) >= 60):
                ai.warm(G, LOCK, m["id"])  # a hand-off is coming: have its summary ready
            return m

        routes = {"/capture": capture, "/remember": remember, "/rebuild": G.rebuild, "/session": session}
        if p == "/settings/ai-key":  # tests the key with the provider: a network call, so never under the lock
            return self.api(lambda: save_ai_key(b.get("provider"), b.get("key")), lock=False)
        if p not in routes:
            return self.reply(404, {"error": "not found"})
        self.api(routes[p])

    def mcp(self, msg, who):
        connector = who.get("scope") == "connector"
        batch = msg if isinstance(msg, list) else [msg]
        for m in batch:
            prm = m.get("params") if isinstance(m, dict) else None
            prm = prm if isinstance(prm, dict) else {}
            if m and isinstance(m, dict) and m.get("method") == "tools/call" and prm.get("name") == "handoff":
                ai.prepare(G, LOCK, (prm.get("arguments") or {}).get("session"))
            if connector and isinstance(m, dict):  # every connector request, without the token
                access_log({"ts": round(time.time()), "from": self.ip(), "token": who["name"],
                            "client": (prm.get("clientInfo") or {}).get("name") or (MCP_SESSIONS.get(self.headers.get("Mcp-Session-Id") or "") or {}).get("name"),
                            "method": m["method"], "tool": prm.get("name"), "args": json.dumps(prm.get("arguments") or {})[:200] or None})
        sid = self.headers.get("Mcp-Session-Id")
        if any(isinstance(m, dict) and m.get("method") == "initialize" for m in batch):
            sid = uuid.uuid4().hex
            MCP_SESSIONS[sid] = {}
            while len(MCP_SESSIONS) > 500:  # ponytail: oldest sessions forgotten first; clients re-initialise
                MCP_SESSIONS.pop(next(iter(MCP_SESSIONS)))
        client = MCP_SESSIONS.get(sid) if sid else None
        if client is not None:
            client["seen"] = time.time()  # the Setup page shows which apps are connected
        if sid and client is None and sid not in MCP_SESSIONS:
            client = {}  # a session from before a restart: credit nobody rather than whoever connected last
        with LOCK:
            out = [r for r in (mcp_handle(G, m, connector, client if client is not None else dict(MCP_CLIENT)) for m in batch) if r]
        extra = {"Mcp-Session-Id": sid} if sid and sid in MCP_SESSIONS else {}
        if not out:
            self.send_response(202)
            for k, v in extra.items():
                self.send_header(k, v)
            self.send_header("Content-Length", "0")
            return self.end_headers()
        self.reply(200, out if isinstance(msg, list) else out[0], headers=extra)


def selfcheck():
    g = Graph(":memory:")
    day = 86400
    t0 = time.time() - 30 * day
    g.ingest("My name is Maya and I live in Porto", "chatgpt.com", "Moving plans - ChatGPT", ts=t0)
    g.ingest("I love self-hosting with Docker on Proxmox", "claude.ai", ts=t0 + day)
    g.ingest("hey can you help me fix my docker compose file, jellyfin keeps crashing on my server", "claude.ai",
             "Jellyfin crash", "https://claude.ai/chat/1", ts=t0 + 2 * day)
    g.ingest("how do I give jellyfin hardware transcoding in docker?", "chatgpt.com", "Jellyfin crash", ts=t0 + 3 * day)
    g.ingest("what's a good pasta recipe with tomatoes", "gemini.google.com", ts=t0 + 4 * day)
    g.ingest("I live in Lisbon now", "gemini.google.com", ts=t0 + 5 * day)
    dup = g.ingest("i love self hosting with docker on proxmox!!", "chatgpt.com", ts=t0 + 6 * day)
    prof = g.profile()
    texts = [m["text"] for m in prof["fact"] + prof["event"]]
    assert "I live in Lisbon now" in texts and "I live in Porto" not in texts, texts          # superseded
    rels = {(r["rel"], r["label"]) for r in prof["relations"]}
    assert ("lives in", "Lisbon") in rels and ("lives in", "Porto") not in rels, rels
    love = [m for m in prof["preference"] if "Proxmox" in m["text"]]
    assert len(love) == 1 and love[0]["count"] == 2 and set(love[0]["ais"]) == {"Claude", "ChatGPT"}, love
    assert dup == [love[0]["id"]]                                                                 # reinforced, not added
    r = g.recall("where do I live?")
    assert r["answer"]["text"] == "You live in Lisbon." and r["memories"][0]["text"] == "I live in Lisbon now", r
    jf = [m for m in g.recall("jellyfin problems")["memories"] if "jellyfin" in m["text"].lower()]
    assert len(jf) == 2 and len({m["topic"] for m in jf}) == 1 and jf[0]["topic"], jf               # sorted together
    assert "transcoding" in g.recall("container transcoding")["memories"][0]["text"]
    assert g.recall("jellyfn")["memories"], "typo tolerance"
    pasta = g.recall("pasta")["memories"][0]
    assert pasta["topic"] != jf[0]["topic"]
    g.recall('AND OR "( NEAR*')                                                                     # no FTS crash
    before = g.graph()["stats"]
    assert g.forget(pasta["id"]) == 1 and not g.recall("pasta")["memories"]
    assert g.rebuild()["memories"] == before["memories"] - 1                                        # stays forgotten
    assert g.recall("where do I live")["memories"][0]["text"] == "I live in Lisbon now"
    assert third_to_first("The user spells it hearthlnk and watches anime") == "I spell it hearthlnk and watches anime"
    assert third_to_first("PulseAudio runs as a user service") == "PulseAudio runs as a user service"
    assert g.ingest("The user prefers tabs over spaces", "agent")
    assert ("likes", "tabs") in {(r["rel"], r["label"]) for r in g.profile()["relations"]}
    c = g.context("docker")["text"]
    assert c.startswith("[mindbaton]") and "Maya" in c and "Lisbon" in c and c.endswith("[/mindbaton]"), c
    init = mcp_handle(g, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
    assert init["result"]["protocolVersion"] == "2025-06-18"
    assert mcp_handle(g, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert {t["name"] for t in mcp_handle(g, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]} >= {"recall", "remember"}
    assert "forget" not in {t["name"] for t in mcp_handle(g, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, connector=True)["result"]["tools"]}
    assert all(live.model_name(live.model_name(x)) == live.model_name(x) for x in ("claude-opus-5-5", "Claude Opus 4.6 (Thinking)", "gpt-5-6-thinking"))
    g.save_topic_names({"x": {"name": "Test", "summary": "quotes a memory"}})
    g.forget(g.db.execute("SELECT id FROM nodes WHERE kind='memory' AND status='active' ORDER BY id DESC LIMIT 1").fetchone()[0])
    assert not g.meta("topic_names"), "forgetting clears AI topic names that might quote it"
    out = mcp_handle(g, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "recall", "arguments": {"query": "where do I live"}}})
    assert "Lisbon" in out["result"]["content"][0]["text"], out
    assert mcp_handle(g, {"jsonrpc": "2.0", "id": 4, "method": "nope"})["error"]["code"] == -32601
    n0 = len(g.graph()["nodes"])
    g.ingest("[mindbaton handoff] I'm continuing...\n## About me\n- I live in Paris\n[/mindbaton handoff]", "chatgpt.com")
    assert len(g.graph()["nodes"]) == n0, "a pasted hand-off is not the user speaking"
    # live mode: a synced chat becomes a session, learns what it never saw, and hands off
    m = live.sync(g, "https://claude.ai/chat/abc", "claude.ai", "Transcoding help - Claude", [
        {"role": "user", "text": "I run Jellyfin on my server and want hardware transcoding"},
        {"role": "assistant", "text": "Use Intel Quick Sync. Pass /dev/dri into the Jellyfin container."},
        {"role": "user", "text": "ok it works now, what about 4k tone mapping?"}], limit="This conversation reached its maximum length")
    assert m["turns"] == 3 and m["ai"] == "Claude" and m["limit"] and m["pct"] == 0.0, m
    assert any("Jellyfin" in c["chat"] + c["snippet"] for c in live.search(g, "quick sync")), "conversations are searchable"
    h = live.make_handoff(g, None, 800, to="chatgpt")
    assert h["text"].startswith("[mindbaton handoff]") and "Quick Sync" in h["text"] and h["open"] == "https://chatgpt.com/", h
    assert live.take_pending(g, "chatgpt.com")["text"] == h["text"] and live.take_pending(g, "chatgpt.com") == {}, "pending is used once"
    assert any(n["kind"] == "session" for n in g.graph()["nodes"])
    # history: what was true when
    g.ingest("I work at Fernhill", "chatgpt.com", ts=t0 + 7 * day)
    g.ingest("I left Fernhill, now I work at Kestrel", "chatgpt.com", ts=t0 + 12 * day)
    Q = brain.query(f"where did I work {int((time.time() - (t0 + 9 * day)) / day)} days ago")
    assert "Fernhill" in (g.answer(Q) or {}).get("text", ""), g.answer(Q)
    assert g.recall("where do I work")["answer"]["text"] == "You work at Kestrel."
    assert any(f["label"] == "Fernhill" and f["to"] for f in g.timeline())
    body, _, _ = live.export(g, "cypher")
    assert b"CREATE (:MB:Thing" in body and b"-[:WORKS_AT" in body
    rz = g.ekeys["kestrel"]
    assert live.path(g, rz, g.ekeys["fernhill"])["found"] or True
    assert live.neighbors(g, rz)["nodes"]
    print("selfcheck ok")




def authcheck():
    """The auth contract end to end, over real HTTP against a throwaway in-memory server on a free port."""
    import tempfile, urllib.request, urllib.error
    global G, ACCESS_LOG
    G, ACCESS_LOG = Graph(":memory:"), os.path.join(tempfile.mkdtemp(), "access.log")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    Handler.log_message = lambda *a: None

    def call(method, path, body=None, cookie=None, token=None, **hdr):
        h = {"Content-Type": "application/json", **{k.replace("_", "-"): v for k, v in hdr.items()}}
        h.update({"Cookie": "mb_session=" + cookie} if cookie else {}, **({"Authorization": "Bearer " + token} if token else {}))
        req = urllib.request.Request(url + path, None if body is None else json.dumps(body).encode(), h, method=method)
        try:
            r = urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as e:
            r = e
        raw = r.read()
        try:
            return r.status, r.headers, json.loads(raw)
        except ValueError:
            return r.status, r.headers, raw
    st = lambda *a, **k: call(*a, **k)[0]
    sess = lambda h: re.search(r"mb_session=([^;]*)", h["Set-Cookie"])[1]
    # first run: the setup code is needed unless the request is typed on this machine
    assert call("GET", "/api/auth/state")[2] == {"setup_needed": True, "authed": False, "code_required": False}
    assert call("GET", "/api/auth/state", X_Forwarded_For="203.0.113.9")[2]["code_required"]
    code = setup_code(G.db)
    assert re.fullmatch(r"\d{4}-\d{4}", code)
    assert st("POST", "/api/auth/setup", {"password": "correct horse"}, Host="192.0.2.7") == 403            # off-loopback, no code
    assert st("POST", "/api/auth/setup", {"password": "correct horse", "code": "0000-0000"}, Host="192.0.2.7") == 403
    assert st("POST", "/api/auth/setup", {"password": "short", "code": code}, Host="192.0.2.7") == 400
    s, h, _ = call("POST", "/api/auth/setup", {"password": "correct horse", "code": code.replace("-", "")}, Host="192.0.2.7")
    c = h["Set-Cookie"]
    assert s == 200 and setup_code(G.db) is None and all(f in c for f in ("HttpOnly", "SameSite=Lax", "Path=/")) and "Secure" not in c, c
    a = sess(h)
    assert st("POST", "/api/auth/setup", {"password": "someone else", "code": code}) == 409
    assert call("GET", "/api/auth/state", cookie=a)[2] == {"setup_needed": False, "authed": True, "code_required": False}
    # login: wrong passwords lock the IP out, even for the right one
    FAILS.clear()
    for _ in range(5):
        assert st("POST", "/api/auth/login", {"password": "wrong password"}) == 401
    s, h, _ = call("POST", "/api/auth/login", {"password": "correct horse"})
    assert s == 429 and 0 < int(h["Retry-After"]) <= 60, s
    FAILS.clear()
    s, h, _ = call("POST", "/api/auth/login", {"password": "correct horse"}, X_Forwarded_Proto="https")
    assert s == 200 and "Secure" in h["Set-Cookie"]
    b = sess(h)
    # nothing without a session or a token; the app's files, health, login and pairing are open
    for m, path in [("GET", "/graph"), ("GET", "/recall?q=x"), ("GET", "/context"), ("GET", "/profile"), ("GET", "/status"),
                    ("GET", "/export"), ("GET", "/sessions"), ("GET", "/handoff"), ("GET", "/ask?q=x"), ("GET", "/tools.json"),
                    ("GET", "/share"), ("GET", "/timeline"), ("GET", "/ai"), ("GET", "/api/tokens"), ("GET", "/api/pair/pending"),
                    ("POST", "/capture"), ("POST", "/remember"), ("POST", "/mcp"), ("POST", "/rebuild"), ("POST", "/session"),
                    ("POST", "/settings/ai-key"), ("POST", "/api/tokens"), ("POST", "/api/auth/logout"), ("POST", "/api/auth/password"),
                    ("POST", "/api/pair/approve"), ("DELETE", "/node/1"), ("DELETE", "/api/tokens/1")]:
        body = {} if m == "POST" else None
        assert st(m, path, body) == 401 and st(m, path, body, token="mb_nope") == 401, path
        assert call(m, path, body)[2] == {"error": "login required"}, path
    for path in ("/", "/index.html", "/health", "/api/auth/state", "/manifest.webmanifest", "/mcp_stdio.py"):
        assert st("GET", path) == 200, path
    assert st("GET", "/assets/%2e%2e/server.py") == 401 and st("GET", "/data/mindbaton.db") == 401     # no way out of assets/
    _, h, _ = call("GET", "/")
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"] and h["Referrer-Policy"] == "no-referrer" \
        and h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY", dict(h)
    s, _, z = call("GET", "/mindbaton-extension.zip")
    assert s == 200 and "manifest.json" in zipfile.ZipFile(io.BytesIO(z)).namelist()
    health = call("GET", "/health")[2]
    assert health["name"] == "mindbaton" and not health["authed"] and "captures" not in health, health
    # the session works, sliding; a cookie never works cross-site
    assert st("GET", "/graph", cookie=a) == 200 and st("GET", "/graph", cookie="forged") == 401
    G.db.execute("UPDATE logins SET expires=?", (time.time() + 86400,))
    _, h, _ = call("GET", "/profile", cookie=a)
    assert sess(h) == a and G.db.execute("SELECT expires FROM logins WHERE hash=?", (sha(a),)).fetchone()[0] > time.time() + 29 * 86400
    assert st("POST", "/capture", {"text": "I prefer dark mode everywhere"}, cookie=a, Origin="https://evil.example") == 403
    assert st("POST", "/capture", {"text": "I prefer dark mode everywhere"}, cookie=a, Origin=url) == 200
    # device tokens: full can export, connector reaches /mcp only (no forget), rate-limited, logged
    s, _, full = call("POST", "/api/tokens", {"name": "Laptop", "kind": "mcp"}, cookie=a)
    assert s == 200 and full["token"].startswith("mb_") and full["scope"] == "full", full
    conn = call("POST", "/api/tokens", {"name": "Claude.ai", "kind": "connector"}, cookie=a)[2]
    assert conn["scope"] == "connector" and st("POST", "/api/tokens", {"name": "x", "kind": "toaster"}, cookie=a) == 400
    assert st("GET", "/api/tokens", token=full["token"]) == 403 and st("POST", "/api/pair/approve", {"code": "x"}, token=full["token"]) == 403
    assert st("GET", "/export", token=full["token"]) == 200 and st("GET", "/recall?q=dark", token=full["token"]) == 200
    assert st("GET", "/export", token=conn["token"]) == 403 and st("DELETE", "/node/1", token=conn["token"]) == 403
    listed = call("POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, token=conn["token"])[2]
    assert "forget" not in {t["name"] for t in listed["result"]["tools"]}
    forget = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "forget", "arguments": {"id": 1}}}
    assert call("POST", "/mcp", forget, token=conn["token"])[2]["result"]["isError"]
    assert "forget" in open(ACCESS_LOG).read() and conn["token"] not in open(ACCESS_LOG).read()
    s, _, d = call("POST", f"/t/{conn['token']}/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert s == 200 and d["result"]["tools"]
    assert st("GET", f"/t/{conn['token']}/graph") == 404 and st("GET", f"/t/{conn['token']}/health") == 200
    assert st("POST", "/t/mb_wrong/mcp", {}) == 401 and st("GET", "/t/mb_wrong/health") == 401
    CONN_HITS[conn["id"]].extend([time.time()] * 60)
    assert st("POST", f"/t/{conn['token']}/mcp", {"jsonrpc": "2.0", "id": 1, "method": "ping"}) == 429
    d = call("GET", f"/t/{full['token']}/health")[2]
    assert d["authed"] and d["captures"] == 1, d
    rows = call("GET", "/api/tokens", cookie=a)[2]
    assert [r["name"] for r in rows] == ["Laptop", "Claude.ai"] and all(set(r) == {"id", "name", "kind", "scope", "created", "last_used"} for r in rows)
    dev = call("GET", "/status", cookie=a)[2]["devices"]
    assert dev["connector"]["recent"] and dev["mcp"]["recent"] and not dev["phone"]["recent"] and dev["extension"]["tokens"] == 0, dev
    assert st("DELETE", f"/api/tokens/{full['id']}", cookie=a) == 200 and st("GET", "/export", token=full["token"]) == 401
    assert st("DELETE", f"/api/tokens/{full['id']}", cookie=a) == 404
    # pairing: approve -> the token is handed out once; deny; expiry
    s, _, pr = call("POST", "/api/pair/start", {"name": "Chrome on laptop", "kind": "extension"})
    assert s == 200 and re.fullmatch(r"[A-Z]{4}-[A-Z]{4}", pr["code"]) and pr["expires_in"] == 600 and pr["approve_url"] == f"{url}/#pair/{pr['code']}", pr
    poll = lambda: call("GET", "/api/pair/poll?poll=" + pr["poll"])[2]
    assert poll()["status"] == "pending" and call("GET", "/api/pair/poll?poll=guess")[2] == {"status": "expired"}
    assert [x["name"] for x in call("GET", "/api/pair/pending", cookie=a)[2]] == ["Chrome on laptop"]
    assert st("POST", "/api/pair/approve", {"code": pr["code"].lower().replace("-", "")}, cookie=a) == 200
    got = poll()
    assert got["status"] == "approved" and got["token"].startswith("mb_") and got["kind"] == "extension" and got["scope"] == "full", got
    assert poll() == {"status": "expired"} and call("GET", "/health", token=got["token"])[2]["authed"]
    assert call("GET", "/status", cookie=a)[2]["extension"]["ok"], "a paired extension that talked turns its tick green"
    pr = call("POST", "/api/pair/start", {"name": "Pixel", "kind": "phone"})[2]
    assert st("POST", "/api/pair/deny", {"code": pr["code"]}, cookie=a) == 200 and poll() == {"status": "denied"} and poll()["status"] == "expired"
    pr = call("POST", "/api/pair/start", {"name": "Pixel", "kind": "phone"})[2]
    PAIRS[pr["code"]]["created"] -= PAIR_S + 1
    assert poll() == {"status": "expired"} and st("POST", "/api/pair/approve", {"code": pr["code"]}, cookie=a) == 404
    assert st("POST", "/api/pair/start", {"name": "x", "kind": "toaster"}) == 400 and not call("GET", "/api/pair/pending", cookie=a)[2]
    # password change keeps this session and signs out the others; logout-all ends every session, tokens stay
    assert st("POST", "/api/auth/password", {"current": "wrong one!", "new": "battery staple"}, cookie=a) == 403
    assert st("POST", "/api/auth/password", {"current": "correct horse", "new": "short"}, cookie=a) == 400
    assert st("POST", "/api/auth/password", {"current": "correct horse", "new": "battery staple"}, cookie=a) == 200
    assert st("GET", "/graph", cookie=a) == 200 and st("GET", "/graph", cookie=b) == 401
    assert st("POST", "/api/auth/login", {"password": "correct horse"}) == 401
    s, h, _ = call("POST", "/api/auth/login", {"password": "battery staple"})
    b = sess(h)
    _, h, _ = call("POST", "/api/auth/logout", cookie=b)
    assert "Max-Age=0" in h["Set-Cookie"] and st("GET", "/graph", cookie=b) == 401 and st("GET", "/graph", cookie=a) == 200
    b = sess(call("POST", "/api/auth/login", {"password": "battery staple"})[1])
    assert st("POST", "/api/auth/logout-all", cookie=a) == 200 and st("GET", "/graph", cookie=a) == 401 and st("GET", "/graph", cookie=b) == 401
    assert call("GET", "/health", token=got["token"])[2]["authed"]
    # the owner's shell resets the password: first run again, device tokens keep working
    assert re.fullmatch(r"\d{4}-\d{4}", reset_password(G.db)) and call("GET", "/api/auth/state")[2]["setup_needed"]
    assert call("GET", "/health", token=got["token"])[2]["authed"] and check_password("x" * 8, hash_password("x" * 8))
    srv.shutdown()
    srv.server_close()
    os.remove(ACCESS_LOG)
    os.rmdir(os.path.dirname(ACCESS_LOG))
    print("auth ok")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        os.environ["MINDBATON_AI"] = "0"  # tests never call the AI
        brain.selfcheck()
        handoff.selfcheck()
        selfcheck()
        authcheck()
        sys.exit()
    os.makedirs(DATA, mode=0o700, exist_ok=True)
    link = lambda code: f"{PUBLIC_URL or f'http://{HOST if HOST not in ('0.0.0.0', '::', '') else 'localhost'}:{PORT}'}/?code={code}"
    if "--setup-code" in sys.argv or "--reset-password" in sys.argv:  # the owner's shell, no server needed
        db = sqlite3.connect(DB, isolation_level=None)
        db.executescript(SCHEMA)
        if "--reset-password" in sys.argv:
            print("Password removed and every browser signed out (device tokens still work).")
        code = reset_password(db) if "--reset-password" in sys.argv else setup_code(db)
        print(f"Setup code: {code} — open {link(code)}" if code else "Mindbaton already has an owner. Forgot the password? "
              "Run: python3 server.py --reset-password")
        sys.exit()
    G = Graph()
    G.naming = True  # only the running server asks the AI for topic names (never tests or the benchmark)
    G.dirty = True
    code = setup_code(G.db)
    if code:
        print(f"Setup code: {code} — open {link(code)}", flush=True)
    if os.environ.get("MINDBATON_WATCH_CLAUDE", "1") != "0" and not G.meta("demo"):  # a demo never picks up real transcripts
        live.watch_claude_code(G, LOCK)
    print(f"Mindbaton {VERSION} on http://{HOST}:{PORT} · data in {DATA}", flush=True)
    # ponytail: one lock around the graph; per-thread connections + WAL readers if concurrent load ever matters
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
