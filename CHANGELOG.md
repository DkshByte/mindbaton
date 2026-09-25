# Changelog

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
