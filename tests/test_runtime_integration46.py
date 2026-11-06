"""Cross-domain acceptance on the #78 world, real API, jobs and SQLite."""
from copy import deepcopy
from unittest.mock import patch

import engine
from backend.repositories.preparation import Repository
from backend.runtime_v3.life import capabilities
from backend.runtime_v3.portraits import visual_age
from backend.runtime_v3.reproduction import known_birth
from backend.runtime_v3.long_term_calendar import target_minute
from devtools.narrative_test_world import ACTOR_ID, load_fixture
from runtime_v3_fixture import execute
from test_api import api
from test_narrative_test_world import CONFIG
from test_npc_review import promoted
from test_phone122 import execute as execute_messages
from test_runtime_v3_engine import raw_for


def turn(repo, sid, raw=None, text='Осматриваюсь.', *, kind='turn', narration='В комнате тихо.'):
    if raw is None:
        raw = raw_for(repo.get_snapshot(sid))
    job = repo.begin_job(sid, text, kind, CONFIG)
    execute(repo, job, raw, narration)
    assert repo.get_job(job)['status'] == 'saved', repo.get_job(job)['error']
    return repo.get_snapshot(sid)


def command(client, repo, sid, route, **body):
    response = client.post(f'/api/saves/{sid}/{route}', json={
        'revision': repo.get_save(sid)['revision'], **body,
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_j02_pending_recipient_commitment_and_knowledge(api):
    client, app = api
    repo = app.state.repository
    sid = load_fixture(repo, 'phone')['save']
    raw = promoted(repo.get_snapshot(sid))
    raw['final_scene']['observed_character_ids'] = ['qa_oleg']
    before = turn(repo, sid, raw, 'Я доверяю Ладе.', kind='start', narration='Лада пришла. Рассказала о мастерской.')
    assert 'new_npc' in before['world_state']['camera']['present_character_ids']
    assert before['world_state']['camera']['observed_character_ids'] == ['qa_oleg']
    assert 'qa_oleg' not in before['world_state']['camera']['present_character_ids']
    later = turn(repo, sid)
    review = later['pending_reviews']['new_npc']
    assert review['status'] == 'pending_review'
    assert 'new_npc' in {r['id'] for r in repo.get_save(sid)['state']['phone']['recipients']}
    with patch('engine.launch'):
        dispatched = command(client, repo, sid, 'phone/dispatch', config=CONFIG, command={
            'action': 'send', 'character_id': 'new_npc', 'content': 'Встретимся через два часа?',
            'operation_id': 'offer-to-pending',
        })
    jid = dispatched['job']['id']
    execute_messages(repo, jid)
    assert repo.get_job(jid)['status'] == 'saved', repo.get_job(jid)['error']
    state = repo.get_snapshot(sid)['world_state']
    plan = state['scheduled_events']['phone-meeting']
    assert set(plan['character_ids']) == {ACTOR_ID, 'new_npc'}
    assert set(plan['remote_source_ids']) <= state['remote_events'].keys()
    assert 'phone-meeting' not in repo.get_save(sid)['state']['world']['scheduled_events']
    reply = next(e for e in state['remote_events'].values() if e['sender_id'] == 'new_npc')
    command(client, repo, sid, 'phone', command={
        'action': 'read', 'event_id': reply['id'], 'operation_id': 'read-pending-npc',
    })
    day = repo.get_save(sid)['state']['world_clock']['projection']['date']
    calendar = client.get(f'/api/saves/{sid}/calendar', params={'start_date': day, 'end_date': day}).json()
    assert any(e['id'] == plan['id'] for e in calendar['scheduled']['items'])
    saved = Repository(repo.path).get_snapshot(sid)
    assert saved['pending_reviews']['new_npc'] == review
    assert saved['world_state']['knowledge'][ACTOR_ID + ':workshop'] == before['world_state']['knowledge'][ACTOR_ID + ':workshop']
    assert saved['world_state']['relationships'][ACTOR_ID + ':new_npc'] == before['world_state']['relationships'][ACTOR_ID + ':new_npc']


def test_j05_three_generations_succession_and_ordinary_continuation(api):
    client, app = api
    repo = app.state.repository
    sid = load_fixture(repo, 'newborn-family')['save']
    before = repo.get_snapshot(sid)['world_state']
    pregnancy, = before['pregnancies'].values()
    child = pregnancy['children'][0]['id']
    assert pregnancy['status'] == 'born'
    assert before['objective_relations']['qa_marriage']['status'] == 'active'
    graph = client.get(f'/api/saves/{sid}/genealogy', params={'root_id': child}).json()
    assert any(r['source_id'] == 'qa_nina' and r['target_id'] == child and r['generations'] == 2
               for r in graph['kinship'] if r['kind'] == 'ancestor')

    request = dict(amount=20, unit='years', max_llm_calls=0)
    jid = repo.begin_job(sid, '', 'long_term', dict(CONFIG, long_term_advance=request))
    engine.run_job(repo.path, jid, engine.Worker())
    assert repo.get_job(jid)['status'] == 'saved', repo.get_job(jid)['error']
    aged = Repository(repo.path).get_snapshot(sid)['world_state']
    assert aged['meta']['world_time'] == target_minute(before, 20, 'years')
    assert aged['characters'][child]['developmental_stage'] == 'adult'
    for key in ('birth_date', 'personality', 'birth_provenance'):
        assert aged['characters'][child][key] == before['characters'][child][key]
    for key in ('roles', 'residences', 'knowledge', 'relationships', 'objective_relations'):
        assert aged[key] == before[key]
    assert not capabilities(before, child)['can_act'] and capabilities(aged, child)['can_act']
    assert (visual_age(before, child), visual_age(aged, child)) == ('infant', 'young_adult')
    assert not repo.request_log(job_id=jid)
    command(client, repo, sid, 'protagonist', operation='permanent', actor_id=child, operation_id='choose-grown-child')
    active = turn(repo, sid)
    assert active['world_state']['camera']['controlled_actor_id'] == child
    assert child + ':qa_private_letter' not in active['world_state']['knowledge']
    text = 'Мой персонаж погибает.'
    raw = raw_for(active)
    raw['life_changes'] = [dict(id=child, life_status='dead', assertion='established', evidence=text,
                                player_assertion='explicit_choice', player_evidence=text)]
    dead = turn(repo, sid, raw, text, narration=text)
    assert dead['world_state']['meta']['protagonist_required']
    assert Repository(repo.path).get_snapshot(sid) == dead
    command(client, repo, sid, 'protagonist', operation='permanent', actor_id='qa_asya', operation_id='continue-as-asya')
    final = turn(repo, sid)
    assert final['world_state']['camera']['controlled_actor_id'] == 'qa_asya'
    assert final['world_state']['characters'][child]['life_status'] == 'dead'
    assert final['world_state']['pregnancies'][pregnancy['id']] == pregnancy
    assert known_birth(final['world_state'], child, ACTOR_ID)
    assert not known_birth(final['world_state'], child, 'qa_marina')


def test_hidden_birth_recipient_directory_and_command(api):
    client, app = api
    repo = app.state.repository
    sid = load_fixture(repo, 'newborn-family')['save']
    before = repo.get_snapshot(sid)['world_state']
    newborn = next(iter(before['pregnancies'].values()))['children'][0]['id']
    assert newborn in {r['id'] for r in repo.get_save(sid)['state']['phone']['recipients']}
    command(client, repo, sid, 'protagonist', operation='temporary', actor_id='qa_marina', operation_id='unwitnessed-birth')
    snapshot = repo.get_snapshot(sid)
    assert newborn not in {r['id'] for r in client.get(f'/api/saves/{sid}').json()['state']['phone']['recipients']}
    response = client.post(f'/api/saves/{sid}/phone', json={
        'revision': repo.get_save(sid)['revision'],
        'command': {'action': 'send', 'operation_id': 'unknown-birth-id', 'character_id': newborn, 'content': 'Привет.'},
    })
    assert response.status_code == 409 and repo.get_snapshot(sid) == snapshot


def test_j04_call_with_authored_hangup_death_and_succession(tmp_path):
    from test_call_continuity import connected
    repo, client, sid, call_id = connected(tmp_path)
    before = repo.get_snapshot(sid)
    assert before['world_state']['remote_events'][call_id]['status'] == 'answered'
    raw = raw_for(before)
    text = 'Мой персонаж умирает.'
    raw['life_changes'] = [dict(id=ACTOR_ID, life_status='dead', assertion='established', evidence=text,
                                player_assertion='explicit_choice', player_evidence=text)]
    raw['call_lifecycle_changes'] = [dict(call_id=call_id, actor_id='qa_vera',
                                          assertion='completed_end', evidence='Вера положила трубку.')]
    dead = turn(repo, sid, raw, text, narration='Вера положила трубку. Кирилл умер.')
    assert dead['world_state']['remote_events'][call_id]['status'] == 'ended'
    assert dead['world_state']['meta']['protagonist_required']
    assert Repository(repo.path).get_snapshot(sid) == dead
    command(client, repo, sid, 'protagonist', operation='permanent', actor_id='qa_vera', operation_id='after-call-death')
    continued = turn(repo, sid)
    assert continued['world_state']['camera']['controlled_actor_id'] == 'qa_vera'
    assert continued['world_state']['remote_events'][call_id] == dead['world_state']['remote_events'][call_id]


def test_j06_checkpoint_repair_retry_variants_and_archive(api):
    """Frozen before/context, two sibling outcomes, both still on disk after rollback."""
    client, app = api
    repo = app.state.repository
    sid = load_fixture(repo, 'newborn-family')['save']
    before = repo.get_snapshot(sid)
    raw = promoted(before)
    invalid = deepcopy(raw)
    invalid['final_scene']['location_id'] = 'missing-location'
    config = dict(CONFIG, context_length=65536)
    jid = repo.begin_job(sid, 'Я доверяю Ладе.', 'turn', config)
    execute(repo, jid, invalid, 'Лада пришла.')
    failed = repo.get_job(jid)
    assert failed['status'] == 'error'
    assert repo.get_snapshot(sid) == before
    attempts = repo.request_log(job_id=jid)
    assert [r['stage'] for r in attempts].count('extraction_repair') == 1

    with patch('engine.launch'):
        response = client.post(f'/api/jobs/{jid}/retry', json={'config': config})
    assert response.status_code == 200, response.text
    execute(repo, jid, raw, 'Лада пришла.')
    saved = repo.get_job(jid)
    assert saved['status'] == 'saved', saved['error']
    for key in ('context_json', 'before_json', 'narrative', 'user_text'):
        assert saved[key] == failed[key]
    accepted = repo.get_snapshot(sid)
    assert accepted['pending_reviews']['new_npc']['status'] == 'pending_review'
    original = repo.list_turns(sid)[-1]
    other = turn(repo, sid, raw_for(before), '', kind='regenerate')
    assert other['world_state']['pregnancies'] == before['world_state']['pregnancies']
    assert 'new_npc' not in other['world_state']['characters']
    assert ACTOR_ID + ':workshop' not in other['world_state']['knowledge']
    assert other['history_head'] != accepted['history_head']
    sibling = repo.list_turns(sid)[-1]['active_variant_id']

    def archives():
        with repo.connect() as db:
            variants = db.execute('SELECT id, payload, context_json FROM response_variants WHERE node_id=? ORDER BY id',
                                  (original['node_id'],)).fetchall()
            heads = db.execute('SELECT id, parent_id, payload_json FROM world_history_v3 WHERE id IN (?,?) ORDER BY id',
                               (accepted['history_head'], other['history_head'])).fetchall()
        return [tuple(row) for row in variants], [tuple(row) for row in heads]

    variants, heads = archives()
    assert {row[0] for row in variants} == {sibling, original['active_variant_id']}
    assert all(row[2] == saved['context_json'] for row in variants)
    assert len(heads) == 2 and all(row[1] == before['history_head'] for row in heads)
    repo = Repository(repo.path)
    repo.select_variant(sid, original['id'], original['active_variant_id'], repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid) == accepted
    repo.rollback_last(sid, repo.get_save(sid)['revision'])
    assert Repository(repo.path).get_snapshot(sid) == before
    assert archives() == (variants, heads)


def test_birth_cannot_commit_as_optional_warning(api):
    client, app = api
    repo = app.state.repository
    sid = load_fixture(repo, 'pregnancy-twins')['save']
    advance = repo.begin_job(sid, '', 'long_term', dict(CONFIG, long_term_advance={
        'amount': 2, 'unit': 'weeks', 'max_llm_calls': 0,
    }))
    engine.run_job(repo.path, advance, engine.Worker())
    assert repo.get_job(advance)['status'] == 'saved'
    before = repo.get_snapshot(sid)
    original_turns = repo.list_turns(sid)
    pregnancy, = before['world_state']['pregnancies'].values()
    child, twin = [c['id'] for c in pregnancy['children']]
    raw = raw_for(before)
    assert pregnancy['status'] == 'due'
    text = 'Вера родила близнецов. У первого ребёнка тёмные волосы.'
    raw['events'] = [dict(id='birth', text=text, participants=['qa_vera'], witnesses=['qa_vera'])]
    raw['births'] = [dict(pregnancy_id=pregnancy['id'], source_event_id='missing', assertion='birth_completed')]
    config = dict(CONFIG, context_length=65536)
    jid = repo.begin_job(sid, 'Я жду.', 'turn', config)
    execute(repo, jid, raw, text)
    failed = repo.get_job(jid)
    assert failed['status'] == 'error' and 'birth_claim_invalid' in failed['repair_diagnostics_json']
    assert repo.get_snapshot(sid) == before and repo.list_turns(sid) == original_turns
    assert len(repo.request_log(job_id=jid)) == 3

    raw['births'][0].update(source_event_id='birth', appearance={child: 'Тёмные волосы', twin: [], 'wrong-id': 'описание'})
    with patch('engine.launch'):
        retry = client.post(f'/api/jobs/{jid}/retry', json={'config': config})
    assert retry.status_code == 200, retry.text
    calls = execute(repo, jid, raw, text)
    saved = repo.get_job(jid)
    assert saved['status'] == 'saved', saved['error']
    assert len(calls) == 1 and calls[0]['response_format']
    assert 'birth_appearance_invalid' in saved['warnings_json']
    after = Repository(repo.path).get_snapshot(sid)
    assert after['world_state']['pregnancies'][pregnancy['id']]['status'] == 'born'
    assert after['world_state']['characters'][child]['appearance']['legacy_text'] == 'Тёмные волосы'
    assert set(after['world_state']['characters']) - before['world_state']['characters'].keys() == {child, twin}
