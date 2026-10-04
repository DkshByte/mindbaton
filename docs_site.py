"""Build the website's documentation (site/docs/) from docs/*.md, SECURITY.md and CHANGELOG.md. Stdlib only.

The Markdown files stay the one source: they read on GitHub as they are, and this turns them into pages in the site's
design (sidebar, "on this page", search, copy buttons). The output is committed, because GitHub Pages serves site/ as is.

  python3 docs_site.py           write site/docs/, and site/llms.txt into the Agent view of site/index.html
  python3 docs_site.py --check   exit 1 if either is out of date, a link or anchor is broken, or an MCP tool is
                                 missing from docs/api.md (CI runs this)
"""
import html, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "site", "docs")
REPO = "https://github.com/DkshByte/mindbaton"
# (group, source, slug, title in the sidebar, one line for search results and <meta>)
PAGES = [
    ("Start", "docs/README.md", "index", "Overview"),
    ("Start", "docs/getting-started.md", "getting-started", "Getting started"),
    ("Start", "docs/connect.md", "connect", "Connect your AIs"),
    ("Guides", "docs/remote-access.md", "remote-access", "Remote access"),
    ("Guides", "docs/configuration.md", "configuration", "Configuration"),
    ("Guides", "docs/backup-and-upgrade.md", "backup-and-upgrade", "Backup and upgrade"),
    ("Guides", "docs/troubleshooting.md", "troubleshooting", "Troubleshooting"),
    ("Reference", "docs/api.md", "api", "API reference"),
    ("Reference", "SECURITY.md", "security", "Security"),
    ("Reference", "CHANGELOG.md", "changelog", "Changelog"),
]
SLUG_OF = {src: slug for _, src, slug, _ in PAGES}
LANG = {"sh": "Terminal", "bash": "Terminal", "json": "JSON", "toml": "TOML", "yaml": "YAML", "python": "Python", "ini": "Config"}
esc = lambda s: html.escape(s, quote=False)
attr = lambda s: html.escape(s, quote=True)


def slugify(text, seen):
    """GitHub's heading anchors, so links written for GitHub work here too."""
    s = re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")
    n = seen.get(s, 0)
    seen[s] = n + 1
    return s if not n else f"{s}-{n}"


class Page:
    def __init__(self, src):
        self.src, self.problems, self.links, self.ids, self.heads = src, [], [], set(), []
        self.seen = {}

    # ── links ──
    def href(self, url):
        if re.match(r"[a-z]+:", url):
            return url
        path, _, frag = url.partition("#")
        if not path:
            self.links.append((self.src, frag))
            return "#" + frag
        target = os.path.normpath(os.path.join(os.path.dirname(self.src), path)).replace(os.sep, "/")
        if target in SLUG_OF:
            self.links.append((target, frag))
            return SLUG_OF[target] + ".html" + ("#" + frag if frag else "")
        if not os.path.exists(os.path.join(HERE, target)):
            self.problems.append(f"{self.src}: link to a missing file {url}")
        return f"{REPO}/blob/main/{target}" + ("#" + frag if frag else "")

    # ── inline ──
    INLINE = re.compile(r"`([^`]+)`|<(https?://[^>\s]+)>|\[([^\]]+)\]\(([^)\s]+)\)|\*\*(.+?)\*\*|(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])")

    def inline(self, s):
        out, i = [], 0
        for m in self.INLINE.finditer(s):
            out.append(esc(s[i:m.start()]))
            code, auto, text, url, bold, it = m.groups()
            if code is not None:
                out.append(f"<code>{esc(code)}</code>")
            elif auto:
                out.append(f'<a href="{attr(auto)}">{esc(auto)}</a>')
            elif text is not None:
                h = self.href(url)
                ext = ' rel="noopener"' if h.startswith("http") else ""
                out.append(f'<a href="{attr(h)}"{ext}>{self.inline(text)}</a>')
            elif bold is not None:
                out.append(f"<strong>{self.inline(bold)}</strong>")
            else:
                out.append(f"<em>{self.inline(it)}</em>")
            i = m.end()
        return "".join(out) + esc(s[i:])

    # ── blocks ──
    LIST = re.compile(r"( {0,3})([-*]|\d+\.) +")
    STARTS = re.compile(r" {0,3}(#{1,6} |```|>|[-*] |\d+\. |\|)")

    def blocks(self, lines):
        out, i = [], 0
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            m = re.match(r"( *)```\s*([\w+-]*)", line)
            if m:
                ind, lang, body = len(m[1]), m[2], []
                i += 1
                while i < len(lines) and lines[i].strip() != "```":
                    body.append(lines[i][ind:] if lines[i][:ind].strip() == "" else lines[i].lstrip())
                    i += 1
                i += 1
                out.append(self.code("\n".join(body), lang))
                continue
            m = re.match(r"(#{1,6})\s+(.*?)\s*#*$", line)
            if m:
                out.append(self.heading(len(m[1]), m[2]))
                i += 1
                continue
            if re.fullmatch(r"\s*(-{3,}|\*{3,})\s*", line):
                out.append("<hr>")
                i += 1
                continue
            if line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
                rows = []
                while i < len(lines) and lines[i].lstrip().startswith("|"):
                    rows.append(lines[i])
                    i += 1
                out.append(self.table(rows))
                continue
            if line.lstrip().startswith(">"):
                q = []
                while i < len(lines) and lines[i].lstrip().startswith(">"):
                    q.append(re.sub(r"^\s*> ?", "", lines[i]))
                    i += 1
                inner = self.blocks(q)
                warn = re.match(r"<p><strong>(Never|Warning|Careful)", inner)
                out.append(f'<div class="callout{" warn" if warn else ""}">{inner}</div>')
                continue
            m = self.LIST.match(line)
            if m:
                i = self.list(lines, i, out)
                continue
            para = [line.strip()]
            i += 1
            while i < len(lines) and lines[i].strip() and not self.STARTS.match(lines[i]):
                para.append(lines[i].strip())
                i += 1
            out.append(f"<p>{self.inline(' '.join(para))}</p>")
        return "\n".join(out)

    def list(self, lines, i, out):
        first = self.LIST.match(lines[i])
        ordered, base = first[2][0].isdigit(), len(first[1])
        items = []
        while i < len(lines):
            j = i
            while j < len(lines) and not lines[j].strip():  # blank lines between items keep one list
                j += 1
            m = self.LIST.match(lines[j]) if j < len(lines) else None
            if m and len(m[1]) == base and m[2][0].isdigit() == ordered:
                i = j
            if not (m and len(m[1]) == base and m[2][0].isdigit() == ordered):
                break
            width = len(m[0])
            body = [lines[i][width:]]
            i += 1
            while i < len(lines):
                l = lines[i]
                if not l.strip():
                    j = i
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines) and len(lines[j]) - len(lines[j].lstrip()) >= min(width, base + 2):
                        body += [""] * (j - i)
                        i = j
                        continue
                    break
                indent = len(l) - len(l.lstrip())
                if indent >= min(width, base + 2):
                    body.append(l[min(indent, width):])
                elif self.LIST.match(l) or self.STARTS.match(l):
                    break
                else:  # a lazy continuation line
                    body.append(l.strip())
                i += 1
            inner = self.blocks(body)
            if inner.count("<p>") == 1 and inner.startswith("<p>"):
                inner = inner.replace("<p>", "", 1).replace("</p>", "", 1)
            items.append(f"<li>{inner}</li>")
        start = int(first[2][:-1]) if ordered else 1
        tag = "ol" if ordered else "ul"
        out.append(f'<{tag}{f" start={start}" if start != 1 else ""}>' + "".join(items) + f"</{tag}>")
        return i

    def heading(self, level, text):
        if level == 1:
            self.title = re.sub(r"[`*]", "", text)
            return f"<h1>{self.inline(text)}</h1>"
        plain = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", re.sub(r"[`*]", "", text))
        hid = slugify(plain, self.seen)
        self.ids.add(hid)
        if level <= 3:
            self.heads.append((level, hid, plain))
        return (f'<h{level} id="{hid}">{self.inline(text)}'
                f'<a class="anchor" href="#{hid}" aria-label="Link to this section">#</a></h{level}>')

    def table(self, rows):
        cells = lambda r: [c.strip() for c in re.split(r"(?<!\\)\|(?=(?:[^`]*`[^`]*`)*[^`]*$)", r.strip().strip("|"))]
        head, body = cells(rows[0]), [cells(r) for r in rows[2:]]
        th = "".join(f"<th>{self.inline(c)}</th>" for c in head)
        tb = "".join("<tr>" + "".join(f"<td>{self.inline(c)}</td>" for c in r) + "</tr>" for r in body)
        return f'<div class="table"><table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div>'

    def code(self, text, lang):
        body = esc(text)
        if lang in ("sh", "bash"):  # dim shell comments: whole lines, or after two spaces
            body = re.sub(r"(^|  )(#[^\n]*)", r'\1<span class="c">\2</span>', body, flags=re.M)
        label = f'<span>{LANG.get(lang, lang.upper())}</span>' if lang else "<span></span>"
        return (f'<div class="code">{label}<button class="copy" type="button" aria-label="Copy code">'
                f'<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="12" height="12" rx="2"/>'
                f'<path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg></button><pre><code>{body}</code></pre></div>')


def plain(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def render(src):
    p = Page(src)
    p.title = ""
    text = open(os.path.join(HERE, src), encoding="utf-8").read()
    body = p.blocks(text.splitlines())
    body = body.replace("<p>", '<p class="lede">', 1) if "</h1>\n<p>" in body else body
    if src == "docs/README.md":  # the docs home: "[Title](page): what it covers" items become whole-row links
        arrow = ICON('<path d="M5 12h14M13 6l6 6-6 6"/>')
        body = re.sub(r'<li><a href="([^"]+)"[^>]*>(.*?)</a>: (.*?)</li>',
                      lambda m: f'<li><a class="row-l" href="{m[1]}"><b>{m[2]}</b><span>{m[3][:1].upper() + m[3][1:]}</span>{arrow}</a></li>', body)
    return p, body


def sections(slug, title, body):
    """Search entries: one per h2/h3 section, with its text."""
    parts = re.split(r'(<h[23] id="[^"]+">.*?</h[23]>)', body)
    out = [{"u": f"{slug}.html", "p": title, "h": title, "t": plain(re.sub(r"<h1>.*?</h1>", "", parts[0]))[:500]}]
    for k in range(1, len(parts), 2):
        m = re.match(r'<h[23] id="([^"]+)">(.*?)<a class="anchor"', parts[k])
        out.append({"u": f"{slug}.html#{m[1]}", "p": title, "h": plain(m[2]), "t": plain(parts[k + 1])[:500]})
    return out


ICON = lambda d: f'<svg class="i" viewBox="0 0 24 24" aria-hidden="true">{d}</svg>'


def page_html(n, slug, label, p, body):
    group_nav = []
    for g in dict.fromkeys(x[0] for x in PAGES):
        cur = ' aria-current="page"'
        links = "".join(f'<li><a href="{s}.html"{cur if s == slug else ""}>{esc(t)}</a></li>' for gg, _, s, t in PAGES if gg == g)
        group_nav.append(f'<p class="grp">{g}</p><ul>{links}</ul>')
    toc = "".join(f'<li class="l{lv}"><a href="#{hid}">{esc(t)}</a></li>' for lv, hid, t in p.heads)
    prev_, next_ = (PAGES[n - 1] if n else None), (PAGES[n + 1] if n + 1 < len(PAGES) else None)
    pn = ""
    if prev_:
        pn += f'<a class="pn prev" href="{prev_[2]}.html"><span>Previous</span>{esc(prev_[3])}</a>'
    if next_:
        pn += f'<a class="pn next" href="{next_[2]}.html"><span>Next</span>{esc(next_[3])}</a>'
    desc = re.search(r'<p class="lede">(.*?)</p>', body)
    desc = plain(desc[1])[:180] if desc else f"{p.title}: Mindbaton documentation."
    title = "Mindbaton docs" if slug == "index" else f"{p.title} · Mindbaton docs"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{attr(desc)}">
<meta name="theme-color" content="#111110">
<meta name="color-scheme" content="dark">
<link rel="canonical" href="https://mindbaton.com/docs/{'' if slug == 'index' else slug + '.html'}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Mindbaton">
<meta property="og:title" content="{attr(title)}">
<meta property="og:description" content="{attr(desc)}">
<meta property="og:image" content="https://mindbaton.com/og.png">
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<link rel="icon" href="../favicon-32.png" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="../apple-touch-icon.png">
<link rel="preload" href="../fonts/Geist-Variable.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="../style.css">
<link rel="stylesheet" href="docs.css">
<script src="search-index.js" defer></script>
<script src="docs.js" defer></script>
</head>
<!-- Made by docs_site.py from {p.src}. Edit that file, then run: python3 docs_site.py -->
<body class="docs{' home' if slug == 'index' else ''}">
<a class="skip" href="#doc">Skip to content</a>
<div class="aurora" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>
<header class="top">
  <div class="top-in">
    <button class="menu" type="button" aria-controls="side" aria-expanded="false" aria-label="Menu">{ICON('<path d="M4 7h16M4 12h16M4 17h16"/>')}</button>
    <a class="brand" href="../" aria-label="Mindbaton website"><span class="wordmark" aria-hidden="true"></span></a>
    <a class="docs-l" href="./">Docs</a>
    <button class="find" type="button" aria-haspopup="dialog">{ICON('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>')}<span>Search the docs</span><kbd>/</kbd></button>
    <div class="top-act">
      <a class="btn ghost" href="{REPO}"><span class="lg m" style="--i:url(../icons/github.svg)" aria-hidden="true"></span><span class="gh-t">GitHub</span></a>
      <a class="btn primary" href="../#install">Install</a>
    </div>
  </div>
</header>
<div class="shell">
  <nav class="side" id="side" aria-label="Documentation">{''.join(group_nav)}</nav>
  <main class="doc" id="doc">
    <article>
{body}
    </article>
    <nav class="pns" aria-label="Previous and next">{pn}</nav>
    <p class="edit"><a href="{REPO}/edit/main/{p.src}" rel="noopener">{ICON('<path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="m13.5 6.5 4 4"/>')}Edit this page on GitHub</a></p>
  </main>
  <aside class="toc" aria-label="On this page">{f'<p class="grp">On this page</p><ul>{toc}</ul>' if toc and slug != 'index' else ''}</aside>
</div>
<dialog class="sdlg" aria-label="Search the docs">
  <form method="dialog" role="search">
    <label class="sbox">{ICON('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>')}<span class="vh">Search the docs</span><input type="search" placeholder="Search the docs" autocomplete="off" spellcheck="false" aria-controls="sres"><kbd>Esc</kbd></label>
  </form>
  <ul class="sres" id="sres" role="listbox" aria-label="Results"></ul>
  <p class="shint">Try “setup code”, “Tailscale”, “token” or “backup”.</p>
</dialog>
</body>
</html>
"""


def mcp_tools():
    src = open(os.path.join(HERE, "server.py"), encoding="utf-8").read()
    block = src[src.index("MCP_TOOLS = ["):src.index("MCP_INSTRUCTIONS")]
    return re.findall(r'\{"name": "(\w+)"', block)


def build():
    files, index, problems, links, ids = {}, [], [], [], {}
    for n, (group, src, slug, label) in enumerate(PAGES):
        p, body = render(src)
        problems += p.problems
        links += [(src, t, f) for t, f in p.links]
        ids[src] = p.ids
        files[f"{slug}.html"] = page_html(n, slug, label, p, body)
        index += sections(slug, label if slug == "index" else p.title, body)
    files["search-index.js"] = ("// Made by docs_site.py: one entry per section, for the docs search.\nwindow.MB_DOCS = [\n"
                                + ",\n".join(json.dumps(e, ensure_ascii=False) for e in index) + "\n];\n")
    for src, target, frag in links:
        if frag and frag not in ids[target]:
            problems.append(f"{src}: no heading #{frag} in {target}")
    # the site's Agent view shows site/llms.txt itself, so "Copy llms.txt" and the file can't drift apart
    page = open(os.path.join(HERE, "site", "index.html"), encoding="utf-8").read()
    llms = open(os.path.join(HERE, "site", "llms.txt"), encoding="utf-8").read().strip()
    files["../index.html"] = re.sub(r'(<pre class="agent-code"[^>]*>).*?(</pre>)', lambda m: m[1] + esc(llms) + m[2], page, count=1, flags=re.S)
    api = open(os.path.join(HERE, "docs", "api.md"), encoding="utf-8").read()
    problems += [f"docs/api.md: the MCP tool `{t}` isn't documented" for t in mcp_tools() if f"`{t}`" not in api]
    return files, problems


def main():
    files, problems = build()
    check = "--check" in sys.argv
    for name, text in files.items():
        path = os.path.join(OUT, name)
        old = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if old != text:
            if check:
                problems.append(f"{os.path.relpath(path, HERE)} is out of date: run python3 docs_site.py")
            else:
                os.makedirs(OUT, exist_ok=True)
                open(path, "w", encoding="utf-8").write(text)
    if not check:
        print(f"wrote {len(files)} files to site/docs/")
    for m in problems:
        print("docs:", m, file=sys.stderr)
    if check and not problems:
        print(f"docs ok: {len(PAGES)} pages, links and anchors resolve, every MCP tool documented")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
