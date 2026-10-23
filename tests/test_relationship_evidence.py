"""QA-02 through Repository, engine jobs, Resolver and SQLite (no paid calls)."""
import json
import pytest
from copy import deepcopy
from unittest.mock import patch
import engine
from backend.repositories.preparation import Repository
from devtools.narrative_test_world import load_fixture
from test_narrative_test_world import CONFIG

A, B = 'qa_kirill', 'qa_vera'
LOVE = 'Кирилл чувствует безграничную любовь к Вере.'


def run(repo, sid, extra=None, *, player='Смотрю на карту.', narrative=LOVE, kind='turn'):
    camera = repo.get_snapshot(sid)['world_state']['camera']
    raw = dict(final_scene=dict(location_id=camera['location_id'],
        present_character_ids=camera['present_character_ids'], elapsed_minutes=0), **(extra or {}))
    job = repo.begin_job(sid, '' if kind == 'start' else player, kind, CONFIG)
    calls = []
    def stream(**kw):
        calls.append(kw)
        yield json.dumps(raw, ensure_ascii=False) if kw.get('response_format') else narrative
    with patch('engine.find_loaded_model', return_value={'config': {}}), patch('engine.chat_stream', side_effect=stream):
        engine.run_job(repo.path, job, engine.Worker())
    assert repo.get_job(job)['status'] == 'saved', repo.get_job(job)['error']
    assert len(calls) == 2
    return repo.get_snapshot(sid)


def test_external_feelings_require_player_evidence(tmp_path):
    repo = Repository(tmp_path/'feelings.sqlite')
    sid = load_fixture(repo, 'initiative')['save']
    run(repo, sid, kind='start', narrative='Тихо.')
    before = repo.get_snapshot(sid)
    change = dict(source_id=A, target_id=B, context='Кирилл влюблён.',
                  dimensions={'affection': 100, 'trust': 100}, evidence=LOVE)
    run(repo, sid, {'relationship_changes': [change]})
    assert Repository(repo.path).get_snapshot(sid)['world_state']['relationships'] == before['world_state']['relationships']
    assert any(w['code'] == 'relationship_evidence_required' for w in repo.turn_diagnostics(sid)[0]['warnings'])


def setup(tmp_path):
    repo = Repository(tmp_path/'relationships.sqlite')
    sid = load_fixture(repo, 'initiative')['save']
    run(repo, sid, kind='start', narrative='Тихо.')
    return repo, sid


def event(repo, sid, *, npc=False):
    text = 'Вера подробно объяснила Кириллу, как восстановить карту.' if npc else 'Помогаю Вере восстановить карту.'
    row = dict(id='help', text=text, participants=[A, B], witnesses=[A, B],
               fact_ids=[], medium='conversation' if npc else 'action', evidence=text)
    extra = {'events': [row]}
    if npc:
        extra['scene_actions'] = [dict(actor_id=B, target_ids=[A], source_event_id='help',
            phase='continue', modality='speech', response='none', evidence=text)]
    else:
        row.update(player_evidence=text, player_assertion='completed_interaction')
    snap = run(repo, sid, extra, player='Слушаю.' if npc else text, narrative=text)
    from backend.runtime_v3.repository import read_history
    with repo.connect() as db:
        history, _ = read_history(db, snap['history_head'])
    return history['events'][-1]['id']


def proposal(ids, value=72, source=A, target=B, **extra):
    return dict(source_id=source, target_id=target, dimensions={'trust': value},
        context='Доверие немного укрепилось после помощи.', assertion='grounded_feelings',
        source_event_ids=ids, rationale='Подтверждённая помощь укрепила доверие.', evidence='Помощь.', **extra)


def trust(snap, source=A, target=B):
    return snap['world_state']['relationships'][source+':'+target]['dimensions']['trust']


def test_series_canonical_interactions_all_directions_and_idempotency(tmp_path):
    repo, sid = setup(tmp_path)
    baseline = repo.get_snapshot(sid)
    e1 = event(repo, sid)
    e2 = event(repo, sid, npc=True)
    after = run(repo, sid, {'relationship_changes': [proposal([e1,e2])]})
    assert trust(after) == 72
    assert after['world_state']['relationships'][B+':'+A] == baseline['world_state']['relationships'][B+':'+A]
    # A consumed source cannot be reused, even with a fresh one in the same claim.
    assert trust(run(repo, sid, {'relationship_changes': [proposal([e1], 74)]})) == 72
    repo = Repository(repo.path)
    assert trust(run(repo, sid, {'relationship_changes': [proposal([e2], 74)]})) == 72
    # Independent reverse direction may use the same event once.
    assert trust(run(repo, sid, {'relationship_changes': [proposal([e2], 63, B, A)]}), B, A) == 63
    e3 = event(repo, sid, npc=True)
    assert trust(run(repo, sid, {'relationship_changes': [proposal([e3], 75)]})) == 75
    # Control switches do not confer/revoke feelings autonomy or copy knowledge.
    repo.switch_actor(sid, 'qa_timur', repo.get_save(sid)['revision'])
    e4 = event(repo, sid, npc=True)
    assert trust(run(repo, sid, {'relationship_changes': [proposal([e4], 78)]})) == 78
    assert repo.get_snapshot(sid)['world_state']['camera']['controlled_actor_id'] == 'qa_timur'


def test_override_priority_old_evidence_fence_and_new_event(tmp_path):
    repo, sid = setup(tmp_path)
    old = event(repo, sid)
    player = 'Я больше не доверяю Вере.'
    override = dict(source_id=A, target_id=B, dimensions={'trust': -40}, context='Не доверяет Вере.',
        player_assertion='explicit_directed_feelings', player_evidence=player, evidence=player)
    after = run(repo, sid, {'relationship_changes': [proposal([old]), override]}, player=player)
    assert trust(after) == -40
    assert trust(run(repo, sid, {'relationship_changes': [proposal([old], -37)]})) == -40
    new = event(repo, sid, npc=True)
    assert trust(run(repo, sid, {'relationship_changes': [proposal([new], -37)]})) == -37
    # UI/API uses the same history, including delete tombstones.
    unused = event(repo, sid)
    repo.update_relationship(sid, A, dict(target_id=B, context='Осторожное доверие.', dimensions={'trust': 20},
        delete=False, revision=repo.get_save(sid)['revision']))
    repo = Repository(repo.path)
    assert trust(run(repo, sid, {'relationship_changes': [proposal([unused], 23)]})) == 20
    newer = event(repo, sid, npc=True)
    assert trust(run(repo, sid, {'relationship_changes': [proposal([newer], 23)]})) == 23
    repo.update_relationship(sid, A, dict(target_id=B, context='', dimensions={},
        delete=True, revision=repo.get_save(sid)['revision']))
    assert A+':'+B not in run(repo, sid, {'relationship_changes': [proposal([newer], 3)]})['world_state']['relationships']


def test_regenerate_variants_rollback_and_sibling_branch(tmp_path):
    repo, sid = setup(tmp_path)
    eid = event(repo, sid)
    before = repo.get_snapshot(sid)
    change = {'relationship_changes': [proposal([eid])]}
    accepted = run(repo, sid, change)
    turn = repo.list_turns(sid)[-1]
    assert trust(run(repo, sid, change, kind='regenerate')) == 72
    repo.select_variant(sid, turn['id'], turn['active_variant_id'], repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid) == accepted
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before
    assert trust(run(repo, sid, change)) == 72
    # Create an event in an abandoned variant; it is not valid in its sibling.
    abandoned = event(repo, sid)
    run(repo, sid, kind='regenerate', narrative='Тихо.')
    assert trust(run(repo, sid, {'relationship_changes': [proposal([abandoned], 75)]})) == 72


@pytest.mark.parametrize('change', [
    dict(source_id=A, target_id=B, context='Безграничная любовь.', evidence=LOVE),
    dict(source_id=A, target_id=B, dimensions={'trust':100}, evidence=LOVE),
    proposal(['fabricated']),
    proposal(['help']),  # a current local Event cannot confirm its own narration
    dict(source_id=A, target_id=B, dimensions={'trust':100}, player_assertion='explicit_directed_feelings', player_evidence=LOVE, evidence=LOVE),
    dict(source_id=B, target_id=A, dimensions={'trust':100}, player_assertion='explicit_directed_feelings', player_evidence='Смотрю на карту.', evidence=LOVE),
    proposal([{}]),
    proposal(['duplicate','duplicate']),
    dict(source_id='missing', target_id=B, context='Любовь.', evidence=LOVE),
])
def test_invalid_optional_feelings_do_not_poison_turn(tmp_path, change):
    repo, sid = setup(tmp_path)
    before = repo.get_snapshot(sid)
    extra = dict(relationship_changes=[change], events=[dict(id='help', text=LOVE,
        participants=[A,B], witnesses=[A,B], medium='conversation', evidence=LOVE)],
        character_changes=[dict(id=B, situation='У стола.', evidence=LOVE)])
    after = run(repo, sid, extra)
    assert after['world_state']['relationships'] == before['world_state']['relationships']
    assert after['world_state']['characters'][B]['situation'] == 'У стола.'
    assert repo.turn_diagnostics(sid)[0]['warnings']


def test_large_jump_and_prose_event_laundering_rejected(tmp_path):
    repo, sid = setup(tmp_path)
    eid = event(repo, sid)
    before = repo.get_snapshot(sid)
    assert trust(run(repo, sid, {'relationship_changes':[proposal([eid],100)]})) == trust(before)
    assert any(w['code']=='relationship_step_exceeded' for w in repo.turn_diagnostics(sid)[0]['warnings'])
    run(repo, sid, {'events':[dict(id='love', text=LOVE, participants=[A,B], witnesses=[A,B], evidence=LOVE)]})
    from backend.runtime_v3.repository import read_history
    with repo.connect() as db:
        history, _ = read_history(db, repo.get_snapshot(sid)['history_head'])
    prose_id = history['events'][-1]['id']
    assert trust(run(repo, sid, {'relationship_changes':[proposal([prose_id],72)]})) == trust(before)
    # Rejected oversized proposal did not consume legitimate evidence.
    assert trust(run(repo, sid, {'relationship_changes':[proposal([eid],72)]})) == 72


def test_unchanged_override_still_fences_old_evidence_and_control_switch(tmp_path):
    repo, sid = setup(tmp_path)
    eid = event(repo, sid)
    player='Я по-прежнему доверяю Вере.'
    before=repo.get_snapshot(sid)['world_state']['relationships'][A+':'+B]
    override=dict(source_id=A,target_id=B,context=before['context'],dimensions=before['dimensions'],
                  player_assertion='explicit_directed_feelings',player_evidence=player,evidence=player)
    run(repo,sid,{'relationship_changes':[override]},player=player)
    assert trust(run(repo,sid,{'relationship_changes':[proposal([eid],72)]}))==70
    repo.switch_actor(sid,B,repo.get_save(sid)['revision'])
    # Old protagonist is no longer the owner of this input.
    assert trust(run(repo,sid,{'relationship_changes':[override]},player=player))==70
    new_player='Я не доверяю Кириллу.'
    other=dict(source_id=B,target_id=A,dimensions={'trust':-20},context='Недоверие.',
               player_assertion='explicit_directed_feelings',player_evidence=new_player,evidence=new_player)
    assert trust(run(repo,sid,{'relationship_changes':[other]},player=new_player),B,A)==-20


def test_receipts_survive_history_tail_and_context_contains_prior_ids(tmp_path):
    repo,sid=setup(tmp_path)
    eid=event(repo,sid,npc=True)
    from backend.runtime_v3.context import build_context
    from backend.runtime_v3.repository import read_history, append_history, relationship_reader
    before=repo.get_snapshot(sid)
    with repo.connect() as db:
        history,_=read_history(db,before['history_head'])
    messages=build_context(before,[],'Слушаю.','turn',32768,4096,extraction_text='Тихо.',world_history=history)
    current=json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('Текущее состояние / GM-only')))
    assert eid in [e['id'] for e in current['relationship_evidence']]
    run(repo,sid,{'relationship_changes':[proposal([eid])]})
    before=repo.get_snapshot(sid)
    # Archive depth does not expire a consumption receipt or resurrect evidence.
    with repo.connect() as db:
        for _ in range(70): before['history_head']=append_history(db,before['history_head'],{})
        db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(before),sid))
    assert relationship_reader(repo,before['history_head'])(A+':'+B,[eid])==[]
    assert trust(run(repo,sid,{'relationship_changes':[proposal([eid],75)]}))==72


@pytest.mark.parametrize('mode', ['turn', 'background'])
def test_shared_resolver_background_contract_and_pending_receipts(tmp_path, mode):
    from backend.runtime_v3.resolver import StateResolver
    from backend.runtime_v3.repository import relationship_reader
    repo,sid=setup(tmp_path)
    e1=event(repo,sid)
    e2=event(repo,sid,npc=True)
    before=repo.get_snapshot(sid)
    state=deepcopy(before['world_state'])
    if mode=='background':
        state['camera'].update(mode='observer',controlled_actor_id=None,present_character_ids=[B])
    raw=dict(final_scene=dict(location_id=state['camera']['location_id'],present_character_ids=state['camera']['present_character_ids']))
    query=relationship_reader(repo,before['history_head'])
    args=dict(mode=mode,protected_actor_id=A,relationship_query=query)
    first=StateResolver(state,LOVE,'',**args).resolve(dict(raw,relationship_changes=[proposal([e1],73)]))
    assert first.state['relationships'][A+':'+B]['dimensions']['trust']==73
    for ids,value in (([e1],74),([e2],78)):
        retry=StateResolver(first.state,LOVE,'',turn_id=first.state['meta']['turn_id'],
            relationship_receipts=first.history['relationship_changes'],**args).resolve(dict(raw,relationship_changes=[proposal(ids,value)]))
        assert retry.state['relationships']==first.state['relationships']
    if mode=='background':
        override=dict(source_id=A,target_id=B,dimensions={'trust':100},player_evidence=LOVE,
                      player_assertion='explicit_directed_feelings')
        blocked=StateResolver(state,LOVE,LOVE,**args).resolve(dict(raw,relationship_changes=[override]))
        assert blocked.state['relationships']==state['relationships']


def test_real_long_term_job_uses_same_evidence_reader_and_drops_narrative_only(tmp_path):
    from backend.runtime_v3.models import Thread
    from backend.runtime_v3.long_term import plan
    repo,sid=setup(tmp_path)
    eid=event(repo,sid,npc=True)
    before=repo.get_snapshot(sid)
    state=before['world_state']
    # Deterministic cause in the existing world, isolated from unrelated commitments.
    state['threads']={'qa_course':Thread(id='qa_course',description='Завершить обучение.',character_ids=[B],relevance=1).model_dump()}
    state['scheduled_events']={}
    state['camera']['present_character_ids']=[A]
    with repo.connect() as db: db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(before),sid))
    request=dict(amount=1,unit='years',max_llm_calls=2)
    candidates=plan(before,request).candidates
    cause=next(c for c in candidates if c.source_id=='qa_course')
    text='Вера завершила обучение.'
    raw=dict(final_scene=dict(location_id=state['camera']['location_id'],present_character_ids=[B],elapsed_minutes=0),
        events=[dict(id='completed',text=text,evidence=text,participants=[B],witnesses=[B],medium='observation',advance_candidate_ids=[cause.id])],
        relationship_changes=[proposal([eid],72),dict(source_id=B,target_id=A,dimensions={'trust':100},context='Безграничное доверие.',evidence=text)])
    calls=[]
    def stream(**kw):
        calls.append(kw)
        yield json.dumps(raw) if kw.get('response_format') else text
    job=repo.begin_job(sid,'','long_term',dict(CONFIG,long_term_advance=request))
    with patch('engine.chat_stream',side_effect=stream): engine.run_job(repo.path,job,engine.Worker())
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    after=Repository(repo.path).get_snapshot(sid)
    assert after['last_long_term_advance']['accepted'],after['last_long_term_advance']['diagnostics']
    assert len(calls)==2
    assert trust(after)==72
    assert trust(after,B,A)==60
    assert after['world_state']['characters'][A]['intentions']==before['world_state']['characters'][A]['intentions']


def test_extraction_repair_applies_evidence_once_and_override_regenerate(tmp_path):
    repo,sid=setup(tmp_path)
    eid=event(repo,sid)
    before=repo.get_snapshot(sid)
    camera=before['world_state']['camera']
    good=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=0),
              relationship_changes=[proposal([eid])])
    bad=deepcopy(good);bad['final_scene']['location_id']='missing'
    count=0
    def stream(**kw):
        nonlocal count
        if not kw.get('response_format'):
            yield 'Тихо.';return
        count+=1
        yield json.dumps(bad if count==1 else good)
    job=repo.begin_job(sid,'Смотрю на карту.','turn',CONFIG)
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,job,engine.Worker())
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    assert count==2 and trust(repo.get_snapshot(sid))==72
    repo.update_relationship(sid,A,dict(target_id=B,context='Осторожное доверие.',dimensions={'trust':10},delete=False,revision=repo.get_save(sid)['revision']))
    claim={'relationship_changes':[proposal([eid],13)]}
    assert trust(run(repo,sid,claim))==10
    assert trust(run(repo,sid,claim,kind='regenerate'))==10
    repo.rollback_last(sid)
    assert trust(repo.get_snapshot(sid))==10


def test_real_background_job_cannot_reuse_main_turn_evidence(tmp_path):
    from backend.runtime_v3.models import ScheduledEvent
    repo,sid=setup(tmp_path)
    eid=event(repo,sid,npc=True)
    before=repo.get_snapshot(sid);s=before['world_state']
    # Timur is off camera, with a due cause for the existing background scheduler.
    cid='qa_timur'
    s['camera']['present_character_ids'].remove(cid)
    s['characters'][cid]['location_id']=next(lid for lid in s['locations'] if lid!=s['camera']['location_id'])
    s['scheduled_events']['qa_background']=ScheduledEvent(id='qa_background',description='Разобрать снимки.',
        character_ids=[cid],due_minute=s['meta']['world_time']).model_dump()
    with repo.connect() as db:db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(before),sid))
    calls=[]
    def stream(**kw):
        calls.append(kw)
        if not kw.get('response_format'):
            yield 'Тихо.';return
        current=json.loads(next(m['content'].split('\n',1)[1] for m in kw['messages'] if m['content'].startswith('Текущее состояние / GM-only')))
        camera=current['camera'];hidden=camera['controlled_actor_id'] is None
        raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=0 if hidden else 1),
            relationship_changes=[proposal([eid],75 if hidden else 72)])
        yield json.dumps(raw)
    job=repo.begin_job(sid,'Рассматриваю карту.','turn',CONFIG)
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,job,engine.Worker())
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    assert len(calls)==4
    assert trust(Repository(repo.path).get_snapshot(sid))==72
    assert any(w['code']=='relationship_source_invalid' and w.get('stage')=='background_simulation'
               for w in repo.turn_diagnostics(sid)[0]['warnings'])
