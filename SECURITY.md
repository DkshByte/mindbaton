# Security

Mindbaton holds what you tell your AIs — often personal. This page says what it protects, what it doesn't, and how to
report a problem.

## Reporting a vulnerability

Please report privately through GitHub: **Security → Report a vulnerability** on
<https://github.com/DkshByte/mindbaton/security>. Don't open a public issue for a security problem.

Include what you found, how to reproduce it, and the version (`/health` shows it). This is a small open-source project:
you'll get a reply as soon as we can, usually within a week, and credit in the release notes if you'd like it. Fixes go
to the latest version on `main`.

## Model

**One owner per install.** Each person runs their own Mindbaton on their own hardware. There are no user accounts,
no cloud service and no telemetry.

**Who is the owner.** Whoever set the password on first run — and anyone with a shell on the Mindbaton computer (they
can run `python3 server.py --reset-password`, and they can read the data folder anyway).

### What Mindbaton protects

- **Nothing without a login.** Apart from the app's own files, `/health`, login and pairing, every endpoint needs the
  owner's session or a device token; otherwise it answers `401`.
- **First run can't be hijacked.** Until a password is set, setting one needs a one-time setup code that is only printed
  on the Mindbaton computer (terminal, logs, `--setup-code`). Only a browser on that computer itself (loopback, with no
  proxy in between) can skip it.
- **Passwords** are stored as scrypt hashes (n=2¹⁴, r=8, p=1, random salt), at least 8 characters. Login is throttled
  per address (5 failures → a 60 s lockout, doubling up to 15 minutes) and overall.
- **Sessions** are random 32-byte values stored only as SHA-256 hashes, sent in an `HttpOnly`, `SameSite=Lax` cookie
  (`Secure` over HTTPS), expiring after 30 days without use. Changing the password signs out every other session.
- **Device tokens** (`mb_…`) are stored only as SHA-256 hashes, shown once, named, and revocable one by one in Settings →
  Devices. Pairing a new device needs the owner to approve it in the app.
- **Connector tokens** — the kind used by the Claude and ChatGPT apps over the internet — cannot forget or export, are
  rate-limited, and every request is logged to `access.log` (without the token).
- **No cross-site access.** Requests from other websites' pages are refused, so a site you visit can't read or change
  your memory through your browser. Pages are sent with a strict Content-Security-Policy, `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`.
- **Secrets stay out of memory.** API keys, passwords and similar strings in your messages are redacted before anything
  is stored. This is pattern-based and best-effort — don't rely on it as a vault.
- **Files.** The data folder is created readable only by your user; `ai_keys` and `access.log` are `0600`.

### What it doesn't protect against

- **Plain HTTP on a network you don't trust.** On your home network Mindbaton speaks plain `http://`; anyone who can
  watch that traffic could see your password or tokens. Away from home, use HTTPS (Tailscale, Cloudflare Tunnel or a
  reverse proxy — see [remote access](docs/remote-access.md)). Never forward the port on your router.
- **Someone with access to the computer or its disk.** The database is not encrypted at rest. Use full-disk
  encryption and keep backups private.
- **The AIs you connect.** An AI with a token can read what it recalls, and a full token can change and forget memories.
  Give each app its own token and revoke the ones you stop using.
- **The optional AI provider.** If you add a Gemini or Groq key, the text needed for a summary, topic name or search
  answer is sent to that provider.
- **What you type into AI sites.** The browser extension reads what you send on supported AI chat sites — that's its
  job. Install it only from your own Mindbaton.
- **Prompt injection.** Memories are text that AIs read. A web page or document you paste into a chat could contain
  instructions aimed at an AI; Mindbaton stores what you send, it can't tell good instructions from bad ones.

## For contributors

Never weaken the rules above to make something easier. New endpoints are authenticated by default; anything that
reads request bodies does so before taking the graph lock; nothing logs a token, password or key. Run
`python3 server.py --check` — it includes the auth tests.
