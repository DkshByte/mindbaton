"""brain — turns chat messages into memories, entities and relations. No LLM, stdlib only.

One message goes through:  redact -> clean -> clauses -> per clause:
  mood       statement / question / hypothetical (only statements assert facts; questions only reveal possessions)
  type       fact / preference / goal / event / question / task / note
  entities   gazetteer names, model numbers (RTX 3060, ThinkPad T480), capitalised runs, out-of-dictionary words
  relations  about the user (with lists, negation, retraction and change-of-state) and about third parties
  time       "yesterday", "last month", "14 november", "by friday" -> a timestamp
  phrases    noun phrases, so the server can promote recurring ones ("thumbnail generator") to concepts
The query side (`query`) expands synonyms and categories and works out which relation a question asks about.

The system dictionary (/usr/share/dict) tells real words from names: "jellyfin" and "razorpay" are not English, so
they are names even when typed in lower case. Without the file everything still works, just less sharp.
"""
import calendar, gzip, math, os, re, time
from collections import Counter
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------------------------------------------------
# lexicon
# ---------------------------------------------------------------------------------------------------------------------
def _load_dict():
    """The English word list (SCOWL, assets/words): bundled, so every computer reads words the same way; the system's
    /usr/share/dict only if the bundled file is missing."""
    words, proper = set(), {}
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "words", "american-english.gz")
    for path in (here, "/usr/share/dict/american-english", "/usr/share/dict/british-english", "/usr/share/dict/words"):
        try:
            with (gzip.open(path, "rt", encoding="utf-8", errors="ignore") if path.endswith(".gz")
                  else open(path, encoding="utf-8", errors="ignore")) as f:
                for w in f:
                    w = w.strip()
                    if w and "'" not in w:
                        (proper.__setitem__(w.lower(), w) if w[0].isupper() else words.add(w))
            break
        except OSError:
            continue
    return words, {k: v for k, v in proper.items() if k not in words}  # "Bill" vs "bill": the common word wins


DICT, PROPER = _load_dict()

STOP = set("""a an the and or but if then else of to in on at by for with from into onto about as is are was were be been
being am do does did doing have has had having i me my mine myself we our ours us you your yours he him his she her it its they
them their this that these those there here what which who whom whose when where why how all any both each few more most other
some such no nor not only own same so than too very can will just should could would may might must shall now also get got
make made like really please thanks thank hi hello hey ok okay yes yeah pls u ur im ive id dont cant wont lets let one use
using used want need know think go going way thing things something anything lot bit much many even still well wanted
out up down over again further once because while during before after above below between give tell show help
write explain create fix add build generate list find try trying see look good best better i'm i've i'd i'll it's that's
don't doesn't didn't isn't aren't can't won't cannot doesnt didnt isnt arent wasnt werent havent hasnt couldnt shouldnt
wouldnt youre youve thats whats theres hes shes theyre weve ill youll""".split())

DET = set("a an the my our your his her their its this that these those some any every each no another either".split())
PRON = set("""i me you he she it we they him us them myself yourself himself herself itself ourselves themselves mine yours
hers ours theirs i'm i've i'd i'll you're you've it's that's there's let's he's she's we're they're what's""".split())
AUX = set("""am is are was were be been being have has had do does did will would shall should can could may might must
don't doesn't didn't isn't aren't wasn't weren't won't wouldn't can't cannot couldn't shouldn't haven't hasn't hadn't not
never 's 're 've 'd 'll""".split())
PREP = set("""in on at for with from to of by about into onto over under via through throughout during before after between
among across against without within near around like as than per upon toward towards off out up down behind beside besides
beyond inside outside since until till except vs versus""".split())
CONJ = set("and or but nor so yet plus & either because while although though whereas".split())
QWORD = set("what which who whom whose when where why how".split())
ADV = set("""very really too also just only even still already always never often sometimes usually mostly mainly almost
quite rather pretty ever again anymore then here there actually basically literally honestly maybe perhaps probably definitely
kinda sorta somewhat totally completely fully primarily mostly generally""".split())
TEMPW = set("today tonight yesterday tomorrow anymore lately recently soon currently now nowadays".split())
CUT = set("last next every each ago someday sometime eventually twice once daily weekly monthly".split()) | set(m.lower() for m in __import__("calendar").month_name if m) | \
    set(d.lower() for d in __import__("calendar").day_name)
STRIP = set("""a an the my our your his her their this that these those some any two three four five several few many much more
most another other new old used second-hand secondhand refurbished brand-new little own main current latest first cheap
expensive good great nice cool awesome basic simple quick decent proper actual same whole entire mostly mainly usually just
only also even still primarily currently really very super pretty""".split())
NOT_THING = set("""idea clue time question problem issue doubt feeling chance way lot bit fun nothing anything everything
something someone anyone everyone one thing things stuff kind sort type part point reason mind life day night week month year
today moment sense luck access trouble experience answer message text name job work fault opinion head end hand need use sure
plan project goal dream code question questions problems issues doubts help tips advice bugs error errors look try""".split())
SECRETISH = set("password passwords passcode pin otp token key keys secret secrets credentials login".split())
FEELING = set("""fine good ok okay sure sorry tired confused lost stuck done ready glad happy sad excited curious new here back
busy free late early bored worried scared afraid interested trying going working using building learning thinking looking
planning not so very also just still home sick well alright great down up in out on off almost about""".split())
IDENTITY = set("""vegetarian vegan pescatarian eggetarian jain student developer engineer designer programmer freelancer
founder teacher doctor nurse lawyer gamer beginner retired unemployed married single engaged divorced pregnant diabetic
lactose-intolerant left-handed colorblind introvert extrovert remote self-employed atheist muslim hindu christian sikh
parent dad mom""".split())
KIN = set("""wife husband brother sister mom mother dad father friend son daughter boss partner girlfriend boyfriend fiance
fiancee dog cat kid child colleague roommate cousin uncle aunt grandma grandmother grandpa grandfather niece nephew manager
teammate puppy kitten pet bestie""".split())
GREET = r"^(?:(?:hey|hi|hello|yo|ok|okay|so|and|also|now|btw|um+|hmm+|well|oh|actually|alright|right|thanks|thank you)[ ,!.]+)*"
ACK = set("ok okay k kk thanks thank you thx ty cool great nice perfect awesome got it yes yeah yep no nope sure alright done lol haha "
          "continue go ahead proceed next retry again do run try fix please pls then now on that this".split())  # steering, not content

# ---- verbs: lemmas plus generated inflections -----------------------------------------------------------------------
IRREG = {"be": "am is are was were been being", "have": "has had having", "do": "does did done doing", "say": "said",
         "go": "goes went gone going", "get": "got gotten", "make": "made", "know": "knew known", "think": "thought",
         "take": "took taken", "see": "saw seen", "come": "came", "give": "gave given", "tell": "told", "find": "found",
         "feel": "felt", "become": "became", "leave": "left", "put": "put", "mean": "meant", "keep": "kept",
         "begin": "began begun", "hold": "held", "bring": "brought", "write": "wrote written", "sit": "sat",
         "stand": "stood", "lose": "lost", "pay": "paid", "meet": "met", "lead": "led", "understand": "understood",
         "speak": "spoke spoken", "spend": "spent", "grow": "grew grown", "win": "won", "buy": "bought", "send": "sent",
         "build": "built", "fall": "fell fallen", "sell": "sold", "break": "broke broken", "run": "ran", "drink": "drank drunk",
         "eat": "ate eaten", "sleep": "slept", "teach": "taught", "catch": "caught", "choose": "chose chosen",
         "drive": "drove driven", "ride": "rode ridden", "forget": "forgot forgotten", "hear": "heard", "wear": "wore worn",
         "draw": "drew drawn", "show": "shown", "throw": "threw thrown", "prefer": "prefers preferred preferring",
         "set": "sets setting", "quit": "quits quitting", "shut": "shuts shutting", "cut": "cuts cutting"}
VERB_LEMMAS = set("""be have do say go get make know think take see come want look use find give tell work call try ask need
feel become leave put mean keep let begin seem help talk turn start show hear play run move like live believe hold bring
happen write provide sit stand lose pay meet include continue set learn change lead understand watch follow stop create speak
read allow add spend grow open walk win offer remember love consider appear buy wait serve die send expect build stay fall cut
reach kill remain suggest raise pass sell require report decide pull break fix install deploy host configure update upgrade
download upload crash fail load reload print return cost enable disable connect access manage design code debug test check
switch migrate replace compare convert translate explain generate list cache store save delete remove render train scrape
parse drop finish plan prefer hate enjoy own study practice improve share post publish launch ship stream transcode buffer
cook eat drink sleep travel visit order book schedule remind teach catch choose drive ride forget hear wear draw throw quit
shut hope intend adore dislike detest join sit rebuild redesign develop prototype setup self-host selfhost drop ditch
uninstall abandon relocate shift reside cause keep freeze hang lag stutter handle solve avoid prevent reduce speed optimize
optimise automate monitor secure protect deal apply implement integrate refactor clean format sort filter merge split fetch
send receive sync mount boot restart reboot kill spawn wrap import export encrypt decrypt compress extract scale resize crop
edit record play watch listen chat message email text call pick choose need seem tend miss catch throw handle suggest""".split())


def _forms(v):
    out = {v}
    if v in IRREG:
        out |= set(IRREG[v].split())
    if re.search(r"(s|sh|ch|x|z|o)$", v):
        out.add(v + "es")
    elif re.search(r"[^aeiou]y$", v):
        out |= {v[:-1] + "ies", v[:-1] + "ied"}
    else:
        out.add(v + "s")
    if v.endswith("e") and not v.endswith("ee"):
        out |= {v + "d", v[:-1] + "ing"}
    elif len(v) <= 4 and re.fullmatch(r"[^aeiouy]*[aeiou][bcdfgklmnprstvz]", v):
        out |= {v + v[-1] + "ed", v + v[-1] + "ing"}
    else:
        out |= {v + "ing"} | ({v + "ed"} if not re.search(r"[^aeiou]y$", v) else set())
    return out


VERB = {f: v for v in VERB_LEMMAS for f in _forms(v)}

# ---- names people type in lower case --------------------------------------------------------------------------------
GAZ = {}
for _v in """Python JavaScript TypeScript Java Rust Golang C++ C# PHP Ruby Swift Kotlin Scala Elixir Haskell Lua Dart Zig SQL
HTML CSS React Vue Svelte Angular Next.js Nuxt Astro Remix Node.js Deno Bun Express Django Flask FastAPI Rails Laravel Spring
Tailwind Bootstrap jQuery Three.js D3.js Docker Docker_Compose Kubernetes Podman Linux Ubuntu Debian Arch Fedora Mint Manjaro
NixOS Pop!_OS Windows macOS Android iOS iPhone iPad MacBook Proxmox TrueNAS Unraid Jellyfin Plex Emby Sonarr Radarr Prowlarr
Lidarr qBittorrent Transmission Pi-hole AdGuard_Home NextDNS Home_Assistant Tailscale ZeroTier WireGuard OpenVPN Cloudflare
Nginx Caddy Traefik Apache PostgreSQL MySQL MariaDB SQLite Redis MongoDB Elasticsearch Kafka RabbitMQ Git GitHub GitLab
Bitbucket VS_Code Vim Neovim Emacs Sublime_Text IntelliJ PyCharm WebStorm Zed Chrome Firefox Brave Safari Edge Opera Vivaldi
YouTube Telegram Discord WhatsApp Slack Signal n8n Zapier Ollama ChatGPT Claude Gemini Copilot Perplexity DeepSeek Grok
OpenAI Anthropic Llama Mistral Gemma Qwen Stable_Diffusion Midjourney ComfyUI Whisper AWS GCP Azure DigitalOcean Hetzner
Vercel Netlify Heroku Supabase Firebase Raspberry_Pi ESP32 ESP8266 Arduino Nvidia AMD Intel Figma Framer Sketch Canva Penpot
Photoshop Illustrator Lightroom Premiere After_Effects DaVinci_Resolve Blender Unity Unreal Godot Minecraft Steam Notion
Obsidian Excel Jupyter Pandas NumPy PyTorch TensorFlow Pillow OpenCV Playwright Selenium Puppeteer Stripe Razorpay GraphQL
MQTT Zigbee Homelab Flutter Electron Bash Zsh PowerShell FFmpeg yt-dlp Spotify Instagram TikTok Twitter Reddit LinkedIn
Gmail Google Microsoft Apple Samsung OnePlus Xiaomi Tesla Netflix Amazon Grafana Prometheus InfluxDB Telegraf Netdata
Uptime_Kuma Portainer Immich Nextcloud Syncthing Vaultwarden Bitwarden 1Password Postman Terraform Ansible Jenkins
GitHub_Actions Nix Homebrew npm pip Webpack Vite ESLint Prettier Jest Pytest Kotlin Cursor_IDE Windsurf LangChain""".split():
    _label = _v.replace("_", " ")
    GAZ[re.sub(r"[^a-z0-9+#]", "", _label.lower())] = _label
ALIAS = {"vs code": "vscode", "visual studio code": "vscode", "nvim": "neovim", "k8s": "kubernetes", "postgres": "postgresql",
         "psql": "postgresql", "js": "javascript", "ts": "typescript", "py": "python", "osx": "macos", "mac os": "macos",
         "rpi": "raspberrypi", "raspi": "raspberrypi", "chat gpt": "chatgpt", "gpt": "chatgpt", "adguard": "adguardhome",
         "compose": "dockercompose", "ha": "homeassistant", "hass": "homeassistant", "sd": "stablediffusion",
         "win": "windows", "win11": "windows", "win10": "windows", "threejs": "three.js", "nextjs": "next.js",
         "nodejs": "node.js", "node": "node.js", "d3": "d3.js", "vscodium": "vscode", "go lang": "golang", "go": "golang"}
for _k, _label in list(GAZ.items()):  # "next.js" also answers to "nextjs"
    if "." in _label:
        ALIAS[_label.lower().replace(".", "")] = _k

MODEL_PATTERNS = [  # hardware and products whose names are model numbers
    (re.compile(r"\b(rtx|gtx|rx|arc|quadro)[ -]?([a-z]?\d{3,4})(?:[ -]?(ti|super|xtx|xt))?\b", re.I),
     lambda m: " ".join(x for x in (m[1].upper(), m[2].upper(), (m[3] or "").upper().replace("SUPER", "Super")) if x), "gpu"),
    (re.compile(r"\b(i[3579])[- ](\d{4,5}[a-z]{0,2})\b", re.I), lambda m: f"Intel {m[1].lower()}-{m[2].upper()}", "cpu"),
    (re.compile(r"\bryzen[ -]?([3579])[ -]?(\d{4}[a-z]{0,2})?\b", re.I), lambda m: f"Ryzen {m[1]}" + (f" {m[2].upper()}" if m[2] else ""), "cpu"),
    (re.compile(r"\bthinkpad[ -]?([txep]\d{2,3}[a-z]?)?\b", re.I), lambda m: "ThinkPad" + (f" {m[1].upper()}" if m[1] else ""), "laptop"),
    (re.compile(r"\b(iphone|ipad|pixel|galaxy s|galaxy a|oneplus)[ -]?(\d{1,2}[a-z]?(?: pro| max| plus| ultra)?)\b", re.I),
     lambda m: f"{m[1].title().replace('Iphone', 'iPhone').replace('Ipad', 'iPad')} {m[2].title()}", "phone"),
    (re.compile(r"\bmacbook[ -]?(air|pro)?(?:[ -]?(m[1-4])(?: (pro|max))?)?\b", re.I),
     lambda m: " ".join(x for x in ("MacBook", (m[1] or "").title(), (m[2] or "").upper(), (m[3] or "").title()) if x), "laptop"),
    (re.compile(r"\b(?:dell )?optiplex(?:[ -]?(\d{3,4}))?\b", re.I), lambda m: "Dell OptiPlex" + (f" {m[1]}" if m[1] else ""), "computer"),
    (re.compile(r"\braspberry[ -]?pi(?:[ -]?(\d|zero(?: 2)?))?\b", re.I), lambda m: "Raspberry Pi" + (f" {m[1].title()}" if m[1] else ""), "computer"),
]

CATEGORY = {  # what kind of thing a name is; lets "which editor do I use" find Neovim
    "editor": "vscode neovim vim emacs sublimetext intellij pycharm webstorm zed cursoride windsurf",
    "os": "linux ubuntu debian arch fedora mint manjaro nixos popos windows macos android ios",
    "dns": "pihole adguardhome nextdns",
    "language": "python javascript typescript java rust golang c++ c# php ruby swift kotlin scala elixir haskell lua dart zig bash",
    "database": "postgresql mysql mariadb sqlite redis mongodb elasticsearch supabase firebase",
    "browser": "chrome firefox brave safari edge opera vivaldi",
    "vpn": "tailscale zerotier wireguard openvpn cloudflare",
    "media": "jellyfin plex emby sonarr radarr prowlarr lidarr qbittorrent transmission",
    "container": "docker dockercompose kubernetes podman portainer proxmox",
    "design": "figma framer sketch canva penpot photoshop illustrator lightroom blender",
    "framework": "react vue svelte angular next.js nuxt astro remix django flask fastapi rails laravel spring tailwind three.js",
    "ai": "chatgpt claude gemini copilot perplexity deepseek grok ollama llama mistral gemma qwen stablediffusion midjourney comfyui whisper",
    "music": "jazz lo-fi lofi rock pop hiphop classical metal edm spotify",
    "food": "vegetarian vegan paneer pasta pizza biryani rice dal curry",
    "hardware": "esp32 esp8266 arduino raspberrypi nvidia amd intel",
}
CAT_OF = {k: c for c, ks in CATEGORY.items() for k in ks.split()}
CAT_WORDS = {  # words in a question that name a category
    "editor": "editor editors ide ides", "os": "os operating distro distros", "dns": "dns adblock adblocker blocker",
    "language": "language languages", "database": "database databases db dbs", "browser": "browser browsers",
    "vpn": "vpn remote", "media": "media streaming", "container": "container containers virtualization",
    "design": "design designing", "framework": "framework frameworks library libraries", "ai": "ai llm llms model models chatbot",
    "music": "music song songs genre genres playlist", "food": "food diet eat eating meal meals dinner lunch breakfast cooking",
    "gpu": "gpu gpus graphics", "cpu": "cpu processor", "laptop": "laptop notebook", "phone": "phone mobile smartphone",
    "hardware": "hardware board boards microcontroller"}
CAT_FROM_WORD = {w: c for c, ws in CAT_WORDS.items() for w in ws.split()}

SYNONYMS = [g.split(",") for g in """gpu,graphics card,video card,graphics|car,vehicle,auto|laptop,notebook|phone,mobile,smartphone
|server,homelab,home server|house,home,flat,apartment|job,work,career,employer,company,office|salary,pay,income|movie,film,cinema
|tv,television|show,series|container,docker|vm,virtual machine|ai,llm,model|pc,computer,desktop|money,budget,cost,price
|food,recipe,cooking,dinner,lunch,breakfast,meal,diet|doctor,health,medical|workout,gym,exercise,fitness|kid,child,son,daughter
|wife,husband,partner,spouse|study,learn,course,learning|bug,error,crash,issue,problem,broken,janky,dropouts,cuts out
|slow,performance,speed,faster,fast|editor,ide|os,operating system,distro|dns,ad blocker,adblock,pihole,adguard
|remote access,vpn,tailscale,wireguard,from outside|music,song,songs,playlist,genre,jazz|pet,cat,dog,puppy,kitten
|allergy,allergies,allergic|birthday,bday,anniversary|girlfriend,boyfriend,partner|project,projects,side project,building
|design,designing,figma|name,called,named|live,living,based,moved|work,working,job""".replace("\n", "").split("|")]


# ---------------------------------------------------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------------------------------------------------
def key(label):
    """Canonical identity of a name: case, punctuation, plurals and aliases folded."""
    k = re.sub(r"[^a-z0-9+#. -]", "", str(label).lower()).strip(" .-")
    if re.fullmatch(r"[a-z0-9][a-z0-9-]*\.[a-z]{2,10}", k) and k not in ALIAS and k.replace(".", "") not in GAZ:
        return k                                                         # bunkr.website stays bunkr.website
    k = re.sub(r"\s+", " ", k)
    if k in ALIAS:
        return ALIAS[k]
    compact = re.sub(r"[ .-]", "", k)
    if compact in GAZ:
        return compact
    if compact in ALIAS:
        return ALIAS[compact]
    if (label.islower() or label.isupper() and len(label) > 4) and len(k) > 3 and k.endswith("s") \
            and not k.endswith(("ss", "us", "is", "os", "ics")):
        k = k[:-3] + "y" if k.endswith("ies") and len(k) > 4 else k[:-1]  # cars -> car, slow queries -> slow query
    return k


def label_of(k, fallback):
    return GAZ.get(k, fallback)


def category_of(k):
    if k in CAT_OF:
        return CAT_OF[k]
    for rx, _, cat in MODEL_PATTERNS:
        if rx.fullmatch(k):
            return cat
    return None


def stem(w):
    for suf in ("ing", "edly", "ed", "ies", "es", "s", "ly"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def is_word(w):
    return w.lower() in DICT or w.lower() in STOP


def near_word(w):
    """True if w is one typo away from a dictionary word (so an unknown token is probably a typo, not a name)."""
    w = w.lower()
    if not DICT or not w.isalpha() or not 4 <= len(w) <= 14:
        return False
    letters = "abcdefghijklmnopqrstuvwxyz"
    for i in range(len(w) + 1):
        a, b = w[:i], w[i:]
        if b and a + b[1:] in DICT:
            return True
        if len(b) > 1 and a + b[1] + b[0] + b[2:] in DICT:
            return True
        for c in letters:
            if b and a + c + b[1:] in DICT or a + c + b in DICT:
                return True
    return False


GLUE = set("the to of and an in on it is for with".split())  # "fromthe", "belowthe": two words typed without the space


def typo(w):
    """An unknown token that is really a mistyped or run-together word, not a name: one edit from a word ("chekc"),
    a word glued to "the"/"to"/… ("fromthe"), or a mistyped stem before -able/-ible ("scrllable")."""
    w = w.lower()
    if not DICT or not w.isalpha() or w in DICT or w in PROPER or w in GAZ:
        return False
    if near_word(w):
        return True
    if any(w[:i] in DICT and len(w[:i]) >= 3 and w[i:] in GLUE for i in range(3, len(w) - 1)):
        return True
    m = re.fullmatch(r"(\w{4,})(able|ible)", w)
    return bool(m and m[1] not in DICT and near_word(m[1]))  # "scrll"+able is a typo; "stream"+able is a word


JARGON = set("""config configs repo repos auth env envs cli ui ux db dev devs prod admin app apps docs doc spec specs todo todos
async regex json yaml yml csv xml pdf url urls api apis sdk sdks http https ssh ssl tls dns vpn cpu gpu ram ssd hdd os ide
lol btw imo tbh idk pls thx gif gifs png jpg jpeg svg mp3 mp4 wifi bluetooth usb hdmi ok okay npm pip env vars var
frontend backend fullstack devops infra saas crud orm cors jwt oauth sql nosql kpi seo cms crm erp""".split())


def namey(w):
    """A token that is a name even in lower case: not English, not a typo, not a verb."""
    lw = w.lower()
    if lw in JARGON or lw in CUT:
        return False
    if lw in PROPER:
        return True
    return bool(DICT) and lw.isalpha() and len(lw) >= 3 and lw not in DICT and lw not in STOP and lw not in VERB and lw not in JARGON \
        and lw not in FEELING and not typo(lw)


# ---------------------------------------------------------------------------------------------------------------------
# privacy: secrets never reach storage
# ---------------------------------------------------------------------------------------------------------------------
SECRET_RX = [re.compile(p) for p in (
    r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,}", r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{12,}", r"\bgh[pousr]_[A-Za-z0-9]{20,}",
    r"\bgithub_pat_[A-Za-z0-9_]{20,}", r"\bglpat-[A-Za-z0-9_-]{16,}", r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    r"\bAKIA[0-9A-Z]{16}\b", r"\bAIza[0-9A-Za-z_-]{30,}", r"\bhf_[A-Za-z0-9]{20,}", r"\bnpm_[A-Za-z0-9]{20,}",
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{6,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)",
    r"\b[A-Fa-f0-9]{32,}\b", r"\b(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Z])(?=[A-Za-z0-9_-]*[a-z])[A-Za-z0-9_-]{28,}\b")]
SECRET_KV = re.compile(r"\b(password|passwd|pwd|passcode|passphrase|pin|otp|secret|token|api[ _-]?key|access[ _-]?key|"
                       r"private[ _-]?key|ssh[ _-]?key|credentials?)\b(\s*(?:is|are|was|=|:)\s*)(\"[^\"]+\"|'[^']+'|`[^`]+`|[^\s,;]+)", re.I)
CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
PIN = re.compile(r"\b(pin|otp|passcode|pass ?code|unlock code)(\s*(?:is|was|=|:|of|code)?\s*)(\d{3,8})\b", re.I)


def _luhn(digits):
    s = [int(c) for c in digits][::-1]
    return (sum(s[0::2]) + sum(sum(divmod(2 * d, 10)) for d in s[1::2])) % 10 == 0


def redact(text):
    """Replace API keys, tokens, passwords, private keys and card numbers with [secret]."""
    for rx in SECRET_RX:
        text = rx.sub("[secret]", text)

    def kv(m):
        v = m[3].strip("\"'`")
        looks_secret = v != "[secret]" and (re.search(r"\d|[^\w\s]", v) or not is_word(v)) and v.lower() not in STOP
        return m[1] + m[2] + "[secret]" if looks_secret else m[0]
    text = SECRET_KV.sub(kv, text)
    text = PIN.sub(lambda m: m[1] + m[2] + "[secret]", text)
    return CARD.sub(lambda m: "[secret]" if _luhn(re.sub(r"\D", "", m[0])) else m[0], text)


# ---------------------------------------------------------------------------------------------------------------------
# cleaning, clauses, tokens
# ---------------------------------------------------------------------------------------------------------------------
SHORTHAND = [(r"\bi m\b", "i'm"), (r"\bim\b", "i'm"), (r"\bive\b", "i've"), (r"\bid\b(?= (?:like|love|want|prefer))", "i'd"),
             (r"\bdont\b", "don't"), (r"\bdoesnt\b", "doesn't"), (r"\bdidnt\b", "didn't"), (r"\bcant\b", "can't"),
             (r"\bwont\b", "won't"), (r"\bisnt\b", "isn't"), (r"\barent\b", "aren't"), (r"\bwasnt\b", "wasn't"),
             (r"\bhavent\b", "haven't"), (r"\bwanna\b", "want to"), (r"\bgonna\b", "going to"), (r"\btryna\b", "trying to"),
             (r"\bgotta\b", "have to"), (r"\bu\b", "you"), (r"\bur\b", "your"), (r"\bpls\b|\bplz\b", "please"),
             (r"\bthx\b", "thanks"), (r"\bcuz\b|\bbc\b", "because"), (r"\brn\b", "right now"), (r"\bidk\b", "i don't know"),
             (r"\bbday\b", "birthday"), (r"\bfav\b", "favourite"), (r"\bthats\b", "that's"), (r"\bwhats\b", "what's"),
             (r"\bits\b(?= (?:a|an|the|not|so|too|very|really|just|been|my|how|what|called)\b)", "it's"), (r"’", "'"),
             (r"\bhs\b", "has"), (r"\bhv\b", "have"), (r"\babt\b", "about"), (r"\bppl\b", "people"), (r"\bcoz\b|\bbcz\b", "because"),
             (r"\bwat\b|\bwht\b", "what"), (r"\bhave build\b", "have built"), (r"\bi build\b(?= (?:a|an|the|my)\b)", "i built")]
ANCHORS = set("""name live lives living work works working have has favourite favorite building build built using love like
hate prefer learning moved bought sister brother wife husband girlfriend boyfriend birthday allergic vegetarian married
engaged daughter mother father years called named project startup company developer engineer designer student""".split())


def _edits(w):
    letters = "abcdefghijklmnopqrstuvwxyz"
    splits = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    return {a + b[1:] for a, b in splits if b} | {a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1} | \
        {a + c + b[1:] for a, b in splits if b for c in letters} | {a + c + b for a, b in splits for c in letters}


def _typo_map():
    seen = {}
    for a in ANCHORS:
        for e in _edits(a):
            if len(e) >= 4 and e != a and e not in DICT and e not in STOP and e not in ANCHORS and e not in JARGON \
                    and e not in GAZ and e not in ALIAS and e not in VERB:
                seen[e] = a if seen.get(e, a) == a else None   # ambiguous typos are left alone
    return {k: v for k, v in seen.items() if v}


TYPO = _typo_map() if DICT else {}


MINDBATON_BLOCK = re.compile(r"\[mindbaton( handoff)?\][\s\S]*?(?:\[/mindbaton(?(1) handoff)\]|$)", re.I)  # briefings and hand-off packs
# What arrives is not always what the person typed: agent harnesses wrap it, chat pages add hidden headings and clocks.
HARNESS = re.compile(  # agent/tool metadata blocks around a message: never the user speaking
    r"(?:The following is an? )?<(ADDITIONAL_METADATA|USER_SETTINGS_CHANGE|SYSTEM_MESSAGE|EPHEMERAL_MESSAGE|system-reminder|"
    r"local-command-[\w-]+|command-(?:name|message|args)|task-notification|bash-(?:input|stdout|stderr)|"
    r"user-prompt-submit-hook|environment_details|agent-message)\b[^>]*>[\s\S]*?(?:</\1>|$)", re.I)
WRAPPER = re.compile(r"</?(?:USER_REQUEST|user_query|pasted_content)\b[^>]*>", re.I)  # wrappers around the user's own words
SPEAKER = re.compile(r"^\s*(?:You|ChatGPT|Gemini|Claude|Copilot|Grok|DeepSeek|Perplexity|Mistral) said:?\s+")  # hidden headings
PREVIEW = re.compile(r"^([\s\S]{12,400}?)…\s+(?=\1)")           # a collapsed preview repeated before the full text
CLOCK = re.compile(r"(?<=[^\W\d_?.!])\d{1,2}:\d{2}(?:\s?[AaPp][Mm])?\s*$|(?<=[^\s\d])\d{1,2}:\d{2}\s?[AaPp][Mm]\s*$|"
                   r"\n\s*\d{1,2}:\d{2}\s?[AaPp][Mm]\s*$")  # "check10:41 PM"
PACK_FROM = re.compile(r"\[mindbaton handoff\] I'm continuing a conversation I had with (.+?) \(\"(.*?)\"")
HINT_MODEL = re.compile(r"`Model Selection` from .*? to (.+?)\. ", re.S)
HINT_TIME = re.compile(r"The current local time is: (\S+?)\.?\s*$", re.M)


def hints(raw):
    """What a harness wrapper says before scrub() drops it: the model picked, and when the message was really sent."""
    m, t = HINT_MODEL.search(raw or ""), HINT_TIME.search(raw or "")
    ts = None
    if t:
        try:
            ts = datetime.fromisoformat(t[1].replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return {"model": m and m[1].strip(), "ts": ts}


def scrub(text, pack="drop"):
    """Raw captured text -> what the person actually typed. Idempotent, so better rules reach old rows at a rebuild.
    pack='mark' collapses a pasted hand-off pack to one line (transcripts keep reading right); 'drop' removes it."""
    t = WRAPPER.sub("", HARNESS.sub("", text or ""))
    t = PREVIEW.sub("", SPEAKER.sub("", t))
    if pack == "mark":
        t = MINDBATON_BLOCK.sub(lambda m: ('[hand-off from %s: "%s"]' % PACK_FROM.search(m[0]).groups()) if PACK_FROM.search(m[0])
                               else "[mindbaton context]", t)
    else:
        t = MINDBATON_BLOCK.sub(" ", t)
    t = CLOCK.sub("", t.strip())
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def clean(text):
    text = MINDBATON_BLOCK.sub(" ", text)                                  # our own injected context is not the user speaking
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) >= 8 and sum(ch.isupper() for ch in letters) > .7 * len(letters):
        text = text.lower()                                               # SHOUTED MESSAGES are ordinary sentences
    if TYPO:
        text = re.sub(r"\b[a-z]{3,12}\b", lambda m: TYPO.get(m[0], m[0]), text)  # "my anme is" -> "my name is"
    text = re.sub(r"```.*?(```|$)", " ", text, flags=re.S)                # code blocks
    text = re.sub(r"`[^`\n]{40,}`", " ", text)                             # long inline code
    text = re.sub(r"https?://([^/\s]+)\S*", r"\1", text)                   # urls -> domain
    for a, b in SHORTHAND:
        text = re.sub(a, b, text, flags=re.I)
    lines = [l for l in text.splitlines()
             if not re.search(r"[;{}]\s*$|^\s{4,}\S|^\s*[$>#] |^\s*(?:import|from|def|class|return|print)\b", l)]
    return re.sub(r"[ \t]+", " ", "\n".join(lines)).strip()


CLAUSE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Za-z\"'])|\n+|;\s*|,?\s+(?:and|but|also|plus|so|though),?\s+(?=(?:i|i'm|i've|i'd|my|now i|we)\b)|"
                          r",\s+(?=(?:i|i'm|i've|my|now i|we|she|he|they|switched|moved|migrated|remind)\b(?! mean))", re.I)


def sentences(text):
    return [s.strip(" -*•\t,") for s in CLAUSE_SPLIT.split(text) if s and len(s.strip()) > 2]


TOKEN = re.compile(r"\[secret\]|[A-Za-z0-9][A-Za-z0-9+#'._/-]*[A-Za-z0-9+#]|[A-Za-z0-9]|[,;:!?()&]")


def tokenize(s):
    return [(m[0].rstrip("."), m.start(), m.start() + len(m[0].rstrip("."))) for m in TOKEN.finditer(s)]


def tag(words):
    """One letter per token: D det, O pronoun, A aux, P prep, C conj, Q wh-word, R adverb, T time, V verb, N content, . punct."""
    out = []
    for w in words:
        l = w.lower()
        if l in ",;:!?()&":
            t = "."
        elif l == "[secret]":
            t = "S"
        elif l in DET:
            t = "D"
        elif l in PRON:
            t = "O"
        elif l in AUX:
            t = "A"
        elif l in PREP:
            t = "P"
        elif l in CONJ:
            t = "C"
        elif l in QWORD:
            t = "Q"
        elif l in TEMPW:
            t = "T"
        elif l in ADV or (l.endswith("ly") and len(l) > 4 and l in DICT and l[:-2] + "le" not in DICT):
            t = "R"
        elif l in VERB and not (out and out[-1] in "DN") and not w[:1].isupper():
            t = "V"
        else:
            t = "N"
        out.append(t)
    for i in range(1, len(words)):
        l, nxt = words[i].lower(), (words[i + 1].lower() if i + 1 < len(words) else "")
        if out[i] != "N" or out[i - 1] != "N" or words[i][:1].isupper():
            continue
        if l in PARTICIPLE and nxt in PREP:             # "a designer living in mumbai"
            out[i] = "V"
        elif l in VERB and not l.endswith("ing") and (l.endswith(("s", "ed")) or l != VERB[l]) and \
                (not nxt or out[i + 1] in "PDOAR.V" or nxt in VERB and nxt.endswith("ing")) and _subjecty(words[i - 1]):
            out[i] = "V"                                # "my brother works at", "jellyfin keeps crashing"
    return out


def _subjecty(w):
    """A word that can plausibly be the subject of the next word: a person, a name, a product ("my own sent messages" is not)."""
    lw = w.lower()
    return lw in KIN or w[:1].isupper() or lw in GAZ or lw in ALIAS or namey(w)


PARTICIPLE = set("living staying residing working studying running using hosting based located sitting".split())


# ---------------------------------------------------------------------------------------------------------------------
# entities
# ---------------------------------------------------------------------------------------------------------------------
def entities(s):
    """Named things in one clause -> [(key, label, type)]."""
    found, spans = {}, []
    low = s.lower()
    for rx, fmt, cat in MODEL_PATTERNS:
        for m in rx.finditer(s):
            lab = fmt(m)
            found[key(lab)] = (lab, "tech")
            spans.append((m.start(), m.end()))
    for k, lab in GAZ.items():  # ponytail: linear gazetteer scan, ~300 names; an Aho-Corasick trie if it grows past thousands
        pat = re.escape(lab.lower()).replace(r"\ ", r"[\s_-]?").replace(r"\-", r"[\s-]?")
        m = re.search(r"(?<![\w.])" + pat + r"(?![\w])", low) or (k != lab.lower() and re.search(r"(?<![\w.])" + re.escape(k) + r"(?![\w])", low))
        if m and not any(a <= m.start() < b for a, b in spans):
            found[k] = (lab, "tech")
            spans.append((m.start(), m.end()))
    for a, target in ALIAS.items():
        if len(a) > 2 and target in GAZ and (m := re.search(r"(?<![\w.])" + re.escape(a) + r"(?![\w])", low)) \
                and not any(x <= m.start() < y for x, y in spans):
            found.setdefault(target, (GAZ[target], "tech"))
            spans.append((m.start(), m.end()))
    toks = tokenize(s)
    words = [w for w, _, _ in toks]
    tg = tag(words)
    run = []
    for i, (w, a, b) in enumerate(toks + [("", len(s), len(s))]):
        inside = any(x <= a < y for x, y in spans)
        cap = w[:1].isupper() and w not in ("I", "I'm", "I've", "I'd", "I'll") and len(w) > 1
        first = i == 0 or toks[i - 1][0] in ".!?"
        proper = cap and (not first or not is_word(w) and not typo(w) or w.lower() in PROPER) and w.lower() not in STOP and not inside
        lowname = bool(w) and not cap and i < len(tg) and tg[i] == "N" and not inside and namey(w)
        if proper or lowname:
            run.append(w)
        else:
            if run:
                lab = " ".join(run)
                if lab.lower() not in STOP and lab.lower() not in JARGON and lab.lower() not in CUT and not (len(run) == 1 and len(lab) < 2):
                    k = key(lab)
                    found.setdefault(k, (label_of(k, PROPER.get(lab.lower(), lab)), "tech" if k in GAZ else "name"))
            run = []
    for m in re.finditer(r"\b[a-z0-9][a-z0-9-]*\.(?:com|net|org|io|ai|dev|app|website|site|xyz|in|co|me|tech|so|gg|sh|ly|fm|tv|"
                         r"cloud|online|store|page|link|lol|club)\b", s, re.I):   # bunkr.website
        if not any(a <= m.start() < b for a, b in spans):
            found.setdefault(m[0].lower(), (m[0].lower(), "name"))
            spans.append((m.start(), m.end()))
    for m in re.finditer(r"(?<![\w.])(?=[A-Za-z]*\d)[A-Za-z][A-Za-z0-9]*\d[A-Za-z0-9]*\b", s):  # esp32, n8n, t480
        if not any(a <= m.start() < b for a, b in spans) and not re.fullmatch(r"[a-z]\d{1,2}", m[0].lower()):
            found.setdefault(key(m[0]), (label_of(key(m[0]), m[0]), "tech"))
    return [(k, l, t) for k, (l, t) in found.items() if k and k not in STOP and k != "secret"]


def phrases(s):
    """Noun phrases (2-4 words) and their tails: candidates for recurring concepts."""
    toks = tokenize(s)
    words = [w for w, _, _ in toks]
    tg = tag(words)
    out, run = set(), []
    for w, t in list(zip(words, tg)) + [("", ".")]:
        if t == "N" and not w.isdigit() and w.lower() not in STRIP and w.lower() not in NOT_THING:
            run.append(w.lower())
        else:
            for i in range(len(run)):
                p = run[i:]
                if 2 <= len(p) <= 4:
                    out.add(key(" ".join(p)))
            run = []
    return sorted(out)


# ---------------------------------------------------------------------------------------------------------------------
# time
# ---------------------------------------------------------------------------------------------------------------------
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m} | {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
MONTHS["sept"] = 9
WEEKDAYS = {d.lower(): i for i, d in enumerate(calendar.day_name)} | {d.lower(): i for i, d in enumerate(calendar.day_abbr)}
NUMW = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "few": 3, "couple of": 2, "couple": 2}
UNIT = {"day": 1, "week": 7, "month": 30, "year": 365}
PAST_V = re.compile(r"\b(moved|bought|went|got|started|joined|left|quit|sold|finished|visited|turned|switched|migrated|"
                    r"was|were|did|had|made|built|launched|shipped|graduated|married|adopted|installed|ordered|broke|lost)\b", re.I)
FUTURE_V = re.compile(r"\b(will|going to|plan|planning|want to|by|next|tomorrow|remind|upcoming|need to|have to)\b", re.I)


def when(s, ref=None):
    """A time expression in s, resolved against ref -> (timestamp, 'past'|'future'|None) or (None, None)."""
    ref = datetime.fromtimestamp(ref or time.time())
    d0 = ref.replace(hour=12, minute=0, second=0, microsecond=0)
    l = s.lower()
    past = bool(PAST_V.search(l))
    fut = bool(FUTURE_V.search(l)) and not past

    def out(d, tense=None):
        return d.timestamp(), tense or ("past" if d < d0 else "future" if d > d0 else None)
    if m := re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", l):
        try:
            return out(d0.replace(year=int(m[1]), month=int(m[2]), day=int(m[3])))
        except ValueError:
            return None, None
    if re.search(r"\bday before yesterday\b", l):
        return out(d0 - timedelta(2))
    if re.search(r"\byesterday\b", l):
        return out(d0 - timedelta(1))
    if re.search(r"\bday after tomorrow\b", l):
        return out(d0 + timedelta(2))
    if re.search(r"\btomorrow\b", l):
        return out(d0 + timedelta(1))
    if re.search(r"\b(today|tonight|this morning|this evening)\b", l):
        return out(d0, "past" if past else "future" if fut else None)
    if m := re.search(r"\b(\d+|an?|one|two|three|four|five|six|few|couple(?: of)?)\s+(day|week|month|year)s?\s+ago\b", l):
        n = int(m[1]) if m[1].isdigit() else NUMW.get(m[1], 1)
        return out(d0 - timedelta(n * UNIT[m[2]]), "past")
    if m := re.search(r"\bin\s+(\d+|an?|one|two|three|four|five|six|few|couple(?: of)?)\s+(day|week|month|year)s?\b", l):
        n = int(m[1]) if m[1].isdigit() else NUMW.get(m[1], 1)
        return out(d0 + timedelta(n * UNIT[m[2]]), "future")
    if m := re.search(r"\b(last|next|this)\s+(week|weekend|month|year)\b", l):
        days = {"week": 7, "weekend": 7, "month": 30, "year": 365}[m[2]]
        sign = {"last": -1, "next": 1, "this": 0}[m[1]]
        return out(d0 + timedelta(sign * days), "past" if sign < 0 else "future" if sign > 0 else None)
    months = "|".join(sorted(MONTHS, key=len, reverse=True))
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + months + r")\b\.?(?:,?\s+(\d{4}))?", l) or \
        re.search(r"\b(" + months + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s+(\d{4}))?", l)
    if m:
        a, b, y = m[1], m[2], m[3]
        day, mon = (int(a), MONTHS[b]) if a.isdigit() else (int(b), MONTHS[a])
        try:
            d = d0.replace(year=int(y) if y else d0.year, month=mon, day=day)
        except ValueError:
            return None, None
        if not y and (fut or "birthday" in l or "anniversary" in l) and d < d0:
            d = d.replace(year=d.year + 1)            # the next one
        elif not y and past and d > d0:
            d = d.replace(year=d.year - 1)            # the last one
        return out(d)
    if m := re.search(r"\b(?:in|since|from|back in|during)\s+(" + months + r")\b", l):
        if m[1] not in ("may", "mar", "jan", "jun", "jul", "aug", "oct", "dec", "sep", "nov", "feb", "apr") or m[0].split()[-1] == m[1]:
            d = d0.replace(month=MONTHS[m[1]], day=1)
            if d > d0 and not fut:
                d = d.replace(year=d.year - 1)
            return out(d)
    if m := re.search(r"\b(last|next|this|on|by|coming)?\s*\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", l):
        wd = WEEKDAYS[m[2]]
        delta = (wd - d0.weekday()) % 7
        if m[1] == "last" or (past and m[1] in (None, "on")):
            delta = delta - 7 if delta else -7
        elif m[1] == "next" and delta == 0:
            delta = 7
        return out(d0 + timedelta(delta))
    return None, None


# ---------------------------------------------------------------------------------------------------------------------
# mood and type
# ---------------------------------------------------------------------------------------------------------------------
Q_START = re.compile(GREET + r"(?:what|which|who|whom|whose|when|where|why|how|should|can|could|would|will|do|does|did|is|are|"
                     r"am|was|were|have|has|may|might|shall|any idea|anyone know|is there|are there)\b", re.I)
HYPO = re.compile(r"\b(if|unless|wish|suppose|supposing|imagine|whether|hypothetically|in case|would(?! like)|could|might|"
                  r"maybe|perhaps|thinking (?:of|about)|considering)\b", re.I)
TASK = re.compile(GREET + r"(please |can you |could you |would you |will you |i need you to |help me |now )?(write|make|create|"
                  r"fix|explain|give|add|build|generate|help|show|tell|list|convert|translate|summari[sz]e|rewrite|debug|design|"
                  r"find|compare|improve|remove|update|change|do|check|suggest|recommend|draft|plan|remind|refactor|optimi[sz]e|"
                  r"review|edit|format|calculate|describe|teach|walk me|set up|setup|implement|port)\b", re.I)
TYPE_RX = [
    ("preference", r"\b(i|we)(?:'d| would)? (?:really |absolutely |kinda |also |still )?(like|love|prefer|enjoy|hate|dislike|adore|"
                   r"detest|can't stand|cannot stand|don't like|do not like|am into|'m into)\b|\bmy fav(ou?rite)?\b|\bfan of\b"),
    ("goal", r"\b(i|we)(?:'m| am| are|'re)? (trying|planning|going|want|need|hoping|aiming|intend|have) to\b|\b(i|we)(?:'m| am| are|'re) "
             r"(building|making|creating|working on|learning|setting up|developing|writing|designing|redesigning|studying)\b|"
             r"\bmy (goal|plan|project|dream|side project)\b|\bget better at\b"),
    ("event", r"\b(i|we)(?:'ve| have)? (?:just |finally |recently )?(moved|bought|joined|left|quit|started|switched|sold|got|"
              r"visited|finished|turned|graduated|adopted|installed|ordered|migrated|launched|shipped)\b"),
    ("fact", r"\b(i|we)(?:'m| am| are| was|'ve| have| had| own| use| run| live| work| study| drive| got|'re)\b|\bmy \w+(?:'s)? "
             r"(?:\w+ )?(?:is|are|was)\b|\bmy (name|age|job|" + "|".join(KIN) + r")\b|\bi don't\b"),
]
IMPORTANCE = {"preference": .9, "fact": .85, "goal": .8, "event": .75, "note": .45, "question": .35, "task": .3}
PERSONAL = {"preference", "fact", "goal", "event"}


def mood(s):
    if s.rstrip().endswith("?") or Q_START.search(s):
        return "question"
    if HYPO.search(s):
        return "hypothetical"
    return "statement"


def classify(s, md=None):
    md = md or mood(s)
    if TASK.search(s):
        return "task"
    if md == "question":
        return "question"
    for t, p in TYPE_RX:
        if re.search(p, s, re.I):
            return t
    return "note"


# ---------------------------------------------------------------------------------------------------------------------
# relations about the user
# ---------------------------------------------------------------------------------------------------------------------
ADVS = r"(?:(?:also|really|still|now|currently|mainly|mostly|usually|just|actually|basically|kinda|always|primarily|sometimes|" \
       r"only|finally|recently|already|remotely|full-time|part-time|mostly|happily|daily|regularly|often)\s+)*"
S = r"\b(?:i|we)(?:'ve|'d|'ll|'m|'re)?\s+(?:(?:have|had|am|are)\s+)?(?:been\s+)?" + ADVS
S2 = r"(?:" + S + r"|\b(?:but|and|now|so|then)\s+(?:now\s+)?)"   # subjectless continuation in a first-person clause
IM = r"\b(?:i am|i'm|we are|we're)\s+(?:(?:also|really|still|now|currently|just|actually|basically|kinda|already)\s+)*"
NOT_OBJ = r"(?!(?:to|been|no|not|had|always|never|already|just|any|it|this|that|them|these|those|you|him|her|how|when|what|" \
          r"why|where|into|out|away|over|through|low|a lot|a bit|some time|fun|trouble|time|access)\b)"
EXCLUSIVE = {"named", "lives in", "works at", "age"}   # one value at a time: a newer one replaces the old
RULES = []                                               # (regex, relation, options)


def _rule(pattern, rel, **opt):
    RULES.append((re.compile(pattern, re.I), rel, opt))


_rule(r"\bmy name(?:'s| is)\s+|\b(?:call me|they call me|people call me)\s+", "named", one=True)
_rule(GREET + r"(?:i am|i'm|this is|it's)\s+(?=[a-z]+\b\s*(?:,|\.|!|$|and\b|from\b|here\b|a\b|an\b))", "named", one=True, namecheck=True)
_rule(r"\bmy age is\s+|\bi turned\s+", "age", number=True)
_rule(IM + r"(?=\d{1,2}(?:\s*(?:years?|yrs?|yo|y/o)\b|\s*(?:,|\.|!|$|and\b)))", "age", number=True)
_rule(S2 + r"(?:live|living|stay|staying|reside|residing)\s+" + ADVS + r"(?:in|at)\s+", "lives in", kind="place", firstperson=True)
_rule(IM + r"(?:moving|relocating|shifting)\s+to\s+|\bi(?:'m| am) going to move to\s+", "plans to move to", kind="place")
_rule(r"\bi was born in\s+|\bborn and raised in\s+|\bi was raised in\s+", "from", kind="place")
_rule(r"\b(?:living|based|staying|settled|located)\s+(?:in|at|out of)\s+", "lives in", kind="place", firstperson=True)
_rule(S + r"(?:have\s+|'ve\s+)?(?:just\s+)?(?:moved|shifted|relocated)\s+(?:back\s+|over\s+)?to\s+", "lives in", kind="place", event=True)
_rule(IM + r"(?:originally\s+)?from\s+|\bi come from\s+|\bi grew up in\s+", "from", kind="place")
_rule(S2 + r"(?:work|working)\s+" + ADVS + r"(?:at|for|with)\s+", "works at", kind="org", firstperson=True)
_rule(r"\b(?:i|i've|i have|we)\s+(?:just\s+|recently\s+)?(?:joined|started at|started working at|got hired at|got hired by|"
      r"(?:got|started|landed|accepted)\s+an?\s+(?:new\s+)?(?:job|role|position|offer|internship)\s+(?:at|with|from))\s+", "works at",
      kind="org", event=True)
_rule(r"\bmy (?:job|company|employer|workplace|office) is (?:at\s+)?", "works at", kind="org")
_rule(S + r"(?:work|working)\s+as\s+(?:an?\s+)?|\bmy job is\s+(?:an?\s+)?|\bmy role is\s+(?:an?\s+)?|\bi'm working as\s+(?:an?\s+)?", "is", kind="role")
_rule(IM + r"(?:an?\s+)?(?:big\s+|huge\s+|massive\s+)?fan of\s+", "likes")
_rule(IM + r"an?\s+(?!(?:bit|little|lot|big fan|huge fan|fan)\b)", "is", kind="role", maxwords=4)
_rule(IM + r"(?:an?\s+)?(?=(?:" + "|".join(sorted(IDENTITY, key=len, reverse=True)) + r")\b)", "is", kind="role", one=True)
_rule(IM + r"(?:very\s+|severely\s+|mildly\s+|slightly\s+)?allergic to\s+", "allergic to")
_rule(S + r"(?:don't|do not|can't|cannot|never)\s+eat\s+", "avoids")
_rule(S + r"(?:have got|'ve got|have|own|got|bought|purchased|ordered|drive|ride)\s+" + NOT_OBJ, "has")
_rule(S2 + r"(?:use|using|run|running|self-?host|host|hosting|rely on|daily[- ]drive|swear by|stick with|went with|chose|"
      r"picked|design in|code in|write in|develop in|program in|edit in|coding in|writing in|programming in)\s+" + NOT_OBJ, "uses",
      firstperson=True)
_rule(S2 + r"(?:play|playing)\s+(?:the\s+)?" + NOT_OBJ + r"(?!with\b|around\b|(?:\S+\s+)?(?:files?|videos?|clips?|media|movies?|"
      r"songs?|music files|back)\b)", "plays", firstperson=True)
_rule(S2 + r"(?:do|practice|practise|go)\s+(?=[a-z]+ing\b)", "does", firstperson=True)
_rule(IM + r"on an?\s+(?=\w+\s+diet\b)", "is", kind="role", one=True)
_rule(IM + r"(?=(?:lactose intolerant|gluten intolerant|gluten free|left handed|colou?r ?blind|a night owl|an early bird|"
      r"a morning person|a night person)\b)", "is", kind="role", maxwords=3)
_rule(r"\b(?:i|we)(?:'ve| have)?\s+(?:just\s+|recently\s+|finally\s+)?(?:installed|set up|setup|started using|deployed|"
      r"switched over to|switched to|migrated to|moved over to|changed to|upgraded to|started with)\s+", "uses", event=True)
_rule(r"(?:^|[,;]\s*|\band\s+|\bnow\s+)(?:switched|migrated|moved over|changed|upgraded)\s+to\s+", "uses", event=True)
_rule(S2 + r"(?:like|love|enjoy|prefer|adore|dig|really like)\s+" + NOT_OBJ + r"(?!being\b|the way\b)", "likes", firstperson=True)
_rule(IM + r"into\s+", "likes")
_rule(S + r"(?:hate|dislike|detest|can't stand|cannot stand|don't like|do not like|don't enjoy|really don't like)\s+" + NOT_OBJ, "dislikes")
_rule(IM + r"not (?:a\s+)?(?:big\s+)?fan of\s+", "dislikes")
_rule(IM + r"(?:building|making|creating|working on|developing|writing|designing|coding|setting up|redesigning|rebuilding|"
      r"prototyping|hacking on|launching)\s+" + NOT_OBJ + r"(?!on\b)", "working on", kind="project")
_rule(r"\bmy (?:side\s+)?project(?:'s| is)\s+(?:called\s+)?", "working on", kind="project")
_rule(S + r"(?:built|made|created|launched|shipped|developed|published|released|coded)\s+" + NOT_OBJ, "built", kind="project")
_rule(r"\b(?:learn|learning|studying|to study|practicing|practising|get better at|getting better at|improve at|improving at|"
      r"improve my|improving my|to master|mastering|brush up on|brushing up on)\s+(?:about\s+|more\s+|some\s+|how to\s+)?", "learning",
      kind="skill", firstperson=True)
_rule(S + r"(?:study|am studying|'m studying|major in|am majoring in|'m majoring in)\s+", "studies", kind="skill")
WANT = re.compile(r"\b(?:i|we)(?:'d|'m|'ll|'re)?\s+(?:(?:really|also|still|kinda|seriously)\s+)?(?:want|would like|like|love|plan|"
                  r"am planning|planning|am going|going|hope|am hoping|hoping|intend|am thinking (?:of|about)|thinking (?:of|about)|"
                  r"am considering|considering|might|may)\s+(?:to\s+)?(buy|get|visit|try|switch to|move to|travel to|go to|build|"
                  r"adopt|upgrade to|buying|"
                  r"getting|visiting|trying|switching to|moving to|building|adopting|upgrading to)\s+", re.I)
WANT_REL = {"buy": "wants", "get": "wants", "adopt": "wants", "visit": "wants to visit", "travel to": "wants to visit",
            "go to": "wants to visit", "try": "wants to try", "switch to": "wants to switch to", "upgrade to": "wants to switch to",
            "move to": "plans to move to", "build": "wants to build"}
WANT_VERB = {"buying": "buy", "getting": "get", "visiting": "visit", "trying": "try", "switching to": "switch to",
             "moving to": "move to", "building": "build", "adopting": "adopt", "upgrading to": "upgrade to"}
NEG = re.compile(r"\b(?:i|we)\s+(?:(?:really|just|actually|kinda)\s+)?(?:don't|do not|no longer|never|don't really|stopped)\s+"
                 r"(use|using|run|running|have|own|live in|living in|work at|work for|working at|working for|like|love|drive)\s+", re.I)
DROP = re.compile(r"\b(?:i|we)(?:'ve| have)?\s+(?:(?:finally|just|recently|already)\s+)?(stopped using|quit using|gave up on|gave up|"
                  r"dropped|uninstalled|ditched|got rid of|sold|deleted|abandoned|moved off|moved away from|switched away from|"
                  r"left|quit|moved out of)\s+(?:of\s+)?", re.I)
USED_TO = re.compile(r"\b(?:i|we)\s+used to\s+(use|live in|work at|work for|have|own|like|love|run)\s+", re.I)
CHANGE = re.compile(r"\b(switched|moved|migrated|changed|went|upgraded|shifted)\s+(?:over\s+)?from\s+(.+?)\s+to\s+(.+)$", re.I)
REPLACED = re.compile(r"\breplaced\s+(?:my\s+)?(.+?)\s+with\s+(.+)$", re.I)
VERB_REL = {"use": "uses", "using": "uses", "run": "uses", "running": "uses", "have": "has", "own": "has", "drive": "has",
            "live in": "lives in", "living in": "lives in", "work at": "works at", "work for": "works at",
            "working at": "works at", "working for": "works at", "like": "likes", "love": "likes",
            "stopped using": "uses", "quit using": "uses", "gave up on": "uses", "gave up": "uses", "dropped": "uses",
            "uninstalled": "uses", "ditched": "uses", "deleted": "uses", "abandoned": "uses", "moved off": "uses",
            "switched away from": "uses", "got rid of": "has", "sold": "has", "moved away from": "lives in",
            "moved out of": "lives in", "left": None, "quit": None}
POSSESSIVE = re.compile(r"\bmy\s+(?P<kin>(?:" + "|".join(sorted(KIN, key=len, reverse=True)) + r"))'s\s+|\bmy\s+", re.I)
SLOT = re.compile(r"\bmy\s+(?P<s>(?:[a-z][\w-]*\s+){0,3}?[a-z][\w-]*)(?:'s\s+(?P<attr>[a-z][\w -]{1,20}?))?\s+(?:is|are|was)\s+"
                  r"(?:called\s+|named\s+)?", re.I)
KIN_RE = re.compile(r"\bmy\s+(?P<kin>" + "|".join(sorted(KIN, key=len, reverse=True)) + r")(?:'s name is|\s+is\s+(?:called|named)|"
                    r"\s+(?:called|named)|,)?\s+(?P<name>[A-Za-z][a-z]+)\b", re.I)
TOOLISH = set("editor ide os distro browser vpn stack setup db database shell terminal language framework".split())  # my X is Y -> uses Y
DEVICE = set("phone laptop server nas router gpu cpu keyboard car bike computer pc desktop tablet watch camera monitor machine rig "
             "workstation console".split())
ATTRIBUTE = set("budget salary income rent age height weight birthday timezone deadline plan goal username handle email address "
                "number score rank level size price cost schedule routine name".split())   # my X is Y: remember, don't own it
PROJECTISH = set("tool bot worker dashboard script pipeline extension plugin library framework engine api service platform".split())
VENTURE = set("startup company business app project product band channel podcast blog website site game agency shop".split())
INSTRUMENT = re.compile(r"\b(?:with|using|via|through|in|on)\s+(?:my\s+|a\s+|an\s+|the\s+)?", re.I)
IS_HOW = re.compile(r"^\s*(?P<e>[\w .+-]{2,30}?)\s+is\s+(?:how|what)\s+(?:i|we)\s+(?:use|reach|access|connect|run|manage|host|"
                    r"deploy|get|stay|work|code|edit|write)\b", re.I)


class Clause:
    def __init__(self, s):
        self.s = s
        self.toks = tokenize(s)
        self.words = [w for w, _, _ in self.toks]
        self.tags = tag(self.words)
        self.appos = {}

    def at(self, pos):
        """Index of the first token starting at or after character pos."""
        return next((i for i, (_, a, _) in enumerate(self.toks) if a >= pos), len(self.toks))

    def objects(self, i, maxwords=5, lists=True):
        """Noun phrases starting at token i: 'jellyfin, pihole and n8n in docker' -> ([jellyfin, pihole, n8n], stop index)."""
        items, cur = [], []
        w, t = self.words, self.tags
        while i < len(w):
            l = w[i].lower()
            if l in CUT and cur:
                break
            if l in ("called", "named") and cur and i + 1 < len(w) and t[i + 1] in "N":
                name, j = Clause(" ".join(w[i + 1:])).objects(0, maxwords=4, lists=False)
                if name:
                    self.appos[name[0]] = " ".join(x for x in cur if x.lower() not in STRIP)
                    cur = name[0].split()
                i += 1 + j
                break
            if t[i] == "N" or (t[i] == "V" and cur and w[i - 1][:1].isupper()):
                cur.append(w[i])
            elif t[i] == "D" and not cur:
                pass
            elif t[i] == "V" and not cur and l == "used":
                pass
            elif l == "," and cur and i + 1 < len(w) and w[i + 1].lower() in ("a", "an") and not items:
                desc, j = Clause(" ".join(w[i + 2:])).objects(0, maxwords=4, lists=False)
                if desc:
                    self.appos[" ".join(cur)] = desc[0]
                i += 2 + j
                break
            elif lists and l in ("and", "or", ",", "&", "plus", "/") and cur and i + 1 < len(w) and \
                    (t[i + 1] in "ND" or (t[i + 1] == "R" and i + 2 < len(w) and t[i + 2] == "N")):
                items.append(cur)
                cur = []
                if t[i + 1] == "R":
                    i += 1
            else:
                break
            i += 1
        if cur:
            items.append(cur)
        out = []
        for words in items:
            words = list(words)
            while words and words[0].lower() in STRIP:
                words.pop(0)
            while words and (words[-1].lower() in STOP or words[-1].lower() in TEMPW) and \
                    not (len(words) == 1 and words[0][:1].isupper() and len(words[0]) > 1):
                words.pop()
            lab = " ".join(words[:maxwords]).strip(" '")
            low = lab.lower()
            if lab and low not in NOT_THING and (low not in STOP or key(lab) in GAZ) and not low.isdigit() and not (set(low.split()) & SECRETISH) \
                    and len(lab) > 1 and lab not in out:
                out.append(lab)
        return out, i

    def next_word(self, i):
        return self.words[i].lower() if i < len(self.words) else ""


def _typed(lab, rel, kind):
    k = key(lab)
    if k in GAZ or category_of(k):
        return (k, label_of(k, lab), "tech")
    if " " not in lab and lab.islower() and lab.lower() in PROPER:
        lab = PROPER[lab.lower()]
    typ = {"named": "name", "age": "value"}.get(rel, kind or "thing")
    if typ in ("place", "person", "org", "name") and lab.islower() and re.fullmatch(r"[a-z][a-z ]*", lab):
        lab = lab.title()                                                # "pune" -> "Pune"
    return (k, lab, typ)


def facts(s, md=None, prev_person=None, prev_thing=None):
    """Relations stated in one clause -> (relations, entities, slots, retracts, person).
    relations: [(subj_key, rel, obj_key)], retracts: [(subj_key, rel|None, obj_key)] (rel None = whatever the user had)."""
    md = md or mood(s)
    c = Clause(s)
    rels, ents, slots, retracts = [], [], [], []
    person = prev_person
    low = s.lower()
    firstperson = bool(re.search(r"\b(i|i'm|i've|i'd|my|me|we|we're|our)\b", low))

    def add(subj, rel, lab, kind=None):
        e = _typed(lab, rel, kind)
        if not e[0] or e[0] == "secret":
            return None
        ents.append(e)
        rels.append((subj, rel, e[0]))
        if subj == "me" and rel in EXCLUSIVE:
            slots.append("me." + rel)
        return e[0]

    # 1. possessions show up even in questions: "why does my docker keep crashing" -> uses docker
    for m in POSSESSIVE.finditer(s):
        if m["kin"]:
            ents.append((key("my " + m["kin"]), "your " + m["kin"].lower(), "person"))
            rels.append(("me", m["kin"].lower(), key("my " + m["kin"])))
            continue
        objs, _ = c.objects(c.at(m.end()), maxwords=5, lists=False)
        if not objs:
            continue
        o = " ".join(w for w in objs[0].split() if not (w.lower() in VERB and VERB[w.lower()] != w.lower()
                                                           and not w.lower().endswith("ing"))) or objs[0]   # "my sent messages"
        head = o.split()[-1].lower()
        first_w = o.split()[0].lower()
        if (head in VENTURE or head in PROJECTISH) and len(o.split()) > 1:   # "my youtube thumbnail automation project"
            for k2, lab2, typ2 in entities(o):
                if typ2 == "tech":
                    ents.append((k2, lab2, "tech"))
                    rels.append(("me", "uses", k2))
            if md != "hypothetical":
                add("me", "working on", o, "project")
            continue
        if key(head) in NOT_THING or head.rstrip("s") in NOT_THING:
            continue
        km = KIN_RE.match(s[m.start():])
        named_kin = km and not (km["name"].lower() in STOP or (is_word(km["name"]) and not km["name"][0].isupper()
                                                               and km["name"].lower() not in PROPER))
        if o.lower() in KIN and not named_kin:
            kk = key("my " + o.lower())
            ents.append((kk, "your " + o.lower(), "person"))
            rels.append(("me", o.lower(), kk))
            if md == "statement":
                _about(s[m.end() + len(o):], kk, add)
            continue
        if head in KIN or first_w in KIN or head in SECRETISH or head in ATTRIBUTE or re.match(r"fav(?:ou?rite)?\b", first_w):
            continue
        if head in VENTURE and re.match(r"\s*(?:is|was)\s+(?:called|named)\b", s[m.end() + len(o):], re.I):
            continue
        techs = [e for e in entities(o) if e[2] == "tech"]
        if techs:
            for k, lab, _ in techs:
                ents.append((k, lab, "tech"))
                rels.append(("me", "uses", k))
        elif md != "hypothetical":
            add("me", "has", o, "thing")
    if md == "question":
        return _dedupe(rels), ents, slots, retracts, person

    # 2. wishes and plans hold even in hypothetical clauses
    for m in WANT.finditer(s):
        verb = WANT_VERB.get(m[1].lower(), m[1].lower())
        rel = WANT_REL.get(verb, "wants")
        for o in c.objects(c.at(m.end()))[0]:
            add("me", rel, o, "place" if "visit" in rel or "move" in rel else "thing")
    if md == "hypothetical":
        return _dedupe(rels), ents, slots, retracts, person

    # 3. retractions and changes of state
    if m := CHANGE.search(s):
        rel = "lives in" if m[1].lower() in ("moved", "shifted") else "uses"
        for o in Clause(m[2]).objects(0, lists=False)[0]:
            retracts.append(("me", rel, key(o)))
        for o in Clause(m[3]).objects(0, lists=False)[0]:
            add("me", rel, o, "place" if rel == "lives in" else None)
    if m := REPLACED.search(s):
        old = Clause(m[1]).objects(0, lists=False)[0]
        device = any(w in DEVICE for o in old for w in o.lower().split())
        for o in old:
            retracts.append(("me", None, key(o)))
        for o in Clause(m[2]).objects(0, lists=False)[0]:
            add("me", "has" if device else "uses", o)
    for rx in (NEG, USED_TO, DROP):
        for m in rx.finditer(s):
            rel = VERB_REL.get(m[1].lower(), "uses")
            for o in c.objects(c.at(m.end()))[0]:
                retracts.append(("me", rel, key(o)))

    # 4a. "it is an attendance tracking app": the thing the conversation was about
    if prev_thing and (m := re.match(r"\s*(?:it|this|that)(?:\s+is|'s|\s+was)\s+(?:an?\s+|the\s+)?", s, re.I)):
        for o in c.objects(c.at(m.end()), maxwords=4, lists=False)[0]:
            if o.lower() not in FEELING:
                ents.append(prev_thing)
                add(prev_thing[0], "is", o, "thing")
    # 4. kin with names: "my sister priya is a doctor in pune"
    for m in KIN_RE.finditer(s):
        name = m["name"]
        if name.lower() in STOP or (is_word(name) and not name[0].isupper() and name.lower() not in PROPER):
            continue
        k = key(name)
        kin_k = key("my " + m["kin"])
        ents[:] = [e for e in ents if e[0] != kin_k]
        rels[:] = [r for r in rels if r[2] != kin_k]
        ents.append((k, name.title() if name.islower() else name, "person"))
        rels.append(("me", m["kin"].lower(), k))
        person = k
        _about(s[m.end():], k, add)
    if person and re.match(r"\s*(?:she|he|they)\b", low):
        _about(re.sub(r"^\s*(?:she|he|they)\b", "", s, flags=re.I), person, add)

    # 5. the rule table
    retracted = {r[2] for r in retracts}
    for rx, rel, opt in RULES:
        if opt.get("firstperson") and not firstperson:
            continue
        for m in rx.finditer(s):
            i = c.at(m.end())
            if opt.get("number"):
                n = re.match(r"\s*(\d{1,3})\b", s[m.end():])
                if n and 5 <= int(n[1]) <= 110:
                    add("me", rel, n[1], "value")
                continue
            if opt.get("one"):
                w = c.words[i] if i < len(c.words) else ""
                if not w or w.lower() in FEELING or w.lower() in STOP:
                    continue
                if opt.get("namecheck") and not (w.isalpha() and not is_word(w) and w.lower() not in VERB):
                    continue
                add("me", rel, w.title() if w.islower() and rel == "named" else w, opt.get("kind"))
                if rel == "named" and c.next_word(i + 1) == "," and c.next_word(i + 2) in ("a", "an"):
                    desc, stop = c.objects(i + 3, maxwords=3, lists=False)
                    for o in desc:
                        add("me", "is", o, "role")
                    if c.next_word(stop) == "from":
                        for o in c.objects(stop + 1, lists=False)[0]:
                            add("me", "from", o, "place")
                continue
            if rel in ("uses", "likes", "plays") and c.next_word(i) == "my":
                continue
            objs, stop = c.objects(i, maxwords=opt.get("maxwords", 5))
            if rel == "is" and objs and c.next_word(stop) in ("at", "for", "with") and stop + 1 < len(c.words):
                for o in c.objects(stop + 1, lists=False)[0]:   # "a software engineer at google"
                    add("me", "works at", o, "org")
            for o in objs:
                if key(o) in retracted or (rel == "is" and o.lower() in FEELING):
                    continue
                k = add("me", rel, o, opt.get("kind"))
                if k and o in c.appos:                   # "hearthlink, a voice intercom" -> hearthlink is voice intercom
                    add(k, "is", c.appos[o], "thing")
                    if rel == "named":
                        add("me", "is", c.appos[o], "role")
            # "... like angular" / "such as X": examples share the relation
            if objs and c.next_word(stop) in ("like", "such", "especially", "including") and rel in ("likes", "dislikes", "uses"):
                for o in c.objects(stop + (2 if c.next_word(stop) == "such" else 1))[0]:
                    add("me", rel, o)
            # "in docker", "with pillow": the tool it is done with
            if objs and stop and rel in ("uses", "working on", "has", "learning"):
                for mm in INSTRUMENT.finditer(s, c.toks[stop - 1][2]):
                    _tool(s[mm.end():], ents, rels, retracted)
    # "i mostly design in figma", "i reach my homelab with tailscale"
    if firstperson and re.search(r"\b(?:i|we)\s+(?:\w+\s+){0,2}?(?:design|code|build|write|edit|reach|access|connect|deploy|host|"
                                 r"manage|work|develop|program|make|run|stream|backup|back up)\b", low):
        for mm in INSTRUMENT.finditer(s):
            _tool(s[mm.end():], ents, rels, retracted)
    if m := IS_HOW.search(s):
        for k, lab, typ in entities(m["e"]):
            if typ == "tech":
                ents.append((k, lab, "tech"))
                rels.append(("me", "uses", k))

    # 6. "my X is Y": attributes, favourites, tools
    for m in SLOT.finditer(s):
        subj = " ".join(w for w in m["s"].split() if w.lower() not in STRIP)
        if not subj:
            continue
        sl = subj.lower()
        if set(sl.split()) & SECRETISH or (m["attr"] and set(m["attr"].lower().split()) & SECRETISH):
            continue
        if sl in KIN and not m["attr"]:
            continue
        objs, _ = c.objects(c.at(m.end()))
        if re.match(r"fav(?:ou?rite)?\b", sl):
            what = sl.split(None, 1)[1] if " " in sl else "thing"
            for o in objs:
                add("me", "likes", o)
            slots.append("me.favourite " + what)
            continue
        if sl.split()[0] in KIN:                      # "my girlfriend's birthday is ..."; named kin is the kin rule's job
            if m["attr"]:
                slots.append("me.%s.%s" % (key(sl), key(m["attr"])))
            continue
        if sl in ("name", "age", "job", "company", "employer", "role", "workplace", "office"):
            continue
        slots.append("me.%s.%s" % (key(subj), key(m["attr"]) if m["attr"] else "is"))
        if set(sl.split()) & ATTRIBUTE or sl in NOT_THING:
            for k2, lab2, typ2 in entities(subj):
                if typ2 == "tech":
                    ents.append((k2, lab2, "tech"))
                    rels.append(("me", "uses", k2))
            continue
        named = re.search(r"(?:called|named)\s+$", s[:m.end()], re.I)
        if named and objs:
            if sl.split()[-1] in VENTURE:            # "my startup is called nimbus"
                k2 = add("me", "working on", objs[0], "project")
                add(k2, "is", subj, "thing")
            else:                                     # "my car is called herbie"
                k2 = add("me", "has", objs[0], "thing")
                add(k2, "is", subj, "thing")
            continue
        k = add("me", "uses" if key(subj) in GAZ else "has", subj, "thing")
        if sl in TOOLISH:
            for o in objs:
                if entities(o) or namey(o.split()[0]) or key(o) in GAZ:
                    add("me", "uses", o)
        else:
            for o in objs:
                inner = entities(o)
                if inner and len(o.split()) <= 4:     # "my laptop is a thinkpad t480" -> laptop is ThinkPad T480
                    e = inner[0] if len(inner) == 1 and inner[0][1].lower() == o.lower() else _typed(o, "is", "thing")
                    ents.append(e)
                    rels.append((k, "is", e[0]))
                    if sl in DEVICE:
                        rels.append(("me", "has", e[0]))
    gone = {r[2] for r in retracts}
    rels = [r for r in rels if not (r[0] == "me" and r[2] in gone)]
    return _dedupe(rels), ents, slots, retracts, person


def _tool(after, ents, rels, retracted):
    for k, lab, typ in entities(after[:40])[:1]:
        if typ == "tech" and after.lower().startswith(lab.lower()[:3]) and k not in retracted:
            ents.append((k, lab, "tech"))
            rels.append(("me", "uses", k))


def _about(rest, subj, add):
    """Facts about a third party: 'is a doctor in pune', 'works at google', 'lives in pune'."""
    c = Clause(rest)
    if m := re.match(r"\s*(?:is|'s|works as|was)\s+(?:an?\s+)?", rest, re.I):
        objs, stop = c.objects(c.at(m.end()), maxwords=3, lists=False)
        for o in objs:
            if o.lower() not in FEELING:
                add(subj, "is", o, "role")
        if c.next_word(stop) in ("in", "at", "from") and stop + 1 < len(c.words):
            for o in c.objects(stop + 1, lists=False)[0]:
                add(subj, "lives in" if c.next_word(stop) != "at" else "works at", o, "place")
    for rx, rel in ((r"\b(?:lives|living|stays|based)\s+in\s+", "lives in"), (r"\bworks?\s+(?:at|for)\s+", "works at"),
                    (r"\b(?:likes|loves)\s+", "likes"), (r"\bstudies\s+", "studies")):
        for m in re.finditer(rx, rest, re.I):
            for o in c.objects(c.at(m.end()))[0]:
                add(subj, rel, o, "place" if rel == "lives in" else None)


def _dedupe(rels):
    seen, out = set(), []
    for r in rels:
        if r not in seen and r[0] != r[2]:
            seen.add(r)
            out.append(r)
    return out


def links(s, ents):
    """Relations between named things in one clause: 'jellyfin keeps crashing on my server' -> (jellyfin, keeps crashing on, server)."""
    c = Clause(s)
    low = [w.lower() for w in c.words]
    spans = []
    for k, lab, _ in ents:
        first = lab.lower().split()[0]
        n = len(lab.split())
        for i in range(len(low)):
            if low[i] == first or key(low[i]) == k:
                spans.append((i, i + n, k))
                break
    spans.sort()
    out = []
    for (a0, a1, ka), (b0, b1, kb) in zip(spans, spans[1:]):
        between = list(range(a1, b0))
        if not 1 <= len(between) <= 5 or ka == kb:
            continue
        tg = [c.tags[i] for i in between]
        if "V" not in tg or any(t in ".CQ" for t in tg) or any(low[i] in ("i", "i'm", "you", "we") for i in between):
            continue
        rel = " ".join(low[i] for i in between if c.tags[i] in "VPAR" and low[i] not in ("is", "are", "was", "be", "my", "the"))
        if rel and rel not in ("called", "named", "is called", "is named"):
            out.append((ka, rel[:40], kb))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# terms and similarity
# ---------------------------------------------------------------------------------------------------------------------
def terms(text, ents=(), phr=()):
    text = re.sub(r"(\w)'(\w)", r"\1\2", text.lower())             # don't -> dont (a stop word), not "don" + "t"
    t = Counter(stem(w) for w in re.findall(r"[a-z0-9][a-z0-9+#.-]*[a-z0-9+#]|[a-z0-9]", text)
                if w not in STOP and len(w) > 1 and not w.isdigit() and w != "secret")
    for k, _, _ in ents:
        t["@" + k] += 2  # shared named things count double
    for p in phr:
        t["#" + p] += 1  # shared phrases, so recurring ones can become concepts
    return dict(t)


def cosine(a, b, idf):
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    dot = sum(v * b[t] * idf(t) ** 2 for t, v in a.items() if t in b)
    if not dot:
        return 0.0
    na = math.sqrt(sum((v * idf(t)) ** 2 for t, v in a.items()))
    nb = math.sqrt(sum((v * idf(t)) ** 2 for t, v in b.items()))
    return dot / (na * nb)


# ---------------------------------------------------------------------------------------------------------------------
# a whole message
# ---------------------------------------------------------------------------------------------------------------------
EXPLICIT = re.compile(GREET + r"(?:(?:can|could|would|will) you\s+|please\s+)?(?:remember|note|keep in mind|don't forget|"
                      r"make a note|for (?:the|your) record|fyi|for future reference)(?: that)?[:,]?\s+", re.I)


# Words that only steer an agent ("check if it works", "what happened", "integrate it then"): a short message made of
# these and function words names nothing about the user, so it isn't a memory (it stays in the chat's transcript).
STEER = {stem(w) for w in """check chek fix do done happen happened happend integrate continue work working try run test proceed go
    ahead again retry start stop wait show see look finish implement apply update redo undo build deploy push commit""".split()}


def steering(body):
    words = re.findall(r"[a-z0-9#+]+", body.lower())  # "i run 5k" keeps its 5k: numbers are content
    return 0 < len(words) <= 10 and all(w in STOP or w.isalpha() and len(w) <= 2 or stem(w) in STEER for w in words)


def analyse(text, ref=None, prev=None):
    """Raw message -> memories. Personal statements become one memory each; questions/tasks collapse into one topic memory.
    prev: the named thing the conversation was last about, so "it is ..." has a subject."""
    body = clean(redact(text))
    if not body or all(w in ACK for w in re.findall(r"[a-z]+", body.lower())) or steering(body):
        return []
    sents = sentences(body)
    long_paste = len(body) > 1500  # pasted docs and logs: keep personal lines and the first line only
    out, rest, person = [], [], None
    for s in sents:
        explicit = bool(EXPLICIT.search(s))
        if explicit:                                  # "can you remember that I prefer short answers?" is a statement
            s = EXPLICIT.sub("", s).rstrip("?. ") or s
        md = mood(s)
        t = classify(s, md)
        found = entities(s)
        rels, extra, slots, retracts, person = facts(s, md, person, prev)
        ents = list({e[0]: e for e in found + extra}.values())
        big = {w for e in extra for w in e[0].split() if len(e[0].split()) > 1}
        ents = [e for e in ents if not (e[2] == "name" and e[0] in big)]
        rels += [r for r in links(s, [e for e in ents if e[2] != "value"]) if r not in rels]
        prev = next((e for e in ents if e[2] in ("name", "project", "tech") and e[0] != "me"), prev)
        at, tense = when(s, ref)
        if t in ("note", "fact") and tense == "past" and PAST_V.search(s) and (rels or retracts):
            t = "event"
        if t == "note" and md == "statement" and (retracts or any(r[0] == "me" for r in rels)):
            t = "event" if PAST_V.search(s) else "fact"
        personal = t in PERSONAL and md != "question"
        conf = 1.0 if explicit else .9 if personal and md == "statement" else .6 if md == "hypothetical" else .5
        if explicit and t not in PERSONAL:
            t, personal = "fact", True
        phr = phrases(s)
        mem = dict(text=s[:500], type=t, mood=md, entities=ents, relations=rels, retracts=retracts, slots=slots, when=at,
                   conf=conf, phrases=phr)
        if personal:
            mem["importance"] = min(1, IMPORTANCE[t] + .03 * min(len(ents), 3) + (.05 if at else 0) + (.1 if explicit else 0))
            mem["terms"] = terms(s, ents, phr)
            out.append(mem)
        elif not long_paste or s is sents[0] or rels:
            rest.append(mem)
    if rest:
        s = " ".join(m["text"] for m in rest)[:500]
        if len(s) >= 12:
            ents = list({e[0]: e for m in rest for e in m["entities"]}.values())
            named = [e for e in ents if e[2] in ("tech", "name")]
            rels = [r for m in rest for r in m["relations"]]
            rels += [(a[0], "related", b[0]) for i, a in enumerate(named) for b in named[i + 1:]][:8]
            phr = sorted({p for m in rest for p in m["phrases"]})
            t = rest[0]["type"]
            at = next((m["when"] for m in rest if m["when"]), None)
            out.append(dict(text=s, type=t, mood=rest[0]["mood"], entities=ents, relations=_dedupe(rels),
                            retracts=[r for m in rest for r in m["retracts"]], slots=[], when=at, conf=.5, phrases=phr,
                            importance=min(1, IMPORTANCE[t] + .03 * min(len(ents), 3)), terms=terms(s, ents, phr)))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# the query side
# ---------------------------------------------------------------------------------------------------------------------
INTENTS = [  # question pattern -> relation(s) it asks about
    (r"\bwhere\b.*\b(live|lived|living|stay|stayed|based|home)\b|\b(my|which) (city|town|place)\b|\bwhere am i\b|\bwhere.*\bi (?:moved|am)\b", ["lives in"]),
    (r"\bwhere\b.*\bwork(ed)?\b|\b(my|which) (job|company|employer|office|workplace)\b|\bwho do i work for\b|\bwhat do i do for (?:a living|work)\b", ["works at", "is"]),
    (r"\b(what'?s|what is|tell me) my name\b|\bwho am i\b|\bmy name\b", ["named"]),
    (r"\bhow old\b|\bmy age\b", ["age"]),
    (r"\bwhat do i do\b|\bmy (profession|role)\b|\bwhat'?s my job\b", ["is", "works at"]),
    (r"\bwhat (?:\w+ )?(?:do|am) i (?:use|using|run|running)\b|\bwhich \w+(?: \w+)? do i (?:use|run)\b|\bmy (stack|setup|tools)\b|\bwhat (?:\w+ ){0,2}do i use\b", ["uses"]),
    (r"\bwhat (?:\w+ ){0,2}do i (?:have|own)\b|\bwhich \w+ do i (?:have|own)\b|\bmy (car|laptop|phone|server|gpu|computer|pc|nas)\b", ["has"]),
    (r"\bwhat do i (like|love|enjoy)\b|\bmy (favou?rite|interests|hobbies)\b|\bwhat am i into\b|\b(music|food|movie) taste\b|\bmy \w+ taste\b", ["likes"]),
    (r"\bwhat do i (hate|dislike)\b|\bwhat don'?t i like\b", ["dislikes"]),
    (r"\bwhat am i (building|making|working on|developing|creating)\b|\bmy (side )?projects?\b|\bwhat.*\bi'?m (building|working on)\b", ["working on"]),
    (r"\bwhat am i (learning|studying)\b|\bi'?m learning\b|\bi am learning\b|\blanguages? (?:am )?i'?m? learning\b", ["learning", "studies"]),
    (r"\ballerg", ["allergic to", "avoids"]),
    (r"\bwhat (?:do|would) i want\b|\bmy (wishlist|plans)\b", ["wants", "plans to move to", "wants to visit", "wants to try"]),
]
KIN_Q = re.compile(r"\bmy (" + "|".join(sorted(KIN, key=len, reverse=True)) + r")\b", re.I)


SYN_OF = {}  # stemmed word -> stemmed words that mean the same (problems ~ crash ~ bug)
for _g in SYNONYMS:
    _st = {stem(w) for x in _g for w in x.split()}
    for _w in _st:
        SYN_OF.setdefault(_w, set()).update(_st)


def expand(q):
    """Query words plus their synonyms (graphics card -> gpu)."""
    low = " " + re.sub(r"[^\w\s'-]", " ", q.lower()) + " "
    extra = [w for g in SYNONYMS if any(" %s " % x in low or " %ss " % x in low for x in g) for w in g]
    return q + " " + " ".join(extra)


def query(q):
    """Understand a question: expanded text, terms, named things, categories, relation intent, kin, time window."""
    low = clean(q).lower()
    x = expand(low)
    base = entities(q)
    ents = base + [e for e in entities(x) if e[0] not in {k for k, _, _ in base}]
    cats = sorted({CAT_FROM_WORD[w] for w in re.findall(r"[a-z]+", low) if w in CAT_FROM_WORD})
    intent = []
    for rx, rels in INTENTS:
        if re.search(rx, low):
            intent += [r for r in rels if r not in intent]
    kin = [m[1].lower() for m in KIN_Q.finditer(low)]
    if kin and not intent:
        intent = ["kin"]
    fav = re.search(r"\bfavou?rite (\w+)", low)
    at, tense = when(low)
    window = None
    if at and re.search(r"\b(yesterday|today|last|ago|this|week|month)\b", low):
        window = (at - 86400 * (7 if "week" in low else 31 if "month" in low else 1.5), at + 86400 * 1.5)
    about_me = bool(re.search(r"\b(about me|who am i|my (profile|preferences|facts|details|info)|about myself|know about me)\b", low))
    first_person = bool(re.search(r"\b(i|me|my|mine|myself|i'm|i've)\b", low))
    types = {"likes": ["preference"], "dislikes": ["preference"], "working on": ["goal"], "learning": ["goal"],
             "wants": ["goal"]}.get(intent[0] if intent else "", [])
    past_at = at if at and (tense == "past" or re.search(r"\b(did|was|were|used to|back then|ago|last)\b", low)) else None
    return dict(text=x, terms=terms(x, ents), base=terms(low), entities=ents, cats=cats, intent=intent, kin=kin, at=past_at,
                favourite=fav[1] if fav else None, window=window, about_me=about_me, first_person=first_person, types=types)


# ---------------------------------------------------------------------------------------------------------------------
def selfcheck():
    def rel_set(text):
        return {r for m in analyse(text) for r in m["relations"]}

    def retr(text):
        return {r for m in analyse(text) for r in m["retracts"]}
    assert ("me", "has", "rd car") in rel_set("i have a rd car")
    m = analyse("My name is Maya and I live in Porto. I love self-hosting with Docker on Proxmox. How do I set up nginx?")
    assert [x["type"] for x in m] == ["fact", "fact", "preference", "question"], [x["type"] for x in m]
    assert m[0]["slots"] == ["me.named"] and ("me", "named", "maya") in m[0]["relations"], m[0]
    assert ("me", "lives in", "porto") in m[1]["relations"], m[1]
    assert {"docker", "proxmox"} <= {e[0] for e in m[2]["entities"]}
    assert "nginx" in {e[0] for e in m[3]["entities"]}
    r = rel_set("i run jellyfin, pihole and n8n in docker on it")
    assert r >= {("me", "uses", k) for k in ("jellyfin", "pihole", "n8n", "docker")}, r
    assert ("me", "uses", "postgresql") not in rel_set("should I use postgres or mysql for a small side project?")
    assert not rel_set("I don't have a car") and ("me", "has", "car") in retr("I don't have a car")
    assert not any("finish" in r[2] for r in rel_set("i have to finish the hearthlink firmware by friday"))
    r = rel_set("my sister priya is a doctor in pune")
    assert {("me", "sister", "priya"), ("priya", "is", "doctor"), ("priya", "lives in", "pune")} <= r, r
    assert ("me", "uses", "adguardhome") in rel_set("I don't use pihole anymore, switched to adguard home")
    assert ("me", "uses", "pihole") in retr("I don't use pihole anymore, switched to adguard home")
    assert ("me", "has", "rtx 3060") in rel_set("i bought a used rtx 3060 yesterday for 18k")
    assert ("me", "learning", "rust") in rel_set("i want to learn rust this year")
    assert ("me", "learning", "system design") in rel_set("i m tryna get better at system design for interviews")
    assert ("me", "is", "vegetarian") in rel_set("i'm vegetarian, suggest a quick dinner with paneer")
    assert ("me", "named", "maya") in rel_set("hi im maya, a product designer from porto")
    assert ("me", "likes", "dark knight") in rel_set("actually my favourite movie is the dark knight")
    assert ("me", "uses", "tailscale") in rel_set("Tailscale is how I reach my homelab from outside")
    assert ("laptop", "is", "thinkpad t480") in rel_set("my laptop is a thinkpad t480")
    assert ("me", "working on", "hearthlink") in rel_set("I'm working on Hearthlink, a voice intercom for my house using esp32 boards")
    r = rel_set("I'm 24 and I love cricket")
    assert ("me", "age", "24") in r and ("me", "likes", "cricket") in r, r
    assert "[secret]" in redact("my api key is sk-proj-abc123def456ghi789jkl012mno345pqr678 ok")
    assert redact("my wifi password is hunter2secret, thanks") == "my wifi password is [secret], thanks"
    assert redact("the token is expired") == "the token is expired"
    assert redact("auth disabled (pin 1423 present)") == "auth disabled (pin [secret] present)"
    assert analyse("ok") == [] and analyse("thanks!!") == []
    ref = time.mktime((2026, 9, 22, 12, 0, 0, 0, 0, -1))
    at, tense = when("i moved to lisbon last month", ref)
    assert tense == "past" and datetime.fromtimestamp(at).month == 8
    at, _ = when("my girlfriend's birthday is on 14 november", ref)
    assert datetime.fromtimestamp(at).strftime("%m-%d") == "11-14"
    assert query("where do I live")["intent"] == ["lives in"]
    assert query("which code editor do I use")["cats"] == ["editor"]
    idf = lambda t: 1.0
    assert cosine(terms("docker compose networking"), terms("docker networking bridge"), idf) > .5
    print("brain ok")


if __name__ == "__main__":
    selfcheck()
