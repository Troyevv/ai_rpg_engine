"""Cheap trigger-based policy. Produces guidance, never prose or forced events."""
from backend.services.world import normalize, identity
from backend.services.timeline import current_time, label


class Director:
    def plan(self, state, kind):
        world=state['world']; now=current_time(state)
        scene=world['scenes'].get(state.get('camera',{}).get('scene_id'),{})
        present=set(scene.get('participants',[]))
        actor=state.get('controlled_actor_id')
        point=world['characters'].get(actor,{})
        gap=max(0,now-point['minute']) if point.get('minute') is not None else 0
        if actor is None:
            points=[world['characters'][cid].get('minute') for cid in present]
            gap=max([now-minute for minute in points if minute is not None]+[0])
        scene_age=max(0,now-scene['start_minute']) if scene.get('start_minute') is not None else 0
        due=[e for e in world['scheduled_events'].values() if e['status']=='pending' and e['due_minute']<=now and present.intersection(e['participants'])]
        threads=[t for t in world['threads'].values() if t['status']!='resolved' and present.intersection(t['character_ids'])]
        threads.sort(key=lambda t:(t['status']=='dormant',-t['relevance'],t['id']))
        reasons=[]
        if kind in ('background','pov'):reasons.append('camera_transition')
        if gap>=30:reasons.append('unobserved_time_gap')
        if due:reasons.append('scheduled_event_due')
        if len(scene.get('event_ids',[]))>=12 and scene_age>=60:reasons.append('consider_quiet_scene_end')
        return dict(triggers=reasons,elapsed_unobserved_minutes=gap,thread_ids=[t['id'] for t in threads[:6]],
                    due_event_ids=[e['id'] for e in sorted(due,key=lambda e:(e['due_minute'],e['id']))[:10]],
                    instruction='Не двигай все линии сразу. Спокойное продолжение и завершение сцены допустимы. Просроченное намерение — не свершившийся факт.')


def observe(original, actor_id=None, scene_id=None, allow_protagonist=False):
    state=normalize(original)
    world=state['world']; main=state['protagonist_id']; now=current_time(state)
    if actor_id is not None:
        if actor_id not in world['characters'] or (actor_id==main and not allow_protagonist):
            raise ValueError('Для камеры мира выбери NPC.')
        scene_id=world['characters'][actor_id].get('scene_id')
    scene=world['scenes'].get(scene_id)
    if scene and main in scene['participants'] and not allow_protagonist:
        raise ValueError('Основной ГГ присутствует в этой сцене. Можно взять управление участником.')
    if scene_id and not scene:raise ValueError('Сцена камеры не найдена.')
    if scene is None and actor_id is None:
        current=world['scenes'].get(state.get('camera',{}).get('scene_id'))
        if state.get('controlled_actor_id') is None and current and main not in current['participants']:
            scene=current
        else:
            candidates=[s for s in world['scenes'].values() if s['status']=='active' and s['participants'] and main not in s['participants']]
            def relevance(s):
                ids=set(s['participants'])
                due=sum(e['status']=='pending' and e['due_minute']<=now and bool(ids.intersection(e['participants'])) for e in world['scheduled_events'].values())
                return (-due, s.get('end_minute') or 0,s['id'])
            scene=next(iter(sorted(candidates,key=relevance)),None)
            if scene is None:
                off=[c for c in world['characters'].values() if c['id']!=main and not c.get('scene_id')]
                if not off:raise ValueError('Нет отдельной сцены без основного ГГ. Сначала разделите персонажей в ходе игры.')
                actor_id=off[0]['id']
    if scene is None:
        c=world['characters'][actor_id]
        sid=identity('scene','unobserved',actor_id)
        scene=dict(id=sid,participants=[actor_id],location=c.get('location') or 'Не указано',start_minute=now,end_minute=now,
                   text=c.get('situation') or 'Последняя ситуация пока неизвестна.',status='active',event_ids=[])
        world['scenes'][sid]=scene
    state['camera']={'scene_id':scene['id'],'mode':'observer','scope':'scene' if allow_protagonist else 'world'}
    state['controlled_actor_id']=None
    state['scene']=scene['text']
    state['sections']['scene']=scene['text']
    state['scene_meta']={'time':label(now),'location':scene['location'],'present_ids':list(scene['participants'])}
    return state


def background_candidate(before, after):
    """At most one relevant off-camera scene per committed turn, never per NPC."""
    now=current_time(after)
    if now<=current_time(before):return None
    world=after['world']
    present=set(after['scene_meta']['present_ids'])
    controlled=after.get('controlled_actor_id')
    for event in sorted(world['scheduled_events'].values(),key=lambda e:(e['due_minute'],e['id'])):
        if event['status']!='pending' or event['due_minute']>now:continue
        if event.get('last_attempt_minute') is not None and now-event['last_attempt_minute']<30:continue
        for actor in event['participants']:
            point=world['characters'][actor]
            scene=world['scenes'].get(point.get('scene_id'))
            if actor not in present and actor!=controlled and (not scene or controlled not in scene['participants']):
                return {'actor_id':actor,'reason':'scheduled_event_due','scheduled_id':event['id']}
    # Time alone is not a reason to invent an event: an established intention or obligation is required.
    if now-current_time(before)<60:return None
    for actor, point in sorted(world['characters'].items()):
        scene=world['scenes'].get(point.get('scene_id'))
        if actor not in present and actor!=controlled and (point['intentions'] or point['obligations']) and (not scene or controlled not in scene['participants']):
            if point.get('minute') is None or now-point['minute']>=60:
                return {'actor_id':actor,'reason':'established_intention_and_time_gap','scheduled_id':None}
    return None
