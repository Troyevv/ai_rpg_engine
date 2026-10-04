# Narrative runtime and skins

Normal turns use narrative + extraction only. Context selects bounded canonical
history; old prose memory remains an archive and is not sent as current truth.
Legacy compactor code remains available for old tooling, outside the turn pipeline.

## Persisted changes

- `meta.calendar`: passage start minute, starting weekday, optional future date.
  Absolute `world_time` stays monotonic. Day numbers count midnight boundaries from
  the passage start, so a Thursday start is Day 1.
- Character goals, intentions and obligations: stable ID, text, lifecycle status,
  evidence, source sequence and optional due minute. Completed records remain in
  canonical snapshots; the existing string-list UI projection contains active items.
- Explicit emotion retains its source sequence and is shown as the last declaration.
- Scheduled events can specify `interrupts` and `location_id`; arrival events at
  the waiting location can satisfy an explicitly named wait.
- `last_time_skip` contains requested/actual duration, interruption and simulation
  diagnostics. It is part of the variant snapshot and cleared by the next normal turn.

The transactional `runtime_v3_lifecycle_calendar` migration updates saves, turns,
variants, archives, actor switches and persisted job snapshots. Legacy strings become
active entities with deterministic IDs. No past completion is guessed. For old saves,
the earliest retained turn anchors the calendar; if no turn survives, current time
is the only recoverable anchor. The original v3 migration marker is retained.

## Time skips and evidence

Manual skips and explicit Russian sleep/wait/travel/long-action/skip phrases share
one deterministic domain, with a maximum interval of seven days. Unspecified sleep
has no invented large duration. Interruptions use established scheduled causes;
there is no random drama generator. Ambiguous phrases are not guessed.

Long skips rank and group established causes, with at most six groups in one pair
of background LLM requests (plus the existing bounded repair policy). Normal turns
keep the existing one-background-scene policy. Hidden simulation cannot publish
notifications or grant knowledge to the player's present scene.

Lifecycle completion uses conservative evidence checks. Unsupported paraphrases may
remain active instead of silently closing an unrelated item. Explicit affirmative
replies can finish an existing answer intention with a uniquely identified present
interlocutor; the promised future action remains active. Current location is owned
by final_scene; situation may also derive from its explicit situation_evidence.

## UI

The Time Skip sheet, lifecycle archive, localized directional relationship changes,
notification queue and diagnostic counts use existing game/variant APIs. Live notices
require a newly committed submitted job; reload, playback and regeneration do not
replay them. New relationship dimensions have no fictitious zero baseline.

Sixteen skins plus the old Neon alias compose base geometry, decoration and accent.
Tokens cover typography, surfaces, borders, spacing density, inputs, buttons, dialogs,
messages and notifications. Decoration is non-interactive and reduced on mobile.

## Verification

- Full backend suite before the final reply-specific guard: 667 passed.
- Final runtime/lifecycle/time/notification/agency targeted suite: 55 passed.
- Production frontend build passed.
- All skins and Time Skip/rollback exercised on desktop and 360/390/412/430 emulated
  mobile widths; representative screenshots visually inspected.
- Existing presentation/runtime/POV browser regression completed successfully.
- Final desktop/mobile skin and Time Skip rerun: 2 passed.
- Model outputs are mocked in automated tests. Real-provider narrative quality and
  physical-phone performance still require user playtesting.
