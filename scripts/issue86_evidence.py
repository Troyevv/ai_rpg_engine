"""Build review pairs from unmodified browser screenshots (no visual retouching)."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1] / 'docs/manual_qa/narrative_v4/issue86-evidence'
SECTIONS = {'Мир': 'world', 'Сцена': 'scene', 'Персонажи': 'characters', 'Отношения': 'relationships', 'Тайны': 'secrets', 'Сюжет': 'threads', 'Память': 'memory'}


def main():
    rows = []
    for width in (1440, 768, 393, 360):
        for skin in ('graphite', 'parchment'):
            for state in ('expanded', 'compact'):
                for section, slug in SECTIONS.items():
                    stem = f'{width}-{skin}-{section}-{state}'
                    reference = ROOT / f'reference-{stem}.png'
                    implementation = ROOT / f'after-{stem}.png'
                    if not reference.exists() or not implementation.exists():
                        raise FileNotFoundError(stem)
                    with Image.open(reference) as a, Image.open(implementation) as b:
                        assert a.size == b.size == (width, 900), (stem, a.size, b.size)
                        # Half-size contact sheets for desktop, full CSS pixels on phones.
                        scale = min(1, 720 / width)
                        w, h = round(width * scale), round(900 * scale)
                        pair = Image.new('RGB', (w * 2, h + 26), 'white')
                        draw = ImageDraw.Draw(pair)
                        draw.text((10, 7), 'REFERENCE', fill='black')
                        draw.text((w + 10, 7), 'IMPLEMENTATION', fill='black')
                        pair.paste(a.resize((w, h)), (0, 26))
                        pair.paste(b.resize((w, h)), (w, 26))
                        name = f'pair-{width}-{skin}-{slug}-{state}.jpg'
                        pair.save(ROOT / name, quality=88)
                    rows.append(f'| {width}×900 | {skin} | {state} | {section} | [Pair]({name}) · [Reference]({reference.name}) · [Application]({implementation.name}) |')
    for skin in ('graphite', 'parchment'):
        pair = Image.new('RGB', (900, 812), 'white')
        draw = ImageDraw.Draw(pair)
        for i, (prefix, label, y) in enumerate((('reference', 'REFERENCE', 180), ('after', 'IMPLEMENTATION', 148))):
            with Image.open(ROOT / f'{prefix}-1440-{skin}-Персонажи-expanded.png') as im:
                draw.text((10, i * 406 + 7), label, fill='black')
                pair.paste(im.crop((250, y, 1150, y + 380)), (0, i * 406 + 26))
        pair.save(ROOT / f'detail-dossier-{skin}.png')
    intro = '''# Inspector #86 — visual evidence

All reference/application pairs use identical CSS viewports and 900 px height, device scale factor 1. `expanded`/`compact` mean the persisted content preference. On phones the switch is hidden and the layout remains single-column; both preferences are captured by changing the width preference at 768 px and then returning to the target phone viewport. Default section/filter state is used. The reference's 32 px **demo-only** bar is intentionally absent in the application. Source screenshots preserve it, so vertical comparisons account for that offset.

Reference: the approved HTML, SHA-256 `538a864e8ef320c8d10740bc832f25859f30d4c9357870d976a6f48f043b7ab0`. Application: real `ui-inspector` save created through the supported import/confirm flow. Text, people and counts differ because demonstration records are not production data. Existing Graphite/Parchment Skin System palettes and #83 dossier are retained. Both full-resolution originals and paired contact sheets are linked below.

## Seven sections, desktop

'''
    for section, slug in SECTIONS.items():
        intro += f'### {section}\n\n![Reference → application](pair-1440-graphite-{slug}-expanded.jpg)\n\n'
    intro += '''## Focused comparisons

[Dossier type, portrait and tab spacing — Graphite](detail-dossier-graphite.png) · [Parchment](detail-dossier-parchment.png). These are unscaled 900×380 crops from the originals, stacked with labels. The source crop starts 32 px lower to account for its demo bar.

## Recordings

- [Desktop navigation, character selector and editor draft](interaction-desktop.webm)
- [Mobile navigation, character selector and editor draft](interaction-mobile.webm)
- [Desktop Start → turn → save/reload → turn](smoke-desktop.webm)
- [Mobile Start → turn → save/reload → turn](smoke-mobile.webm)
- [Desktop family → dossier → family](family-return-desktop.webm)
- [Mobile family → dossier → family](family-return-mobile.webm)
- [Desktop browser Back](browser-back-desktop.webm)
- [Mobile browser Back](browser-back-mobile.webm)
- [Desktop remote call → existing phone](phone-return-desktop.webm)
- [Mobile remote call → existing phone](phone-return-mobile.webm)
- [Desktop filters and scene error/retry/save](scene-save-desktop.webm)
- [Mobile filters and scene error/retry/save](scene-save-mobile.webm)

`before-*` files record master before implementation. Numbered `after-*-0..4` files exercise the five unchanged #83 dossier tabs; these supplement the seven-section matrix.

## Complete comparison matrix

| CSS viewport | Skin | Width preference | Section | Evidence |
| --- | --- | --- | --- | --- |
'''
    (ROOT / 'README.md').write_text(intro + '\n'.join(rows) + '\n')
    print(f'{len(rows)} same-size reference/application pairs verified')


if __name__ == '__main__':
    main()
