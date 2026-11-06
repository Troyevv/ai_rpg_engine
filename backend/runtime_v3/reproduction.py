"""#41: accepted service events, deterministic outcomes, ordinary Characters.

This module extends StateResolver. It owns no persistence, knowledge store, clock,
random generator, genealogy or separate child model. Numbers are game policy.
"""
from copy import deepcopy
from hashlib import sha256
import json
from typing import Literal
from pydantic import Field
from backend.runtime_v3.models import (StrictModel, ReproductiveEvent, Pregnancy,
    NamingDecision, Character, Fact, ObjectiveRelation, PersonalityProfile,
    PersonalityItem, identity)
from backend.runtime_v3.calendar import current_time, age_on, profile_of
from backend.runtime_v3.life import capabilities, _proof, _transition, validate_life_state


class ServiceClaim(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    kind: Literal['sexual_intercourse', 'encounter_ended']
    source_event_id: str
    gestational_actor_id: str
    impregnating_actor_id: str
    protection: Literal['protected', 'unprotected', 'unknown'] = 'unknown'
    consent_actor_ids: list[str] = Field(max_length=2)
    parent_ids: list[str] = Field(default_factory=list, max_length=8)
    assertion: Literal['completed_consensual_adult_event']
    evidence: str = ""
    player_evidence: str = ''
    player_assertion: Literal['explicit_choice'] | None = None


class BirthClaim(StrictModel):
    pregnancy_id: str
    source_event_id: str
    assertion: Literal['birth_completed']
    location_id: str | None = None
    disclosed_parent_ids: list[str] = Field(default_factory=list, max_length=8)
    # Explicit prose facts live on the existing card, not a child Appearance model.
    appearance: dict[str, str] = Field(default_factory=dict)
    evidence: str = ""


class NameClaim(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    pregnancy_id: str
    child_id: str
    components: dict[str, str] = Field(default_factory=dict)
    display_name: str | None = None
    status: Literal['proposed', 'agreed', 'cancelled']
    decision_actor_ids: list[str] = Field(min_length=1, max_length=8)
    delegated_to: str | None = None
    replaces: str | None = None
    source_event_id: str
    evidence: str = ""
    player_evidence: str = ''
    player_assertion: Literal['explicit_choice'] | None = None


def unit(seed, purpose):
    return (int.from_bytes(sha256((seed+'\0'+purpose).encode()).digest()[:8], 'big') >> 11) / 2**53


def source(resolver, claim, events):
    from backend.runtime_v3.resolver import normalized
    event = events.get(claim['source_event_id'])
    if not event or not resolver.supported(claim):
        raise ValueError('current completed narrative event required')
    return event


def fact(s, fid, actors, predicate, value, text):
    s['facts'][fid] = Fact(id=fid, text=text, visibility='secret', character_ids=actors,
        claim=dict(subject_id=actors[0], predicate=predicate, value=str(value), scope=fid)).model_dump()
    return fid


def accepted_rows(resolver, raw, section, model, events, apply):
    for i, row in enumerate(raw.records.get(section, [])[:24]):
        before = deepcopy(resolver.state)
        history_before = deepcopy(vars(resolver.history))
        cards = len(resolver.cards)
        try:
            claim = model.model_validate(row).model_dump()
            event = source(resolver, claim, events)
            apply(resolver, claim, event)
            validate_life_state(resolver.state)
        except (ValueError, TypeError, KeyError) as exc:
            resolver.state.clear(); resolver.state.update(before)
            for k,previous in history_before.items(): getattr(resolver.history,k)[:]=previous
            del resolver.cards[cards:]
            resolver.warn(section,i,str(exc),code='reproduction_claim_invalid')


def intercourse(r, c, event):
    s=r.state; a=c['gestational_actor_id']; b=c['impregnating_actor_id']; pair=[a,b]
    if a == b or any(cid not in s['characters'] for cid in pair): raise ValueError('invalid participants')
    if not set(pair) <= set(event['participants']): raise ValueError('event participants do not match')
    eid=c['id'] if c['id'] in s['reproductive_events'] else identity('intercourse',a,b,c['id'])
    old=s['reproductive_events'].get(eid)
    if old:
        if old['participants'] != pair or old['protection'] != c['protection']:
            raise ValueError('canonical encounter identity conflict')
        if c['kind']=='encounter_ended' and not old['closed']:
            old['closed']=True
        return
    if c['kind']=='encounter_ended': raise ValueError('unknown encounter')
    # One continuous encounter is one attempt, even if Extraction changes a label.
    if any(not x['closed'] and set(x['participants'])==set(pair) for x in s['reproductive_events'].values()):
        raise ValueError('continuous encounter already processed; close it before a new encounter')
    policy=s['reproduction_policy']
    for cid in pair:
        actor=s['characters'][cid]
        age=age_on(actor.get('birth_date'),current_time(s)['date'],profile_of(s))
        if (actor['life_status']!='alive' or not capabilities(s,cid)['adult_eligible'] or
                age is not None and age < policy['adult_age']): raise ValueError('adult eligibility not established')
    if set(c['consent_actor_ids']) != set(pair): raise ValueError('consent required from each participant')
    if r.protected_actor_id in pair and (r.mode=='background' or not _proof(r,c)):
        raise ValueError('EXTERNAL consent requires explicit current player choice')
    if s['characters'][a]['reproductive_capability']!='can_become_pregnant' or s['characters'][b]['reproductive_capability']!='can_impregnate':
        raise ValueError('reproductive capability impossible or unknown')
    if any(p['gestational_actor_id']==a and p['status']!='born' for p in s['pregnancies'].values()):
        raise ValueError('active pregnancy already exists')
    if set(c['parent_ids'])-set(event['participants']): raise ValueError('unknown established parent')
    # Stable identity is not tied to model prose or an untracked random process.
    conceived=unit(eid,'conception') < policy[c['protection']]
    pid=identity('pregnancy',eid) if conceived else None
    lo=r.before['meta']['world_time']; hi=s['meta']['world_time']; exact=event.get('minute')
    if exact is not None and not lo<=exact<=hi: raise ValueError('event minute outside accepted interval')
    rec=ReproductiveEvent(id=eid,participants=pair,gestational_actor_id=a,impregnating_actor_id=b,
        protection=c['protection'],source_event_id=event['id'],evidence=c['evidence'],turn_id=r.turn_id,
        earliest_minute=lo,latest_minute=hi,exact_minute=exact,conceived=conceived,pregnancy_id=pid,policy=policy).model_dump()
    s['reproductive_events'][eid]=rec
    if not conceived: return
    weights=policy['child_weights']; roll=unit(eid,'count')*sum(weights); count=len(weights)
    for i,w in enumerate(weights):
        roll-=w
        if roll<0: count=i+1;break
    children=[dict(id=identity('character',pid,i),sex='female' if unit(eid,'sex:'+str(i))<.5 else 'male') for i in range(count)]
    pf=identity('fact',pid,'exists'); cf=identity('fact',pid,'count')
    sexfacts={ch['id']:identity('fact',pid,ch['id'],'sex') for ch in children}
    from backend.runtime_v3.models import ScheduledEvent
    due=(exact if exact is not None else hi)+policy['gestation_days']*1440
    s['scheduled_events'][pid]=ScheduledEvent(id=pid,description='pregnancy_due',
        character_ids=[a],due_minute=due,type='pregnancy_due').model_dump()
    s['pregnancies'][pid]=Pregnancy(id=pid,event_id=eid,gestational_actor_id=a,
        parent_ids=list(dict.fromkeys(c['parent_ids'])),earliest_minute=lo,latest_minute=hi,
        conception_minute=exact,due_minute=(exact if exact is not None else hi)+policy['gestation_days']*1440,
        children=children,fact_id=pf,count_fact_id=cf,sex_fact_ids=sexfacts).model_dump()
    # Objective assertions only. No Knowledge acquisition is inferred here.
    fact(s,pf,[a],'pregnancy',pid,'pregnancy:'+pid)
    fact(s,cf,[a],'child_count',count,'child_count:'+str(count))
    for ch in children: fact(s,sexfacts[ch['id']],[a],'child_sex',ch['sex'],'child_sex:'+ch['sex'])


def naming(r,c,event):
    s=r.state; p=s['pregnancies'].get(c['pregnancy_id'])
    if not p or c['child_id'] not in {x['id'] for x in p['children']}: raise ValueError('ambiguous or unknown child target')
    decision=set(c['decision_actor_ids'])
    if not decision <= set(p['parent_ids']): raise ValueError('unestablished decision maker')
    if c['status']=='agreed' and decision != set(p['parent_ids']): raise ValueError('all established decision makers must agree or delegate')
    external=r.protected_actor_id in decision
    prior=[n for n in s['naming_decisions'].values() if n['pregnancy_id']==p['id'] and n['child_id']==c['child_id']]
    if c['delegated_to'] is not None and (c['delegated_to'] not in decision or c['delegated_to']==r.protected_actor_id):
        raise ValueError('delegate must be an autonomous decision maker')
    delegated=any(n['delegated_to'] in decision and n['delegated_to'] is not None
        and r.protected_actor_id in n['decision_actor_ids']
        and n['status'] in ('proposed','agreed') for n in prior)
    participating=decision-{r.protected_actor_id} if delegated else decision
    if not participating <= set(event['participants']): raise ValueError('decision makers absent from event')
    if external and (c['status']!='proposed' or c['delegated_to']) and not delegated:
        if r.mode=='background' or not _proof(r,c): raise ValueError('EXTERNAL agreement/delegation requires player choice')
    if c['status']!='cancelled' and ((not c['components'] and not (c['delegated_to'] and c['status']=='proposed')) or len(c['components'])>8 or any(not k.strip() or not v.strip() or len(v)>200 for k,v in c['components'].items())):
        raise ValueError('explicit identity components required')
    nid=c['id'] if c['id'] in s['naming_decisions'] else identity('name',c['id']); existing=s['naming_decisions'].get(nid)
    if existing:
        if any(existing[k]!=c[k] for k in ('pregnancy_id','child_id','components','status','display_name','delegated_to')):
            raise ValueError('name decision identity conflict; use replaces')
        return
    replaced=s['naming_decisions'].get(c['replaces']) if c['replaces'] else None
    if c['replaces'] and (not replaced or replaced not in prior or replaced['status'] not in ('proposed','agreed')):
        raise ValueError('replacement target invalid')
    if c['status']=='cancelled' and not replaced: raise ValueError('cancellation needs target')
    if c['status']=='agreed' and any(n['status']=='agreed' and n is not replaced for n in prior):
        raise ValueError('existing agreed decision must be explicitly replaced')
    fid=identity('fact',nid)
    rec=NamingDecision(**{k:c[k] for k in NamingDecision.model_fields if k in c} | dict(id=nid,source_event_id=event['id'],fact_id=fid,established=c['status']=='agreed')).model_dump()
    old_replaced=deepcopy(replaced)
    if replaced: replaced['status']='cancelled' if c['status']=='cancelled' else 'replaced'
    s['naming_decisions'][nid]=rec
    fact(s,fid,p['parent_ids']+([c['child_id']] if c['child_id'] in s['characters'] else []),'naming',nid,c['evidence'])
    _transition(r,'naming',nid,None,dict(rec,character_ids=p['parent_ids']),c)
    if replaced: _transition(r,'naming',replaced['id'],old_replaced,dict(replaced,character_ids=p['parent_ids']),c)
    reveal(r,event,[fid])
    if p['status']=='born' and c['status']=='agreed': apply_identity(r,p,c['child_id'],rec)


def reveal(r,event,fids):
    """Reuse #76, including witness/capability/background restrictions."""
    from backend.runtime_v3.knowledge import apply_knowledge
    from backend.runtime_v3.raw import RawTurnResult
    e=deepcopy(event); e['medium']='observation'; e['fact_ids']=list(set(e['fact_ids'])|set(fids))
    raw=RawTurnResult.parse(dict(final_scene={},knowledge_gained=[dict(actor_id=cid,fact_id=fid,
        source_event_id=e['local_id'],evidence=e['evidence']) for cid in e['witnesses'] for fid in fids]))
    apply_knowledge(r,raw,{e['local_id']:e})
    for row in r.history.events:
        if row['id']==e['id']: row['fact_ids']=e['fact_ids']


def apply_identity(r,p,cid,decision):
    actor=r.state['characters'][cid]
    actor['identity_components'].update(decision['components'])
    display=decision['display_name'] or decision['components'].get('given_name')
    if display:
        previous=actor.get('display_name')
        if previous and previous!=display:
            actor['name_history'].append(dict(previous=previous,current=display,minute=r.state['meta']['world_time'],
                date=current_time(r.state)['date'],turn_id=r.turn_id,evidence=decision['evidence'],fact_id=decision['fact_id'] if cid in r.state['facts'][decision['fact_id']]['character_ids'] else None))
        actor['display_name']=display


def birth(r,c,event):
    s=r.state;p=s['pregnancies'].get(c['pregnancy_id'])
    if not p: raise ValueError('unknown pregnancy')
    if p['status']=='born': return
    mother=p['gestational_actor_id']
    if mother not in event['participants']: raise ValueError('birth event must establish gestational participant')
    if s['characters'][mother]['life_status']!='alive': raise ValueError('birth outcome needs a living gestational participant')
    now=event.get('minute',s['meta']['world_time'])
    if not r.before['meta']['world_time']<=now<=s['meta']['world_time']: raise ValueError('birth minute outside accepted interval')
    if now<p['due_minute']: raise ValueError('pregnancy is not due under configured game policy')
    if c['location_id'] is not None and c['location_id'] not in s['locations']: raise ValueError('unknown birth location')
    if any(not r.supported({'evidence':v}) for v in c['appearance'].values()): raise ValueError('birth appearance must be explicitly quoted')
    if set(c['appearance'])-{x['id'] for x in p['children']}: raise ValueError('unknown appearance target')
    parents=p['parent_ids'];date=current_time(s,now)['date'];fids=[]
    if set(c['disclosed_parent_ids'])-set(parents): raise ValueError('unestablished disclosed parent')
    for ch in p['children']:
        cid=ch['id']
        if cid in s['characters']: raise ValueError('child identity collision')
        temper={key:('low','moderate','high')[min(2,int(unit(cid,key)*3))] for key in ('activity','adaptability','sensitivity','intensity','sociability')}
        item=PersonalityItem(field='temperament',text=json.dumps(temper,sort_keys=True),source_ids=[event['id']]).model_dump()
        actor=Character(id=cid,location_id=c['location_id'],birth_date=date,birth_date_provenance=dict(source='birth_event',event_id=event['id']),life_status='alive',
            biological_sex=ch['sex'],developmental_stage='infant',personality=PersonalityProfile(items={'early_temperament':item}),values={},
            birth_provenance=dict(pregnancy_id=p['id'],event_id=event['id'],minute=now)).model_dump()
        s['characters'][cid]=actor
        names=[s['characters'][par]['identity_components'].get('family_name') for par in parents]
        if names and all(names) and len(set(names))==1 and s['reproduction_policy']['shared_family_name']:
            actor['identity_components']['family_name']=names[0]
        for decision in s['naming_decisions'].values():
            if decision['child_id']==cid and decision['status']=='agreed': apply_identity(r,p,cid,decision)
        # Empty name is intentional presentation metadata; never a canonical name.
        fields={}
        if c['appearance'].get(cid): fields['Внешность']=c['appearance'][cid]
        from backend.runtime_v3.models import AppearanceProfile
        actor['appearance']=AppearanceProfile(legacy_text=fields.get('Внешность','')).model_dump()
        r.cards.append(dict(id=cid,name='',fields=fields,aliases=[],is_player=False))
        bf=identity('fact',cid,'birth');actor['life_fact_id']=bf
        fact(s,bf,[cid,mother],'birth',date or now,c['evidence']);fids.append(bf)
        for par in parents:
            rid=identity('parent',par,cid);fid=identity('fact',rid)
            fact(s,fid,[par,cid],'parent',cid,c['evidence'])
            if par==mother or par in c['disclosed_parent_ids']: fids.append(fid)
            relation=ObjectiveRelation(id=rid,kind='parent',source_id=par,target_id=cid,since=now,since_date=date,
                evidence=c['evidence'],source_turn=r.turn_id,fact_id=fid).model_dump()
            s['objective_relations'][rid]=relation
            _transition(r,'objective_relations',rid,None,relation,dict(c,source_process_id=p['id']))
        _transition(r,'birth',cid,None,dict(actor,character_ids=[cid,*parents],fact_id=bf),dict(c,source_process_id=p['id']))
        if c['location_id']==s['camera']['location_id'] and mother in s['camera']['present_character_ids']:
            s['camera']['present_character_ids'].append(cid)
    p.update(status='born',birth_event_id=event['id'],birth_minute=now)
    if p['id'] in s['scheduled_events']: s['scheduled_events'][p['id']]['status']='resolved'
    # A witnessed birth reveals the outcome; unrelated characters receive nothing.
    # Witnessing delivery does not disclose an earlier naming conversation.
    # Names use their own accepted communication/observation Knowledge path.
    reveal(r,event,[p['fact_id'],p['count_fact_id'],*p['sex_fact_ids'].values(),*fids])


def advance_due(state):
    """Certain process transition shared by ordinary and long-term progression."""
    changed = []
    for process in state['pregnancies'].values():
        if process['status'] == 'active' and state['meta']['world_time'] >= process['due_minute']:
            process['status'] = 'due'
            changed.append(process)
    return changed


def apply_reproduction(r,raw,events):
    accepted_rows(r,raw,'reproductive_events',ServiceClaim,events,intercourse)
    advance_due(r.state)
    accepted_rows(r,raw,'naming_decisions',NameClaim,events,naming)
    accepted_rows(r,raw,'births',BirthClaim,events,birth)


def context_projection(state, relevant, observer, extraction=False):
    """Only Extraction receives undisclosed outcomes; Narrative gets owned facts."""
    def knows(fid): return state['knowledge'].get(str(observer)+':'+fid,{}).get('status')=='known'
    pregnancies=[]
    processes=sorted(state.get('pregnancies',{}).values(), key=lambda p:(p['status']=='born',-p['due_minute'],p['id']))
    for p in processes:
        if not set([p['gestational_actor_id'],*p['parent_ids'],*(ch['id'] for ch in p['children'])]) & relevant: continue
        if extraction: pregnancies.append(deepcopy(p));continue
        if not knows(p['fact_id']): continue
        row={k:p[k] for k in ('id','gestational_actor_id')}
        row['due']=p['status']!='born' and state['meta']['world_time']>=p['due_minute']
        if knows(p['count_fact_id']): row['child_count']=len(p['children'])
        slots=[dict(id=ch['id'],sex=ch['sex']) for ch in p['children'] if knows(p['sex_fact_ids'][ch['id']])]
        if slots: row['known_children']=slots
        pregnancies.append(row)
    pregnancies=pregnancies[:16]
    names=[deepcopy(n) for n in state.get('naming_decisions',{}).values()
        if n['pregnancy_id'] in {p['id'] for p in pregnancies} and (extraction or knows(n['fact_id']))]
    result={}
    if pregnancies: result['pregnancies']=pregnancies[:16]
    if names: result['naming_decisions']=names[-24:]
    if extraction:
        encounters=[e for e in state.get('reproductive_events',{}).values() if set(e['participants'])&relevant]
        if encounters: result['reproductive_events']=[{k:e[k] for k in ('id','participants','gestational_actor_id','impregnating_actor_id','protection','closed')} for e in encounters[-16:]]
    return result


def private_fact_ids(state):
    ids=set()
    for p in state.get('pregnancies',{}).values(): ids.update([p['fact_id'],p['count_fact_id'],*p['sex_fact_ids'].values()])
    born={c['id'] for p in state.get('pregnancies',{}).values() if p['status']=='born' for c in p['children']}
    ids.update(state['characters'][cid]['life_fact_id'] for cid in born)
    ids.update(r['fact_id'] for r in state['objective_relations'].values() if r['target_id'] in born)
    ids.update(n['fact_id'] for n in state.get('naming_decisions',{}).values())
    return ids


def appearance_adapter(snapshot, child_id):
    """Lossless #74 input boundary, not a speculative AppearanceProfile migration.

    Future #74 consumes this accepted source without modifying old snapshots.
    Unknown values stay absent. No phenotype generation or interpretation here.
    """
    actor=snapshot['world_state']['characters'][child_id]
    card=next((c for c in snapshot['character_cards'] if c['id']==child_id),{})
    from backend.runtime_v3.birth_identity import game_metadata,dob_metadata
    return deepcopy(dict(character_id=child_id,appearance_text=card.get('fields',{}).get('Внешность'),
        birth_provenance=game_metadata(actor),birth_date_provenance=dob_metadata(actor)))


def validate_reproduction(state):
    """Persisted cross-entity integrity; never erase a corrupt process and reroll."""
    actors=state['characters'];pregnancies=state['pregnancies'];events=state['reproductive_events']
    for cid,actor in actors.items():
        pid=actor.get('birth_provenance',{}).get('pregnancy_id')
        if pid is not None and (pid not in pregnancies or pregnancies[pid]['status']!='born' or cid not in {c['id'] for c in pregnancies[pid]['children']}):
            raise ValueError('birth provenance points to a missing or incompatible pregnancy/child')
    active=set();children=set()
    for eid,e in events.items():
        if eid!=e['id'] or set(e['participants'])!={e['gestational_actor_id'],e['impregnating_actor_id']} or len(e['participants'])!=2:
            raise ValueError('invalid reproductive event identity')
        if set(e['participants'])-actors.keys() or e['earliest_minute']>e['latest_minute']:
            raise ValueError('invalid reproductive participants/time')
        if e['conceived'] != (e['pregnancy_id'] is not None) or e['pregnancy_id'] is not None and e['pregnancy_id'] not in pregnancies:
            raise ValueError('orphan conception outcome')
    for pid,p in pregnancies.items():
        e=events.get(p['event_id'])
        if pid!=p['id'] or not e or e['pregnancy_id']!=pid or e['gestational_actor_id']!=p['gestational_actor_id']:
            raise ValueError('invalid pregnancy provenance')
        if set(p['parent_ids'])-actors.keys() or len(set(p['parent_ids']))!=len(p['parent_ids']): raise ValueError('invalid parents')
        if p['earliest_minute']>p['latest_minute'] or p['due_minute']<(p['conception_minute'] if p['conception_minute'] is not None else p['latest_minute']): raise ValueError('invalid pregnancy timing')
        if p['status']!='born':
            if p['gestational_actor_id'] in active: raise ValueError('duplicate active pregnancy')
            active.add(p['gestational_actor_id'])
        for child in p['children']:
            cid=child['id']
            if cid in children: raise ValueError('duplicate child slot')
            children.add(cid)
            if p['status']=='born':
                actor=actors.get(cid)
                if not actor or actor['biological_sex']!=child['sex'] or actor['birth_provenance'].get('pregnancy_id')!=pid:
                    raise ValueError('birth identity/outcome mismatch')
            elif cid in actors: raise ValueError('unborn child already exists')
        fids=[p['fact_id'],p['count_fact_id'],*p['sex_fact_ids'].values()]
        if set(p['sex_fact_ids'])!={c['id'] for c in p['children']} or set(fids)-state['facts'].keys():
            raise ValueError('missing pregnancy assertions')
    for nid,n in state['naming_decisions'].items():
        p=pregnancies.get(n['pregnancy_id'])
        if nid!=n['id'] or not p or n['child_id'] not in {c['id'] for c in p['children']} or n['fact_id'] not in state['facts']:
            raise ValueError('invalid naming target')
        if set(n['decision_actor_ids'])-set(p['parent_ids']): raise ValueError('invalid naming decision maker')
        if n['replaces'] is not None and n['replaces'] not in state['naming_decisions']: raise ValueError('orphan naming replacement')


def known_birth(state, cid, observer):
    from backend.runtime_v3.birth_identity import is_game_birth
    actor=state['characters'][cid]
    return (not is_game_birth(state,cid) or cid==observer or
        state['knowledge'].get(str(observer)+':'+str(actor.get('life_fact_id')),{}).get('status')=='known')


def birth_name(state,cid,observer):
    actor=state['characters'][cid]
    # Canonical unnamed is None. This is only an authorized read projection.
    name=None
    for decision in state['naming_decisions'].values():
        if decision['child_id']==cid and decision.get('established') and state['knowledge'].get(
                str(observer)+':'+decision['fact_id'],{}).get('status')=='known':
            name=decision['display_name'] or decision['components'].get('given_name') or name
    return name or ''
