"""Validate canonical endpoints after all source-backed mutations on a copy."""
from backend.services.timeline import current_time
from .references import require


def validate_final_state(before, state, plan):
    world=state['world'];actors=set(world['characters']);events=set(world['events']);facts=set(world['facts']);scenes=world['scenes']
    now=current_time(state)
    require(now>=current_time(before),'часы мира движутся назад','invalid_time')
    camera=scenes.get(state.get('camera',{}).get('scene_id'))
    require(camera is not None and not camera.get('historical'),'некорректная конечная камера','scene_invalid')
    require(set(camera['participants'])<=actors,'неизвестный участник камеры','unknown_character')
    for cid in camera['participants']:
        c=world['characters'][cid]
        require(c['location']==camera['location'] and c['scene_id']==camera['id'],'конечная сцена противоречит персонажу','character_location_inconsistent',entity=cid)
    for cid,c in world['characters'].items():
        if cid in plan['involved']:require(c.get('location')==plan['positions'][cid],'изменение места без Movement','character_location_inconsistent',entity=cid)
        sid=c.get('scene_id')
        if sid:
            require(sid in scenes,'неизвестная сцена персонажа')
            scene=scenes[sid]
            require(not scene.get('historical') and cid in scene['participants'] and c.get('location')==scene['location'],'scene_id/location персонажа не согласованы','character_location_inconsistent',entity=cid)
        require(not c.get('last_event_id') or c['last_event_id'] in events,'неизвестное последнее событие персонажа')
        require(c.get('minute') is None or c['minute']<=now,'персонаж находится в будущем','invalid_time')
    for s in scenes.values():
        require(set(s['participants'])|set(s.get('witnesses',[]))<=actors,'неизвестный участник сцены')
        require(set(s.get('event_ids',[]))<=events,'неизвестное событие сцены')
        if not s.get('historical'):
            require(s['start_minute']<=s['end_minute']<=now,'интервал сцены противоречит часам','invalid_time')
    for e in world['events'].values():
        require(set(e['participants'])|set(e.get('witnesses',[]))<=actors,'неизвестный участник события')
        require(set(e.get('fact_ids',[]))<=facts,'неизвестный факт события')
        require(not e.get('scene_id') or e['scene_id'] in scenes,'неизвестная сцена события')
    for k in world['knowledge'].values():
        require(k['actor_id'] in actors and k['fact_id'] in facts,'неизвестная ссылка Knowledge')
        require(not k.get('source_event_id') or k['source_event_id'] in events,'неизвестный источник Knowledge')
    for r in world['relationships'].values():require({r['source_id'],r['target_id']}<=actors,'неизвестный персонаж отношения')
    for f in world['facts'].values():require(set(f.get('character_ids',[]))<=actors,'неизвестный персонаж факта')
    for t in world['threads'].values():
        require(set(t.get('character_ids',[]))<=actors,'неизвестный персонаж линии')
        require(not t.get('last_event_id') or t['last_event_id'] in events,'неизвестное событие линии')
    for s in world['scheduled_events'].values():
        require(set(s['participants'])<=actors,'неизвестный участник обязательства')
        require(not s.get('resolved_event_id') or s['resolved_event_id'] in events,'неизвестное событие обязательства')
