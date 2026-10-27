# Inspector #86 — visual evidence

All reference/application pairs use identical CSS viewports and 900 px height, device scale factor 1. `expanded`/`compact` mean the persisted content preference. On phones the switch is hidden and the layout remains single-column; both preferences are captured by changing the width preference at 768 px and then returning to the target phone viewport. Default section/filter state is used. The reference's 32 px **demo-only** bar is intentionally absent in the application. Source screenshots preserve it, so vertical comparisons account for that offset.

Reference: the approved HTML, SHA-256 `538a864e8ef320c8d10740bc832f25859f30d4c9357870d976a6f48f043b7ab0`. Application: real `ui-inspector` save created through the supported import/confirm flow. Text, people and counts differ because demonstration records are not production data. Existing Graphite/Parchment Skin System palettes and #83 dossier are retained. Both full-resolution originals and paired contact sheets are linked below.

## Seven sections, desktop

### Мир

![Reference → application](pair-1440-graphite-world-expanded.jpg)

### Сцена

![Reference → application](pair-1440-graphite-scene-expanded.jpg)

### Персонажи

![Reference → application](pair-1440-graphite-characters-expanded.jpg)

### Отношения

![Reference → application](pair-1440-graphite-relationships-expanded.jpg)

### Тайны

![Reference → application](pair-1440-graphite-secrets-expanded.jpg)

### Сюжет

![Reference → application](pair-1440-graphite-threads-expanded.jpg)

### Память

![Reference → application](pair-1440-graphite-memory-expanded.jpg)

## Focused comparisons

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
| 1440×900 | graphite | expanded | Мир | [Pair](pair-1440-graphite-world-expanded.jpg) · [Reference](reference-1440-graphite-Мир-expanded.png) · [Application](after-1440-graphite-Мир-expanded.png) |
| 1440×900 | graphite | expanded | Сцена | [Pair](pair-1440-graphite-scene-expanded.jpg) · [Reference](reference-1440-graphite-Сцена-expanded.png) · [Application](after-1440-graphite-Сцена-expanded.png) |
| 1440×900 | graphite | expanded | Персонажи | [Pair](pair-1440-graphite-characters-expanded.jpg) · [Reference](reference-1440-graphite-Персонажи-expanded.png) · [Application](after-1440-graphite-Персонажи-expanded.png) |
| 1440×900 | graphite | expanded | Отношения | [Pair](pair-1440-graphite-relationships-expanded.jpg) · [Reference](reference-1440-graphite-Отношения-expanded.png) · [Application](after-1440-graphite-Отношения-expanded.png) |
| 1440×900 | graphite | expanded | Тайны | [Pair](pair-1440-graphite-secrets-expanded.jpg) · [Reference](reference-1440-graphite-Тайны-expanded.png) · [Application](after-1440-graphite-Тайны-expanded.png) |
| 1440×900 | graphite | expanded | Сюжет | [Pair](pair-1440-graphite-threads-expanded.jpg) · [Reference](reference-1440-graphite-Сюжет-expanded.png) · [Application](after-1440-graphite-Сюжет-expanded.png) |
| 1440×900 | graphite | expanded | Память | [Pair](pair-1440-graphite-memory-expanded.jpg) · [Reference](reference-1440-graphite-Память-expanded.png) · [Application](after-1440-graphite-Память-expanded.png) |
| 1440×900 | graphite | compact | Мир | [Pair](pair-1440-graphite-world-compact.jpg) · [Reference](reference-1440-graphite-Мир-compact.png) · [Application](after-1440-graphite-Мир-compact.png) |
| 1440×900 | graphite | compact | Сцена | [Pair](pair-1440-graphite-scene-compact.jpg) · [Reference](reference-1440-graphite-Сцена-compact.png) · [Application](after-1440-graphite-Сцена-compact.png) |
| 1440×900 | graphite | compact | Персонажи | [Pair](pair-1440-graphite-characters-compact.jpg) · [Reference](reference-1440-graphite-Персонажи-compact.png) · [Application](after-1440-graphite-Персонажи-compact.png) |
| 1440×900 | graphite | compact | Отношения | [Pair](pair-1440-graphite-relationships-compact.jpg) · [Reference](reference-1440-graphite-Отношения-compact.png) · [Application](after-1440-graphite-Отношения-compact.png) |
| 1440×900 | graphite | compact | Тайны | [Pair](pair-1440-graphite-secrets-compact.jpg) · [Reference](reference-1440-graphite-Тайны-compact.png) · [Application](after-1440-graphite-Тайны-compact.png) |
| 1440×900 | graphite | compact | Сюжет | [Pair](pair-1440-graphite-threads-compact.jpg) · [Reference](reference-1440-graphite-Сюжет-compact.png) · [Application](after-1440-graphite-Сюжет-compact.png) |
| 1440×900 | graphite | compact | Память | [Pair](pair-1440-graphite-memory-compact.jpg) · [Reference](reference-1440-graphite-Память-compact.png) · [Application](after-1440-graphite-Память-compact.png) |
| 1440×900 | parchment | expanded | Мир | [Pair](pair-1440-parchment-world-expanded.jpg) · [Reference](reference-1440-parchment-Мир-expanded.png) · [Application](after-1440-parchment-Мир-expanded.png) |
| 1440×900 | parchment | expanded | Сцена | [Pair](pair-1440-parchment-scene-expanded.jpg) · [Reference](reference-1440-parchment-Сцена-expanded.png) · [Application](after-1440-parchment-Сцена-expanded.png) |
| 1440×900 | parchment | expanded | Персонажи | [Pair](pair-1440-parchment-characters-expanded.jpg) · [Reference](reference-1440-parchment-Персонажи-expanded.png) · [Application](after-1440-parchment-Персонажи-expanded.png) |
| 1440×900 | parchment | expanded | Отношения | [Pair](pair-1440-parchment-relationships-expanded.jpg) · [Reference](reference-1440-parchment-Отношения-expanded.png) · [Application](after-1440-parchment-Отношения-expanded.png) |
| 1440×900 | parchment | expanded | Тайны | [Pair](pair-1440-parchment-secrets-expanded.jpg) · [Reference](reference-1440-parchment-Тайны-expanded.png) · [Application](after-1440-parchment-Тайны-expanded.png) |
| 1440×900 | parchment | expanded | Сюжет | [Pair](pair-1440-parchment-threads-expanded.jpg) · [Reference](reference-1440-parchment-Сюжет-expanded.png) · [Application](after-1440-parchment-Сюжет-expanded.png) |
| 1440×900 | parchment | expanded | Память | [Pair](pair-1440-parchment-memory-expanded.jpg) · [Reference](reference-1440-parchment-Память-expanded.png) · [Application](after-1440-parchment-Память-expanded.png) |
| 1440×900 | parchment | compact | Мир | [Pair](pair-1440-parchment-world-compact.jpg) · [Reference](reference-1440-parchment-Мир-compact.png) · [Application](after-1440-parchment-Мир-compact.png) |
| 1440×900 | parchment | compact | Сцена | [Pair](pair-1440-parchment-scene-compact.jpg) · [Reference](reference-1440-parchment-Сцена-compact.png) · [Application](after-1440-parchment-Сцена-compact.png) |
| 1440×900 | parchment | compact | Персонажи | [Pair](pair-1440-parchment-characters-compact.jpg) · [Reference](reference-1440-parchment-Персонажи-compact.png) · [Application](after-1440-parchment-Персонажи-compact.png) |
| 1440×900 | parchment | compact | Отношения | [Pair](pair-1440-parchment-relationships-compact.jpg) · [Reference](reference-1440-parchment-Отношения-compact.png) · [Application](after-1440-parchment-Отношения-compact.png) |
| 1440×900 | parchment | compact | Тайны | [Pair](pair-1440-parchment-secrets-compact.jpg) · [Reference](reference-1440-parchment-Тайны-compact.png) · [Application](after-1440-parchment-Тайны-compact.png) |
| 1440×900 | parchment | compact | Сюжет | [Pair](pair-1440-parchment-threads-compact.jpg) · [Reference](reference-1440-parchment-Сюжет-compact.png) · [Application](after-1440-parchment-Сюжет-compact.png) |
| 1440×900 | parchment | compact | Память | [Pair](pair-1440-parchment-memory-compact.jpg) · [Reference](reference-1440-parchment-Память-compact.png) · [Application](after-1440-parchment-Память-compact.png) |
| 768×900 | graphite | expanded | Мир | [Pair](pair-768-graphite-world-expanded.jpg) · [Reference](reference-768-graphite-Мир-expanded.png) · [Application](after-768-graphite-Мир-expanded.png) |
| 768×900 | graphite | expanded | Сцена | [Pair](pair-768-graphite-scene-expanded.jpg) · [Reference](reference-768-graphite-Сцена-expanded.png) · [Application](after-768-graphite-Сцена-expanded.png) |
| 768×900 | graphite | expanded | Персонажи | [Pair](pair-768-graphite-characters-expanded.jpg) · [Reference](reference-768-graphite-Персонажи-expanded.png) · [Application](after-768-graphite-Персонажи-expanded.png) |
| 768×900 | graphite | expanded | Отношения | [Pair](pair-768-graphite-relationships-expanded.jpg) · [Reference](reference-768-graphite-Отношения-expanded.png) · [Application](after-768-graphite-Отношения-expanded.png) |
| 768×900 | graphite | expanded | Тайны | [Pair](pair-768-graphite-secrets-expanded.jpg) · [Reference](reference-768-graphite-Тайны-expanded.png) · [Application](after-768-graphite-Тайны-expanded.png) |
| 768×900 | graphite | expanded | Сюжет | [Pair](pair-768-graphite-threads-expanded.jpg) · [Reference](reference-768-graphite-Сюжет-expanded.png) · [Application](after-768-graphite-Сюжет-expanded.png) |
| 768×900 | graphite | expanded | Память | [Pair](pair-768-graphite-memory-expanded.jpg) · [Reference](reference-768-graphite-Память-expanded.png) · [Application](after-768-graphite-Память-expanded.png) |
| 768×900 | graphite | compact | Мир | [Pair](pair-768-graphite-world-compact.jpg) · [Reference](reference-768-graphite-Мир-compact.png) · [Application](after-768-graphite-Мир-compact.png) |
| 768×900 | graphite | compact | Сцена | [Pair](pair-768-graphite-scene-compact.jpg) · [Reference](reference-768-graphite-Сцена-compact.png) · [Application](after-768-graphite-Сцена-compact.png) |
| 768×900 | graphite | compact | Персонажи | [Pair](pair-768-graphite-characters-compact.jpg) · [Reference](reference-768-graphite-Персонажи-compact.png) · [Application](after-768-graphite-Персонажи-compact.png) |
| 768×900 | graphite | compact | Отношения | [Pair](pair-768-graphite-relationships-compact.jpg) · [Reference](reference-768-graphite-Отношения-compact.png) · [Application](after-768-graphite-Отношения-compact.png) |
| 768×900 | graphite | compact | Тайны | [Pair](pair-768-graphite-secrets-compact.jpg) · [Reference](reference-768-graphite-Тайны-compact.png) · [Application](after-768-graphite-Тайны-compact.png) |
| 768×900 | graphite | compact | Сюжет | [Pair](pair-768-graphite-threads-compact.jpg) · [Reference](reference-768-graphite-Сюжет-compact.png) · [Application](after-768-graphite-Сюжет-compact.png) |
| 768×900 | graphite | compact | Память | [Pair](pair-768-graphite-memory-compact.jpg) · [Reference](reference-768-graphite-Память-compact.png) · [Application](after-768-graphite-Память-compact.png) |
| 768×900 | parchment | expanded | Мир | [Pair](pair-768-parchment-world-expanded.jpg) · [Reference](reference-768-parchment-Мир-expanded.png) · [Application](after-768-parchment-Мир-expanded.png) |
| 768×900 | parchment | expanded | Сцена | [Pair](pair-768-parchment-scene-expanded.jpg) · [Reference](reference-768-parchment-Сцена-expanded.png) · [Application](after-768-parchment-Сцена-expanded.png) |
| 768×900 | parchment | expanded | Персонажи | [Pair](pair-768-parchment-characters-expanded.jpg) · [Reference](reference-768-parchment-Персонажи-expanded.png) · [Application](after-768-parchment-Персонажи-expanded.png) |
| 768×900 | parchment | expanded | Отношения | [Pair](pair-768-parchment-relationships-expanded.jpg) · [Reference](reference-768-parchment-Отношения-expanded.png) · [Application](after-768-parchment-Отношения-expanded.png) |
| 768×900 | parchment | expanded | Тайны | [Pair](pair-768-parchment-secrets-expanded.jpg) · [Reference](reference-768-parchment-Тайны-expanded.png) · [Application](after-768-parchment-Тайны-expanded.png) |
| 768×900 | parchment | expanded | Сюжет | [Pair](pair-768-parchment-threads-expanded.jpg) · [Reference](reference-768-parchment-Сюжет-expanded.png) · [Application](after-768-parchment-Сюжет-expanded.png) |
| 768×900 | parchment | expanded | Память | [Pair](pair-768-parchment-memory-expanded.jpg) · [Reference](reference-768-parchment-Память-expanded.png) · [Application](after-768-parchment-Память-expanded.png) |
| 768×900 | parchment | compact | Мир | [Pair](pair-768-parchment-world-compact.jpg) · [Reference](reference-768-parchment-Мир-compact.png) · [Application](after-768-parchment-Мир-compact.png) |
| 768×900 | parchment | compact | Сцена | [Pair](pair-768-parchment-scene-compact.jpg) · [Reference](reference-768-parchment-Сцена-compact.png) · [Application](after-768-parchment-Сцена-compact.png) |
| 768×900 | parchment | compact | Персонажи | [Pair](pair-768-parchment-characters-compact.jpg) · [Reference](reference-768-parchment-Персонажи-compact.png) · [Application](after-768-parchment-Персонажи-compact.png) |
| 768×900 | parchment | compact | Отношения | [Pair](pair-768-parchment-relationships-compact.jpg) · [Reference](reference-768-parchment-Отношения-compact.png) · [Application](after-768-parchment-Отношения-compact.png) |
| 768×900 | parchment | compact | Тайны | [Pair](pair-768-parchment-secrets-compact.jpg) · [Reference](reference-768-parchment-Тайны-compact.png) · [Application](after-768-parchment-Тайны-compact.png) |
| 768×900 | parchment | compact | Сюжет | [Pair](pair-768-parchment-threads-compact.jpg) · [Reference](reference-768-parchment-Сюжет-compact.png) · [Application](after-768-parchment-Сюжет-compact.png) |
| 768×900 | parchment | compact | Память | [Pair](pair-768-parchment-memory-compact.jpg) · [Reference](reference-768-parchment-Память-compact.png) · [Application](after-768-parchment-Память-compact.png) |
| 393×900 | graphite | expanded | Мир | [Pair](pair-393-graphite-world-expanded.jpg) · [Reference](reference-393-graphite-Мир-expanded.png) · [Application](after-393-graphite-Мир-expanded.png) |
| 393×900 | graphite | expanded | Сцена | [Pair](pair-393-graphite-scene-expanded.jpg) · [Reference](reference-393-graphite-Сцена-expanded.png) · [Application](after-393-graphite-Сцена-expanded.png) |
| 393×900 | graphite | expanded | Персонажи | [Pair](pair-393-graphite-characters-expanded.jpg) · [Reference](reference-393-graphite-Персонажи-expanded.png) · [Application](after-393-graphite-Персонажи-expanded.png) |
| 393×900 | graphite | expanded | Отношения | [Pair](pair-393-graphite-relationships-expanded.jpg) · [Reference](reference-393-graphite-Отношения-expanded.png) · [Application](after-393-graphite-Отношения-expanded.png) |
| 393×900 | graphite | expanded | Тайны | [Pair](pair-393-graphite-secrets-expanded.jpg) · [Reference](reference-393-graphite-Тайны-expanded.png) · [Application](after-393-graphite-Тайны-expanded.png) |
| 393×900 | graphite | expanded | Сюжет | [Pair](pair-393-graphite-threads-expanded.jpg) · [Reference](reference-393-graphite-Сюжет-expanded.png) · [Application](after-393-graphite-Сюжет-expanded.png) |
| 393×900 | graphite | expanded | Память | [Pair](pair-393-graphite-memory-expanded.jpg) · [Reference](reference-393-graphite-Память-expanded.png) · [Application](after-393-graphite-Память-expanded.png) |
| 393×900 | graphite | compact | Мир | [Pair](pair-393-graphite-world-compact.jpg) · [Reference](reference-393-graphite-Мир-compact.png) · [Application](after-393-graphite-Мир-compact.png) |
| 393×900 | graphite | compact | Сцена | [Pair](pair-393-graphite-scene-compact.jpg) · [Reference](reference-393-graphite-Сцена-compact.png) · [Application](after-393-graphite-Сцена-compact.png) |
| 393×900 | graphite | compact | Персонажи | [Pair](pair-393-graphite-characters-compact.jpg) · [Reference](reference-393-graphite-Персонажи-compact.png) · [Application](after-393-graphite-Персонажи-compact.png) |
| 393×900 | graphite | compact | Отношения | [Pair](pair-393-graphite-relationships-compact.jpg) · [Reference](reference-393-graphite-Отношения-compact.png) · [Application](after-393-graphite-Отношения-compact.png) |
| 393×900 | graphite | compact | Тайны | [Pair](pair-393-graphite-secrets-compact.jpg) · [Reference](reference-393-graphite-Тайны-compact.png) · [Application](after-393-graphite-Тайны-compact.png) |
| 393×900 | graphite | compact | Сюжет | [Pair](pair-393-graphite-threads-compact.jpg) · [Reference](reference-393-graphite-Сюжет-compact.png) · [Application](after-393-graphite-Сюжет-compact.png) |
| 393×900 | graphite | compact | Память | [Pair](pair-393-graphite-memory-compact.jpg) · [Reference](reference-393-graphite-Память-compact.png) · [Application](after-393-graphite-Память-compact.png) |
| 393×900 | parchment | expanded | Мир | [Pair](pair-393-parchment-world-expanded.jpg) · [Reference](reference-393-parchment-Мир-expanded.png) · [Application](after-393-parchment-Мир-expanded.png) |
| 393×900 | parchment | expanded | Сцена | [Pair](pair-393-parchment-scene-expanded.jpg) · [Reference](reference-393-parchment-Сцена-expanded.png) · [Application](after-393-parchment-Сцена-expanded.png) |
| 393×900 | parchment | expanded | Персонажи | [Pair](pair-393-parchment-characters-expanded.jpg) · [Reference](reference-393-parchment-Персонажи-expanded.png) · [Application](after-393-parchment-Персонажи-expanded.png) |
| 393×900 | parchment | expanded | Отношения | [Pair](pair-393-parchment-relationships-expanded.jpg) · [Reference](reference-393-parchment-Отношения-expanded.png) · [Application](after-393-parchment-Отношения-expanded.png) |
| 393×900 | parchment | expanded | Тайны | [Pair](pair-393-parchment-secrets-expanded.jpg) · [Reference](reference-393-parchment-Тайны-expanded.png) · [Application](after-393-parchment-Тайны-expanded.png) |
| 393×900 | parchment | expanded | Сюжет | [Pair](pair-393-parchment-threads-expanded.jpg) · [Reference](reference-393-parchment-Сюжет-expanded.png) · [Application](after-393-parchment-Сюжет-expanded.png) |
| 393×900 | parchment | expanded | Память | [Pair](pair-393-parchment-memory-expanded.jpg) · [Reference](reference-393-parchment-Память-expanded.png) · [Application](after-393-parchment-Память-expanded.png) |
| 393×900 | parchment | compact | Мир | [Pair](pair-393-parchment-world-compact.jpg) · [Reference](reference-393-parchment-Мир-compact.png) · [Application](after-393-parchment-Мир-compact.png) |
| 393×900 | parchment | compact | Сцена | [Pair](pair-393-parchment-scene-compact.jpg) · [Reference](reference-393-parchment-Сцена-compact.png) · [Application](after-393-parchment-Сцена-compact.png) |
| 393×900 | parchment | compact | Персонажи | [Pair](pair-393-parchment-characters-compact.jpg) · [Reference](reference-393-parchment-Персонажи-compact.png) · [Application](after-393-parchment-Персонажи-compact.png) |
| 393×900 | parchment | compact | Отношения | [Pair](pair-393-parchment-relationships-compact.jpg) · [Reference](reference-393-parchment-Отношения-compact.png) · [Application](after-393-parchment-Отношения-compact.png) |
| 393×900 | parchment | compact | Тайны | [Pair](pair-393-parchment-secrets-compact.jpg) · [Reference](reference-393-parchment-Тайны-compact.png) · [Application](after-393-parchment-Тайны-compact.png) |
| 393×900 | parchment | compact | Сюжет | [Pair](pair-393-parchment-threads-compact.jpg) · [Reference](reference-393-parchment-Сюжет-compact.png) · [Application](after-393-parchment-Сюжет-compact.png) |
| 393×900 | parchment | compact | Память | [Pair](pair-393-parchment-memory-compact.jpg) · [Reference](reference-393-parchment-Память-compact.png) · [Application](after-393-parchment-Память-compact.png) |
| 360×900 | graphite | expanded | Мир | [Pair](pair-360-graphite-world-expanded.jpg) · [Reference](reference-360-graphite-Мир-expanded.png) · [Application](after-360-graphite-Мир-expanded.png) |
| 360×900 | graphite | expanded | Сцена | [Pair](pair-360-graphite-scene-expanded.jpg) · [Reference](reference-360-graphite-Сцена-expanded.png) · [Application](after-360-graphite-Сцена-expanded.png) |
| 360×900 | graphite | expanded | Персонажи | [Pair](pair-360-graphite-characters-expanded.jpg) · [Reference](reference-360-graphite-Персонажи-expanded.png) · [Application](after-360-graphite-Персонажи-expanded.png) |
| 360×900 | graphite | expanded | Отношения | [Pair](pair-360-graphite-relationships-expanded.jpg) · [Reference](reference-360-graphite-Отношения-expanded.png) · [Application](after-360-graphite-Отношения-expanded.png) |
| 360×900 | graphite | expanded | Тайны | [Pair](pair-360-graphite-secrets-expanded.jpg) · [Reference](reference-360-graphite-Тайны-expanded.png) · [Application](after-360-graphite-Тайны-expanded.png) |
| 360×900 | graphite | expanded | Сюжет | [Pair](pair-360-graphite-threads-expanded.jpg) · [Reference](reference-360-graphite-Сюжет-expanded.png) · [Application](after-360-graphite-Сюжет-expanded.png) |
| 360×900 | graphite | expanded | Память | [Pair](pair-360-graphite-memory-expanded.jpg) · [Reference](reference-360-graphite-Память-expanded.png) · [Application](after-360-graphite-Память-expanded.png) |
| 360×900 | graphite | compact | Мир | [Pair](pair-360-graphite-world-compact.jpg) · [Reference](reference-360-graphite-Мир-compact.png) · [Application](after-360-graphite-Мир-compact.png) |
| 360×900 | graphite | compact | Сцена | [Pair](pair-360-graphite-scene-compact.jpg) · [Reference](reference-360-graphite-Сцена-compact.png) · [Application](after-360-graphite-Сцена-compact.png) |
| 360×900 | graphite | compact | Персонажи | [Pair](pair-360-graphite-characters-compact.jpg) · [Reference](reference-360-graphite-Персонажи-compact.png) · [Application](after-360-graphite-Персонажи-compact.png) |
| 360×900 | graphite | compact | Отношения | [Pair](pair-360-graphite-relationships-compact.jpg) · [Reference](reference-360-graphite-Отношения-compact.png) · [Application](after-360-graphite-Отношения-compact.png) |
| 360×900 | graphite | compact | Тайны | [Pair](pair-360-graphite-secrets-compact.jpg) · [Reference](reference-360-graphite-Тайны-compact.png) · [Application](after-360-graphite-Тайны-compact.png) |
| 360×900 | graphite | compact | Сюжет | [Pair](pair-360-graphite-threads-compact.jpg) · [Reference](reference-360-graphite-Сюжет-compact.png) · [Application](after-360-graphite-Сюжет-compact.png) |
| 360×900 | graphite | compact | Память | [Pair](pair-360-graphite-memory-compact.jpg) · [Reference](reference-360-graphite-Память-compact.png) · [Application](after-360-graphite-Память-compact.png) |
| 360×900 | parchment | expanded | Мир | [Pair](pair-360-parchment-world-expanded.jpg) · [Reference](reference-360-parchment-Мир-expanded.png) · [Application](after-360-parchment-Мир-expanded.png) |
| 360×900 | parchment | expanded | Сцена | [Pair](pair-360-parchment-scene-expanded.jpg) · [Reference](reference-360-parchment-Сцена-expanded.png) · [Application](after-360-parchment-Сцена-expanded.png) |
| 360×900 | parchment | expanded | Персонажи | [Pair](pair-360-parchment-characters-expanded.jpg) · [Reference](reference-360-parchment-Персонажи-expanded.png) · [Application](after-360-parchment-Персонажи-expanded.png) |
| 360×900 | parchment | expanded | Отношения | [Pair](pair-360-parchment-relationships-expanded.jpg) · [Reference](reference-360-parchment-Отношения-expanded.png) · [Application](after-360-parchment-Отношения-expanded.png) |
| 360×900 | parchment | expanded | Тайны | [Pair](pair-360-parchment-secrets-expanded.jpg) · [Reference](reference-360-parchment-Тайны-expanded.png) · [Application](after-360-parchment-Тайны-expanded.png) |
| 360×900 | parchment | expanded | Сюжет | [Pair](pair-360-parchment-threads-expanded.jpg) · [Reference](reference-360-parchment-Сюжет-expanded.png) · [Application](after-360-parchment-Сюжет-expanded.png) |
| 360×900 | parchment | expanded | Память | [Pair](pair-360-parchment-memory-expanded.jpg) · [Reference](reference-360-parchment-Память-expanded.png) · [Application](after-360-parchment-Память-expanded.png) |
| 360×900 | parchment | compact | Мир | [Pair](pair-360-parchment-world-compact.jpg) · [Reference](reference-360-parchment-Мир-compact.png) · [Application](after-360-parchment-Мир-compact.png) |
| 360×900 | parchment | compact | Сцена | [Pair](pair-360-parchment-scene-compact.jpg) · [Reference](reference-360-parchment-Сцена-compact.png) · [Application](after-360-parchment-Сцена-compact.png) |
| 360×900 | parchment | compact | Персонажи | [Pair](pair-360-parchment-characters-compact.jpg) · [Reference](reference-360-parchment-Персонажи-compact.png) · [Application](after-360-parchment-Персонажи-compact.png) |
| 360×900 | parchment | compact | Отношения | [Pair](pair-360-parchment-relationships-compact.jpg) · [Reference](reference-360-parchment-Отношения-compact.png) · [Application](after-360-parchment-Отношения-compact.png) |
| 360×900 | parchment | compact | Тайны | [Pair](pair-360-parchment-secrets-compact.jpg) · [Reference](reference-360-parchment-Тайны-compact.png) · [Application](after-360-parchment-Тайны-compact.png) |
| 360×900 | parchment | compact | Сюжет | [Pair](pair-360-parchment-threads-compact.jpg) · [Reference](reference-360-parchment-Сюжет-compact.png) · [Application](after-360-parchment-Сюжет-compact.png) |
| 360×900 | parchment | compact | Память | [Pair](pair-360-parchment-memory-compact.jpg) · [Reference](reference-360-parchment-Память-compact.png) · [Application](after-360-parchment-Память-compact.png) |
