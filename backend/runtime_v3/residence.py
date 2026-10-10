"""Residence, geographic hierarchy and ongoing social roles inside Runtime v3.

Stdlib graphlib suffices for this single-parent DAG; NetworkX would add no needed
algorithm here. No schedules, population simulation, or inferred biography.
"""
from copy import deepcopy
from graphlib import TopologicalSorter, CycleError
from backend.runtime_v3.models import Location, Residence, NarrativeRole, Organization
from backend.runtime_v3.calendar import current_time, date_parts, profile_of
from backend.runtime_v3.life import _records, _proof, _transition

MODELS = {'residences': Residence, 'roles': NarrativeRole, 'organizations': Organization}


def validate_hierarchy(locations):
    for key, loc in locations.items():
        if key != loc['id'] or not key or (loc['parent_id'] is not None and loc['parent_id'] not in locations):
            raise ValueError('invalid location identity/parent reference')
    try:
        tuple(TopologicalSorter({key: [loc['parent_id']] if loc['parent_id'] else []
                                 for key, loc in locations.items()}).static_order())
    except CycleError as exc:
        raise ValueError('cyclic location hierarchy') from exc


def validate_residence_state(state):
    validate_hierarchy(state['locations'])
    active = set()
    organization_names = set()
    def fact(fid, actor=None):
        if fid is not None and (fid not in state['facts'] or actor and actor not in state['facts'][fid]['character_ids']):
            raise ValueError('unknown or unrelated residence/role fact')
    for section in MODELS:
        for key, row in state.get(section, {}).items():
            if key != row['id'] or not key:
                raise ValueError('invalid residence/role/organization identity')
            actor = row.get('actor_id')
            if section != 'organizations' and actor not in state['characters']:
                raise ValueError('unknown residence/role actor')
            if row['status'] != 'closed' and (row['until'] is not None or row['until_date'] is not None or row['outcome'] or row['closure_fact_id'] is not None):
                raise ValueError('open phase cannot contain closure')
            if row['since'] is not None and row['until'] is not None and row['until'] < row['since']:
                raise ValueError('phase closes before it starts')
            from backend.runtime_v3.calendar import ordinal
            for field in ('since_date', 'until_date'):
                if row[field] is not None: date_parts(row[field], profile_of(state))
            if row['since_date'] and row['until_date'] and ordinal(row['until_date'], profile_of(state)) < ordinal(row['since_date'], profile_of(state)):
                raise ValueError('phase calendar chronology reversed')
            for field in ('fact_id', 'closure_fact_id'): fact(row[field], actor)
            if section == 'residences':
                if row['location_id'] not in state['locations']: raise ValueError('unknown residence location')
                signature = (section, actor, row['location_id'])
            elif section == 'roles':
                org = row['organization_id']
                if org is not None and org not in state['organizations']: raise ValueError('unknown organization')
                if row['status'] == 'active' and org and state['organizations'][org]['status'] == 'closed':
                    raise ValueError('active affiliation at closed organization')
                signature = (section, actor, row['kind'], row['title'], org, row['field'])
            else:
                names = _aliases(row)
                if organization_names & names: raise ValueError('duplicate organization name/alias requires canonical identity')
                organization_names.update(names)
                if any(lid not in state['locations'] for lid in row['location_ids']): raise ValueError('unknown organization location')
                previous = None
                for change in row['name_history']:
                    fact(change['fact_id'])
                    if previous and (change['previous'] != previous['current'] or change['minute'] < previous['minute']):
                        raise ValueError('invalid organization name history')
                    previous = change
                if previous and previous['current'] != row['name']: raise ValueError('organization name differs from history')
                continue
            if row['status'] == 'active':
                if signature in active: raise ValueError('duplicate active phase')
                active.add(signature)


def _aliases(row):
    from backend.runtime_v3.resolver import normalized
    return {normalized(s).casefold() for s in [row['name'], *row.get('aliases', [])] if normalized(s)}


def _remap(raw, remap, field):
    """A supplied canonical alias is identity evidence, never fuzzy matching."""
    if not remap: return
    if field == 'location_id':
        if isinstance(raw.final_scene.get('location_id'),str) and raw.final_scene['location_id'] in remap:
            raw.final_scene['location_id'] = remap[raw.final_scene['location_id']]
    for section, rows in raw.records.items():
        for row in rows:
            if not isinstance(row, dict): continue
            keys = ('location_id','to_location_id','parent_id') if field == 'location_id' else ('organization_id',)
            for key in keys:
                if isinstance(row.get(key), str) and row[key] in remap: row[key] = remap[row[key]]
            if field == 'location_id' and isinstance(row.get('location_ids'),list):
                row['location_ids'] = [remap.get(k,k) if isinstance(k,str) else k for k in row['location_ids']]


def apply_locations(resolver, raw):
    state = resolver.state
    candidates = {}
    remap = {}
    for i, item in resolver.records(raw, 'locations'):
        fields = {k:v for k,v in item.items() if k in Location.model_fields}
        row = resolver.typed(Location, fields, 'locations', i)
        if row is None: continue
        key = row['id']
        if not key.strip() or (key not in state['locations'] and not row['name'].strip()):
            resolver.warn('locations',i,'Нужны ID и имя нового места.',entity=key)
            continue
        if key in state['locations']:
            # Repeating an existing ID is allowed, but mutations use location_changes.
            if any(state['locations'][key][k] != v for k,v in fields.items()):
                from backend.runtime_v3.models import fatal
                fatal('конфликт canonical location ID', 'canonical_id_conflict', repairable=True)
            continue
        matches = [lid for lid, loc in {**state['locations'], **{k:v[1] for k,v in candidates.items()}}.items()
                   if _aliases(loc) & _aliases(row) and (row['parent_id'] is None or loc['parent_id'] is None or row['parent_id'] == loc['parent_id'])]
        if matches:
            if len(matches) == 1:
                remap[key] = matches[0]
                resolver.warn('locations', i, 'Использован известный canonical ID места.', entity=key, code='location_identity_reused')
            else: resolver.warn('locations', i, 'Неоднозначное имя места: укажи canonical ID.', entity=key)
            continue
        candidates[key] = (i,row,item)
    # Parents can follow children in one extraction. Reject cycles and dependent
    # orphan records locally, preserving every unrelated valid creation.
    for _,row,_ in candidates.values(): row['parent_id'] = remap.get(row['parent_id'],row['parent_id'])
    while candidates:
        graph = {**state['locations'], **{k:v[1] for k,v in candidates.items()}}
        bad = {k for k,(_,r,_) in candidates.items() if r['parent_id'] is not None and r['parent_id'] not in graph}
        if not bad:
            try: tuple(TopologicalSorter({k:[r['parent_id']] if r['parent_id'] else [] for k,r in graph.items()}).static_order())
            except CycleError as exc: bad = set(exc.args[1]) & candidates.keys()
        if not bad: break
        for key in sorted(bad):
            i,_,_ = candidates.pop(key)
            resolver.warn('locations',i,'Некорректная иерархия места.',entity=key,code='location_hierarchy_invalid')
    for key,(_,row,item) in candidates.items():
        state['locations'][key] = row
        _transition(resolver,'locations',key,None,row,item)
    _remap(raw,remap,'location_id')
    for i,item in _records(resolver,raw,'location_changes'):
        key=item['id']; old=deepcopy(state['locations'].get(key))
        try:
            if old is None or item.get('assertion') != 'established': raise ValueError('established known location required')
            if set(item) - {'id','assertion','evidence','parent_id','kind','aliases'}: raise ValueError('arbitrary location rewrite forbidden')
            row=deepcopy(old)
            for k in ('parent_id','kind','aliases'):
                if k in item: row[k]=item[k]
            state['locations'][key]=Location.model_validate(row).model_dump()
            validate_hierarchy(state['locations'])
            _transition(resolver,'locations',key,old,state['locations'][key],item)
        except (ValueError,TypeError,KeyError) as exc:
            if old is not None: state['locations'][key]=old
            resolver.warn('location_changes',i,str(exc),entity=key,code='location_hierarchy_invalid')


def _close(resolver, section, row, item, outcome, record=True):
    before = deepcopy(row)
    row.update(status='closed', until=resolver.state['meta']['world_time'],
        until_date=current_time(resolver.state)['date'], outcome=outcome,
        closure_fact_id=item.get('closure_fact_id'), source_turn=resolver.turn_id)
    # Keep opening evidence/context intact; closing evidence lives in History.
    if record: _transition(resolver,section,row['id'],before,row,item)


def _agency(resolver, actor, item):
    if actor != resolver.protected_actor_id: return
    if resolver.mode == 'background': raise ValueError('protected background actor')
    decision = item.get('decision_actor_id')
    if _proof(resolver,item): return
    if (item.get('transition') == 'external' and isinstance(decision,str)
            and decision in resolver.state['characters'] and decision != actor): return
    raise ValueError('controlled voluntary transition requires explicit player choice; external outcome requires its decision actor')


def apply_residence(resolver, raw):
    state = resolver.state
    for section, target in (('organization_changes','organizations'), ('residence_changes','residences'), ('role_changes','roles')):
        for i,item in _records(resolver,raw,section):
            key=item['id']; prior=deepcopy(state); size=len(resolver.history.state_changes)
            try:
                if item.get('assertion') != 'established': raise ValueError('completed/established evidence required')
                model=MODELS[target]; old=deepcopy(state[target].get(key))
                if old and old['status']=='closed': raise ValueError('closed phase is immutable; use new ID')
                allowed = set(model.model_fields) - {'since','until','since_date','until_date','source_turn','name_history'}
                controls = {'assertion'} if target=='organizations' else {'assertion','player_assertion','player_evidence','decision_actor_id','transition','replaces'}
                controls |= {'source_event_id','source_process_id'}
                if target == 'roles':
                    controls.add('significance')
                    if 'significance' in item and item['significance'] not in ('major','routine'):
                        raise ValueError('invalid role significance')
                if set(item)-allowed-controls: raise ValueError('arbitrary state or chronology rewrite forbidden')
                if target == 'organizations':
                    if not old:
                        matches=[o for o in state[target].values() if isinstance(item.get('name'),str) and
                                 _aliases(o) & _aliases(dict(name=item['name'],aliases=item.get('aliases',[])))]
                        if matches: raise ValueError('known organization identity/alias: use its stable ID')
                    fields=deepcopy(old or dict(id=key,since=state['meta']['world_time'],since_date=current_time(state)['date']))
                    for field in ('name','kind','aliases','location_ids','context','fact_id','status'):
                        if field in item: fields[field]=item[field]
                    if old and 'fact_id' in item and item['fact_id'] != old['fact_id']:
                        # For a rename the new fact belongs to the name change, not creation.
                        fields['fact_id']=old['fact_id']
                    if old and fields['name'] != old['name']:
                        fields['name_history'].append(dict(previous=old['name'],current=fields['name'],
                            minute=state['meta']['world_time'],date=current_time(state)['date'],turn_id=resolver.turn_id,
                            evidence=item['evidence'],fact_id=item.get('fact_id')))
                        fields['aliases']=list(dict.fromkeys([*fields['aliases'],old['name']]))
                    if fields.get('status')=='closed':
                        if not old: raise ValueError('cannot close unknown organization')
                        # In background, do not implicitly alter protected affiliations.
                        if resolver.mode=='background' and any(r['actor_id']==resolver.protected_actor_id and r['status']=='active' and r['organization_id']==key for r in state['roles'].values()):
                            raise ValueError('protected affiliation needs foreground outcome')
                        _close(resolver,target,fields,item,'closed',record=False)
                        for row in state['roles'].values():
                            if row['organization_id']==key and row['status']=='active':
                                closure=dict(item)
                                fid=item.get('closure_fact_id')
                                if not fid or row['actor_id'] not in state['facts'].get(fid,{}).get('character_ids',[]): closure.pop('closure_fact_id',None)
                                _close(resolver,'roles',row,closure,'organization_closed')
                    fields.update(source_turn=resolver.turn_id)
                    if not old: fields['evidence']=item['evidence']
                else:
                    actor=old['actor_id'] if old else item.get('actor_id')
                    if not isinstance(actor,str) or actor not in state['characters']: raise ValueError('unknown actor')
                    _agency(resolver,actor,item)
                    fields=deepcopy(old or dict(id=key,actor_id=actor,since=state['meta']['world_time'],since_date=current_time(state)['date']))
                    identity_fields = ('actor_id','location_id') if target=='residences' else ('actor_id','kind','title','organization_id','field')
                    if old:
                        if any(k in item and item[k] != old[k] for k in (*identity_fields,'context','fact_id')):
                            raise ValueError('phase identity/context cannot change; close old and create new phase')
                        if item.get('status') != 'closed': raise ValueError('existing phase requires explicit closure')
                        _close(resolver,target,fields,item,item.get('outcome','ended'),record=False)
                    else:
                        if item.get('status','active') != 'active': raise ValueError('new phase must begin active')
                        if state['characters'][actor]['life_status']=='dead': raise ValueError('cannot start phase for dead actor')
                        if item.get('outcome') or item.get('closure_fact_id'): raise ValueError('new phase cannot include closure')
                        for field in (*identity_fields,'context','fact_id'):
                            if field in item: fields[field]=item[field]
                        fields.update(evidence=item['evidence'],source_turn=resolver.turn_id)
                    replacements=item.get('replaces',[])
                    if not isinstance(replacements,list) or any(not isinstance(k,str) for k in replacements) or len(set(replacements))!=len(replacements): raise ValueError('invalid replacement IDs')
                    if old and replacements: raise ValueError('only new phase can replace old phases')
                    for rid in replacements:
                        row=state[target].get(rid)
                        if row is None or row['actor_id']!=actor or row['status']!='active': raise ValueError('replacement must identify active phase of same actor')
                        # Replacement is an explicit semantic assertion, never an exclusivity default.
                        _close(resolver,target,row,dict(item,closure_fact_id=item.get('fact_id')),'replaced')
                after=model.model_validate(fields).model_dump()
                state[target][key]=after
                validate_residence_state(state)
                _transition(resolver,target,key,old,after,item)
            except (ValueError,TypeError,KeyError) as exc:
                state.clear();state.update(prior)
                del resolver.history.state_changes[size:]
                resolver.warn(section,i,str(exc),entity=key,code='residence_transition_invalid')


def select_social_ids(state, actor_ids, query=''):
    """Domain-specific inputs to the existing ContextScope, never a second store."""
    from backend.runtime_v3.scope import mentions
    result={section:[r['id'] for r in state.get(section,{}).values()
                     if r['actor_id'] in actor_ids and r['status']=='active']
            for section in ('residences','roles')}
    organizations={state['roles'][rid]['organization_id'] for rid in result['roles']
                   if state['roles'][rid]['organization_id']}
    organizations.update(oid for oid,o in state.get('organizations',{}).items()
                         if mentions(query,[o['name'],*o['aliases']]))
    result['organizations']=sorted(organizations)
    return result


def visible_social_state(state, observer, actor_ids=None):
    """Knowledge-authorized UI; opening knowledge cannot disclose a later closure.

    No self-knowledge inference either: explicit informational events are the
    existing single knowledge acquisition path. No hidden provenance is returned.
    """
    from backend.runtime_v3.kinship import knowledge_status
    result={'residences':[], 'roles':[]}
    for section in result:
        for row in state.get(section,{}).values():
            if actor_ids is not None and row['actor_id'] not in actor_ids: continue
            certainty=knowledge_status(state,observer,row['fact_id'])
            if certainty=='unknown': continue
            closed=row['status']=='closed' and knowledge_status(state,observer,row['closure_fact_id'])=='known'
            view={k:row[k] for k in ('id','actor_id','since','since_date')}
            view.update(status='closed' if closed else 'active',certainty=certainty,
                        until=row['until'] if closed else None,until_date=row['until_date'] if closed else None,
                        outcome=row['outcome'] if closed else '')
            if section=='residences':
                view['label']=state['locations'][row['location_id']]['name']
            else:
                view['label']=row['title'];view['kind']=row['kind'];view['field']=row['field']
                org=state['organizations'].get(row['organization_id'])
                if org:
                    name=org['name_history'][0]['previous'] if org['name_history'] else org['name']
                    for change in org['name_history']:
                        if knowledge_status(state,observer,change['fact_id'])=='known': name=change['current']
                    view['organization']=name
            result[section].append(view)
    return result
