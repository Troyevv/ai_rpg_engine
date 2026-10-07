from copy import deepcopy
import json
import pytest
import numpy as np
from backend.runtime_v3.semantic import SemanticRetriever, Document, Retrieval
from backend.runtime_v3.scope import RelevanceResolver, CharacterContextClassifier
from backend.runtime_v3.resolver import StateResolver
from test_context_builder_v2 import clean_world, build, section


@pytest.fixture(autouse=True)
def structural_tests(monkeypatch):
    # Unit tests control retrieval explicitly; no downloaded model or network needed.
    monkeypatch.setenv('RPG_SEMANTIC_ENABLED', '0')


def yura_world():
    snapshot = clean_world()
    card = next(c for c in snapshot['character_cards'] if c['id'] == 'c')
    card.update(name='Юра Яковлев', aliases=['Юрий'])
    card['fields'].update({'Характер': 'Сухой и язвительный', 'Стиль общения': 'Короткие саркастичные фразы', 'Биография': 'DO_NOT_SEND_BIO'})
    snapshot['world_state']['characters']['c'].update(situation='PRIVATE_SITUATION', emotion='PRIVATE_EMOTION', physical_state='PRIVATE_PHYSICAL')
    return snapshot


def mode(snapshot, text, **kwargs):
    scope = RelevanceResolver().resolve(snapshot, text, **kwargs)
    return CharacterContextClassifier().classify('c', scope)


@pytest.mark.parametrize('text', ['Открыть сообщение Юры и прочитать его целиком.', 'Прослушать голосовое Юры.', 'Открыть письмо от Юры.', 'Вспомнить, что тогда сказал Юра.', 'Посмотреть запись, которую оставил Юра.'])
def test_explicit_authored_content(text):
    assert mode(yura_world(), text) == 'ACTIVE_REFERENCED'


def test_presence_and_remote_priority_and_mere_reference():
    s = yura_world()
    assert mode(s, 'Думаю о Юре.') == 'COMPACT_REFERENCED'
    assert mode(s, 'Интересно, где сейчас Юра.') == 'COMPACT_REFERENCED'
    assert mode(s, 'Пишу Юре: ты где?') == 'FULL_REMOTE'
    s['world_state']['camera']['remote_interactions'] = [dict(actor_id='c', channel='phone', last_active_turn=1000)]
    assert mode(s, 'Прочитать сообщение Юры.') == 'FULL_REMOTE'
    s['world_state']['camera']['present_character_ids'].append('c')
    assert mode(s, 'Прочитать сообщение Юры.') == 'FULL_PRESENT'


def test_two_turn_author_and_behavioral_identity_are_preserved():
    s = yura_world(); before = deepcopy(s)
    narrative = 'На экране появилось сообщение от Юры.'
    result = StateResolver(s['world_state'], narrative, 'Достать телефон и прочитать сообщение.').resolve(dict(
        final_scene=dict(location_id='kitchen',present_character_ids=['a','b']),
        events=[dict(id='incoming', text=narrative, evidence=narrative, participants=['a', 'c'], witnesses=['a'], medium='message', author_id='c')]))
    s['world_state'] = result.state
    history = result.history
    assert history['events'][0]['author_id'] == 'c'
    for text in ('Открыть сообщение Юры и прочитать его целиком.', 'Открыть сообщение и прочитать его.'):
        messages = build(s, text=text, history=history)
        actor = section(messages, 'Поведенческие профили / GM-only')[0]
        assert actor['id'] == 'c' and actor['name'] == 'Юра Яковлев'
        assert actor['personality'] == 'Сухой и язвительный'
        assert actor['communication_style'] == 'Короткие саркастичные фразы'
        assert 'DO_NOT_SEND_BIO' not in str(messages)
        assert 'PRIVATE_PHYSICAL' not in str(messages)
        assert messages.selection['characters']['ACTIVE_REFERENCED'] == 1
    assert s['world_state']['characters'] == before['world_state']['characters']
    assert not s['world_state']['camera']['remote_interactions']
    assert 'c' not in s['world_state']['camera']['present_character_ids']


def test_old_visible_message_compatibility_and_hidden_author_isolation():
    s = yura_world()
    assert mode(s, 'Открыть сообщение.', recent_views=[dict(assistant_text='Пришло сообщение от Юры.')]) == 'ACTIVE_REFERENCED'
    history = {'events': [dict(id='hidden',text='Сообщение',medium='message',author_id='c',participants=['c'],witnesses=['b'],turn_id=1000)]}
    assert mode(s, 'Открыть сообщение.', world_history=history) != 'ACTIVE_REFERENCED'


def test_different_authors_receive_different_profiles():
    s = yura_world()
    other = next(c for c in s['character_cards'] if c['id'] == 'npc_0')
    other.update(name='Анна', fields={'Роль':'Коллега', 'Характер':'Вежливая', 'Стиль общения':'Длинные формальные фразы'})
    a = section(build(s, text='Прочитать письмо Анны.'), 'Поведенческие профили / GM-only')[0]
    b = section(build(s, text='Прочитать письмо Юры.'), 'Поведенческие профили / GM-only')[0]
    assert a['communication_style'] != b['communication_style']
    assert a['personality'] != b['personality']


class FixedRetrieval:
    def search(self, docs, query):
        return Retrieval({('characters','c'): .91, ('facts','secret'): .83}, {'status':'ok'})


def test_semantic_is_relevance_only_and_knowledge_has_owners(monkeypatch):
    s = yura_world(); state = s['world_state']
    state['facts']['secret'] = dict(id='secret',text='Непохожая формулировка.',visibility='secret',character_ids=['a','c'])
    state['knowledge']['c:secret'] = dict(actor_id='c',fact_id='secret',status='known')
    before = deepcopy(s)
    scope = RelevanceResolver().resolve(s, 'Что было тогда?', semantic_retriever=FixedRetrieval())
    assert CharacterContextClassifier().classify('c', scope) == 'COMPACT_REFERENCED'
    from backend.runtime_v3.director import plan
    assert plan(s['world_state'], 'turn', scope=scope)['due_event_ids'] == []
    assert scope.fact_ids == ['secret']
    assert not scope.knowledge_ids  # merely mentioned actors do not dump knowledge
    monkeypatch.setattr('backend.runtime_v3.semantic.retrieve', lambda *args: FixedRetrieval().search([],''))
    messages = build(s, text='Прочитать сообщение Юры.')
    assert section(messages, 'Знания POV') == []
    assert section(messages, 'Знания действующих персонажей / GM-only') == [state['knowledge']['c:secret']]
    assert section(messages, 'Текущее состояние / GM-only')['knowledge'] == []
    assert str(messages).count('Непохожая формулировка.') == 1
    assert s == before
    assert all('semantic_similarity' not in m['content'] for m in messages)


def test_compact_runtime_and_soft_overflow_preserve_identity_index():
    s = yura_world()
    compact = build(s, text='Думаю о Юре.')
    assert section(compact, 'Текущее состояние / GM-only')['characters']['c'] == {'id':'c'}
    active = build(s, text='Прочитать сообщение Юры.', target_context_budget=1000)
    assert section(active, 'Индекс персонажей')
    assert section(active, 'Поведенческие профили / GM-only')[0]['communication_style']
    assert active.selection['target_exceeded']
    assert active.selection['character_included']['INDEX'] > 0
    with pytest.raises(ValueError, match='Критические данные'):
        from backend.runtime_v3.context import build_context
        build_context(s, [], 'Прочитать сообщение Юры.', 'turn', 1500, 1000)


def test_director_and_background_participation_are_not_presence():
    s = yura_world()
    s['_background_actor_ids'] = ['c']
    scope = RelevanceResolver().resolve(s, 'Фоновое действие.')
    assert scope.active_actor_ids == {'c'} and 'c' not in scope.present_actor_ids
    del s['_background_actor_ids']
    s['world_state']['scheduled_events']['call'] = dict(id='call',description='Входящее сообщение',character_ids=['c'],due_minute=600,status='pending',condition='',type='message',location_id='kitchen',interrupts=True)
    assert mode(s, 'Продолжить.') == 'ACTIVE_REFERENCED'


class Encoder:
    def __init__(self): self.calls=[]
    def encode(self, texts, **kwargs):
        self.calls.append(list(texts))
        return np.asarray([[1.,0.] if 'target' in t else [0.,1.] for t in texts])


def test_cache_updates_deletes_rollback_and_model_isolation():
    encoder = Encoder(); service = SemanticRetriever(encoder=encoder)
    docs=[Document('facts','a','target'), Document('facts','b','other')]
    cold=service.search(docs,'target'); warm=service.search(docs,'target')
    assert cold.diagnostics['rebuilt_embeddings']==2
    assert warm.diagnostics['cache_hits']==2 and warm.diagnostics['rebuilt_embeddings']==0
    changed=service.search([Document('facts','a','other')],'target')
    assert changed.diagnostics['rebuilt_embeddings']==1 and not changed.scores
    assert service.search([], 'target').scores == {}
    assert service.search(docs, 'target').scores == cold.scores
    assert len(encoder.calls)==6


def test_threshold_limits_ties_and_no_prompt_growth():
    service=SemanticRetriever(encoder=Encoder())
    small=service.search([Document('facts',f'f{i:05}', 'target') for i in range(100)], 'target')
    big=service.search([Document('facts',f'f{i:05}', 'target') for i in range(10000)], 'target')
    assert small.scores == big.scores and len(big.scores)==12
    assert service.search([Document('facts','negative','other')], 'target').scores=={}


def test_embedding_failure_is_visible_and_does_not_break_turn(monkeypatch):
    class Broken:
        def encode(self, *args, **kwargs): raise RuntimeError('private text must not leak')
    service=SemanticRetriever(encoder=Broken())
    result=service.search([Document('facts','f','text')], 'query')
    assert result.diagnostics['status']=='fallback'
    assert result.diagnostics['error']=='RuntimeError'
    monkeypatch.setattr('backend.runtime_v3.semantic.retrieve', lambda *args: result)
    messages=build(yura_world(), text='Прочитать сообщение Юры.')
    assert messages.selection['semantic']['status']=='fallback'
    assert 'private text' not in str(messages.selection)
    assert section(messages,'Поведенческие профили / GM-only')


def test_extraction_does_not_retrieve_or_send_behavior(monkeypatch):
    monkeypatch.setattr('backend.runtime_v3.semantic.retrieve', lambda *args: pytest.fail('unneeded retrieval'))
    messages=build(yura_world(),text='Открыть сообщение Юры.',extraction_text='Юра написал кратко.')
    assert messages.selection['semantic']['status']=='not_requested'
    assert 'Короткие саркастичные фразы' not in str(messages)
    assert not any(m['role']=='assistant' for m in messages)


def test_semantic_history_and_neighborhood_are_bounded():
    s=yura_world()
    history={'events':[dict(id='old',text='Совсем иные слова',participants=['c'],turn_id=1)]}
    class Search:
        def search(self, docs, query):
            return Retrieval({('history_events','old'):.9,('characters','c'):.9},{'status':'ok'})
    for i in range(100):
        s['world_state']['facts'][str(i)]=dict(id=str(i),text='Архивное сведение',visibility='secret',character_ids=['c'])
    scope=RelevanceResolver().resolve(s,'Тот самый давний случай',world_history=history,semantic_retriever=Search())
    assert scope.event_ids==['old']
    assert scope.fact_ids==[]  # semantic actor does not expand into all their facts
    assert scope.knowledge_ids==[]


def test_author_metadata_requires_message_participant():
    s=yura_world();quote='Юра оставил сообщение.'
    raw=dict(final_scene=dict(location_id='kitchen',present_character_ids=['a','b']),
        events=[dict(id='e',text=quote,evidence=quote,medium='message',participants=['a'],witnesses=['a'],author_id='c')])
    result=StateResolver(s['world_state'],quote,'').resolve(raw)
    assert 'author_id' not in result.history['events'][0]
    assert any(w.get('field')=='author_id' for w in result.warnings)


def test_e5_document_and_query_prefixes_even_single_document():
    encoder=Encoder()
    SemanticRetriever(model_name='intfloat/multilingual-e5-small',encoder=encoder).search([Document('facts','x','target')],'target')
    assert encoder.calls == [['passage: target'],['query: target']]


def test_directed_relationships_and_unknown_knowledge_survive_active_projection():
    s=yura_world();state=s['world_state']
    for source,target in [('a','c'),('c','a'),('c','npc_0')]:
        state['relationships'][source+':'+target]=dict(source_id=source,target_id=target,dimensions={},context='Связь')
    state['facts']['topic']=dict(id='topic',text='Поездка назначена на субботу.',visibility='secret',character_ids=['a','c'])
    state['knowledge']['c:topic']=dict(actor_id='c',fact_id='topic',status='unknown')
    messages=build(s,text='Прочитать сообщение Юры про поездку.')
    pairs={(r['source_id'],r['target_id']) for r in section(messages,'Текущее состояние / GM-only')['relationships']}
    assert pairs=={('a','c'),('c','a')}
    assert section(messages,'Знания действующих персонажей / GM-only')==[state['knowledge']['c:topic']]


def test_background_and_offscreen_actions_get_profile_without_presence():
    s=yura_world()
    assert mode(s,'Покажи, что делает Юра за кадром.')=='ACTIVE_REFERENCED'
    assert 'c' not in s['world_state']['camera']['present_character_ids']


def test_prompt_does_not_grow_with_100_1000_10000_semantic_facts(monkeypatch):
    from context_builder import estimate
    monkeypatch.setattr('backend.runtime_v3.semantic.retrieve', lambda *args: Retrieval(
        {('facts',f'f{i:05}'):.9 for i in range(12)}, {'status':'ok'}))
    sizes=[]
    for count in (100,1000,10000):
        s=yura_world()
        s['world_state']['facts']={f'f{i:05}':dict(id=f'f{i:05}',text='Архивная запись '+str(i),visibility='secret',character_ids=[]) for i in range(count)}
        messages=build(s,text='Продолжить.')
        sizes.append(estimate(messages))
        assert messages.selection['sections']['facts']['selected']==12
    assert len(set(sizes))==1


def test_trim_diagnostics_distinguish_selected_and_included(monkeypatch):
    s=yura_world()
    s['world_state']['facts']['secret']=dict(id='secret',text='Поддерживающая деталь',visibility='secret',character_ids=[])
    monkeypatch.setattr('backend.runtime_v3.semantic.retrieve', lambda *args: Retrieval({('facts','secret'):.8},{'status':'ok'}))
    messages=build(s,text='Прочитать сообщение Юры.',target_context_budget=1000)
    row=next(e for e in messages.selection['entities'] if e['entity_id']=='secret')
    assert row['selected'] and not row['included']
    assert row['selection_reasons']==['SEMANTIC']
    assert messages.selection['characters']['ACTIVE_REFERENCED']==messages.selection['character_included']['ACTIVE_REFERENCED']==1


def test_model_load_failure_uses_cooldown(monkeypatch):
    service=SemanticRetriever();calls=[]
    def unavailable():
        calls.append(1)
        raise OSError('model unavailable')
    monkeypatch.setattr(service,'_model',unavailable)
    for _ in range(2):
        assert service.search([Document('facts','f','text')],'query').diagnostics['status']=='fallback'
    assert calls==[1]


def test_semantic_schedule_does_not_indirectly_activate_actor():
    s = yura_world()
    s['world_state']['scheduled_events']['old'] = dict(id='old', description='Далёкое дело',
        character_ids=['c'], due_minute=0, status='pending', condition='', type='message',
        location_id=None, interrupts=False)
    class Search:
        def search(self, docs, query):
            return Retrieval({('scheduled_events', 'old'): .95, ('characters', 'c'): .95}, {'status': 'ok'})
    scope = RelevanceResolver().resolve(s, 'Продолжить.', semantic_retriever=Search())
    assert 'old' in scope.scheduled_event_ids
    assert CharacterContextClassifier().classify('c', scope) == 'COMPACT_REFERENCED'
    from backend.runtime_v3.director import plan
    assert plan(s['world_state'], 'turn', scope=scope)['due_event_ids'] == []


def test_semantic_match_does_not_erase_structural_history_relevance():
    s = yura_world()
    history = {'events': [dict(id='recent', text='Встреча закончилась.', participants=['a', 'c'], turn_id=1000)]}
    class Search:
        def search(self, docs, query):
            return Retrieval({('characters', 'c'): .95}, {'status': 'ok'})
    scope = RelevanceResolver().resolve(s, 'Продолжить.', world_history=history, semantic_retriever=Search())
    assert 'c' in scope.structural_actor_ids
