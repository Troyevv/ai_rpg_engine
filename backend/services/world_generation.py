"""Checkpointed stage execution using Preparation's provider/accounting/lease."""
import json
import threading

from backend.services import initial_world_stages as stages
from backend.services import world_interpretation as interpretation
from backend.services.continuation import request_context
from backend.services.usage import tracked_stream
from backend.services.coordinator import model_lease
from llm import find_loaded_model
from backend.services.world_creation_settings import CreationSettings
from backend.services.generation_constraints import validate_character_facts, validate_stage_facts

PROMPT_VERSION = 'initial-world-stages-4'
RULES = '''Generate only the requested typed partial payload, never an entire world.
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


def _unit(uid,stage,inputs,outputs):
    return dict(id=uid,stage=stage,inputs=inputs,outputs=outputs)


def _claims(plan, sections, ids=None):
    return [row for row in plan['claims'] if (row['classification']=='prohibition' or row['section'] in sections) and
        (ids is None or not ({row['subject_id'],*row['related_ids']}-{None}) or row['subject_id'] in ids or set(row['related_ids']) & set(ids))]


def _people(batches):
    # Small presentation context, not all canonical fields/History for every NPC.
    return [dict(id=cid,name=part['cards'][cid]['name'],
        role=part['cards'][cid]['fields'].get('Роль',''),
        character='' if (actor.get('personality') or {}).get('items') else part['cards'][cid]['fields'].get('Характер',''),
        location_id=actor['location_id'],
        personality={key:{'field':item['field'],'text':item['text'],'revision':item['revision']}
            for key,item in (actor.get('personality') or {}).get('items',{}).items()},
        values={key:{'text':item['text'],'revision':item['revision']}
            for key,item in (actor.get('values') or {}).items() if item['status']=='active'},
        **{field:[{'id':item['id'],'text':item['text'],'status':item['status']} for item in actor.get(field,[])
                  if item['status'] in ('active','blocked')] for field in ('goals','intentions','obligations')})
        for part in batches for cid,actor in part['characters'].items()]


def generation_input(config, idea=''):
    """Capture source/settings/prompts before dispatch, without provider I/O."""
    brief=config['_draft_input']
    if config.get('_use_idea'):
        if not idea.strip(): raise ValueError('Сначала создай сценарий в режиме Сценариста.')
        brief+='\n\n'+idea.strip()
    return {'brief':brief,'constraint_revision':1,'creation':config.get('_creation',{}),
        'prompt':{'version':PROMPT_VERSION,'rules':RULES,
            'interpretation':interpretation.messages('')[0]['content'],
            'schemas':{name:model.model_json_schema() for name,model in stages.STAGES.items()}}}


def run(preparation,jid,config,api_key,handle,loaded,stream_fn):
    repo=preparation.repo
    job=repo.preparation_job(jid)
    inputs=repo.generation_resources(jid,['brief','constraint_revision','prompt','creation'])
    brief=inputs['brief']
    scoped=inputs['prompt']['version'] in ('initial-world-stages-2','initial-world-stages-3','initial-world-stages-4')
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
        system=inputs['prompt']['interpretation'] if stage=='interpret' else inputs['prompt']['rules']+'\nJSON Schema:\n'+json.dumps(inputs['prompt']['schemas'][stage],ensure_ascii=False,separators=(',',':'))
        context_data={**context_data,'creation_settings':inputs['creation']}
        if stage!='interpret':context_data['source_rules']=[row for row in plan['claims'] if any(rule['stage']==stage for rule in row.get('rules',[])) and (stage!='characters' or not ({row['subject_id'],*row['related_ids']}-{None}) or ({row['subject_id'],*row['related_ids']} & set(context_data['assigned_ids'])))]
        locks=repo.generation_field_locks(jid,current_unit)
        if locks: context_data['accepted_field_locks']=locks
        if last_error: context_data={**context_data,'repair_error':last_error,'repair_scope':'Only this stage; preserve all previously accepted inputs.'}
        request=[dict(role='system',content=system+'\nStage: '+stage),
                 dict(role='user',content=json.dumps(context_data,ensure_ascii=False))]
        # Keep the durable executor lease/heartbeat while waiting for the shared
        # local model. The process-local scheduler is not the job owner.
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
            raise RuntimeError('stage/'+stage+': provider request failed; inspect usage and retry explicitly.') from exc
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
                if unit not in ('interpret','assembly'):
                    validate_stage_facts(status['stage'],payload['setting'] if unit=='setting' else payload,plan)
                repo.commit_generation_unit(jid,token,unit,payload)
            except ValueError as exc:
                last_error=str(exc)
                repo.fail_generation_unit(jid,token,unit,last_error)
                if retry==0: continue
                raise
            except Exception:
                repo.fail_generation_unit(jid,token,unit,'Provider request failed; inspect usage before retry.')
                raise
            last_error=''
            return
    try:
        repo.plan_generation_units(jid,token,[
            _unit('interpret','interpret',['brief','constraint_revision','creation','prompt'],{'interpretation':''}),
            _unit('setting','setting',[source('setting'),'prompt'],{'setting':'/setting','registry':'/registry'}),
            _unit('places','places',[source('places'),'setting','registry','prompt'],{'places':''}),
        ])
        execute('interpret',lambda:request('interpret',{'brief':brief},interpretation.Interpretation),
            lambda raw:(interpretation.scoped_plan if scoped else lambda value:value)({**interpretation.accept(raw,brief,job['workspace_id'],inputs['constraint_revision']),'creation':inputs['creation']}))
        plan=repo.generation_resources(jid,['interpretation'])['interpretation']
        if 'creation' in plan: inputs['creation']=plan['creation']
        if plan['blocking_ids']:
            repo.release_generation(jid,token,'paused','interpretation: resolve material ambiguities before continuing')
            return
        protected=[]
        replannable=inputs['prompt']['version']=='initial-world-stages-4'
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
            lambda raw:stages.validate('places',raw))
        places=repo.generation_resources(jid,['places'])['places']
        batches=stages.character_batches(registry)
        batch_keys=['batch:'+batch['id'] for batch in batches]
        planned_units=[
            *[_unit(batch['id'],'characters',([source('character_global'),*['scope:character_'+cid for cid in batch['character_ids'] if 'character_'+cid in plan['scopes']]] if scoped else ['interpretation'])+['setting','registry','places','prompt'],{'batch:'+batch['id']:''}) for batch in batches],
            _unit('life','life',[source('life'),'registry','places',*batch_keys,'prompt'],{'life':''}),
            _unit('lore','lore',[source('lore'),'registry','life',*batch_keys,'prompt'],{'lore':''}),
            _unit('opening','opening',[source('opening'),'registry','places','life','lore',*batch_keys,'prompt'],{'opening':''}),
            _unit('assembly','assembly',['interpretation','setting','registry','places','life','lore','opening',*batch_keys],{'assembled':''}),
        ]
        if replannable:repo.reconcile_generation_plan(jid,token,planned_units,batches)
        else:repo.plan_generation_units(jid,token,planned_units)
        for batch in batches:
            ids=batch['character_ids']
            execute(batch['id'],lambda:request('characters',dict(assigned_ids=ids,
                registry=registry,locations=places['locations'],campaign=setting['setting']['campaign'],
                constraints=_claims(plan,{'character','appearance','personality','role','history','family','opening'} | ({'commitment'} if inputs['prompt']['version'] in ('initial-world-stages-3','initial-world-stages-4') else set()),ids)),stages.CharactersPart),
                lambda raw:validate_character_facts(stages.validate_character_batch(raw,ids,registry),plan))
        parts=list(repo.generation_resources(jid,batch_keys).values())
        people=_people(parts)
        execute('life',lambda:request('life',dict(registry=registry,people=people,places=places,
            constraints=_claims(plan,{'relationship','family','residence','role','possession','contact','commitment'})),stages.LifePart),
            lambda raw:stages.validate('life',raw))
        life=repo.generation_resources(jid,['life'])['life']
        execute('lore',lambda:request('lore',dict(registry=registry,people=people,
            relations=life['objective_relations'],constraints=_claims(plan,{'fact','knowledge','history','family','commitment'})),stages.LorePart),
            lambda raw:stages.validate('lore',raw))
        lore=repo.generation_resources(jid,['lore'])['lore']
        execute('opening',lambda:request('opening',dict(registry=registry,people=people,places=places,
            facts=lore['facts'],knowledge=lore['knowledge'],constraints=_claims(plan,{'opening','setting','knowledge','commitment'})),stages.OpeningPart),
            lambda raw:stages.validate('opening',raw))
        opening=repo.generation_resources(jid,['opening'])['opening']
        execute('assembly',lambda:stages.compose(setting['setting'],registry,places,parts,life,lore,opening,plan,creation=inputs['creation']),lambda value:value)
        if repo.generation_boundary(jid,token):
            repo.publish_generation_draft(jid,token,repo.generation_resources(jid,['assembled'])['assembled'])
    except InterruptedError:
        pass
    except Exception as exc:
        repo.release_generation(jid,token,'paused' if str(exc).startswith('generation/plan/locks') else 'failed',str(exc))
    finally:
        stopped.set();renewer.join(timeout=1)
        repo.release_generation(jid,token)
