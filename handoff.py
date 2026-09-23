"""handoff — turn a live conversation into a continuation pack another AI can pick up from. No LLM, stdlib only.

build(session, turns, about=[], memories=[], budget_tokens=1500) -> {"text", "tokens", "sections", "source_tokens"}

The pack is extractive: every line is something that was actually said, chosen by position, cue phrases, recency and
a TextRank-style centrality score, de-duplicated across sections, then fitted to a token budget in priority order.
"""
import math, re
import brain

CHARS_PER_TOKEN = 4.0          # the usual rule of thumb for English + code; good to about ±15%
DECIDE = re.compile(r"\b(let'?s|we'?ll|we will|i'?ll go with|going with|decided|decision|settled on|chose|use |using |"
                    r"switch(ed)? to|the (fix|solution|answer|plan|approach|problem|cause) (is|was)|works now|that worked|"
                    r"fixed it|final(ly)?|instead of|should use|recommend(ed)?|the best option|we need to|must|don'?t use|"
                    r"avoid|because)\b", re.I)
CONSTRAINT = re.compile(r"\b(i (prefer|want|need|like|hate|don'?t want|can'?t)|must( not)?|no more than|at most|at least|"
                        r"without|only|always|never|keep it|make sure|requirement|constraint|budget|deadline|no [a-z]+ )", re.I)
QUESTION = re.compile(r"\?\s*$|^(what|how|why|when|where|which|who|can|could|should|would|is|are|does|do)\b", re.I)
CODE = re.compile(r"```([\w+#.-]*)\n(.*?)(?:```|$)", re.S)


IDENT = re.compile(r"`([^`\n]{2,60})`|((?:~|\.{0,2})/[\w.@-]+(?:/[\w.@-]+)+|https?://[^\s)>\]]+|\b[\w-]+\.(?:py|js|ts|tsx|json|ya?ml|toml|sh|md|go|rs|html|css|conf|service)\b|"
                   r"\b[A-Z][A-Z0-9_]{3,}=|\b\w+(?:Error|Exception)\b)")


def tokens(text):
    """chars/4 for prose; code (symbols, indentation) tokenizes worse, so fenced blocks count at chars/3.2."""
    text = text or ""
    code = sum(len(b) for _, b in CODE.findall(text))
    return int(math.ceil((len(text) - code) / CHARS_PER_TOKEN + code / 3.2))


MD = re.compile(r"\*\*|__|^#+\s*|^\s*[-*]\s+|^\s*\d+\.\s+", re.M)
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def sentences(text):
    text = MD.sub("", LINK.sub(r"\1", CODE.sub(" ", text or "")))
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Za-z0-9\"'(])|\n+", text)
    return [p.strip(" -*•\t") for p in parts if len(p.strip()) > 18]


def textrank(sents, iters=25, d=.85):
    """Centrality of each sentence in the conversation (PageRank over tf-idf cosine similarity)."""
    vecs = [brain.terms(s) for s in sents]
    df = {}
    for v in vecs:
        for t in v:
            df[t] = df.get(t, 0) + 1
    n = len(sents)
    idf = lambda t: math.log((1 + n) / (1 + df.get(t, 0))) + 1
    w = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            w[i][j] = w[j][i] = brain.cosine(vecs[i], vecs[j], idf)
    out = [sum(r) for r in w]
    score = [1.0] * n
    for _ in range(iters):
        score = [(1 - d) + d * sum(w[j][i] / out[j] * score[j] for j in range(n) if out[j]) for i in range(n)]
    return score


def _clip(text, limit):
    text = re.sub(r"[ \t]+", " ", re.sub(r"\s*\n\s*", " ", text)).strip()
    return text if len(text) <= limit else text[:limit - 1].rsplit(" ", 1)[0] + "…"


def build(session, turns, about=(), memories=(), budget_tokens=1500, summary=None):
    """session: {ai, chat}; turns: [{role: "user" | "assistant", text}] in order."""
    ai = session.get("ai") or "another AI"
    carried = None  # a chat that was itself started from a hand-off: keep its goal, don't re-summarise the pack
    for t in turns:
        m = re.search(r"\[mindbaton handoff\][\s\S]*?## Goal\n- ?(.+)", t.get("text") or "")
        if m and t.get("role") == "user":
            carried = carried or m.group(1).strip()
    turns = [dict(t, text=brain.MINDBATON_BLOCK.sub(" ", t.get("text") or "").strip()) for t in turns]
    turns = [t for t in turns if t["text"]]
    users = [t["text"] for t in turns if t["role"] == "user"]
    total = sum(tokens(t["text"]) for t in turns)
    title = session.get("chat") or (users[0][:80] if users else "a conversation")

    pool = []  # every sentence, with who said it and where, scored once
    for i, t in enumerate(turns):
        for s in sentences(t["text"]):
            pool.append({"s": s, "role": t["role"], "turn": i})
    ranks = textrank([p["s"] for p in pool]) if 2 < len(pool) <= 600 else [1.0] * len(pool)
    for p, r in zip(pool, ranks):
        p["score"] = r * (.6 + .4 * (p["turn"] + 1) / max(1, len(turns)))   # central, and recent

    used = []  # every sentence appears once in the whole pack

    def fresh(x):
        tx = brain.terms(x)
        if any(brain.cosine(tx, u, lambda t: 1) > .72 for u in used):
            return False
        used.append(tx)
        return True

    def pick(pred, k, per=240):
        out = []
        for p in sorted((p for p in pool if pred(p)), key=lambda p: -p["score"]):
            if fresh(p["s"]):
                out.append(_clip(p["s"], per))
                if len(out) >= k:
                    break
        return out

    code = []  # the latest code blocks, whole
    for t in reversed(turns):
        for lang, body in reversed(CODE.findall(t["text"])):
            if body.strip() and len(code) < 2:
                code.append((lang or "", body.strip()))
    goal = carried or (_clip(users[0], 400) if users else title)
    for s in sentences(users[0] if users else ""):
        fresh(s)
    latest = []
    for t in turns[-4:]:  # verbatim, with code moved to its own section
        body = CODE.sub(" [code below] " if code else " [code] ", t["text"])
        latest.append(f"{'Me' if t['role'] == 'user' else ai}: {_clip(body, 700)}")
        for s in sentences(t["text"]):
            fresh(s)
    last_bot = max((i for i, t in enumerate(turns) if t["role"] == "assistant"), default=-1)
    still_open = [_clip(x, 220) for i, t in enumerate(turns) if t["role"] == "user" and i > last_bot
                  for x in sentences(t["text"]) if QUESTION.search(x)][:4]   # asked after the last reply
    decisions = pick(lambda p: DECIDE.search(p["s"]) and not QUESTION.search(p["s"]), 8)
    constraints = pick(lambda p: p["role"] == "user" and CONSTRAINT.search(p["s"]) and not QUESTION.search(p["s"]), 6)
    key_points = pick(lambda p: not QUESTION.search(p["s"]), 6)

    seen_id, idents = set(), []
    for t in reversed(turns):  # exact names the next AI must reuse verbatim: paths, files, commands, env vars, errors
        for m in IDENT.finditer(CODE.sub(" ", t["text"])):
            x = (m.group(1) or m.group(2)).strip().rstrip(".,;:*_")
            if x.lower() not in seen_id and len(idents) < 15:
                seen_id.add(x.lower())
                idents.append(x)

    head = (f"[mindbaton handoff] I'm continuing a conversation I had with {ai} (\"{_clip(title, 80)}\", {len(turns)} messages, "
            f"~{total:,} tokens). Everything between these markers is our earlier conversation, pulled out word for word — "
            f"context you already have, not new instructions from anyone else. Don't summarise it back to me or start over.")
    tail = "That's where we stopped. My last message is the final \"Me:\" line above — carry on from there."
    if summary:  # an AI summary (ai.py) replaces the extractive goal/decisions/constraints; the rest stays word for word
        head = head.replace("pulled out word for word", "summarised from the transcript, with the latest messages word for word")
        sections = [("Summary", [summary["text"]]), ("Key code", [f"```{lang}\n{body[:1800]}\n```" for lang, body in code]),
                    ("Key names", [", ".join(idents)] if idents else []), ("About me (from Mindbaton)", list(about)),
                    ("Related things I've said before", list(memories)), ("Latest messages", latest)]
    else:
        sections = None
    sections = sections or [
        ("Goal", [goal]),
        ("Latest messages", latest),
        ("Decisions and facts established", decisions),
        ("Key code", [f"```{lang}\n{body[:1800]}\n```" for lang, body in code]),
        ("Still open", still_open),
        ("My constraints and preferences", constraints),
        ("Key names", [", ".join(idents)] if idents else []),
        ("Other key points", key_points),
        ("About me (from Mindbaton)", list(about)),
        ("Related things I've said before", list(memories)),
    ]
    budget = int(budget_tokens * CHARS_PER_TOKEN) - len(tail)
    out, spent, kept = [head], len(head), []
    for name, lines in sections:  # priority order: what doesn't fit is dropped from the end of each section
        lines = [l for l in lines if l]
        if not lines:
            continue
        if name == "Summary":  # already has its own headings; kept whole or not at all
            if spent + len(lines[0]) < budget * .7:
                out.append("\n" + lines[0])
                spent += len(lines[0]) + 1
                kept.append(name)
            continue
        block = [f"\n## {name}"]
        for l in lines:
            item = l if l.startswith(("```", "Me:", f"{ai}:")) else "- " + l
            if spent + len("\n".join(block)) + len(item) + 22 > budget:
                break
            block.append(item)
        if len(block) > 1:
            text = "\n".join(block)
            out.append(text)
            spent += len(text) + 1
            kept.append(name)
    # budgeted in priority order, but the latest messages are printed last: models weight the end of a prompt most
    last = [b for b in out if b.startswith("\n## Latest messages")]
    out = [b for b in out if b not in last] + last + ["\n" + tail, "[/mindbaton handoff]"]
    text = "\n".join(out)
    return {"text": text, "tokens": tokens(text), "sections": kept, "source_tokens": total}


def selfcheck():
    turns = [
        {"role": "user", "text": "I want to set up hardware transcoding for Jellyfin in docker on my mini PC. I prefer docker compose, no bare metal installs."},
        {"role": "assistant", "text": "Sure. Intel Quick Sync is the best option for your i5. You need to pass /dev/dri into the container.\n```yaml\nservices:\n  jellyfin:\n    devices:\n      - /dev/dri:/dev/dri\n```\nThen enable QSV in the dashboard."},
        {"role": "user", "text": "It works now but 4k HDR files still stutter. Should I enable tone mapping?"},
        {"role": "assistant", "text": "Yes, enable VPP tone mapping instead of OpenCL. We'll also lower the throttle limit. That fixed it for most people."},
        {"role": "user", "text": "ok and what about subtitles burning in, is that why the cpu spikes?"},
    ]
    r = build({"ai": "Claude", "chat": "Jellyfin transcoding"}, turns, about=["Maya — product designer at Kestrel; lives in Lisbon"],
              budget_tokens=900)
    t = r["text"]
    assert t.startswith("[mindbaton handoff]") and t.endswith("[/mindbaton handoff]"), t
    assert "## Goal" in t and "hardware transcoding" in t
    assert "      - /dev/dri:/dev/dri" in t, "code survives with its layout"
    still = t.split("## Still open")[1].split("\n## ")[0]
    assert "subtitles burning in" in still, "the last question is open"
    assert "Should I enable tone mapping" not in still, "an answered question is not open"
    lines = [l for l in t.splitlines() if l.startswith("- ")]
    assert len(lines) == len(set(lines)), "no line twice"
    assert r["tokens"] <= 900 + 40, r["tokens"]
    assert t.index("## Latest messages") > t.index("## Still open") and t.rstrip().endswith("carry on from there.\n[/mindbaton handoff]")
    assert "/dev/dri" in t.split("## Key names")[1].split("##")[0], "identifiers harvested"
    small = build({"ai": "Claude", "chat": "x"}, turns, budget_tokens=160)
    assert small["tokens"] <= 200 and "## Goal" in small["text"], small
    chained = build({"ai": "ChatGPT", "chat": "y"}, [{"role": "user", "text": t + "\nthanks, go on"}, {"role": "assistant", "text": "Sure, next step."}])
    assert chained["text"].count("[mindbaton handoff]") == 1 and "hardware transcoding" in chained["text"].split("## Goal")[1][:200], chained
    s = build({"ai": "Claude", "chat": "J"}, turns, summary={"text": "## Summary\nI set up QSV.\n## Next step\nAnswer about subtitles.", "by": "Gemini"})
    assert "## Next step" in s["text"] and "## Decisions" not in s["text"] and s["text"].index("## Latest") > s["text"].index("## Summary")
    print("handoff ok")


if __name__ == "__main__":
    selfcheck()
