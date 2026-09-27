"""sense — what a sentence means, as a vector. Stdlib only, offline, the same numbers on every computer.

A static embedding table (assets/sense: Model2Vec potion-base-8M, MIT, distilled from BAAI's bge-base-en-v1.5): every
word piece has a 256-number vector, and a sentence is the normalised mean of its pieces. Nothing runs but a lookup, so a
sentence takes about a millisecond. "what do I do for fun" lands near "I love cricket"; "how do I take my coffee" near
"I drink my coffee black". Recall, links between memories and duplicates use it next to the words themselves.

    python3 sense.py            # self-check
    python3 sense.py --fetch    # download potion-base-8M and write assets/sense (int8 with a scale per row, ~7.7 MB)

Without assets/sense, vec() returns None and everything works on words alone.
"""
import array, functools, math, os, struct, sys, unicodedata
from operator import add, mul

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "sense")
MODEL = "minishlab/potion-base-8M"


def _load():
    try:
        with open(os.path.join(DIR, "vocab.txt"), encoding="utf-8") as f:
            vocab = {w: i for i, w in enumerate(f.read().split("\n"))}
        with open(os.path.join(DIR, "vectors.bin"), "rb") as f:
            raw = f.read()
    except OSError:
        return {}, None, None, 0
    magic, n, d = struct.unpack_from("<4sII", raw)
    if magic != b"MBS1" or n != len(vocab):
        return {}, None, None, 0
    scales = array.array("f")
    scales.frombytes(raw[12:12 + 4 * n])
    if sys.byteorder == "big":
        scales.byteswap()
    return vocab, scales, memoryview(raw)[12 + 4 * n:], d


VOCAB, SCALES, TABLE, DIM = _load()
_rows = {}  # word piece -> its vector, decoded on first use (a personal vocabulary is a few thousand pieces)


def _row(i):
    r = _rows.get(i)
    if r is None:
        q = array.array("b")
        q.frombytes(TABLE[i * DIM:(i + 1) * DIM])
        s = SCALES[i]
        r = _rows[i] = array.array("f", [x * s for x in q])
    return r


def _punct(c):
    o = ord(c)
    return 33 <= o <= 47 or 58 <= o <= 64 or 91 <= o <= 96 or 123 <= o <= 126 or unicodedata.category(c).startswith("P")


@functools.lru_cache(maxsize=50000)
def _pieces(word):
    """WordPiece: the longest known start, then '##' continuations; a word with an unknown part is dropped ([UNK])."""
    if len(word) > 100:
        return ()
    out, s = [], 0
    while s < len(word):
        e = len(word)
        while e > s and (word[s:e] if s == 0 else "##" + word[s:e]) not in VOCAB:
            e -= 1
        if e == s:
            return ()
        out.append(VOCAB[word[s:e] if s == 0 else "##" + word[s:e]])
        s = e
    return tuple(out)


def tokens(text):
    """BERT's uncased pre-tokenizer (lower case, accents off, punctuation split) + WordPiece -> piece ids."""
    # ponytail: CJK characters aren't split one per token as BERT does; they mostly fall out as unknown pieces
    t = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
    ids = []
    for w in t.split():
        cur = ""
        for c in w:
            if _punct(c):
                if cur:
                    ids += _pieces(cur)
                    cur = ""
                ids += _pieces(c)
            else:
                cur += c
        if cur:
            ids += _pieces(cur)
    return ids


def vec(text):
    """A sentence -> unit vector (array of floats), or None without the table or without a known piece."""
    if not DIM:
        return None
    acc = None
    for i in tokens(text or ""):
        acc = _row(i) if acc is None else list(map(add, acc, _row(i)))
    if acc is None:
        return None
    n = math.sqrt(sum(map(mul, acc, acc))) or 1.0
    return array.array("f", [x / n for x in acc])


def weight(word):
    """How much a word counts: the length of its pieces' summed vectors (the table weighs rare words heavier)."""
    ids = tokens(word or "")
    if not ids:
        return 0.0
    s = _row(ids[0]) if len(ids) == 1 else [sum(x) for x in zip(*(_row(i) for i in ids))]
    return math.sqrt(sum(map(mul, s, s)))


def cos(a, b):
    return sum(map(mul, a, b)) if a is not None and b is not None else 0.0


def sig(v):
    """Sign bits as one int: memories whose bits mostly agree point the same way (a cheap first cut before cosines)."""
    return sum(1 << i for i, x in enumerate(v) if x > 0)


popcount = getattr(int, "bit_count", None) or (lambda x: bin(x).count("1"))  # int.bit_count is Python 3.10+


def pack(v):
    return v.tobytes() if v is not None else None


def unpack(b):
    if not b:
        return None
    a = array.array("f")
    a.frombytes(b)
    return a


def fetch():
    """Download the model once and write it the way _load reads it: vocab.txt + vectors.bin (int8, a scale per row)."""
    import json, urllib.request
    base = f"https://huggingface.co/{MODEL}/resolve/main/"
    raw = urllib.request.urlopen(base + "model.safetensors", timeout=300).read()
    tok = json.loads(urllib.request.urlopen(base + "tokenizer.json", timeout=120).read())
    n = struct.unpack("<Q", raw[:8])[0]
    head = json.loads(raw[8:8 + n])["embeddings"]
    assert head["dtype"] == "F32", head
    (rows, d), (a, b) = head["shape"], head["data_offsets"]
    m = array.array("f")
    m.frombytes(raw[8 + n + a:8 + n + b])
    vocab = [w for w, _ in sorted(tok["model"]["vocab"].items(), key=lambda x: x[1])]
    assert len(vocab) == rows and not any("\n" in w for w in vocab)
    scales, q = array.array("f"), array.array("b")
    for i in range(rows):
        row = m[i * d:(i + 1) * d]
        s = max(map(abs, row)) / 127 or 1.0
        scales.append(s)
        q.extend(max(-127, min(127, round(x / s))) for x in row)
    os.makedirs(DIR, exist_ok=True)
    for name, data in (("vocab.txt", "\n".join(vocab).encode()), ("vectors.bin", struct.pack("<4sII", b"MBS1", rows, d)
                                                                  + scales.tobytes() + q.tobytes())):
        tmp = os.path.join(DIR, name + ".tmp")
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, os.path.join(DIR, name))
    print(f"wrote {rows} pieces x {d} dims to {DIR}")


def selfcheck():
    if not DIM:
        print("sense: no table in assets/sense (python3 sense.py --fetch) — words only")
        return
    v = {t: vec(t) for t in ("I love cricket", "what do I do for fun", "my coffee is black", "how do I take my coffee",
                             "the esp32 audio cuts out")}
    assert abs(cos(v["I love cricket"], v["I love cricket"]) - 1) < 1e-4
    assert cos(v["what do I do for fun"], v["I love cricket"]) > cos(v["what do I do for fun"], v["the esp32 audio cuts out"])
    assert cos(v["how do I take my coffee"], v["my coffee is black"]) > cos(v["how do I take my coffee"], v["I love cricket"])
    assert vec("") is None and unpack(pack(v["I love cricket"])) == v["I love cricket"]
    print(f"sense ok ({len(VOCAB)} pieces x {DIM})")


if __name__ == "__main__":
    fetch() if "--fetch" in sys.argv else selfcheck()
