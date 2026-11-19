import json
from copy import deepcopy
import pytest
from backend.runtime_v3 import narrative_frame
from backend.runtime_v3.player_actions import resolver_options
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.time_skip import parse_skip
from test_published_narrative263 import game, CONFIG
from test_life_social import state
from test_long_term_advance import fixture as advance_fixture
pytestmark = pytest.mark.extraction_current


def apply(before, payload, number=1):
    return StateResolver(before, 'Герои встретились.', 'Осматриваюсь.', turn_id=number,
        **resolver_options(before, 'Осматриваюсь.', contract_version=10)).resolve(payload)


def test_physical_ending_and_disclosure_do_not_require_a_route():
    before = state()
    before['locations']['cafe'] = dict(before['locations']['home'], id='cafe', name='Кафе')
    payload = dict(scene=dict(ending=dict(location_id='cafe',present_ids=['a','b']),observed_character_ids=['c']),
                   scene_steps=[dict(kind='information',claims=[dict(fact=dict(id='t',text='Завтра концерт.'),perceived_by=['b'])])])
    result=apply(before,payload)
    assert result.state['camera']['location_id']=='cafe'
    assert [result.state['characters'][c]['location_id'] for c in 'abc']==['cafe','cafe',None]
    assert {m['actor_id'] for m in result.history['movements'] if m.get('derived_from')=='final_scene'}=={'a','b'}
    assert {k['actor_id'] for k in result.state['knowledge'].values()}=={'b'}


def test_stream_chunks_prose_and_partial_menu():
    scene='  Строка\n«Цитата» \\ "🌅"  '
    wire=json.dumps(dict(scene=scene,actions=[dict(text=str(i),facts=[]) for i in range(6)]))
    for i in range(1,len(wire)):
        assert scene.startswith(narrative_frame.read(wire[:i],complete=False)[0])
    actual, frame=narrative_frame.read(wire,complete=True)
    assert actual==scene
    frame['actions'][2]['facts']=['private']
    frame['actions'][3]=frame['actions'][0]
    choices,warnings=narrative_frame.menu(frame,state())
    assert len(choices)==4 and warnings[0]['available']==4


def test_frame_survives_failed_extraction_and_reload(game):
    from backend.repositories.preparation import Repository
    repo,sid=game
    before=repo.get_snapshot(sid)['world_state']
    camera=before['camera'];dest=next(loc for loc in before['locations'] if loc!=camera['location_id'])
    ids=camera['present_character_ids']
    wire=json.dumps(dict(scene='  Сцена.\n',ending=dict(location_id=dest,present_ids=ids,elapsed_minutes=30),
                         actions=[dict(text='Путь '+str(i),facts=[]) for i in range(6)]))
    import engine
    from unittest.mock import patch
    from backend.services.provider_attempt import identity
    calls=[]
    jid=repo.begin_job(sid,'Идём вместе.', 'turn', CONFIG)
    def stream(**kw):
        stage=identity()['stage']; calls.append(stage)
        if stage=='narrative': yield wire
        elif stage=='extraction':
            assert repo.list_turns(sid)[-1]['assistant_text']=='  Сцена.\n'
            yield 'не JSON'
        else: yield '{}'
    with patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,jid,engine.Worker(epoch=0,api_key='offline'))
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    repo=Repository(repo.path)
    t=repo.list_turns(sid)[-1]; world=repo.get_snapshot(sid)['world_state']
    assert t['assistant_text']=='  Сцена.\n' and len(json.loads(t['choices_json']))==6
    assert world['camera']['location_id']==dest and set(world['camera']['present_character_ids'])==set(ids)
    assert world['meta']['world_time']==before['meta']['world_time']+30
    assert 'extraction_repair' not in calls


def test_group_move_and_employment_replacement_are_explicit():
    from test_residence_roles import state as residence_state
    s=residence_state()
    s=apply(s,dict(residence_changes=[dict(actor_ids=['a','b'],location_id='home')],
                   role_changes=[dict(actor_id='a',kind='employment',title='Архивариус',replaces='current')])).state
    assert {r['actor_id'] for r in s['residences'].values() if r['location_id']=='home'} >= {'a','b'}
    s=apply(s,dict(role_changes=[dict(actor_id='a',kind='employment',title='Хранитель',replaces='current')]),2).state
    s=apply(s,dict(role_changes=[dict(actor_id='a',kind='employment',title='Лектор')]),3).state
    assert {(v['title'],v['status']) for v in s['roles'].values()} >= {('Архивариус','closed'),('Хранитель','active'),('Лектор','active')}


def test_experience_consolidates_only_after_three_related_turns():
    s=state()
    for i,theme in enumerate(('listen','other','listen','listen'),1):
        s=apply(s,dict(development_evidence=[dict(actor_id='b',meaning='Выслушал другого.',
            theme=theme,develops=dict(field='habits',text='Даёт собеседнику договорить.'))]),i).state
        p=s['characters']['b']['personality']
        assert bool(p['items'])==(i==4)
    assert len(p['evidence'])==4


@pytest.mark.parametrize('text,minutes',[('Жду 30 минут',30),('Еду три часа',180),('Сплю до следующего утра',1500),
    ('Пропускаю три дня',4320),('Жду до завтра в 14:00',1920)])
def test_short_interval(text,minutes):
    assert parse_skip(text,360,[{'name':''}]).target_minute==360+minutes


@pytest.mark.parametrize('amount,unit',[(1,'months'),(6,'months'),(1,'years'),(5,'years'),(10,'years')])
def test_long_interval_exact_calendar_and_no_invented_phases(amount,unit):
    from backend.runtime_v3.long_term import run
    from backend.runtime_v3.long_term_calendar import target_minute
    before=advance_fixture()
    s=before['world_state']
    after,batch,report=run(deepcopy(before),dict(amount=amount,unit=unit,max_llm_calls=0))
    w=after['world_state']
    assert w['meta']['world_time']==target_minute(s,amount,unit)
    assert all(w[k]==s[k] for k in ('objective_relations','residences','roles'))


def test_complete_actions_survive_truncated_final_metadata():
    text = '{"scene":"За окном дождь.","actions":[{"text":"Открыть окно","facts":[]},{"text":'
    prose, frame = narrative_frame.read(text, complete=True)
    assert prose == 'За окном дождь.'
    assert narrative_frame.menu(frame, state())[0] == [dict(action='Открыть окно',speech='')]
    assert narrative_frame.read('{"actions":[]}', complete=True)[0] == ''


def test_explicit_ending_excludes_distant_observer_even_if_listed_twice():
    before = state()
    before['locations']['cafe'] = dict(before['locations']['home'], id='cafe', name='Кафе')
    result = apply(before,dict(scene=dict(ending=dict(location_id='cafe',present_ids=['a','b','c']),
                                         observed_character_ids=['c'])))
    assert result.state['camera']['present_character_ids']==['a','b']
    assert result.state['camera']['observed_character_ids']==['c']
    assert result.state['characters']['c']['location_id']==before['characters']['c']['location_id']


def test_bad_narrative_endpoint_keeps_independent_extracted_ending():
    from backend.runtime_v3.consequences import resolve_consequences
    before = state()
    before['locations']['cafe'] = dict(before['locations']['home'],id='cafe',name='Кафе')
    def resolve(raw):
        return apply(before,raw)
    raw, result = resolve_consequences(dict(scene=dict(ending=dict(location_id='cafe',present_ids=['a','b']))),
        before,'Герои встретились.',1,[],resolve,authored_scene=dict(ending=dict(location_id='missing',present_ids=['a','b'])))
    assert result.state['camera']['location_id']=='cafe'
    assert any(w.get('action')=='used_extracted_scene' for w in result.warnings)


def test_marriage_supersedes_engagement_and_divorce_keeps_both_phases():
    s = state()
    def relation(kind):
        return dict(social_relation_changes=[dict(kind=kind,source_id='b',target_id='c')])
    s=apply(s,relation('engaged')).state
    result=apply(s,relation('spouse'),2)
    s=result.state
    assert {(r['kind'],r['status'],r['outcome']) for r in s['objective_relations'].values()} >= {
        ('engaged','closed','superseded'),('spouse','active','')}
    s=apply(s,relation('divorce'),3).state
    assert any(r['kind']=='spouse' and r['outcome']=='divorced' for r in s['objective_relations'].values())


def test_observer_reads_own_public_scene_and_other_actor_only_receives_known_facts():
    from backend.services.pov import actor_view, visible
    changes = dict(presentation=dict(observer_scene=True), facts=[dict(text='Звонила Анна',known_by=['b'])])
    scene = dict(kind='background',pov_actor_id='b',audience_json='["a"]',assistant_text='Утро в мастерской.',
                 changes_json=json.dumps(changes))
    assert visible(scene,'b','a') and actor_view(scene,'b','a',observer=True)['assistant_text']==scene['assistant_text']
    for kind in ('turn','background'):
        waking = actor_view(dict(scene,kind=kind),'b','a')['assistant_text']
        assert 'Звонила Анна' in waking and scene['assistant_text'] not in waking
    assert scene['assistant_text'] not in actor_view(scene,'a','a')['assistant_text']
    legacy = dict(scene,pov_actor_id=None,changes_json='{}')
    assert scene['assistant_text'] not in actor_view(legacy,'b','a')['assistant_text']


def test_call_frame_scopes_actions_to_the_current_call_only():
    s = state()
    s['meta']['interaction_focus'] = 'call'
    options = [dict(text=f'Реплика {i}',facts=[]) for i in range(6)]
    frame = dict(actions=[dict(text='Раскрыть секрет',facts=['unknown']), *options])
    choices,warnings = narrative_frame.menu(frame,s)
    assert [c['action'] for c in choices] == [o['text'] for o in options]
    assert all(c['interaction_channel']=='call' for c in choices)
    assert warnings[0]['received']==7 and warnings[0]['available']==6
