# #251 — Berezovsk playability, PR #248

Implementation base: `cdb637a2367cae56d51ca0c2796d3056d77f4c85`;
master `d81a52c9980b79d1be99acfde9fc1a1452d71176`. Updated Issue §1.3 read and
implemented as removal of duplicate gates, not another mandatory proof graph.
One executor. No new PR, merge, world generation or paid DeepSeek calls.

## Evidence and limits

Archive parts concatenated 00→01→02→03; SHA256
`831161494259cd7e207ec1ad63745a16759ce10cea79f8506b291a9b27c3086a` matches.
Gzip integrity, 573/573 manifest entries and all 36 SQLite integrity checks pass.
Inputs remain immutable. CI fixture provenance is in `tests/fixtures/issue251`.
`devtools/live99/replay251.py` uses independent SQLite backups and normal jobs,
History, reload and rollback. It replaces only provider IO with archived strings.
No assertion that every historical payload should be accepted.

## Consumer / invariant map

| Owner / consumers | Retained invariant | Removed duplication |
|---|---|---|
| Resolver Movement → character location, History, final scene | Existing actor; registered endpoint (including new location); canonical origin; explicit arrival/departure; coherent route/order and final location | Arrival does not require a second Event; its quote is not repeated in all structures |
| `player_actions.review/event_provenance`, completion checks | Current-input provenance, significant unauthorized choice, actual Event actor/targets and delivered contact | `meaning=preserved` target-set mismatch is repairable; an inventory cannot demand an Event for every gesture |
| `movement_authorized` | Controlled Actor has explicit input or verified Action (direct or accepted Event); contradictory supplied quote/reference rejected; involuntary source accepted | Two pre-validation raw-Event checks replaced by one check after provenance/presence/completions |
| `event_presence` → Knowledge, contact, situation | Simultaneous geography or active transport; explicit source agrees with route; impossible meetings rejected | No identical Event/Movement order or duplicate empty participants/location required solely for an arrival source |
| Arrival Event contact → domain consumers | No fabricated greeting, consent, participant or witness | Isolated action-only arrival with just traveller loses false contact marker/targets with warning. Any substantive source consumer prevents this normalization |
| Continuity → Director/repetition/choice projection | Only validated annotations may suppress repeated decisions/answers; domain handlers own real obligations, Knowledge, property and relationships | Malformed/unproved/conflicting optional beats lose their own authority with warning; valid Event/domain changes survive |
| Commitments → Calendar/boundaries/UI | Consent, canonical ID, date/anchor, cancellation, dependent boundaries | Time-only refinement of an identified meeting retains resolved occurrence; new plans still need date basis |
| `storage.list_turns(context=True)` → context selection → provider | Active branch snapshots, original prose, current time and enduring state | Internal timestamp/situation projection uses existing SQLite, not new memory or full-history injection |

Movement is the one route record. No fake Events, locations or NPCs are generated
by normalization. Supplied contradictory sources still require repair. Actor
arrival, another participant's contact and acquisition of Knowledge remain separate.
The source-contact normalization changes only a candidate, never archived JSON.

## Original replay results

| Case | Result on unchanged archived proposals | Interpretation |
|---|---|---|
| 001 | Repairable target inconsistency; no archived follow-up response | Tamara mention ≠ address. Human target-only correction reveals a separate undated `agreed` plan; no invented date or silent dropped commitment |
| 002 / 002r | Original proposals accepted; production SQLite commit/reload/rollback | Four Events preserved; only invalid decision beat removed with warning; no repair for decorative JSON |
| 006 | First: scene/route conflict; original repair: repairable target inconsistency | Removed false reauthor classification, retained the real incomplete-route conflict |
| 008 | Repairable target inconsistency | No player-as-recipient normalization. Labelled JSON control fixes incidental recipient classification; normal Retry saves the SAME Narrative |
| 009 / 009r | Rejected: source Event endpoint and independent Event presence conflicts | Duplicate movement quote no longer blocks, but street Event cannot prove home arrival; no false PASS |
| 016 / 016r | Time refinement succeeds structurally; missing explicit assent remains repairable | Labelled JSON control adds the existing missing consent assertion. Retry saves 16 April 10:00, original anchor 558 and participants; no date/week shift |
| 020 / 020r | All four original proposals accepted; production SQLite commit/reload/rollback | Arrival Event retains traveller only; false contact authority removed, no fabricated Tamara participation or Knowledge |
| 024 / 024r | First target mismatch repairable; original repair saves | Verified Action→Event authorizes movement without third quote. Home arrival and separate Saturday-plan consequences retained |

Formerly rejected foregrounds 020/024 have no archived response for newly eligible
independent background. Replay reports `background_transport_failed` and preserves
the valid foreground atomically; it does not pretend to test those missing outcomes.
Human controls prove mechanics, not model reliability or live success rate.

### Weekdays and real transmitted context

- Original 005 numeric weekday=3 still means Thursday 16 April; original final
  025r weekday=6 still means Sunday 19 April. No historical −1 migration.
- Labelled structured controls `wednesday` / `saturday` resolve to 15 / 18 April.
  New input schema requests calendar day IDs; canonical storage remains numeric.
  Custom profile day names and unknown calendar dates are covered.
- Full 025r production replay consumes its first two archived attempts and still
  rejects independent action/Event mismatches. Its final original proposal is
  tested separately for the weekday defect; it is not a universally valid run.
- Original 016/017 messages already contained current 16 April. They lacked dates
  on old exchanges and still presented 11 April situations as current.
- Actual new engine→provider messages on original SQLite now contain six dated
  scenes, current 16 April, last jump from 11 April and dated past situations.
  The original assistant prose is unchanged. Current geography/health/relations
  remain canonical. 017 original production replay saves.
- A builder-only test initially missed that public `list_turns()` discarded both
  snapshot timestamps. The production replay caught it; internal context metadata
  now comes from the real storage path. Public history does not expose GM metadata.
- #026 is a model omission of supplied kinship, not a proven lost canonical fact.
  No new textual kinship validator was added.

## Validation

Commands and final CI results are recorded in the PR Conversation on the exact
published HEAD. Targeted coverage includes original replies, same-Narrative Retry,
compound recipients, independent NPC movement, conflicting routes/quotes/sources,
new places, departure to unknown destination, optional continuity vs substantive
consequences, weekdays/time refinements, custom/unknown dates, midnight/year/leap-day
jumps, actual dispatched messages, regeneration context, reload/rollback and an
injected SQLite write failure. Older strict continuity tests are explicitly pinned
to their legacy contract, with current-policy positive and negative counterparts.
No runtime limits or safety assertions were weakened. Group inventory coverage is
now tested separately from actual Event delivery: missing decorative Events cannot
cancel valid Marina Knowledge, and cannot fabricate an Asya address/Knowledge.

Targeted final batches: 310 related tests, 106 context/call/departure/replay tests,
123 replay/provenance tests, 5 protected-movement tests and the year-long group
scenario pass (overlapping suites, not a unique-test total). The preliminary full
local run exhausted its 4.9 GB `/tmp` while retaining SQLite fixtures; its result
is not an acceptance pass. Identified code/policy failures were fixed and rerun.
Further temporary databases use the working disk.

Frontend production build and 153 unit tests pass. Local Chromium cannot start:
`socket() failed: Operation not permitted`; the environment denies escalation.
Desktop/mobile recovery scenarios are committed for execution in GitHub CI; this
local launch failure is not reported as an application test pass.

Full mobile CI on original 016 exposed an additional UI blocker: the expanded
LTA report lived outside `.story-scroll` and consumed the available height,
putting Retry under the composer/phone. LTA/time-skip/calendar notices now share
the existing story scroller. The browser regression retains an ordinary click
and checks usable story height; no force-click or timeout increase.

## Remaining risk and short real-session plan (NOT authorized/run)

Offline evidence demonstrates removal of specific gates and preserved negative
invariants. It does not establish a new live saved-input ratio or guarantee literary
consistency. A model can still misclassify semantic arrival or assent; no regex/NLP
or additional LLM adjudicator is introduced. The older #245 phone archive is a
concrete example: its `completed_arrival` assertions falsely turn plans into arrivals.
With optional Movement source Events, that structurally consistent JSON now saves
without repair. This is a semantic failure, not a successful playability replay;
requiring a duplicate Event would only incidentally reject that particular encoding.
Legacy hard-classified job diagnostics
remain unchanged and are not bypassed. Ordinary new attempts have the repaired
classification; original abandoned scenes are not silently applied later.

After separate paid-call approval, continue the SAME final Berezovsk save on a
verified copy, with its existing world, History and provider settings; Narrative
and Extraction thinking off. Suggested 8–10 natural inputs, one short bounded LTA:

1. Ordinary conversation with Galina: mention Tamara without addressing her;
   include a gesture and an actual meaningful reply in one natural input.
2. Walk, incidental greeting and another action without prescribing JSON or
   splitting the input artificially. Let NPCs respond autonomously.
3. Visit/leave the cafe and return home; check actual location/contact separately.
4. Refine an existing agreed meeting's time, then inspect its date/day in calendar.
5. Advance a few days within existing boundaries and resume ordinary play;
   verify dated memory/current situation in actual requests and the resulting prose.
6. Allow a few independently eligible background events; check their recorded
   consequences and Knowledge without demanding a specific rare life event.

Track saved player decisions / final lost scenes / manual recoveries, actual
request count, complete latency and spend, autonomous NPC outcomes and retained
significant consequences. Assess story interest separately from JSON validity.
An occasional literary slip is acceptable; repeated blocked everyday turns are
not. Green CI alone does not establish that this live acceptance criterion is met.
