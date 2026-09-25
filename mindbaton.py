#!/usr/bin/env python3
"""Mindbaton on the command line: the installer, the connector for other computers and the capture hooks. Stdlib only.

  ./install.sh   (= python3 mindbaton.py install)     set Mindbaton up on this computer
  python3 mindbaton.py connect [address]             connect this computer's AI tools to a Mindbaton on another one
                                                     (no address: find it on this network or Tailscale)
  python3 mindbaton.py import [--dry-run]            copy what your AI tools already remember (their memory files) in
  python3 mindbaton.py doctor                        check the server, your token and every connected tool; fix problems
  python3 mindbaton.py update                        get the latest version, test it and restart
  python3 mindbaton.py keys                          add, replace or remove the free Gemini / Groq keys
  python3 mindbaton.py models                        list the free AI models and pick the one Mindbaton uses
  python3 mindbaton.py uninstall [--purge]           remove what it added to your AI tools and stop the service
  python3 mindbaton.py hook <tool>                   (run by your AI tools) save one message; silent, never fails
  python3 mindbaton.py logo [--no-motion|--check]    draw the logo

Without a terminal (CI, Docker) or with --yes nothing is asked; answers come from flags:
  install --yes --username maya --password-file pw.txt [--display-name Maya] [--gemini-key K] [--groq-key K]
          [--tools claude,codex|all|none] [--port 3004] [--no-service] [--foreground] [--replace-old] [--import-memories]
Everything it does is written to ~/.mindbaton/install.log (secrets masked).
"""
import argparse
import atexit
import getpass
import hashlib
import ipaddress
import json
import os
import re
import select
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import textwrap
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent

# ── Logo ────────────────────────────────────────────────────────────────────────────────────────────────────
# The art is generated from assets/brand/mark.svg by assets/brand/make-icons.mjs (swap the logo, re-run it).
# Each size has quadrant-block cells ([char, fg, bg] palette indices, None = terminal background) with truecolor and
# xterm-256 palettes for dark and light terminals, plus braille and ASCII monochrome versions.

ART = HERE / 'assets/brand/terminal-logo.json'
BG_DARK, BG_LIGHT = (10, 10, 11), (255, 255, 255)  # what the truecolor reveal fades in from
_art = None


def color_mode(env=os.environ, out=sys.stdout):
    """'truecolor' | '256' | 'braille' | 'ascii': the richest logo this terminal shows well."""
    term = env.get('TERM', '')
    utf8 = 'utf' in (getattr(out, 'encoding', None) or '').lower()
    if env.get('NO_COLOR') or not out.isatty() or term in ('', 'dumb', 'linux'):  # linux console: 8 colours, no braille
        return 'braille' if utf8 and term != 'linux' else 'ascii'
    if env.get('COLORTERM') in ('truecolor', '24bit'):
        return 'truecolor'
    if '256' in term or term.startswith(('xterm', 'screen', 'tmux', 'rxvt')):  # every living xterm-alike has 256
        return '256'
    return 'braille' if utf8 else 'ascii'


def terminal_is_light(env=os.environ):
    """True when the terminal background is light (COLORFGBG, else asks the terminal). Unknown = dark."""
    fgbg = env.get('COLORFGBG', '').split(';')[-1]
    if fgbg.isdigit():
        return int(fgbg) == 7 or int(fgbg) > 8
    try:
        import termios
        import tty
        fd = os.open('/dev/tty', os.O_RDWR | os.O_NOCTTY)
    except (ImportError, OSError):
        return False
    try:
        old = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        # OSC 11 asks for the background colour; DA1 behind it is answered by every terminal, so a terminal that
        # ignores OSC 11 costs one round trip, never a timeout.
        os.write(fd, b'\x1b]11;?\x1b\\\x1b[c')
        buf, end = b'', time.monotonic() + 1
        while not re.search(rb'\x1b\[\?[\d;]*c', buf) and select.select([fd], [], [], max(0, end - time.monotonic()))[0]:
            buf += os.read(fd, 1024)
        termios.tcsetattr(fd, termios.TCSAFLUSH, old)
    except (termios.error, OSError):
        return False
    finally:
        os.close(fd)
    m = re.search(rb'rgb:([0-9a-f]+)/([0-9a-f]+)/([0-9a-f]+)', buf, re.I)
    if not m:
        return False
    r, g, b = (int(h, 16) / (16 ** len(h) - 1) for h in m.groups())
    return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.5


def _color(mode, c, base):
    """SGR parameters for a truecolor (r, g, b) or 256 index c, as fg (base 30) or bg (base 40); None = default."""
    if c is None:
        return f'{base + 9}'
    return f'{base + 8};5;{c}' if mode == '256' else f'{base + 8};2;{c[0]};{c[1]};{c[2]}'


def paint(text, hex_color, mode):
    """`text` in a brand colour ('#a1a1aa') in any colour mode; plain in the monochrome ones."""
    if mode not in ('truecolor', '256'):
        return text
    rgb = tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f'\x1b[{_color(mode, rgb if mode == "truecolor" else _to256(rgb), 30)}m{text}\x1b[39m'


def _to256(rgb):
    steps = (0, 95, 135, 175, 215, 255)
    cube = [(16 + 36 * r + 6 * g + b, (steps[r], steps[g], steps[b])) for r in range(6) for g in range(6) for b in range(6)]
    grey = [(232 + i, (8 + 10 * i,) * 3) for i in range(24)]
    return min(cube + grey, key=lambda c: sum((a - b) ** 2 for a, b in zip(c[1], rgb)))[0]


def logo(max_w=80, max_h=24, mode=None, light=None, mark_only=False, reveal=1.0):
    """The biggest lockup (else mark) that fits max_w × max_h cells → (lines, width); ([], 0) if none fits.
    Every line is exactly `width` cells wide. `reveal` 0..1 is the entrance sweep (see show_logo)."""
    global _art
    if not (_art or ART.exists()):
        return [], 0  # a copy without the art (connect on another computer): callers set the name in type
    _art = _art or json.loads(ART.read_text())
    mode = mode or color_mode()
    # An ASCII-shaded wordmark is illegible, so plain ASCII sets the name in type beside the mark.
    name = '   Mindbaton' if mode == 'ascii' and not mark_only else ''
    for kind in (('mark',) if mark_only or mode == 'ascii' else ('lockup', 'mark')):
        fits = [v for v in _art[kind] if v['cols'] + len(name) <= max_w and v['rows'] <= max_h]
        if fits:
            break
    else:
        return [], 0
    v = fits[-1]
    rows, cols = v['rows'], v['cols']
    # The sweep runs the way the baton travels: from bottom-left up and to the right, with a soft 6-cell edge.
    span, edge = cols + 2 * rows, 6
    front = reveal * (span + edge)
    shown = lambda x, y: max(0.0, min(1.0, (front - x - 2 * (rows - 1 - y)) / edge))
    if mode in ('braille', 'ascii'):
        return [''.join(ch if shown(x, y) >= 0.5 else ' ' for x, ch in enumerate(line.replace('⠀', ' ').ljust(cols)))
                + (name if y == rows // 2 and reveal >= 1 else ' ' * len(name))
                for y, line in enumerate(v[mode])], cols + len(name)
    light = terminal_is_light() if light is None else light
    pal = v['paletteLight' if light else 'palette']
    if mode == '256':
        pal256 = v['paletteLight256' if light else 'palette256']
    else:
        base = BG_LIGHT if light else BG_DARK
        pal = [tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for h in pal]
    lines = []
    for y, row in enumerate(v['cells']):
        out, state = [], None
        for x, (ch, fg, bg) in enumerate(row):
            k = shown(x, y)
            if ch == ' ' or k == 0 or (mode == '256' and k < 0.5):
                cell, fg, bg = ' ', state[0] if state else None, None
            elif mode == '256':
                cell, fg, bg = ch, pal256[fg], None if bg is None else pal256[bg]
            else:
                mix = lambda c: tuple(round(b + (a - b) * k) for a, b in zip(pal[c], base))
                cell, fg, bg = ch, mix(fg), None if bg is None else mix(bg)
            if (fg, bg) != state:
                out.append(f'\x1b[{_color(mode, fg, 30)};{_color(mode, bg, 40)}m')
                state = fg, bg
            out.append(cell)
        lines.append(''.join(out) + '\x1b[0m')
    return lines, cols


def show_logo(out=sys.stdout, max_w=None, max_h=None, motion=True, center=True, **kw):
    """Print the logo, with a 0.7 s entrance sweep on a TTY unless motion=False. Returns (rows, width) drawn."""
    size = shutil.get_terminal_size()
    max_w, max_h = max_w or size.columns - 4, max_h or max(5, size.lines // 3)
    kw.setdefault('mode', color_mode(out=out))
    if kw['mode'] in ('truecolor', '256') and 'light' not in kw:
        kw['light'] = terminal_is_light()
    lines, width = logo(max_w, max_h, **kw)
    pad = ' ' * ((size.columns - width) // 2 if center else 0)
    draw = lambda ls: out.write('\n'.join(pad + line for line in ls))
    if not lines:
        return 0, 0
    if not (motion and out.isatty()):
        draw(lines)
        out.write('\n')
        return len(lines), width
    out.write('\x1b[?25l')  # hide the cursor while the frames run
    try:
        t0, k = time.monotonic(), 0.0
        while k < 1:
            k = min(1.0, (time.monotonic() - t0) / 0.7)
            frame, _ = logo(max_w, max_h, reveal=1 - (1 - k) ** 3, **kw)  # ease-out cubic
            draw(frame)
            out.write(f'\x1b[{len(frame) - 1}A\r' if k < 1 and len(frame) > 1 else '\r' if k < 1 else '\n')
            out.flush()
            time.sleep(1 / 40)
    finally:
        out.write('\x1b[0m\x1b[?25h')
        out.flush()
    return len(lines), width


def logo_check():
    class Out:  # a fake stdout: tty or not, with an encoding
        def __init__(self, tty, enc='utf-8'): self.tty, self.encoding = tty, enc
        def isatty(self): return self.tty
    tty, pipe = Out(True), Out(False)
    assert color_mode({'COLORTERM': 'truecolor', 'TERM': 'xterm-256color'}, tty) == 'truecolor'
    assert color_mode({'TERM': 'xterm-256color'}, tty) == '256'
    assert color_mode({'NO_COLOR': '1', 'COLORTERM': 'truecolor', 'TERM': 'xterm'}, tty) == 'braille'
    assert color_mode({'TERM': 'xterm-256color'}, pipe) == 'braille'
    assert color_mode({'TERM': 'linux'}, tty) == 'ascii' and color_mode({'TERM': 'dumb'}, Out(True, 'ascii')) == 'ascii'
    sgr = re.compile(r'\x1b\[[\d;]*m')
    for mode in ('truecolor', '256', 'braille', 'ascii'):
        for w, h in ((80, 8), (60, 6), (40, 10), (200, 16), (11, 5)):
            for light in (False, True):
                lines, width = logo(w, h, mode=mode, light=light)
                assert width <= w and len(lines) <= h, (mode, w, h)
                assert all(len(sgr.sub('', line)) == width for line in lines), (mode, w, h)
                blank = logo(w, h, mode=mode, light=light, reveal=0)[0]
                assert all(not sgr.sub('', line).strip() for line in blank), (mode, w, h)
    assert logo(11, 5) == ([], 0)  # nothing fits: callers skip the logo
    assert any(line.endswith('Mindbaton') for line in logo(80, 8, mode='ascii')[0])  # ASCII sets the name in type
    print('logo ok')


def cmd_logo(args):
    if '--check' in args:
        return logo_check()
    mode = color_mode()
    light = mode in ('truecolor', '256') and terminal_is_light()
    show_logo(motion='--no-motion' not in args, mode=mode, light=light)
    tagline = 'Tell one AI. Every AI knows.'
    print('\n' + ' ' * max(0, (shutil.get_terminal_size().columns - len(tagline)) // 2)
          + paint(tagline, '#71717a' if light else '#a1a1aa', mode))




# ── This computer's Mindbaton client ───────────────────────────────────────────────────────────────────────
# ~/.mindbaton holds config.json (the server's address and this computer's tokens, 0600), a copy of this script (the
# hooks run it), mcp_stdio.py for stdio-only apps, the offline queue, per-chat logs for apps without transcripts, the log.

MB = Path.home() / '.mindbaton'
CFG, LOG, QUEUE = MB / 'config.json', MB / 'install.log', MB / 'queue.json'
HOOK_RE = re.compile(r"mindbaton\.py['\"\\]*\s+hook\b")  # our hook entries in other apps' settings (the path may be quoted)
HOSTNAME = socket.gethostname().split('.')[0] or 'this computer'
STAMP = time.strftime('%Y%m%d-%H%M%S')  # one backup suffix per run
SECRETS = re.compile(r'\b(mb_|gsk_|AIza)[\w\-]{6,}|(Bearer\s+)\S+')
ENV_FILE = HERE / 'mindbaton.env'
LOG_HTTP = True  # the hooks turn it off: one line per message would bury the log


class Stop(Exception):
    """A final, friendly sentence for the person: shown, then exit 1."""


class Unsafe(Exception):
    """A settings file Mindbaton won't rewrite automatically (comments it would lose, not JSON…)."""


def log(*parts):
    try:
        MB.mkdir(mode=0o700, parents=True, exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > 2_000_000:
            LOG.replace(LOG.with_suffix('.log.1'))
        line = SECRETS.sub(lambda m: (m[1] or m[2]) + '…', ' '.join(str(p) for p in parts))
        fd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, 'a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + line + '\n')
    except OSError:
        pass


def tilde(p):
    p, h = str(p), str(Path.home())
    return '~' + p[len(h):] if p == h or p.startswith(h + os.sep) else p


def write_file(path, text, mode=0o600):
    """Atomic write: a temp file next to it, then rename, so a crash never leaves half a file."""
    path = Path(os.path.realpath(path))  # a symlinked dotfile (stow, chezmoi) is written through, never replaced
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'.{path.name}.mindbaton-tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def load_cfg():
    try:
        return json.loads(CFG.read_text())
    except (OSError, ValueError):
        return {}


def save_cfg(cfg):
    MB.mkdir(mode=0o700, parents=True, exist_ok=True)
    write_file(CFG, json.dumps(cfg, indent=2) + '\n')


def run(cmd, timeout=60, **kw):
    log('$', ' '.join(shlex.quote(str(c)) for c in cmd))
    try:
        r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL, **kw)
    except (OSError, subprocess.TimeoutExpired) as e:
        log('  failed:', e)
        return subprocess.CompletedProcess(cmd, 127, '', str(e))
    if r.returncode:
        log('  exit', r.returncode, (r.stderr or r.stdout).strip()[-600:])
    return r


def must(cmd, what, timeout=60):
    r = run(cmd, timeout)
    if r.returncode:
        last = ((r.stderr or r.stdout).strip().splitlines() or ['no output'])[-1]
        raise RuntimeError(f'{what} failed: {last[:160]}')
    return r.stdout


def http(method, url, body=None, token=None, cookie=None, timeout=10, headers=None):
    """→ (status, json dict, session cookie or None). Status 0 = couldn't reach it."""
    h = {'User-Agent': 'mindbaton-cli/1.0', 'Accept': 'application/json', **(headers or {})}  # Groq's CDN blocks urllib's UA
    if body is not None:
        h['Content-Type'] = 'application/json'
    if token:
        h['Authorization'] = 'Bearer ' + token
    if cookie:
        h['Cookie'] = 'mb_session=' + cookie
    req = urllib.request.Request(url, None if body is None else json.dumps(body).encode(), h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, raw, hdrs = r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        status, raw, hdrs = e.code, e.read(), e.headers
    except (OSError, ValueError) as e:  # refused, timed out, DNS, bad URL
        if LOG_HTTP:
            log(method, url.split('?')[0], '-> unreachable:', getattr(e, 'reason', e))
        return 0, {'error': str(getattr(e, 'reason', e))}, None
    if LOG_HTTP or status >= 400:
        log(method, url.split('?')[0], '->', status)
    try:
        data = json.loads(raw or b'{}')
    except ValueError:
        data = {}
    m = re.search(r'mb_session=([^;]+)', hdrs.get('Set-Cookie') or '')
    return status, data if isinstance(data, dict) else {'list': data}, m and m[1]


def err_text(d, fallback):
    e = (d or {}).get('error') or fallback
    return e[:1].upper() + e[1:] + ('' if e.endswith(('.', '!', '?')) else '.')


# ── The server on this computer ────────────────────────────────────────────────────────────────────────────

def env_file():
    out = {}
    try:
        for line in ENV_FILE.read_text().splitlines():
            k, sep, v = line.strip().partition('=')
            if sep and k and not k.startswith('#'):
                out[k.strip()] = v.strip().strip('"\'')
    except OSError:
        pass
    return out


def setting(key, default=None):
    return os.environ.get(key) or env_file().get(key) or default


def set_env(**kv):
    """KEY=value lines in mindbaton.env next to server.py (None removes one); everything else stays."""
    have = env_file()
    kv = {k: v for k, v in kv.items() if have.get(k) != (None if v is None else str(v))}
    if not kv:
        return
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    for k, v in kv.items():
        lines = [l for l in lines if not re.match(rf'\s*{k}\s*=', l)] + ([f'{k}={v}'] if v is not None else [])
    write_file(ENV_FILE, '\n'.join(lines) + '\n')
    log('mindbaton.env:', ', '.join(f'{k}={"(removed)" if v is None else v}' for k, v in kv.items()))


def data_dir():
    return Path(os.path.expanduser(setting('MINDBATON_DATA', str(HERE / 'data'))))


def port_busy(port):
    try:
        socket.create_connection(('127.0.0.1', port), 0.5).close()
        return True
    except OSError:
        return False


def lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('10.255.255.255', 1))  # no packet is sent; this only picks the interface
            ip = s.getsockname()[0]
        return None if ip.startswith('127.') else ip
    except OSError:
        return None


def health(base, timeout=3):
    s, d, _ = http('GET', base + '/health', timeout=timeout)
    return d if s == 200 and d.get('name') == 'mindbaton' else None


def wait_health(base, secs=25, proc=None):
    end = time.time() + secs
    while time.time() < end:
        if health(base, 2):
            return True
        if proc and proc.poll() is not None:
            return False
        time.sleep(0.4)
    return False


KIDS = []  # the servers this program starts: stopped by PID however it ends (Ctrl-C mid-task, an error, SIGTERM)


def spawn(cmd, **kw):
    p = subprocess.Popen(cmd, cwd=HERE, stdin=subprocess.DEVNULL, start_new_session=True, **kw)
    KIDS.append(p)
    return p


def start_server(port):
    """A copy of the server for setup only (the service or the foreground run replaces it). Returns at once:
    the caller waits for it (wait_health), so a Ctrl-C while it starts still has its PID to stop."""
    MB.mkdir(mode=0o700, parents=True, exist_ok=True)
    out = os.fdopen(os.open(MB / 'server.log', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), 'a')  # it prints the setup code
    p = spawn([sys.executable, str(HERE / 'server.py')], stdout=out, stderr=subprocess.STDOUT,
              env={**os.environ, 'MINDBATON_PORT': str(port)})
    log('started the setup server, pid', p.pid, 'port', port)
    return p


def server_up(p, port):
    if not wait_health(f'http://127.0.0.1:{port}', 30, p):
        stop_server(p)
        raise RuntimeError(f"Mindbaton didn't start. The last lines of {tilde(MB / 'server.log')} say why")


def stop_server(p):
    if p and p.poll() is None:
        p.terminate()  # our own child, by PID
        try:
            p.wait(8)
        except subprocess.TimeoutExpired:
            p.kill()
        log('stopped pid', p.pid)


atexit.register(lambda: [stop_server(p) for p in KIDS])


def self_test():
    log('$ server.py --check')
    p = spawn([sys.executable, str(HERE / 'server.py'), '--check'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        out = p.communicate(timeout=300)[0]
    except subprocess.TimeoutExpired:
        stop_server(p)
        out = 'it took over 5 minutes'
    if p.returncode:
        log('self-test output:', out[-3000:])
        last = (out.strip().splitlines() or ['no output'])[-1][:120]
        raise Stop(f'The self-test failed ({last}). Please open an issue with the details from {tilde(LOG)}.')


# systemd (Linux) or launchd (macOS) keeps it running and starts it at login.
UNIT = Path.home() / '.config/systemd/user/mindbaton.service'
PLIST = Path.home() / 'Library/LaunchAgents/ai.mindbaton.plist'


def service_kind():
    """'systemd' | 'launchd' | None. MINDBATON_SERVICE=systemd|launchd|none overrides the detection."""
    force = os.environ.get('MINDBATON_SERVICE')
    if force:
        return None if force == 'none' else force
    try:
        import pwd
        if Path(pwd.getpwuid(os.getuid()).pw_dir) != Path.home():
            return None  # a borrowed HOME (sudo -E, a test): a login service would land in the wrong place
    except (ImportError, KeyError):
        pass
    if sys.platform == 'darwin' and shutil.which('launchctl'):
        return 'launchd'
    if shutil.which('systemctl') and run(['systemctl', '--user', 'show-environment'], 10).returncode == 0:
        return 'systemd'
    return None


def service_active(kind):
    if kind == 'systemd':
        return run(['systemctl', '--user', 'is-active', 'mindbaton'], 10).stdout.strip() == 'active'
    if kind == 'launchd':
        return run(['launchctl', 'print', f'gui/{os.getuid()}/ai.mindbaton'], 10).returncode == 0
    return False


def install_service(kind):
    py, srv = sys.executable, HERE / 'server.py'
    if kind == 'systemd':
        write_file(UNIT, f"""[Unit]
Description=Mindbaton - long-term memory for all your AIs
After=network-online.target

[Service]
WorkingDirectory={HERE}
ExecStart="{py}" "{srv}"
Environment=PYTHONUNBUFFERED=1
Restart=always

[Install]
WantedBy=default.target
""", 0o644)
        for cmd in (['daemon-reload'], ['enable', '--quiet', 'mindbaton'], ['restart', 'mindbaton']):
            must(['systemctl', '--user', *cmd], 'systemctl ' + cmd[0])
    else:
        logs = Path.home() / 'Library/Logs/mindbaton.log'
        logs.parent.mkdir(parents=True, exist_ok=True)
        write_file(PLIST, f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>ai.mindbaton</string>
  <key>ProgramArguments</key><array><string>{py}</string><string>{srv}</string></array>
  <key>WorkingDirectory</key><string>{HERE}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{logs}</string>
  <key>StandardErrorPath</key><string>{logs}</string>
</dict>
</plist>
""", 0o644)
        run(['launchctl', 'bootout', f'gui/{os.getuid()}/ai.mindbaton'])
        must(['launchctl', 'bootstrap', f'gui/{os.getuid()}', PLIST], 'launchctl bootstrap')


def restart_service(kind):
    if kind == 'systemd':
        must(['systemctl', '--user', 'restart', 'mindbaton'], 'systemctl restart')
    else:
        must(['launchctl', 'kickstart', '-k', f'gui/{os.getuid()}/ai.mindbaton'], 'launchctl kickstart')


def remove_service(kind):
    if kind == 'systemd':
        run(['systemctl', '--user', 'disable', '--now', 'mindbaton'])
        UNIT.unlink(missing_ok=True)
        run(['systemctl', '--user', 'daemon-reload'])
    elif kind == 'launchd':
        run(['launchctl', 'bootout', f'gui/{os.getuid()}/ai.mindbaton'])
        PLIST.unlink(missing_ok=True)


def lingering():
    r = run(['loginctl', 'show-user', getpass.getuser(), '-p', 'Linger', '--value'], 10)
    return r.returncode != 0 or r.stdout.strip() == 'yes'  # unknown: don't nag


def install_client(url=None):
    """Copies this script (the hooks run it), mcp_stdio.py and the logo into ~/.mindbaton."""
    MB.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(MB, 0o700)
    if HERE != MB:
        write_file(MB / 'mindbaton.py', Path(__file__).read_text(), 0o700)
        if ART.exists():
            write_file(MB / 'assets/brand/terminal-logo.json', ART.read_text(), 0o600)
    if (HERE / 'mcp_stdio.py').exists():
        write_file(MB / 'mcp_stdio.py', (HERE / 'mcp_stdio.py').read_text(), 0o700)
    elif url and not (MB / 'mcp_stdio.py').exists():  # another computer: the server hands it out
        req = urllib.request.Request(url + '/mcp_stdio.py', headers={'User-Agent': 'mindbaton-cli/1.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            write_file(MB / 'mcp_stdio.py', r.read().decode(), 0o700)
    log('client copied to', MB)


# ── Free AI keys ───────────────────────────────────────────────────────────────────────────────────────────

KEY_SITES = {'gemini': ('Gemini', 'Google', 'https://aistudio.google.com/apikey', 'GEMINI_KEY'),
             'groq': ('Groq', 'Groq', 'https://console.groq.com/keys', 'GROQ_KEY')}


def check_key(provider, key):
    """Asks the provider's list-models endpoint, which costs no quota. → None if the key works, else a sentence."""
    name, who, site, _ = KEY_SITES[provider]
    if not re.fullmatch(r'[A-Za-z0-9._\-]{20,200}', key):
        return "That doesn't look like a key. Copy the whole key and paste it again."
    if provider == 'gemini':  # the header keeps the key out of URLs and logs
        s, d, _ = http('GET', 'https://generativelanguage.googleapis.com/v1beta/models?pageSize=1',
                       headers={'x-goog-api-key': key}, timeout=15)
    else:
        s, d, _ = http('GET', 'https://api.groq.com/openai/v1/models', token=key, timeout=15)
    if s in (200, 429):  # 429: a real key that is busy right now
        return None
    if s == 0:
        return f"Couldn't reach {who} to check the key. Check the internet connection, or skip this for now."
    if provider == 'gemini' and s == 403:
        return "Google knows this key, but it can't use the Gemini API. Make a new key in AI Studio."
    if s in (400, 401, 403):
        return f"{who} says this key isn't valid. Copy it again from {site.split('//')[1]}."
    return f'{who} answered with an error ({s}). Try again in a minute.'


def local_keys():
    try:
        return dict(l.split('=', 1) for l in (data_dir() / 'ai_keys').read_text().splitlines() if '=' in l)
    except OSError:
        return {}


def remove_local_key(provider):
    path, var = data_dir() / 'ai_keys', KEY_SITES[provider][3]
    lines = [l for l in path.read_text().splitlines() if not l.startswith(var + '=')]
    write_file(path, '\n'.join(lines) + ('\n' if lines else ''))
    log('removed', var, 'from', path)


GEMINI_ID = re.compile(r'^gemini-(\d+(?:\.\d+)*)-flash(-lite)?$')  # stable only: no -preview, -exp, -tts, -image, -latest


def pick_gemini(models):
    """Stable text models from Gemini's list, newest flash first, then flash-lite."""
    found = []
    for m in models:
        mid = m.get('name', '').replace('models/', '', 1)
        g = GEMINI_ID.match(mid)
        if g and 'generateContent' in m.get('supportedGenerationMethods', []):
            found.append((bool(g[2]), tuple(-int(x) for x in g[1].split('.')), mid))
    return [mid for *_, mid in sorted(found)]


def pick_groq(models):
    """Active chat models from Groq's list, the biggest gpt-oss first (speech, guard and tool models left out)."""
    ids = [m['id'] for m in models if m.get('active', True)
           and not re.search(r'whisper|orpheus|guard|tts|compound|prompt|playai|distil', m['id'])]
    size = lambda i: -int(m[1]) if (m := re.search(r'(\d+)b\b', i)) else 0
    return sorted(ids, key=lambda i: (not i.startswith('openai/gpt-oss'), size(i), i))


def list_models(provider, key):
    name, who, site, _ = KEY_SITES[provider]
    if provider == 'gemini':
        s, d, _ = http('GET', 'https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000',
                       headers={'x-goog-api-key': key}, timeout=20)
    else:
        s, d, _ = http('GET', 'https://api.groq.com/openai/v1/models', token=key, timeout=20)
    if s in (400, 401, 403):
        raise Stop(f'{who} refused the saved {name} key. Replace it with: {CLI} keys')
    if s != 200:
        raise Stop(f"Couldn't get the model list from {who} ({s or 'no answer'}). Try again in a minute.")
    return pick_gemini(d.get('models') or []) if provider == 'gemini' else pick_groq(d.get('data') or [])


# ── Other apps' settings files ─────────────────────────────────────────────────────────────────────────────

def backup(path):
    path = Path(os.path.realpath(path))
    b = path.with_name(f'{path.name}.bak-mindbaton-{STAMP}')
    if path.exists() and not b.exists():
        shutil.copy2(path, b)
        log('backup', path, '->', b.name)


def jsonc(text):
    """JSON with // and /* */ comments and trailing commas (VS Code, Zed)."""
    s = re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/', lambda m: m[0] if m[0][0] == '"' else '', text)
    return json.loads(re.sub(r'"(?:\\.|[^"\\])*"|,(\s*[}\]])', lambda m: m[0] if m[1] is None else m[1], s))


def read_json(path):
    try:
        text = Path(path).read_text(encoding='utf-8')
    except OSError:
        return {}
    for parse in (json.loads, jsonc):
        try:
            d = parse(text) if text.strip() else {}
            return d if isinstance(d, dict) else {}
        except ValueError:
            continue
    return {}


JTOK = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/|[{}\[\],:]')


def jsonc_drop(text, key):
    """JSONC text without top-level `key` (its value, and its comma); comments elsewhere stay."""
    depth, toks = 0, list(JTOK.finditer(text))
    for i, m in enumerate(toks):
        t = m[0]
        if depth == 1 and t == json.dumps(key) and i + 1 < len(toks) and toks[i + 1][0] == ':':
            j, d = i + 2, 0
            while j < len(toks):
                c = toks[j][0]
                if c in '{[':
                    d += 1
                elif c in '}]':
                    if d == 0:
                        break  # the object closes: this was the last key
                    d -= 1
                elif c == ',' and d == 0:
                    break
                j += 1
            end = toks[j].end() if toks[j][0] == ',' else toks[j].start()
            start = m.start()
            while start > 0 and text[start - 1] in ' \t':
                start -= 1
            if start > 0 and text[start - 1] == '\n':
                start -= 1
            return text[:start] + text[end:]
        if t in '{[':
            depth += 1
        elif t in '}]':
            depth -= 1
    return text


def edit_json(path, change, private=True):
    """Merge change(dict) into a JSON settings file: backup, atomic write, 0600 when it holds a token. A file with
    comments is only ever touched by adding new top-level keys as text, so every comment survives. → changed?"""
    path = Path(path)
    text = path.read_text(encoding='utf-8') if path.exists() else ''
    strict = True
    try:
        data = json.loads(text) if text.strip() else {}
    except ValueError:
        strict = False
        try:
            data = jsonc(text)
        except ValueError:
            raise Unsafe(f"{tilde(path)} isn't valid JSON, so it was left alone. Fix it (or delete it), then run this again.")
    if not isinstance(data, dict):
        raise Unsafe(f"{tilde(path)} isn't a JSON object, so it was left alone. Fix it (or delete it), then run this again.")
    new = json.loads(json.dumps(data))
    change(new)
    if new == data:
        return False
    if strict:
        out = json.dumps(new, indent=2, ensure_ascii=False) + '\n'
    else:  # comments: only whole top-level keys are added or removed, as text
        if any(k in new and new[k] != v for k, v in data.items()):
            raise Unsafe(f"{tilde(path)} has comments, so Mindbaton won't rewrite it.")
        out = text
        for k in [k for k in data if k not in new]:
            out = jsonc_drop(out, k)
        brace = next(m for m in JTOK.finditer(out) if m[0] == '{').end()
        out = out[:brace] + ''.join(f'\n  {json.dumps(k)}: {textwrap.indent(json.dumps(v, indent=2), "  ").lstrip()},'
                                    for k, v in new.items() if k not in data) + out[brace:]
        if jsonc(out) != new:
            raise Unsafe(f"{tilde(path)} has comments, so Mindbaton won't rewrite it.")
    mode = 0o600 if private else (path.stat().st_mode & 0o777 if path.exists() else 0o644)
    backup(path)
    write_file(path, out, mode)
    log('updated', path)
    return True


DROP = object()


def unhook(o):
    """o without any entry that runs our hook, and without containers that only held such entries."""
    if isinstance(o, str):
        return DROP if HOOK_RE.search(o) else o
    if isinstance(o, list):
        out = [x for x in (unhook(x) for x in o) if x is not DROP]
        return DROP if o and not out else out
    if isinstance(o, dict):
        if any(isinstance(v, str) and HOOK_RE.search(v) for v in o.values()):
            return DROP
        out = {k: u for k, u in ((k, unhook(v)) for k, v in o.items()) if u is not DROP}
        return DROP if o and not out else out
    return o


def replace_all(d, new):
    d.clear()
    d.update({} if new is DROP else new)


TABLE = re.compile(r'^[ \t]*\[\[?[ \t]*([^\]\n]+?)[ \t]*\]\]?[ \t]*(?:#.*)?$', re.M)


def toml_drop(text, name):
    """TOML text without table [name] and its sub-tables."""
    heads = [(m.start(), m[1].replace('"', '').replace("'", '')) for m in TABLE.finditer(text)] + [(len(text), '')]
    out, pos = [], 0
    for (start, n), (end, _) in zip(heads, heads[1:]):
        if n == name or n.startswith(name + '.'):
            out.append(text[pos:start])
            pos = end
    return ''.join(out) + text[pos:]


def toml_tables(text, prefix):
    """{name: block text} for tables [prefix.name]."""
    heads = [(m.start(), m[1].replace('"', '').replace("'", '')) for m in TABLE.finditer(text)] + [(len(text), '')]
    return {n[len(prefix) + 1:]: text[s:e] for (s, n), (e, _) in zip(heads, heads[1:])
            if n.startswith(prefix + '.') and '.' not in n[len(prefix) + 1:]}


def toml_ok(text):
    try:
        import tomllib
    except ImportError:  # Python < 3.11: no parser to double-check with
        return True
    try:
        tomllib.loads(text)
        return True
    except ValueError:
        return False


NOTIFY = re.compile(r'^notify[ \t]*=[ \t]*(\[[^\]]*\])[ \t]*(?:#.*)?\n?', re.M)


def toml_top(text):
    m = TABLE.search(text)
    return text[:m.start()] if m else text



# ── Your AI tools ──────────────────────────────────────────────────────────────────────────────────────────
# Formats verified per app (docs + a throwaway HOME): MCP through the app's own CLI where it has an official one
# (Claude Code), otherwise a merge into its settings file with a backup. Capture hooks where the app has them.

def _home():
    return Path.home()


def _xdg():
    return Path(os.environ.get('XDG_CONFIG_HOME') or _home() / '.config')


def _mac(*p):
    return _home().joinpath('Library/Application Support', *p)


def claude_dir():
    return Path(os.environ.get('CLAUDE_CONFIG_DIR') or _home() / '.claude')


def claude_json():
    return Path(os.environ['CLAUDE_CONFIG_DIR']) / '.claude.json' if os.environ.get('CLAUDE_CONFIG_DIR') else _home() / '.claude.json'


def opencode_json():
    """OpenCode's global config (it reads ~/.config/opencode on every OS); the .jsonc one when that's what exists."""
    d = _xdg() / 'opencode'
    return d / 'opencode.jsonc' if (d / 'opencode.jsonc').exists() and not (d / 'opencode.json').exists() else d / 'opencode.json'


def codex_toml():
    return Path(os.environ.get('CODEX_HOME') or _home() / '.codex') / 'config.toml'


def vscode_user():
    return _mac('Code/User') if sys.platform == 'darwin' else _xdg() / 'Code/User'


def copilot_home():
    return Path(os.environ.get('COPILOT_HOME') or _home() / '.copilot')


def claude_desktop_json():
    return (_mac('Claude') if sys.platform == 'darwin' else _xdg() / 'Claude') / 'claude_desktop_config.json'


# id: (name, commands on PATH, folders that mean it's installed, macOS app, message capture?)
TOOLS = {
    'claude': ('Claude Code', ['claude'], lambda: [claude_dir()], None, True),
    'codex': ('Codex', ['codex'], lambda: [codex_toml().parent], None, True),
    'gemini': ('Gemini CLI', ['gemini'], lambda: [_home() / '.gemini/settings.json'], None, True),
    'antigravity': ('Antigravity', ['agy', 'antigravity'], lambda: [_home() / '.gemini/antigravity-cli',
                                                                   _home() / '.gemini/antigravity'], 'Antigravity.app', True),
    'cursor': ('Cursor', ['cursor', 'cursor-agent'], lambda: [_home() / '.cursor'], 'Cursor.app', True),
    'windsurf': ('Windsurf', ['windsurf', 'devin-desktop'], lambda: [_home() / '.codeium/windsurf', _xdg() / 'devin'],
                 'Windsurf.app', True),
    'vscode': ('VS Code (Copilot)', ['code', 'code-insiders'], lambda: [vscode_user()], 'Visual Studio Code.app', True),
    'zed': ('Zed', ['zed', 'zeditor'], lambda: [_xdg() / 'zed'], 'Zed.app', False),
    'claude-desktop': ('Claude Desktop', [], lambda: [claude_desktop_json().parent], 'Claude.app', False),
    'cline': ('Cline', ['cline'], lambda: [_home() / '.cline'], None, False),
    'continue': ('Continue', ['cn'], lambda: [_home() / '.continue'], None, False),
    'opencode': ('OpenCode', ['opencode'], lambda: [_xdg() / 'opencode'], None, False),
}
SITE = {'claude': 'claude-code', 'codex': 'codex', 'gemini': 'gemini-cli', 'antigravity': 'antigravity', 'cursor': 'cursor',
        'windsurf': 'windsurf', 'vscode': 'vscode', 'cline': 'cline', 'opencode': 'opencode'}  # how the server names each source (server.SITES)


def detect(t):
    """Where tool t was found (a path to show), or None."""
    _, bins, dirs, app, _ = TOOLS[t]
    for b in bins:
        if shutil.which(b):
            return tilde(shutil.which(b))
    for d in dirs():
        if d.exists():
            return tilde(d)
    if app and sys.platform == 'darwin' and (Path('/Applications') / app).exists():
        return '/Applications/' + app
    return None


def json_targets(t):
    """[(settings file, key holding the servers, entry style)] for the apps configured through a JSON file."""
    h, x = _home(), _xdg()
    if t == 'windsurf':  # renamed Devin Desktop in 2026: both files are read, write the ones that exist
        both = [(x / 'devin/mcp_config.json', 'mcpServers', 'url'), (h / '.codeium/windsurf/mcp_config.json', 'mcpServers', 'url')]
        return [b for b in both if b[0].parent.exists()] or both[:1]
    return {'claude': [(claude_json(), 'mcpServers', 'http')],  # only when the `claude` command isn't there
            'gemini': [(h / '.gemini/settings.json', 'mcpServers', 'http')],
            'antigravity': [(h / '.gemini/config/mcp_config.json', 'mcpServers', 'agy')],
            'cursor': [(h / '.cursor/mcp.json', 'mcpServers', 'url')],
            'vscode': [(vscode_user() / 'mcp.json', 'servers', 'http'), (copilot_home() / 'mcp-config.json', 'mcpServers', 'http')],
            'zed': [(x / 'zed/settings.json', 'context_servers', 'url')],
            'claude-desktop': [(claude_desktop_json(), 'mcpServers', 'stdio')],
            'cline': [(Path(os.environ.get('CLINE_DATA_DIR') or h / '.cline/data') / 'settings/cline_mcp_settings.json',
                       'mcpServers', 'cline')],
            'continue': [(h / '.continue/mcpServers/mindbaton.json', 'mcpServers', 'http')],
            'opencode': [(opencode_json(), 'mcp', 'opencode')]}.get(t, [])


def entry(style, url, token):
    h = {'Authorization': 'Bearer ' + token}
    return {'http': {'type': 'http', 'url': url + '/mcp', 'headers': h},
            'url': {'url': url + '/mcp', 'headers': h},
            'agy': {'serverUrl': url + '/mcp', 'headers': h, 'disabled': False},
            'opencode': {'type': 'remote', 'url': url + '/mcp', 'headers': h, 'enabled': True},
            'cline': {'type': 'streamableHttp', 'url': url + '/mcp', 'headers': h, 'disabled': False, 'autoApprove': []},
            'stdio': {'command': sys.executable, 'args': [str(MB / 'mcp_stdio.py')],  # absolute: GUI apps get no PATH
                      'env': {'MINDBATON_URL': url, 'MINDBATON_TOKEN': token}}}[style]


def hook_cmd(t):
    return f'{shlex.quote(sys.executable)} {shlex.quote(str(MB / "mindbaton.py"))} hook {t}'


def _each(events, make):
    def add(d, cmd):
        for ev in events:
            d.setdefault('hooks', {}).setdefault(ev, []).append(make(ev, cmd))
    return add


HOOKS = {  # tool: (settings file, add(settings, command)); every add runs after our old entries are removed
    'claude': (lambda: claude_dir() / 'settings.json',
               _each(('UserPromptSubmit', 'Stop'), lambda ev, c: {'hooks': [{'type': 'command', 'command': c, 'async': True}]})),
    'gemini': (lambda: _home() / '.gemini/settings.json',
               _each(('BeforeAgent', 'AfterAgent'), lambda ev, c: {'hooks': [{'name': 'mindbaton-capture' + ('-reply' if ev == 'AfterAgent' else ''),
                                                                            'type': 'command', 'command': c, 'timeout': 10000}]})),
    'antigravity': (lambda: _home() / '.gemini/config/hooks.json',
                    lambda d, c: d.__setitem__('mindbaton-capture', {'PostInvocation': [{'type': 'command', 'command': c, 'timeout': 10}]})),
    'cursor': (lambda: _home() / '.cursor/hooks.json',
               lambda d, c: (d.setdefault('version', 1), _each(('beforeSubmitPrompt', 'afterAgentResponse'),
                                                               lambda ev, c: {'command': c, 'timeout': 10})(d, c))),
    'windsurf': (lambda: _home() / '.codeium/windsurf/hooks.json',
                 _each(('pre_user_prompt', 'post_cascade_response'), lambda ev, c: {'command': c, 'show_output': False})),
    'vscode': (lambda: copilot_home() / 'hooks/mindbaton.json',  # our own file: VS Code, its Agent Host and Copilot CLI read it
               lambda d, c: d.update(version=1, hooks={'userPromptSubmitted': [{'type': 'command', 'bash': c, 'timeoutSec': 10}]})),
}
OWN_FILES = ('mindbaton.json',)  # files that are entirely ours: removed, not edited, on uninstall


def codex_connect(url, token, capture, prev_notify):
    """MCP with a static bearer header (`codex mcp add` can only read tokens from an env var) and `notify`, which runs
    our hook after every turn and needs no trust step. An existing notify is chained, never dropped. → prev notify."""
    path = codex_toml()
    text = path.read_text() if path.exists() else ''
    new = toml_drop(text, 'mcp_servers.mindbaton').rstrip('\n')
    new += ('\n\n' if new else '') + (f'[mcp_servers.mindbaton]\nurl = {json.dumps(url + "/mcp")}\n'
                                      f'http_headers = {{ Authorization = {json.dumps("Bearer " + token)} }}\nstartup_timeout_sec = 20\n')
    if capture:
        top = toml_top(new)
        m = NOTIFY.search(top)
        if m:
            try:
                old = json.loads(m[1].replace("'", '"'))
            except ValueError:
                old = None
            if not isinstance(old, list):
                raise Unsafe("Codex's notify setting has a format Mindbaton can't read, so messages aren't saved from Codex.")
            if 'mindbaton.py' not in json.dumps(old):  # ours from an earlier run: keep what it chained to
                prev_notify = old
            new = new[:m.start()] + new[m.end():]
        new = f'notify = {json.dumps([sys.executable, str(MB / "mindbaton.py"), "hook", "codex"])}\n' + new.lstrip('\n')
    if not toml_ok(new):
        raise Unsafe(f"{tilde(path)} couldn't be updated safely, so it was left alone.")
    if new != text:
        backup(path)
        write_file(path, new, 0o600)
        log('updated', path)
    return prev_notify


def codex_disconnect(prev_notify):
    path = codex_toml()
    if not path.exists():
        return
    text = path.read_text()
    new = toml_drop(text, 'mcp_servers.mindbaton')
    m = NOTIFY.search(toml_top(new))
    if m and 'mindbaton.py' in m[1]:
        new = new[:m.start()] + (f'notify = {json.dumps(prev_notify)}\n' if prev_notify else '') + new[m.end():]
    new = re.sub(r'\n{3,}', '\n\n', new).strip('\n') + '\n' if new.strip() else ''
    if new != text and toml_ok(new):
        backup(path)
        write_file(path, new, 0o600) if new else path.unlink()
        log('updated', path)


def claude_cli(*args):
    return run(['claude', 'mcp', *args], 60)


def connect_tool(t, url, token, capture=True, state=None):
    """Gives app t Mindbaton's memory tools (MCP) and, where it has hooks, per-message capture.
    → (what it got, a note for the person or None, new state for config.json)."""
    state = dict(state or {})
    notes, pasted, targets = [], 0, []
    if t == 'claude' and shutil.which('claude'):
        backup(claude_json())
        claude_cli('remove', '--scope', 'user', 'mindbaton')  # `add` fails when the name exists
        r = claude_cli('add', '--transport', 'http', '--scope', 'user', 'mindbaton', url + '/mcp', '--header', 'Authorization: Bearer ' + token)
        if r.returncode:
            raise RuntimeError('claude mcp add failed: ' + ((r.stderr or r.stdout).strip().splitlines() or ['?'])[-1][:160])
        if claude_json().exists():
            os.chmod(claude_json(), 0o600)  # it holds the token now
    elif t == 'codex':
        try:
            state['notify_prev'] = codex_connect(url, token, capture, state.get('notify_prev'))
        except Unsafe as e:
            state['notify_prev'] = codex_connect(url, token, False, state.get('notify_prev'))
            capture = False
            notes.append(str(e))
    else:
        if t == 'claude-desktop':
            notes.append('Quit Claude Desktop completely and open it again.')
        targets = json_targets(t)
        for path, top, style in targets:
            try:
                edit_json(path, lambda d: d.setdefault(top, {}).__setitem__('mindbaton', entry(style, url, token)))
            except Unsafe as e:  # a file Mindbaton won't rewrite: hand over a snippet to paste
                snip = MB / f'{t}-snippet.json'
                write_file(snip, json.dumps({top: {'mindbaton': entry(style, url, token)}}, indent=2) + '\n')
                notes += [str(e), f'To connect it by hand, add {tilde(snip)} to it.']
                pasted += 1
    hooked = False
    if capture and t in HOOKS:
        path, add = HOOKS[t][0](), HOOKS[t][1]
        if t != 'windsurf' or path.parent.exists():
            try:
                edit_json(path, lambda d: (replace_all(d, unhook(d)), add(d, hook_cmd(t))), private=False)
                hooked = True
            except Unsafe as e:
                notes += [str(e), f"Until then, messages aren't saved from {TOOLS[t][0]}."]
    elif capture and t == 'codex':
        hooked = True
    state.update(token=token, capture=hooked, url=url)
    if targets and pasted == len(targets):
        what = 'saves every message · paste the snippet for memory tools' if hooked else 'paste the snippet to finish'
    else:
        what = 'memory tools + saves every message' if hooked else 'memory tools'
    return what, ' '.join(dict.fromkeys(notes)) or None, state  # one file can refuse twice (MCP entry, hook): say it once


def disconnect_tool(t, state=None):
    """Removes exactly what connect_tool added (their other settings stay). Backups are taken first."""
    state = state or {}
    if t == 'claude' and shutil.which('claude'):
        backup(claude_json())
        claude_cli('remove', '--scope', 'user', 'mindbaton')
    elif t == 'codex':
        codex_disconnect(state.get('notify_prev'))
    for path, top, _ in ([] if t in ('claude', 'codex') and (t == 'codex' or shutil.which('claude')) else json_targets(t)):
        if path.name in OWN_FILES:
            path.unlink(missing_ok=True)
        elif path.exists():
            def drop(d):
                (d.get(top) or {}).pop('mindbaton', None)
                if top in d and not d[top]:
                    d.pop(top)
            edit_json(path, drop, private=path.stat().st_mode & 0o077 == 0)
            _drop_if_empty(path)
    if t in HOOKS:
        path = HOOKS[t][0]()
        if path.name in OWN_FILES:
            path.unlink(missing_ok=True)
        elif path.exists():
            edit_json(path, lambda d: replace_all(d, unhook(d)), private=False)
            _drop_if_empty(path)


def _drop_if_empty(path):
    """A settings file holding nothing but what we'd have created ({} or Cursor's version line) goes away."""
    if path.exists() and not {k: v for k, v in read_json(path).items() if k != 'version'} and not re.search(r'//|/\*', path.read_text()):
        path.unlink()


def mcp_entry(t):
    """This app's current 'mindbaton' MCP settings, as text (for doctor), or ''."""
    if t == 'codex':
        return toml_tables(codex_toml().read_text() if codex_toml().exists() else '', 'mcp_servers').get('mindbaton', '')
    found = [(read_json(path).get(top) or {}).get('mindbaton') for path, top, _ in json_targets(t)]
    return next((json.dumps(e) for e in found if e), '')


def hook_present(t):
    if t == 'codex':
        return 'mindbaton.py' in (NOTIFY.search(toml_top(codex_toml().read_text())) or [''])[0] if codex_toml().exists() else False
    return t in HOOKS and bool(HOOK_RE.search(json.dumps(read_json(HOOKS[t][0]()))))


def host_port(u):
    u = urlparse(u)
    try:
        return (u.hostname or '').lower(), u.port or {'http': 80, 'https': 443}.get(u.scheme)
    except ValueError:
        return '', None


def legacy(t, url):
    """Older memory connections: a server named like 'memgraph', or another name pointing at this Mindbaton.
    → [(name, the URL it points at or '', same server as url?, remove())]."""
    h, p = host_port(url)
    mine = {(h, p)} | ({(x, p) for x in ('localhost', '127.0.0.1', lan_ip(), HOSTNAME.lower())} if h in ('localhost', '127.0.0.1') else set())

    def old(name, conf):
        u = json.dumps(conf) if not isinstance(conf, str) else conf
        at = re.search(r'https?://[^"\s]+?/mcp\b', u)
        same = bool(at) and host_port(at[0]) in mine
        return (at[0] if at else '', same) if name != 'mindbaton' and (same or 'memgraph' in name.lower()) else None

    found = []
    if t == 'codex' and codex_toml().exists():
        for name, block in toml_tables(codex_toml().read_text(), 'mcp_servers').items():
            if (o := old(name, block)):
                def rm(name=name):
                    p = codex_toml()
                    backup(p)
                    write_file(p, toml_drop(p.read_text(), 'mcp_servers.' + name), 0o600)
                found.append((name, *o, rm))
        return found
    targets = [(claude_json(), 'mcpServers', '')] if t == 'claude' else json_targets(t)
    for path, top, _ in targets:
        for name, conf in (read_json(path).get(top) or {}).items():
            if (o := old(name, conf)):
                if t == 'claude' and shutil.which('claude'):
                    rm = lambda name=name: (backup(claude_json()), claude_cli('remove', '--scope', 'user', name))
                else:
                    rm = lambda path=path, top=top, name=name: edit_json(path, lambda d: d[top].pop(name, None))
                found.append((name, *o, rm))
    return found


# ── Capture hook (`mindbaton.py hook <tool>`) ──────────────────────────────────────────────────────────────
# Runs inside the AI app on every message. Rules: print nothing (stdout goes into the AI's context; Cursor and
# Antigravity want one fixed JSON reply), exit 0 whatever happens (exit 2 would block the prompt), done in 5 s.
# Each chat goes to POST /session as a whole transcript, keyed by the app's own chat id, so repeats are harmless.
# If the server can't be reached it waits in ~/.mindbaton/queue.json and goes with the next message.

CC_NOISE = re.compile(r"<system-reminder>[\s\S]*?</system-reminder>|<local-command-[\w-]+>[\s\S]*?</local-command-[\w-]+>|"
                      r"<command-(?:name|message|args)>[\s\S]*?</command-(?:name|message|args)>|"
                      r"<(task-notification|bash-(?:input|stdout|stderr)|user-prompt-submit-hook)>[\s\S]*?</\1>", re.I)
AGY_NOISE = re.compile(r"The following is a <SYSTEM_MESSAGE>[\s\S]*?</SYSTEM_MESSAGE>|<ADDITIONAL_METADATA>[\s\S]*?"
                       r"</ADDITIONAL_METADATA>|<USER_SETTINGS_CHANGE>[\s\S]*?</USER_SETTINGS_CHANGE>|"
                       r"</?(?:USER_REQUEST|ADDITIONAL_METADATA|USER_SETTINGS_CHANGE|SYSTEM_MESSAGE)>", re.I)
MAX_BODY = 900_000  # the server takes 1 MB


def _lines(path, tail=4_000_000):
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        if size > tail:
            f.seek(size - tail)
            f.readline()
        return f.read().decode('utf-8', 'replace').splitlines()


def _when(s):
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(s).replace('Z', '+00:00')).timestamp()
    except ValueError:
        return None


def _add(turns, role, text, **kw):
    """One turn per change of speaker, as the server's own transcript readers do."""
    if turns and turns[-1]['role'] == role:
        turns[-1]['text'] += '\n\n' + text
        turns[-1].update({k: v for k, v in kw.items() if v})
    else:
        turns.append({'role': role, 'text': text, **kw})


def claude_transcript(path):
    """Claude Code's .jsonl, read the way the server's watcher reads it (live.read_claude_code). → (turns, title)."""
    turns, title = [], None
    for line in _lines(path):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get('type') == 'summary' and r.get('summary'):
            title = title or r['summary']
        if r.get('type') == 'ai-title' and r.get('aiTitle'):
            title = r['aiTitle']
        if r.get('type') not in ('user', 'assistant') or r.get('isMeta') or r.get('isSidechain') or r.get('isCompactSummary'):
            continue
        if r['type'] == 'user' and r.get('promptSource') == 'system':
            continue
        msg = r.get('message') or {}
        c = msg.get('content')
        parts = [c] if isinstance(c, str) else [x.get('text', '') for x in c or [] if isinstance(x, dict) and x.get('type') == 'text']
        text = CC_NOISE.sub('', '\n'.join(p for p in parts if p)).strip()
        if not text or text.startswith(('Caveat:', '[Request interrupted', 'This session is being continued')):
            continue
        model = msg.get('model') if r['type'] == 'assistant' and not str(msg.get('model', '')).startswith('<') else None
        _add(turns, r['type'], text, model=model, ts=_when(r.get('timestamp')) if r.get('timestamp') else None)
    return turns, title


def agy_transcript(path):
    """Antigravity's transcript.jsonl (USER_INPUT / PLANNER_RESPONSE steps). → turns."""
    turns = []
    full = Path(path).with_name('transcript_full.jsonl')
    for line in _lines(full if full.exists() else path):
        try:
            s = json.loads(line)
        except ValueError:
            continue
        kind, text = s.get('type'), AGY_NOISE.sub('', str(s.get('content') or '')).strip()
        if text and kind in ('USER_INPUT', 'PLANNER_RESPONSE'):
            _add(turns, 'user' if kind == 'USER_INPUT' else 'assistant', text, ts=_when(s.get('created_at')))
    return turns


def chat_log(site, cid, new, model):
    """Apps that hand hooks single messages: the chat so far, kept on this computer (~/.mindbaton/chats)."""
    path = MB / 'chats' / f'{site}-{hashlib.sha1(str(cid).encode()).hexdigest()[:16]}.json'
    try:
        turns = json.loads(path.read_text())
    except (OSError, ValueError):
        turns = []
    for role, text in new:
        text = str(text or '').strip()[:20000]
        if not text or (turns and turns[-1]['role'] == role and turns[-1]['text'] == text):
            continue  # the same message twice (a retried hook, or AfterAgent repeating the prompt)
        # one turn per message, never merged: a user turn that grew would be read again as new text every time
        turns.append({'role': role, 'text': text, 'ts': time.time(), **({'model': model} if role == 'assistant' and model else {})})
    write_file(path, json.dumps(turns[:600]))  # ponytail: a chat past 600 messages stops growing here
    return turns


def codex_model():
    m = re.search(r'^model\s*=\s*"([^"]+)"', toml_top(codex_toml().read_text()), re.M) if codex_toml().exists() else None
    return m and m[1]


def hook_payload(tool, p, cfg):
    """What one hook call means: (site, chat id, turns so far, extra fields) or None."""
    tools = cfg.get('tools') or {}
    ev = p.get('hook_event_name') or p.get('agent_action_name') or ''
    if tool == 'claude':
        other = next((s for s, e in (('cursor', 'CURSOR_VERSION'), ('windsurf', 'DEVIN_PROJECT_DIR'), ('continue', 'CONTINUE_PROJECT_DIR'))
                      if os.environ.get(e)), None)
        if other:  # Cursor, Devin and Continue also run Claude Code's hooks: label them right, never twice
            # (Windsurf's own hooks are Cascade's; Devin Local only runs these, so it is never skipped)
            if (other != 'windsurf' and (tools.get(other) or {}).get('capture')) or not p.get('prompt'):
                return None
            cid = p.get('session_id') or p.get('conversation_id') or 'chat'
            return other, cid, chat_log(other, cid, [('user', p['prompt'])], None), {}
        cid, turns, title = p.get('session_id'), [], None
        if p.get('transcript_path') and os.path.isfile(p['transcript_path']):
            turns, title = claude_transcript(p['transcript_path'])
        prompt = str(p.get('prompt') or '').strip()
        if ev == 'UserPromptSubmit' and prompt and not (turns and turns[-1]['role'] == 'user' and turns[-1]['text'].endswith(prompt)):
            _add(turns, 'user', prompt, ts=time.time())  # the transcript doesn't have it yet
        return 'claude-code', cid, turns, {'cwd': p.get('cwd'), 'chat': title}
    if tool == 'antigravity':
        path = p.get('transcriptPath')
        turns = agy_transcript(path) if path and os.path.isfile(path) else []
        return 'antigravity', p.get('conversationId'), turns, {'model': p.get('modelName'), 'cwd': (p.get('workspacePaths') or [None])[0]}
    if tool == 'codex':  # notify: one call per finished turn, with its prompts and the reply
        new = [('user', m) for m in p.get('input-messages') or []] + [('assistant', p.get('last-assistant-message'))]
        site, cid, model, extra = 'codex', p.get('thread-id'), codex_model(), {'cwd': p.get('cwd')}
    elif tool == 'gemini':
        new = [('user', p.get('prompt'))] + ([('assistant', p.get('prompt_response'))] if ev == 'AfterAgent' else [])
        site, cid, model, extra = 'gemini-cli', p.get('session_id'), None, {'cwd': p.get('cwd')}
    elif tool == 'cursor':
        new = [('assistant', p.get('text'))] if ev == 'afterAgentResponse' else [('user', p.get('prompt'))]
        site, cid, model, extra = 'cursor', p.get('conversation_id'), p.get('model'), {'cwd': (p.get('workspace_roots') or [None])[0]}
    elif tool == 'windsurf':
        ti = p.get('tool_info') or {}
        new = [('user', ti.get('user_prompt')), ('assistant', ti.get('response'))]
        site, cid, model, extra = 'windsurf', p.get('trajectory_id'), p.get('model_name'), {}
    elif tool == 'vscode':
        new = [('user', p.get('prompt'))]
        site, cid, model, extra = 'vscode', p.get('sessionId') or p.get('session_id'), None, {'cwd': p.get('cwd')}
    else:
        return None
    if not cid:
        return None
    return site, cid, chat_log(site, cid, new, model), {**extra, 'model': model}


def deliver(cfg, item, key, left):
    """Send this, after anything still waiting from before; what fails waits in the queue. One lock for both."""
    import fcntl
    MB.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(MB / '.queue.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            q = json.loads(QUEUE.read_text())
        except (OSError, ValueError):
            q = {}
        save = lambda: write_file(QUEUE, json.dumps(dict(list(q.items())[-200:]))) if q else QUEUE.unlink(missing_ok=True)
        if item:
            q.pop(key, None)
            q[key] = item  # the newest transcript of a chat replaces an older one still waiting
            save()  # on disk before the network, so a timeout can't lose it
        down = set()
        for k in list(q):
            it = q[k]
            if left() < 1:
                break
            if it['url'] in down:
                continue
            s, _, _ = http('POST', it['url'] + it['path'], it['body'], token=it['token'], timeout=min(3, left()))
            # sent, or never taken (401: a revoked token; a /session item is re-sent whole with the chat's next message)
            if s == 200 or (400 <= s < 500 and s not in (408, 429)):
                q.pop(k)
            else:
                down.add(it['url'])  # down or busy: that server's items wait, in order; other servers' still go
        save()
        return len(q)


def run_hook(tool, payload, cfg, left):
    t = (cfg.get('tools') or {}).get(tool) or {}
    url, token = t.get('url') or cfg.get('url'), t.get('token') or cfg.get('token')
    if not url or not token:
        return
    got = hook_payload(tool, payload, cfg)
    if not got or not got[2]:
        return deliver(cfg, None, None, left)  # nothing new; still try what's waiting
    site, cid, turns, extra = got
    first = next((x['text'] for x in turns if x['role'] == 'user'), '')
    body = {'site': site, 'id': str(cid), 'turns': turns, 'chat': extra.get('chat') or ' '.join(first.split())[:70] or None,
            'model': extra.get('model'), 'cwd': extra.get('cwd')}
    path = '/session'
    if len(json.dumps(body)) > MAX_BODY:  # a huge chat: send just the latest message as a memory
        path, body = '/capture', {'text': next((x['text'] for x in reversed(turns) if x['role'] == 'user'), '')[:20000],
                                  'site': site, 'url': extra.get('cwd'), 'ts': time.time()}
        if not body['text']:
            return
    item = {'url': url, 'path': path, 'body': {k: v for k, v in body.items() if v is not None}, 'token': token}
    return deliver(cfg, item, f'{site}/{cid}' if path == '/session' else f'{site}/{cid}/{time.time()}', left)


def cmd_hook(args):
    global LOG_HTTP
    LOG_HTTP = False
    tool = args[0] if args else ''
    reply = {'cursor': '{"continue": true}', 'antigravity': '{}'}.get(tool, '')
    end = time.monotonic() + 5

    def timeout(*_):
        raise TimeoutError('hook took too long')
    try:
        signal.signal(signal.SIGALRM, timeout)
        signal.alarm(5)
        sys.stdout = open(os.devnull, 'w')  # nothing below may print into the AI's context
        if tool == 'codex':  # notify passes the event as the last argument, not on stdin
            payload = json.loads(args[-1]) if len(args) > 1 else {}
            prev = ((load_cfg().get('tools') or {}).get('codex') or {}).get('notify_prev')
            try:  # the notify program that was there before Mindbaton keeps running
                prev and subprocess.Popen([*prev, args[-1]], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL, start_new_session=True)
            except OSError:
                log('hook codex: the earlier notify program', prev[:1], "didn't start")
        else:
            payload = json.loads(sys.stdin.read(8_000_000) or '{}')
        if hasattr(os, 'fork'):  # answer the app now and send in the background: an unreachable server never stalls it
            if reply:
                os.write(1, reply.encode())
                reply = ''
            if os.fork():
                os._exit(0)
            os.setsid()
            null = os.open(os.devnull, os.O_RDWR)
            for fd in (0, 1, 2):
                os.dup2(null, fd)  # the app waits for these pipes to close
            signal.alarm(12)
            end = time.monotonic() + 10
        run_hook(tool, payload if isinstance(payload, dict) else {}, load_cfg(), lambda: end - time.monotonic())
    except BaseException as e:  # never fail the app over a memory
        log('hook', tool, 'skipped:', repr(e)[:300])
    finally:
        signal.alarm(0)
        if reply:
            os.write(1, reply.encode())
        os._exit(0)


# ── QR code (for the phone link) ───────────────────────────────────────────────────────────────────────────
# A small byte-mode encoder after Project Nayuki's reference (MIT): error correction L, versions 1–40, best mask.

_QR_ECC = {'L': ([7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30,
                  30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
                 [1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19,
                  19, 20, 21, 22, 24, 25], 1),
           'M': ([10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28,
                  28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28],
                 [1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33,
                  35, 37, 38, 40, 43, 45, 47, 49], 0)}


def _gf_mul(x, y):
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs(data, degree):
    div, root = [0] * (degree - 1) + [1], 1
    for _ in range(degree):
        for j in range(degree):
            div[j] = _gf_mul(div[j], root) ^ (div[j + 1] if j + 1 < degree else 0)
        root = _gf_mul(root, 2)
    out = [0] * degree
    for b in data:
        f = b ^ out.pop(0)
        out.append(0)
        for i, c in enumerate(div):
            out[i] ^= _gf_mul(c, f)
    return out


def _raw_modules(v):
    n = (16 * v + 128) * v + 64
    if v >= 2:
        a = v // 7 + 2
        n -= (25 * a - 10) * a - 55
        if v >= 7:
            n -= 36
    return n


def qr_matrix(text, ecl='L'):
    """text → square list of rows of bools (True = dark), without the quiet zone."""
    data = text.encode('utf-8')
    eccs, blocks, fbits = _QR_ECC[ecl]
    for v in range(1, 41):
        cap = _raw_modules(v) // 8 - eccs[v - 1] * blocks[v - 1]
        if 4 + (8 if v < 10 else 16) + 8 * len(data) <= cap * 8:
            break
    else:
        raise ValueError('too long for a QR code')
    bits = [0, 1, 0, 0] + [(len(data) >> i) & 1 for i in reversed(range(8 if v < 10 else 16))]
    bits += [(b >> i) & 1 for b in data for i in reversed(range(8))]
    bits += [0] * min(4, cap * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    words = [int(''.join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    words += [(0xEC, 0x11)[i % 2] for i in range(cap - len(words))]
    nb, ecc, raw = blocks[v - 1], eccs[v - 1], _raw_modules(v) // 8
    short, slen = nb - raw % nb, raw // nb
    parts, k = [], 0
    for i in range(nb):
        d = words[k:k + slen - ecc + (0 if i < short else 1)]
        k += len(d)
        parts.append(d + ([0] if i < short else []) + _rs(d, ecc))
    code = [b[i] for i in range(len(parts[0])) for j, b in enumerate(parts) if i != slen - ecc or j >= short]

    size = v * 4 + 17
    m = [[False] * size for _ in range(size)]
    fn = [[False] * size for _ in range(size)]

    def put(x, y, dark):
        m[y][x], fn[y][x] = dark, True

    for i in range(size):
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                if 0 <= cx + dx < size and 0 <= cy + dy < size:
                    put(cx + dx, cy + dy, max(abs(dx), abs(dy)) not in (2, 4))
    if v > 1:
        a = v // 7 + 2
        step = 26 if v == 32 else (v * 4 + a * 2 + 1) // (a * 2 - 2) * 2
        pos = [6] + sorted(size - 7 - i * step for i in range(a - 1))
        for i, y in enumerate(pos):
            for j, x in enumerate(pos):
                if (i, j) not in ((0, 0), (0, a - 1), (a - 1, 0)):
                    for dy in range(-2, 3):
                        for dx in range(-2, 3):
                            put(x + dx, y + dy, max(abs(dx), abs(dy)) != 1)
    if v >= 7:
        r = v
        for _ in range(12):
            r = (r << 1) ^ ((r >> 11) * 0x1F25)
        vb = v << 12 | r
        for i in range(18):
            put(size - 11 + i % 3, i // 3, (vb >> i) & 1 == 1)
            put(i // 3, size - 11 + i % 3, (vb >> i) & 1 == 1)

    def fmt(mask):
        d = fbits << 3 | mask
        r = d
        for _ in range(10):
            r = (r << 1) ^ ((r >> 9) * 0x537)
        b = [((d << 10 | r) ^ 0x5412) >> i & 1 == 1 for i in range(15)]
        for i in range(6):
            put(8, i, b[i])
        put(8, 7, b[6])
        put(8, 8, b[7])
        put(7, 8, b[8])
        for i in range(9, 15):
            put(14 - i, 8, b[i])
        for i in range(8):
            put(size - 1 - i, 8, b[i])
        for i in range(8, 15):
            put(8, size - 15 + i, b[i])
        put(8, size - 8, True)

    fmt(0)  # reserves the format areas before the data goes in
    i, right = 0, size - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                x = right - j
                y = size - 1 - vert if (right + 1) & 2 == 0 else vert
                if not fn[y][x] and i < len(code) * 8:
                    m[y][x] = (code[i >> 3] >> (7 - (i & 7))) & 1 == 1
                    i += 1
        right -= 2

    masks = [lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0, lambda x, y: (x + y) % 3 == 0,
             lambda x, y: (x // 3 + y // 2) % 2 == 0, lambda x, y: x * y % 2 + x * y % 3 == 0,
             lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0, lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0]

    def masked(k):
        out = [[m[y][x] ^ (not fn[y][x] and masks[k](x, y)) for x in range(size)] for y in range(size)]
        return out

    def penalty(g):
        lines = [''.join('1' if c else '0' for c in row) for row in g]
        lines += [''.join(col) for col in zip(*lines)]
        p = sum(len(r) - 2 for line in lines for r in re.findall(r'0{5,}|1{5,}', line))
        p += 40 * sum(line.count('10111010000') + line.count('00001011101') for line in lines)
        p += 3 * sum(g[y][x] == g[y][x + 1] == g[y + 1][x] == g[y + 1][x + 1] for y in range(size - 1) for x in range(size - 1))
        dark = sum(map(sum, g))
        return p + 10 * (abs(dark * 20 - size * size * 10) // (size * size))

    best = None
    for k in range(8):
        fmt(k)
        g = masked(k)
        score = penalty(g)
        if best is None or score < best[0]:
            best = (score, k, g)
    fmt(best[1])
    return masked(best[1])


def qr_lines(text, quiet=2):
    """The QR code as half-block text: light modules are drawn, dark ones are the background → (lines, width).
    Callers colour it white on black (it also reads correctly, uncoloured, on a dark terminal)."""
    g = qr_matrix(text)
    n = len(g) + 2 * quiet
    light = lambda x, y: not (quiet <= x < n - quiet and quiet <= y < n - quiet and g[y - quiet][x - quiet])
    rows = []
    for y in range(0, n, 2):
        rows.append(''.join(' ▀▄█'[light(x, y) + 2 * (y + 1 < n and light(x, y + 1))] for x in range(n)))
    return rows, n


# ── The full-screen terminal UI ────────────────────────────────────────────────────────────────────────────
# Raw ANSI + termios (curses can't do truecolor): alternate screen, a centred column, redrawn line by line only where
# something changed. Every way out (finish, Ctrl-C, an error, SIGTERM, SIGHUP) restores the terminal.

ANSI = re.compile(r'\x1b\[[\d;?]*[A-Za-z]')
PAL = {False: dict(fg2='#a1a1aa', fg3='#71717a', accent='#ffffff', ok='#3dd68c', danger='#ff6369', warn='#f5a524'),
       True: dict(fg2='#52525b', fg3='#71717a', accent='#09090b', ok='#15803d', danger='#dc2626', warn='#b45309')}
KEYS = {'[A': 'up', '[B': 'down', '[C': 'right', '[D': 'left', 'OA': 'up', 'OB': 'down', 'OC': 'right', 'OD': 'left',
        '[H': 'home', '[F': 'end', 'OH': 'home', 'OF': 'end', '[1~': 'home', '[4~': 'end', '[7~': 'home', '[8~': 'end',
        '[3~': 'delete', '[Z': 'shift-tab', '[5~': 'pgup', '[6~': 'pgdn'}
CTRL = {'\r': 'enter', '\n': 'enter', '\t': 'tab', '\x7f': 'backspace', '\x08': 'backspace', '\x03': 'ctrl-c', '\x04': 'ctrl-d',
        '\x12': 'ctrl-r', '\x15': 'ctrl-u', '\x17': 'ctrl-w', '\x1b': 'esc', ' ': 'space'}


def wrap(text, width):
    return textwrap.wrap(text, max(1, width), break_on_hyphens=False)


def cw(ch):
    return 0 if unicodedata.combining(ch) else 2 if unicodedata.east_asian_width(ch) in 'WF' else 1


def vlen(s):
    return sum(cw(c) for c in ANSI.sub('', s))


def fit(s, w):
    """s cut to w visible cells (ANSI kept intact)."""
    if vlen(s) <= w:
        return s
    out, n = [], 0
    for m in re.finditer(r'\x1b\[[\d;?]*[A-Za-z]|.', s, re.S):
        t = m[0]
        if t[0] == '\x1b':
            out.append(t)
        elif n + cw(t) > w - 1:
            out.append('…')
            break
        else:
            out.append(t)
            n += cw(t)
    return ''.join(out) + '\x1b[0m'


def parse_keys(data):
    out, i = [], 0
    while i < len(data):
        if data.startswith('\x1b[200~', i):  # bracketed paste: a pasted key arrives as one piece, never as keypresses
            end = data.find('\x1b[201~', i)
            out.append(('paste', data[i + 6:end if end >= 0 else len(data)]))
            i = end + 6 if end >= 0 else len(data)
            continue
        m = re.match(r'\x1b(\[[\d;]*[A-Za-z~]|O[A-Za-z])', data[i:])
        if m:
            out.append(KEYS.get(m[1], None))
            i += m.end()
            continue
        ch = data[i]
        out.append(CTRL.get(ch) or (('text', ch) if ch.isprintable() else None))
        i += 1
    return [k for k in out if k]


def field(label, value='', secret=False, check=None, placeholder=''):
    return {'label': label, 'value': value, 'secret': secret, 'check': check, 'placeholder': placeholder, 'error': None}


class TUI:
    interactive = True

    def __init__(self, steps, word, motion=True):
        self.steps, self.word, self.motion = steps, word, motion
        self.step, self.title, self.sub, self.body, self.who = None, '', '', [], ''
        self.mode = color_mode()
        self.color = self.mode in ('truecolor', '256')
        self.light = self.color and terminal_is_light()  # asks the terminal, so before raw mode
        utf = 'utf' in (sys.stdout.encoding or '').lower() and os.environ.get('TERM') != 'linux'
        self.g = dict(ok='✓', fail='✗', warn='!', info='·', todo='○', sel='›', dot='•', bar='━', rule='─', spin='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏',
                      on='[✓]', off='[ ]', up='↑', down='↓') if utf else dict(ok='+', fail='x', warn='!', info='-', todo='o', sel='>',
                                                                            dot='*', bar='=', rule='-', spin='|/-\\', on='[x]',
                                                                            off='[ ]', up='^', down='v')
        self.pal = {k: (tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)) if self.mode == 'truecolor' else
                        _to256(tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)))) for k, v in PAL[self.light].items()}
        self.fd = sys.stdin.fileno()
        import termios
        self.termios = termios
        self.saved = termios.tcgetattr(self.fd)
        a = termios.tcgetattr(self.fd)
        a[0] &= ~(termios.IXON | termios.ICRNL)  # Ctrl-S/Q and Enter arrive as keys
        a[3] &= ~(termios.ECHO | termios.ICANON | termios.ISIG | termios.IEXTEN)  # Ctrl-C too: we clean up, then quit
        termios.tcsetattr(self.fd, termios.TCSANOW, a)
        self.last, self.resized, self.waiting, self.scroll, self.hidden = None, False, False, 0, 0
        signal.signal(signal.SIGWINCH, lambda *_: setattr(self, 'resized', True))
        for sig in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, lambda *_: sys.exit(1))
        self.out('\x1b[?1049h\x1b[?25l\x1b[?2004h\x1b[2J')  # alternate screen, no cursor, bracketed paste

    def close(self):
        self.out('\x1b[?2004l\x1b[0m\x1b[2J\x1b[?25h\x1b[?1049l')
        self.termios.tcsetattr(self.fd, self.termios.TCSAFLUSH, self.saved)
        signal.signal(signal.SIGWINCH, signal.SIG_DFL)

    def out(self, s):
        sys.stdout.write(s)
        sys.stdout.flush()

    # ── style ──
    def st(self, text, role=None, bold=False, rev=False):
        pre = ('\x1b[1m' if bold else '') + ('\x1b[7m' if rev else '')
        if role and self.color and role in self.pal:
            pre += f'\x1b[{_color(self.mode, self.pal[role], 30)}m'
        elif role == 'fg3' and not self.color:
            pre += '\x1b[2m'  # NO_COLOR still allows dim, so the quietest text stays quiet
        return f'{pre}{text}\x1b[0m' if pre else text

    def icon(self, kind):
        if kind == 'spin':
            return self.st(self.g['spin'][int(time.monotonic() * 12) % len(self.g['spin'])], 'accent')
        return self.st(self.g[kind], {'ok': 'ok', 'fail': 'danger', 'warn': 'warn', 'info': 'fg3', 'todo': 'fg3'}[kind],
                       bold=kind in ('ok', 'fail', 'warn'))

    # ── page content ──
    def page(self, step, title, sub=''):
        self.step, self.title, self.sub, self.body = step, title, sub, []

    def retitle(self, title, sub=None):
        self.title, self.sub = title, self.sub if sub is None else sub

    def row(self, kind, label, detail=''):
        item = ['row', kind, label, detail]
        self.body.append(item)
        return item

    def text(self, t, role='fg2'):
        self.body.append(['text', t, role])

    def gap(self):
        self.body.append(['gap'])

    def qr(self, url, caption):
        self.body.append(['qr', url, caption])

    def big(self, t):
        self.body.append(['big', t])

    def head(self, t):
        self.body.append(['head', t])

    def link(self, url, pre='  '):
        self.body.append(['raw', pre + self.st(url, 'accent', bold=True)])

    def clear(self):
        self.body = []

    def view(self, lines, room):
        """A finished page taller than the window: `room` rows from self.scroll, with "↑/↓ n more" where rows are hidden."""
        hidden = len(lines) - room
        if hidden <= 0 or room < 3:
            return lines[:room]
        self.hidden = hidden
        top = self.scroll = max(0, min(self.scroll, hidden))
        out = lines[top:top + room]
        if top:
            out[0] = self.st(f"{self.g['up']} {top + 1} more", 'fg3')
        if top < hidden:
            out[-1] = self.st(f"{self.g['down']} {hidden - top + 1} more", 'fg3')
        return out

    def body_lines(self, W, avail, items, tail=()):
        """The page body in `avail` rows or more; a finished page (tail = its Enter prompt) is cut to fit and scrolls."""
        qr = next((i for i in items if i[0] == 'qr'), None)
        items = [i for i in items if i[0] != 'qr']
        fin = lambda lines, w=W: (self.view(lines, avail - len(tail)) + self.render_items(tail, w)) if self.waiting else lines
        if qr:
            ql, qw = qr_lines(qr[1])
            if self.color:
                ql = [f'\x1b[38;2;255;255;255;48;2;0;0;0m{l}\x1b[0m' if self.mode == 'truecolor' else f'\x1b[38;5;231;48;5;16m{l}\x1b[0m'
                      for l in ql]
            side = W - qw - 4
            cap = [self.st(x, 'fg3') for x in wrap(qr[2], qw)] if qr[2] else []
            cap = cap if len(ql) + len(cap) <= avail else []
            if side >= 34 and len(ql) <= avail:  # the code on the left, everything else beside it (scrolling, if need be)
                right = fin(self.render_items(items, side), side)  # the prompt too: under the text, beside the code
                left = ql + cap
                n = max(len(left), len(right))
                return [(left[k] if k < len(left) else ' ' * qw) + '    ' + (right[k] if k < len(right) else '') for k in range(n)]
            lines = self.render_items(items, W)
            if len(lines) + len(ql) + 1 <= avail - len(tail):
                pad = ' ' * ((W - qw) // 2)
                return fin(lines + [''] + [pad + l for l in ql])
            return fin([self.st('Make this window taller to see a QR code for your phone.', 'fg3'), ''] + lines)
        return fin(self.render_items(items, W))

    def render_items(self, items, W):
        out = []
        for it in items:
            kind = it[0]
            if kind == 'gap':
                out.append('')
            elif kind == 'text':
                out += [self.st(l, it[2]) for l in wrap(it[1], min(W, 74)) or ['']]
            elif kind == 'head':
                out.append(self.st(it[1], bold=True))
            elif kind == 'big':
                out.append(self.st(it[1], 'accent', bold=True))
            elif kind == 'raw':
                out.append(it[1])
            elif kind == 'row':
                _, k, label, detail = it
                style = (lambda t: self.st(t, 'fg2')) if k in ('info', 'todo') else (lambda t: t)
                parts = wrap(label, W - 2) or ['']
                if detail and len(parts) == 1 and len(parts[0]) + 4 + len(detail) <= W:
                    out.append(f'{self.icon(k)} ' + style(parts[0]) + '  ' + self.st(detail, 'fg3'))
                    continue
                out += [(f'{self.icon(k)} ' if j == 0 else '  ') + style(l) for j, l in enumerate(parts)]
                out += ['  ' + self.st(l, 'fg3') for l in wrap(detail, W - 2)]
            elif kind == 'logo':
                out += it[1]
        return out

    # ── frame ──
    def header(self, W, compact):
        left = self.st('Mindbaton', bold=True) + self.st('  ' + self.word, 'fg3')
        right = self.st(self.who, 'fg2') if self.who else ''
        if compact and self.steps and self.step is not None:
            right = self.st(f'{self.step + 1}/{len(self.steps)} {self.steps[self.step]}', 'fg2')
        lines = [left + ' ' * max(1, W - vlen(left) - vlen(right)) + right]
        if compact or not self.steps or self.step is None:
            return lines + [self.st(self.g['rule'] * W, 'fg3')]
        n, cur = len(self.steps), self.step
        row = '  '.join(self.icon('ok') + ' ' + self.st(name, 'fg3') if i < cur else
                        self.st(str(i + 1), 'accent', bold=True) + ' ' + self.st(name, bold=True) if i == cur else
                        self.st(f'{i + 1} {name}', 'fg3') for i, name in enumerate(self.steps))
        done = round(W * cur / max(1, n - 1))
        bar = self.st(self.g['bar'] * done, 'accent') + self.st(self.g['rule'] * (W - done), 'fg3')
        if vlen(row) > W:  # not every step name fits: "3/8 Account" on the right, and the bar
            return self.header(W, True)[:1] + [bar]
        return lines + [row, bar]

    def render(self, extra=(), focus=None, keys=()):
        cols, rows = shutil.get_terminal_size((80, 24))
        if cols < 40 or rows < 12:
            msg = ['Make this window a little bigger', f'at least 40 × 12 (now {cols} × {rows})']
            frame = [''] * rows
            for k, m in enumerate(msg):
                if 0 <= rows // 2 - 1 + k < rows:
                    frame[rows // 2 - 1 + k] = ' ' * max(0, (cols - len(m)) // 2) + fit(self.st(m, 'fg2' if k else None, bold=not k), cols)
            return self.paint(frame)
        W = min(cols - 4, 92)
        x0 = (cols - W) // 2
        H = min(rows, 32)  # tall terminals: a centred frame, not a page stretched to the bottom
        compact = rows < 20
        head = self.header(W, compact) + ['']
        if self.title:
            head += [self.st(l, bold=True) for l in wrap(self.title, W)]
            head += [self.st(l, 'fg2') for l in wrap(self.sub, min(W, 74))] + ['']
        pairs = []
        for k, v in keys + (('ctrl-c', 'quit'),):
            pairs.append(self.st(k, 'fg2') + ' ' + self.st(v, 'fg3'))
        foot = ['', '   '.join(pairs)]
        avail = max(1, H - len(head) - len(foot))
        items, tail = (self.body[:-2], self.body[-2:]) if self.waiting else (self.body, [])  # the Enter prompt stays in sight
        self.hidden = 0
        body = self.body_lines(W, avail, items + list(extra), tail)
        if focus is not None:
            focus += len(self.body_lines(W, avail, items))  # focus counts from the end of the static body
        if len(body) > avail:  # while working: the newest rows (or the focused field)
            start = len(body) - avail if focus is None else max(0, min(focus - avail // 2, len(body) - avail))
            body = body[start:start + avail]
        page = head + body + [''] * max(0, avail - len(body)) + foot
        y0 = (rows - H) // 2
        frame = [''] * y0 + [' ' * x0 + fit(l, W) if l else '' for l in page[:H]]
        frame += [''] * (rows - len(frame))
        self.paint(frame[:rows])

    def paint(self, frame):
        if self.resized:
            self.resized, self.last = False, None
            self.out('\x1b[2J')
        if frame == self.last:
            return
        out = ['\x1b[?2026h']  # synchronized update: no tearing where the terminal supports it
        for i, line in enumerate(frame):
            if self.last is None or i >= len(self.last) or self.last[i] != line:
                out.append(f'\x1b[{i + 1};1H\x1b[0m\x1b[2K{line}')
        self.out(''.join(out) + '\x1b[?2026l')
        self.last = frame

    def keys(self, timeout):
        try:
            r = select.select([self.fd], [], [], timeout)[0]
        except InterruptedError:
            return []
        if not r:
            return []
        ks = parse_keys(os.read(self.fd, 4096).decode('utf-8', 'replace'))
        if 'ctrl-c' in ks:
            raise KeyboardInterrupt
        return ks

    def loop(self, draw, on_key):
        """draw() → (extra lines, focus line in them, key hints); on_key(k) → a result to return, or None."""
        self.termios.tcflush(self.fd, self.termios.TCIFLUSH)  # keys typed during the last screen don't answer this one
        while True:
            extra, focus, hints = draw()
            self.render(extra, focus, hints)
            for k in self.keys(0.05):
                r = on_key(k)
                if r is not None:
                    return r

    # ── widgets ──
    def task(self, label, fn, done=None, hint=''):
        """Runs fn with a spinner; the row turns into ✓ (with done(result) as detail) or ✗ with the reason."""
        item = self.row('spin', label, hint)
        box = {}

        def work():
            try:
                box['r'] = fn()
            except BaseException as e:  # shown on the row; the caller decides what happens next
                box['e'] = e
        th = threading.Thread(target=work, daemon=True)
        th.start()
        while th.is_alive():
            self.render()
            self.keys(0.05)
        if 'e' in box:
            item[1], item[3] = 'fail', friendly(box['e'])
            self.render()
            raise box['e']
        item[1] = 'ok'
        item[3] = (done(box.get('r')) or '') if done else ''
        self.render()
        return box.get('r')

    def busy(self, label, fn):
        """Like task, but the spinner row goes away afterwards (for form submissions that may be retried)."""
        try:
            return self.task(label, fn)
        finally:
            self.body.pop()

    def pause(self, secs=0.7):
        end = time.monotonic() + secs
        while time.monotonic() < end:
            self.render()
            self.keys(0.05)

    def wait(self, label='continue'):
        prompt = [['gap'], ['raw', self.st('Press ', 'fg2') + self.st('Enter', 'accent', bold=True) + self.st(f' to {label}', 'fg2')]]
        self.body += prompt
        self.waiting, self.scroll = True, 0

        def key(k):
            step = {'up': -1, 'down': 1, 'pgup': -8, 'pgdn': 8, 'home': -999, 'end': 999}.get(k)
            if step:
                self.scroll += step
            return True if k == 'enter' else None
        try:
            self.loop(lambda: ((), None, ((('↑↓', 'scroll'),) if self.hidden else ()) + (('enter', label),)), key)
        finally:
            del self.body[-2:]
            self.waiting = False

    def choose(self, options, default=0, cancel=False):
        """options: [(label, hint, detail?)] → index (None on Esc when cancel)."""
        sel = [default]
        wide = max(vlen(o[0]) for o in options) + 3

        def draw():
            lines = []
            for i, o in enumerate(options):
                on = i == sel[0]
                label = self.st(o[0], bold=True) if on else self.st(o[0], 'fg2')
                hint = self.st(o[1], 'accent' if on else 'fg3') if len(o) > 1 and o[1] else ''
                lines.append(['raw', (self.st(self.g['sel'], 'accent', bold=True) if on else ' ') + ' ' + label
                              + ' ' * (wide - vlen(o[0])) + hint])
                if on and len(o) > 2 and o[2]:
                    lines += [['raw', '  ' + self.st(l, 'fg3')] for l in wrap(o[2], 70)]
            focus = next(k for k, l in enumerate(lines) if self.g['sel'] in ANSI.sub('', l[1])[:2])
            return lines, focus, (('↑↓', 'choose'), ('enter', 'select')) + ((('esc', 'back'),) if cancel else ())

        def key(k):
            if k in ('up', 'shift-tab'):
                sel[0] = (sel[0] - 1) % len(options)
            elif k in ('down', 'tab'):
                sel[0] = (sel[0] + 1) % len(options)
            elif k == 'enter':
                return sel[0]
            elif k == 'esc' and cancel:
                return -1
        r = self.loop(draw, key)
        return None if r == -1 else r

    def checklist(self, items, note=''):
        """items: [{'label', 'hint', 'on'}] → indexes ticked."""
        sel = [0]
        wide = max(vlen(i['label']) for i in items) + 3

        def draw():
            lines = []
            for k, it in enumerate(items):
                on = k == sel[0]
                box = self.st(self.g['on'], 'accent', bold=True) if it['on'] else self.st(self.g['off'], 'fg3')
                label = self.st(it['label'], bold=on) if it['on'] or on else self.st(it['label'], 'fg2')
                lines.append(['raw', (self.st(self.g['sel'], 'accent', bold=True) if on else ' ') + f' {box} {label}'
                              + ' ' * (wide - vlen(it['label'])) + self.st(it.get('hint', ''), 'fg3')])
            if note:
                lines += [['gap']] + [['raw', self.st(l, 'fg3')] for l in wrap(note, 74)]
            n = sum(i['on'] for i in items)
            return lines, sel[0], (('↑↓', 'move'), ('space', 'tick'), ('enter', f'connect {n}' if n else 'skip'))

        def key(k):
            if k in ('up', 'shift-tab'):
                sel[0] = (sel[0] - 1) % len(items)
            elif k in ('down', 'tab'):
                sel[0] = (sel[0] + 1) % len(items)
            elif k in ('space', ('text', 'x')):
                items[sel[0]]['on'] = not items[sel[0]]['on']
            elif k == ('text', 'a'):
                every = not all(i['on'] for i in items)
                for i in items:
                    i['on'] = every
            elif k == 'enter':
                return [k for k, i in enumerate(items) if i['on']]
        return self.loop(draw, key)

    def form(self, fields, cancel=False, submit='continue'):
        """Text fields (masked when secret, Ctrl-R shows them). Enter checks the field and moves on; on the last one it
        checks them all. → {label: value}, or None on Esc when cancel."""
        cur = [next((k for k, f in enumerate(fields) if f['error']), 0)]
        reveal = [False]
        lw = max(len(f['label']) for f in fields) + 3

        def draw():
            lines, focus = [], 0
            W = min(shutil.get_terminal_size((80, 24)).columns - 4, 92)
            for k, f in enumerate(fields):
                on = k == cur[0]
                v = f['value']
                shown = '•' * len(v) if f['secret'] and not reveal[0] and self.g['dot'] == '•' else '*' * len(v) if f['secret'] and not reveal[0] else v
                room = max(8, W - lw - 5)
                shown = ('…' + shown[-(room - 1):]) if len(shown) > room else shown
                caret = self.st(' ', rev=True) if on else ''
                ph = self.st(f['placeholder'], 'fg3') if not v and f['placeholder'] else ''
                value = shown + caret + (' ' + ph if ph and on else ph if ph else '')
                mark = self.st(self.g['sel'], 'accent', bold=True) if on else ' '
                label = self.st(f['label'].ljust(lw), None if on else 'fg2', bold=on)
                if on:
                    focus = len(lines)
                lines.append(['raw', f'{mark} {label}{value}'])
                err = f['error'] and (f['error']() if callable(f['error']) else f['error'])
                if err:  # a glyph and bold too, so it doesn't rest on colour alone (NO_COLOR)
                    lines += [['raw', ' ' * (lw + 2) + self.st((self.g['fail'] + ' ' if j == 0 else '  ') + l, 'danger', bold=not self.color)]
                              for j, l in enumerate(wrap(err, max(20, W - lw - 4)))]
                if f.get('note'):
                    lines += [['raw', ' ' * (lw + 4) + self.st(l, 'fg3')] for l in wrap(f['note'], max(20, W - lw - 4))]
            hints = ((('tab', 'next'),) if len(fields) > 1 else ()) + (('enter', submit if cur[0] == len(fields) - 1 else 'next'),)
            if any(f['secret'] for f in fields):
                hints += (('ctrl-r', 'hide' if reveal[0] else 'show'),)
            return lines, focus, hints + ((('esc', 'back'),) if cancel else ())

        def check(k):
            f = fields[k]
            f['error'] = f['check'](f['value'].strip() if not f['secret'] else f['value'], fields) if f['check'] else None
            return not f['error']

        def key(k):
            f = fields[cur[0]]
            if isinstance(k, tuple):
                add = ''.join(ch for ch in k[1] if ch.isprintable() and ch not in '\r\n')
                if add:
                    f['value'] += add.strip() if k[0] == 'paste' else add
                    f['error'] = None
            elif k == 'space':
                f['value'] += ' '
            elif k == 'backspace':
                f['value'], f['error'] = f['value'][:-1], None
            elif k in ('ctrl-u', 'ctrl-w'):
                f['value'], f['error'] = '', None
            elif k == 'ctrl-r':
                reveal[0] = not reveal[0]
            elif k in ('up', 'shift-tab'):
                cur[0] = max(0, cur[0] - 1)
            elif k in ('down', 'tab'):
                cur[0] = min(len(fields) - 1, cur[0] + 1)
            elif k == 'esc' and cancel:
                return 0
            elif k == 'enter':
                if not check(cur[0]):
                    return None
                if cur[0] < len(fields) - 1:
                    cur[0] += 1
                    return None
                bad = [i for i in range(len(fields)) if not check(i)]
                if bad:
                    cur[0] = bad[0]
                    return None
                return {f['label']: (f['value'] if f['secret'] else f['value'].strip()) for f in fields}
        r = self.loop(draw, key)
        return None if r == 0 else r

    def welcome(self, sentence, action):
        """The logo (drawn in from the bottom-left, the way the baton moves), one sentence, Enter. No step row: the logo
        says where you are."""
        self.page(None, '', '')
        t0 = time.monotonic()
        light = self.light if self.color else False

        def draw():
            cols, rows = shutil.get_terminal_size((80, 24))
            W, rows = min(cols - 4, 92), min(rows, 32)
            k = 1.0 if not self.motion else min(1.0, (time.monotonic() - t0) / 0.7)
            text = wrap(sentence, min(W, 64))
            art, width = logo(W, max(0, rows - 13 - len(text)), mode=self.mode, light=light, reveal=1 - (1 - k) ** 3)
            center = lambda s: ' ' * max(0, (W - vlen(s)) // 2) + s
            lines = [['raw', center(l)] for l in art] or [['raw', center(self.st('Mindbaton', 'accent', bold=True))]]
            lines += [['gap'], ['raw', center(self.st('Tell one AI. Every AI knows.', bold=True))], ['gap']]
            lines += [['raw', center(self.st(l, 'fg2'))] for l in text]
            lines += [['gap'], ['raw', center(self.st(f' {action} ', 'accent', bold=True, rev=True) if self.color else
                                             self.st(f'[ {action} ]', bold=True))]]
            room = rows - (4 if rows >= 20 else 3) - 2
            return [['gap']] * max(0, (room - len(lines)) // 2 - 1) + lines, None, (('enter', action.lower()),)
        self.loop(draw, lambda k: True if k == 'enter' else None)


def friendly(e):
    if isinstance(e, (Stop, Unsafe, RuntimeError)):
        return str(e)
    if isinstance(e, KeyboardInterrupt):
        return 'stopped'
    if isinstance(e, OSError) and e.filename:  # the file itself, not its backup or temp copy
        f = tilde(re.sub(r'\.bak-mindbaton-[\d-]+$', '', re.sub(r'/\.([^/]+)\.mindbaton-tmp$', r'/\1', str(e.filename))))
        if isinstance(e, PermissionError):
            return f"Mindbaton can't write {f} (no permission). Fix that folder's permissions, then run this again."
        return f"Couldn't write {f}: {(e.strerror or str(e)).lower()}."
    if isinstance(e, OSError) and e.strerror:
        return e.strerror + '.'
    return f'{type(e).__name__}: {e}'


class Plain:
    """No terminal to draw on (CI, Docker, a pipe) or --yes: the same steps as plain lines; answers come from flags."""
    interactive = False

    def __init__(self, steps, word):
        self.steps, self.who, self.step = steps, '', None
        self.c = sys.stdout.isatty() and not os.environ.get('NO_COLOR')
        utf = 'utf' in (sys.stdout.encoding or '').lower()
        self.g = dict(ok='✓', fail='✗', warn='!', info='·', todo='○', spin='…') if utf else dict(ok='ok', fail='x', warn='!', info='-', todo='o', spin='..')
        print(self.b(f'Mindbaton {word}'), flush=True)

    def b(self, t):
        return f'\x1b[1m{t}\x1b[0m' if self.c else t

    def page(self, step, title, sub=''):
        self.step = step
        n = f'[{step}/{len(self.steps) - 1}] ' if self.steps and step else ''  # the Welcome screen is never shown here
        print('\n' + self.b(n + title) if title else '', flush=True)

    def retitle(self, title, sub=None):
        pass

    def row(self, kind, label, detail=''):
        print(f'  {self.g[kind]} {label}' + (f' ({detail})' if detail else ''), flush=True)
        return ['row', kind, label, detail]

    def text(self, t, role=None):
        print('\n'.join('  ' + l for l in wrap(t, 100)), flush=True)

    def big(self, t):
        print('  ' + t, flush=True)

    def head(self, t):
        print('  ' + t, flush=True)

    def link(self, url, pre='  '):
        print('    ' + url, flush=True)

    def gap(self):
        pass

    def qr(self, url, caption):
        pass

    def clear(self):
        pass

    def task(self, label, fn, done=None, hint=''):
        try:
            r = fn()
        except BaseException as e:
            self.row('fail', label, friendly(e))
            raise
        self.row('ok', label, done(r) if done else '')
        return r

    def busy(self, label, fn):
        return fn()

    def pause(self, secs=0):
        pass

    def wait(self, label=''):
        pass

    def choose(self, options, default=0, cancel=False):
        return default

    def checklist(self, items, note=''):
        return [k for k, i in enumerate(items) if i['on']]

    def form(self, fields, cancel=False, submit=''):
        raise Stop('This step needs an answer and there is no terminal to ask in. Run it in a terminal, or pass the '
                   'answers as flags (python3 mindbaton.py --help).')

    def close(self):
        pass


def make_ui(steps, o, word):
    if getattr(o, 'yes', False) or not (sys.stdin.isatty() and sys.stdout.isatty()) or os.environ.get('TERM') in ('dumb', ''):
        return Plain(steps, word)
    import importlib.util
    if importlib.util.find_spec('termios') is None:  # Windows: no raw terminal mode
        return Plain(steps, word)
    return TUI(steps, word, motion=not getattr(o, 'no_motion', False))


# ── Install ────────────────────────────────────────────────────────────────────────────────────────────────

INSTALL_STEPS = ['Welcome', 'Check', 'Account', 'AI keys', 'Your AI tools', 'Connect', 'Memories', 'Start', 'Done']
CONNECT_STEPS = ['Welcome', 'Pair', 'Your AI tools', 'Connect', 'Memories', 'Done']
WORDS = ('/usr/share/dict/american-english', '/usr/share/dict/british-english', '/usr/share/dict/words')
USERNAME = re.compile(r'[a-z0-9._-]{2,32}')
CLI = 'python3 ~/.mindbaton/mindbaton.py'  # how the person runs this later (install_client puts it there)
START_HINT = None  # set when setup ends with Mindbaton not running: how to start it


def fts5_ok():
    try:
        import sqlite3
        sqlite3.connect(':memory:').execute('create virtual table t using fts5(x)')
        return True
    except Exception:
        return False


def step_check(ui, ctx, o):
    ui.page(1, 'Checking this computer', 'Making sure Mindbaton has everything it needs.')
    v = sys.version_info
    probs = []
    ok = v >= (3, 9)
    ui.row('ok' if ok else 'fail', f'Python {v.major}.{v.minor}.{v.micro}', '' if ok else 'Mindbaton needs Python 3.9 or newer')
    probs += [] if ok else ['python']
    ok = fts5_ok()
    log('check: SQLite FTS5', 'ok' if ok else 'missing')
    ui.row('ok' if ok else 'fail', 'Search engine', '' if ok else "this Python's SQLite has no full-text search (FTS5): "
                                                                  "install a newer python3, or use Docker")
    probs += [] if ok else ['fts5']
    words = next((p for p in WORDS if os.path.exists(p)), None)
    log('check: word list', words or 'missing')
    ui.row('ok' if words else 'fail', 'Dictionary', '' if words else
           'install one: sudo apt install wamerican · sudo dnf install words · sudo pacman -S words')
    probs += [] if words else ['words']
    d = data_dir()
    while not d.exists() and d != d.parent:
        d = d.parent
    free = shutil.disk_usage(d).free
    ok = free > 200e6
    ui.row('ok' if ok else 'fail', 'Space for your memories', f'{free / 1e9:.0f} GB free' if free > 2e9 else f'{free / 1e6:.0f} MB free — needs 200 MB')
    probs += [] if ok else ['disk']
    if probs:
        ui.gap()
        ui.text('Fix the items marked above, then run ./install.sh again.', 'danger')
        ui.wait('quit')
        raise Stop('Setup stopped: this computer is missing something Mindbaton needs (see above).')

    port = int(o.port or setting('MINDBATON_PORT', 3004))
    ctx['running'], moved = None, False
    if port_busy(port):
        h = health(f'http://127.0.0.1:{port}')
        if h:
            ctx['running'] = h
            ui.row('ok', f'Mindbaton is already running on port {port}', f'version {h.get("version", "?")}')
        else:
            alt = next((p for p in range(port + 1, port + 200) if not port_busy(p)), None)
            ui.row('warn', f'Port {port} is used by another program')
            if ui.interactive:
                ui.gap()

                def good(v, _):
                    if not v.isdigit() or not 1024 <= int(v) <= 65535:
                        return 'Use a number from 1024 to 65535.'
                    if port_busy(int(v)):
                        return f'Port {v} is in use too. Try another.'
                while ui.choose([(f'Use port {alt}', 'free'), ('Type a different port', '')]) == 1:
                    v = ui.form([field('Port', str(alt), check=good)], cancel=True, submit='use it')
                    if v:
                        alt = int(v['Port'])
                        break
                ui.body.pop()  # the gap before the menu
            port, moved = alt, True
            ui.row('ok', f'Mindbaton will use port {port}')
    else:
        ui.row('ok', f'Port {port} is free')
    ctx['port'], ctx['base'] = port, f'http://127.0.0.1:{port}'
    set_env(MINDBATON_HOST=os.environ.get('MINDBATON_HOST') or env_file().get('MINDBATON_HOST') or '0.0.0.0',
            MINDBATON_PORT=port, **({'MINDBATON_DATA': os.environ['MINDBATON_DATA']} if os.environ.get('MINDBATON_DATA') else {}))
    ui.task('Self-test', self_test, lambda _: 'all good', 'about 10 seconds')
    ui.gap()
    ui.text('Everything looks good.', 'ok')
    ui.wait() if moved else ui.pause(0.8)  # a changed port is worth a look; all green just moves on


def default_names():
    user = getpass.getuser()
    try:
        import pwd
        full = pwd.getpwnam(user).pw_gecos.split(',')[0].strip()
    except (ImportError, KeyError):
        full = ''
    uname = re.sub(r'[^a-z0-9._-]', '', user.lower())[:32]
    first = full.split()[0] if full else uname
    return (first.capitalize() if first.islower() else first), uname if USERNAME.fullmatch(uname) else ''


def check_name(v, _):
    return None if 1 <= len(v) <= 40 else 'Type your name (up to 40 characters).'


def check_user(v, _):
    return None if USERNAME.fullmatch(v.lower()) else 'Use 2–32 letters, numbers, dots, dashes or underscores.'


def check_pw(v, _):
    return None if len(v) >= 8 else 'Use at least 8 characters.'


def check_again(v, fs):
    if v == fs[2]['value']:
        return None
    fs[3]['value'] = ''  # start the second one over; nobody should need Ctrl-U
    return "The passwords don't match. Type it again."


def login_failed(f, s, d, hint=None):
    """The password field after a failed sign-in: what happened, a way out, and a live countdown when locked."""
    f['value'] = ''
    if s == 429:
        until = time.monotonic() + int(d.get('retry_after') or 60)
        f['error'] = lambda: (f'Too many tries. Try again in {int(until - time.monotonic()) + 1} s.'
                              if time.monotonic() < until else 'You can try again now.')
    else:
        f['error'] = 'Wrong username or password. Try again.' if s == 401 else err_text(d, f'Sign-in failed ({s or "no answer"})')
    if s in (401, 429) and hint:
        f['note'] = hint


def step_account(ui, ctx, o):
    base = ctx['base']
    ui.page(2, 'Your account', '')
    if not health(base):
        ctx['server'] = start_server(ctx['port'])  # its PID is ours before any waiting starts
        ui.task('Starting Mindbaton', lambda: server_up(ctx['server'], ctx['port']))
        ui.clear()
    s, st, _ = http('GET', base + '/api/auth/state')
    if s != 200:
        raise Stop(f"Mindbaton on port {ctx['port']} didn't answer properly ({s}). The log is in {tilde(MB / 'server.log')}.")
    if st.get('setup_needed'):
        create_account(ui, ctx, o)
    else:
        sign_in(ui, ctx, o, st.get('profiles') or [])
    acc = ctx['account']
    ui.who = acc['display_name']
    ui.row('ok', f"Signed in as {acc['display_name']}", f"@{acc['username']} · {acc['role']}")
    cfg = load_cfg()
    if cfg.get('url') == base and cfg.get('token_id'):
        http('DELETE', f"{base}/api/tokens/{cfg['token_id']}", cookie=ctx['cookie'])  # this computer's old CLI token
    tid, token = new_token(base, ctx['cookie'], f'Mindbaton CLI on {HOSTNAME}', 'agent')
    cfg.update(url=base, token=token, token_id=tid, account=acc['username'], server_dir=str(HERE))
    save_cfg(cfg)
    ui.pause(0.8)


def create_account(ui, ctx, o):
    base = ctx['base']
    ui.retitle('Create your account', "You'll be the admin of this Mindbaton. You can add family or friends later, each with their own private memory.")
    if not ui.interactive:
        if not (o.username and o.password_file):
            raise Stop('To create the account without a terminal, pass --username and --password-file.')
        pw = Path(o.password_file).read_text().splitlines()[0] if Path(o.password_file).exists() else ''
        err = check_user(o.username, 0) or check_pw(pw, 0)
        if err:
            raise Stop(err)
        s, d, cookie = http('POST', base + '/api/auth/setup', {'username': o.username.lower(), 'password': pw,
                                                               'display_name': o.display_name or o.username.capitalize()})
        if s != 200:
            raise Stop(err_text(d, f"Couldn't create the account ({s})"))
        ctx.update(cookie=cookie, account=d['account'])
        return
    name, user = default_names()
    fields = [field('Your name', name, check=check_name, placeholder='shown in the app'),
              field('Username', user, check=check_user, placeholder='for signing in'),
              field('Password', '', True, check_pw, 'at least 8 characters'),
              field('Password again', '', True, check_again)]
    while True:
        v = ui.form(fields, submit='create account')
        s, d, cookie = ui.busy('Creating your account', lambda: http('POST', base + '/api/auth/setup', {
            'username': v['Username'].lower(), 'display_name': v['Your name'], 'password': v['Password']}))
        if s == 200:
            ctx.update(cookie=cookie, account=d['account'])
            return
        if s == 409 and 'sign in' in d.get('error', ''):
            return sign_in(ui, ctx, o, http('GET', base + '/api/auth/state')[1].get('profiles') or [])
        e = err_text(d, f"Couldn't create the account ({s or 'no answer'})")
        fields[1 if 'username' in e.lower() else 2 if 'password' in e.lower() else 0]['error'] = e


def sign_in(ui, ctx, o, profiles):
    base = ctx['base']
    ui.retitle('Sign in', 'Mindbaton is already set up here. Sign in to connect your AI tools.')
    if not ui.interactive:
        if not (o.username and o.password_file):
            raise Stop('Mindbaton is already set up here. To sign in without a terminal, pass --username and --password-file.')
        pw = Path(o.password_file).read_text().splitlines()[0]
        s, d, cookie = http('POST', base + '/api/auth/login', {'username': o.username, 'password': pw})
        if s != 200:
            raise Stop(err_text(d, f"Couldn't sign in ({s})"))
        ctx.update(cookie=cookie, account=d['account'])
        return
    user = None
    if len(profiles) == 1:
        user = profiles[0]['username']
        ui.row('info', f"Signing in as {profiles[0]['display_name']}", '@' + user)
    elif profiles:
        i = ui.choose([(p['display_name'], '@' + p['username']) for p in profiles] + [('Someone else', 'type a username')])
        user = profiles[i]['username'] if i < len(profiles) else None
    fields = ([] if user else [field('Username', '', check=check_user)]) + [field('Password', '', True, check_pw)]
    while True:
        v = ui.form(fields, submit='sign in')
        name = user or v['Username'].lower()
        s, d, cookie = ui.busy('Signing in', lambda: http('POST', base + '/api/auth/login', {'username': name, 'password': v['Password']}))
        if s == 200:
            ctx.update(cookie=cookie, account=d['account'])
            return
        login_failed(fields[-1], s, d, f"Forgot it? Run: python3 {tilde(HERE / 'server.py')} --reset-password {name}")


def new_token(base, cookie, name, kind):
    s, d, _ = http('POST', base + '/api/tokens', {'name': name, 'kind': kind}, cookie=cookie)
    if s != 200:
        raise RuntimeError(err_text(d, f"couldn't create a token ({s})"))
    return d['id'], d['token']


def ai_status(base, cred):
    s, d, _ = http('GET', base + '/ai', **cred)
    return set(d.get('providers') or []) if s == 200 else set()


def add_key(ui, base, cred, provider, key=None):
    """One key: paste it (masked), check it with the provider, save it through the admin API. → saved?"""
    name, who, site, _ = KEY_SITES[provider]
    save = lambda k: http('POST', base + '/settings/ai-key', {'provider': provider, 'key': k}, timeout=40, **cred)
    if not ui.interactive:
        err = check_key(provider, key)
        s, d, _ = (0, {'error': err}, None) if err else save(key)
        ui.row('ok' if s == 200 else 'fail', f'{name} key', 'saved' if s == 200 else err_text(d, f'not saved ({s})'))
        return s == 200
    ui.retitle(f'Add a free {name} key', 'Free, no card needed. It takes a minute.')
    ui.clear()
    n = lambda i: ui.st(str(i), 'accent', bold=True) + '  '
    ui.body += [['raw', n(1) + 'Open ' + ui.st(site, 'accent', bold=True) + (' and sign in with Google' if provider == 'gemini' else ' and sign in')],
                ['raw', n(2) + f'Click “{"Create API key" if provider == "gemini" else "Create API Key"}” and copy the key'],
                ['raw', n(3) + 'Paste it here ' + ui.st('(it stays on your Mindbaton)', 'fg3')], ['gap']]
    f = field(f'{name} key', '', True, placeholder='paste here')
    while True:
        v = ui.form([f], cancel=True, submit='check and save')
        if v is None:
            return False
        key = v[f['label']].strip()
        f['error'] = ui.busy(f'Checking the key with {who}', lambda: check_key(provider, key))
        if f['error']:
            continue
        s, d, _ = ui.busy('Saving it', lambda: save(key))
        if s == 200:
            return True
        f['error'] = err_text(d, f"Mindbaton couldn't save it ({s or 'no answer'})")


def keys_screen(ui, base, cred, step, local_remove=False):
    """The key menu: shows what's set, adds or replaces a key, removes one (on the server's own computer)."""
    title, sub = 'Free AI keys', ('Optional. Mindbaton works without them. A free key lets it write a summary when a chat '
                                   'runs out of room, and answer questions about your memory.')
    while True:
        ui.page(step, title, sub)
        have = ai_status(base, cred)
        for p, (name, who, site, _) in KEY_SITES.items():
            ui.row('ok' if name in have else 'todo', name, 'added' if name in have else 'not added · free at ' + site.split('//')[1])
        ui.gap()
        opts, acts = [], []
        for p, (name, *_rest) in KEY_SITES.items():
            opts.append((f'{"Replace" if name in have else "Add"} the {name} key', '' if name in have else 'free'))
            acts.append(('add', p))
        if local_remove:
            for p, (name, *_rest) in KEY_SITES.items():
                if name in have:
                    opts.append((f'Remove the {name} key', ''))
                    acts.append(('remove', p))
        opts.append(('Continue', '') if have else ('Skip for now', '', f'Add them later with: {CLI} keys'))
        acts.append(('done', None))
        i = ui.choose(opts, default=len(opts) - 1 if have else 0)
        act, p = acts[i]
        if act == 'done':
            return
        if act == 'add':
            add_key(ui, base, cred, p)
        else:
            remove_local_key(p)


def step_keys(ui, ctx, o):
    if ctx['account']['role'] != 'admin':
        ui.page(3, 'Free AI keys', '')
        ui.row('info', 'Only an admin can add AI keys to this Mindbaton.')
        return ui.wait()
    cred = {'cookie': ctx['cookie']}
    if ui.interactive:
        return keys_screen(ui, ctx['base'], cred, 3)
    ui.page(3, 'Free AI keys')
    given = [(p, getattr(o, p + '_key')) for p in KEY_SITES if getattr(o, p + '_key', None)]
    for p, k in given:
        if not add_key(ui, ctx['base'], cred, p, k):
            ctx['failed'].append(f'the {KEY_SITES[p][0]} key')
    if not given:
        ui.row('info', 'Skipped', f'add them later with: {CLI} keys')


def step_tools(ui, o, step):
    ui.page(step, 'Your AI tools', 'Tick the ones that should share your memory. Mindbaton adds itself to their '
                                   'settings and keeps a backup of every file it changes.')
    found = {t: w for t in TOOLS if (w := detect(t))}
    connected = load_cfg().get('tools') or {}
    missing = [TOOLS[t][0] for t in TOOLS if t not in found]
    if not ui.interactive:
        want = (o.tools or 'all').lower()
        pick = [] if want == 'none' else list(found) if want == 'all' else [t.strip() for t in want.split(',') if t.strip()]
        for t in pick:
            if t not in TOOLS:
                raise Stop(f"--tools: there's no tool called {t!r}. Known: {', '.join(TOOLS)}.")
            ui.row('ok' if t in found else 'warn', TOOLS[t][0], found.get(t) or 'not found here; connecting anyway')
        if not pick:
            ui.row('info', 'No AI tools found on this computer' if want == 'all' else 'Skipped')
        return pick
    if not found:
        ui.row('info', 'No AI tools found on this computer.')
        ui.text('Install Claude Code, Codex, Cursor or another one, then run this again. You can still use Mindbaton in '
                'the browser and from your phone.')
        ui.wait()
        return []
    items = [{'label': TOOLS[t][0], 'hint': ('connected · ' if t in connected else '') + w, 'on': True, 'id': t} for t, w in found.items()]
    picked = ui.checklist(items, note='Not found here: ' + ', '.join(missing) if missing else '')
    return [items[k]['id'] for k in picked]


def step_connect(ui, o, chosen, step, url, mint, local_admin=False, revoke=None):
    """Writes the settings of every chosen app. mint(tool) → (token id, token) for it; revoke(id) takes back a token
    minted for an app that then failed. → the names of the apps that failed."""
    ui.page(step, 'Connecting your tools', 'Adding Mindbaton to each one.')
    old = [(t, *x) for t in chosen for x in legacy(t, url)]
    if old:
        for t, n, at, same, _ in old:
            ui.row('info', f'"{n}" in {TOOLS[t][0]}', at or 'an older memory connection')
        same = all(x[3] for x in old)
        ui.gap()
        ui.text(('This is an older memory connection. ' if len(old) == 1 else 'These are older memory connections. ')
                + ("Replace it, or your AI sees every memory tool twice." if same else
                   "Replace it only if it's an old copy of this memory that you don't use any more."))
        ui.gap()
        replace = (ui.choose([('Replace with Mindbaton', 'recommended' if same else ''), ('Keep', '' if same else 'recommended')],
                             default=0 if same else 1) == 0) if ui.interactive else bool(o.replace_old)
        ui.clear()
        for t, n, at, same, rm in old:
            if replace:
                ui.task(f'Removed "{n}" from {TOOLS[t][0]}', rm)
            else:
                ui.row('info', f'Kept "{n}" in {TOOLS[t][0]}')
    ui.task('Capture script copied to ~/.mindbaton', lambda: install_client(url))  # doctor and keys run from there too
    if not chosen:
        ui.row('info', 'Nothing to connect.', 'run this again any time to add one')
        ui.wait()
        return []
    cfg = load_cfg()
    tools = cfg.setdefault('tools', {})
    mark = len(getattr(ui, 'body', []))
    done, failed, notes, unfinished = {}, [], [], []
    for t in chosen:
        capture = TOOLS[t][4] and not (t == 'claude' and local_admin)  # the server already reads this computer's Claude Code

        def one(t=t, capture=capture):
            tid, token = mint(t)
            try:
                what, note, state = connect_tool(t, url, token, capture, tools.get(t))
            except BaseException:
                if revoke and tid != (tools.get(t) or {}).get('token_id'):
                    revoke(tid)  # no app holds it: don't leave a dead device in Settings
                raise
            tools[t] = {**state, 'token_id': tid}
            save_cfg(cfg)
            if t == 'claude' and local_admin:
                what += ' · chats are saved automatically on this computer'
            return what, note
        try:
            what, note = ui.task(TOOLS[t][0], one, lambda r: r[0])
            if 'snippet' in what:
                unfinished.append(TOOLS[t][0])  # its warning row below says what to paste where
            if what != 'paste the snippet to finish':
                done.setdefault(what, []).append(TOOLS[t][0])
            if note:
                notes.append((TOOLS[t][0], note))
        except Exception as e:
            log('connect', t, 'failed:', repr(e))
            failed.append((TOOLS[t][0], friendly(e)))
    if ui.interactive and len(chosen) > 1:  # one row per outcome, so a failure never scrolls out of sight
        del ui.body[mark:]
        for what, names in done.items():
            ui.row('ok', ', '.join(names), what)
        for name, why in failed:
            ui.row('fail', name, why)
    for name, note in notes:
        ui.row('warn', name, note)
    ui.gap()
    ui.text(f'Every file that changed has a backup next to it (*.bak-mindbaton-{STAMP}).', 'fg3')
    ui.wait()
    return [name for name, _ in failed] + unfinished


def step_start(ui, ctx, o):
    ui.page(7, 'Keep Mindbaton running', 'Your AIs can only reach it while it runs.')
    base = ctx['base']
    kind = None if o.no_service else service_kind()
    if ctx.get('running'):
        if kind and service_active(kind):
            ctx['mode'] = 'service'
            ui.row('ok', 'Mindbaton runs as a background service', 'it starts again when this computer restarts')
        else:
            ctx['mode'] = 'existing'
            ui.row('ok', f"Mindbaton is already running on port {ctx['port']}")
        return ui.wait()
    opts = []
    if kind:
        opts.append(('Start automatically', 'recommended', 'Runs in the background and starts again when this computer restarts.'))
    opts.append(('Only while this window is open', '', 'Mindbaton runs here after setup and stops when you close the window.'))
    if ui.interactive:
        i = ui.choose(opts) if len(opts) > 1 else 0
    else:
        i = 0 if kind else len(opts) - 1
    ui.clear()
    if kind and i == 0:
        ui.task('Setup copy stopped', lambda: stop_server(ctx.pop('server', None)))
        ui.task('Background service installed' if kind == 'systemd' else 'Login item installed', lambda: install_service(kind),
                lambda _: 'systemd --user unit "mindbaton"' if kind == 'systemd' else 'launchd agent ai.mindbaton')

        def up():
            if not wait_health(base, 30):
                raise RuntimeError("it didn't answer; see: " + ('journalctl --user -u mindbaton' if kind == 'systemd' else '~/Library/Logs/mindbaton.log'))
        ui.task('Mindbaton is answering', up)
        ctx['mode'] = 'service'
        if kind == 'systemd' and not lingering():
            ui.gap()
            ui.row('info', 'To keep it running after you log out too, run this once:')
            ui.link(f'sudo loginctl enable-linger {getpass.getuser()}')
    else:
        global START_HINT
        START_HINT = f'cd {shlex.quote(str(HERE))} && python3 server.py'
        ctx['mode'] = 'foreground' if (ui.interactive or o.foreground) else 'manual'
        why = '' if kind else '--no-service was given' if o.no_service else "this computer can't run it as a service"
        if ctx['mode'] == 'foreground':
            ui.row('ok', 'Mindbaton will keep running in this window after setup', why)
        else:
            ui.row('info', 'Start Mindbaton yourself when setup ends', why)
            ui.link(START_HINT)
    ui.wait()


def not_set_up(ui, failed, retry):
    if failed:
        ui.row('warn', 'Not set up: ' + ', '.join(failed), f'the reasons are in {tilde(LOG)} · {retry} to retry')


def step_done(ui, ctx, chosen):
    acc, failed = ctx['account'], ctx['failed']
    port, host = ctx['port'], setting('MINDBATON_HOST', '0.0.0.0')
    ip = lan_ip() if host in ('0.0.0.0', '::', '') else None
    local, lan = f'http://localhost:{port}', f'http://{ip}:{port}' if ip else None
    if lan and ctx['mode'] == 'existing' and not health(lan, 2):  # it was already running, listening to this computer only
        lan = None
        ctx['phone_note'] = 'To open it from your phone, restart Mindbaton (it only listens on this computer now).'
    ctx['urls'] = local, lan
    first = acc['display_name'].split()[0]
    if failed:
        ui.page(8, f'Almost done, {first}.', 'Mindbaton works, but a few things need another try.')
    else:
        ui.page(8, f"You're all set, {first}.", 'Everything you tell your connected AIs now lands in one private memory.')
    not_set_up(ui, failed, 'run ./install.sh')
    if failed:
        ui.gap()
    if ctx['mode'] == 'manual':
        ui.head('Start it first')
        ui.link(START_HINT, '')
        ui.gap()
    if lan:
        ui.qr(lan, '')
    ui.head('Open Mindbaton')
    ui.link(local, '')
    if lan:
        ui.gap()
        ui.head('On your phone')
        if ui.interactive:
            ui.text('Scan the code, or open:', 'fg2')
        ui.link(lan, '')
        ui.text('Sign in, then Add to Home Screen.', 'fg3')
    if ctx.get('phone_note'):
        ui.gap()
        ui.row('info', ctx['phone_note'])
    ui.gap()
    ui.head('Next')
    works = [t for t in chosen if TOOLS[t][0] not in failed]
    ui.row('info', f'Tell {TOOLS[works[0]][0] if works else "an AI"} “remember I like tea”')
    ui.row('info', 'Browser extension: Settings → Devices')
    if lan:
        ui.row('info', 'Your other computers', f'curl -fsSLO {lan}/mindbaton.py && python3 mindbaton.py connect')
    ui.row('info', f'Health check: {CLI} doctor')
    ui.wait('finish')


REPO = 'https://github.com/DkshByte/mindbaton'


def step_where(ui):
    """The welcome's question. → 'here', 'link' (it runs elsewhere: connect this computer to it) or None (quit)."""
    ui.page(0, 'Where should your memory live?', 'On one computer that stays on. Your other devices link to it.')
    i = ui.choose([('On this computer', 'recommended', 'Sets Mindbaton up here: your account, your AI tools and a link for your phone.'),
                   ('On my server', '', 'A home server, NAS, Raspberry Pi or VPS. Shows what to run there, then links this computer.'),
                   ('Link to my Mindbaton', '', "It already runs on another computer: find it and connect this computer's AI tools.")])
    return server_page(ui) if i == 1 else ('here', None, 'link')[i]


def server_page(ui):
    """"On my server": the commands to run there, then what's next (fits an 80 × 24 terminal). → 'link' or None."""
    ui.page(0, 'Install Mindbaton on your server', 'On the server (after  ssh you@your-server), run:')
    ui.link(f'git clone {REPO}', '  ')
    ui.link('cd mindbaton && ./install.sh', '  ')
    ui.text('Or with Docker (Synology, Unraid, TrueNAS…), instead of ./install.sh:', 'fg3')
    ui.link('docker compose up -d', '  ')
    ui.link('docker compose exec mindbaton python3 server.py --setup-code', '  ')
    ui.gap()
    ui.head('Then link each computer that has AI tools')
    ui.text('This one: choose below. The others:', 'fg2')
    ui.link('curl -fsSLO http://<server address>:3004/mindbaton.py', '  ')
    ui.link('python3 mindbaton.py connect', '  ')
    ui.gap()
    return ('link', None)[ui.choose([("It's running: link this computer", 'recommended'), ('Quit for now', 'run ./install.sh again any time')])]


def cmd_install(o):
    ctx = {'server': None, 'mode': None, 'failed': [], 'urls': (None, None)}
    log('── install', 'from', HERE)
    ui = make_ui(INSTALL_STEPS, o, 'setup')
    where = 'here'
    try:
        if ui.interactive:
            ui.welcome('Mindbaton keeps one private memory for all your AIs, on a computer you own. This sets it up: your '
                       'account, your AI tools and a link for your phone. It takes about two minutes.', 'Start setup')
            where = step_where(ui)
        if where == 'here':
            step_check(ui, ctx, o)
            step_account(ui, ctx, o)
            step_keys(ui, ctx, o)
            chosen = step_tools(ui, o, 4)
            st = http('GET', ctx['base'] + '/status', cookie=ctx['cookie'])[1]
            local_admin = bool((st.get('server') or {}).get('local_sources')) and setting('MINDBATON_WATCH_CLAUDE', '1') != '0'
            ctx['failed'] += step_connect(ui, o, chosen, 5, ctx['base'], lambda t: mint_token(ctx, t), local_admin,
                                          lambda tid: http('DELETE', f"{ctx['base']}/api/tokens/{tid}", cookie=ctx['cookie']))
            step_memories(ui, o, [t for t in chosen if TOOLS[t][0] not in ctx['failed']], 6, ctx['base'], load_cfg().get('token'))
            step_start(ui, ctx, o)
            step_done(ui, ctx, chosen)
    finally:
        ui.close()
        if ctx.get('cookie'):  # the installer's own sign-in isn't left open for 30 days
            http('POST', ctx['base'] + '/api/auth/logout', {}, cookie=ctx['cookie'])
        if ctx.get('server') and ctx.get('mode') != 'existing':
            stop_server(ctx['server'])
    if where != 'here':
        log('install: linking instead' if where else 'install: quit at the start')
        return cmd_connect(o, welcome=False) if where == 'link' else print(f'\n  Run ./install.sh again any time.\n')
    local, lan = ctx['urls']
    print(f"\n  Mindbaton  {local}" + (f"\n  Phone      {lan}" if lan else '') +
          (f"\n  Start it   {START_HINT}" if ctx['mode'] == 'manual' else '') +
          (f"\n  Not done   {', '.join(ctx['failed'])}" if ctx['failed'] else '') +
          f"\n  Check      {CLI} doctor\n  Log        {tilde(LOG)}\n")
    if ctx.get('phone_note'):
        print(f"  {ctx['phone_note']}\n")
    if ctx['failed'] and ctx['mode'] != 'foreground':
        sys.exit(2)  # scripts can tell "done" from "done, but something needs another try"
    if ctx['mode'] == 'foreground':
        print('  Mindbaton is running in this window. Close it or press Ctrl-C to stop.\n', flush=True)
        log('exec server in the foreground')
        os.chdir(HERE)
        os.execv(sys.executable, [sys.executable, str(HERE / 'server.py')])


def mint_token(ctx, t):
    """The app's token: the one it already has when that still works for this account (so a re-run leaves its settings
    as they are, even in files with comments Mindbaton won't rewrite), else a new one."""
    cfg = load_cfg()
    old = (cfg.get('tools') or {}).get(t) or {}
    acc = old.get('token') and old.get('url') == ctx['base'] and token_ok(ctx['base'], old['token'])
    if acc and acc.get('username') == ctx['account'].get('username') and old.get('token_id'):
        return old['token_id'], old['token']
    return new_token(ctx['base'], ctx['cookie'], f'{TOOLS[t][0]} on {HOSTNAME}', 'mcp')


# ── Connect another computer ───────────────────────────────────────────────────────────────────────────────

def normalize(url):
    url = (url or '').strip().rstrip('/')
    if url and '://' not in url:
        url = 'http://' + url
    u = urlparse(url)
    if not u.hostname:
        raise Stop('Give the address of your Mindbaton, for example: python3 mindbaton.py connect http://192.168.1.20:3004')
    return f'{u.scheme}://{u.netloc}{u.path.rstrip("/")}'


NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # a look around the network never goes through a proxy


def probe(base):
    """One unauthenticated GET /health, straight to it: its answer if it is a Mindbaton, else None. Nothing else is sent."""
    u = urlparse(base)
    try:
        socket.create_connection((u.hostname, u.port or (443 if u.scheme == 'https' else 80)), 0.3).close()
        with NOPROXY.open(urllib.request.Request(base + '/health', headers={'User-Agent': 'mindbaton-cli/1.0'}), timeout=1.5) as r:
            d = json.loads(r.read(4096))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get('name') == 'mindbaton' else None


def sweep(ip):
    """The other addresses of this computer's /24, only when it is on a private network (a home or office LAN): never the
    internet, never Tailscale's range (its peers come from Tailscale itself)."""
    # ponytail: assumes a /24 (the stdlib can't read the netmask everywhere); covers home routers, type the address otherwise
    try:
        a = ipaddress.ip_address(ip or '')
    except ValueError:
        return []
    if a.version != 4 or not a.is_private or a.is_loopback or a.is_link_local:
        return []
    return [str(h) for h in ipaddress.ip_network(f'{ip}/24', strict=False).hosts() if str(h) != ip]


def discover(port, scan=True):
    """[(base URL, its /health)] of the Mindbatons nearby: the saved address, this computer, then (scan) Tailscale peers and
    the local network, one port each, 64 at a time, a few seconds in all."""
    from concurrent.futures import ThreadPoolExecutor
    urls = [load_cfg().get('url'), f'http://127.0.0.1:{port}']
    if scan:
        ts = run(['tailscale', 'status', '--json'], 4) if shutil.which('tailscale') else None
        try:
            peers = [x for x in (json.loads(ts.stdout).get('Peer') or {}).values() if x.get('Online')][:50] if ts and not ts.returncode else []
        except (ValueError, AttributeError):
            peers = []
        urls += [f"http://{(x.get('DNSName') or '').rstrip('.') or (x.get('TailscaleIPs') or [''])[0]}:{port}" for x in peers]
        urls += [f'http://{ip}:{port}' for ip in sweep(lan_ip())]
    urls = [u for u in dict.fromkeys(urls) if u and urlparse(u).hostname]
    with ThreadPoolExecutor(64) as ex:
        return [(u, h) for u, h in zip(urls, ex.map(probe, urls)) if h]


def check_address(v, _):
    try:
        url = normalize(v)
    except Stop:
        return 'Type an address like 192.168.1.20:3004 or https://mindbaton.example.com'
    return None if health(url, 4) else f"No Mindbaton answers at {urlparse(url).netloc}. Check the address, and that it's running."


def pick_server(ui, o):
    """Link, step one: find the Mindbatons nearby, or take a typed address. → the chosen one's base URL."""
    port = int(setting('MINDBATON_PORT', 3004))
    scan = not getattr(o, 'no_scan', False)
    while True:
        ui.page(1, 'Find your Mindbaton', f'Looking on this computer, on Tailscale and on your network: it asks nearby devices on port '
                                          f'{port} only "are you Mindbaton?", and sends nothing else.' if scan else '')
        found = ui.task('Looking for Mindbaton', lambda: discover(port, scan), lambda f: f'{len(f)} found' if f else 'none found')
        ui.gap()
        if found:
            ui.text('Pick yours. Only link to a Mindbaton you know: you will approve this computer from its app.', 'fg2')
        opts = [(urlparse(u).netloc, 'not set up yet' if h.get('setup_needed') else 'ready', f"Mindbaton {h.get('version', '')} at {u}")
                for u, h in found] + [('Type its address', ''), ('Look again', '')]
        i = ui.choose(opts)
        if i == len(found) + 1:
            continue
        if i < len(found):
            url, h = found[i]
        else:
            ui.clear()
            v = ui.form([field('Address', '', check=check_address, placeholder='e.g. 192.168.1.20:3004')], cancel=True, submit='use it')
            if not v:
                continue
            url = normalize(v['Address'])
            h = health(url) or {}
        while h.get('setup_needed'):  # nobody could approve the pairing yet
            ui.page(1, 'Create your account there first', f'This Mindbaton is new. Open it in a browser, create your account '
                                                          f'with the setup code from its log, then come back.')
            ui.link(url, '')
            ui.wait('check again')
            h = health(url) or {}
        return url


def cmd_connect(o, welcome=True):
    url = normalize(o.url) if getattr(o, 'url', None) else None
    log('── connect', url or '(find it)')
    global ART
    if not ART.exists():  # only the script on this computer: the server hands out the logo art too
        mine = MB / 'assets/brand/terminal-logo.json'
        try:
            if not mine.exists() and url:  # no address yet: the text logo until it is known
                req = urllib.request.Request(url + '/assets/brand/terminal-logo.json', headers={'User-Agent': 'mindbaton-cli/1.0'})
                with urllib.request.urlopen(req, timeout=4) as r:
                    write_file(mine, json.dumps(json.load(r)))
            ART = mine
        except (OSError, ValueError):
            pass
    ui = make_ui(CONNECT_STEPS, o, 'connect')
    failed = []
    try:
        if not url and not ui.interactive:
            raise Stop('Give the address of your Mindbaton, for example: python3 mindbaton.py connect http://192.168.1.20:3004 '
                       '(in a terminal, leave it out and Mindbaton is found for you).')
        if ui.interactive and welcome:
            ui.welcome(f'Connect the AI tools on this computer to your Mindbaton{" at " + urlparse(url).netloc if url else ""}. '
                       'You approve it once from the app, and each tool can then read and save memories.', 'Start')
        url = url or pick_server(ui, o)
        log('connect to', url)
        ui.page(1, 'Pair this computer', 'Approve it from Mindbaton on your phone or in any browser where you are signed in.')
        ui.task(f'Mindbaton found at {urlparse(url).netloc}', lambda: health(url, 6) or (_ for _ in ()).throw(RuntimeError(
            "no answer. Check the address, and that this computer is on the same network (or Tailscale)")))
        s, d, _ = http('POST', url + '/api/pair/start', {'name': f'{HOSTNAME} (AI tools)', 'kind': 'mcp'})
        if s != 200:
            raise Stop(err_text(d, f"Mindbaton didn't start pairing ({s})"))
        ui.clear()
        ui.qr(d['approve_url'], 'Or scan it')
        ui.text('Your code', 'fg2')
        ui.big(d['code'])
        ui.gap()
        ui.text('Open this link where you are signed in to Mindbaton, check the code, then Approve:', 'fg2')
        ui.link(d['approve_url'], '')
        ui.gap()

        def wait_pair():
            end = time.time() + d.get('expires_in', 600)
            while time.time() < end:
                s2, p, _ = http('GET', url + '/api/pair/poll?poll=' + d['poll'])
                if p.get('status') in ('approved', 'denied', 'expired'):
                    return p
                time.sleep(2)
            return {'status': 'expired'}
        p = ui.task('Waiting for you to approve', wait_pair, lambda p: p['status'])
        if p['status'] != 'approved':
            raise Stop('The request was denied.' if p['status'] == 'denied' else 'The code expired. Run this again for a new one.')
        st = http('GET', url + '/api/auth/state', token=p['token'])[1]
        acc = st.get('account') or {}
        ui.who = acc.get('display_name', '')
        cfg = load_cfg()
        cfg.update(url=url, token=p['token'], token_id=p['id'], account=acc.get('username'), tools=cfg.get('tools') or {})
        cfg.pop('server_dir', None)
        save_cfg(cfg)
        ui.clear()
        ui.row('ok', 'Approved', f"this computer now saves to {acc.get('display_name', 'your')}'s memory")
        ui.pause(1)
        chosen = step_tools(ui, o, 2)
        failed = step_connect(ui, o, chosen, 3, url, lambda t: (p['id'], p['token']))
        step_memories(ui, o, [t for t in chosen if TOOLS[t][0] not in failed], 4, url, p['token'])
        works = [TOOLS[t][0] for t in chosen if TOOLS[t][0] not in failed]
        ui.page(5, 'Almost connected' if failed else 'This computer is connected',
                f'Its AI tools now share the memory at {urlparse(url).netloc}.' if works else '')
        if works:
            ui.row('ok', ', '.join(works))
        not_set_up(ui, failed, f'run {CLI} connect {url}')
        ui.row('info', 'Your other computers', f'curl -fsSLO {url}/mindbaton.py && python3 mindbaton.py connect')
        ui.gap()
        ui.row('info', f'Check on it any time: {CLI} doctor')
        ui.wait('finish')
    finally:
        ui.close()
    if failed:
        sys.exit(2)


# ── Your AI tools' own memories ────────────────────────────────────────────────────────────────────────────
# What each tool keeps about you on disk (researched Sep 2026): notes, saved facts and your own instruction files, at user
# level only. Never chats, transcripts, credentials or settings files. Cursor's memories went away in 2.1 and its database
# holds your login, so it is never read (the app's "Import your old memory" takes its pasted User Rules instead).

MEMORY_FILES = {
    'claude': lambda: [(claude_dir(), 'CLAUDE.md'), (claude_dir(), 'rules/*.md'), (claude_dir(), 'projects/*/memory/*.md')],
    'codex': lambda: [(codex_toml().parent, n) for n in ('AGENTS.md', 'memories/memory_summary.md', 'memories/MEMORY.md')],
    'gemini': lambda: [(_home() / '.gemini', 'GEMINI.md')],  # what save_memory writes, plus your own instructions
    'antigravity': lambda: [(_home() / '.gemini', 'GEMINI.md')],  # the same file: read once
    'windsurf': lambda: [(_home() / '.codeium/windsurf/memories', '*')],
    'vscode': lambda: [(copilot_home(), 'copilot-instructions.md')],
    'cline': lambda: [(_home() / 'Documents/Cline/Rules', '*.md'), (_home() / '.cline/rules', '*.md')],
    # OpenCode falls back to ~/.claude/CLAUDE.md when it has no AGENTS.md; read once if Claude Code is picked too
    'opencode': lambda: [(_xdg() / 'opencode', 'AGENTS.md')] + ([] if (_xdg() / 'opencode/AGENTS.md').exists() else [(claude_dir(), 'CLAUDE.md')]),
}
SECRET_LINE = re.compile(r'\b(mb_|gsk_|AIza|sk-|gh[pousr]_|xox[abprs]-|AKIA)[\w\-]{6,}|Bearer\s+\S|-----BEGIN|'
                         r'\b(password|passwd|passphrase|secret|api[ _-]?key|token|pin)s?\b\s*[:=]', re.I)


def memory_files(tools):
    """{tool: [(path, text, mtime)]}, read with care: regular files inside the tool's own folder (a symlink out of it is
    skipped), UTF-8 text only, at most 256 KB each and 2 MB per tool. Lines that look like a password or key are dropped
    here, before anything leaves this computer (the server redacts again)."""
    out, seen = {}, set()
    for t in tools:
        files, total = [], 0
        for root, pattern in MEMORY_FILES.get(t, lambda: [])():
            top = os.path.realpath(root)
            for p in sorted(Path(root).glob(pattern)):
                real = os.path.realpath(p)
                if real in seen or not real.startswith(top + os.sep) or not os.path.isfile(real) or \
                        (t == 'claude' and p.name == 'MEMORY.md'):  # Claude Code's index of its other notes
                    continue
                try:
                    size = os.path.getsize(real)
                    text = Path(real).read_bytes().decode('utf-8') if size <= 256_000 and total + size <= 2_000_000 else ''
                except (OSError, UnicodeDecodeError):
                    text = ''
                if re.search(r'[\x00-\x08\x0e-\x1f]', text):  # binary (older Windsurf builds wrote protobuf)
                    continue
                seen.add(real)
                total += size
                text = '\n'.join(line for line in text.splitlines() if not SECRET_LINE.search(line)).strip()
                if text:
                    files.append((p, text, os.path.getmtime(real)))
        if files:
            out[t] = files
    return out


def about(text):
    """About how many memories a file makes (the server's rule: one per bullet or paragraph, headings skipped)."""
    body = re.sub(r'\A---\n.*?\n---\n', '', text, flags=re.S)
    return sum(1 for x in re.split(r'\n\s*\n|\n(?=\s*(?:[-*]|\d+\.)\s)', body) if len(x.strip()) >= 12 and not x.lstrip().startswith('#'))


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def fingerprint(text):
    return hashlib.sha1(text.encode()).hexdigest()


def send_memories(url, token, found):
    """Each file to the server's /import (it makes the statements, redacts and skips what it has). → {tool: [imported, skipped]}"""
    cfg, out = load_cfg(), {}
    for t, files in found.items():
        for p, text, mtime in files:
            s, d, _ = http('POST', url + '/import', {'source': SITE[t], 'kind': 'note', 'name': p.name if p.stem.isupper() else p.stem,
                                                     'text': text, 'ts': mtime, 'file': tilde(p)}, token=token, timeout=180)
            if s == 404:
                raise RuntimeError('this Mindbaton is too old to import memories: update it first (mindbaton.py update, on its computer)')
            if s != 200:
                raise RuntimeError(err_text(d, f"Mindbaton didn't take {tilde(p)} ({s or 'no answer'})"))
            n = out.setdefault(t, [0, 0])
            n[0], n[1] = n[0] + d['imported'], n[1] + d['skipped']
            cfg.setdefault('imported', {}).setdefault(url, {})[str(p)] = fingerprint(text)
            save_cfg(cfg)  # after each file: an interrupted import picks up where it stopped
    return out


def show_memories(ui, found, step):
    """"Show me first": exactly what would leave this computer, file by file."""
    ui.page(step, 'What would be copied', 'Exactly this is sent to your Mindbaton, which turns it into memories.')
    for t, files in found.items():
        for p, text, _ in files:
            ui.head(f'{TOOLS[t][0]} · {tilde(p)}')
            for line in text.splitlines():
                if line.strip():
                    ui.text(line, 'fg2')
            ui.gap()
    ui.wait('go back')


def step_memories(ui, o, tools, step, url, token, asked=False):
    """"Your old memories": what the tools just connected already remember, copied into Mindbaton only if the person says
    so. Nothing is sent before that. The default is Not now; unattended it needs --import-memories (asked: `import` was run
    on purpose). Files imported before, unchanged, aren't offered again."""
    done = (load_cfg().get('imported') or {}).get(url) or {}
    found = {t: [f for f in files if done.get(str(f[0])) != fingerprint(f[1])] for t, files in memory_files(tools).items()}
    found = {t: files for t, files in found.items() if files}
    if not found:
        if asked:
            ui.page(step, 'Your old memories')
            ui.row('ok', 'Nothing new to import', 'your AI tools keep no memory files here, or they are in Mindbaton already')
            ui.wait('close')
        return
    if not url or not token:
        return ui.row('warn', "Your AI tools' memories weren't imported", f'this computer has no Mindbaton token: {CLI} doctor')
    dry = getattr(o, 'dry_run', False)
    while True:
        ui.page(step, 'Your old memories', 'Your AI tools already remember things about you. Copy them into Mindbaton, so '
                                           'every AI knows them?')
        for t, files in found.items():
            roots = sorted({tilde(p.parent) for p, _, _ in files})
            ui.row('info', TOOLS[t][0], f"about {plural(sum(about(x) for _, x, _ in files), 'fact')} in {plural(len(files), 'file')}"
                                        f" · {', '.join(roots[:2])}{' …' if len(roots) > 2 else ''}")
        ui.gap()
        ui.text('Only their notes, saved facts and your instruction files are read: never your chats, keys or settings. '
                'Lines that look like a password or key are left out.', 'fg3')
        if dry:
            return show_memories(ui, found, step)
        ui.gap()
        if ui.interactive:
            i = ui.choose([('Import them', 'into your Mindbaton'), ('Show me first', 'nothing is sent'),
                           ('Not now', f'later: {CLI} import')], default=2)
        else:
            i = 0 if asked or getattr(o, 'import_memories', False) else 2
        if i != 1:
            break
        show_memories(ui, found, step)
    ui.clear()
    if i == 2:
        ui.row('info', 'Not imported', f'any time: {CLI} import')
        return ui.pause(1) if ui.interactive else None
    try:
        got = ui.task('Copying them into Mindbaton', lambda: send_memories(url, token, found),
                      lambda r: f"{plural(sum(n[0] for n in r.values()), 'new fact')}")
    except Exception as e:  # never blocks setup: the row already says why
        log('import failed:', repr(e))
        return ui.wait()
    ui.retitle('Your old memories', 'Copied. Every AI connected to Mindbaton can use them now.')
    for t, (n, skipped) in got.items():
        ui.row('ok', TOOLS[t][0], f"{plural(n, 'fact')} imported" + (f' · {skipped} it already had' if skipped else ''))
    ui.wait('close' if asked else 'continue')


def cmd_import(o):
    """`mindbaton.py import`: the same offer, any time, for the tools on this computer (--tools to pick)."""
    cfg = load_cfg()
    if not cfg.get('url') or not cfg.get('token'):
        raise Stop("This computer isn't linked to a Mindbaton yet: run ./install.sh here, or python3 mindbaton.py connect.")
    tools = [t.strip() for t in o.tools.split(',')] if o.tools else [t for t in MEMORY_FILES if detect(t)]
    for t in tools:
        if t not in MEMORY_FILES:
            raise Stop(f"--tools: {t!r} keeps no memory files Mindbaton reads. These do: {', '.join(MEMORY_FILES)}.")
    ui = make_ui(None, o, 'import')
    try:
        if not ui.interactive and not (o.yes or o.dry_run):
            raise Stop('This copies your AI tools\' memories into Mindbaton. Run it in a terminal to be asked, or pass --yes '
                       '(or --dry-run to see what would be sent).')
        step_memories(ui, o, tools, None, cfg['url'], cfg['token'], asked=True)
    finally:
        ui.close()


# ── Doctor ─────────────────────────────────────────────────────────────────────────────────────────────────

def token_ok(url, token):
    s, d, _ = http('GET', url + '/api/auth/state', token=token, timeout=5)
    return d.get('account') if s == 200 and d.get('authed') else None


def cmd_doctor(o):
    ui = make_ui(None, o, 'doctor')
    try:
        doctor(ui, o)
    finally:
        ui.close()


def doctor(ui, o):
    while True:
        cfg = load_cfg()
        ui.page(None, 'Checking Mindbaton', 'The server, this computer\'s token and every connected tool.')
        if not cfg.get('url'):
            ui.row('fail', "This computer isn't set up yet",
                   'run ./install.sh on the Mindbaton computer, or python3 mindbaton.py connect <address> here')
            return ui.wait('close')
        url, fixes = cfg['url'], []
        local = bool(cfg.get('server_dir'))
        kind = service_kind() if local else None
        h = health(url)
        ui.row('ok' if h else 'fail', f'Mindbaton at {url}', f"version {h.get('version')}" if h else 'not answering')
        if not h and kind:
            fixes.append(('Start the service', lambda: (restart_service(kind), wait_health(url, 30) or (_ for _ in ()).throw(
                RuntimeError('it still does not answer')))))
        if local and kind:
            active = service_active(kind)
            ui.row('ok' if active else 'warn', 'Background service', 'running' if active else 'not running')
        acc = token_ok(url, cfg.get('token')) if h else None
        if h:
            ui.row('ok' if acc else 'fail', 'This computer\'s token', f"{acc['display_name']} (@{acc['username']})" if acc else
                   'not accepted any more: run install (or connect) again')
        for t, state in (cfg.get('tools') or {}).items():
            if t not in TOOLS:
                continue
            probs = []
            conf = mcp_entry(t)
            if not conf and not (t == 'claude' and shutil.which('claude')):
                probs.append('Mindbaton is missing from its settings')
            elif conf and state.get('token') and state['token'] not in conf:
                probs.append('its settings hold an old token')
            if t == 'claude' and shutil.which('claude'):
                out = run(['claude', 'mcp', 'get', 'mindbaton'], 30).stdout
                if 'Connected' not in out:
                    probs.append('Claude Code says: ' + ('not connected' if 'mindbaton' in out else 'not configured'))
            if state.get('capture') and not hook_present(t):
                probs.append('the capture hook is missing')
            if h and state.get('token') and not token_ok(url, state['token']):
                probs.append('its token was revoked')
            ui.row('fail' if probs else 'ok', TOOLS[t][0], '; '.join(probs) if probs else 'memory tools' + (' + capture' if state.get('capture') else ''))
            if probs and h:
                tok = state['token'] if token_ok(url, state.get('token')) else cfg.get('token') if acc else None
                if tok:
                    fixes.append((f'Reconnect {TOOLS[t][0]}', lambda t=t, tok=tok, state=state: (
                        cfg['tools'].__setitem__(t, {**connect_tool(t, url, tok, state.get('capture', True), state)[2],
                                                     'token_id': state.get('token_id')}), save_cfg(cfg))))
        try:
            waiting = len(json.loads(QUEUE.read_text()))
        except (OSError, ValueError):
            waiting = 0
        ui.row('warn' if waiting else 'ok', 'Messages waiting to be sent', str(waiting) if waiting else 'none')
        if waiting and h:
            fixes.append(('Send the waiting messages', lambda: deliver(cfg, None, None, lambda: 20)))
        ui.gap()
        if not fixes:
            ui.text('Everything works.' if h and acc else 'Nothing here can be fixed automatically.', 'ok' if h and acc else 'fg2')
            if not (h and acc) and not ui.interactive:
                raise Stop('Mindbaton needs attention (see above).')
            return ui.wait('close')
        if not ui.interactive and not o.fix:
            ui.text(f'{len(fixes)} problem(s) can be fixed: run {CLI} doctor --fix')
            raise Stop('Mindbaton needs attention (see above).')
        if ui.interactive and ui.choose([(f'Fix {"it" if len(fixes) == 1 else f"these {len(fixes)}"}', 'recommended',
                                          ' · '.join(f[0] for f in fixes)), ('Close', '')]) != 0:
            return
        ui.clear()
        for label, fix in fixes:
            try:
                ui.task(label, fix)
            except Exception as e:
                log('fix failed:', label, repr(e))
        ui.pause(1)
        if not ui.interactive:
            o.fix = False


# ── Update, keys, models, uninstall ────────────────────────────────────────────────────────────────────────

def cmd_update(o):
    home = Path(load_cfg().get('server_dir') or HERE)
    if not (HERE / 'server.py').exists() and (home / 'server.py').exists():  # the copy in ~/.mindbaton: update the install
        os.execv(sys.executable, [sys.executable, str(home / 'mindbaton.py'), *sys.argv[1:]])
    ui = make_ui(None, o, 'update')
    try:
        ui.page(None, 'Updating Mindbaton', tilde(HERE))
        if not (HERE / 'server.py').exists():  # a computer set up with connect: only this script lives here
            ui.row('info', 'This computer only has the connector')
            ui.text('Get the latest mindbaton.py from https://github.com/DkshByte/mindbaton, then run: python3 mindbaton.py '
                    f"connect {load_cfg().get('url') or '<address>'}. Your settings and memories stay.")
            return ui.wait('close')
        if not (HERE / '.git').exists():
            ui.row('info', "This copy wasn't installed with git")
            ui.text('Download the latest release from https://github.com/DkshByte/mindbaton, put it in place of this folder '
                    '(keep the data folder and mindbaton.env), then run ./install.sh again. Your memories stay.')
            return ui.wait('close')
        old = run(['git', '-C', HERE, 'rev-parse', 'HEAD']).stdout.strip()
        def pull():
            r = run(['git', '-C', HERE, 'pull', '--ff-only'], 120)
            if r.returncode:
                why = next((l for l in (r.stderr + r.stdout).splitlines() if l.startswith(('error:', 'fatal:'))), 'git pull failed')
                why = why.split(':', 1)[1].strip().rstrip(':.')
                raise Stop(f"git couldn't update this folder: {why[:1].lower() + why[1:]}. Nothing was changed; "
                           f'see: git -C {shlex.quote(str(HERE))} status')
            return r.stdout
        ui.task('Latest version downloaded', pull, lambda out: 'already up to date' if 'Already up to date' in (out or '') else '')
        new = run(['git', '-C', HERE, 'rev-parse', 'HEAD']).stdout.strip()
        ui.task('Self-test', self_test, lambda _: 'all good')
        if CFG.exists():
            ui.task('Capture script updated', install_client)
        kind = service_kind()
        if old != new:
            if kind and service_active(kind):
                ui.task('Mindbaton restarted', lambda: (restart_service(kind), wait_health(load_cfg().get('url') or
                        f"http://127.0.0.1:{setting('MINDBATON_PORT', 3004)}", 30)))
            elif port_busy(int(setting('MINDBATON_PORT', 3004))):
                ui.row('info', 'Restart Mindbaton to use the new version')
            changes = run(['git', '-C', HERE, 'log', '--no-merges', '--format=%s', f'{old}..{new}']).stdout.splitlines()
            ui.gap()
            ui.text(f'What changed ({len(changes)})', None)
            for c in changes[:12]:
                ui.row('info', c)
            if len(changes) > 12:
                ui.row('info', f'…and {len(changes) - 12} more', 'git log for all of it')
        ui.wait('close')
    finally:
        ui.close()


def admin_cred(ui, cfg):
    """How this computer can talk to its server as an admin: this computer's token, else a sign-in."""
    url = cfg.get('url') or f"http://127.0.0.1:{setting('MINDBATON_PORT', 3004)}"
    acc = token_ok(url, cfg.get('token')) if cfg.get('token') else None
    if acc and acc.get('role') == 'admin':
        return url, {'token': cfg['token']}
    if not ui.interactive:
        raise Stop('Only an admin can change the AI keys, and this computer has no admin token. Run this in a terminal to sign in.')
    ui.page(None, 'Sign in as an admin', 'Only an admin can change the AI keys.')
    fields = [field('Username', '', check=check_user), field('Password', '', True, check_pw)]
    while True:
        v = ui.form(fields, cancel=True, submit='sign in')
        if v is None:
            raise Stop('Nothing changed.')
        s, d, cookie = ui.busy('Signing in', lambda: http('POST', url + '/api/auth/login', {'username': v['Username'].lower(), 'password': v['Password']}))
        if s == 200 and d['account']['role'] == 'admin':
            return url, {'cookie': cookie}
        if s == 200:
            http('POST', url + '/api/auth/logout', {}, cookie=cookie)
            fields[1]['error'] = 'That account is not an admin.'
        else:
            login_failed(fields[1], s, d, f"Forgot it? Run: python3 {tilde(HERE / 'server.py')} --reset-password "
                                          f"{v['Username'].lower()}" if (HERE / 'server.py').exists() else None)


def cmd_keys(o):
    ui = make_ui(None, o, 'AI keys')
    try:
        url, cred = admin_cred(ui, load_cfg())
        if 'cookie' in cred:  # a sign-in just for this: ended when it's done
            atexit.register(http, 'POST', url + '/api/auth/logout', {}, cookie=cred['cookie'])
        if not health(url):
            raise Stop(f'Mindbaton at {url} is not answering. Start it first ({CLI} doctor).')
        local = urlparse(url).hostname in ('127.0.0.1', 'localhost') and (HERE / 'server.py').exists()
        if ui.interactive:
            return keys_screen(ui, url, cred, None, local_remove=local)
        ui.page(None, 'Free AI keys')
        for p in KEY_SITES:
            if getattr(o, p + '_key', None):
                add_key(ui, url, cred, p, getattr(o, p + '_key'))
        for p in o.remove or []:
            if not local:
                raise Stop('Keys can only be removed on the Mindbaton computer itself.')
            remove_local_key(p)
            ui.row('ok', f'{KEY_SITES[p][0]} key removed')
    finally:
        ui.close()


def cmd_models(o):
    ui = make_ui(None, o, 'models')
    try:
        ui.page(None, 'Free AI models', 'Which model writes your summaries. Automatic picks a good free one for you.')
        keys = local_keys()
        have = [p for p in KEY_SITES if os.environ.get(KEY_SITES[p][3]) or keys.get(KEY_SITES[p][3])]
        if not (HERE / 'server.py').exists():
            raise Stop('Run this on the Mindbaton computer (where server.py is).')
        if not have:
            raise Stop(f'Add a free key first: {CLI} keys')
        changed = False
        for p in have:
            name, var = KEY_SITES[p][0], f'MINDBATON_{p.upper()}_MODEL'
            models = ui.task(f'{name} models listed', lambda: list_models(p, os.environ.get(KEY_SITES[p][3]) or keys[KEY_SITES[p][3]]),
                             lambda m: f'{len(m)} free text models')
            cur = setting(var)
            want = getattr(o, p + '_model', None)
            if ui.interactive:
                ui.gap()
                ui.text(f'{name}: which model?', None)
                opts = [('Automatic', 'current' if not cur else '', 'Mindbaton picks, and follows along when models retire.')]
                opts += [(m, 'current' if m == cur else '') for m in models[:12]]
                i = ui.choose(opts, default=next((k for k, x in enumerate(opts) if x[1] == 'current'), 0))
                want = None if i == 0 else opts[i][0]
                ui.clear()
            elif want is None:
                for m in models[:12]:
                    ui.row('info', m, 'current' if m == cur else '')
                continue
            elif want == 'auto':
                want = None
            elif want not in models:
                raise Stop(f'{want} is not one of the free {name} models listed above.')
            if want != cur:
                set_env(**{var: want})
                changed = True
            ui.row('ok', name, want or 'automatic')
        kind = service_kind()
        if changed and kind and service_active(kind):
            ui.task('Mindbaton restarted', lambda: restart_service(kind))
        elif changed:
            ui.row('info', 'Restart Mindbaton to use it')
        ui.wait('close')
    finally:
        ui.close()


def cmd_uninstall(o):
    ui = make_ui(None, o, 'uninstall')
    try:
        cfg = load_cfg()
        ui.page(None, 'Remove Mindbaton from this computer', 'This removes what it added to your AI tools and stops it. '
                'Your memories stay unless you choose to delete them.')
        tools = cfg.get('tools') or {}
        local = (HERE / 'server.py').exists() and cfg.get('server_dir', str(HERE)) == str(HERE)
        kind = service_kind() if local else None
        for t in tools:
            ui.row('info', f'Remove Mindbaton from {TOOLS.get(t, (t,))[0]}')
        if kind and (UNIT.exists() or PLIST.exists()):
            ui.row('info', 'Stop and remove the background service')
        ui.row('info', f'Delete {tilde(MB)} (this computer\'s tokens and the capture script)')
        data = data_dir() if local else None
        if data and o.purge:
            ui.row('warn', f'Delete your memories in {tilde(data)}', 'every account, for good')
        ui.gap()
        if ui.interactive:
            if ui.choose([('Remove', 'the items above'), ('Cancel', 'keep everything')], default=1) != 0:
                raise Stop('Nothing changed.')
        elif not o.yes:
            raise Stop('Pass --yes to remove Mindbaton without a terminal.')
        if data and o.purge and ui.interactive:
            f = field('Type delete', '', check=lambda v, _: None if v == 'delete' else 'Type the word delete to confirm.')
            if ui.form([f], cancel=True, submit='delete my memories') is None:
                raise Stop('Nothing changed.')
        ui.clear()
        for t, state in tools.items():
            if t in TOOLS:
                try:
                    ui.task(f'Removed from {TOOLS[t][0]}', lambda t=t, state=state: disconnect_tool(t, state))
                except Exception as e:
                    log('uninstall', t, repr(e))
        if kind and (UNIT.exists() or PLIST.exists()):
            ui.task('Background service removed', lambda: remove_service(kind))
        if data and o.purge:
            if not ((data / 'auth.db').exists() or (data / 'accounts').is_dir() or (data / 'mindbaton.db').exists()):
                ui.row('warn', f'{tilde(data)} does not look like Mindbaton data, so it was kept')
            else:
                ui.task('Memories deleted', lambda: shutil.rmtree(data))
        # A hook left in an app (a settings file Mindbaton wouldn't rewrite) still runs mindbaton.py: without the script it
        # would exit 2, which Cursor, Gemini and Windsurf read as "block this prompt". So the script stays until it's gone.
        left = [t for t in TOOLS if hook_present(t)]
        for t in left:
            ui.row('warn', f'Remove the Mindbaton hook from {TOOLS[t][0]} by hand',
                   f'the lines with "mindbaton.py hook" in {tilde(codex_toml() if t == "codex" else HOOKS[t][0]())}')
        for p in ('config.json', 'queue.json', '.queue.lock', 'mcp_stdio.py', 'server.log') + (() if left else ('mindbaton.py',)):
            (MB / p).unlink(missing_ok=True)
        for p in ('chats', 'assets'):
            shutil.rmtree(MB / p, ignore_errors=True)
        for p in MB.glob('*-snippet.json'):
            p.unlink()
        ui.row('ok', f'{tilde(MB)} cleaned', 'the log stays: ' + tilde(LOG))
        ui.gap()
        ui.text('The backups of your AI tools\' settings are still next to each file (*.bak-mindbaton-*). '
                'To revoke this computer\'s tokens, open the app → Settings → Devices.', 'fg3')
        if data and not o.purge:
            ui.text(f'Your memories are still in {tilde(data)}. To delete them too: '
                    f"python3 {tilde(HERE / 'mindbaton.py')} uninstall --purge", 'fg3')
        ui.wait('close')
    finally:
        ui.close()


# ── Self-check (python3 mindbaton.py --check) ──────────────────────────────────────────────────────────────

def selfcheck():
    """Logo, QR, settings merges and their exact removal, hook parsing and the offline queue, all in a temp HOME."""
    import tempfile
    global MB, CFG, LOG, QUEUE
    logo_check()
    g = qr_matrix('x')
    assert len(g) == 21 and g[0][:7] == [True] * 7 and g[1][1:6] == [False] * 5 and len(qr_matrix('x' * 100)) == 37
    assert qr_lines('http://192.168.1.23:3004')[1] == 29 and all(len(l) == 29 for l in qr_lines('http://192.168.1.23:3004')[0])
    assert parse_keys('\x1b[Aa\r\x1b[200~k e y\x1b[201~\x03') == ['up', ('text', 'a'), 'enter', ('paste', 'k e y'), 'ctrl-c']
    assert fit('\x1b[1mhello world\x1b[0m', 6) == '\x1b[1mhello…\x1b[0m' and vlen('日本') == 4
    gm = lambda *ids: [{'name': 'models/' + i, 'supportedGenerationMethods': ['generateContent']} for i in ids]
    assert pick_gemini(gm('gemini-3.7-flash', 'gemini-3-flash-preview', 'gemini-3.8-flash', 'gemini-3.8-flash-tts',
                          'gemini-3.5-flash-lite', 'gemini-3.1-flash-lite-image', 'gemini-flash-latest')) == \
        ['gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.5-flash-lite']
    assert pick_groq([{'id': 'qwen/qwen3.8-27b'}, {'id': 'openai/gpt-oss-20b'}, {'id': 'openai/gpt-oss-120b'},
                      {'id': 'whisper-large-v3'}, {'id': 'openai/gpt-oss-safeguard-20b'}, {'id': 'old', 'active': False}]) == \
        ['openai/gpt-oss-120b', 'openai/gpt-oss-20b', 'qwen/qwen3.8-27b']

    home = Path(tempfile.mkdtemp(prefix='mindbaton-check-'))
    saved = {k: os.environ.get(k) for k in ('HOME', 'PATH', 'XDG_CONFIG_HOME', 'CODEX_HOME', 'CLAUDE_CONFIG_DIR', 'COPILOT_HOME', 'CLINE_DATA_DIR',
                                            'http_proxy')}
    old_globals = MB, CFG, LOG, QUEUE
    try:
        for k in saved:
            os.environ.pop(k, None)
        os.environ.update(HOME=str(home), PATH=str(home / 'no-bin'))  # no `claude` here: its JSON path is tested
        MB = home / '.mindbaton'
        CFG, LOG, QUEUE = MB / 'config.json', MB / 'install.log', MB / 'queue.json'
        mine = {'command': 'my-own-hook'}
        seed = {
            home / '.claude.json': {'mcpServers': {'memgraph': {'type': 'http', 'url': 'http://10.0.0.2:3004/mcp'}}, 'theme': 'dark'},
            home / '.claude/settings.json': {'model': 'opus', 'hooks': {'UserPromptSubmit': [{'hooks': [{'type': 'command', 'command': 'mine.sh'}]}]}},
            home / '.cursor/mcp.json': {'mcpServers': {'other': {'url': 'https://x.example/mcp'}}},
            home / '.cursor/hooks.json': {'version': 1, 'hooks': {'preToolUse': [mine]}},
            home / '.gemini/settings.json': {'theme': 'x'},
            home / '.gemini/config/mcp_config.json': {'mcpServers': {'remote-mcp': {'serverUrl': 'http://localhost:3004/mcp'},
                                                                     'elsewhere': {'serverUrl': 'http://10.0.0.2:3004/mcp'}}},
            home / '.codeium/windsurf/hooks.json': {},
            home / '.config/opencode/opencode.json': {'$schema': 'https://opencode.ai/config.json', 'theme': 'x'},
        }
        for path, d in seed.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(d))
        for d in ('.gemini/antigravity-cli', '.config/Code/User', '.config/Claude', '.cline', '.continue', '.codex'):
            (home / d).mkdir(parents=True, exist_ok=True)
        zed = home / '.config/zed/settings.json'
        zed.parent.mkdir(parents=True)
        zed.write_text('// Zed settings {\n{\n  "theme": "One Dark", // keep me\n}\n')
        toml = home / '.codex/config.toml'
        toml.write_text('model = "gpt-5.5"\nnotify = ["say", "done"]\n\n[mcp_servers.memgraph]\nurl = "http://10.0.0.2:3004/mcp"\n')
        before = {p: p.read_text() for p in list(seed) + [zed, toml]}

        url, tok = 'http://127.0.0.1:3004', 'mb_' + 'x' * 43
        assert all(detect(t) for t in TOOLS if t != 'windsurf' or True), [t for t in TOOLS if not detect(t)]
        # by name (another host: not the same server), or by host and port (loopback in any spelling); never by port alone
        assert [x[:3] for x in legacy('claude', url)] == [('memgraph', 'http://10.0.0.2:3004/mcp', False)]
        assert [x[:3] for x in legacy('antigravity', url)] == [('remote-mcp', 'http://localhost:3004/mcp', True)]
        assert [x[0] for x in legacy('codex', url)] == ['memgraph'] and legacy('cursor', url) == []
        assert legacy('cursor', 'https://mindbaton.example.com') == []  # no port on either side is not a match
        states = {}
        for t in TOOLS:
            what, note, states[t] = connect_tool(t, url, tok, TOOLS[t][4], None)
            assert ('saves every message' in what) == TOOLS[t][4], (t, what)
            assert tok in mcp_entry(t) and (not TOOLS[t][4] or hook_present(t)), t
        assert json.loads((home / '.claude.json').read_text())['theme'] == 'dark'
        assert os.stat(home / '.cursor/mcp.json').st_mode & 0o777 == 0o600 and os.stat(toml).st_mode & 0o777 == 0o600
        cs = json.loads((home / '.claude/settings.json').read_text())
        assert cs['model'] == 'opus' and len(cs['hooks']['UserPromptSubmit']) == 2 and cs['hooks']['Stop'][0]['hooks'][0]['async']
        oc = json.loads((home / '.config/opencode/opencode.json').read_text())
        assert oc['theme'] == 'x' and oc['mcp']['mindbaton'] == {'type': 'remote', 'url': url + '/mcp', 'headers': {'Authorization': 'Bearer ' + tok}, 'enabled': True}, oc
        assert '// keep me' in zed.read_text() and jsonc(zed.read_text())['context_servers']['mindbaton']['url'] == url + '/mcp'
        t2 = toml.read_text()
        assert t2.startswith('notify = [') and 'hook", "codex"]' in t2 and states['codex']['notify_prev'] == ['say', 'done']
        assert 'Bearer ' + tok in t2 and '[mcp_servers.memgraph]' in t2 and toml_ok(t2)
        connect_tool('codex', url, tok, True, states['codex'])  # a second run changes nothing and keeps the chain
        assert toml.read_text() == t2
        edit_json(home / '.cursor/hooks.json', lambda d: d['hooks']['beforeSubmitPrompt'].append({'command': 'theirs'}), private=False)
        for t in TOOLS:
            disconnect_tool(t, states[t])
        after = json.loads((home / '.cursor/hooks.json').read_text())
        assert after['hooks'] == {'preToolUse': [mine], 'beforeSubmitPrompt': [{'command': 'theirs'}]}, after
        for p, text in before.items():
            if p.name == 'hooks.json' and 'cursor' in str(p):
                continue
            now = p.read_text() if p.exists() else ''
            if p.suffix == '.toml':
                assert toml_ok(now) and set(re.findall(r'^\S.*$', now, re.M)) == set(re.findall(r'^\S.*$', text, re.M)), now
            else:
                assert now == text or read_json(p) == (jsonc(text) if text.strip() else {}), (p, now)
        assert zed.read_text() == before[zed]  # comments and all
        assert not (home / '.continue/mcpServers/mindbaton.json').exists() and not (home / '.copilot/hooks/mindbaton.json').exists()
        assert list(home.glob('.cursor/mcp.json.bak-mindbaton-*'))
        try:
            edit_json(zed, lambda d: d.__setitem__('theme', 'Light'))
            raise AssertionError('rewrote a file with comments')
        except Unsafe:
            pass
        assert unhook({'a': [{'hooks': [{'command': 'x mindbaton.py hook y'}]}], 'b': 1}) == {'b': 1}
        assert unhook({'a': [{'command': "py '/x y/.mindbaton/mindbaton.py' hook cursor"}], 'b': 1}) == {'b': 1}  # quoted path
        zed.write_text('// mine\n{"context_servers": {"other": {"url": "http://x/mcp"}}}\n')  # comments + a key we'd change
        what, note, _ = connect_tool('zed', url, tok, False, None)
        assert 'snippet' in what and 'zed-snippet.json' in note and '"other"' in zed.read_text(), (what, note)
        real = home / 'dotfiles/cursor-mcp.json'
        real.parent.mkdir()
        real.write_text('{}')
        (home / '.cursor/mcp.json').unlink()
        (home / '.cursor/mcp.json').symlink_to(real)
        connect_tool('cursor', url, tok, False, None)
        assert (home / '.cursor/mcp.json').is_symlink() and tok in real.read_text()  # written through the link
        e = PermissionError(13, 'Permission denied', str(home / '.cursor/mcp.json.bak-mindbaton-20260924-101010'))
        assert friendly(e) == "Mindbaton can't write ~/.cursor/mcp.json (no permission). Fix that folder's permissions, then run this again."
        assert all(callable(getattr(Plain, m, None)) for m in ('page', 'retitle', 'row', 'text', 'gap', 'qr', 'big', 'head', 'link',
                                                               'clear', 'task', 'busy', 'pause', 'wait', 'choose', 'checklist', 'form'))

        # the tools' own memories: only the researched files, never out through a symlink, never binary, secrets dropped
        (home / '.claude/CLAUDE.md').write_text('- I prefer small commits\n- api_key = sk-abcdefghijklmnop\n')
        mem = home / '.claude/projects/-w/memory'
        mem.mkdir(parents=True)
        (mem / 'MEMORY.md').write_text('- [prefs](prefs.md)\n')
        (mem / 'prefs.md').write_text('---\nname: prefs\n---\n- The user likes green tea\n')
        (home / '.claude/projects/-w/chat.jsonl').write_text('{"a chat": 1}\n')
        (home / '.claude/.credentials.json').write_text('{"token": "x"}')
        (home / 'diary.md').write_text('- my private diary\n')
        (home / '.claude/rules').mkdir()
        (home / '.claude/rules/link.md').symlink_to(home / 'diary.md')
        (home / '.codex/memories').mkdir(parents=True)
        (home / '.codex/memories/raw_memories.md').write_text('- scratch\n')
        (home / '.codex/memories/MEMORY.md').write_text('- The user deploys with Docker\n')
        (home / '.gemini/GEMINI.md').write_text('## Gemini Added Memories\n- My dog is called Biscuit\n')
        (home / '.codeium/windsurf/memories').mkdir(parents=True)
        (home / '.codeium/windsurf/memories/m.pb').write_bytes(b'\x08\x01\x12\x03abc')
        got = memory_files(['claude', 'codex', 'gemini', 'antigravity', 'windsurf', 'cursor', 'zed'])
        names = {t: [str(p.relative_to(home)) for p, _, _ in fs] for t, fs in got.items()}
        assert names == {'claude': ['.claude/CLAUDE.md', '.claude/projects/-w/memory/prefs.md'], 'codex': ['.codex/memories/MEMORY.md'],
                         'gemini': ['.gemini/GEMINI.md']}, names
        assert got['claude'][0][1] == '- I prefer small commits' and about(got['claude'][1][1]) == 1
        assert about('# Title\n\n- one fact here\n- another fact here\n\nshort\n') == 2 and set(MEMORY_FILES) <= set(SITE)
        # looking for a Mindbaton: one unauthenticated GET /health, never through a proxy, only a private /24
        assert len(sweep('192.168.1.20')) == 253 and '192.168.1.20' not in sweep('192.168.1.20') and '192.168.1.1' in sweep('192.168.1.20')
        assert sweep('100.101.102.103') == sweep('8.8.8.8') == sweep('127.0.0.1') == sweep('169.254.3.4') == sweep(None) == sweep('fd00::1') == []
        from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

        class Fake(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({'name': self.server.who, 'version': '9'} if self.path == '/health' else {}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        fakes = []
        for who in ('mindbaton', 'something-else'):
            f = ThreadingHTTPServer(('127.0.0.1', 0), Fake)
            f.who = who
            threading.Thread(target=f.serve_forever, daemon=True).start()
            fakes.append(f)
        os.environ['http_proxy'] = 'http://127.0.0.1:9'  # a proxy would fail: it is never used
        try:
            mb, other = (f'http://127.0.0.1:{f.server_address[1]}' for f in fakes)
            assert probe(mb)['version'] == '9' and probe(other) is None and probe('http://127.0.0.1:9') is None
            save_cfg({'url': mb})
            assert discover(9, scan=False) == [(mb, {'name': 'mindbaton', 'version': '9'})]
        finally:
            for f in fakes:
                f.shutdown()

        cfg = {'url': 'http://127.0.0.1:9', 'token': tok, 'tools': {'cursor': {'capture': True}}}
        tr = home / 't.jsonl'
        tr.write_text('\n'.join(json.dumps(r) for r in [
            {'type': 'user', 'message': {'content': 'I keep bonsai trees'}, 'timestamp': '2026-09-24T10:00:00Z'},
            {'type': 'assistant', 'message': {'model': 'claude-opus-5', 'content': [{'type': 'text', 'text': 'Nice.'}]}},
            {'type': 'user', 'isMeta': True, 'message': {'content': 'noise'}}, {'type': 'ai-title', 'aiTitle': 'Bonsai'}]))
        site, cid, turns, extra = hook_payload('claude', {'hook_event_name': 'UserPromptSubmit', 'session_id': 's1', 'cwd': '/w',
                                                         'transcript_path': str(tr), 'prompt': 'water them weekly'}, cfg)
        assert (site, cid, extra['chat']) == ('claude-code', 's1', 'Bonsai') and [t['role'] for t in turns] == ['user', 'assistant', 'user']
        os.environ['CURSOR_VERSION'] = '2'
        assert hook_payload('claude', {'prompt': 'hi', 'session_id': 'c'}, cfg) is None  # Cursor has its own hook
        del os.environ['CURSOR_VERSION']
        for tool, p in (('cursor', {'hook_event_name': 'beforeSubmitPrompt', 'conversation_id': 'k', 'prompt': 'I use vim', 'model': 'm'}),
                        ('cursor', {'hook_event_name': 'afterAgentResponse', 'conversation_id': 'k', 'text': 'ok'}),
                        ('cursor', {'hook_event_name': 'beforeSubmitPrompt', 'conversation_id': 'k', 'prompt': 'I use vim'})):
            got = hook_payload(tool, p, cfg)
        assert [t['text'] for t in got[2]] == ['I use vim', 'ok', 'I use vim']
        got = hook_payload('codex', {'type': 'agent-turn-complete', 'thread-id': 'th', 'input-messages': ['a', 'b'],
                                     'last-assistant-message': 'c'}, cfg)
        assert got[0] == 'codex' and [t['text'] for t in got[2]] == ['a', 'b', 'c']
        assert hook_payload('gemini', {'hook_event_name': 'BeforeAgent', 'session_id': 'g', 'prompt': 'p'}, cfg)[2][0]['text'] == 'p'
        assert hook_payload('windsurf', {'trajectory_id': 'w', 'tool_info': {'user_prompt': 'u'}}, cfg)[2][0]['text'] == 'u'
        assert hook_payload('vscode', {'sessionId': 'v', 'prompt': 'q'}, cfg)[2][0]['text'] == 'q'
        agy = home / 'agy.jsonl'
        agy.write_text(json.dumps({'type': 'USER_INPUT', 'content': '<USER_REQUEST>hello</USER_REQUEST><ADDITIONAL_METADATA>x</ADDITIONAL_METADATA>'}))
        assert hook_payload('antigravity', {'conversationId': 'a', 'transcriptPath': str(agy)}, cfg)[2][0]['text'] == 'hello'
        left = lambda: 3
        assert run_hook('vscode', {'sessionId': 'v', 'prompt': 'first'}, cfg, left) == 1  # server down: queued
        assert run_hook('vscode', {'sessionId': 'v', 'prompt': 'second'}, cfg, left) == 1  # the newer transcript replaces it
        q = json.loads(QUEUE.read_text())
        assert [t['text'] for t in q['vscode/v']['body']['turns']] == ['q', 'first', 'second']
        # a revoked token is dropped, a down server holds back only its own items
        answers, sent = {'http://revoked': 401, 'http://down': 0, 'http://up': 200}, []
        fake = lambda m, u, b, token, timeout: (sent.append(u), (answers[u.rsplit('/', 1)[0]], {}, None))[1]
        QUEUE.write_text(json.dumps({k: {'url': u, 'path': '/session', 'body': {}, 'token': tok} for k, u in
                                     (('a', 'http://revoked'), ('b', 'http://down'), ('c', 'http://down'), ('d', 'http://up'))}))
        real_http = globals()['http']
        globals()['http'] = fake
        try:
            assert deliver(cfg, None, None, left) == 2 and set(json.loads(QUEUE.read_text())) == {'b', 'c'}
            assert sent == ['http://revoked/session', 'http://down/session', 'http://up/session'], sent
        finally:
            globals()['http'] = real_http
    finally:
        MB, CFG, LOG, QUEUE = old_globals
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        shutil.rmtree(home, ignore_errors=True)
    print('cli ok')


# ── Command line ───────────────────────────────────────────────────────────────────────────────────────────

def parse(argv):
    p = argparse.ArgumentParser(prog='mindbaton.py', description='Mindbaton on the command line.',
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split('\n\n', 1)[1])
    sub = p.add_subparsers(dest='cmd')
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--yes', '-y', action='store_true', help='ask nothing; answers come from the flags')
    common.add_argument('--no-motion', action='store_true', help='no animation')
    i = sub.add_parser('install', parents=[common], help='set up Mindbaton on this computer')
    i.add_argument('--username')
    i.add_argument('--display-name')
    i.add_argument('--password-file', help='a file whose first line is the password')
    i.add_argument('--gemini-key')
    i.add_argument('--groq-key')
    i.add_argument('--tools', help='claude,codex,… | all (default) | none')
    i.add_argument('--port', type=int)
    i.add_argument('--no-service', action='store_true', help="don't install a login service")
    i.add_argument('--foreground', action='store_true', help='with --yes --no-service: run the server here afterwards')
    i.add_argument('--replace-old', action='store_true', help="replace old 'memgraph' MCP entries")
    i.add_argument('--import-memories', action='store_true', help="with --yes: also copy the tools' own memory files in")
    i.add_argument('--no-scan', action='store_true', help="linking instead: don't look around the network for it")
    c = sub.add_parser('connect', parents=[common], help="connect this computer's AI tools to a Mindbaton elsewhere")
    c.add_argument('url', nargs='?', help='its address; leave it out to find it on your network')
    c.add_argument('--tools')
    c.add_argument('--replace-old', action='store_true')
    c.add_argument('--no-scan', action='store_true', help="don't look around the network; only the saved address and this computer")
    c.add_argument('--import-memories', action='store_true', help="with --yes: also copy the tools' own memory files in")
    im = sub.add_parser('import', parents=[common], help="copy what your AI tools already remember into Mindbaton")
    im.add_argument('--tools', help='claude,codex,… (default: every one found here)')
    im.add_argument('--dry-run', action='store_true', help='only show what would be sent')
    d = sub.add_parser('doctor', parents=[common], help='check everything, fix problems')
    d.add_argument('--fix', action='store_true')
    sub.add_parser('update', parents=[common], help='get the latest version, test it, restart')
    k = sub.add_parser('keys', parents=[common], help='add, replace or remove the free AI keys')
    k.add_argument('--gemini-key')
    k.add_argument('--groq-key')
    k.add_argument('--remove', action='append', choices=list(KEY_SITES))
    m = sub.add_parser('models', parents=[common], help='pick the free AI model')
    m.add_argument('--gemini-model', help='a model id, or auto')
    m.add_argument('--groq-model', help='a model id, or auto')
    u = sub.add_parser('uninstall', parents=[common], help='remove what Mindbaton added; keeps your memories')
    u.add_argument('--purge', action='store_true', help='also delete the memories (asks to confirm)')
    return p, p.parse_args(argv)


def main(argv):
    if argv[:1] == ['hook']:
        return cmd_hook(argv[1:])
    if argv[:1] == ['logo']:
        return cmd_logo(argv[1:])
    if argv[:1] == ['--check']:
        return selfcheck()
    p, o = parse(argv)
    if not o.cmd:
        return p.print_help()
    try:
        {'install': cmd_install, 'connect': cmd_connect, 'doctor': cmd_doctor, 'update': cmd_update, 'keys': cmd_keys,
         'models': cmd_models, 'uninstall': cmd_uninstall, 'import': cmd_import}[o.cmd](o)
    except KeyboardInterrupt:
        log('stopped with Ctrl-C')
        again = "Run ./install.sh again any time — it's safe to repeat." if o.cmd == 'install' else ''
        print(f"\n  Stopped. {again}" + (f"\n  Mindbaton isn't running now. To start it:\n    {START_HINT}" if START_HINT else '') + '\n')
        sys.exit(130)
    except Stop as e:
        log('stop:', e)
        print(f'\n  {e}\n')
        sys.exit(1)
    except Exception as e:
        import traceback
        log('error:', traceback.format_exc())
        print(f'\n  Something went wrong: {friendly(e)}\n  The details are in {tilde(LOG)}.\n')
        sys.exit(1)


if __name__ == '__main__':
    main(sys.argv[1:])
