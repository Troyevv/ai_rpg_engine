import time
import pytest
from backend.repositories.preparation import Repository
from test_api import REMOTE


def new_run(tmp_path):
    repo=Repository(tmp_path/'checkpoints.sqlite3')
    workspace=repo.create_workspace('Checkpoint test')
    jid=repo.begin_preparation(workspace['id'],'draft_world','brief',REMOTE,0)
    repo.create_generation_run(jid,{'brief':'Secret source', 'constraint_revision':1})
    token=repo.claim_generation(jid)
    repo.plan_generation_units(jid,token,[
        dict(id='interpret',stage='interpret',inputs=['brief','constraint_revision'],outputs={'plan':''}),
        dict(id='setting',stage='setting',inputs=['plan'],outputs={'setting':''})])
    return repo,jid,token


def test_checkpoint_is_atomic_durable_and_not_public(tmp_path):
    repo,jid,token=new_run(tmp_path)
    assert repo.claim_generation(jid) is None
    assert repo.begin_generation_unit(jid,token,'interpret')
    vid=repo.commit_generation_unit(jid,token,'interpret',{'secret':'author-only claim'})
    assert not repo.begin_generation_unit(jid,token,'interpret')
    with pytest.raises(ValueError,match='running attempt'):
        repo.commit_generation_unit(jid,token,'interpret',{'secret':'late replacement'})
    reloaded=Repository(tmp_path/'checkpoints.sqlite3')
    assert reloaded.generation_resources(jid,['plan'])=={'plan':{'secret':'author-only claim'}}
    assert reloaded.generation_status(jid)['overall_progress']==1/8
    assert 'author-only' not in str(reloaded.generation_status(jid))
    with reloaded.connect() as db:
        assert db.execute("SELECT count(*) FROM document_versions WHERE kind='generation_checkpoint'").fetchone()[0]==1
        assert db.execute('SELECT status FROM preparation_attempts').fetchone()[0]=='completed'
        assert db.execute('SELECT artifact_id FROM preparation_units WHERE unit_id=?',('interpret',)).fetchone()[0]==vid


def test_pause_finishes_current_checkpoint_and_blocks_next_dispatch(tmp_path):
    repo,jid,token=new_run(tmp_path)
    repo.begin_generation_unit(jid,token,'interpret')
    assert repo.generation_control(jid,'pause')=='pause_requested'
    assert repo.generation_control(jid,'pause')=='pause_requested'
    with pytest.raises(ValueError): repo.begin_generation_unit(jid,token,'setting')
    repo.commit_generation_unit(jid,token,'interpret',{'entities':[]})
    assert not repo.generation_boundary(jid,token)
    assert repo.generation_control(jid,'resume')=='generating'
    assert repo.generation_control(jid,'resume')=='generating'
    second=repo.claim_generation(jid)
    assert second and second!=token
    assert not repo.begin_generation_unit(jid,second,'interpret')
    assert repo.begin_generation_unit(jid,second,'setting')
    with pytest.raises(ValueError,match='lease'): repo.commit_generation_unit(jid,token,'setting',{})


def test_cancel_rejects_late_provider_commit_but_keeps_good_checkpoint(tmp_path):
    repo,jid,token=new_run(tmp_path)
    repo.begin_generation_unit(jid,token,'interpret')
    repo.commit_generation_unit(jid,token,'interpret',{'entities':[]})
    repo.begin_generation_unit(jid,token,'setting')
    assert repo.generation_control(jid,'cancel')=='cancelled'
    assert repo.generation_control(jid,'cancel')=='cancelled'
    with pytest.raises(ValueError): repo.commit_generation_unit(jid,token,'setting',{})
    assert repo.generation_resources(jid,['plan'])=={'plan':{'entities':[]}}
    assert repo.generation_status(jid)['overall_progress']==1/8


def test_recovery_does_not_retry_unknown_billing_outcome(tmp_path):
    repo,jid,token=new_run(tmp_path)
    repo.begin_generation_unit(jid,token,'interpret')
    assert repo.recover_generations(now=time.time()+200)==[jid]
    assert repo.generation_status(jid)['units'][0]['status']=='uncertain'
    with pytest.raises(ValueError,match='billed'): repo.generation_control(jid,'resume')
    with pytest.raises(ValueError): repo.commit_generation_unit(jid,token,'interpret',{})
    repo.generation_control(jid,'resume',allow_uncertain_retry=True)
    new_token=repo.claim_generation(jid)
    assert repo.begin_generation_unit(jid,new_token,'interpret')
    repo.commit_generation_unit(jid,new_token,'interpret',{})
    with repo.connect() as db:
        assert [row[0] for row in db.execute('SELECT status FROM preparation_attempts ORDER BY attempt')]==['uncertain','completed']


def test_recovery_between_requests_requires_credentials_without_losing_work(tmp_path):
    repo,jid,token=new_run(tmp_path)
    repo.begin_generation_unit(jid,token,'interpret')
    repo.commit_generation_unit(jid,token,'interpret',{})
    repo.recover_generations(now=time.time()+200)
    assert repo.preparation_job(jid)['status']=='waiting_for_credentials'
    repo.generation_control(jid,'resume')
    token=repo.claim_generation(jid)
    assert not repo.begin_generation_unit(jid,token,'interpret')
    assert repo.begin_generation_unit(jid,token,'setting')


def test_retry_budget_and_stale_workspace_revision_guard(tmp_path):
    repo,jid,token=new_run(tmp_path)
    for _ in range(3):
        repo.begin_generation_unit(jid,token,'interpret')
        repo.fail_generation_unit(jid,token,'interpret','schema/invalid')
    with pytest.raises(ValueError,match='budget'): repo.begin_generation_unit(jid,token,'interpret')
    with repo.connect() as db:
        db.execute('UPDATE preparation_workspaces SET revision=revision+1')
    with pytest.raises(ValueError,match='ревизий'): repo.renew_generation(jid,token)


def test_pipeline_cannot_overwrite_input_or_another_units_resource(tmp_path):
    repo,jid,token=new_run(tmp_path)
    with pytest.raises(ValueError,match='immutable input'):
        repo.create_generation_run(jid,{'brief':'Replacement'})
    with pytest.raises(ValueError,match='duplicate resource producer'):
        repo.plan_generation_units(jid,token,[dict(id='other',stage='places',inputs=['brief'],outputs={'plan':''})])
    repo.plan_generation_units(jid,token,[dict(id='overwrite',stage='places',inputs=['brief'],outputs={'brief':''})])
    repo.begin_generation_unit(jid,token,'overwrite')
    with pytest.raises(ValueError,match='owns this resource'):
        repo.commit_generation_unit(jid,token,'overwrite','replacement')
    assert repo.generation_resources(jid,['brief'])=={'brief':'Secret source'}
    with repo.connect() as db:
        assert db.execute("SELECT count(*) FROM document_versions WHERE kind='generation_checkpoint'").fetchone()[0]==0


def test_cancel_still_available_after_external_workspace_revision_changes(tmp_path):
    repo,jid,token=new_run(tmp_path)
    with repo.connect() as db: db.execute('UPDATE preparation_workspaces SET revision=revision+1')
    assert repo.generation_control(jid,'cancel')=='cancelled'
