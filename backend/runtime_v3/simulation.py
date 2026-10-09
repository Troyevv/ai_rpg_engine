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


def simulate(before_snapshot, snapshot, history_batch, context_length, config, generate,cancelled,warnings,on_repair):
    before,state=before_snapshot['world_state'],snapshot['world_state']
    batch=[]
    if snapshot.get('last_time_skip') and state['meta']['world_time']-before['meta']['world_time']>=45:
        batch,diagnostics=interval_candidates(before,state)
        snapshot['last_time_skip'].update(diagnostics)
        candidate=batch[0] if batch else None
    else:
        candidate=background_candidate(before,state)
    if not candidate or cancelled.is_set():return snapshot,history_batch
    camera=observe(snapshot,actor_id=candidate['actor_id'],allow_protagonist=True)
    protected=state['camera']['controlled_actor_id']
    if batch: camera['_background_actor_ids']=list({cid for item in batch for cid in item['actor_ids']})
    instruction=('Фоновая симуляция: '+candidate['reason']+'. Продолжи только эту ситуацию до текущего времени мира. '
        'elapsed_minutes=0. Не действуй за управляемого персонажа '+str(protected)+'. Не добавляй его в сцену. '
        'Намерение может остаться незавершённым. Не выдумывай события без причины.')
    if batch: instruction+=' Обработай одной группой только причинно обусловленные изменения интервала: '+json.dumps(batch,ensure_ascii=False)+'. Не обязаны завершиться все намерения.'
    messages=build_context(camera,[],instruction,'background',context_length,config['max_tokens'],prompts=config.get('_prompts'))
    narrative=''.join(generate('world_simulation',messages,config['max_tokens'],config.get('temperature',0.8)))
    if cancelled.is_set():return snapshot,history_batch
    if not narrative.strip():raise ValueError('Фоновая симуляция вернула пустой текст.')
    feedback=None
    for attempt in range(2):
        messages=build_context(camera,[],instruction,'background',context_length,config['update_tokens'],extraction_text=narrative,validation_feedback=feedback,prompts=config.get('_prompts'))
        payload=''.join(generate('world_simulation_delta' if attempt==0 else 'world_simulation_repair',messages,config['update_tokens'],0.1,response_format={'type':'json_object'}))
        if cancelled.is_set():return snapshot,history_batch
        try:
            resolved=StateResolver(camera['world_state'],narrative,'',turn_id=state['meta']['turn_id'],observed=False,mode='background').resolve(payload)
            if resolved.state['meta']['world_time']!=state['meta']['world_time']:
                fatal('background не должен продвигать часы','background_time_invalid',repairable=True)
            if protected is not None and (protected in resolved.state['camera']['present_character_ids'] or
                resolved.state['characters'][protected]!=state['characters'][protected]):
                fatal('background меняет управляемого персонажа','background_agency_invalid',repairable=True)
            break
        except StructuralDeltaError as exc:
            if attempt==1 or not exc.repairable:raise
            diagnostic = exc.diagnostic('world_simulation_repair')
            on_repair(diagnostic)
            feedback = repair_feedback(diagnostic, payload, camera['world_state'])
    result=deepcopy(snapshot)
    result['world_state']=resolved.state
    result['world_state']['camera']=deepcopy(state['camera'])
    scheduled_ids=[eid for item in batch for eid in item['scheduled_ids']] if batch else [candidate['scheduled_id']]
    for eid in scheduled_ids:
        if eid: result['world_state']['scheduled_events'][eid]['last_attempt_minute']=state['meta']['world_time']
    if batch: result['last_time_skip']['background_results']=[dict(actor_id=c['actor_id'],scheduled_ids=c['scheduled_ids']) for c in batch]
    # Hidden simulation cannot grant knowledge to anyone in the player's scene.
    for key in list(result['world_state']['knowledge']):
        if result['world_state']['knowledge'][key]['actor_id'] in state['camera']['present_character_ids']:
            if key in state['knowledge']: result['world_state']['knowledge'][key]=deepcopy(state['knowledge'][key])
            else: del result['world_state']['knowledge'][key]
    resolved.history['knowledge_acquisitions']=[k for k in resolved.history['knowledge_acquisitions'] if k['actor_id'] not in state['camera']['present_character_ids']]
    result['character_cards'].extend(resolved.cards)
    assert_world_state_v3_invariants(result['world_state'],state)
    for section,records in resolved.history.items():history_batch[section].extend(records)
    warnings.extend(dict(w,stage='background_simulation') for w in resolved.warnings)
    return result,history_batch
