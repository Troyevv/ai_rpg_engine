"""#44/#78 rich brief through the actual worker, journal, authoring and Runtime."""
import json
from copy import deepcopy
from unittest.mock import patch
import pytest

pytestmark = pytest.mark.usefixtures('legacy_generation_v5')
from test_api import api,REMOTE
from test_world_generation import wait
from backend.runtime_v3.repository import committed_snapshot,read_history
from backend.runtime_v3.resolver import StateResolver
from test_runtime_v3_storage import connection

PEOPLE=['Илья','Марина','Виктор','Катя','Тимур','Ольга','Денис']
ORGS=['Apex Group','Банк','IT-компания','Страховая компания','Строительная компания','Юридическая фирма']
BRIEF='''Семья Волковых богата. Марина и Виктор усыновили Илью. Катя, Тимур, Ольга и Денис — другие важные персонажи.
В Apex Group входят Банк, IT-компания, Страховая компания, Строительная компания и Юридическая фирма.
Марина хочет в будущем поженить Илью и Катю. Это только её план: Илья и Катя не женаты, согласия и романтических чувств не задано.
Только Марина и Виктор знали об усыновлении до вчерашнего дня. Вчера Илья узнал. Остальные не знают.
Илья сдержанный, но настойчивый. Марина решительная. Тимур работает юристом; страна и юридическая квалификация не заданы.
Сейчас пятница, 06:00. Илья идёт с сумками по дороге к станции. Не решать за Илью, не придумывать беременность.'''


def span(text):
    i=BRIEF.index(text);return dict(start=i,end=i+len(text),quote=text)


def interpreted():
    entities=[dict(key='p'+str(i),kind='character',name=name,tier='protagonist' if i==0 else 'core',spans=[span(name)]) for i,name in enumerate(PEOPLE)]
    entities += [dict(key='o'+str(i),kind='organization',name=name,spans=[span(name)]) for i,name in enumerate(ORGS)]
    def claim(section,field,text,**kwargs):return dict(classification='explicit',section=section,field=field,description=text,spans=[span(text)],**kwargs)
    return dict(entities=entities,claims=[
        claim('family','adoption','Марина и Виктор усыновили Илью.',subject_key='p0',related_keys=['p1','p2'],rules=[dict(stage='life',path='/objective_relations',operator='contains',expected=dict(kind='adoptive_parent',source_id='@p'+str(i),target_id='@p0')) for i in (1,2)]),
        claim('organization','subsidiaries','В Apex Group входят Банк, IT-компания, Страховая компания, Строительная компания и Юридическая фирма.',rules=[dict(stage='places',path='/parent_organizations/@o'+str(i),expected='@o0') for i in range(1,6)]),
        claim('knowledge','adoption','Только Марина и Виктор знали об усыновлении до вчерашнего дня. Вчера Илья узнал. Остальные не знают.',holder_keys=['p0','p1','p2'],time_scope='Илья узнал вчера; родители знали раньше',rules=[dict(stage='lore',path='/knowledge',operator='only',where={'fact_id':'adoption'},select='actor_id',expected=['@p0','@p1','@p2'])]),
        claim('opening','clock','Сейчас пятница, 06:00.',rules=[dict(stage='opening',path='/world_time',expected=6120)]),
        claim('opening','activity','Илья идёт с сумками по дороге к станции.',subject_key='p0',rules=[dict(stage='opening',path='/camera/situation',expected='Илья идёт с сумками по дороге к станции.')]),
        claim('personality','traits','Илья сдержанный, но настойчивый.',subject_key='p0',rules=[dict(stage='characters',path='/characters/@p0/personality/items/traits/text',expected='Сдержанный, но настойчивый')]),
        claim('commitment','marriage_plan','Марина хочет в будущем поженить Илью и Катю.',subject_key='p1',related_keys=['p0','p3']),
        dict(classification='prohibition',section='family',field='marriage',description='Брак не установлен',spans=[span('Илья и Катя не женаты')],rules=[dict(stage='life',path='/objective_relations',operator='absent',expected={'kind':'spouse'})]),
        dict(classification='ambiguity',section='role',field='jurisdiction',subject_key='p4',description='Квалификация юриста зависит от неуказанной юрисдикции',blocking=False,spans=[span('Тимур работает юристом; страна и юридическая квалификация не заданы.')])])


def provider(calls):
    def stream(**kw):
        stage=kw['messages'][0]['content'].split('\nStage: ')[1].split('\n')[0]
        data=json.loads(kw['messages'][-1]['content']);calls.append(stage)
        if stage=='interpret':result=interpreted()
        elif stage=='review':result={'findings':[dict(claim_id=c['id'],verdict='preserved',evidence_paths=['/accepted/'+next(iter(data['accepted']))],explanation='Fixture evidence is consistent') for c in data['claims']]}
        elif stage=='setting':result={'campaign':{'title':'Волковы'},'entities':[dict(key=str(i),existing_id=r['id'],kind=r['kind'],name=r['name'],tier=r['tier']) for i,r in enumerate(data['interpretation']['entities'])]+[dict(key='road',kind='location',name='Дорога к станции')]}
        else:
            ids={r['name']:r['id'] for r in data['registry']};ilya=ids['Илья'];road=ids['Дорога к станции']
            if stage=='places':result=dict(locations={road:dict(id=road,name='Дорога к станции')},organizations={ids[n]:dict(id=ids[n],name=n) for n in ORGS},parent_organizations={ids[n]:ids[ORGS[0]] for n in ORGS[1:]})
            elif stage=='characters':
                result={'characters':{},'cards':{}}
                for r in data['registry']:
                    cid=r['id']
                    if cid not in data['assigned_ids']:continue
                    actor=dict(id=cid,display_name=r['name'],location_id=road if cid==ilya else None)
                    if cid==ilya:actor['personality']={'items':{'traits':dict(field='traits',text='Сдержанный, но настойчивый')}}
                    if r['name']=='Марина':
                        assert any(c['section']=='commitment' and c['subject_id']==cid for c in data['constraints'])
                        actor['intentions']=[dict(id='plan',text='В будущем поженить Илью и Катю')]
                    result['characters'][cid]=actor;result['cards'][cid]=dict(id=cid,name=r['name'],fields={})
            elif stage=='life':result={'objective_relations':{str(i):dict(id=str(i),kind='adoptive_parent',source_id=ids[n],target_id=ilya) for i,n in enumerate(['Марина','Виктор'])}}
            elif stage=='lore':result={'facts':{'adoption':dict(id='adoption',text='Илья усыновлён',visibility='secret',character_ids=[ilya,ids['Марина'],ids['Виктор']])},'knowledge':{ids[n]+':adoption':dict(actor_id=ids[n],fact_id='adoption',status='known',evidence='Вчера узнал' if n=='Илья' else 'Знали раньше') for n in PEOPLE[:3]}}
            elif stage=='opening':result=dict(world_time=6120,camera=dict(mode='actor',controlled_actor_id=ilya,pov_actor_id=ilya,location_id=road,present_character_ids=[ilya],situation='Илья идёт с сумками по дороге к станции.'))
            else:raise AssertionError(stage)
        yield json.dumps(result,ensure_ascii=False)
    return stream


def test_rich_brief_worker_start_reload_and_sibling_history(api,tmp_path):
    client,app=api;repo=app.state.repository;calls=[]
    wid=client.post('/api/workspaces',json={'name':'Волковы'}).json()['id']
    with patch('backend.services.preparation.chat_stream',side_effect=provider(calls)):
        response=client.post(f'/api/workspaces/{wid}/draft/generate',json=dict(task='world_staged',text=BRIEF,revision=0,config=REMOTE,creation={'cast_preset':'small'},api_key='fixture'))
        assert response.status_code==200,response.text
        jid=response.json()['id'];done=wait(client,jid)
        assert done['status']=='saved',done
    assert calls.count('characters')==3
    draft=repo.draft(wid,True);saved=repo.confirm_draft(wid,draft['revision'],draft['version_id'])
    initial=repo.get_snapshot(saved['save']);state=initial['world_state']
    assert len(state['characters'])==7 and len(state['organizations'])==6
    assert sum(f.get('claim',{}).get('predicate')=='organization.parent' for f in state['facts'].values() if f.get('claim'))==5
    assert {r['kind'] for r in state['objective_relations'].values()}=={'adoptive_parent'}
    assert not state['pregnancies']
    assert len(state['knowledge'])==3
    assert state['meta']['world_time']==6120
    assert state['camera']['situation']=='Илья идёт с сумками по дороге к станции.'
    assert not state['characters'][state['camera']['controlled_actor_id']]['intentions']
    assert 'Вчера узнал' in json.dumps(state['knowledge'],ensure_ascii=False)
    assert BRIEF not in json.dumps(repo.draft(wid),ensure_ascii=False)
    db=connection(tmp_path/'branches.sqlite')
    # Start with a portable canonical state; this independent history DB has no
    # foreign pointers from the application's own journal.
    initial=deepcopy(initial);initial['history_head']=None
    snapshots=[]
    for elapsed in (1,2):
        camera=state['camera'];resolved=StateResolver(state,'Пауза.','').resolve({'final_scene':dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=elapsed)})
        with db:next_state=committed_snapshot(db,initial,resolved)
        next_state=json.loads(json.dumps(next_state));snapshots.append(next_state)
        assert next_state['world_state']['knowledge']==state['knowledge']
    assert snapshots[0]['history_head']!=snapshots[1]['history_head']


def test_rich_constraint_revision_reuses_unrelated_character_batches(api):
    from test_generation_edits import checkpoint_body
    client,app=api;repo=app.state.repository;calls=[]
    commit=repo.commit_generation_unit
    def pause(jid,token,unit,payload):
        result=commit(jid,token,unit,payload)
        if unit=='opening':repo.generation_control(jid,'pause')
        return result
    wid=repo.create_workspace('Семья')['id']
    with patch('backend.services.preparation.chat_stream',side_effect=provider(calls)),patch.object(repo,'commit_generation_unit',side_effect=pause):
        response=client.post(f'/api/workspaces/{wid}/draft/generate',json=dict(task='world_staged',text=BRIEF,revision=0,config=REMOTE,api_key='fixture'))
        jid=response.json()['id'];assert wait(client,jid)['status']=='paused'
    plan=repo.generation_resources(jid,['interpretation'])['interpretation'];claim=deepcopy(plan['claims'][5])
    claim['description']='Илья теперь общительный'
    stale_rule=checkpoint_body(repo,jid,'interpret','/claims/5',claim,warnings_ack=True)
    rejected=client.patch(f'/api/workspaces/{wid}/draft',json=stale_rule)
    assert rejected.status_code==409 and 'проверками' in rejected.text
    assert repo.generation_resources(jid,['interpretation'])['interpretation']==plan
    claim['rules'][0]['expected']='Общительный'
    body=checkpoint_body(repo,jid,'interpret','/claims/5',claim,warnings_ack=True)
    peers={u:repo.inspect_generation_checkpoint(jid,u,True) for u in ('core_1','core_2','places')}
    response=client.patch(f'/api/workspaces/{wid}/draft',json=body)
    assert response.status_code==200,response.text
    assert response.json()['stale_units']==['assembly','core_0','life','lore','opening','review_opening_0']
    for unit,old in peers.items():assert repo.inspect_generation_checkpoint(jid,unit,True)==old


def test_roster_tier_revision_replans_batches_and_moves_accepted_locks(api):
    from test_generation_edits import checkpoint_body
    client,app=api;repo=app.state.repository;calls=[]
    commit=repo.commit_generation_unit
    def pause(jid,token,unit,payload):
        result=commit(jid,token,unit,payload)
        if unit=='opening':repo.generation_control(jid,'pause')
        return result
    wid=repo.create_workspace('Пересмотр состава')['id']
    with patch('backend.services.preparation.chat_stream',side_effect=provider(calls)),patch.object(repo,'commit_generation_unit',side_effect=pause):
        response=client.post(f'/api/workspaces/{wid}/draft/generate',json=dict(task='world_staged',text=BRIEF,revision=0,config=REMOTE,api_key='fixture'))
        jid=response.json()['id'];assert wait(client,jid)['status']=='paused'
    plan=repo.generation_resources(jid,['interpretation'])['interpretation']
    marina=plan['entities'][1]['id']
    field='/characters/'+marina+'/physical_state'
    changed=client.patch(f'/api/workspaces/{wid}/draft',json=checkpoint_body(repo,jid,'core_0',field,'Отдохнувшая'))
    assert changed.status_code==200,changed.text
    old=repo.inspect_generation_checkpoint(jid,'core_2',True)
    revised=client.patch(f'/api/workspaces/{wid}/draft',json=checkpoint_body(repo,jid,'interpret','/entities/1/tier','secondary',warnings_ack=True))
    assert revised.status_code==200,revised.text
    fixture=provider(calls)
    def locked_provider(**kwargs):
        data=json.loads(kwargs['messages'][-1]['content'])
        for raw in fixture(**kwargs):
            result=json.loads(raw)
            for pointer,value in data.get('accepted_field_locks',{}).items():
                target=result;bits=pointer.split('/')[1:]
                for bit in bits[:-1]:target=target[bit.replace('~1','/').replace('~0','~')]
                target[bits[-1]]=value
            yield json.dumps(result,ensure_ascii=False)
    with patch('backend.services.preparation.chat_stream',side_effect=locked_provider):
        resumed=client.post(f'/api/jobs/{jid}/generation/resume',json={'revision':revised.json()['revision']})
        assert resumed.status_code==200,resumed.text
        finished=wait(client,jid);assert finished['status']=='saved',finished
    assert repo.generation_field_locks(jid,'secondary_0')=={field:'Отдохнувшая'}
    assert not repo.generation_field_locks(jid,'core_0')
    assert 'core_2' not in {u['unit_id'] for u in repo.generation_status(jid)['units']}
    with repo.connect() as db:
        retired=db.execute("SELECT status,artifact_id FROM preparation_units WHERE job_id=? AND unit_id='core_2'",(jid,)).fetchone()
        assert retired['status']=='retired' and retired['artifact_id']==old['artifact_version']
        assert db.execute("SELECT count(*) FROM preparation_attempts WHERE job_id=? AND unit_id='core_2'",(jid,)).fetchone()[0]==1
    draft=repo.draft(wid,True);saved=repo.confirm_draft(wid,draft['revision'],draft['version_id'])
    assert repo.get_snapshot(saved['save'])['world_state']['characters'][marina]['physical_state']=='Отдохнувшая'
