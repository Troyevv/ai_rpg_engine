# Issue #86 — Inspector preservation and acceptance

Baseline: master `cd91e1b80b28ab0b74971889032341b20a385637`, including final #120/#121. Reference HTML SHA-256: `538a864e8ef320c8d10740bc832f25859f30d4c9357870d976a6f48f043b7ab0`.

## Before implementation: field/action inventory

| Original surface | Fields and actions retained | Destination |
| --- | --- | --- |
| Inspector header | World name, baseline version, save name, close | Sidebar identity, compact breadcrumb, return to story |
| Theme and metadata disclosures | All skins/auto mode, created/updated timestamps, save ID, tone, story rules, source Markdown download | Single world settings dialog |
| Seven SectionTabs | World, scene, characters, relations, secrets, threads, memory | One grouped desktop sidebar / mobile navigation sheet |
| Shared dossier width | sessionStorage `dossier-expanded` | Same preference, all Inspector sections; expanded/compact content width |
| Character shell | Alias/name search, nearby, previous/next, count, GM scope | Accessible searchable avatar selector and compact toolbar |
| CharacterDossier | Five tabs, all editors, portrait viewer/upload/crop/history, public DOB/family, conditions, appearance, possessions, motivations, directed relations, history | Unchanged #83 component inside new shell |
| Scene | Time, location, present IDs, full prose; PATCH /saves/:id/scene with revision, busy/error/success | Scene description, participants, context cards; explicit edit/save/cancel |
| World | Scene, all locations/descriptions, public facts and evidence | Overview hero, current scene, searchable location list, fact cards |
| Commitments | Description, participants, category/status/outcome, exact/window labels, condition, dependency IDs/descriptions, evidence | Bounded commitment cards; calendar link |
| SocialStateView | Public genealogy/kinship, objective relations/status/dates, life status/conditions/name history, residences and roles/orgs/status/certainty/dates, truncation | Overview social details and original genealogy entry |
| Directed relations | Canonical and legacy pairs, context, every numeric/qualitative dimension, change/reason | Direction-filtered pair cards; same existing authorized editor/API |
| Secrets | Secret fact text, known/suspected actors, evidence, original knowledge section | GM-labelled fact cards and source disclosure; no demo role switch |
| Threads | Description, state, status, participants, relevance order; legacy plans and original notes | Status/participant filters, bounded cards, development disclosure |
| Memory | Player-observed vs actor witness/known-source events, minute/turn, participants; nonsecret facts, actor knowledge/evidence/replacement, retired beliefs; legacy event fallback | Searchable timeline, facts/knowledge sidebar, kind/scope/participant filters |
| Legacy LLM memory | GM summary, per-actor summaries | Explicit archive disclosure |
| Other entry points | Calendar, genealogy, library, workshop, settings, reading, Tabletop, phone, current-game actions | Existing destinations retained; only Inspector-owned navigation changes |

## Navigation and state contract

Desktop: one left navigation, content beside it. Mobile: same destinations in the existing Radix navigation sheet. Inspector is a non-modal workspace, not a modal trapping focus away from its navigation. Dialogs remain modal for editing/settings. Escape closes the top dialog first, then returns from dossier to its source, then to the story. Game stays mounted and inert behind the workspace, retaining composer/reading state. Section filters, dossier tab and scroll survive navigation. Save/POV/access context changes remount Inspector state to discard stale restricted caches.

## Dependencies and intentional reference adaptations

No production dependency added. Existing Lucide (ISC), Radix Dialog, Skin System and shared avatars/dossier are reused. No prototype demo data, local fake editing, role switch, fake weather/history/progress or duplicate family graph. Actual relationship range is -100…100. Location parent links and weather use the existing projection when present; neither is reconstructed from prose. Active phone calls use the actor-owned phone projection and remain separate from physical participants. #83 dossier styling remains owned by #83. Skins retain their established palettes rather than forcing prototype hex values globally.

## Editing and back ownership

Scene PATCH retains the revision gate and server busy/error handling. An unchanged time label is sent as an empty `time` (the existing API's keep-current-time contract), avoiding re-parsing a campaign-relative display label when only location/presence changed. Explicit time edits still go through the same API. No backend production code changed.

Browser/Android Back while Inspector is open closes the top dialog, returns a contextual dossier to its source, then closes the workspace. Escape follows the same order. One same-document history entry belongs to Inspector; section switches do not create a history trail. Returning to the existing phone reuses its mounted device and drafts. Family remains mounted/inert beneath its dossier so graph/list position survives.

## Verification

See [design-qa.md](../../../design-qa.md) for visual comparison, [evidence index](issue86-evidence/README.md) for all screenshot pairs and recordings, and the PR for final commands/results. Screenshot assets are generated from real API saves through the existing test provider; the approved HTML is kept unchanged during reference capture. No external LLM credentials are needed.


Final acceptance: 112 same-size reference/application pairs (seven sections × four widths × two skins × two saved width preferences), interaction videos and the required desktop/mobile smoke. Final browser runs: 89 passed / 13 duplicate captures skipped; 28 passed / 4 duplicate captures skipped; final visual matrix 4 passed. Backend full suite and focused 15-test suite passed; production frontend build passed. See the linked QA report for exact commands, evidence and deliberate Skin/#83 adaptations.
