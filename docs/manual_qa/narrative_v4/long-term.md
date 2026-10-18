# Long-term Advance (#43)

Use the existing developer test-world loader with checkpoint `long-term` and an
isolated developer database (see the #78 README).

```sh
RPG_DEV_TOOLS=1 python scripts/narrative_test_world.py --checkpoint long-term --db /tmp/narrative-long-term.sqlite3
```
 Reset by loading it again;
never overwrite a user's save. This extends the existing reproduction fixture
with 120 stored NPC identities and 12 unresolved education threads.

1. Open the started fixture. Record the current date and the newborn's identity.
2. Open **Длительный переход**. Select 15 years and set the call cap to zero.
3. Review the preview and confirm. A due controlled-actor commitment must stop the
   operation at its boundary; it must remain pending, not become fulfilled.
4. With no blocking commitment, the target date is reached. The newborn grows
   from the known birth date without acquiring adult personality, education,
   work, a partner or residence merely because time passed. No daily scenes.
5. Reload: date, identity, personality, History and unresolved sources persist.
6. Regenerate: use the recorded request/before snapshot, not the current date.
7. Roll back, then take an ordinary turn: the alternate branch retains the
   original timeline and does not inherit accepted opportunities from its sibling.
8. Check both narrow mobile and desktop layouts. The interval dialog, preview,
   confirmation and results remain reachable; no horizontal page overflow.
9. Use a deterministic fake provider for automated outcome tests. Do not enable
   paid external providers without explicit authorization.

For a provider-assisted manual session, review bounded group diagnostics and
canonical role/residence/event records after every accepted result. Prose alone
is not evidence that a role transition succeeded. Off-camera summaries are
player-observer information; they must not become character Knowledge. A secret
move must remain secret until the existing witnessed/told/message evidence route
establishes exactly the learned facet.
