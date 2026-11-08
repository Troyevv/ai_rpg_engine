"""Unmodified recorded replies plus explicitly labelled corrected provider controls.

No live provider, prose classifier or alteration of the archived Narrative.
"""
from copy import deepcopy
import gzip
import json
from pathlib import Path

import pytest
from backend.repositories.preparation import Repository
from backend.runtime_v3.context import build_context
from backend.runtime_v3.long_term import advance_clock, run
from backend.runtime_v3.models import WorldHistoryV3
from backend.runtime_v3.player_actions import resolver_options
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from test_integrated_repair247 import execute, history
from test_life248_playability import repository_case

ROOT = Path(__file__).parent / 'fixtures/issue250'
DATA = json.loads(gzip.decompress((ROOT/'berezovsk.json.gz').read_bytes()))
LTA = json.loads(gzip.decompress((ROOT/'lta.json.gz').read_bytes()))
CONFIG = dict(model='test', context_length=131072, max_tokens=2400, update_tokens=8192)


def resolve(data, raw, version=4):
    return StateResolver(data['before'], data['narrative'], data['player_input'],
        **resolver_options(data['before'], data['player_input'], contract_version=version)).resolve(raw)


def latest_case(tmp_path, case):
    repo, sid, _ = repository_case(tmp_path, '005')
    data = deepcopy(DATA[case])
    snapshot = repo.get_snapshot(sid)
    snapshot['world_state'] = deepcopy(data['before'])
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?', (json.dumps(snapshot), sid))
    return repo, sid, data


def grounded_control(data):
    """Human-reviewed provider control; the original stored response is unchanged."""
    raw = json.loads(data['responses']['D'][0])
    for i, choice in enumerate(raw['choices']):
        choice['grounding'] = (dict(fact_ids=['fact_viktor_letter'], scene_evidence=[]) if i == 3
            else dict(fact_ids=[], scene_evidence=[data['narrative']]))
    return raw


def test_original_d002_and_new_context_do_not_offer_offscene_secret(tmp_path):
    repo, sid, data = latest_case(tmp_path, '002')
    raw = json.loads(data['responses']['D'][0])
    # Historical protocol reproduces the exact defect; no keyword detector.
    old = resolve(data, raw, 3)
    assert dict(raw['choices'][3], interaction_channel='physical') in old.choices
    assert 'char_alexey:fact_viktor_letter' not in old.state['knowledge']
    for extraction in (None, data['narrative']):
        messages = build_context(repo.get_snapshot(sid), [], data['player_input'], 'turn',
            131072, 8192, extraction_text=extraction)
        current = next(json.loads(m['content'].split('\n', 1)[1]) for m in messages
            if m['content'].startswith('Текущее состояние / GM-only\n'))
        assert 'fact_viktor_letter' not in current['facts']
        assert all(t['id'] != 'thread_viktor_letter' for t in current['threads'])
        # Check all transmitted blocks, including cards/history/policies.
        for secret in (data['before']['facts']['fact_viktor_letter']['text'], data['before']['threads']['thread_viktor_letter']['description'],
                       'thread_viktor_letter', 'Разобраться с письмом бывшей ученицы'):
            assert secret not in '\n'.join(m['content'] for m in messages)
    # Old free-text suggestions have no v4 authority. They cannot mint Knowledge.
    new = resolve(data, raw)
    assert not new.choices and new.state['knowledge'] == old.state['knowledge']


@pytest.mark.parametrize('speech', [None, 'Что дед получил от своей бывшей ученицы?', 'Спросить, ответил ли Виктор на её послание.'])
def test_d002_individual_choice_sources_reload_rollback_and_free_input(tmp_path, speech):
    repo, sid, data = latest_case(tmp_path, '002')
    before = repo.get_snapshot(sid); old_history = history(repo, sid)
    raw = grounded_control(data)
    if speech is not None: raw['choices'][3]['speech'] = speech
    expected = [dict(action=c['action'], speech=c['speech'], interaction_channel='physical') for i,c in enumerate(raw['choices']) if i != 3]
    job, calls = execute(repo, sid, data, [raw], legacy=False, config=CONFIG)
    assert job['status'] == 'saved', job['error']
    assert len(calls) == 2  # No verification model/call.
    fresh = Repository(repo.path)
    assert json.loads(fresh.list_turns(sid)[-1]['choices_json']) == expected
    assert fresh.get_snapshot(sid)['world_state']['knowledge'] == before['world_state']['knowledge']
    warnings = json.loads(job['warnings_json'])
    assert sum(w['code'] == 'choice_knowledge_unproven' for w in warnings) == 1
    # A suggestion grants no knowledge; a manually typed question remains legal.
    after = fresh.get_snapshot(sid)
    camera = after['world_state']['camera']
    manual = dict(data, player_input='Хочу спросить о письме, если такое есть.', narrative='Мать пожимает плечами.')
    next_raw = dict(final_scene=dict(location_id=camera['location_id'], present_character_ids=camera['present_character_ids'], elapsed_minutes=1))
    follow, _ = execute(fresh, sid, manual, [next_raw], legacy=False, config=CONFIG)
    assert follow['status'] == 'saved', follow['error']
    fresh.rollback_last(sid); assert fresh.get_snapshot(sid) == after
    fresh.rollback_last(sid); assert fresh.get_snapshot(sid) == before
    assert history(fresh, sid) == old_history


def test_choice_source_does_not_grant_knowledge_and_known_source_is_usable():
    data = deepcopy(DATA['002']); raw = grounded_control(data)
    for grounding in (dict(fact_ids=['missing'], scene_evidence=[]),
                      dict(fact_ids=[], scene_evidence=['Never uttered']), None):
        raw['choices'][3]['grounding'] = grounding
        result = resolve(data, raw)
        assert len(result.choices) == 5
        assert result.state['knowledge'] == data['before']['knowledge']
    raw = grounded_control(data)
    known = deepcopy(data['before']['knowledge']['char_viktor:fact_viktor_letter'])
    known['actor_id'] = 'char_alexey'
    data['before']['knowledge']['char_alexey:fact_viktor_letter'] = known
    assert len(resolve(data, raw).choices) == 6


def test_optional_continuity_basis_cannot_bypass_choice_knowledge():
    data=deepcopy(DATA['002']);raw=grounded_control(data)
    choice=raw['choices'][3]
    choice.update(grounding=dict(fact_ids=[],scene_evidence=[data['narrative']]),
                  basis_ids=['thread_viktor_letter'],kind='question')
    result=resolve(data,raw)
    assert len(result.choices)==5 and result.state['knowledge']==data['before']['knowledge']


def lta_second_group():
    snapshot = deepcopy(LTA['snapshot']); narrative, extraction = LTA['requests'][2:4]
    current = extraction['current']
    snapshot['world_state']['meta']['turn_id'] = current['meta']['turn_id']
    advance_clock(snapshot, current['meta']['world_time'], WorldHistoryV3().to_dict())
    snapshot['world_state']['camera'] = current['camera']
    return snapshot, narrative['response_text'], json.loads(extraction['response_text'])


@pytest.mark.parametrize('mode', ['background', 'turn'])
@pytest.mark.parametrize('observed', [True, False])
def test_pasha_original_scene_preserves_geography_without_movement(mode, observed):
    snapshot, narrative, raw = lta_second_group()
    state = snapshot['world_state']; before = deepcopy(state)
    if not observed: raw['final_scene']['observed_character_ids'] = []
    result = StateResolver(state, narrative, '', mode=mode, observed=False,
        preserve_scene_locations=True).resolve(raw)
    assert state == before
    assert result.state['characters']['char_pasha']['location_id'] == 'loc_home_kovalev'
    assert result.history['movements'] == []
    assert result.state['knowledge'] == before['knowledge']
    assert 'char_pasha' not in result.history['events'][0]['participants']
    assert 'char_pasha' not in result.history['events'][0]['witnesses']


@pytest.mark.parametrize('damage', [None,'source','origin','remote','order'])
def test_explicit_departure_preserves_movement_source_validation(damage):
    snapshot,narrative,raw=lta_second_group();state=snapshot['world_state']
    quote='Паша вышел из дома.';narrative+=' '+quote
    raw['final_scene']['observed_character_ids']=[]
    raw['events'].append(dict(id='pasha_exit',text=quote,participants=['char_pasha'],witnesses=[],
        medium='action',location_id='loc_home_kovalev',order=2))
    movement=dict(actor_id='char_pasha',from_location_id='loc_home_kovalev',to_location_id=None,
        assertion='departure',source_event_id='pasha_exit',order=2,evidence=quote)
    raw['movements']=[movement]
    if damage=='source':movement['source_event_id']='missing'
    elif damage=='origin':movement['from_location_id']='loc_home_viktor'
    elif damage=='remote':raw['events'][-1]['medium']='message'
    elif damage=='order':movement['order']=3
    resolver=StateResolver(state,narrative,'',mode='background',observed=False)
    if damage:
        with pytest.raises(StructuralDeltaError):resolver.resolve(raw)
        assert state['characters']['char_pasha']['location_id']=='loc_home_kovalev'
    else:
        result=resolver.resolve(raw)
        assert result.state['characters']['char_pasha']['location_id'] is None
        assert result.history['movements'][0]['source_event_id']==result.history['events'][-1]['id']


def test_absence_of_previously_present_actor_is_not_a_departure():
    snapshot,narrative,raw=lta_second_group();state=snapshot['world_state']
    state['camera']['present_character_ids'].append('char_pasha')
    raw['final_scene']['observed_character_ids']=[]
    result=StateResolver(state,narrative,'',preserve_scene_locations=True).resolve(raw)
    assert result.state['characters']['char_pasha']['location_id']=='loc_home_kovalev'
    assert not result.history['movements']


def test_original_lta_groups_commit_reload_rollback(tmp_path):
    repo, sid, _ = latest_case(tmp_path, '005')
    snapshot = deepcopy(LTA['snapshot'])
    snapshot['history_head'] = repo.get_snapshot(sid)['history_head']
    with repo.connect() as db: db.execute('UPDATE saves SET state_json=? WHERE id=?', (json.dumps(snapshot),sid))
    before = repo.get_snapshot(sid); old_history = history(repo,sid)
    request = dict(amount=3, unit='months', max_llm_calls=4)
    groups = [json.loads(r['response_text'])['events'][0]['advance_candidate_ids']
              for r in LTA['requests'] if r['stage'].endswith('extraction')]
    answers = iter(LTA['requests']); calls=[]
    def generate(stage, messages, *args, **kwargs):
        response=next(answers); calls.append(stage)
        assert stage==response['stage']
        return iter([response['response_text']])
    after,batch,report = run(before, request, generate=generate, config=CONFIG, recorded_groups=groups)
    assert len(report['accepted'])==2, report['diagnostics']
    assert len(calls)==4 and not report['diagnostics']
    assert after['world_state']['characters']['char_pasha']['location_id']=='loc_home_kovalev'
    jid=repo.begin_job(sid,'','long_term',dict(CONFIG,long_term_advance=request))
    repo.job_progress(jid,'validating',narrative='Recorded LTA replay.',complete=True)
    repo.commit_job(jid,after,[],{'long_term_advance':report},history_batch=batch)
    fresh=Repository(repo.path)
    assert fresh.get_snapshot(sid)['world_state']==after['world_state']
    assert fresh.get_snapshot(sid)['world_state']['knowledge']==before['world_state']['knowledge']
    new_events=history(fresh,sid)['events'][len(old_history['events']):]
    assert len(new_events)==2
    assert 'char_pasha' not in new_events[-1]['participants']
    fresh.rollback_last(sid)
    assert fresh.get_snapshot(sid)==before and history(fresh,sid)==old_history


def compound_control(data):
    """Split consent boundaries, retain every original Event and the exact prose."""
    raw=json.loads(data['responses']['D'][0]); events=raw['events']; actions=[]
    for i,event in enumerate(events[:3]):
        aid='compound_'+str(i)
        targets=['char_galina'] if i<2 else ['char_viktor']
        actions.append(dict(id=aid, player_evidence=event['player_evidence'], target_ids=targets,
            narrative_target_ids=targets, outcome='completed', meaning='preserved',
            target_mode='interaction' if i<2 else 'reference'))
        event['player_action_id']=aid
        if i==2: event['player_assertion']='explicit_choice'
    raw['player_agency']['actions']=actions
    raw['player_agency']['narrative_audit']=[] # Optional audit grants no authority.
    return raw


@pytest.mark.parametrize('retry_good',[True,False])
def test_original_d005_failure_retry_full_schema_and_atomicity(tmp_path,retry_good):
    repo,sid,data=latest_case(tmp_path,'005');before=repo.get_snapshot(sid);old_history=history(repo,sid)
    replies=[json.loads(x) for x in data['responses']['D']]
    job,calls=execute(repo,sid,data,replies,legacy=False,config=CONFIG)
    assert job['status']=='error' and len(calls)==3
    assert repo.get_snapshot(sid)==before and history(repo,sid)==old_history
    assert job['narrative']==data['narrative']
    answer=compound_control(data) if retry_good else replies[-1]
    retry,requests=execute(repo,sid,data,[answer,answer],retry=job['id'],legacy=False,config=CONFIG)
    assert all(c.get('response_format') for c in requests) # Same Narrative, no regeneration.
    feedback=requests[0]['messages'][0]['content']
    assert 'omitted_sections_from_previous_proposal' in feedback and 'final_scene' in feedback
    schema=next(json.loads(m['content'].split('\n',1)[1]) for m in requests[0]['messages'] if m['content'].startswith('JSON Schema\n'))
    assert {'final_scene','events','movements'}<=set(schema['required'])
    fresh=Repository(repo.path)
    if not retry_good:
        assert retry['status']=='error' and len(requests)==2
        assert fresh.get_snapshot(sid)==before and history(fresh,sid)==old_history
        fresh.abandon_job(sid,job['id'],fresh.get_save(sid)['revision'],retry['attempt_epoch'])
        assert fresh.get_snapshot(sid)==before
        return
    assert retry['status']=='saved', retry['error']
    assert len(requests)==1 and retry['narrative']==data['narrative']
    after=fresh.get_snapshot(sid)
    assert after['world_state']['characters']['char_alexey']['location_id']=='loc_home_viktor'
    saved=history(fresh,sid)['events'][len(old_history['events']):]
    assert len(saved)==4 and {e['local_id'] for e in saved}=={e['id'] for e in answer['events']}
    assert after['world_state']['knowledge']==before['world_state']['knowledge']
    fresh.rollback_last(sid)
    assert fresh.get_snapshot(sid)==before and history(fresh,sid)==old_history
