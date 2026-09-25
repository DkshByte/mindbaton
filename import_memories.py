#!/usr/bin/env python3
"""Import what other AIs remember on this machine into Mindbaton: the same files `mindbaton.py import` reads (Claude
Code's CLAUDE.md, rules and auto memory; Codex's AGENTS.md and memories; GEMINI.md; Windsurf, Copilot and Cline rules),
never chats, keys or settings. For the server's own machine, with no setup.

    python3 import_memories.py              # everything found
    python3 import_memories.py FILE ...     # just these notes (markdown or text), filed as Claude Code
    MINDBATON_URL=http://host:3004 MINDBATON_TOKEN=mb_... python3 import_memories.py   # a server elsewhere

It talks to the running server over HTTP (POST /import), like any device. Next to the server (same data dir) it needs no
setup: it makes itself a temporary token for the first admin account (this machine's own memories are theirs, like its
Claude Code transcripts) and revokes it when done. For another account, or a server elsewhere, pass a token from
Settings → Devices. The server turns each note into statements ("the user prefers X" -> "I prefer X"), filed under the
note's name so they sort into one topic, redacts secrets and skips what it already has: safe to re-run. A demo memory
never takes them.
"""
import os, sqlite3, sys, time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import server  # noqa: E402  (same folder; importing starts nothing, and loads mindbaton.env)
import mindbaton  # noqa: E402

URL = os.environ.get("MINDBATON_URL", f"http://127.0.0.1:{server.PORT}").rstrip("/")


def local_token():
    """A token for this run only, for the first admin, written straight into the local auth database (this shell can
    read the data dir, so it may)."""
    path = os.path.join(server.DATA, "auth.db")
    db = sqlite3.connect(path, isolation_level=None, timeout=10) if os.path.exists(path) else None
    aid = db and server.local_account(db)
    if not aid:
        sys.exit(f"No account in {server.DATA} takes this machine's memories (start the server and set it up first, or its "
                 "first admin was deleted), or set MINDBATON_TOKEN (Settings → Devices) and MINDBATON_URL")
    mem = os.path.join(server.acct_dir(aid), "memory.db")
    if os.path.exists(mem) and sqlite3.connect(mem).execute("SELECT 1 FROM meta WHERE k='demo'").fetchone():
        sys.exit("That account is a demo memory (demo.py): it never takes this machine's real memories")
    t = server.issue_token(db, aid, "import_memories.py (temporary)", "agent")
    return lambda: db.execute("UPDATE tokens SET revoked=? WHERE id=?", (time.time(), t["id"])), t["token"]


def main(paths):
    token = os.environ.get("MINDBATON_TOKEN", "").strip()
    revoke = None
    if not token:
        revoke, token = local_token()
    clean = lambda text: "\n".join(line for line in text.splitlines() if not mindbaton.SECRET_LINE.search(line))
    found = {"claude": [(Path(p), clean(open(p, encoding="utf-8").read()), os.path.getmtime(p)) for p in paths]} if paths \
        else mindbaton.memory_files(list(mindbaton.MEMORY_FILES))
    for t, files in found.items():
        for p, _, _ in files:
            print(f"  {mindbaton.SITE[t]:12} {p}")
    try:
        got = mindbaton.send_memories(URL, token, found)
    except RuntimeError as e:
        sys.exit(f"import failed: {e}")
    finally:
        if revoke:
            revoke()
    print(f"imported {sum(n for n, _ in got.values())} statements from {sum(map(len, found.values()))} notes "
          f"({sum(s for _, s in got.values())} already imported)")


if __name__ == "__main__":
    main(sys.argv[1:])
