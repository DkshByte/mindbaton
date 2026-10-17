# Mindbaton UI icons

54 original SVG icons for profile bento cards, sidebar navigation, memory, actions, Setup and Team Baton. Authored for Mindbaton's existing graphite interface: 24 × 24 canvas, 1.6px strokes, rounded joins and caps, and transparent backgrounds. They use `currentColor`; category hues and all three themes remain owned by the app.

Open `/assets/icons/ui/index.html` in the running app to inspect the family at 16, 24 and 48px, see the profile bento treatment, switch themes, and download individual SVGs or the ZIP.

`icons.json` is the source. Rebuild after editing it:

```sh
python3 assets/icons/ui/build.py
```

- Individual SVGs: `assets/icons/ui/<name>.svg` (accessible image name included).
- Inline app strings: `MindbatonIcons.<name>` from `icons.js` (decorative, `aria-hidden`).
- Static markup: `<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><use href="/assets/icons/ui/sprite.svg#place"/></svg>`.
- Standalone images: `<img src="/assets/icons/ui/place.svg" alt="Location">`. For CSS-controlled colors, use inline SVG or the sprite; external images do not inherit a page's text color.
- Export: `mindbaton-ui-icons.zip` contains the 54 SVGs, sprite, runtime, source, generator and this guide.

Keep visible labels on navigation and profile cards. An icon-only button needs an accessible action name on the button. The large bento watermark is decorative, so it may have low contrast; it does not replace the title or small category icon.

The app, Team Baton and shared select controls use this family. Provider/product logos, the Baton mascot, the extension and the public marketing site are separate systems.

References consulted before authoring: [Lucide's icon selection guide](https://github.com/lucide-icons/lucide/blob/main/docs/how-to/icon-guide.md), [Lucide](https://lucide.dev/), [Phosphor](https://phosphoricons.com/), and the existing `DESIGN.md` / `PRODUCT.md`. These are original geometry, with no copied third-party icon assets or new dependencies. Repository license applies.
