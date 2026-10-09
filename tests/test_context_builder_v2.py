import json
from copy import deepcopy
import pytest
from context_builder import build_context, describe_context, estimate
from backend.runtime_v3.scope import RelevanceResolver, CharacterContextClassifier
from backend.runtime_v3.models import Motivation, assert_world_state_v3_invariants
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.camera import transition, observe
from long_world_fixture import long_world


def section(messages, title):
    return json.loads(next(m['content'].split('\n', 1)[1] for m in messages if m['content'].startswith(title+'\n')))


def build(snapshot, turns=(), text='Что с конвертом?', history=None, **kwargs):
    return build_context(snapshot, list(turns), text, 'turn', 128000, 4000, world_history=history, **kwargs)


def clean_world():
    snapshot, _, _ = long_world()
    state = snapshot['world_state']
    for key in ('threads', 'facts', 'knowledge', 'relationships', 'scheduled_events'): state[key] = {}
    state['characters']['a']['goals'] = []
    return snapshot


def test_long_scene_isolation_projection_is_immutable():
    snapshot, turns, history = long_world(); before = deepcopy(snapshot)
    messages = build(snapshot, turns, history=history)
    current = section(messages, 'Текущее состояние / GM-only')
    assert set(current['locations']) == {'kitchen'}
    assert set(current['facts']) == {'letter'}
    assert {t['id'] for t in current['threads']} == {'letter_thread'}
    assert {e['id'] for e in current['scheduled_events']} == {'doorbell'}
    assert 'UNRELATED_SECRET_' not in str(messages)
    assert 'UNRELATED_WAREHOUSE_' not in str(messages)
    assert 'REL_npc_' not in str(messages)
    assert 'BIO_a' in str(messages) and 'BIO_b' in str(messages)
    assert 'VOICE_a' in str(messages) and 'VOICE_b' in str(messages)
    assert 'BIO_c' not in str(messages) and 'APPEARANCE_c' not in str(messages)
    assert snapshot == before
    assert_world_state_v3_invariants(snapshot['world_state'])
    selection = describe_context(messages)['selection']
    assert selection['characters']['FULL_PRESENT'] == 2
    assert selection['characters']['COMPACT_REFERENCED'] == 1
    assert selection['sections']['facts'] == {'selected':1, 'included':1, 'total':221}


def test_scope_remote_referenced_old_message_entry_and_decay():
    snapshot = clean_world(); resolver = RelevanceResolver(); classifier = CharacterContextClassifier()
    classify = lambda scope: classifier.classify('c', scope)
    assert classify(resolver.resolve(snapshot, 'Спрашиваю Тимура, что случилось с Соней.')) == 'COMPACT_REFERENCED'
    assert classify(resolver.resolve(snapshot, 'Перечитываю старое сообщение Сони.')) == 'ACTIVE_REFERENCED'
    assert classify(resolver.resolve(snapshot, 'Пишу Соне: привет.')) == 'FULL_REMOTE'
    assert classify(resolver.resolve(snapshot, 'Пишу Соне: «Привет, как ты?»')) == 'FULL_REMOTE'
    snapshot['world_state']['camera']['remote_interactions'] = [dict(actor_id='c', channel='message', last_active_turn=1000)]
    messages = build(snapshot, text='Продолжаем разговор.')
    assert 'VOICE_c' in str(messages)
    assert 'невидимые жесты' in str(messages)
    assert classify(resolver.resolve(snapshot, 'Продолжаем.')) == 'FULL_REMOTE'
    snapshot['world_state']['meta']['turn_id'] += 1
    assert classify(resolver.resolve(snapshot, 'Осматриваюсь.')) == 'INDEX'
    snapshot['world_state']['camera']['remote_interactions'] = []
    assert classify(resolver.resolve(snapshot, '', [{'assistant_text':'Соня вернётся позже.'}])) == 'COMPACT_REFERENCED'
    assert classify(resolver.resolve(snapshot, '', [{'assistant_text':'Соня вернётся позже.'}]+[{'assistant_text':'Тишина.'}]*3)) == 'INDEX'
    snapshot['world_state']['camera']['present_character_ids'].append('c')
    snapshot['world_state']['characters']['c']['location_id']='kitchen'
    assert classify(resolver.resolve(snapshot, '')) == 'FULL_PRESENT'


@pytest.mark.parametrize('text', ['Хочу позвонить Соне.', 'Если я пишу Соне, то спрашиваю про конверт.', 'Я звоню Соне?', 'Тимур сказал: «Пишу Соне».'])
def test_remote_requires_current_interaction(text):
    assert 'c' not in RelevanceResolver().resolve(clean_world(), text).remote_actor_ids


def test_remote_lifecycle_is_additive_and_clears_on_omission_and_pov():
    snapshot = clean_world(); state = snapshot['world_state']; quote='Соня ответила по телефону.'
    raw = dict(final_scene=dict(location_id='kitchen', present_character_ids=['a','b'], remote_interactions=[dict(actor_id='c',channel='phone',evidence=quote)]))
    result=StateResolver(state,quote,'').resolve(raw)
    assert result.state['camera']['remote_interactions'][0]['last_active_turn']==1001
    snapshot['world_state']=result.state
    assert transition(snapshot,'b')['world_state']['camera'].get('remote_interactions',[])==[]
    del raw['final_scene']['remote_interactions']
    result=StateResolver(result.state,'Тишина.','').resolve(raw)
    assert result.state['camera']['remote_interactions']==[]
    raw['final_scene']['remote_interactions']=[dict(actor_id='c',channel='phone',evidence=quote)]
    result=StateResolver(state,'Тишина.','').resolve(raw)
    assert result.state['camera']['remote_interactions']==[]


def test_continuity_is_protected_when_target_exceeded_and_extraction_is_isolated():
    snapshot, turns, history = long_world()
    messages = build(snapshot, turns, history=history, target_context_budget=1000)
    assert [m['content'] for m in messages if m['role']=='assistant'] == [t['assistant_text'] for t in turns]
    assert messages.selection['target_exceeded']
    extraction=build(snapshot, turns, history=history, extraction_text='Тимур ответил Илье про конверт.')
    assert not any(m['role']=='assistant' for m in extraction)
    assert 'BIO_a' not in str(extraction) and 'VOICE_b' not in str(extraction) and 'APPEARANCE_' not in str(extraction)
    assert 'Художественная сцена' not in str(extraction) and 'Драмеди' not in str(extraction)
    assert len(section(extraction,'Entity IDs')) < len(snapshot['character_cards'])
    # #39 adds optional transition schemas, not extra scene/biography context.
    # Compare selected context independently of the growing fixed wire schema.
    extraction_context=[m for m in extraction if not m['content'].startswith('JSON Schema\n')]
    assert estimate(extraction_context) < estimate(messages)
    assert estimate(extraction) < 18000  # Still fits the default soft target.
    with pytest.raises(ValueError, match='Критические данные'):
        build_context(snapshot, turns, 'Ввод остаётся целым', 'turn', 3000, 2500)


def test_scope_and_director_do_not_expand_with_unrelated_world():
    small, turns, history = long_world(1)
    big, _, big_history = long_world(4)
    first = build(small, turns, history=history)
    second = build(big, turns, history=big_history)
    for key in ('locations','facts','knowledge','relationships','threads','scheduled_events','history_events'):
        assert first.selection['sections'][key]['selected']==second.selection['sections'][key]['selected']
    # Only a bounded identity index changes. Full records never scale with unrelated world.
    assert estimate(second)-estimate(first) < 2000
    director = section(second, 'Director / GM-only')
    assert director['thread_ids']==['letter_thread']
    assert 'scheduled_0' not in director['due_event_ids']
    assert director['recent_event_ids']==['letter_event']


def test_no_gm_knowledge_becomes_pov_knowledge_and_legacy_does_not_duplicate():
    snapshot, _, history=long_world()
    del snapshot['world_state']['knowledge']['a:letter']
    snapshot['campaign']['sections']['knowledge']='- Конверт пришёл вчера; Соня просила сохранить его. | Знают: Тимур\nСоня хранит старую записку.'
    messages=build(snapshot, history=history)
    assert section(messages,'Знания POV')==[]
    legacy=section(messages,'Legacy knowledge / GM-only, ownership unknown')
    assert legacy==['Соня хранит старую записку.']
    assert 'letter' in section(messages,'Текущее состояние / GM-only')['facts']


def test_history_old_protagonist_participation_is_not_a_permanent_reason():
    snapshot=clean_world()
    history={'events':[dict(id='old',text='Прошлый поход',participants=['a'],location_id='loc_0',turn_id=1)]}
    scope=RelevanceResolver().resolve(snapshot,'Осматриваю кухню.',world_history=history)
    assert scope.event_ids==[]
    scope=RelevanceResolver().resolve(snapshot,'Вспоминаю прошлый поход.',world_history=history)
    assert scope.event_ids==['old']


@pytest.mark.parametrize('topic', ['Спор о конверте', 'Романтический разговор', 'Возвращаюсь к старой теме'])
def test_recent_subtext_and_identity_survive_long_world(topic):
    snapshot, turns, history=long_world()
    turns[0]['assistant_text']='Шесть сцен назад: «Я тебя не предам». '+topic
    messages=build(snapshot, turns, text=topic, history=history)
    assert turns[0]['assistant_text'] in [m['content'] for m in messages]
    assert 'VOICE_b' in str(messages) and 'BIO_b' in str(messages)


def test_pov_switch_filters_private_continuity_observer_and_background_stats():
    snapshot, turns, _=long_world()
    snapshot=transition(snapshot,'c')
    assert not any(m['role']=='assistant' for m in build(snapshot,turns))
    snapshot=observe(snapshot,'c')
    messages=build_context(snapshot,[], 'Соня ждёт.', 'background',128000,4000)
    assert messages.selection['mode']=='World Simulation Narrative'
    messages=build_context(snapshot,[], '', 'background',128000,4000,extraction_text='Соня ждёт.')
    assert messages.selection['mode']=='World Simulation Extraction'


def test_malformed_legacy_event_fact_ids_do_not_break_context_or_mutate_history():
    snapshot=clean_world()
    history={'events':[dict(id='event',text='Зашёл на кухню',participants=['a'],location_id='kitchen',turn_id=1000,fact_ids=[{'bad':'legacy'}])]}
    before=deepcopy(history)
    assert build(snapshot,history=history)
    assert history==before


def test_conversation_topic_retains_facts_and_imminent_arrival_references_actor():
    from backend.runtime_v3.models import Fact, ScheduledEvent
    snapshot=clean_world();state=snapshot['world_state']
    state['facts']['violin']=Fact(id='violin',text='Скрипка хранится в сейфе.').model_dump()
    state['scheduled_events']['arrival']=ScheduledEvent(id='arrival',description='Соня приходит',character_ids=['c'],location_id='kitchen',due_minute=601).model_dump()
    scope=RelevanceResolver().resolve(snapshot,'Продолжить.',[dict(assistant_text='Скрипка всё ещё цела?')])
    assert scope.fact_ids==['violin']
    assert CharacterContextClassifier().classify('c',scope)=='COMPACT_REFERENCED'


def test_completed_narrative_resolves_inflected_existing_location_before_extraction():
    snapshot=clean_world();state=snapshot['world_state']
    state['camera']['location_id']='loc_0'
    for cid in ('a','b'): state['characters'][cid]['location_id']='loc_0'
    messages=build(snapshot,text='Продолжить.',extraction_text='На кухне пахнет свежим кофе.')
    current=section(messages,'Текущее состояние / GM-only')
    assert 'kitchen' in current['locations']
    assert current['locations']['kitchen']==state['locations']['kitchen']
