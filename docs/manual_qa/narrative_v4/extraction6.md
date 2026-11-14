# Extraction/6: one semantic scene sequence

The server records contract 6 for new ordinary/background/LTA jobs. Remote
Extraction/1 is separate. Recorded jobs v1–v5 and their regeneration retain their
original contract; historical WorldState/History snapshots are not migrated.

`scene_steps.py` owns the external types and projection, not a second Runtime.
`scene_repair.py` owns one-candidate replacement. `RawTurnResult` remains internal.
The full local validator uses the same schema owner as the context projection;
provider projection changes anchors to JSON pointers and removes discriminator
annotations, without weakening required/nullable/additionalProperties rules.

```json
{
  "scene": {"elapsed_minutes": 10, "situation": "Алексей добрался до парка."},
  "scene_steps": [
    {"id":"bye", "kind":"interaction", "actor_id":"alexey",
     "target_ids":["tamara"], "outcome":"completed", "text":"Попрощался.",
     "input_source":{"quote":"Прощаюсь с Тамарой", "meaning":"preserved"}},
    {"id":"walk", "kind":"movement", "actor_id":"alexey",
     "assertion":"completed_arrival", "endpoint":"park", "text":"Пришёл в парк.",
     "input_source":{"quote":"иду в парк", "meaning":"preserved"}}
  ]
}
```

IDs in the example must exist in the particular world, or be established via the
existing locations/promotions sections. It is a schema example, not real QA IO.
No greeting of a person at the destination, witnesses, or Knowledge is inferred.

| Meaning | Owner | Derived consumers |
|---|---|---|
| Actual action, actor, achieved targets/channel/outcome | Extraction step | Event/contact/presence/relationships |
| Relevant input quote + preserved/changed meaning | Step input_source | PlayerAction, Event, Movement; existing agency validators |
| Intended targets when different | input_source.intended_target_ids | Partial action review, no invented recipients |
| Actual arrival/departure/attempt | MovementStep | Route origin from before/prior steps, Movement and source Event |
| Relative sequence / explicit simultaneity | List order / timing | Shared ordinal axis; uncertain ordering is repairable |
| Content + source + per-claim perceivers/status | InformationStep / existing PerceivedClaim | Existing information compiler → Fact/Event/Knowledge |
| Objective domain event (e.g. birth) | OccurrenceStep | Existing BirthClaim/life/process handlers; no newborn contact required |
| Non-derivable composition | scene.visible_character_ids / observed_character_ids | Internal final_scene; never geography/contact |
| Camera position | Existing mode and subject + accepted route | Internal final_scene; observer-only location override |
| Duration / significant chronology finding | scene / chronology_claims | Existing Calendar/boundaries/recovery |
| Technical IDs, provenance and references | Compiler | Exact deterministic step aliases, existing History namespace |

Removed from v6 output: independent events, movements, information_events,
knowledge_gained, player_agency.actions and full final_scene. Unchanged domain
sections remain available, and source_event_id(s) reference step IDs. Model
output cannot set trusted compilation markers. Quiet scenes use an explicit
empty scene_steps list; blank/malformed output cannot stand in for that answer.

## Changed blocking requirements

| Removed duplication | Remaining invariant / negative control |
|---|---|
| Route + independently computed final location | Endpoint exists; explicit visibility cannot teleport another actor |
| Repeated input action/Event/Movement evidence | Current-input quote + semantic meaning; wrong source/unauthorized choice fails |
| Separate Event.order and Movement.order | One shared step axis; pre-arrival contact and uncertain chronology fail |
| Participants/witnesses copied from the same perception | Explicit per-claim perceivers; target/co-presence alone grants no Knowledge |
| Whole-answer replacement on a localized error | Candidate hash, allowed source group, immutable other proposals, full revalidation |
| Exact duplicate Fact ID records | Exact immutable identity only; text/claim/privacy conflicts fail without renaming |

## Repair and replay

One automatic repair is retained. A parsed candidate receives a hash bound to
before, Narrative, input, turn and namespace. Allowed step IDs and connected
sections are server-selected. Replacements preserve step identity/order;
additions need a listed anchor. Independent sections are retained by code.
Section records cannot disappear without explicit per-record `withdrawals`
(section, record_key, reason), recorded as semantic reinterpretation diagnostics.
The model reinterprets the unchanged prose; these diagnostics are not proof that
its reinterpretation is correct. The whole candidate is rebuilt from before and
validated before one commit. No earlier partial result becomes canon.

Invalid JSON/root or unusable source IDs get one full compact replacement,
without subsequently adding another repair. Old jobs use the old repair protocol.
An explicit manual v6 Retry starts a fresh full candidate on the recorded
before/Narrative, rather than treating a prior patch as a full result or merging
failed attempts. Original responses, patch bases, assembled candidate, mode/hash and compiled
records remain attached to their exact request ID in existing request diagnostics;
saved raw_turn_result includes both compiled records and semantic_candidate.
A stale patch sent as the first response is rejected, never auto-upgraded.

## Provider and accounting

Documented Responses JSON Schema capability is selected for DeepSeek
`deepseek-flash` and `deepseek-v4-pro`; other/local/compatible models explicitly
use chat json_object plus the same local semantic validation. No probing,
model switching, implicit downgrade, hidden HTTP retries, or tool roundtrip.
Schema is sent once via `text.format`, rather than duplicated in prompt and API.
Narrative streaming remains Chat Completions. Responses stream handling requires
one completed matching text result; blank/incomplete/truncated/foreign tool or
multiple output is an error. Usage and actual transport/schema are persisted by
the existing request ledger; credentials are not included.

Official protocol sources consulted 2026-11-14:
https://api-docs.deepseek.com/api/create-response/
https://api-docs.deepseek.com/guides/responses_api/

**Live provider capability with the complete schema: NOT RUN.** Mock transport
checks establish request/stream handling only; no strict-mode/live success claim.
Provider smoke requires a separately approved budget before ordinary playtest.
