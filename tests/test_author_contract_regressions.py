"""Schema/validator contract regressions; no provider calls."""
import pytest

pytestmark = pytest.mark.usefixtures("captured_authoring_v1")
from backend.services import world_authoring as a
from test_api import api


def test_analysis_schema_requires_explicit_origin():
    schema = a.AuthorBrief.model_json_schema()
    seed = schema['$defs']['Seed']
    assert seed['properties']['origin'].get('const') == 'explicit'
    assert 'origin' in seed['required']
    payload = {'entities': [dict(key='ilya', name='Илья', kind='character', origin='explicit')]}
    assert a.AuthorBrief.model_validate(payload).entities[0].origin == 'explicit'


@pytest.mark.parametrize('length', [201, 3001, 12000])
def test_plan_prose_survives_page_and_aggregate_without_truncation(length):
    text = 'Я' * length
    payload = dict(records=[dict(section='characters', key='ilya', summary=text)], complete=True)
    assert 'maxLength' not in a.PlanPage.model_json_schema()['$defs']['PageRecord']['properties']['summary']
    page = a.PlanPage.model_validate(payload)
    assert page.records[0].summary == text
    record = a.PlannedRecord.model_validate(page.records[0].model_dump())
    assert record.summary == text


def test_plan_technical_bounds_remain_enforced():
    row = dict(section='characters', key='ilya', summary='Описание')
    with pytest.raises(ValueError):
        a.PlanPage.model_validate(dict(records=[row] * 33, complete=True))
    with pytest.raises(ValueError):
        a.PageRecord.model_validate({**row, 'summary': ''})
    with pytest.raises(ValueError):
        a.PageRecord.model_validate({**row, 'key': 'bad/reference'})


def test_long_plan_summary_reaches_start_and_reload(api):
    import json
    from unittest.mock import patch
    from test_api import REMOTE
    from test_world_generation import wait
    from test_world_authoring import institute, provider
    from test_temporal_guard import run
    from backend.repositories.preparation import Repository

    client, app = api
    repo = app.state.repository
    document = institute()
    calls = []
    base = provider(document, calls)
    text = 'Авторские подробности сохраняются без обрезки. ' * 90

    def stream(**kwargs):
        payload = json.loads(''.join(base(**kwargs)))
        if '\nStage: author_plan_page' in kwargs['messages'][0]['content']:
            for row in payload['records']:
                row['summary'] = text
        yield json.dumps(payload, ensure_ascii=False)

    wid = client.post('/api/workspaces', json={'name': 'Long planning notes'}).json()['id']
    with patch('backend.services.preparation.chat_stream', side_effect=stream):
        response = client.post(f'/api/workspaces/{wid}/draft/generate', json=dict(
            task='world_staged', text='Молодой инженер начинает работать в НИИ.', revision=0,
            creation={'cast_preset': 'custom', 'core_npcs': 1, 'secondary_npcs': 0},
            config={**REMOTE, 'context_length': 131072, 'max_tokens': 2000}, api_key='fixture'))
        assert response.status_code == 200, response.text
        jid = response.json()['id']
        assert wait(client, jid)['status'] == 'saved'
    plan = repo.generation_resources(jid, ['author_plan'])['author_plan']
    assert all(row['summary'] == text for row in plan['records'])
    draft = repo.draft(wid, True)
    sid = repo.confirm_draft(wid, draft['revision'], draft['version_id'])['save']
    assert run(repo, sid, 1, kind='start')[0]['status'] == 'saved'
    assert run(repo, sid, 1)[0]['status'] == 'saved'
    assert Repository(repo.path).get_snapshot(sid) == repo.get_snapshot(sid)



def test_live_empty_complete_plan_and_unanchored_opening_rejected_before_checkpoint():
    from backend.services.world_authoring_pipeline import validate_creative_page
    from test_world_authoring import institute
    with pytest.raises(ValueError, match='empty world'):
        validate_creative_page(a.PlanPage.model_validate({'complete': True}).model_dump(), {})
    opening = institute()['opening']
    opening['time'] = {'description': 'Первое утро, точное время автор не указал'}
    page = a.PlanPage.model_validate(dict(opening=opening, complete=True,
        records=[dict(section='characters', key='newcomer', summary='Приезжий')])).model_dump()
    with pytest.raises(ValueError, match='exact clock'):
        validate_creative_page(page, {})
    # A closing page with no additional records is valid after earlier pages.
    assert validate_creative_page(a.PlanPage.model_validate({'complete':True}).model_dump(),
                                  {'characters/newcomer':{}})['complete']


def test_plan_page_schema_matches_scheduled_capacity():
    from backend.services.author_budget import schema_for
    original = a.PlanPage.model_json_schema()
    for size in (1, 4, 24, 32):
        schema = schema_for('author_plan_page', original, {'max_records': size})
        assert schema['properties']['records']['maxItems'] == size
    assert original['properties']['records']['maxItems'] == 32


def test_provider_opening_time_contract_is_distinct_from_historical_time():
    from backend.services.author_budget import schema_for
    source = a.PlanPage.model_json_schema()
    schema = schema_for('author_plan_page', source, {'max_records':24})
    opening = schema['$defs']['OpeningTime']
    assert opening['required'] == ['clock']
    assert opening['properties']['period']['type'] == 'null'
    assert opening['properties']['day_offset']['type'] == 'null'
    assert 'Friday=4' in opening['properties']['weekday']['description']
    document = a.Document.model_json_schema()
    assert schema_for('author_document', document, {})['$defs']['Time'] == document['$defs']['Time']
    assert 'OpeningTime' not in source['$defs']


def test_overfull_plan_response_is_paginated_losslessly_with_hard_bounds():
    from backend.services.world_authoring_pipeline import partition_plan_page
    rows = [dict(section='locations', key=f'place_{i}', summary='Описание ' * 100) for i in range(40)]
    first = partition_plan_page({'records':rows, 'complete':True}, 24, {})
    assert len(first['records']) == 24 and first['complete'] is False
    registry = {r['section']+'/'+r['key']:r for r in first['records']}
    second = partition_plan_page(first['continuation'], 24, registry)
    assert len(second['records']) == 16 and second['complete'] and second['continuation'] is None
    assert [r['key'] for r in first['records']+second['records']] == [r['key'] for r in rows]
    assert all(r['summary']==rows[0]['summary'] for r in first['records']+second['records'])
    with pytest.raises(ValueError):
        partition_plan_page({'records':rows+[rows[0]], 'complete':True}, 24, {})
    with pytest.raises(ValueError):
        partition_plan_page({'records':rows*76, 'complete':True}, 24, {})
    from backend.services.author_budget import schema_for
    assert 'continuation' not in schema_for('author_plan_page',a.PlanPage.model_json_schema(),{'max_records':24})['properties']


def test_overfull_response_checkpoints_resume_without_requerying_plan(api):
    import json
    from unittest.mock import patch
    from test_api import REMOTE
    from test_world_generation import wait
    from test_world_authoring import institute, provider
    client, app = api
    document = institute()
    document['locations'].extend(dict(key=f'park_{i}',name=f'Парк {i}') for i in range(35))
    calls = []
    fail_batch = [True]
    base = provider(document, calls)
    def stream(**kw):
        if '\nStage: author_batch' in kw['messages'][0]['content'] and fail_batch[0]:
            fail_batch[0] = False
            raise RuntimeError('Simulated interruption after durable planning pages')
        if '\nStage: author_plan_page' in kw['messages'][0]['content']:
            kw['messages'][0]['content'] = kw['messages'][0]['content'].replace('Stage: author_plan_page','Stage: author_plan')
            payload = json.loads(''.join(base(**kw)))
            payload['complete'] = True
            yield json.dumps(payload, ensure_ascii=False)
        else:
            yield from base(**kw)
    wid = client.post('/api/workspaces',json={'name':'Overflow pages'}).json()['id']
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        response = client.post(f'/api/workspaces/{wid}/draft/generate',json=dict(task='world_staged',
            text='Инженер начинает работать в НИИ.',revision=0,
            config={**REMOTE,'context_length':131072,'max_tokens':2000},api_key='fixture'))
        jid=response.json()['id']
        stopped=wait(client,jid)
        assert stopped['status']=='failed'
        version=app.state.repository.inspect_generation_checkpoint(jid,'author_plan_page_0_0',True)['artifact_version']
        resumed=client.post('/api/jobs/'+jid+'/generation/resume',json=dict(revision=stopped['generation']['revision'],api_key='fixture'))
        assert resumed.status_code==200
        assert wait(client,jid)['status']=='saved'
        assert app.state.repository.inspect_generation_checkpoint(jid,'author_plan_page_0_0',True)['artifact_version']==version
    repo=app.state.repository
    plan=repo.generation_resources(jid,['author_plan'])['author_plan']
    assert {f'park_{i}' for i in range(35)} <= {r['key'] for r in plan['records']}
    assert calls.count('author_plan') == 1
    first=repo.inspect_generation_checkpoint(jid,'author_plan_page_0_0',True)
    assert first['artifact']['continuation']['records']
    second=repo.inspect_generation_checkpoint(jid,'author_plan_page_0_1',True)
    assert len(first['artifact']['records']) == len(second['artifact']['records']) == 2


def test_exact_unique_plan_references_normalize_without_guessing():
    from backend.services.world_authoring_pipeline import normalize_plan_references
    rows=[dict(section='characters',key='ilya',references=[]),dict(section='facts',key='secret',references=['ilya'])]
    assert normalize_plan_references(rows)[1]['references']==['characters/ilya']
    assert rows[1]['references']==['ilya']
    with pytest.raises(ValueError,match='неоднозначная'):
        normalize_plan_references(rows+[dict(section='locations',key='ilya',references=[])])
    rows[1]['references']=['missing']
    with pytest.raises(ValueError,match='Неизвестная'):
        normalize_plan_references(rows)


def test_live_analysis_names_resolve_only_exact_unique_entities():
    from backend.services.world_authoring_pipeline import normalize_brief_references
    raw={'entities':[dict(key='nils',name='Нильс',kind='character',origin='explicit')],
         'observations':[dict(section='characters',text='Нильс — андроид.',entities=['Нильс'])]}
    result=a.AuthorBrief.model_validate(normalize_brief_references(raw))
    assert result.observations[0].entities==['nils']
    assert raw['observations'][0]['entities']==['Нильс']
    raw['entities'].append(dict(key='other',name='Нильс',kind='character',origin='explicit'))
    with pytest.raises(ValueError):a.AuthorBrief.model_validate(normalize_brief_references(raw))
    raw['observations'][0]['entities']=['Нильса']
    with pytest.raises(ValueError):a.AuthorBrief.model_validate(normalize_brief_references(raw))
