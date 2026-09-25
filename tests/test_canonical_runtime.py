"""Canonical turn, budget, timing, POV and player edits."""
import json
from copy import deepcopy
from unittest.mock import patch
import pytest
from canonical_fixture import canonical
from context_builder import build_context, estimate
from state_updates import apply_world_updates, EvidenceError
from backend.services.relationship_edit import edit_relationship
from backend.services.world_delta import apply_delta
from backend.services.pov import transition
from test_engine import db, CONFIG, NARRATIVE, result, run
from test_api import api, new_save


def extraction(world, kind='start'):
    payload=canonical(result())
    payload['world_delta']['events'][0]['id']='unique_event'
    return apply_world_updates(world,payload,NARRATIVE,'',0,kind)


def test_canonical_turn_does_not_call_legacy_adapter_and_persists_timing(db):
    storage,_,sid=db
    job=storage.begin_job(sid,'','start',CONFIG)
    with patch('backend.services.world.apply_legacy',side_effect=AssertionError('legacy write')):
        calls=run(storage,job)
    assert len(calls)==2
    turn=storage.list_turns(sid)[0]
    timing=json.loads(turn['timing_json'])
    assert set(['narrative','extraction','validation_apply','total'])<=timing.keys()
    assert not {'memory_compaction','background_simulation','extraction_repair'} & timing.keys()
    assert timing['total']+0.005>=sum(timing[k] for k in ('narrative','extraction','validation_apply'))
    assert storage.get_job(job)['timing_json']==turn['timing_json']
    with storage.connect() as conn:
        assert json.loads(conn.execute('SELECT payload FROM response_variants WHERE id=?',(turn['active_variant_id'],)).fetchone()[0])['timing_json']==turn['timing_json']
        conn.execute('UPDATE turns SET timing_json=NULL WHERE id=?',(turn['id'],))
    assert storage.list_turns(sid)[0]['timing_json'] is None


def test_independent_character_fields_and_directed_relationships(db):
    storage,_,sid=db
    state=storage.get_save(sid)['state']
    from backend.services.world import normalize
    state=normalize(state)
    actor='character_1';npc='character_2'
    state['world']['scenes'][state['camera']['scene_id']]['participants']=[actor,npc]
    state['scene_meta']={'time':'День 1 (Пн) 18:20','location':state['world']['scenes'][state['camera']['scene_id']]['location'],'present_ids':[actor,npc]}
    initial=state['world']['characters'][npc]
    initial.update(goals=['Построить дом'],intentions=['Позвонить'],obligations=['Вернуть книгу'],emotion='Усталость',situation='В кухне')
    delta={'characters':[{'id':npc,'intentions':['Открыть окно'],'evidence':NARRATIVE}],
           'relationships':[{'source_id':npc,'target_id':actor,'context':'Осторожно доверяет','dimensions':{'trust':5},'evidence':NARRATIVE}]}
    after=apply_delta(state,delta,NARRATIVE,'',1)
    point=after['world']['characters'][npc]
    assert point['goals']==['Построить дом'] and point['intentions']==['Открыть окно']
    assert point['obligations']==['Вернуть книгу'] and point['emotion']=='Усталость' and point['situation']=='В кухне'
    edited=edit_relationship(after,actor,npc,'Доверяет за поступок',{'trust':20})
    assert edited['world']['relationships'][f'{actor}:{npc}']['dimensions']['trust']==20
    assert edited['world']['relationships'][f'{npc}:{actor}']['dimensions']['trust']==5
    removed=edit_relationship(edited,actor,npc,'',{},True)
    assert f'{actor}:{npc}' not in removed['world']['relationships']
    assert f'{npc}:{actor}' in removed['world']['relationships']
    with pytest.raises(ValueError):edit_relationship(edited,npc,actor,'Чужое мнение',{'trust':100})
    switched=transition(edited,npc)
    reverse=edit_relationship(switched,npc,actor,'Изменил своё мнение',{'trust':10})
    assert reverse['world']['relationships'][f'{actor}:{npc}']['dimensions']['trust']==20
    assert reverse['world']['relationships'][f'{npc}:{actor}']['dimensions']['trust']==10
    assert 'Доверяет за поступок' in str(build_context(edited,[],'','turn',32768,2000))


def test_unsupported_secondary_delta_is_dropped_with_warning(db):
    storage,_,sid=db
    world=storage.get_save(sid)['state']
    payload=canonical(result());payload['world_delta']['events'][0]['id']='valid_event'
    payload['world_delta']['facts']=[{'id':'bad_fact','text':'Не случилось','evidence':'нет такого'}]
    state,choices,changes,audience,warnings=apply_world_updates(world,payload,NARRATIVE,'',0,'start',discard_unsupported=True)
    assert len(choices)==6 and warnings[0]['section']=='facts'
    assert 'valid_event' in state['world']['events'] and 'bad_fact' not in state['world']['facts']


def test_relevance_uses_mentions_and_keeps_actor_knowledge_under_budget(db):
    storage,_,sid=db
    state=storage.get_save(sid)['state']
    from backend.services.world import normalize
    state=normalize(state)
    state['world']['facts']['known']={'id':'known','text':'Личный факт игрока','secret':True,'character_ids':[], 'evidence':[]}
    state['world']['facts']['secret']={'id':'secret','text':'Скрытый факт чужой сцены','secret':True,'character_ids':['character_3'], 'evidence':[]}
    state['world']['knowledge']['character_1:known']={'actor_id':'character_1','fact_id':'known','status':'known','source_event_id':None}
    state['world']['threads']['linked']={'id':'linked','description':'Персонаж 1 и персонаж 2 обсуждают работу','status':'active','state':'Открыто','relevance':0.95,'character_ids':['character_1','character_2'],'last_event_id':None}
    state['world']['threads']['unrelated']={'id':'unrelated','description':'Далёкая линия','status':'dormant','state':'Спит','relevance':0.1,'character_ids':['character_3','character_4'],'last_event_id':None}
    for i in range(80):state['world']['facts'][f'irrelevant_{i}']={'id':f'irrelevant_{i}','text':'Несущественная запись '+str(i)+' '*200,'secret':False,'character_ids':[],'evidence':[]}
    messages=build_context(state,[],'Что скажет персонаж 2?','turn',16000,2000)
    assert estimate(messages)<=16000-2000-256
    cards=json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('NPC и отношения')))
    assert 'character_3' in {c['id'] for c in cards['characters']}
    assert 'character_4' not in {c['id'] for c in cards['characters']}
    pov=json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('POV и знания')))
    assert {k['fact_id'] for k in pov['actor_knowledge']}=={'known'}
    objective=json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('Objective world')))
    assert 'linked' in {t['id'] for t in objective['threads']}
    assert 'unrelated' not in {t['id'] for t in objective['threads']}
    assert 'known' in {f['id'] for f in objective['facts']}


def test_relationship_api_is_save_scoped_and_follows_controlled_actor(api):
    from test_api import new_save
    client,app=api
    world,save=new_save(client)
    other=client.post(f"/api/worlds/{world['id']}/saves",json={'name':'Независимое прохождение'}).json()
    actor=save['state']['controlled_actor_id'];target=next(c['id'] for c in save['state']['characters'] if c['id']!=actor)
    url=lambda cid:f"/api/saves/{save['id']}/characters/{cid}/relationships"
    dims=client.get('/api/relationships/dimensions').json()
    assert 'trust' in dims
    body={'revision':save['revision'],'target_id':target,'context':'Доверяет на работе','dimensions':{'trust':12}}
    assert client.patch(url(target),json={**body,'target_id':actor}).status_code==409
    created=client.patch(url(actor),json=body)
    assert created.status_code==200,created.text
    updated=created.json();assert updated['state']['world']['relationships'][actor+':'+target]['context']=='Доверяет на работе'
    assert client.get(f"/api/saves/{other['id']}").json()['state']==other['state']
    assert 'Доверяет на работе' in str(build_context(updated['state'],[],'','turn',32768,2000))
    body.update(revision=updated['revision'],context='Разочарован поступком',dimensions={'trust':-10})
    changed=client.patch(url(actor),json=body).json()
    assert changed['state']['world']['relationships'][actor+':'+target]['dimensions']['trust']==-10
    app.state.repository.switch_actor(save['id'],target,changed['revision'])
    switched=client.get(f"/api/saves/{save['id']}").json()
    assert client.patch(url(actor),json={**body,'revision':switched['revision']}).status_code==409
    reverse=client.patch(url(target),json={'revision':switched['revision'],'target_id':actor,'context':'Не уверен в нём','dimensions':{'trust':-3}})
    assert reverse.status_code==200
    state=reverse.json()['state']
    assert state['world']['relationships'][actor+':'+target]['dimensions']['trust']==-10
    assert state['world']['relationships'][target+':'+actor]['dimensions']['trust']==-3
    removed=client.patch(url(target),json={'revision':reverse.json()['revision'],'target_id':actor,'delete':True})
    assert removed.status_code==200
    assert target+':'+actor not in removed.json()['state']['world']['relationships']
    assert actor+':'+target in removed.json()['state']['world']['relationships']


def test_sanitization_does_not_add_repair_timing(db):
    storage,_,sid=db
    payload=canonical(result())
    payload['world_delta']['events'][0]['evidence']='Не существует в тексте'
    job=storage.begin_job(sid,'','start',CONFIG)
    run(storage,job,payload)
    assert storage.get_job(job)['status']=='saved'
    timing=json.loads(storage.list_turns(sid)[0]['timing_json'])
    assert 'extraction_repair' not in timing and timing['extraction']>=0
    assert storage.get_job(job)['warnings_json']!='[]'


def test_significant_npc_can_be_promoted_with_full_card_in_second_call(db):
    from backend.services.world import CARD_FIELDS
    storage,_,sid=db
    before=storage.get_save(sid)['state']
    payload=canonical(result())
    payload['scene']['present_ids'].append('new_npc')
    payload['world_delta']['promotions']=[{'id':'new_npc','name':'Новый участник',
        'fields':{name:'Конкретная характеристика персонажа' for name in CARD_FIELDS},
        'situation':'Разговаривает на кухне','evidence':'Садись, поговорим'}]
    state,_,_,_,_=apply_world_updates(before,payload,NARRATIVE,'',0,'start')
    assert state['world']['characters']['new_npc']['scene_id']==state['camera']['scene_id']
    assert len(state['characters'])==len(before['characters'])+1
    assert 'new_npc' not in before['world']['characters']


def test_off_camera_thread_triggers_at_most_one_candidate(db):
    from backend.services.director import background_candidate
    from backend.services.world import normalize
    from backend.services.scene import scene_metadata
    from backend.services.timeline import current_time
    storage,_,sid=db
    before=normalize(storage.get_save(sid)['state'])
    after=deepcopy(before)
    after['world_clock']={'minute':current_time(before)+60}
    after['scene_meta']=scene_metadata(before)
    after['world']['threads']['off']={'id':'off','description':'Встреча без игрока','status':'active','state':'Открыта','relevance':0.9,'character_ids':['character_3','character_4'],'last_event_id':None}
    assert background_candidate(before,after)['reason']=='relevant_off_camera_thread'
    after['world']['threads']['off']['relevance']=0.1
    assert background_candidate(before,after) is None
