"""Production planning against pinned metadata, real jobs/SQLite, and a transport fixture."""
import json
from unittest.mock import patch

import pytest

from backend.api.schemas import ModelConfig
from backend.services.draft_response import stage_output_limit
from backend.services.token_budget import DETAILS, extraction_output, plan_request, prepare, prose_guidance
from test_api import api, wait_job
from test_runtime_handoff import source, imported, provider_payload, NARRATIVE
from test_initial_draft_v4 import rich, SHORT
from draft_provider_fixture import accept_semantics_unchecked

MODEL = dict(model='deepseek-flash',provider='deepseek')
MESSAGES = [{'role':'user','content':'Город на берегу реки.'}]


def test_new_legacy_and_loaded_window_modes():
    cfg = ModelConfig(**MODEL).model_dump()
    assert cfg['budget_mode'] == 'auto'
    assert ModelConfig(**MODEL,max_tokens=768).budget_mode is None
    local = dict(cfg,provider='local',model='loaded')
    auto = prepare(local,'turn',loaded={'config':{'context_length':8192},'max_context_length':131072})
    assert auto['context_length'] == 8192
    assert cfg['context_length'] == 32768
    with pytest.raises(ValueError,match='Ручной контекст'):
        prepare(dict(local,budget_mode='manual'),'turn',loaded={'config':{'context_length':8192}})
    with pytest.raises(ValueError,match='неизвестно'):
        prepare(dict(cfg,model='deepseek-flash-similar'),'turn')
    assert prepare(dict(cfg,model='private',budget_mode='manual'),'turn')['_budget_caps']['context_length'] is None


def test_stage_targets_and_complete_serialized_request():
    cfg = ModelConfig(**MODEL).model_dump()
    outputs = []
    extraction = []
    for detail in DETAILS:
        config = prepare(cfg,'turn',detail=detail)
        outputs.append(config['max_tokens'])
        extraction.append(extraction_output(config,1200))
    assert outputs == sorted(set(outputs))
    assert len(set(extraction)) == 1
    limits = [stage_output_limit('world', MESSAGES, prepare(dict(cfg,_creation_settings=dict(cast_preset=size,core_npcs=15,secondary_npcs=40)),'draft_world'))
              for size in ('small','medium','large','custom')]
    assert limits == sorted(set(limits))
    config = prepare(cfg,'turn')
    p = plan_request(config,'narrative',MESSAGES,config['max_tokens'])
    assert p['estimated_input']+p['safety_margin']+p['output_allowance'] <= p['context_window']
    schema = {'description':'схема'*3000}
    with pytest.raises(ValueError,match='Контекст'):
        plan_request(dict(config,context_length=8192),'extraction',MESSAGES,4096,structured_schema=schema)


@pytest.mark.parametrize('size,detail', list(zip(('small','medium','large','custom'),DETAILS)))
def test_generated_world_and_new_detail_survive_confirmation_and_reload(api,size,detail):
    client,app = api
    ws = client.post('/api/workspaces',json={'name':'Бюджет'}).json()
    path = f"/api/workspaces/{ws['id']}/draft"
    @accept_semantics_unchecked
    def world(**kwargs):
        kwargs['on_finish']('stop')
        yield json.dumps(rich(),ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=world):
        reply=client.post(path+'/generate',json=dict(revision=0,text=SHORT,config=MODEL,api_key='fixture',
            creation_settings=dict(cast_preset=size,narrative_detail=detail)))
        job=wait_job(client,reply.json()['id'])
    assert job['status']=='saved',job.get('error')
    draft=client.get(path+'?author=true').json()
    confirmed=client.post(path+'/confirm',json=dict(revision=draft['revision'],version_id=draft['version_id'],accept_warnings=True))
    assert confirmed.status_code==200,confirmed.text
    sid=confirmed.json()['save']
    from backend.repositories.preparation import Repository
    repo=Repository(app.state.repository.path)
    assert repo.get_snapshot(sid)['world_state']['meta']['narrative_detail']==detail
    from test_runtime_v3_engine import run as run_turn, raw_for
    for kind in ('start','turn'):
        state=repo.get_snapshot(sid)
        jid=repo.begin_job(sid,'Осматриваюсь.' if kind=='turn' else '',kind,ModelConfig(**MODEL).model_dump())
        run_turn(repo,jid,raw_for(state))
        assert repo.get_job(jid)['status']=='saved', repo.get_job(jid)['error']
        repo=Repository(repo.path)
        assert repo.get_snapshot(sid)['world_state']['meta']['narrative_detail']==detail
    for request in repo.request_log(job_id=job['id']):
        assert request['diagnostics']['budget_plan']['budget_mode']=='auto'


def test_game_detail_new_turn_and_pinned_regeneration(api):
    client,app=api
    value=source()
    value.setdefault('creation_settings',{})['narrative_detail']='brief'
    sid=imported(client,value)
    repo=app.state.repository
    def play(kind,config=MODEL):
        def stream(**kwargs):
            yield json.dumps(provider_payload(kwargs),ensure_ascii=False) if kwargs.get('response_format') else NARRATIVE
        with patch('engine.chat_stream',side_effect=stream):
            response=client.post(f'/api/saves/{sid}/turns',json=dict(kind=kind,text='Я жду.' if kind=='turn' else '',
                revision=repo.get_save(sid)['revision'],config=config,api_key='fixture'))
            job=wait_job(client,response.json()['id'])
        assert job['status']=='saved',job.get('error')
        rows=repo.request_log(job_id=job['id'])
        assert [r['stage'] for r in rows]==['extraction','narrative']
        assert NARRATIVE in next(m['content'] for m in rows[0]['messages'] if m['content'].startswith('completed_narrative'))
        return rows[1]
    first=play('start')
    def change(detail):
        path=f'/api/saves/{sid}/narrative-policy'
        current=client.get(path).json()['current']
        assert client.put(path,json=dict(current,narrative_detail=detail,revision=repo.get_save(sid)['revision'])).status_code==200
    change('extended')
    again=play('regenerate',dict(MODEL,model='deepseek-v4-pro',thinking='high'))
    assert (again['model'],again['messages'],again['max_tokens'])==(first['model'],first['messages'],first['max_tokens'])
    change('extended')
    new=play('turn')
    assert sum(prose_guidance('extended') in m['content'] for m in new['messages'])==1
    assert new['max_tokens']>first['max_tokens']


@pytest.mark.extraction_current
def test_live_contract_auto_downstream_feasibility_and_publication(tmp_path):
    from test_published_narrative263 import play
    from devtools.narrative_test_world import load_fixture
    from backend.repositories.preparation import Repository
    repo=Repository(tmp_path/'auto.sqlite')
    sid=load_fixture(repo,'pacing')['save']
    prose=('У двери зажёгся свет. ' * 160).strip()
    job=play(repo,sid,prose,'{}',kind='start',model='deepseek-flash',budget_mode='auto')
    assert job['status']=='saved',job['error']
    extraction=next(r for r in repo.request_log(job_id=job['id']) if r['stage']=='extraction')
    assert extraction['extraction_contract']==11 and extraction['extraction_transport']=='responses_json_schema'
    assert extraction['diagnostics']['budget_plan']['stage']=='extraction'
    assert prose.strip() in next(m['content'] for m in extraction['messages'] if m['content'].startswith('completed_narrative'))


def test_custom_endpoint_independent_limits_and_cost_envelope(monkeypatch):
    import llm
    from threading import Event
    from backend.services.draft_response import response, TransportError
    from test_draft_response_v4 import JournalRepo
    monkeypatch.setitem(llm.PROVIDERS,'compatible',llm.ProviderSpec('https://example.invalid/v1'))
    monkeypatch.setenv('COMPATIBLE_MODEL_LIMITS',json.dumps({'https://example.invalid/v1':{'explicit':{'max_input':8192,'max_output':2048}}}))
    monkeypatch.setattr(llm, 'OpenAI', lambda **_: (_ for _ in ()).throw(ConnectionError()))
    config=prepare(ModelConfig(provider='compatible',model='explicit').model_dump(),'draft_world')
    with pytest.raises(ValueError,match='Полный вход'):
        plan_request(config,'world',[dict(role='user',content='ю'*10000)],1024)
    assert plan_request(config,'world',MESSAGES,4096)['output_allowance']==2048
    with pytest.raises(TransportError,match='Тариф неизвестен'):
        response(JournalRepo(),'job',{},'world',MESSAGES,dict(config,_draft_cost_budget_usd='.10'),config['context_length'],
                 lambda *_:pytest.fail('paid request'),Event())

def test_detail_rejected_before_transport_when_model_cannot_fit_target():
    config = prepare(ModelConfig(**MODEL).model_dump(), 'turn', detail='extended')
    config['_budget_caps']['max_output'] = 512
    with pytest.raises(ValueError, match='Уменьшите подробность'):
        plan_request(config, 'narrative', MESSAGES, 512)


def test_resume_pins_policy_and_checks_reloaded_local_capacity():
    from backend.services.token_budget import snapshot
    raw = ModelConfig(provider='local', model='same').model_dump()
    original = prepare(raw, 'turn', loaded={'config': {'context_length': 32768}}, detail='brief')
    recorded = dict(raw, _budget_snapshot=snapshot(original))
    larger = prepare(recorded, 'turn', loaded={'config': {'context_length': 65536}}, detail='extended')
    assert snapshot(larger) == snapshot(original)
    with pytest.raises(ValueError, match='Сохранённый план несовместим'):
        prepare(recorded, 'turn', loaded={'config': {'context_length': 8192}})


def test_scene_selector_observes_independent_input_cap():
    from long_world_fixture import long_world
    from context_builder import build_context
    state, turns, history = long_world(4)
    messages = build_context(state, turns, 'Жду ответа.', 'turn', 131072, 2000,
                             world_history=history, max_input=32768, extraction_contract=11)
    assert messages.selection['hard_context_limit'] == 32768 - 256
