"""Optional background uses exactly the same v3 resolver and current invariants."""
from copy import deepcopy
import json
from backend.runtime_v3.camera import observe
from backend.runtime_v3.director import background_candidate, interval_candidates
from backend.runtime_v3.context import build_context
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.raw import repair_feedback
from backend.runtime_v3.models import assert_world_state_v3_invariants,fatal
from backend.services.world_delta_errors import StructuralDeltaError


def background_resolver_options(state):
    """Shared hidden-simulation boundary for production and offline/live QA."""
    visible = set(state['camera']['present_character_ids']) | set(state['camera'].get('observed_character_ids', []))
    return dict(observed=False, mode='background',
                protected_actor_id=state['camera']['controlled_actor_id'],
                protected_knowledge_actor_ids=visible, require_player_agency=False,
                agency_audit_required=False)


class BackgroundGenerationError(RuntimeError):
    """A failed optional provider attempt, including an unknown remote result."""

    def __init__(self, message, *, code="background_transport_failed"):
        super().__init__(message)
        self.code = code


def background_context(*args, **kwargs):
    try:
        return build_context(*args, **kwargs)
    except ValueError as exc:
        # Context assembly is pure candidate validation, not SQLite publication.
        raise BackgroundGenerationError(str(exc), code='background_context_invalid') from exc


def optional_generate(generate):
    # Scope transport handling to the provider iterator. Persistence, selection
    # and application programming errors must not be mistaken for network errors.
    def wrapped(*args, **kwargs):
        import requests
        try:
            yield from generate(*args, **kwargs)
        except (RuntimeError, OSError, requests.RequestException) as exc:
            raise BackgroundGenerationError(type(exc).__name__) from exc
    return wrapped


def simulate(before_snapshot, snapshot, history_batch, context_length, config, generate, cancelled,
             warnings, on_repair, world_history=None):
    before, state = before_snapshot['world_state'], snapshot['world_state']
    result, history = deepcopy(snapshot), deepcopy(history_batch)
    cursor = result.setdefault('background_considerations', dict(
        since_minute=before['meta']['world_time'], attempts={}))
    candidate = background_candidate(before, state, cursor)
    if not candidate or cancelled.is_set():
        return result, history
    batch = []
    if snapshot.get('last_time_skip') and state['meta']['world_time'] - before['meta']['world_time'] >= 45:
        batch, diagnostics = interval_candidates(before, state)
        # Preserve pregnancy selection. For other causes the existing interval
        # grouping supplies bounded context for this one independent scene.
        batch = [g for g in batch if g['actor_id'] == candidate['actor_id']][:1]
        result['last_time_skip'].update(diagnostics, simulated_candidates=0)
    try:
        accepted, accepted_history = _simulate_candidate(result, history, candidate, batch,
            context_length, config, optional_generate(generate), cancelled, warnings, on_repair, world_history)
    except (StructuralDeltaError, BackgroundGenerationError) as exc:
        if cancelled.is_set():
            return snapshot, history_batch
        # The independent candidate was never published; keep exactly foreground.
        accepted, accepted_history = result, history
        detail = dict(code=getattr(exc, 'code', 'background_transport_failed'),
                      stage='background_simulation', scope='independent_background', action='discard_background',
                      candidate_id=candidate['candidate_id'], retry='future_consideration')
        warnings.append(detail)
        on_repair(dict(detail, stage='background_rejected'))
        outcome = 'rejected'
    else:
        outcome = 'accepted'
    if cancelled.is_set():
        return snapshot, history_batch
    now = state['meta']['world_time']
    cursor = accepted['background_considerations']
    cursor['last_dispatch_minute'] = now
    cursor['last_dispatch_turn'] = state['meta']['turn_id']
    cursor['attempts'][candidate['candidate_id']] = now
    # At most one timestamp per existing cause; retain old attempts for fair
    # ordering, prune removed causes. History owns outcomes, not this cursor.
    existing = {prefix + key for prefix, section in (('pregnancy:', 'pregnancies'),
        ('scheduled:', 'scheduled_events'), ('thread:', 'threads'), ('motivation:', 'characters'))
        for key in accepted['world_state'][section]}
    cursor['attempts'] = {key: minute for key, minute in cursor['attempts'].items() if key in existing}
    accepted_history['state_changes'].append(dict(kind='background_consideration',
        candidate_id=candidate['candidate_id'], minute=now, turn_id=state['meta']['turn_id'], outcome=outcome))
    return accepted, accepted_history


def _simulate_candidate(snapshot, history_batch, candidate, batch, context_length, config,
                        generate, cancelled, warnings, on_repair, world_history):
    # Neither failed extraction nor a post-resolution invariant may leak into
    # the foreground candidate or its History batch.
    snapshot, history_batch = deepcopy(snapshot), deepcopy(history_batch)
    state = snapshot['world_state']
    camera=observe(snapshot,actor_id=candidate['actor_id'],allow_protagonist=True)
    boundary=background_resolver_options(state)
    protected=boundary['protected_actor_id']
    visible_actors=boundary['protected_knowledge_actor_ids']
    if batch: camera['_background_actor_ids']=list({cid for item in batch for cid in item['actor_ids']})
    instruction=('Фоновая симуляция: '+candidate['reason']+'. Продолжи только эту ситуацию до текущего времени мира. '
        'elapsed_minutes=0. Не действуй за управляемого персонажа '+str(protected)+'. Не добавляй его в сцену. '
        'Намерение может остаться незавершённым. Не выдумывай события без причины.')
    if batch: instruction+=' Обработай одной группой только причинно обусловленные изменения интервала: '+json.dumps(batch,ensure_ascii=False)+'. Не обязаны завершиться все намерения.'
    messages=background_context(camera,[],instruction,'background',context_length,config['max_tokens'],prompts=config.get('_prompts'),world_history=world_history)
    pacing_decision=messages.selection['pacing']
    initiative_decision=messages.selection['initiative']
    from backend.services.letter_sources import generate_result
    narrative, artifacts = generate_result(generate, 'world_simulation',messages,config['max_tokens'],config.get('temperature',0.8), camera['world_state'])
    if cancelled.is_set():return snapshot,history_batch
    if not narrative.strip():raise BackgroundGenerationError('empty_background')
    feedback=None
    for attempt in range(2):
        messages=background_context(camera,[],instruction,'background',context_length,config['update_tokens'],extraction_text=narrative,validation_feedback=feedback,pacing_decision=pacing_decision,initiative_decision=initiative_decision,prompts=config.get('_prompts'),world_history=world_history)
        payload=''.join(generate('world_simulation_delta' if attempt==0 else 'world_simulation_repair',messages,config['update_tokens'],0.1,response_format={'type':'json_object'}))
        if cancelled.is_set():return snapshot,history_batch
        try:
            resolved=StateResolver(camera['world_state'],narrative,'',letter_sources=artifacts,pacing_decision=getattr(messages,'selection',{}).get('pacing'),initiative_decision=initiative_decision,turn_id=state['meta']['turn_id'],**boundary,milestone_query=(world_history or {}).get('_milestone_query'),development_query=(world_history or {}).get('_development_query'),
                relationship_query=(world_history or {}).get('_relationship_query'),relationship_receipts=history_batch.get('relationship_changes',[]),
                actor_names={c['id']:c['name'] for c in snapshot['character_cards']}).resolve(payload)
            if resolved.state['meta']['world_time']!=state['meta']['world_time']:
                fatal('background не должен продвигать часы','background_time_invalid',repairable=True)
            if protected is not None and (protected in resolved.state['camera']['present_character_ids'] or
                resolved.state['characters'][protected]!=state['characters'][protected]):
                fatal('background меняет управляемого персонажа','background_agency_invalid',repairable=True)
            break
        except StructuralDeltaError as exc:
            diagnostic = exc.diagnostic('world_simulation_repair' if attempt == 0 and exc.repairable else 'background_rejected')
            on_repair(dict(diagnostic, scope='independent_background'))
            if attempt==1 or not exc.repairable:raise
            feedback = repair_feedback(diagnostic, payload, camera['world_state'])
    result=deepcopy(snapshot)
    result['world_state']=resolved.state
    result['world_state']['camera']=deepcopy(state['camera'])
    scheduled_ids=[eid for item in batch for eid in item['scheduled_ids']] if batch else [candidate['scheduled_id']]
    for eid in scheduled_ids:
        if eid: result['world_state']['scheduled_events'][eid]['last_attempt_minute']=state['meta']['world_time']
    if batch:
        result['last_time_skip']['simulated_candidates']=len(batch)
        result['last_time_skip']['background_results']=[dict(actor_id=c['actor_id'],scheduled_ids=c['scheduled_ids']) for c in batch]
    # Hidden simulation cannot grant knowledge to anyone in the player's scene.
    for key in list(result['world_state']['knowledge']):
        if result['world_state']['knowledge'][key]['actor_id'] in visible_actors:
            if key in state['knowledge']: result['world_state']['knowledge'][key]=deepcopy(state['knowledge'][key])
            else: del result['world_state']['knowledge'][key]
    resolved.history['knowledge_acquisitions']=[k for k in resolved.history['knowledge_acquisitions'] if k['actor_id'] not in visible_actors]
    resolved.history['state_changes'] = [c for c in resolved.history['state_changes']
        if c.get('kind') != 'knowledge_transition' or c.get('actor_id') not in visible_actors]
    from backend.services.npc_review import publish_cards
    publish_cards(result, resolved)
    assert_world_state_v3_invariants(result['world_state'],state)
    for section,records in resolved.history.items():history_batch[section].extend(records)
    warnings.extend(dict(w,stage='background_simulation') for w in resolved.warnings)
    return result,history_batch
