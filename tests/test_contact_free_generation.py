"""Provider contract, legacy import, and actual generation/handoff without contacts."""
import json
from unittest.mock import patch
from test_initial_draft_v4 import rich, api, REMOTE, wait_job
from draft_provider_fixture import accept_semantics_unchecked
from backend.services import draft_initial
from backend.services.draft_schema import world_state_schema
from backend.repositories.preparation import Repository


def test_provider_schema_excludes_phonebook_but_import_keeps_it():
    assert 'contacts' not in draft_initial.prompt_schema()['properties']['world']['properties']
    assert 'contacts' in world_state_schema()['properties']['world']['properties']
    candidate=rich()
    owner,target=[c['id'] for c in candidate['characters'][:2]]
    candidate['world']['contacts']={'legacy':dict(id='legacy',owner_id=owner,character_id=target,label='Старая подпись',address='+70000000000',provenance='import',created_at=0)}
    normalized,report=draft_initial.inspect_candidate(candidate)
    assert not report['errors'],report
    assert normalized['world']['contacts']==candidate['world']['contacts']
    from backend.services import draft_repair
    issue=dict(path='/world/contacts/legacy/label',category='semantic_completeness',message='Исправить подпись автора',patch_paths=['/world/contacts/legacy/label'])
    messages,scope=draft_repair.request(json.dumps(candidate),[issue])
    assert 'contacts' in json.loads(messages[1]['content'])['record_schemas']
    repaired=json.loads(draft_repair.apply(json.dumps(candidate),json.dumps({'patches':[{'path':issue['path'],'value':'Работа'}]}),scope))
    assert repaired['world']['contacts']['legacy']['address']=='+70000000000'
    assert repaired['world']['contacts']['legacy']['label']=='Работа'


def test_generated_world_without_contacts_start_send_call_reload(api):
    from test_runtime_v3_engine import run, raw_for
    from test_phone122 import execute
    from test_engine import CONFIG
    client,app=api;repo=app.state.repository
    candidate=rich();candidate['world'].pop('contacts',None)
    candidate['world']['communication']={'text_message':True,'voice_call':True,'presentation':'phone'}
    wid=client.post('/api/workspaces',json={'name':'Без телефонной книги'}).json()['id']
    url=f'/api/workspaces/{wid}/draft'
    calls=[]
    @accept_semantics_unchecked
    def generate(**kw):
        calls.append(kw)
        assert '"contacts"' not in kw['messages'][0]['content']
        yield json.dumps(candidate,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=generate):
        response=client.post(url+'/generate',json=dict(revision=0,text='Город. Современная связь.',config=REMOTE,api_key='offline'))
        assert response.status_code==200,response.text
        assert wait_job(client,response.json()['id'])['status']=='saved'
    assert len(calls)==1  # No phonebook repair or extra generation request.
    draft=client.get(url+'?author=true').json()
    assert draft['state']['world']['contacts']=={}
    response=client.post(url+'/confirm',json=dict(revision=draft['revision'],version_id=draft['version_id'],accept_warnings=True))
    assert response.status_code==200,response.text
    sid=response.json()['save']
    for kind in ('start','turn'):
        snapshot=repo.get_snapshot(sid)
        jid=repo.begin_job(sid,'Осматриваюсь.' if kind=='turn' else '',kind,CONFIG)
        run(repo,jid,raw_for(snapshot))
        assert repo.get_job(jid)['status']=='saved'
    phone=client.get(f'/api/saves/{sid}').json()['state']['phone']
    assert phone['contacts']==[]
    target=phone['recipients'][0]['id']
    for action in ('send','call'):
        with patch('engine.launch'):
            response=client.post(f'/api/saves/{sid}/phone/dispatch',json=dict(revision=repo.get_save(sid)['revision'],config=CONFIG,
                command=dict(action=action,character_id=target,operation_id='new-world-'+action,**({'content':'Здравствуйте.'} if action=='send' else {}))))
        assert response.status_code==200,response.text
        jid=response.json()['job']['id'];execute(repo,jid,outcome='silent')
        assert repo.get_job(jid)['status']=='saved'
    reloaded=Repository(repo.path)
    snapshot=reloaded.get_snapshot(sid)
    assert snapshot['world_state']['contacts']=={}
    assert len(snapshot['world_state']['remote_events'])==2
    jid=reloaded.begin_job(sid,'Продолжаю.', 'turn',CONFIG)
    run(reloaded,jid,raw_for(snapshot))
    assert reloaded.get_job(jid)['status']=='saved'
    assert len(reloaded.get_snapshot(sid)['world_state']['remote_events'])==2
