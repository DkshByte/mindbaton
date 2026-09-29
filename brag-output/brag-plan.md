# Brag Plan: Mindbaton

## What is this app?
One private memory shared by every AI you use (ChatGPT, Claude, Gemini, Claude Code, Cursor…), running on a computer
you already own. Tell one AI, every AI knows; when a chat fills up, pass the baton and another AI keeps going.

## The angle
**The relay.** Mindbaton's mark is a relay baton drawn as a character: a capsule leaning 32° into the run, eyes
looking ahead. So the launch film *is* a relay: we follow one sentence that Maya (the project's made-up demo person)
tells one AI, and watch Baton carry it through the whole product (capture, memory, recall, the hand-off, forgetting)
until every AI knows it. The film is also the guide: six numbered chapters in the voice of the site's "owner's
manual", each one showing the real app doing its job with the real demo data.

## Hook (first 2–3 seconds)
A single chat box types "Hi! I'm Maya. I'm vegetarian, I live in Lisbon…", then splits into 4, 9, 16, 64 chat boxes,
one per real AI logo, all typing the same self-introduction. A wall of you, re-introducing yourself. Then every box
erases at once: *Every AI forgets you / the moment you open another one.*

## Key moments (the middle)
- Maya tells Gemini "I'm vegetarian." An amber highlighter marks the sentence; Baton snatches it and runs.
- It lands as memory #43, stamped `fact · Gemini · Gemini 3 Pro · "Portuguese café phrases"`; the amber counter
  ticks 0066 → 0067; "bytes sent off this box: 0".
- Messy typing becomes clean facts (the real `brain.py` output): "switched jobs, I'm at Stripe now" → *me · works at ·
  Stripe*.
- "I live in Porto for now." gets struck through; "I moved to Lisbon last weekend" replaces it. The old stays in history.
- "where do I live?" → **You live in Lisbon.** "what's my dog's name?" → *Nothing remembered about that yet.*
- The climax: Claude says "This conversation reached its maximum length." Hit the big BATON key, and a 607-token
  hand-off pack prints like a receipt. Baton grabs it and sprints from the Claude lane to the ChatGPT lane, and ChatGPT
  answers the question Claude never got to.

## Outro / punchline
`git clone … && ./install.sh`. Baton blinks. **Tell one AI. Every AI knows.** MINDBATON, free and open source.
"There is no box to buy. It's the computer you already own."

## User flow worth showing
1. Entry: say something to any AI (Gemini web chat, via the extension).
2. Key action: it becomes a memory (sorted, linked, kept up to date), and any AI asks it (search, Alt+M, MCP recall).
3. Result: a chat hits its limit, the baton passes, a different AI carries on.

## Tone
- Preset: `cinematic` (structure, big type, drops) with `polished` restraint in the UI shots
- Creative direction: "The relay: a launch film that follows one sentence from one AI to every AI, told as an
  owner's manual"
- Interpretation: confident and crafted like a Linear/Vercel launch, but warm and a little funny because the
  protagonist is a baton with eyes. Humour comes from the product's own premise (you re-introducing yourself to
  every AI; a receipt printer for your chat), never from gags. Every claim is the product's own copy or real
  output of the running app.

## Format: landscape — 3840x2160 (4K UHD), rendered from a 1920x1080 layout at 2× device pixels
## Duration: ~106 s. The user asked for a complete guide covering everything, which overrides brag's 15–25 s default.
Six short chapters keep it moving, and every line still meets the reading-time floor.

## Visual identity (from the project)
- Background: #0A0A0B (the logo's black) and #111110 (the app's `--bg`); pitch-black #000 plates from the site
- Text: #EEEEEC (app `--fg`), #B5B3AD (`--fg-2`), #F7F8FA (site silkscreen white)
- Accent: amber #FFB21A (site LEDs, seven-segment counter, highlighter); the app's warm aurora (vermilion, amber,
  rose, orange) as the only decorative light; green #3DD68C only for real "connected/live" states
- Display font: Archivo Variable at 125% width, 650–820 weight, uppercase (the site's silkscreen)
- Body font: Geist Variable (the app); Geist Mono / Fragment Mono for data, ids, tokens and commands
- Strongest visual elements: Baton (the mark, rebuilt as a rig: body, two eyes, lean, squash), the amber seven-segment
  counter, the glass BATON key, the receipt, the exploded view of the box, and the real app (You, Topics, Chats, Map,
  Search, Setup) captured from `server.py` running the `demo.py` data at 3× pixel density

## Nothing secret or personal
All people and chats are Maya Haddad's, from `demo.py`, which is entirely fictional. The one address on screen is the
repo's documented example `192.168.1.20:3004` (the capture ran on a loopback port, so that line was swapped). The
pasted key in the redaction beat is made up. Real product logos come from the repo's own `site/icons` and
`assets/icons` (LobeHub, Simple Icons, Devicon).

## Share copy (draft)
I kept re-introducing myself to every AI, so I built Mindbaton: one private memory that ChatGPT, Claude, Gemini,
Cursor and Claude Code all share, running on your own computer. Tell one AI. Every AI knows.

## Audio direction
- Role: an original score, written to picture, carrying the story (brag-slim: music and SFX written as one piece)
- Music: 120 BPM, D minor (Dm9 → Bbmaj9 → Fmaj7 → Cadd9), warm analog-style pads, sub bass, soft four-on-the-floor,
  plucked arpeggios. Built with Web Audio `OfflineAudioContext`, so every hit lands on its frame.
- Music treatment: hook = ticking keys over a rising cluster, then a hard silence at 7.6 s; reveal = the drop; chapters
  1–3 groove; chapter 4 filters down to a drone at "maximum length", the BATON key is the impact, and the relay sprint
  is the biggest drop; Forget is a breakdown; outro resolves and rings out
- Music cue guidance: bars are 2.0 s, so every scene cut sits on a bar line. Strong cues: 8.0 s (Baton lands),
  72.4 s (the relay sprint), 100.0 s (end card). LED sockets and kind cards use the beat grid (0.25 s); readable text
  never snaps faster than its reading floor
- Audio-reactive treatment: subtle. The aurora's brightness and Baton's glow breathe with the kick envelope. No
  waveform or equalizer visuals.
- SFX posture: moderate, motion-matched, pitched into the key: key ticks while typing, a scale-degree pluck per socket
  LED, a soft thud on landings, a dot-matrix chatter for the receipt, a glassy thunk for the BATON key, a reverse swell
  for Forget
- Restraint rule: no stock whooshes on every cut, nothing harsh or spiky, repeated ticks stay under the music

## Storyboard (120 BPM · 1 bar = 2.0 s)

### Scene 1 — The wall of you — 0.0–8.0 s
One chat composer types "Hi! I'm Maya. I'm vegetarian, I live in Lisbon…". At 1.8 s it splits (2×2 → 3×3 → 4×4 →
8×8), one real AI logo per box, all typing the same introduction while the camera pulls back. The wall dims. Two lines:
"Every AI forgets you" / "the moment you open another one." Every box backspaces to empty. Blackout at 7.6 s.
Sequential/interaction: yes, typing multiplied, then a synchronized erase
Audio intent: tension (ticking keys thicken into a swarm, a rising cluster), then silence
Transition mood: hard cut to black → Scene 2

### Scene 2 — Baton — 8.0–16.0 s
Baton drops in, squashes, blinks at camera, leans into its 32° running pose. "Tell one AI." / "Every AI knows."
Lockup: Baton + MINDBATON (silkscreen caps) + "One private memory for every AI you use."
Sequential/interaction: character animation; words land on beats
Audio intent: the drop, warm and wide; a soft bell as the wordmark lands
Transition mood: Baton sprints out right and the chapter card slides in behind it → Scene 3

### Scene 3 — 01 Capture — 16.0–30.0 s
Chapter card "01 · Capture — It listens." A Gemini chat ("Portuguese café phrases", Gemini 3 Pro): Maya types "I'm
vegetarian. what pastries are there besides pastel de nata?" and sends. An amber highlighter sweeps "I'm vegetarian.";
Baton snatches it. It lands in a memory window: "saved on this computer · memory #43", "fact · Gemini · Gemini 3 Pro ·
Portuguese café phrases", brain triple *me · is · vegetarian*, counter 0066 → 0067, 0 bytes sent. Then the sockets:
10 web AIs (browser extension) and 9 coding agents (MCP) light up one by one.
Sequential/interaction: typing, send, highlight, grab, LEDs lighting in sequence
Audio intent: groove starts; key ticks; each LED a note of the arpeggio
Transition mood: clean slide → Scene 4

### Scene 4 — 02 Remember — 30.0–48.0 s
Chapter card "02 · Remember — It sorts itself." The real You page: kind cards drop in one per beat. Caption: "What every
AI has told it about you, sorted by kind." Then "Reads the way you actually type": three messy lines resolve into real
brain triples. Then the real "What changed lately" card: a line strikes through "I live in Porto for now.", the Lisbon
line replaces it, and a caption says "It keeps up when things change. The old stays in history." Then three Pantry
chats from Claude Code and Cursor fly into one topic card: "Same subject, different apps: one topic." Push into the
real map: "All of it, on one map."
Sequential/interaction: card-by-card, strike-through draw, chats converging, camera push
Audio intent: groove continues, plucks on each card, a lift at the map
Transition mood: soft dolly → Scene 5

### Scene 5 — 03 Recall — 48.0–64.0 s
Chapter card "03 · Recall — Any AI can ask." Search types "where do I live?" and the real answer card lands: "You live
in Lisbon." Then "how do I take my coffee?" finds "I love specialty coffee, usually an oat flat white" (match:
meaning). Then "what's my dog's name?" gets the real No match card with Baton. Split screen: in ChatGPT, Alt + M
types the real briefing into the composer; in Claude Code, `recall("where do I live")` answers "You live in Lisbon."
Sequential/interaction: typing, answers popping, keycaps pressed, terminal output
Audio intent: bright, curious; a clean chime per answer
Transition mood: clean → Scene 6

### Scene 6 — 04 Baton — 64.0–80.0 s
Chapter card "04 · Baton — When a chat fills up, pass it on." The real Chats page spotlights "Running out of room".
Inside the Claude chat, messages stream, the context meter fills red, and "This conversation reached its maximum length.
Start a new chat to continue." appears. The glass BATON key rises; a cursor presses it; a receipt prints "Hand-off pack ·
607 tokens" with the real pack. Baton rips it off and sprints across lanes from Claude to ChatGPT. ChatGPT: "Sure.
Model membership as person ↔ household (many-to-many) instead of a single household per user." Caption: "Pass the
baton. Keep going."
Sequential/interaction: meter fill, key press, receipt printing line by line, the relay run, typed reply
Audio intent: filter closes into a drone, the key press lands on silence, dot-matrix chatter, then the biggest drop
Transition mood: dramatic whip → Scene 7

### Scene 7 — 05 Forget — 80.0–86.0 s
Chapter tag "05 · Forget". The real memory panel "I prefer dark mode in every app". Cursor → Forget → "Forget for
good?" → click. The memory dissolves; the counter goes 0067 → 0066; "Re-reading every saved chat…"; "Still gone."
Caption: "Forget in one click. It stays forgotten."
Audio intent: breakdown; a reverse swell into a soft dissolve
Transition mood: fade through black → Scene 8

### Scene 8 — 06 Yours — 86.0–96.0 s
Chapter tag "06 · Yours". The exploded view of the box (sockets, server.py, brain.py + handoff.py, memory.db, your
computer) closes into one folder: "One small Python program and one database file, on the computer you already own."
A white datasheet page slides up: no cloud, no account, no telemetry, 0 bytes sent, secrets become [secret],
everyone gets their own memory, bring your old memory, phone app, export JSON / Neo4j Cypher / GraphML, AGPL-3.0,
"Free. Box not included." Then Mindbaton's own model: 28/30 facts, 0 made up, 1.3 GB, offline.
Audio intent: groove returns, warm and steady
Transition mood: clean → Scene 9

### Scene 9 — Install + end card — 96.0–106.0 s
The terminal types `git clone https://github.com/DkshByte/mindbaton && cd mindbaton && ./install.sh`, and the
installer's nine real steps tick (Welcome → Done). End card: Baton blinks; "Tell one AI. Every AI knows."; MINDBATON;
"Free and open source · AGPL-3.0 · github.com/DkshByte/mindbaton". Fade out.
Audio intent: resolve to the home chord; a final bell; long reverb tail

**Music mood for this video:** cinematic-warm electronic
**Audio summary:** anxious ticking → silence → a warm drop that grooves through the guide, falls to a drone when the
chat runs out of room, explodes on the hand-off, and resolves on the end card.
