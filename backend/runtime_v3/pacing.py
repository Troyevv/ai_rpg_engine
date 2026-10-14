"""Bounded deterministic policy inside the existing Director/Resolver pipeline.

Scores select opportunities to consider, not facts or mandatory plot beats.
There is no timer, randomness, per-NPC clock, or separate semantic request.
"""
from backend.runtime_v3.narrative_policy_models import (
    NarrativePacingProfile, NarrativeRiskProfile, NarrativeDevelopment, ConsequenceClaim,
    PacingRecord,
)


def profiles(state):
    meta = state['meta']
    return (NarrativePacingProfile.model_validate(meta.get('narrative_pacing', {})).model_dump(),
            NarrativeRiskProfile.model_validate(meta.get('narrative_risk', {})).model_dump())


class NarrativeDeathPolicy:
    """Implements #42 DeathPolicy; identity never grants additional immunity."""
    def permits_autonomous_death(self, state, actor_id):
        _, risk = profiles(state)
        key = 'protagonist_death' if actor_id == state['meta'].get('current_protagonist_id') else 'npc_death'
        # Legacy worlds may not have a protagonist until read migration initializes it.
        if not state['meta'].get('current_protagonist_id') and actor_id == state['camera']['controlled_actor_id']:
            key = 'protagonist_death'
        return risk[key]


def development_sources(state, scope, read):
    """Newest visible canonical transitions; no archive-to-actor expansion."""
    if read is None: return []
    now = state['meta']['world_time']
    observer = scope.pov_actor_id or scope.controlled_actor_id
    actors = sorted(scope.present_actor_ids | scope.remote_actor_ids | scope.active_actor_ids)[:8]
    if not actors: return []
    rows = read(actor_ids=actors,start_minute=max(0,now-43200),end_minute=now,limit=24)
    result = []
    for row in rows:
        minute = row.get('minute')
        if type(minute) is not int or not 0 <= now-minute < 43200: continue
        # A source is not a new disclosure to the camera or any NPC.
        if observer and state['knowledge'].get(observer+':'+str(row.get('fact_id')),{}).get('status') != 'known':
            if row['category'] != 'protagonist_transition' or observer not in row['actor_ids']: continue
        result.append(dict(id=row['id'],category=row['category'],actor_ids=row['actor_ids'],
            minute=minute,summary=row['summary'][:240],fact_id=row.get('fact_id'),
            freshness=round(1-(now-minute)/43200,4)))
    return sorted(result,key=lambda row:(-row['minute'],row['id']))[:6]


def evaluate(state, scope):
    pacing, risk = profiles(state)
    now = state['meta']['world_time']
    recent = state['meta'].get('pacing_recent', [])
    sources = getattr(scope,'development_sources',[])
    # Accepted developments and transitions have pressure, even when the player
    # caused them. Repeated assessment of a candidate has no persistent effect.
    pressure_rows = [(r['minute'],r['weight']) for r in recent]
    pressure_rows += [(r['minute'],.5) for r in sources]
    horizon = max(60,pacing['quiet_minutes']*2)
    pressure = round(sum(w*max(0,1-(now-m)/horizon) for m,w in pressure_rows if 0<=now-m<horizon),4)
    quiet = any(0<=now-r['minute']<pacing['quiet_minutes'] for r in recent)
    baseline = (state['meta'].get('calendar') or {}).get('start_minute',0)
    last_development = max([baseline]+[m for m,_ in pressure_rows if m<=now])
    elapsed_signal = min(.4,max(0,now-last_development)/(30*1440)*.4)
    active = sum(t['status'] in ('active','developing') for t in state['threads'].values())
    candidates = []
    def add(family, collection, row, score, text, actors):
        if not actors: return
        cid = family+':'+collection+':'+row['id']
        reasons = []
        same = [r for r in recent if r['source_id']==cid and 0<=now-r['minute']<horizon]
        if same: reasons.append('recent_source')
        if family=='external_disruption' and any(r['family']==family and 0<=now-r['minute']<horizon for r in recent):
            reasons.append('repeated_disruption')
        if quiet: reasons.append('quiet_period')
        if pressure >= pacing['pressure_limit']: reasons.append('recent_pressure')
        if family != 'existing_thread' and active >= pacing['thread_cap']: reasons.append('thread_cap')
        if family=='external_disruption' and pacing['disruption']==0: reasons.append('disruption_disabled')
        score = round(min(1.,score+elapsed_signal),4)
        if score < pacing['relevance_floor']: reasons.append('low_relevance')
        candidates.append(dict(id=cid,family=family,source_kind=collection,source_id=row['id'],
            actor_ids=sorted(actors)[:8],basis_ids=[row.get('fact_id') or row['id']],relevance=score,context=text[:240],eligible=not reasons,
            reasons=reasons,selected=False))
    for tid in scope.thread_ids[:6]:
        t=state['threads'][tid]
        add('existing_thread','threads',t,.45+.35*t['relevance']+.2*pacing['intensity'],t['description'],t['character_ids'])
        add('external_disruption','threads',t,.25+.3*t['relevance']+.45*pacing['disruption'],t['state'],t['character_ids'])
    for collection, ids in (('roles',scope.role_ids[:4]),('residences',scope.residence_ids[:4])):
        for rid in ids:
            row=state[collection][rid]
            if row['status']!='active': continue
            actor=row['actor_id']
            if actor not in scope.present_actor_ids | scope.remote_actor_ids | scope.active_actor_ids: continue
            add('life_opportunity',collection,row,.4+.35*pacing['intensity'],row.get('context',''),[actor])
            add('external_disruption',collection,row,.25+.25*pacing['intensity']+.5*pacing['disruption'],row.get('context',''),[actor])
    for cid in sorted(scope.present_actor_ids | scope.remote_actor_ids | scope.active_actor_ids)[:8]:
        from backend.runtime_v3.lifecycle import actionable
        for goal in [g for g in state['characters'][cid]['goals'] if actionable(g)][:2]:
            add('life_opportunity','goals',goal,.5+.3*pacing['intensity'],goal['text'],[cid])
    for eid in scope.scheduled_event_ids[:4]:
        row=state['scheduled_events'][eid]
        if row['status']=='pending':
            add('life_opportunity','scheduled_events',row,.45+.3*pacing['intensity'],row['description'],row['character_ids'])
    for source in sources:
        add('life_opportunity','milestones',source,.55*source['freshness']+.3*pacing['intensity'],source['summary'],source['actor_ids'])
    candidates.sort(key=lambda row:(-row['relevance'],row['id']))
    # Bound projection and the number of semantic proposals independently.
    candidates=candidates[:24]
    selected=[]
    for row in candidates:
        if row['eligible'] and len(selected)<pacing['candidate_budget']:
            row['selected']=True;selected.append(row['id'])
        elif row['eligible']: row['reasons'].append('candidate_budget')
    main=state['meta'].get('current_protagonist_id')
    linked=[tid for tid in scope.thread_ids if main and main in (
        state['threads'][tid]['character_ids']+state['threads'][tid].get('stakes_for',[]))]
    return dict(profile=pacing,risk=risk,outcome=dict(preference=state['meta'].get('outcome_preference','natural'),
        protagonist_id=main,linked_thread_ids=linked,guarantee='available_path_not_forced_result'),
        pressure=pressure,elapsed_signal=round(elapsed_signal,4),quiet=quiet,active_threads=active,selected_ids=selected,candidates=candidates,
        budget=dict(candidates=pacing['candidate_budget'],extra_llm_calls=0,used_extra_llm_calls=0),
        ordinary_scene_valid=True)


def prompt_policy(decision):
    """Only selected proposals enter the scene prompt; full reasons stay telemetry."""
    return {k:decision[k] for k in ('profile','risk','outcome','quiet','pressure','active_threads','budget','ordinary_scene_valid')} | {
        'candidates':[{k:v for k,v in c.items() if k not in ('reasons','eligible','selected')}
                      for c in decision['candidates'] if c['selected']]}


def recorded_policy(messages, state):
    """Original permits survive regeneration; legacy context grants no new ones."""
    import json
    for message in messages:
        if message['content'].startswith('Director / GM-only\n'):
            wire=json.loads(message['content'].split('\n',1)[1]).get('narrative_policy')
            if wire:
                return dict(wire,candidates=[dict(c,selected=True) for c in wire['candidates']])
    from backend.runtime_v3.scope import ContextScope
    decision=evaluate(state,ContextScope(state['camera']['controlled_actor_id']))
    decision.update(candidates=[],selected_ids=[],legacy_unplanned=True)
    decision['budget']['candidates']=0
    return decision


def extraction_policy(decision):
    """Classification needs permissions/IDs, not another copy of planning prose."""
    return dict(risk=decision['risk'],profile={k:decision['profile'][k] for k in ('thread_cap','escalation')},
        outcome=decision['outcome'],budget=decision['budget'],
        candidates=[{k:c[k] for k in ('id','actor_ids','source_kind','source_id','basis_ids')}
                    for c in decision['candidates'] if c['selected']])


def explicit(resolver, item):
    from backend.runtime_v3.life import _proof
    return resolver.mode != 'background' and _proof(resolver,item)


def reject(code, **details):
    from backend.runtime_v3.models import fatal
    # A failed policy cannot be repaired by hiding the already narrated outcome
    # in Extraction. The whole turn remains uncommitted.
    fatal('Предложенные последствия не соответствуют политике истории.',code,repairable=False,**details)


def validate_risk(resolver, raw):
    """Check consequences before ANY facts, Knowledge or History are mutated.

Semantic classification is supplied by the existing Extraction request. Runtime
also derives minimum categories from structural changes; prose is never parsed
for diagnoses. Unclassified conditions use conservative intersection rules.
"""
    state=resolver.before
    _,risk=profiles(state)
    events={e.get('id'):e for e in raw.records['events'] if isinstance(e,dict) and isinstance(e.get('id'),str) and resolver.supported(e)}
    claims={}
    if len(raw.records['consequences'])>24: reject('risk_budget_exceeded')
    for item in raw.records['consequences']:
        try: claim=ConsequenceClaim.model_validate(item).model_dump()
        except (ValueError,TypeError): reject('risk_claim_invalid')
        cid=claim['actor_id'];event=events.get(claim['source_event_id'])
        if cid not in state['characters'] or not event or not isinstance(event.get('participants',[]),list) or cid not in event.get('participants',[]) or not resolver.supported(claim):
            reject('risk_evidence_invalid')
        if not explicit(resolver,claim) and not grounded(state,claim['basis_ids'],cid): reject('risk_grounding_missing')
        claims.setdefault((claim['source_event_id'],cid),set()).add(claim['kind'])
        if explicit(resolver,claim): continue
        if claim['kind'] in ('npc_death','protagonist_death'):
            main=state['meta'].get('current_protagonist_id') or state['camera'].get('controlled_actor_id')
            if (claim['kind']=='protagonist_death') != (cid==main): reject('risk_severity_mismatch')
            if not resolver.death_policy.permits_autonomous_death(state,cid): reject('risk_death_denied',entity=cid)
        elif not risk[claim['kind']]: reject('risk_denied',consequence=claim['kind'],entity=cid)
        # Existing causal processes may progress without manufacturing a new
        # storyline. A new severe disruption needs the original Director permit.
        continuing=any(key in state['conditions'] and state['conditions'][key]['actor_id']==cid
            and state['conditions'][key]['status']=='active' for key in claim['basis_ids'])
        severe=claim['kind'] in ('serious_illness','permanent_injury','major_accident','npc_death','protagonist_death')
        if severe and not continuing:
            selected=[c for c in (resolver.pacing_decision or {}).get('candidates',[]) if c['selected']]
            if not any(c['id']==claim.get('candidate_id') and cid in c['actor_ids'] and
                set(c.get('basis_ids',[c['source_id']])) & set(claim['basis_ids']) for c in selected):
                reject('risk_pacing_required',entity=cid)

    for section in ('life_changes','condition_changes','social_relation_changes','role_changes','residence_changes','events','character_changes'):
        for item in raw.records[section]:
            if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not resolver.supported(item) or explicit(resolver,item): continue
            if any(key in item and not isinstance(item[key],dict) for key in ('effects','capabilities')): continue
            cid=item.get('actor_id',item.get('id'))
            if section=='condition_changes': cid=state['conditions'].get(item.get('id'),{}).get('actor_id',cid)
            if not isinstance(cid,str) or not isinstance(item.get('source_event_id',''),str): continue
            required=set()
            declared=claims.get((item.get('source_event_id'),cid),set())
            if section=='life_changes':
                old=state['characters'].get(cid,{})
                if item.get('life_status')=='dead' and old.get('life_status')!='dead':
                    if not resolver.death_policy.permits_autonomous_death(state,cid): reject('risk_death_denied',entity=cid)
                    if not declared & {'npc_death','protagonist_death'}: reject('risk_classification_required',entity=cid)
                if any(v is False and old.get('capabilities',{}).get(k) is not False for k,v in item.get('capabilities',{}).items()):
                    if not declared & {'serious_illness','injury','permanent_injury','major_accident'}: reject('risk_classification_required',entity=cid)
            if section=='condition_changes' and item.get('status','active')=='active':
                old=state['conditions'].get(item.get('id'),{})
                if not old or item.get('duration')=='persistent' and old.get('duration')!='persistent' or any(v is False and old.get('effects',{}).get(k) is not False for k,v in item.get('effects',{}).items()):
                    if not declared and any(v is False for v in item.get('effects',{}).values()):
                        reject('risk_classification_required',entity=cid)
                    if not declared:
                        required.update(('serious_illness','injury') if any(v is False for v in item.get('effects',{}).values()) else ('minor_illness','injury'))
                        if item.get('duration')=='persistent': required.add('permanent_injury')
                    elif not declared & {'minor_illness','serious_illness','injury','permanent_injury','major_accident'}:
                        reject('risk_classification_required',entity=cid)
                    elif 'injury' in declared and item.get('duration')=='persistent' and 'permanent_injury' not in declared:
                        reject('risk_severity_mismatch')
                    elif any(v is False for v in item.get('effects',{}).values()) and not declared & {'serious_illness','injury','permanent_injury','major_accident'}:
                        reject('risk_severity_mismatch')
            if section=='social_relation_changes' and item.get('status')=='closed' and item.get('consequence_outcome')!='constructive':
                required.add('relationship_loss')
            if section=='role_changes' and item.get('status')=='closed' and item.get('consequence_outcome')!='constructive':
                old=state['roles'].get(item.get('id'),{})
                required.add('career_loss' if old.get('kind') in ('employment','education') else 'life_role_loss')
            if section=='residence_changes' and item.get('status')=='closed' and item.get('transition')=='external' and item.get('consequence_outcome')!='constructive':
                required.add('life_role_loss')
            for key in required:
                if not risk[key]: reject('risk_denied',consequence=key,entity=cid)
    return claims


def grounded(state, ids, actor):
    """Every basis must exist; at least one belongs to the affected actor/context."""
    rows={key:row for section in ('characters','threads','conditions','roles','residences','scheduled_events','facts','objective_relations','locations')
          for key,row in state[section].items()}
    rows.update({goal['id']:dict(goal,actor_id=cid) for cid,c in state['characters'].items()
        for goal in c['goals'] if isinstance(goal,dict)})
    if any(key not in rows for key in ids): return False
    # A victim identity by itself is not a cause.
    if all(key in state['characters'] for key in ids): return False
    return any(actor in rows[key].get('character_ids',[]) or rows[key].get('actor_id')==actor or
        actor in (rows[key].get('source_id'),rows[key].get('target_id')) or
        key in state['locations'] and state['characters'][actor]['location_id']==key
        for key in ids if key not in state['characters'])


def validate_developments(resolver, raw):
    """Declarations link accepted content to selected sources, never instantiate it."""
    decision=resolver.pacing_decision
    records=list(raw.records['narrative_developments'])
    # Accepted severe outcomes must create pressure even if Extraction omitted
    # the redundant development declaration. One source cannot authorize many events.
    declared={r.get('candidate_id'):r.get('source_event_id') for r in records if isinstance(r,dict) and isinstance(r.get('candidate_id'),str)}
    for claim in raw.records['consequences']:
        cid=claim.get('candidate_id')
        if not cid or explicit(resolver,claim): continue
        if cid in declared:
            if declared[cid]!=claim['source_event_id']: reject('pacing_candidate_reused')
            continue
        records.append(dict(candidate_id=cid,source_event_id=claim['source_event_id'],
            assertion='established',evidence=claim['evidence']))
        declared[cid]=claim['source_event_id']
    if not records: return []
    if not decision: reject('pacing_context_missing')
    if len(records)>decision['budget']['candidates']: reject('pacing_budget_exceeded')
    selected={c['id']:c for c in decision['candidates'] if c['selected']}
    events={e.get('id'):e for e in raw.records['events'] if isinstance(e,dict) and isinstance(e.get('id'),str) and resolver.supported(e)}
    canonical_events={event['local_id']:event['id'] for event in resolver.history.events}
    accepted=[];seen=set()
    for item in records:
        try: claim=NarrativeDevelopment.model_validate(item)
        except (ValueError,TypeError): reject('pacing_claim_invalid')
        if claim.escalation>decision['profile']['escalation']: reject('pacing_escalation_limit')
        candidate=selected.get(claim.candidate_id);event=events.get(claim.source_event_id)
        if not candidate or not event or claim.source_event_id not in canonical_events or not resolver.supported(item) or claim.candidate_id in seen:
            reject('pacing_candidate_invalid')
        if not set(candidate['actor_ids']) & set(event.get('participants',[])): reject('pacing_grounding_missing')
        seen.add(claim.candidate_id)
        accepted.append(dict(source_id=claim.candidate_id,source_event_id=canonical_events[claim.source_event_id],family=candidate['family'],
            minute=resolver.state['meta']['world_time'],weight=1. if candidate['family']=='external_disruption' else .6))
    return accepted


def validate_threads(resolver, raw):
    state=resolver.state;pacing,_=profiles(resolver.before)
    prior=sum(t['status'] in ('active','developing') for t in resolver.before['threads'].values())
    after=sum(t['status'] in ('active','developing') for t in state['threads'].values())
    autonomous=[r for r in raw.records['thread_changes'] if isinstance(r,dict) and not explicit(resolver,r)]
    new=[r for r in autonomous if r.get('id') not in resolver.before['threads'] or
         resolver.before['threads'][r['id']]['status'] not in ('active','developing')]
    opened=[r for r in new if state['threads'].get(r.get('id'),{}).get('status') in ('active','developing')]
    if len(opened)>pacing['candidate_budget']: reject('pacing_budget_exceeded')
    if opened and after>max(prior,pacing['thread_cap']): reject('pacing_thread_cap')
    main=state['meta'].get('current_protagonist_id')
    for item in autonomous:
        thread=state['threads'].get(item.get('id'))
        if not thread or not main or main not in thread['character_ids']+thread.get('stakes_for',[]): continue
        if state['meta']['outcome_preference']!='guaranteed_happy_path': continue
        if thread['status']=='resolved':
            if resolver.before['threads'].get(thread['id'],{}).get('status')=='resolved': continue
            if item.get('resolution')!='favorable': reject('favorable_resolution_required')
            continue
        if not thread.get('favorable_path'): reject('favorable_path_required',entity=thread['id'])
        basis=thread['favorable_path']['basis_ids']
        if not grounded(state,basis,main): reject('favorable_path_ungrounded')
        for key in basis:
            if key in state['facts'] and state['knowledge'].get(main+':'+key,{}).get('status')!='known':
                reject('favorable_path_unknown_basis')


def validate_resolved_consequences(resolver, raw):
    """A permitted claim cannot silently survive a rejected canonical transition.

    Accidents may be events without injury; diagnoses/injuries/death and losses
    must also have an accepted domain transition from this same source event.
    """
    accepted_events={event['local_id'] for event in resolver.history.events}
    state=resolver.state
    _,risk=profiles(resolver.before)
    # Include indirect closures (replacement, organization closure, death cascade).
    for domain,section in (('roles','role_changes'),('residences','residence_changes'),('objective_relations','social_relation_changes')):
        for key,old in resolver.before[domain].items():
            after=state[domain].get(key)
            if old['status']!='active' or not after or after['status']!='closed': continue
            sources=[r for r in raw.records[section] if isinstance(r,dict) and
                (r.get('id')==key or isinstance(r.get('replaces'),list) and key in r['replaces'])]
            if any(explicit(resolver,r) or r.get('consequence_outcome')=='constructive' for r in sources): continue
            category='relationship_loss' if domain=='objective_relations' else ('career_loss' if domain=='roles' and old['kind'] in ('education','employment') else 'life_role_loss')
            if not risk[category]: reject('risk_denied',consequence=category,entity=key)
    domains={'minor_illness':'conditions','serious_illness':'conditions',
        'injury':'conditions','permanent_injury':'conditions',
        'npc_death':'characters','protagonist_death':'characters',
        'relationship_loss':'objective_relations','career_loss':'roles','life_role_loss':None}
    sections={'conditions':'condition_changes','characters':'life_changes',
        'objective_relations':'social_relation_changes','roles':'role_changes','residences':'residence_changes'}
    for claim in raw.records['consequences']:
        if claim['source_event_id'] not in accepted_events: reject('risk_event_not_accepted')
        kind=claim['kind'];actor=claim['actor_id']
        if kind=='major_accident': continue
        candidates=('roles','residences') if kind=='life_role_loss' else (domains[kind],)
        matched=False
        for domain in candidates:
            for item in raw.records[sections[domain]]:
                if not isinstance(item,dict) or not isinstance(item.get('id'),str): continue
                if item.get('source_event_id')!=claim['source_event_id']: continue
                row=state[domain].get(item['id'])
                if not row or row==resolver.before[domain].get(item['id']): continue
                if domain=='characters': valid=row['id']==actor and row['life_status']=='dead'
                elif domain=='objective_relations': valid=actor in (row['source_id'],row['target_id']) and row['status']=='closed'
                else: valid=row['actor_id']==actor and row['status']==('active' if domain=='conditions' else 'closed')
                if kind=='permanent_injury': valid=valid and row.get('duration')=='persistent'
                if valid: matched=True
        if not matched: reject('risk_canonical_consequence_missing',consequence=kind,entity=actor)
    if raw.records['consequences']:
        from copy import deepcopy
        resolver.history.state_changes.append(dict(kind='narrative_consequences',
            accepted=[dict(deepcopy(c),source_event_id=next(e['id'] for e in resolver.history.events
                if e['local_id']==c['source_event_id'])) for c in raw.records['consequences']],turn_id=resolver.turn_id))


def salvage_policy(state):
    """Read migration only; invalid optional settings degrade locally with notice."""
    from pydantic import ValidationError
    import logging
    meta=state.setdefault('meta',{})
    for key,model in (('narrative_pacing',NarrativePacingProfile),('narrative_risk',NarrativeRiskProfile)):
        try: meta[key]=model.model_validate(meta.get(key,{})).model_dump()
        except ValidationError:
            meta[key]=model().model_dump()
            logging.getLogger(__name__).warning('Invalid optional %s; using default on read',key)
    recent=[]
    for row in (meta.get('pacing_recent') or [])[-12:] if isinstance(meta.get('pacing_recent',[]),list) else []:
        try:
            value=PacingRecord.model_validate(row).model_dump()
            if value['minute']<=meta.get('world_time',0): recent.append(value)
        except ValidationError:
            logging.getLogger(__name__).warning('Invalid optional pacing memory; ignoring record on read')
    meta['pacing_recent']=recent
    if meta.get('outcome_preference','natural') not in ('natural','prefer_happy','guaranteed_happy_path'):
        meta['outcome_preference']='natural'
