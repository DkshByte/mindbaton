# Mindbaton — design system: "Clean dark"

Chosen on 2026-09-22 over three bolder directions: the standard modern dark app, executed at the craft level
of **Linear** and **Vercel**. Convention is the commitment — no costume, no smuggled quirk. The direction contract is the
HTML comment at the top of `<body>` in `index.html` (seed b8503b2b).

**Brand:** the Mindbaton mark, app icons and favicons live in `assets/brand/` (the mark is a placeholder until the final
logo lands). Every icon is generated from `assets/brand/mark.svg` by one script (`make-icons.mjs`); UIs reference those
files and never inline a copy of the mark's paths.

## Colour
| token | value | job |
|---|---|---|
| `--bg` / `--side` | #09090b / #0c0c0e | page / sidebar |
| `--panel` `--panel-2` `--panel-3` | #111113 · #17171a · #1d1d21 | cards · hover · pressed/current |
| `--line` `--line-2` `--line-3` | white at 7% · 11% · 18% | hairlines, control borders, hover borders |
| `--fg` `--fg-2` `--fg-3` | #ededef · #a1a1aa · #71717a | text, secondary, tertiary |
| `--accent` (+ `-strong`, `-soft`, `-line`) | #8b95ff | **only** focus rings, selection, the answer card, the brand mark |
| `--ok` / `--danger` | #3dd68c / #ff6369 | live dot / forgetting |
| `--c-who … --c-other` | 11 hues | kind of fact (who, where, building, uses, has, learning, likes, dislikes, people, wants) — dots, map spokes and pills |
| `--t1 … --t12` | 12 hues | a topic's identity — its dot in lists, its map bubble |

Primary buttons are inverted (near-white on black), as Vercel does; there is no second accent.

## Type
**Geist** (sans, variable) for everything; **Geist Mono** for numbers, dates, ids and key hints. Both OFL, served from
`assets/fonts/`. Scale: 11.5 · 12.5 · 13 · 13.5 · 14 (body) · 15 · 16 · 19 · 24 · 30 (greeting). Headings 600, tracking
−0.01 to −0.025em; UI labels 500. Sentence case everywhere.

## Logos
Real brand marks are the only imagery. `fetch_assets.py` downloads them once into `assets/icons/` and writes
`index.json` (entity key or AI name → file, brand hex, mono/colour):
- **LobeHub icons** (MIT) for AI products — ChatGPT/OpenAI, Claude, Claude Code, Codex, Gemini, Perplexity, DeepSeek,
  Grok, Copilot, Mistral, Poe, Cursor, Ollama…
- **Simple Icons** (CC0) for everything else it has — Docker, Jellyfin, Python, Tailscale, Nvidia, Dell, Razorpay…
- **Devicon** (MIT) for what Simple Icons dropped — VS Code, Windows, Slack, AWS, Java, C++…
One-colour marks render as CSS masks tinted with the brand colour (or `--fg` when the brand colour is too dark for the
page); colour marks render as images. Model names map to their maker (RTX 3060 → Nvidia, ThinkPad → Lenovo). A thing
with no logo gets a small dot in its kind's colour; people get a round lettered avatar. Never draw a fake logo.

## Components
- **Shell:** 248px sidebar (mark + name + live dot, nav with hover keycaps 1-2-3, topics with colour dots, sources with
  AI logos, footer with last capture and Re-read all) · 56px top bar (page title, search with `/`, Copy briefing).
- **Card:** `--panel`, 1px `--line`, radius 10; header row 13.5/600 with a quiet hint on the right.
- **Chip:** pill, 28px, `--panel-2`, logo or dot + label + optional grey descriptor.
- **Row (entry):** 22px source-logo column · text (personal statements in `--fg`, questions/tasks in `--fg-2`) + meta
  line (kind, date, count, chat, topic) · mono date. Hover `--panel-2`; current `--accent-soft`.
- **Answer card:** accent-tinted gradient panel with a spark icon; the only accent-filled surface.
- **Detail panel:** 420px slide-over from the right (0.24s), close button, props list, related memories, danger zone
  with a two-step Forget.
- **Segmented control** for filters and the map's view switch.
- **Icons:** inline SVG, 1.6 stroke, round caps — never emoji or unicode glyphs.

### Chats (added 2026-09-23)
- **Chat row:** AI logo · title (one line) with a model chip, app, message count, topic dot, memory count · a context meter
  (64px, 4px, `--fg-2` fill, `--danger` at ≥80% or a hit limit) · mono date. The meter hides under 820px.
- **Model chip:** mono pill on `--panel-2` (`Opus 5 → Opus 5.5` when a chat switched models). Omitted when the app didn't
  say — rows never print "Unknown".
- **Said in:** a memory's sources, newest first, one line each (AI logo, chat title, model chip, date); a chat opens its panel.
- Nav: You `1` · Topics `2` · Chats `3` · Map `4`. Sidebar sources open Chats filtered to that AI.

## The map
Same engine as before, restyled: charcoal field with a soft glow of the centre's colour; kind pills are tinted rounded
pills; things carry their real logo inside a ring of their kind's colour; the centre shows your initial (or the thing's
logo). Labels are placed most-important first and never overlap. Motion: unfurl from the clicked point, flowing hovered
links, pulsing search hits, breathing centre — all off under reduced motion.

## Motion
150ms hovers, 240ms panel slide, a 0.4s rise for newly captured entries. Nothing else moves outside the map.

## Layout
Content column max 1120px, 40px side padding. Overview: two columns (profile by kind 1.55fr / recent + connect 1fr),
stacking under 1100px. Under 820px (the phone) the sidebar becomes a top nav strip, topics and sources hide, the page
scrolls and the detail panel takes the full width.
