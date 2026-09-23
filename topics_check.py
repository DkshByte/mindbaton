"""How well the topics match a hand-labelled answer key of YOUR OWN memories. Pairwise precision/recall over the labelled
memories that still exist. The key lives in data/private/topics_gold.json (git-ignored — it holds your real messages):

    {"topic name": ["normalised text of a memory", ...], "NOISE": [...memories that belong to no topic...]}

Keys are the `key` column of memory nodes (normalised text), so the key survives rebuilds.

    python3 topics_check.py [db]      # default: the server's data dir (MINDBATON_DATA), read-only
"""
import json, os, sqlite3, sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = os.path.join(HERE, "data", "private", "topics_gold.json")
if not os.path.exists(GOLD):
    print(f"No answer key at {os.path.relpath(GOLD, HERE)} — nothing to check (see the docstring to make one).")
    sys.exit(0)
import server  # noqa: E402  (after the early exit: only its DB path is used, honouring mindbaton.env)

path = sys.argv[1] if len(sys.argv) > 1 else server.DB
if not os.path.exists(path):
    sys.exit(f"No database at {path}")
gold = {k: t for t, keys in json.load(open(GOLD)).items() for k in keys}
db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
pred = {k: c if c is not None else "loose:" + k for k, c in
        db.execute("SELECT key, cluster FROM nodes WHERE kind='memory' AND status='active'") if k in gold}
real = [k for k in pred if gold[k] != "NOISE"]
tp = fp = fn = 0
for i, a in enumerate(real):
    for b in real[i + 1:]:
        same_g, same_p = gold[a] == gold[b], pred[a] == pred[b]
        tp += same_g and same_p
        fp += same_p and not same_g
        fn += same_g and not same_p
P, R = tp / ((tp + fp) or 1), tp / ((tp + fn) or 1)
print(f"precision {P:.3f}  recall {R:.3f}  F1 {2 * P * R / ((P + R) or 1):.3f}  "
      f"({len(real)} labelled memories, {len(gold) - len(pred)} no longer in the graph)")
byg = defaultdict(Counter)
for k in real:
    byg[gold[k]][pred[k]] += 1
for g, c in byg.items():
    if len(c) > 1:
        print("  split:", g[:50], dict(c))
