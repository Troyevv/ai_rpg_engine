"""Shared portrait selection for cards, genealogy and future phone consumers."""
from backend.runtime_v3.birth_identity import is_game_birth, birth_sex_disclosed
from backend.runtime_v3.calendar import age_on, current_time, profile_of


def life_period(state, cid):
    actor=state['characters'][cid]
    age=age_on(actor.get('birth_date'),current_time(state)['date'],profile_of(state))
    stage=('infant' if age<2 else 'child' if age<13 else 'adolescent' if age<18 else 'adult') if age is not None else actor.get('developmental_stage','unknown')
    return age,stage


def visual_age(state, cid):
    age, stage = life_period(state, cid)
    if stage in ('infant','child','adolescent'): return stage
    if stage != 'adult': return None
    return 'elderly' if age is not None and age >= 60 else 'mature_adult' if age is not None and age >= 35 else 'young_adult'


def authorized(state, cid):
    from backend.runtime_v3.reproduction import known_birth
    from backend.runtime_v3.appearance import VISUAL_FIELDS, visual_fields_disclosed
    observer = state['camera']['controlled_actor_id']
    return cid in state['characters'] and known_birth(state,cid,observer) and visual_fields_disclosed(state,cid,observer,VISUAL_FIELDS)


def select_portrait(state, cid):
    if state['characters'][cid].get('portrait_mode') == 'procedural': return None
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
    from backend.runtime_v3.appearance import visual_fields_disclosed
    if not visual_fields_disclosed(state,cid,observer,('Пол',)): return 'neutral'
    sex=actor.get('biological_sex')
    def known(fid):
        return state['knowledge'].get(f'{observer}:{fid}', {}).get('status') == 'known'
    if not birth_sex_disclosed(state, cid, observer, known): return 'neutral'
    return sex if sex in ('male','female') else 'neutral'


def projection(state,cid):
    if not authorized(state,cid): return dict(portrait=None,silhouette='neutral')
    p=select_portrait(state,cid)
    descriptor=state['characters'][cid].get('procedural_portrait')
    # Legacy period-bound portraits retain their selection rules. Explicit artistic
    # age choices persist independently of the canon; privacy gates below still apply.
    if descriptor and descriptor.get('visual_age_mode') != 'manual' and descriptor.get('stage') != life_period(state,cid)[1]: descriptor=None
    # Game births have private life/appearance semantics; do not disclose descriptors.
    if is_game_birth(state,cid) and state['camera']['controlled_actor_id'] != cid: descriptor=None
    return dict(procedural_portrait=descriptor, portrait={k:p[k] for k in ('id','asset_id','width','height','crop','label')} if p else None,
                silhouette=silhouette(state,cid))
