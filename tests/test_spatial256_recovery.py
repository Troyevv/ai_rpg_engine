"""Authored provider controls through production jobs; never real-model acceptance."""
import json
from copy import deepcopy
from unittest.mock import patch
import pytest
from test_api import api, wait_job
from test_runtime_handoff import REMOTE
from devtools.narrative_test_world import load_fixture
from test_narrative_test_world import ordinary_job
from backend.repositories.preparation import Repository

pytestmark=pytest.mark.extraction_v7


@pytest.mark.parametrize('version',[7,8])
def test_recovery_same_prose_new_contract_current_before_and_rollback(api, monkeypatch, version):
    monkeypatch.setattr('backend.runtime_v3.player_actions.EXTRACTION_VERSION',version)
    client,app=api;repo=app.state.repository;sid=load_fixture(repo)['save']
    with patch('backend.runtime_v3.player_actions.EXTRACTION_VERSION',5): ordinary_job(repo,sid,'start')
    before=repo.get_snapshot(sid);calls=[]
    prose='Персонаж спокойно осматривает комнату.'
    def stream(**kw):
        calls.append(kw)
        yield json.dumps(dict(scene=dict(elapsed_minutes=1),scene_steps=[])) if kw.get('response_format') else prose
    def submit(**values):
        r=client.post(f'/api/saves/{sid}/turns',json=dict(kind='turn',revision=repo.get_save(sid)['revision'],config=REMOTE,api_key='test-secret',**values))
        assert r.status_code==200,r.text
        return wait_job(client,r.json()['id'])
    with patch('engine.chat_stream',side_effect=stream): original=submit(text='Осматриваюсь.')
    assert original['status']=='saved',original['error']
    original=repo.get_job(original['id']);old=deepcopy(original)
    assert json.loads(original['config_json'])['_extraction_contract']==version
    assert len(calls)==2
    with repo.connect() as db:
        original_variant=dict(db.execute('select * from response_variants where job_id=?',(original['id'],)).fetchone())
    repo.rollback_last(sid,repo.get_save(sid)['revision']);assert repo.get_snapshot(sid)==before
    stale=client.post(f'/api/saves/{sid}/turns',json=dict(kind='turn',revision=original['revision'],config=REMOTE,api_key='test-secret',recovery_source_job_id=original['id']))
    assert stale.status_code==409
    assert repo.get_snapshot(sid)==before
    calls.clear()
    with patch('engine.chat_stream',side_effect=stream): recovered=submit(recovery_source_job_id=original['id'])
    assert recovered['status']=='saved',recovered['error']
    assert len(calls)==1 and calls[0].get('response_format')
    new=repo.get_job(recovered['id']);cfg=json.loads(new['config_json'])
    assert cfg['_narrative_recovery']['source_job_id']==original['id']
    assert new['narrative']==original['narrative']==prose
    assert new['before_json']==original['before_json']
    assert new['context_json'] and new['memory_before_json']
    assert repo.get_job(original['id'])==old
    assert Repository(repo.path).get_snapshot(sid)==repo.get_snapshot(sid)
    with repo.connect() as db:
        current=dict(db.execute('select * from turns where save_id=? order by sequence desc limit 1',(sid,)).fetchone())
        assert dict(db.execute('select * from response_variants where id=?',(original_variant['id'],)).fetchone())==original_variant
    assert current['node_id']==original_variant['node_id']
    corrected=repo.get_snapshot(sid)
    repo.select_variant(sid,current['id'],original_variant['id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==json.loads(json.loads(original_variant['payload'])['after_json'])
    repo.select_variant(sid,current['id'],current['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==corrected
    # Same old Narrative cannot be applied twice at a later story position.
    with patch('engine.chat_stream',side_effect=AssertionError('No paid retry')):
        r=client.post(f'/api/saves/{sid}/turns',json=dict(kind='turn',revision=repo.get_save(sid)['revision'],config=REMOTE,api_key='test-secret',recovery_source_job_id=original['id']))
    assert r.status_code==409
    repo.rollback_last(sid,repo.get_save(sid)['revision']);assert repo.get_snapshot(sid)==before
    with repo.connect() as db:
        assert db.execute('select count(*) from archived_turns where save_id=?',(sid,)).fetchone()[0]==2
        assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
