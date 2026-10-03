"""Real request snapshots, totals, local warnings and variant-specific timing."""
import json
from decimal import Decimal
from unittest.mock import patch
import pytest
import engine
from test_engine import db,CONFIG,NARRATIVE
from test_player_agency import character_payload
from runtime_v3_fixture import execute
from backend.services.relation_dimensions import RELATION_DIMENSIONS
from backend.runtime_v3.raw import extraction_schema


def payload():
    p=character_payload({})
    p.update(facts=[dict(id='f',text='Подтверждённый факт',evidence=NARRATIVE)],
        events=[dict(id='e',text='Разговор',participants=['character_1','character_2'],witnesses=['character_2'],fact_ids=['f'],medium='conversation',evidence=NARRATIVE)],
        knowledge_gained=[dict(actor_id='character_2',fact_id='f',source_event_id='e',evidence=NARRATIVE)],
        relationship_changes=[dict(source_id='character_2',target_id='character_1',dimensions={'trust':55,'respect':70},context='Доверяет',evidence=NARRATIVE)],
        thread_changes=[dict(id='t',description='Разговор',state='Начат',character_ids=['character_2'],evidence=NARRATIVE)])
    return p


@pytest.mark.parametrize('case',['witness','fact','source','action','dimension'])
def test_leaf_errors_keep_independent_changes_without_repair(db,case):
    repo,_,sid=db;p=payload()
    if case=='witness':p['events'][0]['witnesses']=[]
    if case=='fact':p['events'][0]['fact_ids']=[]
    if case=='source':p['knowledge_gained'][0]['source_event_id']='missing'
    if case=='action':p['events'][0]['medium']='action'
    if case=='dimension':p['relationship_changes'][0]['dimensions']['sympathy']=40
    job=repo.begin_job(sid,'','start',CONFIG)
    assert len(execute(repo,job,p,NARRATIVE))==2
    assert repo.get_job(job)['status']=='saved'
    world=repo.get_snapshot(sid)['world_state']
    assert world['relationships']['character_2:character_1']['dimensions']=={'trust':55,'respect':70}
    assert 't' in world['threads'] and 'f' in world['facts']
    assert ('character_2:f' in world['knowledge'])==(case=='dimension')
    diag=repo.turn_diagnostics(sid)[0]
    assert len(diag['requests'])==2 and not diag['repairs'] and 'extraction_repair' not in diag['timing']
    assert diag['warnings'][0]['index']==0
    assert diag['warnings'][0]['section']==('relationships' if case=='dimension' else 'knowledge')


def test_schema_uses_one_dimension_registry():
    dimensions=extraction_schema()['properties']['relationship_changes']['items']['properties']['dimensions']
    assert set(dimensions['properties'])==set(RELATION_DIMENSIONS)
    assert dimensions['additionalProperties'] is False and not dimensions['required']


def test_actual_requests_tokens_cache_cost_and_snapshot_survive_variant_switch(db):
    repo,_,sid=db;config=dict(CONFIG,provider='deepseek',model='deepseek-flash');calls=[]
    job=repo.begin_job(sid,'','start',config)
    def stream(**kw):
        calls.append(kw)
        kw['on_usage']({'prompt_tokens':1000,'completion_tokens':100,'prompt_cache_hit_tokens':800})
        kw['on_finish']('stop')
        yield json.dumps(payload()) if kw.get('response_format') else NARRATIVE
    with patch('engine.chat_stream',side_effect=stream):engine.run_job(repo.path,job,engine.Worker())
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    totals=repo.accounting(sid);diag=totals['turns'][0];rows=diag['requests']
    assert len(rows)==len(calls)==2
    assert totals['game']['input_tokens']==2000 and totals['game']['output_tokens']==200 and totals['game']['cached_input_tokens']==1600
    assert Decimal(totals['game']['cost_usd'])==sum(Decimal(r['cost_usd']) for r in rows)
    by_stage={r['stage']:r for r in rows}
    assert by_stage['narrative']['messages']==calls[0]['messages']
    assert by_stage['extraction']['messages']==calls[1]['messages']
    assert all(r['finish_reason']=='stop' and r['duration']>=0 for r in rows)
    original=repo.list_turns(sid)[0]
    replacement=repo.begin_job(sid,'','regenerate',config)
    execute(repo,replacement,character_payload({}),NARRATIVE)
    assert repo.turn_diagnostics(sid)[0]['job_id']==replacement
    repo.select_variant(sid,original['id'],original['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.turn_diagnostics(sid)[0]['requests']==rows
