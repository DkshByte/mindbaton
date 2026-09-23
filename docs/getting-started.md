# Getting started

Mindbaton is one small Python program. Put it on a computer that is usually on — a home server, a NAS, a Mac mini, a
Raspberry Pi 4, or just your laptop — and every AI you use can share one memory.

You need **either** Python 3.9 or newer (with SQLite's FTS5, which almost every Python has) and the system word list
(`/usr/share/dict/words` — already there on macOS and most Linux desktops; on a minimal server `sudo apt install
wamerican`), **or** Docker. Nothing else: no pip packages, no database server, no build step. The installer checks all
of it for you.

- [Linux](#linux)
- [macOS](#macos)
- [Windows](#windows)
- [Docker, NAS and home-lab boxes](#docker-nas-and-home-lab-boxes)
- [First run: the setup code](#first-run-the-setup-code)
- [Forgot your password?](#forgot-your-password)
- [Uninstall](#uninstall)

## Linux

```sh
git clone https://github.com/DkshByte/mindbaton && cd mindbaton && ./install.sh
```

The installer:

1. checks you have Python 3.9+ with FTS5 and the system word list,
2. writes `mindbaton.env` (listen on your network, port 3004) if you don't have one yet,
3. runs the self-test (`python3 server.py --check`),
4. installs and starts a systemd **user** service called `mindbaton`,
5. prints your first-run link with the setup code, and the address to use from your other devices.

It is safe to run again — for example after an upgrade.

To keep Mindbaton running when you log out, and to start it at boot, turn on "linger" once (the installer reminds you):

```sh
sudo loginctl enable-linger $USER
```

Handy commands:

```sh
systemctl --user status mindbaton        # is it running?
systemctl --user restart mindbaton       # restart after changing mindbaton.env
journalctl --user -u mindbaton -f        # logs (the setup code is printed here too)
```

No systemd (some containers, WSL1, Alpine)? The installer tells you, and you can run it in the foreground instead:

```sh
python3 server.py
```

## macOS

Same one-liner, in Terminal:

```sh
git clone https://github.com/DkshByte/mindbaton && cd mindbaton && ./install.sh
```

If macOS asks to install the command line developer tools (for `git` and `python3`), say yes and run the line again.
The installer sets up a launchd agent (`~/Library/LaunchAgents/ai.mindbaton.plist`) that starts Mindbaton when you
log in and restarts it if it stops. Logs go to `~/Library/Logs/mindbaton.log`.

The first time, macOS may ask whether Python may accept incoming network connections — allow it, or other devices
won't be able to reach Mindbaton.

## Windows

Pick one:

- **Docker Desktop** (easiest): install [Docker Desktop](https://www.docker.com/products/docker-desktop/), then follow
  [Docker](#docker-nas-and-home-lab-boxes) below in PowerShell or Terminal.
- **WSL2**: open your Ubuntu (or other Linux) terminal and follow [Linux](#linux). New WSL installs have systemd turned
  on, so the installer sets up the service; if yours doesn't, it tells you how to run Mindbaton in the foreground.
  Your Windows browser can open it at `http://localhost:3004`. For your phone and other computers to reach it,
  Docker Desktop or [Tailscale](remote-access.md#tailscale) is simpler than WSL's networking.

## Docker, NAS and home-lab boxes

```sh
git clone https://github.com/DkshByte/mindbaton && cd mindbaton && docker compose up -d
docker compose logs mindbaton | grep "Setup code"
```

That builds a small image (Python only, runs as a normal user, no extra packages from pip), starts it on port 3004,
restarts it automatically, and keeps your data in a Docker volume called `mindbaton-data`.

- **Another port:** change the left side of `"3004:3004"` in `compose.yaml` (for example `"8090:3004"`).
- **Settings:** put them in a `mindbaton.env` file next to `compose.yaml` (see [configuration](configuration.md)); it's
  picked up automatically.
- **Without compose:**

  ```sh
  docker build -t mindbaton .
  docker run -d --name mindbaton --restart unless-stopped -p 3004:3004 -v mindbaton-data:/data mindbaton
  docker logs mindbaton | grep "Setup code"
  ```

- **NAS (Synology, Unraid, TrueNAS, …):** copy this folder to the NAS and create a Compose "project" from it in your NAS's
  container app, or run the commands above over SSH.

## First run: the setup code

Until you choose a password, Mindbaton is waiting for its owner. So that nobody else on your network can grab it first,
it makes a one-time **setup code** (like `4821-7730`) and prints it where only you can see it:

- the installer shows it at the end, as part of the link,
- the logs show it every time Mindbaton starts (`journalctl --user -u mindbaton`, `~/Library/Logs/mindbaton.log`,
  or `docker compose logs mindbaton`),
- and you can always ask for it on the Mindbaton computer:

  ```sh
  python3 server.py --setup-code                                  # in the mindbaton folder
  docker compose exec mindbaton python3 server.py --setup-code    # Docker
  ```

Open the link — `http://<your computer>:3004/?code=4821-7730` — and choose a password (8 characters or more).
Opened in a browser on the Mindbaton computer itself (`http://localhost:3004`, not through Docker), no code is needed.

Next, open the **Setup** page. It lists every AI and device, ticks the ones that are connected, and gives you the exact
copy-paste step for the rest. The same steps are in [connect.md](connect.md).

> **Tip:** try it with made-up data first. `MINDBATON_DATA=/tmp/mb-demo python3 demo.py --password demo-pass-123`, then
> `MINDBATON_DATA=/tmp/mb-demo MINDBATON_PORT=3005 python3 server.py` and log in at `http://localhost:3005` with that password.

## Forgot your password?

Anyone with a shell on the Mindbaton computer is the owner, so resetting happens there:

```sh
python3 server.py --reset-password                                  # in the mindbaton folder
docker compose exec mindbaton python3 server.py --reset-password    # Docker
```

This removes the password and signs out every browser. **Your memories and your device tokens are kept** — your
extension and coding agents keep working. It prints a new setup code; open the link and choose a new password.

## Uninstall

Your memories live in `data/` in the mindbaton folder (or the `mindbaton-data` volume with Docker). Keep a
[backup](backup-and-upgrade.md) if you might want them back.

**Linux**

```sh
systemctl --user disable --now mindbaton
rm ~/.config/systemd/user/mindbaton.service && systemctl --user daemon-reload
rm -rf ~/mindbaton        # the folder you cloned — this deletes your data too
```

**macOS**

```sh
launchctl bootout gui/$(id -u)/ai.mindbaton
rm ~/Library/LaunchAgents/ai.mindbaton.plist ~/Library/Logs/mindbaton.log
rm -rf ~/mindbaton        # the folder you cloned — this deletes your data too
```

**Docker**

```sh
docker compose down       # stop and remove the container; your data volume stays
docker compose down -v    # …and delete your data too
```

Then remove the browser extension, and the `mindbaton` entry from any AI app you connected.
