# #83 — Character dossier and genealogy

Base: `614c04fb60de46a5706259e446d67b4e146cb0ce` (master, includes merged PR #120).

## Audit and preservation matrix

The baseline was captured from the actual built app before editing. On 360 px the world title, metadata, section navigation and roster occupied most of the first viewport. The circular avatar and name appeared near the bottom; important context required scrolling. CharacterView had one long disclosure stack, no dossier tabs or width control. Genealogy already used React Flow/Dagre and authorized portraits, but node selection only offered recentering. Thumbnail-driven node heights were inconsistent with layout dimensions.

| Existing field/action or gate | Destination after #83 |
| --- | --- |
| World navigation, theme, source download, world/save metadata | Same Inspector entry point; compact spacing only in character panel |
| Search names/aliases, nearby filter, previous/next, roster select and index | Same Inspector controls |
| Protagonist, controlled actor, observer subject, GM-card distinction | Identity header and existing roster caption; no transfer of control |
| Current portrait/crop, silhouette + initials, original viewer, pencil, upload, history, age bounds, deletion | Shared PortraitControl/CharacterAvatar, all original APIs |
| Name, explicit sex, known age, birth date, location | Header and Overview; no inference from portrait/name |
| Status, situation, last known point, emotion/source sequence | Header and Overview |
| Transient physical_state | Overview, independent of conditions; blank = no data |
| Canonical conditions/effects/provenance, life status | Overview; resolved/cancelled conditions in History; new allowlisted read projection only |
| Role, appearance, biography, custom/unclassified fields | Overview cards; full prose expandable, never discarded |
| Traits, values, communication, habits, strengths, weaknesses, fears, preferences, temperament | Personality |
| Goals/intentions/obligations, MotivationEditor, lifecycle history/review flags | Personality; controlled actor edit gate preserved |
| Directed emotional relationships, numeric dimensions/reasons, change notices, RelationshipEditor | Relationships; original direction/permissions, no new scores |
| Residence/organization/role context and dates/status/certainty | Overview |
| Public family, canonical dates/outcomes, adoption/guardian/sibling/ancestor distinctions | Family preview and **the same** full Genealogy workspace |
| Name/appearance/value history | History |
| Known/suspected/outdated/refuted/replaced beliefs and evidence | History, original KnowledgeRows |
| Card notes/secrets, all original raw fields | History disclosures; existing server projection/GM policy unchanged |
| Narrative name links | Existing Inspector, reading anchor/composer preserved |
| Width, selected tab/character, local scroll | UI memory/session only, never WorldState |

Public kinship and birthdays from PR #120 supersede the older #83 secrecy language. Dossier details and portraits retain their separate authorization. A public family node without an authorized private card can be selected/recentered but does not fetch or open a private dossier. No speculative partner, child, or parent nodes are created. Public graph counts are not claims about private Knowledge.

## Implementation boundaries

- CharacterDossier uses reusable section/fact/empty-state primitives, existing SectionTabs with icons/roving focus, Radix Inspector/portrait dialogs, Motion tokens and Skin System variables.
- Five tabs: Overview, Personality, Relationships, Family, History. Compact panel is 440 px; expanded is capped at 900 px and available viewport. Mobile is full width. Width preference is sessionStorage; per-character/tab scroll is ephemeral.
- Backend `dossier.details` is an additive, disposable read projection on existing cards. Explicit sex uses the existing authorization function; condition text/restrictions/evidence require known provenance (or a controlled actor's unguarded record). Concealed NPC effects are never used to derive a visible limitation. The same condition-fact gate applies to the existing Knowledge subview and life-state summary, so hidden condition text cannot reappear through a fact or count. No schema/migration, runtime state, or historical snapshot changes.
- Family layout still derives only from `/genealogy` and `/genealogy-roots`. Fixed 184×176 nodes prevent portrait layout shifts; ancestry-aware presentation grouping avoids collapsing parents into children via lateral relationships. All original edge types/phases remain. Graph is bounded at 80 nodes; depth 1–6, fit, wheel/pinch pan/zoom, keyboard activation, list alternative and recentering remain read-only.
- UI locale follows `gameLocale()` and the existing presentation-label boundary. New dossier labels have RU/EN dictionaries; inherited editors retain their existing localization behavior.

## Dependency evaluation

Reused installed, lockfile-resolved `@xyflow/react` 12.12.0 and `@dagrejs/dagre` 1.1.8 (MIT), existing Radix Dialog 1.1.23 (MIT), lucide-react 0.468.0 (ISC), and framer-motion 12.43.0 (MIT). No dependency or lockfile change. React Flow already provides viewport/touch/keyboard primitives; Dagre is already used for multigeneration layout. Replacing these with custom pan/zoom or introducing ELK would add a second generic interaction/layout implementation without a demonstrated benefit. Tabs reuse SectionTabs; no separate Radix Tabs dependency or wholesale component migration.

Baseline production chunks: main 824.68 kB (gzip 252.91), lazy genealogy 230.15 kB (gzip 77.31). Final production chunks: main 836.91 kB (gzip 256.56), lazy genealogy 232.56 kB (gzip 78.28). Existing Vite >500 kB main-chunk advisory remains; genealogy stays lazy-loaded.

## Visual evidence

See [evidence index](issue83-evidence/README.md). Baseline and final captures use actual application screens and deterministic #78 developer fixtures. Test portraits are synthetic QA assets, never generated gameplay portraits. Mobile checks use Chromium touch/viewport emulation, not physical Android. The cloud browser could not reach the local test service; captures were produced by the repository's Playwright browser and opened for visual inspection.

## Validation

- `python -m pytest -q tests/test_character_dossier.py tests/test_life_social.py tests/test_public_family_directory.py tests/test_portraits.py tests/test_narrative_test_world.py tests/test_personality.py tests/test_knowledge_lifecycle.py tests/test_tabletop.py`: **186 passed**, 38.62 s on the final backend.
- `cd frontend && npm run build`: TypeScript + production build passed. No new dependency; existing main-chunk size advisory remains.
- `npm run test:e2e -- dossier.spec.ts dossier-states.spec.ts dossier-compact.spec.ts dossier-portraits.spec.ts runtime-handoff.spec.ts`: 22 distinct executed cases passed after the compact-width assertion was changed to wait for the existing transition; 4 duplicate viewport cases intentionally skipped in the mobile project. The compact cases were rerun in the regression command below. This covers five tabs, physical-state variants, sparse/restricted cards, long biographies/names, search and scroll restoration, keyboard, touch pinch, reduced motion, missing portrait files, editor/viewer, and graph retry.
- `npm run test:e2e -- dossier-compact.spec.ts completion-matrix.spec.ts inspector-ux.spec.ts family.spec.ts portraits.spec.ts motivation.spec.ts goals.spec.ts personality.spec.ts knowledge.spec.ts tabletop.spec.ts pr120-completion.spec.ts current-game.spec.ts`: 61 passed and 5 duplicate viewport cases skipped; two obsolete pre-#120 secrecy expectations failed. Updated them to assert public root discovery and selection. `npm run test:e2e -- current-game.spec.ts --grep 'calendar, genealogy'`: **2 passed**, 14.4 s. Final outcome: all 63 executed regression cases passed across this run and its targeted rerun, including all 10 Tabletop cases. File-name matching also includes `dossier-portraits.spec.ts`.
- Mandatory smoke on desktop and mobile: **Start Game → ordinary choice → persisted save with two turns → browser reload → next ordinary choice**. Both cases passed through the real job/API/storage/Runtime pipeline, with three durable turns and a larger revision. Narrative name link → dossier → Escape preserves the exact text anchor and composer draft.
- Backend also reconstructs the dossier through a fresh app/database connection and verifies unchanged persisted snapshot. Tabletop E2E includes a real server restart.

Playwright executable in this environment: `PLAYWRIGHT_EXECUTABLE_PATH=/root/.cache/ms-playwright/chromium_headless_shell-1193/chrome-linux/headless_shell`. Tests run against the built frontend via the repository's own `tests/e2e_server.py`. External model responses use the existing deterministic E2E provider; no live DeepSeek result or physical-device result is claimed. These are targeted suites, not a claim that every repository test was run.

## API and scope audit

Existing API ownership remains unchanged: `GET /api/saves/{id}` supplies disposable card projections; `GET /genealogy-roots` and `GET /genealogy?root_id=…&depth=…&limit=…` supply public family data. Portrait list/upload, asset access, crop/history PATCH and DELETE stay under `/saves/{id}/characters/{cid}/portraits`, with existing revision and authorization checks. Motivation and relationship edits still use their original revision-checked PATCH endpoints. No new mutation endpoint.

No changes to Narrative turn execution, canonical family rules, save schema, portrait storage, phone model, Tabletop rules, or #86/#72/#87. PR #120 remains the baseline for public kinship and birthdays.

## Visual review outcomes

Inspected actual browser screenshots, not only assertions. Corrected the global title-style collision, oversized empty personality disclosures, portrait pencil touch target, sex icon contaminating the accessible heading, retained scroll/selection, graph arc clipping, dense-tree minimum zoom, dark control hover, and graph viewport height. Nodes now have fixed geometry; fit includes the partner-arc margin. Keyboard and list navigation open the same dossier and return to the same tree. No horizontal overflow in the checked layouts.

The genealogy overview of a large family necessarily uses a small scale; users can zoom, change root/depth, or use the accessible list. The graph is capped at 80 real nodes; no fictional continuation nodes are created. The text notice explains truncation.

