import hashlib
import json
import threading
from copy import deepcopy
from unittest.mock import patch
import pytest
from llm import OutputLimitReached
from backend.services.draft_response import response, prefix_complete, join_fragments, TransportError, strict_loads
from backend.services import draft_repair


class JournalRepo:
    def __init__(self): self.journal={};self.progress='';self.phases=[]
    def save_response_journal(self,jid,journal): self.journal=deepcopy(journal)
    def preparation_progress(self,jid,text): self.progress=text
    def draft_phase(self,jid,phase): self.phases.append(phase)


CONFIG={'model':'local','provider':'local','max_tokens':512}
MESSAGES=[{'role':'system','content':'Return JSON'},{'role':'user','content':'idea'}]


def run(parts,**overrides):
    repo=JournalRepo();journal={};calls=[]
    def generate(messages,limit):
        calls.append(deepcopy(messages));text,reason=parts[len(calls)-1]
        yield text
        if reason=='length':raise OutputLimitReached()
    result=response(repo,'j',journal,'world',MESSAGES,dict(CONFIG,**overrides),32768,generate,threading.Event())
    return result,repo,journal,calls


@pytest.mark.parametrize('text,cut',[('{"s":"слово с \\" кавычкой"}',9),('{"a":[1,2,3]}',9),('{"a":{"b":true}}',10),('{"s":"\\u0410"}',10)])
def test_exact_continuation_inside_string_array_object_escape(text,cut):
    result,repo,journal,calls=run([(text[:cut],'length'),(text[cut:],'stop')])
    assert result==text and strict_loads(result)==json.loads(text)
    assert calls[1][-2]['content']==text[:cut]
    assert len(journal['responses']['world']['parts'])==2
    assert repo.progress==text


def test_five_fragments_and_no_extra_request():
    text='{"a":[1,2,3]}'
    parts=[(text[:6],'length'),(text[6:8],'length'),(text[8:10],'length'),(text[10:12],'length'),(text[12:],'stop')]
    assert run(parts)[0]==text
    with pytest.raises(TransportError,match='пяти'):
        run([('{"s":"','length')]+[('x','length')]*4)


def part(text,offset):return dict(text=text,offset=offset,sha256=hashlib.sha256(text.encode()).hexdigest())


def test_repetition_omission_integrity_order():
    first='{"s":"abcdefghijklmnopqrstuvwxyz'
    # A repeated substring within an open string is literal content, not evidence of overlap.
    assert join_fragments([part(first,0),part('abcdefghijklmnopqrstuvwxyz"}',len(first))])==first+'abcdefghijklmnopqrstuvwxyz"}'
    with pytest.raises(TransportError,match='Пропущен'):
        join_fragments([part('{"a":',0),part('1}',7)])
    broken=part('{"a":',0);broken['text']+='x'
    with pytest.raises(TransportError,match='целостность'):join_fragments([broken])
    with pytest.raises(TransportError):join_fragments([part('{"a":[1,',0),part(']}',8)])


@pytest.mark.parametrize('config,context,match',[
    ({'_draft_token_budget':1},32768,'бюджет токенов'),
    ({'_draft_cost_budget_usd':-1},32768,'бюджет расходов'),
    ({},600,'Контекст'),
])
def test_budget_and_context_fail_before_provider(config,context,match):
    with pytest.raises(TransportError,match=match):
        response(JournalRepo(),'j',{},'world',MESSAGES,dict(CONFIG,**config),context,
                 lambda *_:pytest.fail('provider must not run'),threading.Event())


def test_network_unknown_and_cancellation_are_never_replayed():
    repo=JournalRepo();journal={}
    def broken(*_):
        yield '{"a":"'
        raise OSError('offline')
    with pytest.raises(TransportError,match='исход неизвестен'):
        response(repo,'j',journal,'world',MESSAGES,CONFIG,32768,broken,threading.Event())
    assert repo.journal['pending']['text']=='{"a":"'
    with pytest.raises(TransportError,match='повтор запрещён'):
        response(repo,'j',journal,'world',MESSAGES,CONFIG,32768,lambda *_:pytest.fail(),threading.Event())
    event=threading.Event();journal={}
    def cancelled(*_):
        yield '{"a":"'
        event.set()
    assert response(repo,'j',journal,'world',MESSAGES,CONFIG,32768,cancelled,event) is None
    assert journal['pending'] and not journal['responses']['world']['complete']


def test_recover_committed_fragment_without_replaying():
    text='{"a":"hello'
    journal={'responses':{'world':{'parts':[dict(part(text,0),finish_reason='length')],'complete':False}},'pending':None}
    calls=[]
    def suffix(messages,limit):calls.append(messages);yield '"}'
    repo=JournalRepo()
    assert response(repo,'j',journal,'world',MESSAGES,CONFIG,32768,suffix,threading.Event())=='{"a":"hello"}'
    assert len(calls)==1 and calls[0][-2]['content']==text
    assert response(repo,'j',deepcopy(repo.journal),'world',MESSAGES,CONFIG,32768,lambda *_:pytest.fail(),threading.Event())=='{"a":"hello"}'


def test_terminal_json_duplicate_keys_and_syntax_not_guessed():
    with pytest.raises(ValueError,match='Повтор'):strict_loads('{"a":1,"a":2}')
    assert not prefix_complete('{"a":"unfinished')
    with pytest.raises(ValueError):strict_loads('{"a":"unfinished')
    with pytest.raises(TransportError):prefix_complete('{"a":1} garbage')


def test_technical_patch_preserves_all_other_content():
    raw=json.dumps({'characters':[{'name':'Илья','bio':'Не менять'}],'bad':999})
    request,paths=draft_repair.request(raw,[{'path':'/bad','message':'range'}])
    assert json.loads(request[-1]['content'])['fragments']=={'/bad':{'value':json.loads(raw)['bad']}}
    out=draft_repair.apply(raw,'{"patches":[{"path":"/bad","value":99}]}',paths)
    assert json.loads(out)['characters']==json.loads(raw)['characters']
    with pytest.raises(ValueError,match='неразрешённый'):
        draft_repair.apply(raw,'{"patches":[{"path":"/characters","value":[]}]}',paths)


def test_local_repair_context_keeps_unrelated_biographies_out_of_request():
    raw=json.dumps({'characters':[{'name':'Авторское имя','fields':{'bio':'Длинная биография.'*1000}}],
                    'world':{'knowledge':{'a/b':{'actor_id':'missing','fact_id':'f'}}}})
    errors=[{'path':'/world/knowledge/a~1b/actor_id','category':'reference','allowed':['a'],'message':'Unknown actor'}]
    messages,paths=draft_repair.request(raw,errors)
    payload=json.loads(messages[-1]['content'])
    from backend.repositories.drafts import candidate_hash
    assert payload.pop('candidate_hash')==candidate_hash(json.loads(raw))
    assert payload=={'errors':errors,'fragments':{'/world/knowledge/a~1b':{'value':{'actor_id':'missing','fact_id':'f'}}}}
    repaired=draft_repair.apply(raw,json.dumps({'patches':[{'path':paths[0],'value':'a'}]}),paths)
    assert json.loads(repaired)['characters']==json.loads(raw)['characters']


def test_missing_repair_field_is_explicit_without_sending_entire_world():
    messages,paths=draft_repair.request('{"world":{}}',[{'path':'/protagonist_id','message':'required'}])
    assert json.loads(messages[-1]['content'])['fragments']=={'/protagonist_id':{'missing':True}}
    assert json.loads(draft_repair.apply('{"world":{}}','{"patches":[{"path":"/protagonist_id","value":"a"}]}',paths))['protagonist_id']=='a'


def test_syntax_repair_preserves_literal_content():
    raw='{"a":"слово" "b":2}'
    assert json.loads(draft_repair.apply(raw,'{"a":"слово", "b":2}',None))['a']=='слово'
    with pytest.raises(ValueError,match='содержание'):
        draft_repair.apply(raw,'{"a":"другое", "b":2}',None)
