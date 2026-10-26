"""Final-contract regressions. Historical bytes first; continuation is controlled, not live."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import pytest
from backend.services import draft_completeness as review, draft_repair as repair
from backend.services.draft_review_recovery import obtain
from backend.services.draft_calendar import complete
from backend.services.draft_presentation import clock_view
from backend.repositories.drafts import candidate_hash
from test_initial_draft_v4 import api, rich as raw_rich, REMOTE, wait_job
from backend.services.draft_initial import inspect_candidate
def rich():return inspect_candidate(raw_rich())[0]

E4=Path(__file__).parent/'fixtures/initial_world/generation_response_final.json'
SHA='bce102a6c848ab4f5e7d83e7654668efe0b1f0ad5b55c53724b2fe8c2e7b155a'
def evidence():
    assert hashlib.sha256(E4.read_bytes()).hexdigest()==SHA
    return json.loads(E4.read_bytes())

def test_e4_actual_bad_reports_never_crash_or_grant_collection_mutation():
    j=evidence();s=j['candidate_snapshot'];assert j['candidate_version']==366
    failures=[]
    for slot,record in j['responses'].items():
        if not slot.startswith('completeness'):continue
        raw=''.join(p['text'] for p in record['parts'])
        try:review.parse(raw,s)
        except review.ReportError as exc:
            failures.append(exc)
            assert all('unhashable' not in e['message'] for e in exc.errors)
            assert not any(p in ('/world/roles','/world/residences','/world/objective_relations') for i in exc.issues for p in i.get('patch_paths',[]))
    assert len(failures)>=7

@pytest.mark.parametrize('actual',[{},[],0,False,None,1.2])
def test_reference_type_matrix(actual):
    state=rich();state['campaign']['title']=actual
    with pytest.raises(review.ReportError):
        review.parse(json.dumps({'issues':[dict(path='/campaign/title',assertion='missing_reference',target_path='/world/roles',message='reference')]}),state)


def test_record_symmetry_invalid_match_and_stable_split_identity():
    s=rich();a,b=[c['id'] for c in s['characters'][:2]]
    s['world']['objective_relations']={'pair':dict(id='pair',kind='sibling',source_id=a,target_id=b,status='active')}
    issue=dict(section='objective_relations',record_match=dict(kind='sibling',source_id=b,target_id=a),assertion='missing_record',message='missing')
    assert review.parse(json.dumps({'issues':[issue]}),s)[0]['category']=='review_disproved'
    issue['record_match']['kind']='invented'
    with pytest.raises(review.ReportError):review.parse(json.dumps({'issues':[issue]}),s)
    good=dict(path='/campaign/title',message='Keep sibling',patch_paths=['/campaign/title'])
    old=json.dumps({'issues':[issue,good]});errors=[dict(report_path='/issues/0/assertion')]
    replacement=dict(issue,record_match=dict(kind='friend',source_id=a,target_id=b))
    reply=json.dumps({'replacements':[dict(issue_id=review.issue_identity(issue),issues=[replacement,dict(replacement,record_match=dict(kind='coworker',source_id=a,target_id=b))])]})
    merged=json.loads(review.merge_correction(reply,old,errors))
    assert merged['issues'][-1]==good and len(merged['issues'])==3


def test_advisory_wrong_basis_does_not_block_or_authorize_patch():
    s=rich();issue=dict(path='/campaign/title',assertion='optional_detail',message='advice',patch_paths=['/campaign/title'],basis=[dict(path='/campaign/title',value='wrong')])
    out=review.parse(json.dumps({'issues':[issue]}),s)[0]
    assert out['severity']=='recommendation' and not out['patch_paths'] and out['protocol_warnings']


def test_two_append_operations_and_scene_location_are_atomic():
    s=rich();ids=[c['id'] for c in s['characters'][:2]]
    paths=['/world/residences/a','/world/residences/b'];scope=repair.RepairScope(paths,s,{'a','b'})
    ops=[]
    for n,cid in zip(('a','b'),ids):
        ops.extend([dict(op='add_location',path='/locations/-',value=dict(id='home_'+n,name='Жильё '+n,text='Известное жильё')),dict(path='/world/residences/'+n,value=dict(id=n,actor_id=cid,location_id='home_'+n))])
    payload=dict(candidate_hash=candidate_hash(s),patches=ops)
    forward=json.loads(repair.apply(json.dumps(s),json.dumps(payload),scope))
    payload['patches']=list(reversed(ops));reverse=json.loads(repair.apply(json.dumps(s),json.dumps(payload),scope))
    assert forward['world']==reverse['world']
    assert {x['id'] for x in forward['locations']}=={x['id'] for x in reverse['locations']}
    payload['patches']=ops+[ops[0]]
    with pytest.raises(ValueError):repair.apply(json.dumps(s),json.dumps(payload),scope)
    sid=s['camera']['scene_id'];path='/world/scenes/'+sid+'/location'
    _,scope=repair.request(json.dumps(s),[dict(path=path,message='Scene needs its own location')])
    payload=dict(candidate_hash=candidate_hash(s),patches=[dict(op='add_location',path='/locations/-',value=dict(id='scene_place',name='Место сцены',text='')),dict(path=path,value='scene_place')])
    # Scene participants must move together; scope must authorize those dependencies.
    for cid in s['world']['scenes'][sid]['participants']:
        scope.append('/world/characters/'+cid+'/location');payload['patches'].append(dict(path=scope[-1],value='scene_place'))
    assert json.loads(repair.apply(json.dumps(s),json.dumps(payload),scope))['world']['scenes'][sid]['location']=='scene_place'


def test_gregorian_metadata_and_effective_leap_projection_are_read_only():
    s=rich();profile=s['world_clock']['calendar']['profile']
    profile.update(month_names=[str(i) for i in range(12)],weekday_names=['a','b','c','d','e','f','g'],seasons=[dict(name='Весна',month=3,day=1)],observances=[dict(id='festival',name='Праздник города',month=5,day=4,character_ids=[])])
    s['creation_settings']={'calendar_start':{'mode':'gregorian','date':'2024-02-28'}}
    out=complete(s);assert out['world_clock']['calendar']['profile']['month_names']==profile['month_names']
    before=deepcopy(out);view=clock_view(out['world_clock'])
    assert view['effective']['month_lengths'][1]==29 and view['effective']['weekday_names']==profile['weekday_names']
    assert out==before
    assert view['effective']['seasons']==profile['seasons'] and view['effective']['observances']==profile['observances']


def substantive_issues():
    issues=[]
    for a,b,kind in [('c2','c1','parent'),('c2','c8','parent'),('c7','c1','parent'),('c7','c8','parent'),('c1','c8','sibling'),('c1','c3','friend'),('c1','c4','friend'),('c1','c6','friend'),('c4','c5','close_friend'),('c1','c5','close_friend')]:
        issues.append(dict(section='objective_relations',assertion='missing_record',record_match=dict(source_id=a,target_id=b,kind=kind),message='Известная связь должна иметь структурированную запись.'))
    for cid in ('c3','c4','c6'):
        issues.append(dict(section='roles',assertion='missing_record',record_match=dict(actor_id=cid,kind='occupation'),message='Известная профессия.'))
    issues.append(dict(section='roles',assertion='missing_record',record_match=dict(actor_id='c8',kind='military',status='closed'),message='Автор задал прежнее звание и последующее лишение званий; точный день не задан.'))
    for cid in ('c2','c7','c8'):
        issues.append(dict(section='residences',assertion='missing_record',record_match=dict(actor_id=cid,location_id='l2'),message='Жильё установлено биографией и сценой семьи.'))
    for fid in ('f1','f2'):
        issues.append(dict(path='/world/facts/'+fid+'/character_ids',message='Участники факта отличаются от знающих.',patch_paths=['/world/facts/'+fid+'/character_ids']))
    for item in ('rifle','pack','tickets'):
        issues.append(dict(path='/world/possessions/'+item,message='Автор явно задал имущество.',patch_paths=['/world/possessions/'+item]))
    for path,message in [('/world/characters/c5/intentions','Катя намерена предложить поездку; решение Ильи не принято.'),('/world/scheduled_events/south_plan','Поездка предложена, точный срок и согласие Ильи не заданы.'),('/world/threads/t2/state','Илья ещё на вокзале, поездка домой не выполнена.'),('/world/threads/t2/public_state','Не выдавай будущий путь за текущее действие.')]:
        issues.append(dict(path=path,message=message,patch_paths=[path]))
    return issues


@pytest.mark.parametrize('evidence_number,manual_edit',[(4,False),(4,True),(3,False)])
def test_e4_candidate366_resume_repair_quality_start_turn_reload_next(api,evidence_number,manual_edit):
    from test_generation_stability import third
    client,app=api;j=evidence() if evidence_number==4 else third();repo=app.state.repository;s=deepcopy(j['candidate_snapshot'])
    wid=client.post('/api/workspaces',json={'name':'E4 exact 366'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    cfg=dict(REMOTE,context_length=262144,_draft_task='world',_draft_input=j['author_input']['text'],_creation_settings=s.get('creation_settings',{}))
    jid=repo.begin_preparation(wid,'draft_world',j['author_input']['text'],cfg,0)
    journal={k:deepcopy(v) for k,v in j.items() if k not in ('requests','recovery','binding','candidate_snapshot','candidate_version','current_diagnostics','current_start_block_reason','author_input')}
    journal.update(candidate_text=json.dumps(s,ensure_ascii=False),recovery_epoch=0)
    repo.save_response_journal(jid,journal);repo.save_draft_candidate(jid,s,[],review=j['recovery']['review']);repo.preparation_progress(jid,'','error')
    d=client.get(url+'?author=true').json();assert d['review']['status']=='failed'
    # A real manual change must survive every subsequent model stage.
    if manual_edit:d=client.patch(url+'/candidate',json={'revision':d['revision'],'path':'/campaign/title','value':'Возвращение — авторская версия'}).json()
    else:
        assert d['candidate']==s
        assert json.loads(repo.preparation_job(jid)['response_journal'])['candidate_text']==json.dumps(s,ensure_ascii=False)
    assert 'revision' in d,d
    responses=[''.join(p['text'] for p in r['parts']) for k,r in j['responses'].items() if k.startswith('completeness')]
    actual=responses[-1]
    original=next((r for r in responses if any(i.get('assertion')=='missing_record' and i.get('path') is None for i in json.loads(r)['issues'])),responses[0])
    calls=[]
    def provider(**kw):
        system=kw['messages'][0]['content'];payload=json.loads(kw['messages'][1]['content']);calls.append(system)
        if system.startswith(review.MARKER):
            if payload.get('strategy')=='scoped_reaudit':
                rows=[]
                for i,pending in enumerate(payload['pending_issues']):
                    rows.append(dict(issue_id=pending['issue_id'],resolution='replaced' if i==0 else 'disproved',reason='Сверено с авторской идеей и биографиями. Источник знания может быть исходным, событие не обязательно.',basis=[dict(path='/world/knowledge'),dict(path='/characters')],issues=substantive_issues() if i==0 else []))
                yield json.dumps({'resolutions':rows});return
            if 'rejected_response' in payload:
                yield actual;return
            if not any('альтернатив' in c for c in calls) and not payload['candidate']['world']['roles']:
                # Contract upgrades may start with an audit rather than reuse a stale report.
                yield original;return
            yield '{"issues":[]}';return
        assert 'patches' in system, 'Primary world generation is forbidden during Resume'
        patches=[]
        for e in payload['errors']:
            path=e['path']
            if path.startswith('/world/objective_relations/') or path.startswith('/world/roles/') or path.startswith('/world/residences/'):
                record=dict(e['record_match'],id=path.split('/')[-1],context='Авторская идея и биография персонажа.')
                if path.startswith('/world/roles/'):record['title']={'c3':'Автомеханик','c4':'Биолог','c6':'Помощник прокурора','c8':'Бывший лейтенант, лишён всех званий на втором году войны'}[record['actor_id']]
                value=record
            elif path.endswith('/character_ids'):value=['c1'] if '/f1/' in path else ['c8']
            elif path.startswith('/world/possessions/'):
                ident=path.split('/')[-1];owner='c5' if ident=='tickets' else 'c1'
                value=dict(id=ident,name={'rifle':'Винтовка','pack':'Рюкзак с вещами и трофеями','tickets':'Билеты на юг'}[ident],kind='item',owner_id=owner,holder_id=owner)
            elif path=='/world/characters/c5/intentions':value=['Предложить Илье поездку на юг и временное проживание у себя; его ответ ещё не получен.']
            elif path=='/world/scheduled_events/south_plan':value=dict(id='south_plan',description='Катя предлагает совместную поездку на юг.',character_ids=['c5'],due_minute=None,status='pending',condition='Только если Илья согласится; дата не определена.',type='planned_trip',commitment=False)
            elif path.startswith('/world/threads/t2/'):value='Илья на вокзале; Катя говорит, что семья ждёт его дома. Он ещё не ответил.'
            elif path.startswith('/characters/'):
                i=int(path.split('/')[2]);field=path.split('/')[-1]
                value={'Внешность':{1:'Каштановые волосы собраны у затылка, мягкий домашний кардиган.',2:'Коротко стрижен, на пальцах въевшиеся следы машинного масла.',4:'Прямые русые волосы, светлый жакет и удобные кеды.',5:'Аккуратная короткая стрижка, рубашка с закатанными рукавами.',6:'Седеющие виски, прямая осанка, простая тёмная рубашка.',7:'Короткие волосы, усталый внимательный взгляд, поношенная куртка.'}}.get(field,{}).get(i,'Перед ответом делает паузу и смотрит собеседнику в глаза.')
            else:raise AssertionError(path)
            if not any(p['path']==path for p in patches):patches.append(dict(path=path,value=value))
        yield json.dumps(dict(candidate_hash=payload['candidate_hash'],patches=patches),ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        response=client.post(url+'/resume',json={'revision':d['revision'],'api_key':'offline'})
        assert response.status_code==200,response.text
        job=wait_job(client,jid);assert job['status']=='saved',(job.get('error'),client.get(url+'/raw').json().get('review_failures',[])[-1:])
        d=client.get(url+'?author=true').json();ready=d['state'];assert ready
        assert ready['campaign']['title']==('Возвращение — авторская версия' if manual_edit else s['campaign']['title'])
        assert ready['world']['knowledge']==s['world']['knowledge']
        assert ready['world']['relationships']==s['world']['relationships']
        assert ready['world']['facts']['f1']['character_ids']==['c1']
        assert ready['world']['facts']['f2']['character_ids']==['c8']
        assert len(ready['characters'])==8
        pairs={(r['source_id'],r['target_id'],r['kind']) for r in ready['world']['objective_relations'].values()}
        assert {('c2','c1','parent'),('c2','c8','parent'),('c7','c1','parent'),('c7','c8','parent'),('c1','c8','sibling'),('c1','c5','close_friend')}<=pairs
        assert any(r['actor_id']=='c8' and r['status']=='closed' and r.get('until_date') is None for r in ready['world']['roles'].values())
        assert not any(r['actor_id']=='c1' for r in ready['world']['residences'].values())
        assert ready['world']['characters']['c1']['intentions']==s['world']['characters']['c1']['intentions']
        assert ready['world']['scheduled_events']['south_plan']['due_minute'] is None
        assert ready['world']['scheduled_events']['south_plan']['status']=='pending'
        assert ready['world']['characters']['c5']['intentions']
        assert ready['world_clock']==s['world_clock']
        for cid in s['world']['characters']:assert ready['world']['characters'][cid]['birth_date']==s['world']['characters'][cid]['birth_date']
        assert not any(c['fields']['Внешность']=='неизвестно' for c in ready['characters'])
        n=len(calls);assert client.post(url+'/resume',json={'revision':d['revision'],'api_key':'offline'}).status_code==200
        assert wait_job(client,jid)['status']=='saved' and len(calls)==n
    d=client.get(url+'?author=true').json();started=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id']});assert started.status_code==200,started.text
    from test_runtime_v3_engine import run as play,raw_for
    from test_engine import CONFIG
    from backend.repositories.preparation import Repository
    sid=started.json()['save']
    for kind in ('start','turn','turn'):
        before=repo.get_snapshot(sid);job=repo.begin_job(sid,'Осматриваюсь.' if kind=='turn' else '',kind,dict(CONFIG,context_length=262144))
        play(repo,job,raw_for(before));assert repo.get_job(job)['status']=='saved',repo.get_job(job)
        snapshot=repo.get_snapshot(sid);repo=Repository(repo.path);assert repo.get_snapshot(sid)==snapshot
        assert len(snapshot['world_state']['characters'])==8
        assert snapshot['world_state']['knowledge']['c5:f1']['status']=='known'
        assert snapshot['world_state']['possessions']['tickets']['owner_id']=='c5'
        assert snapshot['world_state']['scheduled_events']['south_plan']['status']=='pending'
    exported=client.get(url+'/raw').json()
    assert exported['responses']['world']==j['responses']['world']
    assert hashlib.sha256(E4.read_bytes()).hexdigest()==SHA


def test_quality_empty_review_still_completes_and_author_unknown_can_remain():
    from backend.services import draft_quality as quality
    s=rich();path='/characters/1/fields/Внешность';s['characters'][1]['fields']['Внешность']='неизвестно'
    source='Внешность второго персонажа намеренно неизвестна.';journal={};calls=[]
    def provider(slot,messages,stage):
        calls.append(stage)
        if stage=='draft_world_quality':return json.dumps(dict(patches=[],preserved_unknown=[dict(path=path,author_excerpt=source)]))
        return json.dumps(dict(issues=[],unknown_confirmations=[dict(path=path,actor_id=s['characters'][1]['id'],field='Внешность',decision='preserve',reason='Автор явно оставил внешность второго персонажа неизвестной.')]))
    out,_=quality.complete(s,[],source,journal,provider)
    assert out==s and journal['quality']['status']=='accepted'
    assert calls==['draft_world_quality','draft_world_validation']
    quality.complete(s,[],source,journal,lambda *a:pytest.fail('identical quality retry'))


def test_manual_field_protected_against_direct_and_indirect_repair():
    from backend.services.draft_world import patch as edit
    s=rich();cid=s['characters'][1]['id'];s=edit(s,'character',cid,'fields.Биография','Авторская биография.')
    path='/characters/1/fields/Биография';_,scope=repair.request(json.dumps(s),[dict(path=path,message='Model disagrees')])
    with pytest.raises(ValueError,match='ручное значение'):
        repair.apply(json.dumps(s),json.dumps({'patches':[dict(path=path,value='Модель переписала')]}),scope)


def test_contract_upgrade_releases_old_stop_but_not_new_exhaustion():
    state=rich();journal={'review_no_progress':['old'],'accepted_reviews':{}};calls=[]
    def provider(slot,messages):calls.append(slot);return '{"issues":[]}'
    result=obtain(state,review.messages(state,'Идея'),'new_contract',journal,provider,lambda:None)
    assert result==[] and len(calls)==1
    assert obtain(state,review.messages(state,'Идея'),'new_contract',journal,lambda *a:pytest.fail('duplicate'),lambda:None)==[]


def test_cancelled_review_has_terminal_projection(api):
    client,app=api;repo=app.state.repository
    wid=client.post('/api/workspaces',json={'name':'Interrupted review'}).json()['id']
    jid=repo.begin_preparation(wid,'draft_world','',dict(REMOTE,_draft_task='world',_draft_input=''),0)
    repo.save_draft_candidate(jid,rich(),[],review=dict(status='running',issues=[]))
    repo.preparation_progress(jid,'','stopped','Cancelled')
    assert repo.draft(wid,True)['review']['status']=='failed'


def test_hidden_intrinsic_error_is_not_misreported_as_new_damage():
    s=rich();cid=s['characters'][0]['id'];lid=s['locations'][0]['id']
    s['world']['roles']=42
    s['world']['residences']={'home':dict(id='home',actor_id=cid,location_id=lid,since_date='2022')}
    before=inspect_candidate(s)[1]['diagnostics'];assert before
    path='/world/roles';scope=repair.RepairScope([path],s,set())
    result=json.loads(repair.apply(json.dumps(s),json.dumps({'patches':[dict(path=path,value={})]}),scope))
    assert any(e['path']=='/world/residences/home/since_date' for e in inspect_candidate(result)[1]['diagnostics'])
    bad=deepcopy(result);bad['world']['residences']['home']['location_id']='nonexistent'
    with pytest.raises(repair.RejectedTrial):repair.validate_trial(s,bad)

@pytest.mark.parametrize('authored',[False,True])
def test_model_player_goal_recovery_preserves_source_agency(api,authored):
    client,app=api;s=rich();cid=s['controlled_actor_id']
    s['world']['characters'][cid].update(short_goal='Поехать на юг',goals=[])
    source='Автор задаёт цель героя: поехать на юг.' if authored else 'Герой ещё не решил, поедет ли он на юг.'
    wid=client.post('/api/workspaces',json={'name':'Agency recovery'}).json()['id'];url=f'/api/workspaces/{wid}/draft';calls=[]
    def provider(**kw):
        system=kw['messages'][0]['content'];calls.append(system)
        if system.startswith(review.MARKER):yield '{"issues":[]}';return
        if 'patches' in system:
            payload=json.loads(kw['messages'][1]['content']);assert source in payload['author_context']
            yield json.dumps({'patches':[dict(path='/world/characters/'+cid+'/short_goal',value='Поехать на юг' if authored else ''),dict(path='/world/characters/'+cid+'/goals',value=['Поехать на юг'] if authored else [])]});return
        yield json.dumps(s)
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        response=client.post(url+'/generate',json=dict(revision=0,text=source,config=dict(REMOTE,context_length=262144),api_key='offline'))
        jid=response.json()['id'];job=wait_job(client,jid);assert job['status']=='saved',job
    ready=client.get(url+'?author=true').json()['state']['world']['characters'][cid]
    assert bool(ready['goals']) is authored and not ready['intentions']
    assert len(calls)==3


def test_browser_provider_protocol_recovers_after_known_outage(api):
    from draft_provider_fixture import protocol_review
    def stream(**kw):
        if kw['messages'][0]['content'].startswith(review.MARKER):yield protocol_review(json.loads(kw['messages'][1]['content'])) or '{"issues":[]}'
        else:yield json.dumps(rich())
    client,app=api
    wid=client.post('/api/workspaces',json={'name':'Browser protocol parity'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        response=client.post(url+'/generate',json=dict(revision=0,text='TEST_REVIEW_PROTOCOL API parity',config=dict(REMOTE,context_length=262144),api_key='offline'))
        jid=response.json()['id'];assert wait_job(client,jid)['status']=='error'
        d=client.get(url+'?author=true').json();assert d['review']['status']=='failed' and d['job']['resumable']
        assert client.post(url+'/resume',json=dict(revision=d['revision'],api_key='offline')).status_code==200
        job=wait_job(client,jid);assert job['status']=='saved',job
    rows=client.get(f'/api/workspaces/{wid}/requests').json()
    assert sum(r['stage']=='draft_world' for r in rows)==1
    assert sum(r['stage']=='draft_world_validation' for r in rows)==4


def test_value_cycle_is_persisted_across_resume_epoch(api):
    client,app=api;s=rich();s['campaign']['title']='A'
    wid=client.post('/api/workspaces',json={'name':'Cycle recovery'}).json()['id'];url=f'/api/workspaces/{wid}/draft';calls=[];repairs=[]
    def provider(**kw):
        system=kw['messages'][0]['content'];calls.append(system)
        if system.startswith(review.MARKER):yield json.dumps({'issues':[dict(path='/campaign/title',message='Controlled unresolved conflict')]})
        elif 'patches' in system:
            repairs.append(True);yield json.dumps({'patches':[dict(path='/campaign/title',value='B' if len(repairs)==1 else 'A')]})
        else:yield json.dumps(s)
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        response=client.post(url+'/generate',json=dict(revision=0,text='Рассказ о соседях.',config=dict(REMOTE,context_length=262144),api_key='offline'))
        jid=response.json()['id'];assert wait_job(client,jid)['status']=='error'
        d=client.get(url+'?author=true').json();assert d['candidate']['campaign']['title']=='B'
        assert not d['job']['resumable'] and d['review']['status']!='running'
        n=len(calls)
        assert client.post(url+'/resume',json=dict(revision=d['revision'],api_key='offline')).status_code==409
        assert len(calls)==n

@pytest.mark.parametrize('broken',['{not json','[]','null','{"issues":null}'])
def test_alternate_audit_recovers_malformed_envelope(broken):
    s=rich();journal={};calls=[]
    def call(slot,messages):
        calls.append(slot)
        return '{"issues":[]}' if slot.endswith('_reaudit') else broken
    assert obtain(s,review.messages(s,'Идея'),'test_signature',journal,call,lambda:None)==[]
    assert len(calls)==3 and journal['accepted_reviews']['test_signature']==[]
