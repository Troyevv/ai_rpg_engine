"""Real E5 export; gameplay/extraction replies here are synthetic, not user logs."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import pytest
from test_api import api, REMOTE, wait_job
from backend.runtime_v3.raw import RawTurnResult
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError

ROOT=Path(__file__).parent/'fixtures/runtime_handoff'
REMOTE=dict(REMOTE,context_length=131072) # Explicit large-world test configuration; production defaults unchanged.
WORLD_SHA='c01b7f16ceac3a650c85c960428b12ab57ac3884e0c786818abd31b431e0e98a'
NARRATIVE=json.loads((ROOT/'arrival_scenarios.json').read_text())['cases'][0]['narrative']

def source():
    data=(ROOT/'world.json').read_bytes()
    assert hashlib.sha256(data).hexdigest()==WORLD_SHA
    return json.loads(data)

def imported(client, value=None):
    w=client.post('/api/workspaces',json={'name':'Runtime handoff E5'}).json()
    url=f"/api/workspaces/{w['id']}/draft"
    r=client.post(url+'/import',json={'revision':w['revision'],'text':json.dumps(value or source(),ensure_ascii=False),'format':'json'})
    assert r.status_code==200,r.text
    d=client.get(url+'?author=true').json()
    r=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id'],'accept_warnings':True})
    assert r.status_code==200,r.text
    return r.json()['save']

def arrival(actor='viktoria_solovyova', evidence=NARRATIVE):
    return dict(final_scene=dict(location_id='ilya_cabinet',present_character_ids=['ilya',actor],elapsed_minutes=1),
                movements=[dict(actor_id=actor,from_location_id='salon_lak',to_location_id='ilya_cabinet',assertion='completed_arrival',actor_evidence='Виктория Соловьёва',destination_evidence='кабинет',evidence=evidence)])

def test_original_export_reaches_game_api_with_all_identities(api):
    client,app=api;sid=imported(client)
    expected={c['id']:c['name'] for c in source()['characters']}
    state=client.get(f'/api/saves/{sid}').json()['state']
    assert {c['id']:c['name'] for c in state['characters']}==expected
    assert state['controlled_actor_id']=='ilya'
    assert state['scene_meta']['present_ids']==['ilya']

def test_wrong_actor_cannot_borrow_viktoria_arrival_evidence(api):
    client,app=api;sid=imported(client);s=app.state.repository.get_snapshot(sid)
    with pytest.raises(StructuralDeltaError):
        StateResolver(s['world_state'],NARRATIVE,'',actor_names={c['id']:c['name'] for c in s['character_cards']}).resolve(RawTurnResult.parse(arrival('marina_volkova')))

def submit(client,sid,kind='start',text=''):
    save=client.get(f'/api/saves/{sid}').json()
    r=client.post(f'/api/saves/{sid}/turns',json=dict(kind=kind,text=text,revision=save['revision'],config=REMOTE,api_key='test-secret'))
    assert r.status_code==200,r.text
    return r.json()['id']

def snapshot_state(repo,sid):
    with repo.connect() as db:
        return dict(db.execute('SELECT state_json,revision FROM saves WHERE id=?',(sid,)).fetchone())

def test_real_start_repair_turn_reopen_next_turn(api):
    from storage import Storage
    client,app=api;sid=imported(client);repo=app.state.repository
    before=repo.get_snapshot(sid);calls=[]
    def provider(**kw):
        calls.append(kw)
        if not kw.get('response_format'):yield NARRATIVE;return
        raw=arrival()
        if sum(bool(c.get('response_format')) for c in calls)==1:raw.pop('movements')
        yield json.dumps(raw,ensure_ascii=False)
    with patch('engine.chat_stream',side_effect=provider):
        jid=submit(client,sid);job=wait_job(client,jid)
        assert job['status']=='saved',job.get('error')
        assert len(calls)==3
        assert sum(not c.get('response_format') for c in calls)==1
        first=repo.get_snapshot(sid)
        assert first['world_state']['camera']['present_character_ids']==['ilya','viktoria_solovyova']
        assert first['world_state']['characters']['viktoria_solovyova']['location_id']=='ilya_cabinet'
        assert first['world_state']['meta']['world_time']==before['world_state']['meta']['world_time']+1
        assert first['world_state']['knowledge']==before['world_state']['knowledge']
        for cid in set(before['world_state']['characters'])-{'viktoria_solovyova','ilya'}:
            assert first['world_state']['characters'][cid]['location_id']==before['world_state']['characters'][cid]['location_id']
        jid2=submit(client,sid,'turn','Я спрашиваю: «Как дела?»')
        assert wait_job(client,jid2)['status']=='saved'
        reopened=Storage(repo.path)
        assert reopened.get_snapshot(sid)==repo.get_snapshot(sid)
        assert len(client.get(f'/api/saves/{sid}').json()['state']['characters'])==19
        jid3=submit(client,sid,'turn','Я жду ответа.')
        assert wait_job(client,jid3)['status']=='saved'
    assert len(repo.list_turns(sid))==3
    assert repo.get_snapshot(sid)['world_state']['meta']['world_time']==before['world_state']['meta']['world_time']+3
    requests=repo.request_log(job_id=jid)
    assert {r['stage'] for r in requests}=={'narrative','extraction','extraction_repair'}
    assert all(r['status']!='running' for r in requests)
    assert all(r['cost_usd'] is None for r in requests)
    assert 'scene_arrival_unsupported' in json.dumps(requests,ensure_ascii=False)
    # Both bounded extraction attempts receive exactly the saved narrative.
    for r in requests:
        if r['stage'].startswith('extraction'):assert NARRATIVE in json.dumps(r['messages'],ensure_ascii=False)


def test_failed_extraction_retry_after_repository_reopen_is_atomic(api):
    from storage import Storage
    client,app=api;sid=imported(client);repo=app.state.repository
    before=snapshot_state(repo,sid)
    bad=arrival();bad.pop('movements')
    def rejected(**kw):yield json.dumps(bad) if kw.get('response_format') else NARRATIVE
    with patch('engine.chat_stream',side_effect=rejected):
        jid=submit(client,sid);job=wait_job(client,jid)
    assert job['status']=='error' and job['narrative_complete']
    assert snapshot_state(repo,sid)==before and not repo.list_turns(sid)
    original=repo.get_job(jid);logs=deepcopy(repo.request_log(job_id=jid))
    assert len(logs)==3 and all(r['status']!='running' for r in logs)
    assert len(json.loads(original['repair_diagnostics_json']))==2
    for kind in ('start','turn'):
        r=client.post(f'/api/saves/{sid}/turns',json=dict(kind=kind,text='Жду',revision=before['revision'],config=REMOTE,api_key='test-secret'))
        assert r.status_code==409
    reopened=Storage(repo.path)
    assert reopened.get_job(jid)['narrative']==NARRATIVE
    def repaired(**kw):
        assert kw.get('response_format'),'Narrative must not be regenerated on retry'
        yield json.dumps(arrival())
    with patch('engine.chat_stream',side_effect=repaired):
        r=client.post(f'/api/jobs/{jid}/retry',json=dict(config=REMOTE,api_key='test-secret'))
        assert r.status_code==200,r.text
        assert wait_job(client,jid)['status']=='saved'
    final=repo.get_job(jid)
    assert final['narrative']==original['narrative'] and final['before_json']==original['before_json']
    assert final['memory_before_json']==original['memory_before_json']
    assert len(repo.list_turns(sid))==1
    assert snapshot_state(repo,sid)['revision']==before['revision']+1
    assert client.post(f'/api/jobs/{jid}/retry',json=dict(config=REMOTE,api_key='test-secret')).status_code==409
    newlogs={r['id']:r for r in repo.request_log(job_id=jid)}
    assert all(newlogs[r['id']]==r for r in logs)


@pytest.mark.parametrize('change',[
    {'assertion':'future_arrival'}, {'assertion':'negated'}, {'assertion':'remote_contact'},
    {'actor_evidence':'Марина'}, {'destination_evidence':'улица'},
    {'from_location_id':'moscow'}, {'evidence':'Несуществующая цитата'},
    {'to_location_id':'salon_lak'},
])
def test_arrival_evidence_boundaries_are_atomic(api,change):
    client,app=api;sid=imported(client);snap=app.state.repository.get_snapshot(sid);before=deepcopy(snap)
    raw=arrival();raw['movements'][0].update(change)
    with pytest.raises(StructuralDeltaError):
        StateResolver(snap['world_state'],NARRATIVE,'',actor_names={c['id']:c['name'] for c in snap['character_cards']}).resolve(raw)
    assert snap==before


@pytest.mark.parametrize('parent',[True,False])
@pytest.mark.parametrize('elapsed',[0,1])
def test_arrival_independent_of_hierarchy_and_start_time(api,parent,elapsed):
    client,app=api;sid=imported(client);snap=app.state.repository.get_snapshot(sid);s=snap['world_state']
    if not parent:
        for loc in s['locations'].values():loc['parent_id']=None
    names={c['id']:c['name'] for c in snap['character_cards']}
    raw=arrival();raw['final_scene']['elapsed_minutes']=elapsed
    assert StateResolver(s,NARRATIVE,'',actor_names=names).resolve(raw).state['characters']['viktoria_solovyova']['location_id']=='ilya_cabinet'
    raw.pop('movements');raw['final_scene']['situation_evidence']=NARRATIVE
    with pytest.raises(StructuralDeltaError):StateResolver(s,NARRATIVE,'',actor_names=names).resolve(raw)


def test_legacy_snapshot_projection_context_and_history_are_read_only():
    from backend.runtime_v3.migration import migrate_v2
    from backend.runtime_v3.selectors import ui_view
    from backend.runtime_v3.context import build_context
    original=json.loads((ROOT/'legacy_snapshot.json').read_text());saved=deepcopy(original)
    migrated=migrate_v2(original).snapshot
    assert len(ui_view(migrated)['characters'])==19
    assert original==saved
    messages=build_context(migrated,[],'Виктория Соловьёва','start',32768,2000)
    text=json.dumps(messages,ensure_ascii=False)
    assert 'Виктория' in text and 'Илья' in text
    assert 'birth_date_provenance' not in text
    assert migrate_v2(migrated).snapshot==migrated


def test_birth_provenance_classifier_preserves_real_birth_and_manual_dob():
    from test_reproduction import conceive,deliver
    from backend.runtime_v3.birth_identity import is_game_birth,compatible_state
    from backend.runtime_v3.reproduction import known_birth
    s=deliver(conceive().state).state
    p=next(iter(s['pregnancies'].values()));cid=p['children'][0]['id']
    assert is_game_birth(s,cid)
    before=deepcopy(s['characters'][cid]['birth_provenance'])
    s['characters'][cid]['birth_date_provenance']={'source':'manual'}
    assert s['characters'][cid]['birth_provenance']==before
    assert is_game_birth(s,cid) and not known_birth(s,cid,'outsider')
    s['characters'][cid]['birth_provenance']={'source':'manual'}
    repaired=compatible_state(s)
    assert repaired['characters'][cid]['birth_provenance']['pregnancy_id']==p['id']
    assert is_game_birth(repaired,cid) and not known_birth(repaired,cid,'outsider')
    assert s['characters'][cid]['birth_provenance']=={'source':'manual'}


@pytest.mark.parametrize('metadata',[{}, {'source':'authoring_automatic','input_signature':'abc'}, {'source':'manual'}, {'source':'explicit'}, {'source':'unknown'}, {'twin_group':'twins'}])
def test_dob_metadata_is_not_birth_permission(metadata):
    from backend.runtime_v3.birth_identity import is_game_birth
    from backend.runtime_v3.reproduction import known_birth
    from backend.runtime_v3.kinship import visible_name
    from test_reproduction import state
    s=state();s['characters']['b']['birth_provenance']=metadata;s['characters']['b']['display_name']='Обычный ребёнок'
    assert not is_game_birth(s,'b') and known_birth(s,'b','a')
    assert visible_name(s,'b','a','Обычный ребёнок')=='Обычный ребёнок'


def test_exact_handoff_preserves_authored_graph_and_values(api):
    from backend.runtime_v3.repository import read_history
    client,app=api;sid=imported(client);repo=app.state.repository
    old=json.loads((ROOT/'legacy_snapshot.json').read_text());current=repo.get_snapshot(sid)
    # Baseline artifact was created using the real import/confirm API at 58c8e29.
    # New default DOB field is the sole shape addition; the original export is untouched.
    for cid,actor in old['world_state']['characters'].items():actor.setdefault('birth_date_provenance',{})
    assert current['world_state']==old['world_state']
    assert current['character_cards']==old['character_cards']
    assert current['authoring']==old['authoring']==source()['authoring']
    expected=json.loads((ROOT/'expectations.json').read_text())
    for section,count in expected['counts'].items():
        if section=='cards':value=current['character_cards']
        else:value=current['world_state']['characters' if section=='actors' else section]
        assert len(value)==count,(section,len(value),count)
    for identity in expected['identities']:
        actor=current['world_state']['characters'][identity['id']]
        assert actor['birth_date']==identity['birth_date']
        assert actor['location_id']==identity['initial_location']
    with repo.connect() as db:
        before=list(db.iterdump())
    for _ in range(2):client.get(f'/api/saves/{sid}');repo.get_snapshot(sid)
    with repo.connect() as db:assert list(db.iterdump())==before


def test_nonfixture_identity_and_unknown_birth_metadata_are_not_special_cased(api):
    from backend.runtime_v3.birth_identity import is_game_birth
    value=source()
    text=json.dumps(value,ensure_ascii=False).replace('ilya','other_protagonist').replace('Илья Александров','Другой герой')
    client,app=api;sid=imported(client,json.loads(text))
    view=client.get(f'/api/saves/{sid}').json()['state']
    assert next(c for c in view['characters'] if c['id']=='other_protagonist')['name']=='Другой герой'
    state=app.state.repository.get_snapshot(sid)['world_state']
    state['characters']['other_protagonist']['birth_provenance']={'unrecognized_process':'opaque'}
    assert is_game_birth(state,'other_protagonist')


def test_manual_dob_keeps_game_birth_metadata():
    from backend.services.draft_calendar import manual_edit
    from test_reproduction import conceive,deliver
    state=deliver(conceive().state).state
    child=next(iter(state['pregnancies'].values()))['children'][0]['id']
    actor=deepcopy(state['characters'][child]);before=deepcopy(actor['birth_provenance'])
    draft=dict(world=dict(characters={child:actor}),authoring={})
    manual_edit(draft,f'/world/characters/{child}/birth_date')
    assert actor['birth_provenance']==before
    assert actor['birth_date_provenance']['source']=='manual'


def test_epoch_stale_retry_cancel_and_duplicate_commit_guards(api):
    from storage import Storage
    client,app=api;sid=imported(client);repo=app.state.repository
    jid=repo.begin_job(sid,'','start',REMOTE)
    repo.job_progress(jid,'extracting',narrative=NARRATIVE,complete=True)
    old=Storage(repo.path);old.worker_epoch=0
    repo.job_progress(jid,'stopped')
    repo.retry_job(jid,REMOTE)
    old.job_progress(jid,'error',error='late worker')
    assert repo.get_job(jid)['status']=='extracting'
    repo.job_progress(jid,'validating')
    before=snapshot_state(repo,sid)
    with pytest.raises(ValueError):old.commit_job(jid,repo.get_snapshot(sid),[],{})
    assert snapshot_state(repo,sid)==before
    repo.job_progress(jid,'stopped')
    # Explicit revision change makes this narrative stale; no request can start.
    with repo.connect() as db:db.execute('UPDATE saves SET revision=revision+1 WHERE id=?',(sid,))
    with pytest.raises(ValueError,match='устарел'):repo.retry_job(jid,REMOTE)


def test_hidden_birth_has_no_id_fallback_in_relations_threads_or_camera():
    from test_reproduction import conceive,deliver,snap
    from backend.runtime_v3.models import Relationship,Thread
    from backend.runtime_v3.selectors import ui_view
    result=deliver(conceive().state);s=result.state
    child=next(iter(s['pregnancies'].values()))['children'][0]['id']
    s['camera'].update(controlled_actor_id='c',present_character_ids=['c'])
    s['relationships']['a:'+child]=Relationship(source_id='a',target_id=child).model_dump()
    s['threads']['secret_child']=Thread(id='secret_child',character_ids=[child],description='Private birth').model_dump()
    snapshot=snap(s);snapshot['character_cards'].extend(result.cards)
    snapshot['character_cards']=list({c['id']:c for c in snapshot['character_cards']}.values())
    view=ui_view(snapshot)
    for section in ('characters','relationships','plans','scene_meta'):
        assert child not in json.dumps(view[section])


def test_primary_provider_normalization_writes_dob_field_not_game_birth(api):
    from test_initial_draft_v4 import rich,SHORT
    from draft_provider_fixture import accept_semantics_unchecked
    client,app=api
    raw=rich()
    for card in raw['characters']:card['fields']['Возраст']='25 лет'
    for actor in raw['world']['characters'].values():
        actor['birth_date']=None;actor['birth_provenance']={}
    w=client.post('/api/workspaces',json={'name':'Synthetic primary normalization'}).json();url=f"/api/workspaces/{w['id']}/draft"
    @accept_semantics_unchecked
    def provider(**kw):yield json.dumps(raw,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        r=client.post(url+'/generate',json=dict(revision=0,text=SHORT,config=REMOTE,api_key='test',creation_settings={'calendar_start':{'date':'2026-10-23','time':'18:00'}}))
        assert r.status_code==200,r.text
        job=wait_job(client,r.json()['id']);assert job['status']=='saved',job.get('error')
    draft=client.get(url+'?author=true').json()
    actors=draft['state']['world']['characters']
    assert all(a['birth_date'] for a in actors.values())
    assert all(a['birth_date_provenance']['source']=='authoring_automatic' for a in actors.values())
    assert all(not a['birth_provenance'] for a in actors.values())
    r=client.post(url+'/confirm',json=dict(revision=draft['revision'],version_id=draft['version_id'],accept_warnings=True))
    assert r.status_code==200,r.text
    view=client.get(f"/api/saves/{r.json()['save']}").json()['state']
    assert {c['id']:c['name'] for c in view['characters']}=={c['id']:c['name'] for c in raw['characters']}


def test_e5_candidate_failed_review_handoff_keeps_every_name(api):
    from test_calendar_start_policy import install
    client,app=api;wid,jid,original,journal=install(client,app.state.repository)
    url=f'/api/workspaces/{wid}/draft';d=client.get(url+'?author=true').json()
    assert d['review']['status']=='failed'
    r=client.post(url+'/confirm',json=dict(revision=d['revision'],version_id=d['version_id'],accept_warnings=True))
    assert r.status_code==200,r.text
    view=client.get(f"/api/saves/{r.json()['save']}").json()['state']
    assert {c['id']:c['name'] for c in view['characters']}=={c['id']:c['name'] for c in original['characters']}
    assert not app.state.repository.request_log(save_id=r.json()['save'])


def test_malformed_real_birth_reference_has_explicit_diagnostic():
    from backend.runtime_v3.models import assert_world_state_v3_invariants
    from test_reproduction import state
    s=state();s['characters']['b']['birth_provenance']={'pregnancy_id':'missing','source':'manual'}
    with pytest.raises(ValueError,match='birth provenance'):
        assert_world_state_v3_invariants(s)


def test_old_save_restore_regenerate_variant_rollback_keeps_legacy_bytes(api):
    client,app=api;sid=imported(client);repo=app.state.repository
    snapshot=repo.get_snapshot(sid)
    old=json.loads((ROOT/'legacy_snapshot.json').read_text())
    # Restore the actual baseline canonical payload into a test save. Keep the
    # imported history head, which points at this DB's own immutable history.
    old['history_head']=snapshot['history_head']
    encoded=json.dumps(old,ensure_ascii=False)
    with repo.connect() as db:db.execute('UPDATE saves SET state_json=? WHERE id=?',(encoded,sid))
    assert len(client.get(f'/api/saves/{sid}').json()['state']['characters'])==19
    assert snapshot_state(repo,sid)['state_json']==encoded
    def provider(**kw):yield json.dumps(arrival()) if kw.get('response_format') else NARRATIVE
    with patch('engine.chat_stream',side_effect=provider):
        jid=submit(client,sid);assert wait_job(client,jid)['status']=='saved'
        first=repo.list_turns(sid)[0];saved=repo.get_snapshot(sid);first_before=repo.get_job(jid)['before_json']
        regen=submit(client,sid,'regenerate');assert wait_job(client,regen)['status']=='saved'
    repo.select_variant(sid,first['id'],first['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==saved
    repo.rollback_last(sid)
    assert {c['id']:c['name'] for c in repo.get_save(sid)['state']['characters']}=={c['id']:c['name'] for c in old['character_cards']}
    with repo.connect() as db:
        variants=[json.loads(r[0]) for r in db.execute('SELECT payload FROM response_variants WHERE save_id=?',(sid,))]
    assert len(variants)==2
    assert next(v for v in variants if v['active_variant_id']==first['active_variant_id'])['before_json']==first_before
    assert not repo.list_turns(sid)


def test_context_retains_bounded_identity_and_typed_arrival_contract():
    from backend.runtime_v3.context import build_context
    original=json.loads((ROOT/'legacy_snapshot.json').read_text())
    narrative=build_context(original,[],'','start',131072,2000)
    extraction=build_context(original,[],'','start',131072,4096,extraction_text=NARRATIVE)
    def block(messages,title):return json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith(title+'\n')))
    cards=block(narrative,'Карточки присутствующих / GM-only')
    assert [c['id'] for c in cards]==['ilya']
    index=block(narrative,'Индекс персонажей')
    assert any(c['id']=='viktoria_solovyova' and 'Виктория' in c['name'] for c in index)
    current=block(extraction,'Текущее состояние / GM-only')
    assert current['camera']['present_character_ids']==['ilya']
    assert current['characters']['viktoria_solovyova']['location_id']=='salon_lak'
    schema=block(extraction,'JSON Schema')['properties']['movements']['items']['properties']
    assert {'actor_evidence','destination_evidence','from_location_id','assertion'}<=schema.keys()
    assert 'completed_arrival' in str(extraction)
    assert len(cards)<len(original['character_cards'])
