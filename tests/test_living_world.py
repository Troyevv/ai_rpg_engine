"""Persisted v2 corpus -> one-time migration -> two real v3 commits and reloads."""
from pathlib import Path
import json
import pytest
from storage import Storage
from test_engine import db,CONFIG,NARRATIVE
from test_runtime_v3_engine import raw_for,run
from backend.runtime_v3.models import assert_world_state_v3_invariants

CORPUS=Path(__file__).parent/'fixtures'/'runtime_v3_migration'


@pytest.mark.parametrize('path',sorted(CORPUS.glob('*.json')),ids=lambda p:p.stem)
def test_persisted_v2_save_migrate_play_reload_play(db,path):
    repo,_,sid=db;legacy=json.loads(path.read_text())['state']
    with repo.connect() as conn:
        conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(legacy),sid))
        conn.execute("DELETE FROM schema_migrations WHERE name='runtime_v3'")
    repo=Storage(repo.path);snapshot=repo.get_snapshot(sid);state=snapshot['world_state']
    assert state['meta']['schema_version']==3 and 'events' not in state and 'scenes' not in state
    for k in legacy['world']['knowledge'].values():
        if k['actor_id'] in state['characters'] and k['fact_id'] in state['facts']:
            assert state['knowledge'][k['actor_id']+':'+k['fact_id']]['status']==k['status']
    assert set(state['relationships'])==set(legacy['world']['relationships'])
    assert set(state['threads'])==set(legacy['world']['threads'])
    for step in range(2):
        job=repo.begin_job(sid,'' if step==0 else 'Продолжить','start' if step==0 else 'turn',CONFIG)
        assert len(run(repo,job,raw_for(snapshot)))==2
        assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
        snapshot=repo.get_snapshot(sid);assert_world_state_v3_invariants(snapshot['world_state'])
        repo=Storage(repo.path)
        assert repo.get_snapshot(sid)==snapshot
    with repo.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE name='runtime_v3'").fetchone()[0]==1


def test_missing_old_event_is_audit_only_not_current_knowledge_invariant(db):
    repo,_,sid=db;fixture=json.loads((CORPUS/'missing_knowledge_event.json').read_text())['state']
    with repo.connect() as conn:
        conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(fixture),sid))
        conn.execute("DELETE FROM schema_migrations WHERE name='runtime_v3'")
    repo=Storage(repo.path)
    assert any(w['code']=='history_provenance_incomplete' for w in repo.get_save(sid)['history_warnings'])
    assert_world_state_v3_invariants(repo.get_snapshot(sid)['world_state'])
