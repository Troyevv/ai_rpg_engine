"""Player-authored edits: no LLM or narrative evidence, strict current invariants."""
from copy import deepcopy
from backend.runtime_v3.lifecycle import replace_active
from backend.runtime_v3.models import Relationship,assert_world_state_v3_invariants
from backend.services.relation_dimensions import RELATION_DIMENSIONS


def edit_motivation(snapshot,actor_id,goals,intentions):
    result=deepcopy(snapshot);state=result['world_state']
    if state['camera']['controlled_actor_id']!=actor_id:raise ValueError('Можно редактировать только управляемого персонажа.')
    for value,maximum in ((goals,4000),(intentions,2000)):
        if not isinstance(value,list) or len(value)>20 or any(not isinstance(v,str) or not v.strip() or len(v)>maximum for v in value):
            raise ValueError('Недопустимый размер цели или намерений.')
    for field, values in (('goals', goals), ('intentions', intentions)):
        state['characters'][actor_id][field] = replace_active(state['characters'][actor_id][field], [v.strip() for v in values], actor_id, field, state['meta']['turn_id'])
    assert_world_state_v3_invariants(state)
    return result


def edit_relationship(snapshot,actor_id,target_id,context,dimensions,delete=False):
    result=deepcopy(snapshot);state=result['world_state']
    if state['camera']['controlled_actor_id']!=actor_id:raise ValueError('Редактировать можно только отношения управляемого персонажа.')
    if target_id not in state['characters'] or actor_id==target_id:raise ValueError('Выбери другого существующего персонажа.')
    key=actor_id+':'+target_id
    if delete:
        if key not in state['relationships']:raise ValueError('Отношение уже удалено.')
        del state['relationships'][key]
    else:
        if not isinstance(context,str) or not context.strip() or len(context)>12000:raise ValueError('Опиши отношение персонажа.')
        state['relationships'][key]=Relationship(source_id=actor_id,target_id=target_id,context=context.strip(),dimensions=dimensions).model_dump()
    assert_world_state_v3_invariants(state)
    return result
