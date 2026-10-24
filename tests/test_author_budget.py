"""Offline regression: UI/API settings reach the first bounded provider request."""
import json
from unittest.mock import patch
import pytest
from context_builder import estimate
from backend.services import author_budget as b, world_authoring as a
from backend.services.world_authoring_pipeline import capture, source_sections
from backend.services.world_authoring_compiler import CompileError
from test_api import api, REMOTE
from test_world_generation import wait
from test_world_authoring import provider, institute

SHORT = 'Молодой парень переезжает в большой город, устраивается в НИИ и пытается начать новую жизнь.'
DETAILED = '\n'.join(f'Персонаж {i}: инженер; внешность, характер и история заданы автором. Вчера он переехал в город.' for i in range(30))


@pytest.mark.parametrize('context', [8192, 32768, 65536])
@pytest.mark.parametrize('maximum', [256, 2000, 6000, 12000, 32000])
@pytest.mark.parametrize('source', [SHORT, DETAILED], ids=['short', 'detailed'])
def test_api_starts_first_analysis_with_supported_settings(api, context, maximum, source):
    client, app = api
    wid = client.post('/api/workspaces', json={'name':'Budget regression'}).json()['id']
    seen = []
    def stream(**kw):
        seen.append(kw)
        raise RuntimeError('intentional stop after capturing first request, no network')
        yield
    with patch('backend.services.preparation.chat_stream', side_effect=stream):
        response = client.post(f'/api/workspaces/{wid}/draft/generate', json=dict(
            task='world_staged', text=source, revision=0,
            config={**REMOTE, 'context_length':context, 'max_tokens':maximum}, api_key='fixture'))
        assert response.status_code == 200, response.text
        jid = response.json()['id']; wait(client, jid)
    assert len(seen) == 1
    request = seen[0]
    assert 'Stage: author_brief' in request['messages'][0]['content']
    assert '"title":"AuthorBrief"' in request['messages'][0]['content']
    assert '"title":"Document"' not in request['messages'][0]['content']
    assert request['provider'] == 'deepseek'
    assert 0 < request['max_tokens'] <= maximum
    assert estimate(request['messages']) + request['max_tokens'] + b.MARGIN <= context
    if source == SHORT:
        assert json.loads(request['messages'][1]['content'])['source'] == source
        assert request['max_tokens'] < 2000
    job = app.state.repository.preparation_job(jid)
    assert json.loads(job['config_json'])['max_tokens'] == maximum
    assert app.state.repository.generation_resources(jid, ['brief'])['brief'] == source
    logs = app.state.repository.request_log(job_id=jid)
    assert logs[0]['max_tokens'] == request['max_tokens']


@pytest.mark.parametrize('context', [8192, 32768, 65536])
@pytest.mark.parametrize('maximum', [2000, 12000, 32000])
def test_small_window_completes_all_stages(api, maximum, context):
    client, app = api; calls=[]; seen=[]
    base = provider(institute(), calls)
    def stream(**kw):
        seen.append(kw)
        assert estimate(kw['messages']) + kw['max_tokens'] + b.MARGIN <= context
        yield from base(**kw)
    wid = client.post('/api/workspaces', json={'name':'Small window'}).json()['id']
    with patch('backend.services.preparation.chat_stream', side_effect=stream):
        response = client.post(f'/api/workspaces/{wid}/draft/generate', json=dict(
            task='world_staged', text=SHORT, revision=0,
            creation={'cast_preset':'custom','core_npcs':1,'secondary_npcs':0},
            config={**REMOTE, 'context_length':context,'max_tokens':maximum}, api_key='fixture'))
        assert response.status_code == 200, response.text
        done = wait(client, response.json()['id'])
    assert done['status'] == 'saved', done
    assert 'author_batch' in calls or 'author_document' in calls


def test_model_window_and_diagnostic_are_separate_from_user_ceiling():
    config = dict(provider='deepseek', model='deepseek-flash', context_length=65536, max_tokens=32000)
    with patch.dict(b.DEEPSEEK_LIMITS, {'deepseek-flash':(8192,4096)}):
        assert b.limits(config) == (8192,4096,8192)
        # Capture respects the effective window without changing user settings.
        assert capture(SHORT, config)['brief'] == SHORT
    messages = [dict(content='a' * 20000)]
    with pytest.raises(CompileError) as error:
        b.check(messages, 1024, 8192, 'author_brief', user_context=65536, model_context=8192)
    message = str(error.value)
    assert str(estimate(messages)+1024+b.MARGIN) in message
    for number in ('8192','65536','1024','512'): assert number in message
    assert 'UTF-8' in message
    assert b.limits(dict(config,provider='local'),{'config':{'context_length':4096}})[0] == 4096
    assert b.limits(dict(config,provider='compatible'))[2] is None


def test_source_schema_size_and_lossless_split():
    schema = a.AuthorBrief.model_json_schema()
    assert len(json.dumps(schema,ensure_ascii=False,separators=(',',':')).encode()) < 2000
    original = DETAILED * 15
    for context in (8192,32768,65536):
        sections = source_sections(original,context,12000,schema)
        assert len(sections)>1 and ''.join(sections)==original
        for part in sections:
            data=dict(source=part,known_entities=[],creation_settings={})
            prompt=dict(interpretation=a.ANALYSIS_RULES,schemas={'author_brief':schema})
            b.check(b.messages(prompt,'author_brief',data),b.response_budget('author_brief',data,12000,context),context,'author_brief')
    with pytest.raises(CompileError,match='доступно 1024'):
        source_sections(SHORT,1024,12000,schema)


def test_api_rejects_actual_model_overflow_before_provider(api):
    client, app = api
    wid = client.post('/api/workspaces', json={'name':'Real window'}).json()['id']
    with patch.dict(b.DEEPSEEK_LIMITS, {'deepseek-flash':(1024,4096)}), patch('backend.services.preparation.chat_stream') as stream:
        response = client.post(f'/api/workspaces/{wid}/draft/generate', json=dict(
            task='world_staged',text=SHORT,revision=0,
            config={**REMOTE,'model':'deepseek-flash','context_length':65536,'max_tokens':12000},api_key='fixture'))
    assert response.status_code == 409
    assert 'доступно 1024' in response.text
    assert '65536' in response.text
    stream.assert_not_called()


def test_first_request_reaches_sdk_with_stage_budget(api):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    import llm
    client, app = api
    wid = client.post('/api/workspaces', json={'name':'SDK boundary'}).json()['id']
    sdk = MagicMock()
    chunk = SimpleNamespace(usage=None, choices=[SimpleNamespace(
        finish_reason='stop', delta=SimpleNamespace(content='{"entities":[],"observations":[],"ambiguities":[]}'))])
    stream = MagicMock(); stream.__iter__.return_value=iter([chunk])
    sdk.chat.completions.create.side_effect=[stream,RuntimeError('intentional next-stage stop')]
    with patch('backend.services.preparation.chat_stream', llm.chat_stream), patch('llm.OpenAI',return_value=sdk):
        response = client.post(f'/api/workspaces/{wid}/draft/generate', json=dict(
            task='world_staged',text=SHORT,revision=0,
            config={**REMOTE,'context_length':8192,'max_tokens':12000},api_key='fixture'))
        assert response.status_code == 200
        wait(client,response.json()['id'])
    sent = sdk.chat.completions.create.call_args_list[0].kwargs
    assert sent['max_tokens'] < 2000
    assert sent['response_format'] == {'type':'json_object'}
    assert 'context_length' not in sent  # service budget, not an API window override
    assert estimate(sent['messages']) + sent['max_tokens'] + b.MARGIN <= 8192
    cp=app.state.repository.inspect_generation_checkpoint(response.json()['id'],'author_source_0',True)
    assert cp['status']=='completed'


@pytest.mark.parametrize('detailed', [False, True], ids=['short', 'detailed'])
def test_default_cast_direct_document_edit_start_turn_reload(api, detailed):
    """Exercise real services; provider output is controlled, not live acceptance."""
    from test_world_authoring import family
    from test_temporal_guard import run
    from backend.repositories.preparation import Repository
    client, app = api
    document = family() if detailed else institute()
    source = ('Семейная история. Артём — приёмный сын Сергея. Он упрям, болезненно '
              'реагирует на опеку, но умеет признавать ошибки. Сергей владеет группой '
              'компаний с дочерним банком. Вчера вечером Артём узнал об усыновлении. '
              'Сергей знал об этом раньше. Это секрет, остальные не узнают его автоматически. '
              'Начало в пятницу в 06:00, дома. Не решай за Артёма и не придумывай ему '
              'обязательств. Сохрани различие между биологическим и приёмным родством. '
              'Раскрой характеры, внешность, голоса и обстановку; дальнейший сюжет открыт.'
              if detailed else SHORT)
    calls, requests = [], []
    base = provider(document, calls)
    def stream(**kw):
        requests.append(kw)
        assert estimate(kw['messages']) + kw['max_tokens'] + b.MARGIN <= 32768
        if '\nStage: author_brief' in kw['messages'][0]['content']:
            calls.append('author_brief')
            yield json.dumps(dict(entities=[dict(key=p['key'], name=p['name'],
                kind='character', origin='explicit') for p in document['characters']],
                observations=[], ambiguities=[]))
        else:
            assert json.loads(kw['messages'][-1]['content'])['original_source'] == source
            yield from base(**kw)
    wid = client.post('/api/workspaces', json={'name':'Direct creation'}).json()['id']
    with patch('backend.services.preparation.chat_stream', side_effect=stream):
        response = client.post(f'/api/workspaces/{wid}/draft/generate', json=dict(
            task='world_staged', text=source, revision=0,
            config={**REMOTE, 'context_length':32768, 'max_tokens':8192}, api_key='fixture'))
        assert response.status_code == 200, response.text
        done = wait(client, response.json()['id'])
    assert done['status'] == 'saved', done
    assert calls == ['author_brief', 'author_document']
    assert requests[-1]['max_tokens'] == 8192
    repo = app.state.repository
    draft = repo.draft(wid, True)
    repo.edit_draft(wid, draft['revision'], 'patch', kind='campaign', field='title', value='Моя история')
    edited = repo.draft(wid, True)
    sid = repo.confirm_draft(wid, edited['revision'], edited['version_id'])['save']
    initial = repo.get_snapshot(sid)
    assert initial['campaign']['campaign']['title'] == 'Моя история'
    assert initial['campaign']['initial_world']['brief'] == source
    assert run(repo, sid, 0, kind='start')[0]['status'] == 'saved'
    assert run(repo, sid, 1)[0]['status'] == 'saved'
    saved = repo.get_snapshot(sid)
    reloaded = Repository(repo.path)
    assert reloaded.get_snapshot(sid) == saved
    assert saved['world_state']['knowledge'] == initial['world_state']['knowledge']
    assert run(reloaded, sid, 1)[0]['status'] == 'saved'


def test_captured_legacy_job_retains_paged_route(api):
    from backend.services import world_authoring_pipeline as pipeline
    client, app = api; calls=[]
    original_capture = pipeline.capture
    def legacy(*args, **kwargs):
        result = original_capture(*args, **kwargs)
        result['prompt'].pop('document_first')
        return result
    wid = client.post('/api/workspaces', json={'name':'Captured contract'}).json()['id']
    with patch.object(pipeline, 'capture', side_effect=legacy), patch(
            'backend.services.preparation.chat_stream', side_effect=provider(institute(), calls)):
        response = client.post(f'/api/workspaces/{wid}/draft/generate', json=dict(
            task='world_staged', text=SHORT, revision=0,
            config={**REMOTE, 'context_length':32768, 'max_tokens':8192}, api_key='fixture'))
        assert response.status_code == 200, response.text
        done = wait(client, response.json()['id'])
    assert done['status'] == 'saved', done
    assert 'author_plan_page' in calls and 'author_batch' in calls
    assert 'author_document' not in calls
