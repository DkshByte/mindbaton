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
| `GEMINI_KEY`, `GROQ_KEY` | *(none)* | Free keys for the optional AI. Easier: paste them on the Setup page, which tests and saves them to `ai_keys` in your data folder. |
| `OPENAI_KEY`, `ANTHROPIC_KEY` | *(none)* | Paid keys (OpenAI, Claude), used only after the free ones. Mindbaton reads these names only: an `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` set for another tool is left alone. |
| `MINDBATON_AI_MONTHLY_USD` | `2` | The most the paid keys may cost in a month, as Mindbaton counts it. At the limit they stop until next month; `0` never uses them. A limit set on the Setup page wins. |
| `MINDBATON_OPENAI_MODEL` | `gpt-6-luna` | OpenAI model. The default is its cheapest current one. A model picked on the Setup page wins. |
| `MINDBATON_CLAUDE_MODEL` | `claude-haiku-4-5` | Claude model. The default is its cheapest current one; `claude-sonnet-5-5` or `claude-opus-5-5` write better and cost 2 to 4 times as much. A model picked on the Setup page wins. |
| `MINDBATON_BRAIN` | `auto` | Mindbaton's own model (see below). Who reads is chosen on the Setup page (Accurate or Light); until someone chooses, `auto` = the model reads what the rules couldn't when this computer has 12 GB of memory or more; `on` = the same on any computer; `off` = never, whatever Setup says. |
| `MINDBATON_BRAIN_URL` | *(none)* | Use a model server elsewhere instead (a `llama-server` or LM Studio on your laptop, e.g. `http://192.168.1.20:8080`): nothing is downloaded here. |
| `MINDBATON_BRAIN_MODEL` | `1972521116s/mindbaton-brain-2b` | The Hugging Face repo the model comes from. |
| `MINDBATON_BRAIN_BATTERY` | `0` | `1` lets the model read while a laptop runs on battery. The **Only read while plugged in** switch on the Setup page does the same and wins once someone has set it. |
| `MINDBATON_WATCH_CLAUDE` | `1` | `0` stops Mindbaton reading Claude Code's chat history from `~/.claude/projects` on this computer. Docker sets `0` (there's nothing to read inside the container). |
| `MINDBATON_UPDATE_CHECK` | `1` | `0` stops the once-a-day check with GitHub for a newer release (the "update available" notice admins see). |

For the Claude Desktop bridge (`mcp_stdio.py`), set these in the Claude Desktop config, not in `mindbaton.env`:

| Variable | What it does |
|---|---|
| `MINDBATON_URL` | Your Mindbaton address, e.g. `http://192.168.1.20:3004` |
| `MINDBATON_TOKEN` | A device token from Settings → Devices |

## The optional AI

Everything Mindbaton understands — facts, topics, answers, redaction — comes from rules on your own computer. An AI is
only used, if you add a key, to *word* things more nicely: hand-off summaries, topic names and summaries, and
short answers on the search page (with the memories they came from).

- **Free keys:** [Google AI Studio](https://aistudio.google.com/apikey) (Gemini) or [Groq](https://console.groq.com/keys).
  **Paid keys:** [OpenAI](https://platform.openai.com/api-keys) or [Claude](https://platform.claude.com/settings/keys).
  Paste any of them on the Setup page (**AI keys**); each is tested before it's saved. **Remove key** takes one out again,
  and pasting a new key over an old one replaces it.
- **For the best results, use a paid key.** A paid key has no free-tier quota to run out of, and you can pick a
  stronger model for it. Add one and choose it under **Answer with** to have it answer first; left on the default it
  only steps in when the free keys can't answer.
- Unless you choose otherwise it tries Gemini, then Groq, then OpenAI, then Claude, and uses the first that answers.
- **Your choice.** On the same card an admin can pick which key answers first (**Answer with**), the model each paid
  key runs, and the monthly limit for paid keys. Putting a paid key first means every summary and answer you ask for is
  charged to it, still within the limit. The choices apply to everyone on the install and survive restarts.
- What leaves your computer: the text of the chat or memories that particular summary, name or answer is about — sent to
  that provider only.
- No key, or `MINDBATON_AI=0`: Mindbaton uses rule-made topic names and a plain extract as the hand-off pack.

### Paid keys: only when needed

A paid key is there for when the free ones can't answer, not to be spent freely:

- **Free first.** A paid key is tried only when no free key is saved, or the free providers are busy or over their quota.
- **The cheapest model** of each provider by default, on short prompts (a long chat is cut to about 30,000 tokens).
- **Nothing made ahead of time.** A hand-off summary is written on a paid key when you ask for the hand-off, never just
  because you opened a chat. Topic names, which nobody waits for, use a paid key at most once an hour.
- **A monthly limit.** Mindbaton adds up what each paid answer cost, from the tokens the provider reports, and stops
  using paid keys for the month at `MINDBATON_AI_MONTHLY_USD` (2 US dollars unless you change it). Setup shows the
  running total. The count is kept in `ai_usage.json`, so a restart doesn't reset it.
- **Answers are kept.** The same summary, name or answer is never paid for twice while Mindbaton runs, and topic names
  are stored for good.
- It is an estimate: prices change, and a model Mindbaton has no price for is counted as an expensive one, so the limit
  errs early. **Set a spending limit on the provider's site too**; that one is the real backstop.
- A Gemini key from a Google project with billing turned on is charged by Google, and Mindbaton does not count it. Use
  a key from a free project, or set a budget in Google Cloud.
- **Your keys, your bills.** What a provider charges for a key you add is between you and that provider. Mindbaton's
  limit and total are estimates, not a guarantee, and the project is not responsible for any charges: see the
  [Terms](https://dkshbyte.github.io/mindbaton/terms.html).

### Keeping keys safe

- A key is stored in `ai_keys` in your data folder, readable only by your user. It is never sent back to a browser,
  never written to a log, and never leaves the computer except to its own provider.
- Make a key just for Mindbaton, so you can revoke it without touching anything else. If the provider lets you
  restrict what a key can do or how much it can spend, do it.
- Pasting a key into Setup over plain `http://` on a network you don't control lets others on that network read it.
  Use HTTPS (see [Remote access](remote-access.md)), or put the key in `mindbaton.env` on the server instead.
- If a key leaks, revoke it on the provider's site first, then use **Remove key** and paste a new one.

## Mindbaton's own model

Rules read most of what you tell your AIs. For the rest (the way people really type: "5-a-side football every thursday",
"zero caffeine since march") Mindbaton has its own small model: Qwen3.5-2B fine-tuned on made-up examples only, 1.3 GB.

- An admin chooses who reads on the Setup page, for everyone on the install:
  - **Accurate**: the model is the main reader. It reads every message typed in a chat, and the rules check each fact.
    On sentences it never saw, with wording no rule was written for, this caught 56 of 60 facts.
  - **Light**: the rules read alone. Nothing is downloaded and nothing runs in the background. On the same sentences
    the rules caught 33 of 60.
  - Until someone chooses, it works as before: on a computer with 12 GB of memory or more the model turns on by itself
    and reads only the messages the rules found nothing in.
- Choosing Accurate covers new messages from then on. **Re-read everything** on the same page has the model read the
  older ones too.
- The first time, it downloads the model and the llama.cpp engine (about 1.3 GB, once) into `brain/` in your data folder.
- It reads one message at a time, at low priority on half the processor, and shuts the engine down after 5 idle
  minutes. It uses about 1.5 GB of memory while reading.
- On a laptop it waits for the charger. **Only read while plugged in** (Setup, on by default) is the switch: an admin can
  turn it off after a warning, and the model then reads on battery too, which drains it faster.
- Everything stays on your computer. The rules check every fact it reads (the words must be in your message, never from
  a question or a "maybe") before it's saved, and what it read is kept, so it never reads the same message twice.
- Mindbaton on a small server, but a laptop with memory to spare? Run `llama-server` on the laptop and set
  `MINDBATON_BRAIN_URL` on the server; it reads whenever the laptop is on.

## What's in the data folder

| File | What it is |
|---|---|
| `mindbaton.db` | Everything: every message as it arrived (secrets removed), and the memory graph built from it. |
| `ai_keys` | Optional AI keys (only readable by you). |
| `ai_usage.json` | What the paid AI keys cost this month, as Mindbaton counted it. |
| `access.log` | One line per request made with a connector token (the Claude and ChatGPT apps). |
| `brain/` | Mindbaton's own model and its engine, if this computer runs it (about 1.3 GB). Safe to delete; it downloads again. |

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
