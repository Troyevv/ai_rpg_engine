"""Real E1/E2 replay and controlled provider tests; no live provider claims."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import pytest
from backend.services import draft_initial as initial, draft_repair as repair, draft_completeness as review
from backend.services.draft_calendar import complete, manual_edit
from backend.services.draft_intake import motivations
from backend.services.draft_quality import complete as quality
from test_initial_draft_v4 import rich

FIXTURES=Path(__file__).parent/'fixtures/initial_world'
EVIDENCE=[('generation_response_calendar.json','e1825af870cae2d8326bc2e70cbd8da43738c3fcd4d4852a569f04f0a7c19e58'),('generation_response_stability.json','9d4c22292be2ccd3bee8ba78e7c7b58f452a5d55521e412c5dc128c41b353372')]

def evidence(n=1):
    name,sha=EVIDENCE[n];data=(FIXTURES/name).read_bytes()
    assert hashlib.sha256(data).hexdigest()==sha
    return json.loads(data)

def reply(j,prefix):
    key=next(k for k in j['responses'] if k.startswith(prefix))
    return ''.join(p['text'] for p in j['responses'][key]['parts'])

@pytest.mark.parametrize('index',[0,1])
def test_actual_reports_preserve_bad_outputs_and_fail_closed(index):
    j=evidence(index);state=j['candidate_snapshot'];before=deepcopy(j)
    rejected=[];parsed=[]
    for slot,record in j['responses'].items():
        if not slot.startswith('completeness'):continue
        raw=''.join(p['text'] for p in record['parts'])
        try:parsed.extend(review.parse(raw,state))
        except review.ReportError as exc:rejected.extend(exc.errors)
    assert rejected and parsed
    assert all('report_path' in e and 'world_path' in e for e in rejected)
    assert j==before


def test_e2_partial_date_path_and_real_bad_repair_atomic():
    j=evidence();snapshot=j['candidate_snapshot'];before=deepcopy(snapshot)
    _,report=initial.inspect_candidate(snapshot)
    assert any(e['path']=='/world/residences/res_ilya/until_date' and e['category']=='calendar_date' for e in report['diagnostics'])
    # RECONSTRUCTION, not a historical snapshot: reverse only the last logged
    # repair on the exact candidate to exercise the recorded failing package.
    reconstructed=deepcopy(snapshot)
    reconstructed['world']['residences']['res_ilya'].update(status='active',until_date=None)
    for rid in ('res_timur','res_sonya','res_yura'):reconstructed['world']['residences'][rid]['location_id']='l2'
    raw=reply(j,'repair_921a4')
    paths=[p['path'] for p in json.loads(raw)['patches']]
    scope=repair.RepairScope(paths,reconstructed,set())
    # Isolate the typed trial boundary here; a separate assertion below tests
    # the missing semantic authorization for the recorded closure.
    scope.close_paths={p for p in paths if p.startswith('/world/residences/res_ilya/')}
    with pytest.raises(repair.RejectedTrial) as exc:repair.apply(json.dumps(reconstructed),raw,scope)
    assert exc.value.details['before_hash']!=exc.value.details['trial_hash']
    assert snapshot==before
    # Actual reviewer response cannot authorize a residence closure from travel.
    issues=review.parse(reply(j,'completeness_9603092f6de281d93802c23fd6c6c8e74ce235c885d7362c5c339e85f1627131_2_1'),reconstructed)
    _,scope=repair.request(json.dumps(reconstructed),issues)
    with pytest.raises(ValueError,match='Закрытие проживания'):
        repair.apply(json.dumps(reconstructed),json.dumps({'patches':[dict(path='/world/residences/res_ilya/status',value='closed')]}),scope)


def test_trial_rejects_plain_assignment_and_overlapping_operations():
    state=rich();raw=json.dumps(state);path='/world/roles/job/actor_id'
    _,scope=repair.request(raw,[{'path':path,'message':'wrong actor'}])
    with pytest.raises(repair.RejectedTrial):repair.apply(raw,json.dumps({'patches':[{'path':path,'value':'absent'}]}),scope)
    with pytest.raises(ValueError,match='пересекающиеся'):
        repair.apply(raw,json.dumps({'patches':[{'path':'/world/roles/job','value':{}},{'path':path,'value':'absent'}]}),scope)
    assert json.loads(raw)==state

@pytest.mark.parametrize('value,disproved',[(None,False),('',False),('  ',False),([],False),({},False),(0,True),(False,True)])
def test_missing_predicate_roundtrip(value,disproved):
    state=rich();state['campaign']['title']=value
    report={'issues':[dict(path='/campaign/title',message='missing',assertion='missing_value',target_path=None)]}
    out=review.parse(json.dumps(report),state)[0]
    assert (out['category']=='review_disproved')==disproved
    assert out['assertion']=='missing_value' and 'target_path' in out


def test_npc_short_goal_intake_and_manual_clear():
    state=rich();cid=next(c for c in state['world']['characters'] if c!=state['controlled_actor_id'])
    state['world']['characters'][cid].update(short_goal='Найти инструмент',goals=[])
    state=motivations(state)
    assert state['world']['characters'][cid]['goals']==['Найти инструмент']
    state=initial.normalize(state);state['world']['characters'][cid]['goals']=[]
    assert initial.normalize(state)['world']['characters'][cid]['goals']==[]


def test_duplicate_directed_pairs_and_conflicting_knowledge():
    state=rich();a,b=[c['id'] for c in state['characters'][:2]]
    state['world']['relationships']={'a':dict(source_id=a,target_id=b,dimensions={'trust':4},context='First'), 'b':dict(source_id=a,target_id=b,dimensions={'respect':8},context='Second'),'reverse':dict(source_id=b,target_id=a,dimensions={'trust':9},context='Reverse')}
    merged=initial.normalize(state)['world']['relationships']
    assert len(merged)==2 and merged['a']['dimensions']=={'trust':4,'respect':8}
    assert merged['a']['context']=='First\n\nSecond'
    state['world']['relationships']['b']['dimensions']['trust']=5
    with pytest.raises(initial.DraftErrors):initial.normalize(state)
    state=rich();state['world']['knowledge']={'a':dict(actor_id=a,fact_id='ownership',status='known'),'b':dict(actor_id=a,fact_id='ownership',status='unknown')}
    with pytest.raises(initial.DraftErrors):initial.normalize(state)


def test_server_clock_and_manual_edit_provenance():
    state=complete(rich(),'Сейчас 2026-10-23, 12:00.')
    expected=deepcopy(state['world_clock']);state['world_clock']['minute']+=999
    assert complete(state)['world_clock']==expected
    state['world_clock']['minute']=expected['minute']+60
    assert manual_edit(state,'/world_clock/minute')['world_clock']['minute']==expected['minute']+60

@pytest.mark.parametrize('invalid',[False,True])
def test_bounded_quality_rollback_and_rereview(invalid):
    state=initial.inspect_candidate(complete(rich()))[0];before=deepcopy(state);journal={};calls=[]
    path='/characters/1/fields/Привычки'
    issue=dict(path=path,message='Добавить пригодную для сцены привычку',severity='recommendation',assertion='optional_detail',category='semantic_completeness',patch_paths=[path])
    def call(slot,messages,stage):
        calls.append(slot)
        if slot.startswith('quality_review'):return json.dumps({'issues':[dict(path=path,message='Противоречие автору')] if invalid else []})
        return json.dumps({'patches':[dict(path=path,value='Перед трудным разговором аккуратно складывает очки.')]})
    result,checked=quality(state,[issue],'Идея',journal,call)
    assert len(calls)==2 and state==before
    assert (result==state)==invalid
    quality(result,[issue],'Идея',journal,lambda *a:pytest.fail('second quality batch'))

E3=FIXTURES/'generation_response_missing_reference.json'

def third():
    data=E3.read_bytes()
    assert hashlib.sha256(data).hexdigest()=='1963faa9457d186438678fee4d31be22fd622d0d346a2044488c8ba7a343dad4'
    return json.loads(data)


def test_actual_collection_reference_reports_and_correct_siblings():
    j=third();state=j['candidate_snapshot'];responses=[r for k,r in j['responses'].items() if k.startswith('completeness')]
    original=''.join(p['text'] for p in responses[0]['parts'])
    with pytest.raises(review.ReportError) as exc:review.parse(original,state)
    assert len(exc.value.errors)==3
    assert all('одиночный' in e['message'] and 'unhashable' not in e['message'] for e in exc.value.errors)
    assert [e['path'] for e in exc.value.issues]==['/world/facts/f1','/world/facts/f2']
    for record in responses[1:]:
        raw=''.join(p['text'] for p in record['parts'])
        try:
            merged=review.merge_correction(raw,original,exc.value.errors)
            with pytest.raises(review.ReportError) as err:review.parse(merged,state)
            assert [e['path'] for e in err.value.issues]==['/world/facts/f1','/world/facts/f2']
        except review.ReportError as err:
            assert 'по одному' in str(err)  # The actual empty correction cannot erase findings.


def test_missing_record_distinct_from_scalar_reference():
    s=rich();collection='/world/roles'
    issue=dict(path=collection,message='No occupation',assertion='missing_record',record_match={'actor_id':s['controlled_actor_id'],'kind':'occupation'},patch_paths=['/world/roles/new'])
    assert review.parse(json.dumps({'issues':[issue]}),s)[0]['category']=='review_disproved'
    issue['record_match']['actor_id']=s['characters'][1]['id']
    parsed=review.parse(json.dumps({'issues':[issue]}),s)[0]
    assert parsed['category']=='semantic_completeness' and parsed['record_match']==issue['record_match']
    for actual in ({},[],1,False,None):
        s['campaign']['title']=actual
        with pytest.raises(review.ReportError,match='одиночный'):
            review.parse(json.dumps({'issues':[dict(path='/campaign/title',message='missing',assertion='missing_reference',target_path=collection)]}),s)

from unittest.mock import patch
from test_initial_draft_v4 import api, REMOTE, wait_job

def test_e3_resume_keeps_candidate_siblings_and_stops_identical_corrections(api):
    client,app=api;j=third();repo=app.state.repository
    wid=client.post('/api/workspaces',json={'name':'E3 protocol replay'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    cfg=dict(REMOTE,context_length=262144,_draft_task='world',_draft_input=j['author_input']['text'],_creation_settings=j['candidate_snapshot'].get('creation_settings',{}))
    jid=repo.begin_preparation(wid,'draft_world',j['author_input']['text'],cfg,0)
    journal={'responses':{'world':deepcopy(j['responses']['world'])},'candidate_text':json.dumps(j['candidate_snapshot'],ensure_ascii=False),'recovery_epoch':0}
    repo.save_response_journal(jid,journal)
    repo.save_draft_candidate(jid,j['candidate_snapshot'],[],review=dict(status='failed',issues=[]))
    repo.preparation_progress(jid,'','error')
    actual=[ ''.join(p['text'] for p in r['parts']) for k,r in j['responses'].items() if k.startswith('completeness')][:2]
    calls=[]
    def stream(**kw):
        assert kw['messages'][0]['content'].startswith(review.MARKER), 'world must not regenerate'
        calls.append(kw);yield actual[min(len(calls)-1,1)]
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        d=client.get(url+'?author=true').json()
        assert client.post(url+'/resume',json={'revision':d['revision'],'api_key':'offline'}).status_code==200
        assert wait_job(client,jid)['status']=='error'
        assert len(calls)==3
        d=client.get(url+'?author=true').json()
        assert [i['path'] for i in d['review']['issues']]==['/world/facts/f1','/world/facts/f2']
        assert d['review']['status']=='failed' and not d['job']['resumable']
        assert client.post(url+'/resume',json={'revision':d['revision'],'api_key':'offline'}).status_code==409
        assert wait_job(client,jid)['status']=='error' and len(calls)==3
    raw=client.get(url+'/raw').json()
    assert raw['responses']['world']==j['responses']['world']
    assert raw['candidate_snapshot']['world']['facts']==j['candidate_snapshot']['world']['facts']


def test_explicit_zero_and_unknown_schedule_keep_legacy_compatibility():
    from backend.runtime_v3.calendar import scheduled_time
    state={'meta':{'world_time':100,'calendar':None}}
    assert scheduled_time(state,dict(time_semantics='explicit',due_minute=0))==dict(status='due',due_minute=0)
    assert scheduled_time(state,dict(time_semantics='explicit',due_minute=None))['status']=='unresolved'
    assert scheduled_time(state,dict(due_minute=0))['status']=='unresolved'


def test_player_legacy_goal_is_rejected_without_silent_discard():
    s=rich();cid=s['controlled_actor_id'];s['world']['characters'][cid].update(goals=[],short_goal='Согласиться на переезд')
    before=deepcopy(s)
    with pytest.raises(initial.DraftErrors) as exc:motivations(s)
    assert exc.value.errors[0]['category']=='player_agency' and s==before
    _,scope=repair.request(json.dumps(s),exc.value.errors,author_context='Герой ещё не принимал решение.')
    assert set(scope)=={'/world/characters/'+cid+'/short_goal','/world/characters/'+cid+'/goals'}


def test_id_remap_never_rewrites_prose_field_names():
    s=rich();old=s['characters'][0]['id'];bad='id with spaces'
    s['characters'][0]['id']=bad;s['characters'][0]['fields'][bad]='literal content'
    s['world']['characters'][bad]=s['world']['characters'].pop(old)
    s['protagonist_id']=s['controlled_actor_id']=bad
    result=initial.normalize(s)
    assert result['characters'][0]['fields'][bad]=='literal content'
    assert result['controlled_actor_id']!=bad

@pytest.mark.parametrize('reject',[False,True])
def test_optional_batch_api_and_unchanged_resume(api,reject):
    client,app=api;wid=client.post('/api/workspaces',json={'name':'Quality'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    calls=[];reviews=[];path='/characters/1/fields/Привычки';original=rich()
    def stream(**kw):
        system=kw['messages'][0]['content'];calls.append(system)
        if system.startswith(review.MARKER):
            reviews.append(system)
            yield json.dumps({'issues':[dict(path=path,message='Уточнить привычку',assertion='optional_detail',severity='recommendation',patch_paths=[path])] if len(reviews)==1 else []})
        elif 'patches' in system:
            yield json.dumps({'patches':[dict(path='/characters' if reject else path,value=[] if reject else 'Поправляет очки перед ответом.')]})
        else:yield json.dumps(original)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        r=client.post(url+'/generate',json={'revision':0,'text':'Мир мастерских','config':dict(REMOTE,context_length=262144),'api_key':'offline'})
        jid=r.json()['id'];job=wait_job(client,jid);assert job['status']=='saved',job
        d=client.get(url+'?author=true').json()
        assert d['state']['characters'][1]['fields']['Привычки']==(original['characters'][1]['fields']['Привычки'] if reject else 'Поправляет очки перед ответом.')
        if reject:assert any('дополнение не принято' in w for w in d['validation']['warnings'])
        count=len(calls)
        assert client.post(url+'/resume',json={'revision':d['revision'],'api_key':'offline'}).status_code==200
        assert wait_job(client,jid)['status']=='saved' and len(calls)==count


def test_partial_phase_year_cannot_become_invented_january_first():
    s=rich();s['world']['roles']['job']['since_date']='1370';raw=json.dumps(s)
    _,report=initial.inspect_candidate(s)
    _,scope=repair.request(raw,report['diagnostics'])
    date='/world/roles/job/since_date';context='/world/roles/job/context'
    with pytest.raises(ValueError,match='Неполный год'):
        repair.apply(raw,json.dumps({'patches':[dict(path=date,value='1370-01-01')]}),scope)
    updated=json.loads(repair.apply(raw,json.dumps({'patches':[dict(path=date,value=None),dict(path=context,value='Работает с 1370 года; точная дата неизвестна.')]}),scope))
    assert updated['world']['roles']['job']['since_date'] is None
    assert '1370' in updated['world']['roles']['job']['context']


def test_schedule_compatibility_flag_is_server_owned():
    from backend.services.draft_presentation import editor_contract
    assert 'time_semantics' not in editor_contract()['fields']['scheduled_events']
    state=rich();state['world']['scheduled_events']['plan']=dict(id='plan',description='План',participants=[],due_minute=None,status='pending',time_semantics='explicit')
    path='/world/scheduled_events/plan/time_semantics';raw=json.dumps(state)
    _,scope=repair.request(raw,[dict(path=path,message='Change interpretation')])
    with pytest.raises(ValueError):repair.apply(raw,json.dumps({'patches':[dict(path=path,value='legacy')]}),scope)
