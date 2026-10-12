# #74 — Appearance and portraits manual QA

Use the existing isolated #78 loader; it creates a separate reproducible save:

```sh
RPG_DEV_TOOLS=1 python scripts/narrative_test_world.py --checkpoint appearance
```

Run the app against the loader's reported developer database. `base` is unchanged.
The `appearance` checkpoint extends `family`: Vera has canonical grey eyes and
shoulder-length hair. No portraits or appearance-derived Knowledge are seeded.
Use existing `newborn`, `newborn-twins`, `newborn-triplets` for #41 integration.

## Canonical changes

1. Inspect Vera's card, then start and make two ordinary turns. Grey eyes and
   hairstyle must remain unchanged after save/reload. Existing scene clothes stay
   unclassified legacy prose, never new permanent features.
2. Establish that Vera actually had a haircut. Check accepted Event + Fact,
   `appearance_deltas` with the existing hairstyle item ID/revision, and History.
   Hairstyle changes; eye colour does not. Merely planning a haircut changes none.
3. Establish a completed tattoo; verify one modification and one History change.
   A stated intention or unsupported source is rejected with a local diagnostic.
4. For Kirill (EXTERNAL), narration alone cannot decide a tattoo/haircut. Make the
   explicit choice in player input and establish completion; only then accept it.
   A grounded AUTONOMOUS Vera choice does not need Kirill's permission.
5. Ordinary injury does not create a scar. An explicitly established involuntary
   scar can affect Kirill. Functional loss uses a #38 condition reference; resolve
   that condition and verify no contradictory current appearance copy remains.
6. An off-camera change does not broadcast to unrelated NPCs. Acquire its Fact via
   a grounded witnessed observation or communication and then inspect that POV.
7. Regenerate the accepted turn, select an earlier variant, rollback and branch.
   No duplicate modification, stable source identity, independent branch state.
   Inspect milestones for persistent modifications; history is not in every prompt.
8. In newborn checkpoints, explicit birth appearance stays intact; unknown traits
   remain unknown. No parent phenotype copying. After an ordinary time advance,
   the same Character/profile survives without age-table cosmetic changes.

These tests require semantic assertions from a live model for manual story QA;
CI uses deterministic source records and never depends on a paid model.

## Portrait UI — desktop and mobile

1. Open any Character card. The pencil is the sole editing entry point. With no
   image the circular silhouette/initials is inert; no broken viewer opens.
2. Choose «Загрузить новый портрет». Test PNG, JPEG and WebP, portrait/square/
   landscape images. Preview, adjust horizontal/vertical position and zoom, then
   Cancel: neither revision nor attachments change. Repeat and Save.
3. Test invalid contents disguised as PNG, GIF/SVG, files >10 MiB, dimensions
   4097×256: reject without creating an attachment (impossible aspect ratio).
   Upload 255×256 → 256×257, 64×128 → 256×512, 5000×2500 → 4096×2048;
   verify full frame and proportions, LANCZOS output and the small-image quality
   warning before Save. Valid edges 256×256 and 4096×256 stay unchanged.
   Sources over 32 million pixels and decompression bombs are rejected before
   resizing; errors are HTTP 4xx. EXIF orientation is normalized before resizing.
4. Confirm the saved avatar is circular, not stretched, and the crop matches in
   the Character picker and genealogy. Reload: crop survives. Appearance text and
   Character Knowledge do not change on upload or edit.
5. Click avatar: full original, without circular crop, fits the viewer. Zoom and
   pan with mouse/touch; check keyboard access, Escape, explicit close and focus.
6. Pencil → «Изменить кадрирование»: save a new crop while preserving period,
   age bounds and original pixels. Verify that all shared consumers update.
7. «История портретов»: upload another period, select either entry, inspect the
   full original, set applicability/current default, replace and confirm removal.
   Replacement preserves the prior entry. Cancelling removal preserves it.
8. Assign a childhood portrait and inspect an adult canonical age: no automatic
   use as adult likeness; history retains it. Unknown age cannot satisfy explicit
   age bounds. With no applicable image the shared fallback appears.
9. Delete a current portrait; other eligible history may become current. Delete
   the last eligible image and verify fallback. Missing physical asset also falls
   back; no path or broken image icon is exposed.
10. Save/reload, ordinary turn, regenerate, variant selection, rollback and copied
    branch: original references/crops follow snapshots. Detachment on one branch
    does not erase another branch's original. A foreign save without a reference
    and a hidden newborn cannot fetch the asset, even with its exact UUID.
11. Check 360–412 px mobile and desktop, light/dark and themed skins: no horizontal
    page overflow; controls stay reachable. There is no phone UI or full redesign.

## Automated coverage

`tests/test_appearance.py` covers semantic/agency/CAS/history boundaries, stable
traits, conditions, newborns, migration, real jobs and rollback/regeneration.
`tests/test_portraits.py` covers decoding, authorization, transactions, selection,
periods, retention and independent branches/databases. `frontend/e2e/portraits.spec.ts`
covers the shared card editor/viewer and round-trip crop on desktop/mobile.
Run the full backend suite, frontend build and E2E before merge; see PR results.
