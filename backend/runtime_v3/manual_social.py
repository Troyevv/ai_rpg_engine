"""Player corrections reuse the ordinary social transitions and their phase history."""
from backend.runtime_v3.models import Fact, Knowledge, identity
from backend.runtime_v3.life import apply_life
from backend.runtime_v3.residence import apply_residence
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.raw import RawTurnResult


def correct(world, batch, change, revision):
    actor = change['actor_id']
    other = change.get('other_id')
    action = change['action']
    observers = list(dict.fromkeys(change['known_by']))
    participants = [actor, other] if action in ('engaged','spouse','divorce','parent') else [actor]
    if any(cid not in world['characters'] for cid in [*participants,*observers]):
        raise ValueError('Выбери существующих персонажей.')
    turn = world['meta']['turn_id']
    source = 'Ручное исправление канона'
    text = change['description'].strip()
    if not text:
        raise ValueError('Укажи, что произошло.')
    fid = identity('manual-social-fact', revision, action, *participants, text)
    rid = identity('manual-phase', revision, action, *participants)
    params = dict(evidence=source, player_evidence=source, player_assertion='explicit_choice')
    if action in ('engaged','spouse','parent','divorce'):
        section, apply = 'social_relation_changes', apply_life
        if action == 'divorce':
            active = [r['id'] for r in world['objective_relations'].values() if r['status']=='active'
                      and r['kind']=='spouse' and {r['source_id'],r['target_id']} == {actor,other}]
            if len(active)!=1:
                raise ValueError('Для развода нужен действующий брак выбранной пары.')
            items = [dict(params,id=active[0],status='closed',outcome='divorced',closure_fact_id=fid)]
        else:
            items = [dict(params,id=rid,kind=action,source_id=actor,target_id=other,fact_id=fid)]
            if action=='spouse':
                for r in world['objective_relations'].values():
                    if r['kind']=='engaged' and r['status']=='active' and {r['source_id'],r['target_id']} == {actor,other}:
                        items.insert(0,dict(params,id=r['id'],status='closed',outcome='superseded',closure_fact_id=fid))
    else:
        section, apply = ('residence_changes' if action=='move' else 'role_changes'), apply_residence
        prior = change.get('phase_id')
        collection = world['residences'] if action=='move' else world['roles']
        if prior and (prior not in collection or collection[prior]['actor_id']!=actor or collection[prior]['status']!='active'):
            raise ValueError('Выбери действующую запись этого персонажа.')
        if prior and action!='move' and collection[prior]['kind']!='employment':
            raise ValueError('Выбери место работы.')
        if action=='leave_job':
            if not prior:
                raise ValueError('Выбери работу, которую персонаж оставил.')
            items = [dict(params,id=prior,status='closed',outcome='resigned',closure_fact_id=fid)]
        else:
            row = dict(params,id=rid,actor_id=actor,fact_id=fid)
            if action=='move':
                row['location_id']=change.get('location_id')
            else:
                row.update(kind='employment',title=change.get('title','').strip())
            items = [row]
            if prior:
                items.insert(0,dict(params,id=prior,status='closed',outcome='replaced',closure_fact_id=fid))
    resolver = StateResolver(world, '', source, turn_id=turn, scene_version=10)
    state = resolver.state
    state['facts'][fid] = Fact(id=fid,text=text,visibility='secret',character_ids=participants).model_dump()
    for cid in observers:
        state['knowledge'][cid+':'+fid] = Knowledge(actor_id=cid,fact_id=fid,status='known',
            confirmed_once=True,source_turn=turn).model_dump()
        batch.state_changes.append(dict(kind='manual_knowledge',source='player_edit',turn_id=turn,actor_id=cid,fact_id=fid,status='known'))
    apply(resolver, RawTurnResult.parse(dict(final_scene={}, **{section:items})))
    for record in resolver.history.state_changes:
        batch.state_changes.append(dict(record,source='player_edit'))
    return state
