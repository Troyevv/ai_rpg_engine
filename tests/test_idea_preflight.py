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
