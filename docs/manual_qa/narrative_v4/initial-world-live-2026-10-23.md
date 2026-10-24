# Bounded live DeepSeek assessment — 2026-10-23

PR #105 / Issue #44 remains **Draft, incomplete**. This report supersedes earlier
statements that no live-provider assessment was available. Passing schema checks
and CI does not imply preservation of every circumstance or creative quality.

## Method and budget

Three existing-workspace scenarios, sequential `deepseek-flash`, thinking off,
temperature 0.7, using real Preparation/provider/checkpoint code and real game
engine. Author edit/confirm went through FastAPI; browser regression is separate,
with deterministic fixtures. No fourth scenario was created.

Before every paid call, the harness reserved a conservative peak/no-cache cost
using UTF-8 prompt bytes plus 4,096 protocol tokens and the full output cap. It
rejected dispatch above $3. Reservations were never released. A mutex prohibited
parallel paid generation. Each job/unit was capped at three total attempts,
including selective regeneration; no fresh retry allowance bypassed that cap.
Provider usage was recorded for every dispatched chat request. Missing usage
would have stopped further requests. The credential was read via echo-disabled
stdin into memory; no credential was put in a file, command argument, prompt,
repository or report. SQLite was checked for its absence after game execution.

| Calls | Requests | Input tokens | Output tokens | Estimated USD |
| --- | ---: | ---: | ---: | ---: |
| Short world | 22 | 145,623 | 42,783 | 0.040513698 |
| Medium world | 24 | 175,727 | 36,854 | 0.040154778 |
| Complex world | 16 | 160,808 | 38,285 | 0.044345064 |
| Start Game / ordinary play | 7 | 138,106 | 4,836 | 0.019572060 |
| **Total** | **69** | **620,264** | **122,758** | **0.144585600** |

Total tokens: **743,022**, including **150,400 input cache hits**. Maximum cumulative
reservation: **$1.8167493**, below $3. Costs are calculated estimates from returned
usage and the published Flash off-peak tariff ($0.15/M cache-miss input,
$0.003/M cache-hit input, $0.60/M output), not a billing statement. All charged
calls occurred in that UTC tariff window. Pricing source:
https://api-docs.deepseek.com/quick_start/pricing/ .

There were also four non-generation `/models` probes (three unauthenticated, one
authenticated). One local SDK construction failed before dispatch because this
environment's SOCKS proxy required `socksio`; that attempt is not a paid request
and has no fabricated token count. The environment dependency was installed only
in the test virtualenv. Paid requests stopped after these measurements.

## Observed outcomes

### Short: Ilya moves to Moscow and joins a research institute

**Incomplete.** Interpretation, creative roster and several batches were retained
across failed/resumed work. Real output exposed wrong-batch character IDs,
unregistered places, redundant Gregorian month tables, arbitrary Knowledge keys
and an organization used as a `coworker` endpoint. The latter is a genuine
character-only relation invariant; the application did not reinterpret an
organization as a character or remove the relation to force success.

Some units reached the conservative three-call cap. No fourth call, new world or
manual rewrite of accepted checkpoints was used to turn this into a success.
Canonical publication, editor confirmation and Start Game were not reached.

### Medium: institute, partner company, colleagues and shared history

**Generation, canonical validation, author edit, confirmation, save/reload and
real Start Game passed after local fixes and selective regeneration.** Four
characters, twelve locations and four organizations were assembled. Opening was
Monday 09:00 without inventing a calendar date. Characters had distinct research,
management and social motives/voices.

A source-filter defect initially made Nina an institute employee rather than a
manager of Kontur: the correct mixed employment/acquaintance note was in the
`relationship` section and had been excluded from her character context. After
fixing linked-note routing, only the secondary batch and dependent life/lore/
opening work were regenerated; accepted core/setting/places remained intact.

The first Start Game Extraction failed `scene_transition_evidence`; Runtime
correctly rejected unsupported transition evidence. Retrying only Extraction
succeeded, reusing the accepted narrative. No temporal/evidence guard was changed.

**Quality limit:** the generated Ilya had an unrequested adaptation goal. The
existing prompt prohibition was insufficient; this is not certified player-agency
compliance. There was no additional real ordinary turn in this scenario.

### Complex: Volkov family, Apex, adoption, secrets and chronology

**All sixteen provider units completed on first attempt**, followed by canonical
assembly, author edit, confirmation and reload. Real Start Game and one ordinary
turn (explicit player action: look out the window and check the clock) both
completed and saved. Tuesday 09:00, an unspecified calendar date, and Ilya's
rented apartment were preserved. Ilya's canonical goals/intentions were empty.
NPC biographies, motives and voices differed. The parents' hoped-for marriage was
represented as a secret plan, not an engagement or marriage. Adoption truth was
known to the parents/Ilya and not to Timur/Katya. These are observations, not an
exhaustive proof of secrecy under every future POV.

Both saves were reopened through a fresh Repository after play and passed
canonical normalization without state changes. Medium Start Game ended at 09:03;
complex Start Game plus the explicit ordinary turn ended at 09:07.

**Quality failures:** the five explicitly required subsidiaries were absent;
Apex's profile invented different business areas. The organization note existed
in Blueprint but was excluded from planning context, before places could allocate
new entities. Planning scope now includes organization/location/residence/opening
notes, with a regression and explicit unnamed-subsidiary guidance. This last fix
has **not** been rerun against DeepSeek: the complex run had already been published
and author-edited. The existing completed-job API does not permit reopening it
for checkpoint regeneration; no database bypass or fourth scenario was used.

Adoption was unnecessarily narrowed from childhood to infancy. Sergey was also
assigned awareness of yesterday's conversation without explicit evidence of that
additional knowledge. These require author correction and further quality work.
A future assessment must also verify consistency between accepted organization
profiles and lore. The final fix supplies accepted places and organizational source
notes to lore; this was previously missing and is not yet live-retested.

## Changes made from real failures

- Request-local schemas restrict character batches to assigned IDs/names,
  places to the accepted roster, and references to appropriate entity kinds.
  Immutable captured prompts are not rewritten.
- Places validate registered identities and parent references before costly
  character generation. Organization `description` prose is retained in canonical
  `context` rather than silently ignored.
- Explicit card-label aliases map to existing Russian labels and Runtime
  Personality fields. Explicit secret-labelled card prose becomes a secret Fact,
  without fabricating a Knowledge holder or date.
- Knowledge and emotional relationship keys derive from their canonical endpoint
  pairs; duplicate pairs still fail. Ties reject organization endpoints early.
- Unsupported numeric relationship labels are retained verbatim as unclassified
  context, never guessed into canonical dimensions or rescaled. Canonical range
  and dimension checks remain strict.
- Reverse duplicates of one symmetric active relation collapse only when all
  structural metadata agrees, preserving both context/evidence texts. Conflicting
  chronology still rejects; directed adoption/parent links are unchanged.
- Exact redundant Earth month tables and consistent exact-time/day-period pairs
  normalize without altering the clock. Invalid/custom calendars and conflicting
  time assertions still reject. Camera membership is completed only from an
  already accepted controlled actor at the same location; no movement is invented.
- Character contexts and dependency scopes now include all linked Blueprint notes,
  including employment/Knowledge notes tagged under another section. Planning
  receives circumstances necessary to allocate organizations and locations.
- Lore receives accepted organization/location profiles and the relevant source
  notes, rather than reconstructing businesses from names. Its existing dependency
  through life already invalidates lore after place changes; captured unit
  definitions and completed checkpoints need no rewrite.
- The prior appearance fix was exercised by real outputs: natural hair color and
  hairstyle used valid category/kind combinations. Clothing remains descriptive
  prose; no unsupported structural clothing kinds were introduced.

No Runtime files, temporal guards, DB schema or historical saves were changed.
Canonical normalization and validation still follow these generation adapters.
Previously captured scope artifacts remain historical; new scopes are derived
when interpretation is assembled/revised, not silently backfilled into a save.

## Verification and remaining work

Final local verification:

- `python -m pytest tests -q`: **1619 passed in 219.48s** after the final lore-context fix.
- Frontend `npm run build`: passed, with the existing bundle-size advisory.
- Frontend `npm run test:e2e`: **204 passed, 10 skipped in 11.7m**. The ten skips
  are existing mobile-project exclusions; no assertions, skips or timeouts changed.
- After the last lore-context edit, a fresh backend ran
  `npm run test:e2e -- world-generation.spec.ts`: **18 passed in 38.7s**.
- `git diff --check`: passed. No live credentials or model requests enter CI tests.

These cover schema boundaries, lossless normalization, strict rejection, source
routing, checkpoint recovery and existing game/history behavior. Results are local
verification, not a claim about a completed GitHub Actions run.

Remaining acceptance evidence:

1. Complete the short live scenario under an explicitly authorized future test
   allowance; the current attempt caps must not be reset silently.
2. Verify the subsidiaries/planning and lore-context fixes with real output,
   including preservation of accepted organizational descriptions.
3. Improve preservation of explicit conditions: controlled-actor goals, precision
   of adoption chronology and knowledge of conversations remain model weaknesses.
4. Repeat live editor/play checks after those changes. Regenerate/rollback/branch,
   restart recovery and all entry modes have deterministic coverage, not a full
   live-provider matrix in this assessment.

**Do not close #44 or mark #105 ready based on this run.** Two playable worlds are
positive integration evidence; they do not meet the requested stable three-scenario
quality criterion.
