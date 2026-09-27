"""learn — reads the everyday ways people state a fact that no hand-written rule covers ("switched jobs, I'm at Stripe
now", "not a coffee person tbh", "bought the e-bike yesterday!"). It learns from examples instead of rules. Stdlib only.

Two averaged perceptrons, trained on sentences generated from the templates at the end of this file (never from
anyone's messages):
  which fact    a clause -> "none", or +relation (it's true now) / -relation (it stopped being true)
  which words   the clause's noun phrases -> the object of that fact
brain.analyse asks it only about statements in which the rules found nothing about the user, and keeps an answer only
when it is sure: a missed fact costs less than a made-up one. The weights ship in assets/learn/weights.json.gz.

    python3 learn.py            # self-check
    python3 learn.py --train    # generate examples, train, report held-out accuracy, write the weights (~2 min)
    python3 learn.py --write    # have a big open model (gpt-oss-120b on Groq, GROQ_KEY) write varied chat examples of
                                # made-up facts into assets/learn/examples.jsonl.gz (~30 min of a free tier; nothing personal)
"""
import gzip, hashlib, json, math, os, random, re, sys
from collections import defaultdict
import brain

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "learn", "weights.json.gz")
ME = {"i", "i'm", "i've", "i'd", "i'll", "me", "my", "myself", "mine", "we", "we're", "we've", "our", "us"}
TIMEISH = set("week weekend month year morning evening night time summer winter spring autumn fall birthday anniversary "
              "christmas diwali holidays holiday vacation lockdown today tonight".split())
GENERIC = set("person people user users fan fans lover lovers guy girl type kind junkie addict nerd geek enthusiast freak".split())
KEEP = brain.STOP | brain.PREP | brain.AUX | brain.DET | brain.PRON | brain.ADV | brain.TEMPW | brain.QWORD | brain.CONJ | \
    set("now anymore lately still just finally already new old another first last next every since ago".split())


def _load():
    try:
        with gzip.open(PATH, "rt", encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return None


W = _load()


# ---- features --------------------------------------------------------------------------------------------------------
def shape(words, tags):
    """Content words become N (or V/R), so "at google now" and "at stripe now" look alike; the rest stay words."""
    out = []
    for w, t in zip(words, tags):
        l = w.lower()
        out.append(l if l in KEEP or l in ME or l in brain.VERB and t == "V" else "N" if t == "N" else t)
    return out


def clause_feats(words, tags):
    low = [w.lower() for w in words]
    sh = shape(words, tags)
    f = ["b", "first=" + (sh[0] if sh else ""), "first2=" + "_".join(sh[:2]), "last=" + (sh[-1] if sh else ""),
         "me" if ME & set(low) else "nome", "q" if "?" in low else "noq", "len=%d" % min(len(low) // 3, 5)]
    f += ["w=" + w for w in low] + ["s=" + x for x in sh]
    f += ["b=%s_%s" % p for p in zip(sh, sh[1:])] + ["wb=%s_%s" % p for p in zip(low, low[1:])]
    f += ["t=%s_%s_%s" % p for p in zip(sh, sh[1:], sh[2:])]
    f += ["v=" + brain.VERB[w] for w in low if w in brain.VERB]
    f += ["cat=" + c for w in low for c in [brain.category_of(brain.key(w))] if c]
    return f


def candidates(c):
    """Noun phrases of a clause (the brain's own chunker), each with where it starts and ends: [(text, start, stop)]."""
    out, seen = [], set()
    for i, t in enumerate(c.tags):
        if t in "ND" or t == "V" and c.words[i].lower().endswith("ing"):
            objs, stop = c.objects(i, maxwords=5, lists=False)
            for o in objs[:1]:
                # the phrase, and the phrase without its last word ("coffee person" -> "coffee", "vim user" -> "vim")
                for x in [o] + ([o.rsplit(" ", 1)[0]] if " " in o else []):
                    ws = x.lower().split()
                    if x.lower() not in seen and x.lower() not in brain.STOP and ws[0] not in brain.CUT and \
                            not set(ws) <= brain.UNITS | brain.TEMPW | TIMEISH and ws[-1] not in TIMEISH:  # "last month" is when, not what
                        seen.add(x.lower())
                        out.append((x, i, stop))
    return out


def span_feats(rel, cand, words, i, stop):
    low = [w.lower() for w in words]
    toks = cand.lower().split()
    prev, prev2 = (low[i - 1] if i > 0 else "<s>"), (low[i - 2] if i > 1 else "<s>")
    nxt = low[stop] if stop < len(low) else "</s>"
    k = brain.key(cand)
    cut = low[stop - 1] if stop > i and cand.lower().split()[-1] != low[stop - 1] else "-"  # the word the phrase dropped
    kind = "gaz" if k in brain.GAZ else "cap" if cand[:1].isupper() else "name" if brain.namey(toks[-1]) else "word"
    base = ["head=" + toks[-1], "first=" + toks[0], "prev=" + prev, "prev2=%s_%s" % (prev2, prev), "next=" + nxt,
            "len=%d" % min(len(toks), 4), "kind=" + kind, "cat=%s" % brain.category_of(k), "my=%d" % (prev == "my"),
            "pos=%s" % ("start" if i == 0 else "end" if stop >= len(low) else "mid"), "abstract=%d" % (toks[-1] in brain.ABSTRACT),
            "cut=" + cut, "generic=%d" % (toks[-1] in GENERIC), "cutgeneric=%d" % (cut in GENERIC)]
    return base + [rel + "|" + x for x in base]


def _score(weights, feats, cls=None):
    s = defaultdict(float)
    for f in feats:
        for c, w in weights.get(f, {}).items():
            s[c] += w
    return s if cls is None else s.get(cls, 0.0)


MARKUP = re.compile(r"[()\[\]{}\\=_<>|`$%]|://|\w\.(?:py|js|ts|db|json|md|txt|sh|html|css|ya?ml|toml|log|bak|zip|env)\b|"
                    r"\b\d{4}-\d\d-\d\d\b|\b\d{1,3}(?:\.\d{1,3}){3}\b|\B--?\w|~/|\s/\w")
LEADS = {"update", "fyi", "btw", "ps", "edit", "note", "quick one", "fun fact", "ok", "so", "lol", "news", "confession", "also"}
SOFT = set("and but so just please pls plz now then also first ok okay hey oh well anyway yeah yes yep yup no nope nah sure cool "
           "great nice alright right".split()) | brain.FILLER
PAST_TOO = set("quit hit put set cut let read cost hurt".split())  # a bare past tense: "quit my job" is a statement


def chatlike(s):
    """Is this clause someone telling something in chat, rather than a heading, a list, a log line, a technical note or an
    instruction to an agent? The learner only reads chat; its examples are chat."""
    if MARKUP.search(s) or s.count(",") >= 2:
        return False
    if ":" in s and s.split(":", 1)[0].strip().lower() not in LEADS:
        return False
    words = [w.lower() for w in re.findall(r"[\w'’]+", s.split(":", 1)[-1])]  # after "update:" the message starts
    first = next((w for w in words if w not in SOFT), "")
    return not (first in ("let's", "lets", "don't", "dont", "do") or first in brain.VERB and brain.VERB[first] == first
                and first not in PAST_TOO and not first.endswith("ing"))  # "use black" / "start prototyping" = do this


def read(s):
    """A clause -> [(op, relation, object)] when the learner is sure: op '+' is true now, '-' stopped being true."""
    if not W or not chatlike(s):
        return []
    c = brain.Clause(s)
    if not c.words:
        return []
    sc = _score(W["rel"], clause_feats(c.words, c.tags))
    ranked = sorted(sc.items(), key=lambda x: -x[1]) + [("none", 0.0)]
    (lab, top), second = ranked[0], ranked[1][1]
    if lab == "none" or top - second < W["margin"]:
        return []
    op, rel = lab[0], lab[1:]
    cands = candidates(c)
    if not cands:
        return []
    obj, i, stop = max(cands, key=lambda x: _score(W["span"], span_feats(rel, x[0], c.words, x[1], x[2]), "y"))
    more = c.objects(i, maxwords=5)[0][1:] if op == "+" else []  # "two kids and a golden retriever": the rest of the list
    items = [obj] + more
    if rel in ("lives in", "from"):  # a place is a name: "in college", "in bed" is no place one lives
        items = [o for o in items if any(w[:1].isupper() or w.lower() in brain.PROPER or brain.namey(w) for w in o.split())]
    return [(op, rel, o) for o in items if o.lower() not in brain.NOT_THING and o.lower() not in brain.STOP]


# ---- training --------------------------------------------------------------------------------------------------------
class Perceptron:
    """Averaged multiclass perceptron over sparse binary features: weights[feature][class]."""

    def __init__(self):
        self.w, self.tot, self.ts, self.n = defaultdict(dict), defaultdict(float), defaultdict(int), 0

    def _add(self, f, c, d):
        k = (f, c)
        self.tot[k] += (self.n - self.ts[k]) * self.w[f].get(c, 0.0)
        self.ts[k] = self.n
        self.w[f][c] = self.w[f].get(c, 0.0) + d

    def update(self, truth, guess, feats, wrong=None):
        """Classes: truth +1 / guess -1 on the same features; ranking: truth's features +1, wrong's (the guess) -1."""
        self.n += 1
        if wrong is not None:
            for f in truth:
                self._add(f, "y", 1)
            for f in wrong:
                self._add(f, "y", -1)
        elif truth != guess:
            for f in feats:
                self._add(f, truth, 1)
                self._add(f, guess, -1)

    def averaged(self, floor=1e-3):
        out = {}
        for f, ws in self.w.items():
            kept = {c: round((self.tot[(f, c)] + (self.n - self.ts[(f, c)]) * w) / self.n, 4) for c, w in ws.items()}
            kept = {c: w for c, w in kept.items() if abs(w) >= floor}
            if kept:
                out[f] = kept
        return out


def examples(n_per=600, seed=7):
    """Generated (clause, label, object) triples: every template, its slots filled from the pools, dressed like chat."""
    rnd = random.Random(seed)
    out = []
    for lab, pool, temps in TEMPLATES:
        for _ in range(n_per if lab != "none" else n_per * 2):
            t = rnd.choice(temps)
            obj = rnd.choice(POOLS[pool]) if pool else None
            text = fill(t, obj, rnd)
            out.append((text, lab, obj))
    rnd.shuffle(out)
    return out


def fill(t, obj, rnd):
    t = re.sub(r"\[([^\]]*)\]", lambda m: m[1] if rnd.random() < .55 else "", t)            # optional parts
    t = re.sub(r"\{(\w+)\}", lambda m: obj if m[1] == "o" else rnd.choice(POOLS[m[1]]), t)
    t = rnd.choice(PRE) + t + rnd.choice(POST)
    if rnd.random() < .5:
        t = t.lower()
    if rnd.random() < .2:
        t = t.replace("'", "")
    return re.sub(r"\s+", " ", t).strip()


def clauses(text, lab, obj):
    """What the brain would hand the learner: cleaned clauses. A fact's other clauses ("…, I hate it") are left out, not
    called "none": they often say the same thing again."""
    out = []
    for s in brain.sentences(brain.clean(text)):
        holds = obj and obj.lower() in s.lower()
        if lab == "none" or holds:
            out.append((s, lab, obj if holds else None))
    return out


def prose(n=6000, seed=5):
    """Impersonal sentences from Python's own documentation (the standard library's docstrings): technical text that
    says nothing about anyone. Every Python has it, so the training stays reproducible."""
    import importlib
    out = []
    for name in ("os re json sqlite3 argparse collections datetime pathlib subprocess threading logging email http.server "
                 "urllib.request csv zipfile tarfile shutil socket ssl hashlib random statistics string textwrap unittest "
                 "asyncio typing dataclasses functools itertools calendar decimal fractions gzip heapq inspect ipaddress "
                 "locale mimetypes pickle pprint queue sched secrets selectors signal smtplib tempfile timeit uuid").split():
        try:
            m = importlib.import_module(name)
        except Exception:
            continue
        for d in [m.__doc__] + [getattr(getattr(m, a, None), "__doc__", None) for a in dir(m) if not a.startswith("_")]:
            for line in re.split(r"(?<=[.!?])\s+|\n\s*\n", d if isinstance(d, str) else ""):
                line = " ".join(line.split())
                if 3 <= len(line.split()) <= 25:
                    out.append(line)
    rnd = random.Random(seed)
    out = sorted(set(out))
    rnd.shuffle(out)
    return out[:n]


EXAMPLES = os.path.join(os.path.dirname(PATH), "examples.jsonl.gz")
WRITERS = {  # who writes examples: (endpoint, model, key variable, file)
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-120b", "GROQ_KEY", EXAMPLES),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-3-flash-preview", "GEMINI_KEY",
               EXAMPLES.replace("examples", "examples-gemini")),
}


def written(sources=("groq", "gemini")):
    """The examples big models wrote (--write): [(text, label, object)]. Gemini's are kept apart (its terms bar training
    models that compete with it): fine for these patterns, left out of anything bigger."""
    out = []
    for src in sources:
        try:
            with gzip.open(WRITERS[src][3], "rt", encoding="utf-8") as f:
                out += [(x["text"], x["label"], x.get("obj")) for x in map(json.loads, f)]
        except OSError:
            pass
    return out


def train(epochs=8, weight=3):
    """weight: how many times each example a big model wrote counts (they are the most like real chat). 15% of them,
    split by object so no object is in both, are held out to report how it reads chat it never saw."""
    asked = lambda d: chatlike(d[0]) and brain.mood(d[0]) == "statement"  # what the learner will be asked about
    w = written()
    h = lambda x: int(hashlib.md5(x.lower().encode()).hexdigest(), 16) % 100
    held = lambda text, obj: h(obj) < 15 if obj else h(text) < 15
    w_dev = [c for text, lab, obj in w if held(text, obj) for c in clauses(text, lab, obj) if asked(c)]
    w_tr = [c for text, lab, obj in w if not held(text, obj) for c in clauses(text, lab, obj) if asked(c)]
    data = [c for text, lab, obj in examples() for c in clauses(text, lab, obj) if asked(c)] + \
        [c for text in prose() for c in clauses(text, "none", None) if asked(c)]
    random.Random(11).shuffle(data)
    cut = len(data) // 10
    dev, tr = data[:cut], data[cut:] + w_tr * weight
    random.Random(12).shuffle(tr)
    rel, span = Perceptron(), Perceptron()
    prep = []
    for s, lab, obj in tr:
        c = brain.Clause(s)
        cands = candidates(c) if obj else []
        want = brain.key((brain.Clause(obj).objects(0, lists=False)[0] or [obj])[0]) if obj else None  # "a novel" -> "novel"
        gold = [x for x in cands if brain.key(x[0]) == want] if obj else []
        prep.append((clause_feats(c.words, c.tags), lab, c, cands, gold[:1]))
    rnd = random.Random(3)
    for ep in range(epochs):
        rnd.shuffle(prep)
        right = 0
        for feats, lab, c, cands, gold in prep:
            sc = _score(rel.w, feats)
            guess = max(sc, key=sc.get) if sc else "none"
            right += guess == lab
            rel.update(lab, guess, feats)
            if gold and len(cands) > 1 and lab != "none":
                r = lab[1:]
                fs = {x: span_feats(r, x[0], c.words, x[1], x[2]) for x in cands}
                best = max(cands, key=lambda x: _score(span.w, fs[x], "y"))
                if best != gold[0]:
                    span.update(fs[gold[0]], None, None, wrong=fs[best])
        print(f"epoch {ep + 1}: train accuracy {right / len(prep):.3f}")
    model = {"rel": rel.averaged(), "span": span.averaged(), "margin": 0.0}
    # the margin: the smallest one that keeps made-up facts under 1 in 200 of the held-out clauses that state nothing
    global W
    W = model
    nones = [s for s, lab, _ in dev if lab == "none"]
    wrong = sorted((m for s in nones for m in [_margin(s)] if m is not None), reverse=True)
    allowed = int(len(nones) * .002)
    model["margin"] = round(max(wrong[allowed] if len(wrong) > allowed else 0.0, 10.0), 4)  # 10: below it, guesses (real chats)
    W = model
    if w_dev:
        pos = [(s, lab) for s, lab, _ in w_dev if lab != "none"]
        caught = sum(_label(s) == lab for s, lab in pos)
        false = sum(_label(s) != "none" for s, lab, _ in w_dev if lab == "none")
        print(f"held-out written examples: facts {caught}/{len(pos)}, made-up facts {false}/{len(w_dev) - len(pos)}")
    ok = sum(_label(s) == lab for s, lab, _ in dev) / len(dev)
    obj_ok = [(_object(s, lab), (brain.Clause(obj).objects(0, lists=False)[0] or [obj])[0]) for s, lab, obj in dev if obj and lab != "none"]
    print(f"held-out: label {ok:.3f}, object {sum(brain.key(a or '') == brain.key(b) for a, b in obj_ok) / max(len(obj_ok), 1):.3f}, "
          f"margin {model['margin']}")
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with gzip.open(PATH + ".tmp", "wt", encoding="utf-8") as f:
        json.dump(model, f, separators=(",", ":"))
    os.replace(PATH + ".tmp", PATH)
    print(f"wrote {PATH} ({os.path.getsize(PATH) // 1024} KB, {len(model['rel'])} + {len(model['span'])} features)")


SAY = {"+works at": 'works at "{o}"', "+lives in": 'lives in "{o}"', "+from": 'grew up in / is originally from "{o}"',
       "+is": 'is (a) "{o}"', "+has": 'owns or just got (a) "{o}"', "+uses": 'uses "{o}"', "+likes": 'likes or loves "{o}"',
       "+dislikes": 'dislikes "{o}"', "+avoids": 'avoids or doesn\'t eat/drink "{o}"', "+learning": 'is learning "{o}"',
       "+working on": 'is working on "{o}"', "+plays": 'plays "{o}"', "+wants": 'wants to get (a) "{o}"',
       "-works at": 'no longer works at "{o}"', "-lives in": 'no longer lives in "{o}"', "-uses": 'stopped using "{o}"',
       "-has": 'no longer has (sold or gave away) "{o}"', "-likes": 'no longer likes "{o}"', "-learning": 'gave up learning "{o}"',
       "-working on": 'stopped working on "{o}"', "-plays": 'stopped playing "{o}"'}
ASK_FACTS = """You write training data for a personal memory app. Each numbered line is a fact about the WRITER of a chat message.
For each fact write {k} different messages the writer might send to an AI chat assistant, each stating that fact the way
real people type: casual, sometimes long, sometimes a fragment, typos, slang, lowercase, emoji, often without "I", as a side
remark before or after something else, with varied words and sentence shapes (never just "I <verb> X"). Every message must
contain the quoted text exactly as written (without the quotes) and must make the fact clear about the writer. Reply with
JSON only: {{"1": ["...", ...], "2": [...], ...}}
Facts:
{facts}"""
ASK_NONE = """You write training data for a personal memory app. Each numbered line is a thing. For each, write {k} different chat
messages to an AI assistant that contain the quoted text exactly (without the quotes) but say NOTHING lasting about the
writer: questions about it, requests to the AI, facts about other people, news, hypotheticals ("if I ..."), comparisons,
jokes, technical notes. Vary the style like real chat (typos, lowercase, fragments). Reply with JSON only:
{{"1": ["...", ...], "2": [...], ...}}
Things:
{facts}"""


def write(per=4, batch=20, facts_per_label=45, none_per_pool=70, seed=13, budget=140, writer="groq"):
    """Examples in other words: a big model (gpt-oss-120b, open weights, on Groq's free tier; or Gemini) writes chat
    messages for made-up facts drawn from POOLS. Nothing about anyone real is sent. Kept only if the message holds the
    object verbatim."""
    import time, urllib.error, urllib.request
    url, model, var, out_path = WRITERS[writer]
    key = os.environ.get(var)
    if not key:
        sys.exit(f"set {var}")
    rnd = random.Random(seed)
    jobs = []
    for lab, pool, _ in TEMPLATES:
        if lab != "none" and lab in SAY and pool:
            jobs += [(lab, o) for o in rnd.sample(POOLS[pool], min(facts_per_label // 2 + 1, len(POOLS[pool])))]
    for pool in ("like", "org", "place", "thing", "tool", "topic"):
        jobs += [("none", o) for o in rnd.sample(POOLS[pool], min(none_per_pool // 5, len(POOLS[pool])))]
    rnd.shuffle(jobs)
    got, sent = [], 0
    try:  # a run adds to what earlier runs wrote (a free tier's daily limit may cut a run short)
        with gzip.open(out_path, "rt", encoding="utf-8") as f:
            got = [json.loads(line) for line in f]
    except OSError:
        pass

    def save():
        keep = list({x["text"].lower(): x for x in got}.values())
        with gzip.open(out_path + ".tmp", "wt", encoding="utf-8") as f:
            f.write("".join(json.dumps(dict(x, by=x.get("by") or model), ensure_ascii=False) + "\n" for x in keep))
        os.replace(out_path + ".tmp", out_path)
        return len(keep)
    for i in range(0, len(jobs), batch):
        part = jobs[i:i + batch]
        facts = [j for j in part if j[0] != "none"]
        nones = [j for j in part if j[0] == "none"]
        for group, ask in ((facts, ASK_FACTS), (nones, ASK_NONE)):
            if not group or sent >= budget:
                continue
            lines = "\n".join(f"{n + 1}. " + (SAY[lab].format(o=o) if lab != "none" else f'"{o}"') for n, (lab, o) in enumerate(group))
            body = json.dumps({"model": model, "messages": [{"role": "user", "content": ask.format(k=per, facts=lines)}],
                               "temperature": 1.0, "max_tokens": 8000, "response_format": {"type": "json_object"},
                               "reasoning_effort": "low"}).encode()  # thinking counts against max_tokens: keep it short
            req = urllib.request.Request(url, body,
                                         {"Content-Type": "application/json", "Authorization": "Bearer " + key,
                                          "User-Agent": "mindbaton/1.0 (+self-hosted)"})
            for attempt in range(6):
                try:
                    with urllib.request.urlopen(req, timeout=180) as r:
                        text = json.load(r)["choices"][0]["message"]["content"]
                        out = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip()))
                    break
                except urllib.error.HTTPError as e:
                    wait = float(e.headers.get("retry-after") or 20) if e.code == 429 else 10
                    print(f"  HTTP {e.code}, waiting {wait:.0f}s", flush=True)
                    time.sleep(min(wait, 120) + 1)
                except (OSError, ValueError, KeyError, IndexError) as e:
                    print(f"  {type(e).__name__}, retrying", flush=True)
                    time.sleep(5)
            else:
                continue
            sent += 1
            for n, (lab, o) in enumerate(group):
                for msg in out.get(str(n + 1), []) if isinstance(out, dict) else []:
                    if isinstance(msg, str) and 3 <= len(msg) <= 300 and o.lower() in msg.lower():
                        got.append({"text": " ".join(msg.split()), "label": lab, "obj": o if lab != "none" else None})
        print(f"{min(i + batch, len(jobs))}/{len(jobs)} facts, {sent} requests, {save()} examples saved", flush=True)


def _margin(s):
    """How far a wrongly guessed fact beats 'none' in a clause that states nothing (None when 'none' wins)."""
    c = brain.Clause(s)
    sc = _score(W["rel"], clause_feats(c.words, c.tags))
    best = max(sc, key=sc.get) if sc else "none"
    return None if best == "none" else sc[best] - max([v for k, v in sc.items() if k != best] + [0.0])


def _label(s):
    got = read(s)
    return got[0][0] + got[0][1] if got else "none"


def _object(s, lab):
    got = read(s)
    return got[0][2] if got else None


def selfcheck():
    if not W:
        print("learn: no weights in assets/learn (python3 learn.py --train) — rules only")
        return
    assert read("what's the best laptop for coding?") == [], read("what's the best laptop for coding?")
    print(f"learn ok ({len(W['rel'])} + {len(W['span'])} features, margin {W['margin']})")


# ---- examples: slots and templates (sentences as people type them; never real messages) -------------------------------
P = lambda s: [x.strip() for x in s.split("|") if x.strip()]
POOLS = {
    "org": P("""Google|Microsoft|Amazon|Infosys|TCS|Wipro|Flipkart|Swiggy|Zomato|Razorpay|Stripe|Deloitte|Accenture|Netflix|Spotify|
        Uber|Airbnb|Meta|Apple|Adobe|Salesforce|Atlassian|Shopify|Freshworks|Zoho|Paytm|CRED|Ola|Byju's|Unacademy|IBM|Oracle|Intel|
        Nvidia|Samsung|Siemens|Bosch|KPMG|EY|PwC|McKinsey|Goldman Sachs|JP Morgan|HDFC Bank|ICICI|the bank|the hospital|a startup|
        the office|a law firm|the university|a school|the airport|a call center|a bakery|the clinic|a design studio|an agency|
        a hedge fund|the post office|a warehouse|the factory|a cafe|a hotel|the lab|a nonprofit|the newspaper"""),
    "place": P("""Pune|Mumbai|Bangalore|Bengaluru|Delhi|Chennai|Hyderabad|Kolkata|Jaipur|Lucknow|Goa|Kochi|Indore|Berlin|Munich|London|
        Manchester|Dublin|Paris|Lyon|Lisbon|Porto|Madrid|Barcelona|Amsterdam|Rotterdam|Zurich|Vienna|Prague|Warsaw|Stockholm|Oslo|
        Helsinki|Copenhagen|Toronto|Vancouver|Montreal|New York|Brooklyn|Boston|Seattle|Austin|Denver|Chicago|San Francisco|Los Angeles|
        Miami|Dubai|Abu Dhabi|Doha|Singapore|Tokyo|Osaka|Seoul|Sydney|Melbourne|Auckland|Nairobi|Lagos|Cape Town|Cairo|
        Istanbul|Athens|Rome|Milan|Mexico City|Buenos Aires|Sao Paulo|Bogota|Lima|Santiago"""),
    "role": P("""nurse|teacher|software engineer|designer|data analyst|doctor|lawyer|student|chef|pilot|accountant|product manager|
        photographer|electrician|freelancer|architect|barista|writer|developer|backend dev|frontend developer|researcher|
        pharmacist|dentist|consultant|mechanic|journalist|civil engineer|marketer|sales rep|therapist|translator|musician|
        video editor|data scientist|devops engineer|ux designer|professor|paramedic|firefighter|farmer"""),
    "ident": P("""vegan|vegetarian|pescatarian|diabetic|lactose intolerant|left-handed|colorblind|introvert|night owl|early riser|
        gluten free|sober|single|married|a new dad|a new mom|retired|pregnant|remote|self-employed|unemployed"""),
    "thing": P("""ps5|xbox|e-bike|macbook|macbook air|kindle|kindle paperwhite|golden retriever|tesla|iphone 15|pixel 8|gaming pc|
        thinkpad|drone|espresso machine|air fryer|3d printer|scooter|car|standing desk|nintendo switch|vr headset|synthesizer|
        electric guitar|camera|mirrorless camera|robot vacuum|smartwatch|apple watch|ipad|mechanical keyboard|nas|raspberry pi|
        motorbike|royal enfield|road bike|treadmill|coffee grinder|record player|air purifier|puppy|kitten|parrot|aquarium"""),
    "tool": P("""vim|neovim|vscode|linux|arch|fedora|ubuntu|windows|macos|notion|obsidian|figma|docker|postgres|python|excel|chrome|
        firefox|brave|spotify|whatsapp|telegram|jira|slack|git|emacs|tailscale|proxmox|todoist|trello|canva|lightroom|blender|
        davinci resolve|unity|godot|react|django|kubernetes|terraform|zsh|tmux|home assistant|jellyfin|plex|pihole|bitwarden|
        1password|anki|duolingo|google sheets|airtable|zapier|n8n|cursor|chatgpt|claude|perplexity"""),
    "like": P("""coffee|sushi|jazz|hiking|pickleball|thrillers|anime|cricket|football|k-dramas|pizza|lo-fi|board games|chess|yoga|
        cycling|photography|dark chocolate|spicy food|rainy days|podcasts|sci-fi|biryani|dosa|ramen|tacos|indie games|metal|
        techno|poetry|gardening|baking|running|swimming|camping|road trips|thai food|green tea|matcha|craft beer|wine|puzzles|
        standup comedy|horror movies|documentaries|true crime|f1|basketball|minimalism|mechanical keyboards|vinyl|sneakers"""),
    "avoid": P("""meat|sugar|alcohol|gluten|dairy|caffeine|fried food|junk food|red meat|pork|beef|eggs|soda|onion|garlic|
        seafood|nuts|peanuts|processed food|carbs|energy drinks"""),
    "skill": P("""japanese|spanish|rust|guitar|piano|python|go|french|german|korean|drawing|chess|swimming|calculus|sql|
        kubernetes|sign language|pottery|the violin|the drums|machine learning|react|typescript|photography|singing|salsa|
        mandarin|italian|arabic|statistics|system design|blender|woodworking|knitting|crochet|surfing|boxing"""),
    "project": P("""my budgeting app|an indie game|a novel|my thesis|a chrome extension|a discord bot|my portfolio site|a podcast|
        a youtube channel|a home automation setup|a startup|a mobile app|a board game|a recipe blog|a habit tracker|a newsletter|
        my first saas|an open source library|a cli tool|a telegram bot|a fantasy book|a short film|my dissertation|a mod|
        a weather station|a crypto bot|an ai assistant|a todo app|a music album|a comic"""),
    "play": P("""badminton|cricket|football|tennis|chess|guitar|piano|valorant|the drums|basketball|squash|pickleball|minecraft|
        volleyball|table tennis|golf|dota|league|fifa|the bass|the ukulele|poker|hockey|rugby"""),
    "want": P("""bike|new bike|ps5|macbook|kindle|camera|drone|house|car|new phone|gaming pc|standing desk|steam deck|vision pro|
        mechanical keyboard|espresso machine|new laptop|motorbike|tesla|puppy|guitar|3d printer|smartwatch|air purifier"""),
    "topic": P("""linear algebra|partial derivatives|lagrange multipliers|implicit functions|data structures|operating systems|
        computer networks|compound statements|pointers|recursion|sorting algorithms|binary trees|thermodynamics|organic chemistry|
        matrices|probability|integration|vectors|loops|arrays|file handling|memory management|process scheduling|normalization|
        sql joins|transactions|graph theory|dynamic programming|neural networks|regression|differential equations|
        several variables|conditional statements|storage classes|macros|bitwise operators|the preprocessor|cell biology|
        microeconomics|supply and demand|the french revolution|electromagnetism|optics|quantum mechanics|set theory|logic gates"""),
    "name": P("Karan|Priya|Sarah|Rahul|Ana|Sam|Leo|Meera|Arjun|Tom|Emma|Kenji|Fatima|Diego|Olga|Zoe|Omar|Lina|Raj|Chen"),
    "dur": P("2 years|three months|a decade|5 yrs|a while|ages|six months|8 years|a year|3 yrs|two weeks|forever"),
    "when": P("last week|yesterday|last month|in march|two weeks ago|recently|this year|over the weekend|a few days ago|today"),
    "day": P("monday|tuesday|friday|weekend|saturday|sunday|morning|shift|week"),
    "adj": P("amazing|exhausting|great|chaotic|fine|so good|brutal|intense|chill|wild|boring|fun"),
    "n": P("3|12|40|100|7|21|60|5"),
    "q": P("any tips|what should I do|how do I fix this|what do you think|any ideas|is that normal|help"),
}
PRE = [""] * 8 + ["so ", "btw ", "honestly ", "fyi ", "ok so ", "lol ", "yeah ", "update: ", "ngl ", "fun fact, ", "well ", "welp ",
                  "hey, ", "quick one: ", "anyway ", "oh and "]
POST = [""] * 8 + [" lol", " tbh", " btw", " haha", "!", "!!", " :)", " fr", " lmao", ".", " 🙂", " haha yeah", " ngl", " now", " lately"]

TEMPLATES = [
    ("+works at", "org", P("""[I ]work at {o}|[I'm ]working at {o}|[I've ]been at {o} for {dur}|[I'm ]at {o} now|just joined {o}|
        [I ]joined {o} {when}|[I ]started at {o} {when}|my job at {o} is {adj}|my team at {o} is {adj}|my boss at {o} is {adj}|
        [I'm ]a {role} at {o}|working for {o} these days|[I ]got hired by {o}|[I ]landed a job at {o}|switched jobs, now at {o}|
        new job at {o}!|{dur} at {o} and counting|another {day} at {o}|long {day} at {o}|back to work at {o} tomorrow|
        [I ]just accepted an offer from {o}|day one at {o}|first week at {o} done|[I ]lead a team at {o}|[I'm ]interning at {o}|
        my manager at {o} is {adj}|my desk at {o} is a mess|[I ]commute to {o} every day|payday at {o} finally|
        the cafeteria at {o} is {adj}|my coworkers at {o} are {adj}|[I ]do {role} work at {o}|been with {o} for {dur}|
        working at {o} has been {adj}|at {o} since {when}|my first job was at {o} and I'm still here""")),
    ("+lives in", "place", P("""[I ]live in {o}|[I'm ]living in {o}|[I'm ]based in {o}|[I ]moved to {o} {when}|[I ]just moved to {o}|
        [I ]relocated to {o}|[I ]moved to {o} after {dur} in {place}|moved back to {o} after {dur} away|
        [I ]left {place} and moved to {o}|[I've ]been in {o} for {dur}|[I'm ]back home in {o}|[I ]moved back to {o}|life in {o} is {adj}|
        {o} has been home for {dur}|home is {o} now|it's {adj} here in {o}|another {adj} day here in {o}|[I ]settled in {o}|
        [I ]rent a flat in {o}|my apartment in {o} is {adj}|[I ]stay in {o}|been living in {o} since {when}|new city, {o}!|
        just landed in {o} for good|finally moved into my place in {o}|living the {o} life now|[I'm ]a {o} local now|
        my neighbourhood in {o} is {adj}|the rent in {o} is killing me|[we ]just bought a flat in {o}|
        [I ]call {o} home|{o} is where I live now|living out of {o} these days""")),
    ("+from", "place", P("""[I'm ]originally from {o}|[I ]grew up in {o}|born and raised in {o}|[I ]was born in {o}|{o} is my hometown|
        hometown: {o}|[I'm ]from {o} originally|[I ]spent my childhood in {o}|my family is from {o}|[I'm ]a {o} kid at heart""")),
    ("+is", "role", P("""[I'm ]a {o}|[I ]work as a {o}|as a {o} I work long hours|{o} by profession|been a {o} for {dur}|
        full-time {o} here|[I'm ]a {o} by trade|{o} here, {q}|my job as a {o} is {adj}|life as a {o} is {adj}|
        [I ]became a {o} {when}|[I'm ]now a {o}|{dur} as a {o}|[I ]trained as a {o}|[I'm ]working as a {o} these days""")),
    ("+is", "ident", P("""[I'm ]{o}|been {o} for {dur}|been {o} {dur} now|{dur} {o} and counting|[I've ]been {o} since {when}|[I ]went {o} {when}|[I'm ]{o} now|
        {o} for {dur} now|proudly {o}|[I ]turned {o} {when}|[I am ]{o}, {q}|as someone {o} I have to be careful""")),
    ("+has", "thing", P("""[I ]bought a {o}|[I ]got a {o}|[I ]just got a {o}|got myself a {o}|treated myself to a {o}|
        [I ]finally bought the {o}|my new {o} arrived today|[I ]own a {o}|[I've ]got a {o}|[I ]picked up a {o} {when}|
        [I ]ordered a {o}|the {o} I bought {when} is {adj}|my {o} is {adj}|[I ]have a {o} at home|[I ]upgraded to a {o}|
        unboxed my {o} today|my {o} just got delivered|[I ]finally splurged on a {o}|bought the {o} {when}!|
        [we ]adopted a {o}|[I ]brought home a {o}|my {o} keeps acting up|[I ]set up my new {o}|just got a {o}, it's {adj}|
        [I ]caved and bought a {o}|the {o} came in today|my {o} is the best purchase ever|my {o} arrived {when}|
        my new {o} showed up today""")),
    ("+uses", "tool", P("""[I ]use {o}|[I'm ]using {o}|[I ]switched to {o}|{o} user here|{o} user for life|[I ]daily drive {o}|
        been daily driving {o} for {dur}|my setup runs on {o}|everything I do is in {o}|[I ]do all my notes in {o}|
        [I ]live in {o} all day|[I ]code in {o}|[I ]write everything in {o}|{o} is my daily driver|can't work without {o}|
        [I've ]been on {o} for {dur}|[I'm ]on {o} btw|team {o} all the way|[I ]moved everything to {o}|
        [I ]manage everything with {o}|my workflow is all {o}|[I ]run {o} on everything|[I ]rely on {o} daily|
        proud {o} user|{o} fan since {when}|{o} person through and through""")),
    ("+likes", "like", P("""[I ]love {o}|[I'm ]obsessed with {o}|{o} is my comfort food|{o} is my favourite|big fan of {o}|
        [I'm ]really into {o}|can't get enough of {o}|{o} is life|nothing beats {o}|[I ]could eat {o} every day|
        [I ]can't live without {o}|{o} makes me happy|[I'm ]a sucker for {o}|addicted to {o}|been binging {o} lately|
        [I ]enjoy {o}|{o} is the best thing ever|my guilty pleasure is {o}|weekends are for {o}|[I ]adore {o}|
        {o} is my thing|[I'm ]hooked on {o}|nothing like a bit of {o}|[I ]never get tired of {o}|{o} forever|
        nothing beats a good {o}|a good {o} always cheers me up|{o} lover here""")),
    ("+dislikes", "like", P("""[I ]hate {o}|[I ]can't stand {o}|not a {o} person|not a fan of {o}|{o} is overrated|
        {o} makes me feel sick|{o} makes me anxious|[I ]never liked {o}|ugh, {o}|[I ]despise {o}|{o} is the worst|
        [I ]really don't like {o}|{o}? no thanks|{o} gives me a headache|[I ]can't do {o}|{o} is not for me|
        [I ]find {o} boring|{o} ruins my day|[I ]loathe {o}|{o} is just not my thing|[I ]detest {o}|never been a {o} guy|
        {o} makes me sick, I hate it|{o} and me don't get along""")),
    ("+avoids", "avoid", P("""no more {o} for me|[I ]don't eat {o}|[I've ]cut out {o}|[I'm ]off {o} now|trying to avoid {o}|
        [I ]stay away from {o}|zero {o} for {dur} now|[I've ]stopped eating {o}|[I ]gave up {o} for lent|
        [I ]can't have {o}|[I ]don't do {o} anymore|{o}-free for {dur}|[I ]keep {o} out of my diet|no {o} please, {q}""")),
    ("+learning", "skill", P("""[I'm ]learning {o}|day {n} of learning {o}|[I ]started learning {o}|picking up {o} this year|
        [I'm ]teaching myself {o}|[I've ]been practicing {o}|taking {o} classes|[I'm ]trying to get better at {o}|
        {o} lessons every {day}|[I'm ]studying {o}|[I ]just began {o}|week {n} of {o}|doing a {o} course|
        [I ]signed up for {o} lessons|finally picking up {o}|{o} practice every night|[I'm ]getting into {o}|
        slowly getting the hang of {o}|my {o} is getting better""")),
    ("+working on", "project", P("""[I'm ]working on {o}|[I'm ]building {o}|still grinding on {o}|shipping {o} next week|
        [I'm ]making {o}|{o} is almost done|[I've ]been hacking on {o}|[I'm ]writing {o}|launching {o} soon|
        [I ]spent the weekend on {o}|progress on {o} is {adj}|my side project is {o}|deep in {o} right now|
        [I ]just started {o}|putting the finishing touches on {o}|[I'm ]prototyping {o}|all my evenings go into {o}""")),
    ("+plays", "play", P("""[I ]play {o}|[I ]play {o} every {day}|hit the courts for {o}|{o} every weekend with friends|
        [I'm ]on a {o} team|{o} night with the boys|[I've ]been playing {o} since {when}|[I'm ]part of a {o} club|
        {o} practice tonight|[I ]play {o} to unwind|[I ]never miss {o} on {day}|[I ]jam on {o} most nights""")),
    ("+wants", "want", P("""[I ]want to buy a {o}|saving up for a {o}|[I ]really want a {o}|[I'm ]eyeing a {o}|{o} is on my wishlist|
        [I ]need a new {o}|dreaming of a {o}|next purchase: {o}|[I'm ]going to get a {o} soon|[I've ]been wanting a {o}|
        putting money aside for a {o}|[I ]want a {o} so bad|[I'm ]so close to buying a {o}""")),
    ("-works at", "org", P("""[I ]quit my job at {o}|[I ]left {o}|no longer at {o}|my last day at {o} was {when}|
        [I ]got laid off from {o}|[I ]resigned from {o}|done with {o}, onto new things|[I ]don't work at {o} anymore|
        [I ]walked out of {o}|farewell {o}|[I ]handed in my notice at {o}""")),
    ("-lives in", "place", P("""[I ]moved out of {o}|[I ]left {o} {when}|no longer living in {o}|[I ]don't live in {o} anymore|
        goodbye {o}, it was fun|[I ]packed up and left {o}|moving out of {o} was hard""")),
    ("-uses", "tool", P("""not using {o} anymore|[I ]stopped using {o}|[I ]uninstalled {o}|[I ]ditched {o}|done with {o}, deleted the app|
        [I ]switched away from {o}|bye {o}|[I ]deleted my {o} account|[I ]gave up on {o}|[I ]moved off {o}|
        [I ]don't use {o} anymore|{o} is dead to me|[I ]quit {o} for good""")),
    ("-has", "thing", P("""[I ]sold my {o}|[I ]got rid of my {o}|my {o} got stolen|[I ]gave away my {o}|[I ]returned the {o}|
        [I ]don't have a {o} anymore|said goodbye to my {o}|[I ]traded in my {o}""")),
    ("-likes", "like", P("""{o} and I are done|[I ]don't like {o} anymore|[I'm ]over {o}|[I ]used to love {o}|
        fell out of love with {o}|[I've ]gone off {o}|{o} lost its magic for me|[I'm ]so done with {o}|
        [I ]can't believe I used to like {o}""")),
    ("-learning", "skill", P("""[I ]gave up on {o}|[I ]stopped learning {o}|[I ]quit {o} lessons|dropped {o} after {dur}|
        [I'm ]not learning {o} anymore|[I ]abandoned {o}|{o} wasn't for me, I stopped""")),
    ("-working on", "project", P("""[I ]abandoned {o}|shelved {o}|[I ]killed {o}|[I ]stopped working on {o}|
        [I'm ]putting {o} on hold|[I ]scrapped {o}|{o} is dead, I gave up""")),
    ("-plays", "play", P("""[I ]don't play {o} anymore|[I ]quit {o}|[I ]stopped playing {o}|retired from {o}|
        haven't played {o} in {dur}|hung up my {o} boots""")),
    ("none", "like", P("""what's the best {o}?|is {o} worth it?|how do I get into {o}|any tips for {o}?|where can I find {o}|
        can you recommend some {o}|how does {o} work|write a poem about {o}|explain {o} to me|give me a {o} recipe|
        make a list of {o} ideas|my friend loves {o}|my sister is into {o}|my brother hates {o}|they love {o}|
        {o} is popular these days|should I try {o}?|maybe I'll try {o} someday|if I liked {o} I'd go more|
        what if I tried {o}|I wonder if {o} is fun|would {o} be a good hobby?|{o} is trending again|
        {name} loves {o}|{name} is obsessed with {o}|{name} hates {o}|{name} is really into {o}|{name} can't stand {o}|
        tell me something about {o}|compare {o} with {like}|is {o} healthy?|why do people like {o}|{o} or {like}, which is better?|
        pros and cons of {o} and {like}|rank {o}, {like} and {like}""")),
    ("none", "org", P("""my friend works at {o}|{o} is hiring|{o} announced a new product|{o}'s API docs are great|
        {o} stock went up|is {o} a good place to work?|how do I get a job at {o}|draft an email to {o}|
        my brother just joined {o}|the {o} is closed today|{o} laid off a lot of people|what does {o} do?|
        should I apply to {o}?|compare {o} and another company|write a cover letter for {o}|{o} is down again|
        my dad retired from {o}|she works at {o}|he got an offer from {o}|if I worked at {o} I'd be rich|{name} works at {o}|
        {name} just joined {o}|{name} quit {o} last week|{name} got hired by {o}""")),
    ("none", "place", P("""they moved to {o} last year|{o} is beautiful in spring|is {o} expensive?|what's there to do in {o}|
        plan a trip to {o}|my cousin lives in {o}|how far is {o} from here|if I lived in {o} I'd bike everywhere|
        I wonder if {o} is expensive|the weather in {o} is wild|best food in {o}?|should I visit {o}?|
        my friend is from {o}|{o} is on my bucket list maybe|flights to {o} are cheap now|write about {o}|{name} moved to {o}|
        {name} lives in {o}|{name} grew up in {o}|{name} is based in {o} now""")),
    ("none", "thing", P("""should I buy a {o}?|is the {o} worth it?|compare the {o} and something else|how do I set up a {o}|
        my friend got a {o}|my brother bought a {o}|the {o} is on sale|which {o} should I get?|how much is a {o}?|
        review of the new {o}|my dad has a {o}|reset a {o}|fix my {o} settings|what's wrong with this {o}|
        compare the {o} and the {thing}|{o} or {thing}?|best deals on a {o} this week|{name} bought a {o}|{name} has a {o}|
        {name} just got a {o}""")),
    ("none", "tool", P("""how do I install {o}?|compare {o} and something else for me|is {o} free?|explain {o}|
        {o} released a new version|why is {o} so slow|write a {o} tutorial|what's better than {o}?|my team uses {o}|
        fix this {o} error|maybe I'll try {o} someday|how do I learn {o}|should I switch to {o}?|compare {o} and {tool} for me|
        {o} vs {tool}?|should I use {o} or {tool}|what's the difference between {o} and {tool}|set up {o} with {tool}|
        migrate this from {tool} to {o}|write a script for {o}""")),
    ("none", "topic", P("""{o}|introduction to {o}|basics of {o}|{o} and {topic}|method of {o}|applications of {o}|
        chapter {n} {o}|unit {n} {o}|{o} in practice|advanced {o}|types of {o}|properties of {o}|history of {o}|
        {o} for beginners|differentiation of {o}|limits and {o}|review of {o}|{o} explained|notes on {o}|{o} vs {topic}|
        functions of {o}|syllabus for {o}|{o} and its uses|solved problems on {o}|important questions on {o}""")),
    ("none", "tool", P("""{o} runs as a user service|{o} on port {n}|built to replace {o}|config for {o} lives in the data folder|
        registered {o} at user scope|plain http on the lan|{o} is a probed service|the dashboard uses {o} for disk usage|
        backups of {o} are kept for a week|{o} restarts on failure|{o} needs sudo to restart|logs go to the journal|
        same style as {o}|see the {o} notes|the server does no {o} calls|{o} was set up with a user account|
        {o} request failed|search for {o} failed|{o} returned an error|item name {o}|error in {o}|{o} timed out|
        connection to {o} refused|{o} not found|build failed on {o}|{o} and {tool} extensions|{o} with {tool} support|
        use {o} please|and just use {o}|take the logo from {o}|search the web for {o}|check on the agents|
        provide the link for the site|first publish the site on {o}|get the context first|tell me automatically|
        put it on {o}|make it use {o}|switch it to {o} instead|run it with {o}|and the app url|for the landing page|
        refer to {o} for the logo|no take the logo from {o}|i can provide {o} access|setting up this machine with {o}""")),
    ("none", "tool", P("""done i logged in {o}|i logged into {o}|signed in to {o}|i pushed it to {o}|uploaded it to {o}|
        i opened {o}|i restarted {o}|i ran it on {o}|i tried {o} just now|i clicked the {o} button|i sent it to {o}|
        {o} i think|{o} i guess|i think {o}|probably {o}|maybe {o}|it's {o} i think|yes do all of it|yes do all {n}|
        yes use {o}|no not {o}|yes {o}|nope, {o}|i checked {o}|i installed it just now|i copied it to {o}""")),
    ("none", "name", P("""{o} i think|{o} i guess|maybe {o}|ask {o}|i told {o}|{o} said it's fine|i met {o} today|thanks {o}|
        i called {o} yesterday|{o}?|was it {o}|i asked {o} about it""")),
    ("none", None, P("""ok do it|continue|looks good|try again|thanks, that works|fix the bug in the login page|why is my build so slow|
        can you explain how kubernetes works|summarize this article|translate this into french|what time is it in tokyo|
        I have no idea why this fails|I have a question|I have to finish this by friday|my budget is around {n}k|
        I think the second option is better|I need help with this code|I was wondering about that|I don't know|
        I agree with you|I just want it to work|I'm not sure about this|I'm confused|I'm back|I'm done for today|
        I have a meeting soon|I need to leave in 5 minutes|I tried that already|my code doesn't compile|
        my question is about the api|I meant the other one|I'll check tomorrow|I'm testing something""")),
]


if __name__ == "__main__":
    if "--write" in sys.argv:
        g = "--gemini" in sys.argv
        write(writer="gemini" if g else "groq", seed=29 if g else 13, budget=60 if g else 140, batch=10 if g else 20)
    else:
        train() if "--train" in sys.argv else selfcheck()
