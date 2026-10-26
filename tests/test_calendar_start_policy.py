"""Product policy v2: technical validation is mandatory; semantic approval is optional."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
from unittest.mock import patch
import pytest
from backend.services import calendar_presets as presets
from backend.services.draft_initial import inspect_candidate
from backend.runtime_v3.calendar import current_time, calendar_range
from test_initial_draft_v4 import api, REMOTE, rich

E5=Path(__file__).parent/'fixtures/initial_world/generation_response_e5.json'
SHA='62ac12d4a812f517a26bddb56aaaadf527cdb2977f6c9fa1a87fef921c7a74a7'

def evidence():
    assert hashlib.sha256(E5.read_bytes()).hexdigest()==SHA
    return json.loads(E5.read_bytes())

def install(client,repo,running=False):
    j=evidence();s=j['candidate_snapshot']
    wid=client.post('/api/workspaces',json={'name':'E5 exact 71'}).json()['id']
    cfg=dict(REMOTE,_draft_task='world',_draft_input=j['author_input']['text'],_creation_settings=s['creation_settings'])
    jid=repo.begin_preparation(wid,'draft_world',j['author_input']['text'],cfg,0)
    journal={k:deepcopy(v) for k,v in j.items() if k not in ('requests','recovery','binding','candidate_snapshot','candidate_version','current_diagnostics','current_start_block_reason','author_input')}
    journal['recovery_epoch']=0 # bind immutable export to the new local worker epoch
    journal['candidate_text']=json.dumps(s,ensure_ascii=False)
    repo.save_response_journal(jid,journal)
    repo.save_draft_candidate(jid,s,[],review=dict(j['recovery']['review'],status='running' if running else 'failed'))
    if not running:repo.preparation_progress(jid,'','stopped')
    return wid,jid,s,journal

@pytest.mark.parametrize('running',[False,True])
def test_e5_start_without_review_and_late_write_save_reload(api,running):
    client,app=api;repo=app.state.repository
    wid,jid,original,journal=install(client,repo,running);url=f'/api/workspaces/{wid}/draft'
    d=client.get(url+'?author=true').json()
    assert d['technical_valid'] and d['state'] and d['start_warning'],d
    assert d['candidate']==original
    data=dict(revision=d['revision'],version_id=d['version_id'])
    assert client.post(url+'/confirm',json=data).status_code==409
    with patch('backend.services.preparation.chat_stream',side_effect=AssertionError('No new generation or review')):
        response=client.post(url+'/confirm',json=dict(data,accept_warnings=True,stop_review=running))
    assert response.status_code==200,response.text
    started=response.json();sid=started['save']
    assert client.post(url+'/confirm',json=dict(data,accept_warnings=True,stop_review=running)).json()==started
    retained=json.loads(repo.preparation_job(jid)['response_journal'])
    for field in ('pending','reserved_tokens','reserved_cost','actual_tokens','actual_cost'):
        assert retained.get(field)==journal.get(field)
    repo.save_draft_candidate(jid,rich(),[],review={'status':'completed'})
    assert client.get(url+'?author=true').json()['candidate']==original
    assert client.get(url).json()['review']['status']!='completed'
    from test_runtime_v3_engine import run as play,raw_for
    from test_engine import CONFIG
    from backend.repositories.preparation import Repository
    initial=repo.get_snapshot(sid)
    assert initial['authoring']['manual_paths']==original['authoring']['manual_paths']
    birthdays={k:a['birth_date'] for k,a in original['world']['characters'].items()}
    assert current_time(initial['world_state'])['date']=='2026-10-23'
    assert current_time(initial['world_state'])['time']=='18:00'
    for kind in ('start','turn','turn'):
        before=repo.get_snapshot(sid)
        game_job=repo.begin_job(sid,'Осматриваюсь.' if kind=='turn' else '',kind,dict(CONFIG,context_length=262144))
        play(repo,game_job,raw_for(before));assert repo.get_job(game_job)['status']=='saved',repo.get_job(game_job)
        snapshot=repo.get_snapshot(sid);repo=Repository(repo.path)
        assert repo.get_snapshot(sid)==snapshot
        assert len(snapshot['world_state']['characters'])==19
        assert {k:a['birth_date'] for k,a in snapshot['world_state']['characters'].items()}==birthdays
        assert snapshot['authoring']['manual_paths']==original['authoring']['manual_paths']
    assert hashlib.sha256(E5.read_bytes()).hexdigest()==SHA

@pytest.mark.parametrize('mutation',[lambda s:s.update(controlled_actor_id='missing'),lambda s:s['world']['objective_relations'].update(broken={'id':'broken','kind':'sibling','source_id':'missing','target_id':'absent'}),lambda s:s['world_clock'].update(minute='broken')])
def test_warning_ack_cannot_bypass_runtime(api,mutation):
    client,app=api;repo=app.state.repository
    wid,jid,s,_=install(client,repo,True);mutation(s)
    repo.save_draft_candidate(jid,s,[],review={'status':'failed'})
    d=repo.draft(wid,True)
    assert not d['technical_valid']
    with pytest.raises(ValueError,match='Нельзя начать'):
        repo.confirm_draft(wid,d['revision'],d['version_id'],True,True)
    assert repo.preparation_job(jid)['status']=='generating'

@pytest.mark.parametrize('country',list(presets.COUNTRIES))
def test_country_catalog_and_independent_new_year_control(country):
    regional=dict(country=country,version=presets.VERSION,observed=False)
    events=presets.occurrences(regional,'2026-01-01','2026-12-31')
    assert events and any(e['date']=='2026-01-01' for e in events)
    assert len({e['id'] for e in events})==len(events)
    assert all(e['date'].startswith('2026') for e in events)


def test_movable_observed_and_subdivision_controls():
    gb=dict(country='GB',subdivision='ENG',version=presets.VERSION)
    # GOV.UK bank-holidays: independently published Easter Monday dates.
    for year,day in [(2026,'2026-04-06'),(2027,'2027-03-29')]:
        rows=presets.occurrences(gb,f'{year}-01-01',f'{year}-12-31')
        assert any(e['date']==day and e['name']=='Easter Monday' for e in rows)
    rows=presets.occurrences(dict(gb,observed=True),'2026-12-25','2026-12-29')
    assert any(e['date']=='2026-12-26' and not e['observed'] for e in rows)
    assert any(e['date']=='2026-12-28' and e['observed'] for e in rows)
    for region,epiphany in [('BY',True),('BE',False)]:
        rows=presets.occurrences(dict(country='DE',subdivision=region,version=presets.VERSION),'2026-01-06','2026-01-06')
        assert bool(rows)==epiphany
    with pytest.raises(presets.CoverageError):presets.source('DE','INVALID')

@pytest.mark.parametrize('season,expected',[('north','Весна'),('south','Осень')])
@pytest.mark.parametrize('day',['2026-03-01','2028-03-01'])
def test_seasons_and_runtime_projection(season,expected,day):
    s=rich();s=presets.apply(s,dict(holidays='country',country='RU',seasons=season),True)
    runtime={'meta':{'calendar':dict(s['world_clock']['calendar'],start_date=day),'world_time':s['world_clock']['minute']},'characters':{},'scheduled_events':{}}
    assert current_time(runtime)['season']==expected
    rows=calendar_range(runtime,'2026-12-31','2027-01-02')['events']
    assert any(e['date']=='2027-01-01' for e in rows)


def test_e5_apply_is_addressed_atomic_and_preview_read_only(api):
    client,app=api;repo=app.state.repository
    wid,_,original,_=install(client,repo);url=f'/api/workspaces/{wid}/draft'
    d=repo.draft(wid,True)
    preview=client.post(url+'/calendar-preview',json={'holidays':'auto','seasons':'auto'})
    assert preview.status_code==200,preview.text
    assert preview.json()['regional']['country']=='RU'
    assert repo.draft(wid,True)['version_id']==d['version_id']
    response=client.post(url+'/calendar-presets',json={'revision':d['revision'],'presets':{'holidays':'auto','seasons':'auto'}})
    assert response.status_code==200,response.text
    applied=response.json()['candidate']
    for field in ('characters','world','protagonist_id','controlled_actor_id'):assert applied[field]==original[field]
    assert applied['authoring']['manual_paths']==original['authoring']['manual_paths']
    assert applied['world_clock']['minute']==original['world_clock']['minute']
    for key in ('start_date','start_minute','start_weekday'):assert applied['world_clock']['calendar'][key]==original['world_clock']['calendar'][key]
    assert presets.apply(applied,{'holidays':'auto','seasons':'auto'},True)==applied


def test_overrides_deletion_reload_none_custom_unknown_and_versions():
    s=rich();s=presets.apply(s,dict(holidays='country',country='US',seasons='south'),True)
    p=s['world_clock']['calendar']['profile'];r=p['regional']
    event=presets.occurrences(r,'2026-07-04','2026-07-04')[0]
    r['overrides']=[dict(id=event['id'],removed=True)]
    loaded=json.loads(json.dumps(s));loaded=presets.apply(loaded,dict(holidays='country',country='US',seasons='south'),True)
    assert not presets.occurrences(loaded['world_clock']['calendar']['profile']['regional'],'2026-07-04','2026-07-04')
    p['seasons']=[]
    assert presets.apply(s,dict(holidays='country',country='US',seasons='south'),True)['world_clock']['calendar']['profile']['seasons']==[]
    with pytest.raises(presets.CoverageError):presets.occurrences(r,'1370-01-01','1370-01-02')
    with pytest.raises(presets.CoverageError):presets.occurrences(dict(r,version='old'),'2026-01-01','2026-01-02')
    for geography in ('Европа','Америка','Россия и США'):
        assert presets.resolve(dict(world_type='real_world',geography=geography),{'holidays':'auto','seasons':'auto'})[0] is None
    assert presets.resolve(dict(world_type='alternate',geography='Москва'),{'holidays':'auto','seasons':'auto'})==(None,None)
    assert presets.resolve(dict(world_type='real_world',geography='Бразилия'),{'holidays':'auto','seasons':'auto'})==('BR',None)
    for geography in ('Москва и Буэнос-Айрес','Россия, Москва и Бразилия'):
        assert presets.resolve(dict(world_type='real_world',geography=geography),{'holidays':'auto','seasons':'auto'})==(None,None)


def test_e5_twins_joint_dates_without_rewriting_manual_values():
    from backend.services.draft_calendar import fill_birth_dates
    s=evidence()['candidate_snapshot'];original=deepcopy(s)
    fill_birth_dates(s)
    assert {k:a['birth_date'] for k,a in s['world']['characters'].items()}=={k:a['birth_date'] for k,a in original['world']['characters'].items()}
    for cid in ('katya_volkova','sonya_velichkina'):
        s['world']['characters'][cid]['birth_date']=None
        s['world']['characters'][cid]['birth_provenance']={}
        s['authoring']['calendar_completion']['birth_dates'].pop(cid,None)
    fill_birth_dates(s)
    assert s['world']['characters']['katya_volkova']['birth_date']==s['world']['characters']['sonya_velichkina']['birth_date']
    assert s['world']['characters']['timur_volkov']['birth_date']==original['world']['characters']['timur_volkov']['birth_date']

@pytest.mark.parametrize('day,north,south',[
    ('2026-02-28','Зима','Лето'),('2028-02-29','Зима','Лето'),('2026-03-01','Весна','Осень'),
    ('2026-06-01','Лето','Зима'),('2026-09-01','Осень','Весна'),('2026-12-01','Зима','Лето'),('2027-01-01','Зима','Лето')])
def test_every_season_boundary(day,north,south):
    for mode,expected in [('north',north),('south',south)]:
        s=presets.apply(rich(),{'holidays':'none','seasons':mode},True)
        cal=dict(s['world_clock']['calendar'],start_date=day)
        assert current_time({'meta':{'world_time':cal['start_minute'],'calendar':cal}})['season']==expected


def test_none_country_switch_retains_occurrence_overrides_and_custom_dates():
    choice={'holidays':'country','country':'US','seasons':'north'}
    s=presets.apply(rich(),choice,True);p=s['world_clock']['calendar']['profile']
    event=presets.occurrences(p['regional'],'2026-07-04','2026-07-04')[0]
    p['regional']['overrides']=[dict(id=event['id'],removed=True)]
    p['observances']=[dict(id='family',name='Семейный праздник',month=7,day=4,character_ids=[])]
    s=presets.apply(s,dict(choice,holidays='none'),True)
    s=presets.apply(s,dict(choice,country='RU'),True)
    s=presets.apply(s,choice,True)
    assert not presets.occurrences(s['world_clock']['calendar']['profile']['regional'],'2026-07-04','2026-07-04')
    assert s['world_clock']['calendar']['profile']['observances']==p['observances']


def test_reasoning_only_length_is_missing_review_not_world_defect():
    import threading
    from llm import OutputLimitReached
    from test_draft_response_v4 import JournalRepo,CONFIG,MESSAGES
    from backend.services.draft_response import response,TransportError
    class AccountingRepo(JournalRepo):
        def request_log(self,**kwargs):return [dict(input_tokens=100,output_tokens=20000,reasoning_tokens=20000,cost_usd='0.02')]
    repo=AccountingRepo();journal={};calls=[]
    def generate(messages,limit):
        calls.append(limit)
        if False:yield ''
        raise OutputLimitReached()
    with pytest.raises(TransportError):
        response(repo,'j',journal,'completeness_test',MESSAGES,dict(CONFIG,max_tokens=20000),32768,generate,threading.Event())
    assert len(calls)==1
    assert journal['actual_tokens']==20100 and journal['actual_cost']=='0.02'
    assert journal['responses']['completeness_test']['parts'][0]['text']==''


def test_country_defaults_new_api_and_unknown_year_preview(api):
    client,_=api
    result=client.post('/api/calendar/preview',json={'world_type':'real_world','geography':'Россия, Москва','calendar_start':{'presets':{'holidays':'auto','seasons':'auto'}}})
    assert result.status_code==200,result.text
    assert result.json()['regional']['country']=='RU'
    assert any('год неизвестен' in x for x in result.json()['notices'])


def test_invalid_source_package_and_revision_do_not_write(api):
    client,app=api;repo=app.state.repository;wid,_,_,_=install(client,repo)
    url=f'/api/workspaces/{wid}/draft';d=repo.draft(wid,True)
    r=client.post(url+'/calendar-presets',json={'revision':d['revision'],'presets':{'holidays':'country','country':'DE','subdivision':'INVALID'}})
    assert r.status_code==409
    assert repo.draft(wid,True)['version_id']==d['version_id']
    r=client.post(url+'/calendar-presets',json={'revision':d['revision']+1,'presets':{'holidays':'country','country':'US'}})
    assert r.status_code==409
    assert repo.draft(wid,True)['version_id']==d['version_id']

@pytest.mark.parametrize('country,day',[
 ('RU','06-12'),('DE','10-03'),('FR','07-14'),('GB','12-25'),('IT','06-02'),('ES','10-12'),
 ('PL','11-11'),('US','07-04'),('CA','07-01'),('MX','09-16'),('BR','09-07'),('AR','07-09')])
def test_catalog_country_specific_control_dates(country,day):
    value='2026-'+day
    assert presets.occurrences(dict(country=country,version=presets.VERSION),value,value)

@pytest.mark.parametrize('status',['not_started','stale','failed','completed'])
def test_semantic_state_is_advisory_and_never_disclosed_to_player(api,status):
    client,app=api;repo=app.state.repository;wid,jid,s,_=install(client,repo,True)
    issue=dict(message='PRIVATE author-only finding',severity='blocker')
    repo.save_draft_candidate(jid,s,[],review=dict(status=status,issues=[issue]))
    repo.preparation_progress(jid,'','error',error='PRIVATE provider diagnostic')
    d=repo.draft(wid,True);public=repo.draft(wid)
    assert d['technical_valid'] and d['start_warning']
    assert 'PRIVATE' not in json.dumps(public,ensure_ascii=False)
    result=repo.confirm_draft(wid,d['revision'],d['version_id'],True)
    assert result['save']
    assert repo.draft(wid,True)['review']['issues']==[issue]


def test_custom_profile_and_none_preserve_author_seasons():
    s=rich();s['world_clock']['calendar']['profile']={'system':'custom','month_lengths':[30,30], 'seasons':[{'name':'Сухой период','month':2,'day':1}]}
    s['world_clock']['calendar']['start_date']='0010-01-01'
    before=deepcopy(s)
    applied=presets.apply(s,dict(holidays='country',country='RU',seasons='north'),True)
    assert applied['world_clock']['calendar']['profile']['seasons']==before['world_clock']['calendar']['profile']['seasons']
    assert applied['world_clock']['calendar']['start_date']=='0010-01-01'
    assert applied['authoring']['calendar_presets']['notices']
    disabled=presets.apply(applied,dict(holidays='none',seasons='none'),True)
    assert disabled['world_clock']['calendar']['profile']['seasons']==before['world_clock']['calendar']['profile']['seasons']
    assert presets.preview(disabled)['current']['season'] is None


def test_author_age_disagreement_warns_but_invalid_date_still_blocks(api):
    client,app=api;repo=app.state.repository;wid,jid,s,_=install(client,repo,True)
    cid=s['characters'][0]['id'];s['characters'][0]['fields']['Возраст']='99 лет'
    repo.save_draft_candidate(jid,s,[],review={'status':'failed'})
    repo.preparation_progress(jid,'','stopped')
    d=repo.draft(wid,True)
    assert d['technical_valid'] and d['validation']['semantic_warnings'] and d['start_warning']
    assert repo.confirm_draft(wid,d['revision'],d['version_id'],True)['save']
    s['world']['characters'][cid]['birth_date']='2026-02-30'
    assert inspect_candidate(s,for_start=True)[1]['errors']


def test_existing_78_calendar_checkpoint_preserves_presets_through_turn_reload_rollback(tmp_path):
    from devtools.narrative_test_world import build_fixture
    from backend.repositories.preparation import Repository
    from test_runtime_v3_engine import run as play,raw_for
    from test_engine import CONFIG
    state=build_fixture('calendar-evening');original=deepcopy(state)
    state=presets.apply(state,{'holidays':'country','country':'RU','seasons':'north'},True)
    repo=Repository(tmp_path/'qa78.sqlite');w=repo.create_workspace('QA78 calendar presets')
    repo.import_draft(w['id'],json.dumps(state,ensure_ascii=False),w['revision'],format='json')
    d=repo.draft(w['id'],True);sid=repo.confirm_draft(w['id'],d['revision'],d['version_id'])['save']
    profile=repo.get_snapshot(sid)['world_state']['meta']['calendar']['profile']
    for kind in ('start','turn','turn'):
        before=repo.get_snapshot(sid)
        jid=repo.begin_job(sid,'Осматриваюсь.' if kind=='turn' else '',kind,dict(CONFIG,context_length=262144))
        play(repo,jid,raw_for(before));assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)
        repo=Repository(repo.path)
        assert repo.get_snapshot(sid)['world_state']['meta']['calendar']['profile']==profile
    repo.rollback_last(sid)
    assert Repository(repo.path).get_snapshot(sid)['world_state']['meta']['calendar']['profile']==profile
    assert build_fixture('calendar-evening')==original
