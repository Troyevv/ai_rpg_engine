"""Real SDK wire requests + API/jobs/SQLite; deterministic HTTP, no live API claim."""
import json
from unittest.mock import patch

import httpx
from openai import OpenAI
import pytest
import engine
from backend.repositories.preparation import Repository
from test_phone122 import setup
from test_narrative_test_world import CONFIG
from test_communication_cycle import decision
from phone_semantic_fixture import extract

KEY = 'local-http-fixture-secret'


class DeepSeekHTTP:
    def __init__(self):
        self.requests = []
        self.reject_semantic = False
        self.answer = None

    def handle(self, request):
        body = json.loads(request.content)
        self.requests.append(body)
        messages = body['messages']
        if body.get('response_format') == {'type': 'json_object'} and not any(
                'json' in m['content'].lower() for m in messages):
            return httpx.Response(400, json={'error': {
                'message': "messages must contain the word json to use response_format json_object",
                'type': 'invalid_request_error', 'param': 'messages'}})
        semantic = messages[0]['content'].startswith('Remote semantic extraction/')
        if semantic and self.reject_semantic and 'scheduled_event_changes' in json.loads(messages[1]['content'])['schema']['properties']:
            self.reject_semantic = False
            return httpx.Response(400, json={'error': {'message': 'fixture rejection',
                'type': 'invalid_request_error', 'param': 'messages'}})
        if self.answer is not None:
            value = self.answer(body) if callable(self.answer) else self.answer
        elif semantic:
            value = json.dumps(extract(json.loads(messages[1]['content'])), ensure_ascii=False)
        elif messages[0]['content'].startswith('Group communication reaction/'):
            data = json.loads(messages[1]['content'])
            actors = data['groups'][0]['actor_ids']
            value = json.dumps({'messages': [dict(actor_id=a, content='Да, договорились.',
                basis_ids=[data['source_message']['id']], read_previous=i > 0)
                for i, a in enumerate(actors[:2])]}, ensure_ascii=False)
        else:
            value = decision(messages).replace('Да, увидимся завтра.', 'Да, договорились.')
        chunk = dict(id='fixture', object='chat.completion.chunk', created=0, model=body['model'],
            choices=[dict(index=0, delta={'content': value}, finish_reason='stop')])
        return httpx.Response(200, headers={'content-type': 'text/event-stream'},
            content='data: ' + json.dumps(chunk) + '\n\ndata: [DONE]\n\n')

    def client(self, **kwargs):
        return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(self.handle)))


def config(thinking='off'):
    return dict(CONFIG, provider='deepseek', model='deepseek-flash', thinking=thinking)


def run(repo, jid, http):
    with patch('llm.OpenAI', side_effect=http.client):
        engine.run_job(repo.path, jid, engine.Worker(api_key=KEY, epoch=repo.get_job(jid)['attempt_epoch']))


def send(repo, client, sid, cfg, group):
    if group:
        joined = client.post(f'/api/saves/{sid}/phone', json=dict(revision=repo.get_save(sid)['revision'],
            command=dict(action='join', conversation_id='qa-group', operation_id='http-join', member_ids=['qa_oleg'])))
        assert joined.status_code == 200, joined.text
    command = dict(action='send', operation_id='deepseek-http-send', content='Встретимся через два часа?')
    command.update({'conversation_id': 'qa-group'} if group else {'contact_id': 'phone-qa_kirill-qa-vera'})
    with patch('engine.launch'):
        response = client.post(f'/api/saves/{sid}/phone/dispatch', json=dict(
            revision=repo.get_save(sid)['revision'], config=cfg, api_key=KEY, command=command))
    assert response.status_code == 200, response.text
    return response.json()['job']['id']


@pytest.mark.parametrize('thinking', ['off', 'low', 'high'])
@pytest.mark.parametrize('group', [False, True])
def test_sdk_phone_json_thinking_meeting(tmp_path, thinking, group):
    repo, client, sid = setup(tmp_path)
    http = DeepSeekHTTP()
    jid = send(repo, client, sid, config(thinking), group)
    run(repo, jid, http)
    assert repo.get_job(jid)['status'] == 'saved', repo.get_job(jid)['error']
    state = repo.get_snapshot(sid)['world_state']
    assert 'phone-meeting' in state['scheduled_events']
    if group:
        assert len(http.requests) == 2  # one author + one Extraction, not per NPC
        assert len({e['sender_id'] for e in state['remote_events'].values()}) == 3
    for body in http.requests:
        assert body['model'] == 'deepseek-flash'
        assert body['response_format'] == {'type': 'json_object'}
        assert body['thinking'] == {'type': 'disabled' if thinking == 'off' else 'enabled'}
        assert ('temperature' in body) == (thinking == 'off')
        assert body.get('reasoning_effort') == (None if thinking == 'off' else thinking)
        assert 'extra_body' not in body  # SDK merges it into the HTTP body
        assert 0 < body['max_tokens'] <= config()['update_tokens']
        assert [m['role'] for m in body['messages']] == ['system', 'user']
    assert Repository(repo.path).get_snapshot(sid) == repo.get_snapshot(sid)


@pytest.mark.parametrize('legacy_channel_context', [False, True])
def test_http400_extraction_reload_retry_reuses_author(tmp_path, legacy_channel_context):
    repo, client, sid = setup(tmp_path)
    http = DeepSeekHTTP(); http.reject_semantic = True
    jid = send(repo, client, sid, config(), True)
    run(repo, jid, http)
    assert repo.get_job(jid)['status'] == 'error'
    assert len(http.requests) == 2
    log = repo.request_log(job_id=jid)
    failed = next(r for r in log if r['status'] == 'error')
    assert failed['stage'] == 'remote_semantics'
    assert failed['diagnostics']['provider_error']['http_status'] == 400
    before = repo.get_snapshot(sid)
    assert len(before['world_state']['remote_events']) == 1
    if legacy_channel_context:
        from backend.runtime_v3.group_planning import GROUP_TEXT_CONTEXT
        job = repo.get_job(jid); frames = json.loads(job['context_json'])
        author = next(f for f in frames if f['stage'] == 'communication')
        author['messages'][0]['content'] = author['messages'][0]['content'].replace(GROUP_TEXT_CONTEXT, '')
        data = json.loads(author['messages'][1]['content']); data['source_message'].pop('channel')
        for group in data['groups']:
            group.pop('channel'); group.pop('communication_profile')
            for actor in group['actors']:
                for field in ('personality','legacy_voice','personal_context'): actor.pop(field)
        author['messages'][1]['content'] = json.dumps(data, ensure_ascii=False)
        repo.save_communication_context(jid, frames, json.loads(job['memory_before_json'] or job['before_json']))
    repo = Repository(repo.path)
    assert repo.get_snapshot(sid) == before
    with patch('engine.launch'):
        response = client.post(f'/api/jobs/{jid}/retry', json={'config': config(), 'api_key': KEY})
    assert response.status_code == 200, response.text
    run(repo, jid, http)
    assert repo.get_job(jid)['status'] == 'saved', repo.get_job(jid)['error']
    assert len(http.requests) == 3
    state = repo.get_snapshot(sid)['world_state']
    assert len(state['remote_events']) == 3 and len(state['scheduled_events']) == 1
    run(repo, jid, http)
    assert len(http.requests) == 3 and repo.get_snapshot(sid)['world_state'] == state
    with repo.connect() as conn:
        assert KEY not in '\n'.join(conn.iterdump())


def test_all_group_json_stage_prompts():
    from test_group152 import group, provider
    from test_remote_communication import command
    from backend.runtime_v3.remote_initiative import stage
    from backend.runtime_v3.remote_semantics import messages
    from backend.runtime_v3.group_planning import reaction_context
    s, gid = group(); gen, calls = provider(gid)
    after = stage(s, gen, 'json-stage-contract')
    after = command(after, 'send', conversation_id=gid, content='Да, приду.')
    source = list(after['world_state']['remote_events'])[-1]
    prompts = [(name, ms) for name, ms, _ in calls]
    prompts += [('group_reaction', reaction_context(after, source)),
                ('response_gate', messages(after, source, response_only=True)),
                ('remote_semantics', messages(after, source))]
    from llm import chat_stream
    http = DeepSeekHTTP(); http.answer = '{"requests":[]}'
    for name, ms in prompts:
        assert 'json' in ms[0]['content'].lower(), name
        with patch('llm.OpenAI', side_effect=http.client):
            assert ''.join(chat_stream('deepseek-flash', ms, provider='deepseek', api_key=KEY,
                response_format={'type': 'json_object'}, require_complete=True)) == http.answer


def test_pre_fix_group_prompt_http400_diagnostics_and_retry(tmp_path):
    from backend.runtime_v3.group_planning import reaction_context
    repo, client, sid = setup(tmp_path)
    http = DeepSeekHTTP()
    jid = send(repo, client, sid, config(), True)
    def pre_fix(snapshot, source):
        ms = reaction_context(snapshot, source)
        ms[0]['content'] = ms[0]['content'].replace(
            'Return one valid JSON object matching the schema. ', '')
        assert not any('json' in m['content'].lower() for m in ms)
        return ms
    with patch('backend.runtime_v3.group_planning.reaction_context', side_effect=pre_fix):
        run(repo, jid, http)
    assert repo.get_job(jid)['status'] == 'error'
    assert len(http.requests) == 1  # no SDK automatic retries
    failed = repo.request_log(job_id=jid)[0]
    assert failed['stage'] == 'remote_initiative'
    diagnostic = failed['diagnostics']['provider_error']
    assert diagnostic['http_status'] == 400
    assert diagnostic['reason'] == 'json_instruction_required'
    assert diagnostic['parameter'] == 'messages'
    assert diagnostic['request']['has_json_instruction'] is False
    assert diagnostic['request']['max_tokens'] == 2400
    assert diagnostic['request']['response_format'] == {'type': 'json_object'}
    assert 'content' not in json.dumps(diagnostic) and KEY not in json.dumps(diagnostic)
    repo = Repository(repo.path)
    assert len(repo.get_snapshot(sid)['world_state']['remote_events']) == 1
    with patch('engine.launch'):
        retried = client.post(f'/api/jobs/{jid}/retry', json={'config': config(), 'api_key': KEY})
    assert retried.status_code == 200, retried.text
    run(repo, jid, http)
    assert repo.get_job(jid)['status'] == 'saved', repo.get_job(jid)['error']
    assert len(http.requests) == 3
    assert len(repo.get_snapshot(sid)['world_state']['remote_events']) == 3


def test_legacy_completed_response_gate_survives_prompt_fix_and_retry(tmp_path):
    from copy import deepcopy
    from group152_provider import response as fixture, ACCEPT
    from backend.runtime_v3.group_planning import pending
    from backend.runtime_v3.remote_semantics import RESPONSE_JSON_INSTRUCTION, same_extraction_context
    repo, client, sid = setup(tmp_path)
    joined = client.post(f'/api/saves/{sid}/phone', json=dict(revision=repo.get_save(sid)['revision'],
        command=dict(action='join', conversation_id='qa-group', operation_id='gate-join', member_ids=['qa_timur','qa_oleg'])))
    assert joined.status_code == 200
    http = DeepSeekHTTP()
    http.answer = lambda body: fixture(body['messages'], bool(body.get('response_format')))
    turn = repo.begin_job(sid, 'Смотрю на дождь.', 'turn', config())
    run(repo, turn, http)
    assert repo.get_job(turn)['status'] == 'saved', repo.get_job(turn)['error']
    assert pending(repo.get_snapshot(sid)['world_state'], 'qa-group')
    read = client.post(f'/api/saves/{sid}/phone', json=dict(revision=repo.get_save(sid)['revision'],
        command=dict(action='read', conversation_id='qa-group', operation_id='gate-read')))
    assert read.status_code == 200
    with patch('engine.launch'):
        sent = client.post(f'/api/saves/{sid}/phone/dispatch', json=dict(
            revision=repo.get_save(sid)['revision'], config=config(), api_key=KEY,
            command=dict(action='send', operation_id='gate-answer', conversation_id='qa-group', content=ACCEPT)))
    assert sent.status_code == 200, sent.text
    jid = sent.json()['job']['id']; http.reject_semantic = True
    run(repo, jid, http)
    assert repo.get_job(jid)['status'] == 'error'
    job = repo.get_job(jid); frames = json.loads(job['context_json'])
    gate = next(f for f in frames if f['stage'] == 'remote_response_semantics')
    assert gate['accepted']
    current = deepcopy(gate['messages'])
    gate['messages'][0]['content'] = gate['messages'][0]['content'].replace(RESPONSE_JSON_INSTRUCTION, '')
    data = json.loads(gate['messages'][1]['content']); data.pop('example_json_output')
    gate['messages'][1]['content'] = json.dumps(data, ensure_ascii=False)
    assert same_extraction_context(gate['messages'], current, response_only=True)
    altered = deepcopy(gate['messages']); altered[1]['content'] += ' '
    assert not same_extraction_context(altered, current, response_only=True)
    assert not same_extraction_context(gate['messages'], current, response_only=False)
    repo.save_communication_context(jid, frames, json.loads(job['memory_before_json'] or job['before_json']))
    repo = Repository(repo.path); count = len(http.requests)
    with patch('engine.launch'):
        retried = client.post(f'/api/jobs/{jid}/retry', json={'config': config(), 'api_key': KEY})
    assert retried.status_code == 200
    run(repo, jid, http)
    assert repo.get_job(jid)['status'] == 'saved', repo.get_job(jid)['error']
    assert len(http.requests) == count + 1  # neither gate nor author is paid twice
    state = repo.get_snapshot(sid)['world_state']
    assert not pending(state, 'qa-group') and 'group152-meeting' in state['scheduled_events']
    assert len([e for e in state['remote_events'].values() if e['content'] == ACCEPT]) == 1
