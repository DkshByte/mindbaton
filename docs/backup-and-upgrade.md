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
git pull
./install.sh            # runs the self-test and restarts the service
```

**Docker:**

```sh
cd ~/mindbaton
git pull
docker compose up -d --build
```

Mindbaton builds its image from this folder, so `git pull` + `--build` is the upgrade (there's no separate image to
`docker pull`). Your data stays in the `mindbaton-data` volume.

After upgrading, reload the browser extension if it changed: download `/mindbaton-extension.zip` again, unzip it over the
old folder, and press the reload button on it in `chrome://extensions`.

## Moving to another computer

Install Mindbaton on the new computer, stop it, copy `mindbaton.db` (and `ai_keys`) into its data folder, and start it.
Your password, device tokens and memories all come along — just update the address in your extension and apps if it
changed.
