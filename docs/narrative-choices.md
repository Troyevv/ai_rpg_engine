# Narrative choice generation (#73)

The existing Extraction call generates up to six `{action, speech}` suggestions.
`Choice context / controlled actor` is a disposable projection in the existing
Context Builder, not persisted state or a recommendation service. No schema or
SQL migration, new dependency, model call, UI or Tabletop change is required.

The projection uses camera control identity, #67 canonical personality (including
communication/habits), #75 actionable motivations/values, outbound relationships
with scene/remote participants, capabilities and selected own known/suspected
assertions. A missing legacy personality can use card fields; an empty canonical
profile never revives retired card text. Other actors' inner states and objective
truth are not choice knowledge. An old `known` belief may disagree with world truth.

Recent expression comes from at most the configured six visible scenes, only actual
ordinary inputs owned by this actor (legacy owner falls back to protagonist), with
800 characters per input and explicit truncation. No previous choices, background
instructions, other actors' inputs or historical prose are copied. A submitted
attempt is not automatically a completed event. Current input/completed narrative
remain separate authoritative current-turn sources; the contract places suggestions
at the observable end of that narrative, not at the initial camera.

Knowledge reuses ContextScope selection and is refreshed when optional facts are
trimmed. Existing projection budgets limit personality/motivations. Mandatory policy
and actor identity can exceed the 18k soft target (reported in diagnostics), but the
existing hard context limit still applies. No full card/history dump is added.

The policy requests materially distinct, context-appropriate decisions, including
plausible atypical ones, in the active game's language. Personality never validates
manual input. RawTurnResult choices stay separate from resolver records and cannot
be evidence or mutate the state patch/history; observer/background/incapacity return
an empty list even if a model produces choices. Save snapshots, original-context
regeneration, variant ancestry and rollback remain owned by the existing pipeline.

Limit: this is a prompt/context contract, not a semantic firewall against a model
ignoring instructions. Extraction must see GM truth for its existing resolution
responsibility. Tests prove filtered choice inputs, provenance and Runtime agency,
not arbitrary model literary quality or perfect semantic non-disclosure. No extra
LLM verifier or text heuristics claim otherwise. Follow the focused
[manual QA](manual_qa/narrative_v4/choices.md) for live model evaluation.
