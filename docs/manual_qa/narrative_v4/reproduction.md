# #41 manual QA — the existing “Два берега” world

Use the isolated developer database/server and existing loader described in the
#78 instructions. Never load fixtures into a production/user database.

```sh
RPG_DEV_TOOLS=1 python scripts/narrative_test_world.py --checkpoint pregnancy
```

Available checkpoints: `pregnancy`, `pregnancy-twins`, `pregnancy-triplets`,
`newborn`, `newborn-twins`, `newborn-triplets`. Reset by loading the same checkpoint
again; the loader creates a separate world/save. The initial characters remain the
same #78 cast. The fixture explicitly establishes adult reproductive capabilities,
matching family names and deterministic weights. **Only these QA worlds** use a
one-day gestation and guaranteed unprotected conception, to make birth testable
without introducing Long-term Advance (#43).

## Hidden pregnancy and independent knowledge

1. Load `pregnancy-twins`. The accepted encounter has one stored conception and two
   child slots; there are no child Characters or pregnancy Knowledge yet.
2. Check ordinary POV, choices, facts and character cards: no count or sex disclosure.
   No automatic romance, affection, commitment or emotion change.
3. Through ordinary narrative establish an examination that reveals pregnancy only.
   Inspect extraction: the current information Event links only the existence fact.
4. Establish a later examination revealing child count only, then one child's sex.
   Other sex facts remain hidden. Switch POV to an uninformed character: no broadcast.
5. Continue the same encounter over turns if testing a fresh fixture: reuse its ID,
   do not create new attempts each turn. End it explicitly before a new encounter.
6. Test a proposal/intention, kissing, unknown capability, protected event, missing
   consent and a minor: none may create an eligible conception under this fixture's
   policy. Invalid optional records produce diagnostics; the turn remains playable.

## Names and birth

1. Discuss “мне нравится имя Мира”: verify `proposed`, not agreed.
2. Explicitly agree, reject, replace, defer, or delegate to Вера. For twins/triplets
   target a concrete slot; an ambiguous “назовём её” must not guess a child.
3. Explicitly Time Skip to the due boundary. Reaching it alone creates no children;
   a completed birth Event must resolve the process. No estimated date is a birthday.
4. Alternatively load a `newborn*` checkpoint to inspect the resolved result directly.
5. Each child has its own ordinary card and two independently derived parent edges.
   “Без имени” is a placeholder, not a canonical name. An agreed planned given name
   applies once; proposal-only does not. Matching configured family names carry over.
6. Inspect child data: actual birth date/time, stable sex/provenance, sparse personality
   containing only early temperament, empty motivations/values, no inherited Knowledge.
   Explicitly narrated appearance survives reload. Nothing is generated from parents.
7. Family → Родословная shows each child once. Verify desktop and mobile, including
   blank/partial names and cards. No duplicate edges after a page refresh.

## Persistence and gameplay

- Start → ordinary turn → save/reload → next ordinary turn must work in each checkpoint.
- Regenerate the birth using the same accepted event: same IDs/count/sex/temperament.
  Select the previous variant, rollback, then replay: no orphan pregnancy, child or edge.
- Branch from the pre-birth snapshot. A branch without the accepted birth has no
  children. The original branch remains intact. Changed encounter identities may
  legitimately produce different outcomes; the same identity never rerolls.
- Agree/replace a name after birth, reload, rollback and restore a variant. Keep prior
  decision provenance; never infer EXTERNAL acceptance from an NPC suggestion.
- With an explicit later calendar/stage transition, the same Character can develop
  through #67. Age does not itself create adult personality or future life events.
- Check ordinary legacy Narrative and Tabletop saves. No new fields are required.

Automated coverage is in `tests/test_reproduction.py` and `frontend/e2e/newborn.spec.ts`;
all fixtures/mock providers are deterministic and require no paid model calls.
