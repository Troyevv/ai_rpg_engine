"""#67 domain, lineage, agency and playable integration regressions."""
from copy import deepcopy
import json
import pytest
from hypothesis import given, strategies as st
from backend.runtime_v3.models import PersonalityProfile
from backend.runtime_v3.personality import initialize_profiles, project_card, context_profile
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.migration import migrate_v2
from backend.runtime_v3.repository import committed_snapshot, read_history
from test_milestones import snapshot, db

TEXT = 'Я отказалась молчать и спокойно объяснила свою позицию.'


def setup():
    snap=snapshot()
    snap['character_cards'][1]['fields']={'Характер':'Осторожная','Привычки':'Читает вечером','Сильные стороны':'Внимательна'}
    return initialize_profiles(snap)


def payload(s,actor='b',kind='behavior',change=None,text=TEXT):
    raw=dict(final_scene=dict(location_id=s['camera']['location_id'],present_character_ids=s['camera']['present_character_ids']),
        events=[dict(id='source',text=text,evidence=text,participants=[actor],witnesses=[],fact_ids=[])],
        development_evidence=[dict(id='proof',actor_id=actor,source_event_id='source',meaning='Отстаивает границы',kind=kind,
            assertion='completed',evidence=text,player_evidence=text,player_assertion='completed_voluntary_behavior')])
    if change: raw['personality_deltas']=[change]
    return raw


def delta(actor='b',refs=None,item='traits',text='Осторожная, увереннее отстаивает границы',old='Осторожная',rev=0,operation='refine',field='traits',evidence=TEXT):
    return dict(actor_id=actor,evidence_ids=refs or ['proof'],rationale='Устойчивое поведение поддерживает постепенное изменение.',
        developmental_fit='established_capability',evidence=evidence,
        operations=[dict(item_id=item,field=field,operation=operation,text=text,expected_text=old,expected_revision=rev)])


def run(s,actor='b',kind='behavior',change=None,**kwargs):
    return StateResolver(s,TEXT,kwargs.pop('player',TEXT),**kwargs).resolve(payload(s,actor,kind,change))

def profile(s,actor='b'): return s['characters'][actor]['personality']
def refs(s,actor='b'): return list(profile(s,actor)['evidence'])
def pattern(s,actor='b'):
    for _ in range(3): s=run(s,actor).state
    return s


def test_pattern_partial_delta_chronology():
    s=pattern(setup()['world_state']);prior=deepcopy(profile(s))
    r=run(s,change=delta(refs=refs(s)))
    assert not r.warnings
    assert profile(r.state)['items']['traits']['text'].endswith('границы')
    assert profile(r.state)['items']['habits']==prior['items']['habits']
    assert profile(r.state)['items']['strengths']==prior['items']['strengths']
    c=next(c for c in r.history['state_changes'] if c.get('kind')=='personality_delta')
    assert c['before']['traits']['text']=='Осторожная' and len(c['sources'])==3 and c['source_record_id']


def test_ordinary_episode_emotion_and_full_card_cannot_rewrite():
    s=setup()['world_state'];r=run(s,change=delta())
    assert profile(r.state)['items']==profile(s)['items']
    assert any(w['code']=='personality_evidence_insufficient' for w in r.warnings)
    raw=payload(s);raw['development_evidence']=[]
    raw['character_changes']=[dict(id='b',emotion='Злится',personality={'traits':'Агрессивная'},evidence=TEXT)]
    r=StateResolver(s,TEXT,'').resolve(raw)
    assert profile(r.state)['items']==profile(s)['items']


def test_external_exceptional_change_requires_player_and_completion():
    s=setup()['world_state'];s['camera'].update(controlled_actor_id='b',present_character_ids=['b'])
    s['characters']['b']['location_id']=s['camera']['location_id']
    assert profile(run(s,kind='turning_point',change=delta(),player='Смотрю в окно.').state)['items']==profile(s)['items']
    assert not run(s,kind='turning_point',change=delta()).warnings
    r=StateResolver(s,'Она посмотрела в окно.',TEXT).resolve(payload(s,'b','turning_point',delta()))
    assert profile(r.state)['items']==profile(s)['items']


def test_npc_experience_not_permission_after_external_switch():
    s=pattern(setup()['world_state']);s['camera'].update(controlled_actor_id='b',present_character_ids=['b'])
    s['characters']['b']['location_id']=s['camera']['location_id']
    assert profile(run(s,change=delta(refs=refs(s))).state)['items']==profile(s)['items']
    s=pattern(s);r=run(s,change=delta(refs=refs(s)[-3:]))
    assert not r.warnings and profile(r.state)['items']!=profile(s)['items']


def test_retry_reload_same_source_cannot_reapply_changed_text():
    s=setup()['world_state'];raw=payload(s,'b','turning_point',delta())
    first=StateResolver(s,TEXT,TEXT,turn_id=1).resolve(raw)
    raw['personality_deltas'][0]['operations'][0]['text']='Иная личность'
    retry=StateResolver(json.loads(json.dumps(first.state)),TEXT,TEXT,turn_id=1).resolve(raw)
    assert profile(retry.state)==profile(first.state)
    assert not any(c.get('kind')=='personality_delta' for c in retry.history['state_changes'])


def test_retirement_stale_cas_and_atomicity():
    s=pattern(setup()['world_state']);r=run(s,change=delta(refs=refs(s),operation='retire',text=''))
    assert 'traits' not in profile(r.state)['items'] and 'habits' in profile(r.state)['items']
    d=delta(refs=refs(s));d['operations'].append(dict(item_id='absent',field='weaknesses',operation='retire',text='',expected_text='No',expected_revision=0))
    assert profile(run(s,change=d).state)['items']==profile(s)['items']
    assert profile(run(s,change=delta(refs=refs(s),old='Wrong')).state)['items']==profile(s)['items']


def test_child_sparse_no_inheritance_or_age_only_generation():
    s=setup()['world_state'];s['characters']['b'].update(developmental_stage='infant',personality=PersonalityProfile().model_dump())
    d=delta(item='curious',old=None,operation='establish',text='Любознательная')
    assert not profile(run(s,kind='turning_point',change=d).state)['items']
    d['operations'][0]['field']='temperament';r=run(s,kind='turning_point',change=d)
    assert not r.warnings
    s=r.state;before=deepcopy(profile(s));s['meta']['world_time']+=10*365*1440
    s['characters']['b']['developmental_stage']='adolescent'
    r=StateResolver(s,'Прошли годы.','').resolve({'final_scene':payload(s)['final_scene']})
    assert profile(r.state)==before
    assert project_card(dict(fields={}),r.state['characters']['b'])['fields']=={'Темперамент':'Любознательная'}


def test_background_npc_and_external_protection():
    s=setup()['world_state'];r=run(s,kind='turning_point',change=delta(),mode='background',protected_actor_id='a',player='',observed=False)
    assert not r.warnings and profile(r.state)['items']!=profile(s)['items']
    r=run(s,actor='a',kind='turning_point',mode='background',protected_actor_id='a',player='')
    assert profile(r.state,'a')==profile(s,'a')


def test_atomic_persistence_and_sibling_branch_isolation():
    conn=db();before=setup();r=run(before['world_state'],kind='turning_point',change=delta())
    with pytest.raises(RuntimeError),conn:
        committed_snapshot(conn,before,r)
        raise RuntimeError('abort')
    assert not conn.execute('SELECT id FROM world_history_v3').fetchall()
    with conn:
        left=committed_snapshot(conn,before,r)
        right=committed_snapshot(conn,before,run(before['world_state']))
    assert profile(left['world_state'])!=profile(right['world_state'])
    assert any(c.get('kind')=='personality_delta' for c in read_history(conn,left['history_head'])[0]['state_changes'])
    assert not any(c.get('kind')=='personality_delta' for c in read_history(conn,right['history_head'])[0]['state_changes'])


def test_legacy_baseline_and_malformed_optional_local(caplog):
    snap=snapshot();snap['character_cards'][1]['fields']={'Характер':'Старое описание целиком'}
    r=migrate_v2(snap).snapshot
    assert profile(r['world_state'])['items']['traits']['text']=='Старое описание целиком'
    assert migrate_v2(r).snapshot==r
    r['world_state']['characters']['b']['personality']='malformed'
    assert profile(migrate_v2(r).snapshot['world_state'])['items']['traits']['text']=='Старое описание целиком'
    assert 'malformed optional personality' in caplog.text


def test_hidden_change_and_provenance_not_in_ui():
    from backend.runtime_v3.selectors import ui_view
    snap=setup();snap['world_state']=run(snap['world_state'],kind='turning_point',change=delta()).state
    ui=ui_view(snap)
    assert ui['characters'][1]['fields']['Характер']==''
    assert 'personality' not in ui['world']['characters']['b']
    assert 'Отстаивает границы' not in json.dumps(ui,ensure_ascii=False)


@given(st.integers(min_value=1,max_value=100000000))
def test_elapsed_time_is_not_evidence(minutes):
    s=setup()['world_state'];before=deepcopy(profile(s));s['meta']['world_time']+=minutes
    assert profile(StateResolver(s,'Прошло время.','').resolve({'final_scene':payload(s)['final_scene']}).state)==before


def test_milestone_sources_respect_lineage():
    from backend.runtime_v3.milestones import query
    from test_milestones import relations, marriage
    conn=db();snap=setup();snap=committed_snapshot(conn,snap,relations(snap['world_state'],[marriage()]))
    read=lambda **filters:query(conn,snap['history_head'],**filters)
    raw=payload(snap['world_state'],'b','turning_point',delta());raw['events']=[]
    raw['development_evidence'][0].update(source_kind='milestone',source_event_id=read()[0]['id'])
    r=StateResolver(snap['world_state'],TEXT,'',milestone_query=read).resolve(raw)
    assert not r.warnings
    raw['development_evidence'][0]['source_event_id']='fabricated'
    bad=StateResolver(snap['world_state'],TEXT,'',milestone_query=read).resolve(raw)
    assert profile(bad.state)==profile(snap['world_state'])


def test_old_save_still_plays_after_migration(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job
    repo=Repository(tmp_path/'legacy.sqlite');sid=load_fixture(repo)['save'];snap=repo.get_snapshot(sid)
    for actor in snap['world_state']['characters'].values(): actor.pop('personality',None)
    with repo.connect() as conn: conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snap),sid))
    ordinary_job(repo,sid,'start');ordinary_job(repo,sid)
    repo=Repository(repo.path);ordinary_job(repo,sid)


def test_checkpoint_real_turn_reload_regenerate_variants_and_child_control(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture, ACTOR_ID
    from test_narrative_test_world import ordinary_job, CONFIG
    from runtime_v3_fixture import execute
    repo=Repository(tmp_path/'qa.sqlite');sid=load_fixture(repo,'personality')['save']
    original=repo.get_snapshot(sid)
    assert profile(original['world_state'],'qa_asya')['items']['drawing']['text']=='Любит рисовать.'
    ordinary_job(repo,sid);repo=Repository(repo.path);ordinary_job(repo,sid)
    repo.switch_actor(sid,'qa_asya',repo.get_save(sid)['revision'])
    controlled=repo.get_snapshot(sid)
    assert profile(controlled['world_state'],'qa_asya')==profile(original['world_state'],'qa_asya')
    # Three player-owned voluntary actions, same canonical path as selected choices.
    for n in range(3):
        before=repo.get_snapshot(sid);s=before['world_state']
        text=f'Я выбрала рисовать пейзаж и закончила рисунок номер {n+1}.'
        raw=payload(s,'qa_asya',text=text)
        raw['development_evidence'][0]['meaning']='Выбирает пейзажи для рисования.'
        if n==2:
            selected=[eid for eid,e in profile(s,'qa_asya')['evidence'].items() if e['player_owned']]+['proof']
            raw['personality_deltas']=[delta('qa_asya',refs=selected,item='drawing',field='preferences',
                old='Любит рисовать.',rev=1,text='Любит рисовать пейзажи.',evidence=text)]
        jid=repo.begin_job(sid,text,'turn',CONFIG);calls=execute(repo,jid,raw,text)
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
        assert len(calls)==2
    changed=repo.get_snapshot(sid);turn=repo.list_turns(sid)[-1]
    assert profile(changed['world_state'],'qa_asya')['items']['drawing']['text']=='Любит рисовать пейзажи.'
    jid=repo.begin_job(sid,'','regenerate',CONFIG);execute(repo,jid,dict(final_scene=raw['final_scene']),'Ася молчит.')
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    assert profile(repo.get_snapshot(sid)['world_state'],'qa_asya')==profile(before['world_state'],'qa_asya')
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert profile(repo.get_snapshot(sid)['world_state'],'qa_asya')==profile(changed['world_state'],'qa_asya')
    repo.rollback_last(sid)
    assert profile(repo.get_snapshot(sid)['world_state'],'qa_asya')==profile(before['world_state'],'qa_asya')
    repo.switch_actor(sid,ACTOR_ID,repo.get_save(sid)['revision'])
    current=repo.get_snapshot(sid);raw=dict(final_scene=payload(current['world_state'])['final_scene'])
    raw['final_scene']['elapsed_minutes']=1440
    jid=repo.begin_job(sid,'Отдыхаю.','turn',CONFIG);execute(repo,jid,raw,'Прошёл спокойный день.')
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    repo.switch_actor(sid,'qa_asya',repo.get_save(sid)['revision'])
    assert profile(repo.get_snapshot(sid)['world_state'],'qa_asya')==profile(before['world_state'],'qa_asya')


def test_context_hundred_dormant_characters_and_archive():
    from backend.runtime_v3.context import build_context
    from backend.runtime_v3.models import Character
    from backend.runtime_v3.personality import history_query
    snap=setup();conn=db()
    r=run(snap['world_state'],kind='turning_point',change=delta())
    snap=committed_snapshot(conn,snap,r)
    assert history_query(conn,snap['history_head'],actor_ids=['b'])[0]['before']['traits']['text']=='Осторожная'
    assert not history_query(conn,None,actor_ids=['b'])
    for n in range(120):
        cid=f'dormant_{n}'
        snap['world_state']['characters'][cid]=Character(id=cid).model_dump()
        snap['character_cards'].append(dict(id=cid,name=cid,fields={'Характер':'NOT_FOR_PROMPT_'+cid}))
    initialize_profiles(snap)
    msgs=build_context(snap,[],'Продолжить','turn',32768,2000,extraction_text=TEXT)
    text=str(msgs)
    assert 'NOT_FOR_PROMPT' not in text and 'seen_sources' not in text and 'personality_source_' not in text
    assert len(text)<80000


def test_evicted_sources_cannot_be_duplicated_on_replay():
    s=setup()['world_state'];first=run(s);s=first.state
    for _ in range(35): s=run(s).state
    # Recorded source turn used during an actual replay, not a fresh new action.
    s['meta']['turn_id']=1
    result=StateResolver(s,TEXT,TEXT,turn_id=1).resolve(payload(s))
    assert not any(c.get('kind')=='development_evidence' for c in result.history['state_changes'])
    assert len(profile(result.state)['evidence'])==32


def test_archived_evidence_can_support_bounded_evaluation_but_not_cross_branch():
    from backend.runtime_v3.personality import history_query
    conn=db();base=setup();snap=base
    for n in range(36):
        r=run(snap['world_state']);snap=committed_snapshot(conn,snap,r)
        if n==2: old_refs=refs(snap['world_state'])
    assert not set(old_refs)&set(refs(snap['world_state']))
    read=lambda **kw:history_query(conn,snap['history_head'],**kw)
    r=run(snap['world_state'],change=delta(refs=old_refs),development_query=read)
    assert not r.warnings and profile(r.state)['items']['traits']['revision']==1
    sibling=lambda **kw:history_query(conn,base['history_head'],**kw)
    r=run(snap['world_state'],change=delta(refs=old_refs),development_query=sibling)
    assert profile(r.state)['items']['traits']['revision']==0


def test_multiple_events_same_turn_not_sustained_pattern_and_invalid_optional_is_local():
    s=setup()['world_state'];raw=payload(s,change=delta(refs=['e1','e2','e3']))
    source=raw['events'][0];evidence=raw['development_evidence'][0]
    raw['events']=[dict(source,id='e'+str(n)) for n in range(1,4)]
    raw['development_evidence']=[dict(evidence,id='e'+str(n),source_event_id='e'+str(n)) for n in range(1,4)]
    raw['personality_deltas'].append({'actor_id':'b','operations':'bad'})
    r=StateResolver(s,TEXT,TEXT).resolve(raw)
    assert profile(r.state)['items']==profile(s)['items']
    assert r.warnings
