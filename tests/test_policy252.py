"""#252 structural controls. Authored JSON is never a new model-semantic PASS."""
from copy import deepcopy
import json
from threading import Event
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator
import engine
from backend.repositories.preparation import Repository
from backend.runtime_v3.context import build_context
from backend.runtime_v3.models import Location, Thread, WorldHistoryV3
from backend.runtime_v3.player_actions import resolver_options
from backend.runtime_v3.raw import RawTurnResult, compile_semantic, prompt_schema
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.simulation import simulate
from backend.services.world_delta_errors import StructuralDeltaError
from test_reproduction import state, snap
from test_integrated_repair247 import archived, seed, execute, history, corrected

CONFIG = dict(model='test', context_length=65536, max_tokens=2000, update_tokens=8192)


def raw(s):
    return dict(final_scene=dict(location_id=s['camera']['location_id'],
        present_character_ids=list(s['camera']['present_character_ids']), elapsed_minutes=0))


def resolve(s, p, **kwargs):
    return StateResolver(s, 'Авторский контроль.', '', **resolver_options(s, '', contract_version=5), **kwargs).resolve(p)


def info():
    return dict(id='tell', text='Вера сообщила два факта.', source_actor_id='b', medium='conversation',
        claims=[dict(fact=dict(id='local-one', text='Первый факт.'), assertion='testimony', perceived_by=['a','c'], status='known'),
                dict(fact=dict(id='local-two', text='Второй факт.'), assertion='testimony', perceived_by=['a','c'], status='known')])


def test_information_schema_compilation_and_four_perceptions():
    s=state(); p=raw(s); p['information_events']=[info()]
    Draft202012Validator(prompt_schema(semantic_slice=True, explicit_departures=True, consequence_first=True)).validate(p)
    original=deepcopy(p)
    result=resolve(s,p)
    assert len(result.history['knowledge_acquisitions'])==4
    assert len(result.history['events'])==1
    assert len(result.state['facts'])==2
    e=result.history['events'][0]
    assert e['information_source']['actor_id']=='b'
    assert set(e['witnesses'])=={'a','c'}
    assert not any(k.startswith('b:') for k in result.state['knowledge'])
    assert all(k['source_event_id']==e['id'] for k in result.state['knowledge'].values())
    assert resolve(s,p).history==result.history and p==original
    parsed=RawTurnResult.parse(p)
    compiled=compile_semantic(parsed,s,'Авторский контроль.',1)
    assert compile_semantic(compiled,s,'Авторский контроль.',1)==compiled


@pytest.mark.parametrize('damage', ['offscene','rumor_known','duplicate','unknown_fact','missing_source'])
def test_information_negative_controls_are_atomic(damage):
    s=state(); p=raw(s); p['information_events']=[info()]; original=deepcopy(s)
    if damage=='offscene':
        s['locations']['remote']=Location(id='remote',name='Далеко').model_dump()
        s['characters']['c']['location_id']='remote'; original=deepcopy(s)
    elif damage=='rumor_known': p['information_events'][0]['claims'][0]['assertion']='rumor'
    elif damage=='duplicate': p['events']=[dict(id='tell',text='Дубликат')]
    elif damage=='unknown_fact': p['information_events'][0]['claims'][0]=dict(fact_id='missing',assertion='testimony',perceived_by=['a'],status='known')
    else: p['information_events'][0]['source_actor_id']='missing'
    with pytest.raises(StructuralDeltaError): resolve(s,p)
    assert s==original


def test_perception_is_per_claim_and_rumor_is_only_suspected():
    s=state(); p=raw(s); item=info()
    item['claims'][0].update(assertion='rumor',status='suspected',perceived_by=['c'])
    item['claims'][1]['perceived_by']=['a']
    p['information_events']=[item]
    result=resolve(s,p)
    assert len(result.state['knowledge'])==2
    assert sorted(k['status'] for k in result.state['knowledge'].values())==['known','suspected']
    assert not any(k['actor_id']=='b' for k in result.state['knowledge'].values())


def test_recorded_knowledge_scene_compact_control_commit_reload_rollback(tmp_path):
    data=archived('knowledge'); repo=Repository(tmp_path/'knowledge.sqlite'); sid=seed(repo,data)['save']
    p=corrected(data)
    # Original prose/input and other domains retained. Only representation is authored.
    facts=p.pop('facts'); acquisitions=p.pop('knowledge_gained')
    event=p['events'][0]; event['fact_ids']=[]
    p['information_events']=[dict(id='vera-reply',text='Вера сообщила день рождения и расположение каталога.',evidence='\n'.join(f['evidence'] for f in facts),
        source_actor_id='qa_vera',medium='conversation',location_id='qa_home',order=2,
        claims=[dict(fact={k:v for k,v in f.items() if k!='evidence'},assertion='testimony',status='known',perceived_by=[k['actor_id'] for k in acquisitions if k['fact_id']==f['id']]) for f in facts])]
    before=repo.get_snapshot(sid)
    job,calls=execute(repo,sid,data,[p],legacy=False,config=CONFIG)
    assert job['status']=='saved',job['error']
    assert len(calls)==2
    fresh=Repository(repo.path); after=fresh.get_snapshot(sid)
    acquired=history(fresh,sid)['knowledge_acquisitions'][-4:]
    assert len(acquired)==4 and {a['actor_id'] for a in acquired}=={'qa_kirill','qa_timur'}
    assert all(after['world_state']['knowledge'][a['actor_id']+':'+a['fact_id']]['source_event_id']==a['source_event_id'] for a in acquired)
    # Actual source data never changed.
    assert archived('knowledge')==data
    assert before['world_state']['knowledge']!=after['world_state']['knowledge']


@pytest.mark.parametrize('assertion,target', [('intent','away'),('attempt','away'),('departure',None),('completed_arrival','away')])
def test_movement_semantics_and_false_arrival_limit(assertion,target):
    s=state(); s['locations']['away']=Location(id='away',name='Другое место').model_dump()
    p=raw(s); p['movements']=[dict(actor_id='c',from_location_id='home',to_location_id=target,assertion=assertion)]
    result=resolve(s,p)
    assert result.state['characters']['c']['location_id']==(target if assertion in ('departure','completed_arrival') else 'home')
    # A model falsely asserting completed_arrival still needs semantic evaluation.


@pytest.mark.parametrize('version', [4,5])
def test_production_background_contract_arrival_without_duplicate_event(version):
    from test_background_time import fixture
    before=fixture(); after=deepcopy(before)
    after['world_state']['meta']['world_time']+=240
    after['world_state']['meta']['turn_id']+=1
    sent=[]; kwargs_seen=[]
    real=StateResolver
    def resolver(*args,**kwargs):
        kwargs_seen.append(kwargs); return real(*args,**kwargs)
    def generate(stage,messages,*args,**kwargs):
        sent.append((stage,messages))
        if stage=='world_simulation': return iter(['Олег пришёл в новую комнату.'])
        current=json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('Текущее состояние / GM-only\n')))
        p=raw(dict(camera=current['camera']))
        p['final_scene'].update(location_id='new-room',present_character_ids=['qa_oleg'])
        p['locations']=[dict(id='new-room',name='Комната')]
        p['movements']=[dict(actor_id='qa_oleg',from_location_id=after['world_state']['characters']['qa_oleg']['location_id'],to_location_id='new-room',assertion='completed_arrival')]
        return iter([json.dumps(p)])
    warnings=[]
    with patch('backend.runtime_v3.simulation.StateResolver',side_effect=resolver):
        result,batch=simulate(before,after,WorldHistoryV3().to_dict(),65536,dict(CONFIG,_extraction_contract=version),generate,Event(),warnings,lambda row:None)
    assert result['world_state']['characters']['qa_oleg']['location_id']=='new-room',warnings
    assert len(sent)==2
    assert kwargs_seen[0]['consequence_first'] and kwargs_seen[0]['semantic_slice']==(version>=5)
    assert len(batch['movements'])==1


@pytest.mark.parametrize('version', [4,5])
def test_production_lta_arrival_keeps_reason_without_duplicate_arrival_event(version):
    from backend.runtime_v3.long_term import plan,run
    before=snap(state()); before['world_state']['threads']['education']=Thread(id='education',description='Учёба',character_ids=['c'],relevance=1).model_dump()
    candidate=next(c for c in plan(before,dict(amount=5,unit='years')).candidates if c.source_id=='education')
    sent=[]
    def generate(stage,messages,*args,**kwargs):
        sent.append((stage,messages))
        if stage=='long_term_narrative': return iter(['Он пришёл учиться.'])
        p=dict(final_scene=dict(location_id='school',present_character_ids=['c'],elapsed_minutes=0),
            locations=[dict(id='school',name='Школа')],movements=[dict(actor_id='c',from_location_id='home',to_location_id='school',assertion='completed_arrival')],
            events=[dict(id='study',text='Начал занятие.',participants=['c'],witnesses=['c'],medium='observation',advance_candidate_ids=[candidate.id])])
        return iter([json.dumps(p)])
    result,batch,report=run(before,dict(amount=5,unit='years',max_llm_calls=2),generate=generate,config=dict(CONFIG,_extraction_contract=version))
    assert report['accepted'],report['diagnostics']
    assert result['world_state']['characters']['c']['location_id']=='school'
    assert len(sent)==2 and len(batch['movements'])==1


@pytest.mark.parametrize('assertion,days,expected', [('narrator',1,'conflict'),('narrator',5,'ok'),('belief',1,'ok'),('lie',1,'ok'),('quotation',1,'ok')])
def test_typed_chronology_uses_event_not_recording_time(assertion,days,expected):
    s=state(); s['meta']['world_time']=5*1440
    p=raw(s);p['chronology_claims']=[dict(event_id='meeting',assertion=assertion,elapsed_days=days,evidence='Вчера они встретились.')]
    events=[dict(id='meeting',minute=0,recorded_minute=5*1440,text='Встреча.')]
    if expected=='conflict':
        with pytest.raises(StructuralDeltaError) as error: resolve(s,p,chronology_events=events)
        assert not error.value.repairable
        assert error.value.path['chronology']['actual_elapsed_days']==5
    else: resolve(s,p,chronology_events=events)


def test_unknown_event_time_is_never_guessed():
    s=state();p=raw(s);p['chronology_claims']=[dict(event_id='meeting',assertion='narrator',elapsed_days=1,evidence='Вчера.')]
    with pytest.raises(StructuralDeltaError,match='recorded_minute'):
        resolve(s,p,chronology_events=[dict(id='meeting',recorded_minute=0)])


def test_current_npc_conversation_is_relationship_source_without_optional_marker():
    s=state();p=raw(s)
    p['events']=[dict(id='help',text='Они помогли друг другу.',participants=['b','c'],witnesses=['b','c'],medium='conversation',actor_id='b',target_ids=['c'])]
    p['relationship_changes']=[dict(source_id='b',target_id='c',source_event_ids=['help'],assertion='grounded_feelings',rationale='Совместная помощь.',dimensions={'trust':3})]
    result=resolve(s,p)
    assert result.state['relationships']['b:c']['dimensions']['trust']==3
    assert 'c:b' not in result.state['relationships']
    assert result.history['relationship_changes'][0]['source_event_ids']==[result.history['events'][0]['id']]


def test_original_phone_false_arrival_remains_semantic_failure_not_pass():
    data=archived('phone')
    # Original model output is structurally accepted but is semantically FALSE.
    result=StateResolver(data['before'],data['narrative'],data['player_input'],**resolver_options(data['before'],data['player_input'],contract_version=5)).resolve(data['responses'][0]['payload'])
    assert result.history['movements']
    assert any(result.state['characters'][cid]['location_id']!=data['before']['characters'][cid]['location_id'] for cid in ('qa_timur','qa_vera'))


def seed_chronology(repo):
    """Authored dated checkpoint built by real Resolver/History, not an archive replay."""
    from backend.runtime_v3.repository import append_history
    data=archived('knowledge'); selection=seed(repo,data);sid=selection['save']
    snapshot=repo.get_snapshot(sid);s=snapshot['world_state'];p=raw(s)
    p['events']=[dict(id='old-meeting',text='Вера встретилась с Тимуром.',participants=['qa_vera','qa_timur'],witnesses=['qa_vera','qa_timur'],medium='conversation',minute=s['meta']['world_time'])]
    first=StateResolver(s,'Вера встретилась с Тимуром.','',**resolver_options(s,'',contract_version=5)).resolve(p)
    p=raw(first.state);p['final_scene']['elapsed_minutes']=7200
    later=StateResolver(first.state,'Прошло пять дней.','').resolve(p)
    with repo.connect() as db:
        head=append_history(db,snapshot['history_head'],first.history,before=s,after=first.state)
        head=append_history(db,head,later.history,before=first.state,after=later.state)
        snapshot.update(world_state=later.state,history_head=head)
        snapshot.pop('background_considerations',None)
        db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot),sid))
        db.execute('UPDATE turns SET sequence=? WHERE save_id=?',(later.state['meta']['turn_id'],sid))
    selection.update(action='Слушаю разговор.',narrative='Комната затихла. Вчера Вера встретилась с Тимуром. За окном шёл дождь.',
        event_id=first.history['events'][0]['id'])
    return selection


def chronology_payload(repo,sid,event_id,days=1):
    p=raw(repo.get_snapshot(sid)['world_state'])
    p['chronology_claims']=[dict(event_id=event_id,assertion='narrator',elapsed_days=days,
        evidence='Вчера Вера встретилась с Тимуром.' if days==1 else 'Пять дней назад Вера встретилась с Тимуром.')]
    return p


def test_explicit_correction_new_candidate_new_extraction_lineage_and_rollback(tmp_path):
    repo=Repository(tmp_path/'chronology.sqlite');selected=seed_chronology(repo);sid=selected['save']
    data=dict(player_input=selected['action'],narrative=selected['narrative'])
    before=repo.get_snapshot(sid);old_history=history(repo,sid);old_turns=repo.list_turns(sid)
    failed,calls=execute(repo,sid,data,[chronology_payload(repo,sid,selected['event_id'])],config=CONFIG,legacy=False)
    assert failed['status']=='error' and len(calls)==2
    assert repo.get_snapshot(sid)==before and history(repo,sid)==old_history
    public=repo.public_job(failed)
    assert public['chronology_correction_available'] and not public['retry_allowed']
    with pytest.raises(ValueError):repo.retry_job(failed['id'],CONFIG)
    new_id=repo.correct_chronology_job(failed['id'],failed['revision'],failed['attempt_epoch'])
    assert new_id!=failed['id']
    assert repo.get_job(failed['id'])['narrative']==selected['narrative']
    calls=[]
    def stream(**kw):
        calls.append(kw)
        if 'Исправь только хронологические' in str(kw['messages']):
            yield json.dumps(dict(edits=[dict(original='Вчера Вера встретилась с Тимуром.',replacement='Пять дней назад Вера встретилась с Тимуром.')]),ensure_ascii=False)
        else:
            assert 'Пять дней назад' in str(kw['messages'])
            yield json.dumps(chronology_payload(repo,sid,selected['event_id'],5),ensure_ascii=False)
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,new_id,engine.Worker())
    accepted=repo.get_job(new_id)
    assert accepted['status']=='saved',accepted['error']
    assert len(calls)==2 and all(c.get('response_format') for c in calls)
    assert accepted['narrative']==selected['narrative'].replace('Вчера','Пять дней назад')
    assert repo.list_turns(sid)[:-1]==old_turns
    assert repo.get_job(failed['id'])['narrative']==selected['narrative']
    stages=[r['stage'] for r in repo.request_log(job_id=new_id)]
    assert stages==['extraction','narrative_correction']
    repo=Repository(repo.path)
    assert repo.get_job(new_id)['status']=='saved'
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)['world_state']==before['world_state']
    assert history(repo,sid)==old_history


@pytest.mark.parametrize('damage',['stale','cancelled','bad_edit','unchanged','overlap'])
def test_correction_never_publishes_invalid_or_stale_candidate(tmp_path,damage):
    from backend.runtime_v3.continuity import corrected_candidate
    if damage in ('bad_edit','unchanged','overlap'):
        source='Вчера была встреча.'
        grounds=[dict(evidence=source)]
        if damage=='overlap':grounds.append(dict(evidence='Вчера'))
        edits=[dict(original=source if damage!='bad_edit' else 'Встреча.',replacement=source if damage=='unchanged' else 'Пять дней назад была встреча.')]
        if damage=='overlap':edits.append(dict(original='Вчера',replacement='Недавно'))
        with pytest.raises(ValueError):corrected_candidate(source,json.dumps(dict(edits=edits)),grounds)
        return
    repo=Repository(tmp_path/'stale.sqlite');sel=seed_chronology(repo);sid=sel['save']
    failed,_=execute(repo,sid,dict(player_input=sel['action'],narrative=sel['narrative']),[chronology_payload(repo,sid,sel['event_id'])],legacy=False,config=CONFIG)
    if damage=='stale':
        with repo.connect() as db:db.execute('UPDATE saves SET revision=revision+1 WHERE id=?',(sid,))
        with pytest.raises(ValueError):repo.correct_chronology_job(failed['id'],failed['revision'],failed['attempt_epoch'])
        assert repo.get_job(failed['id'])['status']=='error'
    else:
        new=repo.correct_chronology_job(failed['id'],failed['revision'],failed['attempt_epoch'])
        before=repo.get_snapshot(sid)
        repo.job_progress(new,'stopped')
        with patch('engine.chat_stream') as provider:engine.run_job(repo.path,new,engine.Worker())
        provider.assert_not_called()
        assert repo.get_snapshot(sid)==before


def test_correction_api_uses_recorded_config_and_persists_source(tmp_path):
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    app=create_app(tmp_path/'api.sqlite',recover=False);repo=app.state.repository
    sel=seed_chronology(repo);sid=sel['save']
    failed,_=execute(repo,sid,dict(player_input=sel['action'],narrative=sel['narrative']),[chronology_payload(repo,sid,sel['event_id'])],legacy=False,config=CONFIG)
    with TestClient(app) as client, patch('engine.launch') as launch:
        response=client.post('/api/jobs/'+failed['id']+'/retry',json=dict(config=dict(CONFIG,model='different'),correct_chronology=True,revision=failed['revision'],attempt_epoch=failed['attempt_epoch']))
        assert response.status_code==200,response.text
        candidate=response.json()
        assert candidate['id']!=failed['id']
        launch.assert_called_once()
        config=json.loads(repo.get_job(candidate['id'])['config_json'])
        assert config['model']=='test' and config['_extraction_contract']==5
        assert config['_narrative_correction']['source_job_id']==failed['id']
        assert 'config_json' not in candidate and 'chronology' not in candidate
        assert repo.get_job(failed['id'])['narrative']==sel['narrative']


def test_semantic_knowledge_sqlite_failure_publishes_nothing(tmp_path):
    data=archived('knowledge');repo=Repository(tmp_path/'failure.sqlite');sid=seed(repo,data)['save']
    s=repo.get_snapshot(sid)['world_state'];p=raw(s)
    p['information_events']=[dict(text='Вера сообщила адрес.',source_actor_id='qa_vera',medium='conversation',
        claims=[dict(fact=dict(text='Адрес каталога.'),assertion='testimony',status='known',perceived_by=['qa_kirill','qa_timur'])])]
    before=repo.get_snapshot(sid);old_history=history(repo,sid);turns=repo.list_turns(sid)
    with repo.connect() as db:
        db.execute("CREATE TRIGGER fail252 BEFORE INSERT ON turns BEGIN SELECT RAISE(ABORT, 'injected252'); END")
    job,_=execute(repo,sid,data,[p],config=CONFIG,legacy=False)
    assert job['status']=='error' and 'injected252' in job['error']
    assert repo.get_snapshot(sid)==before and history(repo,sid)==old_history and repo.list_turns(sid)==turns


def test_information_local_alias_cannot_double_apply_legacy_knowledge():
    s=state();p=raw(s);p['information_events']=[info()]
    p['knowledge_gained']=[dict(actor_id='a',fact_id='local-one',source_event_id='tell')]
    with pytest.raises(StructuralDeltaError) as exc: resolve(s,p)
    assert exc.value.code=='semantic_duplicate'


@pytest.mark.parametrize('case', ['test_npc_experience_changes_personality_and_preserves_role_chronology', 'test_accepted_birth_then_child_ages_without_adult_personality'])
def test_existing_lta_lifecycle_controls_with_contract5(monkeypatch,case):
    import test_long_term_advance as suite
    original=suite.run
    def run(*args,**kwargs):
        kwargs['config']=dict(kwargs.get('config') or {},_extraction_contract=5)
        return original(*args,**kwargs)
    monkeypatch.setattr(suite,'run',run)
    getattr(suite,case)()


@pytest.mark.parametrize('mode', ['turn','background'])
def test_compiled_perception_unknown_source_is_not_silently_lost(mode):
    s=state();p=raw(s);p['information_events']=[info()]
    p['information_events'][0]['source_actor_id']='missing'
    for claim in p['information_events'][0]['claims']: claim['perceived_by']=['c']
    with pytest.raises(StructuralDeltaError,match='неизвестного персонажа'):
        resolve(s,p,mode=mode)


def test_compiled_background_perception_cannot_change_foreground_knowledge():
    s=state();p=raw(s);p['information_events']=[info()]
    with pytest.raises(StructuralDeltaError,match='Фоновое событие'):
        resolve(s,p,mode='background',protected_knowledge_actor_ids={'a'})


@pytest.mark.parametrize('authorized', [False,True])
def test_information_speaker_preserves_player_agency_and_independent_perceivers(authorized):
    s=state();p=raw(s);item=info();item['source_actor_id']='a';item['target_ids']=['b']
    for claim in item['claims']: claim['perceived_by']=['b','c']
    p['information_events']=[item];text='Рассказываю b два факта.'
    if authorized:
        item['player_action_id']='tell'
        p['player_agency']=dict(status='preserved',actions=[dict(id='tell',player_evidence=text,
            target_ids=['b'],narrative_target_ids=['b'],target_mode='interaction',outcome='completed',meaning='preserved')])
    resolver=StateResolver(s,text,text,**resolver_options(s,text,contract_version=5))
    if authorized:
        result=resolver.resolve(p)
        assert len(result.history['knowledge_acquisitions'])==4
        assert result.history['events'][0]['target_ids']==['b']
    else:
        with pytest.raises(StructuralDeltaError,match='player_action_id'): resolver.resolve(p)


@pytest.mark.parametrize('damage',['source','revision','agency','planned'])
def test_significant_possession_loss_is_repairable_not_silent(damage):
    from test_possessions import state as possession_state, delta, payload, TEXT
    s=possession_state();c=delta(s);p=payload(s,c);p['final_scene']['elapsed_minutes']=0;before=deepcopy(s)
    if damage=='source': p['possession_deltas'][0]['source_event_id']='missing'
    elif damage=='revision': p['possession_deltas'][0]['expected_revision']=2
    elif damage=='agency':
        c.update(transition='voluntary',decision_actor_id='a',updates=dict(owner_id='a',holder_id='a'))
    else: c['assertion']='planned'
    resolver=StateResolver(s,TEXT,'',**resolver_options(s,'',contract_version=5))
    if damage=='planned':
        result=resolver.resolve(p);assert result.warnings and not result.state['possessions']
    else:
        with pytest.raises(StructuralDeltaError) as exc:resolver.resolve(p)
        assert exc.value.repairable and exc.value.code in ('possession_rejected','possession_invalid')
    assert s==before


@pytest.mark.parametrize('assertion',['absent','belief','narrator'])
def test_corrected_chronology_must_be_reinterpreted(assertion):
    from backend.runtime_v3.continuity import require_chronology_recheck
    p=raw(state())
    if assertion!='absent':p['chronology_claims']=[dict(event_id='e',assertion=assertion,elapsed_days=5,evidence='Пять дней назад.')]
    if assertion=='narrator':require_chronology_recheck(RawTurnResult.parse(p),[dict(event_id='e')])
    else:
        with pytest.raises(StructuralDeltaError):require_chronology_recheck(RawTurnResult.parse(p),[dict(event_id='e')])


@pytest.mark.parametrize('profile,start',[(dict(system='gregorian'),'2026-01-01'),(dict(system='custom',month_lengths=[20,25],weekday_names=['A','B','C']), '0042-01-19'),(dict(system='gregorian'),None)])
def test_chronology_respects_calendar_and_unknown_dates(profile,start):
    from test_calendar_v2 import state as calendar_state
    s=calendar_state(start,0,0,profile)
    s['meta']['world_time']=7200;p=raw(s)
    p['chronology_claims']=[dict(event_id='meeting',assertion='narrator',elapsed_days=1,evidence='Вчера.')]
    with pytest.raises(StructuralDeltaError) as exc:resolve(s,p,chronology_events=[dict(id='meeting',minute=0)])
    assert exc.value.path['chronology']['actual_elapsed_days']==5
    assert (exc.value.path['chronology']['event_date'] is None)==(start is None)


def test_documented_compact_example_matches_schema_and_runtime():
    from pathlib import Path
    example=json.loads((Path(__file__).parent/'fixtures/policy252/compact.json').read_text())
    Draft202012Validator(prompt_schema(semantic_slice=True,explicit_departures=True,consequence_first=True)).validate(example)
    result=resolve(state(),example)
    assert len(result.history['knowledge_acquisitions'])==4
    assert sorted(k['status'] for k in result.state['knowledge'].values())==['known','known','suspected','suspected']
    assert not result.history['movements']


def test_lta_information_and_current_npc_relationship_share_canonical_event():
    from backend.runtime_v3.long_term import plan,run
    before=snap(state());before['world_state']['threads']['study']=Thread(id='study',description='Учёба вместе',character_ids=['b','c'],relevance=1).model_dump()
    candidate=next(c for c in plan(before,dict(amount=5,unit='years')).candidates if c.source_id=='study')
    def generate(stage,messages,*args,**kwargs):
        if stage=='long_term_narrative':return iter(['c помог b разобраться с учебным заданием.'])
        p=raw(before['world_state']);p['final_scene']['present_character_ids']=['b','c']
        p['information_events']=[dict(id='lesson',text='c объяснил b учебный материал.',source_actor_id='c',target_ids=['b'],medium='conversation',advance_candidate_ids=[candidate.id],
            claims=[dict(fact=dict(text='Свойство изученного вещества.'),assertion='testimony',perceived_by=['b'],status='known')])]
        p['relationship_changes']=[dict(source_id='b',target_id='c',source_event_ids=['lesson'],assertion='grounded_feelings',rationale='Помощь с трудной задачей.',dimensions={'trust':3})]
        return iter([json.dumps(p)])
    result,batch,report=run(before,dict(amount=5,unit='years',max_llm_calls=2),generate=generate,config=dict(CONFIG,_extraction_contract=5))
    assert report['accepted'],report['diagnostics']
    assert len(batch['knowledge_acquisitions'])==1 and len(result['world_state']['facts'])==1
    assert result['world_state']['relationships']['b:c']['dimensions']['trust']==3
    assert 'c:b' not in result['world_state']['relationships']
    assert batch['knowledge_acquisitions'][0]['source_event_id']==batch['relationship_changes'][0]['source_event_ids'][0]


def test_npc_experience_source_cannot_disappear_before_later_development():
    from test_personality import setup,payload,TEXT
    s=setup()['world_state'];p=payload(s);p['final_scene']['elapsed_minutes']=0
    p['development_evidence'][0]['source_event_id']='missing'
    with pytest.raises(StructuralDeltaError) as exc:
        StateResolver(s,TEXT,'',**resolver_options(s,'',contract_version=5)).resolve(p)
    assert exc.value.code=='development_source_invalid' and exc.value.repairable


def test_optional_contact_annotation_is_not_an_independent_scene_gate():
    s=state();p=raw(s)
    p['events']=[dict(id='talk',text='b говорит.',actor_id='b',target_ids=['missing'],participants=['b'],medium='conversation')]
    result=resolve(s,p)
    assert len(result.history['events'])==1 and 'target_ids' not in result.history['events'][0]
    assert any(w.get('code')=='event_contact_annotation_ignored' for w in result.warnings)
    p['relationship_changes']=[dict(source_id='b',target_id='c',source_event_ids=['talk'],assertion='grounded_feelings',rationale='Общение',dimensions={'trust':3})]
    with pytest.raises(StructuralDeltaError,match='адресаты'):resolve(s,p)
