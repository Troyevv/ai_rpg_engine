"""Shared Character contract for initial promotion data and reviewed field patches.

Only explicit authored values enter the canonical model. IDs, provenance and
related entities remain owned by their existing Runtime domains.
"""
from copy import deepcopy
from pydantic import ValidationError
from backend.runtime_v3.models import Character, assert_world_state_v3_invariants
from backend.services.draft_initial import ACTOR_FIELDS, runtime_schema

TECHNICAL = {'birth_provenance','birth_date_provenance','name_history','life_fact_id','parentage_complete_fact_id'}
PROFILE_FIELDS = {'appearance','personality','values'}
INITIAL_FIELDS = tuple(f for f in ACTOR_FIELDS if f not in TECHNICAL) + ('situation','goals','intentions','obligations','emotion')
EDITABLE_FIELDS = tuple(f for f in INITIAL_FIELDS if f not in PROFILE_FIELDS)
LABELS = dict(biological_sex='Биологический пол',birth_date='Дата рождения',life_status='Жизненный статус',
    developmental_stage='Стадия развития',reproductive_capability='Репродуктивная способность',capabilities='Способности',
    identity_components='Состав имени',physical_state='Физическое состояние',situation='Текущая ситуация',
    goals='Цели',intentions='Намерения',obligations='Обязательства',emotion='Эмоции')


def initial_schema():
    schema=runtime_schema(Character)
    properties={k:schema['properties'][k] for k in INITIAL_FIELDS}
    # Initial authoring never imports lifecycle/provenance. Sending those large
    # histories in every extraction schema also starves ordinary repair context.
    for key in ('goals','intentions','obligations'):
        properties[key]=dict(type='array',items=dict(type='string'))
    def allow(node, keys):
        if 'anyOf' in node:
            for child in node['anyOf']:
                if child.get('type')=='object': allow(child,keys)
            return node
        node['properties']={k:v for k,v in node.get('properties',{}).items() if k in keys}
        if 'required' in node: node['required']=[k for k in node['required'] if k in keys]
        return node
    allow(properties['personality'], {'items'})
    personality=next(n for n in properties['personality']['anyOf'] if n.get('type')=='object')
    allow(personality['properties']['items']['additionalProperties'], {'field','text'})
    allow(properties['appearance'], {'items','legacy_text'})
    allow(properties['appearance']['properties']['items']['additionalProperties'], {'category','kind','text'})
    values=next(n for n in properties['values']['anyOf'] if n.get('type')=='object')
    allow(values['additionalProperties'], {'id','text','status'})
    return dict(type='object',additionalProperties=False,properties=properties,
        description='Только явно установленные начальные атрибуты нового NPC. Неизвестное пропускай или используй null/unknown. '
        'Не выводи пол из имени; не придумывай дату рождения. Источники, ревизии, IDs связей и история создаются Runtime. '
        'Отношения, роли, Knowledge и другие сущности передавай отдельными каноническими deltas.')


def initial_character(cid, name, payload):
    if not isinstance(payload,dict) or set(payload)-set(INITIAL_FIELDS): raise ValueError('Недопустимые начальные атрибуты Character.')
    payload=deepcopy(payload)
    # Unknown is represented by null in the canonical sex model, never inferred.
    if payload.get('biological_sex')=='unknown': payload['biological_sex']=None
    actor=Character.model_validate(dict(id=cid,display_name=name,**payload),strict=True).model_dump()
    for field in ('goals','intentions','obligations'):
        for item in actor[field]:
            if item['revision'] or item['source_event_id'] or item['dependencies'] or item['source_sequence'] is not None or item['status']!='active':
                raise ValueError('Начальная мотивация не может подменять историю или ссылки Runtime.')
    profile=actor.get('personality') or {}
    if any(profile.get(k) for k in ('evidence','applied','seen_sources')): raise ValueError('История личности создаётся Runtime.')
    for item in profile.get('items',{}).values():
        if item['revision'] or any(item.get(k) for k in ('source_ids','fact_ids','witnesses')): raise ValueError('Источники личности создаются Runtime.')
    appearance=actor['appearance']
    if appearance['applied']: raise ValueError('История внешности создаётся Runtime.')
    for item in appearance['items'].values():
        if item['revision'] != 1 or any(item.get(k) for k in ('condition_id','source_event_id','fact_id')): raise ValueError('Источники внешности создаются Runtime.')
    for item in (actor.get('values') or {}).values():
        if any(item.get(k) for k in ('revision','source_ids','fact_ids','witnesses')): raise ValueError('Источники ценностей создаются Runtime.')
    return actor


def validate_dates(state,cid):
    from backend.runtime_v3.calendar import date_parts,current_time,profile_of,age_on
    actor=state['characters'][cid];date=actor['birth_date']
    if date is None:return
    profile=profile_of(state);date_parts(date,profile)
    age=age_on(date,current_time(state)['date'],profile)
    if age is not None and (age<0 or age<1 and actor['developmental_stage'] not in ('unknown','infant') or age<18 and actor['developmental_stage']=='adult'):
        raise ValueError('Дата рождения противоречит времени мира или стадии развития.')


def editable_values(actor):
    from backend.runtime_v3.lifecycle import active_texts
    return {k:active_texts(actor[k]) if k in ('goals','intentions','obligations') else deepcopy(actor[k]) for k in EDITABLE_FIELDS}


def editor_schema():
    properties=initial_schema()['properties']
    for k in ('goals','intentions','obligations'):properties[k]=dict(type='array',items=dict(type='string'))
    return [dict(key=k,label=LABELS[k],schema=properties[k]) for k in EDITABLE_FIELDS]


def validate_patch(cid,patch):
    if not isinstance(patch,dict) or set(patch)-set(EDITABLE_FIELDS):raise ValueError('Недопустимое поле редактора Character.')
    for key in ('goals','intentions','obligations'):
        if key in patch and (not isinstance(patch[key],list) or any(not isinstance(v,str) or not v.strip() for v in patch[key])):
            raise ValueError(LABELS[key]+': удали пустые записи или заполни их.')
    initial_character(cid,cid,patch)
    return deepcopy(patch)


def apply_review(state,cid,patch,baseline):
    """Field-level CAS, lifecycle-preserving changes and full world validation."""
    patch=validate_patch(cid,patch)
    actor=state['characters'][cid];current=editable_values(actor)
    changed={k:v for k,v in patch.items() if v!=baseline[k]}
    if changed and state['camera']['controlled_actor_id']==cid:
        raise ValueError('Этот NPC сейчас управляется игроком. Верни исходного героя перед проверкой карточки.')
    conflicts=[LABELS[k] for k,v in changed.items() if current[k]!=baseline[k] and current[k]!=v]
    if conflicts:raise ValueError('После создания изменились: '+', '.join(conflicts)+'. Прими актуальные значения в разделе «Состояние» и повтори подтверждение.')
    if actor['life_status']=='dead' and changed.get('life_status','dead')!='dead':raise ValueError('Смерть нельзя отменить карточкой. Используй откат хода.')
    if 'birth_date' in changed and (actor['birth_provenance'] or actor['birth_date_provenance']):
        raise ValueError('Дата рождения закреплена историей. Используй откат исходного изменения.')
    from backend.runtime_v3.resolver import StateResolver
    from backend.runtime_v3.raw import RawTurnResult
    from backend.runtime_v3.life import apply_life
    lifecycle_fields={'life_status','capabilities','developmental_stage','reproductive_capability','identity_components'}
    lifecycle={k:v for k,v in changed.items() if k in lifecycle_fields}
    audit={}
    if lifecycle:
        resolver=StateResolver(state,'','',turn_id=state['meta']['turn_id'])
        raw=RawTurnResult.parse(dict(final_scene={},life_changes=[dict(id=cid,**lifecycle,
            evidence='Явная правка в редакторе проверки NPC.',assertion='established')]))
        apply_life(resolver,raw)
        state.clear();state.update(resolver.state)
        actor=state['characters'][cid]
        audit=resolver.history.to_dict()
    from backend.runtime_v3.lifecycle import replace_active
    for key,value in changed.items():
        if key in lifecycle_fields:continue
        if key in ('goals','intentions','obligations'):
            if actor['life_status']=='dead':raise ValueError('Мёртвому персонажу нельзя назначать мотивации.')
            actor[key]=replace_active(actor[key],value,cid,key,state['meta']['turn_id'])
        else:actor[key]=deepcopy(value)
    if 'emotion' in changed:actor['emotion_source_sequence']=state['meta']['turn_id']-1
    validate_dates(state,cid)
    state['characters'][cid]=Character.model_validate(actor,strict=True).model_dump()
    assert_world_state_v3_invariants(state)
    from backend.runtime_v3.remote import active_call
    from backend.runtime_v3.life import capabilities
    call=active_call(state,cid)
    if call and call['status']=='answered' and not all(capabilities(state,cid)[k] for k in ('can_act','can_speak','can_perceive')):
        raise ValueError('Сначала заверши активный звонок: новые способности делают разговор невозможным.')
    return audit
