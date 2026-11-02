"""Offline provider contracts, not evidence of live DeepSeek artistic quality."""
import json
from copy import deepcopy
from unittest.mock import patch
import pytest
from test_api import api, REMOTE, wait_job
from test_initial_draft_v4 import rich
from backend.services.draft_initial import inspect_candidate
from backend.services.draft_changes import apply_proposal
from backend.services import draft_creative, draft_completeness
from backend.repositories.drafts import candidate_hash
from backend.repositories.preparation import Repository


def candidate():
    state, report = inspect_candidate(rich())
    assert not report['errors'], report
    return state


def proposal(state, changes=None):
    return json.dumps(dict(candidate_hash=candidate_hash(state), rationale='Прибрежная мастерская связывает жителей общим прошлым.',
                           changes=changes if changes is not None else additions(state)), ensure_ascii=False)


def change(path, value, op='add'):
    return dict(op=op, path=path, value=value, reason='Связь с историей мастерской.')


def additions(state):
    other=state['characters'][1]['id']
    card=deepcopy(state['characters'][1]);card.update(id='craftswoman',name='Вера',is_player=False)
    card['fields']['Биография']='Вернулась в город, чтобы спасти семейную мастерскую после пожара.'
    return [change('/characters/-',card),
        change('/world/characters/craftswoman',dict(id='craftswoman',situation='Сортирует уцелевшие инструменты.',location=None,goals=[],intentions=[],obligations=[],emotion='',minute=None,scene_id=None)),
        change('/world/organizations/workshop',dict(id='workshop',name='Мастерская Веры')),
        change('/world/roles/craft',dict(id='craft',actor_id='craftswoman',kind='occupation',title='Реставратор',organization_id='workshop')),
        change('/world/objective_relations/friend',dict(id='friend',source_id='craftswoman',target_id=other,kind='friend',context='Вместе спасали инструменты при пожаре.')),
        change('/world/facts/fire',dict(id='fire',text='Мастерская пострадала от пожара.',secret=False,character_ids=['craftswoman',other],evidence=[])),
        change('/world/events/fire',dict(id='fire',text='Вера с другом спасла инструменты.',participants=['craftswoman',other],witnesses=[],minute=None,scene_id=None,fact_ids=['fire'],player_observed=False)),
        change('/world/knowledge/fire',dict(actor_id='craftswoman',fact_id='fire',status='known',source_event_id='fire')),
        change('/world/threads/rebuild',dict(id='rebuild',description='Судьба мастерской после пожара.',state='Инструменты спасены; ремонт не оплачен.',status='active',character_ids=['craftswoman',other],visible_to_ids=['craftswoman'],relevance=.6,last_event_id='fire'))]


def test_atomic_related_additions_provenance_and_idempotent_resume():
    state=candidate();old=deepcopy(state);journal={};calls=[];checkpoints=[]
    def call(slot,messages):
        calls.append(slot)
        payload=json.loads(messages[1]['content'])
        assert payload['candidate']['world']==state['world']
        return proposal(state)
    enhanced=draft_creative.develop(state,'Не раскрывай происхождение героя.',journal,call,lambda:checkpoints.append(deepcopy(journal)))
    assert state==old and len(enhanced['characters'])==len(old['characters'])+1
    assert enhanced['world']['knowledge']['fire']['source_event_id']=='fire'
    assert journal['creative']['provenance']['source']=='creative_model'
    assert draft_creative.develop(enhanced,'brief',journal,call,lambda:None)==enhanced
    # Crash between journal persistence and appending candidate version.
    assert draft_creative.develop(state,'brief',journal,call,lambda:None)==enhanced
    assert len(calls)==1 and checkpoints[-1]['candidate_text']==json.dumps(enhanced,ensure_ascii=False)


@pytest.mark.parametrize('changes',[
    lambda s:[change('/world/facts/fire',dict(id='wrong',text='x'))],
    lambda s:[change('/characters/-',s['characters'][0])],
    lambda s:[change('/world/organizations/apex',dict(id='apex',name='Collision'))],
    lambda s:[change('/world/roles/bad',dict(id='bad',actor_id='absent',kind='occupation',title='x'))],
    lambda s:[change('/world/events/bad',dict(id='bad',text='Future',minute=9999999,participants=[],witnesses=[],fact_ids=[]))],
    lambda s:[change('/world_clock/minute',1,'replace')],
    lambda s:[change('/world/characters/'+s['controlled_actor_id']+'/unknown_authority',True)],
    lambda s:[change('/world/scheduled_events/new',dict(id='new',description='plan',participants=[],status='pending',due_minute=0,time_semantics='legacy'))],
    lambda s:[change('/world/characters/'+s['controlled_actor_id']+'/intentions',['Согласиться'],'replace')],
    lambda s:[change('/world/characters/'+s['controlled_actor_id']+'/birth_date_provenance',dict(source='manual'))],
    lambda s:[change('/world/knowledge/bad',dict(actor_id=s['controlled_actor_id'],fact_id='ownership',status='known',source_event_id='absent'))],
    lambda s:[change('/campaign/title','a','replace'),change('/campaign/title','b','replace')],
])
def test_invalid_packages_leave_candidate_intact(changes):
    state=candidate();before=deepcopy(state)
    with pytest.raises(ValueError):apply_proposal(state,proposal(state,changes(state)))
    assert state==before


def test_revision_manual_paths_and_rejected_response_are_not_replayed():
    state=candidate();state.setdefault('authoring',{})['manual_paths']=['/campaign/title']
    reply=proposal(state,[change('/campaign/title','Overwritten','replace')]);journal={};calls=[]
    def call(*_):calls.append(1);return reply
    for _ in range(2):
        with pytest.raises(ValueError):draft_creative.develop(state,'brief',journal,call,lambda:None)
    assert len(calls)==1 and journal['creative']['status']=='rejected'
    state['campaign']['title']='Edited'
    with pytest.raises(ValueError,match='устарело'):apply_proposal(state,reply)


def test_cancel_and_transport_error_preserve_candidate():
    from backend.services.draft_response import TransportError
    state=candidate();journal={}
    assert draft_creative.develop(state,'brief',journal,lambda *_:None,lambda:None) is None
    assert journal['creative']['status']=='cancelled' and 'candidate_text' not in journal
    def fail(*_):raise TransportError('offline')
    with pytest.raises(TransportError):draft_creative.develop(state,'brief',journal,fail,lambda:None)
    assert journal['creative']['status']=='interrupted'
    assert draft_creative.develop(state,'brief',journal,lambda *_:proposal(state),lambda:None)


@pytest.mark.parametrize("repair", [False, True])
def test_generation_editor_start_turn_reload(api,repair):
    client,app=api;wid=client.post('/api/workspaces',json={'name':'Creative'}).json()['id']
    path=f'/api/workspaces/{wid}/draft';calls=[];reviews=[]
    def stream(**kw):
        system=kw['messages'][0]['content'];calls.append(system)
        if system.startswith(draft_creative.MARKER):
            data=json.loads(kw['messages'][1]['content']);s=data['candidate']
            yield json.dumps(dict(candidate_hash=data['candidate_hash'],rationale='Связь мастерской с местными жителями.',changes=additions(s)),ensure_ascii=False)
        elif system.startswith(draft_completeness.MARKER):
            reviews.append(1)
            yield json.dumps({'issues':[dict(path='/world/organizations/workshop/name',message='Название должно отражать ремесло.',patch_paths=['/world/organizations/workshop/name'])] if repair and len(reviews)==1 else []})
        elif 'patches' in system:
            yield json.dumps({'patches':[dict(path='/world/organizations/workshop/name',value='Реставрационная мастерская Веры')]},ensure_ascii=False)
        else:yield json.dumps(rich(),ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        response=client.post(path+'/generate',json={'revision':0,'text':'В приморском городе после пожара восстанавливают мастерскую. Происхождение героя неизвестно.','config':dict(REMOTE,context_length=131072),'api_key':'offline'})
        job=wait_job(client,response.json()['id']);assert job['status']=='saved',job
    draft=client.get(path+'?author=true').json()
    assert len(calls)==(5 if repair else 3) and draft['review']['status']=='completed'
    expected='Реставрационная мастерская Веры' if repair else 'Мастерская Веры'
    assert draft['state']['world']['organizations']['workshop']['name']==expected
    started=client.post(path+'/confirm',json={'revision':draft['revision'],'version_id':draft['version_id'],'accept_warnings':True})
    assert started.status_code==200,started.text
    sid=started.json()['save'];repo=app.state.repository
    from test_runtime_v3_engine import run as play, raw_for
    from test_engine import CONFIG
    for kind in ('start','turn'):
        before=repo.get_snapshot(sid);jid=repo.begin_job(sid,'Осмотреться.' if kind=='turn' else '',kind,CONFIG)
        play(repo,jid,raw_for(before));assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
        repo=Repository(repo.path)
        assert repo.get_snapshot(sid)['world_state']['organizations']['workshop']['name']==expected


def test_factored_schema_is_valid_and_has_all_canonical_roots():
    from jsonschema import Draft202012Validator
    schema=draft_creative.creative_schema()
    Draft202012Validator.check_schema(schema)
    assert set(schema['properties'])==set(draft_creative.prompt_schema()['properties'])


@pytest.mark.parametrize('brief',['Средневековье без магии и телефонов. Прошлое героя неизвестно.', 'Космическая станция. Без главного героя, только наблюдение.', 'Семейная история; без обязательных тайн и конфликтов.'])
def test_complete_author_context_and_settings_are_not_clipped(brief):
    state=candidate();state['creation_settings']={'genre':'family_saga'}
    request=json.loads(draft_creative.messages(state,brief)[1]['content'])
    assert request['author_context']==brief
    assert request['candidate']['creation_settings']==state['creation_settings']
    assert request['candidate']['world']==state['world']


@pytest.mark.parametrize('failure', ['empty', 'network', 'truncated'])
def test_transport_resume_keeps_candidate_and_actual_usage(api,failure):
    from llm import OutputLimitReached
    client,app=api
    wid=client.post('/api/workspaces',json={'name':'Creative recovery'}).json()['id']
    url=f'/api/workspaces/{wid}/draft';creative_calls=[];world_calls=[];reply=''
    def stream(**kw):
        nonlocal reply
        system=kw['messages'][0]['content']
        kw['on_usage']({'prompt_tokens':100,'completion_tokens':20})
        kw['on_finish']('stop')
        if system.startswith(draft_creative.MARKER):
            creative_calls.append(kw)
            payload=json.loads(kw['messages'][1]['content'])
            reply=json.dumps(dict(candidate_hash=payload['candidate_hash'],rationale='Сеть отношений мастерской.',changes=additions(payload['candidate'])),ensure_ascii=False)
            if len(creative_calls)==1:
                if failure=='empty':yield '';return
                if failure=='network':raise OSError('controlled unknown outcome')
                kw['on_finish']('length')
                yield reply[:len(reply)//2]
                raise OutputLimitReached()
            if failure=='truncated':
                assert kw['messages'][-2]['content']==reply[:len(reply)//2]
                yield reply[len(reply)//2:];return
            yield reply
        elif system.startswith(draft_completeness.MARKER):yield '{"issues":[]}'
        else:
            world_calls.append(kw)
            yield json.dumps(rich(),ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        created=client.post(url+'/generate',json={'revision':0,'text':'Мастерская после пожара.','config':dict(REMOTE,context_length=131072),'api_key':'offline'})
        jid=created.json()['id'];job=wait_job(client,jid)
        if failure!='truncated':
            assert job['status']=='error',job
            draft=client.get(url+'?author=true').json()
            assert draft['candidate'] and draft['technical_valid']
            assert 'workshop' not in draft['candidate']['world']['organizations']
            journal=json.loads(app.state.repository.preparation_job(jid)['response_journal'])
            assert journal['creative']['status']=='interrupted'
            if failure=='network':
                assert journal['pending'] and job['unknown_outcome']
                assert client.post(url+'/resume',json={'revision':draft['revision'],'api_key':'offline'}).status_code==409
                recovery={'acknowledge_unknown':True}
            else:
                assert job['empty_retry_token'] and not journal['pending']
                recovery=dict(retry_empty_response=job['empty_retry_token'],expected_epoch=job['attempt_epoch'])
            # Reload the repository before recovery, as after a process restart.
            assert Repository(app.state.repository.path).draft(wid,True)['candidate']==draft['candidate']
            resumed=client.post(url+'/resume',json=dict(revision=draft['revision'],api_key='offline',**recovery))
            assert resumed.status_code==200,resumed.text
            job=wait_job(client,jid)
        assert job['status']=='saved',job
    journal=json.loads(app.state.repository.preparation_job(jid)['response_journal'])
    assert len(world_calls)==1 and len(creative_calls)==2
    assert journal['creative']['status']=='applied'
    assert len(app.state.repository.request_log(job_id=jid))==4
    # Failed network billing is not inferred; the prior reservation stays intact.
    if failure=='network':assert journal['unknown_attempts'] and journal['reserved_tokens']>0
    else:assert journal['actual_tokens']==480 and journal['reserved_tokens']==0
    assert client.get(url+'?author=true').json()['state']['world']['organizations']['workshop']

@pytest.mark.parametrize('fault',['reference','shape','scope'])
def test_addressed_correction_preserves_related_package(fault):
    state=candidate();before=deepcopy(state);changes=additions(state)
    if fault=='reference':changes[3]['value']['actor_id']='missing'
    elif fault=='shape':changes[3]['value']['title']=12
    else:changes.append(change('/world_clock/minute',100,'replace'))
    original=proposal(state,changes);journal={};calls=[]
    def call(slot, request):
        calls.append(slot)
        if not slot.startswith('creative_correction_'):return original
        payload=json.loads(request[1]['content'])
        patches=[] if fault=='scope' else [dict(path='/changes/3/value/'+('actor_id' if fault=='reference' else 'title'),value='craftswoman' if fault=='reference' else 'Реставратор')]
        assert all(p['path'] in payload['allowed_paths'] for p in patches),payload
        return json.dumps(dict(proposal_hash=payload['proposal_hash'],patches=patches,drop_indices=[9] if fault=='scope' else []))
    enhanced=draft_creative.develop(state,'Авторский бриф',journal,call,lambda:None)
    assert state==before and len(calls)==2
    assert journal['creative']['original_reply']==original
    assert len(journal['creative']['corrections'])==1
    assert enhanced['world']['knowledge']['fire']['source_event_id']=='fire'
    assert enhanced['world']['threads']['rebuild']['last_event_id']=='fire'
    assert enhanced['world']['organizations']['workshop']['name']=='Мастерская Веры'
    assert draft_creative.develop(state,'Авторский бриф',journal,lambda *_:pytest.fail('repeat'),lambda:None)==enhanced


def test_correction_exhaustion_is_persistent_and_cannot_rewrite_good_changes():
    state=candidate();before=deepcopy(state);changes=additions(state);changes[3]['value']['actor_id']='missing'
    original=proposal(state,changes);journal={};calls=[]
    def call(slot, request):
        calls.append(slot)
        if not slot.startswith('creative_correction_'):return original
        payload=json.loads(request[1]['content'])
        return json.dumps(dict(proposal_hash=payload['proposal_hash'],patches=[dict(path='/changes/0/value/name',value='Hacked')],drop_indices=[]))
    for _ in range(3):
        with pytest.raises(ValueError):draft_creative.develop(state,'brief',journal,call,lambda:None)
        journal=json.loads(json.dumps(journal))
    assert len(calls)==3 and len(journal['creative']['corrections'])==2
    assert journal['creative']['current_reply']==original and state==before
    assert 'candidate_text' not in journal
    assert all('неразрешённый' in a['error'] for a in journal['creative']['corrections'])


def test_correction_interruption_resumes_same_proposal_and_slot():
    from backend.services.draft_response import TransportError
    state=candidate();changes=additions(state);changes[3]['value']['actor_id']='missing'
    original=proposal(state,changes);journal={};slots=[]
    def interrupted(slot, request):
        slots.append(slot)
        if slot.startswith('creative_correction_'):raise TransportError('outage')
        return original
    with pytest.raises(TransportError):draft_creative.develop(state,'brief',journal,interrupted,lambda:None)
    assert journal['creative']['status']=='interrupted' and not journal['creative']['corrections']
    journal=json.loads(json.dumps(journal))
    def recovered(slot, request):
        assert slot==slots[-1]
        payload=json.loads(request[1]['content'])
        return json.dumps(dict(proposal_hash=payload['proposal_hash'],patches=[dict(path='/changes/3/value/actor_id',value='craftswoman')],drop_indices=[]))
    assert draft_creative.develop(state,'brief',journal,recovered,lambda:None)['world']['organizations']['workshop']
    assert journal['creative']['original_reply']==original and len(journal['creative']['corrections'])==1


def test_changed_transport_policy_recovers_empty_length_without_losing_history():
    from backend.services.draft_creative import response_slot
    record={'slot':'creative_base','request_key':'old'}
    old=dict(parts=[dict(text='')],failure={'code':'empty_output_limit'})
    journal={'responses':{'creative_base':old}}
    assert response_slot(journal,record,'new')=='creative_base_new'
    assert journal['responses']['creative_base']==old
    record={'slot':'creative_partial','request_key':'old'}
    journal={'responses':{'creative_partial':dict(parts=[dict(text='{"changes":')])}}
    assert response_slot(journal,record,'new')=='creative_partial'
    record={'slot':'creative_base','request_key':'old'}
    journal=dict(response_retries={'creative_base':'confirmed'},empty_retries={'fp':dict(slot='confirmed',epoch=1,used=False)},recovery_epoch=1)
    assert response_slot(journal,record,'new')=='creative_base'


def test_api_correction_accounting_and_saved_candidate(api):
    client,app=api;repo=app.state.repository
    wid=client.post('/api/workspaces',json={'name':'Addressed creative correction'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    stages=[]
    def stream(**kw):
        system=kw['messages'][0]['content'];kw['on_usage']({'prompt_tokens':100,'completion_tokens':20,'prompt_cache_hit_tokens':0});kw['on_finish']('stop')
        if system.startswith(draft_creative.MARKER):
            stages.append('creative');payload=json.loads(kw['messages'][1]['content']);changes=additions(payload['candidate']);changes[3]['value']['actor_id']='missing'
            yield json.dumps(dict(candidate_hash=payload['candidate_hash'],rationale='Связанный пакет мастерской',changes=changes))
        elif system.startswith('Адресная коррекция'):
            stages.append('correction');payload=json.loads(kw['messages'][1]['content'])
            draft=repo.draft(wid,True);assert 'workshop' not in draft['candidate']['world']['organizations']
            yield json.dumps(dict(proposal_hash=payload['proposal_hash'],patches=[dict(path='/changes/3/value/actor_id',value='craftswoman')],drop_indices=[]))
        elif system.startswith(draft_completeness.MARKER):stages.append('review');yield '{"issues":[]}'
        else:stages.append('world');yield json.dumps(rich())
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        created=client.post(url+'/generate',json=dict(revision=0,text='Город мастерских',config=dict(REMOTE,context_length=131072),api_key='offline'))
        jid=created.json()['id'];job=wait_job(client,jid);assert job['status']=='saved',job
    raw=client.get(url+'/raw').json()
    assert stages==['world','creative','correction','review']
    assert raw['actual_tokens']==480 and raw['reserved_tokens']==0
    assert float(raw['actual_cost'])>0 and float(raw.get('reserved_cost',0))==0
    assert [r['stage'] for r in raw['requests']].count('draft_world_creative_repair')==1
    assert 'missing' in raw['creative']['original_reply'] and len(raw['creative']['corrections'])==1
    saved=Repository(repo.path).draft(wid,True)
    assert saved['state']['world']['knowledge']['fire']['source_event_id']=='fire'
