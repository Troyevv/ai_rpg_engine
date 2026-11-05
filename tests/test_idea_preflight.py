"""The review step shares generate validation and has no persistent side effects."""
from copy import deepcopy
import pytest
from test_initial_draft_v4 import api, REMOTE


def body(**overrides):
    return dict(name='Замысел',text='Город у моря',revision=0,config=REMOTE,**overrides)


def snapshot(repo):
    with repo.connect() as db:
        return '\n'.join(db.iterdump())


@pytest.mark.parametrize('settings',[
    {'primary_genre':'custom','custom_genre':''},
    {'calendar_start':{'mode':'custom','date':'2026-01-31','profile':{'id':'custom','system':'custom','month_lengths':[30],'month_names':['Первый'],'weekday_names':['Первый']}}},
    {'core_npcs':0},
    {'secondary_npcs':41},
])
def test_invalid_settings_never_create_workspace_or_job(api,settings):
    client,app=api;repo=app.state.repository;before=snapshot(repo)
    response=client.post('/api/world-creation/validate',json=body(creation_settings=settings))
    assert response.status_code==422,response.text
    problem=response.json()['detail'][0]
    assert problem['loc'][:2]==['body','creation_settings']
    assert problem['msg'] and set(problem)=={'loc','msg','type'}
    assert snapshot(repo)==before


def test_preflight_scenario_validation_and_no_writes(api):
    client,app=api;repo=app.state.repository
    wid=client.post('/api/workspaces',json={'name':'Сценарий'}).json()['id']
    data=body(workspace_id=wid,use_idea=True);data['text']=''
    before=snapshot(repo)
    assert client.post('/api/world-creation/validate',json=data).status_code==409
    assert snapshot(repo)==before
    with repo.connect() as db:
        db.execute('UPDATE preparation_workspaces SET idea=? WHERE id=?',('Сохранённый сценарий',wid))
    before=snapshot(repo)
    assert client.post('/api/world-creation/validate',json=data).json()=={'valid':True}
    assert snapshot(repo)==before


def test_valid_complex_settings_are_accepted_without_mutation(api):
    client,app=api;repo=app.state.repository
    profile=client.get('/api/communication/presets').json()['letters']
    profile.update(preset='custom',voice_call=True,presentation='phone')
    settings={'communication':profile,'primary_genre':'custom','custom_genre':'Драма у моря','cast_preset':'custom','core_npcs':4,'secondary_npcs':7,
      'calendar_start':{'mode':'custom','date':'2026-02-30','time':'18:30','profile':{'id':'custom','system':'custom','month_lengths':[30,40],'month_names':['Первый','Второй'],'weekday_names':['Один','Два','Три']}}}
    before=snapshot(repo)
    response=client.post('/api/world-creation/validate',json=body(creation_settings=deepcopy(settings)))
    assert response.status_code==200,response.text
    assert snapshot(repo)==before


def test_real_generation_502_review_reuses_candidate_and_job(api):
    import json
    import time
    from unittest.mock import patch
    from idea190_provider import IdeaProvider
    from test_api import wait_job
    client,app=api;repo=app.state.repository
    provider=IdeaProvider(fail_review=True,custom_calendar=True)
    settings={'primary_genre':'custom','custom_genre':'Драма','cast_preset':'custom','core_npcs':4,'secondary_npcs':7}
    profile=client.get('/api/communication/presets').json()['letters'];profile.update(preset='custom',voice_call=True,presentation='phone')
    settings['communication']=profile
    settings['calendar_start']={'mode':'custom','date':'2026-02-30','time':'18:30','profile':{'id':'custom','system':'custom','month_lengths':[30,40],'month_names':['Первый','Второй'],'weekday_names':['Первый','Второй','Третий']}}
    data=body(creation_settings=settings);data.update(text='ATELIER190. Город друзей',config=dict(REMOTE,context_length=131072,max_tokens=24000))
    assert client.post('/api/world-creation/validate',json=data).status_code==200
    wid=client.post('/api/workspaces',json={'name':data['name']}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    data.pop('name')
    def stream(**kwargs):
        assert provider.matches(kwargs)
        yield from provider.stream(kwargs)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        started=client.post(url+'/generate',json=dict(data,api_key='offline-fixture'))
        assert started.status_code==200,started.text
        jid=started.json()['id']
        try:
            for _ in range(500):
                before=client.get(url+'?author=true').json()
                if before['job']['phase']=='reviewing':break
                time.sleep(.01)
            assert before['version_id'],before['job']
            assert before['version_origin_job_id']==jid and before['version_is_candidate']
            duplicate=client.post(url+'/generate',json=dict(data,revision=before['revision'],api_key='offline-fixture'))
            assert duplicate.status_code==409
        finally:provider.gate.set()
        failed=wait_job(client,jid)
        assert failed['status']=='error',failed
        d=client.get(url).json()
        assert d['job']['response_diagnostic']['http_status']==502,d
        assert d['state'] is not None
        assert d['source_text']=='' and d['candidate'] is None
        resume=client.post(url+'/resume',json=dict(revision=d['revision'],api_key='offline-fixture'))
        assert resume.status_code==200,resume.text
        assert resume.json()['id']==jid
        assert wait_job(client,jid)['status']=='saved'
    after=client.get(url+'?author=true').json()
    assert provider.world_calls==1 and provider.review_calls==2
    assert after['review']['status']=='completed'
    assert after['version_origin_job_id']==jid and not after['version_is_candidate']
    assert after['creation_settings']['communication']['voice_call']
    assert after['creation_settings']['communication']['letter'] and after['creation_settings']['communication']['courier']
    assert after['creation_settings']['communication']['presentation']=='phone'
    assert after['creation_settings']['custom_genre']=='Драма'
    assert after['creation_settings']['core_npcs']==4
    for key,value in settings['calendar_start'].items():
        if key=='profile':
            for field,expected in value.items():assert after['creation_settings']['calendar_start'][key][field]==expected
        else:assert after['creation_settings']['calendar_start'][key]==value
    journal=json.loads(repo.preparation_job(jid)['response_journal'])
    assert journal['recovery_epoch']==1


def test_preflight_validation_never_echoes_credentials_or_input(api):
    client,_=api
    response=client.post('/api/world-creation/validate',json=body(api_key='secret-key-must-not-echo',creation_settings={'custom_genre':'','primary_genre':'custom'}))
    assert response.status_code==422
    assert 'secret-key-must-not-echo' not in response.text
    assert 'input' not in response.json()['detail'][0]
    assert 'custom genre requires a description' in response.json()['detail'][0]['msg']
