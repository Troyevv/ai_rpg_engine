# GenrePolicy (#110)

## Audit

Baseline master `d9617c7`, including merged #136 / #137. Creation already had
primary/secondary/custom genres; migration copied pacing/risk/expressiveness but
lost genre selections. Narrative received only legacy campaign genre text.
Director/pacing/initiative had no genre arbitration. Existing policy API,
transactional policy updates and recorded regeneration context are reused.
The issue's `docs/initial-world-v2.md` is absent on this baseline; actual contracts
are CreationSettings, migration and `manual_qa/narrative_v4/master-generator.md`.

## State and compatibility

`world_state.meta.genre` owns the configuration. `GenreConfig` is also the base of
CreationSettings: optional primary ID, up to three distinct secondary IDs, no
primary duplicate, custom text at most 2000 characters and nonblank when selected.
Unselected custom text is retained for editing but has no effect. Secondary-only
selections remain supporting accents without an invented primary. Empty is neutral.

Creation/import transfers the existing settings at migration. Missing canonical
configuration falls back to legacy campaign genre: an exact supported ID is reused,
other free text becomes primary `custom`, without guessing its meaning. Oversized
legacy text contributes its first 2000 characters; original metadata is retained.
Explicit neutral configuration prevents further legacy fallback. Previously lost
creation selections cannot be reconstructed from existing saves; retained campaign
text is used and the user can edit it in-game.

Migration copies current input without rewriting historical snapshots or SQLite
schema. Save/reload, rollback, variant selection and branching use existing
snapshot/history transactions. Regenerate uses recorded original context, including
original genres, even after edits. No parallel world state or scheduler is added.

## Context and examples

One `Genre / soft creative guidance` block goes through the shared Context Builder
to Narrative (ordinary/start/background/remote/long-term narrative). Legacy campaign
genre is omitted from the prompt to avoid conflicting instructions. Genre is excluded
from Extraction's state slice. Existing bounded `selection.genre_guidance` diagnostics
record the effective block. Schema limits bound it and existing context-budget/hard
limit checks account for its tokens. No additional model call is made.

Example primary romance / secondary drama:

```json
{"primary":{"genre":"romance","themes":"Nuanced relationships, dialogue and emotional subtext; attraction is never guaranteed."},"secondary":[{"genre":"drama","themes":"Conflicting values, difficult choices and their personal consequences."}]}
```

Primary thriller instead uses: `Uncertainty, suspense and consequential tension;
constant crime is unnecessary.` Custom preserves the user's text as themes.
The shared instruction emphasizes primary, treats secondary as supporting accents,
welcomes off-genre developments and quiet scenes, and never forces outcomes,
attraction or character decisions. It preserves canon, Knowledge, POV, agency,
personality, NPC initiative, pacing, risk and explicit constraints. Prompt language
does not change the configured game language.

Director is unchanged. There are no genre rankings, probabilities, event quotas,
eligibility tests, validators, warnings or post-hoc approvals. A valid mystery event
commits identically in romance and neutral worlds; invalid references remain invalid.

## API/UI

GET `/api/saves/{sid}/narrative-policy` includes `current.genre` and its schema.
PUT accepts genre with the existing pacing/risk/outcome fields and revision. Omitted
genre preserves it for older clients; explicit empty configuration clears it.
Invalid config returns 422, stale revision 409; existing idle protection remains.
Updates create no turn and rewrite no historical narrative.

World creation and the existing Policy dialog share GenreSettings, with ru/en labels
using `gameLocale()`. Inspector badges read active configuration instead of stale
creation text. Primary has explanatory text; secondary selections cap at three;
custom requires a description. Existing themes and responsive dialog remain in use.

## Reproducible QA

Use the existing #78 world, checkpoint `pacing`, in the isolated dev database:

```sh
RPG_DEV_TOOLS=1 python scripts/narrative_test_world.py --checkpoint pacing
```

Rerun for reset/new save. Current game → Settings → Story policy: choose romance
with drama/thriller, then custom; verify limits and nonblank input. Save/reload and
take an ordinary turn. Inspect `selection.genre_guidance`; history must be unchanged.
Switch to thriller and take another turn; regenerate an older turn and verify its
original genre context. Roll back and branch: restored snapshot owns genres.
POV switching must not transfer agency or reveal the QA private letter. Neutral
settings must produce no genre block.

Automated coverage is in `tests/test_genre_policy.py`: creation/import and legacy,
bounded/different guidance and main emphasis, identical Extraction prompts and
Director, off-genre acceptance, invalid-location rejection, revision/validation and
old-client compatibility, start → turn → save/reload → next turn, regenerate,
variant selection, rollback/branch and 15 further turns with exactly two model
calls each. Provider responses are deterministic, not live literary-quality evidence.

## Validation in this PR

- `python -m pytest tests/test_genre_policy.py tests/test_narrative_pacing.py tests/test_runtime_v3_context.py tests/test_runtime_v3_storage.py tests/test_runtime_v3_engine.py tests/test_narrative_authority136.py tests/test_npc_initiative.py tests/test_narrative_continuity.py -q`: 236 passed before four additional focused API/invalid-location cases were added.
- Final `python -m pytest tests/test_genre_policy.py -q`: 20 passed, including exact recorded context equality on regeneration.
- `python -m pytest tests/test_initial_draft_v4.py -q`: 17 passed.
- Frontend `npm test`: 45 passed; `npm run build`: passed (existing bundle-size warning).
- `PLAYWRIGHT_EXECUTABLE_PATH=/tmp/genre-browser/chromium npm run test:e2e -- genre-policy.spec.ts narrative-pacing.spec.ts calendar-creation.spec.ts --reporter=line`: 10 passed, desktop/mobile. Browser download failed; local Chromium 153 was used through the existing executable override.
- Visual inspection: 1440×1000 graphite and 393×851 parchment, compact two-column choices, no horizontal overflow; settings save/reopen and custom input covered by Playwright. Temporary screenshots/logs remain outside committed files; no video.

Limitations: no live DeepSeek run or claim of improved literary quality; primary
emphasis is a prompt preference, not a measurable guarantee. No full unrelated
Tabletop suite was run. Imported very long legacy genre text is bounded as described
above. Existing history and original source metadata are retained.
