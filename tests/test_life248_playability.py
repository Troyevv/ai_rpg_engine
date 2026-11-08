"""Real Berezovsk replies: offline replay, never fabricated Live success."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import pytest
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.player_actions import resolver_options
from backend.runtime_v3.raw import repair_feedback
from backend.runtime_v3.long_term import run
from backend.services.world_delta_errors import StructuralDeltaError

DATA=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/issue247/life248.json.gz').read_bytes()))

def resolve(d,p):
    return StateResolver(d['before'],d['narrative'],d['player_input'],**resolver_options(d['before'],d['player_input'],contract_version=2)).resolve(p)

@pytest.mark.parametrize('case',['002','003','005','007'])
def test_original_first_extraction_remains_rejected_atomically(case):
    d=deepcopy(DATA[case]);before=deepcopy(d['before'])
    with pytest.raises(StructuralDeltaError):resolve(d,d['responses'][0]['payload'])
    assert d['before']==before

@pytest.mark.parametrize('case',['002','006','007'])
def test_original_real_successful_repair_is_accepted(case):
    d=DATA[case];result=resolve(d,d['responses'][-1]['payload'])
    assert result.history['events']
    assert result.state['knowledge']==d['before']['knowledge']
    if case=='006':
        assert result.state['characters']['char_alexey']['location_id']=='loc_home_viktor'
        assert result.state['characters']['char_galina']['location_id']=='loc_home_galina'


def test_repair_envelope_is_not_output_and_stays_invalid():
    d=DATA['003'];payload=d['responses'][1]['payload']
    assert 'diagnostic' in json.loads(payload)
    with pytest.raises(StructuralDeltaError) as e:resolve(d,payload)
    assert e.value.code=='raw_unknown_field'
    feedback=json.loads(repair_feedback(e.value.diagnostics('validation_failed'),payload,d['before']))
    assert 'NOT output fields' in feedback['contract']
    assert feedback['original_extraction']==json.loads(payload)


def test_lta_dates_prior_scene_without_mutating_original_or_accepting_player():
    d=DATA['008'];before=deepcopy(d['snapshot']);captured=[]
    def generate(stage,messages,*args,**kwargs):
        captured.append(messages)
        return iter([next(r['payload'] for r in d['responses'] if r['stage']==stage)])
    after,batch,report=run(before,dict(amount=3,unit='months',max_llm_calls=2),generate=generate,
        config=dict(context_length=131072,max_tokens=2400,update_tokens=8192))
    assert before==d['snapshot']
    assert report['llm_calls']==2 and not report['accepted']
    assert after['world_state']['characters']==before['world_state']['characters']
    for messages in captured:
        current=next(json.loads(m['content'].split('\n',1)[1]) for m in messages if m['content'].startswith('Текущее состояние / GM-only\n'))
        assert not current['camera']['situation']
        assert all(not c.get('situation') for c in current['characters'].values())
        text='\n'.join(m['content'] for m in messages)
        assert 'Прошлая сцена на начало интервала' in text
        assert str(before['world_state']['meta']['world_time']) in text


def repository_case(tmp_path, case):
    from test_integrated_repair247 import seed
    from backend.repositories.preparation import Repository
    repo=Repository(tmp_path/'game.sqlite');d=DATA[case];sid=seed(repo,d)['save']
    snapshot=deepcopy(DATA['008']['snapshot'])
    snapshot['world_state']=deepcopy(d['before'])
    snapshot['history_head']=repo.get_snapshot(sid)['history_head']
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot),sid))
    return repo,sid,d

@pytest.mark.parametrize('repair',[False,True])
def test_real_accepted_response_job_history_reload_rollback(tmp_path,repair):
    from test_integrated_repair247 import execute,history
    from backend.repositories.preparation import Repository
    repo,sid,d=repository_case(tmp_path,'002');before=repo.get_snapshot(sid)
    replies=[json.loads(d['responses'][-1]['payload'])]
    if repair:replies.insert(0,json.loads(d['responses'][0]['payload']))
    job,calls=execute(repo,sid,d,replies,legacy=False,config=dict(model='test',context_length=131072,max_tokens=2400,update_tokens=8192))
    assert job['status']=='saved',job['error']
    assert len(calls)==2+int(repair)
    assert history(repo,sid)['events']
    assert Repository(repo.path).get_snapshot(sid)==repo.get_snapshot(sid)
    repo.rollback_last(sid, repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)['world_state']==before['world_state']


def test_real_failed_visit_then_real_retry_preserves_narrative(tmp_path):
    from test_integrated_repair247 import execute
    repo,sid,d=repository_case(tmp_path,'005');before=repo.get_snapshot(sid)
    cfg=dict(model='test',context_length=131072,max_tokens=2400,update_tokens=8192)
    job,_=execute(repo,sid,d,[json.loads(r['payload']) for r in d['responses']],legacy=False,config=cfg)
    assert job['status']=='error' and repo.get_snapshot(sid)==before
    fixed=DATA['006']['responses'][-1]['payload']
    result,calls=execute(repo,sid,d,[json.loads(fixed)],retry=job['id'],legacy=False,config=cfg)
    assert result['status']=='saved',result['error']
    assert result['narrative']==d['narrative'] and len(calls)==1
    assert repo.get_snapshot(sid)['world_state']['characters']['char_alexey']['location_id']=='loc_home_viktor'


def test_galina_failure_abandon_keeps_history_and_can_reload(tmp_path):
    from test_integrated_repair247 import execute,history
    from backend.repositories.preparation import Repository
    repo,sid,d=repository_case(tmp_path,'003');before=repo.get_snapshot(sid);old_history=history(repo,sid)
    job,_=execute(repo,sid,d,[json.loads(r['payload']) for r in d['responses']],legacy=False,
        config=dict(model='test',context_length=131072,max_tokens=2400,update_tokens=8192))
    assert job['status']=='error'
    assert job['narrative']==d['narrative'] and repo.get_snapshot(sid)==before
    repo.abandon_job(sid,job['id'],repo.get_save(sid)['revision'],job['attempt_epoch'])
    assert Repository(repo.path).get_snapshot(sid)==before
    assert history(repo,sid)==old_history
