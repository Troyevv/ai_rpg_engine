"""Convert historical test fixtures into the current extraction wire format."""
from copy import deepcopy


def canonical(payload, sequence=0):
    p=deepcopy(payload)
    if 'world_delta' in p:
        delta=p.pop('world_delta')
    else:delta={}
    facts=p.pop('facts',[])
    events=p.pop('events',[])
    relations=p.pop('relationships',[])
    characters=p.pop('characters',[])
    plans=p.pop('plans',[])
    p.pop('locations',None)
    if facts:
        delta.setdefault('facts',[]).extend({'id':f'test_fact_{sequence}_{i}','text':f['text'], 'secret':False,'character_ids':f['known_by'],'evidence':f['evidence']} for i,f in enumerate(facts))
    if events:
        delta.setdefault('events',[]).extend({'id':f'test_event_{sequence}_{i}','text':e['text'],'participants':e['character_ids'], 'witnesses':e['character_ids'], 'fact_ids':[f'test_fact_{sequence}_{j}' for j,f in enumerate(facts) if set(f['known_by'])<=set(e['character_ids'])], 'medium':'conversation','evidence':e['evidence']} for i,e in enumerate(events))
    if facts and events:
        delta.setdefault('knowledge',[]).extend({'actor_id':cid,'fact_id':f'test_fact_{sequence}_{i}','status':'known','source_event_id':f'test_event_{sequence}_0','evidence':f['evidence']} for i,f in enumerate(facts) for cid in f['known_by'])
    for r in relations:
        delta.setdefault('relationships',[]).append({'source_id':r['source_id'],'target_id':r['target_id'],'context':r['text'],'dimensions':{'trust':1 if r['direction']=='up' else -1},'evidence':r['evidence']})
    for c in characters:
        delta.setdefault('characters',[]).append({'id':c['id'],'evidence':c['evidence'],**({'situation':c['now']} if 'now' in c else {}),**({'goals':[c['goal']]} if 'goal' in c else {})})
    for t in plans:
        if events:
            delta.setdefault('threads',[]).append({'id':t['id'],'description':t['text'],'character_ids':t['character_ids'],'status':'active' if t['status']=='open' else 'resolved','state':t['text'],'relevance':0.5,'last_event_id':f'test_event_{sequence}_0','evidence':t['evidence']})
    p['world_delta']=delta
    return p


def fixture_sequence(storage,job_id):
    job=storage.get_job(job_id)
    turns=storage.list_turns(job['save_id'])
    if job['replaces_id']:
        return next(t['sequence'] for t in turns if t['id']==job['replaces_id'])
    return len(turns)
