"""Issue #192: user decisions, scoped writes, immutable preview and version safety."""
import json
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import pytest
from test_api import api, REMOTE, wait_job


def imported(client):
    state=json.loads((Path(__file__).parent/'fixtures/initial_world/workshop188.json').read_text())
    wid=client.post('/api/workspaces',json={'name':'Мастерская 192'}).json()['id']
    url=f'/api/workspaces/{wid}/draft'
    response=client.post(url+'/import',json={'revision':0,'format':'json','text':json.dumps(state,ensure_ascii=False)})
    assert response.status_code==200,response.text
    return wid,url,client.get(url+'?author=true').json()


@pytest.mark.parametrize('kind,values',[('character',{'name':'Новый знакомый','fields.Биография':'Приехал вчера.'}),('location',{'name':'Читальня','text':'Тихая комната.'}),('fact',{'text':'Под окном растёт клён.'}),('thread',{'description':'Подготовить встречу.'}),('event',{'text':'Открылась читальня.'}),('scene',{'text':'У окна стоит пустое кресло.'})])
def test_create_requires_content_and_writes_one_version(api,kind,values):
    client,_=api;wid,url,before=imported(client)
    for bad in (None,{}, {next(iter(values)):'  '}):
        r=client.patch(url,json={'revision':before['revision'],'operation':'add','kind':kind,'value':bad})
        assert r.status_code==409,r.text
        now=client.get(url+'?author=true').json()
        assert (now['revision'],now['history'],now['state'])==(before['revision'],before['history'],before['state'])
    r=client.patch(url,json={'revision':before['revision'],'operation':'add','kind':kind,'value':values})
    assert r.status_code==200,r.text
    after=r.json();assert after['revision']==before['revision']+1
    assert len(after['history'])==len(before['history'])+1
    from backend.services.draft_world import entity
    item=entity(after['state'],kind,after['entity_id'])
    for key,value in values.items():assert (item['fields'][key[7:]] if key.startswith('fields.') else item[key])==value


def test_directed_add_exact_pair_duplicate_and_no_protagonist(api):
    client,_=api;wid,url,before=imported(client)
    created=client.patch(url,json={'revision':before['revision'],'operation':'add','kind':'character','value':{'name':'Адресат'}})
    assert created.status_code==200,created.text
    target=created.json()['entity_id'];before=created.json()
    state=before['state'];ids=[c['id'] for c in state['characters']]
    source=next(c for c in ids if c!=state['controlled_actor_id'])
    value={'source_id':source,'target_id':target,'context':'Новое знакомство.'}
    r=client.patch(url,json={'revision':before['revision'],'operation':'add','kind':'relationship','value':value})
    assert r.status_code==200,r.text
    after=r.json();created=after['state']['world']['relationships'][after['entity_id']]
    assert all(created[k]==v for k,v in value.items())
    old_pairs=state['world']['relationships'];new_pairs=after['state']['world']['relationships']
    assert len(new_pairs)==len(old_pairs)+1 and all(new_pairs[k]==v for k,v in old_pairs.items())
    for invalid in (value,{'source_id':source}, {'source_id':source,'target_id':source},{'source_id':'missing','target_id':target}):
        assert client.patch(url,json={'revision':after['revision'],'operation':'add','kind':'relationship','value':invalid}).status_code==409
        now=client.get(url+'?author=true').json();assert now['revision']==after['revision'];assert now['state']==after['state']


def test_atomic_fields_version_preview_ownership_restore_and_conflict(api):
    client,_=api;wid,url,before=imported(client)
    cid=before['state']['characters'][0]['id']
    r=client.patch(url,json={'revision':before['revision'],'operation':'patch_fields','kind':'character','entity_id':cid,'value':{'name':'Новое имя','fields.Биография':'Новая биография.'}})
    assert r.status_code==200,r.text
    after=r.json();assert after['revision']==before['revision']+1
    assert client.patch(url,json={'revision':before['revision'],'operation':'patch_fields','kind':'character','entity_id':cid,'value':{'name':'Потерянная правка'}}).status_code==409
    assert client.patch(url,json={'revision':after['revision'],'operation':'patch_fields','kind':'character','entity_id':cid,'value':{'name':'Не сохранять','fields.Биография':42}}).status_code==409
    assert client.get(url+'?author=true').json()['state']==after['state']
    endpoint=url+f"/versions/{before['version_id']}"
    assert client.get(endpoint).status_code==409
    snap=client.get(endpoint+'?author=true');assert snap.status_code==200,snap.text
    assert snap.json()['state']==before['state']
    other,other_url,_=imported(client)
    assert client.get(other_url+f"/versions/{before['version_id']}?author=true").status_code==409
    assert client.get(url+'?author=true').json()['revision']==after['revision']
    restored=client.patch(url,json={'revision':after['revision'],'operation':'restore','source_id':before['version_id']}).json()
    assert restored['state']==before['state'];assert restored['revision']==after['revision']+1
    assert len(restored['history'])==len(before['history'])+2


@pytest.mark.parametrize('decision',['accept','reject','stale'])
def test_field_variant_preview_decision_is_scoped_and_single_call(api,decision):
    client,_=api;wid,url,before=imported(client);cid=before['state']['characters'][0]['id']
    calls=[]
    def provider(**kwargs):
        calls.append(kwargs)
        kwargs['on_usage']({'prompt_tokens':100,'completion_tokens':30});kwargs['on_finish']('stop')
        yield json.dumps({'value':'Предложенный характер.'},ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        response=client.post(url+'/generate',json={'revision':before['revision'],'preview':True,'task':'field','kind':'character','entity_id':cid,'field':'fields.Характер','config':dict(REMOTE,context_length=131072,max_tokens=4000),'api_key':'fixture-key'})
        assert response.status_code==200,response.text
        job=wait_job(client,response.json()['id'])
    assert job['status']=='saved',job
    assert job['phase']=='preview';assert len(calls)==1
    now=client.get(url+'?author=true').json();assert now['state']==before['state'];assert now['revision']==before['revision']
    endpoint=url+'/field-proposals/'+job['id']
    assert client.get(endpoint).status_code==409
    proposal=client.get(endpoint+'?author=true').json();assert proposal['value']=='Предложенный характер.';assert not proposal['stale']
    if decision=='stale':
        r=client.patch(url,json={'revision':now['revision'],'operation':'patch','kind':'campaign','field':'title','value':'Новая ревизия'});assert r.status_code==200,r.text
        now=r.json();assert client.get(endpoint+'?author=true').json()['stale']
    r=client.post(endpoint,json={'revision':now['revision'],'decision':'accept' if decision=='stale' else decision,'accept_warnings':True})
    assert r.status_code==(409 if decision=='stale' else 200),r.text
    final=client.get(url+'?author=true').json()
    if decision=='accept':
        expected=deepcopy(before['state']);next(c for c in expected['characters'] if c['id']==cid)['fields']['Характер']='Предложенный характер.'
        expected.pop('authoring',None);actual=deepcopy(final['state']);actual.pop('authoring',None)
        assert actual==expected;assert final['revision']==before['revision']+1
    else:assert final['state']==now['state'];assert final['revision']==now['revision']
    assert len(calls)==1


def test_location_cycle_export_and_projection_metadata(api):
    client,_=api;wid,url,before=imported(client)
    locations=before['state']['locations'];parent,child=locations[0]['id'],locations[1]['id']
    response=client.patch(url,json={'revision':before['revision'],'operation':'patch','kind':'location','entity_id':child,'field':'parent_id','value':parent,'warnings_ack':True})
    assert response.status_code==200,response.text
    current=response.json()
    for target in (parent,child):
        bad=client.patch(url,json={'revision':current['revision'],'operation':'patch','kind':'location','entity_id':parent,'field':'parent_id','value':target})
        assert bad.status_code==409,bad.text
    assert client.get(url+'?author=true').json()['state']==current['state']
    plain=client.get(url+f"/export?version_id={current['version_id']}&format=plain")
    legacy=client.get(url+f"/export?version_id={current['version_id']}&format=txt")
    assert plain.status_code==legacy.status_code==200
    assert current['state']['campaign']['title'] in plain.text
    assert not any(line.startswith('#') for line in plain.text.splitlines())
    assert 'AI_RPG_STATE_V2' not in plain.text and 'AI_RPG_STATE_V2' in legacy.text
    reader=client.get(url).json();author=client.get(url+'?author=true').json()
    assert set(reader['presentation']['thread_visibility'])==set(reader['state']['world']['threads'])
    for tid,visibility in author['presentation']['thread_visibility'].items():
        assert visibility==('known' if tid in reader['state']['world']['threads'] else 'author')


def test_removing_created_card_remaps_manual_paths_without_affecting_next_card():
    from backend.services import draft_world as domain
    state=domain.prepare(json.loads((Path(__file__).parent/'fixtures/initial_world/workshop188.json').read_text()))
    state,first=domain.add(state,'character',{'name':'Первый'})
    state,second=domain.add(state,'character',{'name':'Второй'})
    index=next(i for i,c in enumerate(state['characters']) if c['id']==second)
    assert f'/characters/{index}/name' in state['authoring']['manual_paths']
    result=domain.remove(state,'character',first)
    assert f'/characters/{index-1}/name' in result['authoring']['manual_paths']
    assert f'/characters/{index}/name' not in result['authoring']['manual_paths']


@pytest.mark.parametrize('custom',[False,True])
def test_date_selection_uses_runtime_calendar_without_writing(custom):
    from backend.services.draft_presentation import time_selection
    profile={'system':'custom','month_lengths':[30,30],'month_names':['Свет','Тень'],'weekday_names':['Один','Два']} if custom else {}
    clock={'minute':25*1440+9*60,'calendar':{'start_minute':25*1440,'start_date':'2024-02-28','start_weekday':2,'profile':profile}}
    before=deepcopy(clock)
    result=time_selection(clock,clock['minute'],'2024-02-29')
    assert result['world_time']==26*1440+9*60
    assert result['date']=='2024-02-29' and result['time']=='09:00'
    assert clock==before
    with pytest.raises(ValueError):time_selection(clock,clock['minute'],'2024-02-31')


def test_whole_card_preview_preserves_identity_and_requires_decision(api):
    client,_=api;wid,url,before=imported(client)
    card=before['state']['characters'][0];cid=card['id']
    proposed={key:deepcopy(card.get(key,[] if key=='aliases' else '')) for key in ('name','aliases','fields')}
    proposed['fields']['Характер']+=' Любит ранние прогулки.'
    calls=[]
    def provider(**kwargs):
        calls.append(kwargs);kwargs['on_finish']('stop')
        yield json.dumps({'value':proposed},ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=provider):
        response=client.post(url+'/generate',json={'revision':before['revision'],'preview':True,'task':'character','kind':'character','entity_id':cid,'config':dict(REMOTE,context_length=131072,max_tokens=4000),'api_key':'fixture-key'})
        assert response.status_code==200,response.text
        job=wait_job(client,response.json()['id'])
    assert job['status']=='saved' and job['phase']=='preview',job
    staged=client.get(url+'?author=true').json();assert staged['state']==before['state'];assert staged['pending_editor']
    endpoint=url+'/field-proposals/'+job['id']
    preview=client.get(endpoint+'?author=true').json();assert preview['value']==proposed
    response=client.post(endpoint,json={'revision':before['revision'],'decision':'accept','accept_warnings':True})
    assert response.status_code==200,response.text
    final=response.json();assert final['revision']==before['revision']+1
    assert final['state']['world']==before['state']['world']
    result=next(c for c in final['state']['characters'] if c['id']==cid)
    assert result==dict(card,**proposed);assert len(calls)==1;assert not final['pending_editor']
    assert client.post(endpoint,json={'revision':final['revision'],'decision':'accept','accept_warnings':True}).status_code==409


def test_event_periods_use_world_day_and_preserve_unknown_dates():
    from backend.services.draft_presentation import event_periods
    state={'world_clock':{'minute':2880},'world':{'events':{'old':{'minute':2879},'today':{'minute':2880},'later_today':{'minute':4319},'future':{'minute':4320},'unknown':{'minute':None}}}}
    assert event_periods(state)=={'old':'past','today':'today','later_today':'today','future':'future'}


def test_review_revision_is_pinned_without_duplicate_versions(tmp_path):
    from backend.repositories.preparation import Repository
    from test_initial_draft_v4 import rich
    repo=Repository(tmp_path/'review.sqlite');w=repo.create_workspace('review')
    cfg=dict(REMOTE,_draft_task='world',_draft_input='Мир',_draft_token_budget=30000)
    jid=repo.begin_preparation(w['id'],'draft_world','Мир',cfg,0)
    review={'status':'completed','issues':[]}
    repo.save_draft_candidate(jid,rich(),[],review=review)
    checked=repo.draft(w['id'],True)
    assert checked['review']['checked_revision']==checked['revision']
    repo.save_draft_candidate(jid,rich(),[],review=review)
    repeated=repo.draft(w['id'],True)
    assert (repeated['revision'],repeated['history'])==(checked['revision'],checked['history'])
    repo.preparation_progress(jid,'','error')
    repo.edit_candidate(w['id'],checked['revision'],'/campaign/title','Новое название')
    edited=repo.draft(w['id'],True)
    assert edited['review']['status']=='stale'
    assert edited['review']['checked_revision']==checked['revision']<edited['revision']
    assert 'checked_revision' not in repo.draft(w['id'],False)['review']
