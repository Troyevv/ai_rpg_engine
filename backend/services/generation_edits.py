"""Author patches of validated generation checkpoints; no alternate world model."""
from copy import deepcopy

from backend.services.initial_world_stages import validate_character_batch
from backend.runtime_v3.models import PersonalityItem
from backend.services.generation_constraints import validate_character_facts


def patch_character(repo, wid, jid, unit, revision, artifact_version, cid, field, value, *, preview=True):
    job=repo.preparation_job(jid)
    if not job or job['workspace_id']!=wid:
        raise ValueError('generation/edit: job does not belong to this workspace')
    checkpoint=repo.inspect_generation_checkpoint(jid,unit,author=True)
    if checkpoint['stage']!='characters' or checkpoint['status']!='completed':
        raise ValueError('generation/edit: select a validated character checkpoint')
    payload=deepcopy(checkpoint['artifact'])
    if cid not in payload['characters']:
        raise ValueError('generation/edit: character does not belong to this checkpoint')
    if not isinstance(value,str) or not value.strip() or len(value)>3000:
        raise ValueError('generation/edit: character description must contain 1–3000 characters')
    # Only personality text is exposed here. Do not offer arbitrary JSON writes
    # to identity, source claims, Knowledge, evidence or protagonist intentions.
    profile=payload['characters'][cid].get('personality') or dict(items={},evidence={},applied=[],seen_sources=[])
    if field.startswith('personality.items.') and field.endswith('.text'):
        key=field[len('personality.items.'):-len('.text')]
        if key not in profile['items']: raise ValueError('generation/edit: personality item not found')
        item=profile['items'][key]
        category=item['field']
    elif field.startswith('personality.'):
        category=field[len('personality.'):]
        # Pydantic owns the canonical category vocabulary.
        item=PersonalityItem(field=category,text=value).model_dump()
        if any(row['field']==category for row in profile['items'].values()):
            raise ValueError('generation/edit: edit the existing personality item')
        key='author_'+category
        if key in profile['items']: raise ValueError('generation/edit: personality item identity conflict')
    else:
        raise ValueError('generation/edit: this field is not editable at a checkpoint')
    plan=repo.generation_resources(jid,['interpretation'])['interpretation']
    for claim in plan['claims']:
        if claim['classification'] not in ('explicit','prohibition'): continue
        if claim['subject_id'] not in (None,cid): continue
        # A free-form source constraint cannot safely be reconciled by substring
        # matching. Preserve it and request a versioned source revision instead.
        if claim['section']=='personality' or (claim['section']=='character' and claim['field'] in ('personality','traits','communication','habits','strengths','weaknesses','fears','preferences','temperament')):
            raise ValueError('generation/constraints/'+claim['id']+': explicit personality constraint; revise the source constraint before editing this character')
    item={**item,'text':value.strip(),'revision':item.get('revision',0)+1}
    profile['items'][key]=item
    payload['characters'][cid]['personality']=profile
    registry=repo.generation_resources(jid,['registry'])['registry']
    payload=validate_character_facts(validate_character_batch(payload,list(payload['characters']),registry),plan)
    escape=lambda text:text.replace('~','~0').replace('/','~1')
    # Lock the entire item, including its canonical category and revision.
    pointer='/characters/'+escape(cid)+'/personality/items/'+escape(key)
    return repo.revise_generation_checkpoint(jid,unit,payload,revision,artifact_version,[pointer],preview=preview)
