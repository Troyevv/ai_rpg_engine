"""Camera commands never create world scenes or move characters."""
from copy import deepcopy
from backend.runtime_v3.models import assert_world_state_v3_invariants


def controlled(snapshot):
    return snapshot['world_state']['camera']['controlled_actor_id']


def transition(snapshot, actor, source=None):
    from backend.runtime_v3.protagonist import transition as change
    return change(snapshot,'temporary',actor,'compatibility-control')[0]



def observe(snapshot, actor_id=None, scene_id=None, allow_protagonist=False):
    state=snapshot['world_state']
    main=state['meta'].get('current_protagonist_id') or snapshot.get('campaign',{}).get('protagonist_id')
    if actor_id==main and actor_id is not None and not allow_protagonist:
        raise ValueError('Для камеры мира выбери NPC.')
    if actor_id is None and scene_id:
        lid=scene_id.removeprefix('view:')
        if scene_id=='view:camera':
            lid=state['camera']['location_id']
            subject=state['camera'].get('subject_id') or state['camera']['controlled_actor_id']
            if subject in state['characters'] and state['characters'][subject]['life_status']!='dead': actor_id=subject
        actor_id=actor_id or next((cid for cid,c in state['characters'].items() if c['location_id']==lid and c.get('life_status') != 'dead'),None)
    if actor_id is None:
        main_location=state['characters'].get(main,{}).get('location_id')
        actor_id=next((cid for cid,c in state['characters'].items() if c.get('life_status') != 'dead' and (allow_protagonist or (cid!=main and (c['location_id'] is None or c['location_id']!=main_location)))),None)
    if actor_id is None:raise ValueError('Нет доступного персонажа для наблюдения.')
    from backend.runtime_v3.protagonist import transition as change
    result=change(snapshot,'observe',actor_id,'compatibility-observation')[0]
    if not allow_protagonist and main in result['world_state']['camera']['present_character_ids']:
        raise ValueError('Основной ГГ присутствует в этой сцене.')
    result['world_state']['camera'].update(controlled_actor_id=None,mode='observer')
    return result
