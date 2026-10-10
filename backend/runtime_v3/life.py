"""Canonical life/social transitions, using the existing resolver and History.

No biography inference, legal simulator, emotion thresholds, or second graph store.
Graph validation uses stdlib graphlib; projections use bounded deque traversal.
"""
from copy import deepcopy
from graphlib import TopologicalSorter, CycleError
from pydantic import ValidationError
from backend.runtime_v3.models import ObjectiveRelation, Condition, Capabilities, Character
from backend.runtime_v3.calendar import current_time

SYMMETRIC = {'spouse', 'partner', 'engaged', 'sibling', 'contact', 'friend', 'close_friend', 'coworker'}
PARENTAGE = {'parent', 'adoptive_parent'}
FAMILY = PARENTAGE | {'spouse', 'partner', 'engaged', 'guardian', 'foster_parent', 'step_parent', 'sibling'}
VOLUNTARY = {'spouse', 'partner', 'engaged', 'guardian', 'adoptive_parent', 'foster_parent', 'contact', 'friend', 'close_friend'}


def capabilities(state, actor_id):
    actor = state['characters'].get(actor_id, {})
    result = {k: actor.get('capabilities', {}).get(k) is not False for k in Capabilities.model_fields}
    for condition in state.get('conditions', {}).values():
        if condition['actor_id'] == actor_id and condition['status'] in ('active', 'unknown_outcome'):
            for key, value in condition['effects'].items():
                if value is False: result[key] = False
    stage = actor.get('developmental_stage', 'unknown')
    if stage == 'infant':
        result.update(can_act=False, can_speak=False, can_move=False)
    if actor.get('life_status') == 'dead':
        result = dict.fromkeys(result, False)
    if not result['conscious']:
        result.update(can_perceive=False, can_act=False, can_speak=False, can_move=False)
    result.update(adult_eligible=stage == 'adult' and result['can_act'],
                  independent_work=stage == 'adult' and result['can_act'],
                  independent_remote=stage in ('adolescent', 'adult') and result['can_act'])
    return result


def validate_life_state(state):
    actors = state['characters']
    def reference(fid, participants):
        if fid is not None and (fid not in state['facts'] or not set(participants) <= set(state['facts'][fid]['character_ids'])):
            raise ValueError('life/social fact must reference all affected identities')
    graph, active = {}, set()
    for rid, r in state.get('objective_relations', {}).items():
        a, b = r['source_id'], r['target_id']
        if rid != r['id'] or a == b or a not in actors or b not in actors:
            raise ValueError('invalid objective relation endpoints/identity')
        if r['kind'] in SYMMETRIC and a > b:
            raise ValueError('symmetric relation endpoints must be canonical sorted IDs')
        if r['status'] == 'active':
            if r['until'] is not None or r['outcome']:
                raise ValueError('active relation has a closure')
            key = (r['kind'], a, b)
            if key in active: raise ValueError('duplicate active relation phase')
            active.add(key)
            if r['kind'] in ('spouse', 'partner', 'engaged') and any(actors[c].get('life_status') == 'dead' for c in (a,b)):
                raise ValueError('dead actor cannot have an active partnership')
        if r['since'] is not None and r['until'] is not None and r['until'] < r['since']:
            raise ValueError('relation closes before it starts')
        if r['kind']=='parent' and actors[a].get('birth_date') and actors[b].get('birth_date'):
            from backend.runtime_v3.calendar import ordinal, profile_of
            if ordinal(actors[a]['birth_date'],profile_of(state)) >= ordinal(actors[b]['birth_date'],profile_of(state)):
                raise ValueError('parent cannot be born at or after child birth')
        for f in ('fact_id', 'closure_fact_id'): reference(r[f], (a,b))
        # Historical ancestry remains ancestry. Revocation does not permit cycles.
        if r['kind'] in PARENTAGE | {'guardian','foster_parent','step_parent'}:
            graph.setdefault(b,set()).add(a)
    try: tuple(TopologicalSorter(graph).static_order())
    except CycleError as exc: raise ValueError('cyclic parentage') from exc
    for key, c in state.get('conditions', {}).items():
        if key != c['id'] or c['actor_id'] not in actors:
            raise ValueError('invalid condition identity/actor')
        if any(v is True for v in c['effects'].values()):
            raise ValueError('conditions restrict capabilities; cannot grant them')
        if c['until'] is not None and (c['status'] in ('active','unknown_outcome') or c['since'] is not None and c['until'] < c['since']):
            raise ValueError('invalid condition chronology')
        reference(c['fact_id'], (c['actor_id'],))
    for cid, c in actors.items():
        for f in ('life_fact_id','parentage_complete_fact_id'): reference(c.get(f), (cid,))
        previous = None
        for n in c.get('name_history', []):
            reference(n['fact_id'], (cid,))
            if previous and (n['previous'] != previous['current'] or n['minute'] < previous['minute']):
                raise ValueError('inconsistent identity chronology')
            previous = n
        if previous and previous['current'] != c.get('display_name'):
            raise ValueError('current name differs from identity chronology')
    if any(actors[c].get('life_status') == 'dead' for c in state['camera']['present_character_ids']):
        raise ValueError('dead actor in ordinary scene')
    if any(actors[r['actor_id']].get('life_status') == 'dead' for r in state['camera']['remote_interactions']):
        raise ValueError('dead remote actor')


def _proof(resolver, item):
    from backend.runtime_v3.resolver import normalized
    proof = item.get('player_evidence')
    return (item.get('player_assertion') == 'explicit_choice' and isinstance(proof,str)
            and bool(normalized(proof)) and normalized(proof) in normalized(resolver.player_input))


def _transition(resolver, section, key, before, after, item):
    """Append structured provenance; bounded History reads never own current truth."""
    from backend.runtime_v3.milestones import stable_id, transition_provenance
    actors = ([key] if section in ('life_changes','birth_date_established') else
              [after[k] for k in ('actor_id','source_id','target_id') if after.get(k)])
    actors = list(dict.fromkeys([*actors, *after.get('character_ids', [])]))
    record = dict(kind=section, entity=key, before=deepcopy(before), after=deepcopy(after),
        turn_id=resolver.turn_id, minute=resolver.state['meta']['world_time'],
        date=current_time(resolver.state)['date'], evidence=item['evidence'], player_observed=resolver.observed,
        names={cid:resolver.state['characters'][cid].get('display_name') or resolver.actor_names.get(cid,cid) for cid in actors},
        **transition_provenance(resolver,item,actors))
    record['id'] = stable_id('transition', {k:v for k,v in record.items() if k not in ('evidence','names','player_observed')})
    if section == 'roles' and item.get('significance') in ('major','routine'):
        record['significance'] = item['significance']
    resolver.history.state_changes.append(record)


def _records(resolver, raw, section):
    # Unlike mandatory camera IDs, bad optional transition IDs are record-local.
    seen = set()
    for i,item in enumerate(raw.records.get(section, [])):
        key = item.get('id') if isinstance(item,dict) else None
        if not isinstance(key,str) or not key.strip() or key in seen or not resolver.supported(item):
            resolver.warn(section,i,'Нужны уникальный ID и подтверждённое основание.',code='life_transition_invalid')
            continue
        seen.add(key)
        yield i,item


def apply_life(resolver, raw):
    """Run after facts/knowledge, before ordinary actor updates and final validation."""
    s = resolver.state
    now, date = s['meta']['world_time'], current_time(s)['date']
    controlled = resolver.protected_actor_id
    for section in ('life_changes','condition_changes','social_relation_changes'):
        for index, item in _records(resolver,raw,section):
            key = item['id']
            old_state = deepcopy(s)
            history_size = len(resolver.history.state_changes)
            try:
                if item.get('assertion') != 'established':
                    raise ValueError('only established/completed truth, not intent or proposal')
                if section == 'life_changes':
                    if key not in s['characters']: raise ValueError('unknown actor')
                    if resolver.mode == 'background' and key == controlled: raise ValueError('protected background actor')
                    old = deepcopy(s['characters'][key]); actor = s['characters'][key]
                    for field in ('life_status','capabilities','developmental_stage','parentage_complete_fact_id'):
                        if field in item:
                            if field == 'capabilities':
                                value = Capabilities.model_validate(item[field]).model_dump(exclude_unset=True)
                                actor[field].update(value)
                            else: actor[field] = item[field]
                    if 'life_status' in item:
                        if old['life_status'] == 'dead' and item['life_status'] != 'dead':
                            raise ValueError('death cannot be undone by ordinary extraction; use rollback')
                        actor['life_fact_id'] = item.get('fact_id')
                    if 'display_name' in item:
                        name = item['display_name']
                        if not isinstance(name,str) or not name.strip(): raise ValueError('empty name')
                        if key == controlled and not _proof(resolver,item): raise ValueError('name choice needs player evidence')
                        previous = actor['display_name'] or resolver.actor_names.get(key)
                        if not previous: raise ValueError('missing original name')
                        if name != previous:
                            actor['name_history'].append(dict(previous=previous,current=name,minute=now,date=date,
                                turn_id=resolver.turn_id,evidence=item['evidence'],fact_id=item.get('fact_id')))
                            actor['display_name'] = name
                    s['characters'][key] = Character.model_validate(actor).model_dump()
                    if actor['life_status'] == 'dead':
                        # Remove ordinary participation, retain identity/control/history/location.
                        s['camera']['present_character_ids'] = [c for c in s['camera']['present_character_ids'] if c != key]
                        s['camera']['remote_interactions'] = [r for r in s['camera']['remote_interactions'] if r['actor_id'] != key]
                        for r in s['objective_relations'].values():
                            if r['status'] == 'active' and key in (r['source_id'],r['target_id']) and r['kind'] in ('spouse','partner','engaged'):
                                prior = deepcopy(r)
                                r.update(status='closed',until=now,until_date=date,outcome='widowed' if r['kind']=='spouse' else 'ended',
                                         evidence=item['evidence'],source_turn=resolver.turn_id)
                                # Death knowledge does not automatically disclose the partnership.
                                r['closure_fact_id'] = None
                                _transition(resolver,'objective_relations',r['id'],prior,r,item)
                    after = s['characters'][key]
                elif section == 'condition_changes':
                    old = deepcopy(s['conditions'].get(key))
                    cid = old['actor_id'] if old else item.get('actor_id')
                    if cid not in s['characters']: raise ValueError('unknown condition actor')
                    if resolver.mode == 'background' and cid == controlled: raise ValueError('protected background actor')
                    if old and old['status'] in ('resolved','cancelled'): raise ValueError('terminal condition: new phase needs new ID')
                    if old is None and item.get('status','active') != 'active': raise ValueError('new condition must begin active')
                    fields = deepcopy(old or dict(id=key,actor_id=cid,since=now))
                    for f in ('description','effects','duration','status','fact_id'):
                        if f in item:
                            # Unknown effect values cannot release an existing restriction.
                            fields[f] = {**fields.get(f,{}),**Capabilities.model_validate(item[f]).model_dump(exclude_unset=True,exclude_none=True)} if f=='effects' else item[f]
                    if 'actor_id' in item and item['actor_id'] != cid: raise ValueError('condition identity cannot change')
                    fields.update(evidence=item['evidence'],source_turn=resolver.turn_id)
                    if fields.get('status') in ('resolved','cancelled'): fields['until'] = now
                    after = Condition.model_validate(fields).model_dump()
                    s['conditions'][key] = after
                else:
                    old = deepcopy(s['objective_relations'].get(key))
                    if old and old['status'] == 'closed': raise ValueError('closed phase is immutable; use new ID')
                    fields = deepcopy(old or dict(id=key,since=now,since_date=date))
                    for f in ('kind','source_id','target_id','context','fact_id','status','outcome','closure_fact_id'):
                        if f in item: fields[f] = item[f]
                    if fields.get('kind') == 'child':
                        fields['kind'] = 'parent'
                        fields['source_id'],fields['target_id'] = fields.get('target_id'),fields.get('source_id')
                    if fields.get('kind') in SYMMETRIC and all(isinstance(fields.get(k),str) for k in ('source_id','target_id')):
                        fields['source_id'],fields['target_id'] = sorted((fields['source_id'],fields['target_id']))
                    if old and any(fields.get(f) != old[f] for f in ('kind','source_id','target_id','fact_id')):
                        raise ValueError('relation identity cannot be rewritten')
                    if fields.get('status') == 'closed':
                        if not old: raise ValueError('cannot close unknown relation')
                        fields.update(until=now,until_date=date,outcome=item.get('outcome','ended'))
                    ids = (fields.get('source_id'),fields.get('target_id'))
                    if any(not isinstance(c,str) or c not in s['characters'] for c in ids): raise ValueError('unknown relation actor')
                    if resolver.mode == 'background' and controlled in ids: raise ValueError('protected background relation')
                    if not old and fields.get('kind') in VOLUNTARY and controlled in ids and not _proof(resolver,item):
                        raise ValueError('voluntary relation needs explicit player choice')
                    if old and fields.get('status') == 'closed' and controlled in ids:
                        decision = item.get('decision_actor_id')
                        if decision not in ids or decision == controlled:
                            if not _proof(resolver,item): raise ValueError('closure needs NPC decision or player choice')
                    fields.update(evidence=item['evidence'],source_turn=resolver.turn_id)
                    after = ObjectiveRelation.model_validate(fields).model_dump()
                    s['objective_relations'][key] = after
                validate_life_state(s)
                _transition(resolver,section,key,old,after,item)
            except (ValueError,TypeError,KeyError,ValidationError) as exc:
                s.clear(); s.update(old_state)
                del resolver.history.state_changes[history_size:]
                resolver.warn(section,index,str(exc),entity=key,code='life_transition_invalid')
    # Owners consume dead IDs independently; no monolithic cascade deleting state.
    dead = {cid for cid,c in s['characters'].items() if c['life_status']=='dead'}
    from backend.runtime_v3.lifecycle import invalidate_dead_motivations
    from backend.runtime_v3.commitments import invalidate_dead_commitments
    invalidate_dead_motivations(resolver,dead)
    invalidate_dead_commitments(resolver,dead)


def salvage_life_data(state):
    """Read-only optional schema salvage. Never update stored historical snapshots.

    Structural cross-reference/cycle failures still raise an invariant diagnostic;
    only individually malformed additions degrade here, with a logged warning.
    """
    import logging
    state=deepcopy(state)
    if not isinstance(state,dict): return state
    log=logging.getLogger(__name__)
    for cid, actor in state.get('characters',{}).items():
        if not isinstance(actor,dict): continue
        for field in ('life_status','life_fact_id','display_name','name_history','capabilities','developmental_stage','parentage_complete_fact_id'):
            if field not in actor: continue
            try: Character.model_validate(dict(id=cid,**{field:actor[field]}))
            except (ValueError,TypeError):
                log.warning('Ignoring malformed optional life field %s for %s',field,cid)
                if field=='capabilities':
                    # Corruption must not silently restore an incapacitated actor.
                    actor[field]=dict.fromkeys(Capabilities.model_fields,False)
                else: actor.pop(field)
    for section,model in (('objective_relations',ObjectiveRelation),('conditions',Condition)):
        records=state.get(section,{})
        if not isinstance(records,dict):
            if section=='conditions':
                raise ValueError('Malformed condition section requires explicit repair; capability safety cannot be established')
            log.warning('Ignoring malformed optional life section %s',section)
            state[section]={};continue
        for key,record in list(records.items()):
            try:model.model_validate(record)
            except (ValueError,TypeError):
                if section=='conditions':
                    # A corrupt limitation cannot be treated as cured/removed.
                    raise ValueError('Malformed condition requires explicit repair; capability safety cannot be established')
                log.warning('Ignoring malformed optional %s record %s',section,key)
                records.pop(key)
    return state
