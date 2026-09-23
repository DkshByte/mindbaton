#!/bin/sh
# Mindbaton installer: checks Python, writes mindbaton.env, runs the self-test, starts Mindbaton as a background
# service (systemd on Linux, launchd on macOS) and prints your first-run link. Safe to run again.   ./install.sh
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"

command -v python3 >/dev/null 2>&1 || { echo "Mindbaton needs Python 3.9 or newer. Install python3 and run this again."; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' \
  || { echo "Mindbaton needs Python 3.9 or newer (you have $(python3 -V 2>&1))."; exit 1; }
python3 -c 'import sqlite3; sqlite3.connect(":memory:").execute("create virtual table t using fts5(x)")' 2>/dev/null \
  || { echo "Your Python's SQLite has no FTS5 (full-text search). Install a newer python3 (or use Docker)."; exit 1; }
[ -e /usr/share/dict/american-english ] || [ -e /usr/share/dict/british-english ] || [ -e /usr/share/dict/words ] || {
  echo "Mindbaton needs the system word list (/usr/share/dict/words) to tell names from typos. Install it:"
  echo "  Debian/Ubuntu: sudo apt install wamerican · Fedora: sudo dnf install words · Arch: sudo pacman -S words"
  exit 1
}
PY="$(command -v python3)"

[ -f mindbaton.env ] || printf 'MINDBATON_HOST=0.0.0.0\nMINDBATON_PORT=%s\n' "${MINDBATON_PORT:-3004}" > mindbaton.env
HOST="$(sed -n 's/^MINDBATON_HOST=//p' mindbaton.env | tail -n 1 | tr -d "\"'")"
PORT="$(sed -n 's/^MINDBATON_PORT=//p' mindbaton.env | tail -n 1 | tr -d "\"'")"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-3004}"

OUT="$("$PY" server.py --check 2>&1)" || { echo "$OUT"; echo "Self-test failed — please open an issue with the output above."; exit 1; }
echo "✓ self-test passed"

SERVICE=""
if [ "$(uname -s)" = Darwin ]; then
  PLIST="$HOME/Library/LaunchAgents/ai.mindbaton.plist"
  mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
  cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>ai.mindbaton</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$DIR/server.py</string></array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/mindbaton.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/mindbaton.log</string>
</dict>
</plist>
PLIST
  launchctl bootout "gui/$(id -u)/ai.mindbaton" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  SERVICE="launchd agent ai.mindbaton (logs: ~/Library/Logs/mindbaton.log)"
elif command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  mkdir -p "$HOME/.config/systemd/user"
  cat > "$HOME/.config/systemd/user/mindbaton.service" <<UNIT
[Unit]
Description=Mindbaton - long-term memory for all your AIs
After=network-online.target

[Service]
WorkingDirectory=$DIR
ExecStart="$PY" "$DIR/server.py"
Restart=always

[Install]
WantedBy=default.target
UNIT
  systemctl --user daemon-reload
  systemctl --user enable --quiet mindbaton
  systemctl --user restart mindbaton
  SERVICE="systemd user service mindbaton (logs: journalctl --user -u mindbaton -f)"
  if [ "$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null)" != yes ]; then
    echo "  Tip: to keep Mindbaton running after you log out and start it at boot, run:  sudo loginctl enable-linger $(id -un)"
  fi
fi

case "$HOST" in 0.0.0.0|127.0.0.1|localhost) CHECK=127.0.0.1 ;; *) CHECK="$HOST" ;; esac
if [ "$HOST" = 0.0.0.0 ]; then
  IP="$("$PY" -c 'import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("10.255.255.255", 1)); print(s.getsockname()[0])' 2>/dev/null || true)"
else
  IP="$CHECK"
fi
URL="http://${IP:-localhost}:$PORT"

if [ -n "$SERVICE" ]; then
  i=0
  until "$PY" -c "import urllib.request; urllib.request.urlopen('http://$CHECK:$PORT/health', timeout=2)" 2>/dev/null; do
    i=$((i + 1))
    [ "$i" -lt 20 ] || { echo "Mindbaton didn't answer on port $PORT. Check the logs: $SERVICE"; exit 1; }
    sleep 1
  done
  echo "✓ Mindbaton is running as a $SERVICE"
else
  echo "No systemd or launchd here (a container or WSL1?), so start Mindbaton yourself and keep it running:"
  echo "    cd \"$DIR\" && python3 server.py"
  echo "  (Docker is the easy way to keep it running on such systems — see docs/getting-started.md.)"
fi

CODE="$("$PY" server.py --setup-code 2>/dev/null | grep -Eo '[0-9]{4}-[0-9]{4}' | head -n 1 || true)"
echo
if [ -n "$CODE" ]; then
  echo "  Open this link to create your password (setup code $CODE):"
  echo "    $URL/?code=$CODE"
else
  echo "  Open Mindbaton:  $URL"
fi
if [ "$HOST" = 0.0.0.0 ]; then
  echo "  Other devices on your network: $URL · away from home: see docs/remote-access.md"
fi
