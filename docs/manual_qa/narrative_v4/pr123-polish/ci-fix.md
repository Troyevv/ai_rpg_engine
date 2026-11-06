# PR #123 — browser CI repair

Failed run: https://github.com/Troyevv/ai_rpg_engine/actions/runs/40414546608
Head inspected: `d6a3d8d0d3129dd755f96023a76114c37a35d253`.

Both projects reported the same two failures. Mobile finished with 143 passed, 23 skipped and 2 failed; desktop was cancelled after reporting the same failures. Backend/build job passed.

- InspectorCard lost its accessible section name during the workspace conversion. Restore the localized title as aria-label, so titled sections are navigable named regions again. This does not change layout or colors.
- Commitments now expand through Details, not the record heading. Update the test interaction and retain assertions for condition, time window, dependency, read-only revision, reload and overflow.
- The scenario parity test still expected the removed modal and old service heading. Assert the actual workspace, dossier, linked character name and active Overview tab instead. Keep the subsequent action, regeneration, rollback and reload checks.

Validation: `npm run build --prefix frontend` passed. With `CI=true`, `npm run test:e2e --prefix frontend -- e2e/commitments.spec.ts e2e/parity.spec.ts` passed **6/6** across desktop/mobile. The local browser is installed Chromium headless shell 1193 via PLAYWRIGHT_EXECUTABLE_PATH. GitHub CI uses its lockfile-matched browser and runs the full suite after publication.

No runtime, persistence, permissions, palette or workflow changes. No tests disabled or timeouts increased.
