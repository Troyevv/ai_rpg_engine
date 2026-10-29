"""Actual report bytes; reconstructed candidate, not the unavailable frozen user input.

Provider responses for semantic repair/gameplay are controlled offline fixtures.
"""
from copy import deepcopy
from pathlib import Path
from threading import Event
from unittest.mock import patch
import hashlib
import json
import pytest
from backend.services import draft_completeness as review, draft_initial as initial
from backend.services.draft_response import join_fragments,response
from backend.repositories.drafts import candidate_hash
from backend.services.draft_presentation import clock_view
from test_initial_draft_v4 import api,REMOTE,wait_job,rich
from test_draft_response_v4 import JournalRepo,MESSAGES

FIXTURE=Path(__file__).parent/'fixtures/initial_world/generation_response_review.json'

def saved():return json.loads(FIXTURE.read_bytes())
def reconstruct():
    j=saved();slot=j['responses']['world']
    from backend.services.draft_schema import world_state_schema
    text=join_fragments(slot['parts'],slot['assembly'],schema=world_state_schema())
    state,report=initial.inspect_candidate(json.loads(text))
    assert not report['diagnostics']
    return state


def test_actual_four_complete_reports_keep_every_message_and_raw_bytes():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest()=='90b08ec8b348956ea76c55536806a46fa5ff59e2c465fc7e6c9c9aeb50579b6e'
    j=saved();state=reconstruct()
    # Exact user candidate snapshot/settings are absent; do not misrepresent equality.
    assert candidate_hash(state)!=j['review_failures'][0]['candidate_hash']
    for f,count in zip(j['review_failures'],[34,33,33,33]):
        parsed=review.parse(f['response'],state)
        assert len(parsed)==count
        assert [p['message'] for p in parsed]==[p['message'] for p in json.loads(f['response'])['issues']]
        assert any(p.get('protocol_warnings') for p in parsed)
    assert review.parse(j['review_failures'][-1]['response'],state)[5]['path']=='/world_clock/calendar'
    before=deepcopy(j)
    text=response(JournalRepo(),'j',j,'world',MESSAGES,dict(REMOTE,max_tokens=12000),262144,lambda *_:pytest.fail('world replay'),Event())
    assert len(text)==80363 and j['responses']['world']['parts']==before['responses']['world']['parts']
    assert j['actual_tokens']==before['actual_tokens']


@pytest.mark.parametrize('field,value',[('path','/missing'),('related_paths',['/missing']),('patch_paths',['/world']),('path','/characters/999/name')])
def test_optional_navigation_never_authorizes_unsafe_patch(field,value):
    raw=dict(message='Сохранить это замечание',severity='recommendation',**{field:value})
    parsed=review.parse(json.dumps({'issues':[raw]}),rich())[0]
    assert parsed['message']==raw['message'] and not parsed['patch_paths']
    assert parsed['original_issue'][field]==value and parsed['protocol_warnings']
    raw['severity']='blocker'
    with pytest.raises(review.ReportError):review.parse(json.dumps({'issues':[raw]}),rich())


def test_aliases_are_structural_and_do_not_redirect_dynamic_character_state():
    s=rich();cid=s['characters'][0]['id']
    assert review.diagnostic_alias(s,'/characters/'+cid)=='/characters/0'
    assert review.diagnostic_alias(s,'/world/characters/'+cid) is None
    s['characters'].append(deepcopy(s['characters'][0]))
    assert review.diagnostic_alias(s,'/characters/'+cid) is None
    assert review.diagnostic_alias(s,'/world/world/characters/'+cid) is None
    assert review.diagnostic_alias(s,'/characters/bad~2') is None


def test_correction_does_not_replay_full_candidate_or_grow_history():
    s=reconstruct();msgs=review.messages(s,'Intact author text')
    errors=[dict(report_path='/issues/0/path',world_path='/world/world_clock/calendar',message='bad path')]
    correction=review.correction(msgs,'{"issues":[]}',errors)
    body=json.loads(correction[1]['content'])
    assert 'candidate' not in body and body['author_context']=='Intact author text'
    assert body['related_context']['/world_clock/calendar']==s['world_clock']['calendar']
    assert len(correction)==2 and len(json.dumps(correction))<len(json.dumps(msgs))


def test_calendar_and_birth_age_boundaries():
    s=rich();s['world_clock']={'minute':480,'calendar':{'start_minute':480,'start_weekday':4,'start_date':'2026-10-23','profile':{'system':'gregorian'}}}
    assert clock_view(s['world_clock'])['label']=='Пятница, 23 октября 2026, 08:00'
    s['world_clock']['minute']+=1440
    assert clock_view(s['world_clock'])['label']=='Суббота, 24 октября 2026, 08:00'
    cid=s['characters'][0]['id'];s['characters'][0]['fields']['Возраст']='20 лет'
    for birth,valid in [('2006-10-24',True),('2006-10-25',False),('2005-10-25',True),('2005-10-24',False),(None,True)]:
        s['world']['characters'][cid]['birth_date']=birth
        state,report=initial.inspect_candidate(s)
        assert (not any(e['category']=='age_conflict' for e in report['diagnostics']))==valid
        if birth is None:assert state['world']['characters'][cid]['birth_date'] is None
    custom={'minute':1920,'calendar':{'start_minute':480,'start_weekday':1,'start_date':'1370-02-30','profile':{'system':'custom','month_lengths':[30,30],'month_names':['Первый','Второй'],'weekday_names':['Один','Два','Три']}}}
    assert clock_view(custom)['label']=='Три, 1 Первый 1371, 08:00'
    assert 'дата неизвестна' in clock_view({'minute':480,'calendar':{'start_minute':480,'start_weekday':4}})['label']


def test_complete_saved_world_local_recovery_repair_edit_start_reload(api):
    client,app=api;repo=app.state.repository
    wid=client.post('/api/workspaces',json={'name':'Actual complete journal'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    # Original author input is NOT in the export. This is explicit test metadata,
    # not a substitute user brief or a claim of live workspace reproduction.
    source='Offline replay of saved candidate; original frozen author input unavailable.'
    with patch('backend.services.preparation.chat_stream',side_effect=RuntimeError('offline setup')):
        jid=client.post(url+'/generate',json={'revision':0,'text':source,'config':dict(REMOTE,context_length=262144),'api_key':'fixture'}).json()['id'];wait_job(client,jid)
    j=saved();j.pop('requests');j.pop('recovery');j.pop('binding');j['recovery_epoch']=0
    repo.save_response_journal(jid,j)
    base=reconstruct();fixes=[]
    for i,c in enumerate(base['characters']):
        if c['id'] not in ('char_timur','char_marina','char_sergey'):continue
        bio=c['fields']['Биография'].replace('Родился после усыновления Ильи','Родился за шесть лет до усыновления Ильи')
        bio=bio.replace('Они усыновили Илью, а позже родились Тимур и Катя.','Тимур уже родился, когда они усыновили Илью; позже родилась Катя.')
        bio=bio.replace('После нескольких лет брака они не могли иметь детей; Марина тяжело переживала.','После рождения Тимура они несколько лет не могли завести второго ребёнка; Марина тяжело переживала.')
        bio=bio.replace('Женился на Марине, но у них не было детей.','Женился на Марине; после рождения Тимура они несколько лет не могли завести второго ребёнка.')
        if bio!=c['fields']['Биография']:fixes.append(dict(path=f'/characters/{i}/fields/Биография',value=bio))
    # Controlled semantic repair reconciles the prose to the existing court location.
    # The journal has no prosecutor location; Python must not invent one.
    prosecutor=base['world']['characters']['char_yura']['location']
    fixes.append(dict(path='/world/characters/char_yura/situation',value='Уже находится у здания суда, готовится к заседанию в 10:00.'))
    calls=[]
    def provider(**kw):
        calls.append(kw);n=len(calls)
        if kw['messages'][0]['content'].startswith(review.MARKER):
            assert source in kw['messages'][1]['content']
            if n==1:
                yield json.dumps({'issues':[dict(path=fixes[0]['path'],message='Хронология рождения противоречит возрастам, местоположение Юры не согласовано с ситуацией.',severity='blocker',patch_paths=[p['path'] for p in fixes])]})
            else:
                yield json.dumps({'issues':[dict(message='Необязательное уточнение быта',severity='recommendation',path='/missing/optional')]})
        else:
            assert 'patches' in kw['messages'][0]['content'];yield json.dumps({'patches':fixes},ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        assert client.post(url+'/resume',json={'revision':0,'api_key':'fixture'}).status_code==200
        job=wait_job(client,jid);assert job['status']=='saved',job
        assert len(calls)==3 # review, exact patch, review; zero world/continuation calls
        d=client.get(url+'?author=true').json();state=deepcopy(d['state'])
        for field in ('knowledge','relationships','objective_relations','contacts','residences'):
            assert state['world'][field]==base['world'][field]
        d=client.patch(url,json={'revision':d['revision'],'operation':'patch','kind':'campaign','field':'title','value':'Сохранённый мир — правка автора'}).json()
        assert d['review']['status']=='stale'
        assert client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id']}).status_code==409
        assert client.post(url+'/resume',json={'revision':d['revision'],'api_key':'fixture'}).status_code==200
        assert wait_job(client,jid)['status']=='saved'
    assert len(calls)==4
    d=client.get(url+'?author=true').json();raw=client.get(url+'/raw').json()
    assert raw['candidate_snapshot'] and raw['author_input']['text']==source
    assert raw['responses']['world']['parts']==saved()['responses']['world']['parts']
    assert raw['actual_tokens']>=saved()['actual_tokens']
    start=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id'],'accept_warnings':True});assert start.status_code==200,start.text
    from test_runtime_v3_engine import run as play,raw_for
    from test_engine import CONFIG
    from backend.repositories.preparation import Repository
    sid=start.json()['save']
    for kind in ('start','turn','turn'):
        snap=repo.get_snapshot(sid);turn=repo.begin_job(sid,'Осматриваюсь.' if kind=='turn' else '',kind,dict(CONFIG,provider='deepseek',model='deepseek-flash',context_length=262144))
        play(repo,turn,raw_for(snap));assert repo.get_job(turn)['status']=='saved',repo.get_job(turn)['error']
        repo=Repository(repo.path)
        assert repo.get_snapshot(sid)['world_state']['characters']['char_yura']['location_id']==prosecutor


def test_nullable_extension_edit_and_string_evidence_use_runtime_contract():
    from presentation_fixture import presentation_world
    from backend.services import draft_world
    s=presentation_world()
    s=draft_world.patch(s,'residences','home_b','until',None)
    assert s['world']['residences']['home_b']['until'] is None
    s=draft_world.patch(s,'conditions','condition_a','evidence','Новое основание автора')
    assert s['world']['conditions']['condition_a']['evidence']=='Новое основание автора'
    with pytest.raises(ValueError):draft_world.patch(s,'conditions','condition_a','effects',{'can_move':'yes'})


def test_populated_synthetic_world_roundtrip_and_author_player_separation(api):
    from presentation_fixture import presentation_world
    client,app=api;s=presentation_world()
    wid=client.post('/api/workspaces',json={'name':'Synthetic coverage'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    assert client.post(url+'/import',json={'revision':0,'format':'json','text':json.dumps(s)}).status_code==200
    author=client.get(url+'?author=true').json();player=client.get(url).json()
    assert author['presentation']['clock']['label']=='Пятница, 23 октября 2026, 08:00'
    for key in ('contacts','conditions','residences','possessions','objective_relations','organizations','roles'):
        assert author['state']['world'][key]
    assert not player['state']['world'].get('contacts')
    assert 'source_turn' not in player.get('editor',{}) if player.get('editor') else True
    assert author['editor']['enums']['contacts']['kind']==['person','service','shared']
    started=client.post(url+'/confirm',json={'revision':author['revision'],'version_id':author['version_id']});assert started.status_code==200,started.text
    snap=app.state.repository.get_snapshot(started.json()['save'])['world_state']
    for group in ('contacts','conditions','residences','possessions'):assert snap[group]==s['world'][group]


def test_separate_family_world_preserves_all_lifecycle_records(api):
    from presentation_fixture import family_world
    client,app=api;s=family_world();wid=client.post('/api/workspaces',json={'name':'Synthetic family'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    imported=client.post(url+'/import',json={'revision':0,'format':'json','text':json.dumps(s)});assert imported.status_code==200,imported.text
    d=client.get(url+'?author=true').json()
    for group in ('reproductive_events','pregnancies','naming_decisions'):assert d['state']['world'][group]==s['world'][group]
    start=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id']});assert start.status_code==200,start.text
    from backend.repositories.preparation import Repository
    reopened=Repository(app.state.repository.path).get_snapshot(start.json()['save'])['world_state']
    for group in ('reproductive_events','pregnancies','naming_decisions'):assert reopened[group]==s['world'][group]


def test_subset_correction_cannot_drop_or_replace_valid_siblings():
    valid={'path':'/campaign/title','message':'Существенное противоречие','patch_paths':['/campaign/title']}
    invalid={'severity':'misspelled','message':'Второй пункт'}
    previous=json.dumps({'issues':[valid,invalid]})
    errors=[dict(report_path='/issues/1/severity',world_path=None,message='unknown severity')]
    result=review.merge_correction(json.dumps({'issues':[dict(invalid,severity='recommendation')]}),previous,errors)
    assert json.loads(result)['issues'][0]==valid
    assert len(review.parse(result,rich()))==2
    with pytest.raises(review.ReportError):review.merge_correction('{"issues":[]}',previous,errors)
    with pytest.raises(review.ReportError):review.merge_correction(json.dumps({'issues':[valid,invalid]}),previous,errors)


def test_birth_field_generation_gets_card_age_and_calendar_without_other_world():
    from backend.services.draft_generation import messages_for
    s=rich();cid=s['characters'][0]['id']
    class Repo:
        def draft(self,*args,**kwargs):return {'state':s}
    msgs=messages_for(Repo(),{'workspace_id':'fixture'},{'_draft_task':'field','_draft_target':{'kind':'actor','id':cid,'field':'birth_date'},'_draft_input':'Выбери подходящий день рождения.'})
    payload=json.loads(msgs[1]['content'])
    assert payload['world_clock']==s['world_clock']
    assert payload['card']==s['characters'][0]
    assert payload['field_schema']['anyOf']
    assert 'world' not in payload


def test_knowledge_evidence_and_optional_birth_edit_preserve_runtime_types():
    from backend.services import draft_world
    s=initial.inspect_candidate(rich())[0];cid=s['characters'][0]['id']
    s['world']['characters'][cid]['birth_date']='2000-01-01'
    out=draft_world.patch(s,'actor',cid,'birth_date',None)
    assert out['world']['characters'][cid]['birth_date'] is None
    key=next(iter(s['world']['knowledge']))
    out=draft_world.patch(s,'knowledge',key,'evidence','Явное основание автора')
    assert out['world']['knowledge'][key]['evidence']=='Явное основание автора'
