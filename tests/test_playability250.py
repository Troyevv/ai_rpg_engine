"""Consequence-first production paths; only provider transport is scripted."""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest
import engine
from backend.repositories.preparation import Repository
from backend.runtime_v3.models import Thread
from backend.runtime_v3.player_actions import resolver_options
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.long_term import run, plan
from backend.services.world_delta_errors import StructuralDeltaError
from test_engine import db, CONFIG
from test_integrated_repair247 import seed, execute, history
from test_live248_recovery import live, control


@pytest.mark.parametrize('audit', ['absent', 'uncertain', 'incidental_detail', 'bad_reference', 'malformed_inventory'])
def test_npc_reply_keeps_four_acquisitions_without_question_inventory(tmp_path, audit):
    data=live('knowledge');raw=control(data)
    raw['events']=[e for e in raw['events'] if e['actor_id']=='qa_vera']
    if audit=='absent':
        raw.pop('player_agency')
    else:
        raw['player_agency']['status']='uncertain'
        raw['player_agency']['narrative_audit']=[dict(narrative_evidence='Бытовая деталь.',
            classification='execution_detail' if audit=='bad_reference' else audit,
            player_action_id='unverified' if audit=='bad_reference' else None)]
    if audit=='malformed_inventory':raw['player_agency']['actions']=[{'id':'unused'},None]
    raw['diagnostics']={'events':[{'id':'untrusted'}], '_extraction_contract':1}
    repo=Repository(tmp_path/'game.sqlite');sid=seed(repo,data)['save']
    before=repo.get_snapshot(sid);old=history(repo,sid)
    job,calls=execute(repo,sid,data,[raw],legacy=False)
    assert job['status']=='saved' and len(calls)==2,job['error']
    fresh=Repository(repo.path);after=fresh.get_snapshot(sid);saved=history(fresh,sid)
    assert len(saved['knowledge_acquisitions'])-len(old['knowledge_acquisitions'])==4
    assert all('player_action' not in e for e in saved['events'][len(old['events']):])
    assert not any(e.get('local_id')=='untrusted' for e in saved['events'])
    assert after['world_state']['characters']['qa_vera']['location_id']==data['before']['characters']['qa_vera']['location_id']
    fresh.rollback_last(sid)
    assert fresh.get_snapshot(sid)==before and history(fresh,sid)==old


@pytest.mark.parametrize('damage', ['source', 'listener', 'significant_choice', 'malformed_major_audit', 'unknown_outcome'])
def test_advisory_audit_never_authorizes_substantial_conflict(tmp_path, damage):
    data=live('knowledge');raw=control(data)
    raw['events']=[e for e in raw['events'] if e['actor_id']=='qa_vera']
    raw['player_agency']['narrative_audit']=[dict(narrative_evidence='Деталь.',
        classification='incidental_detail',player_action_id=None)]
    if damage=='source':raw['knowledge_gained'][0]['source_event_id']='missing'
    elif damage=='listener':raw['events'][0]['witnesses'].remove('qa_kirill')
    elif damage in ('significant_choice','malformed_major_audit'):
        raw['player_agency']['narrative_audit'].append(dict(narrative_evidence='Согласился на брак.',
            classification='unauthorized_choice',player_action_id=[] if damage=='malformed_major_audit' else None))
    else:raw['marriages']=[{'actor_id':'qa_kirill'}]
    repo=Repository(tmp_path/'game.sqlite');sid=seed(repo,data)['save']
    before=repo.get_snapshot(sid);old=history(repo,sid)
    job,calls=execute(repo,sid,data,[raw,raw],legacy=False)
    assert job['status']=='error',job
    assert len(calls)==(2 if damage in ('significant_choice','malformed_major_audit') else 3)
    assert Repository(repo.path).get_snapshot(sid)==before and history(repo,sid)==old


def install_background(repo, sid):
    from test_runtime_v3_storage import snapshot_fixture
    snapshot=snapshot_fixture();s=snapshot['world_state']
    s['camera']['present_character_ids']=['a']
    for cid in ('b','c'):s['characters'][cid]['location_id']='hall'
    s['threads']={key:Thread(id=key,description='Самостоятельное занятие NPC.',
        character_ids=[cid],relevance=1).model_dump() for key,cid in [('first','b'),('second','c')]}
    with repo.connect() as conn:conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot),sid))
    return snapshot


def turn(repo,sid,*,failure=None,cancel=False,stale=False,elapsed=5):
    jid=repo.begin_job(sid,'Жду.','turn' if repo.list_turns(sid) else 'start',CONFIG);worker=engine.Worker();calls=[]
    def stream(**kw):
        current=json.loads(next(m['content'].split('\n',1)[1] for m in kw['messages']
            if m['content'].startswith('Текущее состояние / GM-only\n')))
        camera=current['camera'];hidden=camera['mode']=='observer'
        calls.append((hidden,bool(kw.get('response_format'))))
        if hidden and failure=='transport':raise RuntimeError('unknown remote result')
        if not kw.get('response_format'):yield 'Разговор продолжается.';return
        raw=dict(final_scene=dict(location_id=camera['location_id'],
            present_character_ids=camera['present_character_ids'],elapsed_minutes=0 if hidden else elapsed),
            choices=[dict(action='Осмотреться.',speech='')])
        if hidden:
            cid=camera['present_character_ids'][0]
            raw['events']=[dict(id='independent',text='NPC закончил работу.',
                participants=[cid],witnesses=[cid],medium='observation')]
            raw['character_changes']=[dict(id=cid,situation='Работа завершена.',evidence='NPC закончил работу.')]
            if failure=='extraction':raw['final_scene']['location_id']='nonexistent'
            if failure=='agency':raw['player_agency']=dict(status='violated',actions=[])
            if cancel:worker.cancelled.set()
            if stale:
                with repo.connect() as conn:conn.execute('UPDATE saves SET revision=revision+1 WHERE id=?',(sid,))
        yield json.dumps(raw)
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,jid,worker)
    return repo.get_job(jid),calls


@pytest.mark.parametrize('failure', ['extraction','transport'])
def test_short_turns_background_failure_reload_fairness_and_rollback(db,failure):
    repo,_,sid=db;install_background(repo,sid)
    for _ in range(8):
        job,calls=turn(repo,sid)
        assert job['status']=='saved' and len(calls)==2,job['error']
    repo=Repository(repo.path);before=repo.get_snapshot(sid);old=history(repo,sid)
    job,calls=turn(repo,sid,failure=failure)
    assert job['status']=='saved' and len(calls)==(5 if failure=='extraction' else 3),job['error']
    after=Repository(repo.path).get_snapshot(sid);saved=history(repo,sid)
    assert after['world_state']['meta']['world_time']==45
    assert after['world_state']['characters']==before['world_state']['characters']
    assert after['world_state']['knowledge']==before['world_state']['knowledge']
    assert saved['events']==old['events'] and len(saved['turns'])==len(old['turns'])+1
    assert saved['state_changes'][-1]['outcome']=='rejected'
    assert after['background_considerations']['attempts']=={'thread:first':45}
    for _ in range(2):assert len(turn(repo,sid)[1])==2
    # A failed first cause cannot monopolize the next slot.
    job,calls=turn(Repository(repo.path),sid)
    assert job['status']=='saved' and len(calls)==4,job['error']
    final=repo.get_snapshot(sid)
    assert final['background_considerations']['attempts']=={'thread:first':45,'thread:second':60}
    assert final['world_state']['knowledge']==before['world_state']['knowledge']
    assert len(history(repo,sid)['events'])==len(old['events'])+1
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)['background_considerations']['attempts']=={'thread:first':45}
    # Zero elapsed after a restart does not spend another background call.
    assert len(turn(Repository(repo.path),sid,elapsed=0)[1])==2


@pytest.mark.parametrize('mode',['cancel','stale'])
def test_background_isolation_does_not_swallow_cancel_or_stale(db,mode):
    repo,_,sid=db;install_background(repo,sid)
    for _ in range(8):turn(repo,sid)
    before=repo.get_snapshot(sid);old=history(repo,sid)
    job,_=turn(repo,sid,cancel=mode=='cancel',stale=mode=='stale')
    assert job['status']!='saved'
    assert repo.get_snapshot(sid)==before and history(repo,sid)==old


def lta_fixture():
    from test_long_term_advance import fixture
    before=fixture();s=before['world_state']
    s['threads']={key:Thread(id=key,description='NPC занимается своим делом.',
        character_ids=ids,relevance=1).model_dump() for key,ids in [('first',['a','b']),('second',['c'])]}
    return before


@pytest.mark.parametrize('repair_ok',[False,True])
def test_lta_independent_player_related_group_bounded_repair_and_other_group(repair_ok):
    before=lta_fixture();original=deepcopy(before);calls=[]
    request=dict(amount=1,unit='months',max_llm_calls=5)
    candidates={c.id:c for c in plan(before,request).candidates}
    assert not next(c for c in candidates.values() if c.source_id=='first').requires_player
    def generate(stage,messages,*args,context_key,**kwargs):
        calls.append((stage,context_key))
        if stage=='long_term_narrative':return ['NPC продолжил работу.']
        candidate=candidates[context_key[0]]
        if candidate.source_id=='first' and (stage=='long_term_extraction' or not repair_ok):
            return ['{"final_scene":{"location_id":"missing","present_character_ids":[]}}']
        actor=next(c for c in candidate.actor_ids if c!='a')
        return [json.dumps(dict(final_scene=dict(location_id=before['world_state']['characters'][actor]['location_id'],
            present_character_ids=[actor],elapsed_minutes=0),events=[dict(id='work',text='NPC продолжил работу.',
            participants=[actor],witnesses=[actor],medium='observation',advance_candidate_ids=context_key)]))]
    after,batch,report=run(before,request,generate=generate)
    assert before==original and report['llm_calls']==len(calls)==5
    assert len(report['accepted'])==(2 if repair_ok else 1),report
    assert report['coverage']['rejected_causes']==(0 if repair_ok else 1)
    assert sum(stage=='long_term_repair' for stage,_ in calls)==1
    assert after['world_state']['characters']['a']==before['world_state']['characters']['a']
    assert after['world_state']['knowledge']==before['world_state']['knowledge']
    assert all(not e['player_observed'] and 'a' not in e['participants'] for e in batch['events'])


def test_lta_repair_uses_budget_and_does_not_claim_calm_when_rejected():
    before=lta_fixture();calls=[]
    def generate(stage,*args,**kwargs):
        calls.append(stage)
        return ['NPC продолжил работу.' if stage=='long_term_narrative' else '{}']
    _,batch,report=run(before,dict(amount=1,unit='months',max_llm_calls=4),generate=generate)
    assert len(calls)==report['llm_calls']==3
    assert report['status']=='incomplete' and not report['accepted'] and not report['quiet']
    assert report['coverage']['budget_unattempted']>=1 and report['coverage']['rejected_causes']>=1
    assert not batch['events']


def test_lta_calm_is_distinct_from_zero_budget_and_rejected():
    before=lta_fixture()
    def generate(stage,messages,*args,**kwargs):
        if stage=='long_term_narrative':return ['Ситуация без изменений.']
        current=json.loads(next(m['content'].split('\n',1)[1] for m in messages
            if m['content'].startswith('Текущее состояние / GM-only\n')))
        return [json.dumps(dict(final_scene=dict(location_id=current['camera']['location_id'],
            present_character_ids=current['camera']['present_character_ids'],elapsed_minutes=0)))]
    _,batch,report=run(before,dict(amount=1,unit='months',max_llm_calls=4),generate=generate)
    assert report['status']=='quiet' and len(report['quiet'])==2 and not batch['events']
    _,_,calendar=run(before,dict(amount=1,unit='months',max_llm_calls=0),generate=generate)
    assert calendar['status']=='calendar_only' and calendar['llm_calls']==0


def test_latest_original_visit_errors_are_not_hidden_by_soft_audit(tmp_path):
    import gzip
    from pathlib import Path
    from test_life248_playability import repository_case
    data=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/issue250/berezovsk.json.gz').read_bytes()))['005']
    repo,sid,_=repository_case(tmp_path,'005');before=repo.get_snapshot(sid);old=history(repo,sid)
    assert before['world_state']==data['before']
    for payload in data['responses']['D']:
        with pytest.raises(StructuralDeltaError) as error:
            StateResolver(data['before'],data['narrative'],data['player_input'],
                **resolver_options(data['before'],data['player_input'],contract_version=3)).resolve(payload)
        assert error.value.code in ('player_action_completion_invalid','raw_root_invalid')
    job,calls=execute(repo,sid,data,[json.loads(p) for p in data['responses']['D']],legacy=False,
        config=dict(CONFIG,context_length=131072,update_tokens=8192))
    assert job['status']=='error' and len(calls)==3
    assert repo.get_snapshot(sid)==before and history(repo,sid)==old


def test_optional_choice_errors_drop_only_choices_and_keep_next_input(tmp_path):
    from test_life248_playability import repository_case
    repo,sid,data=repository_case(tmp_path,'002')
    raw=json.loads(data['responses'][0]['payload'])
    raw['choices']=[dict(action='Осмотреться.',speech=''),
        dict(action='Неверная привязка.',speech='',basis_ids=['missing'],kind='question')]
    job,calls=execute(repo,sid,data,[raw],legacy=False)
    assert job['status']=='saved' and len(calls)==2
    assert any(w['code']=='choice_basis_invalid' for w in json.loads(job['warnings_json']))
    after=repo.get_snapshot(sid)
    assert after['world_state']['knowledge']==data['before']['knowledge']
    # No stale choice is copied into the next result; free input remains usable.
    raw=dict(final_scene=dict(location_id=after['world_state']['camera']['location_id'],
        present_character_ids=after['world_state']['camera']['present_character_ids'],elapsed_minutes=1))
    next_job,_=execute(Repository(repo.path),sid,dict(data,player_input='Жду.'),[raw],legacy=False)
    assert next_job['status']=='saved',next_job['error']


@pytest.mark.parametrize('budget',[4,5])
def test_lta_rejected_groups_report_survives_sqlite_reload_and_rollback(db,budget):
    repo,_,sid=db;before=lta_fixture()
    with repo.connect() as conn:conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(before),sid))
    assert turn(repo,sid,elapsed=0)[0]['status']=='saved'
    original=repo.get_snapshot(sid)
    request=dict(amount=1,unit='months',max_llm_calls=budget)
    candidates=plan(original,request).candidates
    jid=repo.begin_job(sid,'','long_term',dict(CONFIG,long_term_advance=request))
    extractions=[]
    def stream(**kw):
        if not kw.get('response_format'):
            yield 'NPC занимается своим делом.';return
        extractions.append(kw)
        if len(extractions)<=2:
            yield '{}';return
        current=json.loads(next(m['content'].split('\n',1)[1] for m in kw['messages']
            if m['content'].startswith('Текущее состояние / GM-only\n')))
        camera=current['camera'];actor=camera['present_character_ids'][0]
        candidate=next(c for c in candidates if c.kind=='thread' and actor in c.actor_ids)
        yield json.dumps(dict(final_scene=dict(location_id=camera['location_id'],
            present_character_ids=camera['present_character_ids'],elapsed_minutes=0),
            events=[dict(id='work',text='NPC занимается своим делом.',participants=[actor],
                witnesses=[actor],medium='observation',advance_candidate_ids=[candidate.id])]))
    with patch('engine.chat_stream',side_effect=stream):engine.run_job(repo.path,jid,engine.Worker())
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    after=Repository(repo.path).get_snapshot(sid);report=after['last_long_term_advance']
    assert report['status']=='incomplete' and report['coverage']['rejected_causes']==1,json.dumps(report['diagnostics'],ensure_ascii=False)
    assert report['llm_calls']==(3 if budget==4 else 5)
    assert len(repo.request_log(job_id=jid))==report['llm_calls']
    assert report['coverage']['accepted_groups']==(0 if budget==4 else 1)
    assert len(history(repo,sid)['events'])==len(history(Repository(repo.path),sid)['events'])==(0 if budget==4 else 1)
    assert after['world_state']['knowledge']==original['world_state']['knowledge']
    assert history(repo,sid)['state_changes'][-1]['report']==report
    assert repo.get_save(sid)['state']['last_long_term_advance']['coverage']==report['coverage']
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==original


def test_rejected_background_agency_does_not_mark_foreground_for_reauthor(db):
    repo,_,sid=db;install_background(repo,sid)
    for _ in range(8):turn(repo,sid)
    job,calls=turn(repo,sid,failure='agency')
    assert job['status']=='saved' and len(calls)==4,job['error']
    public=Repository(repo.path).public_job(job)
    assert not public['narrative_reauthor_required']
    assert repo.get_snapshot(sid)['background_considerations']['attempts']=={'thread:first':45}
    assert all(row.get('scope')=='independent_background'
               for row in json.loads(job['repair_diagnostics_json']))


def test_lta_discarded_events_are_rejected_not_reported_as_calm():
    before=lta_fixture()
    def generate(stage,messages,*args,**kwargs):
        if stage=='long_term_narrative':return ['NPC продолжил работу.']
        camera=json.loads(next(m['content'].split('\n',1)[1] for m in messages
            if m['content'].startswith('Текущее состояние / GM-only\n')))['camera']
        return [json.dumps(dict(final_scene=dict(location_id=camera['location_id'],
            present_character_ids=camera['present_character_ids'],elapsed_minutes=0),events=[None]))]
    _,batch,report=run(before,dict(amount=1,unit='months',max_llm_calls=3),generate=generate)
    assert report['status']=='incomplete' and report['coverage']['rejected_causes']>0
    assert not report['quiet'] and not batch['events']
    assert report['llm_calls']==3


def test_recorded_lta_groups_keep_original_causes_after_selection_policy_change():
    before=lta_fixture();request=dict(amount=1,unit='months',max_llm_calls=4)
    original=next(c for c in plan(before,request).candidates if c.source_id=='second')
    calls=[]
    def generate(stage,messages,*args,context_key,**kwargs):
        calls.append((stage,context_key))
        if stage=='long_term_narrative':return ['NPC продолжил работу.']
        camera=json.loads(next(m['content'].split('\n',1)[1] for m in messages
            if m['content'].startswith('Текущее состояние / GM-only\n')))['camera']
        return [json.dumps(dict(final_scene=dict(location_id=camera['location_id'],
            present_character_ids=camera['present_character_ids'],elapsed_minutes=0)))]
    _,_,report=run(before,request,generate=generate,recorded_groups=[[original.id]])
    assert report['llm_calls']==len(calls)==2
    assert all(ids==[original.id] for _,ids in calls)
    assert report['quiet'][0]['candidate_ids']==[original.id]
    assert report['coverage']['budget_unattempted']==1


def test_optional_background_context_failure_keeps_foreground_without_provider_retry(db):
    repo,_,sid=db;install_background(repo,sid)
    for _ in range(8):turn(repo,sid)
    before=repo.get_snapshot(sid)
    with patch('backend.runtime_v3.simulation.build_context',side_effect=ValueError('context budget')):
        job,calls=turn(repo,sid)
    assert job['status']=='saved' and len(calls)==2,job['error']
    assert repo.get_snapshot(sid)['world_state']['characters']==before['world_state']['characters']
    assert any(d['code']=='background_context_invalid' for d in json.loads(job['warnings_json']))
