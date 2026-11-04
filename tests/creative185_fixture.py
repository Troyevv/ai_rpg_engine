"""Build a pre-upgrade rejected checkpoint using real generation persistence."""
import json
from pathlib import Path
from unittest.mock import patch
from backend.services import draft_creative
from test_api import REMOTE, wait_job


def seed_rejected(client):
    data=json.loads((Path(__file__).parent/'fixtures/creative185/sosnovka.json').read_text())
    def stream(**kw):
        if kw['messages'][0]['content'].startswith(draft_creative.MARKER):
            value=json.loads(data['creative']['original_reply'])
            value['candidate_hash']=json.loads(kw['messages'][1]['content'])['candidate_hash']
        else:value=data['candidate']
        kw['on_finish']('stop');kw['on_usage']({'prompt_tokens':100,'completion_tokens':20})
        yield json.dumps(value,ensure_ascii=False)
    workspace=client.post('/api/workspaces',json={'name':'Сосновка: восстановление'}).json()
    url=f"/api/workspaces/{workspace['id']}/draft"
    with patch('backend.services.preparation.chat_stream',side_effect=stream),patch.object(draft_creative,'VALIDATION_VERSION',1),patch.object(draft_creative,'apply_proposal',side_effect=ValueError('Модель не может назначать серверное происхождение: revision')):
        response=client.post(url+'/generate',json=dict(revision=0,text='Сосновка.',config=dict(REMOTE,context_length=131072,max_tokens=20000),api_key='offline'))
        assert response.status_code==200,response.text
        job=wait_job(client,response.json()['id']);assert job['status']=='error',job
    return workspace
