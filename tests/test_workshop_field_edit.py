"""Regression from the author's #188 draft: literary edits are not AppearanceProfile."""
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import pytest
from test_api import api, REMOTE, wait_job


def source():
    state=json.loads((Path(__file__).parent/'fixtures/initial_world/workshop188.json').read_text())
    state['world']['characters']['maxim']['appearance']={
        'items':{'scar':{'category':'modification','kind':'scar','text':'Шрам на левом запястье','revision':2}},
        'legacy_text':'Особая примета из старого мира.', 'applied':['historical-operation']}
    return state


@pytest.mark.parametrize('valid',[True,False])
def test_literary_appearance_isolated_and_failed_response_export(api,valid):
    client,app=api
    wid=client.post('/api/workspaces',json={'name':'Максим'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    r=client.post(url+'/import',json={'revision':0,'format':'json','text':json.dumps(source(),ensure_ascii=False)})
    assert r.status_code==200,r.text
    before=client.get(url+'?author=true').json()
    card=next(c for c in before['state']['characters'] if c['id']=='maxim')
    new=card['fields']['Внешность'].replace('тёмной стрижкой','светлой стрижкой')
    answer=json.dumps({'value':new if valid else {'items':'invalid literary response'}},ensure_ascii=False)
    calls=[]
    def provider(**kwargs):
        calls.append(kwargs['messages'])
        kwargs['on_usage']({'prompt_tokens':100,'completion_tokens':50});kwargs['on_finish']('stop')
        yield answer
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        response=client.post(url+'/generate',json={'revision':before['revision'],'task':'field','kind':'character',
            'entity_id':'maxim','field':'fields.Внешность','text':'Измени только цвет волос на светлый.',
            'warnings_ack':True,'config':dict(REMOTE,context_length=131072,max_tokens=4000),'api_key':'PRIVATE-API-KEY'})
        assert response.status_code==200,response.text
        job=wait_job(client,response.json()['id'])
    assert job['status']==('saved' if valid else 'error'),job
    payload=json.loads(calls[0][1]['content'])
    assert payload['current_value']==card['fields']['Внешность'] and payload['card']==card and payload['entity']==card
    assert 'дословно сохрани' in calls[0][0]['content']
    after=client.get(url+'?author=true').json();expected=deepcopy(before['state'])
    if valid:
        next(c for c in expected['characters'] if c['id']=='maxim')['fields']['Внешность']=new
        # Provenance is allowed to track the authored field, never neighboring data.
        after['state'].pop('authoring',None);expected.pop('authoring',None)
    assert after['state']==expected
    exported=client.get(url+'/raw').json()
    assert exported['job_id']==job['id'] and exported['target']=={'kind':'character','id':'maxim','field':'fields.Внешность'}
    assert exported['operation']=='field' and exported['application']['phase']=='editing'
    assert exported['model_response']['text']==answer and exported['model_response']['available']
    assert exported['requests'][0]['stage']=='draft_field' and exported['requests'][0]['status']=='complete'
    assert exported['model_response']['request_ids']==[exported['requests'][0]['id']]
    assert bool(exported['application']['error']) is not valid
    assert exported['last_saved_state']['version_id']==after['version_id']
    assert 'PRIVATE-API-KEY' not in json.dumps(exported) and 'config_json' not in exported
    assert answer not in client.get(url).text
    assert client.patch(url,json={'revision':after['revision'],'operation':'patch','kind':'actor','entity_id':'maxim','field':'appearance','value':new}).status_code==409
    started=client.post(url+'/confirm',json={'revision':after['revision'],'version_id':after['version_id'],'accept_warnings':True})
    assert started.status_code==200,started.text
    game=app.state.repository.get_snapshot(started.json()['save'])
    from backend.runtime_v3.models import AppearanceProfile
    assert game['world_state']['characters']['maxim']['appearance']==AppearanceProfile.model_validate(before['state']['world']['characters']['maxim']['appearance']).model_dump()
    assert next(c for c in game['character_cards'] if c['id']=='maxim')['fields']['Внешность']==(new if valid else card['fields']['Внешность'])
