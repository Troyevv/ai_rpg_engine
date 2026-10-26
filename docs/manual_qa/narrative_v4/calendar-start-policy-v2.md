# Calendar presets and author-controlled start — PR #116

This is the 2026-10-26 product decision supplied in
`codex_pr116_calendar_and_start_policy_v2_spec.md`. It supersedes only previous
requirements making successful semantic review mandatory. Issue #44 is not edited
or closed. The original release/live acceptance history remains valid historical
evidence; warning-start is not successful model review or successful live generation.

## Implementation contracts

- Start reruns canonical validation of the selected revision, including types,
  references, scene/time consistency and lossless Runtime migration. Semantic
  failed/stale/unreviewed/with-issues states require `accept_warnings` for that
  revision, not a new model call. Age prose disagreeing with a valid birth date is
  advisory at start; invalid dates and Runtime invariants still block.
- `stop_review` cancels the optional worker in the same SQLite transaction as
  selection and save, bumps its epoch, and signals its stream after commit.
  Immutable `draft_save` records bind decision/hash/revision and enforce idempotency.
  Pending requests/reservations remain unknown, not free. Late results cannot write
  a candidate or begin another paid stage under the old epoch.
- Calendar arithmetic remains the existing Gregorian/custom Runtime calendar.
  `CalendarProfile.regional` selects a pure bounded projection through the existing
  `calendar_range`, `nearby_calendar` and narrative Context Builder. It does not
  fabricate recurring month/day records for movable dates.
- Regional overrides are concrete-occurrence edits, explicitly labeled in UI.
  Identity uses country + explicit English source identity + original date, never
  UI locale. Deleted/renamed/moved occurrences survive reload, reapply, and country
  switches. Overrides are retained when a set is disabled. No implicit all-years
  rule editor is offered. `seasons_enabled=false` hides authored seasons without
  deleting their definitions.
- `authoring.calendar_presets` records ownership/selection. Apply is revision guarded
  and validates a copy before committing; previews do not write. Existing drafts
  require Apply; old saves are not silently enriched. New generation settings default
  to auto; imports and saved generation resumes retain their previous behavior.
- Standard server-owned calendar fields are excluded from primary prompt schema.
  Primary token/context settings are unchanged. Existing per-stage bounded output
  policy remains; no automatic thinking/model switch was introduced.
- DOB completion groups only explicit ID-linked twin relations or existing twin
  groups, uses joint candidate sets, preserves manual/explicit dates and ordinary
  siblings, and avoids inferring same-day birth from midnight/uncertain prose.
  Contradictory automatic twins are recalculated by Python before model review.
- No SQLite schema migration. Optional profile defaults are omitted on serialization
  so legacy calendars retain their shape. Authoring manual paths now persist in the
  confirmed snapshot and ordinary-turn/reload path.

## Supported rules and limitations

Pinned `holidays==0.87`, adapter version `holidays-0.87-v1`; PUBLIC category;
explicit `en_US` names (documented fallback, independent of UI/machine locale).
Application coverage: **2025–2030**. Other dates remain playable with a coverage
warning and custom dates. This is not a production/workday calendar; future one-off
legislation is not promised. A saved rules-version mismatch produces a warning,
not a silent recalculation with a different library. No network at runtime.

| UI group | Countries | 2026 fixed control besides January 1 |
| --- | --- | --- |
| Россия | RU | June 12 |
| Европа | DE, FR, GB, IT, ES, PL | October 3; July 14; December 25; June 2; October 12; November 11 |
| Америка | US, CA, MX, BR, AR | July 4; July 1; September 16; September 7; July 9 |

Subdivisions are the exact codes exposed by the pinned source, including GB's
ENG/NIR/SCT/WLS and German states. Unsupported codes are rejected rather than
expanded to all regions. Category-specific local/religious variants are not claimed
as comprehensive regional coverage (e.g. predominantly Catholic municipalities).
National sets alone are not full province/state employment calendars.

Independent controls: GB/ENG Easter Monday **2026-04-06**, **2027-03-29**;
Boxing Day **2026-12-26** versus observed **2026-12-28**; German BY includes
Epiphany **2026-01-06**, BE does not. Seasons are the selected three-month game
convention (March/June/September/December boundaries), not climatic inference.
Russia/Moscow auto resolves RU/north; country-only tropical/ambiguous locations
and alternate worlds do not inherit arbitrary real-world seasons/holidays.

Primary/source references checked or used as upstream provenance:

- Adapter API and documented `get_list` for multiple names on one date:
  https://holidays.readthedocs.io/en/latest/api/
- Pinned source/catalog and country-specific provenance:
  https://github.com/vacanza/holidays/tree/v0.87/holidays/countries
- Independent movable/observed controls: https://www.gov.uk/bank-holidays
- BY: https://www.stmi.bayern.de/staat-und-verfassung/feiertage/
- BE: https://www.berlin.de/tourismus/infos/1887651-1721039-feiertage-schulferien.html
- Seasonal convention: https://www.noaa.gov/stories/whats-difference-between-meteorological-and-astronomical-seasons

The national fixed-date matrix is a code regression control, not a claim that
all local legal rules, years or country datasets were independently audited.

## E5 and verification

Fixture `tests/fixtures/initial_world/generation_response_e5.json` is byte-identical
SHA-256 `62ac12d4a812f517a26bddb56aaaadf527cdb2977f6c9fa1a87fef921c7a74a7`, candidate 71.
The local replay binds export metadata to a new test workspace/job/epoch but does
not change candidate contents, original responses, pending reservations or manual
edits. It tests stopped and in-flight review variants, no generation/review calls,
confirm → start → turn → SQLite reopen → next turn. Gameplay replies are controlled.
19 characters, DOB/manual paths, October 23 at 18:00 and source snapshot are checked.
Calendar Apply separately asserts entire characters/world/Knowledge equality.

Regression modules: `test_calendar_start_policy`, `test_calendar_v2`,
`test_generation_calendar`, prior draft/review/recovery/release suites.
`calendar-policy.spec.ts` covers Player warning/start, Author preview/apply/edit,
Quick/Scenario settings and overflow on desktop/mobile, with screenshots.
Older tests expecting a semantic veto now check advisory state or explicitly
acknowledge warnings. Technical rejection assertions remain active.

Local Chromium downloads returned invalid/truncated archives; local browser success
is not claimed. CI results must be read for the published commit. Live DeepSeek calls:
**zero**; no key or paid budget was supplied. Passing controlled gameplay is not live
model-quality acceptance. Final counts/SHA/CI links belong in the PR delivery report.

## #78 manual QA extension (existing fixture, no second game world)

Keep the existing `base` checkpoint stable. Use the existing #78 fixture loader with
an isolated dev DB, open its ordinary Narrative save and its canonical calendar API.
For UI authoring checks import its existing export into a draft; choose a Gregorian
start date in 2026, apply RU/north, then US with north unchanged. Add a personal date;
rename/delete a concrete public occurrence. Preview 2026 and 2027 (GB/ENG Easter
control above), confirm with any truthful warning, play a turn and reload. Branch or
rollback the ordinary turn through the existing history UI: calendar source/version,
custom dates, overrides and season choice must remain identical. No holiday should
assign a job, vacation, commitment or player action. Player View must show only the
safe warning and public calendar; raw review evidence stays in Author View.
For custom calendars select none/custom and verify existing authored seasons survive
while disabled. Never modify the user's E5 evidence for this checklist.
