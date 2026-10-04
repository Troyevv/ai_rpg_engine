"""Deterministic director based on present locations, obligations and due items."""

def plan(state, kind, history=None):
    now=state['meta']['world_time'];present=set(state['camera']['present_character_ids'])
    due=[e for e in state['scheduled_events'].values() if e['status']=='pending' and e['due_minute'] is not None and e['due_minute']<=now]
    threads=sorted((t for t in state['threads'].values() if t['status']!='resolved'),key=lambda t:(-t['relevance'],t['id']))
    recent=[e.get('id') for e in (history or {}).get('events',[]) if isinstance(e,dict) and isinstance(e.get('participants'),list) and any(isinstance(cid,str) and cid in present for cid in e['participants'])][-12:]
    return dict(recent_event_ids=recent,triggers=(['camera_transition'] if kind in ('pov','background') else [])+(['scheduled_event_due'] if due else []),
        thread_ids=[t['id'] for t in threads[:6]],due_event_ids=[e['id'] for e in due[:10]],
        instruction='Не двигай все линии сразу. Намерение и просроченный срок — не свершившийся факт.')


def background_candidate(before, after):
    now=after['meta']['world_time'];elapsed=now-before['meta']['world_time']
    if elapsed<=0:return None
    camera=after['camera'];present=set(camera['present_character_ids']);controlled=camera['controlled_actor_id']
    def eligible(cid):
        point=after['characters'][cid]
        return cid not in present and cid!=controlled and (camera['location_id'] is None or point['location_id']!=camera['location_id'])
    for event in sorted(after['scheduled_events'].values(),key=lambda e:(e['due_minute'] or 0,e['id'])):
        if event['status']!='pending' or event['due_minute'] is None or event['due_minute']>now:continue
        if event.get('last_attempt_minute') is not None and now-event['last_attempt_minute']<30:continue
        for cid in event['character_ids']:
            if eligible(cid):return dict(actor_id=cid,reason='scheduled_event_due',scheduled_id=event['id'])
    if elapsed>=45:
        for thread in sorted(after['threads'].values(),key=lambda t:(-t['relevance'],t['id'])):
            if thread['status'] not in ('active','developing') or thread['relevance']<0.6:continue
            for cid in thread['character_ids']:
                if eligible(cid):return dict(actor_id=cid,reason='relevant_off_camera_thread',scheduled_id=None)
    if elapsed>=60:
        for cid,point in sorted(after['characters'].items()):
            if eligible(cid) and any(isinstance(r,str) or r.get('status')=='active' for field in ('intentions','obligations') for r in point[field]):
                return dict(actor_id=cid,reason='established_intention_and_time_gap',scheduled_id=None)
    return None


def interval_candidates(before, after, budget=6):
    """Rank causes once for an interval, group by actor, never tick every NPC."""
    now=after['meta']['world_time']; start=before['meta']['world_time']
    protected=set(after['camera']['present_character_ids'])
    controlled=after['camera']['controlled_actor_id']
    def eligible(cid):
        return cid in after['characters'] and cid not in protected and cid!=controlled and after['characters'][cid]['location_id']!=after['camera']['location_id']
    candidates=[]
    for e in after['scheduled_events'].values():
        if e['status']=='pending' and e['due_minute'] is not None and e['due_minute']<=now and (e.get('last_attempt_minute') is None or e['last_attempt_minute']<start):
            ids=[cid for cid in e['character_ids'] if eligible(cid)]
            if ids:candidates.append(dict(actor_id=ids[0],actor_ids=ids,reason=e['description'],scheduled_id=e['id'],score=100))
    for cid,c in after['characters'].items():
        if not eligible(cid):continue
        for field in ('obligations','intentions'):
            for r in c[field]:
                if not isinstance(r,dict) or r['status']!='active':continue
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
