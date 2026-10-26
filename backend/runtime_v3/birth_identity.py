"""DOB calculation metadata never grants or removes birth/name authorization.

Legacy payloads are interpreted on a copy; immutable history is not rewritten.
Unknown provenance remains protected. Only an explicit born pregnancy/child link
can recover a real birth whose metadata was overwritten by the old DOB editor.
"""
from copy import deepcopy

DOB_KEYS = frozenset(('source','input_signature','twin_group','seed','algorithm'))
DOB_SOURCES = frozenset(('authoring_automatic','automatic','manual','explicit','unknown'))

def dob_metadata(actor):
    legacy=actor.get('birth_provenance') or {}
    values={k:v for k,v in legacy.items() if k in DOB_KEYS and (k!='source' or v in DOB_SOURCES)}
    return dict(values,**(actor.get('birth_date_provenance') or {}))

def game_metadata(actor):
    legacy=actor.get('birth_provenance') or {}
    return {k:v for k,v in legacy.items() if k not in DOB_KEYS or k=='source' and v not in DOB_SOURCES}

def is_game_birth(state,cid):
    actor=state['characters'][cid]
    return bool(game_metadata(actor)) or any(
        p.get('status')=='born' and any(c.get('id')==cid for c in p.get('children',[]))
        for p in state.get('pregnancies',{}).values())

def compatible_state(state):
    result=deepcopy(state)
    actors=result.get('characters',{})
    for cid,actor in actors.items():
        if not isinstance(actor,dict):continue
        matches=[p for p in result.get('pregnancies',{}).values()
                 if p.get('status')=='born' and any(c.get('id')==cid for c in p.get('children',[]))]
        if len(matches)==1 and not game_metadata(actor):
            # Preserve legacy DOB data, not a new fact or a fabricated birth event.
            actor['birth_date_provenance']=dob_metadata(actor)
            actor['birth_provenance']={'pregnancy_id':matches[0]['id'],'recovered_from':'pregnancy_child'}
    return result
