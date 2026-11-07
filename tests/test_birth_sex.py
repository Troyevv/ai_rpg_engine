"""#231 full job -> SQLite -> reload regressions with deterministic provider responses.

The fixtures explicitly encode Extraction's semantic interpretation; these tests
do not pretend a mock proves a real LLM can never misread arbitrary literature.
"""
from copy import deepcopy
import json

import pytest
from jsonschema import Draft202012Validator

from backend.repositories.preparation import Repository
from backend.runtime_v3.context import build_context
from backend.runtime_v3.raw import extraction_schema, prompt_schema
from backend.runtime_v3.repository import read_history
from birth_sex_fixture import CONFIG, REACTION, due_save, payload, execute


def history(repo, sid):
    with repo.connect() as db:
        return read_history(db, repo.get_snapshot(sid)['history_head'])[0]


def assert_atomic(repo, sid, before, turns, hist):
    assert repo.get_snapshot(sid) == before
    assert repo.list_turns(sid) == turns
    assert history(repo, sid) == hist
    assert Repository(repo.path).get_snapshot(sid) == before


@pytest.mark.parametrize('target', [0, 1], ids=['male', 'female'])
@pytest.mark.parametrize('wrong', [False, True], ids=['matching', 'contradictory'])
def test_narrative_canonical_matrix_sqlite(tmp_path, target, wrong):
    repo, sid = due_save(tmp_path/'matrix.sqlite', 'pregnancy-twins')
    before = repo.get_snapshot(sid)
    p, = before['world_state']['pregnancies'].values()
    sexes = [None, None]
    canonical = p['children'][target]['sex']
    sexes[target] = ('female' if canonical=='male' else 'male') if wrong else canonical
    narrative, raw = payload(before['world_state'], sexes=sexes)
    turns, hist = repo.list_turns(sid), history(repo, sid)
    job, calls = execute(repo, sid, narrative, raw)
    assert len(calls) == 2  # No unconditional reviewer or automatic reauthor call.
    if wrong:
        assert job['status'] == 'error'
        diagnostic = json.loads(job['repair_diagnostics_json'])[-1]
        assert diagnostic['code'] == 'birth_narrative_sex_conflict'
        assert diagnostic['action'] == 'reauthor_narrative'
        assert_atomic(repo, sid, before, turns, hist)
        return
    assert job['status'] == 'saved', job['error']
    after = Repository(repo.path).get_snapshot(sid)
    state = after['world_state']
    for i, child in enumerate(p['children']):
        cid, fid = child['id'], p['sex_fact_ids'][child['id']]
        assert state['characters'][cid]['biological_sex'] == child['sex']
        assert state['facts'][fid] == before['world_state']['facts'][fid]
        for actor in ('qa_vera', 'qa_kirill', 'qa_timur', 'qa_oleg'):
            known = state['knowledge'].get(actor+':'+fid)
            # The speaker's explicit direct observation is also a source of
            # Knowledge, even if Extraction listed only listeners in perceived_by.
            assert bool(known) == (i==target and actor in ('qa_vera','qa_kirill','qa_timur'))
            if known:
                event = next(e for e in history(repo, sid)['events'] if e['id']==known['source_event_id'])
                assert fid in event['fact_ids'] and actor in event['witnesses']
    assert repo.list_turns(sid)[-1]['assistant_text'] == narrative


def test_stage_c_original_missing_assessment_cannot_commit_or_survive_repair(tmp_path):
    repo, sid = due_save(tmp_path/'stage-c.sqlite')
    before = repo.get_snapshot(sid)
    narrative, raw = payload(before['world_state'], sexes=['female'])
    narrative = '— Есть, — коротко говорит врач. — Девочка.'
    raw['events'][0].update(text='Вера родила девочку дома.', evidence=narrative)
    raw['births'][0]['evidence'] = narrative
    del raw['births'][0]['sex_observations']
    turns, hist = repo.list_turns(sid), history(repo, sid)
    job, calls = execute(repo, sid, narrative, raw)
    assert job['status']=='error' and len(calls)==3  # Exactly one bounded structural repair.
    assert len(json.loads(job['repair_diagnostics_json']))==2
    assert_atomic(repo, sid, before, turns, hist)


def test_wrong_narrative_with_canonical_event_and_knowledge_delta_is_rejected(tmp_path):
    repo, sid = due_save(tmp_path/'laundering.sqlite')
    before = repo.get_snapshot(sid)
    p, = before['world_state']['pregnancies'].values()
    narrative, raw = payload(before['world_state'], sexes=['female'], event_sexes=['male'])
    fid = next(iter(p['sex_fact_ids'].values()))
    raw['events'][0]['fact_ids'] = [fid]
    raw['knowledge_gained'] = [dict(actor_id='qa_kirill', fact_id=fid, source_event_id='delivery')]
    turns, hist = repo.list_turns(sid), history(repo, sid)
    job, calls = execute(repo, sid, narrative, raw)
    assert job['status']=='error' and len(calls)==2
    assert_atomic(repo, sid, before, turns, hist)
    # A corrected JSON must not launder this same rejected text after reload.
    reloaded = Repository(repo.path)
    assert reloaded.public_job(reloaded.get_job(job['id']))['narrative_reauthor_required']
    with pytest.raises(ValueError, match='новую сцену'):
        reloaded.retry_job(job['id'], CONFIG)
    assert len(repo.request_log(job_id=job['id']))==2
    repo.abandon_job(sid, job['id'], job['revision'], job['attempt_epoch'])
    good_narrative, good = payload(before['world_state'])
    accepted, calls = execute(repo, sid, good_narrative, good)
    assert accepted['status']=='saved' and len(calls)==2
    assert all(t['assistant_text']!=narrative for t in repo.list_turns(sid))


@pytest.mark.parametrize('repeat', [False, True])
def test_correct_narrative_wrong_event_repaired_once(tmp_path, repeat):
    repo, sid = due_save(tmp_path/'repair.sqlite')
    before = repo.get_snapshot(sid)
    narrative, wrong = payload(before['world_state'], event_sexes=['female'])
    _, corrected = payload(before['world_state'])
    job, calls = execute(repo, sid, narrative, [wrong, wrong if repeat else corrected])
    assert len(calls)==3
    assert job['status']==('error' if repeat else 'saved'), job['error']
    diagnostics = json.loads(job['repair_diagnostics_json'])
    assert diagnostics[0]['code']=='birth_event_sex_conflict'
    if repeat:
        assert repo.get_snapshot(sid)==before
        assert len(diagnostics)==2
    else:
        assert repo.list_turns(sid)[-1]['assistant_text']==narrative
        assert all('Девочка' not in e['text'] for e in history(repo, sid)['events'])


def test_mistaken_semantic_reading_of_correct_prose_fails_closed(tmp_path):
    repo,sid=due_save(tmp_path/'misread.sqlite')
    before=repo.get_snapshot(sid)
    correct_text,_=payload(before['world_state'])
    _,misread=payload(before['world_state'],sexes=['female'])
    job,calls=execute(repo,sid,correct_text,misread)
    assert job['status']=='error' and len(calls)==2
    assert repo.get_snapshot(sid)==before
    assert repo.public_job(job)['narrative_reauthor_required']


@pytest.mark.parametrize('recipients', [[], ['qa_vera'], ['qa_vera','qa_kirill']])
def test_no_announcement_and_partial_perception(tmp_path, recipients):
    repo, sid = due_save(tmp_path/'witness.sqlite')
    before = repo.get_snapshot(sid)['world_state']
    p, = before['pregnancies'].values()
    narrative, raw = payload(before, sexes=['male' if recipients else None], recipients=recipients,
                             basis='observation')
    job, calls = execute(repo, sid, narrative, raw)
    assert job['status']=='saved', job['error']
    assert len(calls)==2
    state = Repository(repo.path).get_snapshot(sid)['world_state']
    fid = next(iter(p['sex_fact_ids'].values()))
    assert {k['actor_id'] for k in state['knowledge'].values() if k['fact_id']==fid} == set(recipients)


@pytest.mark.parametrize('invalid', ['absent', 'unconfirmed', 'speaker', 'knowledge', 'wrong_child'])
def test_provenance_rejections_are_atomic_and_bounded(tmp_path, invalid):
    repo, sid = due_save(tmp_path/'source.sqlite')
    before = repo.get_snapshot(sid)
    narrative, raw = payload(before['world_state'])
    row = raw['births'][0]['sex_observations'][0]
    if invalid=='absent': row['perceived_by'].append('qa_oleg')
    if invalid=='unconfirmed': row['source_assertion']='prior_knowledge'
    if invalid=='speaker': row['source_actor_id']='qa_oleg'
    if invalid=='wrong_child': row['child_id']='invented-child'
    if invalid=='knowledge':
        p, = before['world_state']['pregnancies'].values()
        fid = next(iter(p['sex_fact_ids'].values()))
        raw['events'][0]['fact_ids']=[fid]
        raw['knowledge_gained']=[dict(actor_id='qa_oleg', fact_id=fid, source_event_id='delivery')]
    turns, hist = repo.list_turns(sid), history(repo, sid)
    job, calls = execute(repo, sid, narrative, raw)
    assert job['status']=='error' and len(calls)==3
    assert_atomic(repo, sid, before, turns, hist)


def test_birth_disclosure_lineage_and_lta_continuation(tmp_path):
    repo, sid = due_save(tmp_path/'lineage.sqlite', 'pregnancy-twins')
    before = repo.get_snapshot(sid)
    narrative, raw = payload(before['world_state'])
    first, calls = execute(repo, sid, narrative, raw)
    assert first['status']=='saved', first['error']
    accepted = repo.get_snapshot(sid)
    original = repo.list_turns(sid)[-1]
    sibling, calls = execute(repo, sid, narrative, raw, kind='regenerate')
    assert sibling['status']=='saved', sibling['error']
    assert repo.get_snapshot(sid)['world_state']==accepted['world_state']
    repo.select_variant(sid, original['id'], original['active_variant_id'], repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==accepted
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==before
    undisclosed, other = payload(before['world_state'], sexes=[None,None])
    branch, _ = execute(repo, sid, undisclosed, other)
    assert branch['status']=='saved', branch['error']
    after = Repository(repo.path).get_snapshot(sid)
    p, = after['world_state']['pregnancies'].values()
    assert p['children']==next(iter(before['world_state']['pregnancies'].values()))['children']
    assert not any(k['fact_id'] in p['sex_fact_ids'].values() for k in after['world_state']['knowledge'].values())
    import engine
    jid=repo.begin_job(sid,'','long_term',dict(CONFIG,long_term_advance=dict(amount=2,unit='weeks',max_llm_calls=0)))
    engine.run_job(repo.path,jid,engine.Worker())
    assert repo.get_job(jid)['status']=='saved'
    final=repo.get_snapshot(sid)
    assert final['last_long_term_advance']['interruption'] is None
    assert final['world_state']['pregnancies'][p['id']]['children']==p['children']


def test_schema_resolves_nested_observations_and_requires_explicit_nulls(tmp_path):
    repo, sid = due_save(tmp_path/'schema.sqlite')
    _, raw = payload(repo.get_snapshot(sid)['world_state'])
    for schema in (extraction_schema(), prompt_schema()):
        validator = Draft202012Validator(schema)
        validator.validate(raw)
        missing = deepcopy(raw)
        del missing['births'][0]['sex_observations']
        assert list(validator.iter_errors(missing))


def test_author_constraint_is_not_pov_knowledge_or_early_disclosure(tmp_path):
    repo, sid = due_save(tmp_path/'context.sqlite')
    snapshot = repo.get_snapshot(sid)
    p, = snapshot['world_state']['pregnancies'].values()
    messages=build_context(snapshot,[],REACTION,'turn',65536,2000)
    author=[m for m in messages if m['content'].startswith('Birth authoring constraints / GM-only')]
    assert len(author)==1 and p['children'][0]['id'] in author[0]['content']
    for label in ('Знания POV', 'Знания действующих персонажей / GM-only', 'Текущее состояние / GM-only'):
        block=next(m['content'] for m in messages if m['content'].startswith(label))
        assert p['children'][0]['id'] not in block
    earlier=deepcopy(snapshot)
    earlier['world_state']['meta']['world_time']=p['due_minute']-1
    earlier['world_state']['pregnancies'][p['id']]['status']='active'
    early=build_context(earlier,[],REACTION,'turn',65536,2000)
    assert not any(m['content'].startswith('Birth authoring constraints') for m in early)
    assert repo.get_snapshot(sid)==snapshot


def test_prior_parent_knowledge_survives_birth_without_new_disclosure(tmp_path):
    from test_temporal_guard import run as ordinary
    repo, sid = due_save(tmp_path/'known.sqlite')
    state = repo.get_snapshot(sid)['world_state']
    p, = state['pregnancies'].values()
    fid = next(iter(p['sex_fact_ids'].values()))
    text = 'Тимур показывает результат обследования: мальчик. Кирилл и Вера читают результат.'
    job, _ = ordinary(repo,sid,0,text=text,config=CONFIG,extra=dict(
        events=[dict(id='exam',text=text,evidence=text,participants=['qa_vera','qa_timur'],
            witnesses=['qa_vera','qa_kirill'],fact_ids=[fid],medium='observation')],
        knowledge_gained=[dict(actor_id=actor,fact_id=fid,source_event_id='exam',evidence=text)
                          for actor in ('qa_vera','qa_kirill')]))
    assert job['status']=='saved',job['error']
    known = repo.get_snapshot(sid)['world_state']['knowledge']
    assert all(known[actor+':'+fid]['status']=='known' for actor in ('qa_vera','qa_kirill'))
    text, raw = payload(repo.get_snapshot(sid)['world_state'], sexes=[None])
    job, calls = execute(repo,sid,text,raw)
    assert job['status']=='saved' and len(calls)==2
    state = Repository(repo.path).get_snapshot(sid)['world_state']
    for actor in ('qa_vera','qa_kirill'):
        assert state['knowledge'][actor+':'+fid]==known[actor+':'+fid]
    assert 'qa_timur:'+fid not in state['knowledge']


def test_player_speculation_does_not_become_disclosure(tmp_path):
    repo,sid=due_save(tmp_path/'guess.sqlite')
    state=repo.get_snapshot(sid)['world_state']
    text,raw=payload(state,sexes=[None])
    text += ' Кирилл предполагает: «Наверное, девочка?» Врач пока не отвечает.'
    raw['events'][0]['text']='Вера родила; Кирилл лишь предполагает пол ребёнка.'
    job,calls=execute(repo,sid,text,raw)
    assert job['status']=='saved' and len(calls)==2
    after=repo.get_snapshot(sid)['world_state']
    p,=after['pregnancies'].values()
    assert not any(k['fact_id'] in p['sex_fact_ids'].values() for k in after['knowledge'].values())


def test_malformed_unrelated_knowledge_keeps_existing_local_handling(tmp_path):
    repo,sid=due_save(tmp_path/'malformed-knowledge.sqlite')
    text,raw=payload(repo.get_snapshot(sid)['world_state'])
    raw['knowledge_gained']=[dict(actor_id='qa_kirill', fact_id=[], source_event_id='delivery')]
    job,calls=execute(repo,sid,text,raw)
    assert job['status']=='saved',job['error']
    assert len(calls)==2
    assert 'knowledge_path_invalid' in job['warnings_json']


def test_remote_birth_discloses_only_to_local_observer(tmp_path):
    from test_temporal_guard import run as ordinary
    from test_due_scene import block, job as run_job
    repo,sid=due_save(tmp_path/'remote.sqlite')
    state=repo.get_snapshot(sid)['world_state']
    p,=state['pregnancies'].values()
    camera=state['camera']
    away=next(lid for lid in state['locations'] if lid!=camera['location_id'])
    moved,_=ordinary(repo,sid,0,text='Вера ушла в соседний дом.',config=CONFIG,extra=dict(
        movements=[dict(actor_id='qa_vera',to_location_id=away,evidence='Вера ушла.')],
        final_scene=dict(location_id=camera['location_id'],elapsed_minutes=0,
                         present_character_ids=[cid for cid in camera['present_character_ids'] if cid!='qa_vera'])))
    assert moved['status']=='saved', moved['error']
    def provider(**kwargs):
        messages=kwargs['messages']
        current=block(messages,'Текущее состояние / GM-only')
        private=block(messages,'Текущий ввод')['kind']=='background'
        if not kwargs.get('response_format'):
            author=[m for m in messages if m['content'].startswith('Birth authoring constraints')]
            assert bool(author)==private
            yield 'Вера родила и сама увидела: мальчик.' if private else 'Кирилл ждёт дома.'
            return
        cam=current['camera']
        raw=dict(final_scene=dict(location_id=cam['location_id'],present_character_ids=cam['present_character_ids'],elapsed_minutes=0))
        if private:
            text=block(messages,'completed_narrative')
            raw.update(events=[dict(id='birth',text=text,evidence=text,participants=['qa_vera'],
                witnesses=['qa_vera'],medium='observation')],births=[dict(pregnancy_id=p['id'],
                source_event_id='birth',assertion='birth_completed',location_id=away,evidence=text,
                sex_observations=[dict(child_id=p['children'][0]['id'],narrative_sex='male',event_sex='male',
                    basis='observation',perceived_by=['qa_vera'],evidence=text)])])
        yield json.dumps(raw,ensure_ascii=False)
    after,calls=run_job(repo,sid,'turn','Жду.',stream=provider)
    assert [c['stage'] for c in calls]==['narrative','extraction','world_simulation','world_simulation_delta']
    state=Repository(repo.path).get_snapshot(sid)['world_state']
    fid=next(iter(p['sex_fact_ids'].values()))
    assert {k['actor_id'] for k in state['knowledge'].values() if k['fact_id']==fid}=={'qa_vera'}
    event=next(e for e in history(repo,sid)['events'] if e['id']==state['knowledge']['qa_vera:'+fid]['source_event_id'])
    assert not event['player_observed']
    assert state['pregnancies'][p['id']]['status']=='born'
