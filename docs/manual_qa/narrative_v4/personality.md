# #67 — Personality development

## Deterministic setup/reset

```bash
RPG_DEV_TOOLS=1 python scripts/narrative_test_world.py --checkpoint personality
```

Use the printed save in the existing isolated `data/dev-narrative-v4.sqlite3` dev-server.
Repeating the loader creates a fresh save; it never deletes earlier games. The `base`
and all earlier checkpoints retain their existing semantics. This checkpoint is already
started: three deterministic accepted scenes are present, no live LLM calls required.

Asya begins with a sparse developmental profile. Across three accepted drawing choices
she establishes only `preferences/drawing = Любит рисовать.`; she does not acquire a full
adult personality. Vera witnessed these sources; Kirill does not automatically know them.

## Action sequence and expected results

1. Select Asya for control. Open World → Characters → Asya → Preferences. Her established
   drawing preference is visible; no fabricated strengths/weaknesses or adult traits.
2. Reload. Same Character ID, profile, evidence IDs and source chronology remain.
3. Across three ordinary turns choose to draw landscapes and finish them. Free text and
   generated choice selection are equivalent. Once completion and a sustained preference
   are canonically established, extraction may refine the existing drawing item. Other
   items stay unchanged; it must not replace the entire card or invent voluntary reactions.
4. Inspect diagnostics/context: development uses ordinary Narrative + Extraction only.
   A rejected optional delta leaves the game playable and explains the rejection.
5. Regenerate the last changing turn without that development. Prior profile returns.
   Select the earlier response variant: accepted changed profile returns exactly once.
   Roll back: original before-profile and history head return.
6. Switch back to Kirill, advance a quiet day, then select Asya again. Identity/profile
   and evidence survive; time alone adds no trait. NPC autonomy resumes from the same
   profile when she is no longer controlled.
7. Try one ordinary argument/angry evening: emotion can change; durable personality should
   not. A life event happening to the controlled actor cannot assign their coping style.
8. Compare divergent response variants. No trait/evidence from one branch leaks into the
   other. Replaying identical source IDs cannot apply the same development twice.
9. For infant integration, use `Character(developmental_stage='infant', personality={})`
   in a unit fixture. Only experience-backed early temperament is eligible; no adult
   strengths/weaknesses. Birth generation remains #41 and is not simulated by this loader.

Semantic interpretation by a live LLM is not deterministic. Exact acceptance/rejection,
source identity, control transitions, archive lookup and variant behavior are verified by
`tests/test_personality.py` without paid calls. Browser coverage on desktop/mobile is in
`frontend/e2e/personality.spec.ts`; it checks sparse card rendering and reload.
