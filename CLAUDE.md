# Mindbaton — working here

Rules for anyone changing this repo, human or code agent. What it is: `README.md`. Product truth: `PRODUCT.md`.
The app's visual system: `DESIGN.md`. How to contribute: `CONTRIBUTING.md`. What must stay secure: `SECURITY.md`.

## Ground rules

- **Stdlib only.** No pip packages, no build step, no CDN at runtime. Fonts, logos and scripts live in `assets/` and are
  served by `server.py`; add a brand by extending `fetch_assets.py` (real logos only — never draw a fake one).
- **Laziest solution that actually works** — shortest correct diff, no speculative abstractions — but never cut
  security, validation, data-loss protection or accessibility. Non-trivial logic leaves one runnable check (extend
  `python3 server.py --check`).
- **No real personal data anywhere in the repo.** Tests use synthetic people; screenshots use `demo.py`. A user's own
  test cases go in `data/private/` (git-ignored) — never copy them into tracked files.
- **No hardcoded addresses.** The base URL comes from `MINDBATON_PUBLIC_URL` or the request (`Host`,
  `X-Forwarded-Proto`). No IPs, hostnames or tailnet names in code or docs (examples use `192.168.1.20` and
  `mindbaton.example.com`).
- **Design:** "Clean dark", Linear/Vercel craft bar — read `DESIGN.md` before touching `index.html`, `share.html` or the
  extension UI. Honour `prefers-reduced-motion`.

## How the brain works — keep it this way

- **Rules decide, AI only words things.** Understanding (`brain.py`, rules + the bundled SCOWL word list in `assets/words`)
  and topic assignment (`Graph.cluster`) are deterministic and offline. Improve them with general rules, never
  one-off string matches.
- **Everything that arrives goes through `brain.scrub()`** (agent harness wrappers, Gemini's hidden "You said",
  Perplexity's glued clocks, pasted hand-off packs) and `brain.hints()` (model + true time from wrappers). Add new noise
  patterns there, never in a caller. Short agent-steering messages (`brain.steering`) and typos (`brain.typo`) never
  become memories or things.
- **One name per AI:** `server.ai_of(site)` maps every raw source (web host, MCP `clientInfo.name`,
  `antigravity-client`…) to the display name that is also its logo key. Never compare raw site strings.
- **Topics = conversations.** A memory's unit is its chat (`ctx`); units merge by average-linkage tf-idf (`TAU`);
  projects (`memory://` notes, coding sessions' `cwd` under `~`) pool; different projects never merge. The bench gate
  "same topic across apps" is the core promise as a test — keep it green.
- **Attribution:** a capture's `extra` holds `session` (its chat) and `model`; memory sources are
  `{ai, chat, ts, ctx, model, note}`; turns carry `model` and `ts`. Claude Code transcripts give the model per reply and
  the app's own title (`ai-title`); agent hooks can send their conversation id, title, model and times to `/session`.

## Measure every logic change

- `python3 bench.py` must stay **all green, holdout included** — with and without `data/private/`. When a message is
  misread, add a synthetic equivalent to `bench.py` (`PHRASINGS`, `V1`, `QUERIES`, …) first, then fix the rule.
  `data/private/bench_real.json` (same shape as `V1`) adds a gate for the owner's own messages when present.
- `python3 topics_check.py` scores topics against a hand-labelled key of the owner's real memories in
  `data/private/topics_gold.json` (precision must stay 1.0); without the key it says so and exits 0.
- **After changing `brain.py`, bump `LOGIC_VERSION`** in `server.py`, so the next start re-derives the graph from the raw
  `captures` table. Never edit derived tables (`nodes`, `edges`, `fts`) by hand.

## Data and safety

- Forgetting must survive rebuilds and re-reads (`forgotten` table, matched on normalised text). Secrets are redacted
  before anything is stored (`brain.redact`); keep it that way.
- The server is threaded but every graph access holds `LOCK` (one shared SQLite connection). Read request bodies
  before taking the lock.
- **Auth is the contract in `SECURITY.md`:** every endpoint except the app's files, `/health`, login and pairing needs
  the owner's session cookie (`mb_session`) or a device token (`Authorization: Bearer mb_…`; `/t/<token>/` path prefix
  only for `/mcp` and `/health`). Cookie-authenticated writes pass the same-origin check (`foreign()`). Connector-scope
  tokens get no forget/export, are rate-limited and logged to `access.log`. New endpoints are authenticated by default.
- Never print, log or commit secrets: the data dir holds `mindbaton.db`, `ai_keys` (0600) and `access.log`; `data/` and
  `*.env` are git-ignored.

## Optional AI

`ai.py`: Gemini → Groq, keys in `<data>/ai_keys` or `GEMINI_KEY`/`GROQ_KEY`. It writes hand-off summaries, topic
names/summaries and search answers (`/ask`, cited, grounded in recall), always outside `LOCK`
(`ai.prepare`/`ai.warm`/`ai.warm_topics`), validated and cached (names in `meta.topic_names` by membership signature, so a
rebuild makes no calls; forgetting clears them). Only the running server calls it (`G.naming`), never tests or the bench.
No keys or `MINDBATON_AI=0` = rule names and the extractive pack. `python3 ai.py` is a live check (uses real quota).

## Running it

- Dev server: `MINDBATON_DATA=/tmp/mb-dev MINDBATON_PORT=3005 python3 server.py` (seed it with
  `MINDBATON_DATA=/tmp/mb-dev python3 demo.py --password demo-pass-123`). Editing `index.html` needs no restart.
- Installed service: `systemctl --user restart mindbaton` (Linux) · `launchctl kickstart -k gui/$(id -u)/ai.mindbaton`
  (macOS) · `docker compose up -d --build` (Docker).
- The extension zip (`/mindbaton-extension.zip`) is built on the fly from `extension/` — never commit a zip.
- MCP is served at `/mcp` (streamable HTTP, JSON responses); `mcp_stdio.py` bridges stdio-only clients.
