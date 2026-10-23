"""Interpretation is provenance, never an omniscient Runtime mutation."""
import json
import threading
from copy import deepcopy
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.usefixtures('legacy_generation_v5')
from test_api import api, REMOTE, wait_job
from backend.services.world_interpretation import accept, public_summary

BRIEF = 'Анна удочерила Миру. Только Анна знала это до вчерашнего дня; вчера Мира узнала. В пятницу в 06:00 Мира идёт с сумками к станции. Не решать за Миру.'


def span(text):
    start = BRIEF.index(text)
    return {'start': start, 'end': start + len(text), 'quote': text}


def interpretation():
    return {'entities': [
        {'key': 'anna', 'kind': 'character', 'name': 'Анна', 'spans': [span('Анна удочерила')]},
        {'key': 'mira', 'kind': 'character', 'name': 'Мира', 'tier': 'protagonist', 'spans': [span('Мира узнала')]},
    ], 'claims': [
        {'classification': 'explicit', 'section': 'family', 'field': 'adoption', 'subject_key': 'anna',
         'related_keys': ['mira'], 'description': 'Удочерение', 'spans': [span('Анна удочерила Миру.')]},
        {'classification': 'explicit', 'section': 'knowledge', 'field': 'discovery', 'holder_keys': ['mira'],
         'description': 'Мира узнала вчера', 'time_scope': 'вчера', 'spans': [span('вчера Мира узнала.')]},
        {'classification': 'explicit', 'section': 'opening', 'field': 'activity', 'subject_key': 'mira',
         'description': 'В пятницу в 06:00 Мира идёт с сумками к станции.',
         'spans': [span('В пятницу в 06:00 Мира идёт с сумками к станции.')]},
        {'classification': 'prohibition', 'section': 'setting', 'field': 'agency',
         'description': 'Не решать за Миру.', 'spans': [span('Не решать за Миру.')]},
        {'classification': 'open', 'section': 'setting', 'field': 'country', 'description': 'Страна не задана'},
    ]}


def test_exact_provenance_temporal_claims_and_unknowns():
    raw = interpretation()
    raw['entities'][0]['spans'][0].update(start=999, end=1000)
    plan = accept(raw, BRIEF, 'workspace', 1)
    assert plan['entities'][0]['spans'][0] == span('Анна удочерила')
    assert plan['claims'][1]['holder_ids'] == [plan['entities'][1]['id']]
    assert plan['claims'][1]['time_scope'] == 'вчера'
    assert plan['claims'][1]['visibility'] == 'author'
    assert plan['claims'][4]['value'] is None
    assert len(plan['fixed_claim_ids']) == 4
    assert 'удочер' not in json.dumps(public_summary(plan), ensure_ascii=False)
    assert raw['entities'][0]['spans'][0]['start'] == 999


def test_id_stability_across_reordering_and_source_revision():
    first = accept(interpretation(), BRIEF, 'workspace', 1)
    raw = interpretation(); raw['entities'].reverse()
    second = accept(raw, 'Новый пролог. ' + BRIEF, 'workspace', 2, first)
    assert {e['name']: e['id'] for e in first['entities']} == {e['name']: e['id'] for e in second['entities']}
    assert first['brief'] == BRIEF
    assert first['claims'][0]['id'] != second['claims'][0]['id']
    assert accept(interpretation(), BRIEF, 'other-workspace', 1)['entities'][0]['id'] != first['entities'][0]['id']


@pytest.mark.parametrize('mutation', ['unknown_holder', 'unknown_subject', 'unknown_relation', 'invented_quote', 'missing_span', 'duplicate_key'])
def test_invalid_interpretation_rejected(mutation):
    raw = interpretation()
    if mutation == 'unknown_holder': raw['claims'][1]['holder_keys'] = ['outsider']
    if mutation == 'unknown_subject': raw['claims'][0]['subject_key'] = 'outsider'
    if mutation == 'unknown_relation': raw['claims'][0]['related_keys'] = ['outsider']
    if mutation == 'invented_quote': raw['claims'][0]['spans'][0]['quote'] = 'Мира родилась в Москве'
    if mutation == 'missing_span': raw['claims'][0]['spans'] = []
    if mutation == 'duplicate_key': raw['entities'].append(deepcopy(raw['entities'][0]))
    with pytest.raises(ValueError): accept(raw, BRIEF, 'workspace', 1)


def submit(client, wid, revision=0):
    response = client.post(f'/api/workspaces/{wid}/draft/generate', json={
        'task': 'interpret', 'text': BRIEF, 'revision': revision, 'config': REMOTE, 'api_key': 'interpret-key'})
    assert response.status_code == 200, response.text
    return response.json()['id']


def test_interpretation_is_journaled_without_draft_mutation_or_public_spoilers(api):
    client, app = api
    wid = client.post('/api/workspaces', json={'name': 'Семья'}).json()['id']
    path = f'/api/workspaces/{wid}/draft'
    for revision in (0, 1):
        with patch('backend.services.preparation.chat_stream', return_value=iter([json.dumps(interpretation())])):
            jid = submit(client, wid, revision)
            job = wait_job(client, jid)
            assert job['status'] == 'saved', job
            assert job['narrative'] == ''
        plan = client.get(path + '/interpretation?author=true').json()['plan']
        assert plan['constraint_revision'] == revision + 1
        assert 'Мира' not in json.dumps(client.get(path + '/interpretation').json(), ensure_ascii=False)
        assert client.get(path).json()['state'] is None
    with app.state.repository.connect() as db:
        versions = db.execute("SELECT content FROM document_versions WHERE kind='world_interpretation' AND owner=? ORDER BY id", (wid,)).fetchall()
        assert [json.loads(row[0])['constraint_revision'] for row in versions] == [1, 2]
        assert 'interpret-key' not in '\n'.join(db.iterdump())
    with patch('backend.services.preparation.chat_stream', return_value=iter(['{"bad": true}'])):
        failed = wait_job(client, submit(client, wid, 2))
        assert failed['status'] == 'error'
    assert client.get(path + '/interpretation?author=true').json()['plan'] == plan


def test_cancel_discards_late_interpretation(api):
    client, app = api
    wid = client.post('/api/workspaces', json={'name': 'Семья'}).json()['id']
    entered, release = threading.Event(), threading.Event()
    def stream(**kwargs):
        entered.set(); release.wait(5)
        yield json.dumps(interpretation())
    with patch('backend.services.preparation.chat_stream', side_effect=stream):
        jid = submit(client, wid)
        assert entered.wait(2)
        assert client.post(f'/api/jobs/{jid}/stop').status_code == 200
        release.set()
        assert wait_job(client, jid)['status'] == 'stopped'
    assert client.get(f'/api/workspaces/{wid}/draft/interpretation?author=true').json() is None
