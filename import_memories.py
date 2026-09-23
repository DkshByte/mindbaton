#!/usr/bin/env python3
"""Import the memories other AIs keep on this machine into Mindbaton.

  Claude Code   ~/.claude/projects/*/memory/*.md   (MEMORY.md, the index, is skipped)
  Codex         ~/.codex/memories/*

    python3 import_memories.py              # everything found
    python3 import_memories.py FILE ...     # just these notes (markdown or text), filed as Claude Code
    MINDBATON_URL=http://host:3004 MINDBATON_TOKEN=mb_... python3 import_memories.py   # a server elsewhere

It talks to the running server over HTTP, like any device. Next to the server (same data dir) it needs no setup: it makes
itself a temporary token in the local database and revokes it when done. Elsewhere, pass a token from Settings → Devices.

Each note becomes short standalone statements ("the user prefers X" -> "I prefer X"), filed under the note's name so
they sort into one topic. Safe to re-run: statements already sent are remembered in <data dir>/imported.json and skipped.
"""
import glob, hashlib, json, os, re, sqlite3, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import server  # noqa: E402  (same folder; importing starts nothing, and loads mindbaton.env)
from server import third_to_first  # noqa: E402

URL = os.environ.get("MINDBATON_URL", f"http://127.0.0.1:{server.PORT}").rstrip("/")
STATE = os.path.join(server.DATA, "imported.json")
AUTH = {}
SOURCES = [("claude-code", "~/.claude/projects/*/memory/*.md"), ("codex", "~/.codex/memories/*")]


def frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n?", text, re.S)
    meta = dict(re.findall(r"^[ \t]*(\w+):[ \t]*\"?(.*?)\"?[ \t]*$", m[1], re.M)) if m else {}   # nested keys too (metadata.type)
    return meta, text[m.end():] if m else text


def statements(body, description=""):
    """Markdown -> short statements: one per bullet, long paragraphs split into sentence groups of ~350 chars."""
    body = re.sub(r"\[\[([^\]]+)\]\]", r"\1", body)                        # [[wiki links]]
    body = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", body)                   # [text](url)
    body = re.sub(r"(\*\*|__|`)(.+?)\1", r"\2", body)                       # **bold**, `code`
    out = [description] if len(description) > 12 else []
    for block in re.split(r"\n\s*\n", body):
        for item in re.split(r"\n(?=\s*(?:[-*]|\d+\.)\s)", block):
            item = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", item).replace("\n", " ").strip()
            if len(item) < 12 or item.startswith("#"):
                continue
            cur = ""
            for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z(`])", item):
                if cur and len(cur) + len(sent) > 350:
                    out.append(cur)
                    cur = sent
                else:
                    cur = (cur + " " + sent).strip()
            if cur:
                out.append(cur)
    return out


def first_person(t):
    t = re.sub(r"\b(for|to|with|by|from|ask|tell|asked|told|let|help|remind|show)\s+(?:the\s+)?user\b", r"\1 me", t, flags=re.I)
    return third_to_first(t)


def post(body):
    req = urllib.request.Request(URL + "/capture", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + AUTH["token"]})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["ids"]


def local_token():
    """A token for this run only, written straight into the local database (this shell can read the data = owner)."""
    if not os.path.exists(server.DB):
        sys.exit(f"No Mindbaton database at {server.DB}: set MINDBATON_TOKEN (Settings → Devices) and MINDBATON_URL")
    db = sqlite3.connect(server.DB, isolation_level=None, timeout=10)
    t = server.issue_token(db, "import_memories.py (temporary)", "agent")
    return lambda: db.execute("UPDATE tokens SET revoked=? WHERE id=?", (time.time(), t["id"])), t["token"]


def main(paths):
    AUTH["token"] = os.environ.get("MINDBATON_TOKEN", "").strip()
    revoke = None
    if not AUTH["token"]:
        revoke, AUTH["token"] = local_token()
    try:
        run(paths)
    finally:
        if revoke:
            revoke()


def run(paths):
    try:
        done = set(json.load(open(STATE)))
    except (OSError, ValueError):
        done = set()
    files = [(src, p) for src, pattern in SOURCES for p in sorted(glob.glob(os.path.expanduser(pattern)))
             if os.path.basename(p) != "MEMORY.md" and os.path.isfile(p)] if not paths else [("claude-code", p) for p in paths]
    sent = skipped = memories = 0
    for src, path in files:
        meta, body = frontmatter(open(path, encoding="utf-8", errors="replace").read())
        name = meta.get("name") or os.path.splitext(os.path.basename(path))[0]
        base = os.path.getmtime(path)
        facts = statements(body, meta.get("description", ""))
        if meta.get("type") == "project":  # a project note means the owner works on it
            title = next((w for w in re.findall(r"[A-Za-z][\w-]+", meta.get("description", "") + " " + body[:300])
                          if w.lower() == name.lower().replace("-", "")), name.replace("-", " "))
            facts.insert(0, f"I'm working on {title}")
        for i, s in enumerate(facts):
            text = first_person(s)
            h = hashlib.sha1(f"{src}\0{name}\0{text}".encode()).hexdigest()
            if h in done:
                skipped += 1
                continue
            ids = post({"text": text, "site": src, "chat": name, "url": f"memory://{src}/{name}", "ts": base + i})
            memories += len(ids)
            sent += 1
            done.add(h)
        print(f"  {src:12} {name:28} {path}")
    os.makedirs(server.DATA, mode=0o700, exist_ok=True)
    json.dump(sorted(done), open(STATE, "w"))
    print(f"imported {sent} statements from {len(files)} notes -> {memories} memories ({skipped} already imported)")


if __name__ == "__main__":
    main(sys.argv[1:])
