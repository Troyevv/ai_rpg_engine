import json
from copy import deepcopy
from unittest.mock import patch
import pytest
import engine
from backend.runtime_v3.remote_authoring import DIGITAL_TEXT_STYLE, speaker_context, pre_style_context
from backend.runtime_v3.remote_initiative import planning_context, stage
from backend.runtime_v3.group_planning import reaction_context, context, opportunities
from backend.runtime_v3.communication import options_for
from backend.runtime_v3.models import PersonalityProfile, PersonalityItem, Relationship
from backend.repositories.preparation import Repository
from test_group152 import group, provider
from test_remote_communication import command
from test_group_deepseek_http import DeepSeekHTTP, config, run, send
from test_phone122 import setup, read
from digital_style_provider import response, REPLY, DRY


def test_three_authors_share_one_optional_style_rule_and_personal_context():
    snapshot,gid = group(); state = snapshot['world_state']
    state['characters']['b']['personality'] = PersonalityProfile(items={'voice':PersonalityItem(
        field='communication',text='Любит живое общение, но с начальством сдержан')}).model_dump()
    state['characters']['b'].update(emotion='Сердится',situation='Занят работой')
    snapshot['character_cards'].append(dict(id='c',fields={'Характер':'Сдержанный','Стиль общения':'Сухо, без украшений'}))
    for source,target,text in [('b','a','Близкий друг'),('b','c','Соперничество'),('a','b','Невысказанное чувство')]:
        state['relationships'][source+':'+target]=Relationship(source_id=source,target_id=target,context=text).model_dump()
    original=deepcopy(snapshot)
    direct=command(snapshot,'send',contact_id='a-b',content='Привет')
    source=list(direct['world_state']['remote_events'])[-1]
    dm=planning_context(direct, options_for(direct,source,set()))
    voice=json.loads(dm[1]['content'])['actors'][0]
    for key,value in speaker_context(direct,'b',{'a'}).items():assert voice[key]==value
    assert [r['target_id'] for r in voice['relationships']]==['a']
    assert voice['emotion']=='Сердится' and voice['pending'][0]['content'] is None
    sent=command(snapshot,'send',conversation_id=gid,content='Привет всем')
    gm=reaction_context(sent,list(sent['world_state']['remote_events'])[-1])
    actors={a['id']:a for a in json.loads(gm[1]['content'])['groups'][0]['actors']}
    assert actors['b']['personality']==voice['personality']
    assert {r['target_id'] for r in actors['b']['relationships']}=={'a','c'}
    assert actors['c']['legacy_voice']['Стиль общения']=='Сухо, без украшений'
    assert not actors['c']['relationships']
    gen,calls=provider(gid,question=False);stage(snapshot,gen,'style-shared')
    assert len(calls)==2
    for messages in (dm,gm,calls[0][1]):
        assert messages[0]['content'].count(DIGITAL_TEXT_STYLE)==1
        assert 'no emoji is equally valid' in messages[0]['content']
        assert 'no quotas, probabilities or uniform style' in messages[0]['content']
    assert json.loads(dm[1]['content'])['communication_profile']==state['meta']['communication']
    assert snapshot==original


@pytest.mark.parametrize('group_chat',[False,True])
@pytest.mark.parametrize('text',[REPLY,DRY])
def test_unicode_and_plain_text_api_jobs_sqlite_retry_reload(tmp_path,group_chat,text):
    repo,client,sid=setup(tmp_path); http=DeepSeekHTTP()
    def authored(body):
        value=json.loads(response(body['messages'],True))
        if body['messages'][0]['content'].startswith('Group communication reaction/'):
            value['messages'][0]['content']=text
        elif value.get('action') and value['action']['action']=='send':value['action']['content']=text
        return json.dumps(value,ensure_ascii=False)
    http.answer=authored;http.reject_semantic=True
    jid=send(repo,client,sid,config(),group_chat);before=repo.get_snapshot(sid)
    run(repo,jid,http);assert repo.get_job(jid)['status']=='error'
    author_count=len(http.requests)-1
    assert len(repo.get_snapshot(sid)['world_state']['remote_events'])==1
    # Exercise an actual pre-style accepted journal, then resume via the API.
    job=repo.get_job(jid);frames=json.loads(job['context_json'])
    for frame in frames:
        if frame['stage']=='communication':frame['messages']=pre_style_context(frame['messages'],before,group=group_chat)
    repo.save_communication_context(jid,frames,json.loads(job['memory_before_json'] or job['before_json']))
    repo=Repository(repo.path)
    with patch('engine.launch'):
        retried=client.post(f'/api/jobs/{jid}/retry',json={'config':config(),'api_key':'local-http-fixture-secret'})
    assert retried.status_code==200,retried.text
    run(repo,jid,http);assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    assert len(http.requests)==author_count+2
    state=repo.get_snapshot(sid)['world_state']
    rows=list(state['remote_events'].values())
    assert rows[1]['content']==text
    assert len(rows)==(3 if group_chat else 2)
    assert state['camera']==before['world_state']['camera']
    # Existing clock normalization may resolve an unknown developmental stage.
    # Verify physical state and voluntary/personality fields, not that derived age cache.
    for cid,actor in state['characters'].items():
        for field in ('location_id','situation','emotion','goals','intentions','obligations','personality'):
            assert actor[field]==before['world_state']['characters'][cid][field]
    controlled=state['camera']['controlled_actor_id']
    assert state['characters'][controlled]==before['world_state']['characters'][controlled]
    assert not state['scheduled_events']
    assert repo.get_save(sid)['state']['phone']['events'][1]['content'] is None
    read(repo,client,sid)
    assert client.get(f'/api/saves/{sid}').json()['state']['phone']['events'][1]['content']==text
    assert Repository(repo.path).get_snapshot(sid)==repo.get_snapshot(sid)
    count=len(http.requests);run(repo,jid,http);assert len(http.requests)==count


def test_autonomous_unicode_series_uses_one_author_and_existing_extraction():
    snapshot,gid=group();gen,calls=provider(gid,question=False)
    def unicode_author(name,messages,*args,**kwargs):
        value=json.loads(''.join(gen(name,messages,*args,**kwargs)))
        if name=='remote_initiative':value['group_series']['messages'][0]['content']=REPLY
        return iter([json.dumps(value,ensure_ascii=False)])
    after=stage(snapshot,unicode_author,'unicode-autonomous')
    assert len(calls)==2
    assert list(after['world_state']['remote_events'].values())[0]['content']==REPLY
    assert after['world_state']['camera']==snapshot['world_state']['camera']


def test_autonomous_unicode_actual_api_job_and_sqlite(tmp_path):
    repo,client,sid=setup(tmp_path)
    joined=client.post(f'/api/saves/{sid}/phone',json=dict(revision=repo.get_save(sid)['revision'],
        command=dict(action='join',conversation_id='qa-group',operation_id='unicode-autonomous-join',member_ids=['qa_timur','qa_oleg'])))
    assert joined.status_code==200
    http=DeepSeekHTTP();http.answer=lambda body:response(body['messages'],bool(body.get('response_format')))
    # The long accepted remote transcript also enters ordinary Extraction.
    # Use a supported larger context window; keep all production budget guards.
    wide_config=dict(config(),context_length=65536)
    with patch('engine.launch'):
        submitted=client.post(f'/api/saves/{sid}/turns',json=dict(revision=repo.get_save(sid)['revision'],text='Смотрю на дождь.',kind='turn',config=wide_config,api_key='local-http-fixture-secret'))
    assert submitted.status_code==200,submitted.text
    jid=submitted.json()['id'];run(repo,jid,http)
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    rows=list(repo.get_snapshot(sid)['world_state']['remote_events'].values())
    assert rows[0]['content']==REPLY and len(rows)==2
    assert all(e['sender_id']!='qa_kirill' for e in rows)
    stages=[r['stage'] for r in repo.request_log(job_id=jid)]
    assert stages.count('remote_initiative')==1 and stages.count('remote_group_semantics')==1
    assert repo.get_save(sid)['state']['phone']['events'][0]['content'] is None
    read(repo,client,sid)
    assert client.get(f'/api/saves/{sid}').json()['state']['phone']['events'][0]['content']==REPLY
    assert Repository(repo.path).get_snapshot(sid)==repo.get_snapshot(sid)
