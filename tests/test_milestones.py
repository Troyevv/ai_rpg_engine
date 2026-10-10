"""#40: accepted truth -> immutable index, lineage, knowledge and bounded context."""
from copy import deepcopy
import json
import sqlite3

import pytest
from hypothesis import given, settings, strategies as st

from backend.runtime_v3.milestones import derive, query, index_batch, visible_query, reader, select_context
from backend.runtime_v3.repository import initialize, append_history, committed_snapshot, read_history
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.models import Fact, Knowledge
from test_residence_roles import state, run, residence, role, TEXT


def db():
    result = sqlite3.connect(':memory:'); initialize(result); result.commit()
    return result


def snapshot(s=None):
    return dict(schema_version=3,world_state=s or state(),history_head=None,memory={},
        character_cards=[dict(id=c,name='Name '+c,fields={}) for c in 'abc'],campaign=dict(protagonist_id='a'))


def relations(s, rows):
    return run(s,'social_relation_changes',rows,actor_names={'a':'Old A','b':'Old B'})


def marriage():
    return dict(id='marriage',kind='spouse',source_id='a',target_id='b')


def test_marriage_divorce_engagement_names_birth_death_and_no_inferred_marriage():
    s=state()
    engagement=relations(s,[dict(id='engagement',kind='engaged',source_id='a',target_id='b')])
    assert [m['category'] for m in derive(engagement.history)]==['engagement']
    wedding=relations(engagement.state,[marriage(),dict(id='engagement',status='closed',outcome='superseded')])
    m=next(m for m in derive(wedding.history) if m['category']=='marriage')
    assert m['names']=={'a':'Old A','b':'Old B'}
    renamed=run(wedding.state,'life_changes',[dict(id='b',display_name='New B')],actor_names={'b':'Old B'})
    assert [m['category'] for m in derive(renamed.history)]==['name_change']
    assert m['names']['b']=='Old B'
    divorce=relations(renamed.state,[dict(id='marriage',status='closed',outcome='divorced')])
    assert [m['category'] for m in derive(divorce.history)]==['divorce']
    death=run(divorce.state,'life_changes',[dict(id='b',life_status='dead')])
    assert [m['category'] for m in derive(death.history)]==['death']
    repeat=run(death.state,'life_changes',[dict(id='b',life_status='dead')])
    assert not derive(repeat.history)
    text='Дата рождения: 1990-01-01.'
    birth=StateResolver(s,text,'').resolve(dict(final_scene=dict(location_id='home',present_character_ids=['a']),
        character_changes=[dict(id='b',birth_date='1990-01-01',evidence=text)]))
    b=derive(birth.history)[0]
    assert (b['category'],b['date'],b['minute'])==('birth','1990-01-01',None)
    assert not derive(run(s,'life_changes',[dict(id='b',life_status='alive')]).history)
    assert not derive({'events':[dict(id='invented',text='A married B and died.') ]})


def test_roles_residence_and_routine_does_not_flood():
    r=run(state(),'residence_changes',[residence()])
    assert [m['category'] for m in derive(r.history)]==['relocation']
    r=run(r.state,'residence_changes',[residence('new',location='second',replaces=['r1'])])
    assert {m['category'] for m in derive(r.history)}=={'relocation','residence_ended'}
    r=run(r.state,'role_changes',[role()])
    assert [m['category'] for m in derive(r.history)]==['role_started']
    r=run(r.state,'role_changes',[dict(id='job',status='closed',outcome='retired')])
    assert [m['category'] for m in derive(r.history)]==['role_ended']
    for destination in ('room','south','home'):
        r=run(r.state,scene=dict(location_id=destination,present_character_ids=['a']))
        assert not derive(r.history)
    assert not derive(run(state(),'role_changes',[role(kind='other')]).history)


def test_atomic_index_retry_replay_save_reload_and_sibling_branches(tmp_path):
    path=tmp_path/'milestones.sqlite'; conn=sqlite3.connect(path);initialize(conn);conn.commit()
    before=snapshot(); r=relations(before['world_state'],[marriage()])
    with pytest.raises(RuntimeError), conn:
        committed_snapshot(conn,before,r)
        raise RuntimeError('injected before save commit')
    assert conn.execute('SELECT COUNT(*) FROM world_milestones_v3').fetchone()[0]==0
    with conn:
        after=committed_snapshot(conn,before,r)
        index_batch(conn,after['history_head'],r.history)
        replay=append_history(conn,after['history_head'],r.history)
        sibling=committed_snapshot(conn,before,run(before['world_state']))
    assert len(query(conn,replay))==1
    assert conn.execute('SELECT COUNT(*) FROM world_milestones_v3').fetchone()[0]==1
    assert not query(conn,before['history_head']) and not query(conn,sibling['history_head'])
    conn.close();conn=sqlite3.connect(path);initialize(conn)
    assert len(query(conn,json.loads(json.dumps(after))['history_head']))==1
    assert query(conn,replay)[0]['source_record_id']==r.history['turns'][0]['id']


def test_thousands_of_batches_query_actor_category_time_and_protagonist_boundary():
    conn=db(); s=state(); head=None
    for section,rows in [('social_relation_changes',[marriage()]),
            ('social_relation_changes',[dict(id='marriage',status='closed',outcome='divorced')]),
            ('residence_changes',[residence()]),('life_changes',[dict(id='b',life_status='dead')])]:
        r=run(s,section,rows); s=r.state;head=append_history(conn,head,r.history)
    # Explicit structured Runtime boundary, not a camera switch or inferred prose.
    batch={'state_changes':[dict(kind='protagonist_transition',entity='main',before={'actor_id':'a'},
        after={'actor_id':'c'},minute=20,evidence='Explicit Runtime command'),
        dict(kind='birth_date_established',entity='c',before={'birth_date':None},after={'birth_date':'1990-01-01'})]}
    head=append_history(conn,head,batch)
    for turn in range(3000):
        head=append_history(conn,head,{'turns':[dict(turn_id=turn+10)],'events':[dict(id=str(turn),text='Routine dialogue')]})
    assert not read_history(conn,head)[0]['state_changes']
    assert {m['category'] for m in query(conn,head)}=={'marriage','divorce','death','birth','relocation','protagonist_transition'}
    assert len(query(conn,head,actor_ids=['a'],category='marriage',start_minute=5,end_minute=5))==1
    assert not query(conn,head,actor_ids=['c'],category='marriage')
    assert len(query(conn,head,start_date='1990-01-01',end_date='1990-01-01'))==1
    assert len({m['id'] for offset in range(6) for m in query(conn,head,limit=1,offset=offset)})==6
    with pytest.raises(ValueError): query(conn,head,limit=101)
    with pytest.raises(ValueError): query(conn,head,start_minute=9,end_minute=2)


def test_conservative_backfill_never_rewrites_snapshots_or_history(tmp_path):
    conn=sqlite3.connect(tmp_path/'legacy.sqlite')
    conn.execute('CREATE TABLE world_history_v3(id TEXT PRIMARY KEY,parent_id TEXT,payload_json TEXT,created_at TEXT)')
    history=relations(state(),[marriage()]).history
    conn.executemany('INSERT INTO world_history_v3 VALUES(?,?,?,NULL)',[
        ('old',None,json.dumps(history)), ('prose','old',json.dumps({'events':[dict(text='They married.')]})),
        ('broken','prose','not json')])
    original=conn.execute('SELECT * FROM world_history_v3').fetchall()
    initialize(conn); initialize(conn)
    assert len(query(conn,'broken'))==1
    assert conn.execute('SELECT * FROM world_history_v3').fetchall()==original
    assert not derive({'state_changes':[None,{'kind':'life_changes','entity':'b','after':[]} ]})
    # Damaged cycles terminate instead of hanging a read.
    conn.execute("UPDATE world_history_v3 SET parent_id='broken' WHERE id='old'")
    assert len(query(conn,'broken'))==1
    assert not derive({'state_changes':[dict(kind='life_changes',entity='b',before={},
        after={'display_name':'New','name_history':['damaged']})]})
    conn.execute("UPDATE world_milestones_v3 SET payload_json='broken'")
    assert not query(conn,'broken')


def test_shared_causal_event_process_and_bad_reference_local_diagnostic():
    s=state(); quote=TEXT
    raw=dict(final_scene=dict(location_id='home',present_character_ids=['a']),
        events=[dict(id='accident',text=quote,evidence=quote,participants=['b'],witnesses=[],fact_ids=[])],
        condition_changes=[dict(id='injury',actor_id='b',description='Injury',effects={'can_act':False},
            assertion='established',evidence=quote,source_event_id='accident')],
        life_changes=[dict(id='b',life_status='dead',assertion='established',evidence=quote,source_event_id='accident')])
    r=StateResolver(s,quote,'').resolve(raw)
    changes=[c for c in r.history['state_changes'] if c.get('source_event_id')]
    assert len(changes)==2 and len({c['source_event_id'] for c in changes})==1
    conn=db();head=append_history(conn,None,r.history)
    assert len(query(conn,head,source_event_id=changes[0]['source_event_id']))==1
    assert derive(r.history)[0]['source_event_id']==r.history['events'][0]['id']
    r=run(state(),'role_changes',[role(source_event_id='absent',source_process_id=[])])
    assert len(derive(r.history))==1 and len(r.warnings)==2
    assert derive(r.history)[0]['source_event_id'] is None


def test_100_npc_bounded_context_no_archived_actor_promotion_and_current_truth_wins():
    from backend.runtime_v3.models import Character
    from backend.runtime_v3.context import build_context
    s=state();snap=snapshot(s);conn=db()
    head=append_history(conn,None,run(s,'life_changes',[dict(id='b',life_status='dead')]).history)
    s['camera']['present_character_ids'].append('b');s['characters']['b']['location_id']='home'
    for i in range(120):
        cid=f'npc{i}';s['characters'][cid]=Character(id=cid).model_dump()
        snap['character_cards'].append(dict(id=cid,name=cid,fields={}))
        head=append_history(conn,head,{'state_changes':[dict(kind='life_changes',entity=cid,
            before={'life_status':'alive'},after={'life_status':'dead'},minute=1,evidence='IRRELEVANT ARCHIVE')]})
    read=lambda **filters:query(conn,head,**filters)
    messages=build_context(snap,[],'Разговор.','turn',32768,2000,world_history={'_milestone_query':read})
    current=json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('Текущее состояние')))
    assert current['characters']['b']['life_status']=='alive'
    assert current['milestones'][0]['diagnostic']=='milestone_conflicts_with_current_life_status'
    assert 'IRRELEVANT ARCHIVE' not in str(messages)
    assert len(current['milestones'])<=16
    limited=build_context(snap,[],'Разговор.','turn',32768,2000,world_history={'_milestone_query':read},target_context_budget=1)
    current=json.loads(next(m['content'].split('\n',1)[1] for m in limited if m['content'].startswith('Текущее состояние')))
    assert not current.get('milestones') and current['characters']['b']['life_status']=='alive'


@given(st.lists(st.booleans(),min_size=1,max_size=30))
@settings(max_examples=20,deadline=None)
def test_property_retry_and_branch_membership(choices):
    conn=db(); root=None;batch=relations(state(),[marriage()]).history
    for include in choices:
        parent=root
        root=append_history(conn,parent,batch if include else {})
        sibling=append_history(conn,parent,{})
        assert len(query(conn,root))<=1
        assert query(conn,sibling)==query(conn,parent)
    assert bool(query(conn,root))==any(choices)


def test_qa_checkpoint_api_knowledge_filters_and_real_engine_lifecycle(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture, ACTOR_ID
    from test_narrative_test_world import ordinary_job, CONFIG
    from runtime_v3_fixture import execute
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    repo=Repository(tmp_path/'qa.sqlite');sid=load_fixture(repo,'milestones')['save']
    initial=repo.get_snapshot(sid)
    with repo.connect() as conn:
        all_rows=query(conn,initial['history_head'])
        assert not read_history(conn,initial['history_head'])[0]['state_changes']
    assert {r['category'] for r in all_rows}>={'engagement','marriage','divorce','relocation','role_ended','death'}
    public=visible_query(repo,initial)
    assert 'history_id' not in str(public) and 'source_event_id' not in str(public)
    assert len(public)==len(all_rows)
    hidden=deepcopy(initial);hidden['world_state']['camera']['controlled_actor_id']='qa_zoya'
    assert not visible_query(repo,hidden)
    # Removing opening knowledge must hide even metadata/pagination of that event.
    hidden=deepcopy(initial);del hidden['world_state']['knowledge'][ACTOR_ID+':qa_wedding_fact']
    assert not visible_query(repo,hidden,category='marriage')
    client=TestClient(create_app(repo.path))
    response=client.get(f'/api/saves/{sid}/milestones',params={'category':'marriage','actor_id':'qa_timur'})
    assert response.status_code==200 and len(response.json())==1
    assert response.json()[0]['category']=='marriage'
    assert client.get(f'/api/saves/{sid}/milestones',params={'limit':101}).status_code==409
    ordinary_job(repo,sid,'start');ordinary_job(repo,sid)
    repo=Repository(repo.path);ordinary_job(repo,sid)
    before=repo.get_snapshot(sid)
    camera=before['world_state']['camera']
    raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids']),
        role_changes=[dict(id='qa_job',status='closed',outcome='retired',assertion='established',
            evidence=TEXT,player_assertion='explicit_choice',player_evidence=TEXT)])
    jid=repo.begin_job(sid,TEXT,'turn',CONFIG);execute(repo,jid,raw,TEXT)
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    after=repo.get_snapshot(sid);turn=repo.list_turns(sid)[-1]
    before_rows=reader(repo,before['history_head'])()
    after_rows=reader(repo,after['history_head'])()
    assert len(after_rows)==len(before_rows)+1
    repo=Repository(repo.path);assert reader(repo,repo.get_snapshot(sid)['history_head'])()==after_rows
    jid=repo.begin_job(sid,'','regenerate',CONFIG)
    execute(repo,jid,{'final_scene':raw['final_scene']},'Обычный разговор.')
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    assert reader(repo,repo.get_snapshot(sid)['history_head'])()==before_rows
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert reader(repo,repo.get_snapshot(sid)['history_head'])()==after_rows
    repo.rollback_last(sid)
    assert reader(repo,repo.get_snapshot(sid)['history_head'])()==before_rows
    assert repo.get_snapshot(sid)==before


def test_pov_switch_does_not_create_protagonist_milestone(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    repo=Repository(tmp_path/'pov.sqlite');sid=load_fixture(repo,'milestones')['save']
    before=repo.get_snapshot(sid)
    repo.switch_actor(sid,'qa_vera',repo.get_save(sid)['revision'])
    after=repo.get_snapshot(sid)
    assert before['campaign']['protagonist_id']==after['campaign']['protagonist_id']
    assert reader(repo,after['history_head'])()==reader(repo,before['history_head'])()
    assert not reader(repo,after['history_head'])(category='protagonist_transition')


def test_significant_custom_roles_and_routine_suppression():
    r=run(state(),'role_changes',[role(kind='guild_apprenticeship',significance='major')])
    assert [m['category'] for m in derive(r.history)]==['role_started']
    assert not derive(run(state(),'role_changes',[role(significance='routine')]).history)
    invalid=run(state(),'role_changes',[role(significance='made_up')])
    assert invalid.warnings and not invalid.state['roles'] and not derive(invalid.history)


def test_same_minute_distinct_transitions_and_summary_edits_use_source_identity():
    conn=db();s=state();head=None
    for name in ('B1','B2','B1'):
        r=run(s,'life_changes',[dict(id='b',display_name=name)],actor_names={'b':'B'},
              scene=dict(location_id='home',present_character_ids=['a'],elapsed_minutes=0))
        s=r.state;head=append_history(conn,head,r.history)
    assert len(query(conn,head,category='name_change'))==3
    batch=deepcopy(r.history)
    next(c for c in batch['state_changes'] if c.get('id'))['evidence']='Different rendering of same accepted source'
    head=append_history(conn,head,batch)
    assert len(query(conn,head,category='name_change'))==3


def test_causal_chain_condition_missed_commitment_and_role_milestone():
    from backend.runtime_v3.models import ScheduledEvent
    s=run(state(),'role_changes',[role(actor='b')]).state
    s['scheduled_events']['meeting']=ScheduledEvent(id='meeting',description='Meeting',character_ids=['b'],
        due_minute=10,commitment=True).model_dump()
    raw=dict(final_scene=dict(location_id='home',present_character_ids=['a']),
        events=[dict(id='accident',text=TEXT,evidence=TEXT,participants=['b'],witnesses=[],fact_ids=[])],
        condition_changes=[dict(id='injury',actor_id='b',description='Injury',effects={'can_act':False},
            assertion='established',evidence=TEXT,source_event_id='accident')],
        role_changes=[dict(id='job',status='closed',outcome='left',assertion='established',evidence=TEXT,
            source_event_id='accident',source_process_id='injury')],
        scheduled_event_changes=[dict(id='meeting',assertion='missed',evidence=TEXT,
            source_event_id='accident',source_process_id='injury')])
    r=StateResolver(s,TEXT,'').resolve(raw)
    assert not r.warnings
    changes=[c for c in r.history['state_changes'] if c.get('source_event_id')]
    assert {c['kind'] for c in changes}=={'condition_changes','roles','scheduled_events'}
    assert len({c['source_event_id'] for c in changes})==1
    assert r.state['scheduled_events']['meeting']['status']=='cancelled'
    conn=db();head=append_history(conn,None,r.history)
    rows=query(conn,head,source_process_id='injury')
    assert len(rows)==1 and rows[0]['category']=='role_ended'


def test_old_key_category_is_not_buried_by_repeated_career_changes():
    from backend.runtime_v3.scope import ContextScope
    conn=db();s=state();r=relations(s,[marriage()]);s=r.state
    head=append_history(conn,None,r.history)
    for n in range(40):
        r=run(s,'role_changes',[role(rid='job'+str(n))]);s=r.state
        head=append_history(conn,head,r.history)
    scope=ContextScope('a',present_actor_ids={'a'})
    selected=select_context(s,scope,lambda **filters:query(conn,head,**filters))
    assert any(m['category']=='marriage' for m in selected)
    assert len(selected)<=2
