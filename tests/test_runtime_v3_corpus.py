"""Historical failure scenarios replayed as v3 inputs, not v2 mutation fallback."""
from pathlib import Path
from copy import deepcopy
import json
import pytest
from test_engine import db,CONFIG
from runtime_v3_fixture import setup_scenario,wire,execute
from backend.runtime_v3.models import assert_world_state_v3_invariants, identity

CORPUS=Path(__file__).parent/'fixtures'/'runtime_failures'
SCENE_CONFLICTS = {'10_final_scene_location_conflict', '11_multiple_movements'}


PLAYER='Прощаюсь и выхожу в коридор.'

def player_movement(raw, actor='character_1'):
    # Historical fixtures predate source-bound controlled movement. Replay the
    # authored player choice explicitly; no runtime inference from narrative.
    if actor not in raw['final_scene']['present_character_ids']: return
    target=raw['final_scene']['location_id']
    rows=[r for r in raw.get('movements',[]) if r.get('actor_id')==actor and r.get('to_location_id')==target]
    if not rows:
        raw.setdefault('movements',[]).append(dict(actor_id=actor,to_location_id=target))
        rows=[raw['movements'][-1]]
    for row in rows: row.update(player_assertion='explicit_choice',player_evidence=PLAYER)


@pytest.mark.parametrize('path',sorted(p for p in CORPUS.glob('*.json') if p.stem not in SCENE_CONFLICTS),ids=lambda p:p.stem)
def test_reconstructed_failure_corpus_commits_without_repair(db,path):
    repo,_,sid=db;fixture=json.loads(path.read_text())
    before=setup_scenario(repo,sid,fixture['initial'],observer=fixture['kind']=='background')
    raw=wire(fixture['payload'],fixture['narrative'],before)
    player_movement(raw,fixture.get('config',{}).get('actor_id','character_1'))
    # Background scenarios start from the supplied observer camera; no artificial
    # preceding turn is needed to test the same resolver and commit path.
    job=repo.begin_job(sid,PLAYER,'pov' if fixture['kind']=='pov' else 'start',dict(CONFIG,recent_turns=100,**fixture['config']))
    assert len(execute(repo,job,raw,fixture['narrative']))==2
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    state=repo.get_snapshot(sid)['world_state'];assert_world_state_v3_invariants(state)
    for cid,place in fixture['expected_positions'].items():
        assert state['locations'][state['characters'][cid]['location_id']]['name']==place
    assert not repo.turn_diagnostics(sid)[0]['repairs']


@pytest.mark.parametrize('path',sorted((Path(__file__).parent/'fixtures'/'turn_delta').glob('*.json')),ids=lambda p:p.stem)
def test_earlier_source_backed_scenarios_on_v3(db,path):
    repo,_,sid=db;fixture=json.loads(path.read_text());before=setup_scenario(repo,sid)
    raw=wire(fixture['payload'],fixture['narrative'],before)
    player_movement(raw,fixture.get('config',{}).get('actor_id','character_1'))
    job=repo.begin_job(sid,PLAYER,'start',CONFIG)
    assert len(execute(repo,job,raw,fixture['narrative']))==2
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    state=repo.get_snapshot(sid)['world_state'];assert_world_state_v3_invariants(state)
    assert state['locations'][state['characters']['character_1']['location_id']]['name']=='коридор'
    if path.stem=='missing_event_evidence':assert state['knowledge']['character_2:f']['source_event_id']


@pytest.mark.parametrize('name', sorted(SCENE_CONFLICTS))
def test_conflicting_scene_corpus_requires_repair_before_commit(db, name):
    repo, _, sid = db
    fixture = json.loads((CORPUS / (name + '.json')).read_text())
    before = setup_scenario(repo, sid, fixture['initial'])
    raw = wire(fixture['payload'], fixture['narrative'], before)
    for row in raw.get('movements', []):
        if row.get('actor_id')=='character_1':
            row.update(player_assertion='explicit_choice',player_evidence=PLAYER)
    # The old policy silently discarded these conflicting movements. #64
    # asks extraction to reconcile them; this mock repair follows the narrative.
    fixed = deepcopy(raw)
    fixed['final_scene']['location_id'] = identity('location', 'коридор')
    fixed['locations'] = []
    fixed['movements'] = [dict(actor_id='character_2',
        to_location_id=identity('location', 'ординаторская'), evidence=fixture['narrative'])]
    player_movement(fixed)
    job = repo.begin_job(sid, PLAYER, 'start', CONFIG)
    assert len(execute(repo, job, raw, fixture['narrative'], repaired=fixed)) == 3
    assert repo.get_job(job)['status'] == 'saved', repo.get_job(job)['error']
    state = repo.get_snapshot(sid)['world_state']
    assert_world_state_v3_invariants(state)
    assert state['characters']['character_1']['location_id'] == identity('location', 'коридор')
    assert state['characters']['character_2']['location_id'] == identity('location', 'ординаторская')
    repairs = repo.turn_diagnostics(sid)[0]['repairs']
    assert len(repairs) == 1
    assert repairs[0]['repair_error_code'] == 'scene_movement_conflict'
