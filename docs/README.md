# Mindbaton docs

Mindbaton is one private memory for ChatGPT, Claude, Gemini, Claude Code, Cursor and every other AI you use. It runs on
a computer you already own, and when a chat fills up it packs the chat so another AI can carry on.

## Start here

- [Getting started](getting-started.md): install it on Linux, macOS, Windows or Docker, and sign in the first time.
- [Connect your AIs](connect.md): the browser extension, coding agents, Claude Desktop, the Claude and ChatGPT apps, and your phone.

## Guides

- [Remote access](remote-access.md): reach Mindbaton away from home over HTTPS, without opening a port.
- [Configuration](configuration.md): every setting, the optional AI, Mindbaton's own model, and what's in the data folder.
- [Backup and upgrade](backup-and-upgrade.md): back up, restore, update, and move to another computer.
- [Troubleshooting](troubleshooting.md): what the common errors mean and how to fix them.

## Reference

- [API reference](api.md): the MCP tools and the HTTP API, for agents and scripts.
- [Security](../SECURITY.md): what Mindbaton protects, what it doesn't, and how to report a problem.
- [Changelog](../CHANGELOG.md): what changed in each version.

## Try it first

Want to look around before connecting anything? Start Mindbaton with a made-up person's memory:

```sh
MINDBATON_DATA=/tmp/mb-demo python3 demo.py --password demo-pass-123
MINDBATON_DATA=/tmp/mb-demo MINDBATON_PORT=3005 python3 server.py
```

Then open `http://localhost:3005` and sign in as `maya` with that password.
