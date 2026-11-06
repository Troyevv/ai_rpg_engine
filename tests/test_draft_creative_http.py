"""Real OpenAI SDK wire payloads; no live DeepSeek calls."""
import json
from unittest.mock import patch

import httpx
from openai import OpenAI
import pytest

from test_api import api, REMOTE, wait_job
from test_initial_draft_v4 import rich
from test_draft_creative import additions
from backend.services import draft_creative, draft_completeness
from backend.repositories.preparation import Repository

KEY = 'private-fixture-key'


class CreativeHTTP:
    def __init__(self, rejection=None):
        self.requests = []
        self.rejection = rejection

    def client(self, **kwargs):
        return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(self.handle)))

    def handle(self, request):
        body = json.loads(request.content)
        self.requests.append(body)
        system = body['messages'][0]['content']
        creative = system.startswith(draft_creative.MARKER)
        error = None
        if body.get('response_format') == {'type': 'json_object'} and not any('json' in m['content'].lower() for m in body['messages']):
            error = ('messages must contain json for json_object', 'messages')
        elif creative and self.rejection:
            error = self.rejection
        if error:
            return httpx.Response(400, json={'error': dict(message=error[0]+' '+KEY+' private echoed prompt', param=error[1], type='invalid_request_error')})
        if creative:
            payload = json.loads(body['messages'][1]['content'])
            value = dict(candidate_hash=payload['candidate_hash'], rationale='Восстановление мастерской.', changes=additions(payload['candidate']))
        elif system.startswith(draft_completeness.MARKER):
            value = {'issues': []}
        else:
            value = rich()
        chunk = dict(id='fixture', object='chat.completion.chunk', created=0, model=body['model'], choices=[dict(index=0, delta={'content': json.dumps(value, ensure_ascii=False)}, finish_reason='stop')], usage={'prompt_tokens':100,'completion_tokens':20,'total_tokens':120})
        return httpx.Response(200, headers={'content-type':'text/event-stream'}, content='data: '+json.dumps(chunk)+'\n\ndata: [DONE]\n\n')


def start(client, thinking='low'):
    wid = client.post('/api/workspaces', json={'name':'Сосновка'}).json()['id']
    url = f'/api/workspaces/{wid}/draft'
    response = client.post(url+'/generate', json=dict(revision=0,text='Сосновка, конец октября. Жители восстанавливают мастерскую.',config=dict(REMOTE,thinking=thinking,context_length=131072,max_tokens=20000),api_key=KEY))
    assert response.status_code == 200, response.text
    return wid, url, response.json()['id']


@pytest.mark.parametrize('thinking', ['off','low','high'])
def test_creative_sdk_success(api, thinking):
    client, app = api
    http = CreativeHTTP()
    with patch('llm.OpenAI', side_effect=http.client):
        wid, url, jid = start(client, thinking)
        job = wait_job(client, jid)
    assert job['status'] == 'saved', job
    body = next(b for b in http.requests if b['messages'][0]['content'].startswith(draft_creative.MARKER))
    assert body['response_format'] == {'type':'json_object'}
    assert 'json' in body['messages'][0]['content'].lower()
    assert body['thinking'] == {'type':'disabled' if thinking == 'off' else 'enabled'}
    assert body.get('reasoning_effort') == (None if thinking == 'off' else thinking)
    assert ('temperature' in body) == (thinking == 'off')
    assert body['max_tokens'] == 20000
    assert len(http.requests) == 3
    draft = client.get(url+'?author=true').json()
    assert draft['state']['world']['organizations']['workshop']
    assert draft['review']['status'] == 'completed'


@pytest.mark.parametrize('rejection,reason', [
    (('messages must contain json','messages'),'json_instruction_required'),
    (('max_tokens out of range','max_tokens'),'output_limit'),
    (('context length exceeded','messages'),'context_limit'),
    (('invalid model does not exist','model'),'model_unavailable'),
    (('reasoning_effort incompatible with thinking','reasoning_effort'),'incompatible_parameters'),
    (('response_format unsupported','response_format'),'incompatible_parameters'),
    (('opaque refusal','private parameter'),'unclassified_rejection'),
])
def test_http400_diagnostics_resume_and_accounting(api, rejection, reason):
    client, app = api
    http = CreativeHTTP(rejection)
    with patch('llm.OpenAI', side_effect=http.client):
        wid, url, jid = start(client)
        job = wait_job(client, jid)
        assert job['status'] == 'error'
        assert len(http.requests) == 2  # no SDK/service automatic retry of 400
        diag = job['response_diagnostic']
        assert diag['reason'] == reason
        assert diag['http_status'] == 400 and not diag['received_text']
        assert len(diag['request_id']) == 32
        assert 'Текст ответа не получен' in diag['message']
        draft = client.get(url+'?author=true').json()
        assert draft['candidate'] and draft['technical_valid']
        assert 'workshop' not in draft['candidate']['world']['organizations']
        before = draft['candidate']
        version = draft['version_id']
        assert Repository(app.state.repository.path).draft(wid, True)['candidate'] == before
        assert client.get(url).json()['job']['response_diagnostic'] == diag
        raw = client.get(url+'/raw').json()
        assert raw['creative']['diagnostics'] == diag
        assert raw['http_failures'][0]['reservation_released']
        assert raw['http_failures'][0]['provider_error']['reason'] == reason
        assert raw['reserved_tokens'] == 0 and raw['actual_tokens'] == 120
        assert raw['requests'][0]['usage_json'] is None
        assert raw['responses'][raw['active_response']]['parts'] == []
        assert KEY not in json.dumps(raw) and 'private echoed prompt' not in json.dumps(raw)
        assert raw['http_failures'][0]['diagnostic']['request_id'] == raw['requests'][0]['id']
        if reason != 'unclassified_rejection':
            blocked = client.post(url+'/resume', json=dict(revision=draft['revision'],api_key=KEY,context_length=140000))
            assert blocked.status_code == 200
            assert wait_job(client,jid)['status'] == 'error'
            assert len(http.requests) == 2  # unchanged invalid payload is not sent
        http.rejection = None
        resumed = client.post(url+'/resume', json=dict(revision=draft['revision'],api_key=KEY,max_tokens=19000))
        assert resumed.status_code == 200, resumed.text
        job = wait_job(client, jid)
        assert job['status'] == 'saved', job
        assert job['response_diagnostic'] is None
        assert len(http.requests) == 4  # base once, failed creative, creative, review
        final = client.get(url+'?author=true').json()
        assert final['state']['world']['organizations']['workshop']
        assert final['version_id'] != version
        assert any(v['id'] == version for v in final['history'])
        raw = client.get(url+'/raw').json()
        assert raw['actual_tokens'] == 360 and raw['reserved_tokens'] == 0
        assert raw['creative']['status'] == 'applied'
        # Applied journal checkpoint never reapplies or calls the provider.
        journal = json.loads(app.state.repository.preparation_job(jid)['response_journal'])
        assert draft_creative.develop(final['state'], 'бриф', journal, lambda *_:pytest.fail('duplicate request'),lambda:None) == final['state']
        with app.state.repository.connect() as db:
            assert KEY not in '\n'.join(db.iterdump())


@pytest.mark.parametrize('edit_candidate', [False,True])
def test_legacy_invalid_json_request_recovers_after_prompt_fix(api, edit_candidate):
    client, app = api
    http = CreativeHTTP()
    fixed = draft_creative.RULES
    legacy = fixed.replace('Верни один JSON-объект по response_schema, без Markdown и пояснений: атомарный пакет, не полный мир.', 'Верни один атомарный пакет по response_schema, не полный мир.')
    with patch('llm.OpenAI', side_effect=http.client):
        with patch.object(draft_creative,'RULES',legacy):
            wid,url,jid = start(client)
            job = wait_job(client,jid)
        assert job['status'] == 'error'
        assert job['response_diagnostic']['reason'] == 'json_instruction_required'
        assert len(http.requests) == 2
        assert not any('json' in m['content'].lower() for m in http.requests[-1]['messages'])
        draft = client.get(url+'?author=true').json()
        original_hash = client.get(url+'/raw').json()['creative']['before_hash']
        if edit_candidate:
            response = client.patch(url,json=dict(revision=draft['revision'],operation='patch',kind='character',entity_id=draft['candidate']['characters'][0]['id'],field='fields.Стиль общения',value='Говорит отрывисто.',warnings_ack=True))
            assert response.status_code == 200, response.text
            draft = response.json()
        response = client.post(url+'/resume',json=dict(revision=draft['revision'],api_key=KEY))
        assert response.status_code == 200, response.text
        assert wait_job(client,jid)['status'] == 'saved'
    raw = client.get(url+'/raw').json()
    assert raw['creative']['status'] == 'applied'
    assert len(http.requests) == 4
    assert raw['actual_tokens'] == 360 and raw['reserved_tokens'] == 0
    if edit_candidate:
        assert raw['creative']['before_hash'] != original_hash
        assert raw['creative_history'][0]['before_hash'] == original_hash
        assert raw['candidate_snapshot']['characters'][0]['fields']['Стиль общения'] == 'Говорит отрывисто.'
