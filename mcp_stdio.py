#!/usr/bin/env python3
"""Mindbaton MCP bridge: stdio <-> the Mindbaton server's /mcp endpoint. Stdlib only, any OS with Python 3.8+.

For MCP clients that launch a local command (Claude Desktop, some IDEs). Clients that speak HTTP can skip this and
use <server>/mcp directly with an `Authorization: Bearer <token>` header.

    MINDBATON_URL=http://your-server:3004 MINDBATON_TOKEN=mb_... python3 mcp_stdio.py

Make the token in the Mindbaton app: Settings → Devices.
"""
import json, os, sys, urllib.error, urllib.request

BASE = os.environ.get("MINDBATON_URL", "").strip().rstrip("/")
if not BASE:
    sys.exit("mcp_stdio.py: set MINDBATON_URL to your Mindbaton server (e.g. http://your-server:3004) and MINDBATON_TOKEN to a device token")
URL = BASE if BASE.endswith("/mcp") else BASE + "/mcp"
TOKEN = os.environ.get("MINDBATON_TOKEN", "").strip()
SESSION = {}  # the server's Mcp-Session-Id, sent back so this app is credited with its own saves


def forward(line):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    if SESSION.get("id"):
        headers["Mcp-Session-Id"] = SESSION["id"]
    req = urllib.request.Request(URL, data=line.encode(), method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        SESSION["id"] = r.headers.get("Mcp-Session-Id") or SESSION.get("id")
        return r.read().decode()


for line in sys.stdin:  # newline-delimited JSON-RPC, as MCP stdio specifies
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    try:
        out = forward(line)
    except (urllib.error.URLError, OSError) as e:
        if isinstance(msg, dict) and msg.get("id") is not None:  # tell the client instead of hanging it
            why = "the token was refused — make a new one in Settings → Devices" if getattr(e, "code", None) in (401, 403) \
                else f"Mindbaton unreachable at {URL}: {e}"
            out = json.dumps({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32000, "message": why}})
        else:
            continue
    if out.strip():
        sys.stdout.write(out.strip() + "\n")
        sys.stdout.flush()
