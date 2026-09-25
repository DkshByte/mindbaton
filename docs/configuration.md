# Configuration

Mindbaton works with no configuration at all. When you want to change something, put `NAME=value` lines in
**`mindbaton.env`** next to `server.py` (the installer creates one; `mindbaton.env.example` lists everything) and
restart Mindbaton. Real environment variables win over the file. With Docker, use a `mindbaton.env` next to
`compose.yaml`, or `-e NAME=value` with `docker run`.

## Settings

| Variable | Default | What it does |
|---|---|---|
| `MINDBATON_HOST` | `127.0.0.1` | Address to listen on. `127.0.0.1` = only this computer; `0.0.0.0` = every device on your network. The installer and Docker use `0.0.0.0`. |
| `MINDBATON_PORT` | `3004` | Port to listen on. (Docker: leave it, and change the left side of the port mapping instead.) |
| `MINDBATON_DATA` | `data/` next to `server.py` | Folder for your data. Docker uses `/data` (the volume). |
| `MINDBATON_PUBLIC_URL` | *(none)* | Your HTTPS address, e.g. `https://mindbaton.example.com`, used in the Setup page's copy-paste steps and for secure cookies. Without it, Mindbaton uses the address you opened it on. See [remote access](remote-access.md). |
| `MINDBATON_AI` | `1` | `0` turns the optional AI off completely, even if keys are saved. |
| `MINDBATON_AI_DAILY` | `400` | Most requests per day the optional AI may make. |
| `MINDBATON_AI_ASK_DAILY` | `200` | Most of those that search answers may use, so hand-offs always have some left. |
| `MINDBATON_GEMINI_MODEL` | `gemini-3.6-flash` | Gemini model for hand-off summaries. |
| `MINDBATON_GROQ_MODEL` | `openai/gpt-oss-120b` | Groq model, used when Gemini isn't available. |
| `GEMINI_KEY`, `GROQ_KEY` | *(none)* | Keys for the optional AI. Easier: paste them on the Setup page, which tests and saves them to `ai_keys` in your data folder. |
| `MINDBATON_WATCH_CLAUDE` | `1` | `0` stops Mindbaton reading Claude Code's chat history from `~/.claude/projects` on this computer. Docker sets `0` (there's nothing to read inside the container). |
| `MINDBATON_UPDATE_CHECK` | `1` | `0` stops the once-a-day check with GitHub for a newer release (the "update available" notice admins see). |

For the Claude Desktop bridge (`mcp_stdio.py`), set these in the Claude Desktop config, not in `mindbaton.env`:

| Variable | What it does |
|---|---|
| `MINDBATON_URL` | Your Mindbaton address, e.g. `http://192.168.1.20:3004` |
| `MINDBATON_TOKEN` | A device token from Settings → Devices |

## The optional AI

Everything Mindbaton understands — facts, topics, answers, redaction — comes from rules on your own computer. An AI is
only used, if you add a free key, to *word* things more nicely: hand-off summaries, topic names and summaries, and
short answers on the search page (with the memories they came from). It tries Gemini first, then Groq.

- Get a free key from [Google AI Studio](https://aistudio.google.com/apikey) or [Groq](https://console.groq.com/keys)
  and paste it on the Setup page.
- What leaves your computer: the text of the chat or memories that particular summary, name or answer is about — sent to
  that provider only.
- No key, or `MINDBATON_AI=0`: Mindbaton uses rule-made topic names and a plain extract as the hand-off pack.

## What's in the data folder

| File | What it is |
|---|---|
| `mindbaton.db` | Everything: every message as it arrived (secrets removed), and the memory graph built from it. |
| `ai_keys` | Optional AI keys (only readable by you). |
| `access.log` | One line per request made with a connector token (the Claude and ChatGPT apps). |

The folder is created readable only by you. Back it up — see [backup and upgrade](backup-and-upgrade.md).

## Command line

Run these in the Mindbaton folder (Docker: prefix with `docker compose exec mindbaton`):

| Command | What it does |
|---|---|
| `python3 server.py` | Run Mindbaton in the foreground. |
| `python3 server.py --check` | Self-test of the rules, the database and login. Exits with an error if anything is wrong. |
| `python3 server.py --setup-code` | Show the first-run setup code and link (only before a password is set). |
| `python3 server.py --reset-password` | Forgot your password: removes it and signs out every browser; memories and device tokens stay. Prints a new setup code. |
| `python3 bench.py` | The quality benchmark (for contributors). |
