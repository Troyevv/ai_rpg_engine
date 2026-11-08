# Independent Berezovsk findings, 2026-11-08

These are confirmed residual defects, **not fixed by #250**, and not converted to
advisory success. They require separate scoped work before claiming reliable
Knowledge/geography in live play. Baseline: PR #248 `c978a8f`; repeated with the
#250 working implementation. No paid provider calls, no rewritten prose.

## High: secret information in an optional choice

Original comparison D/002 includes:

> «А что он ещё говорил? Про письмо или про кого-нибудь?»

Alexey does not know `fact_viktor_letter`. The choice lacks a structured source
link; `continuity.filter_choices()` accepts it as a scene-based suggestion.
Canonical Knowledge is unchanged, but the proposed speech leaks the secret and
invites the player to use it. Optional-choice validation correctly rejects bad
explicit basis IDs; that does not establish semantic safety of ungrounded text.

Recommendation: separately define and verify source-grounded choice generation
using the existing controlled-actor context and Knowledge visibility. Preserve
safe free input and discard an unsafe proposal only. Do not infer secrets with
keywords/regex or grant Knowledge because the model proposed mentioning them.
Test original D/002, paraphrases, safe scene-based choices and NPC-only secrets.

## High: observed Pasha loses his canonical location in LTA

Original second LTA group has `present_character_ids=[char_andrey,char_marina]`,
`observed_character_ids=[char_pasha]`, and describes Pasha in his room. There are
no movements. Before: `char_pasha.location_id=loc_home_kovalev`; after accepted
resolve: `null`. Knowledge is unchanged.

The final-scene reconciliation in `resolver.py` treats removing a character from
physical membership as a geography change, including the LTA private-camera
projection. Restoring only the player's camera later cannot restore the lost
character location. This predates #250. The exact baseline `long_term.run()` replay
of four archived responses accepts the groups and reproduces the loss. The #250
replay below also reproduces the original second group through the current
`advance_clock()` and `StateResolver` with its recorded private camera. It does
not claim unchanged full-run candidate selection: #250 now considers independent
NPC activity in player-linked threads too.

Recommendation: separately resolve observation/membership versus actual departure
in the existing final-scene/movement owner. Absence from a private shot cannot
invent a departure. Preserve actual exits to unknown destinations, arrivals,
observed doorway actors, concurrent presence validation and ordinary POV changes.
Test original group plus SQLite reload and foreground/background/LTA variants.

## Reproduce without a model

Extract the original `life248-playability-live-evidence-20261108.tar.gz`
(SHA256 in `tests/fixtures/issue250/source.md`). From repository root:

```sh
PYTHONPATH=. python scripts/reproduce_berezovsk250.py /path/to/life248-playability-live
```

The script reads the committed original D/002 fixture and original
`lta/turns/001/{before.json.gz,requests.json.gz}`. It never changes an archive,
save, response or Narrative and never calls a provider. Observed output:

```json
{
  "provider_calls": 0,
  "choice_secret_known": false,
  "leaked_choices": [{
    "action": "Налить чай и поставить чашку перед матерью",
    "speech": "«А что он ещё говорил? Про письмо или про кого-нибудь?»",
    "interaction_channel": "physical"
  }],
  "pasha_before": "loc_home_kovalev",
  "pasha_after": null,
  "knowledge_unchanged": true
}
```

## Composite visit: distinguish covered and remaining failures

The earlier `life248` visit (`005`) now commits unchanged original Narrative and
its first Extraction in two calls: no standalone farewell Event is required just
to cover an unreferenced action-list entry. The explicit movement still passes
its own player-source/arrival validation and survives SQLite reload/rollback.

Latest D/005 is different: original Extraction contains conflicting Event/action
quotes and a missing target participant; its repair contains no complete
`final_scene`. Current production still rejects it atomically after the bounded
repair. This is not an optional-audit error. `test_latest_original_visit_errors_are_not_hidden_by_soft_audit`
retains exact responses and verifies no partial History/snapshot commit.
No claim is made that #250 makes every archived failed response acceptable.
