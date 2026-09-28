"""deep — Mindbaton's own model reads, in the background, the messages the rules couldn't. Optional: without it
everything works as before.

- The model: a Qwen3.5-2B fine-tuned on made-up examples only (train/brain-2b.ipynb), 1.3 GB, from the Hugging Face repo
  in MINDBATON_BRAIN_MODEL. On a test it never saw it read 28 of 30 everyday facts, against 14 for the rules alone.
- The engine: llama.cpp's llama-server (MIT), one pinned build, downloaded once into <data>/brain with the model, run at
  low priority on half the cores, stopped after a few idle minutes and paused on battery. Or any OpenAI-compatible
  server in MINDBATON_BRAIN_URL (a llama-server or LM Studio on another computer): then nothing is downloaded here.
- It is asked only about messages in which the rules found nothing firm, one at a time, newest first. The rules check
  every answer (check): its words must be in the message, the relation one Mindbaton knows, and a new fact must sit in a
  statement, not a question or a maybe. What it read is kept with the capture, so a rebuild replays it without asking.

MINDBATON_BRAIN = auto (on with 12 GB of memory or more) | on | off.
    python3 deep.py                 # self-check against a stand-in server (no model needed)
    python3 deep.py --try "text"    # download what's missing, start the engine, read one message
"""
import glob, json, os, platform, re, socket, subprocess, sys, tarfile, threading, time, urllib.request, zipfile
import brain, learn

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = "b11223"  # llama.cpp build: pinned, so every install runs the engine that was tested
MODEL = os.environ.get("MINDBATON_BRAIN_MODEL", "1972521116s/mindbaton-brain-2b")
URL = re.sub(r"/v1/?$", "", os.environ.get("MINDBATON_BRAIN_URL", "").strip().rstrip("/"))
MODE = os.environ.get("MINDBATON_BRAIN", "auto").strip().lower()
IDLE_S = 300
RELS = {"works at", "lives in", "from", "is", "has", "uses", "likes", "dislikes", "avoids", "learning", "working on", "plays",
        "wants", "studies", "allergic to", "built", "wants to visit", "wants to try", "plans to move to"} | brain.KIN
STATE = {"state": "off", "read": 0, "left": None, "progress": None, "error": None, "sec": None, "dl": None}
FORCED = PAUSED = False  # an admin asked to re-read everything (Setup, with warnings) / paused it
RUN = {"graphs": None, "lock": None, "thread": None, "engine": None}


def home():
    return os.path.join(os.path.expanduser(os.environ.get("MINDBATON_DATA") or os.path.join(HERE, "data")), "brain")


def memory_gb():
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30
    except (ValueError, OSError, AttributeError):
        pass
    try:  # Windows
        import ctypes

        class M(ctypes.Structure):
            _fields_ = [("n", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(f, ctypes.c_ulonglong) for f in "abcdefg"]
        m = M()
        m.n = ctypes.sizeof(M)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.a / 2 ** 30
    except Exception:
        return 0


def asset():
    """The llama.cpp build for this computer, or None (then only MINDBATON_BRAIN_URL can work)."""
    m = platform.machine().lower()
    arch = "arm64" if m in ("arm64", "aarch64") else "x64" if m in ("x86_64", "amd64") else None
    name = {"linux": f"ubuntu-{arch}.tar.gz", "darwin": f"macos-{arch}.tar.gz",
            "win32": "win-cpu-x64.zip" if arch == "x64" else None}.get(sys.platform) if arch else None
    return name and f"https://github.com/ggml-org/llama.cpp/releases/download/{BUILD}/llama-{BUILD}-bin-{name}"


def enabled():
    return MODE != "off" and bool(URL or asset()) and (MODE == "on" or bool(URL) or FORCED or memory_gb() >= 12)


def on_battery():
    """True on a laptop running on its battery: the model waits for the charger (MINDBATON_BRAIN_BATTERY=1 reads anyway)."""
    if os.environ.get("MINDBATON_BRAIN_BATTERY") == "1":
        return False
    try:
        if sys.platform == "darwin":
            return "Battery Power" in subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
        if os.name == "nt":
            import ctypes

            class P(ctypes.Structure):
                _fields_ = [("ac", ctypes.c_byte), ("flag", ctypes.c_byte), ("pct", ctypes.c_byte), ("r", ctypes.c_byte),
                            ("life", ctypes.c_ulong), ("full", ctypes.c_ulong)]
            p = P()
            ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(p))
            return p.ac == 0
        mains = [p for p in glob.glob("/sys/class/power_supply/*/type") if open(p).read().strip() == "Mains"]
        return bool(mains) and all(open(os.path.join(os.path.dirname(p), "online")).read().strip() == "0" for p in mains)
    except Exception:
        return False


def _get(url, path, label):
    """Download to path (via path.part, so a cut connection never leaves half a file), showing progress in STATE."""
    req = urllib.request.Request(url, headers={"User-Agent": "mindbaton"})
    with urllib.request.urlopen(req, timeout=60) as r, open(path + ".part", "wb") as f:
        total, done = int(r.headers.get("Content-Length") or 0), 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            STATE["progress"] = f"downloading the {label}: " + (f"{done * 100 // total}%" if total else f"{done >> 20} MB")
            STATE["dl"] = {"what": label, "done": done, "total": total}
    os.replace(path + ".part", path)
    STATE["progress"] = STATE["dl"] = None


def fetch():
    """The engine and the model, downloaded once into <data>/brain -> (llama-server, model file)."""
    d = home()
    os.makedirs(d, exist_ok=True)
    find = lambda: sorted(glob.glob(os.path.join(d, "**", "llama-server*"), recursive=True))
    if not find():
        url = asset()
        if not url:
            raise RuntimeError("no llama.cpp build for this computer: set MINDBATON_BRAIN_URL")
        arc = os.path.join(d, url.rsplit("/", 1)[1])
        _get(url, arc, "engine")
        if arc.endswith(".zip"):
            zipfile.ZipFile(arc).extractall(d)
        else:
            with tarfile.open(arc) as t:
                t.extractall(d, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        os.remove(arc)
    ggufs = glob.glob(os.path.join(d, "*.gguf"))
    if not ggufs:
        with urllib.request.urlopen(f"https://huggingface.co/api/models/{MODEL}/tree/main", timeout=30) as r:
            files = [f["path"] for f in json.load(r) if f["path"].lower().endswith(".gguf")]
        name = next((f for f in files if "q4_k_m" in f.lower()), files[0] if files else None)
        if not name:
            raise RuntimeError(f"no model file in huggingface.co/{MODEL}")
        ggufs = [os.path.join(d, os.path.basename(name))]
        _get(f"https://huggingface.co/{MODEL}/resolve/main/{name}", ggufs[0], "model")
    exe = [p for p in find() if not p.endswith((".so", ".dll", ".dylib"))]
    if os.name != "nt":
        os.chmod(exe[0], 0o755)
    return exe[0], ggufs[0]


class Engine:
    """llama-server while there's reading to do: low priority, half the cores, stopped when idle."""

    def __init__(self):
        self.proc, self.url = None, URL or None

    def up(self):
        if URL:
            return URL
        if self.proc and self.proc.poll() is None:
            return self.url
        exe, model = fetch()
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        args = [exe, "-m", model, "--host", "127.0.0.1", "--port", str(port), "-c", "2048", "-np", "1", "--jinja",
                "-t", str(max(1, (os.cpu_count() or 2) // 2))]
        kw = {"creationflags": getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)} if os.name == "nt" else \
            {"preexec_fn": lambda: os.nice(19)}  # the owner's work comes first
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=open(os.path.join(home(), "engine.log"), "ab"), **kw)
        self.url = f"http://127.0.0.1:{port}"
        for _ in range(180):  # loading 1.3 GB from a slow disk can take a while
            if self.proc.poll() is not None:
                raise RuntimeError("the engine stopped while starting (see brain/engine.log)")
            try:
                urllib.request.urlopen(self.url + "/health", timeout=2).read()
                return self.url
            except Exception:
                time.sleep(1)
        self.down()
        raise RuntimeError("the engine didn't start in 3 minutes")

    def usage(self):
        """What the running engine takes now: {memory: bytes, cpu: % of the whole computer} or None when it's off."""
        if not (self.proc and self.proc.poll() is None):
            return None
        pid = self.proc.pid
        try:
            if sys.platform.startswith("linux"):
                rss = int(re.search(r"VmRSS:\s+(\d+)", open(f"/proc/{pid}/status").read())[1]) * 1024
                f = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()
                now, spent = time.time(), (int(f[11]) + int(f[12])) / os.sysconf("SC_CLK_TCK")
                last, self.cpu_mark = getattr(self, "cpu_mark", None), (now, spent)
                pct = (spent - last[1]) / (now - last[0]) * 100 if last and now > last[0] else None  # since the last look
            else:  # macOS: ps gives memory and a recent CPU share
                out = subprocess.run(["ps", "-o", "rss=,%cpu=", "-p", str(pid)], capture_output=True, text=True, timeout=5).stdout.split()
                rss, pct = int(out[0]) * 1024, float(out[1])
        except Exception:
            return None
        return {"memory": rss, "cpu": None if pct is None else round(pct / (os.cpu_count() or 1), 1)}

    def down(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None


def ask(base, text, timeout=180):
    """One message -> the facts the model reads in it (unchecked)."""
    body = {"model": os.environ.get("MINDBATON_BRAIN_NAME", "mindbaton-brain-2b"), "temperature": 0, "max_tokens": 300,
            "messages": [{"role": "system", "content": learn.SYSTEM}, {"role": "user", "content": text}],
            "response_format": {"type": "json_object"}, "chat_template_kwargs": {"enable_thinking": False}, "cache_prompt": True}
    req = urllib.request.Request(base + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = re.sub(r"<think>[\s\S]*?</think>", "", json.load(r)["choices"][0]["message"]["content"] or "")
    try:
        facts = json.loads(out[out.find("{"):out.rfind("}") + 1])["facts"]
    except (ValueError, KeyError, TypeError):
        return []
    return facts if isinstance(facts, list) else []


def check(text, facts):
    """The rules' veto on what the model read: its words must be in the message, the relation one Mindbaton knows, about
    the user or someone the message names, and a new fact must sit in a statement, not a question or a maybe."""
    low, out = text.lower(), []
    clauses = brain.sentences(brain.clean(text)) or [text]
    for f in facts[:8]:
        if not isinstance(f, dict):
            continue
        op, who, rel, what = f.get("op"), str(f.get("who") or "").strip(), str(f.get("rel") or "").strip().lower(), \
            str(f.get("what") or "").strip()
        wl = what.lower()
        if op not in ("+", "-") or rel not in RELS or not what or len(what.split()) > 6 or wl not in low or \
                wl in brain.STOP or wl in brain.PRON or "[secret]" in wl or not who or who != "me" and who.lower() not in low:
            continue
        if op == "-" and who != "me":
            continue
        clause = next((c for c in clauses if wl in c.lower()), text)
        if op == "+" and brain.mood(clause) != "statement":
            continue
        fact = {"op": op, "who": who, "rel": rel, "what": what}
        if fact not in out:
            out.append(fact)
    return out


def chat(text, url, site):
    """A message someone typed in a chat: not an agent's notes, not a tool's structured fact, not a pasted document."""
    return not (url or "").startswith("memory://") and site != "agent" and len(text) <= 1500


def need(text, url, site):
    """Is the model worth asking? Only chat in which the rules found no firm fact about the user."""
    if not chat(text, url, site):
        return False
    return any(m["mood"] == "statement" and m["type"] != "task" and
               not any(r[0] == "me" and r[1] not in brain.KIN for r in m["relations"]) for m in brain.analyse(text))


def step(graphs, lock, eng):
    """Read the newest unread message of any account. -> True if there was one."""
    job, left = None, 0
    with lock:
        for g in graphs():
            row, n = g.unread()
            left += n
            if not n and g.meta("deep_force") == "1":  # everything re-read: the graph once more from the captures, cleanly
                g.meta("deep_force", "")
                g.rebuild()
            if row and not job:
                job = (g, g.meta("deep_force") == "1") + tuple(row)
    STATE["left"] = left
    if not job:
        return False
    g, forced, cid, text, url, site = job
    facts = None
    if forced and chat(text, url, site) and any(brain.mood(c) == "statement" for c in brain.sentences(brain.clean(text))) \
            or need(text, url, site):  # forced: every statement, not only where the rules found nothing; never a question
        STATE["state"], t0 = "reading", time.time()
        facts = check(text, ask(eng.up(), text))
        dt = time.time() - t0
        STATE["sec"] = round(dt if STATE["sec"] is None else .8 * STATE["sec"] + .2 * dt, 2)
    with lock:
        g.deep_read(cid, facts or [], f"{MODEL}@{BUILD}")
        if facts:
            g.dirty = True
    STATE["read"] += facts is not None
    return True


def work(graphs, lock, stop=None):
    """The background reader: reads while there is something to read and the laptop is plugged in; idle -> engine off."""
    eng, last = Engine(), time.time()
    RUN["engine"] = eng
    while not (stop and stop.is_set()):
        if PAUSED:
            STATE["state"] = "paused"
            eng.down()
            time.sleep(5)
            continue
        if not enabled() or on_battery():
            STATE["state"] = "paused: on battery" if enabled() else "off"
            eng.down()
            time.sleep(60)
            continue
        try:
            if step(graphs, lock, eng):
                last = time.time()
                continue
            STATE["state"] = "ready"
        except Exception as e:  # no network, a broken download, a busy remote server: try again later
            STATE["state"], STATE["error"] = "waiting", f"{type(e).__name__}: {e}"[:300]
            eng.down()
            time.sleep(300)
        if time.time() - last > IDLE_S:
            eng.down()
        time.sleep(15)
    eng.down()


def start(graphs, lock):
    RUN.update(graphs=graphs, lock=lock)
    if enabled() and not (RUN["thread"] and RUN["thread"].is_alive()):
        STATE["state"] = "starting"
        RUN["thread"] = threading.Thread(target=work, args=(graphs, lock), daemon=True, name="deep")
        RUN["thread"].start()


def force(g):
    """An admin asked (with warnings) to re-read every chat message of this account with the model: what it read before is
    set aside, "is it needed" is skipped, and when all is read the graph is rebuilt once, so it holds this reading only."""
    global FORCED, PAUSED
    if MODE == "off":
        raise ValueError("the model is turned off in this install (MINDBATON_BRAIN=off)")
    if not (URL or asset()):
        raise ValueError("this computer can't run the model: set MINDBATON_BRAIN_URL to a model server on another computer")
    g.db.execute("UPDATE captures SET extra=json_remove(extra, '$.deep') WHERE json_extract(extra, '$.deep') IS NOT NULL")
    g.meta("deep_force", "1")
    FORCED, PAUSED = True, False
    if RUN["graphs"]:
        start(RUN["graphs"], RUN["lock"])
    return {"messages": g.unread()[1]}


def pause(paused):
    global PAUSED
    PAUSED = bool(paused)
    return {"paused": PAUSED}


def status():
    d = home()
    disk = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(d) for f in fs) if os.path.isdir(d) else 0
    return dict(STATE, enabled=enabled(), paused=PAUSED, model=MODEL, engine=URL or BUILD, mode=MODE, can=bool(URL or asset()),
                memory_gb=round(memory_gb(), 1), downloaded=bool(URL or glob.glob(os.path.join(d, "*.gguf"))), remote=bool(URL),
                disk=disk, usage=RUN["engine"].usage() if RUN["engine"] else None)


def selfcheck():
    """Against a stand-in OpenAI-compatible server: facts applied, made-up ones vetoed, kept for rebuilds."""
    import http.server, server
    said = {"5-a-side football every thursday after work": [{"op": "+", "who": "me", "rel": "plays", "what": "football"}],
            "zero caffeine since march": [{"op": "+", "who": "me", "rel": "avoids", "what": "caffeine"},
                                          {"op": "+", "who": "me", "rel": "likes", "what": "tennis"}],     # not in the message
            "should I get a ps5?": [{"op": "+", "who": "me", "rel": "wants", "what": "ps5"}]}                # a question

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            b = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            out = json.dumps({"choices": [{"message": {"content": json.dumps({"facts": said.get(b["messages"][1]["content"], [])})}}]})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(out.encode())

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    global URL
    old, URL = URL, f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        g, lock, eng = server.Graph(":memory:"), threading.RLock(), Engine()
        for i, t in enumerate(["I live in Pune", *said]):
            g.ingest(t, "chatgpt.com", ts=time.time() - 3600 + i)
        while step(lambda: [g], lock, eng):
            pass
        rels = lambda: {(a, r, b) for a, r, b in ((x["src_key"], x["rel"], x["dst_key"]) for x in (
            dict(zip(("src_key", "rel", "dst_key"), row)) for row in g.db.execute(
                "SELECT s.key, x.rel, d.key FROM edges x JOIN nodes s ON s.id = x.src JOIN nodes d ON d.id = x.dst")))}
        have = rels()
        assert {("me", "plays", "football"), ("me", "avoids", "caffeine"), ("me", "lives in", "pune")} <= have, have
        assert ("me", "likes", "tennis") not in have and ("me", "wants", "ps5") not in have, "vetoed"
        assert g.unread() == (None, 0) and STATE["read"] == 2, (g.unread(), STATE)  # not asked: Pune (rules) and the question
        global FORCED
        assert force(g)["messages"] == 4 and g.meta("deep_force") == "1"
        while step(lambda: [g], lock, eng):
            pass
        step(lambda: [g], lock, eng)  # nothing left: the forced pass ends with one rebuild
        assert not g.meta("deep_force") and STATE["read"] == 5, STATE  # forced: "I live in Pune" asked too; the question never
        assert {("me", "plays", "football"), ("me", "avoids", "caffeine")} <= rels()
        FORCED = False
        srv.shutdown()
        g.rebuild()  # the stand-in is gone: a rebuild replays what was read
        assert {("me", "plays", "football"), ("me", "avoids", "caffeine")} <= rels(), "kept with the capture"
    finally:
        URL = old
        srv.server_close()
    print("deep ok")


if __name__ == "__main__":
    if "--try" in sys.argv:
        e = Engine()
        try:
            t = sys.argv[sys.argv.index("--try") + 1]
            print(json.dumps(check(t, ask(e.up(), t)), indent=1))
        finally:
            e.down()
    else:
        selfcheck()
