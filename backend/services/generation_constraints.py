"""Deterministic checks for directly representable source facts.

Free-form semantic claims still require interpretation/reconciliation. Never
pretend a fuzzy text match proves that a generated fact preserves the source.
"""


def validate_character_facts(payload, plan):
    fields={'birth_date','biological_sex','life_status','display_name','developmental_stage'}
    for claim in plan['claims']:
        if claim['classification']!='explicit' or claim['section']!='character': continue
        if claim['time_scope'] or claim['field'] not in fields or claim['value'] is None: continue
        actor=payload['characters'].get(claim['subject_id'])
        if actor is not None and actor.get(claim['field'])!=claim['value']:
            raise ValueError('generation/constraints/'+claim['id']+'/characters/'+claim['subject_id']+'/'+claim['field']+': generated value conflicts with explicit source fact')
    return payload


def _subset(value,expected):
    if isinstance(expected,dict):
        return isinstance(value,dict) and all(k in value and _subset(value[k],v) for k,v in expected.items())
    if isinstance(expected,list):
        return isinstance(value,list) and all(any(_subset(v,e) for v in value) for e in expected)
    return type(value) is type(expected) and value==expected


def validate_stage_facts(stage,payload,plan):
    """Enforce source-backed canonical bindings without fuzzy identity matching."""
    for claim in plan['claims']:
        if claim['classification'] not in ('explicit','prohibition'):continue
        for rule in claim.get('rules',[]):
            if rule['stage']!=stage:continue
            path=rule['path'];parts=[p.replace('~1','/').replace('~0','~') for p in path.split('/')[1:]]
            if stage=='characters' and len(parts)>1 and parts[0] in ('characters','cards') and parts[1] not in payload[parts[0]]:continue
            found=True;value=payload
            try:
                for part in parts:value=value[int(part)] if isinstance(value,list) else value[part]
            except (KeyError,TypeError,IndexError,ValueError):found=False
            expected=rule.get('expected');op=rule['operator']
            if op=='equals':valid=found and type(value) is type(expected) and value==expected
            else:
                rows=list(value.values()) if isinstance(value,dict) else value if isinstance(value,list) else []
                if rule.get('where'):rows=[row for row in rows if _subset(row,rule['where'])]
                if op=='only':
                    from backend.services.initial_world_stages import fingerprint
                    selected=[row.get(rule['select']) if isinstance(row,dict) else None for row in rows] if rule.get('select') else rows
                    valid=found and isinstance(expected,list) and sorted(map(fingerprint,selected))==sorted(map(fingerprint,expected))
                else:
                    present=found and any(_subset(row,expected) for row in rows)
                    valid=present if op=='contains' else not present
            if not valid:raise ValueError('generation/constraints/'+claim['id']+path+': результат противоречит исходному ограничению')
    return validate_character_facts(payload,plan) if stage=='characters' else payload


def validate_snapshot_facts(snapshot,plan):
    from backend.services.initial_world_stages import LifePart
    state=snapshot['world_state'];campaign=snapshot.get('campaign',{})
    parents={f['claim']['subject_id']:f['claim']['value'] for f in state['facts'].values() if f.get('claim') and f['claim']['predicate']=='organization.parent'}
    parts=dict(setting={'campaign':campaign.get('campaign',campaign)},
        characters={'characters':state['characters'],'cards':{c['id']:c for c in snapshot.get('character_cards',[])}},
        places={'locations':state['locations'],'organizations':state['organizations'],'parent_organizations':parents},
        life={key:state[key] for key in LifePart.model_fields},
        lore={**{key:state[key] for key in ('facts','knowledge','threads')},'initial_history':snapshot.get('initial_history',{})},
        opening={**{key:state[key] for key in ('camera','scheduled_events')},'world_time':state['meta']['world_time'],'calendar':state['meta']['calendar']})
    for entity in plan['entities']:
        row=state[{'character':'characters','location':'locations','organization':'organizations'}[entity['kind']]].get(entity['id'])
        if row is None or row['display_name' if entity['kind']=='character' else 'name']!=entity['name']:
            raise ValueError('generation/constraints/entities/'+entity['id']+': исходная сущность изменена')
    for stage,payload in parts.items():validate_stage_facts(stage,payload,plan)
    return snapshot
