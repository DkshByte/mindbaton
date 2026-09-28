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
| `--bg` / `--side` | #09090b / #0c0c0e | page / sidebar (on desktop the sidebar is frosted glass: `--side` at 58%) |
| `--panel` `--panel-2` `--panel-3` | #111113 · #17171a · #1d1d21 | cards · hover · pressed/current |
| `--line` `--line-2` `--line-3` | white at 7% · 11% · 18% | hairlines, control borders, hover borders |
| `--fg` `--fg-2` `--fg-3` | #ededef · #a1a1aa · #71717a | text, secondary, tertiary |
| `--accent` (+ `-strong`, `-soft`, `-line`) | #8b95ff | **only** focus rings, selection, the answer card, the brand mark |
| `--ok` / `--danger` | #3dd68c / #ff6369 | live dot / forgetting |
| `--c-who … --c-other` | 11 hues (Radix Colors dark, step 11) | kind of fact (who, where, building, uses, has, learning, likes, dislikes, people, wants) — icon tiles, map spokes and pills |
| `--t1 … --t12` | 12 hues (Radix Colors dark, step 11) | a topic's identity — its mark (initials tile), its map bubble |

Primary buttons are inverted (near-white on black), as Vercel does; there is no second accent.

## Type
**Geist** (sans, variable) for everything; **Geist Mono** for numbers, dates, ids and key hints. Both OFL, served from
`assets/fonts/`. Scale: 11.5 · 12.5 · 13 · 13.5 · 14 (body) · 15 · 16 · 19 · 24 · 30 (greeting). Headings 600, tracking
−0.01 to −0.025em; UI labels 500. Sentence case everywhere.

## Marks, not dots
Decorative coloured dots read as generated UI, so there are none. A **kind of fact** is its icon (person, pin, layers,
wrench, box, book, heart, blocked, people, star) in a `kic` tile tinted with its colour; chips inside a kind card are
plain pills (real logos and people's initials stay). A **topic** is its `tm` mark: a rounded tile of its colour with its
initial — two initials from 24px up, skipping small words ("Pantry onboarding flow" → PO), a person for About you.
The only dots left are status lights (Live, Connected, the Setup states), where a dot is the honest signal.

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
- Nav: You `1` · Topics `2` · Chats `3` · Map `4` · Setup `5`. Sidebar sources open Chats filtered to that AI.

### You and Chats (reworked 2026-09-28)
- **Hero:** greeting or title + a status line on the left, the page's own actions on the right (You: Ask your memory,
  Explore the map · Chats: Open the latest).
- **The aurora:** four soft radial glows in the colours of your most recently active topics rise from the top edge of
  the whole app, drift over 21–33 s, and fade out gradually over ~640px (a stepped vertical mask), with a 1px gradient
  line along the very top. It adapts to the page: opacity .55 on You, a .2 wash on Topics/Chats/Setup, off on the map,
  cross-fading over 1.4 s. A new memory brightens it for ~1.5 s anywhere — the app's heartbeat. Plain gradients moving
  by transform, no blur filters; still under reduced motion. It sits behind `.side` and `.main`, so re-renders never
  restart it.
- **Frosted chrome:** the sidebar (`rgba(12,12,14,.58)`, blur 28px) and the top bar (`rgba(9,9,11,.34)`, blur 24px) are
  glass over the aurora, so the colour carries through them instead of stopping at a black edge. The top bar sits at
  z-index 4 (over the page and its menu, under the detail panel). On the phone the sidebar drops its filter — a filter
  there would make it the containing block of the fixed tab bar.
- **Number tiles** (`kpis`): four clickable cells in one hairline-divided panel — a mono 26px number, a label, and a
  one-line note (green when something's new, red when chats are near their limit). Each goes somewhere: You → Topics,
  Map, Chats, Setup; Chats → sort by recent, longest, fullest.
- **You:** "What they know about you" is a masonry of kind cards (`columns: 3 290px`), each with its kind icon, count and chips on flat `--panel` — never a clipped scroll box. Below: Recently beside "Pick up where you left off"
  (the 3 latest chats as `pick` cards with their meter and hand-off buttons), then In your own words, then a dashed
  "Connect more AIs" strip to Setup.
- **Chats:** "Running out of room" (chats at ≥70% or at their limit) as red-tinted pick cards first — that's the moment
  to pass the baton. Then a bar with the AI filter, a find-by-title box (filters in place, keeps focus through live
  refreshes) and Recent / Longest / Fullest; the list is grouped Today / Yesterday / This week / This month / Earlier,
  and every row carries a visible **Hand off** button (icon only on the phone).

### Topics (reworked 2026-09-28)
- **Grid first:** one card per topic, 3 across (2 under 1100px, 1 on the phone), sorted Recent or Biggest. A card: topic dot
  with a soft ring · name (2 lines) · count · its lead line · AI logos, chats, last active. Flat `--panel`; hover lifts it and tints the border.
- **A topic's page:** All topics (back) · dot + 30px name · Rename / Merge… (not for About you or Loose ends) · a status
  line · the AI summary when one exists (never a rule line dressed up as one) · an action bar: continue the latest chat
  in another AI, and Copy topic briefing (primary) · entries split into What you've said / Notes & decisions / Open
  questions / Tasks (6 each, then "Show all") beside Chats and Things it's about.
- **Rename** is inline (Enter saves, Esc cancels, empty = automatic name); **merge** is a sheet listing the other topics.
  Both are stored per conversation in `meta` (`topic_renames`, `topic_merges`), so they outlive new chats and rebuilds.
- The sidebar marks the open topic; the Topics nav always returns to the grid.

### Buttons
Anything a person came to do is a visible button (`.btn sm`, primary for the one main action) — never grey text. Quiet
text buttons (`.btn-quiet`) are for maintenance only and use `--fg-2`, not `--fg-3`.

### Setup (reworked 2026-09-28)
- **Own-model panel first:** Mindbaton's own model is the headline feature, so it leads the page as a wide panel (brain icon
  tile, "Reads what the rules can't", a soft white corner glow on `--panel`, its live state on the right), a plain-language
  pitch, three measured stats in mono (28/30 facts, 0 made up, 1.3 GB — from the README's test, update both together), then
  what it's doing now, progress bars and the Re-read action. It refreshes in place every 4 s while it downloads or reads.
- **Bring your old memory** is the second featured panel (same `.feat` shell: icon tile, eyebrow, 19px title, AI logo stack,
  lead), with the import tool always open — no longer a card in Extras.
- **The bloom** (`bloom(from, box)`) is the one celebratory motion: a blurred conic gradient of the topic hues
  (`--t2 --t5 --t4 --t1 --t3 --t11`) spreads from the pressed button across its panel while turning, a sharper ring of the
  same colours leads it, and ~22 coloured motes drift off; all of it dissolves in ~3 s. It plays on "Re-read everything…"
  (before the sheet opens), when the re-read starts, and when an import is saved. Off under reduced motion. Nowhere else.
- Then two groups under section headers: **Essentials** (server, extension, coding agents) and **Extras** (phone, free AI,
  Claude/ChatGPT apps).
- **Cards, not rows:** each group is a row of clickable cards (3 across each, 1 on the phone). A card: tick circle (number for essentials, an icon for extras, a green check when working) · status on the
  right (green dot + "Connected / Running / On", or a hollow dot + "To do / Optional / Any time") · title · a two-line
  status. A 3px track along each card's bottom edge turns green when it works, so the row reads as progress.
- **One panel per group:** clicking a card opens its steps in a panel spanning the group (on a phone, right under that
  card); clicking again or ✕ closes it. Every panel's body stays in the page (only hidden), so forms keep what's typed.
  An unfinished essential opens by default; extras start closed.
- **Live:** while Setup is open it re-checks `/status` every 8 s and patches only the cards whose state changed. A piece
  that starts working pops its tick, drops its pulsing "Listening —" line and says so in a toast.
- **Coding agents:** one row of app chips (logo, name, green dot when connected) and one command panel for the chosen app —
  never a grid of every config at once.

## The map
Same engine as before, restyled: charcoal field with a soft glow of the centre's colour; kind pills are tinted rounded
pills; things carry their real logo inside a ring of their kind's colour; the centre shows your initial (or the thing's
logo). Labels are placed most-important first and never overlap. Motion: unfurl from the clicked point, flowing hovered
links, pulsing search hits, breathing centre — all off under reduced motion.

## Motion
150ms hovers, 240ms panel slide, a 0.4s rise for newly captured entries. Nothing else moves outside the map.

## Layout
Content column max 1120px, 40px side padding. You: kind cards in up to 3 columns, then Recently 1.45fr / pick-up 1fr,
stacking under 1100px. Under 820px (the phone) the sidebar becomes a top nav strip, topics and sources hide, the page
scrolls and the detail panel takes the full width.

## Not allowed (found in a vibe-coding review, 2026-09-28)
Colour washes or gradients inside cards and panels (surfaces are flat `--panel`; colour lives only in icons, marks and
logos), eyebrow labels above headings, hero-metric number tiles (numbers are one quiet line of links), sparklines
standing in for content, zero-offset glow halos, tilted stacks of tiles as illustration. The aurora behind the app is
the one decorative gradient, and it never sits inside a box.
