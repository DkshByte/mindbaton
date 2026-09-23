# Contributing

Thanks for helping! Mindbaton is deliberately small and boring to run. A few rules keep it that way.

## Ground rules

- **Standard library only.** No pip packages, no framework, no build step, no CDN at runtime. The server is plain
  Python 3.9+ and SQLite; the app is one `index.html`; fonts, logos and scripts are vendored in `assets/`.
- **The laziest thing that actually works.** Shortest correct change, no speculative abstractions or options nobody
  asked for. But never cut security, validation, error handling that prevents data loss, or accessibility.
- **Rules decide, AI only words things.** Understanding (`brain.py`) and topics are deterministic and work offline.
  Improve them with general rules — never a one-off match for a single message.
- **No real personal data** in code, tests, issues or screenshots. Use `demo.py` (a made-up person) for screenshots and
  the synthetic messages in `bench.py` for tests.
- **Security is not optional.** Read [SECURITY.md](SECURITY.md) before touching auth, tokens, cookies or anything that
  handles a request.

## Getting set up

```sh
git clone https://github.com/DkshByte/mindbaton && cd mindbaton
python3 server.py --check                                             # self-test (rules, database, auth)
python3 bench.py                                                      # quality benchmark
MINDBATON_DATA=/tmp/mb-demo python3 demo.py --password demo-pass-123  # a made-up person's memory
MINDBATON_DATA=/tmp/mb-demo MINDBATON_PORT=3005 python3 server.py     # → http://localhost:3005
```

Editing `index.html` needs only a browser reload; changes to Python files need a restart.

## Before you open a pull request

1. `python3 server.py --check` passes.
2. `python3 bench.py` is **all green, holdout included**. If you changed how messages are understood, add the case to
   `bench.py` first (`PHRASINGS`, `QUERIES`, …), watch it fail, then fix the rule.
3. Changed `brain.py`? Bump `LOGIC_VERSION` in `server.py`, so existing installs rebuild their graph from saved
   messages on the next start.
4. Touched the app? Follow the design rules in [DESIGN.md](DESIGN.md) and [PRODUCT.md](PRODUCT.md) (Clean dark;
   Geist; real brand logos only — add one with `fetch_assets.py`, never draw a fake). Check keyboard use, focus rings,
   `prefers-reduced-motion` and a narrow phone screen.
5. `sh -n install.sh` (and `shellcheck install.sh` if you have it) if you changed the installer.

CI runs the self-test and the benchmark on Python 3.9 and 3.13 and builds the Docker image.

## Your own messages in the benchmark (optional)

If Mindbaton misreads *your* real messages, you can keep them as private test cases that never leave your computer:

- `data/private/bench_real.json` — same shape as `V1` in `bench.py`; `bench.py` adds a gate for it when it exists.
- `data/private/topics_gold.json` — a hand-labelled answer key for `python3 topics_check.py` (see its docstring).

`data/` is git-ignored. Never copy those messages into `bench.py` itself — write a made-up message that fails the same
way instead.

## More

Working rules for code agents (and humans who like details) are in [CLAUDE.md](CLAUDE.md).

By contributing you agree your contribution is licensed under the [AGPL-3.0](LICENSE), like the rest of Mindbaton.
