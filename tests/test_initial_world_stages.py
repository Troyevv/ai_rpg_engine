from copy import deepcopy
import pytest
from backend.services import initial_world_stages as stages
from backend.services import draft_world
from backend.services.initial_world_v2 import normalize
from backend.services.world_interpretation import accept
from test_world_interpretation import interpretation, BRIEF


def parts():
    plan = accept(interpretation(), BRIEF, 'w', 1)
    setting = {'campaign': {'title': 'Семья'}, 'entities': [
        dict(key=str(index),kind=row['kind'],name=row['name'],existing_id=row['id'],tier=row['tier'])
        for index,row in enumerate(plan['entities'])] + [dict(key='road',kind='location',name='Дорога к станции')]}
    registry = stages.allocate_entities(setting, plan, 'w')
    anna, mira, road = [row['id'] for row in registry]
    batches = [{'characters': {row['id']:dict(id=row['id'],display_name=row['name'],
                 location_id=road if row['id']==mira else None,
                 situation='Идёт с сумками к станции' if row['id']==mira else '')
                 for row in registry if row['kind']=='character'},
                'cards': {row['id']:dict(id=row['id'],name=row['name'],fields={})
                 for row in registry if row['kind']=='character'}}]
    return dict(setting=setting, registry=registry,
        places={'locations':{road:dict(id=road,name='Дорога к станции')}}, batches=batches,
        life={'objective_relations': {'adoption':dict(id='adoption',kind='adoptive_parent',source_id=anna,target_id=mira)}},
        lore={'facts':{'adoption':dict(id='adoption',text='Мира удочерена',visibility='secret',character_ids=[anna,mira])},
              'knowledge':{cid+':adoption':dict(actor_id=cid,fact_id='adoption',status='known',evidence='Узнала вчера' if cid==mira else 'Знала ранее') for cid in (anna,mira)}},
        opening={'world_time':4*1440+360,'camera':dict(mode='actor',controlled_actor_id=mira,pov_actor_id=mira,
            location_id=road,present_character_ids=[mira],situation='Мира идёт с сумками к станции.')}, interpretation=plan)


def test_typed_stages_assemble_without_model_calls_and_preserve_start():
    inputs = parts(); original = deepcopy(inputs)
    snapshot = stages.compose(**inputs)
    state = snapshot['world_state']
    assert state['meta']['world_time'] == 6120
    assert state['camera']['situation'] == 'Мира идёт с сумками к станции.'
    assert [r['kind'] for r in state['objective_relations'].values()] == ['adoptive_parent']
    assert state['pregnancies'] == {}
    assert state['residences'] == {}
    assert all(c['birth_date'] is None for c in state['characters'].values())
    draft = draft_world.prepare(snapshot)
    assert not draft_world.validate(draft)['errors']
    assert normalize(draft).snapshot['world_state'] == state
    assert normalize(draft).snapshot['campaign']['initial_world'] == inputs['interpretation']
    assert inputs == original


@pytest.mark.parametrize('damage', ['omitted','renamed','extra','repeated','blocking','wrong_place'])
def test_assembly_refuses_incomplete_or_inconsistent_units(damage):
    data = parts()
    cid = data['registry'][0]['id']
    if damage == 'omitted': data['batches'] = []
    if damage == 'renamed': data['batches'][0]['cards'][cid]['name'] = 'Замена'
    if damage == 'extra': data['batches'][0]['characters']['unplanned'] = dict(id='unplanned')
    if damage == 'repeated': data['batches'] *= 2
    if damage == 'blocking': data['interpretation']['blocking_ids'] = ['contradiction']
    if damage == 'wrong_place': data['opening']['camera']['location_id'] = 'missing'
    with pytest.raises(ValueError): stages.compose(**data)


def test_roster_rejects_omitted_explicit_npc_even_if_cast_target_is_smaller():
    data = parts()
    data['setting']['entities'].pop(0)
    with pytest.raises(ValueError, match='omitted source'):
        stages.allocate_entities(data['setting'], data['interpretation'], 'w')
    roster = [dict(id=str(i),kind='character',tier='core' if i<7 else 'secondary') for i in range(25)]
    batches = stages.character_batches(roster)
    assert [len(b['character_ids']) for b in batches] == [3,3,1,5,5,5,3]
    assert [cid for b in batches for cid in b['character_ids']] == [str(i) for i in range(25)]


def test_semantic_dependencies_invalidate_only_consumers_and_their_outputs():
    resources = {'character:a:personality':{'traits':['спокойный']},
                 'character:b:personality':{'traits':['резкий']}, 'location:station':{'name':'Станция'},
                 'relationship:a-b':{'trust':40}, 'opening':{'text':'Станция'}}
    checkpoints = {
        'relations-a': {'inputs':stages.input_manifest(resources,['character:a:personality','character:b:personality']), 'outputs':['relationship:a-b']},
        'opening': {'inputs':stages.input_manifest(resources,['relationship:a-b','location:station']), 'outputs':['opening']},
        'b-voice': {'inputs':stages.input_manifest(resources,['character:b:personality']), 'outputs':['voice:b']},
        'station': {'inputs':stages.input_manifest(resources,['location:station']), 'outputs':['map:station']},
    }
    assert stages.stale_units(checkpoints,resources) == []
    resources['character:a:personality'] = {'traits':['терпеливый']}
    assert stages.stale_units(checkpoints,resources) == ['opening','relations-a']
    with pytest.raises(ValueError,match='missing'): stages.input_manifest(resources,['missing'])


def test_replanned_setting_preserves_locked_generated_identity_without_promoting_origin():
    data=parts();protected=[dict(id='protected_npc',name='Сосед',kind='character',tier='secondary',origin='generated')]
    with pytest.raises(ValueError,match='omitted source entities'):
        stages.allocate_entities(data['setting'],data['interpretation'],'w',protected)
    data['setting']['entities'].append(dict(key='neighbor',existing_id='protected_npc',kind='character',name='Сосед',tier='secondary'))
    registry=stages.allocate_entities(data['setting'],data['interpretation'],'w',protected)
    assert registry[-1]==protected[0]
