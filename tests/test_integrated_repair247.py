"""Original #245 replies; corrected JSON is a test control, never Live QA."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import engine
from context_builder import build_context, estimate
from backend.repositories.preparation import Repository
from backend.runtime_v3.repository import read_history
from backend.runtime_v3.raw import repair_feedback, extraction_schema
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from devtools.narrative_test_world import load_fixture
from test_narrative_test_world import ordinary_job

ROOT = Path(__file__).parent / 'fixtures' / 'issue247'
CONFIG = dict(model='test', context_length=49152, max_tokens=2000, update_tokens=4096)


def archived(case):
    return json.loads((ROOT / (case+'.json')).read_text())


def corrected(data):
    raw = deepcopy(data['responses'][-1]['payload'])
    case = data['case']
    if case == 'knowledge':
        by_event = {}
        for row in raw['knowledge_gained']:
            by_event.setdefault(row['source_event_id'], set()).add(row['fact_id'])
        for event in raw['events']:
            event['fact_ids'] = sorted(by_event.get(event['id'], set(event.get('fact_ids', []))))
    elif case == 'family':
        raw['player_agency']['actions'][0]['target_mode'] = 'reference'
        raw['final_scene']['elapsed_minutes'] = 0
    elif case == 'crisis':
        # The original prose itself invents the conversation; do not launder it.
        raw['player_agency']['status'] = 'violated'
    elif case == 'phone':
        # Human-reviewed control: Timur stands by the table; Vera is still in
        # the house. The original camera denotes the house, not just the table.
        raw['movements'] = []
        raw['final_scene']['present_character_ids'] = list(data['before']['camera']['present_character_ids'])
        raw['final_scene']['situation'] = 'Кирилл рассматривает фотографии. Тимур стоит у стола; Вера собирается в глубине дома.'
        raw['events'][0]['text'] = 'Вера объявила о сборах и отошла в глубину дома.'
        raw['events'][1]['text'] = 'Тимур встал у стола и пообещал занести фотографии Олегу.'
        for row in raw['character_changes']:
            row['situation'] = {'qa_kirill':'Рассматривает фотографии.',
                'qa_vera':'Собирается в глубине дома.', 'qa_timur':'Стоит у стола с фотографиями.'}[row['id']]
    return raw


def seed(repo, data):
    selected = load_fixture(repo)
    sid = selected['save']
    ordinary_job(repo, sid, 'start')
    snapshot = repo.get_snapshot(sid)
    snapshot['world_state'] = deepcopy(data['before'])
    snapshot.pop('background_considerations', None)  # Imported checkpoint owns its own clock.
    # Import the exact before state into test-only lineage; never modify evidence.
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?', (json.dumps(snapshot), sid))
        db.execute('UPDATE turns SET sequence=? WHERE save_id=?', (data['before']['meta']['turn_id'], sid))
    return selected


def history(repo, sid):
    with repo.connect() as db:
        return read_history(db, repo.get_snapshot(sid)['history_head'])[0]


def execute(repo, sid, data, replies, *, retry=None, kind='turn', config=None, legacy=True, contract_version=None):
    config = config or CONFIG
    if retry:
        repo.retry_job(retry, config)
    jid = retry or repo.begin_job(sid, data['player_input'] if kind=='turn' else '', kind, config)
    if legacy and not retry and kind != 'regenerate':
        with repo.connect() as db:
            saved = json.loads(repo.get_job(jid)['config_json'])
            saved.pop('_extraction_contract', None)
            db.execute('UPDATE game_jobs SET config_json=? WHERE id=?', (json.dumps(saved), jid))
    if contract_version is not None:
        assert not retry and kind != 'regenerate'
        with repo.connect() as db:
            saved = json.loads(repo.get_job(jid)['config_json'])
            saved['_extraction_contract'] = contract_version
            db.execute('UPDATE game_jobs SET config_json=? WHERE id=?', (json.dumps(saved), jid))
    calls = []
    replies = iter(deepcopy(replies))
    def stream(**kw):
        calls.append(kw)
        if kw['messages'][0]['content'].startswith('Select at most ONE optional grounded autonomous remote action.'):
            yield json.dumps({'action':None})
        else:
            yield json.dumps(next(replies), ensure_ascii=False) if kw.get('response_format') else data['narrative']
    with patch('engine.find_loaded_model', return_value={'config':{}}), patch('engine.chat_stream', side_effect=stream):
        engine.run_job(repo.path, jid, engine.Worker(epoch=repo.get_job(jid)['attempt_epoch']))
    return repo.get_job(jid), calls


@pytest.mark.parametrize('case', ['family','knowledge','crisis','phone','social','campaign'])
def test_original_qa245_replay(case):
    data = archived(case)
    before = deepcopy(data['before'])
    payload = data['responses'][0]['payload'] if case!='campaign' else data['responses'][-1]['payload']
    resolver = StateResolver(before, data['narrative'], data['player_input'], require_player_agency=True)
    if case in ('social','campaign'):
        assert resolver.resolve(payload).history['events']
    else:
        with pytest.raises(StructuralDeltaError) as error:
            resolver.resolve(payload)
        rows = error.value.diagnostics('test')
        codes = {r['code'] for r in rows}
        if case=='family':
            assert {'player_action_completion_invalid','ordinary_temporal_boundary'} <= codes
            assert rows[-1]['temporal_boundary']['max_minutes']==0
        elif case=='knowledge':
            assert {'knowledge_fact_link_missing','controlled_actor_unsupported'} <= codes
            links = [r for r in rows if r['code']=='knowledge_fact_link_missing']
            assert len(links)==4
            assert all(r['related_paths']==['events[0].fact_ids'] for r in links)
        elif case=='crisis':
            assert codes=={'event_presence_invalid'}  # no downstream fake errors
        elif case=='phone':
            assert codes=={'movement_source_invalid'} and len(rows)==2
    assert before==data['before']


@pytest.mark.parametrize('case', ['family','knowledge','phone','crisis','social','campaign'])
def test_one_repair_through_jobs_context_history_reload(tmp_path, case):
    data=archived(case)
    repo=Repository(tmp_path/'game.sqlite'); sid=seed(repo,data)['save']
    before, hist, turns=repo.get_snapshot(sid),history(repo,sid),repo.list_turns(sid)
    good=corrected(data)
    bad=data['responses'][0]['payload']
    replies=[good] if case in ('social','campaign') else [bad,good]
    job,calls=execute(repo,sid,data,replies)
    assert len(calls)==len(replies)+1, job['error']
    assert sum(not c.get('response_format') for c in calls)==1
    for call in calls[1:]:
        assert json.dumps(data['narrative'],ensure_ascii=False) in '\n'.join(m['content'] for m in call['messages'])
    fresh=Repository(repo.path)
    if case=='crisis':
        assert job['status']=='error'
        assert repo.public_job(job)['narrative_reauthor_required']
        assert not repo.public_job(job)['retry_allowed']
        assert fresh.get_snapshot(sid)==before and history(fresh,sid)==hist and fresh.list_turns(sid)==turns
        with pytest.raises(ValueError): repo.retry_job(job['id'],CONFIG)
        return
    assert job['status']=='saved',job['error']
    saved=fresh.get_snapshot(sid)['world_state']
    assert fresh.list_turns(sid)[-1]['assistant_text']==data['narrative']
    if case=='knowledge':
        gains=history(fresh,sid)['knowledge_acquisitions'][len(hist['knowledge_acquisitions']):]
        assert len(gains)==4
        for row in good['knowledge_gained']:
            entry=saved['knowledge'][row['actor_id']+':'+row['fact_id']]
            assert entry['status']=='known' and entry['revision']==1
            assert any(g['actor_id']==entry['actor_id'] and g['fact_id']==entry['fact_id'] for g in gains)
        again=StateResolver(saved,data['narrative'],data['player_input']).resolve(dict(
            final_scene=good['final_scene'],events=[{k:v for k,v in e.items() if k not in ('actor_id','target_ids','player_action_id','player_evidence','player_assertion','minute')} for e in good['events']],knowledge_gained=good['knowledge_gained']))
        assert not again.history['knowledge_acquisitions']
    elif case=='family':
        assert saved['pregnancies']==data['before']['pregnancies']
        assert saved['meta']['world_time']==data['before']['meta']['world_time']
        assert saved['characters'].keys()==data['before']['characters'].keys()
    elif case=='phone':
        assert history(fresh,sid)['movements']==hist['movements']
        assert saved['camera']['present_character_ids']==data['before']['camera']['present_character_ids']
        for actor in ('qa_vera','qa_timur'):
            assert saved['characters'][actor]['location_id']==data['before']['characters'][actor]['location_id']


@pytest.mark.parametrize('case', ['family','knowledge','phone'])
def test_repeat_failure_retry_and_variant_atomicity(tmp_path,case):
    data=archived(case);repo=Repository(tmp_path/'variants.sqlite');sid=seed(repo,data)['save']
    before,hist,turns=repo.get_snapshot(sid),history(repo,sid),repo.list_turns(sid)
    bad=data['responses'][0]['payload'];good=corrected(data)
    failed,calls=execute(repo,sid,data,[bad,bad])
    assert failed['status']=='error' and len(calls)==3
    assert Repository(repo.path).get_snapshot(sid)==before
    assert history(repo,sid)==hist and repo.list_turns(sid)==turns
    saved,calls=execute(repo,sid,data,[good],retry=failed['id'])
    assert saved['status']=='saved',saved['error']
    assert len(calls)==1 and calls[0].get('response_format')
    prior=repo.get_snapshot(sid);turn=repo.list_turns(sid)[-1]
    sibling,calls=execute(repo,sid,data,[good],kind='regenerate')
    assert sibling['status']=='saved',sibling['error']
    assert len(repo.variants(turn['node_id']))==2
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==prior
    repo.rollback_last(sid)
    assert Repository(repo.path).get_snapshot(sid)==before
    assert history(repo,sid)==hist


def test_crisis_scope_does_not_label_referenced_vera_present(tmp_path):
    data=archived('crisis');repo=Repository(tmp_path/'scope.sqlite');sid=seed(repo,data)['save']
    messages=build_context(repo.get_snapshot(sid),[],data['player_input'],'turn',49152,2000)
    blocks={m['content'].split('\n',1)[0]:m['content'].split('\n',1)[1] for m in messages if '\n' in m['content']}
    assert 'qa_vera' not in blocks['Карточки присутствующих / GM-only']
    assert 'qa_vera' in blocks['Упомянутые, присутствие не установлено / GM-only']


def test_repair_budget_40960_and_insufficient_window_no_dispatch(tmp_path):
    data=archived('knowledge');repo=Repository(tmp_path/'budget.sqlite');sid=seed(repo,data)['save']
    bad=data['responses'][0]['payload'];good=corrected(data)
    job,calls=execute(repo,sid,data,[bad,good],config=dict(CONFIG,context_length=40960))
    assert job['status']=='saved',job['error']
    assert len(calls)==3
    assert all(estimate(c['messages'])<=40960-c['max_tokens']-256 for c in calls)
    repo.rollback_last(sid)
    before=repo.get_snapshot(sid)
    failed,calls=execute(repo,sid,data,[bad,bad])
    assert failed['status']=='error'
    failed,calls=execute(repo,sid,data,[good],retry=failed['id'],config=dict(CONFIG,context_length=8192))
    assert failed['status']=='error' and not calls
    assert repo.get_snapshot(sid)==before and failed['narrative']==data['narrative']


def arrival_control(data):
    raw=corrected(data); actor='qa_timur'; target='new-arrival-place'
    raw['locations']=[dict(id=target,name='Новая мастерская',evidence='Тимур прибыл в новую мастерскую.')]
    raw['final_scene']['present_character_ids'].remove(actor)
    raw['events'].append(dict(id='arrival',text='Тимур прибыл в новую мастерскую.',
        medium='action',participants=[actor],location_id=target,order=2))
    raw['movements']=[dict(actor_id=actor,to_location_id=target,
        from_location_id=data['before']['characters'][actor]['location_id'],
        assertion='completed_arrival',source_event_id='arrival',order=2)]
    return raw


@pytest.mark.parametrize('fault', ['none','missing','unknown','actor','endpoint','order','legacy-order','channel','scene'])
def test_arrival_provenance_and_new_location_atomicity(fault):
    data=archived('phone');raw=arrival_control(data)
    event=raw['events'][-1];move=raw['movements'][0]
    if fault=='missing': move.pop('source_event_id')
    if fault=='unknown': move['source_event_id']='historical-event'
    if fault=='actor': event['participants']=[]
    if fault=='endpoint': event['location_id']=data['before']['camera']['location_id']
    if fault=='order': event['order']=3
    if fault=='legacy-order':
        move.pop('assertion')
        event['order']=3
    if fault=='channel': event['medium']='message'
    if fault=='scene': raw['final_scene']['present_character_ids'].append('qa_timur')
    before=deepcopy(data['before'])
    if fault!='none':
        with pytest.raises(StructuralDeltaError) as error:
            StateResolver(before,'Тимур прибыл в мастерскую.',data['player_input']).resolve(raw)
        assert error.value.code in ('movement_source_invalid','scene_movement_conflict','event_presence_invalid')
        assert before==data['before']
        return
    result=StateResolver(before,'Тимур прибыл в мастерскую.',data['player_input']).resolve(raw)
    assert result.state['characters']['qa_timur']['location_id']=='new-arrival-place'
    movement,=result.history['movements']
    assert movement['source_event_id']==next(e['id'] for e in result.history['events'] if e['local_id']=='arrival')


@pytest.mark.parametrize('fault,code', [('actor','knowledge_actor_unknown'),('fact','knowledge_fact_unknown'),
    ('event','knowledge_event_unknown'),('witness','knowledge_witness_missing'),('medium','knowledge_medium_invalid')])
def test_optional_knowledge_failures_do_not_become_fact_link_errors(fault,code):
    data=archived('knowledge');raw=corrected(data)
    raw.pop('scheduled_event_changes')
    raw['knowledge_gained']=raw['knowledge_gained'][:1]
    row=raw['knowledge_gained'][0]; event=raw['events'][0]
    event['fact_ids']=[]
    if fault=='actor': row['actor_id']='unknown'
    if fault=='fact': row['fact_id']='unknown'
    if fault=='event': row['source_event_id']='unknown'
    if fault=='witness': event['witnesses']=[]
    if fault=='medium': event['medium']='action'
    result=StateResolver(data['before'],data['narrative'],data['player_input']).resolve(raw)
    assert result.state['knowledge']==data['before']['knowledge']
    assert not result.history['knowledge_acquisitions']
    assert code in {w['code'] for w in result.warnings}


def test_birth_completion_discharge_is_not_masked_by_independent_action_error(tmp_path):
    from birth_sex_fixture import due_save, payload
    repo,sid=due_save(tmp_path/'birth.sqlite');state=repo.get_snapshot(sid)['world_state']
    narrative,raw=payload(state,sexes=[None])
    text='Спрашиваю Веру о помощи.'
    raw['player_agency']['actions']=[dict(id='ask',player_evidence=text,target_ids=['qa_vera'],
        narrative_target_ids=['qa_vera'],outcome='completed',meaning='preserved')]
    with pytest.raises(StructuralDeltaError) as error:
        StateResolver(state,narrative,text).resolve(raw)
    assert {r['code'] for r in error.value.diagnostics('test')}=={'player_action_completion_invalid'}
    assert repo.get_snapshot(sid)['world_state']==state


def test_multiple_independent_completions_and_boundary_have_original_paths():
    data=archived('family');raw=deepcopy(data['responses'][0]['payload'])
    second=deepcopy(raw['player_agency']['actions'][0])
    second.update(id='second',player_evidence='Спрашиваю Веру о помощи.')
    raw['player_agency']['actions'].append(second)
    with pytest.raises(StructuralDeltaError) as error:
        StateResolver(data['before'],data['narrative'],data['player_input']+' '+second['player_evidence']).resolve(raw)
    rows=error.value.diagnostics('test')
    assert {r['path'] for r in rows if r['code']=='player_action_completion_invalid'} == {
        'player_agency.actions[0].outcome', 'player_agency.actions[1].outcome'}
    assert any(r['code']=='ordinary_temporal_boundary' for r in rows)


def test_new_arrival_event_source_survives_history_reload(tmp_path):
    data=archived('phone')
    data['narrative'] += '\nПозже Тимур прибыл в новую мастерскую.'
    repo=Repository(tmp_path/'arrival.sqlite');sid=seed(repo,data)['save']
    job,calls=execute(repo,sid,data,[arrival_control(data)])
    assert job['status']=='saved',job['error']
    assert len(calls)==2
    fresh=Repository(repo.path)
    persisted=history(fresh,sid)
    arrival=next(e for e in persisted['events'] if e.get('local_id')=='arrival')
    movement=persisted['movements'][-1]
    assert movement['source_event_id']==arrival['id']
    assert movement['to_location_id']==fresh.get_snapshot(sid)['world_state']['characters']['qa_timur']['location_id']


@pytest.mark.parametrize('fault', ['retirement_without_belief', 'supersedes_without_belief', 'revision'])
def test_missing_fact_link_does_not_harden_other_invalid_knowledge(fault):
    data=archived('knowledge');raw=corrected(data)
    raw['knowledge_gained']=raw['knowledge_gained'][:1]
    row=raw['knowledge_gained'][0];event=raw['events'][0]
    event['fact_ids']=[]
    if fault=='retirement_without_belief': row['status']='refuted'
    if fault=='revision': row['expected_revision']=99
    if fault=='supersedes_without_belief':
        other=next(f['id'] for f in raw['facts'] if f['id']!=row['fact_id'])
        row['supersedes']=[other];event['fact_ids']=[other]
    result=StateResolver(data['before'],data['narrative'],data['player_input']).resolve(raw)
    assert not result.history['knowledge_acquisitions']
    assert result.state['knowledge']==data['before']['knowledge']
    assert any(w['code'] in ('knowledge_path_invalid','knowledge_revision_conflict') for w in result.warnings)


@pytest.mark.parametrize('reference', [[], {}])
def test_malformed_action_reference_reaches_bounded_repair(tmp_path, reference):
    data=archived('knowledge');good=corrected(data);bad=deepcopy(good)
    bad['events'][0]['player_action_id']=reference
    # An unrelated invalid optional ID must not break diagnostic bookkeeping.
    bad['events'].append(dict(id=[],text='Invalid optional Event'))
    repo=Repository(tmp_path/'malformed.sqlite');sid=seed(repo,data)['save']
    before_count=len(history(repo,sid)['knowledge_acquisitions'])
    job,calls=execute(repo,sid,data,[bad,good])
    assert job['status']=='saved',job['error']
    assert len(calls)==3
    assert len(history(repo,sid)['knowledge_acquisitions'])==before_count+4
    assert 'events[0].player_action_id' in job['repair_diagnostics_json']


def test_diagnostic_birth_probe_has_no_observable_side_effects(tmp_path):
    from birth_sex_fixture import due_save, payload
    repo, sid = due_save(tmp_path/'probe.sqlite')
    state = repo.get_snapshot(sid)['world_state']
    narrative, raw = payload(state, sexes=[None])
    text = 'Спрашиваю Веру о помощи.'
    raw['player_agency']['actions'] = [dict(id='ask', player_evidence=text,
        target_ids=['qa_vera'], narrative_target_ids=['qa_vera'], outcome='completed', meaning='preserved')]
    resolver = StateResolver(state, narrative, text)
    original = resolver.raise_independent_errors
    def audited(*args):
        def mutable_state():
            return {k:v for k,v in vars(resolver).items() if isinstance(v, (dict, list, set))} | {
                'history': vars(resolver.history)}
        before = deepcopy(mutable_state())
        arguments = deepcopy(args[:-1])
        errors = list(args[-1])
        with pytest.raises(StructuralDeltaError) as caught:
            original(*args)
        assert mutable_state() == before
        assert args[:-1] == arguments
        assert args[-1] == errors
        raise caught.value
    with patch.object(resolver, 'raise_independent_errors', side_effect=audited):
        with pytest.raises(StructuralDeltaError):
            resolver.resolve(raw)
    assert repo.get_snapshot(sid)['world_state'] == state


@pytest.mark.parametrize('birth_source', ['delivery', 'bad-time'])
def test_independent_events_birth_and_knowledge_diagnostics(tmp_path, birth_source):
    from birth_sex_fixture import due_save, payload
    repo, sid = due_save(tmp_path/'independent.sqlite')
    state = repo.get_snapshot(sid)['world_state']
    narrative, raw = payload(state, sexes=[None])
    raw['births'][0]['sex_observations'][0]['event_sex'] = 'male'
    raw['births'].append(dict(raw['births'][0], pregnancy_id='unknown-pregnancy', source_event_id=birth_source))
    raw['events'].extend([
        dict(id='bad-time', text='Invalid time', minute=-1),
        dict(id='bad-place', text='Impossible meeting', medium='conversation',
             participants=['qa_kirill', 'qa_nina']),
        dict(id='information', text='Независимое сообщение.', medium='conversation',
             participants=['qa_vera'], witnesses=['qa_kirill'])])
    raw['facts'] = [dict(id='independent-fact', text='Новое сообщение.', character_ids=['qa_vera'])]
    raw['knowledge_gained'] = [dict(actor_id='qa_kirill', fact_id='independent-fact', source_event_id=e)
                              for e in ('bad-time', 'bad-place', 'information')]
    with pytest.raises(StructuralDeltaError) as caught:
        StateResolver(state, narrative, '').resolve(raw)
    rows = caught.value.diagnostics('test')
    assert {r['code'] for r in rows} == {'event_minute_invalid', 'event_presence_invalid',
        'birth_event_sex_conflict', 'birth_claim_invalid', 'knowledge_fact_link_missing'}
    assert {r['path'] for r in rows if r['section']=='births'} == {
        'births[0].sex_observations', 'births[1]'}
    assert [r['path'] for r in rows if r['code']=='knowledge_fact_link_missing'] == [
        'knowledge_gained[2].source_event_id']
    # Repair all independent causes together through the real job boundary.
    good = deepcopy(raw)
    good['births'] = good['births'][:1]
    good['births'][0]['sex_observations'][0]['event_sex'] = None
    good['events'][1]['minute'] = state['meta']['world_time']
    good['events'][2]['participants'] = ['qa_kirill']
    good['events'][3]['fact_ids'] = ['independent-fact']
    # Only the actual informational source grants this test-authored fact.
    good['knowledge_gained'] = good['knowledge_gained'][2:]
    from birth_sex_fixture import execute as birth_job
    job, calls = birth_job(repo, sid, narrative, [raw, good])
    assert job['status']=='saved', job['error']
    assert len(calls)==3 and sum(not c.get('response_format') for c in calls)==1
    persisted = Repository(repo.path).get_snapshot(sid)['world_state']
    assert persisted['knowledge']['qa_kirill:independent-fact']['status']=='known'
    assert all(p['status']=='born' for p in persisted['pregnancies'].values())


def test_unrelated_rejected_event_does_not_mask_action_completion():
    data = archived('family'); raw = deepcopy(data['responses'][0]['payload'])
    raw['events'].append(dict(id='unrelated', text='Other event', minute=-1, participants=['qa_timur']))
    with pytest.raises(StructuralDeltaError) as caught:
        StateResolver(data['before'], data['narrative'], data['player_input']).resolve(raw)
    assert {d['code'] for d in caught.value.diagnostics('test')} == {
        'event_minute_invalid', 'player_action_completion_invalid', 'ordinary_temporal_boundary'}


def multiple_arrivals(data):
    raw = arrival_control(data)
    raw['final_scene']['present_character_ids'].remove('qa_vera')
    raw['events'][-1]['participants'].append('qa_vera')
    raw['locations'].append(dict(id='second-new-place', name='Новый причал'))
    raw['events'].append(dict(id='second-arrival', text='Оба прибыли на причал.', medium='action',
        participants=['qa_vera', 'qa_timur'], location_id='second-new-place', order=4))
    raw['movements'].append(dict(raw['movements'][0], actor_id='qa_vera'))
    raw['movements'].extend(dict(actor_id=actor, from_location_id='new-arrival-place',
        to_location_id='second-new-place', assertion='completed_arrival', source_event_id='second-arrival', order=4)
        for actor in ('qa_vera', 'qa_timur'))
    # Input order is not the timeline; each actor's explicit route is sorted.
    raw['movements'].reverse()
    return raw


@pytest.mark.parametrize('fault', ['none', 'earlier-source', 'other-actor', 'same-order'])
def test_multiple_arrival_sources_and_participants(fault):
    data = archived('phone'); raw = multiple_arrivals(data)
    if fault=='earlier-source': raw['movements'][0]['source_event_id']='arrival'
    if fault=='other-actor': raw['events'][-1]['participants'].remove('qa_timur')
    if fault=='same-order': raw['movements'][0]['order']=2
    if fault!='none':
        with pytest.raises(StructuralDeltaError):
            StateResolver(data['before'], data['narrative'], data['player_input']).resolve(raw)
        return
    result = StateResolver(data['before'], data['narrative'], data['player_input']).resolve(raw)
    events = {e['id']:e for e in result.history['events']}
    assert len(result.history['movements'])==4
    for movement in result.history['movements']:
        event = events[movement['source_event_id']]
        assert event['location_id']==movement['to_location_id']
        assert event['order']==movement['order']
        assert movement['actor_id'] in event['participants']


def test_multiple_arrival_history_rollback_and_siblings(tmp_path):
    data = archived('phone'); repo=Repository(tmp_path/'routes.sqlite'); sid=seed(repo,data)['save']
    before, old_history = repo.get_snapshot(sid), history(repo, sid)
    raw = multiple_arrivals(data)
    job, _ = execute(repo, sid, data, [raw])
    assert job['status']=='saved', job['error']
    saved = repo.get_snapshot(sid); saved_history = history(repo, sid)
    turn = repo.list_turns(sid)[-1]
    sibling, _ = execute(repo, sid, data, [raw], kind='regenerate')
    assert sibling['status']=='saved', sibling['error']
    repo.select_variant(sid, turn['id'], turn['active_variant_id'], repo.get_save(sid)['revision'])
    fresh=Repository(repo.path)
    assert fresh.get_snapshot(sid)==saved and history(fresh,sid)==saved_history
    repo.rollback_last(sid)
    assert Repository(repo.path).get_snapshot(sid)==before and history(repo,sid)==old_history
