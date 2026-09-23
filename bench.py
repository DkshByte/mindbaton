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
import json, os, sys, time
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
    ("grok.com", None, "my api key is sk-proj-abc123def456ghi789jkl012mno345pqr678 can you check why this curl fails"),  # 18
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
           ("where did I work 39 days ago", "infosys")]
SAME_TOPIC = [(3, 4), (7, 8), (8, 9), (14, 15), (15, 38), (11, 12), (24, 25)]
DIFF_TOPIC = [(3, 11), (7, 14), (11, 15), (29, 4)]


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
        ("gemini.google.com", None, "my github token is ghp_16C7e42F292c6912E7710c838347Ae178B4a so pls debug"),
    ],
    have=[("me", "named", "ananya"), ("me", "lives in", "pune"), ("me", "uses", "figma"), ("me", "cat", "mochi"),
          ("me", "likes", "jazz"), ("me", "working on", "portfolio site"), ("me", "is", "ux designer")],
    have_not=[("me", "lives in", "mumbai"), ("me", "uses", "framer"), ("me", "learning", "three.js"), ("me", "learning", "spline")],
    queries=[("where do I live", [5], 1, [0]), ("what design tools do i use", [1], 3, []), ("my pet", [2], 2, []),
             ("portfolio animation bug", [4], 2, []), ("music taste", [8], 3, []), ("food allergies", [9], 2, [])],
    answers=[("where do I live", "pune"), ("what's my name", "ananya")],
    secrets=["ghp_16C7e42F292c6912E7710c838347Ae178B4a"],
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
    return ok, 12, bad


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
    sys.exit(0 if ok else 1)
