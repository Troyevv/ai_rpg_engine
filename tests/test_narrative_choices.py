"""#73 tests the model contract and real Runtime boundaries, not literary quality."""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest
from hypothesis import given, strategies as st

from backend.runtime_v3.context import build_context
from backend.runtime_v3.context_contract import CHOICE_CONTRACT
from backend.runtime_v3.camera import transition, observe
from backend.runtime_v3.migration import migrate_v2
from backend.runtime_v3.models import Fact, Knowledge, Motivation, Relationship
from backend.runtime_v3.raw import RawTurnResult, extraction_schema, prompt_schema
from backend.runtime_v3.resolver import StateResolver
from backend.repositories.preparation import Repository
from devtools.narrative_test_world import load_fixture, CHOICE_EXAMPLES, ACTOR_ID
from test_milestones import snapshot
from test_narrative_test_world import CONFIG

TITLE = 'Choice context / controlled actor'


def section(messages, title=TITLE):
    return json.loads(next(m['content'].split('\n', 1)[1] for m in messages if m['content'].startswith(title+'\n')))


def initial():
    snap = snapshot()
    for card in snap['character_cards']:
        card['fields'] = {'Характер':'OLD_'+card['id'], 'Стиль общения':'VOICE_'+card['id'],
                          'Привычки':'HABIT_'+card['id']}
    snap = migrate_v2(snap).snapshot
    s = snap['world_state']; a = s['characters']['a']
    a['personality']['items']['traits'].update(text='CURRENT_a',revision=3)
    s['camera']['present_character_ids'].append('b'); s['characters']['b']['location_id']='home'
    for key in ('goals','intentions','obligations'):
        a[key] = [Motivation(id=key, text='ACTIVE_'+key).model_dump(),
                  Motivation(id=key+'_done', text='DONE_'+key,status='completed').model_dump(),
                  Motivation(id=key+'_blocked', text='BLOCKED_'+key,status='blocked').model_dump(),
                  Motivation(id=key+'_review', text='REVIEW_'+key,review_required=['role:closed']).model_dump()]
    for src,dst in [('a','b'),('b','a'),('a','c')]:
        s['relationships'][src+':'+dst] = Relationship(source_id=src,target_id=dst,context=src+'_to_'+dst).model_dump()
    return snap


def build(snap, turns=(), **kwargs):
    return build_context(snap,list(turns),kwargs.pop('text','Рассмотреть карту.'),kwargs.pop('kind','turn'),
                         kwargs.pop('context_length',32768),2000,extraction_text='Разговор о карте продолжается.',**kwargs)


def turn(actor='a', text='PLAYER_a', **kwargs):
    return dict(dict(pov_actor_id=actor,kind='turn',user_text=text,assistant_text='Разговор.',
        audience_json='["a","b"]',sequence=0,choices_json=json.dumps([dict(action='UNSELECTED',speech='')])) , **kwargs)


def raw(s, **kwargs):
    return dict(final_scene={k:s['camera'][k] for k in ('location_id','present_character_ids')},**kwargs)


def test_canonical_profile_context_policy_and_no_mutation():
    snap=initial(); before=deepcopy(snap); turns=[turn()]; messages=build(snap,turns)
    ctx=section(messages)
    assert ctx['actor_id']=='a' and ctx['enabled']
    assert ctx['personality']['items']['traits']==dict(field='traits',text='CURRENT_a',revision=3)
    assert ctx['personality']['items']['communication']['text']=='VOICE_a'
    assert ctx['personality']['items']['habits']['text']=='HABIT_a'
    for key in ('goals','intentions','obligations'):
        assert [r['id'] for r in ctx[key]]==[key]
    assert [r['context'] for r in ctx['relationships']]==['a_to_b']
    assert ctx['scene']['location_id']=='home' and ctx['scene']['present_actor_ids']==['a','b']
    assert ctx['recent_player_expression'][0]['player_input']=='PLAYER_a'
    assert 'OLD_a' not in str(ctx) and 'UNSELECTED' not in str(messages)
    assert CHOICE_CONTRACT in messages[0]['content']
    assert messages.selection['choice_context']==dict(enabled=True,actor_id='a',recent_inputs=1,knowledge=0)
    assert snap==before and turns==[turn()]


def test_legacy_fallback_and_retired_profile_never_resurrects_card():
    snap=initial(); actor=snap['world_state']['characters']['a']
    actor['personality']=None
    assert section(build(snap))['personality']['items']['traits']['text']=='OLD_a'
    actor['personality']=dict(items={},evidence={})
    assert section(build(snap))['personality']==dict(items={})
    assert 'OLD_a' not in str(build(snap))


def test_only_owned_beliefs_without_truth_refresh_or_retired_secret_leaks():
    snap=initial(); s=snap['world_state']
    statuses=['known','suspected','unknown','outdated','refuted','superseded']
    for status in statuses:
        fid='map_'+status
        s['facts'][fid]=Fact(id=fid,text='Карта '+status,character_ids=['a','b']).model_dump()
        s['knowledge']['a:'+fid]=Knowledge(actor_id='a',fact_id=fid,status=status).model_dump()
    s['facts']['hidden']=Fact(id='hidden',text='Карта HIDDEN_b',visibility='secret',character_ids=['b']).model_dump()
    s['knowledge']['b:hidden']=Knowledge(actor_id='b',fact_id='hidden').model_dump()
    # The old assertion is still believed even though the world now differs.
    for fid,place in [('old','OldWorkshop'),('truth','SecretAcademy')]:
        s['facts'][fid]=Fact(id=fid,text='Карта: работа '+place,character_ids=['b'],
            claim=dict(subject_id='b',predicate='employment',value=place)).model_dump()
    s['knowledge']['a:old']=Knowledge(actor_id='a',fact_id='old').model_dump()
    messages=build(snap,text='Карта'); ctx=section(messages)
    assert {r['fact_id'] for r in ctx['knowledge']}=={'map_known','map_suspected','old'}
    assert next(r for r in ctx['knowledge'] if r['fact_id']=='map_suspected')['status']=='suspected'
    assert 'OldWorkshop' in str(ctx) and 'SecretAcademy' not in str(ctx) and 'HIDDEN_b' not in str(ctx)
    # Extraction truth remains available for state resolution, never for choices.
    assert 'SecretAcademy' in str(section(messages,'Текущее состояние / GM-only'))
    switched=section(build(transition(snap,'b'),text='Карта'))
    assert [r['text'] for r in switched['knowledge']]==['Карта HIDDEN_b']


def test_control_switch_and_bounded_history_do_not_learn_other_actors_or_observers():
    snap=initial()
    turns=[turn(sequence=i,text=f'A_{i}') for i in range(10)]
    turns += [turn('b','PLAYER_b'),turn(None,'OBSERVER',kind='background'),turn('a','START',kind='start')]
    ctx=section(build(snap,turns))
    assert [r['player_input'] for r in ctx['recent_player_expression']]==['A_7','A_8','A_9']
    other=section(build(transition(snap,'b'),turns))
    assert other['actor_id']=='b' and other['personality']['items']['communication']['text']=='VOICE_b'
    assert [r['player_input'] for r in other['recent_player_expression']]==['PLAYER_b']
    legacy=section(build(snap,[turn(None,'LEGACY')]))
    assert legacy['recent_player_expression'][0]['player_input']=='LEGACY'
    assert section(build(snap,turns,recent_turns=0))['recent_player_expression']==[]
    huge=section(build(snap,[turn(text='x'*20000)]))['recent_player_expression'][0]
    assert huge['truncated'] and len(huge['player_input'])==800


@pytest.mark.parametrize('mode',['observer','background','blocked'])
def test_no_choices_even_if_model_returns_them(mode):
    snap=initial(); resolver_mode='turn'
    if mode=='observer': snap=observe(snap,'b',allow_protagonist=True)
    if mode=='background': resolver_mode='background'
    if mode=='blocked': snap['world_state']['characters']['a']['capabilities']['can_act']=False
    assert not section(build(snap,kind='background' if mode=='background' else 'turn'))['enabled']
    s=snap['world_state']
    result=StateResolver(s,'Тишина.','',mode=resolver_mode).resolve(raw(s,choices=CHOICE_EXAMPLES))
    assert result.choices==[]


@given(st.lists(st.fixed_dictionaries({'action':st.text(max_size=100),'speech':st.text(max_size=100)}),max_size=8))
def test_arbitrary_suggestions_never_change_state_patch_or_history(choices):
    s=initial()['world_state']; before=deepcopy(s)
    baseline=StateResolver(s,'Тишина.','Наблюдаю.').resolve(raw(s))
    offered=StateResolver(s,'Тишина.','Наблюдаю.').resolve(raw(s,choices=choices))
    assert offered.state==baseline.state and offered.patch==baseline.patch and offered.history==baseline.history
    assert offered.choices==choices[:6] and s==before


def test_proposal_is_not_evidence_and_atypical_manual_input_is_allowed():
    s=initial()['world_state']; proposal='Чувствую радость. Хочу уехать.'
    payload=raw(s,choices=[dict(action=proposal,speech='')],
        character_changes=[dict(id='a',emotion='Радость',emotion_assertion='explicit_internal_state',
            player_evidence=dict(emotion='Чувствую радость.'),goals=['Уехать'],evidence=proposal)],
        facts=[dict(id='unselected',text='Уехал.',evidence=proposal)],
        events=[dict(id='unselected',text='Уехал.',participants=['a'],witnesses=['a'],fact_ids=[],evidence=proposal)])
    r=StateResolver(s,'Тишина.','Наблюдаю.').resolve(payload)
    assert r.state['characters']==s['characters'] and r.state['facts']==s['facts']
    assert not r.history['events']
    assert r.warnings
    # The same expression supplied by the player is allowed without trait checks.
    payload['character_changes'][0].pop('goals')
    accepted=StateResolver(s,'Тишина.',proposal).resolve(payload)
    assert accepted.state['characters']['a']['emotion']=='Радость'


def test_schema_compatibility_and_context_pressure_no_hidden_copy():
    schema=extraction_schema()['properties']['choices']
    assert set(schema['items']['properties'])=={'action','speech'}
    assert prompt_schema()['properties']['choices']['items']['required']==['action','speech']
    s=initial(); state=s['world_state']
    for i in range(40):
        fid=f'support{i}'
        state['facts'][fid]=Fact(id=fid,text='Support '+str(i),character_ids=['a','b']).model_dump()
        state['knowledge']['a:'+fid]=Knowledge(actor_id='a',fact_id=fid).model_dump()
    full=build(s,target_context_budget=28000); pressured=build(s,target_context_budget=1000)
    assert len(section(full)['knowledge'])>len(section(pressured)['knowledge'])
    assert {k['fact_id'] for k in section(pressured)['knowledge']} <= set(section(pressured,'Текущее состояние / GM-only')['facts'])
    assert section(pressured)['personality']==section(full)['personality']
    assert RawTurnResult.parse(raw(state,choices=[dict(action='Legacy without speech')])).choices==[dict(action='Legacy without speech')]


def play(repo,sid,text='Рассмотреть карту.',kind='turn'):
    import engine
    calls=[]
    def stream(**kwargs):
        calls.append(kwargs)
        if not kwargs.get('response_format'):
            yield 'Разговор о карте продолжается.'; return
        current=section(kwargs['messages'],'Текущее состояние / GM-only')
        yield json.dumps(raw(current,choices=CHOICE_EXAMPLES),ensure_ascii=False)
    jid=repo.begin_job(sid,text,kind,CONFIG)
    with patch('engine.find_loaded_model',return_value={'config':{'context_length':32768}}),patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,jid,engine.Worker())
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    assert len(calls)==2
    return calls


def test_qa_fixture_real_evolution_reload_regenerate_rollback_and_control(tmp_path):
    repo=Repository(tmp_path/'choices.sqlite3'); selected=load_fixture(repo,'choices'); sid=selected['save']
    before=repo.get_snapshot(sid); actor=before['world_state']['characters'][ACTOR_ID]
    voice=actor['personality']['items']['communication']
    assert voice['revision']==1 and len(actor['personality']['evidence'])==3
    card=next(c for c in before['character_cards'] if c['id']==ACTOR_ID)
    assert card['fields']['Стиль общения']!=voice['text']
    first=play(repo,sid,'Вопреки привычке, предлагаю рискнуть.')
    ctx=section(first[1]['messages'])
    assert ctx['personality']['items']['communication']['text']==voice['text']
    assert ctx['goals'] and ctx['intentions'] and ctx['obligations'] and ctx['relationships']
    assert all(k['fact_id']!='qa_private_letter' for k in ctx['knowledge'])
    after=repo.get_snapshot(sid)
    assert after['world_state']['characters']==before['world_state']['characters']
    saved_turn=repo.list_turns(sid)[-1]
    assert json.loads(saved_turn['choices_json'])==CHOICE_EXAMPLES
    repo=Repository(repo.path)
    assert repo.get_snapshot(sid)==after
    next_calls=play(repo,sid,'Теперь выбираю другой путь.')
    assert section(next_calls[1]['messages'])['recent_player_expression'][-1]['player_input']=='Вопреки привычке, предлагаю рискнуть.'
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==after
    # A later control switch must not change the recorded source of regeneration.
    repo.switch_actor(sid,'qa_vera',repo.get_save(sid)['revision'])
    regen=play(repo,sid,'','regenerate')
    assert section(regen[1]['messages'])==ctx
    repo.select_variant(sid,saved_turn['id'],saved_turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==after
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==before
    repo.switch_actor(sid,'qa_vera',repo.get_save(sid)['revision'])
    switched=play(repo,sid,'Предлагаю устроить выставку.')
    other=section(switched[1]['messages'])
    assert other['actor_id']=='qa_vera' and other['recent_player_expression']==[]
    assert other['personality']['items']['communication']['text']!=voice['text']


def test_start_turn_save_reload_next_turn(tmp_path):
    repo=Repository(tmp_path/'smoke.sqlite3'); sid=load_fixture(repo,'base')['save']
    play(repo,sid,'','start'); play(repo,sid,'Рассмотреть снимки.')
    before=repo.get_snapshot(sid); repo=Repository(repo.path)
    assert repo.get_snapshot(sid)==before
    calls=play(repo,sid,'Сравнить снимки.')
    assert section(calls[1]['messages'])['actor_id']==ACTOR_ID
    assert len(repo.list_turns(sid))==3
