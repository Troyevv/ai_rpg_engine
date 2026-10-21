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
