"""#128: one capability owner from authoring through real Narrative persistence."""
import json
from copy import deepcopy
from unittest.mock import patch
import pytest
from test_api import api, REMOTE, wait_job
from test_draft_world import fixture
from test_remote_communication import phone, command
from test_initial_draft_v4 import rich
from draft_provider_fixture import accept_semantics_unchecked
from backend.runtime_v3.remote_models import CommunicationCapabilities
from backend.runtime_v3.migration import migrate_v2
from backend.runtime_v3.remote import projection
from backend.runtime_v3.selectors import ui_view
from backend.services import draft_world, draft_initial
from backend.services.communication_profile import catalog, edit_profile, apply_explicit, CHANNELS
from backend.repositories.preparation import Repository


@pytest.mark.parametrize('year,preset,enabled',[(1350,'modern',{'text_message','voice_call'}),(1939,'1939',{'letter','telegram','landline'}),(2026,'custom',{'courier'}),(2026,'none',set()),(1350,'fantastic',{'magic'})])
def test_channels_independent_of_calendar(year,preset,enabled):
    profile=catalog()[preset]
    if preset=='custom':profile['courier']=True
    raw=fixture();raw['world_clock']['calendar']={'start_date':f'{year}-01-01','start_minute':0}
    state=draft_initial.normalize(edit_profile(raw,profile))
    canonical=migrate_v2(state).snapshot
    actual=canonical['world_state']['meta']['communication']
    assert {c for c in CHANNELS if actual[c]}==enabled
    assert canonical['world_state']['meta']['calendar']['start_date']==f'{year}-01-01'
    assert migrate_v2(canonical).snapshot==canonical
    assert bool(ui_view(canonical)['phone'])==('text_message' in enabled)


def mixed():
    return dict(catalog()['modern'],preset='custom',letter=True,magic=True,
                delivery_policy=dict(text_message='instant',voice_call='live',letter='delayed',magic='instant'),
                author_note='Письма с печатями и смартфоны в 1350 году.')


@pytest.mark.parametrize('format,profile_name',[('json','mixed'),('text','mixed'),('json','none')])
def test_import_edit_start_turn_reload_next_turn_and_rollback(api,format,profile_name):
    client,app=api
    wid=client.post('/api/workspaces',json={'name':'Mixed channels'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    original=edit_profile(fixture(),catalog()['1939'])
    text=json.dumps(original) if format=='json' else draft_world.export_markdown(original)
    imported=client.post(url+'/import',json={'revision':0,'format':format,'text':text})
    assert imported.status_code==200,imported.text
    draft=imported.json();profile=mixed() if profile_name=='mixed' else catalog()['none']
    edited=client.post(url+'/communication',json={'revision':draft['revision'],'profile':profile})
    assert edited.status_code==200,edited.text
    assert client.post(url+'/communication',json={'revision':draft['revision'],'profile':catalog()['none']}).status_code!=200
    draft=client.get(url+'?author=true').json()
    assert draft['state']['world']['communication']==profile
    assert draft['creation_settings']['communication']==profile
    public=client.get(url).json()
    assert public['state']['world']['communication']==profile
    assert draft_world.exported_state(draft_world.export_markdown(draft['state']))['world']['communication']==profile
    confirmed=client.post(url+'/confirm',json={'revision':draft['revision'],'version_id':draft['version_id'],'accept_warnings':True})
    assert confirmed.status_code==200,confirmed.text
    sid=confirmed.json()['save'];repo=app.state.repository
    from test_runtime_v3_engine import run,raw_for
    from test_engine import CONFIG
    for kind in ('start','turn','turn'):
        before=repo.get_snapshot(sid)
        jid=repo.begin_job(sid,'Осматриваюсь.' if kind=='turn' else '',kind,CONFIG)
        run(repo,jid,raw_for(before))
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
        repo=Repository(repo.path)
        assert repo.get_snapshot(sid)['world_state']['meta']['communication']==profile
        assert repo.get_save(sid)['state']['communication_profile']==profile
        assert bool(repo.get_save(sid)['state']['phone'])==(profile_name=='mixed')
    latest=repo.list_turns(sid)[-1];original_variant=latest['active_variant_id']
    original_after=repo.get_snapshot(sid)
    jid=repo.begin_job(sid,'','regenerate',CONFIG)
    run(repo,jid,raw_for(before))
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    assert repo.get_snapshot(sid)['world_state']['meta']['communication']==profile
    repo.select_variant(sid,latest['id'],original_variant,repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==original_after
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==before


def test_legacy_phone_and_unknown_migrate_without_guessing_or_lost_history():
    snap=command(phone(),'send',contact_id='a-b',content='Сохрани сообщение')
    cfg=snap['world_state']['meta']['communication']
    legacy_keys={'text_message','voice_call','presentation','region','ring_timeout_minutes','emergency_numbers'}
    snap['world_state']['meta']['communication']={k:v for k,v in cfg.items() if k in legacy_keys}
    before=deepcopy(snap)
    upgraded=migrate_v2(snap).snapshot
    assert snap==before
    assert upgraded['world_state']['remote_events']==before['world_state']['remote_events']
    assert projection(upgraded)['events']
    assert upgraded['world_state']['meta']['communication']['preset']=='unspecified'
    assert migrate_v2(upgraded).snapshot==upgraded
    unknown=fixture();unknown['campaign']['era']='2026';unknown['campaign']['genre']='science_fiction'
    unknown['world'].pop('communication',None)
    cfg=migrate_v2(unknown).snapshot['world_state']['meta']['communication']
    assert not any(cfg[c] for c in CHANNELS)


def test_explicit_profile_survives_model_override_and_author_revision():
    state=edit_profile(fixture(),mixed())
    state['world']['communication']=catalog()['none']
    apply_explicit(state)
    assert state['world']['communication']==mixed()
    changed=edit_profile(state,catalog()['letters'])
    apply_explicit(changed)
    assert changed['world']['communication']==catalog()['letters']
    assert state['creation_settings']['communication']==mixed()
    none=dict(catalog()['none'],author_note='Есть смартфоны, включи звонки')
    state=edit_profile(fixture(),none)
    cfg=migrate_v2(state).snapshot['world_state']['meta']['communication']
    assert not any(cfg[c] for c in CHANNELS)


def test_generation_preserves_explicit_profile_without_extra_model_stage(api):
    client,app=api;wid=client.post('/api/workspaces',json={'name':'Explicit channels'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    raw=rich();raw['world']['communication']=catalog()['modern'];calls=[]
    @accept_semantics_unchecked
    def stream(**kwargs):
        calls.append(kwargs)
        yield json.dumps(raw,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        reply=client.post(url+'/generate',json={'revision':0,'text':'1350 со смартфонами и магией','config':dict(REMOTE,context_length=65536),'api_key':'test-secret','creation_settings':{'communication':mixed()}})
        job=wait_job(client,reply.json()['id'])
    assert job['status']=='saved',job
    assert len(calls)==1
    draft=client.get(url+'?author=true').json()
    assert draft['state']['world']['communication']==mixed()
    assert draft['creation_settings']['communication']==mixed()
    assert 'Технологии связи communication заданы явно' in calls[0]['messages'][1]['content']


def test_typed_import_reports_channel_errors_without_discarding_source():
    raw=fixture();raw['world']['communication']={'magic':'yes'}
    with pytest.raises(draft_initial.DraftErrors) as exc:draft_initial.validate_typed(raw)
    assert any(e['path']=='/world/communication/magic' for e in exc.value.errors)
    assert raw['world']['communication']=={'magic':'yes'}


def test_resume_retains_explicit_profile_and_continues_once(tmp_path):
    import hashlib
    from backend.services.preparation import Preparation, Handle
    from backend.services.draft_generation import run
    repo=Repository(tmp_path/'resume.sqlite3');w=repo.create_workspace('profile resume')
    config=dict(REMOTE,context_length=65536,_draft_task='world',_draft_input='Смартфоны в 1350',_use_idea=False,_creation_settings={'communication':mixed()})
    jid=repo.begin_preparation(w['id'],'draft_world','Смартфоны в 1350',config,0)
    raw=json.dumps(rich(),ensure_ascii=False,separators=(',',':'));cut=raw.index('Apex')+2;first=raw[:cut]
    repo.save_response_journal(jid,{'pending':None,'responses':{'world':{'complete':False,'parts':[dict(text=first,offset=0,sha256=hashlib.sha256(first.encode()).hexdigest(),finish_reason='length')]}}})
    repo.preparation_progress(jid,first,'stopped')
    repo=Repository(repo.path);config=repo.resume_draft_response(jid);calls=[]
    @accept_semantics_unchecked
    def stream(**kwargs):calls.append(kwargs);yield raw[cut:]
    run(Preparation(repo),jid,config,None,Handle(),None,stream)
    assert len(calls)==1
    assert repo.draft(w['id'],True)['state']['world']['communication']==mixed()
