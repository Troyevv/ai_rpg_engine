"""Deterministic StateResolver replay of Stage B Social/005 (#207)."""
import pytest
from backend.services.world_delta_errors import StructuralDeltaError

from backend.repositories.preparation import Repository
from backend.runtime_v3.resolver import StateResolver
from devtools.narrative_test_world import ACTOR_ID, load_fixture

VERA = 'qa_vera'
EVENT = 'event_8c1f2a4d7e9b3a51c2d0'
ACTION = 'Предлагаю вместе разобрать фотографии, не передавая оригинал карты.'
ASSENT = 'Вера одобрила совместный разбор фотографий.'


@pytest.fixture(scope='module')
def state(tmp_path_factory):
    repo = Repository(tmp_path_factory.mktemp('photo') / 'save.sqlite')
    return repo.get_snapshot(load_fixture(repo, 'knowledge')['save'])['world_state']


def photo_turn(state, narrative=ASSENT, *, action=ACTION, kind='proposal', status='resolved'):
    camera = state['camera']
    from runtime_v3_fixture import player_action
    raw = dict(
        final_scene=dict(location_id=camera['location_id'], elapsed_minutes=1,
                         present_character_ids=camera['present_character_ids']),
        events=[dict(id=EVENT, text=narrative, evidence=narrative, medium='conversation',
                     participants=[ACTOR_ID, VERA], witnesses=[ACTOR_ID, VERA],
                     player_assertion='completed_interaction', player_evidence=action)],
        continuity_beats=[dict(source_event_id=EVENT, actor_id=ACTOR_ID, target_ids=[VERA],
                               basis_ids=['qa_map'], kind=kind, status=status,
                               decision_actor_id=VERA, evidence=ASSENT)],
    )
    return player_action(raw, ACTOR_ID, [VERA], action, EVENT)


def test_stage_b_proposal_keeps_event_without_inventing_npc_decision(state):
    out = StateResolver(state, ASSENT, ACTION).resolve(photo_turn(state))
    event, = out.history['events']
    assert event['player_evidence'] == ACTION and event['text'] == ASSENT
    assert 'continuity' not in event
    assert any(w['code'] == 'continuity_npc_response_unconfirmed' for w in out.warnings)


def npc_reply(phase, evidence):
    return dict(actor_id=VERA, target_ids=[ACTOR_ID], source_event_id=EVENT, phase=phase,
                modality='speech', evidence=evidence)


@pytest.mark.parametrize(('action', 'kind', 'phase', 'status', 'text'), [
    (ACTION, 'proposal', 'accept', 'resolved', 'Вера кивает. «Давай, сейчас принесу альбом».'),
    (ACTION, 'proposal', 'refuse', 'rejected', 'Вера отодвигает альбом. «Сегодня не хочу».'),
    ('Спрашиваю Веру, где фотографии.', 'question', 'answer', 'resolved', '«В альбоме», — отвечает Вера.'),
])
def test_grounded_npc_response(state, action, kind, phase, status, text):
    raw = photo_turn(state, text, action=action, kind=kind, status=status)
    raw['scene_actions'] = [npc_reply(phase, text)]
    raw['continuity_beats'][0]['evidence'] = 'Не переносить в History лишние детали аннотации.'
    out = StateResolver(state, text, action).resolve(raw)
    event, = out.history['events']
    beat, = event['continuity']
    assert (beat['actor_id'], beat['decision_actor_id'], beat['status']) == (ACTOR_ID, VERA, status)
    assert beat['source_event_id'] == event['id'] and beat['evidence'] == text
    assert event['player_evidence'] == action and event['scene_action']['phase'] == phase
    assert out.state['knowledge'] == state['knowledge']


@pytest.mark.parametrize(('phase', 'kind', 'status'), [
    ('accept', 'proposal', 'resolved'), ('refuse', 'proposal', 'rejected'),
    ('answer', 'question', 'resolved'), ('end', 'decision', 'resolved'),
    ('redirect', 'decision', 'resolved'),
])
def test_response_cannot_borrow_evidence_from_another_event(state, phase, kind, status):
    silence = 'Вера молча листает альбом.'
    unrelated = 'Тимур отодвинул чашку.'
    raw = photo_turn(state, silence, kind=kind, status=status)
    if kind == 'decision':
        raw['continuity_beats'][0].update(actor_id=VERA, target_ids=[ACTOR_ID])
    raw['events'].append(dict(id='cup', text=unrelated, evidence=unrelated,
                              participants=['qa_timur'], witnesses=[ACTOR_ID]))
    raw['scene_actions'] = [npc_reply(phase, unrelated)]
    out = StateResolver(state, silence + ' ' + unrelated, ACTION).resolve(raw)

    source, other = out.history['events']
    assert source['player_evidence'] == ACTION and source['evidence'] == silence
    assert other['local_id'] == 'cup' and other['evidence'] == unrelated
    assert 'scene_action' not in source and 'continuity' not in source
    assert {(w['section'], w['code'], w['action']) for w in out.warnings} >= {
        ('scene_actions', 'initiative_response_unconfirmed', 'drop_record'),
        ('continuity_beats', 'continuity_npc_response_unconfirmed', 'drop_record'),
    }
    assert out.state['knowledge'] == state['knowledge']


def test_silence_event_survives_invented_assent(state):
    silence = 'Вера молча листает альбом.'
    raw = photo_turn(state, silence)
    raw['scene_actions'] = [npc_reply('accept', ASSENT)]
    out = StateResolver(state, silence, ACTION).resolve(raw)
    event, = out.history['events']
    assert event['text'] == silence and event['player_evidence'] == ACTION
    assert 'scene_action' not in event and 'continuity' not in event
    assert any(w['code'] == 'continuity_npc_response_unconfirmed' for w in out.warnings)


def test_response_uses_full_event_evidence_not_a_text_fragment(state):
    text = 'Вера перечитала слова «Я согласна» на обороте снимка и промолчала.'
    raw = photo_turn(state, text)
    raw['scene_actions'] = [npc_reply('accept', 'Я согласна')]
    out = StateResolver(state, text, ACTION).resolve(raw)
    event, = out.history['events']
    assert 'scene_action' not in event and 'continuity' not in event
    assert event['evidence'] == text


def test_response_can_reference_event_summary_with_normalized_typography(state):
    narrative = 'Вера придвинула стопку к Кириллу. «Давай смотреть».'
    summary = 'Вера сказала «да» и взяла фотографии.'
    raw = photo_turn(state, narrative)
    raw['events'][0]['evidence'] = summary
    raw['scene_actions'] = [npc_reply('accept', '  Вера сказала "да"   и взяла фотографии.')]
    out = StateResolver(state, narrative, ACTION).resolve(raw)
    event, = out.history['events']
    assert event['continuity'][0]['evidence'] == summary
    assert event['scene_action']['phase'] == 'accept'


@pytest.mark.parametrize(('event_change', 'reply_change', 'beat_change', 'warning'), [
    ({}, None, {'status': 'open'}, 'continuity_npc_response_unconfirmed'),
    ({}, {'phase': 'offer'}, {}, 'continuity_npc_response_unconfirmed'),
    ({}, {'phase': 'refuse'}, {}, 'continuity_npc_response_unconfirmed'),
    ({}, {'evidence': ''}, {}, 'continuity_npc_response_unconfirmed'),
    ({}, {'source_event_id': 'other'}, {}, 'continuity_npc_response_unconfirmed'),
    ({}, {'target_ids': []}, {}, 'continuity_npc_response_unconfirmed'),
    ({}, {}, {'target_ids': []}, 'continuity_npc_response_unconfirmed'),
    ({}, {}, {'decision_actor_id': 'qa_timur'}, 'continuity_beat_evidence'),
    ({}, {}, {'evidence': ' '}, 'continuity_player_interaction_unconfirmed'),
    ({'medium': 'message', 'author_id': VERA}, {}, {}, 'continuity_player_interaction_unconfirmed'),
    ({'player_assertion': ''}, {}, {'player_evidence': ACTION}, 'continuity_player_interaction_unconfirmed'),
])
def test_unconfirmed_response_drops_only_annotation(state, event_change, reply_change, beat_change, warning):
    text = ASSENT if reply_change is not None else 'Вера молча смотрит на часы.'
    raw = photo_turn(state, text)
    raw['events'][0].update(event_change)
    if reply_change is not None:
        raw['scene_actions'] = [dict(npc_reply('accept', text), **reply_change)]
    raw['continuity_beats'][0].update(beat_change)
    if 'author_id' in event_change:
        with pytest.raises(StructuralDeltaError) as exc:
            StateResolver(state, text, ACTION).resolve(raw)
        assert exc.value.code == 'player_action_event_mismatch'
        return
    out = StateResolver(state, text, ACTION).resolve(raw)
    event, = out.history['events']
    assert 'continuity' not in event and event['local_id'] == EVENT
    assert any(w['code'] == warning and w['action'] == 'drop_record' for w in out.warnings)
    assert out.state['knowledge'] == state['knowledge']


def test_no_reply_preserves_open_player_proposal(state):
    text = 'Вера листает альбом молча.'
    raw = photo_turn(state, text, status='open')
    del raw['continuity_beats'][0]['decision_actor_id']
    raw['continuity_beats'][0]['evidence'] = ACTION
    out = StateResolver(state, text, ACTION).resolve(raw)
    beat, = out.history['events'][0]['continuity']
    assert beat['status'] == 'open' and beat['decision_actor_id'] is None


def test_response_checks_responder_and_observer_knowledge(state):
    from copy import deepcopy
    from backend.runtime_v3.continuity import project
    from backend.runtime_v3.scope import ContextScope

    state = deepcopy(state)
    thread = state['threads']['qa_map']
    thread['discovered_by'] = [ACTOR_ID]
    raw = photo_turn(state)
    raw['scene_actions'] = [npc_reply('accept', ASSENT)]
    out = StateResolver(state, ASSENT, ACTION).resolve(raw)
    assert 'continuity' not in out.history['events'][0]
    assert any(w['code'] == 'continuity_basis_unavailable' for w in out.warnings)
    thread['discovered_by'].append(VERA)
    raw['events'][0]['witnesses'].append('qa_timur')
    out = StateResolver(state, ASSENT, ACTION).resolve(raw)
    assert out.history['events'][0]['continuity']
    for observer, visible in [(VERA, True), ('qa_timur', False)]:
        scope = ContextScope(observer, present_actor_ids={ACTOR_ID, VERA, 'qa_timur'})
        assert bool(project(out.state, scope, out.history)['recent_beats']) is visible
    assert out.state['knowledge'] == state['knowledge']


@pytest.mark.parametrize(('owner', 'phase', 'accepted'), [
    (VERA, 'accept', True), (VERA, None, False), (VERA, 'offer', False),
    ('qa_timur', 'accept', False), (None, None, False),
])
@pytest.mark.parametrize('decision_actor', [None, VERA])
def test_npc_owned_decision_requires_attributed_event(state, owner, phase, accepted, decision_actor):
    raw = photo_turn(state)
    event = raw['events'][0]
    event.pop('player_assertion')
    event.pop('player_evidence')
    event.pop('player_action_id')
    event.pop('actor_id')
    event.pop('target_ids')
    # This fixture now describes only the NPC decision, not a completed player
    # action with its source Event deliberately removed (#237).
    raw['player_agency']['actions'] = []
    raw['player_agency']['narrative_audit'] = []  # This control now describes only NPC decisions.
    event['participants'].append('qa_timur')
    if owner:
        event.update(medium='message', author_id=owner)
    if phase:
        raw['scene_actions'] = [npc_reply(phase, ASSENT)]
    raw['continuity_beats'][0].update(kind='decision', actor_id=VERA, decision_actor_id=decision_actor,
                                      target_ids=[ACTOR_ID])
    out = StateResolver(state, ASSENT, ACTION).resolve(raw)
    saved, = out.history['events']
    assert bool(saved.get('continuity')) is accepted
    if not accepted:
        assert any(w['code'] == 'continuity_npc_response_unconfirmed' for w in out.warnings)


def test_proposal_job_is_atomic_and_regenerates_from_the_original_branch(tmp_path):
    from copy import deepcopy
    from backend.runtime_v3.repository import read_history
    from runtime_v3_fixture import execute
    from test_narrative_test_world import CONFIG

    repo = Repository(tmp_path / 'lineage.sqlite')
    sid = load_fixture(repo, 'knowledge')['save']
    before = repo.get_snapshot(sid)
    turns = repo.list_turns(sid)
    revision = repo.get_save(sid)['revision']
    raw = photo_turn(before['world_state'])
    forged = deepcopy(raw)
    forged['continuity_beats'][0].update(actor_id=VERA, kind='decision', decision_actor_id=ACTOR_ID)
    job = repo.begin_job(sid, ACTION, 'turn', CONFIG)
    execute(repo, job, forged, ASSENT)
    assert repo.get_job(job)['status'] == 'error'
    assert repo.get_snapshot(sid) == before and repo.list_turns(sid) == turns
    assert repo.get_save(sid)['revision'] == revision

    repo.retry_job(job)
    execute(repo, job, raw, ASSENT)
    assert repo.get_job(job)['status'] == 'saved', repo.get_job(job)['error']
    assert repo.get_save(sid)['revision'] == revision + 1
    saved = repo.get_snapshot(sid)
    turn = repo.list_turns(sid)[-1]
    repo = Repository(repo.path)
    assert repo.get_snapshot(sid) == saved

    def photo_events(snapshot):
        with repo.connect() as db:
            history, _ = read_history(db, snapshot['history_head'])
        return [e for e in history['events'] if e.get('local_id') == EVENT]

    original, = photo_events(saved)
    assert original['player_evidence'] == ACTION and 'continuity' not in original
    refusal = 'Вера закрывает альбом. «В другой раз».'
    other = photo_turn(before['world_state'], refusal, status='rejected')
    other['scene_actions'] = [npc_reply('refuse', refusal)]
    regen = repo.begin_job(sid, '', 'regenerate', CONFIG)
    execute(repo, regen, other, refusal)
    assert repo.get_job(regen)['status'] == 'saved'
    sibling = repo.get_snapshot(sid)
    alternate, = photo_events(sibling)
    beat, = alternate['continuity']
    assert beat['source_event_id'] == alternate['id'] != original['id']
    assert beat['status'] == 'rejected' and beat['evidence'] == refusal
    repo.select_variant(sid, turn['id'], turn['active_variant_id'], repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid) == saved
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid) == before and not photo_events(before)
    assert photo_events(saved) == [original] and photo_events(sibling) == [alternate]
