# Mindbaton bento icons

11 original icons generated with ChatGPT's built-in image generation tool for the profile bento cards: Who you are, Where, Building, Uses, Has, Learning, Likes, Dislikes, People, Wants and Related.

Warm ivory faces, graphite bevels and the category colors from the existing app. The PNG backgrounds contain real alpha transparency. Every original is retained with its exact prompt embedded and saved beside it; `manifest.json` records the full prompt set and filenames.

`index.html` is the gallery. `mindbaton-bento-icons.zip` contains the full-resolution PNGs, 192px WebP app exports, prompts, manifest and this guide. The app uses the WebP files in the card headings and their decorative corners; these images have empty alt text because the headings already identify the categories.

To rebuild the small app exports and ZIP after replacing a source PNG:

```sh
python3 assets/icons/generated/export.py
```

The export uses the already installed Pillow package. It resizes and losslessly encodes the generated artwork; it does not redraw it. The rest of the app continues to use its vector UI icons. Product logos and the Baton brand mark are separate assets.
