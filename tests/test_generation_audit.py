"""Independent stage faults: later stages remain exercised when earlier ones fail."""
import json
from copy import deepcopy
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from backend.services import initial_world_stages as stages, generation_ties as ties
from backend.services.generation_contracts import request_schema
from backend.services.world_blueprint import Blueprint
from backend.services.generation_semantics import AdvisoryReview
from test_api import api
from test_world_blueprint import creative_provider, submit
from test_world_generation import wait
from test_generation_contracts import REGISTRY, places
from test_generation_ties import registry
from llm import OutputLimitReached


@pytest.mark.parametrize('stage', ['interpret','setting','places','characters','ties',
                                   'circumstances','background','knowledge','opening','review'])
@pytest.mark.parametrize('fault', ['json','provider','output_limit'])
def test_each_provider_boundary_preserves_checkpoints_and_resumes(api, stage, fault):
    client, app = api; repo = app.state.repository
    base = creative_provider([]); broken = True; attempts = []
    def stream(**kw):
        current = kw['messages'][0]['content'].split('\nStage: ')[1].split('\n')[0]
        if current == stage and broken:
            attempts.append(current)
            if fault == 'json':
                yield '{'; return
            if fault == 'output_limit':
                kw['on_finish']('length')
                yield '{'
                raise OutputLimitReached('private response')
            raise RuntimeError('private provider detail')
        yield from base(**kw)
    with patch('backend.services.preparation.chat_stream', side_effect=stream):
        wid, jid = submit(client)
        result = wait(client, jid)
        assert result['status'] == 'failed', result
        assert len(attempts) == (2 if fault == 'json' else 1)
        assert 'private' not in result['error']
        versions = {u['unit_id']: repo.inspect_generation_checkpoint(jid,u['unit_id'],True)['artifact_version']
                    for u in result['generation']['units'] if u['status']=='completed'}
        broken = False
        resumed = client.post(f'/api/jobs/{jid}/generation/resume', json={
            'revision':result['generation']['revision'], 'api_key':'fixture'})
        assert resumed.status_code == 200, resumed.text
        assert wait(client,jid)['status'] == 'saved'
    assert all(repo.inspect_generation_checkpoint(jid,k,True)['artifact_version']==v for k,v in versions.items())
    draft=repo.draft(wid,True)
    save=repo.confirm_draft(wid,draft['revision'],draft['version_id'])['save']
    from backend.repositories.preparation import Repository
    assert Repository(repo.path).get_snapshot(save)['world_state']['knowledge']


@pytest.mark.parametrize('size', [2, 16, 30])
def test_dense_directed_graph_exceeds_request_cap_but_not_runtime(size):
    people=registry(size); parts=[]
    for batch in ties.batches(people):
        rows={f'{a}:{b}':dict(source_id=a,target_id=b,dimensions={'trust':i})
              for pair in batch['pairs'] for i,(a,b) in enumerate((pair,pair[::-1]))}
        parts.append(ties.validate({'relationships':rows}, people, batch))
    value=ties.combine(parts,people)
    assert len(value['relationships']) == size*(size-1)
    assert stages.validate('life',value)['relationships']==value['relationships']
    assert stages.validate_ties(value,people,aggregate=True)==value
    if size>15:
        with pytest.raises(ValueError,match='too_long'):stages.validate_ties(value,people)
    # Canonical validation and JSON reload, independent of provider/schema claims.
    from backend.runtime_v3.models import Character
    from backend.services.initial_world_v2 import normalize
    from test_draft_world import fixture
    snapshot=normalize(fixture()).snapshot
    for person in people:
        snapshot['world_state']['characters'][person['id']]=Character(id=person['id'],display_name=person['name']).model_dump()
        snapshot['character_cards'].append(dict(id=person['id'],name=person['name'],fields={},aliases=[]))
    snapshot['world_state']['relationships'].update(value['relationships'])
    accepted=normalize(snapshot).snapshot
    assert normalize(json.loads(json.dumps(accepted))).snapshot==accepted


@pytest.mark.parametrize('fault',['location_cycle','organization_cycle','organization_location'])
def test_places_fail_at_their_own_boundary(fault):
    raw=places()
    if fault=='location_cycle':raw['locations']['lab']['parent_id']='lab'
    elif fault=='organization_cycle':raw['parent_organizations']={'nii':'nii'}
    else:raw['organizations']['nii']['location_ids']=['missing']
    with pytest.raises(ValueError,match='places'):stages.validate_places(raw,REGISTRY)


@pytest.mark.parametrize('fault',['actor','fact','replacement','fact_actor','fact_id'])
def test_lore_rejects_dangling_references_before_opening(fault):
    raw={'facts':{'f':dict(id='f',text='Тайна',visibility='secret',character_ids=['hero'])},
         'knowledge':{'k':dict(actor_id='hero',fact_id='f')}}
    if fault=='actor':raw['knowledge']['k']['actor_id']='missing'
    elif fault=='fact':raw['knowledge']['k']['fact_id']='missing'
    elif fault=='replacement':raw['knowledge']['k']['replaced_by']='missing'
    elif fault=='fact_actor':raw['facts']['f']['character_ids']=['missing']
    else:raw['facts']['f']['id']='other'
    with pytest.raises(ValueError,match='lore/'):stages.validate_lore(raw,REGISTRY)


def test_technical_tie_id_is_derived_without_inventing_or_reversing_relation():
    raw={'objective_relations':{'adoption':dict(kind='adoptive_parent',source_id='hero',target_id='colleague')}}
    original=deepcopy(raw)
    value=stages.validate_ties(raw,REGISTRY)
    assert value['objective_relations']['adoption']['id']=='adoption'
    assert raw==original
    schema=request_schema('ties',stages.TiesPart.model_json_schema(),{'registry':REGISTRY})
    assert 'id' not in schema['$defs']['ObjectiveRelation']['required']


# Array/dictionary maxima are provider budgets, distinct from aggregate sizes.
@pytest.mark.parametrize('model,field,row,limit', [
    (Blueprint,'entities',lambda i:dict(key=str(i),kind='character',name=str(i)),100),
    (stages.SettingPart,'entities',lambda i:dict(key=str(i),kind='character',name=str(i)),200),
    (stages.PlacesPart,'locations',lambda i:dict(id=str(i),name=str(i)),100),
    (stages.TiesPart,'relationships',lambda i:dict(source_id=str(i),target_id='other'),200),
    (stages.CircumstancesPart,'roles',lambda i:dict(id=str(i),actor_id='a',kind='work',title='Work'),200),
    (stages.BackgroundPart,'facts',lambda i:dict(id=str(i),text='Fact'),200),
    (stages.KnowledgePart,'knowledge',lambda i:dict(actor_id=str(i),fact_id='f'),500),
    (stages.OpeningPart,'scheduled_events',lambda i:dict(id=str(i),description='Event'),80),
    (AdvisoryReview,'findings',lambda i:dict(claim_id=str(i),verdict='preserved',explanation='OK'),8),
])
@pytest.mark.parametrize('size', ['minimal','ordinary','maximum','overflow'])
def test_provider_collection_boundaries(model,field,row,limit,size):
    count={'minimal':0,'ordinary':2,'maximum':limit,'overflow':limit+1}[size]
    rows=[row(i) for i in range(count)]
    data={field:rows if field in ('entities','findings') else {str(i):v for i,v in enumerate(rows)}}
    if model is stages.SettingPart:data['campaign']={'title':'World'}
    if model is stages.OpeningPart:data.update(world_time=0,camera={'mode':'observer'})
    if size=='overflow':
        with pytest.raises(ValidationError):model.model_validate(data)
    else:assert len(getattr(model.model_validate(data),field))==count


@pytest.mark.parametrize('section,row', [
    ('residences',dict(id='x',actor_id='missing',location_id='lab')),
    ('roles',dict(id='x',actor_id='hero',kind='work',title='Researcher',organization_id='missing')),
    ('possessions',dict(id='x',name='Key',kind='key',owner_id='missing')),
    ('conditions',dict(id='x',actor_id='missing',description='Tired')),
])
def test_circumstance_references_fail_before_lore(section,row):
    with pytest.raises(ValueError,match='life/'):
        stages.validate_life({section:{'x':row}},REGISTRY)


@pytest.mark.parametrize('size',[0,1,5,6])
def test_character_batch_budget(size):
    raw={field:{str(i):(dict(id=str(i),display_name=str(i)) if field=='characters' else dict(id=str(i),name=str(i)))
                for i in range(size)} for field in ('characters','cards')}
    if size>5:
        with pytest.raises(ValidationError):stages.CharactersPart.model_validate(raw)
    else:assert len(stages.CharactersPart.model_validate(raw).characters)==size


def test_setting_cannot_plan_unrepresentable_places_or_noncharacter_protagonist():
    for entities in ([dict(key=str(i),name=str(i),kind='location') for i in range(101)],
                     [dict(key='lab',name='Lab',kind='location',tier='protagonist')]):
        with pytest.raises(ValidationError):
            stages.SettingPart.model_validate(dict(campaign={'title':'World'},entities=entities))


@pytest.mark.parametrize('scenario',['short','medium','volkov'])
def test_three_scenario_fixtures_reach_start_save_reload(api,scenario):
    client,app=api;repo=app.state.repository
    if scenario=='volkov':
        from test_initial_world_rich_brief import interpreted,provider,BRIEF
        stream=creative_provider([],interpreted(),provider([]));brief=BRIEF
    else:
        brief='Илья, Москва, НИИ.' if scenario=='short' else 'Илья работает в НИИ в Москве. Вера и Олег — его коллеги; партнёр НИИ — университет.'
        seeds=[dict(key='ilya',kind='character',name='Илья',tier='protagonist'),
               dict(key='moscow',kind='location',name='Москва'),
               dict(key='nii',kind='organization',name='НИИ')]
        if scenario=='medium':seeds += [dict(key=k,kind='character',name=n,tier='core') for k,n in [('vera','Вера'),('oleg','Олег')]]+[dict(key='uni',kind='organization',name='Университет')]
        def stream(**kw):
            stage=kw['messages'][0]['content'].split('\nStage: ')[1].split('\n')[0]
            data=json.loads(kw['messages'][-1]['content'])
            if stage=='interpret':raw=dict(entities=seeds,notes=[])
            elif stage=='setting':raw=dict(campaign={'title':brief},entities=[dict(key=str(i),existing_id=r['id'],kind=r['kind'],name=r['name'],tier=r['tier']) for i,r in enumerate(data['interpretation']['entities'])])
            else:
                registry=data['registry'];actors=[r for r in registry if r['kind']=='character']
                hero=next(r['id'] for r in actors if r['tier']=='protagonist')
                place=next(r['id'] for r in registry if r['kind']=='location')
                org=next(r['id'] for r in registry if r['name']=='НИИ')
                if stage=='places':raw=dict(locations={r['id']:dict(id=r['id'],name=r['name']) for r in registry if r['kind']=='location'},organizations={r['id']:dict(id=r['id'],name=r['name']) for r in registry if r['kind']=='organization'})
                elif stage=='characters':
                    selected=[r for r in actors if r['id'] in data['assigned_ids']]
                    raw=dict(characters={r['id']:dict(id=r['id'],display_name=r['name'],location_id=place) for r in selected},cards={r['id']:dict(id=r['id'],name=r['name'],fields={}) for r in selected})
                elif stage=='ties':raw=dict(relationships={r['id']:dict(source_id=r['id'],target_id=hero,dimensions={'respect':25}) for r in actors if r['id']!=hero})
                elif stage=='circumstances':raw=dict(roles={r['id']:dict(id=r['id'],actor_id=r['id'],organization_id=org,kind='occupation',title='Исследователь') for r in actors})
                elif stage=='background':raw=dict(facts={'work':dict(id='work',text='Илья работает в НИИ',character_ids=[hero])})
                elif stage=='knowledge':raw=dict(knowledge={'self':dict(actor_id=hero,fact_id='work')})
                elif stage=='opening':raw=dict(world_time=540,camera=dict(mode='actor',controlled_actor_id=hero,pov_actor_id=hero,location_id=place,present_character_ids=[r['id'] for r in actors],situation='Утро в Москве.'))
                else:raise AssertionError(stage)
            yield json.dumps(raw,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        wid,jid=submit(client,brief);result=wait(client,jid)
    assert result['status']=='saved',result
    draft=repo.draft(wid,True);save=repo.confirm_draft(wid,draft['revision'],draft['version_id'])['save']
    from backend.repositories.preparation import Repository
    snapshot=Repository(repo.path).get_snapshot(save)
    assert len(snapshot['world_state']['characters'])=={'short':1,'medium':3,'volkov':7}[scenario]
    assert snapshot['world_state']['knowledge']
