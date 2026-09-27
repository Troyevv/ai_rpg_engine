"""Identity and reference checks independent of prose and intermediate geometry."""
from backend.services.world_delta_errors import StructuralDeltaError


def require(ok, message, code='invalid_reference', **path):
    if not ok:raise StructuralDeltaError('World Delta: '+message, code, **path)


def validate_references(state, delta):
    world=state['world'];actors=set(world['characters']);facts=set(world['facts'])|{f['id'] for f in delta['facts']}
    for section, records in delta.items():
        seen=set()
        for index,r in enumerate(records):
            ids=(r.get('character_ids',[])+r.get('participants',[])+r.get('witnesses',[])
                 +[r[k] for k in ('actor_id','source_id','target_id') if k in r])
            if section=='characters':ids.append(r['id'])
            require(set(ids)<=actors,'неизвестный персонаж','unknown_character',section=section,index=index)
            if section=='transitions':continue
            key=r.get('id') or ((r['actor_id'],r['fact_id']) if section=='knowledge' else (r['source_id'],r['target_id']))
            require(key not in seen,'повтор сущности в delta','canonical_id_conflict',section=section,index=index)
            seen.add(key)
            if section=='events':
                require(r['id'] not in world['events'],'event id уже существует','canonical_id_conflict',section=section,index=index)
                require(set(r['fact_ids'])<=facts,'неизвестный факт события',section=section,index=index)
            if section=='knowledge':require(r['fact_id'] in facts,'неизвестный факт знания',section=section,index=index)
