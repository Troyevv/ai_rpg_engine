"""Only structural v3 failures authorize a single extraction repair."""
import json
from unittest.mock import patch
import pytest
from storage import Storage
from test_engine import db,CONFIG,NARRATIVE
from test_player_agency import character_payload
from runtime_v3_fixture import execute
from backend.services.world_delta_errors import StructuralDeltaError


@pytest.mark.parametrize('secondary',[False,True])
def test_repair_reason_persists_restart_and_variant_switch(db,secondary):
    repo,_,sid=db;bad=character_payload({});bad['final_scene']['present_character_ids']=['missing']
    fixed=character_payload({'emotion':'боится'} if secondary else {})
    job=repo.begin_job(sid,'Я подхожу к окну.','start',CONFIG)
    assert len(execute(repo,job,bad,NARRATIVE,repaired=fixed))==3
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    original=repo.list_turns(sid)[0];repo=Storage(repo.path)
    first=repo.turn_diagnostics(sid)[0];reason=first['repairs'][0]
    assert reason['repair_error_code']=='unknown_character' and reason['stage']=='extraction_repair'
    assert bool(first['warnings'])==secondary and first['timing']['extraction_repair']>=0
    requests={r['stage']:r for r in first['requests']}
    assert json.loads(requests['extraction']['response_text'])==bad
    assert json.loads(requests['extraction_repair']['response_text'])==fixed
    replacement=repo.begin_job(sid,'','regenerate',CONFIG)
    assert len(execute(repo,replacement,character_payload({}),NARRATIVE))==2
    assert repo.turn_diagnostics(sid)[0]['repairs']==[]
    repo.select_variant(sid,original['id'],original['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.turn_diagnostics(sid)[0]['repairs']==[reason]


@pytest.mark.parametrize('error',[ValueError('validator bug'),StructuralDeltaError('unsafe','unsafe',repairable=False)])
def test_unexpected_or_unsafe_failure_never_calls_repair(db,error):
    repo,_,sid=db;before=repo.get_snapshot(sid);job=repo.begin_job(sid,'','start',CONFIG)
    with patch('engine.StateResolver.resolve',side_effect=error):
        assert len(execute(repo,job,character_payload({}),NARRATIVE))==2
    assert repo.get_job(job)['status']=='error'
    assert repo.get_snapshot(sid)==before and not repo.list_turns(sid)
    assert json.loads(repo.get_job(job)['repair_diagnostics_json'])==[]


def test_repair_exhaustion_cannot_commit_partial_changes(db):
    repo,_,sid=db;before=repo.get_snapshot(sid);bad=character_payload({'situation':'Изменено'})
    bad['final_scene']['location_id']='missing'
    job=repo.begin_job(sid,'','start',CONFIG)
    assert len(execute(repo,job,bad,NARRATIVE))==3
    assert repo.get_job(job)['status']=='error' and repo.get_snapshot(sid)==before


def test_saved_current_corruption_is_rejected_before_paid_request(db):
    repo,_,sid=db;state=repo.get_snapshot(sid)
    state['world_state']['characters']['character_1']['location_id']='missing'
    with repo.connect() as conn:conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(state),sid))
    with pytest.raises(StructuralDeltaError):repo.get_snapshot(sid)
    with pytest.raises(StructuralDeltaError):repo.get_save(sid)
    with pytest.raises(StructuralDeltaError):repo.begin_job(sid,'','start',CONFIG)
    assert repo.latest_job(sid) is None
