"""Exact immutable candidate replay; controlled review/repair/gameplay, not live LLM."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import pytest
from backend.services.draft_calendar import complete, idea_start, manual_edit
from backend.services import draft_initial, draft_world, draft_repair, draft_completeness
from backend.runtime_v3.calendar import age_on, current_time
from backend.repositories.drafts import candidate_hash
from test_initial_draft_v4 import api, REMOTE, wait_job, rich

FIXTURE=Path(__file__).parent/'fixtures/initial_world/generation_response_calendar.json'
SHA='e1825af870cae2d8326bc2e70cbd8da43738c3fcd4d4852a569f04f0a7c19e58'
def saved():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest()==SHA
    return json.loads(FIXTURE.read_bytes())
def restored():
    j=saved();return complete(j['candidate_snapshot'],j['author_input']['text'],j['binding']['job_id'])
def now(s):return current_time({'meta':{'world_time':s['world_clock']['minute'],'calendar':s['world_clock']['calendar']}})


def test_exact_candidate_reproduces_time_then_completes_without_mutation():
    j=saved();raw=j['candidate_snapshot'];before=deepcopy(raw)
    assert j['candidate_version']==329 and now(raw)['time']=='06:00'
    assert all(c['birth_date'] is None for c in raw['world']['characters'].values())
    s=restored();assert raw==before
    assert (now(s)['date'],now(s)['weekday'],now(s)['time'])==('2026-10-23',4,'12:00')
    assert s['world_clock']['minute']==79920
    assert complete(s,j['author_input']['text'])==s
    for card in s['characters']:
        birth=s['world']['characters'][card['id']]['birth_date']
        assert age_on(birth,'2026-10-23')==int(card['fields']['Возраст'].split()[0])
    for key in ('relationships','knowledge','facts','residences','events','scheduled_events','contacts','possessions'):
        assert s['world'][key]==raw['world'][key]
    assert s['locations']==raw['locations']
    assert s['scene']==raw['scene']
    for before,after in zip(raw['characters'],s['characters']):
        assert before['id']==after['id'] and before['name']==after['name']
        for field in ('Биография','Характер','Внешность','Возраст'):assert before['fields'][field]==after['fields'][field]
    assert not draft_initial.inspect_candidate(s)[1]['errors']
    assert all(c['minute']==79920 for c in s['world']['characters'].values())


@pytest.mark.parametrize('settings,expected',[
    ({},('2026-10-23','12:00')),
    ({'mode':'gregorian'},('2026-10-23','12:00')),
    ({'time':'08:30'},('2026-10-23','08:30')),
    ({'date':'1370-01-02'},('1370-01-02','12:00')),
])
def test_field_priorities(settings,expected):
    j=saved();s=j['candidate_snapshot'];s['creation_settings']['calendar_start']=settings
    s=complete(s,j['author_input']['text']);assert (now(s)['date'],now(s)['time'])==expected


def test_partial_and_history_extraction():
    assert idea_start('Война началась 23.10.2022. Сейчас пятница, 08:00.')=={'weekday':4,'time':'08:00'}
    assert idea_start('Родился 23.10.2000. Сейчас 2026 год.')=={'year':2026}
    assert idea_start('Сейчас 2026-10-23.')=={'date':'2026-10-23'}
    s=rich();s['world_clock'].pop('calendar')
    s=complete(s,'Сейчас пятница 08:00.');assert now(s)['date'] is None and now(s)['weekday']==4 and now(s)['time']=='08:00'


def test_manual_changes_and_dependent_births():
    s=restored();cid=s['characters'][0]['id']
    birth=s['world']['characters'][cid]['birth_date']
    s=manual_edit(s,'/world/characters/'+cid+'/birth_date')
    s['world_clock']['calendar']['start_date']='2027-10-23'
    s=manual_edit(s,'/world_clock/calendar')
    assert s['world']['characters'][cid]['birth_date']==birth
    assert any(e['category']=='age_conflict' for e in draft_initial.inspect_candidate(s)[1]['diagnostics'])
    assert complete(s,saved()['author_input']['text'])==s
    assert now(s)['date']=='2027-10-23'
    s['world_clock']['minute']+=120;s=manual_edit(s,'/world_clock/minute',79920)
    assert now(s)['time']=='14:00'
    assert s['world']['scenes']['s1']['start_minute']==80040


def test_custom_and_unrepresentable_birth():
    s=rich();s['creation_settings']={'calendar_start':{'mode':'custom','date':'0010-02-40','time':'23:59','weekday':2,'profile':{'system':'custom','month_lengths':[40,40],'month_names':['A','B'],'weekday_names':['A','B','C']}}}
    for c in s['characters']:c['fields']['Возраст']='25 лет'
    s=complete(s);assert all(c.get('birth_date') is None for c in s['world']['characters'].values())
    assert all('notice' in v for v in s['authoring']['calendar_completion']['birth_dates'].values())
    s['world_clock']['minute']+=1
    assert now(s)['date']=='0011-01-01' and now(s)['weekday']==0


def test_typed_false_claim_cannot_authorize_mutation():
    s=restored();issue={'path':'/world/relationships/r3/dimensions/attraction','message':'Missing','assertion':'missing_value'}
    found=draft_completeness.parse(json.dumps({'issues':[issue]}),s)
    assert found[0]['category']=='review_disproved' and not found[0]['patch_paths']
    issue={'path':'/world/residences/new','message':'More detail','assertion':'optional_detail'}
    assert draft_completeness.parse(json.dumps({'issues':[issue]}),s)[0]['severity']=='recommendation'


def residence_issues(s):
    # The actual recorded diagnostics identify three generated residence records.
    # This is controlled semantic adjudication from source + repair history,
    # not a name/type heuristic in the implementation.
    return [i for i in saved()['recovery']['review']['issues'] if i['severity']=='blocker' and i['path'].startswith('/world/residences/')]


def test_linked_repair_is_atomic_and_version_bound():
    s=restored();issues=residence_issues(s);_,scope=draft_repair.request(json.dumps(s),issues)
    rid=next(iter(scope.residences));original=deepcopy(s)
    payload={'candidate_hash':candidate_hash(s),'patches':[
        {'op':'add_location','path':'/locations/-','value':{'id':'new_home','name':'Квартира на окраине','text':'Жилой дом','kind':'building'}},
        {'path':'/world/residences/'+rid+'/location_id','value':'new_home'}]}
    result=json.loads(draft_repair.apply(json.dumps(s),json.dumps(payload),scope))
    assert len(result['locations'])==len(s['locations'])+1 and s==original
    with pytest.raises(ValueError):draft_repair.apply(json.dumps(result),json.dumps(payload),scope)
    payload['patches'][1]['value']='broken'
    with pytest.raises(ValueError):draft_repair.apply(json.dumps(s),json.dumps(payload),scope)
    assert s==original


def test_same_candidate_resume_editor_start_turn_save_reload(api):
    client,app=api;repo=app.state.repository;j=saved();raw=deepcopy(j['candidate_snapshot'])
    wid=client.post('/api/workspaces',json={'name':'Calendar exact candidate'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    config=dict(REMOTE,context_length=262144,_draft_task='world',_draft_input=j['author_input']['text'],_creation_settings=raw['creation_settings'])
    jid=repo.begin_preparation(wid,'draft_world',j['author_input']['text'],config,0)
    # Preserve all provider bytes; recover the exact edited candidate rather than world response.
    journal={k:deepcopy(v) for k,v in j.items() if k not in ('requests','recovery','binding','candidate_snapshot','candidate_version','current_diagnostics','current_start_block_reason','author_input')}
    journal['recovery_epoch']=0  # isolated DB epoch; immutable fixture retains original epoch
    journal['candidate_text']=json.dumps(raw,ensure_ascii=False)
    repo.save_response_journal(jid,journal)
    repo.save_draft_candidate(jid,raw,j['current_diagnostics'],review=j['recovery']['review'])
    repo.preparation_progress(jid,'','error')
    calls=[]
    def stream(**kw):
        calls.append(kw)
        if kw['messages'][0]['content'].startswith(draft_completeness.MARKER):
            s=json.loads(kw['messages'][1]['content'])['candidate']
            assert now(s)['time']=='12:00'
            assert s['world']['relationships']['r3']['dimensions']['attraction']==40
            assert s['world']['relationships']['r4']['dimensions']['attraction']==85
            issues=[i for i in residence_issues(s) if i['path'].split('/')[-1] in s['world']['residences']]
            issues=[dict(i,remove_paths=[i['path']]) for i in issues]  # Explicit controlled adjudication grants deletion.
            yield json.dumps({'issues':[{k:v for k,v in i.items() if k in ('path','message','severity','patch_paths','related_paths','remove_paths')} for i in issues]})
        else:
            request=json.loads(kw['messages'][1]['content'])
            assert request['residence_operations']
            yield json.dumps({'candidate_hash':request['candidate_hash'],'patches':[{'op':'remove','path':'/world/residences/'+rid,'expected':row} for rid,row in request['residence_records'].items()]})
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        d=client.get(url+'?author=true').json()
        response=client.post(url+'/resume',json={'revision':d['revision'],'api_key':'offline'})
        assert response.status_code==200,response.text
        job=wait_job(client,jid);assert job['status']=='saved',job.get('error',job)
        assert len(calls)==3
        d=client.get(url+'?author=true').json();s=d['state']
        assert len(s['world']['residences'])==5 and s['locations']==raw['locations']
        assert s['world']['knowledge']['k4']['status']=='known' and s['world']['knowledge']['k4']['source_event_id'] is None
        assert s['world']['knowledge']['k5']['status']=='suspected'
        for section in ('knowledge','relationships','facts','contacts','possessions'):assert s['world'][section]==raw['world'][section]
        d=client.patch(url,json={'revision':d['revision'],'operation':'patch','kind':'campaign','field':'title','value':'Ручное название'}).json()
        assert client.post(url+'/resume',json={'revision':d['revision'],'api_key':'offline'}).status_code==200
        assert wait_job(client,jid)['status']=='saved'
        d=client.get(url+'?author=true').json();assert d['state']['campaign']['title']=='Ручное название'
        count=len(calls)
        assert client.post(url+'/resume',json={'revision':d['revision'],'api_key':'offline'}).status_code==200
        assert wait_job(client,jid)['status']=='saved' and len(calls)==count
    d=client.get(url+'?author=true').json()
    exported=client.get(url+'/raw').json()
    assert exported['responses']['world']==j['responses']['world']
    start=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id']});assert start.status_code==200,start.text
    from test_runtime_v3_engine import run as play,raw_for
    from test_engine import CONFIG
    from backend.repositories.preparation import Repository
    sid=start.json()['save']
    for kind in ('start','turn','turn'):
        before=repo.get_snapshot(sid)
        turn=repo.begin_job(sid,'Осматриваюсь.' if kind=='turn' else '',kind,dict(CONFIG,context_length=262144))
        play(repo,turn,raw_for(before));assert repo.get_job(turn)['status']=='saved',repo.get_job(turn)['error']
        persisted=repo.get_snapshot(sid)
        repo=Repository(repo.path);assert repo.get_snapshot(sid)==persisted
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest()==SHA

@pytest.mark.parametrize('date,following', [('2024-02-28','2024-02-29'),('2024-02-29','2024-03-01'),('2026-12-31','2027-01-01'),('1370-01-31','1370-02-01')])
def test_calendar_rollovers(date,following):
    s=rich();s['creation_settings']={'calendar_start':{'date':date,'time':'23:59'}}
    s=complete(s);s['world_clock']['minute']+=1
    assert now(s)['date']==following and now(s)['time']=='00:00'


def test_twins_unknown_age_and_addition_stability():
    s=rich();cards=s['characters']
    for card in cards:card['fields']['Возраст']='25 лет'
    for card in cards[:2]:s['world']['characters'][card['id']]['birth_provenance']={'twin_group':'explicit_twins'}
    s['world']['characters'][cards[2]['id']]['birth_provenance']={'source':'unknown'}
    s=complete(s,seed='fixed');a,b=[s['world']['characters'][c['id']] for c in cards[:2]]
    assert a['birth_date']==b['birth_date']
    assert s['world']['characters'][cards[2]['id']].get('birth_date') is None
    before=deepcopy(s['world']['characters']);new=deepcopy(cards[0]);new['id']='new_npc'
    s['characters'].append(new);s['world']['characters']['new_npc']={'id':'new_npc','situation':'Elsewhere'}
    s=complete(s);assert all(s['world']['characters'][cid]==value for cid,value in before.items())


def test_timezone_and_import_do_not_change_completion(monkeypatch):
    a=restored()
    for zone in ('UTC','Europe/Moscow','America/Los_Angeles'):
        monkeypatch.setenv('TZ',zone);assert restored()==a
    raw=saved()['candidate_snapshot'];imported=draft_world.prepare(raw)
    assert all(c['birth_date'] is None for c in imported['world']['characters'].values())
    assert 'authoring' not in imported


def test_synthetic_new_home_and_residence_are_one_transaction():
    s=restored();path='/world/residences/new_residence'
    issues=[dict(path=path,category='semantic_completeness',patch_paths=[path],message='Explicit home needs its canonical record')]
    _,scope=draft_repair.request(json.dumps(s),issues)
    payload={'candidate_hash':candidate_hash(s),'patches':[
        {'op':'add_location','path':'/locations/-','value':{'id':'new_home','name':'Жильё при мастерской','text':'Прямо заданное автором жильё.','kind':'building'}},
        {'path':path,'value':{'id':'new_residence','actor_id':'c4','location_id':'new_home','context':'Автор явно задал проживание при мастерской'}}]}
    result=json.loads(draft_repair.apply(json.dumps(s),json.dumps(payload),scope))
    assert result['world']['residences']['new_residence']['location_id']=='new_home'
    assert complete(result)['world']['residences']==result['world']['residences']
