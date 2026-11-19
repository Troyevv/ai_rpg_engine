"""Provider protocol controls only; no live capability claim."""
import json
from copy import deepcopy
from types import SimpleNamespace
from threading import Event
from unittest.mock import patch
import pytest
from jsonschema import Draft202012Validator
from backend.services.structured_extraction import response_events, wire_schema, transport
from backend.runtime_v3.scene_steps import input_schema
from llm import chat_stream, OutputLimitReached

pytestmark=pytest.mark.extraction_v6


def events(text='{"scene":{},"scene_steps":[]}',status='completed'):
    return [dict(type='response.output_text.delta',delta=text,output_index=0,content_index=0),
        dict(type='response.'+status,response=dict(status=status,
            usage=dict(input_tokens=12,output_tokens=7,input_tokens_details=dict(cached_tokens=3)),
            output=[dict(type='message',content=[dict(type='output_text',text=text)])]))]


def test_lossless_provider_schema_refs_and_nullable():
    original=input_schema();wire=wire_schema(original)
    Draft202012Validator.check_schema(wire)
    assert '$anchor' not in json.dumps(wire) and 'discriminator' not in json.dumps(wire)
    value=dict(scene={},scene_steps=[dict(id='gone',kind='movement',actor_id='npc',text='Ушёл.',assertion='departure',endpoint=None)])
    Draft202012Validator(original).validate(value);Draft202012Validator(wire).validate(value)
    assert original==input_schema()


def test_actual_responses_request_shape_accounting_and_no_roundtrip():
    schema=wire_schema(input_schema());stream=SimpleNamespace(__iter__=None)
    class Stream(list):
        closed=False
        def close(self):self.closed=True
    output=Stream(events());client=SimpleNamespace(responses=SimpleNamespace(create=lambda **kw:None))
    usage=[];finish=[]
    with patch('llm.OpenAI') as factory:
        sdk=factory.return_value;sdk.responses.create.return_value=output
        text=''.join(chat_stream(model='deepseek-flash',messages=[dict(role='system',content='JSON Schema\n'+json.dumps(schema)),dict(role='user',content='Input')],
            provider='deepseek',api_key='private',thinking='off',require_complete=True,
            structured_schema=schema,extraction_transport='responses_json_schema',on_usage=usage.append,on_finish=finish.append))
        request=sdk.responses.create.call_args.kwargs
        assert request['text']['format']==dict(type='json_schema',name='extraction_v6',schema=schema)
        assert request['reasoning']==dict(effort='none') and request['input']==[dict(role='user',content='Input')]
        assert 'response_format' not in request and 'messages' not in request
        assert sdk.responses.create.call_count==1 and sdk.chat.completions.create.call_count==0
        assert factory.call_args.kwargs['max_retries']==0
        sdk.close.assert_called_once()
    assert output.closed and json.loads(text)['scene_steps']==[]
    assert finish==['stop'] and usage[0]['prompt_tokens']==12 and usage[0]['prompt_cache_hit_tokens']==3


@pytest.mark.parametrize('damage',['blank','incomplete','no_terminal','multiple','tool','mismatch','length','cancel'])
def test_bad_stream_never_becomes_success(damage):
    seq=events();cancel=Event()
    if damage=='blank':seq=events('   ')
    if damage=='incomplete':seq=events(status='incomplete')
    if damage=='no_terminal':seq=seq[:1]
    if damage=='multiple':seq.insert(1,dict(type='response.output_text.delta',delta='{}',output_index=1,content_index=0))
    if damage=='tool':seq[-1]['response']['output'].append(dict(type='function_call',name='foreign',arguments='{}'))
    if damage=='mismatch':seq[-1]['response']['output'][0]['content'][0]['text']='other'
    if damage=='length':seq=events(status='incomplete');seq[-1]['response']['incomplete_details']={'reason':'max_output_tokens'}
    if damage=='cancel':cancel.set()
    with pytest.raises(RuntimeError):list(response_events(seq,cancel,None,None))


def test_capability_selection_does_not_change_model():
    assert transport(dict(provider='deepseek',model='deepseek-flash'))=='responses_json_schema'
    assert transport(dict(provider='deepseek',model='older-model'))=='chat_json_object'
    assert transport(dict(provider='compatible',model='deepseek-flash'))=='chat_json_object'
