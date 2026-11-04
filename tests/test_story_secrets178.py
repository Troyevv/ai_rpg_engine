"""#178 privacy, classification, subject identity and source-bound perception."""
import json
from copy import deepcopy
import pytest
from backend.runtime_v3.models import Fact, Knowledge, assert_world_state_v3_invariants
from backend.runtime_v3.remote import apply
from backend.runtime_v3.remote_semantics import resolve, messages
from backend.runtime_v3.selectors import ui_view
from backend.runtime_v3.secrets import first_confirmations, legacy_secret_metadata
from backend.runtime_v3.protagonist import transition
from test_remote_communication import phone, incoming
from test_goals_values import raw
from backend.runtime_v3.resolver import StateResolver


def fixture():
    snap=phone();s=snap['world_state']
    s['facts']['plot']=Fact(id='plot',text='Соня скрывает авторство романа.',visibility='secret',story_secret=True,
        secret_subject_ids=['b'],secret_existence='discoverable').model_dump()
    s['knowledge']['b:plot']=Knowledge(actor_id='b',fact_id='plot').model_dump()
    return snap


def read(snap,eid,actor='a'):
    return apply(snap,dict(action='read',event_id=eid,operation_id='reading-'+eid+'-'+actor),actor_id=actor)


def classify(snap,eid,assertion='confirmed',facts=None):
    s=snap['world_state']
    return resolve(snap,eid,dict(final_scene=dict(location_id=s['camera']['location_id'],
        present_character_ids=s['camera']['present_character_ids'],elapsed_minutes=0),
        facts=facts or [],secret_disclosures=[dict(source_event_id=eid,fact_id='plot',assertion=assertion,evidence=s['remote_events'][eid]['content'])]))


def test_bread_private_read_and_safe_aliases():
    snap=incoming(fixture(),content='Купи хлеб');eid=next(iter(snap['world_state']['remote_events']))
    before=ui_view(snap)
    assert 'Купи хлеб' not in json.dumps(before,ensure_ascii=False)
    snap,batch=read(snap,eid)
    fact=next(f for f in snap['world_state']['facts'].values() if f['text']=='Сообщение: «Купи хлеб»')
    assert fact['visibility']=='secret' and not fact['story_secret']
    assert snap['world_state']['knowledge']['a:'+fact['id']]['status']=='known'
    view=ui_view(snap,batch)
    assert 'Купи хлеб' in json.dumps(view,ensure_ascii=False)
    assert all(not f.get('story_secret') for f in view['world']['facts'].values())
    assert view['story_secrets']['personal']['b'][0]['status']=='hidden'
    assert 'Соня скрывает' not in json.dumps(view,ensure_ascii=False)
    assert all(k['actor_id']=='a' for k in view['world']['knowledge'].values())


def test_semantics_before_read_is_pending_and_replay_does_not_duplicate():
    snap=incoming(fixture(),content='Это я написала роман.');eid=next(iter(snap['world_state']['remote_events']))
    snap,_=classify(snap,eid)
    assert 'a:plot' not in snap['world_state']['knowledge']
    before=deepcopy(snap['world_state']);snap,batch=read(snap,eid)
    assert snap['world_state']['knowledge']['a:plot']['status']=='known'
    assert len(first_confirmations(before,snap['world_state'],batch))==1
    assert sum(f['story_secret'] for f in snap['world_state']['facts'].values())==1
    again,history=read(snap,eid)
    assert again==snap and not history['knowledge_acquisitions']
    reclassified,h=classify(snap,eid)
    assert reclassified['world_state']['knowledge']==snap['world_state']['knowledge']
    assert not h['knowledge_acquisitions']
    view=ui_view(snap,batch)
    assert view['story_secrets']['personal']['b'][0]['text']=='Соня скрывает авторство романа.'
    assert view['story_secrets']['personal'].get('a') is None


def test_rumor_is_not_confirmation_then_other_read_source_confirms():
    snap=incoming(fixture(),content='Говорят, она написала роман.');eid=next(iter(snap['world_state']['remote_events']))
    snap,_=read(snap,eid);before=deepcopy(snap['world_state'])
    snap,h=classify(snap,eid,'rumor')
    assert snap['world_state']['knowledge']['a:plot']['status']=='suspected'
    assert not first_confirmations(before,snap['world_state'],h)
    snap,_=apply(snap,dict(action='send',contact_id='b-a',content='Да, это мой роман.',operation_id='second-confession'),actor_id='b',autonomous=True)
    eid=max(snap['world_state']['remote_events'].values(),key=lambda e:e['ordinal'])['id']
    snap,_=read(snap,eid);before=deepcopy(snap['world_state'])
    snap,h=classify(snap,eid)
    assert len(first_confirmations(before,snap['world_state'],h))==1
    assert snap['world_state']['knowledge']['a:plot']['revision']==2


def test_new_secret_in_same_operation_and_canonical_rollback():
    snap=fixture();del snap['world_state']['facts']['plot'];del snap['world_state']['knowledge']['b:plot']
    snap=incoming(snap,content='Я написала роман.');eid=next(iter(snap['world_state']['remote_events']))
    snap,_=read(snap,eid);before=deepcopy(snap)
    facts=[dict(id='plot',text='Соня написала роман.',visibility='secret',story_secret=True,secret_subject_ids=['b'],evidence='Я написала роман.')]
    after,h=classify(snap,eid,facts=facts)
    assert first_confirmations(before['world_state'],after['world_state'],h)[0]['kind']=='new'
    assert snap==before
    assert 'plot' not in ui_view(before)['world']['facts']
    variant,_=resolve(before,eid,dict(final_scene=dict(location_id=before['world_state']['camera']['location_id'],present_character_ids=before['world_state']['camera']['present_character_ids'],elapsed_minutes=0)))
    assert 'plot' not in variant['world_state']['facts']
    restored=json.loads(json.dumps(after))
    assert ui_view(restored)['story_secrets']==ui_view(after)['story_secrets']


def test_hidden_existence_camera_and_no_actor():
    snap=fixture();s=snap['world_state'];initial=ui_view(snap)['story_secrets']
    s['camera']['pov_actor_id']='b';s['camera']['subject_id']='b'
    assert ui_view(snap)['story_secrets']==initial
    s['facts']['sealed']=Fact(id='sealed',text='Скрыто даже существование',visibility='secret',story_secret=True,secret_subject_ids=['b']).model_dump()
    assert ui_view(snap)['story_secrets']==initial
    s['camera']['controlled_actor_id']=None;s['camera']['mode']='observer'
    view=ui_view(snap)
    assert view['story_secrets']==dict(personal={},world=[],revealed=[])
    assert not view['world']['knowledge']
    assert 'Соня скрывает' not in json.dumps(view,ensure_ascii=False)


def test_legacy_is_conservative_and_structural_not_text():
    assert not legacy_secret_metadata(dict(secret=True,text='Тайна убийства'),{'b':{}})['story_secret']
    assert legacy_secret_metadata(dict(secret=True,owner_id='b'),{'b':{}})['secret_subject_ids']==['b']
    snap=fixture();s=snap['world_state']
    for f in s['facts'].values():
        for key in ('story_secret','secret_subject_ids','secret_existence'):f.pop(key)
    loaded=assert_world_state_v3_invariants(s)
    assert loaded['facts']['plot']['story_secret'] is False
    assert loaded['knowledge']==s['knowledge']
    assert s['facts']['plot'].get('story_secret') is None


def test_existing_narrative_acquisition_and_world_secret():
    snap=fixture();s=snap['world_state'];s['facts']['plot']['secret_subject_ids']=[]
    p=raw(s,events=[dict(id='disclosure',text='Признание',evidence='Признание',participants=['a','b'],witnesses=['a'],fact_ids=['plot'],medium='conversation')],
          knowledge_gained=[dict(actor_id='a',fact_id='plot',source_event_id='disclosure',evidence='Признание')])
    r=StateResolver(s,'Признание','').resolve(p)
    assert len(first_confirmations(s,r.state,r.history))==1
    view=ui_view(dict(snap,world_state=r.state),r.history)
    assert view['story_secrets']['world'][0]['status']=='known'


def test_arbitrary_link_and_missing_read_cannot_grant_truth():
    snap=incoming(fixture(),content='Купи хлеб');eid=next(iter(snap['world_state']['remote_events']))
    payload=json.loads(messages(snap,eid)[1]['content'])
    assert 'secret_disclosures' in payload['schema']['properties']
    p=raw(snap['world_state'],secret_disclosures=[dict(source_event_id=eid,fact_id='plot',assertion='confirmed',evidence='Купи хлеб')])
    result=StateResolver(snap['world_state'],'Купи хлеб','').resolve(p)
    assert any(w['code']=='secret_disclosure_invalid' for w in result.warnings)
    assert 'a:plot' not in result.state['knowledge']


def test_group_only_actual_readers_acquire():
    snap=fixture()
    snap,_=apply(snap,dict(action='create_group',member_ids=['b','child'],label='Друзья',operation_id='secret-group-create'))
    cid=next(c['id'] for c in snap['world_state']['conversations'].values() if c['group'])
    snap,_=apply(snap,dict(action='send',conversation_id=cid,content='Это мой роман.',operation_id='secret-group-message'),actor_id='b',autonomous=True)
    eid=next(iter(snap['world_state']['remote_events']))
    snap,_=classify(snap,eid);snap,_=read(snap,eid)
    assert snap['world_state']['knowledge']['a:plot']['status']=='known'
    assert 'child:plot' not in snap['world_state']['knowledge']
    snap,_=read(snap,eid,'child')
    assert snap['world_state']['knowledge']['child:plot']['status']=='known'


def test_letter_link_is_bound_on_send_consumed_only_after_delivery_and_read():
    from test_historical_correspondence130 import letters, artifact, authored, extracted
    from test_narrative_phone138 import payload
    from backend.runtime_v3.long_term import advance_clock
    from backend.runtime_v3.models import WorldHistoryV3
    snap=fixture();snap['world_state']['meta']['communication'].update(letter=True,delivery_minutes={'letter':30})
    a=artifact();p=payload(snap['world_state'],[extracted(a)])
    p['secret_disclosures']=[dict(source_event_id='letter-1',fact_id='plot',assertion='confirmed',evidence=a['content'])]
    r=StateResolver(snap['world_state'],authored(a),'Жду.').resolve(p)
    snap['world_state']=r.state;e=next(iter(r.state['remote_events'].values()))
    assert len(e['secret_disclosures'])==1 and 'a:plot' not in r.state['knowledge']
    advance_clock(snap,e['delivery_due_at'],WorldHistoryV3().to_dict())
    assert 'a:plot' not in snap['world_state']['knowledge']
    snap,h=read(snap,e['id'])
    assert snap['world_state']['knowledge']['a:plot']['status']=='known'


def test_protected_condition_never_contributes_slots():
    from backend.runtime_v3.models import Condition
    snap=fixture();s=snap['world_state']
    baseline=ui_view(snap)['story_secrets']
    s['facts']['medical']=Fact(id='medical',text='PROTECTED MEDICAL',character_ids=['b'],visibility='secret',story_secret=True,secret_subject_ids=['b'],secret_existence='discoverable').model_dump()
    s['conditions']['medical']=Condition(id='medical',actor_id='b',description='PROTECTED MEDICAL',fact_id='medical').model_dump()
    assert ui_view(snap)['story_secrets']==baseline
    assert 'PROTECTED MEDICAL' not in json.dumps(ui_view(snap))


def test_draft_patch_handoff_and_api_author_separation(tmp_path):
    from backend.services.draft_world import patch
    from backend.runtime_v3.migration import migrate_v2
    from test_draft_world import fixture as draft_fixture
    from backend.api.app import create_app
    from fastapi.testclient import TestClient
    from devtools.narrative_test_world import load_fixture
    draft=draft_fixture()
    draft=patch(draft,'fact','meeting','story_secret',True)
    subject=draft['characters'][1]['id']
    draft=patch(draft,'fact','meeting','secret_subject_ids',[subject])
    draft=patch(draft,'fact','meeting','secret_existence','discoverable')
    canonical=migrate_v2(draft).snapshot['world_state']['facts']['meeting']
    assert canonical['story_secret'] and canonical['secret_subject_ids']==[subject]
    app=create_app(tmp_path/'secrets.sqlite',recover=False);repo=app.state.repository;client=TestClient(app)
    sid=load_fixture(repo,'phone')['save'];snap=repo.get_snapshot(sid)
    snap['world_state']['facts']['unknown']=Fact(id='unknown',text='UNSEEN-PLOT-178',story_secret=True,visibility='secret').model_dump()
    snap['campaign'].setdefault('sections',{})['knowledge']='RAW-SECRET-178'
    with repo.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snap),sid))
    r=client.get(f'/api/saves/{sid}');assert r.status_code==200
    assert 'UNSEEN-PLOT-178' not in r.text and 'RAW-SECRET-178' not in r.text
    author=client.get(f'/api/saves/{sid}/author-state');assert author.status_code==200
    assert 'UNSEEN-PLOT-178' in author.text and 'RAW-SECRET-178' in author.text


def test_private_new_fact_cannot_advertise_existence_before_read():
    snap=fixture();del snap['world_state']['facts']['plot'];del snap['world_state']['knowledge']['b:plot']
    snap=incoming(snap,content='Скрытое признание.');eid=next(iter(snap['world_state']['remote_events']))
    snap,_=classify(snap,eid,facts=[dict(id='plot',text='NEW PRIVATE SECRET',story_secret=True,
        visibility='secret',secret_subject_ids=['b'],secret_existence='discoverable',evidence='Скрытое признание.')])
    assert not ui_view(snap)['story_secrets']['personal']
    assert 'NEW PRIVATE SECRET' not in json.dumps(ui_view(snap))


def test_repository_regeneration_rollback_and_read_receipts(tmp_path):
    from test_phone122 import setup, dispatch, execute, read as api_read
    from test_narrative_test_world import CONFIG
    from backend.repositories.preparation import Repository
    repo,client,sid=setup(tmp_path)
    snap=repo.get_snapshot(sid);s=snap['world_state']
    s['facts']['plot']=Fact(id='plot',text='Вера тайно написала роман.',story_secret=True,visibility='secret',secret_subject_ids=['qa_vera']).model_dump()
    with repo.connect() as db: db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snap),sid))
    def semantic(value,data):
        reply=next(e for e in reversed(data['accepted_messages']) if e['sender_id']=='qa_vera')
        return dict(final_scene=data['final_scene'],secret_disclosures=[dict(source_event_id=reply['id'],fact_id='plot',assertion='confirmed',evidence=reply['content'])])
    jid=dispatch(repo,client,sid,'Ты написала роман?');execute(repo,jid,transform=semantic)
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    assert 'qa_kirill:plot' not in repo.get_snapshot(sid)['world_state']['knowledge']
    api_read(repo,client,sid)
    assert repo.get_snapshot(sid)['world_state']['knowledge']['qa_kirill:plot']['status']=='known'
    repo=Repository(repo.path)
    assert repo.get_save(sid)['state']['story_secrets']['revealed'][0]['id']=='plot'
    regen=repo.begin_job(sid,'','regenerate',CONFIG);execute(repo,regen,transform=semantic)
    assert repo.get_job(regen)['status']=='saved',repo.get_job(regen)['error']
    assert 'qa_kirill:plot' not in repo.get_snapshot(sid)['world_state']['knowledge']
    api_read(repo,client,sid)
    assert repo.get_snapshot(sid)['world_state']['knowledge']['qa_kirill:plot']['status']=='known'
    repo.rollback_last(sid)
    assert 'qa_kirill:plot' not in repo.get_snapshot(sid)['world_state']['knowledge']
    assert not repo.get_save(sid)['state']['story_secrets']['revealed']
