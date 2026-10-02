# Mindbaton — design system: "Clean dark"

Chosen on 2026-09-22 over three bolder directions: the standard modern dark app, executed at the craft level
of **Linear** and **Vercel**. Convention is the commitment — no costume, no smuggled quirk. The direction contract is the
HTML comment at the top of `<body>` in `index.html` (seed b8503b2b).

**Brand:** the mark is **Baton** (final): a relay baton as a character, black and white, so the brand is monochrome and
the interface stays neutral around it. Mark, wordmark, app icons and favicons live in `assets/brand/`. Every icon is generated from `assets/brand/mark.svg` by one script (`make-icons.mjs`); UIs reference those
files and never inline a copy of the mark's paths.

## The model, live (Setup)
While Mindbaton's own model downloads, starts or reads, its panel becomes a live monitor (refreshes every 3 s): a
pulsing state ("Reading your messages"), the model's name, engine and computer; a progress bar; checked / total, time
left from its real speed, facts found (each checked by the rules), read this session; and two live graphs — processor
and memory — over the last two minutes. Downloading shows MB, measured speed and time left. Idle, it goes back to one
line of status. Graphs here are data, not decoration.

Above the stats, **Who reads what you type**: two option tiles that are real radios (arrows and Space work) — Accurate
(the model reads every message) and Light (the rules alone). Each says what it does, what it catches and what it
costs (the cost line in Geist Mono). The chosen tile is `--panel-2` with an `--accent-line` border and a filled check;
nothing is coloured. Until someone chooses, the one that fits this computer carries a "Recommended here" pill. Light
hides Re-read everything. Under the tiles, one checkbox, **Only read while plugged in** (on by default): unticking it
opens a sheet that says what reading on battery costs, with the safe answer as the primary button; ticking it back asks
nothing.

## The live card (sidebar)
A pill beside the wordmark (state dot + word) opens a card under it — one card instead of a "Live" dot: an honest state — **Live** (a radiating ring only while memories
arrive, the last 10 minutes; still otherwise), **Quiet** (amber, nothing for 2 days), **Reconnecting…** (a spinner) —
then the AI that sent the last memory and when, and 14 thin bars of memories per day with today in green, and an Open Setup button.
Never a green "Live" that isn't true.

## Baton in the product
The sidebar shows Baton beside the real wordmark lettering (both inlined at runtime from `assets/brand/`, so there is one
source and `currentColor` follows the theme). Baton **reacts**: it hops forward when a memory arrives and dims when the
server is offline. It appears where people pause: empty states, the "Baton passed" hand-off toast, the sign-in screen
(with "Tell one AI. Every AI knows."). Nowhere as decoration.

## Colour — "Graphite + vermilion" (2026-09-28)
Warm greys from Radix **sand** with one **tomato** (vermilion) signature. Chosen over violet and cyan, which design
write-ups list as the default AI-generated palette. Values are Radix Colors' own (dark scale).
| token | value | job |
|---|---|---|
| `--bg` / `--side` | #111110 / #141413 | page / sidebar (frosted over the aurora on desktop) |
| `--panel` `--panel-2` `--panel-3` | #191918 · #222221 · #2a2a28 (sand 2–4) | cards · hover · pressed/current |
| `--line` `--line-2` `--line-3` | warm white at 7% · 11% · 19% | hairlines, control borders, hover borders |
| `--fg` `--fg-2` `--fg-3` | #eeeeec · #b5b3ad · #908e87 | text, secondary, tertiary (all ≥4.5:1 on the panels) |
| `--brand` / `--brand-ink` | warm white #eeeeec / #111110 (Light: ink #21201c / white) | primary buttons — neutral; no colour on what you touch |
| `--accent` / `--accent-strong` | warm white (Light: ink) | focus rings, selection, the answer card, pressed chips — neutral since 2026-09-28: vermilion on buttons read badly |
| `--ok` / `--danger` | #3dd68c / #ff8fa3 (crimson, kept apart from the signature) | live dot / forgetting |
| `--c-who … --c-other` | 11 hues (Radix dark, step 11) | kind of fact — icon tiles, kind titles, map spokes and pills |
| `--t1 … --t12` | 12 hues (Radix dark, step 11) | a topic's identity — its mark, its map bubble |

**Themes** (account menu → Theme, remembered per device, applied before first paint): **Dark** (the table above),
**Light** (Radix light sand + tomato: bg #f9f9f8, panels #fdfdfc/#f1f0ef/#e9e8e6, ink #21201c/#63635e/#6f6e68, the
category colours at their light step 11; the aurora multiplies at low opacity; pale brand marks turn to ink),
**OLED** (bg and chrome #000 — the sidebar solid, no glow through it — panels #0d0d0c/#161615/#1e1e1c, hairlines a touch
brighter so cards never vanish). The signature, marks and layout are the same in every theme.

No category colour may equal the signature (Dislikes is crimson, topic 10 is sky). The aurora is warm: vermilion,
amber, rose, orange.

## Type
**Geist** (sans, variable) for everything; **Geist Mono** for numbers, dates, ids and key hints. Both OFL, served from
`assets/fonts/`. Scale: 11.5 · 12 · 12.5 · 13 · 13.5 · 14 (body) · 15 · 16 · 19 · 24 · 30 (greeting). Nothing you read is under 11.5px; the only
smaller letters are the initials inside marks (`tm`, `letter`), which are marks, not text. Headings 600, tracking
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
  the whole app, drift, and fade out gradually over ~640px (a stepped vertical mask), with a 1px gradient
  line along the very top. It adapts to the page: opacity .55 on You, a .2 wash on Topics/Chats/Setup, off on the map,
  cross-fading over 1.4 s. A new memory brightens it for ~1.5 s anywhere — the app's heartbeat. Since 2026-10-02 it is built like the website's: the four glows overlap unevenly as one
  light (first colour the core, the last far right) over a deep wash of the third, mixed in OKLab; each drifts on four
  sine waves of unrelated lengths, so it never stops, ping-pongs or repeats; it is dimmest at the very top, where the
  bar's small text sits, and brightest just under it. Mindbaton's own preset (Vermilion) is the website's coral,
  crimson, rose and cold night. Plain gradients moving
  by transform, no blur filters; still under reduced motion. It sits behind `.side` and `.main`, so re-renders never
  restart it.
- **Seamless chrome:** the glow runs unbroken behind the sidebar and top bar. On desktop the top bar is clear (the
  page scrolls below it, never under it) and shows its hairline only once the page is scrolled; the sidebar is a light
  tint (`rgba(20,20,19,.22)`) with no blur or saturation, which shifted the colours at its edge. Every glow fades on an
  eased curve that reaches zero flat, the vertical fade has eight stops, and a 5% grain sits over the aurora, so no
  rim, band or 8-bit step shows. On the phone the top bar is frosted again, since the page scrolls under it.
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

### You, quieter (2026-10-02)
The home screen shows one thing at a time. The hero is the greeting and its two lines, with no buttons (search is the
top bar, the map is in the nav). The numbers are one quiet line of links with no notes and no rules above or below.
"What they know about you" is a bento: twelve columns, 14px gaps, 16px tiles on flat `--panel`, in rows of two or
three that always fill (`bento()`), each tile as wide as what it holds. A tile is its kind before it is read: the
kind's own icon sits large and faint in its corner in its colour, the title is `--fg`, the chips are fills with no
outline. "Who you are" is set as type (the first fact at 24px), not chips. A tile's border catches the light near the
pointer (neutral, border only). Two columns under 1100px, one on the phone. Section headings carry no instructions.
A pick card on You offers one other AI and Copy hand-off (Chats has the full set). "In your own words" shows the eight
that matter most, then "Show all N". The dashed "Connect more AIs" strip appears only with fewer than three AIs. The
sidebar lists the six biggest topics, then "All N topics". Content column padding is 44/48/80px; sections sit 52px apart.

### Welcome: the first run (2026-10-02)
A person's first sign-in opens the welcome instead of the app, whatever is in their memory: full-screen moments in a
modal dialog, the aurora behind them as on the sign-in screen. **Hello** (one sentence, an honest "about two minutes",
three things that stay private, and the Terms and Privacy Policy to agree to) → **Pick a look** (the three theme
cards) → **Its own model** (the three measured stats and what it is doing on this computer) → **A free AI key**
(admins only, optional: get one, paste it, it's tested before it's saved) → **Connect your first AI** (browser or
coding agent; the chosen path's steps open in place) → **done**. One decision per screen; slim bars at the top say
where you are. The terms can't be skipped (no Skip, no Esc, only Sign out); everything after can. The server stamps the
account (`accounts.terms`, `accounts.welcomed`, set once through `PATCH /api/me`), so it shows once, on whichever
device comes first; accounts that had signed in before the upgrade are counted as done, and Setup's "Guided setup"
starts it again. The connect step ends by itself: typing the code the extension shows is the approval, then "Listening
for your first memory…", and the moment one arrives the last screen says "It remembered." and shows it, with the
bloom. Its one container per screen is a double bezel (a hairline tray, `--panel` inside with a smaller concentric
radius) and its primary button carries its arrow in a circle: the welcome is staged, the app stays flat. Steps enter
on `cubic-bezier(.32, .72, 0, 1)`, staggered; nothing moves under reduced motion.

### The extension (5.2.1, 2026-10-02)
The popup, its Connect tab and the bar it adds to chat pages follow this system: sand greys, Geist and Geist Mono
(bundled in `extension/fonts/`), flat `--panel` cards on hairlines, the website's light behind the top edge. A chat's
fullness is one 4px meter (`--fg-2`, `--danger` from 80%, as in the app) under a mono number; "Continue in" is a grid
of logo buttons; the Connect tab is a double bezel like the welcome, with the pairing code large in mono. The on-page
bar is one row, its Copy pack the primary. No emoji or glyph icons: ticks, arrows and the close are drawn.

### The other screens, quieter (2026-10-02)
Chats follows You: its numbers are one line with no notes (only "running out of room" keeps its red note, and only
when there is one), section headings carry no instructions, and the filter bar is two rows: which AI, then find on the
left and sort on the right. A chat row's Hand off is quiet (icon and label in `--fg-3`, no border) until the row is
hovered or focused, where there is a pointer to hover with; on touch it is always a full button. The map shows no
breadcrumb at its root, where the You / Topics switch already says where you are. Settings fields are at most 440px
wide. The detail panel names what it shows ("Claude chat", "Fact"), never a row number.

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
On a phone the legend is one scrolling strip along the bottom (Fit above it), so the map keeps the full width.

## Appearance (added 2026-09-29)
Settings → Appearance (account menu → Gradient, or the palette): **Theme** as three cards with a small app preview
each, and **Gradient** as a grid of cards (4 across, 2 on the phone), each a small live aurora of its four colours that
drifts on hover and while it's selected. Presets live in `GRADS` in the `<head>` script, so the chosen one (`mb-grad`,
per device, like the theme) is set on `:root` as `--a1…--a4` before the first paint; the sign-in screen follows it until
someone is picked. **Auto** follows the hour (`GRAD_AUTO`: Dawn Peach, Day Azur Lane, Golden hour, Dusk Relay, Night
Borealis) and shows the day as a strip with a tick at now; **None** hides the aurora. Picking one is a **reveal**:
the new aurora spreads from the card as a growing circle over the old one (1.1 s) while the glow comes up; off
under reduced motion. While Appearance is open the aurora is at full strength so you see what you pick. These
previews are the one place the aurora sits inside a box: they are samples of it, not decoration.

## Motion
150ms hovers, 240ms panel slide, a 0.4s rise for newly captured entries. Nothing else moves outside the map.

## Layout
Content column max 1120px, 40px side padding. You: kind cards in up to 3 columns, then Recently 1.45fr / pick-up 1fr,
stacking under 1100px. Under 820px (the phone) the sidebar becomes a top nav strip, topics and sources hide, the page
scrolls and the detail panel takes the full width.

## The website (`site/`, 2026-09-29)
The landing page follows this system instead of its own costume (the "box and its manual" page it replaced). Same tokens,
Geist and Geist Mono, flat `--panel` cards on hairlines, the app's `.btn`, chips, rows and segmented control, and the
aurora as the only decoration: one light behind the top edge that cools as it spreads (a coral core, crimson, rose, wine
underneath, a cold night glow on the far side; reds, not oranges, which turn brown when dimmed over the dark), mixed in
OKLab, with a faint film grain against banding. Each glow fades on an eased curve that reaches zero flat and drifts on
four sine waves of unrelated lengths, so it never stops, ping-pongs or repeats; it comes up once on load and rests off
screen. It is dimmest at the very top and brightest just under the top bar, and its strength is set so the small grey
text over it keeps 4.5:1 (measured at 1280, 768 and 390px; re-measure if the colours or strengths change). The top bar
is clear at the top of the page and frosts once the page scrolls under it. **For agents / For humans** is one ghost
button beside GitHub that names the other reading of the page (the Agent view is `site/llms.txt` itself, at `#agent`);
pressing it wipes the page down into plain text, and back up again. Not a segmented control: a dark box of two words
read as a setting and fought with Install. Under the install line the hero shows eight of the AIs it works with as
their real marks (six on a phone), linking to the full list. On phones every screenshot is the app's own phone screen
(`shots/app-*-m.webp`, 390×844 from `demo.py`), shown as a phone, never a shrunken desktop window. The page closes with
its one centred moment: the install command again, over the same light rising from behind the footer's line. Privacy
answers lead with their verdict in `--fg` ("None.", "Not needed."). The **404** is an eclipse where the 0 would be:
the aurora's five colours as a turning corona behind a black disc that slides across it on load, with one bright bead
on the rim that leans toward the pointer; the one place a glow surrounds a shape, because the shape is what hides it. Left-aligned: headline, lede, the
install command with Copy (primary), then a real screenshot of You. "How it works" is three steps, each beside one of the
app's components filled with the demo person (Recently rows, the answer card, a pick card and its real hand-off pack);
then the app's screens behind a segmented control, "Works with" as kind rows of chips, privacy as hairline rows,
install as a Script / Docker switch with numbered steps, questions, footer. Screens and data come from `demo.py`, never
invented. Privacy and terms (`legal.css`) are plain reading pages in the same palette. **Docs** (`site/docs/`, made by `docs_site.py`)
are laid out like the app: the sidebar of pages (current one on `--panel-3`), a 720px reading column (15.5px text in
`--fg-2`, headings in `--fg`), "On this page" on the right, code on the sidebar grey with its kind and a copy button,
flat callouts (a "Never" one gets the danger border), hairline tables, and search as a palette dialog (`/`, Ctrl/⌘K). No eyebrows, no metric tiles, no
feature-card grid, no gradients inside boxes. **Motion** shows the product working, never decoration: the hero relay (a fact typed
into one AI, the baton carries it into Mindbaton, another AI answers with it; the aurora pulses on each save), new
memories rising into Recently, the question typing itself and Porto struck through, the meter filling and the baton
hopping to the next AI; sections rise in once, the hero screenshot settles on scroll. Transform and opacity only, only
while on screen; under reduced motion each demo shows its finished state.

## Not allowed (found in a vibe-coding review, 2026-09-28)
Colour washes or gradients inside cards and panels (surfaces are flat `--panel`; colour lives only in icons, marks and
logos), eyebrow labels above headings, hero-metric number tiles (numbers are one quiet line of links), sparklines
standing in for content, zero-offset glow halos, tilted stacks of tiles as illustration. The aurora behind the app is
the one decorative gradient, and it never sits inside a box.
