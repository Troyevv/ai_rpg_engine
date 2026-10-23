import json
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.usefixtures('legacy_generation_v5')
from test_api import api
from test_world_generation import fake_stages, submit, wait


def paused_world(client, repo, calls):
    commit=repo.commit_generation_unit
    def pause_after_opening(jid,token,unit,payload):
        result=commit(jid,token,unit,payload)
        if unit=='opening': repo.generation_control(jid,'pause')
        return result
    with patch('backend.services.preparation.chat_stream',side_effect=fake_stages(calls)), patch.object(repo,'commit_generation_unit',side_effect=pause_after_opening):
        wid,jid=submit(client)
        assert wait(client,jid)['status']=='paused'
    cp=repo.inspect_generation_checkpoint(jid,'core_0',True)
    cid=next(iter(cp['artifact']['characters']))
    body=dict(operation='patch',kind='character',generation_job=jid,generation_unit='core_0',
        artifact_version=cp['artifact_version'],revision=repo.generation_status(jid)['revision'],
        entity_id=cid,field='personality.traits',value='Сдержанная, но настойчивая',preview=True)
    return wid,jid,body,cp


def test_paused_character_patch_preview_cas_resume_and_start(api):
    client,app=api;repo=app.state.repository;calls=[]
    wid,jid,body,before=paused_world(client,repo,calls)
    path=f'/api/workspaces/{wid}/draft'
    with repo.connect() as db: count=db.execute('SELECT count(*) FROM document_versions').fetchone()[0]
    preview=client.patch(path,json=body)
    assert preview.status_code==200,preview.text
    assert preview.json()['stale_units']==['assembly','life','lore','opening','review_life_0','review_lore_0','review_opening_0']
    with repo.connect() as db: assert db.execute('SELECT count(*) FROM document_versions').fetchone()[0]==count
    accepted=client.patch(path,json={**body,'preview':False})
    assert accepted.status_code==200,accepted.text
    assert client.patch(path,json={**body,'preview':False}).status_code==409
    after=repo.inspect_generation_checkpoint(jid,'core_0',True)
    cid=body['entity_id']
    other=next(key for key in before['artifact']['characters'] if key!=cid)
    assert after['artifact']['characters'][other]==before['artifact']['characters'][other]
    assert after['artifact']['cards']==before['artifact']['cards']
    assert repo.generation_field_locks(jid,'core_0')
    assert 'Сдержанная' not in json.dumps(repo.generation_status(jid),ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=fake_stages(calls)):
        response=client.post(f'/api/jobs/{jid}/generation/resume',json={'revision':accepted.json()['revision']})
        assert response.status_code==200,response.text
        assert wait(client,jid)['status']=='saved'
    assert calls==['interpret','setting','places','characters','life','lore','opening','life','lore','opening','review','review','review']
    draft=repo.draft(wid,True)
    result=repo.confirm_draft(wid,draft['revision'],draft['version_id'])
    actor=repo.get_snapshot(result['save'])['world_state']['characters'][cid]
    assert actor['personality']['items']['author_traits']['text']==body['value']


def test_checkpoint_patch_rejects_foreign_workspace_source_fact_and_stale_artifact(api):
    client,app=api;repo=app.state.repository
    wid,jid,body,before=paused_world(client,repo,[])
    foreign=repo.create_workspace('Other')['id']
    assert client.patch(f'/api/workspaces/{foreign}/draft',json=body).status_code==409
    assert client.patch(f'/api/workspaces/{wid}/draft',json={**body,'field':'display_name','value':'Renamed'}).status_code==409
    plan=repo.inspect_generation_checkpoint(jid,'interpret',True)
    # Model a previously accepted explicit source constraint. This is deliberately
    # internal setup; clients cannot replace interpretation with arbitrary JSON.
    payload=plan['artifact']
    payload['claims'].append(dict(id='fixed-trait',classification='explicit',section='personality',subject_id=body['entity_id']))
    repo.revise_generation_checkpoint(jid,'interpret',payload,body['revision'],plan['artifact_version'],[],preview=False)
    # Already-invalidated character output is not editable through the API.
    assert client.patch(f'/api/workspaces/{wid}/draft',json=body).status_code==409
    with repo.connect() as db:
        db.execute("UPDATE preparation_units SET status='completed' WHERE job_id=? AND unit_id='core_0'",(jid,))
    body['revision']=repo.generation_status(jid)['revision']
    rejected=client.patch(f'/api/workspaces/{wid}/draft',json=body)
    assert rejected.status_code==409 and 'fixed-trait' in rejected.text
    assert repo.inspect_generation_checkpoint(jid,'core_0',True)['artifact']==before['artifact']


def test_explicit_canonical_character_facts_reject_generated_conflicts():
    from backend.services.generation_constraints import validate_character_facts
    plan={'claims':[dict(id='sex',classification='explicit',section='character',time_scope='',
        subject_id='a',field='biological_sex',value='female')]}
    with pytest.raises(ValueError,match='biological_sex'):
        validate_character_facts({'characters':{'a':{'biological_sex':'male'}}},plan)
    assert validate_character_facts({'characters':{'a':{'biological_sex':'female'}}},plan)


def test_staged_provider_cannot_commit_a_changed_explicit_character_fact(api):
    from test_world_interpretation import BRIEF
    from test_api import REMOTE
    client,app=api;calls=[];fixture=fake_stages(calls)
    brief=BRIEF+' Анна — женщина.'
    def contradictory(**kwargs):
        for raw in fixture(**kwargs):
            result=json.loads(raw)
            if calls[-1]=='interpret':
                result['claims'].append(dict(classification='explicit',section='character',field='biological_sex',
                    subject_key='anna',value='female',description='Анна — женщина.',
                    spans=[dict(start=len(BRIEF)+1,end=len(brief),quote='Анна — женщина.')]))
            if calls[-1]=='characters':
                for actor in result['characters'].values():
                    if actor['display_name']=='Анна': actor['biological_sex']='male'
            yield json.dumps(result,ensure_ascii=False)
    wid=client.post('/api/workspaces',json={'name':'Protected source'}).json()['id']
    with patch('backend.services.preparation.chat_stream',side_effect=contradictory):
        response=client.post(f'/api/workspaces/{wid}/draft/generate',json=dict(task='world_staged',text=brief,
            revision=0,config=REMOTE,api_key='free-fixture'))
        jid=response.json()['id'];result=wait(client,jid)
    assert result['status']=='failed'
    assert 'biological_sex' in result['error']
    assert calls.count('characters')==2
    assert app.state.repository.draft(wid,True)['state'] is None
    assert app.state.repository.inspect_generation_checkpoint(jid,'core_0',True)['artifact_version'] is None


def checkpoint_body(repo,jid,unit,field,value,**extra):
    cp=repo.inspect_generation_checkpoint(jid,unit,True)
    return dict(operation='patch',kind='checkpoint',generation_job=jid,generation_unit=unit,
        artifact_version=cp['artifact_version'],revision=repo.generation_status(jid)['revision'],
        field=field,value=value,preview=False,**extra)


def test_paused_place_edit_unlock_and_selective_regeneration(api):
    client,app=api;repo=app.state.repository
    wid,jid,_,_=paused_world(client,repo,[])
    path=f'/api/workspaces/{wid}/draft'
    lid=next(iter(repo.generation_resources(jid,['places'])['places']['locations']))
    body=checkpoint_body(repo,jid,'places','/locations/'+lid+'/description','Длинная дорога')
    before=repo.inspect_generation_checkpoint(jid,'places',True)
    preview=client.patch(path,json={**body,'preview':True})
    assert preview.status_code==200,preview.text
    assert repo.inspect_generation_checkpoint(jid,'places',True)==before
    saved=client.patch(path,json=body)
    assert saved.status_code==200,saved.text
    assert 'places' not in saved.json()['stale_units']
    assert repo.generation_field_locks(jid,'places')=={body['field']:'Длинная дорога'}
    unlocked=client.patch(path,json={**checkpoint_body(repo,jid,'places',body['field'],None),'operation':'unlock'})
    assert unlocked.status_code==200,unlocked.text
    assert unlocked.json()['locked_paths']==[]
    assert not repo.generation_field_locks(jid,'places')
    regen=client.patch(path,json={**checkpoint_body(repo,jid,'places','',None),'operation':'regenerate'})
    assert regen.status_code==200,regen.text
    assert 'places' in regen.json()['stale_units']
    assert 'interpret' not in regen.json()['stale_units']
    assert 'setting' not in regen.json()['stale_units']


def test_explicit_constraint_revision_requires_ack_and_retains_source(api):
    client,app=api;repo=app.state.repository
    wid,jid,_,_=paused_world(client,repo,[])
    path=f'/api/workspaces/{wid}/draft'
    original=repo.generation_resources(jid,['interpretation'])['interpretation']
    body=checkpoint_body(repo,jid,'interpret','/claims/4/description','Страна — вымышленная')
    assert client.patch(path,json=body).status_code==409
    saved=client.patch(path,json={**body,'warnings_ack':True})
    assert saved.status_code==200,saved.text
    revised=repo.generation_resources(jid,['interpretation'])['interpretation']
    assert revised['brief']==original['brief']
    assert revised['claims'][:4]==original['claims'][:4]
    assert revised['constraint_revision']==original['constraint_revision']+1
    assert revised['amendments'][-1]['path']=='/claims/4/description'
    assert 'setting' in saved.json()['stale_units']


@pytest.mark.parametrize('stage,payload,rule',[
    ('life',{'objective_relations':{'r':{'kind':'biological_parent','source_id':'a','target_id':'b'}}},
     dict(path='/objective_relations',operator='contains',expected={'kind':'adoptive_parent','source_id':'a','target_id':'b'})),
    ('life',{'relationships':{'r':{'source_id':'a','target_id':'b','context':'romance'}}},
     dict(path='/relationships',operator='absent',expected={'source_id':'a','target_id':'b','context':'romance'})),
    ('lore',{'knowledge':{'a':{'actor_id':'a','fact_id':'secret'},'b':{'actor_id':'b','fact_id':'secret'}}},
     dict(path='/knowledge',operator='only',where={'fact_id':'secret'},select='actor_id',expected=['a'])),
    ('opening',{'world_time':6000},dict(path='/world_time',operator='equals',expected=6120)),
    ('lore',{'initial_history':{'events':[{'minute':6000,'text':'Discovered'}]}},
     dict(path='/initial_history/events',operator='contains',expected={'minute':4680,'text':'Discovered'})),
])
def test_source_bindings_reject_changed_relations_prohibitions_knowledge_and_chronology(stage,payload,rule):
    from backend.services.generation_constraints import validate_stage_facts
    plan={'claims':[{'id':'source','classification':'explicit','rules':[dict(stage=stage,**rule)]}]}
    with pytest.raises(ValueError,match='source'):validate_stage_facts(stage,payload,plan)


def test_confirmation_rechecks_source_bindings_after_author_edit(api):
    from backend.services.world_interpretation import accept
    from test_world_interpretation import BRIEF,interpretation
    from backend.services.generation_constraints import validate_snapshot_facts
    from backend.services.initial_world_v2 import normalize
    client,app=api;repo=app.state.repository;calls=[]
    fixture=fake_stages(calls)
    def bound(**kwargs):
        for raw in fixture(**kwargs):
            result=json.loads(raw)
            if calls[-1]=='interpret':result['claims'][2]['rules']=[dict(stage='opening',path='/world_time',operator='equals',expected=6120)]
            yield json.dumps(result,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=bound):
        wid,jid=submit(client)
        assert wait(client,jid)['status']=='saved'
    draft=repo.draft(wid,True)
    response=client.patch(f'/api/workspaces/{wid}/draft',json=dict(revision=draft['revision'],operation='patch',kind='start',field='minute',value=6200))
    assert response.status_code==200,response.text
    changed=response.json()
    denied=client.post(f'/api/workspaces/{wid}/draft/confirm',json=dict(revision=changed['revision'],version_id=changed['version_id']))
    assert denied.status_code==409 and 'constraints' in denied.text


def test_source_knowledge_revision_keeps_setting_places_and_characters(api):
    client,app=api;repo=app.state.repository
    wid,jid,_,_=paused_world(client,repo,[])
    original={u:repo.inspect_generation_checkpoint(jid,u,True) for u in ('setting','places','core_0')}
    body=checkpoint_body(repo,jid,'interpret','/claims/1/description','Мира узнала вчера вечером',warnings_ack=True)
    saved=client.patch(f'/api/workspaces/{wid}/draft',json=body)
    assert saved.status_code==200,saved.text
    assert saved.json()['stale_units']==['assembly','lore','opening','review_life_0','review_lore_0','review_opening_0']
    for unit,before in original.items():assert repo.inspect_generation_checkpoint(jid,unit,True)==before
    calls=[]
    with patch('backend.services.preparation.chat_stream',side_effect=fake_stages(calls)):
        response=client.post(f'/api/jobs/{jid}/generation/resume',json={'revision':saved.json()['revision']})
        assert response.status_code==200,response.text
        assert wait(client,jid)['status']=='saved'
    assert calls==['lore','opening','review','review','review']


def test_canonical_editor_schema_and_named_references_are_author_only(api):
    client,app=api;repo=app.state.repository
    wid,jid,body,cp=paused_world(client,repo,[])
    assert 'Character' in cp['editor_schema']['$defs']
    assert any(row['id']==body['entity_id'] for row in cp['reference_options'])
    public=repo.inspect_generation_checkpoint(jid,'core_0',False)
    assert not {'artifact','editor_schema','reference_options','locked_paths'} & public.keys()


@pytest.mark.parametrize('rule',[
    dict(stage='life',path='/objective_relation',operator='absent',expected={'kind':'spouse'}),
    dict(stage='lore',path='/knowledge',operator='only',expected=None),
    dict(stage='life',path='/objective_relations/~wrong',operator='absent'),
])
def test_source_bindings_reject_malformed_canonical_targets(rule):
    from backend.services.world_interpretation import ConstraintRule
    with pytest.raises(ValueError):ConstraintRule.model_validate(rule)


def test_absence_binding_does_not_prove_a_prohibition_when_path_is_missing():
    from backend.services.generation_constraints import validate_stage_facts
    plan={'claims':[dict(id='no-marriage',classification='prohibition',rules=[dict(stage='life',path='/objective_relations/missing',operator='absent',expected={'kind':'spouse'})])]}
    with pytest.raises(ValueError,match='no-marriage'):
        validate_stage_facts('life',{'objective_relations':{}},plan)


def test_source_entity_tier_edit_uses_the_existing_interpretation_schema(api):
    client,app=api;repo=app.state.repository
    wid,jid,_,_=paused_world(client,repo,[])
    before=repo.inspect_generation_checkpoint(jid,'interpret',True)
    body=checkpoint_body(repo,jid,'interpret','/entities/0/tier','unsupported-tier',warnings_ack=True)
    response=client.patch(f'/api/workspaces/{wid}/draft',json=body)
    assert response.status_code==409 and 'tier' in response.text
    assert repo.inspect_generation_checkpoint(jid,'interpret',True)==before


def test_player_draft_diagnostics_do_not_leak_hidden_character_names(api):
    from test_draft_world import fixture
    client,app=api;repo=app.state.repository
    wid=repo.create_workspace('Private review')['id']
    state=fixture();card=state['characters'][1]
    card['name']='Секретный участник';card['hidden']=True
    card['fields']['Внешность']=''
    for scene in state['world']['scenes'].values():
        scene['participants']=[cid for cid in scene['participants'] if cid!=card['id']]
    card['visible_to_ids']=[]
    with repo.connect() as db:repo._write_draft(db,wid,state,'fixture',generated=True)
    authored=repo.draft(wid,True)
    assert 'Секретный участник' in json.dumps(authored['validation'],ensure_ascii=False)
    player=repo.draft(wid,False)
    assert player['validation']['warnings']
    assert 'Секретный участник' not in json.dumps(player['validation'],ensure_ascii=False)


@pytest.mark.parametrize('collection',['relationships','residences','roles','possessions','contacts','facts','threads','scheduled_events'])
def test_paused_record_families_resume_without_rewriting_unrelated_characters(api,collection):
    client,app=api;repo=app.state.repository
    wid,jid,_,_=paused_world(client,repo,[])
    registry=repo.generation_resources(jid,['registry'])['registry']
    people=[r['id'] for r in registry if r['kind']=='character'];a,b=people
    location=next(r['id'] for r in registry if r['kind']=='location')
    values={
        'relationships':{a+':'+b:dict(source_id=a,target_id=b,dimensions={'trust':0.4},context='Автор добавил доверие')},
        'residences':{'home':dict(id='home',actor_id=a,location_id=location,evidence='Автор явно задал проживание')},
        'roles':{'role':dict(id='role',actor_id=a,kind='occupation',title='Авторская профессия')},
        'possessions':{'bag':dict(id='bag',name='Дорожная сумка',kind='personal',owner_id=a)},
        'contacts':{'phone':dict(id='phone',owner_id=a,character_id=b,label='Личный номер',address='fixture-contact',provenance='Явно добавлено автором',created_at=6120)},
        'facts':{'note':dict(id='note',text='Авторский факт',visibility='public')},
        'threads':{'thread':dict(id='thread',description='Открытая возможность',character_ids=[a])},
        'scheduled_events':{'event':dict(id='event',description='Встреча когда будет удобно',character_ids=[a],due_minute=None)},
    }
    stage='lore' if collection in ('facts','threads') else 'opening' if collection=='scheduled_events' else 'life'
    prior=repo.inspect_generation_checkpoint(jid,stage,True)['artifact']
    value={**prior[collection],**values[collection]}
    peers={u:repo.inspect_generation_checkpoint(jid,u,True) for u in ('setting','places','core_0')}
    body=checkpoint_body(repo,jid,stage,'/'+collection,value)
    accepted=client.patch(f'/api/workspaces/{wid}/draft',json=body)
    assert accepted.status_code==200,accepted.text
    assert repo.generation_field_locks(jid,stage)['/'+collection]==repo.inspect_generation_checkpoint(jid,stage,True)['artifact'][collection]
    for unit,old in peers.items():
        current=repo.inspect_generation_checkpoint(jid,unit,True)
        for key in ('artifact','artifact_version','status','locked_paths'):assert current[key]==old[key]
        if collection=='facts':assert any(r['id']=='note' for r in current['reference_options'])
    calls=[]
    with patch('backend.services.preparation.chat_stream',side_effect=fake_stages(calls)):
        resumed=client.post(f'/api/jobs/{jid}/generation/resume',json={'revision':accepted.json()['revision']})
        assert resumed.status_code==200,resumed.text
        assert wait(client,jid)['status']=='saved'
    assert 'characters' not in calls and 'setting' not in calls and 'places' not in calls
    draft=repo.draft(wid,True);confirmed=repo.confirm_draft(wid,draft['revision'],draft['version_id'])
    state=repo.get_snapshot(confirmed['save'])['world_state']
    for key,fields in values[collection].items():
        for field,expected in fields.items():assert state[collection][key][field]==expected


def test_source_revision_can_unlock_stale_character_without_revalidating_old_artifact(api):
    client,app=api;repo=app.state.repository
    wid,jid,body,_=paused_world(client,repo,[]);endpoint=f'/api/workspaces/{wid}/draft'
    assert client.patch(endpoint,json={**body,'preview':False}).status_code==200
    locked=repo.inspect_generation_checkpoint(jid,'core_0',True)
    pointer=locked['locked_paths'][0]
    source=checkpoint_body(repo,jid,'interpret','/entities/0/name','Анна Новая',warnings_ack=True)
    assert client.patch(endpoint,json=source).status_code==200
    stale=repo.inspect_generation_checkpoint(jid,'core_0',True)
    assert stale['status']=='stale' and stale['artifact']==locked['artifact']
    unlock={**checkpoint_body(repo,jid,'core_0',pointer,None),'operation':'unlock'}
    rejected=client.patch(endpoint,json={**unlock,'artifact_version':-1})
    assert rejected.status_code==409
    preview=client.patch(endpoint,json={**unlock,'preview':True})
    assert preview.status_code==200,preview.text
    assert repo.generation_field_locks(jid,'core_0')
    saved=client.patch(endpoint,json=unlock)
    assert saved.status_code==200,saved.text
    assert not repo.generation_field_locks(jid,'core_0')
    after=repo.inspect_generation_checkpoint(jid,'core_0',True)
    assert after['status']=='stale' and after['artifact']==stale['artifact']
    assert after['artifact_version']==stale['artifact_version']
    assert saved.json()['revision']==unlock['revision']+1
    assert client.patch(endpoint,json=unlock).status_code==409
