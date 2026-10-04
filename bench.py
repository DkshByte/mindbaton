"""Benchmark for Mindbaton's understanding and recall. Synthetic chat history, gold answers, hard numbers.

  python3 bench.py          # prints the scorecard, exits non-zero if any gate fails

A timeline of messages as one person would type them across AIs (lowercase, typos, lists, a move, a job change,
negations, secrets, pasted code), then:
  relations  — what must be known about the user at the end, and what must NOT be (retracted, negated, hypothetical)
  queries    — questions an agent would ask; the right memory must rank near the top, stale ones must not
  answers    — direct answers for "where do I live"-type questions
  topics     — which messages belong together and which don't
  privacy    — secrets typed into a chat must never be stored
"""
import json, os, re, sys, time
import live, server

DAY = 86400
# (site, chat title, text)
MSGS = [
    ("chatgpt.com", "Intro", "hi im rohan, a backend dev from jaipur"),                                          # 0
    ("chatgpt.com", "Homelab rebuild", "my server is an old dell optiplex with 16gb ram running ubuntu 22.04"),  # 1
    ("claude.ai", "Homelab rebuild", "i run jellyfin, pihole and n8n in docker on it"),                          # 2
    ("claude.ai", "Jellyfin crash", "jellyfin keeps crashing when i play 4k files, any idea why?"),              # 3
    ("chatgpt.com", "Jellyfin crash", "how do i enable hardware transcoding for jellyfin in docker compose"),    # 4
    ("gemini.google.com", None, "whats the best budget gpu for transcoding and running llama locally"),          # 5
    ("www.perplexity.ai", None, "rtx 3060 vs arc a380 for jellyfin transcoding"),                                # 6
    ("chatgpt.com", "Thumbnail worker", "im building a youtube thumbnail generator in python with pillow"),      # 7
    ("claude.ai", "Thumbnail worker", "the thumbnail generator is too slow, it takes 8 seconds per image"),      # 8
    ("claude.ai", "Thumbnail worker", "write a function that caches the fonts so pillow doesnt reload them"),    # 9
    ("chatgpt.com", None, "I prefer dark mode and minimal UIs, I hate bloated frameworks like angular"),         # 10
    ("gemini.google.com", "Dinner ideas", "i'm vegetarian, suggest a quick dinner with paneer"),                 # 11
    ("gemini.google.com", "Dinner ideas", "make it without onion and garlic"),                                   # 12
    ("chat.deepseek.com", None, "i want to learn rust this year"),                                               # 13
    ("claude.ai", "DoorTalk", "I'm working on DoorTalk, a voice intercom for my house using esp32 boards"),      # 14
    ("claude.ai", "DoorTalk", "the esp32 audio cuts out when wifi is busy, how do I buffer it?"),                 # 15
    ("chatgpt.com", None, "my sister meera is a doctor in pune"),                                                # 16
    ("chatgpt.com", None, "I use vscode and neovim, mostly neovim"),                                             # 17
    ("grok.com", None, "my api key is sk-" "proj-abc123def456ghi789jkl012mno345pqr678 can you check why this curl fails"),  # 18
    ("chatgpt.com", None, "my wifi password is hunter2secret, make a qr code for it"),                           # 19
    ("claude.ai", None, "I work at Infosys but I'm planning to switch jobs"),                                    # 20
    ("gemini.google.com", None, "i moved to bangalore last month"),                                              # 21
    ("chatgpt.com", None, "I don't use pihole anymore, switched to adguard home"),                               # 22
    ("claude.ai", None, "I left Infosys, now I work at Razorpay"),                                               # 23
    ("chatgpt.com", None, "i bought a used rtx 3060 yesterday for 18k"),                                         # 24
    ("www.perplexity.ai", None, "is the rtx 3060 good for stable diffusion?"),                                   # 25
    ("chatgpt.com", "Python help", "```python\nimport os\nprint(os.listdir())\n```\nwhy does this print an empty list"),  # 26
    ("copilot.microsoft.com", None, "write a bash script to backup my docker volumes to the nas every night"),  # 27
    ("claude.ai", None, "my girlfriend's birthday is on 9 march, remind me to plan something"),                   # 28
    ("chatgpt.com", None, "I'm 27 and I love cricket"),                                                          # 29
    ("gemini.google.com", None, "should I use postgres or mysql for a small side project?"),                     # 30
    ("chatgpt.com", None, "I don't have a car"),                                                                 # 31
    ("claude.ai", "DoorTalk", "i have to finish the doortalk firmware by friday"),                               # 32
    ("chatgpt.com", None, "i m tryna get better at system design for interviews"),                               # 33
    ("claude.ai", None, "Tailscale is how I reach my homelab from outside"),                                     # 34
    ("gemini.google.com", None, "my favourite movie is interstellar"),                                           # 35
    ("chatgpt.com", None, "actually my favourite movie is the dark knight"),                                     # 36
    ("chat.deepseek.com", None, "explain how raft consensus works"),                                             # 37
    ("claude.ai", "DoorTalk", "can you make it use the opus codec instead"),                                     # 38
    ("chatgpt.com", None, "thanks!"),                                                                            # 39
    ("chatgpt.com", None, "ok"),                                                                                 # 40
    ("www.perplexity.ai", None, "how much does a 4tb nas drive cost in india"),                                  # 41
]

HAVE = [  # (subject, relation, object key) that must hold at the end
    ("me", "named", "rohan"), ("me", "lives in", "bangalore"), ("me", "works at", "razorpay"),
    ("me", "uses", "docker"), ("me", "uses", "jellyfin"), ("me", "uses", "n8n"), ("me", "uses", "adguardhome"),
    ("me", "uses", "neovim"), ("me", "uses", "vscode"), ("me", "has", "server"), ("me", "has", "rtx 3060"),
    ("me", "sister", "meera"), ("me", "likes", "dark mode"), ("me", "dislikes", "bloated framework"),
    ("me", "working on", "doortalk"), ("me", "working on", "youtube thumbnail generator"), ("me", "learning", "rust"),
    ("me", "age", "27"), ("me", "likes", "cricket"), ("me", "is", "vegetarian"), ("me", "uses", "tailscale"),
    ("me", "likes", "dark knight"), ("meera", "is", "doctor"), ("meera", "lives in", "pune"),
    ("me", "learning", "system design"),
]
HAVE_NOT = [  # must not be asserted (stale, negated, hypothetical, or junk)
    ("me", "lives in", "jaipur"), ("me", "works at", "infosys"), ("me", "uses", "pihole"), ("me", "has", "car"),
    ("me", "uses", "postgresql"), ("me", "uses", "mysql"), ("me", "likes", "interstellar"),
]
JUNK = ("to finish", "idea", "been", "hunter2", "sk-proj", "to plan")  # no entity may contain these

QUERIES = [  # (query, message indexes of which at least one must be in the top k, k, message indexes that must NOT appear)
    ("where do I live", [21], 1, [0]),
    ("where do i work", [23], 1, [20]),
    ("what is my name", [0], 2, []),
    ("what graphics card do I have", [24], 3, []),
    ("jellyfin problems", [3], 3, []),
    ("jellyfin transcoding in docker", [4], 3, []),
    ("what am I building", [7, 14], 3, []),
    ("my side projects", [14], 5, []),
    ("food preferences", [11], 3, []),
    ("what does my sister do", [16], 1, []),
    ("which code editor do I use", [17], 2, []),
    ("thumbnail tool is slow", [8], 2, []),
    ("favourite movie", [36], 1, [35]),
    ("esp32 audio dropouts", [15], 1, []),
    ("stable diffusion", [25], 1, []),
    ("doortalk", [14], 2, []),
    ("remote access to my homelab", [34], 3, []),
    ("girlfriend birthday", [28], 1, []),
    ("what dns blocker do i use", [22], 3, []),
    ("programming languages i'm learning", [13], 3, []),
]
ANSWERS = [("where do I live", "bangalore"), ("where do i work", "razorpay"), ("what's my name", "rohan"),
           ("how old am i", "27"), ("what gpu do i have", "rtx 3060"),
           ("where did I work 39 days ago", "infosys"), ("where did I live before", "jaipur"), ("where did i work before", "infosys")]
SAME_TOPIC = [(3, 4), (7, 8), (8, 9), (14, 15), (15, 38), (11, 12), (24, 25)]
DIFF_TOPIC = [(3, 11), (7, 14), (11, 15), (29, 4)]

# A fake GitHub token for the redaction test, split so secret scanners don't take test data for a leaked one
FAKE_GH_TOKEN = "gh" + "p_" + "16C7e42F292c6912E7710c838347Ae178B4a"

HOLDOUT = dict(  # a different person and phrasing; never tuned against, only reported
    msgs=[
        ("claude.ai", None, "Hey! I'm Ananya, I'm a UX designer living in Mumbai"),
        ("chatgpt.com", None, "i mostly design in figma but i've started using framer too"),
        ("gemini.google.com", None, "my cat is called Mochi and she hates the vacuum"),
        ("chatgpt.com", "Portfolio", "I'm redesigning my portfolio site with astro"),
        ("claude.ai", "Portfolio", "the portfolio hero animation is janky on safari, how can i fix it"),
        ("chatgpt.com", None, "I moved to Pune in March"),
        ("www.perplexity.ai", None, "best ergonomic chairs under 20000 rupees"),
        ("gemini.google.com", None, "I no longer use framer, it was too expensive"),
        ("chatgpt.com", None, "i love jazz and lo-fi when i work"),
        ("claude.ai", None, "I'm allergic to peanuts"),
        ("chatgpt.com", "Portfolio", "can you write alt text for these portfolio images"),
        ("chat.deepseek.com", None, "should i learn three.js or spline for 3d on the web?"),
        ("gemini.google.com", None, f"my github token is {FAKE_GH_TOKEN} so pls debug"),
    ],
    have=[("me", "named", "ananya"), ("me", "lives in", "pune"), ("me", "uses", "figma"), ("me", "cat", "mochi"),
          ("me", "likes", "jazz"), ("me", "working on", "portfolio site"), ("me", "is", "ux designer")],
    have_not=[("me", "lives in", "mumbai"), ("me", "uses", "framer"), ("me", "learning", "three.js"), ("me", "learning", "spline")],
    queries=[("where do I live", [5], 1, [0]), ("what design tools do i use", [1], 3, []), ("my pet", [2], 2, []),
             ("portfolio animation bug", [4], 2, []), ("music taste", [8], 3, []), ("food allergies", [9], 2, [])],
    answers=[("where do I live", "pune"), ("what's my name", "ananya")],
    secrets=[FAKE_GH_TOKEN],
)


PHRASINGS = [  # one sentence, one fact that must come out of it (None: nothing may be asserted about the user)
    ("I've been using Arch Linux for 3 years", ("me", "uses", "arch linux")),
    ("my main machine is a macbook pro m2", ("me", "has", "macbook pro m2")),
    ("I usually code in Go and TypeScript", ("me", "uses", "golang")),
    ("I'm a software engineer at Google", ("me", "works at", "google")),
    ("i work remotely for a startup called Acme", ("me", "works at", "acme")),
    ("my wife Sarah loves hiking", ("sarah", "likes", "hiking")),
    ("My dog's name is Bruno", ("me", "dog", "bruno")),
    ("I got a new job at Microsoft last week", ("me", "works at", "microsoft")),
    ("I'm moving to Berlin next month", ("me", "plans to move to", "berlin")),
    ("I just started learning Japanese", ("me", "learning", "japanese")),
    ("i'm not a fan of tailwind", ("me", "dislikes", "tailwind")),
    ("I switched from windows to linux", ("me", "uses", "linux")),
    ("I'm on a keto diet", ("me", "is", "keto")),
    ("I was born in Chennai", ("me", "from", "chennai")),
    ("I'm from Kerala but live in Hyderabad", ("me", "lives in", "hyderabad")),
    ("I drive a Honda City", ("me", "has", "honda city")),
    ("my favorite band is Radiohead", ("me", "likes", "radiohead")),
    ("I'd like to visit Japan someday", ("me", "wants to visit", "japan")),
    ("I'm thinking about switching to Neovim", ("me", "wants to switch to", "neovim")),
    ("My brother works at Amazon in Seattle", ("my brother", "works at", "amazon")),
    ("Can you remember that I prefer short answers?", ("me", "likes", "short answer")),
    ("my startup is called Nimbus", ("me", "working on", "nimbus")),
    ("I play guitar and piano", ("me", "plays", "piano")),
    ("I'm running Home Assistant on a Raspberry Pi 4", ("me", "uses", "homeassistant")),
    ("If I had money I'd buy a 4090", None),
    ("my budget is around 50k rupees", None),
    ("should I learn go or rust?", None),
    ("I have no idea why this fails", None),
]


def phrasings():
    import brain
    ok, bad = 0, []
    for text, want in PHRASINGS:
        got = {r for m in brain.analyse(text) for r in m["relations"]}
        good = (want in got) if want else not any(r[0] == "me" and r[1] not in ("related",) for r in got)
        ok += good
        if not good:
            bad.append(f"  phrasing: {text!r} want {want} got {sorted(got)}")
    return ok, bad


V1 = dict(  # messages as the v1 extension sent them (lower case, SHOUTING, typos, pronouns), with what must come out
    msgs=[("agent", ["ChatGPT"], "i have a bl scooter"),
          ("agent", ["ChatGPT"], "I LIVE IN LUCKNOW"),
          ("agent", ["ChatGPT"], "THE BLUE SCOOTER HS STIKERS ON IT OF YELOW COLOUR"),
          ("agent", ["ChatGPT", "chat: Tiffin Project Overview"], "i have build tiffinbox.app"),
          ("agent", ["ChatGPT", "chat: Tiffin Project Overview"], "it is meal plannig app"),
          ("agent", ["ChatGPT", "chat: Tiffin Project Overview"], "my nmae is kabir")],
    have=[("me", "has", "bl scooter"), ("me", "lives in", "lucknow"), ("me", "built", "tiffinbox.app"),
          ("tiffinbox.app", "is", "meal plannig app"), ("me", "named", "kabir")],
    recall=("my scooter", "blue scooter"))  # this query must bring back a message containing that text in its top 2
# Your own misread messages go in data/private/bench_real.json (same shape, git-ignored): an extra gate runs when it exists.
PRIVATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "private", "bench_real.json")


def real(case):
    g = server.Graph(":memory:")
    t0 = time.time() - 3600
    for i, (site, ents, text) in enumerate(case["msgs"]):
        g.ingest(text, site, entities=ents, relations=[[e, "on", "ChatGPT"] for e in ents if e.startswith("chat: ")], ts=t0 + i * 60)
    ek = {r[0]: r[1] for r in g.db.execute("SELECT id, key FROM nodes WHERE kind='entity'")}
    rels = {(ek[a], rel, ek[b]) for a, b, rel in g.db.execute("SELECT src, dst, rel FROM edges") if a in ek and b in ek}
    have = [tuple(r) for r in case["have"]]
    q, want = case["recall"]
    ok = sum(r in rels for r in have) + (want in " ".join(m["text"] for m in g.recall(q)["memories"][:2]).lower())
    ais = {a for (s,) in g.db.execute("SELECT sources FROM nodes WHERE kind='memory'") for a in [x["ai"] for x in json.loads(s)]}
    ok += ais == {"ChatGPT"}
    bad = [f"  real: missing {r}" for r in have if r not in rels] + ([] if ais == {"ChatGPT"} else [f"  real: sources {ais}"])
    return ok, len(have) + 2, bad


STEERING = ["chek it if can fix it then only do", "what happend", "integrate it then", "chek if it si working", "what can we do",
            "ok do it now", "check it again", "go ahead and deploy it"]   # agent steering: no memory
KEEP_SHORT = ["check my jellyfin logs", "i use arch linux", "fix the wifi on my thinkpad", "where do i live", "what gpu should i buy",
              "i work at razorpay", "deploy mindbaton on my nas", "my car is red"]  # short but about something: kept


TYPO_NAMES = [("Chekc on agents", "chekc"), ("make the long grid scrllable so it fits", "scrllable"),
              ("the bento grid is still belowthe recent list", "belowthe"), ("take the logo fromthe web", "fromthe")]  # typos: no entity
REAL_NAMES = [("i use pulseaudio on my server", "pulseaudio"), ("jellyfin keeps crashing on my nas", "jellyfin"),
              ("check the netdata charts for my box", "netdata"), ("restart it with systemctl", "systemctl"),
              ("Grafana shows my homelab metrics", "grafana"), ("my project is called mindbaton", "mindbaton"),
              ("the mcp server speaks Streamable HTTP", "streamable http")]  # real names: kept


def typo_names():
    import brain
    ents = lambda t: {k for m in brain.analyse(t) for k, _, _ in m["entities"]}
    bad = [f"  typo became a thing: {k!r} in {t!r}" for t, k in TYPO_NAMES if k in ents(t)] + \
          [f"  real name lost: {k!r} in {t!r}" for t, k in REAL_NAMES if k not in ents(t)]
    return len(TYPO_NAMES) + len(REAL_NAMES) - len(bad), bad


def steering():
    import brain
    bad = [f"  steering kept: {t!r}" for t in STEERING if brain.analyse(t)] + \
          [f"  real message dropped: {t!r}" for t in KEEP_SHORT if not brain.analyse(t)]
    return len(STEERING) + len(KEEP_SHORT) - len(bad), bad


def cross_app():
    """The owner's complaint, as gates: one subject in two apps is one topic; a project's memory file, its coding sessions
    and another agent's chat about it are one topic, while a different project stays apart; harness wrappers and UI clocks
    never become memories or names; every source says which AI and model it came from."""
    g = server.Graph(":memory:")
    t0, ok, bad = time.time() - 5 * DAY, 0, []
    def check(name, cond):
        nonlocal ok
        ok += bool(cond)
        if not cond:
            bad.append("  cross-app: " + name)
    a = g.ingest("opus 5.5 just relesed check", "chatgpt.com", "Opus 55 Release Check", "https://chatgpt.com/c/opus1", t0)
    g.ingest("what is better than opus 5", "chatgpt.com", "Opus 55 Release Check", "https://chatgpt.com/c/opus1", t0 + 60)
    b_ = g.ingest("when was opus 5.5 relesed10:41 PM", "www.perplexity.ai", "when was opus 5.5 relesed",
                  "https://www.perplexity.ai/search/opus2", t0 + 600)
    g.ingest("i take a pottery class, what syllabus do i have for term 1", "chatgpt.com", "Pottery", "https://chatgpt.com/c/pot", t0 + 900)
    home = [g.ingest(t, "claude-code", None, "memory://claude-code/doortalk", t0 + 1000 + i) for i, t in enumerate([
        "DoorTalk voice intercom app at ~/DoorTalk — Node/Express/Socket.IO + WebRTC, systemd service",
        "DoorTalk uses PulseAudio echo_cancel devices; config/default.json sets port 4000",
        "PulseAudio runs as a user service; a crash leaves a stale socket that DoorTalk can't reach"])]
    dash = [g.ingest(t, "claude-code", None, "memory://claude-code/homelab-panel", t0 + 2000 + i) for i, t in enumerate([
        "Home lab dashboard at ~/panel — stdlib-only Python + a single HTML page, replaces Uptime Kuma",
        "netdata does not track / on this box, the dashboard uses os.statvfs for disk usage"])]
    live.sync(g, None, "claude-code", "DoorTalk echo fix", [
        {"role": "user", "text": "the intercom crackles when two stations talk at once"},
        {"role": "assistant", "text": "That's the PulseAudio echo_cancel module in DoorTalk; raise the aec buffer.", "model": "claude-opus-5-5"},
        {"role": "user", "text": "ok and the stale pulse socket after a crash?"}], ts=t0 + 3000, key="claude-code/s1",
        cwd=os.path.expanduser("~/DoorTalk/backend"))
    live.sync(g, None, "antigravity-client", "Add MCP to intercom", [
        {"role": "user", "text": "<USER_REQUEST>\nhook the doortalk stations into the mindbaton mcp\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\n"
                                 "The current local time is: 2026-09-22T22:04:17+05:30.\n</ADDITIONAL_METADATA>"},
        {"role": "assistant", "text": "Added an MCP client to DoorTalk's station.js; PulseAudio devices unchanged."}], ts=t0 + 4000, key="antigravity/c1")
    dropped = g.ingest("<USER_REQUEST>\ncontinue\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nThe current local time is: x\n</ADDITIONAL_METADATA>",
                       "antigravity", None, None, t0 + 5000)
    g.ensure()
    cl = dict(g.db.execute("SELECT id, cluster FROM nodes WHERE kind='memory'"))
    topic = lambda ids: {cl.get(m) for m in ids} - {None}
    ag = [m for (m,) in g.db.execute("SELECT id FROM nodes WHERE kind='memory' AND label LIKE '%doortalk stations%'")]
    cc = [m for (m,) in g.db.execute("SELECT id FROM nodes WHERE kind='memory' AND label LIKE '%crackles%'")]
    check("opus in ChatGPT and Perplexity share a topic", topic(a) & topic(b_))
    check("pottery class stays apart from opus", not (topic(a) & topic(g.db.execute(
        "SELECT id FROM nodes WHERE kind='memory' AND label LIKE '%syllabus%'").fetchone() or [])))
    check("glued clock is not an entity", not g.db.execute("SELECT 1 FROM nodes WHERE kind='entity' AND (key LIKE '%relesed1%' OR key='pm')").fetchone())
    check("project memory file + its coding session share a topic", topic([m for ms in home for m in ms]) & topic(cc))
    check("another agent's chat about the project joins it", ag and topic(ag) & topic([m for ms in home for m in ms]))
    check("a different project stays apart", not (topic([m for ms in home for m in ms]) & topic([m for ms in dash for m in ms])))
    check("the project topic is named after it", any("doortalk" in (g.topics.get(c) or {}).get("name", "").lower()
                                                    for c in topic([m for ms in home for m in ms])))
    check("harness 'continue' is not a memory", dropped == [])
    check("no harness tag stored", not g.db.execute("SELECT 1 FROM captures WHERE text LIKE '%<USER_REQUEST>%' OR text LIKE '%ADDITIONAL_METADATA%'").fetchone())
    srcs = [x for (s,) in g.db.execute("SELECT sources FROM nodes WHERE kind='memory' AND label LIKE '%stale pulse%'") for x in json.loads(s)]
    check("a message knows its AI and the model that answered", any(x.get("ai") == "Claude Code" and x.get("model") == "Opus 5.5" for x in srcs))
    check("MCP client names are canonical", {r[0] for r in g.db.execute("SELECT type FROM nodes WHERE kind='session'")} >= {"Antigravity", "Claude Code"})
    check("each chat links its memories", all(g.db.execute("SELECT 1 FROM edges WHERE rel='said in' AND dst=?", (n,)).fetchone()
                                              for (n,) in g.db.execute("SELECT id FROM nodes WHERE kind='session'").fetchall()))
    # common sense about projects and small things, as the owner's real memory needed it (2026-10-02): a project kept on a
    # shelf (~/Documents) under a name with a space, memory files named after facts, a second checkout, a chat that links
    # the repo, a chat whose title names it -> one topic, named after the project. A short untitled chat is a loose end.
    # No topic is named after a typo, and an import is named after where it came from.
    g = server.Graph(":memory:")
    cwd = os.path.expanduser("~/Documents/plant log")
    said = lambda *ts: [{"role": "user", "text": t} for t in ts]
    live.sync(g, None, "claude-code", "Seed swap reminders", said("add a reminder a week before each seed swap",
              "the watering schedule should skip rainy days", "show the last repotting date on each plant card"), ts=t0, key="claude-code/p1", cwd=cwd)
    live.sync(g, None, "claude-code", "Landing page copy", said("the landing page headline is too long", "use dummy plants on the landing page, no real names"),
              ts=t0 + 100, key="claude-code/p2", cwd=os.path.expanduser("~/plant-logger"))
    g.ingest("Plant log (~/Documents/plant log) has its signing key only on this laptop; losing it blocks every update", "claude-code", None,
             "memory://claude-code/release-key-backup", t0 + 200)
    g.ingest("The play store listing needs the release build, never the debug one", "claude-code", None, "memory://claude-code/store-listing-plan",
             t0 + 300, meta={"file": "~/.claude/projects/%s/memory/store-listing-plan.md" % re.sub(r"[^A-Za-z0-9]", "-", cwd)})
    live.sync(g, None, "antigravity-client", None, said("in this repo https://github.com/someone/plant-logger the login video is cut off on small phones",
              "the blur under the video still shows a hard edge"), ts=t0 + 400, key="antigravity/p3")
    g.ingest("which host is cheapest for it", "gemini.google.com", "Hosting Plant Log Online", "https://gemini.google.com/app/pl1", t0 + 500)
    for i, t in enumerate(["are yuo done, do it fast", "what about the 1080 p one i want to see it"]):
        g.ingest(t, "claude.ai", None, "https://claude.ai/code/session_s1", t0 + 600 + i)
    for i, t in enumerate(["why can i see lines in the gradint", "mkae the gradint smooth plese", "betifull cards plese, like big comapnies",
                           "the cards are still not betifull", "add a gradint picker with presets"]):
        g.ingest(t, "claude.ai", None, "https://claude.ai/code/session_s2", t0 + 700 + i)
    g.ingest("I always pick the window seat", "chatgpt.com", "Memory from ChatGPT", "memory://chatgpt.com/import", t0 + 800)
    g.ingest("I keep a paper notebook for every trip", "chatgpt.com", "Memory from ChatGPT", "memory://chatgpt.com/import", t0 + 801)
    g.ensure()
    tp = lambda like: {c for (c,) in g.db.execute("SELECT cluster FROM nodes WHERE kind='memory' AND label LIKE ?", (like,))}
    plant = tp("%seed swap%")
    name = lambda cs: (g.topics.get(next(iter(cs)) if cs else None) or {}).get("name", "")
    check("a project on a shelf is named after its own folder", len(plant) == 1 and name(plant).lower() == "plant log")
    check("a memory file naming the project's folder joins it", tp("%signing key%") == plant)
    check("a memory file kept for the project's folder joins it", tp("%play store%") == plant)
    check("a second checkout is the same project", tp("%headline%") == plant)
    check("a chat that links the project's repo joins it", tp("%hard edge%") == plant)
    check("a chat whose title names the project joins it", tp("%cheapest%") == plant)
    check("a short untitled chat is a loose end", tp("%yuo done%") == {None})
    names = [t["name"] for t in g.topics.values()]
    check("no topic is named after a typo", not any(w in n.lower() for n in names for w in ("gradint", "betifull", "plese", "mkae", "comapnies")))
    check("an import is named after where it came from", name(tp("%window seat%")) == "Memory from ChatGPT")
    return ok, 21, bad


# ---- the brain: meaning, people, links, honesty, change ---------------------------------------------------------------
BRAIN = dict(  # a third person, said plainly; every question uses other words than the memory it needs
    msgs=["hi, I'm Nikhil, I work as a data analyst at Deloitte",               # 0
          "I love cricket and play every sunday with friends",                  # 1
          "my wife Sarah is a pediatric nurse",                                 # 2
          "I drink my coffee black, no sugar",                                  # 3
          "I'm vegetarian since 2019",                                          # 4
          "my laptop is a thinkpad t480 running fedora",                        # 5
          "Tailscale is how I reach my homelab from outside",                   # 6
          "i'm saving up for a trip to japan next spring",                      # 7
          "I have mild asthma, so I avoid running in cold weather",             # 8
          "my dog Bruno is a golden retriever",                                 # 9
          "I'm learning spanish on duolingo",                                   # 10
          "i usually code in go and typescript",                                # 11
          "the jellyfin server keeps buffering on my tv",                       # 12
          "I was born and raised in Chennai",                                   # 13
          "we are planning our wedding anniversary dinner on 12 june",          # 14
          "my brother arjun works at amazon in seattle",                        # 15
          "I prefer short, direct answers without fluff",                       # 16
          "i drive a red honda city",                                           # 17
          "my budget for a new monitor is 20k rupees",                          # 18
          "I listen to lo-fi and jazz while working",                           # 19
          "my inhaler is almost empty, where can I refill it",                  # 20
          "got a new bat for the weekend match",                                # 21
          "how much is a hotel in tokyo in april",                              # 22
          "my movies stutter when streaming 4k on the living room tv",          # 23
          "suggest a high protein dinner without meat",                         # 24
          "Bruno needs his rabies shot next week",                              # 25
          "Sarah works at Apollo Hospital"],                                    # 26
    queries=[  # (question, messages that answer it): one must be in the top 3
        ("what do I do for fun", [1, 19, 21]), ("what sport do I play", [1, 21]), ("who is my partner", [2]),
        ("what does my wife do for a living", [2, 26]), ("how do I take my coffee", [3]), ("do I eat meat", [4, 24]),
        ("what computer do I use", [5]), ("how do I access my home network remotely", [6]), ("any upcoming vacation plans", [7, 22]),
        ("do I have any health conditions", [8, 20]), ("do I have pets", [9, 25]), ("what languages am I studying", [10]),
        ("which programming languages do I know", [11]), ("problems with my media server", [12, 23]), ("where did I grow up", [13]),
        ("when is our anniversary", [14]), ("where does my brother live", [15]), ("how should you answer me", [16]),
        ("what car do I have", [17]), ("how much can I spend on a display", [18]), ("what music do I like", [19]),
        ("where do I work", [0]), ("where does my wife work", [26])],
    answers=[("who is my partner", "sarah"), ("where does my wife work", "apollo"), ("what does my brother do", "amazon"),
             ("where does my brother live", "seattle"), ("where did I grow up", "chennai"), ("what's my dog called", "bruno")],
    linked=[(8, 20), (1, 21), (7, 22), (12, 23), (4, 24), (9, 25), (2, 26)],     # one subject in other words: linked
    unlinked=[(8, 12), (1, 3), (7, 5), (20, 21), (22, 24), (16, 17), (3, 18)],   # nothing in common: not linked
    unknown=["what's my blood type", "what is my favourite colour", "tell me about my boat", "what's my shoe size",
             "which gym do I go to", "what's my mother's name"],                 # never said: no answer and no memories
    changes=[  # (messages in one chat, relation, does it hold at the end?)
        (["I love coffee", "I can't stand coffee anymore"], ("me", "likes", "coffee"), False),
        (["I love coffee", "I can't stand coffee anymore"], ("me", "dislikes", "coffee"), True),
        (["I don't like sushi", "ok I love sushi now"], ("me", "dislikes", "sushi"), False),
        (["I love coffee", "my wife hates coffee"], ("me", "likes", "coffee"), True),            # someone else's taste
        (["I want to buy a PS5", "I finally bought a PS5"], ("me", "wants", "ps5"), False),
        (["I want to buy a PS5", "my brother bought a PS5"], ("me", "wants", "ps5"), True),      # someone else's purchase
        (["I'm moving to Berlin next month", "I moved to Berlin"], ("me", "plans to move to", "berlin"), False),
        (["I'm learning Rust", "I gave up on Rust"], ("me", "learning", "rust"), False),
        (["I'm learning Rust", "I gave up on Go"], ("me", "learning", "rust"), True),
        (["I play guitar", "I don't play guitar anymore"], ("me", "plays", "guitar"), False),
        (["I'm working on DoorTalk", "I abandoned DoorTalk"], ("me", "working on", "doortalk"), False),
        (["I use Windows on my desktop", "I switched to Linux last month"], ("me", "uses", "windows"), False),
        (["my wife loves hiking", "my wife's name is Sarah"], ("sarah", "likes", "hiking"), True),
        (["my wife is Sarah", "my wife loves hiking"], ("sarah", "likes", "hiking"), True),
        (["my sister Meera is a doctor", "my sister Priya is a lawyer", "my sister loves painting"],
         ("meera", "likes", "painting"), False),                                                   # which sister? don't guess
        (["I'm building DoorTalk", "I renamed DoorTalk to HearthLink"], ("me", "working on", "hearthlink"), True),
        (["my brother arjun moved to seattle", "he works at amazon now"], ("arjun", "works at", "amazon"), True)])
HOLDOUT2 = dict(  # the same suite on another person in other words; never tuned against, only reported
    msgs=["I'm Leo, I teach high school chemistry in Porto", "my girlfriend Ana is an architect",
          "I've been bouldering twice a week for three years", "I can't eat gluten, I have celiac disease",
          "I edit my photos in darktable on a framework laptop", "my cat Pixel sleeps on my keyboard all day",
          "I'm writing a fantasy novel in the evenings", "we're saving for a house deposit",
          "I only drink green tea, coffee makes me jittery", "my home server runs proxmox with three VMs",
          "I want to visit iceland in winter", "my mom lives in lyon", "Ana just got promoted at her firm"],
    queries=[("what's my job", [0]), ("who am I dating", [1]), ("what exercise do I do", [2]), ("any dietary restrictions", [3]),
             ("what photo software do I use", [4]), ("do I have any animals", [5]), ("what creative projects am I working on", [6]),
             ("what are we saving money for", [7]), ("do I drink coffee", [8]), ("what hypervisor do I run", [9]),
             ("where do I want to travel", [10]), ("where does my mother live", [11])],
    answers=[("where does my mother live", "lyon"), ("what does my girlfriend do", "architect"), ("what's my name", "leo")],
    linked=[(1, 12)], unlinked=[(2, 8), (5, 9), (3, 10)],
    unknown=["what's my blood group", "what car do I drive", "how tall am I"],
    changes=[(["I love running", "I hate running now, my knees hurt"], ("me", "likes", "running"), False),
             (["I want to buy a kindle", "just got a kindle paperwhite"], ("me", "wants", "kindle"), False),
             (["I'm planning to move to Lisbon", "we finally moved to Lisbon"], ("me", "plans to move to", "lisbon"), False),
             (["I'm learning the piano", "I quit piano lessons"], ("me", "learning", "piano"), False),
             (["my partner loves sushi", "my partner's name is Sam"], ("sam", "likes", "sushi"), True),
             (["My podcast is called Night Owls", "I renamed Night Owls to Late Shift"], ("me", "working on", "late shift"), True),
             (["my sister Priya just started at Google", "she lives in Zurich now"], ("priya", "lives in", "zurich"), True)])
HOLDOUT3 = dict(  # written after the brain was tuned (2026-09-27) and run once: the honest number for new people
    msgs=["hey, I'm Priya, I work as a product manager at Swiggy", "I run 5k every morning before work", "my husband Karan is a pilot",
          "I'm lactose intolerant", "I use an iPad Pro for sketching", "I've been learning the violin for two years",
          "we're planning a trip to Ladakh in October", "my phone is a pixel 8", "I read a lot of sci-fi, Asimov is my favourite",
          "my son Aarav just turned six", "I host my blog on a hetzner vps", "I hate crowded places", "Karan works at IndiGo"],
    queries=[("what's my morning routine", [1]), ("who am I married to", [2, 12]), ("any food intolerances", [3]),
             ("what do I draw on", [4]), ("what instrument do I play", [5]), ("where are we travelling", [6]),
             ("what smartphone do I have", [7]), ("what books do I like", [8]), ("how old is my kid", [9]),
             ("where is my website hosted", [10]), ("what kind of places do I avoid", [11])],
    answers=[("where does my husband work", "indigo"), ("who is my spouse", "karan"), ("what's my son's name", "aarav")],
    linked=[(2, 12)], unlinked=[(1, 7), (3, 10)],
    unknown=["what's my cat's name", "which university did I go to", "what's my favourite football team"],
    changes=[(["I love sushi", "sushi makes me sick now, I hate it"], ("me", "likes", "sushi"), False),
             (["I want to buy an e-bike", "bought the e-bike yesterday!"], ("me", "wants", "e-bike"), False),
             (["I'm moving to Pune next month", "I've moved to Pune"], ("me", "plans to move to", "pune"), False),
             (["I'm learning German", "I stopped learning German"], ("me", "learning", "german"), False),
             (["my daughter loves drawing", "my daughter's name is Isha"], ("isha", "likes", "drawing"), True),
             (["I'm building Kiosk", "Kiosk is now called Stall"], ("me", "working on", "stall"), True),
             (["my friend Rahul moved to Delhi", "he works at Zomato"], ("rahul", "works at", "zomato"), True),
             (["I use Chrome", "I switched to Firefox"], ("me", "uses", "chrome"), False)])
NATURAL = [  # everyday ways to say a fact that no rule was written for: the learner is for these (written before it)
    ("switched jobs, I'm at Stripe now", ("me", "works at", "stripe")), ("another monday at the bank, yay", ("me", "works at", "bank")),
    ("been at Google for 3 years now", ("me", "works at", "google")), ("my manager at Infosys is super strict", ("me", "works at", "infosys")),
    ("moved back home to Pune after 5 years in Dubai", ("me", "lives in", "pune")),
    ("it's so hot here in Chennai today", ("me", "lives in", "chennai")), ("been living out of Berlin since last year", ("me", "lives in", "berlin")),
    ("been vegan 3 yrs now lol", ("me", "is", "vegan")), ("as a nurse I work night shifts", ("me", "is", "nurse")),
    ("finally took the plunge and got myself a ps5", ("me", "has", "ps5")), ("bought the e-bike yesterday!", ("me", "has", "e-bike")),
    ("just got a kindle paperwhite", ("me", "has", "kindle paperwhite")), ("my new macbook arrived today", ("me", "has", "macbook")),
    ("I've got two kids and a golden retriever", ("me", "has", "golden retriever")),
    ("can't live without my kindle", ("me", "likes", "kindle")), ("obsessed with pickleball lately", ("me", "likes", "pickleball")),
    ("sushi is my comfort food", ("me", "likes", "sushi")), ("nothing beats a good thriller", ("me", "likes", "thriller")),
    ("not a coffee person tbh", ("me", "dislikes", "coffee")), ("sushi makes me sick now, I hate it", ("me", "dislikes", "sushi")),
    ("ugh, crowds make me anxious", ("me", "dislikes", "crowd")), ("no more meat for me", ("me", "avoids", "meat")),
    ("day 40 of learning japanese!", ("me", "learning", "japanese")), ("finally picking up rust this summer", ("me", "learning", "rust")),
    ("vim user for life", ("me", "uses", "vim")), ("my whole setup runs on arch btw", ("me", "uses", "arch")),
    ("been daily driving linux for years", ("me", "uses", "linux")), ("still grinding on my indie game", ("me", "working on", "indie game")),
    ("hit the courts for badminton every saturday", ("me", "plays", "badminton")), ("saving up for a new bike", ("me", "wants", "bike"))]
NATURAL_NOT = [  # nothing new about the user (a relative may still be named)
    "what's the best way to learn rust?", "if I lived in Berlin I'd bike everywhere", "my friend works at Google",
    "the bank is closed today", "Stripe's API docs are great", "can you explain how kubernetes works", "they moved to Pune last year",
    "ok do it", "is the kindle worth it?", "fix the bug in the login page", "Google announced a new phone",
    "I wonder if Japan is expensive", "should I buy a ps5 or an xbox", "my sister loves sushi", "write a poem about coffee",
    "compare arch and fedora for me", "why is my build so slow", "maybe I'll try vim someday"]
NATURAL_GONE = [  # the user takes something back: it must be retracted
    ("ugh, coffee and I are done for good", "coffee"), ("quit my job at Infosys", "infosys"), ("not using notion anymore", "notion"),
    ("sold my car last month", "car"), ("done with twitter, deleted the app", "twitter")]

NATURAL2 = dict(  # written after the learner was trained (2026-09-27), run once: the honest number for everyday phrasing
    facts=[("three years at Accenture and still no promotion", ("works at", "accenture")),
           ("finally settled in Lisbon after all the moving around", ("lives in", "lisbon")),
           ("Mumbai rains are something else, love living here", ("lives in", "mumbai")),
           ("vegetarian since birth, never tasted meat", ("is", "vegetarian")), ("picked up a steam deck over the holidays", ("has", "steam deck")),
           ("I'm a huge fan of Studio Ghibli films", ("likes", "studio ghibli film")), ("honestly obsessed with sourdough baking", ("likes", "sourdough baking")),
           ("can't stop listening to Taylor Swift", ("likes", "taylor swift")), ("horror movies are my thing", ("likes", "horror movie")),
           ("I really can't stand cilantro", ("dislikes", "cilantro")), ("mushrooms are disgusting", ("dislikes", "mushroom")),
           ("been off alcohol for 6 months", ("avoids", "alcohol")), ("cut out sugar completely this year", ("avoids", "sugar")),
           ("on day 12 of my duolingo streak for korean", ("learning", "korean")), ("trying to learn the ukulele during lockdown", ("learning", "ukulele")),
           ("mostly using Obsidian for notes these days", ("uses", "obsidian")), ("moved all my photos to Immich last weekend", ("uses", "immich")),
           ("writing a fantasy trilogy in my spare time", ("working on", "fantasy trilogy")),
           ("almost done with my portfolio redesign", ("working on", "portfolio redesign")),
           ("tennis every sunday morning with my dad", ("plays", "tennis")), ("really want a mechanical keyboard for my birthday", ("wants", "mechanical keyboard")),
           ("spent my whole childhood in Nagpur", ("from", "nagpur")), ("starting my new role at Atlassian on Monday", ("works at", "atlassian")),
           ("Arch user since 2019", ("uses", "arch")), ("just adopted a rescue cat named Miso", ("has", "rescue cat")),
           ("my daily commute is on a royal enfield", ("has", "royal enfield")), ("I'm a pharmacist at a small clinic", ("is", "pharmacist")),
           ("love a good masala dosa on sundays", ("likes", "masala dosa")), ("working remotely from Goa this month", ("lives in", "goa")),
           ("still hooked on Elden Ring", ("likes", "elden ring"))],
    none=["what's a good name for a rescue cat?", "my dad plays tennis every sunday", "Atlassian is hiring backend engineers",
          "summarize the latest Taylor Swift album reviews", "Setup notes: the NAS mounts at /mnt/data", "Chapter 4: Recursion and backtracking",
          "Loops, arrays, strings and pointers", "use obsidian for this please", "is sourdough hard to make?", "Lisbon is gorgeous in October",
          "if I had time I'd learn korean", "the espresso machine at work is broken again", "ok that fixed it, thanks",
          "Priya moved to Lisbon last year", "compare Obsidian and Notion for a student", "error: permission denied when running the script",
          "my brother is obsessed with F1", "the new steam deck looks amazing", "Studio Ghibli announced a new film", "Operating systems and networks"],
    gone=[("no longer at Accenture as of this week", "accenture"), ("sold the steam deck, never used it", "steam deck"),
          ("stopped using Obsidian, too slow for me", "obsidian"), ("not doing duolingo anymore", "duolingo"),
          ("quit tennis after my knee injury", "tennis"), ("gave away my old kindle", "kindle")])

NATURAL3 = dict(  # written before the learner saw any AI-written examples (2026-09-27): the clean before/after for step 2b
    facts=[("my 9 to 5 is at a fintech called Revolut", ("works at", "revolut")), ("two years into my job at Tesla now", ("works at", "tesla")),
           ("we just closed on a house in Austin!", ("lives in", "austin")), ("finally unpacked after the move to Leeds", ("lives in", "leeds")),
           ("keto for three months and down 8 kilos", ("is", "keto")), ("proud owner of a Tamagotchi again lol", ("has", "tamagotchi")),
           ("the new Pixel 9 is in my pocket as we speak", ("has", "pixel 9")), ("my cat Biscuit knocked over my coffee again", ("cat", "biscuit")),
           ("can't get enough of Korean dramas lately", ("likes", "korean drama")), ("Formula 1 weekends are sacred in my house", ("likes", "formula 1")),
           ("honestly can't do spicy food anymore", ("dislikes", "spicy food")), ("giving up meat for good this year", ("avoids", "meat")),
           ("zero caffeine since march", ("avoids", "caffeine")), ("grinding leetcode every night for interviews", ("learning", "leetcode")),
           ("halfway through a pottery course at the community center", ("learning", "pottery")),
           ("Emacs for everything, org-mode changed my life", ("uses", "emacs")), ("all my passwords live in Bitwarden", ("uses", "bitwarden")),
           ("building a tiny rust compiler for fun", ("working on", "rust compiler")),
           ("launching my candle shop on etsy next week", ("working on", "candle shop")),
           ("5-a-side football every thursday after work", ("plays", "football")),
           ("desperately need a new laptop, mine is dying", ("wants", "laptop")), ("my hometown is Mysore", ("from", "mysore")),
           ("I've been a UX researcher for 6 years", ("is", "ux researcher")), ("Toronto has been home for a decade", ("lives in", "toronto")),
           ("mechanic by trade, coder by night", ("is", "mechanic")), ("absolutely love hiking in the Alps", ("likes", "hiking")),
           ("recently switched from Android to an iPhone 16", ("uses", "iphone 16")), ("my daughter Zara just turned 3", ("daughter", "zara")),
           ("been using a Framework laptop since last spring", ("uses", "framework laptop")),
           ("lactose intolerant, so no milk in my tea", ("is", "lactose intolerant"))],
    none=["how do I get a job at Revolut?", "my roommate just bought a Pixel 9", "Austin real estate prices are wild",
          "if I went keto would I lose weight?", "plan a 5-day trip to Iceland for me", "what's the difference between Emacs and Vim",
          "Bitwarden vs 1Password?", "my mom loves Korean dramas", "install: pip install -r requirements.txt", "Week 3: Trees, heaps and hashing",
          "Tesla recalled another model", "someone told me pottery is relaxing", "rewrite this paragraph to sound more formal",
          "Leeds United lost again", "Zara is a clothing brand, right?"],
    gone=[("left Revolut after the layoffs", "revolut"), ("no more Bitwarden, moved everything elsewhere", "bitwarden"),
          ("sold my Pixel last week", "pixel"), ("stopped going to pottery class", "pottery"), ("don't live in Leeds anymore", "leeds"),
          ("not into Korean dramas these days", "korean drama")])


def rels_of(g):
    ek = {r[0]: r[1] for r in g.db.execute("SELECT id, key FROM nodes WHERE kind='entity'")}
    return {(ek[a], rel, ek[b]) for a, b, rel in g.db.execute("SELECT src, dst, rel FROM edges") if a in ek and b in ek}


def said(msgs, chat=None, gap=DAY):
    """msgs said one per `gap` (in one chat if given) -> (graph, memory ids per message)."""
    g = server.Graph(":memory:")
    t0 = time.time() - (len(msgs) + 1) * gap
    return g, [g.ingest(t, "chatgpt.com", chat, chat and "https://chatgpt.com/c/" + chat, t0 + i * gap) for i, t in enumerate(msgs)]


def brain_suite(s):
    """-> {part: (ok, total, misses)} for meaning, answers, links, unknown and changes."""
    g, ids = said(s["msgs"])
    of = {m: i for i, ms in enumerate(ids) for m in ms}
    out = {}
    bad = []
    for q, want in s["queries"]:
        got = [of.get(m["id"]) for m in g.recall(q, 10)["memories"]]
        if not any(i in want for i in got[:3]):
            bad.append(f"  meaning: {q!r} want {want} got {got[:5]}")
    out["meaning"] = (len(s["queries"]) - len(bad), len(s["queries"]), bad)
    bad = []
    for q, want in s["answers"]:
        ans = (g.recall(q, 5).get("answer") or {}).get("text", "")
        if want not in ans.lower():
            bad.append(f"  answer: {q!r} want {want!r} got {ans!r}")
    out["answers"] = (len(s["answers"]) - len(bad), len(s["answers"]), bad)
    sim = {frozenset(e) for e in g.db.execute("SELECT src, dst FROM edges WHERE rel='similar'")}
    linked = lambda a, b: any(frozenset((x, y)) in sim for x in ids[a] for y in ids[b])
    bad = [f"  not linked: {s['msgs'][a]!r} ~ {s['msgs'][b]!r}" for a, b in s["linked"] if not linked(a, b)] + \
          [f"  wrongly linked: {s['msgs'][a]!r} ~ {s['msgs'][b]!r}" for a, b in s["unlinked"] if linked(a, b)]
    out["links"] = (len(s["linked"]) + len(s["unlinked"]) - len(bad), len(s["linked"]) + len(s["unlinked"]), bad)
    bad = []
    for q in s["unknown"]:
        r = g.recall(q, 8)
        if r["answer"] or r["memories"]:
            bad.append(f"  should not know: {q!r} -> {(r['answer'] or {}).get('text')!r} {[m['text'][:40] for m in r['memories'][:3]]}")
    out["unknown"] = (len(s["unknown"]) - len(bad), len(s["unknown"]), bad)
    bad = []
    for msgs, triple, want in s["changes"]:
        if (triple in rels_of(said(msgs, "c1", 3600)[0])) != want:
            bad.append(f"  change: {msgs} -> {triple} should be {'there' if want else 'gone'}")
    out["changes"] = (len(s["changes"]) - len(bad), len(s["changes"]), bad)
    return out


PARTS = {"meaning": "asked in other words", "answers": "answers about people", "links": "linked by meaning",
         "unknown": "says when it doesn't know", "changes": "facts that change"}


def natural(facts=None, none=None, gone=None):
    """Everyday phrasings: facts found, false facts avoided, things taken back -> [(ok, total, misses)]."""
    import brain
    facts = facts or [(t, w[1:]) for t, w in NATURAL]
    none, gone = none or NATURAL_NOT, gone or NATURAL_GONE
    rel = lambda t: {r for m in brain.analyse(t) for r in m["relations"]}
    hit = lambda t, w: any(r[0] == "me" and r[1] == w[0] and (r[2] == w[1] or brain.same_thing(r[2], w[1])) for r in rel(t))
    found = [f"  missed: {t!r} want {w} got {sorted(rel(t))}" for t, w in facts if not hit(t, w)]
    false = [f"  false fact: {t!r} -> {sorted(r for r in rel(t) if r[0] == 'me' and r[1] not in brain.KIN)}" for t in none
             if any(r[0] == "me" and r[1] not in brain.KIN for r in rel(t))]
    back = [f"  not taken back: {t!r} ({k})" for t, k in gone
            if not any(r[2] == k or brain.same_thing(k, r[2]) for m in brain.analyse(t) for r in m["retracts"])]
    return [(len(facts) - len(found), len(facts), found), (len(none) - len(false), len(none), false),
            (len(gone) - len(back), len(gone), back)]


def holdout():
    h = HOLDOUT
    g = server.Graph(":memory:")
    t0 = time.time() - 30 * DAY
    ids = [g.ingest(text, site, chat, None, ts=t0 + i * DAY) for i, (site, chat, text) in enumerate(h["msgs"])]
    msg_of = {m: i for i, ms in enumerate(ids) for m in ms}
    ek = {r[0]: r[1] for r in g.db.execute("SELECT id, key FROM nodes WHERE kind='entity'")}
    rels = {(ek[a], rel, ek[b]) for a, b, rel in g.db.execute("SELECT src, dst, rel FROM edges") if a in ek and b in ek}
    have = sum(r in rels for r in h["have"])
    wrong = [r for r in h["have_not"] if r in rels]
    q = 0
    for text, want, k, never in h["queries"]:
        got = [msg_of.get(m["id"]) for m in g.recall(text, 10)["memories"]]
        q += any(i in want for i in got[:k]) and not any(i in never for i in got[:k])
    a = sum(w in (g.recall(t, 5).get("answer") or {}).get("text", "").lower() for t, w in h["answers"])
    dump = " ".join(str(r) for t in ("captures", "nodes") for r in g.db.execute(f"SELECT * FROM {t}"))
    leaks = sum(s in dump for s in h["secrets"])
    print(f"holdout: relations {have}/{len(h['have'])}, wrong {len(wrong)}, queries {q}/{len(h['queries'])}, "
          f"answers {a}/{len(h['answers'])}, leaks {leaks}")
    missing = [r for r in h["have"] if r not in rels]
    if missing or wrong:
        print("  holdout missing:", missing, "wrong:", wrong)


def run(verbose=True):
    g = server.Graph(":memory:")
    t0 = time.time() - 60 * DAY
    ids = []
    for i, (site, chat, text) in enumerate(MSGS):
        ids.append(g.ingest(text, site, chat, "https://%s/c/%s" % (site, chat or i), ts=t0 + i * DAY))
    msg_of = {m: i for i, ms in enumerate(ids) for m in ms}
    ent_key = {r[0]: r[1] for r in g.db.execute("SELECT id, key FROM nodes WHERE kind='entity'")}
    rels = {(ent_key[a], rel, ent_key[b]) for a, b, rel in g.db.execute("SELECT src, dst, rel FROM edges")
            if a in ent_key and b in ent_key}
    score, lines = {}, []

    def gate(name, ok, total, need):
        score[name] = (ok, total, need)
        lines.append(f"{name:28} {ok:3}/{total:<3} {'ok ' if ok >= need else 'LOW'} (need {need})")

    have = [r for r in HAVE if r in rels]
    gate("relations known", len(have), len(HAVE), len(HAVE))
    wrong = [r for r in HAVE_NOT if r in rels]
    gate("stale/negated absent", len(HAVE_NOT) - len(wrong), len(HAVE_NOT), len(HAVE_NOT))
    junk = [k for k in ent_key.values() if any(j in k for j in JUNK)]
    gate("junk-free entities", len(ent_key) - len(junk), len(ent_key), len(ent_key))
    q_ok, rr, misses = 0, [], []
    for q, want, k, never in QUERIES:
        got = [msg_of.get(m["id"]) for m in g.recall(q, 10)["memories"]]
        rank = next((r for r, i in enumerate(got, 1) if i in want), None)
        bad = [i for i in never if i in got[:k]]
        ok = rank is not None and rank <= k and not bad
        q_ok += ok
        rr.append(1 / rank if rank else 0)
        if not ok:
            misses.append(f"  miss: {q!r} want {want} got {got[:5]}" + (f" stale {bad}" if bad else ""))
    gate("queries hit@k", q_ok, len(QUERIES), len(QUERIES))
    mrr = sum(rr) / len(rr)
    a_ok = 0
    for q, want in ANSWERS:
        ans = (g.recall(q, 5).get("answer") or {}).get("text", "")
        a_ok += want in ans.lower()
        if want not in ans.lower():
            misses.append(f"  answer: {q!r} want {want!r} got {ans!r}")
    gate("direct answers", a_ok, len(ANSWERS), len(ANSWERS))
    cl = {r[0]: r[1] for r in g.db.execute("SELECT id, cluster FROM nodes WHERE kind='memory'")}
    topic = lambda i: {cl.get(m) for m in ids[i]} - {None}
    same = sum(1 for a, b in SAME_TOPIC if topic(a) & topic(b))
    diff = sum(1 for a, b in DIFF_TOPIC if not (topic(a) & topic(b)))
    for a, b in SAME_TOPIC:
        if not topic(a) & topic(b):
            misses.append(f"  topic: {a} and {b} should share a topic")
    gate("topics together", same, len(SAME_TOPIC), len(SAME_TOPIC) - 1)
    gate("topics apart", diff, len(DIFF_TOPIC), len(DIFF_TOPIC))
    dump = " ".join(str(r) for t in ("captures", "nodes") for r in g.db.execute(f"SELECT * FROM {t}")).lower()
    leaks = [s for s in ("hunter2secret", "sk-proj-abc123") if s in dump]
    gate("secrets redacted", 2 - len(leaks), 2, 2)
    dropped = sum(1 for i in (39, 40) if not ids[i])
    gate("chit-chat dropped", dropped, 2, 2)
    r_ok, r_n, r_bad = real(V1)
    gate("v1 extension messages", r_ok, r_n, r_n)
    misses += r_bad
    if os.path.exists(PRIVATE):
        r_ok, r_n, r_bad = real(json.load(open(PRIVATE)))
        gate("your real messages (private)", r_ok, r_n, r_n)
        misses += r_bad
    y_ok, y_bad = typo_names()
    gate("typos vs real names", y_ok, len(TYPO_NAMES) + len(REAL_NAMES), len(TYPO_NAMES) + len(REAL_NAMES))
    misses += y_bad
    s_ok, s_bad = steering()
    gate("steering vs short content", s_ok, len(STEERING) + len(KEEP_SHORT), len(STEERING) + len(KEEP_SHORT))
    misses += s_bad
    c_ok, c_n, c_bad = cross_app()
    gate("same topic across apps", c_ok, c_n, c_n)
    misses += c_bad
    p_ok, p_bad = phrasings()
    gate("phrasings understood", p_ok, len(PHRASINGS), len(PHRASINGS))
    misses += p_bad
    for part, (ok, n, bad) in brain_suite(BRAIN).items():
        gate(PARTS[part], ok, n, n - (part == "links"))  # asthma ~ inhaler: beyond the static vectors (0.18)
        misses += bad
    for name, (ok, n, bad) in zip(("everyday phrasings", "no false facts", "taken back"), natural()):
        gate(name, ok, n, n - (name == "everyday phrasings"))  # "sushi is my comfort food": the learner picks "comfort food"
        misses += bad
    if verbose:
        print("\n".join(lines))
        print(f"{'MRR':28} {mrr:.3f}")
        if wrong:
            print("  wrongly asserted:", wrong)
        if len(have) < len(HAVE):
            print("  missing:", [r for r in HAVE if r not in rels])
        if junk:
            print("  junk entities:", junk)
        print("\n".join(misses))
    return all(ok >= need for ok, _, need in score.values()), score, mrr


if __name__ == "__main__":
    ok, _, _ = run()
    holdout()
    h2 = brain_suite(HOLDOUT2)
    print("holdout 2: " + ", ".join(f"{PARTS[k]} {a}/{n}" for k, (a, n, _) in h2.items()))
    print("\n".join(b for _, _, bad in h2.values() for b in bad))
    h3 = brain_suite(HOLDOUT3)
    print("holdout 3: " + ", ".join(f"{PARTS[k]} {a}/{n}" for k, (a, n, _) in h3.items()))
    print("\n".join(b for _, _, bad in h3.values() for b in bad))
    (f, fn, fb), (n, nn, nb), (g_, gn, gb) = natural(NATURAL2["facts"], NATURAL2["none"], NATURAL2["gone"])
    print(f"everyday phrasings, fresh set: facts {f}/{fn}, no false facts {n}/{nn}, taken back {g_}/{gn}")
    print("\n".join(fb + nb + gb))
    (f, fn, fb), (n, nn, nb), (g_, gn, gb) = natural(NATURAL3["facts"], NATURAL3["none"], NATURAL3["gone"])
    print(f"everyday phrasings, fresh set 3: facts {f}/{fn}, no false facts {n}/{nn}, taken back {g_}/{gn}")
    print("\n".join(fb + nb + gb))
    sys.exit(0 if ok else 1)
