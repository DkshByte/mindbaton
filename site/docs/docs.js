// Mindbaton docs: search (/, Ctrl/⌘K), copy buttons on code, the phone menu and "On this page". Nothing is fetched.
const $ = (s, el = document) => el.querySelector(s);
const CHECK = '<path d="M5 12.5l4.5 4.5L19 7.5"/>';

// copy buttons
document.querySelectorAll(".code .copy").forEach((b) => {
  const icon = b.querySelector("svg").innerHTML;
  b.addEventListener("click", async () => {
    const text = b.parentElement.querySelector("pre").innerText.replace(/\n$/, "");
    let ok = true;
    try { await navigator.clipboard.writeText(text); } catch { ok = false; }
    b.querySelector("svg").innerHTML = ok ? CHECK : icon;
    b.classList.toggle("done", ok);
    b.setAttribute("aria-label", ok ? "Copied" : "Copy failed, select the code instead");
    clearTimeout(b.t);
    b.t = setTimeout(() => { b.querySelector("svg").innerHTML = icon; b.classList.remove("done"); b.setAttribute("aria-label", "Copy code"); }, 1600);
  });
});

// the phone menu
const menu = $(".menu"), side = $("#side");
const setMenu = (open) => { side.classList.toggle("open", open); menu.setAttribute("aria-expanded", open); document.body.style.overflow = open ? "hidden" : ""; };
menu.addEventListener("click", () => setMenu(!side.classList.contains("open")));
side.addEventListener("click", (e) => { if (e.target.closest("a")) setMenu(false); });
addEventListener("keydown", (e) => { if (e.key === "Escape" && side.classList.contains("open")) { setMenu(false); menu.focus(); } });
matchMedia("(min-width: 901px)").addEventListener("change", () => setMenu(false));

// keep the current page in view in a long sidebar
$('.side a[aria-current="page"]')?.scrollIntoView({ block: "nearest" });

// "On this page": the section you're reading is marked
const toc = [...document.querySelectorAll(".toc a")];
if (toc.length) {
  const byId = new Map(toc.map((a) => [a.hash.slice(1), a]));
  const heads = [...document.querySelectorAll(".doc h2[id], .doc h3[id]")].filter((h) => byId.has(h.id));
  let queued = false;
  const onToc = () => {
    queued = false;
    let cur = heads[0];
    for (const h of heads) if (h.getBoundingClientRect().top < 200) cur = h;
    toc.forEach((a) => a.classList.toggle("on", a === byId.get(cur?.id)));
  };
  addEventListener("scroll", () => { if (!queued) { queued = true; requestAnimationFrame(onToc); } }, { passive: true });
  onToc();
}

// search: every h2/h3 section of every page (search-index.js), ranked by where the words are found
const dlg = $(".sdlg"), input = $("input", dlg), list = $("#sres"), hint = $(".shint");
const DOCS = window.MB_DOCS || [];
let sel = 0, hits = [];

function open() {
  if (dlg.open) return;
  dlg.showModal();
  input.select();
  run();
}
function run() {
  const q = input.value.trim().toLowerCase(), terms = q.split(/\s+/).filter(Boolean);
  if (!terms.length) hits = DOCS.filter((d) => !d.u.includes("#"));
  else {
    hits = DOCS.map((d) => {
      const h = d.h.toLowerCase(), p = d.p.toLowerCase(), t = d.t.toLowerCase();
      let s = 0;
      for (const w of terms) {
        const inH = h.includes(w), inP = p.includes(w), inT = t.includes(w);
        if (!inH && !inP && !inT) return null;
        s += (inH ? 6 : 0) + (inP ? 2 : 0) + (inT ? 1 : 0) + (h.startsWith(w) ? 2 : 0);
      }
      if (h.includes(q)) s += 8;
      return { d, s };
    }).filter(Boolean).sort((a, b) => b.s - a.s).slice(0, 12).map((x) => x.d);
  }
  sel = 0;
  draw(terms);
}
function highlight(el, text, terms) {
  const re = terms.length ? new RegExp("(" + terms.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")", "gi") : null;
  (re ? text.split(re) : [text]).forEach((part, i) => {
    if (re && i % 2) { const m = document.createElement("mark"); m.textContent = part; el.append(m); }
    else el.append(part);
  });
}
function snippet(t, terms) {
  const i = terms.length ? Math.max(0, t.toLowerCase().indexOf(terms[0])) : 0;
  return (i > 40 ? "…" + t.slice(i - 30) : t).slice(0, 160);
}
function draw(terms) {
  list.replaceChildren(...hits.map((d, i) => {
    const li = document.createElement("li"), a = document.createElement("a");
    li.setAttribute("role", "option");
    li.id = "sr" + i;
    li.setAttribute("aria-selected", i === sel);
    a.href = d.u;
    const p = document.createElement("span"), h = document.createElement("span"), t = document.createElement("span");
    p.className = "sp"; h.className = "sh"; t.className = "st";
    p.textContent = d.u.includes("#") ? d.p : "Page";
    highlight(h, d.h, terms);
    highlight(t, snippet(d.t, terms), terms);
    a.append(p, h, t);
    li.append(a);
    li.addEventListener("mousemove", () => { if (sel !== i) { sel = i; mark(); } });
    return li;
  }));
  const q = input.value.trim();
  hint.hidden = Boolean(q && hits.length);
  hint.textContent = q && !hits.length ? `Nothing found for “${q}”.` : "Try “setup code”, “Tailscale”, “token” or “backup”.";
  mark();
}
function mark() {
  [...list.children].forEach((li, i) => li.setAttribute("aria-selected", i === sel));
  input.setAttribute("aria-activedescendant", hits.length ? "sr" + sel : "");
  list.children[sel]?.scrollIntoView({ block: "nearest" });
}

input.addEventListener("input", run);
input.addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    if (hits.length) { sel = (sel + (e.key === "ArrowDown" ? 1 : hits.length - 1)) % hits.length; mark(); }
  } else if (e.key === "Enter") {
    e.preventDefault();
    const a = list.children[sel]?.querySelector("a");
    if (a) { dlg.close(); location.href = a.href; }
  }
});
list.addEventListener("click", (e) => { if (e.target.closest("a")) dlg.close(); });
dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
$(".find").addEventListener("click", open);
addEventListener("keydown", (e) => {
  const typing = /^(input|textarea|select)$/i.test(e.target.tagName) || e.target.isContentEditable;
  if ((e.key === "/" && !typing) || (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey))) { e.preventDefault(); open(); }
});
