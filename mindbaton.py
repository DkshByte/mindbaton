#!/usr/bin/env python3
"""Mindbaton on the command line. Stdlib only.

  python3 mindbaton.py logo [--no-motion]    draw the Mindbaton logo for this terminal
"""
import json
import os
import re
import select
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ── Logo ────────────────────────────────────────────────────────────────────────────────────────────────────
# The art is generated from assets/brand/mark.svg by assets/brand/make-icons.mjs (swap the logo, re-run it).
# Each size has half-block cells ([char, fg, bg] palette indices, None = terminal background) in truecolor and
# xterm-256 palettes for dark and light terminals, plus braille and ASCII monochrome versions.

ART = HERE / 'assets/brand/terminal-logo.json'
BG_DARK, BG_LIGHT = (10, 10, 11), (255, 255, 255)  # what the art's anti-aliased edges were blended over
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
    _art = _art or json.loads(ART.read_text())
    mode = mode or color_mode()
    for kind in (('mark',) if mark_only else ('lockup', 'mark')):
        fits = [v for v in _art[kind] if v['cols'] <= max_w and v['rows'] <= max_h]
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
                for y, line in enumerate(v[mode])], cols
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


def cmd_logo(args):
    mode = color_mode()
    show_logo(motion='--no-motion' not in args)
    tagline = 'Tell one AI. Every AI knows.'
    print('\n' + ' ' * max(0, (shutil.get_terminal_size().columns - len(tagline)) // 2) + paint(tagline, '#a1a1aa', mode))


if __name__ == '__main__':
    args = sys.argv[1:]
    try:
        if args[:1] == ['logo']:
            cmd_logo(args[1:])
        else:
            print(__doc__.strip())
    except KeyboardInterrupt:
        sys.exit(130)
