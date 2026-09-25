import json
from unittest.mock import patch
import pytest
from storage import Storage
from test_engine import db, CONFIG, NARRATIVE
from test_player_agency import character_payload, execute
from backend.services.world_delta_errors import StructuralDeltaError

@pytest.mark.parametrize('secondary',[False,True])
def test_repair_reason_persists_restart_and_variant_switch(db,secondary):
    repo,_,sid=db
    bad=character_payload({});bad['scene']['present_ids']=['missing']
    fixed=character_payload({'emotion':'боится'} if secondary else {})
    job=repo.begin_job(sid,'Я подхожу к окну.','start',CONFIG)
    calls=execute(repo,job,bad,repaired=fixed)
    assert len(calls)==3 and repo.get_job(job)['status']=='saved'
    original=repo.list_turns(sid)[0]
    repo=Storage(repo.path)
    first=repo.turn_diagnostics(sid)[0]
    reason=first['repairs'][0]
    assert reason['repair_error_code']=='unknown_character'
    assert reason['stage']=='extraction_repair'
    assert reason['repair_error_type']=='StructuralDeltaError' and reason['repair_reason']
    assert bool(first['warnings'])==secondary
    assert first['timing']['extraction_repair']>=0
    assert 'unknown_character' in str(calls[2]['messages'])
    requests={q['stage']:q for q in first['requests']}
    assert json.loads(requests['extraction']['response_text'])==bad
    assert json.loads(requests['extraction_repair']['response_text'])==fixed
    second=repo.begin_job(sid,'','regenerate',CONFIG)
    assert len(execute(repo,second,character_payload({})))==2
    assert repo.turn_diagnostics(sid)[0]['repairs']==[]
    repo.select_variant(sid,original['id'],original['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.turn_diagnostics(sid)[0]['repairs']==[reason]

@pytest.mark.parametrize('error',[ValueError('validator bug'),StructuralDeltaError('unsafe','unsafe',repairable=False)])
def test_unexpected_or_unsafe_failure_never_calls_repair(db,error):
    repo,_,sid=db;before=repo.get_save(sid)['state']
    job=repo.begin_job(sid,'','start',CONFIG)
    with patch('engine.apply_world_updates',side_effect=error):
        assert len(execute(repo,job,character_payload({})))==2
    assert repo.get_job(job)['status']=='error'
    assert repo.get_save(sid)['state']==before and repo.list_turns(sid)==[]
    assert json.loads(repo.get_job(job)['repair_diagnostics_json'])==[]

def test_sanitizer_no_progress_is_fatal_without_repair(db):
    repo,_,sid=db;job=repo.begin_job(sid,'','start',CONFIG)
    with patch('backend.services.world_delta_errors.sanitize_secondary',return_value={}):
        assert len(execute(repo,job,character_payload({'emotion':'боится'})))==2
    assert repo.get_job(job)['status']=='error'
    assert repo.list_turns(sid)==[]

@pytest.mark.parametrize('repaired_secondary',[False,True])
def test_background_structural_repair_records_reason(repaired_secondary,db):
    from threading import Event
    from copy import deepcopy
    from backend.services.simulation import simulate
    from backend.services.pov import transition
    from test_living_world import ready, delta, QUOTE
    from backend.services.world_delta import apply_delta
    repo,_,sid=db
    state=transition(apply_delta(ready(repo,sid),delta(),QUOTE,'',2),'character_1')
    before=deepcopy(state);state['world_clock']['minute']=1200;state['scene_meta']['time']='День 1 20:00'
    calls=[];warnings=[];repairs=[]
    def generate(stage,*args,**kwargs):
        calls.append(stage)
        if stage=='world_simulation':yield QUOTE;return
        scene={'text':'Встреча','time':'День 1 20:00','location':'Подвал','present_ids':['character_3','character_4']}
        if stage=='world_simulation_delta':scene['present_ids']=['missing']
        dimensions={'respect':30}
        if repaired_secondary:dimensions['loyalty']=50
        yield json.dumps({'scene':scene,'choices':[], 'world_delta':{'relationships':[{'source_id':'character_3','target_id':'character_4','context':'Уважает','dimensions':dimensions,'evidence':QUOTE}]}})
    after=simulate(before,state,3,32768,CONFIG,generate,Event(),warnings=warnings,on_repair=repairs.append)
    assert calls==['world_simulation','world_simulation_delta','world_simulation_repair']
    assert repairs[0]['stage']=='world_simulation_repair' and repairs[0]['repair_error_code']=='unknown_character'
    assert bool(warnings)==repaired_secondary
    assert after['world']['relationships']['character_3:character_4']['dimensions']['respect']==30
