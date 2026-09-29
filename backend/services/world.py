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
    return sorted(rows,key=lambda e:(e['minute'] if e['minute'] is not None else e.get('recorded_minute',-1),e.get('order') or 0,e['id']))
