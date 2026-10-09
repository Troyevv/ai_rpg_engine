"""Camera commands never create world scenes or move characters."""
from copy import deepcopy
from backend.runtime_v3.models import assert_world_state_v3_invariants


def controlled(snapshot):
    return snapshot['world_state']['camera']['controlled_actor_id']


def transition(snapshot, actor, source=None):
    result=deepcopy(snapshot);state=result['world_state']
    if actor not in state['characters'] or state['characters'][actor].get('life_status') == 'dead' or any(c['id']==actor and c.get('available') is False for c in result['character_cards']):
        raise ValueError('Персонаж недоступен.')
    lid=state['characters'][actor]['location_id']
    present=[cid for cid,c in state['characters'].items() if c['location_id']==lid and c.get('life_status') != 'dead'] if lid is not None else [actor]
    state['camera']=dict(location_id=lid,present_character_ids=present,controlled_actor_id=actor,mode='actor',situation=state['characters'][actor]['situation'])
    assert_world_state_v3_invariants(state)
    return result


def observe(snapshot, actor_id=None, scene_id=None, allow_protagonist=False):
    state=snapshot['world_state']
    main=snapshot.get('campaign',{}).get('protagonist_id')
    if actor_id==main and actor_id is not None and not allow_protagonist:
        raise ValueError('Для камеры мира выбери NPC.')
    if actor_id is None and scene_id:
        lid=scene_id.removeprefix('view:')
        if scene_id=='view:camera':lid=state['camera']['location_id']
        actor_id=next((cid for cid,c in state['characters'].items() if c['location_id']==lid and c.get('life_status') != 'dead'),None)
    if actor_id is None:
        main_location=state['characters'].get(main,{}).get('location_id')
        actor_id=next((cid for cid,c in state['characters'].items() if c.get('life_status') != 'dead' and (allow_protagonist or (cid!=main and (c['location_id'] is None or c['location_id']!=main_location)))),None)
    if actor_id is None:raise ValueError('Нет доступного персонажа для наблюдения.')
    result=transition(snapshot,actor_id)
    if not allow_protagonist and main in result['world_state']['camera']['present_character_ids']:
        raise ValueError('Основной ГГ присутствует в этой сцене.')
    result['world_state']['camera'].update(controlled_actor_id=None,mode='observer')
    return result
