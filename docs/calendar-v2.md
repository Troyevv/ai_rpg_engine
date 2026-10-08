# Canonical Calendar v2

Runtime v3 remains the sole runtime. `meta.world_time` is the monotonic local
minute counter; `meta.calendar` holds the campaign anchor and explicit profile.
`current_time()` computes date, Day N, weekday, HH:MM, period and optional season.
No derived age/period/date is persisted as mutable current state. Calendar dates
on history events are immutable projections of a known event minute.

## Configuration and boundaries

Normal Initial World JSON accepts `world_clock.calendar` and
`world.characters[id].birth_date`. Import validates them before confirmation;
migration carries them into the existing WorldStateV3. No birthday is inferred
from an age/card/location name. Example:

```json
{"start_minute":5562,"start_weekday":3,"start_date":"2026-10-08",
 "profile":{"id":"two-shores","system":"gregorian",
 "observances":[{"id":"bridge-day","name":"День моста","month":10,"day":9}],
 "seasons":[]}}
```

Gregorian `start_date` determines weekday. Day 1 is always the anchor's civil
day, independent of weekday; HH:MM remains world_time modulo 1440.
Profiles configure their own observances, personal annual anniversaries
(`character_ids`), optional seasons (named month/day starts), and optionally
month/weekday names. `system=custom` uses explicit fixed `month_lengths`
(1–24 months, each 1–99 days), optional weekday_names (up to 14); no leap rule is
invented. Gregorian profiles cannot override Gregorian month lengths.
Unknown timezone/geography stays unknown. There is no location inference,
country holiday database, DST conversion or geographic model; #39 can provide
explicit configuration later. Local world minutes intentionally do not change
with real-world timezone rules.

Annual Feb 29 observances/birthdays only occur in leap years. Age for Feb 29 births
advances on March 1 in non-leap years. Date limits are years 1–9999; beyond them
relative time remains available. Unknown or malformed optional dates in legacy
reads degrade locally and log diagnostics; stored historical snapshots are not
rewritten. New imports reject malformed configuration.

## Read API and context

`GET /api/saves/{id}/calendar` returns current and a display label.
`?minute=N` provides a read-only preview within ±7 days (not a Time Skip command).
`?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` returns an inclusive 1–400 day range,
weekday placement, month boundaries, campaign day numbers and recurring events.
It supports week/month/year clients without creating a frontend calendar source.
UI labels for current and known historical minutes are server projections;
Time Skip previews use the read API. Full calendar navigation remains #45.

Narrative and extraction share `current_time`. During Time Skip they also receive
`time_skip_target` computed from actual_target. Context omits the annual profile:
nearby dates are limited to yesterday through seven days ahead and 12 events,
with birthdays/personal dates limited to context-relevant Characters. Annual
observances never generate actions, Knowledge, celebrations or canonical events.

Periods are defined once: night [00:00,06:00), morning [06:00,12:00), afternoon
[12:00,18:00), evening [18:00,22:00), night [22:00,24:00). Labels are structured
neutral identifiers; existing Russian UI presentation is preserved (this codebase
currently has no i18n service). Diegetic text follows campaign language.

## Scheduled temporal boundary for #66

ScheduledEvent may carry `temporal` with one of `date`, `weekday` (zero-based in
profile), `day_offset`, plus `time` HH:MM or day_period. Runtime owns
`time_reference_minute`; relative times bind to the original turn, not each read.
Existing positive due_minute is supported. Zero without a resolved temporal
constraint is unknown, not overdue. A narrow legacy adapter recognises explicit
weekday/relative-day plus time/period in condition; unknown prose stays unresolved.
Legacy values without a recorded reference use campaign start, conservatively.
No LLM call or commitment lifecycle is added. Scope, Director and Time Skip share
this resolution. Due/overdue remains distinct from happened.

## Dependency evaluation

`datetime`/stdlib `calendar` handle Gregorian date, leap-year and month arithmetic.
`zoneinfo` is unnecessary for a local fictional monotonic clock without timezone
conversion. `python-dateutil` was evaluated: no month/year increment or general
RRULE is required here; annual month/day projection is bounded and direct, so
adding it would not reduce the implemented logic. Custom fixed calendars stay
behind the same small arithmetic adapter. Existing pinned Hypothesis dev
range supplies Gregorian/date projection properties; no dependency added.

Manual QA/checkpoints: [calendar.md](manual_qa/narrative_v4/calendar.md).
