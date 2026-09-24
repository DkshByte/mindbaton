#!/bin/sh
# Mindbaton installer. Checks for Python, then hands over to the full-screen setup in mindbaton.py:
# your account, free AI keys, your AI tools, a background service and a link for your phone. Safe to run again.
#   ./install.sh                     interactive
#   ./install.sh --yes --username maya --password-file pw.txt --tools all    unattended (CI, Docker)
#   ./install.sh --help              every option
set -eu
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Mindbaton needs Python 3.9 or newer, and this computer has no python3."
  echo "  Debian/Ubuntu: sudo apt install python3 · Fedora: sudo dnf install python3 · macOS: xcode-select --install"
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
  echo "Mindbaton needs Python 3.9 or newer (this computer has $(python3 -V 2>&1)). Install a newer python3, or use Docker."
  exit 1
fi

exec python3 mindbaton.py install "$@"
