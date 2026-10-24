from copy import deepcopy
import json
from unittest.mock import patch
import pytest
from backend.services import draft_initial as initial, draft_relations as relations, draft_repair
from backend.runtime_v3.life import SYMMETRIC
from test_initial_draft_v4 import rich, api, REMOTE, SHORT, wait_job


def pair(kind='sibling',reverse=True):
    state=rich();a,b=[c['id'] for c in state['characters'][:2]]
    one=dict(id='a',kind=kind,source_id=a,target_id=b,context='Брат и сестра',evidence='Документы')
    two=dict(one,id='b',source_id=b if reverse else a,target_id=a if reverse else b,context='Сестра и брат')
    state['world']['objective_relations']={'b':two,'a':one}
    return state


@pytest.mark.parametrize('kind',sorted(SYMMETRIC))
@pytest.mark.parametrize('reverse',[True,False])
def test_lossless_deterministic_merge(kind,reverse):
    state=pair(kind,reverse);before=deepcopy(state)
    state['refs']={'relation_ids':['a','b'],'objective_relation_id':'b','text':'b'}
    merged=relations.merge(state)
    assert set(merged['world']['objective_relations'])=={'a'}
    assert merged['world']['objective_relations']['a']['context']=='Брат и сестра\nСестра и брат'
    assert merged['refs']=={'relation_ids':['a','a'],'objective_relation_id':'a','text':'b'}
    assert relations.merge(merged)==merged
    state['world']['objective_relations']=dict(reversed(list(state['world']['objective_relations'].items())))
    assert relations.merge(state)==merged
    assert before['world']['relationships']==merged['world']['relationships']


@pytest.mark.parametrize('field,value',[('since',10),('since_date','2020-01-01'),('fact_id','ownership'),('source_turn',3)])
def test_conflicts_get_local_exact_paths(field,value):
    state=pair();state['world']['objective_relations']['b'][field]=value
    result,report=initial.inspect_candidate(state)
    errors=[e for e in report['diagnostics'] if e['category']=='relation_conflict']
    assert errors and set(result['world']['objective_relations'])=={'a','b'}
    messages,paths=draft_repair.request(json.dumps(result),errors)
    assert set(paths)=={f'/world/objective_relations/{rid}/{field}' for rid in ('a','b')}
    payload=json.loads(messages[-1]['content'])
    assert {'/world/objective_relations/a','/world/objective_relations/b'}<=set(payload['related'])
    assert '/characters/0' in payload['related']
    with pytest.raises(ValueError):draft_repair.apply(json.dumps(result),json.dumps({'patches':[{'path':'/world/objective_relations/b/status','value':'closed'}]}),paths)


def test_history_and_invalid_records_are_not_salvaged():
    state=pair();rows=state['world']['objective_relations']
    rows['old']=dict(rows['a'],id='old',status='closed',since=0,until=5,outcome='ended')
    rows['older']=dict(rows['old'],id='older',since=1)
    merged=relations.merge(state)
    assert set(merged['world']['objective_relations'])=={'a','old','older'}
    state['world']['objective_relations']['b']['context']=['invalid']
    assert len(relations.merge(state)['world']['objective_relations'])==4


def test_saved_conflict_resume_repairs_without_generation(api):
    client,app=api;url='/api/workspaces/'+client.post('/api/workspaces',json={'name':'relations'}).json()['id']+'/draft'
    state=pair();state['world']['objective_relations']['b']['since']=10
    calls=[]
    def fail(**kw):
        calls.append(kw);yield json.dumps(state) if len(calls)==1 else '{"patches":[]}'
    with patch('backend.services.preparation.chat_stream',side_effect=fail):
        jid=client.post(url+'/generate',json={'revision':0,'text':SHORT,'config':REMOTE,'api_key':'test'}).json()['id']
        assert wait_job(client,jid)['status']=='error'
    d=client.get(url+'?author=true').json()
    assert d['relation_merges'][0]['safe'] is False
    assert client.post(url+'/merge-relations',json={'revision':d['revision'],'ids':['a','b']}).status_code==409
    resumed=[]
    def repair(**kw):
        resumed.append(kw)
        if len(resumed)==1:
            payload=json.loads(kw['messages'][1]['content']);assert 'related' in payload
            yield '{"patches":[{"path":"/world/objective_relations/b/since","value":null}]}'
        else:yield '{"issues":[]}'
    with patch('backend.services.preparation.chat_stream',side_effect=repair):
        assert client.post(url+'/resume',json={'revision':d['revision'],'api_key':'test'}).status_code==200
        final=wait_job(client,jid);assert final['status']=='saved',final
    assert len(resumed)==2
    d=client.get(url+'?author=true').json()
    assert set(d['state']['world']['objective_relations'])=={'a'}
    assert d['state']['world']['objective_relations']['a'].get('status','active')=='active'
    assert client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id']}).status_code==200


def test_three_duplicates_and_closed_identical_phases():
    state=pair();rows=state['world']['objective_relations']
    rows['c']=dict(rows['a'],id='c',context='Третье свидетельство')
    rows['past']=dict(rows['a'],id='past',status='closed',until=4,outcome='ended')
    rows['past2']=dict(rows['past'],id='past2')
    merged=relations.merge(state)
    assert set(merged['world']['objective_relations'])=={'a','past','past2'}
    assert merged['world']['objective_relations']['a']['context']=='Брат и сестра\nСестра и брат\nТретье свидетельство'
    assert relations.merge(merged)==merged


def test_author_merge_revision_privacy_and_preserved_review(api):
    client,app=api;repo=app.state.repository
    wid=client.post('/api/workspaces',json={'name':'old candidate'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    client.post(url+'/import',json={'revision':0,'format':'json','text':json.dumps(rich())})
    d=client.get(url+'?author=true').json()
    d=client.patch(url+'/candidate',json={'revision':d['revision'],'path':'/world/objective_relations','value':pair()['world']['objective_relations']}).json()
    assert client.get(url).json()['relation_merges']==[]
    old_revision=d['revision']
    r=client.post(url+'/merge-relations',json={'revision':old_revision,'ids':['a','b']})
    assert r.status_code==200,r.text
    assert set(r.json()['candidate']['world']['objective_relations'])=={'a'}
    assert client.post(url+'/merge-relations',json={'revision':old_revision,'ids':['a','b']}).status_code==409
    # The original two records remain available in append-only author history.
    with repo.connect() as db:
        previous=json.loads(repo._draft_head(db,wid)['content'])
    assert previous['candidate'] is True


def test_prose_contradiction_is_reviewed_then_locally_repaired(api):
    client,app=api;wid=client.post('/api/workspaces',json={'name':'text conflict'}).json()['id'];url=f'/api/workspaces/{wid}/draft'
    state=pair();state['world']['objective_relations']['b']['context']='Они не родственники, sibling ошибочен.'
    calls=[]
    def stream(**kw):
        calls.append(kw)
        if len(calls)==1:yield json.dumps(state)
        elif len(calls)==2:
            assert 'Они не родственники' in kw['messages'][1]['content'] and 'Брат и сестра' in kw['messages'][1]['content']
            yield json.dumps({'issues':[{'path':'/world/objective_relations/a/context','patch_paths':['/world/objective_relations/a/context'],'message':'Описания родства противоречат друг другу.','severity':'blocker'}]})
        elif len(calls)==3:
            payload=json.loads(kw['messages'][1]['content'])
            assert payload['errors'][0]['path']=='/world/objective_relations/a/context'
            yield '{"patches":[{"path":"/world/objective_relations/a/context","value":"Брат и сестра"}]}'
        else:yield '{"issues":[]}'
    with patch('backend.services.preparation.chat_stream',side_effect=stream):
        jid=client.post(url+'/generate',json={'revision':0,'text':SHORT,'config':REMOTE,'api_key':'test'}).json()['id']
        result=wait_job(client,jid);assert result['status']=='saved',result
    assert len(calls)==4
    assert client.get(url+'?author=true').json()['state']['world']['objective_relations']['a']['context']=='Брат и сестра'


@pytest.mark.parametrize('state',[None,[],{'world':[]},{'world':{'objective_relations':[]}}])
def test_malformed_candidate_does_not_break_author_diagnostics(state):
    assert relations.plans(state)==[]


def test_escaped_conflict_paths():
    state=pair();rows=state['world']['objective_relations']
    rows['x/y~z']=dict(rows.pop('b'),id='x/y~z',since=20)
    checked,report=initial.inspect_candidate(state)
    errors=[e for e in report['diagnostics'] if e['category']=='relation_conflict']
    _,paths=draft_repair.request(json.dumps(checked),errors)
    assert '/world/objective_relations/x~1y~0z/since' in paths


def test_import_normalization_export_and_start_without_provider(api):
    client,app=api;url='/api/workspaces/'+client.post('/api/workspaces',json={'name':'manual relations'}).json()['id']+'/draft'
    with patch('backend.services.preparation.chat_stream',side_effect=AssertionError('no paid import')):
        r=client.post(url+'/import',json={'revision':0,'format':'json','text':json.dumps(pair())});assert r.status_code==200,r.text
        d=client.get(url+'?author=true').json()
        assert len(d['state']['world']['objective_relations'])==1
        exported=client.get(url+'/export',params={'version_id':d['version_id'],'format':'json'}).json()
        assert exported['world']['objective_relations']==d['state']['world']['objective_relations']
        r=client.post(url+'/confirm',json={'revision':d['revision'],'version_id':d['version_id']});assert r.status_code==200,r.text


def test_invalid_kind_is_not_a_root_level_merge_failure():
    state=pair();state['world']['objective_relations']['b']['kind']=['sibling']
    _,report=initial.inspect_candidate(state)
    assert '/world/objective_relations/b/kind' in {e['path'] for e in report['diagnostics']}
    assert all(e['path']!='/' for e in report['diagnostics'])
