"""Disposable read projections. None of these scene IDs may enter WorldStateV3."""
from copy import deepcopy
from backend.runtime_v3.models import identity
from backend.runtime_v3.calendar import calendar_label, current_time, nearby_calendar, age_on, profile_of, commitment_view
from backend.runtime_v3.lifecycle import active_texts


def ui_view(snapshot, history=None):
    from backend.runtime_v3.models import assert_world_state_v3_invariants
    from backend.runtime_v3.protagonist import initialize
    snapshot = initialize(deepcopy(snapshot))
    state=assert_world_state_v3_invariants(snapshot['world_state']);history=history or {}
    camera=state['camera'];now=state['meta']['world_time']
    label=lambda minute: calendar_label(state, minute)
    from backend.runtime_v3.personality import project_card
    from backend.runtime_v3.reproduction import known_birth, context_projection, private_fact_ids
    cards=[project_card(c, state['characters'][c['id']], observer=camera['controlled_actor_id'], state=state) for c in snapshot['character_cards'] if known_birth(state,c['id'],camera['controlled_actor_id'])]
    from backend.runtime_v3.appearance import project_card as appearance_card
    from backend.runtime_v3.portraits import projection as portrait_projection
    cards=[dict(appearance_card(c,state,camera['controlled_actor_id']),**portrait_projection(state,c['id'])) for c in cards]
    from backend.runtime_v3.kinship import visible_name
    for card in cards:
        card['name'] = visible_name(state,card['id'],camera['controlled_actor_id'],card['name'])
    from backend.runtime_v3.appearance import visible as visible_appearance
    appearance_history={card['id']:[] for card in cards}
    for change in reversed(history.get('state_changes',[])):
        cid=change.get('entity')
        if change.get('kind')!='appearance_delta' or cid not in appearance_history: continue
        rows=appearance_history[cid]
        if len(rows)>=24 or not visible_appearance(state,cid,dict(source_event_id=True,fact_id=change.get('fact_id')),camera['controlled_actor_id']): continue
        old=change.get('before') or {};new=change.get('after') or {}
        rows.append(dict(before=old.get('text') if visible_appearance(state,cid,old,camera['controlled_actor_id']) else None,after=new.get('text'),minute=change['minute']))
    for card in cards:
        card['appearance_history']=appearance_history[card['id']]
    for card in cards: card['is_player'] = card['id'] == state['meta']['current_protagonist_id']
    names={c['id']:c['name'] for c in cards}
    locations=state['locations']
    def place(lid):return locations.get(lid,{}).get('name','Не указано') if isinstance(lid,str) else 'Не указано'
    scenes={}
    groups={}
    for cid,c in state['characters'].items():
        if c['location_id'] is not None and c.get('life_status') != 'dead':groups.setdefault(c['location_id'],[]).append(cid)
    for lid,present in groups.items():
        sid='view:'+lid
        scenes[sid]=dict(id=sid,location=place(lid),participants=sorted(present),start_minute=now,end_minute=now,
            text='\n'.join(state['characters'][cid]['situation'] for cid in present),status='active',event_ids=[])
    sid='view:camera'
    scenes[sid]=dict(id=sid,location=place(camera['location_id']),participants=list(camera['present_character_ids']),
        start_minute=now,end_minute=now,text=camera['situation'],status='active',event_ids=[])
    world=dict(version=2,characters={},facts={},knowledge=deepcopy(state['knowledge']),relationships=deepcopy(state['relationships']),
        threads=deepcopy(state['threads']),scheduled_events={},scenes=scenes,events={},scene_records={})
    for change in history.get('relationship_changes',[]):
        if not isinstance(change,dict) or change.get('turn_id')!=state['meta']['turn_id'] or change.get('player_observed') is not True or not change.get('before'):continue
        key=change.get('entity')
        if not isinstance(key,str) or key not in world['relationships']:continue
        prior=change.get('before') or {};after=change.get('after') or {}
        if not isinstance(prior,dict) or not isinstance(after,dict):continue
        previous=prior.get('dimensions',{});current=after.get('dimensions',{})
        if not isinstance(previous,dict) or not isinstance(current,dict):continue
        differences=[(v-previous[d])*(1 if d in ('trust','affection','respect','attraction') else -1) for d,v in current.items() if d in previous and type(v) in (int,float) and type(previous[d]) in (int,float)]
        if differences and any(differences):
            value=max(differences,key=abs)
            world['relationships'][key]['change']=dict(direction='mixed' if any(v>0 for v in differences) and any(v<0 for v in differences) else 'up' if value>0 else 'down',reason=after.get('context',''))
    for cid,c in state['characters'].items():
        world['characters'][cid]=dict(c,age=age_on(c.get('birth_date'),current_time(state)['date'],profile_of(state)),goals=active_texts(c['goals']),intentions=active_texts(c['intentions']),obligations=active_texts(c['obligations']),lifecycle={k:c[k] for k in ('goals','intentions','obligations')},location=place(c['location_id']) if c['location_id'] else None,
            scene_id=sid if cid in camera['present_character_ids'] else 'view:'+c['location_id'] if c['location_id'] else None,
            minute=now,last_event_id=None,short_goal='\n'.join(active_texts(c['goals'])))
    for fid,f in state['facts'].items():world['facts'][fid]=dict(f,secret=f['visibility']=='secret',evidence=[])
    for eid,e in state['scheduled_events'].items():
        view = commitment_view(state, e)
        window = view['temporal_projection']
        # Presentation labels are disposable and reuse the canonical calendar.
        view['start_label'] = label(window['start_minute']) if window['start_minute'] is not None else None
        view['end_label'] = label(window['end_minute']) if window['end_minute'] is not None else None
        world['scheduled_events'][eid]=dict(view,participants=e['character_ids'])
    for e in history.get('events',[]):
        if not isinstance(e,dict) or not isinstance(e.get('id'),str) or not isinstance(e.get('text'),str):continue
        if any(not isinstance(e.get(k,[]),list) or any(not isinstance(v,str) for v in e.get(k,[])) for k in ('participants','witnesses')):continue
        world['events'][e['id']]=dict(e,participants=e.get('participants',[]),witnesses=e.get('witnesses',[]),
            calendar_date=current_time(state,e['minute'])['date'] if type(e.get('minute')) is int else e.get('calendar_date'),
            minute=e.get('minute') if type(e.get('minute')) is int else None,recorded_minute=e.get('recorded_minute') if type(e.get('recorded_minute')) is int else -1,source_sequence=e.get('source_sequence',e['turn_id']-1 if type(e.get('turn_id')) is int else None),player_observed=e.get('player_observed',False))
    for i,t in enumerate(history.get('turns',[])):
        if not isinstance(t,dict) or not isinstance(t.get('narrative'),str):continue
        if not isinstance(t.get('camera',{}),dict):continue
        if 'world_time' in t and type(t['world_time']) is not int:continue
        participants=t.get('camera',{}).get('present_character_ids',t.get('participants',[]))
        if not isinstance(participants,list) or any(not isinstance(cid,str) for cid in participants):continue
        rid=t.get('id') if isinstance(t.get('id'),str) else identity('record',t.get('turn_id'),i,t.get('narrative'))
        world['scene_records'][rid]=dict(t,id=rid,participants=t.get('camera',{}).get('present_character_ids',t.get('participants',[])),
            minute=t.get('world_time',t.get('minute')),source_sequence=t.get('sequence',t.get('source_sequence',t['turn_id']-1 if type(t.get('turn_id')) is int else None)),
            pov_actor_id=t.get('camera',{}).get('controlled_actor_id',t.get('pov_actor_id')),
            scene_meta=t.get('scene_meta',dict(time=label(t.get('world_time',now)),location=place(t.get('camera',{}).get('location_id')),present_ids=t.get('camera',{}).get('present_character_ids',[]))))
    for card in cards:
        c=state['characters'][card['id']]
        age = age_on(c.get('birth_date'),current_time(state)['date'],profile_of(state))
        if age is not None: card['fields']['Возраст'] = str(age)
        card['fields'].update({'Сейчас':c['situation'],'Чего хочет':'\n'.join(active_texts(c['goals'])),'Намерения':'\n'.join(active_texts(c['intentions']))})
    metadata=dict(time=label(now),location=place(camera['location_id']),present_ids=list(camera['present_character_ids']))
    campaign=deepcopy(snapshot.get('campaign',{}))
    result=dict(campaign,characters=cards,world=world,controlled_actor_id=camera['controlled_actor_id'],
        narrative_policy={k:deepcopy(state['meta'][k]) for k in ('narrative_pacing','narrative_risk','outcome_preference')},
        protagonist_required=state['meta']['protagonist_required'], protagonist_periods=state['meta']['protagonist_periods'],
        protagonist_id=state['meta']['current_protagonist_id'] or campaign.get('protagonist_id') or next((c['id'] for c in cards if c.get('is_player')),None),
        camera=dict(scene_id=sid,mode=camera['mode'],scope='scene',subject_id=camera.get('subject_id'),pov_actor_id=camera.get('pov_actor_id')),scene=camera['situation'],scene_meta=metadata,
        world_clock=dict(minute=now,last_event_time=label(now),calendar=state['meta'].get('calendar'),projection=current_time(state),nearby=nearby_calendar(state,set(camera['present_character_ids']))),memory=deepcopy(snapshot.get('memory',{})),
        sections=dict(campaign.get('sections',{}),scene=camera['situation']),
        relationships=[dict(r,text=r['context'],target_name=names.get(r['target_id'],'')) for r in world['relationships'].values()],
        facts=[dict(f,known_by=[k['actor_id'] for k in state['knowledge'].values() if k['fact_id']==f['id'] and k['status']=='known']) for f in state['facts'].values()],
        plans=[dict(t,text=t['state'] or t['description'],status='done' if t['status']=='resolved' else 'open') for t in state['threads'].values()],
        events=[dict(e,text=e['text'],character_ids=e['participants'],turn=e['source_sequence']) for e in world['events'].values() if e['player_observed']],
        locations=[dict(l,text=l['description'] or l['name']) for l in locations.values()])
    # Disposable labels let all historical UI surfaces share the same arithmetic.
    minutes = {now}
    for rows in (world['events'].values(), world['scene_records'].values()):
        minutes.update(r['minute'] for r in rows if type(r.get('minute')) is int)
    result['world_clock']['calendar'] = dict(state['meta'].get('calendar') or {},
        labels={str(m): label(m) for m in minutes})
    from backend.runtime_v3.kinship import genealogy, visible_relations
    from backend.runtime_v3.life import capabilities
    for cid, actor in world['characters'].items():
        for field in ('life_fact_id','name_history','parentage_complete_fact_id','personality','values','appearance','portraits'):
            actor.pop(field,None)
    from backend.runtime_v3.personality import visible_item
    # One bounded-per-actor projection pass, not NPC-count × History scans.
    value_rows={}
    for change in reversed(history.get('state_changes',[])):
        if not isinstance(change,dict) or change.get('kind')!='value_delta': continue
        cid=change.get('entity')
        if cid not in world['characters']: continue
        rows=value_rows.setdefault(cid,[])
        if len(rows)>=32: continue
        item=change.get('after') or {}
        if not visible_item(state,cid,item,camera['controlled_actor_id']): continue
        prior=change.get('before') or {}
        before_text=prior.get('text') if visible_item(state,cid,prior,camera['controlled_actor_id']) else None
        rows.append(dict(id=change['id'],before=before_text,text=item['text'],status=item['status'],minute=change['minute']))
    for cid,rows in value_rows.items():
        if rows: world['characters'][cid]['value_history']=rows
    result['life_state'] = ({'life_status':state['characters'][camera['controlled_actor_id']]['life_status'],
        'conditions':[dict(id=c['id'],description=c['description'],status=c['status'],duration=c['duration'])
                      for c in state['conditions'].values() if c['actor_id']==camera['controlled_actor_id']],
        'names':[dict(previous=n['previous'],current=n['current'],date=n['date'],minute=n['minute'])
                 for n in state['characters'][camera['controlled_actor_id']]['name_history']]}
        if camera['controlled_actor_id'] else None)
    result['genealogy'] = genealogy(dict(snapshot,world_state=state))
    result['objective_relations'] = visible_relations(state,camera['controlled_actor_id'])
    result['actor_capabilities'] = capabilities(state,camera['controlled_actor_id']) if camera['controlled_actor_id'] else None
    from backend.runtime_v3.residence import visible_social_state
    result['residence_roles'] = visible_social_state(state,camera['controlled_actor_id'])
    observer=camera['controlled_actor_id']
    reproductive = context_projection(state,set(state['characters']),observer)
    if reproductive: result['reproduction']=reproductive
    hidden={cid for cid in state['characters'] if not known_birth(state,cid,observer)}
    for cid in hidden: world['characters'].pop(cid,None)
    for actor in world['characters'].values():
        if state['characters'][actor['id']].get('birth_provenance'):
            actor['display_name']=names.get(actor['id'])
        for key in ('birth_provenance','biological_sex','identity_components','reproductive_capability'):
            actor.pop(key,None)
    protected=private_fact_ids(state)
    protected |= {identity('communicated_text',e['id']) for e in state.get('remote_events',{}).values() if e['channel']=='TEXT_MESSAGE' and observer != e['sender_id']}
    hidden_facts={fid for fid in protected if state['knowledge'].get(str(observer)+':'+fid,{}).get('status')!='known'}
    world['facts']={k:v for k,v in world['facts'].items() if k not in hidden_facts}
    result['facts']=[f for f in result['facts'] if f['id'] not in hidden_facts]
    world['knowledge']={k:v for k,v in world['knowledge'].items() if v['fact_id'] not in hidden_facts}
    for scene in world['scenes'].values():
        scene['participants']=[cid for cid in scene['participants'] if cid not in hidden]
    for pid,p in state['pregnancies'].items():
        if p['fact_id'] in hidden_facts: world['scheduled_events'].pop(pid,None)
        elif pid in world['scheduled_events']:
            world['scheduled_events'][pid]['description']='Ожидаемые роды'
    # Localized disposable labels; canonical claims retain typed predicates.
    for rows in (world['facts'].values(),result['facts']):
        for f in rows:
            if f['id'] not in protected: continue
            claim=f.get('claim') or {};predicate=claim.get('predicate')
            if predicate=='pregnancy': f['text']='Беременность установлена'
            elif predicate=='child_count': f['text']='Количество детей: '+claim['value']
            elif predicate=='child_sex': f['text']='Пол ребёнка: '+{'female':'женский','male':'мужской'}.get(claim['value'],claim['value'])
    from backend.runtime_v3.remote import projection as phone_projection
    result['phone'] = phone_projection(dict(snapshot,world_state=state))
    result['runtime_version']=3
    result['last_time_skip']=deepcopy(snapshot.get('last_time_skip'))
    from backend.runtime_v3.notifications import notifications
    result['notifications']=notifications(state, history)
    return result
