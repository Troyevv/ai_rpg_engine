"""Canonical dossier projection is disposable and distinct from actor Knowledge."""
from copy import deepcopy
import json
import pytest
from fastapi.testclient import TestClient
from backend.api.app import create_app
from backend.runtime_v3.models import ObjectiveRelation
from backend.runtime_v3.dossier import personal_relations
from backend.runtime_v3.kinship import visible_relations
from backend.runtime_v3.selectors import ui_view
from test_life_social import state, snapshot, inform


@pytest.mark.parametrize('certainty', ['unknown', 'suspected', 'known'])
@pytest.mark.parametrize('kind', ['spouse', 'partner', 'engaged'])
def test_canon_independent_of_knowledge_and_observer(certainty, kind):
    s = state()
    inform(s, 'romance', ['a', 'b'], {'a': certainty})
    s['objective_relations']['romance'] = ObjectiveRelation(id='romance', kind=kind,
        source_id='a', target_id='b', fact_id='romance', evidence='PRIVATE EVIDENCE').model_dump()
    s['characters']['c']['location_id'] = 'home'
    s['camera']['present_character_ids'] = ['a', 'b', 'c']
    expected = personal_relations(s)
    for observer in ('a', 'b', 'c', None):
        s['camera']['controlled_actor_id'] = observer
        s['camera']['mode'] = 'actor' if observer else 'observer'
        before = deepcopy(s)
        view = ui_view(snapshot(s))
        assert view['dossier_personal_relations'] == expected
        assert view['objective_relations'] == visible_relations(s, observer)
        assert ('romance' in [r['id'] for r in view['objective_relations']]) == (observer == 'a' and certainty != 'unknown')
        assert set(expected[0]) == {'id','kind','source_id','target_id','status','outcome','since','since_date','until','until_date'}
        assert 'PRIVATE' not in str(expected)
        assert s == before


def test_api_authoring_legacy_reload_and_next_turn(tmp_path):
    from devtools.narrative_test_world import build_fixture
    from test_narrative_test_world import ordinary_job
    from context_builder import build_context
    app = create_app(tmp_path/'game.sqlite', recover=False)
    repo = app.state.repository
    client = TestClient(app)
    source = build_fixture('ui-canonical-personal')
    workspace = client.post('/api/workspaces', json={'name':'Волковы'}).json()
    imported = client.post(f"/api/workspaces/{workspace['id']}/draft/import", json={
        'revision':workspace['revision'], 'format':'json', 'text':json.dumps(source)})
    assert imported.status_code == 200, imported.text
    draft = client.get(f"/api/workspaces/{workspace['id']}/draft?author=true").json()
    assert draft['state']['world']['objective_relations']['volkov-marriage']['since_date'] == '1999-06-12'
    confirmed = client.post(f"/api/workspaces/{workspace['id']}/draft/confirm", json={
        'revision':draft['revision'], 'version_id':draft['version_id']})
    assert confirmed.status_code == 200, confirmed.text
    sid = confirmed.json()['save']
    original = deepcopy(repo.get_snapshot(sid))
    # Existing saves contain only the canonical relation, never the new view.
    assert 'dossier_personal_relations' not in json.dumps(original)
    messages = build_context(original, [], 'Осмотреть комнату', 'turn', 32768, 2000)
    first = client.get(f'/api/saves/{sid}').json()['state']
    assert first['objective_relations'] == []
    assert first['dossier_personal_relations'][0]['id'] == 'volkov-marriage'
    assert repo.get_snapshot(sid) == original
    assert build_context(repo.get_snapshot(sid), [], 'Осмотреть комнату', 'turn', 32768, 2000) == messages
    assert 'dossier_personal_relations' not in str(messages)
    # GM's existing canonical context is not player knowledge: no new knowledge
    # is created by reading the directory, and the Narrative contract is identical.
    assert visible_relations(original['world_state'], 'qa_kirill') == []
    client = TestClient(create_app(tmp_path/'game.sqlite', recover=False))
    assert client.get(f'/api/saves/{sid}').json()['state']['dossier_personal_relations'] == first['dossier_personal_relations']
    for kind in ('start', 'turn'):
        ordinary_job(repo, sid, kind)
        fresh = client.get(f'/api/saves/{sid}').json()['state']
        assert fresh['dossier_personal_relations'] == first['dossier_personal_relations']
        assert fresh['objective_relations'] == []


def test_closed_phases_and_missing_endpoints_keep_exact_canon_without_mutation():
    s = state()
    for outcome in ('divorced', 'widowed', 'superseded'):
        s['objective_relations'][outcome] = ObjectiveRelation(id=outcome, kind='spouse',
            source_id='a', target_id='missing', status='closed', outcome=outcome,
            until_date='2005-01-01').model_dump()
    before = deepcopy(s)
    rows = personal_relations(s)
    assert [r['outcome'] for r in rows] == ['divorced','widowed','superseded']
    assert all(r['target_id'] == 'missing' for r in rows)
    assert s == before


@pytest.mark.parametrize('outcome', ['divorced', 'widowed'])
def test_hidden_closure_is_canonical_only_not_observer_knowledge(outcome):
    s = state()
    inform(s, 'marriage', ['a', 'b'], {'a':'known'})
    inform(s, 'closure', ['a', 'b'], {'b':'known'})
    s['objective_relations']['marriage'] = ObjectiveRelation(id='marriage', kind='spouse',
        source_id='a', target_id='b', fact_id='marriage', closure_fact_id='closure',
        status='closed', outcome=outcome, until=20).model_dump()
    view = ui_view(snapshot(s))
    assert view['dossier_personal_relations'][0]['outcome'] == outcome
    assert view['dossier_personal_relations'][0]['until'] == 20
    assert view['objective_relations'][0]['status'] == 'active'
    assert view['objective_relations'][0]['outcome'] == ''
    assert view['objective_relations'][0]['until'] is None


def test_old_snapshot_missing_optional_fields_is_projected_without_rewriting():
    s = state()
    s['objective_relations']['marriage'] = dict(id='marriage', kind='spouse', source_id='a', target_id='b')
    before = deepcopy(s)
    view = ui_view(snapshot(s))
    assert view['dossier_personal_relations'][0]['status'] == 'active'
    assert view['dossier_personal_relations'][0]['until'] is None
    assert view['objective_relations'] == []
    assert s == before
