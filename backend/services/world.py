"""Versioned world aggregate. Pure functions; no database, HTTP or model calls."""
from copy import deepcopy
from hashlib import sha256
from backend.services.scene import scene_metadata
from backend.services.timeline import current_time, label

KINDS = ('characters','facts','knowledge','relationships','threads','scenes','events','scheduled_events','scene_records')
CARD_FIELDS = ('Возраст','Роль','Статус','Внешность','Характер','Стиль общения','Привычки',
               'Сильные стороны','Слабости','Страхи и уязвимости','Биография')


def normalize_card_fields(fields):
    """Project legacy character cards onto the current static profile, without inventing details."""
    fields = dict(fields)
    legacy = fields.pop('Суть', '')
    if legacy:
        if not fields.get('Характер'):
            fields['Характер'] = legacy
        elif legacy not in fields['Характер']:
            fields['Характер'] += '\n\n' + legacy
    return {**{key:fields.get(key,'') for key in CARD_FIELDS},
            **{key:value for key,value in fields.items() if key not in CARD_FIELDS}}


def identity(kind, *parts):
    return kind + '_' + sha256('\0'.join(map(str, parts)).encode()).hexdigest()[:20]


def normalize(original):
    state = deepcopy(original)
    if not isinstance(state.get('characters'),list):
        return state  # Incomplete ancient saves remain readable, never destroyed.
    for card in state['characters']:
        if isinstance(card.get('fields'),dict):
            card['fields']=normalize_card_fields(card['fields'])
    if state.get('world', {}).get('version') == 2:
        state['world'].setdefault('scene_records',{})
        for character in state['world']['characters'].values():
            character.setdefault('goals', [character['short_goal']] if character.get('short_goal') else [])
        return state
    from backend.services.pov import protagonist, controlled
    main, actor = protagonist(state), controlled(state)
    now, meta = current_time(state), scene_metadata(state)
    world = {'version': 2, **{k: {} for k in KINDS}}
    state.update(world=world, protagonist_id=main, controlled_actor_id=actor)
    names = {c['name']: c['id'] for c in state['characters']}
    for c in state['characters']:
        world['characters'][c['id']] = dict(id=c['id'], location=None, situation=c['fields'].get('Сейчас',''),
            short_goal=c['fields'].get('Чего хочет',''), goals=[c['fields']['Чего хочет']] if c['fields'].get('Чего хочет') else [], intentions=[], emotion='', obligations=[],
            last_event_id=None, minute=None, scene_id=None)
    points = {'initial': {'text':state['scene'], 'meta':meta}, **state.get('actor_scenes',{})}
    for key, point in points.items():
        m = point.get('meta',{})
        participants = [x for x in m.get('present_ids',[]) if x in world['characters']]
        sid = identity('scene', m.get('location'), sorted(participants))
        from backend.services.timeline import parse_time
        minute = parse_time(m.get('time',''), now)
        world['scenes'][sid] = dict(id=sid, participants=participants, location=m.get('location','Не указано'),
            start_minute=minute, end_minute=minute, text=point.get('text',''), status='active', event_ids=[])
        for cid in participants:
            world['characters'][cid].update(location=m.get('location'), minute=minute, scene_id=sid)
        if key == 'initial':
            state['camera'] = {'scene_id':sid, 'mode':'actor' if actor else 'observer'}
    for i, f in enumerate(state.get('facts',[])):
        fid = identity('legacy_fact', i, f['text'])
        world['facts'][fid] = dict(id=fid, text=f['text'], secret=False, character_ids=f.get('known_by',[]), evidence=[])
        for cid in f.get('known_by',[]):
            if cid in world['characters']:
                world['knowledge'][cid+':'+fid] = dict(actor_id=cid, fact_id=fid, status='known', source_event_id=None, legacy=True)
    for i, r in enumerate(state.get('relationships',[])):
        target = r.get('target_id') or names.get(r.get('target_name'))
        if target:
            rid = r['source_id']+':'+target
            world['relationships'][rid] = dict(source_id=r['source_id'], target_id=target, context=r['text'], dimensions={})
    for p in state.get('plans',[]):
        tid = p.get('id') or identity('thread',p['text'])
        world['threads'][tid] = dict(id=tid, description=p['text'], character_ids=p.get('character_ids',[]),
            status='active' if p.get('status')=='open' else 'resolved', state=p['text'], relevance=0.5, last_event_id=None)
    for i, e in enumerate(state.get('events',[])):
        eid = identity('legacy_event',i,e['text'])
        world['events'][eid] = dict(id=eid, text=e['text'], participants=e.get('character_ids',[]), witnesses=[],
            minute=None, scene_id=None, fact_ids=[], medium='legacy', evidence='', player_observed=True,
            source_sequence=e.get('turn'), legacy=True)
    from backend.services.initial_world import seed
    seed(world,state,now)
    return state


def record_scene(state, changes, sequence, kind):
    """Update only observed participants; keep off-camera points and other scenes."""
    world = state['world']
    meta = state['scene_meta']
    participants = meta['present_ids']
    prior = world['scenes'].get(state.get('camera',{}).get('scene_id'))
    same = prior and prior['location']==meta['location'] and set(prior['participants'])==set(participants)
    sid = prior['id'] if same else identity('scene',sequence,meta['location'],sorted(participants))
    now = current_time(state)
    scene = world['scenes'].setdefault(sid,dict(id=sid, start_minute=now, event_ids=[]))
    scene.update(participants=participants,location=meta['location'],end_minute=now,text=state['scene'],status='active')
    state['camera'] = {'scene_id':sid,'mode':'observer' if kind=='background' else 'actor','scope':state.get('camera',{}).get('scope','world')}
    if kind=='background':
        state['controlled_actor_id'] = None
    for cid in participants:
        c = world['characters'][cid]
        c.update(location=meta['location'],scene_id=sid,minute=now)
        # Remove a moved participant from its old live scene, retaining its history.
        for other in world['scenes'].values():
            if other['id']!=sid and cid in other['participants']:
                other['participants'].remove(cid)
                if not other['participants']:other['status']='ended'
    return sid


def apply_legacy(state, changes, sequence, kind):
    """Compatibility adapter: old extraction fields enter the same world aggregate."""
    state = normalize(state)
    world = state['world']
    sid = record_scene(state,changes,sequence,kind)
    scene = world['scenes'][sid]
    def event(text, witnesses, evidence, medium='observation'):
        eid = identity('event',sequence,sid,text)
        world['events'][eid] = dict(id=eid, text=text, participants=list(witnesses), witnesses=list(witnesses),
            minute=current_time(state), scene_id=sid, fact_ids=[], medium=medium, evidence=evidence,
            player_observed=True, source_sequence=sequence)
        if eid not in scene['event_ids']:scene['event_ids'].append(eid)
        for cid in witnesses:world['characters'][cid]['last_event_id']=eid
        return eid
    for e in changes.get('events',[]):
        event(e['text'],e['character_ids'],e['evidence'])
    for f in changes.get('facts',[]):
        fid = identity('fact',sequence,sid,f['text'])
        eid = event(f['text'],f['known_by'],f['evidence'])
        world['facts'][fid] = dict(id=fid,text=f['text'],character_ids=f['known_by'],secret=False,evidence=[f['evidence']])
        world['events'][eid]['fact_ids'].append(fid)
        for cid in f['known_by']:
            world['knowledge'][cid+':'+fid] = dict(actor_id=cid,fact_id=fid,status='known',source_event_id=eid)
    for c in changes.get('characters',[]):
        target = world['characters'][c['id']]
        if 'now' in c:target['situation']=c['now']
        if 'goal' in c:
            target['short_goal']=c['goal']
            target['goals']=[c['goal']] if c['goal'] else []
    for r in changes.get('relationships',[]):
        key = r['source_id']+':'+r['target_id']
        relation = world['relationships'].setdefault(key,dict(source_id=r['source_id'],target_id=r['target_id'],dimensions={}))
        relation['context']=r['text']
        relation['dimensions'][r['aspect']]={'direction':r['direction'],'reason':r['reason']}
    for p in changes.get('plans',[]):
        old = world['threads'].get(p['id'],{})
        world['threads'][p['id']] = dict(id=p['id'],description=p['text'],character_ids=p['character_ids'],
            status='active' if p['status']=='open' else 'resolved',state=p['text'],relevance=old.get('relevance',0.5),last_event_id=old.get('last_event_id'))
    return state


def knowledge_for(world, actor):
    result = []
    for k in world['knowledge'].values():
        if k['actor_id']==actor and k['status']!='unknown' and k['fact_id'] in world['facts']:
            result.append({'fact_id':k['fact_id'],'text':world['facts'][k['fact_id']]['text'],'status':k['status']})
    return sorted(result,key=lambda x:x['fact_id'])


def timeline(state, visibility='player'):
    state=normalize(state)
    actor=state['controlled_actor_id']
    events=state['world']['events'].values()
    known_events={k.get('source_event_id') for k in state['world']['knowledge'].values() if k['actor_id']==actor and k['status']=='known'}
    rows=[e for e in events if e.get('player_observed')] if visibility=='player' else [e for e in events if actor in e['witnesses'] or e['id'] in known_events]
    return sorted(rows,key=lambda e:(e['minute'] if e['minute'] is not None else -1,e['id']))


def record_narrative(state, narrative, sequence, observed=True, previous_events=()):
    """Immutable scene recording, including off-camera scenes not in chat prose."""
    world=state['world']
    scene=world['scenes'][state['camera']['scene_id']]
    rid=identity('record',sequence,scene['id'],narrative)
    world.setdefault('scene_records',{})[rid]=dict(id=rid,scene_id=scene['id'],source_sequence=sequence,
        minute=current_time(state),scene_meta=deepcopy(state['scene_meta']),narrative=narrative,
        participants=list(scene['participants']),player_observed=observed,pov_actor_id=state.get('controlled_actor_id'))
    for eid,event in world['events'].items():
        if eid not in previous_events and event['source_sequence']==sequence and event['scene_id']==scene['id']:
            event['source_record_id']=rid
    scene['last_record_id']=rid
    return rid


def compatibility_view(state):
    """Refresh old read models from canonical entities; no second mutable world."""
    world=state['world']
    names={c['id']:c['name'] for c in state['characters']}
    for key,r in world['relationships'].items():
        existing=next((p for p in state['relationships'] if p['source_id']==r['source_id'] and (p.get('target_id')==r['target_id'] or p.get('target_name')==names[r['target_id']])),None)
        if existing is None:
            existing={'source_id':r['source_id'],'target_id':r['target_id'],'target_name':names[r['target_id']]}
            state['relationships'].append(existing)
        existing['text']=r['context']
    state['facts']=[{'id':f['id'],'text':f['text'],'known_by':[k['actor_id'] for k in world['knowledge'].values() if k['fact_id']==f['id'] and k['status']=='known']} for f in world['facts'].values()]
    state['plans']=[{'id':t['id'],'text':t['state'] or t['description'],'character_ids':t['character_ids'],
                     'status':'done' if t['status']=='resolved' else 'open'} for t in world['threads'].values()]
    # Compatibility inspector is player-facing; don't expose unobserved simulation events here.
    state['events']=[{'id':e['id'],'text':e['text'],'character_ids':e['participants'],'turn':e['source_sequence']} for e in world['events'].values() if e['player_observed']]
    for c in state['characters']:
        if world['characters'][c['id']]['situation']:
            c['fields']['Сейчас']=world['characters'][c['id']]['situation']
    return state
