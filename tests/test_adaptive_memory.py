import json
from threading import Event
from backend.services.memory_compactor import Compactor,output_budget
from context_builder import estimate
from test_engine import CONFIG


def test_large_source_and_old_summary_fit_small_context_without_source_truncation():
    calls=[];old='Предыдущие события. '*900
    source='Новые события беседы. '*1800
    def generate(messages):
        calls.append(json.loads(messages[1]['content']))
        assert estimate(messages)<=8192-output_budget({'context_length':8192})-256
        yield 'Краткая память.'
    compactor=Compactor('Обнови компактную память.',{**CONFIG,'context_length':8192},generate,Event())
    assert compactor.fold(old,[{'sequence':1,'player':'Реплика','narrator':source}],'actor_A')=='Краткая память.'
    assert len(calls)>2
    assert all(c['POV']=='actor_A' for c in calls)
    fragments=[t for c in calls for t in c['turns']]
    assert ''.join(t.get('previous_memory','') for t in fragments)==old
    assert ''.join(t.get('narrator','') for t in fragments)==source
    assert ''.join(t.get('player','') for t in fragments)=='Реплика'


def test_model_failure_reduces_batch_automatically():
    sizes=[]
    def generate(messages):
        data=json.loads(messages[1]['content']);sizes.append(len(data['turns']))
        yield 'X'*9000 if len(data['turns'])>1 else 'Краткая память.'
    compactor=Compactor('Правила',CONFIG,generate,Event())
    result=compactor.fold('',[{'sequence':i,'narrator':str(i)} for i in range(4)],'actor_A')
    assert result=='Краткая память.'
    assert 4 in sizes and 2 in sizes and 1 in sizes


def test_compactor_cache_is_scoped_to_actor():
    scopes=[]
    def generate(messages):
        scopes.append(json.loads(messages[1]['content'])['POV'])
        yield 'Память.'
    compactor=Compactor('Правила',CONFIG,generate,Event())
    for actor in ['A','A','B']:compactor.fold('',[{'narrator':'Событие'}],actor)
    assert scopes==['A','B']
