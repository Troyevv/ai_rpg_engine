"""Draft authoring over canonical Character, never a second playable actor model."""
from copy import deepcopy
from typing import Literal
from pydantic import Field
from backend.runtime_v3.models import (StrictModel, Character, Location, Organization,
    ObjectiveRelation, Relationship, Fact, Knowledge, Residence, NarrativeRole,
    assert_world_state_v3_invariants)
from backend.services.world import CARD_FIELDS
from backend.runtime_v3.milestones import stable_id


class CardDraft(StrictModel):
    name: str = Field(min_length=1,max_length=200)
    aliases: list[str] = Field(default_factory=list,max_length=32)
    fields: dict[str,str] = Field(default_factory=lambda:dict.fromkeys(CARD_FIELDS,''))


class KnowledgeDraft(StrictModel):
    fact_id: str
    source_actor_id: str | None = None
    source_event_id: str | None = None
    evidence: str = Field(min_length=1,max_length=2000)
    approved: bool = False


class SecretDraft(StrictModel):
    text: str = Field(min_length=1,max_length=4000)
    holders: list[str] = Field(default_factory=list,max_length=32)
    evidence: str = Field(min_length=1,max_length=2000)
    approved: bool = False


class Proposal(StrictModel):
    holders: list[str] = Field(default_factory=list,max_length=32)
    kind: Literal['location','organization','objective_relation','relationship','residence','role']
    value: dict
    evidence: str = Field(min_length=1,max_length=2000)
    approved: bool = False


class CharacterDraft(StrictModel):
    mode: Literal['newcomer','integrated'] = 'newcomer'
    card: CardDraft
    character: Character
    starting_scene: str = Field(min_length=1,max_length=8000)
    proposals: list[Proposal] = Field(default_factory=list,max_length=64)
    knowledge: list[KnowledgeDraft] = Field(default_factory=list,max_length=64)
    secrets: list[SecretDraft] = Field(default_factory=list,max_length=32)


def empty_draft(snapshot, operation_id):
    cid=stable_id('character',operation_id)
    return dict(mode='newcomer',card=dict(name='',aliases=[],fields=dict.fromkeys(CARD_FIELDS,'')),
        character=Character(id=cid,life_status='alive').model_dump(),starting_scene='',proposals=[],knowledge=[],secrets=[])


def creation_context(snapshot):
    """No biography, hidden NPC facts, prior actor memory or secrets in generation."""
    s=snapshot['world_state']
    public=[dict(id=f['id'],text=f['text'][:500]) for f in s['facts'].values() if f['visibility']=='public'][:24]
    return dict(time=s['meta']['world_time'],
        characters=[dict(id=c['id'],name=c.get('display_name') or c['id']) for c in s['characters'].values()][:64],
        locations=[dict(id=l['id'],name=l['name']) for l in s['locations'].values()][:64],
        organizations=[dict(id=o['id'],name=o['name']) for o in s['organizations'].values()][:32],public_facts=public)


def prepare(snapshot, payload, operation_id, history=None):
    """Validate everything on a private copy, then return one canonical candidate."""
    draft=CharacterDraft.model_validate(payload); result=deepcopy(snapshot); s=result['world_state']
    cid=stable_id('character',operation_id)
    if draft.character.id != cid: raise ValueError('character.id: используй ID текущего черновика.')
    if cid in s['characters']: raise ValueError('character.id: персонаж уже существует.')
    actor=draft.character.model_dump()
    if actor['life_status'] not in ('alive','unknown'): raise ValueError('character.life_status: новый ГГ должен быть жив.')
    # New identity cannot import another identity's evolution/provenance or portrait assets.
    from backend.runtime_v3.birth_identity import game_metadata
    if game_metadata(actor) or any(actor[k] for k in ('name_history','portraits','life_fact_id','parentage_complete_fact_id')):
        raise ValueError('character: история и ссылки на происхождение создаются Runtime.')
    actor.update(display_name=draft.card.name,situation=draft.starting_scene)
    s['characters'][cid]=actor
    result['character_cards'].append(dict(id=cid,is_player=False,**draft.card.model_dump()))
    from backend.runtime_v3.calendar import age_on,current_time,profile_of,date_parts
    if actor['birth_date']: date_parts(actor['birth_date'],profile_of(s))
    for profile in (actor.get('personality') or {},actor.get('appearance') or {}):
        if any(profile.get(key) for key in ('evidence','applied','seen_sources')):
            raise ValueError('character: новая биография не может импортировать историю развития.')
    for item in [*(actor.get('personality') or {}).get('items',{}).values(),*(actor.get('values') or {}).values()]:
        if any(item.get(key) for key in ('source_ids','fact_ids','witnesses')):
            raise ValueError('character: происхождение исходных качеств задаётся созданием, не чужими событиями.')
    for item in actor['appearance']['items'].values():
        if any(item.get(key) for key in ('condition_id','source_event_id','fact_id')):
            raise ValueError('character.appearance: нельзя заимствовать чужое происхождение внешности.')
    age=age_on(actor['birth_date'],current_time(s)['date'],profile_of(s))
    if age is not None and ((age<1 and actor['developmental_stage'] not in ('unknown','infant')) or (age<18 and actor['developmental_stage']=='adult')): raise ValueError('character.developmental_stage: противоречит дате рождения.')
    if age is not None and age<0: raise ValueError('character.birth_date: дата рождения в будущем.')
    models={'location':('locations',Location),'organization':('organizations',Organization),
        'objective_relation':('objective_relations',ObjectiveRelation),'relationship':('relationships',Relationship),
        'residence':('residences',Residence),'role':('roles',NarrativeRole)}
    from backend.runtime_v3.life import SYMMETRIC
    acquisitions=[]; events=[]
    for i,proposal in enumerate(draft.proposals):
        if not proposal.approved: raise ValueError(f'proposals.{i}: подтверди предложение отдельно или удали его.')
        section,model=models[proposal.kind]; value=deepcopy(proposal.value)
        if proposal.kind=='objective_relation':
            if cid not in (value.get('source_id'),value.get('target_id')): raise ValueError(f'proposals.{i}: связь должна относиться к новому персонажу.')
            if value.get('kind') in SYMMETRIC: value['source_id'],value['target_id']=sorted((value['source_id'],value['target_id']))
        if proposal.kind=='relationship' and value.get('source_id')!=cid:
            raise ValueError(f'proposals.{i}: нельзя назначать чувства существующему NPC.')
        if proposal.kind in ('residence','role') and value.get('actor_id')!=cid:
            raise ValueError(f'proposals.{i}: нельзя менять место жительства/роль существующего NPC.')
        record=model.model_validate(value).model_dump()
        # Authored onboarding describes established phases in this timeline.
        for field in ('since','until'):
            if record.get(field) is not None and record[field]>s['meta']['world_time']:
                raise ValueError(f'proposals.{i}.{field}: событие ещё не произошло.')
        from backend.runtime_v3.calendar import ordinal
        today=current_time(s)['date']
        for field in ('since_date','until_date'):
            if record.get(field):
                date_parts(record[field],profile_of(s))
                if today and ordinal(record[field],profile_of(s))>ordinal(today,profile_of(s)):
                    raise ValueError(f'proposals.{i}.{field}: дата в будущем.')
        if record.get('since_date') and record.get('until_date') and ordinal(record['until_date'],profile_of(s))<ordinal(record['since_date'],profile_of(s)):
            raise ValueError(f'proposals.{i}: окончание раньше начала.')
        key=record['source_id']+':'+record['target_id'] if proposal.kind=='relationship' else record['id']
        if key in s[section]: raise ValueError(f'proposals.{i}: существующая сущность неизменяема при создании.')
        if proposal.kind not in ('location','relationship'):
            record.update(evidence=proposal.evidence,source_turn=s['meta']['turn_id'])
        if set(proposal.holders)-s['characters'].keys():
            raise ValueError(f'proposals.{i}.holders: неизвестный носитель знания.')
        # A reviewed connection is a fact, but its audience is separately authored.
        # Reuse the existing Fact/Knowledge provenance consumed by social projections.
        fid=stable_id('onboarding-proposal',[operation_id,i])
        participants=list(dict.fromkeys([cid,*[record[k] for k in ('source_id','target_id','actor_id') if record.get(k)]]))
        s['facts'][fid]=Fact(id=fid,text=proposal.evidence,visibility='secret',character_ids=participants).model_dump()
        if 'fact_id' in record:
            if record.get('fact_id') or record.get('closure_fact_id'):
                raise ValueError(f'proposals.{i}: происхождение новой связи задаётся подтверждением.')
            record['fact_id']=fid
            if record.get('status')=='closed': record['closure_fact_id']=fid
        eid=stable_id('onboarding-proposal-event',[operation_id,i])
        events.append(dict(id=eid,text=proposal.evidence,participants=participants,witnesses=list(dict.fromkeys(proposal.holders)),
            fact_ids=[fid],medium='testimony',minute=s['meta']['world_time'],turn_id=s['meta']['turn_id'],player_observed=True))
        for holder in dict.fromkeys(proposal.holders):
            knowledge=Knowledge(actor_id=holder,fact_id=fid,source_event_id=eid,evidence=proposal.evidence,source_turn=s['meta']['turn_id']).model_dump()
            s['knowledge'][holder+':'+fid]=knowledge;acquisitions.append(knowledge)
        s[section][key]=record
    if actor['location_id'] not in s['locations']: raise ValueError('character.location_id: выбери место или подтверди создание нового.')
    event_id=stable_id('onboarding',operation_id)
    facts=[]
    existing_events={e['id']:e for e in (history or {}).get('events',[]) if isinstance(e,dict) and isinstance(e.get('id'),str)}
    for i,known in enumerate(draft.knowledge):
        fact=s['facts'].get(known.fact_id)
        if not known.approved or not fact: raise ValueError(f'knowledge.{i}: нужны существующий факт и явное подтверждение.')
        observer=snapshot['world_state']['camera'].get('pov_actor_id') or snapshot['world_state']['camera']['controlled_actor_id']
        if fact['visibility']=='secret' and snapshot['world_state']['knowledge'].get(str(observer)+':'+known.fact_id,{}).get('status')!='known':
            raise ValueError(f'knowledge.{i}: эта тайна недоступна текущему POV для авторизации.')
        if fact['visibility']=='secret' and (not known.source_actor_id or s['knowledge'].get(known.source_actor_id+':'+known.fact_id,{}).get('status')!='known'):
            raise ValueError(f'knowledge.{i}: тайна требует подтверждённого источника, который её знает.')
        if known.source_actor_id and known.source_actor_id not in s['characters']:
            raise ValueError(f'knowledge.{i}: неизвестный источник.')
        if known.source_event_id:
            event=existing_events.get(known.source_event_id)
            if not event or known.fact_id not in event.get('fact_ids',[]):
                raise ValueError(f'knowledge.{i}.source_event_id: событие не подтверждает этот факт.')
            if observer not in event.get('witnesses',[]) and not known.source_actor_id:
                raise ValueError(f'knowledge.{i}.source_event_id: укажи известный источник сведений о событии.')
        acquisition_id=stable_id('onboarding-knowledge',[operation_id,i])
        events.append(dict(id=acquisition_id,text=known.evidence,participants=[cid,*([known.source_actor_id] if known.source_actor_id else [])],witnesses=[cid],fact_ids=[known.fact_id],medium='testimony',minute=s['meta']['world_time'],turn_id=s['meta']['turn_id'],player_observed=True))
        record=Knowledge(actor_id=cid,fact_id=known.fact_id,source_event_id=acquisition_id,evidence=known.evidence,source_turn=s['meta']['turn_id']).model_dump()
        s['knowledge'][cid+':'+known.fact_id]=record;acquisitions.append(dict(record,origin_event_id=known.source_event_id));facts.append(known.fact_id)
    for i,secret in enumerate(draft.secrets):
        if not secret.approved: raise ValueError(f'secrets.{i}: подтверди собственную биографическую тайну.')
        if set(secret.holders)-s['characters'].keys(): raise ValueError(f'secrets.{i}: неизвестный носитель знания.')
        fid=stable_id('biography',[operation_id,i]);facts.append(fid)
        s['facts'][fid]=Fact(id=fid,text=secret.text,visibility='secret',character_ids=[cid]).model_dump()
        secret_event=stable_id('onboarding-secret',[operation_id,i])
        events.append(dict(id=secret_event,text=secret.evidence,participants=[cid],witnesses=list(dict.fromkeys(secret.holders)),fact_ids=[fid],medium='testimony',minute=s['meta']['world_time'],turn_id=s['meta']['turn_id'],player_observed=True))
        for holder in dict.fromkeys(secret.holders):
            record=Knowledge(actor_id=holder,fact_id=fid,source_event_id=secret_event,evidence=secret.evidence,source_turn=s['meta']['turn_id']).model_dump()
            s['knowledge'][holder+':'+fid]=record;acquisitions.append(record)
    from backend.runtime_v3.personality import initialize_profiles
    from backend.runtime_v3.appearance import initialize_profiles as initialize_appearance
    new_only=dict(world_state=s,character_cards=[result['character_cards'][-1]])
    initialize_profiles(new_only);initialize_appearance(new_only)
    result['world_state']=assert_world_state_v3_invariants(s)
    history=dict(state_changes=[dict(id=event_id,kind='character_creation',entity=cid,before=None,after=actor,
        minute=s['meta']['world_time'],turn_id=s['meta']['turn_id'],source='explicit_confirmation',evidence=draft.starting_scene)],
        knowledge_acquisitions=acquisitions,events=events)
    return result,cid,history


def editor_schema():
    """Reuse canonical field definitions for every typed onboarding proposal."""
    schema=CharacterDraft.model_json_schema()
    schemas={}
    for kind,model in (('location',Location),('organization',Organization),('objective_relation',ObjectiveRelation),
                       ('relationship',Relationship),('residence',Residence),('role',NarrativeRole)):
        value=model.model_json_schema();schema.setdefault('$defs',{}).update(value.pop('$defs',{}));schemas[kind]=value
    return schema,schemas


def editor_context(snapshot, history=None):
    """Explicit authoring choices can include secrets already known at the current POV.

    This catalog is not sent to generation: only user-selected draft knowledge is.
    """
    result=creation_context(snapshot);s=snapshot['world_state'];camera=s['camera']
    observer=camera.get('pov_actor_id') or camera['controlled_actor_id']
    known={k['fact_id'] for k in s['knowledge'].values() if k['actor_id']==observer and k['status']=='known'}
    result['events']=[dict(id=e['id'],text=e.get('text','')[:500]) for e in (history or {}).get('events',[])
        if isinstance(e,dict) and isinstance(e.get('id'),str) and observer in e.get('witnesses',[])][-64:]
    result['knowledge_facts']=[dict(id=fid,text=f['text'][:500]) for fid,f in s['facts'].items()
        if f['visibility']=='public' or fid in known][:128]
    return result
