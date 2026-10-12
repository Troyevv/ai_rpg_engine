"""Shared portrait selection for cards, genealogy and future phone consumers."""
from backend.runtime_v3.calendar import age_on, current_time, profile_of


def life_period(state, cid):
    actor=state['characters'][cid]
    age=age_on(actor.get('birth_date'),current_time(state)['date'],profile_of(state))
    stage=('infant' if age<2 else 'child' if age<13 else 'adolescent' if age<18 else 'adult') if age is not None else actor.get('developmental_stage','unknown')
    return age,stage


def authorized(state, cid):
    from backend.runtime_v3.reproduction import known_birth
    return cid in state['characters'] and known_birth(state,cid,state['camera']['controlled_actor_id'])


def select_portrait(state, cid):
    age,stage=life_period(state,cid)
    rows=[]
    for p in state['characters'][cid].get('portraits',[]):
        if p['deleted'] or p['stage']!=stage: continue
        if any(p[k] is not None for k in ('min_age','max_age')):
            if age is None or p['min_age'] is not None and age<p['min_age'] or p['max_age'] is not None and age>p['max_age']: continue
        rows.append(p)
    return max(rows,key=lambda p:(p['order'],p['id']),default=None)


def silhouette(state,cid):
    actor=state['characters'][cid];observer=state['camera']['controlled_actor_id']
    sex=actor.get('biological_sex')
    if actor.get('birth_provenance') and observer!=cid:
        pid=actor['birth_provenance'].get('pregnancy_id');p=state.get('pregnancies',{}).get(pid,{})
        fid=p.get('sex_fact_ids',{}).get(cid)
        if state['knowledge'].get(str(observer)+':'+str(fid),{}).get('status')!='known': sex=None
    return sex if sex in ('male','female') else 'neutral'


def projection(state,cid):
    if not authorized(state,cid): return dict(portrait=None,silhouette='neutral')
    p=select_portrait(state,cid)
    return dict(portrait={k:p[k] for k in ('id','asset_id','width','height','crop','label')} if p else None,
                silhouette=silhouette(state,cid))
