"""Bounded autonomous scene, reusing GM/context/delta. Its result joins the parent transaction."""
from copy import deepcopy
from backend.services.director import background_candidate, observe
from backend.services.world import apply_legacy, record_narrative
from backend.services.world_delta import apply_delta
from backend.services.pov import apply_scene_policy
from backend.services.timeline import current_time


def simulate(before, state, sequence, context_length, config, generate, cancelled):
    candidate=background_candidate(before,state)
    if not candidate or cancelled.is_set():return state
    from context_builder import build_context
    from state_updates import apply_updates
    camera=observe(state,actor_id=candidate['actor_id'],allow_protagonist=True)
    instruction=('Фоновая симуляция по причине '+candidate['reason']+'. Это не наблюдение игрока. '
                 'Продолжи только эту ситуацию до текущего времени мира; не продвигай глобальные часы. '
                 'Не вводи текущего управляемого персонажа '+str(state.get('controlled_actor_id'))+'. '
                 'Уже подтверждённый срок может остаться незавершённым. Не создавай события без причины.')
    messages=build_context(camera,[],instruction,'background',context_length,config['max_tokens'],prompts=config.get('_prompts'))
    messages[-1]['content']+='\n'+instruction
    narrative=''.join(generate('world_simulation',messages,config['max_tokens'],config.get('temperature',0.8)))
    if cancelled.is_set():return state
    if not narrative.strip():raise ValueError('Фоновая симуляция вернула пустую сцену.')
    messages=build_context(camera,[],instruction,'background',context_length,config['update_tokens'],extraction_text=narrative,prompts=config.get('_prompts'))
    payload=''.join(generate('world_simulation_delta',messages,config['update_tokens'],0.1,response_format={'type':'json_object'}))
    if cancelled.is_set():return state
    updated,_,changes=apply_updates(camera,payload,narrative,'',sequence,'background')
    updated,audience=apply_scene_policy(camera,updated,changes,'background')
    if state.get('controlled_actor_id') in audience:
        raise ValueError('Фоновая симуляция не может действовать за управляемого персонажа.')
    if current_time(updated)!=current_time(state):
        raise ValueError('Фоновая симуляция должна завершаться на текущем времени мира.')
    updated=apply_legacy(updated,changes,sequence,'background')
    if changes.get('world_delta'):
        point=state['world']['characters'][candidate['actor_id']]
        updated=apply_delta(updated,changes['world_delta'],narrative,'',sequence,since=point.get('minute') if point.get('minute') is not None else current_time(state))
    # No simulated scene enters the player's observed timeline or the main POV's memory.
    old=set(state['world']['events'])
    for eid,event in updated['world']['events'].items():
        if eid not in old:event['player_observed']=False
    record_narrative(updated,narrative,sequence,False,old)
    if candidate['scheduled_id']:
        updated['world']['scheduled_events'][candidate['scheduled_id']]['last_attempt_minute']=current_time(state)
    for key in ('camera','controlled_actor_id','scene','scene_meta','pov_transition'):
        if key in state:updated[key]=deepcopy(state[key])
        else:updated.pop(key,None)
    updated['sections']['scene']=state['sections']['scene']
    return updated
