# Backup and upgrade

## What to back up

Everything lives in the **data folder**: `data/` inside the mindbaton folder (or wherever `MINDBATON_DATA` points), or
the `mindbaton-data` volume with Docker. The one file that matters is `mindbaton.db`; `ai_keys` holds your optional AI
keys. Your `mindbaton.env` (if you changed it) is worth keeping too.

## Make a backup

Mindbaton can keep running. This uses SQLite's own backup, so the copy is consistent even mid-write:

```sh
cd ~/mindbaton
python3 -c "import sqlite3; sqlite3.connect('data/mindbaton.db').backup(sqlite3.connect('mindbaton-backup.db'))"
```

With Docker:

```sh
docker compose exec mindbaton python3 -c "import sqlite3; sqlite3.connect('/data/mindbaton.db').backup(sqlite3.connect('/data/backup.db'))"
docker compose cp mindbaton:/data/backup.db ./mindbaton-backup.db
docker compose exec mindbaton rm /data/backup.db
```

Keep the backup somewhere private — it contains everything you've told your AIs (secrets are removed, but it is still
your life). To back up every night, put the first command in a cron job or systemd timer.

Want your memory in another tool instead? **Export** it from the app, or with a full token:
`curl -H "Authorization: Bearer mb_xxxxxxxx" "http://localhost:3004/export?format=json"` (also `cypher` for Neo4j and
`graphml` for Gephi).

## Restore

Stop Mindbaton, put the backup in place, start it again:

```sh
systemctl --user stop mindbaton                        # macOS: launchctl bootout gui/$(id -u)/ai.mindbaton
cp mindbaton-backup.db data/mindbaton.db
rm -f data/mindbaton.db-wal data/mindbaton.db-shm
systemctl --user start mindbaton                       # macOS: ./install.sh
```

With Docker:

```sh
docker compose stop
docker compose run --rm -v "$PWD:/backup" mindbaton \
  sh -c "cp /backup/mindbaton-backup.db /data/mindbaton.db && rm -f /data/mindbaton.db-wal /data/mindbaton.db-shm"
docker compose start
```

(Removing the old `-wal`/`-shm` files matters: they belong to the database you're replacing.)

## Upgrade

Upgrades keep all your data. Mindbaton saves every message as it arrived and builds the memory graph from those, so
when a new version understands messages better it simply rebuilds the graph on its first start — and anything you told
it to forget stays forgotten. A backup first never hurts.

**Installed with `install.sh`:**

```sh
cd ~/mindbaton
python3 mindbaton.py update   # downloads, runs the self-test (goes back if it fails), restarts the service
```

**Docker** (Windows, macOS, Linux, NAS), in the folder with `compose.yaml`:

```sh
docker compose pull
docker compose up -d
```

That fetches the newest published image (`ghcr.io/dkshbyte/mindbaton`) and restarts on it. Your data stays in the
`mindbaton-data` volume. Started with plain `docker run` instead? Then `docker pull ghcr.io/dkshbyte/mindbaton`, remove
the old container (`docker rm -f mindbaton`) and run the same `docker run` command again: the volume keeps everything.

**Your folder is from before 25 September 2026?** The project's history was rewritten once that day, so `git pull`
refuses in older copies. Run this once in the folder (your data and `mindbaton.env` aren't touched):

```sh
git fetch origin
git reset --hard origin/main
```

After upgrading, reload the browser extension if it changed: download `/mindbaton-extension.zip` again, unzip it over the
old folder, and press the reload button on it in `chrome://extensions`.

## Moving to another computer

Install Mindbaton on the new computer, stop it, copy `mindbaton.db` (and `ai_keys`) into its data folder, and start it.
Your password, device tokens and memories all come along — just update the address in your extension and apps if it
changed.
