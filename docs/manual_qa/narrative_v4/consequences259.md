# #259: preparation for compound consequences and staged game acceptance

Base `4794159`, existing PR #248. No paid requests in this phase. This is the required pre-qualification adapter, not completion of #259 or a new production default.

## Four original paths reproduced

The #258 archive SHA256 is `cf00dfe7e4b3ddd173d1f0f2b723611fb74a2da59da6f9cae8c784194ec87bca`. On unchanged code, replaying actual river-T, cafe-S, unrequested_refusal-R and calendar-R responses through the original candidate and Resolver reproduced their recorded resulting states/History exactly (including calendar rejection).

- River-T: input and full Narrative reach the provider; its own situation says river, but no movement effect exists. Adapter/compiler faithfully compile interactions/occurrences. The resulting character locations are still porch. Persistent geography supplied to the next context consequently remains wrong. This is a missing semantic effect, not dropped compiler data.
- Cafe-S: message content reaches the model; it emits empty claims even in the en-route speech. Compiler cannot infer a Fact from text. No Knowledge acquisition reaches the next context.
- Refusal-R: the model states clean and omits a substantial agency finding. The photograph source does not prove the unchosen refusal was reviewed. No adapter loss is required for this false acceptance.
- Calendar-R: concrete narrator date reaches Calendar and causes reauthor despite the model's clean assessment. The concrete claim is useful; the self-assessment is not independent evidence.

The four-case replay is in `work/issue259-free/original-replay.json`. Complexity/attention/profile remain hypotheses, not established causal explanations.

## One candidate, not another review flag

`devtools/issue259/compound.py` makes a source contain an evidence excerpt and multiple typed effects. A walk with conversation can carry movement and actual perceptions together. Each effect loses its separate generated text, evidence and ID. Derived IDs and route-time links are built by code; existing compilation and domain owners validate every effect. Evidence is copied, never interpreted by Python. The old scene_steps list is replaced in the external schema, not accompanied by a second canonical summary.

The source is one unit for repair, with independent effects protected against deletion/modification; the existing candidate hash, replacement protocol and single-repair policy remain. Domain source references address a derived source/effect identity explicitly. No authority or perceiver is inferred from the compound group.

The instruction has a dedicated owner, not a chain of legacy text replacements. On original river-T, rules shrink 17,829 → 3,121 characters; schema 35,984 → 35,872. State 30,980, Choice context 8,795, entity references, full input and 1,722-character Narrative remain identical. These are characters, not billed tokens. Responses adapter sends the schema once. The schema is still substantial: rare domain capabilities are deliberately retained; this is a remaining model burden, not claimed solved compression.

Choices remain in the same Extraction with their actor-accessible context and grounding checks. Moving them to Narrative without a privacy design is not included. No new mandatory request, critic, automatic fallback or Runtime prose analysis.

Prototype limits: domain payloads retain existing typed forms, and some effect-level sources/references remain explicit. The candidate is not yet a complete alternative production context builder. Before adoption, actual provider outcomes must qualify it; domain source repair, old contracts, background/LTA/Remote, next-context memory, production schema/config recording and desktop/mobile recovery are mandatory integration gates. Production will use the next server-recorded version after checking the current HEAD, not silently change v8 jobs.

## Free controls

`python -m pytest -q tests/test_compound259.py tests/test_technical258.py tests/test_candidates258.py`: **29 passed**. Controls cover compound route plus Knowledge, no hearing by an arrival bystander, no-change scenes, retained domain schema, repair/hash/independent effects and actual job→SQLite→cold reload→rollback via an explicitly patched candidate seam. This is authored provider IO; production default is unchanged and the test does not establish provider-schema integration or live model accuracy.

Two QA setup mistakes were corrected: a test initially called the existing birth section `birth_claims` instead of `births`; the legacy helper initially removed the recorded contract and double-encoded the response. Its normal `legacy=False` path with a dict response resolves that setup error. No provider calls were involved.

18 original/contrast inputs are frozen under `work/issue259-free/frozen`, with original and projected hashes. Untested contrasts remain holdouts unless used for correction. Full CI is deferred until the qualified implementation is integrated and stabilized, per Issue stage D; the old green run is not evidence for this candidate.

## One proposed authorization, conditional stages

No old authorization is reused. Existing ledger currently ends at reservation 777 with no unknown outcome; no ledger rows changed during preparation.

| Stage | Cases / transition | Maximum calls, including one repair | Conservative cap |
|---|---|---:|---:|
| Initial hypothesis | 8 candidate cases: river, cafe, river_talk, partial secret, both refusals, calendar, Olga; fresh v8 control on river/cafe/unrequested refusal | 22 | $0.75 |
| One correction and one fallback | At most 8 affected/regression cases after one justified correction; if semantic omissions persist, same 8 on one different Extraction profile | 32 | $1.25 |
| Confirmation | 6 prior holdouts, detail/belief/route-hearer contrasts, original birth, no-change, one new genre/name contrast, 2 predeclared variability repeats | 28 | $0.75 |
| Sequential recovery | Four original Narratives from last correct predecessor; up to 8 extraction/repair calls and 4 existing background calls; reload and next context | 12 | $0.50 |
| Ordinary UI game | 30 new ordinary turns: 60 basic calls, up to 30 automatic repair, 15 background and 5 calls reserved for player-visible recovery | 110 | $2.75 |
| **Total** | Stage caps and total both binding | **204** | **$6.00** |

Main profile: DeepSeek Flash/off, Responses schema, temperature 0.1, max output 8192. Narrative stays Flash/off. The single proposed fallback is **Flash/low only for Extraction**, max output 16384; a predeclared correction may use 32768 only after an actual output-limit receipt, counting the failed call. No Pro, hidden third call, automatic profile switching or paid world generation. If the low profile wins, only explicit stage-specific Extraction configuration may carry it into the later stages, with effective settings recorded.

Official docs checked 2026-11-16: https://api-docs.deepseek.com/guides/thinking_mode and https://api-docs.deepseek.com/quick_start/pricing. Responses supports `reasoning.effort=none/low/high/max`; current adapter maps off→none and omits temperature while thinking. Flash alias currently maps to V4.1-Flash-1017. Peak cold-input/output rates are $0.30/$1.20 per million; use these even during discounted hours. No separate visible-JSON reserve parameter is established by these docs. Reasoning shares the output allowance; a larger cap does not guarantee JSON. Full unknown reserve at 32768 output is $0.3538944 and remains charged/blocking under existing Budget rules.

Previous #258 receipts: 22 calls, 570,941 input / 20,062 output, $0.1953567. Earlier playtest confirmed 197,297 input / 8,384 output at $0.0692499, plus its separately retained unknown reserve. These support an approximate **$1.5–3 expected total**, not a promise; the agreed ceiling would be $6, about 1–3 hours including reading/UI and checks. Receipt accounting replaces estimates as calls occur. Stage limits do not silently transfer to another stage.

Before dispatch freeze severity: lost movement/wrong identity/address/secret leak/lost substantial information/unchosen decision/serious date conflict/save damage are blockers. Route ordering/detail is assessed by effect on listeners, access, outcomes and choice; equivalent harmless representation is not a blocker. Historical #257/#258 tables remain unchanged. A semantically wrong structural acceptance never gets an oracle-driven repair.

If initial results fail, establish the cause and execute only the predeclared correction/profile branch. Integration errors are fixed deterministically; persistent semantic failures do not trigger new Runtime gates. A third semantic request is NOT authorized by this plan. Stop paid dispatch on unresolved spend, either cap, or a demonstrated unresolved blocker after the allowed branch. Confirmation, recovery and game require passing preceding gates. Do not play over a false accepted predecessor. Keep the 30-turn diary separate from technical investigation; no code edits during the UI session.
