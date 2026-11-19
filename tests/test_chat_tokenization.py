"""Tokenizer data IO is substituted; real tokenizers library and budget path run."""
import hashlib
import io
import json
import zipfile
from unittest.mock import Mock,patch

import pytest
from tokenizers import Tokenizer,models,pre_tokenizers
from backend.chat import tokenization as tokens
from backend.chat.context import budget
from backend.chat.models import ModelSettings
from test_chat_mode import env


@pytest.fixture
def artifact(tmp_path,monkeypatch):
    tokenizer=Tokenizer(models.WordLevel({'[UNK]':0,'hello':1,'world':2},unk_token='[UNK]'))
    tokenizer.pre_tokenizer=pre_tokenizers.Whitespace()
    data=tokenizer.to_str().encode()
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive:
        archive.writestr(tokens.ENTRY,data)
        archive.writestr('deepseek_v4_tokenizer/evil.py','raise RuntimeError("must never execute")')
    zipped=buffer.getvalue();file=tmp_path/'tokenizer.json'
    monkeypatch.setenv('RPG_CHAT_TOKENIZER_PATH',str(file))
    monkeypatch.setattr(tokens,'TOKENIZER_SHA256',hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(tokens,'ARCHIVE_SHA256',hashlib.sha256(zipped).hexdigest())
    tokens.load.cache_clear()
    response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
    response.iter_content.return_value=[zipped]
    return file,data,response


def test_real_counter_is_used_only_for_known_compatible_model(artifact):
    file,data,_=artifact;file.write_bytes(data)
    config=ModelSettings(provider='deepseek',model='deepseek-flash',auto_context=True).model_dump()
    messages=[{'role':'user','content':'hello world '*100}]
    result=budget(messages,config)
    assert result['token_method'].startswith('DeepSeek V4 tokenizer')
    assert result['approximate']  # API framing still estimated; never claims exact provider usage.
    fallback=budget(messages,dict(config,provider='compatible'))
    assert fallback['token_method']=='Консервативная оценка UTF-8'
    assert fallback['estimated_tokens']>result['estimated_tokens']
    assert budget(messages,dict(config,model='unknown'))['token_method']==fallback['token_method']


def test_free_install_reads_only_pinned_json_and_is_idempotent(env,artifact):
    client,_=env;file,data,response=artifact
    config=ModelSettings(provider='deepseek',model='deepseek-v4-pro').model_dump()
    with patch('backend.chat.tokenization.requests.get',return_value=response) as get,patch('llm.chat_stream') as llm:
        first=client.post('/api/chat/tokenizer',json=config)
        assert first.status_code==200,first.text
        assert first.json()=={'installed':True,'downloaded':True}
        assert client.post('/api/chat/tokenizer',json=config).json()=={'installed':True,'downloaded':False}
        assert get.call_count==1 and llm.call_count==0
    assert file.read_bytes()==data
    assert not (file.parent/'evil.py').exists()
    assert client.post('/api/chat/capabilities',json=config).json()['tokenizer'].startswith('DeepSeek V4')


def test_unverified_or_missing_asset_falls_back_and_bad_download_is_not_installed(artifact):
    file,_,response=artifact
    assert tokens.available() is None
    file.write_text('unverified data')
    assert tokens.available() is None
    response.iter_content.return_value=[b'invalid archive']
    with patch('backend.chat.tokenization.requests.get',return_value=response),pytest.raises(ValueError,match='Консервативная оценка'):
        tokens.install()
    assert file.read_text()=='unverified data'


def test_tokenizer_install_rejects_unknown_model_before_network(env,artifact):
    client,_=env
    with patch('backend.chat.tokenization.requests.get') as get:
        response=client.post('/api/chat/tokenizer',json=ModelSettings(provider='compatible',model='deepseek-flash').model_dump())
        assert response.status_code==409 and get.call_count==0
