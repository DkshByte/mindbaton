# Credits

Everything on this site is made here or used under the licence below. It uses no third-party photos, stock images,
scripts or 3D models.

| What | Where | Licence |
|---|---|---|
| Geist and Geist Mono (variable), `fonts/Geist-Variable.woff2`, `fonts/GeistMono-Variable.woff2` | Vercel, https://github.com/vercel/geist-font | SIL OFL 1.1, `fonts/LICENSE-Geist.txt` |
| AI product logos in `icons/` (`*-color.svg`, `openai.svg`, `grok.svg`, `cursor.svg`, `windsurf.svg`, `opencode.svg`) | LobeHub icons, https://github.com/lobehub/lobe-icons | MIT |
| `icons/github.svg`, `docker.svg`, `zedindustries.svg` | Simple Icons, https://simpleicons.org | CC0 1.0 |
| `icons/vscode.svg` | Devicon, https://devicon.dev | MIT |

AI names and logos are trademarks of their owners. They appear only to say which apps Mindbaton works with, from the
unmodified SVG files: colour marks as they are, one-colour marks tinted with the text colour (as the app shows them).

## Made here

- **The page** (`index.html`, `style.css`, `site.js`) is hand-written HTML, CSS and JavaScript with no dependencies,
  in the app's own design system (`DESIGN.md`). The rows, answer card, chat card and chips are the app's components
  redrawn in HTML with the demo person's real data.
- **The docs** (`docs/`) are made by the repo's `docs_site.py` from `docs/*.md`, `SECURITY.md` and `CHANGELOG.md`;
  `docs.css` and `docs.js` are hand-written.
- **The brand** (`brand/`, `favicon.svg`, `favicon-32.png`, `apple-touch-icon.png`) comes from the repo's
  `assets/brand/`.
- **The hand-off pack** under "Pass the baton" is real output of `live.make_handoff()` (with what Mindbaton knows about
  the person, no AI summary) on `demo.py`'s made-up person, Maya Haddad: her Claude chat "Pantry onboarding flow",
  1,500-token budget. The recent memories and the "where do I live" answer are hers too.
- **`shots/*.png`** are screenshots of the Mindbaton app (1440×900 at 1.5×) running on `demo.py`, with the own model
  switched off (`MINDBATON_BRAIN=off`) and no AI keys.
- **`og.png`** is a 1200×630 screenshot of the page's first viewport, taken with headless Chromium.

## Regenerating

- **Shots:** `MINDBATON_DATA=/tmp/mb-demo python3 demo.py --password demo-pass-123`, then start the server with
  `MINDBATON_DATA=/tmp/mb-demo MINDBATON_AI=0 MINDBATON_BRAIN=off python3 server.py`, sign in as `maya` and screenshot
  You, Topics, Chats, Map (`app-graph.png`), Setup scrolled to Essentials, a chat's panel after Copy hand-off
  (`app-handoff.png`) and the signed-out screen (`app-login.png`).
- **Pack:** on the same server, `GET /handoff?session=Pantry+onboarding+flow&about=1&ai=0`; paste its `text`
  (HTML-escaped) into `#pack` in `index.html` and update the token count in its summary.
- **`og.png`:** serve `site/` (`python3 -m http.server 3105 -d site`) and screenshot `http://127.0.0.1:3105/` at a
  1200×630 viewport.
