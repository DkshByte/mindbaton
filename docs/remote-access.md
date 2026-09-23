# Remote access

At home, your devices reach Mindbaton at `http://<computer>:3004`. To use it from anywhere — or to install the phone
app, or to connect the Claude and ChatGPT apps — give it an **HTTPS** address.

> **Never** forward port 3004 on your router or put Mindbaton on the internet over plain `http://`. Your password and
> tokens would travel unencrypted. Every option below gives you HTTPS without opening any port.

After you pick one, tell Mindbaton its address so the Setup page shows the right links. In `mindbaton.env`:

```sh
MINDBATON_PUBLIC_URL=https://mindbaton.example.com
```

then restart it (`systemctl --user restart mindbaton`, or `docker compose up -d` after editing). With Docker, put the
line in a `mindbaton.env` next to `compose.yaml`.

## Tailscale

[Tailscale](https://tailscale.com) connects your devices into a private network. Install it on the Mindbaton computer
and on your phone and laptops, then on the Mindbaton computer:

```sh
tailscale serve --bg 3004
```

Mindbaton is now at `https://<computer>.<tailnet>.ts.net` — with a real certificate, reachable **only by your own
devices** on Tailscale. This is the recommended setup: it's what the phone app wants, and nothing is public.
Set `MINDBATON_PUBLIC_URL` to that address.

### Funnel: for the Claude and ChatGPT apps

Custom connectors in the Claude and ChatGPT apps are called from those companies' servers, so they need an address on
the public internet. Tailscale **Funnel** can publish Mindbaton on a second port while the main address stays private:

```sh
tailscale funnel --bg --https=10000 3004
```

Your connector URL is then `https://<computer>.<tailnet>.ts.net:10000/t/<connector token>/mcp`
(see [connect.md](connect.md#claude-and-chatgpt-apps)). Everything on that public address still needs your password or
a token, and connector tokens can't forget or export anything. Turn it off with `tailscale funnel --https=10000 off`.

## Cloudflare Tunnel

If you have a domain on Cloudflare, [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
gives Mindbaton a public HTTPS address without opening ports.

- **Just trying it:** `cloudflared tunnel --url http://localhost:3004` prints a temporary
  `https://<random>.trycloudflare.com` address (it changes every time).
- **For keeps:** in the Cloudflare dashboard go to Zero Trust → Networks → Tunnels, create a tunnel, run the connector
  command it shows on the Mindbaton computer, and add a public hostname (say `mindbaton.example.com`) pointing to
  `http://localhost:3004`. Set `MINDBATON_PUBLIC_URL=https://mindbaton.example.com`.

This address is public: anyone can reach the login page, so use a strong password. (If you put Cloudflare Access in
front, the Claude and ChatGPT connectors won't get through unless you exclude `/t/` paths.)

## Your own reverse proxy

Already run Caddy, nginx or Traefik with HTTPS? Point it at Mindbaton and make sure it passes the original `Host` and
sets `X-Forwarded-Proto` (and `X-Forwarded-For`), so Mindbaton knows the request came over HTTPS, marks your login
cookie secure, and throttles the right address.

**Caddy** (does all of that by itself):

```
mindbaton.example.com {
    reverse_proxy 127.0.0.1:3004
}
```

**nginx:**

```nginx
server {
    listen 443 ssl;
    server_name mindbaton.example.com;
    # ssl_certificate … ssl_certificate_key …

    location / {
        proxy_pass http://127.0.0.1:3004;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;
    }
}
```

If the proxy runs on the same computer, you can also set `MINDBATON_HOST=127.0.0.1` so Mindbaton is only reachable
through the proxy.

## How the first-run setup code works behind a proxy

Requests through a tunnel or proxy never count as "typed on this computer", even though they arrive from `127.0.0.1` —
so the setup code is always required through them. Get it with `python3 server.py --setup-code` on the Mindbaton
computer.
