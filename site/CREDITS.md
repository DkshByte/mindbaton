# Credits

Everything on this site is made here or used under the licence below. It uses no third-party photos, stock images or 3D
models.

| What | Where | Licence |
|---|---|---|
| Archivo (variable, width and weight axes), `fonts/Archivo-Variable.woff2` | Omnibus-Type, https://github.com/Omnibus-Type/Archivo, via Google Fonts | SIL OFL 1.1, `fonts/LICENSE-Archivo.txt` |
| Fragment Mono, `fonts/FragmentMono-Regular.woff2` | Wei Huang, https://github.com/weiweihuanghuang/fragment-mono, via Google Fonts | SIL OFL 1.1, `fonts/LICENSE-FragmentMono.txt` |
| AI product logos in `icons/` (`*-color.svg`, `openai.svg`, `grok.svg`, `cursor.svg`, `windsurf.svg`) | LobeHub icons, https://github.com/lobehub/lobe-icons | MIT |
| `icons/github.svg`, `docker.svg`, `zedindustries.svg` | Simple Icons, https://simpleicons.org | CC0 1.0 |
| `icons/vscode.svg` | Devicon, https://devicon.dev | MIT |
| three.js r186 (`vendor/three.min.js`), Motion 13.4 (`vendor/motion.js`) | https://threejs.org · https://motion.dev | MIT, `vendor/LICENSE-*`. Kept in the repo; the current page loads neither. |

AI names and logos are trademarks of their owners. They appear only to say which apps Mindbaton works with. The page
shows them in one colour, as silkscreen on the panel, from the unmodified SVG files.

## Made here

- **The page** (`index.html`, `style.css`, `main.js`) is hand-written HTML, CSS and JavaScript with no dependencies. The
  front panel, the sockets, the receipt and the exploded diagram are CSS and inline SVG.
- **The hand-off packs** on the page are real output of the project's `handoff.py` on `demo.py`'s made-up person, Maya
  Haddad. The receipt is `handoff.build()` run on her ChatGPT chat "Relocating to Lisbon" with a 700-token budget and a
  blank last message that the page fills with what the visitor types. The pack under "One fact, followed" is
  `live.make_handoff()` on her Claude chat "Pantry onboarding flow" (1,500-token budget). Claude's reply after the hand-off
  is written for the page and is labelled as a demo.
- **`og.png`** is a 1200×630 screenshot of the page's first viewport, taken with headless Chromium.
- **`shots/*.png`** are screenshots of the Mindbaton app running on `demo.py`'s invented person.

Every PNG carries its origin in an `impeccable:prompt` text chunk
(`node embed-prompt.mjs <file> --read` from the Impeccable skill).

## Regenerating

- **Packs:** seed a scratch data dir with `MINDBATON_DATA=/tmp/mb-demo python3 demo.py`, then in Python (from the repo
  root, with the same `MINDBATON_DATA`) open Maya's graph with `server.open_data(server.DATA)` and `server.graph(<her id>)`
  and call the functions above. Paste the text into `index.html` (HTML-escaped) in the `#pack-hero` template and the
  "Read the whole pack" block.
- **`og.png`:** serve `site/` (`python3 -m http.server 3105 -d site`) and screenshot `http://127.0.0.1:3105/` at a
  1200×630 viewport.
