#!/usr/bin/env python3
"""Download the brand logos the viewer shows, once, into assets/icons/ — the page itself never fetches from outside.

  Simple Icons  (CC0)  si/<slug>.svg   one-colour brand marks, with the brand's hex
  LobeHub icons (MIT)  lh/<name>.svg   AI products (ChatGPT/OpenAI, Claude, Gemini, Grok, DeepSeek, Copilot, …)
  Devicon       (MIT)  dv/<name>.svg   developer tools missing from Simple Icons (VS Code, Windows, Slack, AWS, …)

Writes assets/icons/index.json: {name key: {"src": path, "hex": "#rrggbb" | None, "mono": bool}}.
Keys are what Mindbaton uses: brain.py entity keys ("docker", "rtx 3060" -> nvidia) and AI names ("ChatGPT").

    python3 fetch_assets.py
"""
import json, os, re, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets", "icons")
SI = "https://cdn.jsdelivr.net/npm/simple-icons@16.32.0"
LH = "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@1.95.1/icons"
DV = "https://cdn.jsdelivr.net/npm/devicon@2.16.0/icons"

LOBE = {  # AI products: key -> LobeHub file (colour where it exists)
    "chatgpt": "openai", "openai": "openai", "whisper": "openai", "codex": "codex-color", "claude": "claude-color",
    "claude code": "claudecode-color", "anthropic": "anthropic", "gemini": "gemini-color", "perplexity": "perplexity-color",
    "deepseek": "deepseek-color", "grok": "grok", "xai": "xai", "copilot": "copilot-color", "githubcopilot": "githubcopilot",
    "microsoft": "microsoft-color", "mistral": "mistral-color", "poe": "poe-color", "cursoride": "cursor", "cursor": "cursor",
    "windsurf": "windsurf", "ollama": "ollama", "huggingface": "huggingface-color", "midjourney": "midjourney",
    "comfyui": "comfyui-color", "stablediffusion": "stability-color", "n8n": "n8n-color", "llama": "meta-color",
    "qwen": "qwen-color", "gemma": "gemma-color", "langchain": "langchain-color", "opencode": "opencode",
}
DEVICON = {"vscode": "vscode/vscode-original", "windows": "windows11/windows11-original", "slack": "slack/slack-original",
           "aws": "amazonwebservices/amazonwebservices-original-wordmark", "azure": "azure/azure-original",
           "heroku": "heroku/heroku-original", "powershell": "powershell/powershell-original", "canva": "canva/canva-original",
           "photoshop": "photoshop/photoshop-original", "illustrator": "illustrator/illustrator-plain",
           "premiere": "premierepro/premierepro-original", "aftereffects": "aftereffects/aftereffects-original",
           "playwright": "playwright/playwright-original", "linkedin": "linkedin/linkedin-original",
           "java": "java/java-original", "c++": "cplusplus/cplusplus-original", "c#": "csharp/csharp-original"}
SIMPLE = {  # Mindbaton key -> Simple Icons slug (same name unless listed)
    "golang": "go", "dockercompose": "docker", "arch": "archlinux", "mint": "linuxmint", "adguardhome": "adguard",
    "traefik": "traefikproxy", "kafka": "apachekafka", "emacs": "gnuemacs", "intellij": "intellijidea", "zed": "zedindustries",
    "chrome": "googlechrome", "firefox": "firefoxbrowser", "esp32": "espressif", "esp8266": "espressif", "unreal": "unrealengine",
    "godot": "godotengine", "bash": "gnubash", "twitter": "x", "nix": "nixos", "pip": "pypi", "nextjs": "nextdotjs",
    "nodejs": "nodedotjs", "rails": "rubyonrails", "tailwind": "tailwindcss", "threejs": "threedotjs", "d3js": "d3",
    "vue": "vuedotjs", "gcp": "googlecloud", "raspberrypi": "raspberrypi", "davinciresolve": "davinciresolve",
    "uptimekuma": "uptimekuma", "homeassistant": "homeassistant", "pihole": "pihole", "1password": "1password",
    "githubactions": "githubactions", "sublimetext": "sublimetext", "stripe": "stripe", "razorpay": "razorpay",
    "iphone": "apple", "ipad": "apple", "macbook": "apple", "html": "html5", "css": "css",
}
BRANDS = {"nvidia", "amd", "intel", "lenovo", "apple", "dell", "raspberrypi", "google", "samsung", "oneplus", "xiaomi", "tesla",
          "netflix", "infosys", "spotify", "youtube", "instagram", "tiktok", "reddit", "gmail", "steam", "notion", "obsidian"}
MODELS = [(r"^(rtx|gtx|quadro)", "nvidia"), (r"^arc ", "intel"), (r"^rx ", "amd"), (r"^ryzen", "amd"), (r"^intel", "intel"),
          (r"^thinkpad", "lenovo"), (r"^(macbook|iphone|ipad|imac|mac mini)", "apple"), (r"^dell", "dell"),
          (r"^raspberry pi", "raspberrypi"), (r"^pixel", "google"), (r"^galaxy", "samsung"), (r"^oneplus", "oneplus")]
AI_NAMES = {"ChatGPT": "chatgpt", "Claude": "claude", "Gemini": "gemini", "Perplexity": "perplexity", "DeepSeek": "deepseek",
            "Grok": "grok", "Copilot": "copilot", "Poe": "poe", "Mistral": "mistral", "Claude Code": "claude code", "Codex": "codex",
            "Cursor": "cursor", "OpenCode": "opencode"}


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return r.read()
    except OSError:
        return None


def visible(hexcode):
    """Brand colours too dark for a near-black page fall back to the page's ink."""
    n = int(hexcode, 16)
    r, g, b = (n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255
    lum = lambda c: c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4
    L = .2126 * lum(r) + .7152 * lum(g) + .0722 * lum(b)
    return (L + .05) / (.0 + .05 + .004) >= 3.2  # against ~#0b0b0d


def main():
    sys.path.insert(0, HERE)
    import brain
    for d in ("si", "lh", "dv"):
        os.makedirs(os.path.join(OUT, d), exist_ok=True)
    data = json.loads(get(SI + "/data/simple-icons.json"))
    si = {i.get("slug") or re.sub(r"[^a-z0-9]", "", i["title"].lower()): i["hex"] for i in data}
    keys = set(brain.GAZ) | set(LOBE) | set(DEVICON) | BRANDS | {"homelab"}
    index, missing = {}, []

    def fetch(path, url):
        full = os.path.join(OUT, path)
        if not os.path.exists(full):
            body = get(url)
            if not body or b"<svg" not in body[:500]:
                return False
            open(full, "wb").write(body)
        return True

    def add(key):
        if key in LOBE and fetch(f"lh/{LOBE[key]}.svg", f"{LH}/{LOBE[key]}.svg"):
            mono = not LOBE[key].endswith("-color")
            return {"src": f"lh/{LOBE[key]}.svg", "hex": None, "mono": mono}
        slug = SIMPLE.get(key, key)
        if slug in si and fetch(f"si/{slug}.svg", f"{SI}/icons/{slug}.svg"):
            return {"src": f"si/{slug}.svg", "hex": "#" + si[slug] if visible(si[slug]) else None, "mono": True}
        if key in DEVICON and fetch(f"dv/{key}.svg", f"{DV}/{DEVICON[key]}.svg"):
            return {"src": f"dv/{key}.svg", "hex": None, "mono": False}
        return None

    for key in sorted(keys):
        e = add(key)
        if e:
            index[key] = e
        else:
            missing.append(key)
    for name, key in AI_NAMES.items():
        if key in index:
            index[name] = index[key]
    index["_models"] = [[rx, brand] for rx, brand in MODELS if brand in index]
    json.dump(index, open(os.path.join(OUT, "index.json"), "w"), indent=0, sort_keys=True)
    print(f"{len(index) - 1} logos -> assets/icons/index.json; no logo for: {', '.join(missing)}")


if __name__ == "__main__":
    main()
