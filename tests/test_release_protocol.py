"""Untrusted provider replies: real handlers, never successful handler stubs."""
from copy import deepcopy
import json
import pytest
from backend.services import draft_completeness as review, draft_quality as quality
from test_issue44_final import rich

@pytest.mark.parametrize('item',[None,False,7,1.5,'bad',[],{'path':'/campaign/title','message':'x','basis':None}])
def test_correction_builder_handles_untrusted_item(item):
    state=rich();raw=json.dumps({'issues':[item]})
    with pytest.raises(review.ReportError) as caught:review.parse(raw,state)
    built=review.correction(review.messages(state,'Авторский текст'),raw,caught.value.errors)
    assert json.loads(built[1]['content'])['rejected_response']

@pytest.mark.parametrize('answer',[[],None,'bad',{'patches':[],'preserved_unknown':None},{'patches':None},{'patches':[None]}])
def test_quality_invalid_reply_preserves_checked_world(answer):
    state=rich();state['characters'][1]['fields']['Внешность']='неизвестно';before=deepcopy(state);journal={}
    out,issues=quality.complete(state,[],'Авторский текст',journal,lambda *a:json.dumps(answer))
    assert out==before and state==before and issues is None
    assert journal['quality']['status'] in ('partial','rejected')

@pytest.mark.parametrize('extra',[{'section':'characters','entity_id':'missing','field':'name'},{'path':'/campaign/title','remove_paths':['/world']},{'path':'/campaign/title','patch_paths':['/world']},{'path':'/campaign/title','basis':None}])
def test_bad_advisory_is_isolated(extra):
    item=dict(message='Optional',severity='recommendation',assertion='optional_detail',**extra)
    out=review.parse(json.dumps({'issues':[item]}),rich())
    assert len(out)==1 and out[0]['severity']=='recommendation'
    assert not out[0].get('patch_paths') and not out[0].get('remove_paths') and out[0]['protocol_warnings']

from pathlib import Path
from hypothesis import given,settings,strategies as st
from jsonschema import Draft202012Validator
from backend.services import draft_repair as repair
from backend.services.draft_review_recovery import obtain,parse_alternate,alternate,reaudit_schema
from backend.services.draft_protocol import ProtocolError,Correction,decode
CASES=json.loads((Path(__file__).parent/'fixtures/initial_world/release_protocol_cases.json').read_text())['cases']
BAD=[None,False,1,1.5,'текст',{},[],[None],{'x':[]}]

@pytest.mark.parametrize('case',CASES,ids=lambda c:c['id'])
def test_release_bundle_cases_run_real_handlers(case):
    state=rich();stage=case['stage'];raw=case['response_text'];old='{"issues":[null]}'
    if stage in ('review','review_correction'):
        try:out=review.parse(raw,state)
        except review.ReportError as exc:
            assert exc.errors and all(e['stage']=='review' and e['code'] for e in exc.errors)
            review.correction(review.messages(state,'Авторское название: Верное.'),raw,exc.errors)
        else:
            assert all(not r.get('patch_paths') and not r.get('remove_paths') for r in out if r.get('protocol_warnings'))
            if case['id']=='advisory_with_real_blocker':assert any(r['severity']=='blocker' and r['patch_paths']==['/campaign/title'] for r in out)
    elif stage=='correction':
        with pytest.raises(ValueError):review.merge_correction(raw,old,[dict(report_path='/issues/0')])
    elif stage=='reaudit':
        with pytest.raises(ValueError):parse_alternate(raw,old,state)
    else:
        path='/characters/1/fields/Внешность';state['characters'][1]['fields']['Внешность']='неизвестно'
        state['characters'][1]['name']='Лада' if case['id']!='quality_wrong_owner_excerpt' else 'Другой персонаж'
        source='Внешность Лады намеренно оставь неизвестной.';journal={}
        def call(slot,messages,stage):
            payload=json.loads(messages[1]['content'])
            if stage=='draft_world_quality':
                if case['id']=='quality_rereview_broken':return json.dumps({'patches':[{'path':path,'value':'Седые волосы.'}]})
                return raw
            if case['id']=='quality_rereview_broken':return raw
            return json.dumps(dict(issues=[],unknown_confirmations=[dict(path=path,actor_id=state['characters'][1]['id'],field='Внешность',decision='preserve' if case['id']=='quality_valid_preserved_only' else 'unresolved',reason='Сверено имя и явное пожелание автора.')]))
        before=deepcopy(state);out,_=quality.complete(state,[],source,journal,call)
        assert out==before and state==before
        assert journal['quality']['status']==('accepted' if case['id']=='quality_valid_preserved_only' else 'partial')

@pytest.mark.parametrize('field',['basis','related_paths','patch_paths','record_match','target_path','section','entity_id','remove_paths'])
@pytest.mark.parametrize('value',BAD)
def test_review_nested_type_matrix(field,value):
    state=rich();item=dict(path='/campaign/title',message='Обязательное замечание');item[field]=value
    raw=json.dumps({'issues':[dict(message='Соседний совет',severity='recommendation'),item]})
    try:review.parse(raw,state)
    except review.ReportError as exc:
        built=review.correction(review.messages(state,'Название задано автором'),raw,exc.errors)
        assert json.loads(built[1]['content'])['rejected_items']
        assert any(p['message']=='Соседний совет' for p in exc.issues)

@pytest.mark.parametrize('value',BAD)
@pytest.mark.parametrize('field',['issue_id','issues'])
def test_correction_nested_type_matrix(field,value):
    row={'issue_id':review.issue_identity(None),'issues':[{'path':'/campaign/title','message':'x'}]};row[field]=value
    try:review.merge_correction(json.dumps({'replacements':[row]}),'{"issues":[null]}',[dict(report_path='/issues/0')])
    except ValueError:pass

@pytest.mark.parametrize('value',BAD)
@pytest.mark.parametrize('field',['issue_id','basis','issues','resolution','reason'])
def test_reaudit_nested_type_matrix(field,value):
    row=dict(issue_id=review.issue_identity(None),resolution='disproved',reason='Проверено',basis=[{'path':'/campaign/title'}]);row[field]=value
    try:parse_alternate(json.dumps({'resolutions':[row]}),'{"issues":[null]}',rich())
    except ValueError:pass

@pytest.mark.parametrize('value',BAD)
@pytest.mark.parametrize('field',['path','author_excerpt'])
def test_quality_nested_type_matrix(field,value):
    state=rich();state['characters'][1]['fields']['Внешность']='неизвестно';before=deepcopy(state);journal={}
    item=dict(path='/characters/1/fields/Внешность',author_excerpt='Внешность Лады намеренно неизвестна.');item[field]=value
    out,_=quality.complete(state,[],item.get('author_excerpt') if isinstance(item.get('author_excerpt'),str) else 'source',journal,lambda *a:json.dumps(dict(patches=[],preserved_unknown=[item])))
    assert out==before and journal['quality']['status']=='partial'

json_value=st.recursive(st.none()|st.booleans()|st.integers()|st.text(max_size=25),lambda x:st.lists(x,max_size=4)|st.dictionaries(st.text(max_size=15),x,max_size=4),max_leaves=15)
@given(json_value)
@settings(max_examples=80,deadline=None)
def test_arbitrary_bounded_json_never_escapes_protocol_boundary(value):
    state=rich();raw=json.dumps(value);old='{"issues":[null]}'
    for call in (lambda:review.parse(raw,state),lambda:review.merge_correction(raw,old,[dict(report_path='/issues/0')]),lambda:parse_alternate(raw,old,state),lambda:repair.apply(json.dumps(state),raw,repair.RepairScope(['/campaign/title'],state,set()))):
        try:call()
        except ValueError:pass
    try:review.parse(raw,state)
    except review.ReportError as exc:review.correction(review.messages(state,'Автор'),raw,exc.errors)

@pytest.mark.parametrize('extra',[dict(section='characters',entity_id='absent',field='name'),dict(basis=[{'path':[]}]),dict(patch_paths=['/world']),dict(remove_paths=['/world']),dict(related_paths=[None]),dict(assertion='missing_record',section='roles',record_match={'actor_id':[],'kind':'occupation'}),dict(assertion='missing_reference',target_path='/missing')])
def test_advisory_policy_entire_item_and_required_siblings(extra):
    good=dict(path='/campaign/title',message='Автор требует другое название',patch_paths=['/campaign/title'])
    bad=dict(path='/campaign/title',message='Совет',severity='recommendation',assertion='optional_detail');bad.update(extra)
    rows=review.parse(json.dumps({'issues':[bad,good]}),rich())
    assert rows[0]['protocol_warnings'] and not rows[0]['patch_paths'] and not rows[0].get('remove_paths')
    assert rows[1]['severity']=='blocker' and rows[1]['patch_paths']==good['patch_paths']
    with pytest.raises(review.ReportError):review.parse(json.dumps({'issues':[bad,None]}),rich())

@pytest.mark.parametrize('item',[dict(message='x',severity='blocker',assertion='optional_detail'),dict(message='x',severity='recommendation',assertion='invented'),None])
def test_conflicting_or_unreadable_classification_never_becomes_advisory(item):
    with pytest.raises(review.ReportError):review.parse(json.dumps({'issues':[item]}),rich())

from test_initial_draft_v4 import api,REMOTE,wait_job
from unittest.mock import patch
from backend.services import draft_initial
from backend.repositories.preparation import Repository

def test_published_contracts_and_legacy_correction_adapter():
    state=rich();good=dict(path='/campaign/title',message='Уточнить название',patch_paths=['/campaign/title'])
    report={'issues':[good]};Draft202012Validator(review.report_schema()).validate(report);assert review.parse(json.dumps(report),state)
    old=json.dumps({'issues':[None,good]});errors=[dict(report_path='/issues/0')]
    built=review.correction(review.messages(state,'Автор'),old,errors);schema=json.loads(built[1]['content'])['response_schema']
    reply={'replacements':[dict(issue_id=review.issue_identity(None),issues=[good,dict(good,path='/campaign/description',patch_paths=['/campaign/description'])])]}
    Draft202012Validator(schema).validate(reply)
    out=json.loads(review.merge_correction(json.dumps(reply),old,errors));assert len(out['issues'])==3 and out['issues'][-1]==good
    legacy=review.merge_correction(json.dumps({'issues':[good]}),old,errors);assert json.loads(legacy)['issues']==[good,good]
    rows={'resolutions':[dict(issue_id=review.issue_identity(None),resolution='replaced',reason='Уточнён адрес',issues=[good])]}
    Draft202012Validator(reaudit_schema()).validate(rows);assert parse_alternate(json.dumps(rows),'{"issues":[null]}',state)[0]
    for bad in ({'resolutions':[dict(rows['resolutions'][0],issues=[])]},{'resolutions':[dict(rows['resolutions'][0],resolution='disproved',basis=[])]}):
        assert list(Draft202012Validator(reaudit_schema()).iter_errors(bad))
        with pytest.raises(ValueError):parse_alternate(json.dumps(bad),'{"issues":[null]}',state)
    issue=review.parse(json.dumps(report),state);messages,scope=repair.request(json.dumps(state),issue)
    response={'patches':[{'path':'/campaign/title','value':'Верное'}]}
    Draft202012Validator(json.loads(messages[1]['content'])['response_schema']).validate(response)
    assert json.loads(repair.apply(json.dumps(state),json.dumps(response),scope))['campaign']['title']=='Верное'
    assert 'replacements' in built[0]['content'] or 'response_schema' in built[0]['content']
    audit=alternate(review.messages(state,'Автор'),old,errors);payload=json.loads(audit[1]['content'])
    assert 'report_schema' not in payload and 'resolutions' in payload['response_schema']['properties']

@pytest.mark.parametrize('mode',['patches','preserve','mixed'])
def test_quality_valid_forms_share_published_schema(mode):
    state=rich();state['characters'][1]['name']='Лада';state['characters'][1]['fields']['Внешность']='неизвестно'
    path='/characters/1/fields/Внешность';other='/characters/1/fields/Привычки'
    if mode=='mixed':state['characters'][1]['fields']['Привычки']='неизвестно'
    source='Внешность Лады намеренно оставь неизвестной.' if mode!='patches' else 'Дополняй внешность свободно.'
    journal={}
    def call(slot,messages,stage):
        payload=json.loads(messages[1]['content'])
        if stage=='draft_world_quality':
            response=dict(patches=[])
            if mode!='preserve':response['patches']=[dict(path=other if mode=='mixed' else path,value='Записывает наблюдения в блокнот.' if mode=='mixed' else 'Рыжие волосы и веснушки.')]
            if mode!='patches':response['preserved_unknown']=[dict(path=path,author_excerpt=source)]
        else:
            response={'issues':[]}
            if mode!='patches':response['unknown_confirmations']=[dict(path=path,actor_id=state['characters'][1]['id'],field='Внешность',decision='preserve',reason='Автор явно просит сохранить неизвестность внешности Лады.')]
        Draft202012Validator(payload.get('response_schema',payload.get('report_schema'))).validate(response)
        return json.dumps(response,ensure_ascii=False)
    out,_=quality.complete(state,[],source,journal,call)
    assert journal['quality']['status']=='accepted'
    assert out['characters'][1]['fields']['Внешность']==('неизвестно' if mode!='patches' else 'Рыжие волосы и веснушки.')

@pytest.mark.parametrize('raw',['[]','null','"bad"','{"patches":null}','{"patches":[null]}','{"patches":[],"preserved_unknown":null}','{"patches":[],"preserved_unknown":[{"path":[],"author_excerpt":"012345678"}]}'])
def test_quality_bad_forms_rejected_by_published_schema(raw):
    state=rich();issues=[dict(path='/characters/1/fields/Внешность',message='Дополнить')]
    messages,_=repair.request(json.dumps(state),issues)
    schema=quality.quality_schema(json.loads(messages[1]['content'])['response_schema'])
    assert list(Draft202012Validator(schema).iter_errors(json.loads(raw)))


def test_builder_domain_failure_advances_without_provider_charge_and_internal_error_does_not():
    state=rich();journal={};calls=[];persisted=[]
    original=review.correction
    def bad_builder(*args):raise ProtocolError('correction',[dict(report_path='/issues/0',message='Неразрешимая форма')])
    def call(slot,messages):
        calls.append(slot);payload=json.loads(messages[1]['content'])
        if payload.get('strategy')=='scoped_reaudit':return json.dumps({'resolutions':[dict(issue_id=p['issue_id'],resolution='disproved',reason='Название установлено',basis=[dict(path='/campaign/title')]) for p in payload['pending_issues']]})
        return '{"issues":[null]}'
    with patch.object(review,'correction',side_effect=bad_builder):
        assert obtain(state,review.messages(state,'Автор'),'s',journal,call,lambda:persisted.append(deepcopy(journal)))==[]
    assert len(calls)==2 and journal['review_preparation_failures'] and journal['review_failures'][0]['response']=='{"issues":[null]}'
    assert 's' in journal['accepted_reviews']
    with patch.object(review,'correction',side_effect=RuntimeError('implementation defect')):
        with pytest.raises(RuntimeError):obtain(state,review.messages(state,'Автор'),'other',{},call,lambda:None)

@pytest.mark.parametrize('broken_review',[False,True])
def test_quality_rejected_rereview_or_cancel_rolls_back(broken_review):
    state=rich();state['characters'][1]['fields']['Внешность']='неизвестно';before=deepcopy(state);journal={}
    def call(slot,messages,stage):
        if stage=='draft_world_quality':return json.dumps({'patches':[dict(path='/characters/1/fields/Внешность',value='Седые волосы.')]})
        return '{"issues":[null]}' if broken_review else None
    out,checked=quality.complete(state,[], 'Автор',journal,call)
    assert out==before and checked is None and journal['quality']['status']==('partial' if broken_review else 'cancelled')
    assert 'after_hash' not in journal['quality']

@pytest.mark.parametrize('scenario',['nullable_review','advisory','quality_partial'])
def test_api_protocol_recovery_to_game_without_manual_world_edit(api,scenario):
    client,app=api;state=rich();state['campaign']['title']='Неверное название'
    if scenario=='quality_partial':state['characters'][1]['fields']['Внешность']='неизвестно'
    wid=client.post('/api/workspaces',json={'name':'Release'}).json()['id'];url=f'/api/workspaces/{wid}/draft';calls=[]
    blocker=dict(path='/campaign/title',message='Автор явно задал название Верное.',patch_paths=['/campaign/title'])
    advice=dict(section='characters',entity_id='missing',field='name',severity='recommendation',assertion='optional_detail',message='Совет')
    def provider(**kw):
        system=kw['messages'][0]['content'];calls.append(system)
        if system.startswith(review.MARKER):
            payload=json.loads(kw['messages'][1]['content'])
            if payload.get('strategy')=='scoped_reaudit':
                yield json.dumps({'resolutions':[dict(issue_id=p['issue_id'],resolution='replaced',reason='Сверено с авторским названием',issues=[blocker] if isinstance(p['issue'],dict) and p['issue'].get('path')=='/campaign/title' else [dict(message='Необязательное дополнение',severity='recommendation')]) for p in payload['pending_issues']]});return
            if 'rejected_response' in payload:yield '{"replacements":null}';return
            yield json.dumps({'issues':([None,blocker] if scenario=='nullable_review' else [advice,blocker]) if payload['candidate']['campaign']['title']!='Верное' else []});return
        if system.startswith('Один необязательный пакет'):yield '{"patches":[],"preserved_unknown":null}';return
        if 'patches' in system:yield '{"patches":[{"path":"/campaign/title","value":"Верное"}]}';return
        assert len(calls)==1
        yield json.dumps(state,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        reply=client.post(url+'/generate',json=dict(revision=0,text='Авторское название мира: Верное.',config=dict(REMOTE,context_length=262144),api_key='offline'))
        jid=reply.json()['id'];job=wait_job(client,jid);assert job['status']=='saved',job
        d=client.get(url+'?author=true').json();assert d['state']['campaign']['title']=='Верное'
        n=len(calls);client.post(url+'/resume',json=dict(revision=d['revision'],api_key='offline'));assert wait_job(client,jid)['status']=='saved' and len(calls)==n
    exported=client.get(url+'/raw').json()
    if scenario=='quality_partial':
        assert exported['quality']['status']=='partial' and exported['quality']['response']=='{"patches":[],"preserved_unknown":null}'
        assert d['validation']['warnings']
    assert sum(r['stage']=='draft_world' for r in exported['requests'])==1
    if scenario=='advisory':assert not exported.get('review_failures')
    d=client.get(url+'?author=true').json();confirmed=client.post(url+'/confirm',json=dict(revision=d['revision'],version_id=d['version_id']));assert confirmed.status_code==200,confirmed.text
    from test_runtime_v3_engine import run,raw_for
    from test_engine import CONFIG
    repo=app.state.repository;sid=confirmed.json()['save'];original=repo.get_snapshot(sid)
    for kind in ('start','turn','turn'):
        snapshot=repo.get_snapshot(sid);jid=repo.begin_job(sid,'Осматриваюсь.' if kind=='turn' else '',kind,CONFIG);run(repo,jid,raw_for(snapshot));assert repo.get_job(jid)['status']=='saved'
        repo=Repository(repo.path)
    final=repo.get_snapshot(sid)
    for section in ('knowledge','relationships','objective_relations','roles','possessions'):assert final['world_state'][section]==original['world_state'][section]

@pytest.mark.parametrize('section,field',[('relationships','source_id'),('relationships','dimensions'),('relationships','context'),('knowledge','actor_id'),('knowledge','status')])
@pytest.mark.parametrize('value',[None,[],{},True])
def test_initial_duplicate_normalization_validates_before_hash_or_iteration(section,field,value):
    state=rich();row=next(iter(state['world'][section].values()));row[field]=value
    _,report=draft_initial.inspect_candidate(state)
    if section=='relationships' and field=='dimensions' and value=={}:
        assert not report['errors'];return
    assert report['errors'] and all(e['category']!='validation_incomplete' for e in report['diagnostics'])
    assert any(e['path'].startswith('/world/'+section+'/') for e in report['diagnostics'])


def test_strict_json_for_regeneration_and_depth_limit():
    from backend.services.draft_generation import decode_result
    from backend.services.draft_response import strict_loads
    with pytest.raises(ValueError):strict_loads('['*101+'0'+']'*101)
    assert strict_loads(json.dumps('['*200))=='['*200
    state=rich();cid=state['characters'][1]['id']
    with pytest.raises(ValueError):decode_result('{"value":"a","value":"b"}',state,dict(_draft_task='field',_draft_target=dict(kind='character',id=cid,field='name')))

@pytest.mark.parametrize('target',['claim','actor_location','scene_location','event_participants','organization_locations'])
@pytest.mark.parametrize('bad',[{},[],True])
def test_adjacent_canonical_shape_errors_have_exact_diagnostics(target,bad):
    state=rich();world=state['world']
    if target=='claim':world['facts']['ownership']['claim']['value']=bad
    elif target=='actor_location':world['characters'][state['controlled_actor_id']]['location']=bad
    elif target=='scene_location':world['scenes'][state['camera']['scene_id']]['location']=bad
    elif target=='event_participants':
        world['events']['probe']=dict(id='probe',text='Факт',minute=None,participants=bad,witnesses=[],fact_ids=[])
    else:world['organizations']['apex']['location_ids']=bad
    _,report=draft_initial.inspect_candidate(state)
    if target in ('event_participants','organization_locations') and bad==[]:return
    assert report['errors']
    assert all(e['category']!='validation_incomplete' for e in report['diagnostics']),report

@pytest.mark.parametrize('status',['stopped','error'])
def test_terminal_quality_state_is_persisted_atomically_and_survives_late_journal(api,status):
    client,app=api;repo=app.state.repository;wid=client.post('/api/workspaces',json={'name':'Terminal quality'}).json()['id']
    jid=repo.begin_preparation(wid,'draft_world','',dict(REMOTE,_draft_task='world',_draft_input=''),0)
    state=rich();repo.save_draft_candidate(jid,state,[],review=dict(status='completed',issues=[]))
    journal=dict(quality=dict(status='running',before_hash='h'),quality_attempts={'q':dict(status='running',before_hash='h')},reserved_tokens=123,pending={'slot':'quality'})
    repo.save_response_journal(jid,journal);repo.preparation_progress(jid,'',status,'Interrupted')
    repo.save_response_journal(jid,journal)  # Same-epoch delayed write must not revive running.
    saved=json.loads(Repository(repo.path).preparation_job(jid)['response_journal'])
    assert saved['quality']['status']==('cancelled' if status=='stopped' else 'partial')
    assert saved['quality_attempts']['q']['status']!='running' and saved['reserved_tokens']==123 and saved['pending']==journal['pending']
    assert repo.draft(wid,True)['candidate']==state


def test_process_restart_finalizes_quality_and_preserves_unknown_provider_outcome(tmp_path):
    from backend.api.app import create_app
    from fastapi.testclient import TestClient
    path=tmp_path/'restart.sqlite3';repo=Repository(path);wid=repo.create_workspace('Restart')['id']
    jid=repo.begin_preparation(wid,'draft_world','',dict(REMOTE,_draft_task='world',_draft_input=''),0)
    state=rich();repo.save_draft_candidate(jid,state,[],review=dict(status='completed',issues=[]))
    repo.save_response_journal(jid,dict(quality=dict(status='running'),pending={'slot':'quality'},reserved_cost='0.05',candidate_text=json.dumps(state)))
    with TestClient(create_app(path)) as client:
        job=repo.preparation_job(jid);assert job['status']=='stopped'
        journal=json.loads(job['response_journal']);assert journal['quality']['status']=='cancelled' and journal['reserved_cost']=='0.05'
        assert client.post(f'/api/workspaces/{wid}/draft/resume',json=dict(revision=0,api_key='offline')).status_code==409
        assert client.get(f'/api/workspaces/{wid}/draft?author=true').json()['candidate']==state


def test_internal_quality_error_is_not_success_or_provider_protocol_error(api):
    client,app=api;wid=client.post('/api/workspaces',json={'name':'Internal failure'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    state=rich();state['characters'][1]['fields']['Внешность']='неизвестно'
    def provider(**kw):
        system=kw['messages'][0]['content']
        yield '{"issues":[]}' if system.startswith(review.MARKER) else '{"patches":[]}' if system.startswith('Один необязательный пакет') else json.dumps(state)
    with patch('backend.services.preparation.chat_stream',side_effect=provider),patch.object(quality,'decode',side_effect=TypeError('Internal injected defect')):
        r=client.post(url+'/generate',json=dict(revision=0,text='Мир',config=dict(REMOTE,context_length=262144),api_key='offline'))
        job=wait_job(client,r.json()['id']);assert job['status']=='error' and 'internal_error' in job['error']
    raw=client.get(url+'/raw').json();assert raw['internal_errors'][-1]['code']=='internal_error' and raw['quality']['status']=='partial'
    assert raw['candidate_snapshot']['world']['knowledge']==state['world']['knowledge']
    assert 'internal_errors' not in client.get(url).json()


from copy import deepcopy
from unittest.mock import patch
import json
import pytest
from test_initial_draft_v4 import api,rich as cast_rich,REMOTE,wait_job
from backend.services.world_creation_settings import CreationSettings
from backend.services.draft_completeness import MARKER
from backend.repositories.preparation import Repository

@pytest.mark.parametrize('settings,count',[({'cast_preset':'large'},36),({'cast_preset':'custom','core_npcs':15,'secondary_npcs':40},56)])
def test_cast_bound_contract_budget_and_preservation(api,settings,count):
    client,app=api
    typed=CreationSettings.model_validate(settings);target=typed.cast_targets([])
    assert target['core']+target['secondary']+1==count
    wid=client.post('/api/workspaces',json={'name':'Upper cast boundary'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    with patch('backend.services.preparation.chat_stream',side_effect=AssertionError('budget guard must precede provider')) as provider:
        reply=client.post(url+'/generate',json=dict(revision=0,text='Город ремесленников.',config=REMOTE,api_key='offline',creation_settings=settings,budget={'max_total_tokens':1}))
        job=wait_job(client,reply.json()['id']);assert job['status']=='error' and 'бюджет' in job['error'];provider.assert_not_called()
    state=cast_rich();template=deepcopy(state['characters'][1]);actor=deepcopy(state['world']['characters'][template['id']])
    while len(state['characters'])<count:
        cid='extra_'+str(len(state['characters']));card=deepcopy(template);card.update(id=cid,name='Житель '+cid,aliases=[])
        state['characters'].append(card);state['world']['characters'][cid]=dict(deepcopy(actor),id=cid)
    def stream(**kw):
        if kw['messages'][0]['content'].startswith(MARKER):yield '{"issues":[]}'
        else:yield json.dumps(state,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        reply=client.post(url+'/generate',json=dict(revision=0,text='Город ремесленников.',config=dict(REMOTE,context_length=262144),api_key='offline',creation_settings=settings))
        job=wait_job(client,reply.json()['id']);assert job['status']=='saved',job
    d=client.get(url+'?author=true').json();assert len(d['state']['characters'])==count
    assert {x['id'] for x in d['state']['characters']}=={x['id'] for x in state['characters']}
    out=client.post(url+'/confirm',json=dict(revision=d['revision'],version_id=d['version_id']));assert out.status_code==200,out.text
    repo=app.state.repository;snap=repo.get_snapshot(out.json()['save'])
    assert len(snap['world_state']['characters'])==count
    assert Repository(repo.path).get_snapshot(out.json()['save'])==snap
