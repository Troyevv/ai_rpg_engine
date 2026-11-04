"""Canonical plot-secret classification and actor-owned disclosure projection.

Privacy is independent. Semantic links are accepted during existing Extraction;
reading only consumes those links, never interprets content or calls a provider.
"""
from copy import deepcopy
from pydantic import ValidationError
from backend.runtime_v3.models import identity, fatal
from backend.runtime_v3.remote_models import SecretDisclosure


def legacy_secret_metadata(fact, actors):
    explicit = fact.get('story_secret')
    owner = fact.get('owner_id')
    classified = explicit if explicit is not None else bool(fact.get('secret') and owner in actors)
    subjects = fact.get('secret_subject_ids', [owner] if classified and owner in actors else [])
    return dict(story_secret=classified, secret_subject_ids=subjects,
                secret_existence=fact.get('secret_existence', 'hidden'))


def validate_disclosures(state):
    for fact in state['facts'].values():
        origin=fact.get('origin_remote_event_id')
        if origin is not None and origin not in state['remote_events']:
            fatal('Invalid remote fact origin', section='facts', entity=fact['id'])
    for event in state['remote_events'].values():
        links = event.get('secret_disclosures', [])
        if links and event['channel'] == 'VOICE_CALL':
            fatal('Disclosure requires a written source', section='remote_events', entity=event['id'])
        seen=set()
        for link in links:
            fid=link['fact_id']
            if fid in seen or not state['facts'].get(fid,{}).get('story_secret'):
                fatal('Invalid disclosure fact reference', section='remote_events', entity=event['id'])
            seen.add(fid)


def acquire_disclosures(state, event, actor, batch):
    if actor not in event['read_by'] or actor not in event['delivered_to']:
        return
    from backend.runtime_v3.knowledge import apply_knowledge
    # Adapt runtime-proven perception into the SAME belief transition machinery,
    # including claim conflicts, revisions, retired beliefs and History.
    class Perception:
        observed=True
        mode='turn'
        protected_knowledge_actor_ids=set()
        def __init__(self):
            self.state=state
            self.history=batch
            self.turn_id=state['meta']['turn_id']
        def records(self, raw, section):
            return enumerate(raw)
        def typed(self, model, value, *args):
            return model.model_validate(value).model_dump()
        def warn(self, *args, **kwargs):
            # A later read must not revive retired beliefs or overwrite a newer
            # interpretation. Existing Knowledge remains authoritative.
            return None
    for link in event.get('secret_disclosures', []):
        fid=link['fact_id']; prior=state['knowledge'].get(actor+':'+fid)
        status='known' if link['assertion']=='confirmed' else 'suspected'
        if prior and (prior['status'] in ('known','outdated','refuted','superseded') or prior['source_event_id']==identity('secret_read',event['id'],actor,fid)):
            continue
        eid=identity('secret_read',event['id'],actor,fid)
        source=dict(id=eid,local_id=eid,remote_interaction_id=event['id'],text=event['content'],
            participants=sorted({event['sender_id'],actor}),witnesses=[actor],fact_ids=[fid],
            medium='message',author_id=event['sender_id'],evidence=link['evidence'],
            turn_id=state['meta']['turn_id'],minute=state['meta']['world_time'],
            player_observed=actor==state['camera']['controlled_actor_id'])
        before=len(batch.knowledge_acquisitions)
        apply_knowledge(Perception(), [dict(actor_id=actor,fact_id=fid,status=status,
            source_event_id=eid,evidence=link['evidence'])], {eid:source})
        if len(batch.knowledge_acquisitions)>before: batch.events.append(source)


def apply_disclosures(resolver, raw):
    s=resolver.state
    for i,item in resolver.records(raw,'secret_disclosures'):
        try:
            link=SecretDisclosure.model_validate({k:v for k,v in item.items() if k!='source_event_id'}).model_dump()
            eid=getattr(resolver,'disclosure_source_ids',{}).get(item.get('source_event_id'),item.get('source_event_id'))
            event=s['remote_events'].get(eid)
            # Existing canonical source or source staged by this accepted turn;
            # neither arbitrary extracted Event nor a fabricated read is sufficient.
            allowed = eid in resolver.remote_semantic_sources or eid in getattr(resolver,'disclosure_source_ids',{}).values() or any(
                e.get('remote_interaction_id')==eid for e in resolver.history.events)
            if not event or event['channel']=='VOICE_CALL' or not allowed:
                raise ValueError('Missing accepted written source')
            if not s['facts'].get(link['fact_id'],{}).get('story_secret'):
                raise ValueError('Not a classified story secret')
            links=event.setdefault('secret_disclosures',[])
            prior=next((l for l in links if l['fact_id']==link['fact_id']),None)
            if prior and prior!=link:
                raise ValueError('Immutable source interpretation conflict')
            if not prior: links.append(link)
            if link['fact_id'] not in resolver.before['facts']:
                s['facts'][link['fact_id']]['origin_remote_event_id']=eid
            for actor in event['read_by']:
                acquire_disclosures(s,event,actor,resolver.history)
        except (ValidationError,ValueError,TypeError):
            # Validation input may itself contain a private message or secret.
            resolver.warn('secret_disclosures',i,'Недопустимая связь тайны с принятым письменным источником.',code='secret_disclosure_invalid')


def projection(state, *, excluded=()):
    """Only this projection authorizes slots; unknown rows contain no fact IDs."""
    from backend.runtime_v3.reproduction import private_fact_ids, known_birth
    actor=state['camera']['controlled_actor_id']
    if actor is None: return dict(personal={},world=[])
    from backend.runtime_v3.possessions import private_fact_ids as possession_facts
    protected=private_fact_ids(state) | possession_facts(state) | set(excluded)
    protected |= {c['fact_id'] for c in state.get('conditions',{}).values() if c.get('fact_id')}
    protected |= {identity('communicated_text',e['id']) for e in state['remote_events'].values()}
    result=dict(personal={},world=[])
    for fid,fact in state['facts'].items():
        if not fact.get('story_secret'): continue
        subjects=fact['secret_subject_ids']
        if any(not known_birth(state,cid,actor) for cid in subjects+fact['character_ids']): continue
        belief=state['knowledge'].get(actor+':'+fid,{})
        known=belief.get('status')=='known'
        if not known and (fact.get('origin_remote_event_id') or fid in protected or fact['secret_existence']!='discoverable'): continue
        # Scoped opaque identity has no canonical fact/subject encoded in it.
        row=dict(id=identity('secret_slot',state['meta'].get('seed',''),actor,fid),status='known' if known else 'hidden')
        if known:
            row.update(fact_id=fid,text=fact['text'])
            # Evidence is the observer's accepted acquisition, never GM history.
            if belief.get('evidence'): row['source']=belief['evidence']
        if subjects:
            for cid in subjects: result['personal'].setdefault(cid,[]).append(deepcopy(row))
        else: result['world'].append(row)
    return result


def first_confirmations(before, after, history):
    """#168 commit consumer: canonical branch-owned acquisitions, no load events."""
    actor=after['camera']['controlled_actor_id']
    if not actor or before['camera']['controlled_actor_id']!=actor: return []
    result=[];seen=set()
    events={e.get('id'):e for e in history.get('events',[])}
    for row in history.get('knowledge_acquisitions',[]):
        fid=row.get('fact_id')
        if (row.get('actor_id')!=actor or row.get('status')!='known' or not row.get('source_event_id')
                or row.get('migrated') or fid in seen or not after['facts'].get(fid,{}).get('story_secret')
                or before['knowledge'].get(actor+':'+fid,{}).get('status')=='known'
                or before['knowledge'].get(actor+':'+fid,{}).get('confirmed_once')
                or after['knowledge'].get(actor+':'+fid,{}).get('status')!='known'):
            continue
        source=events.get(row['source_event_id'],{})
        if actor not in source.get('witnesses',[]) or fid not in source.get('fact_ids',[]): continue
        seen.add(fid)
        result.append(dict(id=identity('secret_confirmation',actor,fid,row['source_event_id']),fact_id=fid,
            kind='new' if fid not in before['facts'] else 'revealed',source_event_id=row['source_event_id']))
    return result


def visible_fact_ids(state):
    actor=state['camera']['controlled_actor_id']
    from backend.runtime_v3.reproduction import private_fact_ids, known_birth
    from backend.runtime_v3.possessions import private_fact_ids as possession_facts
    protected=private_fact_ids(state) | possession_facts(state)
    protected|={c['fact_id'] for c in state.get('conditions',{}).values() if c.get('fact_id')}
    communications={identity('communicated_text',e['id']):e for e in state['remote_events'].values()}
    allowed=set()
    for fid,f in state['facts'].items():
        if any(not known_birth(state,cid,actor) for cid in f['character_ids']+f['secret_subject_ids']): continue
        status=state['knowledge'].get(str(actor)+':'+fid,{}).get('status')
        if fid in communications:
            e=communications[fid]
            if actor!=e['sender_id'] and actor not in e['read_by']: continue
        if fid in protected and status!='known': continue
        if f.get('origin_remote_event_id') and status not in ('known','suspected','outdated','refuted','superseded'): continue
        if f['visibility']=='public' or actor and status in ('known','suspected','outdated','refuted','superseded'):
            allowed.add(fid)
    return allowed


def secure_game_view(result, state):
    """Close legacy aliases as well as the main fact/Knowledge dictionaries."""
    actor=state['camera']['controlled_actor_id']; world=result['world']
    allowed=visible_fact_ids(state)
    world['facts']={k:v for k,v in world['facts'].items() if k in allowed}
    world['knowledge']={k:v for k,v in world['knowledge'].items() if v['actor_id']==actor and v['fact_id'] in allowed}
    for row in world['knowledge'].values():
        if row.get('replaced_by') not in allowed: row['replaced_by']=None
    result['facts']=[dict(f,known_by=[actor] if state['knowledge'].get(str(actor)+':'+f['id'],{}).get('status')=='known' else []) for f in result['facts'] if f['id'] in allowed]
    for f in [*world['facts'].values(),*result['facts']]:
        f.pop('origin_remote_event_id',None)
    result['story_secrets']=projection(state)
    known_ids={row['fact_id'] for rows in [result['story_secrets']['world'], *result['story_secrets']['personal'].values()] for row in rows if row['status']=='known'}
    result['story_secrets']['revealed']=[dict(deepcopy(f),character_ids=f['secret_subject_ids']) for fid,f in world['facts'].items() if fid in known_ids]
    # Unknown source events must not disclose a fact through searchable History.
    world['events']={k:v for k,v in world['events'].items() if actor in v.get('witnesses',[]) and set(v.get('fact_ids',[]))<=allowed}
    result['events']=[v for v in result['events'] if v['id'] in world['events']]
    world['scene_records']={k:v for k,v in world['scene_records'].items() if actor and v.get('pov_actor_id')==actor}
    # Unstructured author notes have no verifiable Knowledge provenance. They
    # remain in the canonical snapshot/author endpoint, never behind CSS masks.
    result.get('sections',{}).pop('knowledge',None)
    for key in ('story_notes','world_summary','summary','campaign'):
        result.pop(key,None)
    for card in result['characters']:
        for key in ('Тайны','Тайна','Секреты','Секрет','Знания'):
            card.get('fields',{}).pop(key,None)
