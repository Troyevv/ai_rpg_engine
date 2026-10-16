"""#70 deterministic canonical actions and information boundaries."""
import json
from copy import deepcopy
from unittest.mock import patch
import pytest
from test_protagonist import snapshot
from backend.runtime_v3.models import Contact, Character, WorldHistoryV3, Location
from backend.runtime_v3.remote_models import CommunicationCapabilities
from backend.runtime_v3.remote import apply, projection, context_projection, resolve_identity, advance
from backend.runtime_v3.remote_initiative import accept, opportunities
from backend.runtime_v3.protagonist import transition


def phone():
    snap=snapshot();s=snap['world_state']
    s['meta']['communication']=CommunicationCapabilities(text_message=True,voice_call=True,presentation='phone').model_dump()
    for owner,target in [('a','b'),('b','a'),('a','child')]:
        cid=owner+'-'+target
        s['contacts'][cid]=Contact(id=cid,owner_id=owner,character_id=target,label='Saved '+target,address='address-'+target,
            identity_visible=True,provenance='explicit fixture',created_at=0).model_dump()
    s['characters']['b']['location_id']='away';s['locations']['away']=Location(id='away',name='Другое место').model_dump()
    s['camera']['present_character_ids'].remove('b')
    return snap


def command(s,action,**kw):
    return apply(s,dict(action=action,operation_id=kw.pop('operation_id','operation-'+str(len(s['world_state']['remote_events']))+'-'+action),**kw))[0]


def incoming(s, action='send', content='Давай завтра встретимся.'):
    return apply(s,dict(action=action,operation_id='incoming-'+action,contact_id='b-a',content=content),actor_id='b',autonomous=True)[0]


def test_contacts_switch_and_no_automatic_graph():
    s=phone();p=projection(s)
    assert [c['label'] for c in p['contacts']]==['Saved b','Saved child']
    assert s['world_state']['characters']['b']['display_name']=='b'
    other,_=transition(s,'temporary','b','switch')
    assert [c['label'] for c in projection(other)['contacts']]==['Saved a']
    assert not projection(snapshot())


def test_delivery_read_and_quote_provenance():
    s=incoming(phone());e=next(iter(s['world_state']['remote_events'].values()))
    assert e['status']=='delivered' and e['read_by']==[]
    assert projection(s)['events'][0]['content'] is None
    assert 'Давай завтра' not in json.dumps(context_projection(s['world_state']),ensure_ascii=False)
    assert len(s['world_state']['knowledge'])==1
    after,batch=apply(s,dict(action='read',operation_id='read-message',event_id=e['id']))
    assert projection(after)['events'][0]['content']==e['content']
    assert len(after['world_state']['knowledge'])==2
    assert batch['knowledge_acquisitions'][0]['source_event_id'] in {r['id'] for r in batch['events']}
    assert not any(k['actor_id']=='child' for k in after['world_state']['knowledge'].values())
    again=command(after,'read',event_id=e['id']); assert again['world_state']==after['world_state']


def test_group_membership_delivery_snapshot_and_late_join():
    s=command(phone(),'create_group',label='Группа',member_ids=['b'])
    gid=next(iter(s['world_state']['conversations']))
    s=command(s,'send',conversation_id=gid,content='До вступления',operation_id='first-text')
    s=command(s,'join',conversation_id=gid,member_ids=['child'])
    old=next(iter(s['world_state']['remote_events'].values()));assert old['delivered_to']==['b']
    s=command(s,'send',conversation_id=gid,content='После вступления',operation_id='second-text')
    assert list(s['world_state']['remote_events'].values())[-1]['delivered_to']==['b','child']
    s=command(s,'remove',conversation_id=gid,member_ids=['child'])
    s=command(s,'send',conversation_id=gid,content='После выхода',operation_id='third-text')
    assert list(s['world_state']['remote_events'].values())[-1]['delivered_to']==['b']


@pytest.mark.parametrize('action,outcome',[('answer','answered'),('decline','declined'),('ignore','missed')])
def test_call_controls_preserve_physical_scene(action,outcome):
    s=phone();before=deepcopy(s['world_state']['camera']);s=incoming(s,'call','')
    e=next(iter(s['world_state']['remote_events'].values()));assert e['status']=='ringing'
    s=command(s,action,event_id=e['id'])
    assert s['world_state']['remote_events'][e['id']]['status']==outcome
    assert s['world_state']['camera']==before
    assert s['world_state']['characters']['b']['location_id']=='away'
    if action=='answer':
        assert s['world_state']['meta']['interaction_focus']=='call'
        s=command(s,'focus',focus='physical');assert s['world_state']['remote_events'][e['id']]['status']=='answered'
        s=command(s,'end',event_id=e['id']);assert s['world_state']['meta']['interaction_focus']=='physical'


def test_outgoing_does_not_assume_answer_and_canonical_timeout():
    s=command(phone(),'call',contact_id='a-b');e=next(iter(s['world_state']['remote_events'].values()))
    assert e['status']=='ringing'
    with pytest.raises(ValueError):command(s,'answer',event_id=e['id'])
    before=s['world_state']['characters']['b']['location_id']
    s['world_state']['meta']['world_time']=2;batch=WorldHistoryV3();advance(s['world_state'],batch)
    assert e['status']=='missed' and s['world_state']['characters']['b']['location_id']==before
    assert not s['world_state']['knowledge'].get('b:secret')


def test_unresolved_and_shared_identity_no_eager_character():
    s=command(phone(),'add_contact',label='Мастерская',address='workshop',kind='shared')
    cid=list(s['world_state']['contacts'])[-1]
    s=command(s,'call',contact_id=cid)
    assert len(s['world_state']['characters'])==4
    with pytest.raises(ValueError):resolve_identity(s,cid,address='workshop',evidence='Name',name='Иван')
    s=command(phone(),'add_contact',label='Неизвестный',address='number')
    cid=list(s['world_state']['contacts'])[-1]
    s=command(s,'send',contact_id=cid,content='Привет')
    assert list(s['world_state']['remote_events'].values())[-1]['status']=='sent'
    linked=resolve_identity(s,cid,address='number',evidence='Подтверждён владелец номера',character_id='b')
    assert len(linked['world_state']['characters'])==4
    fresh=resolve_identity(s,cid,address='number',evidence='Представился',name='Иван')
    assert len(fresh['world_state']['characters'])==5
    assert resolve_identity(fresh,cid,address='number',evidence='Представился',name='Иван')==fresh


def test_emergency_is_setting_destination_and_no_real_person():
    s=phone()
    with pytest.raises(ValueError):command(s,'call',service='medical')
    s['world_state']['meta']['communication'].update(region='fiction',emergency_numbers={'medical':'fiction-med'})
    after=command(s,'call',service='medical')
    event=next(iter(after['world_state']['remote_events'].values()))
    assert event['destination']=='fiction-med' and event['recipient_ids']==[]
    assert after['world_state']['characters']==s['world_state']['characters']


def test_event_first_eligibility_and_external_control():
    s=phone();s['world_state']['characters']['b']['intentions']=[dict(id='reason',text='Связаться',status='active',source_sequence=None,
        evidence='',due_minute=None,revision=0,source_event_id=None,dependencies={},review_required=[],reviewed_signature='')]
    options=opportunities(s['world_state']);assert options
    p=dict(actor_id='b',action='call',contact_id='b-a',basis_ids=['reason'])
    after,batch=accept(s,p,options,'npc-operation')
    assert next(iter(after['world_state']['remote_events'].values()))['status']=='ringing'
    assert batch['events'] and not s['world_state']['remote_events']
    with pytest.raises(ValueError):accept(s,dict(p,actor_id='a'),options,'invalid-actor')
    with pytest.raises(ValueError):accept(s,dict(p,contact_id='a-b'),options,'invalid-path')
    with pytest.raises(ValueError):accept(s,dict(p,knowledge_ids=['a:secret']),options,'invalid-knowledge')


def test_context_bounded_and_portrait_authorization():
    s=phone()
    for i in range(40):s=command(s,'send',contact_id='a-b',content='x'*2000,operation_id=f'text-{i:08}')
    ctx=context_projection(s['world_state']);assert len(ctx['recent'])==6
    assert len(json.dumps(ctx))<9000
    s['world_state']['contacts']['a-b']['identity_visible']=False
    c=projection(s)['contacts'][0];assert c['subject']['id']=='' and not c['subject']['portrait']


def test_qa_import_and_persisted_idempotency(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    repo=Repository(tmp_path/'phone.sqlite');sid=load_fixture(repo,'phone')['save']
    initial=repo.get_save(sid);p=initial['state']['phone'];assert p
    cmd=dict(action='send',operation_id='persistent-send',contact_id=p['contacts'][0]['id'],content='Авторский текст без изменений')
    after=repo.remote_action(sid,initial['revision'],cmd)
    duplicate=repo.remote_action(sid,initial['revision'],cmd)
    assert duplicate==after
    with pytest.raises(ValueError):repo.remote_action(sid,initial['revision'],dict(cmd,content='Подмена'))
    assert len(Repository(repo.path).get_snapshot(sid)['world_state']['remote_events'])==1


def test_atomic_event_first_retry_regenerate_variants_and_rollback(tmp_path):
    import engine
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import CONFIG, ordinary_job
    from backend.runtime_v3.models import Motivation
    repo=Repository(tmp_path/'lineage.sqlite');sid=load_fixture(repo,'phone')['save']
    ordinary_job(repo,sid,'start')
    s=repo.get_snapshot(sid)
    s['world_state']['characters']['qa_vera']['intentions']=[Motivation(id='call-reason',text='Обсудить встречу').model_dump()]
    with repo.connect() as db:db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(s),sid))
    before=repo.get_snapshot(sid);camera=before['world_state']['camera'];seen=[]
    proposal=dict(actor_id='qa_vera',action='call',contact_id='phone-qa_vera-qa-kirill',basis_ids=['call-reason'])
    def stream(**kw):
        if kw['messages'][0]['content'].startswith('Select at most ONE'):
            seen.append('plan');yield json.dumps({'action':proposal});return
        if not kw.get('response_format'):
            seen.append('narrative')
            current=json.loads(next(m['content'].split('\n',1)[1] for m in kw['messages'] if m['content'].startswith('Текущее состояние / GM-only\n')))
            assert current['communication']['recent'][0]['status']=='ringing'
            assert repo.get_save(sid)['state']['phone']['events']==[]  # atomic publication
            yield 'Телефон звонит. В комнате тихо.'
        else:
            yield json.dumps(dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=0),choices=[]))
    jid=repo.begin_job(sid,'Смотрю в окно.','turn',CONFIG)
    with patch('engine.find_loaded_model',return_value={'config':{'context_length':32768}}),patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,jid,engine.Worker())
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    after=repo.get_snapshot(sid);events=after['world_state']['remote_events'];assert len(events)==1
    original=repo.list_turns(sid)[-1]
    assert seen==['plan','narrative']
    def regenerated(**kw):
        assert not kw['messages'][0]['content'].startswith('Select at most ONE')
        yield json.dumps(dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=0),choices=[])) if kw.get('response_format') else 'Телефон продолжает звонить.'
    jid2=repo.begin_job(sid,'','regenerate',CONFIG)
    with patch('engine.find_loaded_model',return_value={'config':{'context_length':32768}}),patch('engine.chat_stream',side_effect=regenerated):
        engine.run_job(repo.path,jid2,engine.Worker())
    assert repo.get_job(jid2)['status']=='saved',repo.get_job(jid2)['error']
    assert repo.get_snapshot(sid)['world_state']['remote_events']==events
    repo.select_variant(sid,original['id'],original['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==after
    repo.rollback_last(sid);assert repo.get_snapshot(sid)==before
    assert not repo.get_save(sid)['state']['phone']['events']


def test_phone_ordinary_cycle_and_legacy_disabled(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job
    repo=Repository(tmp_path/'cycle.sqlite');sid=load_fixture(repo,'phone')['save']
    ordinary_job(repo,sid,'start');ordinary_job(repo,sid)
    saved=repo.get_snapshot(sid);repo=Repository(repo.path);assert repo.get_snapshot(sid)==saved
    ordinary_job(repo,sid);repo.rollback_last(sid);assert repo.get_snapshot(sid)==saved
    legacy=load_fixture(repo,'base')['save'];ordinary_job(repo,legacy,'start')
    assert repo.get_save(legacy)['state']['phone'] is None
