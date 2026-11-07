"""#240 equivalent Family replay; real jobs/SQLite, deterministic model IO only.

The #239 raw archive was unpublished at implementation time. Semantic assessments
are provider fixtures, not proof that arbitrary free-form prose is always understood.
"""
from copy import deepcopy
import json

import pytest

from backend.repositories.preparation import Repository
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from birth_sex_fixture import due_save, execute, payload, CONFIG, REACTION
from test_birth_sex import history, assert_atomic
from test_due_scene import HELP, SIGNS, block


def ongoing(state, minutes=0, *, assessed=False):
    camera = state['camera']
    raw = dict(player_agency=dict(status='preserved', actions=[]),
        final_scene=dict(location_id=camera['location_id'],
            present_character_ids=camera['present_character_ids'], elapsed_minutes=minutes),
        events=[dict(id='labor', text=SIGNS, evidence=SIGNS, medium='observation',
                     participants=['qa_vera'], witnesses=camera['present_character_ids'])], births=[])
    if assessed:
        assess(raw, state, 'ongoing')
    return raw


def assess(raw, state, outcome, evidence=SIGNS):
    raw['final_scene']['due_birth_assessments'] = [dict(pregnancy_id=p['id'],
        narrative_outcome=outcome, evidence=evidence) for p in state['pregnancies'].values()
        if p['status'] != 'born' and p['due_minute'] <= state['meta']['world_time']]
    return raw


def family(path, checkpoint='pregnancy'):
    repo, sid = due_save(path, checkpoint)
    state = repo.get_snapshot(sid)['world_state']
    p, = state['pregnancies'].values()
    assert state['meta']['world_time'] == p['due_minute'] == 1980
    assert p['status'] == 'due'
    first, calls = execute(repo, sid, SIGNS, ongoing(state), player_input=HELP)
    assert first['status'] == 'saved', first['error']
    assert len(calls) == 2
    return repo, sid


def test_family_replay_repairs_two_to_zero_and_reloads(tmp_path):
    repo, sid = family(tmp_path/'replay.sqlite')
    before = repo.get_snapshot(sid)
    state = before['world_state']
    initial_turns = repo.list_turns(sid)
    bad, good = ongoing(state, 2), ongoing(state, assessed=True)
    with pytest.raises(StructuralDeltaError) as error:
        StateResolver(state, SIGNS, REACTION).resolve(bad)
    assert error.value.code == 'ordinary_temporal_boundary'
    assert error.value.repairable
    assert state == before['world_state']
    job, calls = execute(repo, sid, SIGNS, [bad, good])
    assert job['status'] == 'saved', job['error']
    assert len(calls) == 3
    logs = list(reversed(repo.request_log(job_id=job['id'])))
    assert [c['stage'] for c in logs] == ['narrative', 'extraction', 'extraction_repair']
    assert all(block(c['messages'], 'completed_narrative') == SIGNS for c in logs[1:])
    assert all('due_birth_assessments' in str(c['messages']) for c in logs[1:])
    diagnostic, = json.loads(job['repair_diagnostics_json'])
    detail = diagnostic['temporal_boundary']
    assert detail['world_time'] == 1980
    assert detail['max_minutes'] == 0 and detail['elapsed_minutes'] == 2
    assert detail['boundaries'][0]['due_minute'] == 1980
    assert detail['boundaries'][0]['kind'] == 'pregnancy_due'
    assert 'temporal_boundary' in str(logs[-1]['messages'])
    saved = Repository(repo.path).get_snapshot(sid)
    after = saved['world_state']
    assert after['meta']['world_time'] == 1980
    for key in ('pregnancies', 'knowledge', 'scheduled_events', 'characters', 'facts'):
        assert after[key] == state[key]
    assert len(repo.list_turns(sid)) == len(initial_turns) + 1
    assert repo.list_turns(sid)[:-1] == initial_turns
    assert len([e for e in history(repo,sid)['events'] if e['text']==SIGNS]) == 2
    assert not any(c.get('kind')=='birth' for c in history(repo,sid)['state_changes'])
    assert repo.list_turns(sid)[-1]['assistant_text'] == SIGNS


@pytest.mark.parametrize('repair', ['repeat', 'missing_assessment', 'invent_birth', 'crossing'])
def test_repair_failure_is_atomic_and_abandon_is_free(tmp_path, repair):
    repo, sid = family(tmp_path/'failure.sqlite')
    before = repo.get_snapshot(sid)
    state = before['world_state']
    bad = ongoing(state, 2)
    revised = ongoing(state, 2 if repair=='repeat' else 0, assessed=True)
    expected = 'ordinary_temporal_boundary'
    if repair == 'missing_assessment':
        revised['final_scene'].pop('due_birth_assessments')
        expected = 'due_birth_assessment_invalid'
    elif repair == 'invent_birth':
        _, revised = payload(state, sexes=[None])
        assess(revised, state, 'ongoing')
        expected = 'due_birth_assessment_invalid'
    elif repair == 'crossing':
        assess(revised, state, 'unresolved_time_advance', 'Прошло два часа, роды продолжаются.')
        expected = 'narrative_temporal_conflict'
    turns, hist = repo.list_turns(sid), history(repo, sid)
    job, calls = execute(repo, sid, SIGNS, [bad, revised])
    assert job['status'] == 'error' and len(calls) == 3
    assert json.loads(job['repair_diagnostics_json'])[-1]['code'] == expected
    assert len(json.loads(job['repair_diagnostics_json'])) == 2
    assert_atomic(repo, sid, before, turns, hist)
    count = len(repo.request_log(job_id=job['id']))
    if repair == 'crossing':
        public = repo.public_job(job)
        assert public['narrative_reauthor_required'] and not public['retry_allowed']
        with pytest.raises(ValueError, match='новую сцену'):
            repo.retry_job(job['id'], CONFIG)
    repo.abandon_job(sid, job['id'], repo.get_save(sid)['revision'], job['attempt_epoch'])
    assert len(repo.request_log(job_id=job['id'])) == count
    assert_atomic(Repository(repo.path), sid, before, turns, hist)


def test_crossing_narrative_cannot_be_laundered_by_zero_or_birth(tmp_path):
    repo, sid = family(tmp_path/'crossing.sqlite')
    before = repo.get_snapshot(sid)
    state = before['world_state']
    narrative = 'Прошло два часа, но роды всё ещё продолжаются.'
    raw = assess(ongoing(state, 0), state, 'unresolved_time_advance', narrative)
    job, calls = execute(repo, sid, narrative, [raw, ongoing(state, assessed=True)])
    assert job['status']=='error' and len(calls)==2
    assert repo.public_job(job)['narrative_reauthor_required']
    assert Repository(repo.path).get_snapshot(sid) == before


@pytest.mark.parametrize('checkpoint', ['pregnancy', 'pregnancy-twins'])
def test_repeated_repair_then_real_birth_preserves_children_and_lineage(tmp_path, checkpoint):
    repo, sid = family(tmp_path/'lineage.sqlite', checkpoint)
    before = repo.get_snapshot(sid)
    state = before['world_state']
    for _ in range(3):
        job, calls = execute(repo,sid,SIGNS,[ongoing(state,2),ongoing(state,assessed=True)])
        assert job['status']=='saved' and len(calls)==3
        state = Repository(repo.path).get_snapshot(sid)['world_state']
        assert state['meta']['world_time']==1980
        assert state['pregnancies']==before['world_state']['pregnancies']
    ongoing_snapshot = repo.get_snapshot(sid)
    p, = state['pregnancies'].values()
    narrative, birth = payload(state, sexes=[None]*len(p['children']))
    assess(birth, state, 'completed', narrative)
    job, calls = execute(repo,sid,narrative,birth)
    assert job['status']=='saved' and len(calls)==2
    born = repo.get_snapshot(sid)
    for ch in p['children']:
        assert born['world_state']['characters'][ch['id']]['biological_sex']==ch['sex']
        fid = p['sex_fact_ids'][ch['id']]
        assert not any(k['fact_id']==fid for k in born['world_state']['knowledge'].values())
    assert len([c for c in history(repo,sid)['state_changes'] if c.get('kind')=='birth'])==len(p['children'])
    turn = repo.list_turns(sid)[-1]
    sibling, calls = execute(repo,sid,narrative,birth,kind='regenerate')
    assert sibling['status']=='saved' and len(calls)==2
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==born
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==ongoing_snapshot
    branch, calls = execute(repo,sid,SIGNS,[ongoing(state,2),ongoing(state,assessed=True)])
    assert branch['status']=='saved' and len(calls)==3
    assert Repository(repo.path).get_snapshot(sid)['world_state']['pregnancies']==state['pregnancies']


@pytest.mark.parametrize('remote', [False, True])
@pytest.mark.parametrize('known', [False, True])
def test_known_hidden_local_remote_repair_does_not_grant_knowledge(tmp_path, remote, known):
    from test_temporal_guard import run as ordinary
    repo, sid = due_save(tmp_path/'knowledge.sqlite')
    state = repo.get_snapshot(sid)['world_state']
    p, = state['pregnancies'].values()
    if known:
        text = 'Вера подтвердила Кириллу беременность.'
        event = dict(id='known', text=text, evidence=text, medium='conversation',
            participants=['qa_vera','qa_kirill'], witnesses=['qa_kirill'], fact_ids=[p['fact_id']])
        result, _ = ordinary(repo,sid,0,text=text,config=CONFIG,extra=dict(events=[event],
            knowledge_gained=[dict(actor_id='qa_kirill',fact_id=p['fact_id'],source_event_id='known')]))
        assert result['status']=='saved',result['error']
    if remote:
        destination = next(lid for lid in state['locations'] if lid != state['camera']['location_id'])
        text = 'Вера перешла в другую комнату. Кирилл остался.'
        result, _ = ordinary(repo,sid,0,text=text,config=CONFIG,extra=dict(
            movements=[dict(actor_id='qa_vera',to_location_id=destination,evidence=text)],
            final_scene=dict(location_id=state['camera']['location_id'],elapsed_minutes=0,
                present_character_ids=[c for c in state['camera']['present_character_ids'] if c!='qa_vera'])))
        assert result['status']=='saved',result['error']
    before = repo.get_snapshot(sid)
    state = before['world_state']
    bad, good = ongoing(state,2), ongoing(state,assessed=True)
    narrative = 'Кирилл смотрит в окно.' if remote else SIGNS
    if remote:
        for raw in (bad,good):
            raw['events'] = []
        good['final_scene']['due_birth_assessments'][0]['evidence'] = narrative
    def background(**kw):
        from test_due_scene import provider, REMOTE_SIGNS
        if not kw.get('response_format'):
            yield REMOTE_SIGNS
        else:
            yield from provider(**kw)
    job, calls = execute(repo,sid,narrative,[bad,good],background_provider=background)
    assert job['status']=='saved', job['error']
    assert len(calls)==(5 if remote else 3)
    after = Repository(repo.path).get_snapshot(sid)['world_state']
    assert after['knowledge']==state['knowledge']
    assert after['pregnancies']==state['pregnancies']
    assert after['meta']['world_time']==1980
    narrative_context = str(calls[0]['messages'])
    assert ('Birth authoring constraints / GM-only' in narrative_context) != remote
    if not known and remote:
        assert p['id'] not in narrative_context
    for child in p['children']:
        assert child['id'] not in after['characters']


@pytest.mark.parametrize('legacy', [False, True])
def test_retry_retains_assessment_requirement_and_saved_narrative(tmp_path, legacy):
    repo,sid = family(tmp_path/'retry.sqlite')
    before=repo.get_snapshot(sid)
    state=before['world_state']
    failed,calls=execute(repo,sid,SIGNS,ongoing(state,2))
    assert failed['status']=='error' and len(calls)==3
    if legacy:
        # Model the old #240 persisted refusal, without rewriting any accepted turn.
        old = [dict(code='ordinary_temporal_boundary', action='regenerate',
                    stage='validation_failed', attempt=0, attempt_epoch=0)]
        with repo.connect() as db:
            db.execute('UPDATE game_jobs SET repair_diagnostics_json=? WHERE id=?',
                       (json.dumps(old), failed['id']))
    # Explicit retry is still bounded, reuses Narrative, and cannot omit assessment.
    failed,calls=execute(Repository(repo.path),sid,'MUST NOT BE GENERATED',ongoing(state),retry=failed['id'])
    assert failed['status']=='error' and len(calls)==2
    assert all(block(c['messages'],'completed_narrative')==SIGNS for c in calls)
    assert repo.get_snapshot(sid)==before
    saved,calls=execute(repo,sid,'MUST NOT BE GENERATED',ongoing(state,assessed=True),retry=failed['id'])
    assert saved['status']=='saved' and len(calls)==1
    assert repo.list_turns(sid)[-1]['assistant_text']==SIGNS


def test_repaired_regeneration_keeps_prior_variant_and_rollback(tmp_path):
    repo,sid=family(tmp_path/'regenerate.sqlite')
    before=repo.get_snapshot(sid)
    state=before['world_state']
    turn=repo.list_turns(sid)[-1]
    revised,calls=execute(repo,sid,SIGNS,[ongoing(state,2),ongoing(state,assessed=True)],kind='regenerate')
    assert revised['status']=='saved' and len(calls)==3
    assert len(repo.variants(turn['node_id']))==2
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert Repository(repo.path).get_snapshot(sid)==before


def test_assessment_schema_and_future_or_mixed_boundaries_are_strict(tmp_path):
    from jsonschema import Draft202012Validator
    from backend.runtime_v3.raw import extraction_schema, prompt_schema
    from backend.runtime_v3.models import ScheduledEvent
    repo,sid=due_save(tmp_path/'strict.sqlite')
    state=repo.get_snapshot(sid)['world_state']
    raw=ongoing(state,assessed=True)
    # Evidence is optional metadata in the existing schema; the semantic outcome is mandatory.
    raw['final_scene']['due_birth_assessments'][0].pop('evidence')
    assert StateResolver(state,SIGNS,REACTION,require_due_birth_assessment=True).resolve(raw).state['meta']['world_time']==1980
    for schema in (extraction_schema(),prompt_schema(player_agency_required=True)):
        Draft202012Validator(schema).validate(raw)
    # A coincident non-birth boundary does not acquire a birth-only repair.
    state['scheduled_events']['meeting']=ScheduledEvent(id='meeting',description='Встреча',
        character_ids=['qa_kirill'],due_minute=1980).model_dump()
    with pytest.raises(StructuralDeltaError) as error:
        StateResolver(state,SIGNS,REACTION).resolve(ongoing(state,2))
    assert error.value.code=='ordinary_temporal_boundary' and not error.value.repairable
    del state['scheduled_events']['meeting']
    state['meta']['world_time']=1979
    with pytest.raises(StructuralDeltaError) as error:
        StateResolver(state,SIGNS,REACTION).resolve(ongoing(state,2))
    assert error.value.code=='ordinary_temporal_boundary' and not error.value.repairable


def test_repair_can_extract_delivery_only_when_narrative_assessment_completed(tmp_path):
    repo,sid=family(tmp_path/'missing-birth.sqlite')
    state=repo.get_snapshot(sid)['world_state']
    narrative,good=payload(state,sexes=[None])
    bad=deepcopy(good)
    bad['births']=[]
    assess(good,state,'completed',narrative)
    saved,calls=execute(repo,sid,narrative,[bad,good])
    assert saved['status']=='saved',saved['error']
    assert len(calls)==3
    after=Repository(repo.path).get_snapshot(sid)['world_state']
    p,=after['pregnancies'].values()
    assert p['status']=='born' and p['birth_minute']==1980
    assert after['meta']['world_time']==1982
    assert repo.list_turns(sid)[-1]['assistant_text']==narrative
    assert sum(c.get('kind')=='birth' for c in history(repo,sid)['state_changes'])==1
