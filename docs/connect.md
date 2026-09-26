# Connect your AIs

The easiest way is the **Setup** page in Mindbaton: it shows a green tick next to everything already connected and,
for the rest, the exact command or config with your address and a fresh token already filled in — just copy it.

This page explains the same steps. In the examples, replace

- `http://192.168.1.20:3004` with your Mindbaton address (use your `https://` address if you set one up — see
  [remote access](remote-access.md)), and
- `mb_xxxxxxxx` with a **device token**.

## Device tokens

Everything except your own browser proves who it is with a device token — a long secret that starts with `mb_`.

- Make one under **Settings → Devices → New token**: give it a name ("Cursor on work laptop") and a kind. It is shown
  **once**, so copy it straight into the app you're connecting.
- Every token has its own row in Settings → Devices with when it was last used. **Revoke** one and that app is cut off
  immediately; nothing else is affected.
- One token per app or device is best — then you can revoke just the one you lose.
- Treat a token like a password. Anything holding a full token can read and change your memory.

## Browser extension

Captures what you send to ChatGPT, Claude, Gemini, Perplexity, DeepSeek, Grok, Copilot, Poe, Mistral and Google AI
Studio, keeps whole chats in Live mode, and brings your memory into any chat. Works in Chrome, Edge, Brave, Arc and
other Chromium browsers.

1. Add it from the **[Chrome Web Store](https://chromewebstore.google.com/detail/mindbaton/nfadphcjimkchbapapbcphnbpajmfmih)** (Chrome, Edge and Brave all install from there, and it updates itself).
   Or by hand: download `http://192.168.1.20:3004/mindbaton-extension.zip` from your Mindbaton (also on the Setup page),
   unzip it, open `chrome://extensions`, switch on **Developer mode**, click **Load unpacked** and pick the folder.
2. The Connect page opens (or click the Mindbaton icon in the toolbar), type your Mindbaton address and press **Connect**.
3. A Mindbaton tab opens asking *"Connect Chrome on laptop (browser extension)?"* with a code like `ABCD-EFGH`. Log in if
   asked, check it's the request you just made, and press **Approve**. Done — the extension now has its own token.

Can't use the approve tab (for example Mindbaton is on a different network right now)? Make a token in Settings →
Devices and paste it into the extension instead.

Using it:

- Chat as usual. What you type is saved; secrets like API keys are blanked out first.
- Press **`Alt+M`** in a chat box to insert a short briefing of what Mindbaton knows that's relevant to what you're typing.
- The toolbar popup shows how full the current chat is. When it's nearly full, **hand it off**: Mindbaton packs the chat
  up and you paste it into a new chat with any AI.

## Coding agents and editors

Coding agents talk to Mindbaton over **MCP** (Model Context Protocol) at `http://192.168.1.20:3004/mcp`, with the token
in an `Authorization: Bearer` header. They get these tools: `context`, `recall`, `remember`, `profile`, `handoff`,
`sessions`, `save_conversation` and `forget`.

### Claude Code

```sh
claude mcp add --transport http -s user mindbaton http://192.168.1.20:3004/mcp --header "Authorization: Bearer mb_xxxxxxxx"
```

Check it with `claude mcp get mindbaton`. Bonus: if Mindbaton runs on the same computer as Claude Code, it also reads
Claude Code's own chat history (`~/.claude/projects`) by itself — turn that off with `MINDBATON_WATCH_CLAUDE=0`.

### Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.mindbaton]
url = "http://192.168.1.20:3004/mcp"
http_headers = { Authorization = "Bearer mb_xxxxxxxx" }
```

### Cursor

Add to `~/.cursor/mcp.json` (or Cursor Settings → MCP → Add):

```json
{
  "mcpServers": {
    "mindbaton": {
      "url": "http://192.168.1.20:3004/mcp",
      "headers": { "Authorization": "Bearer mb_xxxxxxxx" }
    }
  }
}
```

### Windsurf

Add to `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "mindbaton": {
      "serverUrl": "http://192.168.1.20:3004/mcp",
      "headers": { "Authorization": "Bearer mb_xxxxxxxx" }
    }
  }
}
```

### VS Code (GitHub Copilot)

```sh
code --add-mcp '{"name":"mindbaton","type":"http","url":"http://192.168.1.20:3004/mcp","headers":{"Authorization":"Bearer mb_xxxxxxxx"}}'
```

### Gemini CLI

```sh
gemini mcp add --transport http mindbaton http://192.168.1.20:3004/mcp --header "Authorization: Bearer mb_xxxxxxxx"
```

### Antigravity

Open the **…** menu in the agent panel → **MCP Servers** → **Manage MCP Servers** → **View raw config**, and add:

```json
{
  "mcpServers": {
    "mindbaton": {
      "serverUrl": "http://192.168.1.20:3004/mcp",
      "headers": { "Authorization": "Bearer mb_xxxxxxxx" }
    }
  }
}
```

### Anything else that speaks MCP

Cline, Zed and other clients: use the URL `http://192.168.1.20:3004/mcp` (streamable HTTP) and the header
`Authorization: Bearer mb_xxxxxxxx`. If a client can only launch a local command, use the bridge below.

## Claude Desktop

Claude Desktop starts MCP servers as local programs, so Mindbaton ships a tiny bridge, `mcp_stdio.py` (Python, nothing
to install).

1. Download it from your Mindbaton: `http://192.168.1.20:3004/mcp_stdio.py` and save it somewhere permanent.
2. In Claude Desktop open **Settings → Developer → Edit Config** and add:

   ```json
   {
     "mcpServers": {
       "mindbaton": {
         "command": "python3",
         "args": ["/path/to/mcp_stdio.py"],
         "env": {
           "MINDBATON_URL": "http://192.168.1.20:3004",
           "MINDBATON_TOKEN": "mb_xxxxxxxx"
         }
       }
     }
   }
   ```

   On Windows use `"command": "python"` and a path like `"C:\\Users\\you\\mcp_stdio.py"`.
3. Restart Claude Desktop.

## Claude and ChatGPT apps

The Claude and ChatGPT apps (on the web and on your phone) can use Mindbaton as a **custom connector**. Their servers
call Mindbaton from the internet, so this one needs a public **HTTPS** address — set one up first with
[Tailscale Funnel or Cloudflare Tunnel](remote-access.md).

1. In Settings → Devices make a token of kind **connector**. Connector tokens are deliberately limited: they can't
   forget or export anything, they're rate-limited, and every request is written to `access.log` in your data folder.
2. Your connector URL is your HTTPS address + `/t/` + the token + `/mcp`:

   ```
   https://mindbaton.example.com/t/mb_xxxxxxxx/mcp
   ```

   (The token sits in the address because these apps can't send headers. Keep the URL private, and revoke the token if
   it ever leaks.)
3. **Claude:** Settings → Connectors → **Add custom connector**, paste the URL.
   **ChatGPT:** Settings → Apps & Connectors → Advanced settings → turn on **Developer mode**, then **Create** a
   connector with the URL.
4. In a chat, turn the connector on and ask "what do you know about me?".

Custom connectors depend on your plan with those apps.

## Phone

Mindbaton is also a phone app you install from the browser. Installing needs an HTTPS address — the simplest is
[Tailscale](remote-access.md#tailscale) (`https://<computer>.<tailnet>.ts.net`).

- **Android (Chrome):** open your HTTPS address, log in, then menu **⋮ → Add to Home screen** (or **Install app**).
  Mindbaton now appears in Android's **Share** menu: share a link, a note or a bit of text from any app and it's saved.
- **iPhone (Safari):** open your HTTPS address, log in, then **Share → Add to Home Screen**. (iOS doesn't let web apps
  appear in the Share menu, so saving from other apps is Android-only.)

## Scripts and everything else

Any program can use the same HTTP API with a token:

```sh
# a briefing of what's relevant to a question, ready for an AI to read (JSON: {"text": ...})
curl -H "Authorization: Bearer mb_xxxxxxxx" "http://192.168.1.20:3004/context?q=my+homelab"

# save a fact
curl -H "Authorization: Bearer mb_xxxxxxxx" -H "Content-Type: application/json" \
     -d '{"text": "I switched my home server to Debian 13"}' http://192.168.1.20:3004/remember
```

The MCP tools, in the JSON shape the Claude and OpenAI tool-calling APIs take, are at `/tools.json`.
