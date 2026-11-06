"""Lossless coalescing of draft relation descriptions, never inference of history.

Only identical typed active phase data may share a record. Prose is retained
verbatim and remains subject to the ordinary semantic review. Closed phases
and directed emotional relationships are untouched. Exact copies
of directed objective records may coalesce without reversing their endpoints.
"""
from copy import deepcopy
from pydantic import ValidationError
from backend.runtime_v3.models import ObjectiveRelation
from backend.runtime_v3.life import SYMMETRIC


def pointer(key):
    return '/world/objective_relations/'+key.replace('~','~0').replace('/','~1')


def plans(state):
    world=state.get('world') if isinstance(state,dict) else None
    rows=world.get('objective_relations') if isinstance(world,dict) else None
    if not isinstance(rows,dict):return []
    groups={}; result=[]
    for key,row in sorted(rows.items()):
        try: typed=ObjectiveRelation.model_validate(row).model_dump()
        except (ValidationError,TypeError):continue
        if typed['id']!=key or typed['status']!='active':continue
        if typed['kind'] in SYMMETRIC:
            typed['source_id'],typed['target_id']=sorted((typed['source_id'],typed['target_id']))
        signature=(typed['kind'],typed['source_id'],typed['target_id'],typed['status'])
        for other,previous in groups.get(signature,[]):
            differences=[f for f in typed if f!='id' and typed[f]!=previous[f]]
            safe=not differences or typed['kind'] in SYMMETRIC and set(differences)<={'context','evidence'}
            result.append(dict(paths=[pointer(other),pointer(key)],ids=[other,key],differences=differences,safe=safe,
                               records=[deepcopy(rows[other]),deepcopy(row)]))
            if safe:break
        groups.setdefault(signature,[]).append((key,typed))
    return result


def merge(state,selected=None):
    value=deepcopy(state)
    world=value.get('world') if isinstance(value,dict) else None
    rows=world.get('objective_relations') if isinstance(world,dict) else None
    if not isinstance(rows,dict):return value
    remap={}
    for row in rows.values():
        if isinstance(row,dict) and isinstance(row.get('kind'),str) and row['kind'] in SYMMETRIC and all(isinstance(row.get(f),str) for f in ('source_id','target_id')):
            row['source_id'],row['target_id']=sorted((row['source_id'],row['target_id']))
    for plan in plans(value):
        if not plan['safe'] or selected is not None and plan['ids']!=selected:continue
        keep,drop=plan['ids']
        while keep in remap:keep=remap[keep]
        if drop in remap:continue
        for field in ('context','evidence'):
            # Newline is a separator, not a claim of semantic equivalence.
            texts=[rows[keep].get(field,''),rows[drop].get(field,'')]
            if texts[1] and texts[1]!=texts[0]:rows[keep][field]='\n'.join(t for t in texts if t)
        remap[drop]=keep;del rows[drop]
    def references(v,field=''):
        if isinstance(v,dict):return {k:references(x,k) for k,x in v.items()}
        if isinstance(v,list):return [references(x,field) for x in v]
        if isinstance(v,str) and field in ('objective_relation_id','objective_relation_ids','relation_id','relation_ids'):
            while v in remap:v=remap[v]
        return v
    return references(value)
