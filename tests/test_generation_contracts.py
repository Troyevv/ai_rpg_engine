from copy import deepcopy
import pytest
from backend.services.generation_contracts import request_schema, HINTS
from backend.services.initial_world_stages import CharactersPart, PlacesPart, validate_places

REGISTRY=[dict(id='hero',name='Илья',kind='character'),dict(id='colleague',name='Вера',kind='character'),
          dict(id='lab',name='Лаборатория',kind='location'),dict(id='nii',name='НИИ',kind='organization')]


def test_character_request_exposes_only_assigned_output_identities():
    captured=CharactersPart.model_json_schema();before=deepcopy(captured)
    schema=request_schema('characters',captured,dict(registry=REGISTRY,assigned_ids=['colleague'],locations={'lab':{}}))
    for section in ('characters','cards'):
        field=schema['properties'][section]
        assert field['required']==['colleague'] and set(field['properties'])=={'colleague'}
        assert field['additionalProperties'] is False
        assert field['properties']['colleague']['allOf'][1]['properties']['id']=={'const':'colleague'}
    assert schema['$defs']['Character']['properties']['location_id']=={'enum':[None,'lab']}
    assert captured==before
    assert 'complete roster' in HINTS['setting']


def places():
    return dict(locations={'lab':dict(id='lab',name='Лаборатория')},organizations={'nii':dict(id='nii',name='НИИ')})


def test_places_contract_binds_names_ids_and_parent_references():
    schema=request_schema('places',PlacesPart.model_json_schema(),dict(registry=REGISTRY))
    assert schema['properties']['locations']['required']==['lab']
    assert schema['properties']['organizations']['required']==['nii']
    assert schema['$defs']['Location']['properties']['parent_id']=={'enum':[None,'lab']}
    assert validate_places(places(),REGISTRY)['locations']['lab']['id']=='lab'


@pytest.mark.parametrize('fault', ['extra','missing','rename','parent','organization_parent'])
def test_unplanned_or_broken_place_is_rejected_before_character_requests(fault):
    raw=places()
    if fault=='extra':raw['locations']['invented']=dict(id='invented',name='Кафе')
    elif fault=='missing':raw['locations']={}
    elif fault=='rename':raw['locations']['lab']['id']='planning_key'
    elif fault=='parent':raw['locations']['lab']['parent_id']='unknown'
    else:raw['parent_organizations']={'nii':'unknown'}
    with pytest.raises(ValueError,match='places/'):
        validate_places(raw,REGISTRY)


def test_organization_description_alias_preserves_existing_context_without_mutation():
    raw=places();raw['organizations']['nii'].update(context='История института.',description='Исследует транспорт.')
    before=deepcopy(raw)
    value=validate_places(raw,REGISTRY)
    assert value['organizations']['nii']['context']=='История института.\nИсследует транспорт.'
    assert raw==before and validate_places(value,REGISTRY)==value


def test_gregorian_redundant_month_table_is_removed_but_custom_or_invalid_is_not():
    from backend.services.initial_world_stages import validate
    standard=[31,28,31,30,31,30,31,31,30,31,30,31]
    raw=dict(world_time=540,camera={'mode':'observer'},calendar=dict(start_minute=540,start_weekday=1,profile=dict(system='gregorian',month_lengths=standard)))
    before=deepcopy(raw)
    result=validate('opening',raw)
    assert result['calendar']['profile']['month_lengths']==[] and raw==before
    assert result['world_time']==540
    raw['calendar']['profile']['month_lengths']=[30]*12
    with pytest.raises(ValueError):validate('opening',raw)
    raw['calendar']['profile']['system']='custom'
    assert validate('opening',raw)['calendar']['profile']['month_lengths']==[30]*12


def test_generated_card_labels_reach_personality_and_private_prose_becomes_unknown_secret():
    from backend.services.generated_characters import normalize_cards, private_card_facts
    raw={'characters':{'npc':{'id':'npc','personality':None}},'cards':{'npc':{'id':'npc','fields':{
        'характер':'Ироничная и собранная.','манера_речи':'Говорит быстро, с иронией.',
        'биография':'Работала в частной лаборатории.','секрет':'Подрабатывает репетитором.'}}}}
    before=deepcopy(raw)
    result=normalize_cards(raw)
    assert result['characters']['npc']['personality']['items']['communication']['text']=='Говорит быстро, с иронией.'
    assert result['cards']['npc']['fields']['Биография']=='Работала в частной лаборатории.'
    facts=private_card_facts(result['cards'])
    assert len(facts)==1
    fact=next(iter(facts.values()))
    assert fact['visibility']=='secret' and fact['text']=='Подрабатывает репетитором.'
    assert fact['character_ids']==['npc'] and 'секрет' not in result['cards']['npc']['fields']
    assert raw==before
    assert not private_card_facts(result['cards'])
    # Conversion creates no Knowledge holder, timeline or event.
    assert 'knowledge' not in result and 'source_event_id' not in fact


def test_opening_membership_is_derived_only_from_accepted_same_location():
    from backend.services.initial_world_stages import validate_opening
    people=[dict(id='hero',location_id='home',life_status='alive')]
    raw=dict(world_time=540,camera=dict(mode='actor',controlled_actor_id='hero',pov_actor_id='hero',location_id='home',present_character_ids=[]))
    before=deepcopy(raw)
    result=validate_opening(raw,people)
    assert result['camera']['present_character_ids']==['hero'] and raw==before
    assert validate_opening(result,people)==result
    raw['camera']['location_id']='work'
    with pytest.raises(ValueError,match='accepted controlled actor location'):validate_opening(raw,people)


def test_knowledge_keys_are_derived_without_changing_holders_or_claims():
    from backend.services.initial_world_stages import validate
    raw={'knowledge':{'friendly_label':dict(actor_id='a',fact_id='secret',status='suspected',evidence='Слышал намёк')}}
    before=deepcopy(raw);result=validate('lore',raw)
    assert set(result['knowledge'])=={'a:secret'}
    assert result['knowledge']['a:secret']['status']=='suspected'
    assert raw==before and validate('lore',result)==result
    raw['knowledge']['duplicate']=deepcopy(raw['knowledge']['friendly_label'])
    with pytest.raises(ValueError,match='duplicate actor/fact'):validate('lore',raw)


def test_relationship_keys_and_character_only_endpoints():
    from backend.services.initial_world_stages import validate_ties
    raw=dict(relationships={'friendly':dict(source_id='hero',target_id='colleague',context='Коллеги')})
    result=validate_ties(raw,REGISTRY)
    assert set(result['relationships'])=={'hero:colleague'}
    assert result['relationships']['hero:colleague']['dimensions']=={}
    raw['objective_relations']={'work':dict(id='work',kind='coworker',source_id='hero',target_id='nii')}
    with pytest.raises(ValueError,match='Character IDs'):validate_ties(raw,REGISTRY)


def test_actor_context_and_dependency_scope_include_mixed_section_notes():
    from backend.services.world_generation import _claims
    from backend.services.world_interpretation import scoped_plan
    from backend.services.world_blueprint import accept
    plan=accept({'entities':[dict(key='nina',kind='character',name='Нина'),dict(key='kontur',kind='organization',name='Контур')],
        'notes':[dict(section='relationship',subject_key='nina',related_keys=['kontur'],text='Нина — менеджер Контура; знает Веру со студенчества.')]},'Идея','namespace',1)
    plan=scoped_plan(plan);cid=next(r['id'] for r in plan['entities'] if r['kind']=='character')
    assert _claims(plan,{'character','personality'},[cid])==plan['claims']
    assert plan['scopes']['character_'+cid]['claims']==plan['claims']


def test_only_redundant_consistent_day_period_is_removed():
    from backend.services.initial_world_stages import validate
    raw=dict(world_time=540,camera={'mode':'observer'},scheduled_events={'meeting':dict(id='meeting',description='Встреча',temporal=dict(weekday=0,time='09:00',day_period='morning'))})
    before=deepcopy(raw);value=validate('opening',raw)
    assert value['scheduled_events']['meeting']['temporal']['time']=='09:00'
    assert value['scheduled_events']['meeting']['temporal']['day_period'] is None and raw==before
    raw['scheduled_events']['meeting']['temporal']['day_period']='night'
    with pytest.raises(ValueError):validate('opening',raw)


def test_planning_receives_unnamed_subsidiaries_before_roster_allocation():
    from backend.services.world_interpretation import scoped_plan
    from backend.services.world_blueprint import accept
    plan=accept({'entities':[dict(key='apex',kind='organization',name='Apex Group')],
        'notes':[dict(section='organization',subject_key='apex',text=
            'Группа включает банк, IT-компанию, страховую, строительную и юридическую компании.')]},
        'Идея','namespace',1)
    plan=scoped_plan(plan)
    assert plan['scopes']['setting']['claims']==plan['claims']
    assert plan['scopes']['places']['claims']==plan['claims']
    assert 'subsidiaries' in HINTS['setting']


def test_noncanonical_relationship_labels_remain_prose_not_invented_dimensions():
    from backend.services.initial_world_stages import validate_ties
    raw={'relationships':{'friendly':dict(source_id='hero',target_id='colleague',dimensions={'trust':.7,'warmth':.45,'familiarity':.1},context='Работают вместе.')}}
    before=deepcopy(raw);result=validate_ties(raw,REGISTRY)
    relation=result['relationships']['hero:colleague']
    assert relation['dimensions']=={'trust':.7}  # Never rescale or guess affection.
    assert 'warmth' in relation['context'] and '0.45' in relation['context'] and 'familiarity' in relation['context']
    assert raw==before and validate_ties(result,REGISTRY)==result
    raw['relationships']['friendly']['dimensions']['trust']=101
    with pytest.raises(ValueError,match='outside -100..100'):validate_ties(raw,REGISTRY)
    # Canonical range remains enforced at Runtime; request schema now exposes it.
    schema=request_schema('ties',__import__('backend.services.initial_world_stages',fromlist=['TiesPart']).TiesPart.model_json_schema(),dict(registry=REGISTRY))
    assert schema['$defs']['Relationship']['properties']['dimensions']['properties']['trust']['maximum']==100


def test_reciprocal_symmetric_rows_merge_only_same_phase_and_keep_both_descriptions():
    from backend.services.initial_world_stages import validate_ties
    raw={'objective_relations':{
        'one':dict(id='one',kind='coworker',source_id='hero',target_id='colleague',context='Общий проект.'),
        'two':dict(id='two',kind='coworker',source_id='colleague',target_id='hero',context='Работают в лаборатории.')}}
    before=deepcopy(raw);result=validate_ties(raw,REGISTRY)
    assert len(result['objective_relations'])==1
    row=next(iter(result['objective_relations'].values()))
    assert row['source_id']=='colleague' and row['target_id']=='hero'
    assert row['context']=='Общий проект.\nРаботают в лаборатории.'
    assert raw==before and validate_ties(result,REGISTRY)==result
    raw['objective_relations']['two']['since']=100
    with pytest.raises(ValueError,match='conflicting duplicate'):validate_ties(raw,REGISTRY)
    raw['objective_relations']['two']['since']=None
    for row in raw['objective_relations'].values():row['kind']='adoptive_parent'
    assert len(validate_ties(raw,REGISTRY)['objective_relations'])==2
