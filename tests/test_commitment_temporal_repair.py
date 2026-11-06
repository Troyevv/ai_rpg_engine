"""Stage B #208, replayed through the production job and SQLite transaction."""
from copy import deepcopy
import json

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from backend.repositories.preparation import Repository
from backend.runtime_v3.models import TemporalValue
from backend.runtime_v3.raw import extraction_schema, prompt_schema
from devtools.narrative_test_world import ACTOR_ID, load_fixture
from runtime_v3_fixture import execute
from test_narrative_test_world import CONFIG, ordinary_job


@pytest.mark.parametrize('scenario', ['campaign', 'knowledge'])
@pytest.mark.parametrize('fix_shape', [False, True], ids=['repeated-error', 'corrected'])
def test_stage_b_repair(tmp_path, scenario, fix_shape):
    repo = Repository(tmp_path / 'stage-b.sqlite')
    sid = load_fixture(repo)['save']
    before = ordinary_job(repo, sid, 'start')
    turns = repo.list_turns(sid)
    campaign = scenario == 'campaign'
    clock, period = ('10:00', 'morning') if campaign else ('15:00', 'afternoon')
    player = 'Когда ты позвонишь Олегу?' if campaign else 'Когда ты хочешь встретиться?'
    narrative = ('Тимур отвечает: «Позвоню Олегу завтра в 10:00».' if campaign
                 else 'Вера предлагает Кириллу встретиться завтра в 15:00 и ждёт ответа.')
    actor = 'qa_timur' if campaign else 'qa_vera'
    participants = [actor, 'qa_oleg' if campaign else ACTOR_ID]
    source = 'event_13_timur_call_plan' if campaign else 'event_vera_offer'
    eid = 'sched_timur_call_oleg' if campaign else 'sched_vera_meeting'
    camera = before['world_state']['camera']
    raw = dict(final_scene=dict(location_id=camera['location_id'],
                                present_character_ids=camera['present_character_ids'], elapsed_minutes=1),
               events=[dict(id=source, text=narrative, participants=[ACTOR_ID, actor],
                            witnesses=[ACTOR_ID, actor], evidence=narrative)],
               scheduled_event_changes=[dict(id=eid, description=narrative, character_ids=participants,
                                             assertion='agreed', decision_actor_id=actor, source_event_id=source,
                                             temporal=dict(day_offset=1, time=clock, day_period=period), evidence=narrative)])
    repaired = deepcopy(raw)
    if fix_shape:
        del repaired['scheduled_event_changes'][0]['temporal']['day_period']
    jid = repo.begin_job(sid, player, 'turn', CONFIG)
    calls = execute(repo, jid, raw, narrative, repaired=repaired)
    assert [bool(call.get('response_format')) for call in calls] == [False, True, True]
    job = repo.get_job(jid)
    diagnostics = json.loads(job['repair_diagnostics_json'])
    expected = ['commitment_invalid']
    if not fix_shape:
        expected.append('commitment_invalid')
    elif not campaign:
        expected.append('controlled_actor_unsupported')
    assert [d['code'] for d in diagnostics] == expected
    repo = Repository(repo.path)
    if not (fix_shape and campaign):
        assert job['status'] == 'error'
        assert repo.get_snapshot(sid) == before
        assert repo.list_turns(sid) == turns
    else:
        assert job['status'] == 'saved', job['error']
        saved = repo.get_snapshot(sid)
        entry = saved['world_state']['scheduled_events'][eid]
        assert entry['temporal']['time'] == clock and entry['temporal']['day_offset'] == 1
        assert entry['temporal']['day_period'] is None
        assert entry['character_ids'] == participants and entry['evidence'] == narrative
        turn = repo.list_turns(sid)[-1]
        ordinary_job(repo, sid, 'regenerate')
        repo.select_variant(sid, turn['id'], turn['active_variant_id'], repo.get_save(sid)['revision'])
        assert repo.get_snapshot(sid) == saved
        repo.rollback_last(sid)
        assert repo.get_snapshot(sid) == before
    for d in diagnostics:
        if d['code'] == 'commitment_invalid':
            assert d['path'] == 'scheduled_event_changes[0].temporal'
            assert 'time and day_period are mutually exclusive' in d['repair_reason']
        else:
            assert d['evidence_field'] == 'player_assertion'
    feedback = calls[2]['messages'][0]['content']
    assert diagnostics[0]['path'] in feedback and diagnostics[0]['repair_reason'] in feedback
    assert json.dumps(raw['scheduled_event_changes'][0], ensure_ascii=False, separators=(',', ':')) in feedback


@pytest.fixture(scope='module')
def scheduled_schemas():
    validators = []
    for schema in (extraction_schema(), prompt_schema()):
        validators.append(Draft202012Validator({
            '$defs': schema.get('$defs', {}),
            'properties': {'scheduled_event_changes': schema['properties']['scheduled_event_changes']},
        }))
    return validators


@pytest.mark.parametrize('temporal, valid', [
    ({'date': '2026-11-07', 'time': '10:00'}, True),
    ({'weekday': 13, 'day_period': 'morning'}, True),
    ({'day_offset': -366}, True), ({'day_offset': 0}, True), ({'day_offset': 366}, True),
    ({'date': '2026-11-07', 'weekday': None, 'time': None, 'day_period': None}, True),
    ({'minute_offset': 0}, True), ({'minute_offset': 527040}, True),
    ({'day_offset': 1, 'time': '10:00', 'day_period': 'morning'}, False),
    ({'day_offset': 1, 'time': '25:00'}, False), ({'day_offset': 1, 'time': '9:05'}, False),
    ({'day_offset': 1, 'day_period': 'noon'}, False), ({'day_offset': 367}, False),
    ({'day_offset': -367}, False), ({'weekday': 14}, False), ({'minute_offset': -1}, False),
    ({'minute_offset': 1, 'time': '10:00'}, False), ({'minute_offset': 1, 'day_period': 'night'}, False),
    ({'minute_offset': 0, 'date': '2026-11-07'}, False), ({'weekday': 0, 'day_offset': 0}, False),
    ({'date': '2026-11-07', 'minute_offset': 0, 'time': '10:00'}, False),
    ({'day_offset': None}, False), ({'time': '15:00'}, False), ({}, False),
])
def test_temporal_contract_matches_runtime(temporal, valid, scheduled_schemas):
    if valid:
        TemporalValue.model_validate(temporal)
    else:
        with pytest.raises(ValidationError):
            TemporalValue.model_validate(temporal)
    for field in ('temporal', 'end_temporal'):
        payload = {'scheduled_event_changes': [
            {'id': 'plan', 'assertion': 'agreed', 'evidence': 'Plan', field: temporal},
        ]}
        for validator in scheduled_schemas:
            assert validator.is_valid(payload) == valid
