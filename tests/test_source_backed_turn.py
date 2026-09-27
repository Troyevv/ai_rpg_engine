"""Endpoint consistency replaces reconstruction of intermediate geometry."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from test_engine import db, CONFIG
from test_player_agency import execute
from test_temporal_delta import setup, payload, apply, A, B, C, QUOTE
from state_updates import apply_world_updates
from backend.services.world_delta import WorldDelta
from backend.services.world_delta_errors import StructuralDeltaError

FIXTURES=Path(__file__).parent/'fixtures'/'turn_delta'

@pytest.mark.parametrize('name',[p.stem for p in sorted(FIXTURES.glob('*.json'))])
def test_manual_failure_classes_through_saved_pipeline(db,name):
    repo,_,sid=db;setup(repo,sid)
    fixture=json.loads((FIXTURES/(name+'.json')).read_text())
    job=repo.begin_job(sid,'','start',CONFIG)
    assert len(execute(repo,job,fixture['payload'],fixture['narrative']))==2
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    diag=repo.turn_diagnostics(sid)[0];w=repo.get_save(sid)['state']['world']
    assert not diag['repairs'] and len(diag['requests'])==2
    assert w['characters'][A]['location']=='коридор'
    assert diag['derivations'][0]['origin']=='кабинет' and diag['derivations'][0]['destination']=='коридор'
    if name=='missing_event_evidence':
        assert 'e' not in w['events'] and B+':f' not in w['knowledge']
        assert any(x['code']=='evidence_missing' for x in diag['warnings'])
    else:
        assert not diag['warnings'] and w['knowledge'][B+':f']['status']=='known'
        event=w['events']['e'];snapshot=w['scenes'][event['scene_id']]
        assert snapshot['participants']==[A,B] and snapshot['witnesses']==[A,B]
        assert event['minute']==(542 if name=='incomplete_order' else None)
    assert w['characters'][B]['location']==('ординаторская' if name=='witness_departure' else 'кабинет')


def test_unknown_event_metadata_and_no_incidental_historical_bystanders(db):
    repo,_,sid=db;before=setup(repo,sid)
    before['world']['characters'][C]['location']='кабинет'
    p=payload([A,B]);e=p['world_delta']['events'][0]
    for key in ('minute','order','location'):e.pop(key)
    e['witnesses']=[B]
    w=apply(before,p)[0]['world'];event=w['events']['e'];snapshot=w['scenes'][event['scene_id']]
    assert event['location'] is None and event['minute'] is None
    assert snapshot['location'] is None and snapshot['start_minute'] is None
    assert snapshot['participants']==[A,B] and snapshot['witnesses']==[B] and C not in snapshot['participants']


def test_source_event_can_involve_npc_without_faking_a_movement(db):
    repo,_,sid=db;before=setup(repo,sid,[A])
    p=payload([A]);p['world_delta']['characters']=[dict(id=B,situation='Закончила разговор',evidence=QUOTE)]
    after=apply(before,p)[0]['world']
    assert after['characters'][B]['location']=='коридор'  # Event is not a location mutation.
    assert after['characters'][B]['situation']=='Закончила разговор' and B+':f' in after['knowledge']


@pytest.mark.parametrize('orders',[[30,10,20],[None,None,None],[10,10,20]])
def test_relative_movements_need_unambiguous_order_only(db,orders):
    repo,_,sid=db;before=setup(repo,sid)
    dest={10:'коридор',20:'лифт',30:'улица'}
    p=payload([A],location='улица')
    p['world_delta']['transitions']=[dict(actor_id=A,to_location=dest.get(order,'коридор'),evidence=QUOTE,**({'order':order} if order is not None else {})) for order in orders]
    if orders==[30,10,20]:
        after,_,saved,_,_=apply(before,p)
        assert after['world']['characters'][A]['location']=='улица'
        assert [d['origin'] for d in saved['derivations']]==['кабинет','коридор','лифт']
    else:
        after,_,saved,_,warnings=apply(before,p)
        assert after['world']['characters'][A]['location']=='улица'
        assert not warnings
        assert saved['derivations'][-1]['code']=='final_location_derived_from_scene'


def test_promoted_final_participant_needs_no_synthetic_transition(db):
    from backend.services.world import CARD_FIELDS
    repo,_,sid=db;before=setup(repo,sid,[A])
    p=payload([A,'new']);p['world_delta']['promotions']=[dict(id='new',name='Новый',fields={f:'Описание' for f in CARD_FIELDS},evidence=QUOTE)]
    p['world_delta']['events'][0].update(participants=[A,'new'],witnesses=['new'])
    p['world_delta']['knowledge'][0]['actor_id']='new'
    after=apply(before,p)[0]['world']
    assert after['characters']['new']['location']=='кабинет' and 'new:f' in after['knowledge']


def test_unsupported_event_does_not_grant_remote_edit_authority(db):
    repo,_,sid=db;before=setup(repo,sid,[A])
    p=payload([A]);p['world_delta']['events'][0].update(participants=[C],witnesses=[C],evidence='Нет цитаты')
    p['world_delta']['knowledge']=[]
    p['world_delta']['characters']=[dict(id=C,emotion='радуется',evidence=QUOTE)]
    with pytest.raises(StructuralDeltaError) as exc:apply(before,p)
    assert exc.value.code=='character_not_involved'


def test_missing_movement_is_derived_from_final_scene(db):
    repo,_,sid=db;setup(repo,sid);p=payload([A],location='коридор')
    job=repo.begin_job(sid,'','start',CONFIG)
    assert len(execute(repo,job,p,QUOTE))==2
    assert repo.get_job(job)['status']=='saved'
    diag=repo.turn_diagnostics(sid)[0]
    assert not diag['repairs'] and not diag['warnings']
    assert diag['derivations'][0]['code']=='final_location_derived_from_scene'
    w=repo.get_save(sid)['state']['world']
    assert w['characters'][A]['location']=='коридор'
    assert w['characters'][B]['location']=='кабинет'


def test_schema_hides_legacy_origin_and_requires_only_movement_changes():
    schema=WorldDelta.model_json_schema()['$defs']
    assert 'from_location' not in schema['Transition']['properties']
    assert set(schema['Transition']['required'])=={'actor_id','to_location','evidence'}
    assert not set(('minute','order','location'))&set(schema['Event']['required'])
    assert WorldDelta.model_validate({'transitions':[dict(actor_id=A,to_location='коридор',from_location='старое',evidence='цитата')]}).transitions[0].from_location=='старое'


def test_final_validator_rejects_dangling_and_inconsistent_endpoints(db):
    from backend.services.turn_delta.final_state import validate_final_state
    repo,_,sid=db;before=setup(repo,sid);after=apply(before,payload([A,B]))[0]
    plan=dict(involved={A,B},positions={cid:c['location'] for cid,c in after['world']['characters'].items()})
    broken=deepcopy(after);broken['world']['characters'][B]['scene_id']='missing'
    with pytest.raises(StructuralDeltaError):validate_final_state(before,broken,plan)
    broken=deepcopy(after);broken['world']['knowledge'][B+':f']['source_event_id']='missing'
    with pytest.raises(StructuralDeltaError):validate_final_state(before,broken,plan)
    broken=deepcopy(after);broken['world_clock']['minute']=539
    with pytest.raises(StructuralDeltaError):validate_final_state(before,broken,plan)


def test_derived_diagnostics_follow_selected_variant(db):
    repo,_,sid=db;setup(repo,sid)
    f=json.loads((FIXTURES/'conversation_departure.json').read_text())
    job=repo.begin_job(sid,'','start',CONFIG)
    assert len(execute(repo,job,f['payload'],f['narrative']))==2
    first=repo.list_turns(sid)[0];derived=repo.turn_diagnostics(sid)[0]['derivations']
    second=repo.begin_job(sid,'','regenerate',CONFIG)
    assert len(execute(repo,second,payload([A,B]),QUOTE))==2
    assert repo.turn_diagnostics(sid)[0]['derivations']==[]
    repo.select_variant(sid,first['id'],first['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.turn_diagnostics(sid)[0]['derivations']==derived


def test_omitted_event_time_survives_pov_and_next_turn(db):
    from backend.services.pov import transition
    repo,_,sid=db;before=transition(setup(repo,sid),B)
    p=payload([B],location='ординаторская',transitions=[dict(actor_id=B,to_location='ординаторская',evidence=QUOTE)])
    for key in ('minute','order','location'):p['world_delta']['events'][0].pop(key,None)
    after=apply_world_updates(before,p,QUOTE,'',1,'pov',discard_unsupported=True)[0]
    snapshot=deepcopy(after['world']['scenes'][after['world']['events']['e']['scene_id']])
    next_p=payload([B],location='кабинет',transitions=[dict(actor_id=B,to_location='кабинет',evidence=QUOTE)])
    next_p['scene'].update(time='День 1 09:06',elapsed_minutes=3)
    next_p['world_delta']['events']=[];next_p['world_delta']['knowledge']=[]
    final=apply_world_updates(after,next_p,QUOTE,'',2,'turn',discard_unsupported=True)[0]
    assert final['world']['scenes'][snapshot['id']]==snapshot
    assert final['controlled_actor_id']==B and final['world']['characters'][B]['location']=='кабинет'


def test_unknown_event_minute_keeps_current_turn_recency_without_inventing_time(db):
    from backend.services.relevance import rank
    from backend.services.world import timeline
    repo,_,sid=db;before=setup(repo,sid);p=payload([A,B])
    p['world_delta']['events'][0].pop('minute')
    after=apply(before,p)[0];event=after['world']['events']['e']
    after['world']['events']['old']=dict(event,id='old',minute=1,recorded_minute=1)
    assert event['minute'] is None and event['recorded_minute']==543
    assert rank(after,'')['events']['e']>rank(after,'')['events']['old']
    assert [e['id'] for e in timeline(after)]==['old','e']
