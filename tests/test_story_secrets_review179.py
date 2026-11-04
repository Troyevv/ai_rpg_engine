"""Review #179: exercise trust and disclosure boundaries through real HTTP/SQLite."""
import json
from copy import deepcopy
from threading import Event
import pytest
from fastapi.testclient import TestClient
from backend.api.app import create_app
from backend.runtime_v3.models import Fact, Knowledge, WorldHistoryV3
from backend.runtime_v3.repository import append_history
from devtools.narrative_test_world import load_fixture


@pytest.fixture
def game(tmp_path):
    app=create_app(tmp_path/'review.sqlite',recover=False)
    repo=app.state.repository
    seed=load_fixture(repo,'phone')
    return repo,TestClient(app),seed


def persist(repo,sid,snap,batch=None):
    with repo.connect() as db:
        if batch: snap['history_head']=append_history(db,snap.get('history_head'),batch)
        db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snap),sid))


@pytest.mark.parametrize('status',['suspected','known','refuted','outdated','superseded','unknown'])
@pytest.mark.parametrize('existence',['hidden','discoverable'])
def test_secret_status_api_reload_and_actor_switch(game,status,existence):
    repo,client,seed=game;sid=seed['save'];snap=repo.get_snapshot(sid);s=snap['world_state']
    a,b='qa_kirill','qa_vera'
    s['facts']['review-secret']=Fact(id='review-secret',text='CANONICAL_TRUTH_179',visibility='secret',
        story_secret=True,secret_subject_ids=[b],secret_existence=existence).model_dump()
    s['knowledge'][a+':review-secret']=Knowledge(actor_id=a,fact_id='review-secret',status=status,
        evidence='CANONICAL_EVIDENCE_179',source_event_id='review-source',
        confirmed_once=status in ('refuted','outdated','superseded')).model_dump()
    s['knowledge'][b+':review-secret']=Knowledge(actor_id=b,fact_id='review-secret',status='known',evidence='OTHER_MIND_179').model_dump()
    snap['campaign'].setdefault('sections',{})['knowledge']='RAW_AUTHOR_179'
    snap['character_cards'][0]['fields']['Тайны']='RAW_CARD_179'
    batch=WorldHistoryV3().to_dict()
    batch['events']=[dict(id='review-source',text='CANONICAL_EVENT_179',evidence='CANONICAL_EVENT_EVIDENCE_179',
        participants=[a,b],witnesses=[a],fact_ids=['review-secret'],turn_id=s['meta']['turn_id'],
        recorded_minute=s['meta']['world_time'],player_observed=True)]
    persist(repo,sid,snap,batch)
    for current in (client,TestClient(create_app(repo.path,recover=False))):
        response=current.get(f'/api/saves/{sid}');assert response.status_code==200,response.text
        view=response.json()['state']
        for marker in ('OTHER_MIND_179','RAW_AUTHOR_179','RAW_CARD_179'):assert marker not in response.text
        for marker in ('CANONICAL_TRUTH_179','CANONICAL_EVIDENCE_179','CANONICAL_EVENT_179','CANONICAL_EVENT_EVIDENCE_179'):
            assert (marker in response.text)==(status=='known')
        if status!='known':
            assert 'review-secret' not in view['world']['facts']
            assert a+':review-secret' not in view['world']['knowledge']
            slots=view['story_secrets']['personal'].get(b,[])
            assert len(slots)==(1 if existence=='discoverable' else 0)
            assert all(set(row)=={'id','status'} for row in slots)
        author=current.get(f'/api/saves/{sid}/author-state').json()['snapshot']
        assert author['world_state']['knowledge'][a+':review-secret']['status']==status
        assert author['world_state']['knowledge'][a+':review-secret']['evidence']=='CANONICAL_EVIDENCE_179'
    revision=client.get(f'/api/saves/{sid}').json()['revision']
    switched=client.post(f'/api/saves/{sid}/protagonist',json=dict(revision=revision,operation_id='review-switch-179',operation='temporary',actor_id=b))
    assert switched.status_code==200,switched.text
    response=client.get(f'/api/saves/{sid}')
    assert 'CANONICAL_TRUTH_179' in response.text and 'OTHER_MIND_179' in response.text
    assert 'CANONICAL_EVIDENCE_179' not in response.text


def test_memory_internal_compaction_preserves_canonical_and_reload(game):
    from backend.services.memory import compact
    repo,client,seed=game;sid=seed['save'];snap=repo.get_snapshot(sid)
    snap['memory']=dict(id='memory179',summary='GM_ONLY_179',through_sequence=10,per_actor={
        'qa_kirill':dict(summary='REMEMBERED_179',through_sequence=10),
        'qa_vera':dict(summary='OTHER_MEMORY_179',through_sequence=8)})
    before=deepcopy(snap)
    def unexpected(*args,**kwargs):raise AssertionError('No work needs a provider call')
    from test_narrative_test_world import CONFIG
    compacted=compact(repo,{},snap,[],CONFIG,unexpected,Event())
    assert compacted['memory']==before['memory']
    assert snap==before
    persist(repo,sid,compacted)
    current=TestClient(create_app(repo.path,recover=False))
    response=current.get(f'/api/saves/{sid}')
    assert 'REMEMBERED_179' in response.text
    assert 'GM_ONLY_179' not in response.text and 'OTHER_MEMORY_179' not in response.text
    assert current.get(f'/api/saves/{sid}/author-state').json()['snapshot']['memory']==before['memory']


def test_history_aliases_do_not_leak_but_recorded_prose_survives(game):
    from test_narrative_test_world import ordinary_job, NARRATIVE, CONFIG
    from context_builder import build_context
    repo,client,seed=game;sid=seed['save']
    ordinary_job(repo,sid,'start')
    snap=repo.get_snapshot(sid);s=snap['world_state'];actor=s['camera']['controlled_actor_id']
    s['facts']['secret179']=Fact(id='secret179',text='ALIAS_TRUTH_179',story_secret=True,visibility='public').model_dump()
    s['knowledge'][actor+':secret179']=Knowledge(actor_id=actor,fact_id='secret179',status='suspected',evidence='ALIAS_EVIDENCE_179').model_dump()
    persist(repo,sid,snap)
    with repo.connect() as db:
        row=db.execute('SELECT id,changes_json FROM turns WHERE save_id=? ORDER BY sequence DESC LIMIT 1',(sid,)).fetchone()
        changes=json.loads(row['changes_json'])
        changes.update(world_delta={'facts':[s['facts']['secret179']]},facts=[dict(s['facts']['secret179'],known_by=[actor])],
            events=[dict(id='alias-event',text='ALIAS_EVENT_179',fact_ids=['secret179'],witnesses=[actor])])
        original=json.dumps(changes)
        db.execute('UPDATE turns SET changes_json=? WHERE id=?',(original,row['id']))
    for current in (client,TestClient(create_app(repo.path,recover=False))):
        r=current.get(f'/api/saves/{sid}');assert r.status_code==200
        assert all(marker not in r.text for marker in ('ALIAS_TRUTH_179','ALIAS_EVIDENCE_179','ALIAS_EVENT_179'))
        assert NARRATIVE in r.json()['turns'][-1]['assistant_text']
        records=r.json()['state']['world']['scene_records']
        assert any(NARRATIVE in v['narrative'] for v in records.values())
        playback=current.get(f"/api/saves/{sid}/playback/{row['id']}")
        assert playback.json()['narrative']==NARRATIVE
    # Read projection never rewrites canon or historical source payloads.
    with repo.connect() as db:assert db.execute('SELECT changes_json FROM turns WHERE id=?',(row['id'],)).fetchone()[0]==original
    messages=build_context(repo.get_snapshot(sid),repo.list_turns(sid),'Дальше','turn',32768,2000)
    assert NARRATIVE in json.dumps(messages,ensure_ascii=False)


def test_author_access_matches_existing_single_user_routes(game):
    repo,client,seed=game;sid=seed['save'];wid=seed['world']
    world=repo.get_world(wid)
    response=client.get(f'/api/worlds/{wid}')
    assert response.status_code==200 and response.json()['source_md']==world['source_md']
    workspace=repo.create_workspace('Author boundary 179');owner=workspace['id']
    repo.import_draft(owner,world['source_md'],workspace['revision'])
    author=client.get(f'/api/workspaces/{owner}/draft?author=true')
    assert author.status_code==200 and author.json()==repo.draft(owner,True)
    for route in (f'/api/worlds/{wid}',f'/api/workspaces/{owner}/draft?author=true',f'/api/saves/{sid}/author-state'):
        # No login/cookie/header grants "author" privileges: all clients already
        # have server-operator trust, including direct clients setting Origin.
        assert client.get(route,headers={'Origin':'https://untrusted.example'}).status_code==200
    blocked=client.post('/api/workspaces',json={'name':'forged'},headers={'Origin':'https://untrusted.example'})
    assert blocked.status_code==403  # CSRF mitigation, not read authorization.
    assert client.get(f'/api/saves/{sid}/author-state').json()['snapshot']==repo.get_snapshot(sid)
