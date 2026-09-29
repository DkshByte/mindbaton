// Mindbaton's website: copy buttons and tabs. Everything works without it; nothing is fetched.
const status = document.getElementById("status");

async function copy(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch {}
  const t = Object.assign(document.createElement("textarea"), { value: text });
  t.setAttribute("readonly", ""); t.style.cssText = "position:fixed;opacity:0";
  document.body.append(t); t.select();
  const ok = document.execCommand("copy"); t.remove(); return ok;
}

document.querySelectorAll("[data-copy]").forEach((b) => {
  const label = b.querySelector("[data-label]"), was = label.textContent;
  b.addEventListener("click", async () => {
    const ok = await copy(document.querySelector(b.dataset.copy).textContent.trim());
    label.textContent = ok ? "Copied" : "Select and copy";
    b.classList.toggle("done", ok);
    status.textContent = ok ? "Copied to the clipboard." : "Couldn't copy. Select the text and copy it.";
    clearTimeout(b.t); b.t = setTimeout(() => { label.textContent = was; b.classList.remove("done"); }, 1800);
  });
});

// tabs: the app's segmented control, with arrow keys, Home and End
document.querySelectorAll('[role="tablist"]').forEach((list) => {
  const tabs = [...list.querySelectorAll('[role="tab"]')];
  const pick = (tab, focus) => {
    tabs.forEach((t) => {
      const on = t === tab;
      t.setAttribute("aria-selected", on); t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
    });
    if (focus) tab.focus();
  };
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => pick(t));
    t.addEventListener("keydown", (e) => {
      const j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
      if (j === undefined) return;
      e.preventDefault(); pick(tabs[(j + tabs.length) % tabs.length], true);
    });
  });
});
