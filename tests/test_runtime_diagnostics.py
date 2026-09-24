"""Runtime v2 manual-test regressions: leaf degradation and persisted diagnostics."""
import json
from copy import deepcopy
from unittest.mock import patch
import pytest
from backend.services.world_delta import WorldDelta, RELATION_DIMENSIONS, SecondaryDeltaError
from state_updates import apply_world_updates
from canonical_fixture import canonical
from test_engine import db, CONFIG, NARRATIVE, result, run
from test_api import api, new_save


def payload():
    p=canonical(result());d=p['world_delta'];eid=d['events'][0]['id']
    d['facts']=[dict(id='f',text='Подтверждённый факт',evidence=NARRATIVE)]
    d['events'][0]['fact_ids']=['f']
    d['knowledge']=[dict(actor_id='character_2',fact_id='f',source_event_id=eid,status='known',evidence=NARRATIVE)]
    d['characters']=[dict(id='character_2',situation='Ждёт ответа',evidence=NARRATIVE)]
    d['relationships']=[dict(source_id='character_2',target_id='character_1',dimensions={'trust':55,'respect':70},context='Доверяет за поступок',evidence=NARRATIVE)]
    d['threads']=[dict(id='t',description='Разговор',state='Начался',status='active',relevance=0.5,character_ids=['character_2'],last_event_id=eid,evidence=NARRATIVE)]
    return p


def corrupt(p,case):
    d=p['world_delta']
    if case=='witness':d['events'][0]['witnesses']=['character_1']
    elif case=='fact':d['events'][0]['fact_ids']=[]
    elif case=='source':d['knowledge'][0]['source_event_id']='missing_event'
    elif case=='action':d['events'][0]['medium']='action'
    elif case=='dimension':d['relationships'][0]['dimensions']['sympathy']=40


@pytest.mark.parametrize('case',['witness','fact','source','action','dimension'])
def test_leaf_errors_repair_once_and_keep_independent_delta(db,case):
    storage,_,sid=db;p=payload();corrupt(p,case)
    before=storage.get_save(sid)['state']
    with pytest.raises(SecondaryDeltaError):apply_world_updates(before,p,NARRATIVE,'',0,'start')
    job=storage.begin_job(sid,'','start',CONFIG)
    calls=run(storage,job,p)
    assert len(calls)==3 and storage.get_job(job)['status']=='saved'
    state=storage.get_save(sid)['state'];w=state['world']
    assert w['characters']['character_2']['situation']=='Ждёт ответа'
    assert w['relationships']['character_2:character_1']['dimensions']=={'trust':55,'respect':70}
    assert w['relationships']['character_2:character_1']['context']=='Доверяет за поступок'
    assert 't' in w['threads'] and 'f' in w['facts'] and p['world_delta']['events'][0]['id'] in w['events']
    assert ('character_2:f' in w['knowledge'])==(case=='dimension')
    diagnostic=storage.accounting(sid)['turns'][0]
    assert len(diagnostic['requests'])==3
    assert {r['stage'] for r in diagnostic['requests']}=={'narrative','extraction','extraction_repair'}
    warning=diagnostic['warnings'][0]
    assert warning['index']==0
    assert warning['section']==('relationships' if case=='dimension' else 'knowledge')
    if case=='dimension':assert warning['field']=='dimensions.sympathy' and warning['entity']=='character_2:character_1'
    assert diagnostic['timing']['extraction_repair']>=0
    assert storage.get_save(sid)['state']!=before


def test_valid_knowledge_and_all_canonical_dimensions(db):
    storage,_,sid=db;p=payload()
    p['world_delta']['relationships'][0]['dimensions']={k:10 for k in RELATION_DIMENSIONS}
    job=storage.begin_job(sid,'','start',CONFIG)
    assert len(run(storage,job,p))==2
    state=storage.get_save(sid)['state']
    assert state['world']['knowledge']['character_2:f']['status']=='known'
    assert storage.turn_diagnostics(sid)[0]['warnings']==[]
    schema=WorldDelta.model_json_schema()['$defs']
    dimensions=schema['Relationship']['properties']['dimensions']
    assert set(dimensions['properties'])==set(RELATION_DIMENSIONS)
    assert dimensions['additionalProperties'] is False
    assert not dimensions.get('required')
    assert all(v['minimum']==-100 and v['maximum']==100 for v in dimensions['properties'].values())
    assert 'Witness' in schema['Knowledge']['properties']['source_event_id']['description']


@pytest.mark.parametrize('case',['actor','type','scene','time','duplicate','range','unsupported_actor'])
def test_structural_failure_remains_atomic_even_with_secondary_error(db,case):
    storage,_,sid=db;p=payload();corrupt(p,'dimension')
    d=p['world_delta']
    if case=='actor':d['knowledge'][0]['actor_id']='missing_actor'
    elif case=='type':d['knowledge'][0]['source_event_id']=42
    elif case=='scene':p['scene']['present_ids']=['missing_actor']
    elif case=='time':d['events'][0]['minute']=99999999
    elif case=='duplicate':d['events'].append(deepcopy(d['events'][0]))
    elif case=='range':d['relationships'][0]['dimensions']['trust']=200
    elif case=='unsupported_actor':d['characters'][0].update(id='missing_actor',evidence='Несуществующая цитата')
    before=storage.get_save(sid)['state']
    job=storage.begin_job(sid,'','start',CONFIG)
    assert len(run(storage,job,p))==3
    assert storage.get_job(job)['status']=='error'
    assert storage.list_turns(sid)==[] and storage.get_save(sid)['state']==before


def test_multiple_dropped_entries_preserve_original_indices(db):
    storage,_,sid=db;p=payload();d=p['world_delta']
    d['knowledge'].append({**d['knowledge'][0],'actor_id':'character_1'})
    d['events'][0]['witnesses']=[]
    d['relationships'][0]['dimensions'].update(sympathy=40,loyalty=50)
    _,_,changes,_,warnings=apply_world_updates(storage.get_save(sid)['state'],p,NARRATIVE,'',0,'start',discard_unsupported=True)
    assert [w['index'] for w in warnings if w['section']=='knowledge']==[0,1]
    assert len(warnings)==4 and changes['world_delta']['knowledge']==[]
    assert changes['world_delta']['relationships'][0]['dimensions']=={'trust':55,'respect':70}


def test_api_timing_requests_totals_and_variant_association(api):
    client,app=api;_,save=new_save(client);storage=app.state.repository;sid=save['id']
    job=storage.begin_job(sid,'','start',CONFIG);run(storage,job)
    turn=client.get(f'/api/saves/{sid}').json()['turns'][0]
    assert turn['timing']['total']>=0
    with storage.connect() as conn:
        conn.execute("UPDATE llm_requests SET input_tokens=100,output_tokens=20,cached_input_tokens=60,cost_usd='0.001' WHERE job_id=?",(job,))
    data=client.get(f'/api/saves/{sid}/accounting').json();t=data['turns'][0]
    assert t['job_id']==job and len(t['requests'])==2
    assert data['game']['input_tokens']==200 and data['game']['output_tokens']==40 and data['game']['cached_input_tokens']==120
    assert float(data['game']['cost_usd'])==.002
    assert all(r['duration']>=0 and r['max_tokens']>0 and r['messages'] for r in t['requests'])
    original_timing=t['timing']
    second=storage.begin_job(sid,'','regenerate',CONFIG);bad=payload();corrupt(bad,'dimension');run(storage,second,bad)
    newer=storage.turn_diagnostics(sid)[0];assert newer['job_id']==second and len(newer['warnings'])==1
    assert newer['timing']['extraction_repair']>=0
    storage.select_variant(sid,turn['id'],turn['active_variant_id'],storage.get_save(sid)['revision'])
    restored=storage.turn_diagnostics(sid)[0]
    assert restored['job_id']==job and restored['timing']==original_timing and restored['warnings']==[]
    assert len(restored['requests'])==2
    with storage.connect() as conn:conn.execute('UPDATE turns SET timing_json=NULL WHERE id=?',(turn['id'],))
    assert client.get(f'/api/saves/{sid}').json()['turns'][0]['timing'] is None
    assert client.get(f'/api/saves/{sid}/accounting').json()['turns'][0]['timing'] is None


def test_background_uses_one_repair_and_records_leaf_warning(db):
    from threading import Event
    from backend.services.simulation import simulate
    from backend.services.pov import transition
    from test_living_world import ready, delta, QUOTE
    from backend.services.world_delta import apply_delta
    storage,_,sid=db
    state=transition(apply_delta(ready(storage,sid),delta(),QUOTE,'',2),'character_1')
    before=deepcopy(state);state['world_clock']['minute']=1200;state['scene_meta']['time']='День 1 20:00'
    calls=[];warnings=[]
    def generate(stage,*args,**kwargs):
        calls.append(stage)
        if stage=='world_simulation':yield QUOTE
        else:
            yield json.dumps({'scene':{'text':'Встреча','time':'День 1 20:00','location':'Подвал','present_ids':['character_3','character_4']},'choices':[],
                'world_delta':{'relationships':[{'source_id':'character_3','target_id':'character_4','context':'Уважает','dimensions':{'respect':30,'loyalty':50},'evidence':QUOTE}]}})
    after=simulate(before,state,3,32768,CONFIG,generate,Event(),warnings=warnings)
    assert calls==['world_simulation','world_simulation_delta','world_simulation_repair']
    assert after['world']['relationships']['character_3:character_4']['dimensions']['respect']==30
    assert 'loyalty' not in after['world']['relationships']['character_3:character_4']['dimensions']
    assert warnings[0]['stage']=='background_simulation' and warnings[0]['field']=='dimensions.loyalty'
    assert after['camera']==state['camera'] and after['controlled_actor_id']=='character_1'
