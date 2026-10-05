"""Semantic fixtures are Extraction outputs; Runtime tests provenance/invariants, not NLP."""
from copy import deepcopy
import pytest
from backend.runtime_v3.models import Motivation, Relationship
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.manual import edit_relationship
from backend.runtime_v3.raw import extraction_schema, prompt_schema
from backend.runtime_v3.context_contract import EXTRACTION_CONTRACT
from test_runtime_v3_domain import initial
from test_runtime_v3_storage import snapshot_fixture


def raw(**records):
    return dict(final_scene=dict(location_id='room', present_character_ids=['a','b']), **records)


@pytest.mark.parametrize('field,text,quote,status', [
    ('intentions','Поддеть Юру','Илья язвительно пошутил над Юрой.','completed'),
    ('goals','Поговорить с Соней','Они долго беседовали о конверте.','completed'),
    ('goals','Не дать обеду стать скучным','Обед закончился; гости разошлись.','expired'),
    ('intentions','Достать ключ','Ключ безвозвратно утонул.','failed'),
    ('obligations','Вернуть книгу','Илья вернул книгу.','completed'),
])
@pytest.mark.parametrize('actor',['a','b'])
def test_semantic_lifecycle_uses_ids_and_current_evidence(field,text,quote,status,actor):
    state=initial(); state['characters'][actor][field]=[Motivation(id='motivation', text=text).model_dump()]
    payload=raw(character_changes=[dict(id=actor, **{field+'_updates':[dict(id='motivation',status=status,evidence=quote)]})])
    result=StateResolver(state, quote, '').resolve(payload)
    assert result.state['characters'][actor][field][0]['status']==status
    assert result.state['characters'][actor][field][0]['evidence']==quote
    # Same quote in a previous scene is not current-turn evidence.
    rejected=StateResolver(state, 'Тишина.', '').resolve(payload)
    assert rejected.state['characters'][actor][field][0]['status']=='active'
    # Terminal records never reactivate or change to a different terminal state.
    payload['character_changes'][0][field+'_updates'][0]['status']='active'
    assert StateResolver(result.state,quote,'').resolve(payload).state['characters'][actor][field][0]['status']==status


def test_unknown_lifecycle_id_cannot_create_or_complete_and_new_player_desire_needs_input():
    payload=raw(character_changes=[dict(id='a', intentions_updates=[dict(id='missing',text='Уйти',status='active',evidence='Он посмотрел на дверь.')])])
    result=StateResolver(initial(),'Он посмотрел на дверь.','').resolve(payload)
    assert not result.state['characters']['a']['intentions']
    del payload['character_changes'][0]['intentions_updates'][0]['id']
    assert not StateResolver(initial(),'Он посмотрел на дверь.','').resolve(payload).state['characters']['a']['intentions']


@pytest.mark.parametrize('quote,value',[
    ('Внутри привычная горечь.','привычная горечь'),
    ('На душе тревожно.','тревожно'),
    ('Меня это бесит.','бесит'),
    ('Настроение в ноль.','настроение в ноль'),
    ('Чувствую себя опустошённым.','опустошённый'),
    ('Внутри какое-то стеклянное безвременье.','стеклянное безвременье'),
])
def test_open_emotion_vocabulary_is_player_sourced(quote,value):
    payload=raw(character_changes=[dict(id='a',emotion=value,emotion_assertion='explicit_internal_state',player_evidence={'emotion':quote})])
    state=initial()
    result=StateResolver(state,'Он вздохнул.',quote).resolve(payload)
    assert result.state['characters']['a']['emotion']==value
    assert 'emotion_assertion' not in result.state['characters']['a']
    assert StateResolver(state,quote,'Я смотрю на дверь.').resolve(payload).state['characters']['a']['emotion']==state['characters']['a']['emotion']


@pytest.mark.parametrize('text',['Сжимаю кулак.','Улыбаюсь.','Отвожу взгляд.','Вздыхаю.'])
def test_gesture_has_no_automatic_emotion(text):
    # Model omits emotion per contract. Even a bare inferred paraphrase without
    # semantic assertion is unsupported. There is no Runtime gesture→emotion map.
    state=initial()
    assert StateResolver(state,text,text).resolve(raw()).state['characters']['a']['emotion']==state['characters']['a']['emotion']
    payload=raw(character_changes=[dict(id='a',emotion='злится',player_evidence={'emotion':text})])
    assert StateResolver(state,text,text).resolve(payload).state['characters']['a']['emotion']==state['characters']['a']['emotion']


@pytest.mark.parametrize('text,evidence',[
    ('Соня сказала: «На душе тревожно».','На душе тревожно'),
    ('На душе тревожно?','На душе тревожно'),
    ('Если на душе тревожно, я ухожу.','Если на душе тревожно, я ухожу'),
    ('На душе было бы тревожно.','На душе было бы тревожно'),
])
def test_emotion_assertion_does_not_bypass_provenance(text,evidence):
    payload=raw(character_changes=[dict(id='a',emotion='тревожно',emotion_assertion='explicit_internal_state',player_evidence={'emotion':evidence})])
    assert not StateResolver(initial(),'',text).resolve(payload).state['characters']['a']['emotion']


@pytest.mark.parametrize('actor',['a','b'])
def test_physical_state_appears_changes_clears_and_requires_current_source(actor):
    state=initial()
    for quote, value in [('Он промок и замёрз.','промок и замёрз'),('Он согрелся у печки, одежда ещё мокрая.','промок'),('Одежда высохла.','')]:
        payload=raw(character_changes=[dict(id=actor,physical_state=value,evidence=quote)])
        result=StateResolver(state,quote,'').resolve(payload)
        assert result.state['characters'][actor]['physical_state']==value
        rejected=StateResolver(state,'Ничего не изменилось.','').resolve(payload)
        assert rejected.state['characters'][actor]['physical_state']==state['characters'][actor]['physical_state']
        state=result.state


@pytest.mark.parametrize('source,target',[('b','c'),('b','a'),('a','b')])
def test_relationship_all_directions_no_player_gate_and_no_mirroring(source,target):
    state=initial(); state['relationships']={}
    quote='Один спас другого из огня.'
    payload=raw(relationship_changes=[dict(source_id=source,target_id=target,dimensions={'trust':35},evidence=quote)])
    result=StateResolver(state,quote,'').resolve(payload)
    assert result.state['relationships'][source+':'+target]['dimensions']['trust']==35
    assert target+':'+source not in result.state['relationships']


def test_relationship_inertia_directed_dynamics_manual_baseline():
    snapshot=snapshot_fixture()
    snapshot=edit_relationship(snapshot,'a','b','Доверяет',{'trust':40.0})
    state=snapshot['world_state']; state['relationships']['b:a']=Relationship(source_id='b',target_id='a',dimensions={'trust':10.0}).model_dump()
    neutral=StateResolver(state,'Обменялись приветствиями.','').resolve(raw())
    assert neutral.state['relationships']==state['relationships']
    quote='Он поддержал друга в трудную минуту.'
    positive=StateResolver(state,quote,'').resolve(raw(relationship_changes=[dict(source_id='a',target_id='b',dimensions={'trust':42},evidence=quote)]))
    assert positive.state['relationships']['a:b']['dimensions']['trust']==42
    assert positive.state['relationships']['b:a']['dimensions']['trust']==10
    quote='Предательство вскрылось, оба поссорились.'
    result=StateResolver(positive.state,quote,'').resolve(raw(relationship_changes=[
        dict(source_id='a',target_id='b',dimensions={'trust':-20},evidence=quote),
        dict(source_id='b',target_id='a',dimensions={'irritation':30},evidence=quote)]))
    assert result.state['relationships']['a:b']['dimensions']['trust']==-20
    assert result.state['relationships']['b:a']['dimensions']=={'trust':10.0,'irritation':30}
    assert 'Нейтральный разговор' in EXTRACTION_CONTRACT and 'новые абсолютные значения' in EXTRACTION_CONTRACT


def test_compact_schema_has_identical_validation_rules():
    schema=prompt_schema()
    def expand(node):
        if isinstance(node,dict):
            if '$ref' in node: return expand(schema['$defs'][node['$ref'].split('/')[-1]])
            return {key:expand(value) for key,value in node.items() if key!='$defs' and not (key=='description' and isinstance(value,str))}
        if isinstance(node,list):return [expand(value) for value in node]
        return node
    assert expand(schema)==expand(extraction_schema())
