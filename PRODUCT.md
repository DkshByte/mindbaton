# Product

<!-- impeccable:product-schema 1 -->

## Platform

web (laptop browser), plus an installable phone app (Android share target), a Chromium browser extension, and MCP for
coding agents and the Claude/ChatGPT apps

## Users
One person per install: the owner, who runs Mindbaton on their own hardware (home server, NAS, mini PC, laptop, or
Docker) and looks at their own memory from their laptop browser and phone. They chat with many AIs (ChatGPT, Claude,
Gemini, Perplexity, DeepSeek, Grok, Copilot…) and use coding agents (Claude Code, Codex, Cursor, Antigravity…); the
extension and MCP feed everything they say into Mindbaton. Technical enough to run one install command or
`docker compose up`, not necessarily a developer.

## Product Purpose
Tell one AI, every AI knows. A private, self-hosted memory shared by every AI the owner talks to. When they open the app
they want all of it: see what it knows about them, explore how memories connect, search and clean up wrong memories,
check that capture from each AI is working, and pass a chat that hit its limit to another AI (the baton).

## Positioning
Memory that belongs to the user, not to one AI vendor: one graph fed by every AI chat, hosted on their own box;
understanding and topics are deterministic (brain.py, cluster) and every graph is rebuildable from raw captures — an
optional free AI only writes summaries and topic names. Open source (AGPL-3.0), no account, no cloud, no telemetry.

## Operating Context
- Served by `server.py` on the owner's machine (default port 3004), reached on the LAN or over HTTPS through Tailscale,
  Cloudflare Tunnel or a reverse proxy. Owner password + per-device tokens; first run is claimed with a setup code.
- Opened in a laptop browser; the phone gets the same page (installable) and a Share screen.
- Data: memories (typed fact / preference / goal / question / task / note), entities (tech, name, person, thing,
  self="You"), relations, "similar" links, "replaces" links for superseded facts, auto topics incl. "About you",
  per-memory source AIs, chat titles and models, whole chats with context meters, counts and recall hits.

## Capabilities and Constraints
- API: GET /graph, /recall?q= (direct answer + memories), /context?q= (a briefing for an AI), /profile, /sessions,
  /handoff; DELETE /node/<id> (forget, sticks across rebuilds, even when the text is re-read differently); POST /rebuild.
  Auth: /api/auth/*, /api/tokens, /api/pair/* (device pairing with owner approval).
- MCP (streamable HTTP, JSON responses) at POST /mcp with tools context, recall, remember, profile, handoff, sessions,
  save_conversation, forget; `mcp_stdio.py` bridges stdio-only clients (Claude Desktop). Web AIs can't reach a LAN MCP
  server, so the extension's Alt+M inserts the briefing into the chat box instead.
- Quality is measured, not asserted: `python3 bench.py` (gates on relations, stale facts, queries, answers, topics,
  redaction, v1-extension messages, typos, steering, cross-app topics, phrasings, plus a never-tuned holdout).
- Single `index.html`, no build step, no external fetches: fonts and logos are served from `assets/` on the same server.
- Stdlib-only backend; no new dependencies.

## Brand Commitments
Name: Mindbaton (ids: `mindbaton`). Mark and icons from `assets/brand/` (the mark is a placeholder; every icon derives from
`assets/brand/mark.svg`). Visual register: clean modern dark at the craft level of Linear and Vercel — see DESIGN.md.
Every product or company shown uses its real logo (downloaded once by `fetch_assets.py`, never fetched live).

## Evidence on Hand
A new install starts empty and fills up over days. Empty and near-empty states must look intentional and say what to
connect next. Screenshots and demos use `demo.py` (a fictional person), never real data.

## Product Principles
- The user's own words are the content; show them verbatim.
- Every memory is traceable to which AI, which chat and which model it came from; the same subject in different apps is
  one topic.
- Forgetting is always one click away and permanent.
- Sorting is automatic; the UI explains the sorting rather than asking the user to do it.
- Private by default: nothing leaves the box unless the owner adds an AI key or connects an app.
