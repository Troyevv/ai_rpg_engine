"""Explicitly authorized QA of one mandatory revision, not a production default.

Reuse a recorded first response. Exactly one provider dispatch, including when
the first candidate resolves. No oracle errors, replacement Narrative or retry.
"""
from copy import deepcopy
import json
import time

from context_builder import estimate
from backend.runtime_v3.scene_repair import record_key, references, repair_schema, strings
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.player_actions import resolver_options
from backend.services.structured_extraction import request_schema
from backend.services.world_delta_errors import StructuralDeltaError
from .compound import CompoundCandidate, effect_id


REVISION = '''This is the one explicitly requested semantic revision of the SAME candidate.
Structural diagnostics are real but do not exhaust semantic errors. Compare the entire
unchanged Narrative and player input with its consequential effects. Correct actual
omissions/misinterpretations, preserve correct independent outcomes and optional choices.
In particular distinguish real travel from intent, actual perceivers from mere presence,
the stated proposition from the whole related secret, and a chosen act from a new reply
or decision. A genuine but unrelated input quote never authorizes a different decision.
Narrator chronology and unauthorized player decisions remain explicit findings for
normal reauthor; do not delete their evidence or adjust time merely to obtain acceptance.
Do not add claims to questions/greetings that convey no new information. Do not invent
consequences. Revise only affected source records or related domain records, with a
source-linked reason. Unmentioned records are retained. A source/effect is not deletable.
Return the hash-bound patch, not a new full result, prose summary, score or PASS flag.
If no correction is needed, return empty replacements/sections and explain no change.
There will be no further automatic repair of this revision.
'''


def revision_feedback(candidate, diagnostics, original):
    """Explicit whole-candidate review scope, not fabricated Runtime diagnostics.

This QA mode may amend any named source; the established patch owner retains
unmentioned records, hash binding and typed dependencies. Semantic preservation
still needs independent evaluation; a broad review scope cannot prove it.
"""
    info = json.loads(candidate.feedback(diagnostics, original))
    if candidate.base is None:
        raise ValueError('Revision experiment requires a parsed, addressable first candidate')
    base = candidate.base
    sections = {'scene'} | {
        key for key, schema in candidate.schema['properties'].items()
        if schema.get('type') == 'array' and key not in ('scene_steps', 'choices')
    }
    dependencies = references(base)
    actors = set()
    for source in base['scene_steps']:
        dependencies.update(effect_id(source, j) for j in range(len(source['effects'])))
        for effect in source['effects']:
            for key in ('actor_id', 'actor_ids', 'source_actor_id', 'target_ids'):
                actors.update(strings(effect.get(key)))
    candidate.scope = dict(
        step_ids=[s['id'] for s in base['scene_steps']], sections=sorted(sections),
        record_keys={key: [record_key(v) for v in values]
                     for key, values in base.items() if key in sections and isinstance(values, list)},
        dependencies=sorted(dependencies), actor_ids=sorted(actors),
    )
    candidate.effect_scope = {s['id']: set(range(len(s['effects']))) for s in base['scene_steps']}
    info.update(scope=deepcopy(candidate.scope), record_keys=deepcopy(candidate.scope['record_keys']),
                revision_scope='whole_candidate_semantic_review',
                contract=info['contract'] + '\n' + REVISION)
    return json.dumps(info, ensure_ascii=False)


def run(case, original, generate, record):
    state = case['snapshot']['world_state']
    turn = state['meta']['turn_id'] + 1
    messages = deepcopy(case['messages']['compound259'])
    schema = request_schema(messages)
    candidate = CompoundCandidate(state, case['narrative'], case['player_input'], turn,
                                  version=8, schema=schema,
                                  on_record=lambda audit: record(dict(event='candidate', audit=audit)))
    options = case.get('resolver_options') or resolver_options(state, case['player_input'], contract_version=8)

    def resolve(response):
        return StateResolver(state, case['narrative'], case['player_input'], turn_id=turn,
                             **options).resolve(candidate.parse(response, defer_errors=True))

    def resolved(event, result):
        record(dict(event=event, state=result.state, history=result.history,
                    warnings=result.warnings, choices=result.choices,
                    semantic_status='REQUIRES_INDEPENDENT_REVIEW'))

    record(dict(event='reused_first_response', response=original, new_paid_call=False))
    diagnostics = []
    try:
        resolved('before_revision', resolve(original))
    except StructuralDeltaError as exc:
        diagnostics = exc.diagnostics('before_revision')
        record(dict(event='before_revision_diagnostics', diagnostics=diagnostics))
    feedback = revision_feedback(candidate, diagnostics, original)
    projected = repair_schema(schema, feedback)
    for message in messages:
        if message['content'].startswith('JSON Schema\n'):
            message['content'] = 'JSON Schema\n' + json.dumps(projected, ensure_ascii=False, separators=(',', ':'))
    messages[0]['content'] += '\nCandidate revision protocol:\n' + feedback
    config = dict(provider='deepseek', model=case['profiles']['compound259'], thinking='off',
                  temperature=.1, max_tokens=8192, response_format={'type': 'json_object'},
                  structured_schema=request_schema(messages), extraction_transport='responses_json_schema')
    assert estimate(messages) < case['config']['context_length'] - config['max_tokens'] - 256
    record(dict(event='request', messages=messages, config=config))
    usage = []
    chunks = []
    start = time.monotonic()
    try:
        for chunk in generate(messages=messages, require_complete=True, on_usage=usage.append, **config):
            chunks.append(chunk)
            record(dict(event='chunk', text=chunk))
    except BaseException as exc:
        record(dict(event='error', error_type=type(exc).__name__, partial=''.join(chunks), usage=usage))
        raise
    response = ''.join(chunks)
    record(dict(event='response', response=response, usage=usage, provider_seconds=time.monotonic()-start))
    try:
        resolved('resolved', resolve(response))
    except StructuralDeltaError as exc:
        record(dict(event='diagnostics', diagnostics=exc.diagnostics('after_revision')))
    record(dict(event='end', calls=1, end_to_end_seconds=time.monotonic()-start))
