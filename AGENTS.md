# Codex repository instructions

## Scope and source of truth
- These instructions apply to the entire repository.
- Read the relevant implementation and tests before changing behavior. README is orientation, not proof that a feature is already merged or complete.
- Follow the GitHub issue/PR acceptance criteria. If they conflict with these instructions, explain the conflict rather than silently overriding either.
- Keep changes focused; do not opportunistically rewrite unrelated modules.

## Architecture
- The application uses a FastAPI backend, SQLite persistence, and a React + TypeScript frontend built with Vite.
- Keep domain logic out of HTTP handlers and UI components. Preserve existing service, persistence, provider, and runtime boundaries; inspect actual module layout before choosing files.
- Narrative and Tabletop are separate game runtimes sharing infrastructure. Never apply Narrative world-state assumptions to Tabletop mechanics or vice versa.
- Prefer existing abstractions and established dependencies to new frameworks, parallel implementations, or speculative generalization.
- Do not implement future modes or features unless requested by the task.

## Narrative invariants
- Canonical World State, not prose, is the authoritative persistent state.
- Preserve separation of POV (camera/perspective) and Controlled Actor (player agency). Observing an NPC or using “World without protagonist” must not silently transfer control.
- Do not let LLM-generated prose or extraction assign the controlled actor goals, intentions, emotions, commitments, or decisions without evidence of explicit player input.
- Respect character-specific knowledge and secrets. Do not leak omniscient information into a character's context.
- Validate extracted WorldDelta before applying it. Do not silently swallow unknown or dangerous semantic errors. Keep diagnostics for rejected or repaired changes.
- Preserve turn/variant lineage, before/after snapshots, rollback behavior, and atomic persistence. Regeneration must use the recorded original context, not silently reconstructed later context.
- Keep existing saves compatible. Do not rewrite historical snapshots as a migration shortcut.

## Tabletop invariants
- The server-side rules and dice engines, not the LLM, decide checks, damage, resources, inventory, equipment, initiative, conditions, and combat outcomes.
- The LLM may interpret intent, write dialogue, and narrate validated outcomes; it must not fabricate authoritative mechanical results.
- Keep game rules deterministic and testable. Prefer structured content and validated content packs to unconstrained LLM generation unless a task explicitly changes this design.
- Preserve existing content formats and saved campaigns or supply an explicit migration path.

## LLM integration
- Do not add LLM calls where deterministic code suffices. Avoid redundant retries, unnecessary context, and token-expensive workflows.
- Preserve provider abstraction, model selection, streaming behavior, and per-stage configuration where relevant.
- Record actual attempts, token usage, cost estimates, and diagnostics through existing instrumentation. Do not invent usage data.
- Never expose API keys to the browser, logs, prompts, or stored request diagnostics.

## Data integrity and compatibility
- Treat SQLite schema changes as migrations. Preserve user data and existing save/load behavior.
- Use transactions for multi-step state updates and maintain revision/concurrency protections.
- Never delete or silently reshape persisted game state to make a new feature pass.
- Validate IDs, references, and cross-entity consistency at appropriate boundaries.

## Frontend
- Preserve responsive desktop/mobile behavior and existing theme/skin architecture.
- Avoid duplicating entire screens per theme or mode where shared components suffice.
- Maintain usable streaming, stable scroll position, and accessibility for interactive controls when touched.
- Do not add native browser prompts/menus as substitutes for existing application UI without explicit approval.

## Testing and delivery
- Add or update focused automated tests for behavior changes and regressions, especially state transitions, player agency, migrations, and deterministic rules.
- Run relevant backend tests and frontend checks when available; frontend scripts include `npm run build` and `npm run test:e2e`. Inspect repository configuration for backend test commands rather than assuming one.
- Never claim tests passed if they were not run. Report exact commands, results, and blockers.
- In the final report, summarize changed files, behavioral impact, compatibility/migration implications, tests, and remaining risks.
- Do not create unrelated PRs, merge branches, or modify issue scope without explicit instruction.
