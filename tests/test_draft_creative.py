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
