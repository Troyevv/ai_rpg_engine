from threading import Event
from unittest.mock import patch, MagicMock
from types import SimpleNamespace as NS
import pytest
from backend.services.continuation import stream_document, request_context
from backend.services.preparation import Preparation, Handle
from backend.repositories.preparation import Repository
from context_builder import estimate
from llm import OutputLimitReached, chat_stream
from test_engine import CONFIG
from test_worlds import summary


@pytest.mark.parametrize('kind',['idea','summary'])
@pytest.mark.parametrize('provider',['local','deepseek'])
def test_preparation_continues_until_complete_and_tracks_each_request(tmp_path,kind,provider):
    repo=Repository(tmp_path/'test.db');w=repo.create_workspace('Документ');wid=w['id']
    with repo.connect() as db:db.execute('UPDATE preparation_workspaces SET idea=? WHERE id=?',('Исходная идея',wid))
    text=summary() if kind=='summary' else '# План\nПервая часть.\nВторая часть.\nФинал.'
    pieces=[text[:len(text)//3],text[len(text)//3:2*len(text)//3],text[2*len(text)//3:]]
    calls=[]
    def generate(**kw):
        calls.append(kw)
        kw['on_usage']({'prompt_tokens':100,'completion_tokens':50,'prompt_cache_hit_tokens':0})
        yield pieces[len(calls)-1]
        if len(calls)<3:raise OutputLimitReached('length')
    config={**CONFIG,'provider':provider,'model':'deepseek-flash' if provider=='deepseek' else 'test'}
    jid=repo.begin_preparation(wid,kind,'Напиши',config,0)
    with patch('backend.services.preparation.chat_stream',side_effect=generate),patch('backend.services.preparation.find_loaded_model',return_value={'config':{'context_length':32768}}):
        Preparation(repo).run(jid,config,'test-key',Handle())
    job=repo.preparation_job(jid)
    assert job['status']=='saved',job['error']
    assert job['narrative']==text and repo.workspace(wid)[kind]==text
    assert calls[1]['messages'][-2]['content']==pieces[0]
    assert calls[2]['messages'][-2]['content']==pieces[0]+pieces[1]
    if kind=='summary':assert repo.workspace(wid)['summary_complete']
    with repo.connect() as db:
        rows=db.execute('SELECT status,input_tokens,output_tokens FROM llm_requests WHERE job_id=? ORDER BY rowid',(jid,)).fetchall()
        assert [r['status'] for r in rows]==['length','length','complete']
        assert sum(r['output_tokens'] for r in rows)==150


def test_long_generated_document_slides_context_without_truncating_output():
    source=[{'role':'system','content':'Исходные правила'},{'role':'user','content':'Полный шаблон и идея'}]
    text='Начало документа\n'+'Большой текст. '*5000+'ХВОСТ'
    messages,limit=request_context(source,text,8192,2000)
    assert messages[:2]==source
    assert messages[-2]['content'].endswith('ХВОСТ')
    assert len(messages[-2]['content'])<len(text)
    assert estimate(messages)+limit+512<=8192


def test_no_artificial_continuation_count_limit_and_cancel():
    cancel=Event();calls=[]
    def generate(messages,limit):
        calls.append(messages)
        yield f'Часть {len(calls)}\n'
        if len(calls)==12:cancel.set()
        raise OutputLimitReached('length')
    text=''.join(stream_document([{'role':'user','content':'Документ'}],8192,512,generate,cancel))
    assert len(calls)==12 and text.endswith('Часть 12\n')


def test_transport_failure_is_not_silently_marked_complete_or_retried():
    calls=[]
    def generate(messages,limit):
        calls.append(messages);yield 'Черновик'
        raise RuntimeError('connection lost')
    stream=stream_document([{'role':'user','content':'Документ'}],8192,512,generate,Event())
    assert next(stream)=='Черновик'
    with pytest.raises(RuntimeError,match='connection lost'):next(stream)
    assert len(calls)==1


def test_thinking_without_text_increases_request_budget():
    limits=[]
    def generate(messages,limit):
        limits.append(limit)
        if len(limits)==1:raise OutputLimitReached('length')
        yield 'Готово'
    assert ''.join(stream_document([{'role':'user','content':'Документ'}],8192,512,generate,Event()))=='Готово'
    assert limits==[512,1024]


def test_stopped_draft_preserves_unflushed_tail(tmp_path):
    repo=Repository(tmp_path/'test.db');w=repo.create_workspace('Документ')
    config={**CONFIG,'provider':'local'}
    jid=repo.begin_preparation(w['id'],'idea','Напиши',config,0)
    repo.preparation_progress(jid,'Часть','stopped')
    revision=repo.workspace(w['id'])['revision']
    repo.preparation_progress(jid,'Часть и последний фрагмент','stopped')
    assert repo.preparation_job(jid)['narrative']=='Часть и последний фрагмент'
    assert repo.workspace(w['id'])['revision']==revision


@pytest.mark.parametrize('reason,expected',[('length',OutputLimitReached),(None,RuntimeError),('content_filter',RuntimeError)])
def test_provider_exposes_output_limit_without_hiding_other_termination(reason,expected):
    client=MagicMock();stream=MagicMock()
    stream.__iter__.return_value=iter([NS(choices=[NS(delta=NS(content='Текст'),finish_reason=reason)])])
    client.chat.completions.create.return_value=stream
    with patch('llm.OpenAI',return_value=client):
        output=chat_stream('test',[],require_complete=True)
        assert next(output)=='Текст'
        with pytest.raises(expected) as exc:next(output)
        if reason!='length':assert not isinstance(exc.value,OutputLimitReached)
    stream.close.assert_called_once();client.close.assert_called_once()


def test_estimated_overflow_does_not_prevent_provider_request():
    # UTF-8 estimate is not a tokenizer: Cyrillic can be badly overestimated.
    original=[{'role':'system','content':'Правила'}, {'role':'user','content':'Сценарий: '+('Разговор друзей. '*3000)}]
    calls=[]
    def generate(messages,limit):
        assert messages[:2]==original  # No silent source truncation/compression.
        calls.append(limit)
        if len(calls)==1:
            yield 'Начало. '
            raise OutputLimitReached('length')
        assert messages[-2]['content']=='Начало. '
        yield 'Завершение.'
    output=''.join(stream_document(original,8192,12000,generate,Event()))
    assert output=='Начало. Завершение.' and calls==[1024,1024]


def test_real_provider_context_error_is_not_retried_forever():
    source=[{'role':'user','content':'Сценарий '*5000}]
    calls=[]
    def generate(messages,limit):
        calls.append(messages)
        raise RuntimeError('maximum context length exceeded')
        yield ''
    with pytest.raises(RuntimeError,match='maximum context'):
        list(stream_document(source,8192,12000,generate,Event()))
    assert len(calls)==1


def test_compact_builtin_summary_template_keeps_import_contract():
    from backend.services.generation_prompts import build_summary_messages, PROMPTS
    from world_parser import SECTIONS
    template=(PROMPTS/'summary_template.md').read_text()
    assert len(template.encode())<8000
    assert all('# '+section in template for section in SECTIONS)
    messages=build_summary_messages({'idea':'Мой полный сценарий'})
    assert 'Мой полный сценарий' in messages[1]['content']
    assert 'Знают:' in template and 'Подозревают:' in template and 'Время:' in template
