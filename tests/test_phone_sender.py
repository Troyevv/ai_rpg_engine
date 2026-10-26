"""#121: authorized authors, distinct counterparties, unchanged stored events."""
from copy import deepcopy
import json
from test_remote_communication import phone, command, incoming
from backend.runtime_v3.remote import apply, projection
from backend.runtime_v3.protagonist import transition
from backend.runtime_v3.models import PortraitReference, WorldStateV3
from backend.runtime_v3.portraits import life_period


def portraits(s):
    for n, cid in enumerate(('a', 'b', 'child'), 1):
        s['world_state']['characters'][cid]['portraits'] = [PortraitReference(
            id=f'{n:032x}', asset_id=f'{n:032x}', width=300, height=400, stage=life_period(s["world_state"],cid)[1],
        ).model_dump()]
    return s


def test_outgoing_author_is_not_counterparty_and_projection_does_not_mutate():
    s = command(portraits(phone()), 'send', contact_id='a-b', content='Привет')
    before = deepcopy(s)
    row = projection(s)['events'][0]
    assert row['sender']['id'] == 'a'
    assert row['subject']['id'] == 'b'
    assert row['sender'] is not row['subject']
    assert row['sender']['portrait']['asset_id'] != row['subject']['portrait']['asset_id']
    assert s == before
    for card in s['character_cards']:
        card['name'] = 'Александр'
    for actor in s['world_state']['characters'].values():
        actor['display_name'] = 'Александр'
    for contact in s['world_state']['contacts'].values():
        contact['label'] = 'Александр'
    same_name = projection(s)['events'][0]
    assert same_name['sender']['name'] == same_name['subject']['name']
    assert same_name['sender']['portrait']['asset_id'] != same_name['subject']['portrait']['asset_id']
    # Legacy snapshots carry no derived sender projection; JSON round-trip is sufficient.
    assert projection(json.loads(json.dumps(s))) == projection(s)
    assert 'sender' not in next(iter(s['world_state']['remote_events'].values()))


def test_group_three_authors_and_temporary_owner():
    s = command(portraits(phone()), 'create_group', label='Трое', member_ids=['b','child'])
    gid = next(iter(s['world_state']['conversations']))
    for cid in ('a','b','child'):
        s, _ = apply(s, dict(action='send', operation_id='message-'+cid,
            conversation_id=gid, content='Сообщение '+cid), actor_id=cid, autonomous=cid!='a')
    assert [r['sender']['id'] for r in projection(s)['events']] == ['a','b','child']
    switched, _ = transition(s, 'temporary', 'b', 'switch')
    own = next(r for r in projection(switched)['events'] if r['outgoing'])
    assert own['sender']['id'] == 'b'
    assert own['sender']['portrait']['asset_id'] == f'{2:032x}'
    assert own['subject']['id'] != 'b'


def test_valid_hidden_identity_remains_in_canonical_state_but_not_sender():
    s = portraits(phone())
    s['world_state']['contacts']['a-b']['identity_visible'] = False
    s['world_state']['characters']['b']['biological_sex'] = 'female'
    s = incoming(s)
    validated = WorldStateV3.model_validate(s['world_state']).model_dump()
    assert validated['contacts']['a-b']['character_id'] == 'b'
    assert validated['characters']['b']['portraits']
    assert next(iter(validated['remote_events'].values()))['sender_id'] == 'b'
    s['world_state'] = validated
    row = projection(s)['events'][0]
    assert row['sender'] == dict(id='', name='Неизвестный участник', portrait=None, silhouette='neutral')
    assert 'sender_id' not in row
    assert row['content'] is None


def test_calls_keep_counterparties_both_directions():
    outgoing = command(portraits(phone()), 'call', contact_id='a-b')
    inbound = incoming(portraits(phone()), action='call')
    for s in (outgoing, inbound):
        before = deepcopy(s)
        row = projection(s)['events'][0]
        assert row['subject']['id'] == 'b'
        assert 'sender' not in row
        assert s == before


def test_real_api_upload_sender_branch_reload_and_rollback(tmp_path):
    from fastapi.testclient import TestClient
    from backend.api.app import create_app
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job
    from test_portraits import image
    app = create_app(tmp_path/'sender.sqlite', recover=False)
    repo = app.state.repository; client = TestClient(app)
    sid = load_fixture(repo, 'phone')['save']
    ordinary_job(repo, sid, 'start')
    for cid in ('qa_kirill', 'qa_vera'):
        response = client.post(f'/api/saves/{sid}/characters/{cid}/portraits',
            params={'revision':repo.get_save(sid)['revision']}, content=image(),
            headers={'content-type':'image/png'})
        assert response.status_code == 200
    response = client.post(f'/api/saves/{sid}/phone', json={
        'revision':repo.get_save(sid)['revision'], 'command':dict(action='send',
        operation_id='api-sender-message', contact_id='phone-qa_kirill-qa-vera', content='Сохрани автора.')})
    assert response.status_code == 200
    row = response.json()['state']['phone']['events'][0]
    assert row['sender']['id'] == 'qa_kirill' and row['subject']['id'] == 'qa_vera'
    assert row['sender']['portrait']['asset_id'] != row['subject']['portrait']['asset_id']
    snapshot = repo.get_snapshot(sid)
    events = deepcopy(snapshot['world_state']['remote_events'])
    branch = repo.create_save(repo.get_save(sid)['world_id'], 'branch')
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?', (json.dumps(snapshot), branch))
    reloaded = Repository(repo.path)
    assert reloaded.get_save(branch)['state']['phone']['events'][0]['sender'] == row['sender']
    # A copied canonical snapshot starts a sibling journal; the optional phone
    # planner returns silence, followed by the normal narrative/extraction pair.
    import engine
    from unittest.mock import patch
    from test_narrative_test_world import CONFIG, NARRATIVE
    camera = snapshot['world_state']['camera']
    def stream(**kwargs):
        if kwargs['messages'][0]['content'].startswith('Select at most ONE'):
            yield json.dumps({'action':None})
        elif kwargs.get('response_format'):
            yield json.dumps(dict(final_scene=dict(location_id=camera['location_id'],
                present_character_ids=camera['present_character_ids'],elapsed_minutes=1), choices=[]))
        else:
            yield NARRATIVE
    jid = reloaded.begin_job(branch, '', 'start', CONFIG)
    with patch('engine.find_loaded_model',return_value={'config':{'context_length':32768}}), patch('engine.chat_stream',side_effect=stream):
        engine.run_job(reloaded.path, jid, engine.Worker())
    assert reloaded.get_job(jid)['status'] == 'saved', reloaded.get_job(jid)['error']
    assert reloaded.get_snapshot(branch)['world_state']['remote_events'] == events
    original = reloaded.list_turns(branch)[-1]
    regenerated = reloaded.begin_job(branch, '', 'regenerate', CONFIG)
    with patch('engine.find_loaded_model',return_value={'config':{'context_length':32768}}), patch('engine.chat_stream',side_effect=stream):
        engine.run_job(reloaded.path, regenerated, engine.Worker())
    assert reloaded.get_job(regenerated)['status'] == 'saved'
    reloaded.select_variant(branch, original['id'], original['active_variant_id'], reloaded.get_save(branch)['revision'])
    assert reloaded.get_save(branch)['state']['phone']['events'][0]['sender'] == row['sender']
    reloaded.rollback_last(branch)
    assert reloaded.get_snapshot(branch)['world_state']['remote_events'] == events
    assert reloaded.get_save(branch)['state']['phone']['events'][0]['sender'] == row['sender']
    assert repo.get_snapshot(sid) == snapshot
