"""Synthetic Extraction responses; only the provider is substituted in API tests."""
import json
from copy import deepcopy
from unittest.mock import patch
import pytest
from test_api import api, wait_job
from test_runtime_handoff import imported, submit, arrival
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.raw import RawTurnResult
from backend.services.world_delta_errors import StructuralDeltaError


def test_t45_start_without_movement_reload_next_turn(api):
    from storage import Storage
    client, app = api
    sid = imported(client); repo = app.state.repository
    before = repo.get_snapshot(sid); calls = []
    payload = arrival(); payload['movements'] = []
    def provider(**kw):
        calls.append(kw)
        yield json.dumps(payload) if kw.get('response_format') else 'Виктория вошла внутрь и подошла к столу.'
    with patch('engine.chat_stream', side_effect=provider):
        job = wait_job(client, submit(client, sid))
        assert job['status'] == 'saved', job.get('error')
        assert len(calls) == 2
        after = repo.get_snapshot(sid)
        assert after['world_state']['characters']['viktoria_solovyova']['location_id'] == 'ilya_cabinet'
        assert after['world_state']['knowledge'] == before['world_state']['knowledge']
        assert Storage(repo.path).get_snapshot(sid) == after
        assert wait_job(client, submit(client, sid, 'turn', 'Я спрашиваю: «Как дела?»'))['status'] == 'saved'
    assert len(repo.list_turns(sid)) == 2


def test_t46_observed_without_boundary_or_movement(api):
    client, app = api; sid = imported(client)
    before = app.state.repository.get_snapshot(sid)['world_state']
    raw = arrival(); raw['movements'] = []
    raw['final_scene'].update(present_character_ids=['ilya'], observed_character_ids=['viktoria_solovyova'])
    out = StateResolver(before, 'Виктория стоит в проёме, не заходя.', '').resolve(raw)
    assert out.state['camera']['observed_character_ids'] == ['viktoria_solovyova']
    assert out.state['characters']['viktoria_solovyova']['location_id'] == before['characters']['viktoria_solovyova']['location_id']
    assert out.state['locations'] == before['locations']
    assert not out.history['movements']


@pytest.mark.parametrize('section', ['life_changes', 'movements', 'scheduled_event_changes'])
def test_t32_essential_wrong_type_requires_repair(section):
    with pytest.raises(StructuralDeltaError) as error:
        RawTurnResult.parse(dict(final_scene={}, **{section:{'id':'meaningful'}}))
    assert error.value.repairable
    assert error.value.path['section'] == section


def test_t31_unknown_meaningful_section_diagnostic():
    with pytest.raises(StructuralDeltaError) as error:
        RawTurnResult.parse(dict(final_scene={}, life_change={'id':'npc','life_status':'dead'}))
    assert error.value.code == 'raw_unknown_field'


@pytest.mark.parametrize('section', ['scene_actions','consequences'])
def test_t28_optional_wrong_type_is_local(section):
    raw = RawTurnResult.parse(dict(final_scene={}, **{section:{'broken':True}}))
    assert raw.records[section] == []
    assert raw.warnings[0]['section'] == section


@pytest.mark.parametrize('elapsed', [None, 0, 5, '5', -1, True])
def test_t34_elapsed_is_explicit_and_typed(api, elapsed):
    client, app = api; sid = imported(client)
    before = app.state.repository.get_snapshot(sid)['world_state']
    raw = arrival(); raw['movements']=[]
    if elapsed is None: raw['final_scene'].pop('elapsed_minutes')
    else: raw['final_scene']['elapsed_minutes']=elapsed
    resolver=StateResolver(before, 'Разговор.', '', require_elapsed=True)
    if type(elapsed) is int and elapsed >= 0:
        out=resolver.resolve(raw)
        assert out.state['meta']['world_time']==before['meta']['world_time']+elapsed
    else:
        with pytest.raises(StructuralDeltaError): resolver.resolve(raw)


@pytest.mark.parametrize('field,value', [
    ('present_character_ids',['ilya','missing']),
    ('present_character_ids',['ilya','ilya']),
    ('observed_character_ids',['ilya']),
    ('observed_character_ids',['missing']),
    ('location_id','missing'),
    ('remote_interactions',[dict(actor_id='missing',channel='phone')]),
    ('remote_interactions',[dict(actor_id='ilya',channel='phone')]),
    ('remote_interactions',[dict(actor_id='marina_volkova',channel='phone')]*2),
])
def test_t49_structural_membership_conflict_is_atomic(api,field,value):
    client, app=api; sid=imported(client)
    before=app.state.repository.get_snapshot(sid)['world_state']; original=deepcopy(before)
    raw=arrival();raw['movements']=[];raw['final_scene'][field]=value
    with pytest.raises(StructuralDeltaError): StateResolver(before,'Литературный текст.','').resolve(raw)
    assert before==original


def test_t47_history_route_retained_and_unknown_departure_not_invented(api):
    client,app=api;sid=imported(client);before=app.state.repository.get_snapshot(sid)['world_state']
    raw=arrival();raw['movements']=[]
    inside=StateResolver(before,'Она уже рядом.','').resolve(raw).state
    raw['final_scene']['present_character_ids']=['ilya']
    raw['events']=[dict(id='talk',text='Разговор закончился.',participants=['ilya','viktoria_solovyova'])]
    out=StateResolver(inside,'Она ответила и ушла.','').resolve(raw)
    assert out.state['characters']['viktoria_solovyova']['location_id'] is None
    assert out.history['events'][0]['local_id']=='talk'
    assert not out.history['movements']
    raw['movements']=[dict(actor_id='viktoria_solovyova',to_location_id='salon_lak')]
    moved=StateResolver(inside,'Она ушла в салон.','').resolve(raw)
    assert moved.state['characters']['viktoria_solovyova']['location_id']=='salon_lak'
    assert moved.history['movements'][0]['to_location_id']=='salon_lak'


def test_t01_t25_npc_death_without_permit_quote_or_classification(api):
    client,app=api;sid=imported(client);before=app.state.repository.get_snapshot(sid)['world_state']
    raw=arrival();raw['movements']=[]
    raw['life_changes']=[dict(id='viktoria_solovyova',life_status='dead',assertion='established')]
    raw['events']=[dict(id='death',text='Её дыхание оборвалось.',participants=['viktoria_solovyova'])]
    out=StateResolver(before,'Она осела на пол; дыхание оборвалось.','').resolve(raw)
    assert out.state['characters']['viktoria_solovyova']['life_status']=='dead'
    assert 'viktoria_solovyova' not in out.state['camera']['present_character_ids']
    assert any(x['kind']=='life_changes' for x in out.history['state_changes'])
    assert before['characters']['viktoria_solovyova']['life_status']!='dead'


def test_t38_t39_t42_assembled_prompt_contract_and_override(api):
    from backend.runtime_v3.context import build_context
    from backend.runtime_v3.raw import extraction_schema, prompt_schema
    client,app=api;sid=imported(client);snapshot=app.state.repository.get_snapshot(sid)
    prose='Виктория вошла внутрь. '+('Она огляделась. '*1800)
    messages=build_context(snapshot,[], 'Жду.', 'turn',131072,4096,extraction_text=prose,
        prompts={'state_update_prompt.md':{'content':'CUSTOM OVERRIDE SENTINEL'}})
    wire='\n'.join(m['content'] for m in messages)
    assert prose in wire and wire.count('CUSTOM OVERRIDE SENTINEL')==1
    assert 'narrative-authority-v1' in wire
    for obsolete in ('New arrivals need completed_arrival','New severe harm requires selected candidate_id','movement or situation_evidence'):
        assert obsolete not in wire
    for section in ('life_changes','appearance_deltas','possession_deltas','role_changes','residence_changes','personality_deltas','value_deltas'):
        assert section in wire
    assert 'observed_character_ids' in json.dumps(extraction_schema())
    assert 'observed_character_ids' in json.dumps(prompt_schema())


def test_required_journey_api_jobs_sqlite_phone_reload(tmp_path):
    """#78 fixture: start/arrival/contact/threshold/call/agreement/reload/next turn."""
    import engine
    from test_phone122 import setup, execute, CONFIG
    from test_call_continuity import turn, saved
    from call_continuity_fixture import OFFER
    from backend.repositories.preparation import Repository
    repo,client,sid=setup(tmp_path)  # Actual Start Game job from shared #78 world.
    def physical(observed=False):
        old=repo.get_snapshot(sid)['world_state'];camera=old['camera']
        present=[x for x in camera['present_character_ids'] if x!='qa_marina']
        if not observed:present.append('qa_marina')
        raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=present,
            observed_character_ids=['qa_marina'] if observed else [],elapsed_minutes=0),
            events=[dict(id='conversation',text='Марина отвечает.',participants=[camera['controlled_actor_id'],'qa_marina'],witnesses=[camera['controlled_actor_id']],medium='conversation')])
        with patch('engine.launch'):
            r=client.post(f'/api/saves/{sid}/turns',json=dict(kind='turn',text='Спрашиваю, как дела.',revision=repo.get_save(sid)['revision'],config=CONFIG))
        assert r.status_code==200,r.text
        jid=r.json()['id'];calls=[]
        def provider(**kw):
            if kw['messages'][0]['content'].startswith('Select at most ONE'):yield '{"action":null}';return
            calls.append(kw)
            yield json.dumps(raw) if kw.get('response_format') else ('Марина стоит в проёме.' if observed else 'Марина вошла внутрь и ответила.')
        with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=provider):
            engine.run_job(repo.path,jid,engine.Worker())
        saved(repo,jid);assert len(calls)==2
        state=repo.get_snapshot(sid)['world_state']
        assert ('qa_marina' in state['camera']['present_character_ids']) != observed
        if observed:assert state['characters']['qa_marina']['location_id'] is None
    physical();physical();physical(True)
    with patch('engine.launch'):
        r=client.post(f'/api/saves/{sid}/phone/dispatch',json=dict(revision=repo.get_save(sid)['revision'],config=CONFIG,command=dict(action='call',contact_id='phone-qa_kirill-qa-vera',operation_id='issue136-call')))
    assert r.status_code==200,r.text
    execute(repo,r.json()['job']['id'])
    for text in [OFFER,'Тогда до встречи.']:
        jid,calls=turn(repo,client,sid,text);saved(repo,jid)
        assert calls==['narrative','extraction']
    assert 'office-meeting' in repo.get_snapshot(sid)['world_state']['scheduled_events']
    assert Repository(repo.path).get_snapshot(sid)==repo.get_snapshot(sid)
    physical(True)


@pytest.mark.parametrize('omit', [False, True])
def test_t17_repair_cannot_erase_death_and_preserves_atomic_lineage(api, omit):
    from storage import Storage
    client,app=api;sid=imported(client);repo=app.state.repository
    before=repo.get_snapshot(sid);calls=[]
    raw=arrival();raw['movements']=[]
    raw['life_changes']=[dict(id='viktoria_solovyova',life_status='dead')]
    raw['events']=[dict(id='death',text='Её дыхание оборвалось.',participants=['viktoria_solovyova'])]
    def provider(**kw):
        calls.append(kw)
        if not kw.get('response_format'):yield 'Её дыхание оборвалось.';return
        value=deepcopy(raw)
        if len(calls)==2:value['final_scene']['location_id']='missing-room'
        elif omit:value['life_changes']=[]
        yield json.dumps(value)
    with patch('engine.chat_stream',side_effect=provider):job=wait_job(client,submit(client,sid))
    assert len(calls)==3
    if omit:
        assert job['status']=='error'
        assert repo.get_snapshot(sid)==before and repo.list_turns(sid)==[]
        assert json.loads(repo.get_job(job['id'])['repair_diagnostics_json'])[-1]['repair_error_code']=='extraction_repair_omission'
    else:
        assert job['status']=='saved',job.get('error')
        after=Storage(repo.path).get_snapshot(sid)
        assert after['world_state']['characters']['viktoria_solovyova']['life_status']=='dead'
        assert len(repo.list_turns(sid))==1
        repo.rollback_last(sid)
        assert repo.get_snapshot(sid)==before


@pytest.mark.parametrize('authorization', ['none','forged','player','involuntary'])
def test_t50_controlled_movement_requires_owned_source(api, authorization):
    client,app=api;sid=imported(client);before=app.state.repository.get_snapshot(sid)['world_state']
    raw=arrival();raw['final_scene'].update(location_id='salon_lak',present_character_ids=['ilya'])
    move=dict(actor_id='ilya',to_location_id='salon_lak')
    raw['movements']=[move]
    player='Иду в салон.'
    if authorization in ('player','forged'):
        move.update(player_assertion='explicit_choice',player_evidence=player)
        if authorization=='forged':player='Смотрю в окно.'
    if authorization=='involuntary':
        move.update(player_assertion='involuntary',source_event_id='carried')
        raw['events']=[dict(id='carried',text='Его перенесли в салон.',participants=['ilya','viktoria_solovyova'])]
    if authorization in ('none','forged'):
        with pytest.raises(StructuralDeltaError) as exc:StateResolver(before,'Переход завершён.',player).resolve(raw)
        assert exc.value.code=='movement_agency'
    else:
        after=StateResolver(before,'Переход завершён.',player).resolve(raw)
        assert after.state['characters']['ilya']['location_id']=='salon_lak'


def test_t31_nested_life_typo_is_visible():
    with pytest.raises(StructuralDeltaError) as exc:
        RawTurnResult.parse(dict(final_scene={},life_changes=[dict(id='npc',life_stauts='dead')]))
    assert exc.value.path['path']=='life_changes[0].life_stauts'


def test_retry_after_restart_cannot_erase_classified_outcome(api):
    from test_runtime_handoff import REMOTE
    client,app=api;sid=imported(client);repo=app.state.repository;before=repo.get_snapshot(sid)
    bad=arrival();bad['movements']=[];bad['final_scene']['location_id']='missing'
    bad['life_changes']=[dict(id='viktoria_solovyova',life_status='dead')]
    def first(**kw):yield json.dumps(bad) if kw.get('response_format') else 'Её дыхание оборвалось.'
    with patch('engine.chat_stream',side_effect=first):job=wait_job(client,submit(client,sid))
    assert job['status']=='error'
    calls=[];omitted=arrival();omitted['movements']=[]
    def retry(**kw):calls.append(kw);yield json.dumps(omitted)
    with patch('engine.chat_stream',side_effect=retry):
        response=client.post(f"/api/jobs/{job['id']}/retry",json=dict(config=REMOTE,api_key='test-secret'))
        assert response.status_code==200,response.text
        result=wait_job(client,job['id'])
    assert result['status']=='error' and len(calls)==1
    assert repo.get_snapshot(sid)==before and repo.list_turns(sid)==[]
    assert json.loads(repo.get_job(job['id'])['repair_diagnostics_json'])[-1]['repair_error_code']=='extraction_repair_omission'


def test_observed_stale_colocation_clears_only_unknown_position(api):
    client,app=api;sid=imported(client);before=app.state.repository.get_snapshot(sid)['world_state']
    before['characters']['viktoria_solovyova']['location_id']='ilya_cabinet'
    raw=arrival();raw['movements']=[]
    raw['final_scene'].update(present_character_ids=['ilya'],observed_character_ids=['viktoria_solovyova'])
    out=StateResolver(before,'Она видна за открытым окном.','').resolve(raw)
    assert out.state['characters']['viktoria_solovyova']['location_id'] is None
    assert not out.history['movements'] and out.state['locations']==before['locations']


def test_offcamera_protected_movement_cannot_borrow_pov_agency(api):
    client,app=api;sid=imported(client);before=app.state.repository.get_snapshot(sid)['world_state']
    before['camera'].update(mode='observer',present_character_ids=[])
    raw=dict(final_scene=dict(location_id='salon_lak',present_character_ids=['viktoria_solovyova']),
             movements=[dict(actor_id='ilya',to_location_id='salon_lak')])
    with pytest.raises(StructuralDeltaError) as exc:StateResolver(before,'Илья теперь в салоне.','').resolve(raw)
    assert exc.value.code=='movement_agency'


@pytest.mark.parametrize('damage', ['elapsed_missing','elapsed_type','life_changes','movements','scheduled_event_changes'])
def test_structural_repair_uses_one_narrative_and_one_commit(api, damage):
    client,app=api;sid=imported(client);repo=app.state.repository;calls=[]
    good=arrival();good['movements']=[]
    bad=deepcopy(good)
    if damage=='elapsed_missing':bad['final_scene'].pop('elapsed_minutes')
    elif damage=='elapsed_type':bad['final_scene']['elapsed_minutes']='1'
    else:bad[damage]={'id':'damaged-envelope'}
    # Ordinary turns require explicit elapsed; establish Start Game first.
    def start(**kw):yield json.dumps(good) if kw.get('response_format') else 'Виктория вошла.'
    with patch('engine.chat_stream',side_effect=start):assert wait_job(client,submit(client,sid))['status']=='saved'
    before=repo.get_snapshot(sid)
    def provider(**kw):
        calls.append(kw)
        yield (json.dumps(bad if len(calls)==2 else good) if kw.get('response_format') else 'Она отвечает на вопрос.')
    with patch('engine.chat_stream',side_effect=provider):job=wait_job(client,submit(client,sid,'turn','Спрашиваю, как дела.'))
    assert job['status']=='saved',job.get('error')
    assert len(calls)==3 and sum(not c.get('response_format') for c in calls)==1
    assert len(repo.list_turns(sid))==2
    assert repo.get_snapshot(sid)['world_state']['meta']['world_time']==before['world_state']['meta']['world_time']+1
