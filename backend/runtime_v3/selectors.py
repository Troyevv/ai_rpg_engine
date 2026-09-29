"""Disposable read projections. None of these scene IDs may enter WorldStateV3."""
from copy import deepcopy
from backend.runtime_v3.models import identity
from backend.services.timeline import label


def ui_view(snapshot, history=None):
    state=deepcopy(snapshot['world_state']);history=history or {}
    camera=state['camera'];now=state['meta']['world_time']
    cards=deepcopy(snapshot['character_cards'])
    names={c['id']:c['name'] for c in cards}
    locations=state['locations']
    def place(lid):return locations.get(lid,{}).get('name','Не указано') if isinstance(lid,str) else 'Не указано'
    scenes={}
    groups={}
    for cid,c in state['characters'].items():
        if c['location_id'] is not None:groups.setdefault(c['location_id'],[]).append(cid)
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
        if not isinstance(change,dict) or change.get('turn_id')!=state['meta']['turn_id']:continue
        key=change.get('entity')
        if not isinstance(key,str) or key not in world['relationships']:continue
        prior=change.get('before') or {};after=change.get('after') or {}
        if not isinstance(prior,dict) or not isinstance(after,dict):continue
        previous=prior.get('dimensions',{});current=after.get('dimensions',{})
        if not isinstance(previous,dict) or not isinstance(current,dict):continue
        differences=[v-previous.get(d,0) for d,v in current.items() if type(v) in (int,float) and type(previous.get(d,0)) in (int,float)]
        if differences and any(differences):
            value=max(differences,key=abs)
            world['relationships'][key]['change']=dict(direction='up' if value>0 else 'down',reason=after.get('context',''))
    for cid,c in state['characters'].items():
        world['characters'][cid]=dict(c,location=place(c['location_id']) if c['location_id'] else None,
            scene_id=sid if cid in camera['present_character_ids'] else 'view:'+c['location_id'] if c['location_id'] else None,
            minute=now,last_event_id=None,short_goal='\n'.join(c['goals']))
    for fid,f in state['facts'].items():world['facts'][fid]=dict(f,secret=f['visibility']=='secret',evidence=[])
    for eid,e in state['scheduled_events'].items():world['scheduled_events'][eid]=dict(e,participants=e['character_ids'])
    for e in history.get('events',[]):
        if not isinstance(e,dict) or not isinstance(e.get('id'),str) or not isinstance(e.get('text'),str):continue
        if any(not isinstance(e.get(k,[]),list) or any(not isinstance(v,str) for v in e.get(k,[])) for k in ('participants','witnesses')):continue
        world['events'][e['id']]=dict(e,participants=e.get('participants',[]),witnesses=e.get('witnesses',[]),
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
        card['fields'].update({'Сейчас':c['situation'],'Чего хочет':'\n'.join(c['goals']),'Намерения':'\n'.join(c['intentions'])})
    metadata=dict(time=label(now),location=place(camera['location_id']),present_ids=list(camera['present_character_ids']))
    campaign=deepcopy(snapshot.get('campaign',{}))
    result=dict(campaign,characters=cards,world=world,controlled_actor_id=camera['controlled_actor_id'],
        protagonist_id=campaign.get('protagonist_id') or next((c['id'] for c in cards if c.get('is_player')),None),
        camera=dict(scene_id=sid,mode=camera['mode'],scope='scene'),scene=camera['situation'],scene_meta=metadata,
        world_clock=dict(minute=now,last_event_time=label(now)),memory=deepcopy(snapshot.get('memory',{})),
        sections=dict(campaign.get('sections',{}),scene=camera['situation']),
        relationships=[dict(r,text=r['context'],target_name=names[r['target_id']]) for r in world['relationships'].values()],
        facts=[dict(f,known_by=[k['actor_id'] for k in state['knowledge'].values() if k['fact_id']==f['id'] and k['status']=='known']) for f in state['facts'].values()],
        plans=[dict(t,text=t['state'] or t['description'],status='done' if t['status']=='resolved' else 'open') for t in state['threads'].values()],
        events=[dict(e,text=e['text'],character_ids=e['participants'],turn=e['source_sequence']) for e in world['events'].values() if e['player_observed']],
        locations=[dict(l,text=l['description'] or l['name']) for l in locations.values()])
    result['runtime_version']=3
    return result
