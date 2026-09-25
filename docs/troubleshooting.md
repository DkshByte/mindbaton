# Troubleshooting

First, look at the logs — Mindbaton says what's wrong there:

| Installed with | Logs |
|---|---|
| `install.sh` on Linux | `journalctl --user -u mindbaton -f` |
| `install.sh` on macOS | `tail -f ~/Library/Logs/mindbaton.log` |
| Docker | `docker compose logs -f mindbaton` |

And run the self-test in the mindbaton folder: `python3 server.py --check`.

## Installing

**"Your Python's SQLite has no FTS5"** — your Python was built without full-text search. Install Python from your
package manager, python.org or Homebrew, or use [Docker](getting-started.md#docker-nas-and-home-lab-boxes).

**"Mindbaton needs Python 3.9 or newer"** — update Python, or use Docker.

**"Mindbaton didn't answer on port 3004"** — something else may already use that port. Set another one in
`mindbaton.env` (`MINDBATON_PORT=3010`) and run `./install.sh` again.

**No systemd or launchd** (containers, WSL1, Alpine) — run `python3 server.py` yourself (in `tmux` or `screen` to keep
it alive), or use Docker.

## First run and logging in

**The page asks for a setup code** — that's the first-run protection. Get the code on the Mindbaton computer with
`python3 server.py --setup-code` (Docker: `docker compose exec mindbaton python3 server.py --setup-code`), or find the
`Setup code:` line in the logs.

**"Wrong or missing setup code"** — codes look like `4821-7730`. Copy it again with `--setup-code`; it changes after a
password reset.

**Forgot your password** — `python3 server.py --reset-password` on the Mindbaton computer, then open the link it prints.
Your memories and device tokens are kept. See [getting started](getting-started.md#forgot-your-password).

**"Too many attempts — try again in … s"** — after 5 wrong passwords Mindbaton makes you wait a minute (longer if it
keeps happening). Wait, then try again.

## Reaching it from other devices

**Works on the Mindbaton computer but not from my phone or laptop**

- `MINDBATON_HOST` must be `0.0.0.0` (the installer and Docker set this) — check `mindbaton.env`, then restart.
- A firewall may block the port. Ubuntu: `sudo ufw allow 3004/tcp`. macOS: allow Python in System Settings → Network →
  Firewall.
- Both devices need to be on the same network (guest Wi-Fi often isn't), or use [Tailscale](remote-access.md#tailscale).
- WSL2: other devices can't see into WSL by default — use Docker Desktop or Tailscale.

**The phone app won't install** — installing needs HTTPS. Use [Tailscale](remote-access.md#tailscale) and open the
`https://…ts.net` address.

## Connecting AIs

**An app says "401" or "login required"** — its token is missing, mistyped or revoked. Make a new one in Settings →
Devices and paste it in again. (For MCP, the header is exactly `Authorization: Bearer mb_…`.)

**The Setup page doesn't show a green tick** — ticks turn green once that app has actually used Mindbaton. Ask it
something that needs memory ("what do you know about me?") and reload the page.

**The browser extension can't connect** — check the address includes `http://` (or `https://`) and the port, e.g.
`http://192.168.1.20:3004`. Open that address in the same browser: if it doesn't load there, it's a network problem
(see above). If the approve tab says you're logged out, log in and approve again.

**Nothing is captured from a chat site** — reload the chat tab after installing or updating the extension. Sites
change their pages now and then; make sure you have the latest extension from `/mindbaton-extension.zip`.

**Claude or ChatGPT connector fails** — these need a public `https://` address (Tailscale Funnel or Cloudflare Tunnel),
a **connector** token, and the URL in the form `https://…/t/<token>/mcp`. Open `https://…/t/<token>/health` in a
browser: it should answer with `"ok": true`. Every connector request is logged in `access.log` in your data folder.

## Memory

**It remembered something wrong** — open it and press **Forget**. It stays forgotten, even if the same message is
read again.

**Topics or facts look off after an upgrade** — press **Re-read all** in the sidebar: Mindbaton rebuilds everything from
your saved messages with the current rules.

**Still stuck?** Open an issue at <https://github.com/DkshByte/mindbaton/issues> with the log lines and what you
expected. Please don't paste your tokens, password or personal memories.
