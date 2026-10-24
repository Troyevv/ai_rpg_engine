"""Real-response regressions. Reviewer/repair replies are controlled, not live LLM."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from test_api import api, REMOTE, wait_job
from backend.services import draft_initial, draft_world, draft_completeness as review, draft_repair
from backend.repositories.preparation import Repository
from backend.services.preparation import Preparation, Handle
from backend.services.draft_generation import run

REAL_PATH=Path('tests/fixtures/initial_world/volkov_deepseek_real.json')
SOURCE=Path('tests/fixtures/initial_world/volkov_user_brief.txt').read_text()
# The original fixture does not contain this later author clarification. Preserve
# it verbatim and append the explicitly supplied event, rather than inventing it.
DINNER=SOURCE+'\nУточнение: вчера вечером Сергей сообщил правду об усыновлении за семейным ужином. Присутствовала вся семья: Сергей, Марина, Тимур, Катя и Илья. Это раскрытие произошло после описанного прежнего состояния незнания.\n'


def real():return json.loads(REAL_PATH.read_text())
def candidate():return draft_world.prepare(draft_initial.normalize(real()))


def corrections():
    """Localized, author-grounded mock repair, retaining every original record."""
    out=[]
    def add(path,value):out.append(dict(path=path,value=value))
    add('/world_clock/calendar/start_weekday',4)
    # No invented 20:00/21:00 for yesterday evening.
    add('/world/events/e1/minute',None);add('/world/events/e2/minute',None)
    add('/world/events/e1/text','Сергей за семейным ужином сообщил Илье, Марине, Тимуру и Кате правду об усыновлении Ильи.')
    add('/world/events/e1/participants',['c1','c2','c3','c5','c7'])
    add('/world/events/e1/witnesses',['c1','c2','c3','c5','c7'])
    add('/world/events/e1/medium','conversation')
    for key in ('k4','k5'):
        add('/world/knowledge/'+key+'/status','known')
        add('/world/knowledge/'+key+'/source_event_id','e1')
    add('/world/characters/c1/intentions',[])
    add('/world/characters/c1/goals',['Построить жизнь самостоятельно'])
    add('/world/characters/c1/emotion','')
    relations=[]
    for parent in ('c2','c7'):
        relations.append((parent,'c1','adoptive_parent'))
        relations.extend((parent,child,'parent') for child in ('c3','c5'))
    relations.extend([('c3','c5','sibling'),('c1','c3','sibling'),('c1','c5','sibling'),('c4','c5','close_friend'),('c1','c6','friend'),('c1','c8','friend'),('c1','c8','coworker')])
    for i,(a,b,kind) in enumerate(relations):
        key='tie_'+str(i)
        add('/world/objective_relations/'+key,dict(id=key,kind=kind,source_id=a,target_id=b,context='Социальная связь семьи и профессионального окружения; усыновление не означает биологического родства.'))
    for cid,title,kind,org in [('c1','Государственный адвокат','occupation',None),('c6','Помощник прокурора','occupation',None),('c8','Юрист','occupation','o1'),('c4','Учится на биолога','education',None),('c5','Учится на юриста','education',None)]:
        key='role_'+cid
        add('/world/roles/'+key,dict(id=key,actor_id=cid,title=title,kind=kind,organization_id=org))
    for cid in ('c1','c2','c3','c5','c7'):
        key='home_'+cid
        add('/world/residences/'+key,dict(id=key,actor_id=cid,location_id='l3' if cid=='c1' else 'l1'))
    for i,name in enumerate(('Банк','IT-компания','Страховая компания','Строительная компания','Юридическая фирма')):
        key='subsidiary_'+str(i);fid='ownership_'+str(i)
        add('/world/organizations/'+key,dict(id=key,name=name))
        add('/world/facts/'+fid,dict(id=fid,text=name+' входит в Apex Group Inc.',secret=False,character_ids=[],claim=dict(subject_id=key,predicate='parent_organization',value='o1')))
    return out


def findings():
    return [dict(path=p['path'],message='Несогласованность с заданными обстоятельствами; исправить '+p['path'],related_paths=['/world/events/e1','/world/facts/f1','/characters/0']) for p in corrections()]


def test_real_response_reproduces_semantic_holes_despite_canonical_validity():
    raw=real();s=candidate()
    assert raw['world_clock']=={'minute':4800,'last_event_time':'День 5 (Пт) 08:00'}
    assert raw['scene_meta']['time']=='День 4 (Чт) 08:00'
    assert raw['world']['events']['e1']['minute']//1440==4800//1440
    assert all(not raw['world'][k] for k in ('objective_relations','roles','residences'))
    assert raw['world']['knowledge']['k4']['status']=='unknown'
    assert raw['world']['characters']['c1']['intentions']==['Скрыть своё эмоциональное состояние']
    draft_initial.canonical_check(s)  # Demonstrates why type checks alone fail.
    payload=json.loads(review.messages(s,DINNER)[-1]['content'])
    assert payload['author_context']==DINNER
    assert payload['candidate']['characters']==s['characters']
    assert payload['candidate']['world']['events']==raw['world']['events']
    errors=review.parse(json.dumps({'issues':findings()}),s)
    assert len(errors)==len(corrections())
    assert all(e['category']=='semantic_completeness' for e in errors)


def test_calendar_projection_is_deterministic_and_preserves_unknown_date():
    s=candidate()
    assert s['world_clock']['minute']==4800
    assert s['world_clock']['calendar']['start_date'] is None
    assert s['world_clock']['last_event_time']==s['scene_meta']['time']
    assert 'Чт' in s['scene_meta']['time']
    s['world_clock']['calendar']['start_weekday']=4
    s=draft_world.prepare(s)
    assert 'Пт' in s['scene_meta']['time'] and '08:00' in s['scene_meta']['time']
    assert s['world_clock']['minute']==4800  # Never parsed from old text labels.
    s['world_clock']['calendar']['start_date']='2026-10-23'
    s=draft_world.prepare(draft_initial.normalize(s))
    assert '2026-10-23' in s['scene_meta']['time']
    assert draft_initial.canonical_check(s).snapshot['world_state']['meta']['calendar']['start_date']=='2026-10-23'


def test_local_repair_retains_cards_relationships_and_unaffected_secrets():
    s=candidate();errors=review.parse(json.dumps({'issues':findings()}),s)
    messages,paths=draft_repair.request(json.dumps(s),errors,DINNER)
    sent=json.loads(messages[-1]['content'])
    assert sent['author_context']==DINNER
    assert sent['related']['/world/events/e1']==s['world']['events']['e1']
    assert '/characters/1' not in sent['related']
    repaired=json.loads(draft_repair.apply(json.dumps(s),json.dumps({'patches':corrections()}),paths))
    assert repaired['characters']==s['characters']
    assert repaired['world']['relationships']==s['world']['relationships']
    for key in ('k6','k7','k8'):assert repaired['world']['knowledge'][key]==s['world']['knowledge'][key]
    assert repaired['world']['facts']['f1']==s['world']['facts']['f1']
    prepared=draft_world.prepare(draft_initial.normalize(repaired))
    canonical=draft_initial.canonical_check(prepared)
    world=canonical.snapshot['world_state']
    assert len(world['organizations'])==6
    assert all(r['kind']!='parent' for r in world['objective_relations'].values() if r['target_id']=='c1')
    assert world['roles']['role_c1']['organization_id'] is None
    assert world['residences']['home_c1']['location_id']=='l3'
    assert [g['text'] for g in world['characters']['c1']['goals']]==['Построить жизнь самостоятельно']
    assert not world['characters']['c1']['intentions']
    assert world['knowledge']['c3:f1']['status']=='known'
    history=canonical.history
    assert any(k['actor_id']=='c3' and k['source_event_id']=='e1' and k['provenance_complete'] for k in history['knowledge_acquisitions'])
    assert all(e['minute'] is None for e in history['events'])


@pytest.mark.parametrize('path', ['/world','/world/roles','/world/characters/c1','/characters/0','/world/events/nope/minute'])
def test_review_cannot_authorize_broad_or_impossible_changes(path):
    if path=='/world/events/nope/minute':
        with pytest.raises(review.ReportError):review.parse(json.dumps({'issues':[dict(path=path,message='bad')]}),candidate())
    else:
        issues=review.parse(json.dumps({'issues':[dict(path=path,message='bad')]}),candidate())
        assert issues[0]['patch_paths']==[]
        with pytest.raises(ValueError):draft_repair.request(json.dumps(candidate()),issues)


@pytest.mark.parametrize('section,key,field,value',[
    ('knowledge','k1','source_event_id','missing'),
    ('organizations','o1','location_ids',['missing']),
    ('events','e1','witnesses',['missing']),
])
def test_bad_cross_references_have_exact_repair_paths(section,key,field,value):
    s=candidate();s['world'][section][key][field]=value
    with pytest.raises(draft_initial.DraftErrors) as exc:draft_initial.validate_typed(s)
    assert any(e['path'].startswith(f'/world/{section}/{key}/{field}') for e in exc.value.errors)


def test_real_response_review_repair_start_turn_reload(api):
    client,app=api;workspace=client.post('/api/workspaces',json={'name':'Real Volkov response'}).json()
    path=f"/api/workspaces/{workspace['id']}/draft";calls=[];reviews=[]
    def stream(**kw):
        calls.append(kw)
        if kw['messages'][0]['content'].startswith(review.MARKER):
            data=json.loads(kw['messages'][-1]['content']);reviews.append(data)
            assert data['author_context'].find(DINNER)>=0
            yield json.dumps({'issues':findings() if len(reviews)==1 else []})
        elif 'patches' in kw['messages'][0]['content']:
            request=json.loads(kw['messages'][-1]['content'])
            assert len(request['errors'])==len(corrections())
            yield json.dumps({'patches':corrections()},ensure_ascii=False)
        else:yield REAL_PATH.read_text()
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        res=client.post(path+'/generate',json={'revision':0,'text':DINNER,'config':dict(REMOTE,context_length=65536),'api_key':'test'})
        job=wait_job(client,res.json()['id']);assert job['status']=='saved',job
    assert len(calls)==4 and len(reviews)==2
    assert reviews[1]['candidate']['world']['knowledge']['k4']['status']=='known'
    draft=client.get(path+'?author=true').json()
    for before,after in zip(real()['characters'],draft['state']['characters']):
        for field in ('Биография','Характер','Внешность'):assert before['fields'][field]==after['fields'][field]
    confirmed=client.post(path+'/confirm',json={'revision':draft['revision'],'version_id':draft['version_id']})
    assert confirmed.status_code==200,confirmed.text
    sid=confirmed.json()['save'];repo=app.state.repository
    from test_runtime_v3_engine import run as play, raw_for
    from test_engine import CONFIG
    for kind in ('start','turn'):
        before=repo.get_snapshot(sid);jid=repo.begin_job(sid,'Осматриваюсь.' if kind=='turn' else '',kind,CONFIG)
        play(repo,jid,raw_for(before));assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
        repo=Repository(repo.path);world=repo.get_snapshot(sid)['world_state']
        assert world['meta']['calendar']['start_weekday']==4
        assert world['meta']['calendar']['start_date'] is None
        assert world['knowledge']['c5:f1']['status']=='known'
        assert world['knowledge']['c8:f1']['status']=='unknown'
        assert len(world['roles'])==5 and len(world['organizations'])==6


def test_unresolved_semantics_cannot_save_and_repair_budget_is_shared(tmp_path):
    repo=Repository(tmp_path/'fail.sqlite');w=repo.create_workspace('semantic failure')
    cfg=dict(REMOTE,context_length=65536,_draft_task='world',_draft_input=DINNER,_use_idea=False)
    jid=repo.begin_preparation(w['id'],'draft_world',DINNER,cfg,0);cfg=json.loads(repo.preparation_job(jid)['config_json']);calls=[]
    def stream(**kw):
        calls.append(kw)
        if kw['messages'][0]['content'].startswith(review.MARKER):
            yield json.dumps({'issues':[dict(path='/world/characters/c1/intentions',message='Незаданное намерение.')]})
        elif 'patches' in kw['messages'][0]['content']:
            yield json.dumps({'patches':[dict(path='/world/characters/c1/intentions',value=['Скрыть своё эмоциональное состояние'])]})
        else:yield REAL_PATH.read_text()
    with pytest.raises(ValueError,match='Две попытки'):
        run(Preparation(repo),jid,cfg,None,Handle(),None,stream)
    assert len(calls)==4  # generation + cached review + 2 repairs, never regeneration
    assert repo.draft(w['id'],True)['state'] is None
    # Replay completed journal after a restart: no extra provider requests.
    with pytest.raises(ValueError,match='Две попытки'):
        run(Preparation(Repository(repo.path)),jid,cfg,None,Handle(),None,lambda **kw:pytest.fail('replayed paid request'))


def test_malformed_review_is_not_semantic_acceptance():
    for reply in ('{}','{"issues":null}','{"issues":[],"approved":true}'):
        with pytest.raises(ValueError):review.parse(reply,candidate())
