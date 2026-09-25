#!/bin/sh
# Mindbaton on Docker (Linux, macOS, NAS): get the newest release, and go back to the one you had if it doesn't come up
# healthy. Your memories live in the mindbaton-data volume and are never touched.
#
#   sh scripts/auto-update.sh             update now
#   sh scripts/auto-update.sh --install   also every night at 04:00 (one line in your crontab)
#   sh scripts/auto-update.sh --remove    stop the nightly update
#
# Windows: scripts\auto-update.ps1 does the same with Task Scheduler.
set -u
cd "$(dirname "$0")/.." || exit 1   # the folder with compose.yaml
IMG=${MINDBATON_IMAGE:-ghcr.io/dkshbyte/mindbaton:latest}
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a auto-update.log; }

case "${1:-}" in
  --install)
    (crontab -l 2>/dev/null | grep -v 'scripts/auto-update.sh'; echo "0 4 * * * cd '$PWD' && sh scripts/auto-update.sh >/dev/null 2>&1") | crontab - &&
      echo "Mindbaton will update itself every night at 04:00. Log: $PWD/auto-update.log"
    exit $? ;;
  --remove)
    crontab -l 2>/dev/null | grep -v 'scripts/auto-update.sh' | crontab - && echo "Nightly updates are off."
    exit $? ;;
esac

cid=$(docker compose ps -q mindbaton)
[ -n "$cid" ] || { log "Mindbaton isn't running in this folder: start it with docker compose up -d"; exit 1; }
old=$(docker inspect -f '{{.Image}}' "$cid")
docker compose pull -q mindbaton || { log "couldn't download the new version (offline?); nothing changed"; exit 1; }
new=$(docker image inspect -f '{{.Id}}' "$IMG")
[ "$old" = "$new" ] && { log "already up to date"; exit 0; }
if [ "$new" = "$(cat .auto-update-skip 2>/dev/null)" ]; then  # this release failed here before: wait for a newer one
  docker tag "$old" "$IMG"; log "skipping the release that failed its health check last time; waiting for a newer one"; exit 0
fi
docker compose up -d mindbaton || { log "couldn't start the new version: going back"; docker tag "$old" "$IMG"; docker compose up -d mindbaton; exit 1; }

s=starting
for _ in $(seq 1 36); do   # up to 3 minutes: the first health check runs 30 s after start
  s=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$(docker compose ps -q mindbaton)" 2>/dev/null)
  case "$s" in
    healthy) log "updated to $(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.version"}}' "$IMG")"
             docker image prune -f >/dev/null; exit 0 ;;
    unhealthy) break ;;
  esac
  sleep 5
done
log "the new version didn't come up healthy ($s): going back to the one you had (and skipping that release)"
echo "$new" > .auto-update-skip
docker tag "$old" "$IMG" && docker compose up -d mindbaton
exit 1
