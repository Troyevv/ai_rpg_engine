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


def patch_checkpoint(repo,wid,jid,unit,revision,artifact_version,path,value,*,preview=True,operation='patch',ack=False):
    from backend.services import initial_world_stages as stages
    from backend.services.world_interpretation import InterpretedClaim, EntitySeed
    from backend.services.initial_world_v2 import _check
    from backend.services.world_creation_settings import CreationSettings
    from backend.services.generation_constraints import validate_stage_facts
    job=repo.preparation_job(jid)
    if not job or job['workspace_id']!=wid:raise ValueError('generation/edit: чужой черновик')
    cp=repo.inspect_generation_checkpoint(jid,unit,True)
    if operation=='unlock':
        return repo.unlock_generation_fields(jid,unit,revision,artifact_version,[path],preview=preview)
    if cp['status']!='completed' or cp['artifact_version']!=artifact_version:raise ValueError('generation/artifact: обнови версию этапа')
    stage=cp['stage'];payload=deepcopy(cp['artifact'])
    if stage=='assembly':raise ValueError('generation/edit: сборка вычисляется из предыдущих этапов')
    parts=[p.replace('~1','/').replace('~0','~') for p in path.split('/')[1:]] if path.startswith('/') else []
    if operation not in ('patch','regenerate','unlock'):raise ValueError('generation/edit: неизвестное действие')
    if operation!='regenerate' and not parts:raise ValueError('generation/edit: выбери поле')
    if any(p in ('id','existing_id','key') for p in parts):raise ValueError('generation/edit: идентификаторы менять нельзя')
    if stage=='interpret' and operation!='patch':raise ValueError('generation/edit: пересмотри исходное ограничение явно')
    if operation=='patch':
        if stage=='interpret':
            if not ack:raise ValueError('generation/constraints: подтверди явный пересмотр ограничения')
            allowed=(len(parts)==3 and parts[0]=='claims' and parts[2] in ('value','description','classification','blocking','time_scope','holder_ids','related_ids','subject_id','rules')) or (len(parts)==2 and parts[0]=='claims') or (len(parts)==3 and parts[0]=='entities' and parts[2] in ('name','tier')) or parts==['creation']
            if not allowed:raise ValueError('generation/constraints: исходный текст и история неизменяемы')
            if parts[0]=='claims' and len(parts)==2:
                old=payload['claims'][int(parts[1])]
                if not isinstance(value,dict) or any(value.get(k)!=old.get(k) for k in ('id','spans','section','field')):
                    raise ValueError('generation/constraints: сохрани идентификатор, источник и тип ограничения')
        target=payload
        try:
            for part in parts[:-1]:target=target[int(part)] if isinstance(target,list) else target[part]
            if isinstance(target,list):target[int(parts[-1])]=value
            else:
                if parts[-1] not in target and stage!='interpret':raise KeyError(parts[-1])
                target[parts[-1]]=value
        except (KeyError,IndexError,TypeError,ValueError):raise ValueError('generation/edit: поле не найдено') from None
    if stage=='interpret':
        for index,entity in enumerate(payload['entities']):
            _check(EntitySeed,{'key':str(index),**{k:v for k,v in entity.items() if k in EntitySeed.model_fields}},'interpretation/entities/'+str(index))
        ids={r['id'] for r in payload['entities']};people={r['id'] for r in payload['entities'] if r['kind']=='character'}
        for claim in payload['claims']:
            required={'id','subject_id','holder_ids','related_ids','classification','blocking','spans','section','field'}
            if not isinstance(claim,dict) or not required<=claim.keys():raise ValueError('generation/constraints: запись ограничения неполна')
            raw={k:v for k,v in claim.items() if k in InterpretedClaim.model_fields}
            raw.update(subject_key=claim['subject_id'],holder_keys=claim['holder_ids'],related_keys=claim['related_ids'])
            _check(InterpretedClaim,raw,'interpretation/claims/'+claim['id'])
            if (claim['subject_id'] is not None and claim['subject_id'] not in ids) or set(claim['holder_ids'])-people or set(claim['related_ids'])-ids:
                raise ValueError('generation/constraints: неизвестная ссылка')
        if sum(e.get('tier')=='protagonist' for e in payload['entities'])>1:raise ValueError('generation/constraints: выбери одного главного героя')
        if any(not isinstance(e['name'],str) or not e['name'].strip() for e in payload['entities']):raise ValueError('generation/constraints: имя не должно быть пустым')
        if 'creation' in payload:payload['creation']=_check(CreationSettings,payload['creation'],'creation').model_dump()
        # A prose/holder/time revision must not keep a now potentially obsolete
        # executable binding silently. Require one explicit atomic claim edit.
        for old,new in zip(cp['artifact']['claims'],payload['claims']):
            semantic=('description','value','time_scope','holder_ids','related_ids','subject_id')
            if old.get('rules') and any(old.get(k)!=new.get(k) for k in semantic) and old['rules']==new.get('rules'):
                raise ValueError('generation/constraints/'+old['id']+': пересмотри запись ограничения вместе с её проверками; прежние проверки нельзя молча применять к новому смыслу')
        payload['constraint_revision']+=1
        payload['blocking_ids']=[c['id'] for c in payload['claims'] if c['blocking']]
        payload['fixed_claim_ids']=[c['id'] for c in payload['claims'] if c['classification'] in ('explicit','prohibition')]
        payload.setdefault('amendments',[]).append(dict(revision=payload['constraint_revision'],path=path,value=deepcopy(value),origin='author'))
        if 'scopes' in payload:
            from backend.services.world_interpretation import scoped_plan
            scoped_plan(payload)
        locks=[]
    else:
        plan=repo.generation_resources(jid,['interpretation'])['interpretation']
        registry=repo.generation_resources(jid,['registry'])['registry'] if stage!='setting' else payload['registry']
        if stage=='setting':
            if operation=='patch' and parts[:2]!=['setting','campaign']:raise ValueError('generation/edit: состав мира меняется в интерпретации')
            payload['setting']=stages.validate('setting',payload['setting'])
            retained={e.get('existing_id') for e in cp['artifact']['setting']['entities']}
            protected=[r for r in cp['artifact']['registry'] if r['id'] in retained]
            if stages.allocate_entities(payload['setting'],plan,wid,protected)!=payload['registry']:raise ValueError('generation/edit: состав изменён')
        elif stage=='characters':payload=validate_character_batch(payload,list(cp['artifact']['characters']),registry)
        else:payload=stages.validate(stage,payload)
        validate_stage_facts(stage,payload['setting'] if stage=='setting' else payload,plan)
        if operation=='patch':
            sections={'places':{'location','organization'},'characters':{'character','appearance','personality'},'setting':{'setting'},'life':{'family','relationship','residence','role','possession','contact','commitment'},'lore':{'fact','knowledge','history'},'opening':{'opening','commitment'}}[stage]
            # A source family constraint must not prevent editing an unrelated
            # possession or role. Exact bindings still run for the whole stage;
            # final semantic reviews revalidate affected accepted artifacts.
            collection_sections={'objective_relations':{'family'},'relationships':{'relationship'},
                'residences':{'residence'},'roles':{'role'},'possessions':{'possession'},
                'contacts':{'contact'},'facts':{'fact'},'knowledge':{'knowledge'},
                'initial_history':{'history'},'threads':{'fact'},'scheduled_events':{'commitment'}}
            if parts and parts[0] in collection_sections:
                sections=collection_sections[parts[0]]
            subject=parts[1] if stage in ('characters','places') and len(parts)>1 else None
            for claim in plan['claims']:
                if not any(rule['stage']==stage for rule in claim.get('rules',[])) and claim['classification'] in ('explicit','prohibition') and claim['section'] in sections and (stage not in ('characters','places') or claim['subject_id'] in (None,subject)):
                    raise ValueError('generation/constraints/'+claim['id']+': сначала явно пересмотри исходное ограничение')
        if operation=='patch':
            # Once all parts exist, also check the edit against Runtime's own
            # cross-reference/invariant layer before writing a checkpoint.
            units=repo.generation_status(jid)['units']
            parts_by_stage={}
            batches=[]
            for row in units:
                if row['stage'] in ('interpret','assembly'):continue
                stored=payload if row['unit_id']==unit else repo.inspect_generation_checkpoint(jid,row['unit_id'],True).get('artifact')
                if stored is None:continue
                if row['stage']=='characters':batches.append(stored)
                else:parts_by_stage[row['stage']]=stored
            if all(key in parts_by_stage for key in ('setting','places','life','lore','opening')) and sum(len(b['characters']) for b in batches)==sum(r['kind']=='character' for r in registry):
                stages.compose(parts_by_stage['setting']['setting'],parts_by_stage['setting']['registry'],parts_by_stage['places'],batches,parts_by_stage['life'],parts_by_stage['lore'],parts_by_stage['opening'],plan)
        locks=[path] if operation=='patch' else []
    return repo.revise_generation_checkpoint(jid,unit,payload,revision,artifact_version,locks,preview=preview,
        regenerate=operation=='regenerate',unlock_paths=[path] if operation=='unlock' else [])
