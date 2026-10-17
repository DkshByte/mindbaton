# Team Baton (experimental, opt in)

Team Baton adds isolated shared project memory to one Mindbaton host. Teammates need project invitations, not personal
Mindbaton accounts. Personal categories are navigation only: they never grant access or select conversations for sharing.

**Disabled by default.** Leave `MINDBATON_TEAM=0` for existing installs. Enable only in a test deployment with
`MINDBATON_TEAM=1`, restart the host, then open **Team Baton** from the app. There is no personal-memory migration.
Production release remains gated on the multi-laptop rehearsal and restore verification described below.

## Host setup and invitations

1. Sign in to Mindbaton as an administrator and open Team Baton. Create a project and set its goals.
2. Generate a ten-minute invitation with a six-character code, displayed as `ABC-234` (uppercase letters and digits). Send the host's `/team.html` address and code to your teammate.
3. The teammate enters their name and the code in six boxes, or pastes the whole code. Approve the pending request in the project's Members panel.
4. Their browser receives a separate HttpOnly project session, valid for thirty days. They can read shared memory,
   publish reports and create project device credentials. They cannot reach personal memory or host administration.
5. Revoke one member to revoke all their devices and browser access. A new invite replaces the previous invite;
   Disable invite prevents new requests. Pending approvals also expire after ten minutes.

The project chooser shows a bento grid with measured health. Green means sharing is available;
yellow means the project is read only or optional AI summaries need attention; red means a
storage or connection check failed. Projects share one Team Baton host. Checks refresh every
ten seconds while the grid is visible and retain last-known details during an outage.
Missing project databases are never recreated by health checks or ordinary reads.

Each project has a permanent random ID and `<data>/projects/<id>/project.db`. Memberships, invite hashes, request
approvals and credential hashes live in `auth.db`. Project content, revisions, graph links, summaries, processing jobs,
AI caches and usage estimates live only in the project database. Identical message IDs in two projects stay independent.

Use HTTPS for access from another device. A TLS reverse proxy must connect from loopback; only its HTTPS header is
trusted. Alternatively, set `MINDBATON_TEAM_PRIVATE_CIDRS` to the exact peer ranges of an **encrypted** private network
(such as your WireGuard network). This is an operator assertion that transport is encrypted, not a way to secure a
plain LAN. HTTP loopback works for local development. Browser and coding clients also require an explicit private
network option when using remote HTTP. Avoid broad CIDRs and do not expose the backend port directly behind a proxy.

## Nearby servers

Opening **Join with an invite** automatically looks for other hosts on the **Mindbaton server’s LAN**.
The invitation form shows the current host; **Find nearby** opens an inline list of other hosts.
Close and reopen that list to check again. The six-box code input stays in the same invitation.
Open a discovered HTTPS host, enter its six-character invitation code, and wait for that host’s approval.
Discovery does not transfer sessions, credentials, invite codes, project names, or memory.
Announcements are unverified: confirm the displayed host address with your teammate before opening it.

Discovery starts with Team Baton. Set `MINDBATON_TEAM_DISCOVERY=0` and restart to disable it.
To let teammates open this host, set `MINDBATON_PUBLIC_URL=https://your-host.example` to its working HTTPS origin.
Hosts without an HTTPS origin appear as **HTTPS needed**; discovery does not bypass transport checks.
A loopback-only host without a public URL can search but does not advertise itself.

This uses a small Team Baton UDP protocol, not Bonjour/mDNS: IPv4 multicast `239.255.77.66`, UDP port `45837`,
TTL 1, three queries over two seconds, at most 32 results, with ten-second caching. Allow this traffic on trusted
LANs if the firewall blocks it. Discovery uses the server’s default interface. Guest Wi-Fi isolation, routed VLANs,
VPNs and Docker bridge networking can block multicast; use the direct invitation URL in those cases.
Opening a hosted page on a phone does not discover the phone’s own Wi-Fi network unless its Mindbaton server
is also on that network. No dependencies or browser network scanning are required.

## Codex and Claude Code

Download `team_client.py` from your host or use the copy in this repository. Python 3.9+ is enough; there are no pip
dependencies. Create a separate device token per client from the project's Connected clients panel.

```sh
python3 team_client.py --config project-device.json init --host https://mindbaton.example.com --project <project-id>
```

Enter the project token at the hidden prompt. Configuration and SQLite queue files are private to your OS user.
For encrypted private-network HTTP, add `--private-network` to `init`.

Install additional hooks without replacing unrelated configuration:

```sh
python3 team_client.py --config project-device.json install-hooks codex ~/.codex/hooks.json
python3 team_client.py --config project-device.json install-hooks claude ~/.claude/settings.json
```

Both clients run `SessionStart`, `UserPromptSubmit` and `Stop`. Review and trust the new hooks in the coding client.
Configuration backups are saved beside the edited file. The installer is idempotent; reinstalling the same definition
does not duplicate it. Do not install several project configurations on the same session: select one explicit binding.

**Every session starts Private.** Find its session ID in the coding client's session metadata or hook payload, then bind
that exact session to this configuration:

```sh
python3 team_client.py --config project-device.json bind codex <session-id>
python3 team_client.py --config project-device.json bind claude <session-id>
python3 team_client.py --config project-device.json watch
```

Keep `watch` running while the coding clients run. It resumes pending uploads after restart, retries with increasing
delays capped at a minute, and stops on revoked access. `Stop` also attempts delivery after capturing completed responses.
`UserPromptSubmit` stores the user prompt before requesting context. Context retrieval has a three-second retrieval deadline.
If offline, it injects a dated cached briefing or a clear no-context notice. `status`, `flush`, and `context` are available
as helper subcommands. `Ctrl+C` stops the watcher; restarting it resumes its durable queue.

The helper uses separate queue/cache databases for every host, project and credential. New credentials get new stores;
do not replace an old credential file until you have reviewed its pending work. Storage exhaustion reports a capture
error and rolls back only the new capture; existing pending work is retained. Protocol errors retain queued work for
review. Access revocation stops retries and invalidates briefing caches.

The adapters read only visible user and completed assistant text. Hidden reasoning, tool output, system messages and
marked `[team-baton]…[/team-baton]` context are excluded. Unknown transcript records fail with an explicit unsupported
format error. Codex transcript formats are not a stable interface; the synthetic supported-schema fixtures are in
`tests/fixtures/`. Adapters must be updated and tested when formats change. Source IDs are preserved where available;
Codex records without IDs use their append-only record positions.

Hook contracts: [official Codex hooks](https://learn.chatgpt.com/docs/hooks) and
[Claude Code hooks](https://code.claude.com/docs/en/hooks). Older clients without these lifecycle hooks can use the
project MCP endpoint directly; automatic capture/context requires a supported client version.

## Browser extension

Update the extension. Open an AI conversation, open the extension popup, expand **Connect a project**, and enter the
host address, project ID and a project device token. Grant access to that host. The popup explains whether external
processing is enabled. Connecting does not share anything yet.

Select a project under **Share this conversation**. Selection is explicit for the conversation URL and starts a new,
device-owned shared conversation. Selecting Private ends new project capture; already queued shared updates still sync.
Personal pairing and personal capture continue independently on Private conversations.

The existing readers cover ChatGPT, Claude, Gemini, Google AI Studio, Perplexity, DeepSeek, Grok, Copilot, Poe and Mistral,
including the extension's alternate ChatGPT and Copilot hosts. Both speakers are captured, with model information when
available. Stable site message IDs preserve edits; when a site exposes none, changed text becomes an additional visible
report instead of overwriting an uncertain source. Virtualized or off-screen text that is absent from the DOM cannot be
captured until visible. Previously shared content is never deleted when the page shows a shorter transcript.

Send and Enter retrieve project context before replaying one native Send click. The original user text is retained.
A draft edited while context is loading is left for you to send again. A missing or changed send control shows
**Automatic retrieval unavailable**; **Alt+M** inserts project context manually. A missing control is not proof that
automatic retrieval happened. Inspect the draft before using a newly changed site adapter.

Project uploads are saved in extension storage before delivery and acknowledged individually. Retry alarms survive the
service worker restarting; backoff is capped at a minute. The popup shows Private, Sharing with Project, Synced,
Pending upload, access errors, and context availability. Cached outage context is dated. A storage error preserves
existing pending work and shows a capture error. Extension storage is finite; it does not silently trim project queues.

## Project MCP and upload protocol

Use `https://mindbaton.example.com/team/<project-id>/mcp` with `Authorization: Bearer tb_…`. These credentials cannot be
used at `/mcp`, `/graph`, `/export` or host settings. There are exactly four project tools:

| Tool | Input | Result |
|---|---|---|
| `project_context` | Optional `query`, `since` revision | Roughly 2,000-token briefing, source references, project revision, summary coverage and recent messages. |
| `project_search` | Optional `query` or exact `sources` array | Shared messages/publications or exact revisioned supporting messages. |
| `project_publish` | `id`, `kind`, `content`, optional `sources`, `replaces` | Explicit report with history; the host alone agrees decisions. Reuse an ID to retry safely. |
| `project_handoff` | `query`, `teammate`, optional `since` | Task-specific extractive briefing; works without AI. |

Uploads use `POST /team/<id>/upload`:

```json
{
  "session_id": "client-created-session-id",
  "title": "Queue investigation",
  "ai": "Codex",
  "messages": [
    {
      "message_id": "client-created-message-id",
      "revision": 1,
      "speaker": "assistant",
      "content": "Discovery: uploads survive restart.",
      "timestamp": 1792240000,
      "model": "available-model-name",
      "branch": "available-branch"
    }
  ]
}
```

One request accepts at most 200 updates and one megabyte. Message identity is `(session_id, message_id, revision)`.
The authenticated device owns the session; member identity never comes from the body. Accepted data commits before
acknowledgement. Identical retries return acknowledgements without duplicates; conflicting content at the same revision
returns 409. Out-of-order revisions stay in history; only the highest becomes current. Shorter transcripts cannot delete
previous content. Clients remove work only after matching every acknowledgement.

## Optional external AI

External processing starts **off** for every project. The host selects a provider/model from existing Mindbaton settings,
a project monthly USD limit, and explicitly enables automatic processing. Existing host keys and the host paid-use cap
are reused. A project call uses only its selected provider/model; it never silently falls through to another provider.

Changed conversations batch after fifteen seconds of inactivity, with a maximum one-minute batching delay. One Team
Baton provider job runs at a time. Jobs and source revisions survive host restarts. Results are cached by project,
source versions, provider/model and prompt version. Structure and citations are validated before saving, and late
results cannot replace a newer source revision. Input is bounded; a long conversation's newest messages are summarized,
while all captured messages remain locally searchable. Local ranking considers the newest 2,000 matching messages. Summary coverage is reported by project revision.

Budget reservations are conservative estimates and persist before calling the provider, including interrupted/failed
calls whose billing is unknown. Usage is visible in the project interface. Provider timeout, quota, invalid JSON,
unsupported citations or exhausted budget leave local search and extractive handoffs working. Costs depend on provider
billing; set provider-side limits too. Free-provider estimates are zero, and do not cover a provider account with
billing enabled outside Mindbaton's paid-provider list.

AI output is marked **unverified AI**. A reported AI decision becomes a proposal, never an agreed decision. Progress is
reported, not verified work. The host can agree a decision or publish an explicit replacement with history. Conflicting
offline reports remain distinct publications for review. No scheduling or agent orchestration is performed.

## Export, backup and restore

The project host can export a JSON snapshot or save a backup in `<data>/project_backups/`. Export includes messages,
revision history, knowledge/links, summaries, processing jobs/cache and usage estimates, but excludes memberships and
credentials. Back up `auth.db` plus the entire data directory while the host is stopped to retain identities as well.

Restore a JSON export in the project list. It is validated before a new permanent project ID is allocated, and external
processing is disabled. Historical device IDs remain provenance; invite and provision clients again. Restore does not
merge with or overwrite an existing project. The upload limit for a restore is 50 MB. Archived projects stay readable
and reject new content/settings writes; access can still be revoked and snapshots exported.

## Verification and release gate

```sh
python3 server.py --check
python3 -m unittest discover -s tests -p 'test_team.py'
python3 bench.py
python3 docs_site.py --check
node tests/team_extension.cjs
node tests/team_browser.cjs
node tests/team_ui.cjs
```

Browser checks require an existing Playwright installation and Chromium. Set `PLAYWRIGHT_MODULE` to that module's path
when it is not on Node's normal search path. This is test tooling, not an app dependency. Synthetic fixtures cover every
host in the extension manifest and check capture, single Enter/click submission, rapid Enter, edited drafts, outage
notices and visible fallback. The UI check runs host approval, a project-only teammate, shared reports, archive and
desktop/mobile layout against an isolated synthetic host. These checks do not establish compatibility with every current authenticated live-site layout.

Before production enablement, rehearse with a host and at least two separate laptops: one Claude Code session publishes
a discovery and a Codex session receives it before its next response, then reverse the direction; repeat using each
supported browser site. Disconnect the host after an upload is saved but before acknowledgement. Restart clients,
restore the host, verify one update per revision and missed context recovery. Revoke a member, check all their devices,
and restore an exported project into a new test host. Keep the feature off until this rehearsal and restore review pass.

There is one authoritative host. During outages teammates can work with cached context and queue their reports; live
coordination is unavailable. Managed hosting, host election, task scheduling and agent orchestration are intentionally
outside this version.
