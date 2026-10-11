"""#75 semantic fixtures come from Extraction; no Python NLP truth oracle."""
from copy import deepcopy
import json
import pytest
from hypothesis import given, strategies as st
from backend.runtime_v3.models import Motivation, Character, Organization, NarrativeRole
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.lifecycle import active_texts, context_records
from backend.runtime_v3.values import initialize_values, project_values
from backend.runtime_v3.context import build_context
from backend.runtime_v3.migration import migrate_v2
from backend.runtime_v3.repository import committed_snapshot, read_history
from test_milestones import snapshot, db
from test_personality import setup, pattern, refs, payload, TEXT

MEET='Илья встретился с Соней. Они поговорили и разошлись.'
OFFER='Соня предложила поездку в коттедж. Илья согласился.'
ILYA='intentions_4d05e847cba4c0a38a98'
SONYA='intentions_ef4ffaa2b77eac28626d'


def initial():
    snap=migrate_v2(snapshot()).snapshot;s=snap['world_state']
    for cid,rid,text in (('a',ILYA,'После «Критического успеха» встретиться с Соней'),('b',SONYA,'Предложить Илье поездку в коттедж')):
        s['characters'][cid]['intentions']=[Motivation(id=rid,text=text,source_sequence=50).model_dump()]
        s['characters'][cid]['goals']=[Motivation(id='long_'+cid,text='Развивать отношения' if cid=='a' else 'Провести выходные').model_dump()]
    snap['character_cards'][0]['fields']['Намерения']=s['characters']['a']['intentions'][0]['text']
    return snap


def raw(s, **sections):
    return dict(final_scene={k:deepcopy(s['camera'][k]) for k in ('location_id','present_character_ids')},**sections)


def completion(s, cid='a', rid=ILYA, text=MEET, **changes):
    return raw(s,events=[dict(id='done',text=text,evidence=text,participants=[cid],witnesses=[cid],fact_ids=[])],
        character_changes=[dict(id=cid,intentions_updates=[dict(id=rid,status='completed',expected_revision=0,
            source_event_id='done',evidence=text,**changes)])])


def test_live_ilya_sonya_completed_not_long_term_goals_and_not_next_choices():
    snap=initial();s=snap['world_state'];goals=deepcopy({c:s['characters'][c]['goals'] for c in 'ab'})
    first=StateResolver(s,MEET,'Иду навстречу Соне.').resolve(completion(s))
    p=completion(first.state,'b',SONYA,OFFER)
    p['facts']=[dict(id='fact_cottage_agreed',text='Илья согласился на поездку.',evidence=OFFER,character_ids=['a','b'])]
    p['events'][0]['fact_ids']=['fact_cottage_agreed']
    second=StateResolver(first.state,OFFER,'Соглашаюсь.').resolve(p)
    assert not first.warnings and not second.warnings
    for cid,r in (('a',first),('b',second)):
        entry=r.state['characters'][cid]['intentions'][0]
        assert entry['status']=='completed' and entry['revision']==1 and entry['source_event_id']
        assert r.state['characters'][cid]['goals']==goals[cid]
        history=next(c for c in r.history['state_changes'] if c.get('kind')=='motivation_transition')
        assert history['before']['status']=='active' and history['after']['id']==entry['id']
    s=second.state
    for _ in range(5):
        s=StateResolver(s,'Разговор о книгах.','Слушаю.').resolve(raw(s)).state
        snap['world_state']=s
        context=build_context(snap,[],'Продолжить','turn',32768,2000)
        assert ILYA not in str(context) and SONYA not in str(context)
        assert 'После «Критического успеха» встретиться с Соней' not in str(context)
        assert 'Развивать отношения' in str(context)
    assert 'fact_cottage_agreed' in s['facts']


def test_extraction_supplies_existing_ids_status_revision_not_terminal_entries():
    snap=initial();s=snap['world_state']
    msgs=build_context(snap,[],'Иду к Соне.','turn',32768,2000,extraction_text=MEET)
    current=json.loads(next(m['content'].split('\n',1)[1] for m in msgs if m['content'].startswith('Текущее состояние')))
    row=current['characters']['a']['intentions'][0]
    assert row['id']==ILYA and row['status']=='active' and row['revision']==0
    assert 'Live regression' in str(msgs)


@pytest.mark.parametrize('bad', ['future','missing_event','stale_revision','unknown_id'])
def test_completion_requires_narrated_result_and_stable_identity(bad):
    s=initial()['world_state'];p=completion(s);narrative=MEET;player=''
    change=p['character_changes'][0]['intentions_updates'][0]
    if bad=='future': narrative='Илья ещё дома.';player=MEET
    if bad=='missing_event': change['source_event_id']='invented'
    if bad=='stale_revision': change['expected_revision']=8
    if bad=='unknown_id': change['id']='other'
    r=StateResolver(s,narrative,player).resolve(p)
    assert r.state['characters']['a']['intentions']==s['characters']['a']['intentions'] and r.warnings


def test_replay_terminal_and_conflicting_updates_do_not_duplicate_history():
    s=initial()['world_state'];p=completion(s)
    r=StateResolver(s,MEET,'').resolve(p);again=StateResolver(r.state,MEET,'').resolve(p)
    assert again.state['characters']['a']['intentions']==r.state['characters']['a']['intentions']
    assert not any(c.get('kind')=='motivation_transition' for c in again.history['state_changes'])
    p['character_changes'][0]['intentions_updates'][0]['status']='active'
    assert StateResolver(r.state,MEET,'').resolve(p).state['characters']['a']['intentions'][0]['status']=='completed'


@pytest.mark.parametrize('status',['cancelled','superseded'])
def test_external_abandonment_requires_explicit_choice(status):
    s=initial()['world_state'];quote='Я отказываюсь от встречи.'
    p=raw(s,character_changes=[dict(id='a',intentions_updates=[dict(id=ILYA,status=status,evidence=quote)])])
    assert StateResolver(s,quote,'Смотрю в окно.').resolve(p).state['characters']['a']['intentions'][0]['status']=='active'
    p['character_changes'][0]['intentions_updates'][0].update(player_evidence=quote,player_assertion='explicit_choice')
    r=StateResolver(s,quote,quote).resolve(p)
    assert r.state['characters']['a']['intentions'][0]['status']==status
    background=StateResolver(s,quote,quote,mode='background',protected_actor_id='a').resolve(p)
    assert background.state['characters']['a']['intentions'][0]['status']=='active'


def test_legacy_partial_lists_preserve_omitted_and_closed_records():
    s=initial()['world_state'];s['characters']['b']['goals'].append(Motivation(id='old',text='Законченная цель',status='completed').model_dump())
    r=StateResolver(s,OFFER,'').resolve(raw(s,character_changes=[dict(id='b',goals=['Новая цель'],evidence=OFFER)]))
    assert [e['status'] for e in r.state['characters']['b']['goals']]==['active','completed','active']


@given(st.integers(min_value=1,max_value=10000000))
def test_time_and_due_date_never_complete(minutes):
    s=initial()['world_state'];s['characters']['a']['intentions'][0]['due_minute']=0
    s['meta']['world_time']+=minutes
    r=StateResolver(s,'Прошло время.','').resolve(raw(s))
    assert r.state['characters']['a']['intentions']==s['characters']['a']['intentions']


@pytest.mark.parametrize('section',['characters','roles','organizations'])
def test_cross_domain_review_is_bounded_idempotent_and_non_actionable(section):
    s=initial()['world_state']
    if section=='characters': rid='b';s['characters']['b']['life_status']='dead'
    elif section=='organizations': rid='org';s[section][rid]=Organization(id=rid,name='Колледж',status='closed').model_dump()
    else: rid='role';s[section][rid]=NarrativeRole(id=rid,actor_id='a',kind='student',title='Студент',status='closed').model_dump()
    entry=s['characters']['a']['intentions'][0];entry['dependencies']={section:[rid]}
    s['camera']['present_character_ids']=['a']
    r=StateResolver(s,'Тихий вечер.','').resolve(raw(s));entry=r.state['characters']['a']['intentions'][0]
    assert entry['status']=='active' and entry['review_required'] and not active_texts([entry])
    assert not context_records([entry]) and context_records([entry],evaluation=True)[0]['id']==ILYA
    r2=StateResolver(r.state,'Тихий вечер.','').resolve(raw(r.state))
    assert r2.state['characters']['a']['intentions']==r.state['characters']['a']['intentions']
    text='Встреча невозможна.'
    p=raw(r.state,character_changes=[dict(id='a',intentions_updates=[dict(id=ILYA,status='blocked',evidence=text,expected_revision=1)])])
    blocked=StateResolver(r.state,text,'').resolve(p)
    assert blocked.state['characters']['a']['intentions'][0]['status']=='blocked'
    assert not blocked.state['characters']['a']['intentions'][0]['review_required']
    assert blocked.state['characters']['a']['goals']==s['characters']['a']['goals']


def value_delta(actor='b', **kw):
    return dict(actor_id=actor,item_id='honesty',operation='establish',text='Ценит честность.',
        expected_revision=0,expected_text=None,basis='sustained_behavior',evidence_ids=[],evidence=TEXT,
        rationale='Повторяющийся добровольный выбор.',**kw)


def test_values_use_existing_evidence_but_not_personality_items():
    snap=setup();s=pattern(snap['world_state']);before=deepcopy(s['characters']['b'])
    d=value_delta();d['evidence_ids']=refs(s)
    p=raw(s,value_deltas=[d]);r=StateResolver(s,TEXT,'').resolve(p)
    assert not r.warnings and r.state['characters']['b']['values']['honesty']['revision']==1
    assert r.state['characters']['b']['personality']==before['personality']
    assert r.state['characters']['b']['goals']==before['goals']
    d.update(operation='refine',expected_text='Ценит честность.',expected_revision=1,text='Ценит бережную честность.')
    assert StateResolver(r.state,TEXT,'').resolve(p).state['characters']['b']['values']==r.state['characters']['b']['values']


def test_external_values_reject_npc_era_and_single_episode_accept_repeated_owned():
    s=pattern(setup()['world_state'],'b');d=value_delta();d['evidence_ids']=refs(s)
    r=StateResolver(s,TEXT,TEXT,protected_actor_id='b').resolve(raw(s,value_deltas=[d]))
    assert not r.state['characters']['b']['values']
    for _ in range(3):
        r=StateResolver(s,TEXT,TEXT,protected_actor_id='b').resolve(payload(s,'b'));s=r.state
    d['evidence_ids']=[eid for eid,e in s['characters']['b']['personality']['evidence'].items() if e['player_owned']]
    r=StateResolver(s,TEXT,TEXT,protected_actor_id='b').resolve(raw(s,value_deltas=[d]))
    assert not r.warnings and 'honesty' in r.state['characters']['b']['values']


def test_explicit_value_partial_refine_retire_agency_and_knowledge():
    s=setup()['world_state'];d=value_delta('a');d.update(basis='explicit_statement',source_event_id='statement',
        player_evidence=TEXT,player_assertion='explicit_value')
    p=raw(s,events=[dict(id='statement',text=TEXT,evidence=TEXT,participants=['a'],witnesses=['a'],fact_ids=[])],value_deltas=[d])
    assert not StateResolver(s,TEXT,'Слушаю.').resolve(p).state['characters']['a']['values']
    r=StateResolver(s,TEXT,TEXT).resolve(p);assert not r.warnings
    assert r.state['knowledge']==s['knowledge']
    assert project_values(dict(fields={}),r.state['characters']['a'],state=r.state,observer='b')['fields']=={}
    d.update(operation='refine',expected_revision=1,expected_text=d['text'],text='Ценит честность и такт.')
    r=StateResolver(r.state,TEXT,TEXT).resolve(p);assert not r.warnings
    assert r.state['characters']['a']['values']['honesty']['revision']==2
    d.update(operation='retire',expected_revision=2,expected_text=d['text'],text='')
    retired=StateResolver(r.state,TEXT,TEXT).resolve(p);assert not retired.warnings
    assert retired.state['characters']['a']['values']['honesty']['status']=='retired'
    assert project_values(dict(fields={'Ценности':'Старое значение'}),retired.state['characters']['a'])['fields']=={}


def test_migration_keeps_legacy_prose_and_salvages_optional_fields(caplog):
    snap=snapshot();snap['character_cards'][0]['fields'].update({'Ценности':'Честность; верность.', 'Характер':'Терпеливый.'})
    for actor in snap['world_state']['characters'].values(): actor.pop('values',None)
    first=migrate_v2(snap).snapshot;assert first==migrate_v2(first).snapshot
    assert [r['text'] for r in first['world_state']['characters']['a']['values'].values()]==['Честность; верность.']
    bad=deepcopy(first);bad['world_state']['characters']['a']['values']['bad']={'text':42}
    assert migrate_v2(bad).snapshot['world_state']['characters']['a']['values']==first['world_state']['characters']['a']['values']
    assert 'malformed optional value' in caplog.text


def test_hundred_npcs_and_large_actor_records_stay_bounded():
    snap=initial()
    for n in range(120):
        cid=f'dormant_{n}';snap['world_state']['characters'][cid]=Character(id=cid,goals=['DO_NOT_INJECT_'+cid]).model_dump()
        snap['character_cards'].append(dict(id=cid,name=cid,fields={}))
    actor=snap['world_state']['characters']['a']
    actor['intentions'] += [Motivation(id=f'int_{n}',text='Намерение '+str(n)).model_dump() for n in range(120)]
    for extraction in (None,MEET):
        msgs=build_context(snap,[],'Продолжить','turn',32768,2000,extraction_text=extraction)
        assert 'DO_NOT_INJECT' not in str(msgs) and len(str(msgs))<100000
        current=json.loads(next(m['content'].split('\n',1)[1] for m in msgs if m['content'].startswith('Текущее состояние')))
        assert len(current['characters']['a']['intentions'])<=8 and len(current['characters'])<20


def test_atomic_history_branches_do_not_rewrite_prior_state():
    conn=db();snap=initial();r=StateResolver(snap['world_state'],MEET,'').resolve(completion(snap['world_state']))
    with pytest.raises(RuntimeError),conn:
        committed_snapshot(conn,snap,r);raise RuntimeError('abort')
    assert not conn.execute('SELECT id FROM world_history_v3').fetchall()
    with conn:
        left=committed_snapshot(conn,snap,r)
        right=committed_snapshot(conn,snap,StateResolver(snap['world_state'],'Тишина.','').resolve(raw(snap['world_state'])))
    assert left['world_state']['characters']['a']['intentions'][0]['status']=='completed'
    assert right['world_state']['characters']['a']['intentions'][0]['status']=='active'
    assert any(c.get('kind')=='motivation_transition' for c in read_history(conn,left['history_head'])[0]['state_changes'])
    assert not any(c.get('kind')=='motivation_transition' for c in read_history(conn,right['history_head'])[0]['state_changes'])


def test_checkpoint_real_game_reload_regenerate_variant_rollback(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import CONFIG
    from runtime_v3_fixture import execute
    repo=Repository(tmp_path/'goals.sqlite');sid=load_fixture(repo,'goals')['save']
    before=repo.get_snapshot(sid);s=before['world_state'];cid='qa_ilya'
    p=completion(s,cid);jid=repo.begin_job(sid,'Иду навстречу.','turn',CONFIG)
    calls=execute(repo,jid,p,MEET);assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    assert len(calls)==2
    after=repo.get_snapshot(sid);turn=repo.list_turns(sid)[-1]
    assert after['world_state']['characters'][cid]['intentions'][0]['status']=='completed'
    repo=Repository(repo.path);assert repo.get_snapshot(sid)==after
    jid=repo.begin_job(sid,'','regenerate',CONFIG);execute(repo,jid,raw(s),'Соня ещё не пришла.')
    assert repo.get_job(jid)['status']=='saved'
    assert repo.get_snapshot(sid)['world_state']['characters'][cid]['intentions'][0]['status']=='active'
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)['world_state']['characters'][cid]['intentions']==after['world_state']['characters'][cid]['intentions']
    repo.rollback_last(sid);assert repo.get_snapshot(sid)['world_state']['characters'][cid]['intentions']==s['characters'][cid]['intentions']
    jid=repo.begin_job(sid,'Жду.','turn',CONFIG);execute(repo,jid,raw(s),'Илья ждёт.');assert repo.get_job(jid)['status']=='saved'


def test_legacy_migration_start_turn_reload_next_turn(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job
    repo=Repository(tmp_path/'legacy.sqlite');sid=load_fixture(repo)['save'];snap=repo.get_snapshot(sid)
    for actor in snap['world_state']['characters'].values():
        actor.pop('values',None)
        for field in ('goals','intentions'):
            actor[field]=[r['text'] for r in actor[field]]
    with repo.connect() as conn: conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snap),sid))
    ordinary_job(repo,sid,'start');ordinary_job(repo,sid)
    repo=Repository(repo.path);ordinary_job(repo,sid)


def test_review_batches_rotate_instead_of_starving_and_total_updates_are_capped():
    rows=[Motivation(id=str(n),text='Проверить '+str(n),review_required=['roles:x:closed']).model_dump() for n in range(100)]
    seen=set()
    for turn in range(25): seen.update(r['id'] for r in context_records(rows,evaluation=True,turn=turn))
    assert seen=={str(n) for n in range(100)}
    s=initial()['world_state'];s['characters']['b']['intentions']=[]
    changes=[dict(text=f'Новая цель {n}',status='active',evidence=OFFER) for n in range(40)]
    r=StateResolver(s,OFFER,'').resolve(raw(s,character_changes=[dict(id='b',intentions_updates=changes)]))
    assert len(r.state['characters']['b']['intentions'])==24
    assert any(w['code']=='motivation_budget' for w in r.warnings)


def test_value_evolution_archive_and_sibling_sources():
    from backend.runtime_v3.personality import history_query
    conn=db();snap=setup();source_ids=[]
    for n in range(3):
        s=snap['world_state'];r=StateResolver(s,TEXT,'').resolve(payload(s))
        snap=committed_snapshot(conn,snap,r);source_ids=list(r.state['characters']['b']['personality']['evidence'])
    # Evicted current evidence is still addressable through recorded lineage.
    snap['world_state']['characters']['b']['personality']['evidence']={}
    d=value_delta();d['evidence_ids']=source_ids
    read=lambda **filters:history_query(conn,snap['history_head'],**filters)
    r=StateResolver(snap['world_state'],TEXT,'',development_query=read).resolve(raw(snap['world_state'],value_deltas=[d]))
    assert not r.warnings and r.state['characters']['b']['values']['honesty']
    unrelated=lambda **filters:history_query(conn,None,**filters)
    r=StateResolver(snap['world_state'],TEXT,'',development_query=unrelated).resolve(raw(snap['world_state'],value_deltas=[d]))
    assert not r.state['characters']['b']['values']


def test_unblocked_needs_semantic_assertion_and_creation_requires_player_statement():
    s=initial()['world_state'];s['characters']['a']['intentions'][0]['status']='blocked'
    text='Встреча снова возможна.'
    change=dict(id=ILYA,status='active',evidence=text)
    p=raw(s,character_changes=[dict(id='a',intentions_updates=[change])])
    assert StateResolver(s,text,'').resolve(p).state['characters']['a']['intentions'][0]['status']=='blocked'
    change['assertion']='unblocked'
    assert StateResolver(s,text,'').resolve(p).state['characters']['a']['intentions'][0]['status']=='active'
    claim=dict(text='Travel abroad',status='active',evidence=text)
    p=raw(s,character_changes=[dict(id='a',goals_updates=[claim])])
    assert len(StateResolver(s,text,'').resolve(p).state['characters']['a']['goals'])==1
    quote='My new goal is to travel abroad.'
    claim.update(evidence=quote,player_evidence=quote,player_assertion='explicit_choice')
    r=StateResolver(s,text,quote).resolve(p)
    assert len(r.state['characters']['a']['goals'])==2


def test_attaching_dead_dependency_does_not_silently_acknowledge_review():
    s=initial()['world_state'];s['characters']['b']['life_status']='dead';s['camera']['present_character_ids']=['a']
    change=dict(id=ILYA,status='active',dependencies={'characters':['b']},evidence=MEET)
    p=raw(s,character_changes=[dict(id='a',intentions_updates=[change])])
    r=StateResolver(s,MEET,'').resolve(p)
    assert r.state['characters']['a']['intentions'][0]['review_required']
    again=StateResolver(r.state,MEET,'').resolve(p)
    assert again.state['characters']['a']['intentions']==r.state['characters']['a']['intentions']


def test_canonical_graduation_can_resolve_only_linked_goal():
    s=initial()['world_state'];s['roles']['student']=NarrativeRole(id='student',actor_id='a',kind='student',title='Студент',status='closed').model_dump()
    s['characters']['a']['goals'].append(Motivation(id='graduate',text='Окончить университет',dependencies={'roles':['student']}).model_dump())
    text='Илья окончил университет и получил диплом.'
    p=raw(s,events=[dict(id='graduation',text=text,evidence=text,participants=['a'],witnesses=['a'],fact_ids=[])],
        character_changes=[dict(id='a',goals_updates=[dict(id='graduate',status='completed',evidence=text,source_event_id='graduation')])])
    r=StateResolver(s,text,'').resolve(p)
    assert [g['status'] for g in r.state['characters']['a']['goals']]==['active','completed']
    assert r.state['characters']['a']['values']==s['characters']['a']['values']


def test_value_real_reload_regenerate_variant_and_rollback(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import CONFIG
    from runtime_v3_fixture import execute
    repo=Repository(tmp_path/'value-lineage.sqlite');sid=load_fixture(repo,'goals')['save']
    before=repo.get_snapshot(sid);s=before['world_state'];cid='qa_ilya'
    old=next(iter(s['characters'][cid]['values'].values()))
    text='Для меня важна честность, но я не хочу ранить людей правдой.'
    d=dict(actor_id=cid,item_id=old['id'],operation='refine',text='Ценит честность и такт.',
        expected_revision=old['revision'],expected_text=old['text'],basis='explicit_statement',
        source_event_id='statement',evidence=text,player_evidence=text,player_assertion='explicit_value',rationale='Явно уточнил принцип.')
    p=raw(s,value_deltas=[d],events=[dict(id='statement',text=text,evidence=text,participants=[cid],witnesses=[cid],fact_ids=[])])
    jid=repo.begin_job(sid,text,'turn',CONFIG);execute(repo,jid,p,text)
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    after=repo.get_snapshot(sid);assert after['world_state']['characters'][cid]['values'][old['id']]['revision']==1
    repo=Repository(repo.path);assert repo.get_snapshot(sid)==after
    view=repo.get_save(sid)['state']['world']['characters'][cid]
    assert view['value_history'][0]['before']==old['text']
    turn=repo.list_turns(sid)[-1];jid=repo.begin_job(sid,'','regenerate',CONFIG)
    execute(repo,jid,raw(s),'Илья обдумывает ответ.')
    assert repo.get_job(jid)['status']=='saved'
    assert repo.get_snapshot(sid)['world_state']['characters'][cid]['values']==s['characters'][cid]['values']
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)['world_state']['characters'][cid]['values']==after['world_state']['characters'][cid]['values']
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)['world_state']['characters'][cid]['values']==s['characters'][cid]['values']
