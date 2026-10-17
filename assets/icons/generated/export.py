"""Package ChatGPT-generated bento icons and small lossless WebP exports for the app."""
from pathlib import Path
import json
import zipfile
from PIL import Image

HERE = Path(__file__).resolve().parent
catalog = json.loads((HERE / 'catalog.json').read_text())['icons']
assert len(catalog) == 11, 'Expected exactly the 11 profile categories'
entries = []
for name, info in catalog.items():
    original = HERE / (name + '.png')
    prompt = (HERE / (name + '.prompt.txt')).read_text().strip()
    with Image.open(original) as image:
        assert image.mode == 'RGBA', (name, image.mode)
        assert all(image.getpixel(p)[3] == 0 for p in [(0, 0), (image.width-1, 0), (0, image.height-1), (image.width-1, image.height-1)]), name
        size = image.size
        # Keep the full-resolution originals; export only the size the cards need.
        image.thumbnail((192, 192), Image.Resampling.LANCZOS)
        exif = Image.Exif()
        exif[270] = 'ChatGPT image generation. Exact prompt: ' + prompt
        image.save(HERE / (name + '.webp'), 'WEBP', lossless=True, method=6, exif=exif)
    entries.append({'key': name, **info, 'original': name + '.png', 'app': name + '.webp', 'originalSize': size, 'prompt': prompt, 'generator': 'ChatGPT built-in image generation', 'transparent': True})
manifest = {'count': len(entries), 'scope': 'Mindbaton profile bento cards', 'icons': entries}
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
with zipfile.ZipFile(HERE / 'mindbaton-bento-icons.zip', 'w', zipfile.ZIP_DEFLATED) as bundle:
    for entry in entries:
        for suffix in ['.png', '.webp', '.prompt.txt']:
            bundle.write(HERE / (entry['key'] + suffix), entry['key'] + suffix)
    for filename in ['manifest.json', 'README.md', 'catalog.json', 'export.py']:
        bundle.write(HERE / filename, filename)
print('Exported 11 transparent icons. App WebP total:', sum((HERE / (name + '.webp')).stat().st_size for name in catalog), 'bytes')
