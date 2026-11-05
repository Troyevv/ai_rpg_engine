"""What a Workshop reader can learn, independently of editing and Runtime."""
import json
from copy import deepcopy
from pathlib import Path

from backend.services.draft_world import player_view, prepare, validate, dependencies
from backend.services.draft_initial import inspect_candidate, prompt_schema
from test_api import api


def source():
    return json.loads((Path(__file__).parent/'fixtures/initial_world/workshop188.json').read_text())


def text(value):
    return json.dumps(value,ensure_ascii=False)


def test_real_world_keeps_everyday_life_and_removes_direct_and_indirect_spoilers():
    s=prepare(source());unchanged=deepcopy(s)
    p=player_view(s);w=p['world'];c=next(c for c in p['characters'] if c['id']=='maxim')
    assert 'менеджера по закупкам' in c['fields']['Биография'] and 'Характер' in c['fields']
    assert w['characters']['maxim']['goals'][0]['text'].startswith('Закрыть накопившиеся дела')
    assert {r['actor_id'] for r in w['roles'].values()}=={'sonya','maxim','ilya'}
    assert len(w['residences'])==3 and len(w['objective_relations'])==2
    for mark in ('fact_sonya_love','fact_maxim_sale','без продажи дома','переписка с риелтором',
                 'для сони эта дружба давно стала чем-то большим','её чувства станут обузой'):
        assert mark not in text(p).lower()
    assert s==unchanged


def test_classification_and_references_protect_secrets_and_their_dependent_rows():
    s=prepare(source());w=s['world']
    secret='fact_maxim_sale';f=w['facts'][secret];f['secret']=False;f['secret_biography_ids']=['maxim']
    maxim=next(c for c in s['characters'] if c['id']=='maxim')
    maxim['aliases']=['SECRET_ALIAS'];maxim['fields']['Биография']='BIO_MARKER'
    w['events']['closed']={'id':'closed','text':'EVENT_MARKER','participants':['ilya'],'player_observed':True,'fact_ids':[secret]}
    w['events']['open']={'id':'open','text':'Публичная выставка','participants':['sonya'],'witnesses':[],'fact_ids':[]}
    w['scenes']['closed_scene']={'id':'closed_scene','text':'SCENE_MARKER','participants':['ilya'],'event_ids':['closed']}
    w['scheduled_events']['closed_plan']={'id':'closed_plan','description':'SCHEDULE_MARKER','source_event_id':'closed'}
    w['scheduled_events']['derived']={'id':'derived','description':'DEPENDANT_MARKER','depends_on':['closed_plan']}
    a=w['characters']['maxim'];a['last_event_id']='closed';a['situation']='SITUATION_MARKER'
    s['card_field_facts']={'maxim':{'Внешность':[secret]}}
    a['appearance']={'items':{'hair':{'kind':'hairstyle','category':'presentation','text':'HAIR_MARKER'}}}
    a['goals'].extend([{'text':'MOTIVE_MARKER','dependencies':{'facts':[secret]}},{'text':'SOURCE_MARKER','source_event_id':'closed'}])
    w['roles']['secret_role']={'id':'secret_role','actor_id':'maxim','title':'ROLE_MARKER','fact_id':secret}
    w['knowledge']['fake_evidence']={'actor_id':'ilya','fact_id':'fact_siblings','status':'known','evidence':'EVIDENCE_MARKER','replaced_by':secret}
    w['knowledge']['ilya:guard']={'actor_id':'ilya','fact_id':secret,'status':'suspected','source_event_id':None}
    p=player_view(s)
    assert 'Публичная выставка' in text(p)
    assert all(v not in text(p) for v in ('_MARKER','SECRET_ALIAS','fact_maxim_sale','closed_plan','closed_scene'))
    w['knowledge']['ilya:guard']['status']='known'
    p=player_view(s)
    assert 'EVENT_MARKER' in text(p) and 'BIO_MARKER' in text(p)
    assert 'SOURCE_MARKER' in text(p) and 'ROLE_MARKER' in text(p)
    w['knowledge']['retired-later']={'actor_id':'ilya','fact_id':secret,'status':'refuted'}
    assert 'EVENT_MARKER' not in text(player_view(s))  # match V2 → Runtime handoff
    # A switch to a new controlled actor is a fresh view, not a knowledge write.
    s['controlled_actor_id']='sonya'
    assert 'EVENT_MARKER' not in text(player_view(s))


def test_field_fact_bindings_roundtrip_confirm_and_atomic_edit(api):
    client,app=api;s=source();cid='maxim';fid='fact_maxim_sale';field='Планы на лето'
    next(c for c in s['characters'] if c['id']==cid)['fields'][field]='FIELD_MARKER'
    s['card_field_facts']={cid:{field:[fid]}}
    assert 'card_field_facts' in prompt_schema()['properties']
    wid=client.post('/api/workspaces',json={'name':'Dossier read'}).json()['id'];path=f'/api/workspaces/{wid}/draft'
    initial=client.post(path+'/import',json={'revision':0,'format':'json','text':text(s)})
    assert initial.status_code==200,initial.text
    assert 'FIELD_MARKER' not in initial.text and fid not in initial.text
    def get():return client.get(path+'?author=true').json()
    def change(**kwargs):
        args=dict(operation='patch',kind='character',entity_id=cid,field='fields.'+field,value='FIELD_MARKER',revision=get()['revision'],warnings_ack=True)
        return client.patch(path,json={**args,**kwargs})
    full=get(); assert full['state']['card_field_facts']==s['card_field_facts']
    assert 'Скрытые мотивы' in full['editor']['field_visibility_excluded']
    for args in ({'field_visibility':['missing']},{'field_visibility':None},{'field_visibility':[],'field':'name'},
                 {'field_visibility':[],'field':'fields.Секрет'},{'operation':'remove','kind':'fact','entity_id':fid,'field_visibility':[]}):
        assert change(**args).status_code in (409,422)
        assert get()['revision']==full['revision']
    assert change(value='UPDATED_MARKER').status_code==200
    assert fid not in client.get(path).text and 'UPDATED_MARKER' not in client.get(path).text
    assert change(field_visibility=[],value='PUBLIC_MARKER').status_code==200
    assert 'PUBLIC_MARKER' in client.get(path).text and fid not in client.get(path).text
    assert change(field_visibility='default').status_code==200
    assert 'FIELD_MARKER' not in client.get(path).text and 'card_field_facts' not in get()['state']
    assert change(field_visibility=[fid]).status_code==200
    full=get()
    exported=client.get(path+'/export',params={'version_id':full['version_id'],'format':'json'}).json()
    assert exported['card_field_facts']==s['card_field_facts']
    launched=client.post(path+'/confirm',json=dict(revision=full['revision'],version_id=full['version_id'],accept_warnings=True))
    assert launched.status_code==200,launched.text
    snap=app.state.repository.get_snapshot(launched.json()['save'])
    assert 'card_field_facts' not in text(snap)
    assert next(c for c in snap['character_cards'] if c['id']==cid)['fields'][field]=='FIELD_MARKER'
    trial=deepcopy(full['state']);assert {'id':cid,'kind':'character'} in dependencies(trial,'fact',fid)
    del trial['world']['facts'][fid]
    assert validate(trial)['errors'] and 'FIELD_MARKER' not in text(player_view(trial))
    trial=deepcopy(full['state']);trial['card_field_facts'][cid][field]='bad';assert inspect_candidate(trial)[1]['errors']
    assert 'FIELD_MARKER' not in text(player_view(trial))
