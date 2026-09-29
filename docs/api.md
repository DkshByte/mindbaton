# API reference

Everything the app, the extension and your AIs do goes through one small HTTP API on your Mindbaton. You can use it
from scripts too. In the examples, replace `http://192.168.1.20:3004` with your address and `mb_xxxxxxxx` with a
[device token](connect.md#device-tokens).

## Authentication

Every endpoint except the app's own files, `/health`, login and pairing needs either the owner's session cookie (the
browser) or a device token in a header:

```sh
curl -H "Authorization: Bearer mb_xxxxxxxx" http://192.168.1.20:3004/profile
```

Without one you get `401`. Each token reaches only its own account's memory.

- **Full tokens** (apps, agents, scripts) can use everything below.
- **Connector tokens** (the Claude and ChatGPT apps over the internet) reach `/mcp` only, never get `forget`, are
  limited to 60 requests a minute and 600 an hour, and every request is written to `access.log`. Because those apps
  can't send headers, the token goes in the path: `https://mindbaton.example.com/t/mb_xxxxxxxx/mcp`.

Requests from a browser with the session cookie must come from Mindbaton's own page; other websites are refused. See
[security](../SECURITY.md) for the full model.

## MCP

`POST /mcp` speaks the Model Context Protocol over streamable HTTP with JSON responses. Coding agents, editors and the
Claude and ChatGPT apps connect here (setup for each is in [connect your AIs](connect.md)). `GET /tools.json` returns
the same tools in the JSON shape the Claude and OpenAI tool-calling APIs take.

| Tool | Arguments | What it does |
|---|---|---|
| `context` | `topic` (optional) | A briefing about the user: who they are, what they use and work on, their preferences, and what they've said before about `topic`. Call it at the start of a conversation. Read-only. |
| `recall` | `query`, `k` (1–20) | Searches everything the user told any AI. Returns a direct answer when one is known, plus the most relevant memories with their ids. Read-only. |
| `remember` | `fact`, `model` | Saves one lasting fact in the user's own first person ("I use Neovim"). `model` is the AI's own model name, if it knows it. |
| `profile` | none | Everything known about the user as a structured profile: summary, facts, preferences, goals. Read-only. |
| `handoff` | `session`, `budget` (200–12000), `about` | A continuation pack for a conversation from another AI: the goal, decisions, key code, open questions and the latest messages. No `session` = the most recent chat. `about: true` also adds what Mindbaton knows about the user. Read-only. |
| `sessions` | `limit` (1–50) | Recent conversations across AIs: id, AI, title, messages, how full each is and whether it hit a limit. Read-only. |
| `save_conversation` | `title`, `turns`, `summary`, `model` | Saves the current conversation (turns of `{role, text}`, or a summary) so it can be continued elsewhere. Returns the id to hand off. |
| `forget` | `id` | Permanently deletes a memory by the id `recall` returned. Not available to connector tokens. |

Mindbaton also tells every AI that connects how to use these: call `context` first, `recall` before anything personal,
`remember` for lasting facts, `handoff` to continue a chat.

## Read

| Request | Returns |
|---|---|
| `GET /recall?q=…&k=8` | `answer` (when one is known), ranked `memories` (each with `match`: answer, thing, words or meaning), and related `conversations`. `k` up to 50. |
| `GET /context?q=…&budget=1800` | `{"text": …}`: a briefing an AI can read, about the user and what's relevant to `q`. `budget` in tokens, 300–8000. |
| `GET /profile` | Everything known about the user, sorted by kind. |
| `GET /graph` | All memories, things, links and topics (what the app's map draws). |
| `GET /sessions?limit=40` | Recent chats from every AI, with model, messages and how full each is. |
| `GET /session?id=…` | One chat's messages. `id` is a chat id or words from its title. |
| `GET /handoff?session=…&budget=1500&about=1` | `{"text", "tokens", "sections", "session"}`: the hand-off pack for a chat. `about=1` adds what Mindbaton knows about the user. |
| `GET /timeline?subject=me` | How facts about a subject changed over time. |
| `GET /export?format=json` | Everything, as a download. `format` is `json`, `cypher` (Neo4j) or `graphml`. Not for connector tokens. |
| `GET /tools.json` | The MCP tools in tool-calling JSON. |
| `GET /health` | `{"ok", "name", "version", "setup_needed", "authed"}`. No token needed. |

## Write

| Request | Body | What it does |
|---|---|---|
| `POST /capture` | `{"text", "site", "chat", "url", "ts"}` | Saves one message as you said it (what the browser extension sends). Secrets are redacted first. |
| `POST /remember` | `{"text", "entities", "relations"}` | Saves a fact; `entities` and `relations` (`[a, rel, b]`) are optional hints. |
| `POST /session` | `{"turns": [{"role", "text"}], "title", "url", "site", "model", "limit"}` | Saves or updates a whole chat, for hand-offs and context meters. |
| `POST /import` | `{"source", "text", "preview"}` | Imports another AI's memory export or an agent's memory file. `preview: true` shows what would be saved. |
| `DELETE /node/<id>` | none | Forgets a memory. It stays forgotten across rebuilds, even if the same words arrive again. |
| `POST /rebuild` | none | Re-derives the whole memory from the saved messages. |

Errors come back as JSON with an `error` field and a matching status: `400` for a bad request, `401` without a login or
token, `403` for something that token can't do, `404` for nothing there, `429` when a connector goes over its limit.

## Examples

```sh
# a briefing of what's relevant to a question
curl -H "Authorization: Bearer mb_xxxxxxxx" "http://192.168.1.20:3004/context?q=my+homelab"

# ask a question
curl -H "Authorization: Bearer mb_xxxxxxxx" "http://192.168.1.20:3004/recall?q=where+do+I+live"

# save a fact
curl -H "Authorization: Bearer mb_xxxxxxxx" -H "Content-Type: application/json" \
     -d '{"text": "I switched my home server to Debian 13"}' http://192.168.1.20:3004/remember

# pack up your latest chat for another AI
curl -H "Authorization: Bearer mb_xxxxxxxx" "http://192.168.1.20:3004/handoff"
```
