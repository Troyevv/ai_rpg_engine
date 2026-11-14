"""Deterministic director based on present locations, obligations and due items."""
from backend.runtime_v3.life import capabilities
from backend.runtime_v3.lifecycle import actionable
from backend.runtime_v3.commitments import pregnancy_boundaries
from backend.runtime_v3.continuity import due_births_in_scene_clock
from backend.runtime_v3.calendar import scheduled_boundary as scheduled_due


def plan(state, kind, history=None, scope=None):
    # All context consumers share the same resolver. Compatibility for direct callers.
    if scope is None:
        from backend.runtime_v3.scope import RelevanceResolver
        scope = RelevanceResolver().resolve(dict(world_state=state, character_cards=[]), '', world_history=history)
    now = state['meta']['world_time']
    due = [eid for eid in scope.scheduled_event_ids if eid in scope.acting_scheduled_event_ids
           and scheduled_due(state, state['scheduled_events'][eid]) is not None
           and scheduled_due(state, state['scheduled_events'][eid]) <= now]
    continuity = scope.continuity_decision
    scene_direction = {}
    if kind != 'background':
        from backend.runtime_v3.kinship import knowledge_status
        observer = scope.pov_actor_id or scope.controlled_actor_id
        def visible_boundary(eid):
            pregnancy = state.get('pregnancies', {}).get(eid)
            return not pregnancy or knowledge_status(state, observer, pregnancy['fact_id']) == 'known'
        if continuity and continuity.get('compression'):
            compression = continuity['compression']
            continuity = dict(continuity, compression=dict(compression, boundary_ids=[
                eid for eid in compression['boundary_ids'] if visible_boundary(eid)]))
        due = [eid for eid in due if visible_boundary(eid)]
        if continuity.get('compression', {}).get('max_minutes') == 0 and (processes := due_births_in_scene_clock(state)):
            instruction = ('Отыграй последнее действие игрока в эту же минуту, включая помощь, '
                           'наблюдение или невмешательство. Предположение игрока само по себе не факт. '
                           'Оставь следующий выбор игроку и не переключай сюжет.')
            visible = scope.present_actor_ids | scope.observed_actor_ids
            subjects = []
            if observer in scope.present_actor_ids and capabilities(state, observer)['can_perceive']:
                subjects = [p['gestational_actor_id'] for p in processes if p['gestational_actor_id'] in visible]
            immediate = dict(observable_actor_ids=subjects)
            if subjects:
                instruction += (' Покажи ощутимое или видимое развитие: потугу, новое движение '
                                'или само рождение, если оно происходит в сцене. Для этого не нужно '
                                'решение игрока. Не утверждай скрытые подробности.')
                # These are witnessed events in the same instant, not proof of delivery.
                previous = [e['id'] for e in scope.history_events if e.get('player_observed')
                            and type(e.get('turn_id')) is int and 0 <= state['meta']['turn_id'] - e['turn_id'] < 3
                            and e.get('minute', e.get('recorded_minute')) == now
                            and observer in e.get('witnesses', [])
                            and set(subjects).intersection(e.get('participants', []))]
                if previous:
                    immediate['previous_observation_ids'] = previous[-3:]
                    instruction += (' Продолжи с последнего наблюдения из истории. Покажи, что '
                                    'изменилось с тех пор, вместо повторения тех же признаков. '
                                    'Исход может оставаться открытым.')
            scene_direction['immediate_scene'] = dict(immediate, instruction=instruction)
    from backend.runtime_v3.pacing import evaluate, prompt_policy
    scope.pacing_decision = scope.pacing_decision or evaluate(state, scope)
    from backend.runtime_v3.initiative import scene_plan
    if scope.initiative_decision is None: scope.initiative_decision = scene_plan(state, scope)
    return dict(**scene_direction, continuity=continuity, scene_agency=scope.initiative_decision, narrative_policy=prompt_policy(scope.pacing_decision),recent_event_ids=scope.event_ids, actors=sorted(scope.relevant_actor_ids),
        location_ids=scope.location_ids,
        acting_actor_ids=sorted(cid for cid in scope.present_actor_ids | scope.observed_actor_ids | scope.remote_actor_ids | scope.active_actor_ids if capabilities(state,cid)['can_act']),
        referenced_actor_ids=sorted(scope.referenced_actor_ids),
        triggers=(['camera_transition'] if kind in ('pov','background') else []) + (['scheduled_event_due'] if due else []),
        thread_ids=scope.thread_ids, due_event_ids=due,
        instruction='Не двигай все линии сразу. Намерение и просроченный срок — не свершившийся факт.')


def background_candidate(before, after, considerations=None):
    """One fair, bounded opportunity; attempts are receipts, never outcomes.

    The snapshot cursor belongs to the active History branch. World time, not
    wall time or the length of a single turn, drives eligibility after reload.
    """
    now = after['meta']['world_time']
    elapsed = now - before['meta']['world_time']
    if elapsed < 0:
        return None
    cursor = considerations or {}
    origin = cursor.get('since_minute', before['meta']['world_time'])
    attempts = cursor.get('attempts', {})
    camera = after['camera']
    controlled = camera['controlled_actor_id']
    present = set(camera['present_character_ids']) | set(camera.get('observed_character_ids', []))
    last_dispatch = cursor.get('last_dispatch_minute')
    candidates = []

    def add(key, actor, reason, cooldown, priority, scheduled_id=None, due=False):
        last = attempts.get(key)
        # Due births retain their existing per-turn development, including a frozen
        # clock. They are not ordinary thread polling; never repeat one turn.
        due_birth_turn = (key.startswith('pregnancy:')
                        and after['meta']['turn_id'] > before['meta']['turn_id']
                        and cursor.get('last_dispatch_turn') != after['meta']['turn_id'])
        if last is not None and not due_birth_turn and now - last < cooldown:
            return
        if not due and now - (last if last is not None else origin) < cooldown:
            return
        candidates.append(dict(candidate_id=key, actor_id=actor, reason=reason,
                               scheduled_id=scheduled_id, last_considered=last,
                               priority=priority, due_birth_turn=due_birth_turn))

    def eligible(cid, *, active=True):
        point = after['characters'][cid]
        return ((not active or capabilities(after, cid)['can_act']) and cid not in present and cid != controlled
                and (camera['location_id'] is None or point['location_id'] != camera['location_id'])
                and not (controlled and point['location_id'] is not None
                         and point['location_id'] == after['characters'][controlled]['location_id']))

    for boundary in pregnancy_boundaries(after):
        mother = after['pregnancies'][boundary['id']]['gestational_actor_id']
        if boundary['due_minute'] <= now and eligible(mother, active=False):
            add('pregnancy:' + boundary['id'], mother,
                'Покажи происходящее с этим персонажем: потуги и их наблюдаемое развитие. '
                'Роды могут завершиться в сцене или остаться незавершёнными. Не раскрывай скрытые подробности',
                15, 0, due=True)
    # Zero-time input only develops due births at a frozen scene clock; it
    # never ticks ordinary intentions or repeats the same canonical turn.
    if elapsed > 0:
        for event in after['scheduled_events'].values():
            due = scheduled_due(after, event)
            if event['status'] != 'pending' or due is None or due > now:
                continue
            if event.get('last_attempt_minute') is not None and now - event['last_attempt_minute'] < 30:
                continue
            actor = next((cid for cid in event['character_ids'] if eligible(cid)), None)
            if actor:
                add('scheduled:' + event['id'], actor, 'scheduled_event_due', 30, 1, event['id'], due=True)
        for thread in after['threads'].values():
            if thread['status'] not in ('active', 'developing') or thread['relevance'] < 0.6:
                continue
            actor = next((cid for cid in thread['character_ids'] if eligible(cid)), None)
            if actor:
                add('thread:' + thread['id'], actor, 'relevant_off_camera_thread', 45, 2)
        for cid, point in after['characters'].items():
            if eligible(cid) and any(actionable(r) for f in ('intentions', 'obligations') for r in point[f]):
                add('motivation:' + cid, cid, 'established_intention_and_time_gap', 60, 3)
    if last_dispatch is not None and now - last_dispatch < 15:
        candidates = [c for c in candidates if c['due_birth_turn']]
    # Unconsidered causes go first; an unsuccessful high-priority cause cannot
    # monopolize the slot. Only one group is dispatched, never a per-NPC loop.
    return min(candidates, key=lambda c: (c['last_considered'] is not None,
               c['last_considered'] if c['last_considered'] is not None else origin,
               c['priority'], c['candidate_id']), default=None)


def interval_candidates(before, after, budget=6):
    """Rank causes once for an interval, group by actor, never tick every NPC."""
    now=after['meta']['world_time']; start=before['meta']['world_time']
    protected=set(after['camera']['present_character_ids']) | set(after['camera'].get('observed_character_ids',[]))
    controlled=after['camera']['controlled_actor_id']
    def eligible(cid):
        return cid in after['characters'] and capabilities(after,cid)['can_act'] and cid not in protected and cid!=controlled and after['characters'][cid]['location_id']!=after['camera']['location_id']
    candidates=[]
    for e in after['scheduled_events'].values():
        if e['status']=='pending' and scheduled_due(after,e) is not None and scheduled_due(after,e)<=now and (e.get('last_attempt_minute') is None or e['last_attempt_minute']<start):
            ids=[cid for cid in e['character_ids'] if eligible(cid)]
            if ids:candidates.append(dict(actor_id=ids[0],actor_ids=ids,reason=e['description'],scheduled_id=e['id'],score=100))
    for cid,c in after['characters'].items():
        if not eligible(cid):continue
        for field in ('obligations','intentions'):
            for r in c[field]:
                if not isinstance(r,dict) or not actionable(r):continue
                if r.get('due_minute') is not None and r['due_minute']>now:continue
                candidates.append(dict(actor_id=cid,actor_ids=[cid],reason=r['text'],scheduled_id=None,score=80 if field=='obligations' else 40))
    for t in after['threads'].values():
        if t['status'] not in ('active','developing') or t['relevance']<0.6:continue
        ids=[cid for cid in t['character_ids'] if eligible(cid)]
        if ids:candidates.append(dict(actor_id=ids[0],actor_ids=ids,reason=t['description'],scheduled_id=None,score=60*t['relevance']))
    ranked=sorted(candidates,key=lambda c:(-c['score'],c['actor_id'],c['reason']))
    groups={}
    for c in ranked:
        key=tuple(sorted(c['actor_ids']))
        if key not in groups:groups[key]=dict(c,reasons=[],scheduled_ids=[])
        groups[key]['reasons'].append(c['reason'])
        if c['scheduled_id']:groups[key]['scheduled_ids'].append(c['scheduled_id'])
    selected=list(groups.values())[:budget]
    for group in selected:
        group['reasons']=group['reasons'][:3]
    return selected,dict(background_candidates=len(candidates),simulated_candidates=len(selected),
                         merged_candidates=len(candidates)-len(groups),skipped_candidates=max(0,len(groups)-budget))
