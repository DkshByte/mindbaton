# Changelog

## Unreleased

- **Pick your gradient.** Settings → Appearance (also Gradient in the account menu and the command palette) shows the
  theme and the glow behind the app as cards with live previews: 17 presets (most from uiGradients), Auto, which
  follows the time of day (Dawn, Day, Golden hour, Dusk, Night), and None. The new gradient spreads out from the card
  you press. It's remembered on this device and applied before the first paint.
- **Smooth gradients.** No more visible rims under each glow, bands in the fade, or a strip under the top bar: the
  glows fade on an eased curve, a faint grain hides 8-bit steps, and the top bar is clear until you scroll.
- **UI fixes from an audit.** The sidebar wordmark no longer has a stray mark over its "i"; the nav reads You · Topics
  · Chats · Map · Setup, matching keys 1–5; the Topics count includes Loose ends like the Topics page does; panels say
  what a related memory is and when, not its row number; a failed model download says so in words (the raw error on
  hover); search snippets start and end on whole words. On a phone: a new page opens at its top, the map's legend is a
  strip along the bottom so the map uses the full width, the search hint is never cut mid-word, and header lines no
  longer start with a stray dot. "Bring your old memory" in the command palette brings that card to the front.
- **Understands meaning, not just words.** A built-in table of word meanings (Model2Vec potion-base-8M, 7.7 MB, plain
  Python, offline) finds "I love cricket" for "what do I do for fun?" and links memories about one subject in other
  words. Questions asked in other words: 15/23 → 23/23 on the benchmark; 11/11 for a new person it was never tuned on.
- **Keeps up when things change.** A dislike replaces the like, buying what you wanted closes the wish, a move you
  made ends the plan, giving something up ends it, and switching tools retires the old one of the same kind.
  Changing facts: 6/17 → 17/17. The history stays: "where did I live before?" has an answer.
- **One person, one name.** "my wife" becomes Sarah once you say her name; renamed projects keep one history and the
  old name still finds them; "he works at Amazon now" knows who "he" is from earlier in the chat.
- **Says when it doesn't know.** Questions about things you never mentioned ("what's my blood type?") get nothing
  instead of look-alikes, and "what's my favourite colour?" no longer lists everything you like.
- **Reads the way people actually type.** "switched jobs, I'm at Stripe now", "not a coffee person tbh", "bought the
  e-bike yesterday!": a small learner in plain Python (trained on made-up examples, some written by an open model,
  never on your messages) reads what no rule covers, only when it's sure. Everyday phrasings: 2/30 → 29/30 on the
  benchmark; on sets it never saw, 17/30 and 14/30, with no made-up facts.
- **Mindbaton's own model.** Qwen3.5-2B fine-tuned on made-up examples, run by a downloaded llama.cpp at low priority,
  reads in the background the messages the rules found nothing in; the rules check every fact before it's saved. On in
  `auto` with 12 GB of memory or more; `MINDBATON_BRAIN_URL` uses a model server on another computer. Unseen everyday
  sentences: 28/30 facts, no made-up facts (the rules and learner alone: 14/30).
- Search results say how they matched (a direct answer, a thing you named, your words, or meaning only).
- **`mindbaton update`** from any folder, like `claude update`: the installer and the updater add a `mindbaton` command
  (`mindbaton doctor`, `mindbaton keys`, … too); uninstall removes it.
- **Hand-offs carry the chat only.** "About me" is left out unless you tick **New AI? Include what Mindbaton knows
  about me** (app and extension 5.1.0), or an AI asks for it (`handoff` tool, `about: true`).
- Everything Mindbaton knows now shows in briefings: what you play and do, and "a data analyst at Deloitte" keeps its
  company. A day or a month is never taken as a thing ("play every sunday").
- The memory is rebuilt once on update (logic version 18).

## 0.1.3

- Automatic updates, opt-in, every night. Each update is tested; a version that fails is rolled back and skipped until
  a newer release. Installer: `python3 mindbaton.py autoupdate on`. Docker: `scripts/auto-update.ps1 -Install`
  (Windows, Task Scheduler) or `sh scripts/auto-update.sh --install` (Linux, macOS, NAS: cron).
- Uninstall also removes the nightly update job.

## 0.1.2

- "Update available" notice for admins: the server checks GitHub once a day and the app shows what's new and the exact
  command for how Mindbaton is installed (Docker or the installer). Turn it off with `MINDBATON_UPDATE_CHECK=0`.
- Docker: `compose.yaml` uses the published image, so updating is `docker compose pull` then `docker compose up -d`.

## 0.1.1

- Browser extension 5.0.1: you can type in the Connect page's address box again (every key was being cancelled).
- Update: if a new version fails its self-test, Mindbaton goes back to the version you had.
- Landing page: the exploded view shows its plates in Firefox.

## 0.1.0

First public release.

- One private memory for ChatGPT, Claude, Gemini, Perplexity, DeepSeek, Grok, Copilot, Poe and Mistral (browser
  extension) and Claude Code, Codex, Cursor, Windsurf, VS Code, Gemini CLI, Antigravity, Cline, Zed, OpenCode and Claude
  Desktop (MCP).
- Whole chats with the model and context meter; hand-off packs another AI continues from.
- Multiple local accounts, each with its own separate memory; admin controls; device tokens and pairing by code.
- Import your old memory: a ready-made prompt for web chatbots, and coding agents' memory files on connect.
- Full-screen terminal installer: this computer, your server, or link to an existing Mindbaton on your network.
- Browser extension connects to any Mindbaton by pairing code (no built-in addresses).
- Works offline; optional free Gemini or Groq key for summaries and answers.
- Web app works on phones (bottom tab bar) and installs as an app.
- Privacy policy and terms on the website.
