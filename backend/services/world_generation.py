"""Checkpointed stage execution using Preparation's provider/accounting/lease."""
import json
import threading

from backend.services import initial_world_stages as stages
from backend.services import generation_ties
from backend.services.generation_contracts import request_schema, HINTS
from backend.services.generated_characters import normalize_cards
from backend.services import world_interpretation as interpretation
from backend.services import world_blueprint as blueprint
from backend.services.generated_appearance import character_schema, INSTRUCTIONS as APPEARANCE_INSTRUCTIONS
from backend.services.initial_world_v2 import _check
from backend.services import generation_semantics as semantics
from backend.services.continuation import request_context
from backend.services.usage import tracked_stream
from backend.services.coordinator import model_lease
from llm import find_loaded_model
from backend.services.world_creation_settings import CreationSettings
from backend.services.generation_constraints import validate_character_facts, validate_stage_facts

PROMPT_VERSION = 'initial-world-stages-6'
LEGACY_RULES = '''Generate only the requested typed partial payload, never an entire world.
Use the user's language. Explicit user facts and prohibitions outrank conventions.
Genre tendencies never mandate romance, conflict, births or deaths. Family saga
allows long/multigenerational horizons without predetermining any life events.
Cast counts are targets, not mandatory fillers; premise constraints take priority.
Named NPCs count toward targets and remain protected even above target. Core NPCs
need differentiated voice, values, motives, appearance and grounded background;
secondary NPCs need concise distinct traits, not invented full biographies.
Reconcile structured selections with source facts. Material conflicts must become
blocking ambiguities during interpretation, not silent overrides. Geography is
optional; distinguish selected/generated geography from explicit source facts.
Never rename, omit, duplicate or reidentify assigned entities. Fill only permitted
unspecified details. Do not infer birthdays from ages, residence from presence,
children/pregnancy from marriage, citizenship/country from names, or consent from
someone else's plans. Adoption is not biological kinship. Plans for marriage are
intentions, not marriage or engagement. Separate affection from romance.
Knowledge has explicit holders and temporal provenance; never spread secrets to
everyone. Private biography must not appear in public_description or opening
prose without an established POV knowledge path. No mandatory secrets or trauma.
Preserve exact initial day/time/place/activity. Do not decide the protagonist's
next action, speech, goals or feelings. Use the supplied canonical IDs unchanged.
Use unknown/null/empty optional fields when evidence is absent. Do not invent
historical events or exact dates to satisfy schema. Later stages cannot rewrite
accepted earlier records. Return one JSON object matching the supplied schema.
'''


RULES = """Create a rich, coherent playable world from the author's idea and settings.
You are a creative coauthor, not a literal parser. Develop missing surroundings,
organizations, locations, biographies, relationships, distinctive voices, habits
and motives. Major NPCs need depth; secondary NPCs need enough to act independently;
incidental figures need only useful detail. Optional fields may remain empty.
Respect explicit circumstances and accepted author edits. Mark uncertainty honestly.
Genres, geography, cast scale, expressiveness, pacing and risk guide possibilities,
not mandatory drama. Create circumstances and opportunities, never a future script.
Do not decide the controlled protagonist's next actions, speech, consent or feelings.
Assign that actor goals, intentions or commitments only when explicitly supplied
by the author; creative NPC motivations never grant control over the protagonist.
Adoption is not biology; affection is not romance; plans are not completed events.
Knowledge requires specific holders and chronology. Never put private NPC secrets
in public descriptions or opening prose without a POV knowledge path. Preserve
explicit initial time and commitments. Do not invent exact dates from vague ages.
Use supplied canonical IDs; never duplicate assigned entities or rewrite accepted
records. Return only this stage's typed JSON, not a complete WorldState. Use the
user's language. Technical schema and Runtime invariants remain mandatory.
"""


class TransientProviderFailure(RuntimeError):
    """A definite HTTP rejection before any output; not a lost response."""


def _unit(uid,stage,inputs,outputs):
    return dict(id=uid,stage=stage,inputs=inputs,outputs=outputs)


def _claims(plan, sections, ids=None):
    if ids is not None and plan.get('version') == 2:
        # Blueprint notes group several circumstances under one section. An
        # actor's employment may be inside a relationship note; do not lose it.
        def targets(row): return {row['subject_id'], *row['related_ids']} - {None}
        return [row for row in plan['claims'] if targets(row) & set(ids) or
                (not targets(row) and (row['classification']=='prohibition' or row['section'] in sections))]
    return [row for row in plan['claims'] if (row['classification']=='prohibition' or row['section'] in sections) and
        (ids is None or not ({row['subject_id'],*row['related_ids']}-{None}) or row['subject_id'] in ids or set(row['related_ids']) & set(ids))]


def _people(batches):
    # Small presentation context, not all canonical fields/History for every NPC.
    return [dict(id=cid,name=part['cards'][cid]['name'],
        role=part['cards'][cid]['fields'].get('Роль',''),
        character='' if (actor.get('personality') or {}).get('items') else part['cards'][cid]['fields'].get('Характер',''),
        background=part['cards'][cid]['fields'].get('Биография',''),
        author_notes={k:v for k,v in part['cards'][cid]['fields'].items() if k.casefold() in ('секрет','секреты','тайна','тайны','secret','secrets')},
        life_status=actor.get('life_status','alive'),location_id=actor['location_id'],
        personality={key:{'field':item['field'],'text':item['text'],'revision':item['revision']}
            for key,item in (actor.get('personality') or {}).get('items',{}).items()},
        values={key:{'text':item['text'],'revision':item['revision']}
            for key,item in (actor.get('values') or {}).items() if item['status']=='active'},
        **{field:[{'id':item['id'],'text':item['text'],'status':item['status']} for item in actor.get(field,[])
                  if item['status'] in ('active','blocked')] for field in ('goals','intentions','obligations')})
        for part in map(normalize_cards,batches) for cid,actor in part['characters'].items()]


def generation_input(config, idea=''):
    """Capture source/settings/prompts before dispatch, without provider I/O."""
    brief=config['_draft_input']
    if config.get('_use_idea'):
        if not idea.strip(): raise ValueError('Сначала создай сценарий в режиме Сценариста.')
        brief+='\n\n'+idea.strip()
    return {'brief':brief,'constraint_revision':1,'creation':config.get('_creation',{}),
        'prompt':{'version':PROMPT_VERSION,'rules':(RULES + APPEARANCE_INSTRUCTIONS) if PROMPT_VERSION=='initial-world-stages-6' else LEGACY_RULES,
            'interpretation':(blueprint if PROMPT_VERSION=='initial-world-stages-6' else interpretation).messages('')[0]['content'],
            'semantic_review':semantics.ADVISORY_INSTRUCTIONS if PROMPT_VERSION=='initial-world-stages-6' else semantics.INSTRUCTIONS,
            'schemas':{name:(character_schema(model) if name=='characters' else model.model_json_schema()) for name,model in {**stages.STAGES,**(stages.CREATIVE_PARTS if PROMPT_VERSION=='initial-world-stages-6' else {}),'review':semantics.AdvisoryReview if PROMPT_VERSION=='initial-world-stages-6' else semantics.Review}.items()}}}


def run(preparation,jid,config,api_key,handle,loaded,stream_fn):
    repo=preparation.repo
    job=repo.preparation_job(jid)
    inputs=repo.generation_resources(jid,['brief','constraint_revision','prompt','creation'])
    brief=inputs['brief']
    scoped=inputs['prompt']['version'] in ('initial-world-stages-2','initial-world-stages-3','initial-world-stages-4','initial-world-stages-5','initial-world-stages-6')
    creative=inputs['prompt']['version']=='initial-world-stages-6'
    source=lambda stage:'scope:'+stage if scoped else 'interpretation'
    token=repo.claim_generation(jid)
    if not token: return
    stopped=threading.Event()
    def heartbeat():
        while not stopped.wait(20):
            try: repo.renew_generation(jid,token)
            except ValueError:
                handle.cancel.set()
                if handle.stream:
                    try: handle.stream.close()
                    except Exception: pass
                return
    renewer=threading.Thread(target=heartbeat,daemon=True);renewer.start()
    context=config['context_length']
    if loaded: context=min(context,int(loaded.get('config',{}).get('context_length') or context))
    def opened(stream):
        handle.stream=stream
        if handle.cancel.is_set(): stream.close()
    last_error=''
    current_unit=None
    def request(stage,context_data,model):
        system=inputs['prompt']['interpretation'] if stage=='interpret' else inputs['prompt']['rules']+'\nJSON Schema:\n'+json.dumps(request_schema(stage,inputs['prompt']['schemas'][stage],context_data),ensure_ascii=False,separators=(',',':'))
        if stage=='review':system=inputs['prompt']['semantic_review']+'\nJSON Schema:\n'+json.dumps(inputs['prompt']['schemas']['review'],ensure_ascii=False)
        system += '\n' + HINTS.get(stage, '')
        context_data={**context_data,'creation_settings':inputs['creation']}
        if stage not in ('interpret','review'):context_data['source_rules']=[row for row in plan['claims'] if any(rule['stage']==stage for rule in row.get('rules',[])) and (stage!='characters' or not ({row['subject_id'],*row['related_ids']}-{None}) or ({row['subject_id'],*row['related_ids']} & set(context_data['assigned_ids'])))]
        locks=repo.generation_field_locks(jid,current_unit)
        if locks: context_data['accepted_field_locks']=locks
        if last_error: context_data={**context_data,'repair_error':last_error,'repair_scope':'Only this stage; preserve all previously accepted inputs.'}
        request=[dict(role='system',content=system+'\nStage: '+stage),
                 dict(role='user',content=json.dumps(context_data,ensure_ascii=False))]
        # Keep the durable executor lease/heartbeat while waiting for the shared
        # local model. The process-local scheduler is not the job owner.
        pieces=[]
        try:
            with model_lease(config['provider']):
                if handle.cancel.is_set(): raise InterruptedError('Generation cancelled')
                actual_context=context
                if config['provider']=='local':
                    current=find_loaded_model(config['model'])
                    if not current: raise ValueError('Сначала загрузи выбранную локальную модель.')
                    actual_context=min(context,int(current.get('config',{}).get('context_length') or context))
                messages,limit=request_context(request,'',actual_context,config['max_tokens'],format_hint='json')
                pieces=[]
                for chunk in tracked_stream(repo,stream_fn,jid,'initial_'+stage,config,messages,
                        model=config['model'],provider=config['provider'],api_key=api_key,
                        temperature=config['temperature'],max_tokens=limit,require_complete=True,
                        cancel_event=handle.cancel,on_stream=opened,
                        **({'response_format':{'type':'json_object'}} if config['provider']=='deepseek' else {})):
                    if handle.cancel.is_set(): raise InterruptedError('Generation cancelled')
                    pieces.append(chunk)
                if handle.cancel.is_set(): raise InterruptedError('Generation cancelled')
        except InterruptedError:
            raise
        except Exception as exc:
            # Provider exceptions may echo prompt material or request headers.
            # Keep public job diagnostics bounded; usage owns request outcomes.
            from llm import OutputLimitReached
            if isinstance(exc, OutputLimitReached):
                logs=repo.request_log(job_id=jid)
                measured=next((r for r in logs if r['stage']=='initial_'+stage),{})
                repo.record_generation_diagnostic(jid,token,current_unit,dict(
                    category='output_limit',max_tokens=measured.get('max_tokens'),
                    input_tokens=measured.get('input_tokens'),output_tokens=measured.get('output_tokens'),
                    finish_reason=measured.get('finish_reason'),
                    partial_json_bytes=len(''.join(pieces).encode('utf-8')),
                    expected_json_bytes=None,assigned_pair_count=len(context_data.get('assigned_pairs',[]))))
            status=getattr(getattr(exc,'response',None),'status_code',None)
            if status in (429,503) and not pieces:
                raise TransientProviderFailure('stage/'+stage+': provider temporarily rejected request') from exc
            code=' HTTP '+str(status) if isinstance(status,int) else ' '+type(exc).__name__
            raise RuntimeError('stage/'+stage+': provider request failed ('+code.strip()+'); inspect usage and retry explicitly.') from exc
        try: return json.loads(''.join(pieces))
        except ValueError as exc: raise ValueError('stage/'+stage+': invalid JSON') from exc
    def execute(unit, producer, validate):
        nonlocal last_error,current_unit
        current_unit=unit
        if handle.cancel.is_set() or not repo.generation_boundary(jid,token): raise InterruptedError('Generation paused or cancelled')
        status=next(row for row in repo.generation_status(jid)['units'] if row['unit_id']==unit)
        if status['status']=='completed': return
        # Bounded schema retries are local to this unit. Provider exceptions are
        # surfaced; uncertain requests are never replayed automatically.
        for retry in range(2):
            if not repo.generation_boundary(jid,token): raise InterruptedError('Generation paused')
            repo.begin_generation_unit(jid,token,unit)
            try:
                payload=validate(producer())
                if status['stage'] not in ('interpret','assembly'):
                    validate_stage_facts(status['stage'],payload['setting'] if unit=='setting' else payload,plan)
                repo.commit_generation_unit(jid,token,unit,payload)
            except TransientProviderFailure as exc:
                repo.fail_generation_unit(jid,token,unit,str(exc))
                if retry==0:
                    if handle.cancel.wait(1):raise InterruptedError('Generation cancelled')
                    continue
                raise
            except semantics.SemanticConflict as exc:
                repo.record_generation_diagnostic(jid,token,unit,exc.report)
                repo.fail_generation_unit(jid,token,unit,str(exc))
                raise
            except ValueError as exc:
                last_error=str(exc)
                repo.fail_generation_unit(jid,token,unit,last_error)
                if retry==0: continue
                raise
            except Exception as exc:
                repo.fail_generation_unit(jid,token,unit,str(exc) if isinstance(exc,RuntimeError) and str(exc).startswith('stage/') else 'Provider request failed; inspect usage before retry.')
                raise
            last_error=''
            return
    try:
        if config.get('_review_only'):
            saved=repo.generation_resources(jid,['interpretation','author_draft'])
            plan=saved['interpretation'];assembled=saved['author_draft']
            inputs['creation']=plan.get('creation',inputs['creation'])
            for group in semantics.groups(plan):
                review_context=semantics.context(assembled,group)
                execute(group['id'],lambda:request('review',review_context,semantics.Review),lambda raw:semantics.validate_advisory(raw,review_context) if creative else semantics.validate(raw,review_context))
            execute('assembly',lambda:assembled,lambda value:value)
            if repo.generation_boundary(jid,token):repo.publish_generation_draft(jid,token,assembled)
            return
        chunks=blueprint.fragments(brief) if creative else []
        chunk_keys=['brief_part:'+str(i) for i in range(len(chunks))]
        repo.plan_generation_units(jid,token,[
            *[_unit('interpret_'+str(i),'interpret',['brief','prompt',*chunk_keys[:i]],{key:''}) for i,key in enumerate(chunk_keys)],
            _unit('interpret','interpret',['brief','constraint_revision','creation','prompt',*chunk_keys],{'interpretation':''}),
            _unit('setting','setting',[source('setting'),'prompt'],{'setting':'/setting','registry':'/registry'}),
            _unit('places','places',[source('places'),'setting','registry','prompt'],{'places':''}),
        ])
        if creative:
            accepted=[]
            for i,chunk in enumerate(chunks):
                known={e['key']:e for part in accepted for e in part['entities']}
                def validate_fragment(raw):
                    part=_check(blueprint.Blueprint,raw,'blueprint').model_dump()
                    blueprint.accept_parts([*accepted,part],brief,job['workspace_id'],inputs['constraint_revision'])
                    return part
                execute('interpret_'+str(i),lambda:request('interpret',{'brief':chunk,'known_entities':list(known.values())},blueprint.Blueprint),validate_fragment)
                accepted.append(repo.generation_resources(jid,[chunk_keys[i]])[chunk_keys[i]])
            execute('interpret',lambda:blueprint.accept_parts(accepted,brief,job['workspace_id'],inputs['constraint_revision']),
                lambda value:interpretation.scoped_plan({**value,'creation':inputs['creation']}))
        else:
            execute('interpret',lambda:request('interpret',{'brief':brief},interpretation.Interpretation),
                lambda raw:(interpretation.scoped_plan if scoped else lambda value:value)({**interpretation.accept(raw,brief,job['workspace_id'],inputs['constraint_revision']),'creation':inputs['creation']}))
        plan=repo.generation_resources(jid,['interpretation'])['interpretation']
        if 'creation' in plan: inputs['creation']=plan['creation']
        if plan['blocking_ids']:
            repo.release_generation(jid,token,'paused','interpretation: resolve material ambiguities before continuing')
            return
        protected=[]
        replannable=inputs['prompt']['version'] in ('initial-world-stages-4','initial-world-stages-5','initial-world-stages-6')
        semantic_groups=semantics.groups(plan) if inputs['prompt']['version'] in ('initial-world-stages-5','initial-world-stages-6') else []
        if replannable:
            protected_ids=set()
            for old_unit in repo.generation_status(jid)['units']:
                if old_unit['stage']!='characters':continue
                for pointer,value in repo.generation_field_locks(jid,old_unit['unit_id']).items():
                    bits=pointer.split('/')[1:]
                    if len(bits)>1:protected_ids.add(bits[1].replace('~1','/').replace('~0','~'))
                    elif isinstance(value,dict):protected_ids.update(value)
            if protected_ids:
                old_setting=repo.inspect_generation_checkpoint(jid,'setting',True).get('artifact') or {}
                protected=[r for r in old_setting.get('registry',[]) if r['id'] in protected_ids]
        execute('setting',lambda:request('setting',{'protected_entities':protected,'interpretation':(plan['scopes']['setting'] if scoped else plan),
            'cast_targets':CreationSettings.model_validate(inputs['creation']).cast_targets(plan['entities'])},stages.SettingPart),
            lambda raw:dict(setting=stages.validate('setting',raw),registry=stages.allocate_entities(raw,plan,job['workspace_id'],protected)))
        setting=repo.generation_resources(jid,['setting','registry'])
        registry=setting['registry']
        execute('places',lambda:request('places',dict(registry=registry,campaign=setting['setting']['campaign'],
            constraints=_claims(plan,{'setting','location','organization','residence','opening'})),stages.PlacesPart),
            lambda raw:stages.validate_places(raw,registry))
        places=repo.generation_resources(jid,['places'])['places']
        batches=stages.character_batches(registry)
        batch_keys=['batch:'+batch['id'] for batch in batches]
        review_inputs={'setting':['setting'],'places':['places','lore'],'characters':batch_keys,'life':['life','lore'],'lore':['life','lore'],'opening':['life','lore','opening',*batch_keys]}
        tie_batches = generation_ties.batches(registry) if creative else []
        existing_units = repo.generation_status(jid)['units']
        old_ties = next((u for u in existing_units if u['unit_id']=='life_ties'), None)
        # Published/author-edited aggregates keep their captured contract. Failed
        # units with no accepted artifact can be subdivided after explicit resume.
        if len(tie_batches) <= 1 or (old_ties and not any(u['unit_id'].startswith('life_ties_') for u in existing_units)
                and repo.inspect_generation_checkpoint(jid,'life_ties',True).get('artifact') is not None):
            tie_batches = []
        tie_inputs = [source('life'),'registry','places',*batch_keys,'prompt']
        tie_keys = ['ties:'+b['id'] for b in tie_batches]
        if tie_batches and old_ties:
            repo.prepare_ties_subdivision(jid, token)
        planned_units=[
            *[_unit(batch['id'],'characters',([source('character_global'),*['scope:character_'+cid for cid in batch['character_ids'] if 'character_'+cid in plan['scopes']]] if scoped else ['interpretation'])+['setting','registry','places','prompt'],{'batch:'+batch['id']:''}) for batch in batches],
            *[_unit(b['id'],'life',[source('life'),'registry','prompt',
                *['batch:'+actors['id'] for actors in batches
                  if set(actors['character_ids']) & {cid for pair in b['pairs'] for cid in pair}]],
                {'ties:'+b['id']:''}) for b in tie_batches],
            *([_unit('life_ties','life',tie_inputs+tie_keys,{'ties':''})] if creative else []),
            _unit('life','life',[source('life'),'registry','places',*batch_keys,'prompt',*(['ties'] if creative else [])],{'life':''}),
            *([_unit('lore_background','lore',[source('lore'),'registry','life',*batch_keys,'prompt'],{'background':''})] if creative else []),
            _unit('lore','lore',[source('lore'),'registry','life',*batch_keys,'prompt',*(['background'] if creative else [])],{'lore':''}),
            _unit('opening','opening',[source('opening'),'registry','places','life','lore',*batch_keys,'prompt'],{'opening':''}),
            *[_unit(group['id'],'assembly',['scope:review_'+group['stage'],'prompt',*review_inputs[group['stage']]],{group['id']:''}) for group in semantic_groups],
            _unit('assembly','assembly',['interpretation','setting','registry','places','life','lore','opening',*batch_keys,*[g['id'] for g in semantic_groups]],{'assembled':''}),
        ]
        if replannable:repo.reconcile_generation_plan(jid,token,planned_units,batches)
        else:repo.plan_generation_units(jid,token,planned_units)
        for batch in batches:
            ids=batch['character_ids']
            execute(batch['id'],lambda:request('characters',dict(assigned_ids=ids,
                registry=registry,locations=places['locations'],campaign=setting['setting']['campaign'],
                constraints=_claims(plan,{'character','appearance','personality','role','history','family','opening'} | ({'commitment'} if inputs['prompt']['version'] in ('initial-world-stages-3','initial-world-stages-4','initial-world-stages-5','initial-world-stages-6') else set()),ids)),stages.CharactersPart),
                lambda raw:validate_character_facts(stages.validate_character_batch(raw,ids,registry),plan))
        parts=list(repo.generation_resources(jid,batch_keys).values())
        people=_people(parts)
        life_context=dict(registry=registry,people=people,places=places,
            constraints=_claims(plan,{'relationship','family','residence','role','possession','contact','commitment'}))
        if creative:
            for tie_batch in tie_batches:
                execute(tie_batch['id'],
                    lambda:request('ties',generation_ties.context(life_context,tie_batch),stages.TiesPart),
                    lambda raw:generation_ties.validate(raw,registry,tie_batch))
            execute('life_ties',
                (lambda:generation_ties.combine(repo.generation_resources(jid,tie_keys).values(),registry)) if tie_batches
                else (lambda:request('ties',life_context,stages.TiesPart)),
                lambda raw:stages.validate_ties(raw,registry))
            ties=repo.generation_resources(jid,['ties'])['ties']
            execute('life',lambda:{**ties,**_check(stages.CircumstancesPart,request('circumstances',{**life_context,'accepted_ties':ties},stages.CircumstancesPart),'circumstances').model_dump()},lambda raw:stages.validate('life',raw))
        else:
            execute('life',lambda:request('life',life_context,stages.LifePart),lambda raw:stages.validate('life',raw))
        life=repo.generation_resources(jid,['life'])['life']
        # Life already depends on places, so edits invalidate lore transitively.
        # Include accepted profiles rather than asking lore to reinvent businesses.
        lore_context=dict(registry=registry,people=people,places=places,relations=life['objective_relations'],
            constraints=_claims(plan,{'fact','knowledge','history','family','commitment','organization','location'}))
        if creative:
            execute('lore_background',lambda:request('background',lore_context,stages.BackgroundPart),
                lambda raw:{k:v for k,v in stages.validate('lore',_check(stages.BackgroundPart,raw,'background').model_dump()).items() if k in stages.BackgroundPart.model_fields})
            background=repo.generation_resources(jid,['background'])['background']
            execute('lore',lambda:{**background,**_check(stages.KnowledgePart,request('knowledge',{**lore_context,'accepted_background':background},stages.KnowledgePart),'knowledge').model_dump()},lambda raw:stages.validate('lore',raw))
        else:
            execute('lore',lambda:request('lore',lore_context,stages.LorePart),lambda raw:stages.validate('lore',raw))
        lore=repo.generation_resources(jid,['lore'])['lore']
        execute('opening',lambda:request('opening',dict(registry=registry,people=people,places=places,
            facts=lore['facts'],knowledge=lore['knowledge'],constraints=_claims(plan,{'opening','setting','knowledge','commitment'})),stages.OpeningPart),
            lambda raw:stages.validate_opening(raw,people))
        opening=repo.generation_resources(jid,['opening'])['opening']
        assembled=stages.compose(setting['setting'],registry,places,parts,life,lore,opening,plan,creation=inputs['creation'])
        for group in semantic_groups:
            review_context=semantics.context(assembled,group)
            execute(group['id'],lambda:request('review',review_context,semantics.Review),lambda raw:semantics.validate_advisory(raw,review_context) if creative else semantics.validate(raw,review_context))
        execute('assembly',lambda:assembled,lambda value:value)
        if repo.generation_boundary(jid,token):
            repo.publish_generation_draft(jid,token,repo.generation_resources(jid,['assembled'])['assembled'])
    except InterruptedError:
        pass
    except Exception as exc:
        repo.release_generation(jid,token,'paused' if isinstance(exc,semantics.SemanticConflict) or str(exc).startswith('generation/plan/locks') else 'failed',str(exc))
    finally:
        stopped.set();renewer.join(timeout=1)
        repo.release_generation(jid,token)
