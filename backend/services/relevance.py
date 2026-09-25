"""Deterministic relevance ranking for the current camera; no model calls."""
import re
from character_links import character_aliases
from backend.services.timeline import current_time

POLICY = {
    'controlled': 120, 'present': 110, 'mentioned': 105,
    'known': 95, 'suspected': 80, 'relationship': 55,
    'thread': 50, 'motivation': 36, 'scheduled': 40,
    'event': 24, 'fact': 20,
}


def rank(state, user_text, kind='turn'):
    world=state['world']; now=current_time(state)
    actor=state.get('controlled_actor_id')
    present=set(state.get('scene_meta',{}).get('present_ids',[]))
    mentioned={cid for alias,cid in character_aliases(state['characters']).items()
               if re.search(r'(?<!\w)'+re.escape(alias)+r'(?!\w)',user_text,re.I)}
    scores={cid:0 for cid in world['characters']}
    for cid in present:scores[cid]=max(scores.get(cid,0),POLICY['present'])
    for cid in mentioned:scores[cid]=max(scores.get(cid,0),POLICY['mentioned'])
    if actor:scores[actor]=max(scores.get(actor,0),POLICY['controlled'])
    if kind=='start':
        for cid in scores:scores[cid]=max(scores[cid],POLICY['thread'])
    for r in world['relationships'].values():
        if r['source_id'] in present|mentioned or r['target_id'] in present|mentioned:
            for cid in (r['source_id'],r['target_id']):scores[cid]=max(scores.get(cid,0),POLICY['relationship'])
    for cid,point in world['characters'].items():
        if any(any(name.casefold() in str(item).casefold() for name in (c['name'] for c in state['characters'] if c['id'] in present|mentioned))
               for item in point.get('intentions',[])+point.get('obligations',[])):
            scores[cid]=max(scores.get(cid,0),POLICY['motivation'])
    threads={}
    for tid,t in world['threads'].items():
        if t['status']=='resolved':continue
        links=set(t.get('character_ids',[]))
        score=(POLICY['thread'] if links & (present|mentioned|({actor} if actor else set())) else 0)
        score+=int(20*t.get('relevance',0))
        if t['status']=='dormant':score//=2
        if score>=35:
            threads[tid]=score
            for cid in links:scores[cid]=max(scores.get(cid,0),score)
    scheduled={}
    for eid,e in world['scheduled_events'].items():
        if e['status']!='pending':continue
        proximity=max(0,24-abs(e['due_minute']-now)//10)
        score=proximity+(POLICY['scheduled'] if set(e['participants']) & (present|mentioned) else 0)
        if score>=25:
            scheduled[eid]=score
            for cid in e['participants']:scores[cid]=max(scores.get(cid,0),score)
    knowledge={}
    for k in world['knowledge'].values():
        if k['actor_id']==actor and k['status']!='unknown':
            knowledge[k['fact_id']]=POLICY['known'] if k['status']=='known' else POLICY['suspected']
    facts={fid:max(knowledge.get(fid,0),POLICY['fact']+max((scores.get(cid,0)//4 for cid in f.get('character_ids',[])),default=0))
           for fid,f in world['facts'].items()}
    events={eid:POLICY['event']+max((scores.get(cid,0)//3 for cid in e['participants']),default=0)
            +max(0,15-(now-(e.get('minute') or 0))//60)
            for eid,e in world['events'].items()}
    relations={rid:max(scores.get(r['source_id'],0),scores.get(r['target_id'],0))
               + (30 if r['source_id'] in present and r['target_id'] in present else 0)
               for rid,r in world['relationships'].items()}
    return dict(characters=scores,threads=threads,scheduled_events=scheduled,knowledge=knowledge,
                facts=facts,events=events,relationships=relations,present=present,mentioned=mentioned)


def ordered(values,scores):
    return sorted(values,key=lambda key:(-scores.get(key,0),str(key)))
