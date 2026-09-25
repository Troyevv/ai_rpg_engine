"""Player edits only the outgoing relation of the currently controlled actor."""
from copy import deepcopy
from math import isfinite
from backend.services.world import normalize
from backend.services.world_delta import RELATION_DIMENSIONS


def edit_relationship(original,actor_id,target_id,context,dimensions,delete=False):
    state=normalize(original)
    if actor_id!=state.get('controlled_actor_id'):
        raise ValueError('Редактировать можно только отношения управляемого персонажа.')
    if actor_id==target_id or target_id not in state['world']['characters']:
        raise ValueError('Выбери другого существующего персонажа.')
    if set(dimensions)-set(RELATION_DIMENSIONS) or any(type(v) not in (int,float) or not isfinite(v) or not -100<=v<=100 for v in dimensions.values()):
        raise ValueError('Недопустимые параметры отношений.')
    key=actor_id+':'+target_id
    state=deepcopy(state)
    relationships=state['world']['relationships']
    if delete:
        if key not in relationships:raise ValueError('Отношение уже удалено.')
        del relationships[key]
    else:
        if not isinstance(context,str) or not context.strip() or len(context)>12000:
            raise ValueError('Опиши отношение персонажа.')
        relationships[key]={'source_id':actor_id,'target_id':target_id,'context':context.strip(),
                            'dimensions':dict(dimensions),'provenance':{'source':'player_edit'}}
    from backend.services.world import compatibility_view
    return compatibility_view(state)
