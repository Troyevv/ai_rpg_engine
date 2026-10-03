"""Raw local salvage and canonical-origin movement through the real job pipeline."""
from copy import deepcopy
from collections import Counter
import json
import pytest
from pydantic import ValidationError
from test_engine import db, CONFIG
from test_player_agency import execute
from test_temporal_delta import setup, payload, move, apply, A, B, C, QUOTE
from state_updates import apply_world_updates
from backend.services.world_delta import WorldDelta
from backend.services.world_delta_errors import StructuralDeltaError
from storage import Storage

DIRECT='Илья выходит из кабинета в коридор.'


def relation():
    return dict(source_id=B,target_id=A,dimensions={'trust':15},context='Доверяет',evidence=QUOTE)


def run(repo,sid,p,narrative=QUOTE):
    job=repo.begin_job(sid,'','start',CONFIG)
    calls=execute(repo,job,p,narrative)
    assert repo.get_job(job)['status']=='saved', repo.get_job(job)['error']
    return calls,repo.turn_diagnostics(sid)[0]


def test_missing_event_evidence_commits_two_calls_and_cascades(db):
    repo,_,sid=db;setup(repo,sid)
    p=payload([A,B]);del p['world_delta']['events'][0]['evidence']
    p['world_delta']['characters']=[dict(id=B,situation='Завершила разговор',evidence=QUOTE)]
    p['world_delta']['threads']=[dict(id='thread',description='Разговор',character_ids=[A,B],status='active',state='Начат',relevance=.5,last_event_id='e',evidence=QUOTE)]
    calls,diag=run(repo,sid,p)
    assert len(calls)==2 and not diag['repairs']
    warnings=diag['warnings'];w=next(w for w in warnings if w['code']=='evidence_missing')
    assert (w['section'],w['index'],w['field'],w['entity'],w['action'])==('events',0,'evidence','e','drop_record')
    state=repo.get_save(sid)['state']['world']
    assert 'e' not in state['events'] and B+':f' not in state['knowledge'] and 'thread' not in state['threads']
    assert state['characters'][B]['situation']=='Завершила разговор'
    assert Storage(repo.path).turn_diagnostics(sid)[0]['warnings']==warnings
    assert '"evidence"' not in json.dumps(json.loads(next(r for r in diag['requests'] if r['stage']=='extraction')['response_text'])['world_delta']['events'][0])


def test_missing_fact_evidence_prunes_only_dependent_references(db):
    repo,_,sid=db;setup(repo,sid);p=payload([A,B])
    del p['world_delta']['facts'][0]['evidence']
    p['world_delta']['facts'].append(dict(id='kept',text='Второй факт',evidence=QUOTE))
    p['world_delta']['events'][0]['fact_ids'].append('kept')
    calls,diag=run(repo,sid,p)
    w=repo.get_save(sid)['state']['world']
    assert len(calls)==2 and not diag['repairs']
    assert 'f' not in w['facts'] and 'kept' in w['facts']
    assert w['events']['e']['fact_ids']==['kept'] and B+':f' not in w['knowledge']


def test_multiple_missing_and_unsupported_keep_original_indices(db):
    repo,_,sid=db;before=setup(repo,sid);p=payload([A,B])
    p['world_delta']['events']=[dict(p['world_delta']['events'][0],id='missing'),dict(p['world_delta']['events'][0],id='bad',evidence='Нет цитаты'),p['world_delta']['events'][0]]
    del p['world_delta']['events'][0]['evidence']
    p['world_delta']['relationships']=[relation(),dict(relation(),source_id=A,target_id=B)]
    del p['world_delta']['relationships'][1]['evidence']
    state,_,_,_,warnings=apply(before,p)
    counts=Counter(w['code'] for w in warnings)
    assert counts['evidence_missing']==2 and counts['evidence_unsupported']==1
    assert next(w for w in warnings if w['code']=='evidence_unsupported')['index']==1
    assert 'e' in state['world']['events'] and B+':f' in state['world']['knowledge']


@pytest.mark.parametrize('bad',["invalid",{'events':{}},{'events':'invalid'},
    {'events':[dict(id='e',text='x',participants='Илья',witnesses=[],medium='action')]},
    {'events':[dict(id='e',text='x',participants=[],witnesses=[],medium='action',minute='вечером')]},
    {'facts':[dict(id='f',text='x',unknown=True)]}])
def test_other_schema_errors_are_not_hidden_by_missing_evidence(db,bad):
    repo,_,sid=db;before=setup(repo,sid);p=payload([A,B]);p['world_delta']=bad
    with pytest.raises(StructuralDeltaError) as exc:apply(before,p)
    assert exc.value.code=='schema_invalid' and repo.get_save(sid)['state']==before
    fixed=payload([A,B]);job=repo.begin_job(sid,'','start',CONFIG)
    assert len(execute(repo,job,p,QUOTE,repaired=fixed))==3
    assert repo.get_job(job)['status']=='saved'
    assert repo.turn_diagnostics(sid)[0]['repairs'][0]['repair_error_code']=='schema_invalid'


def test_fact_unknown_without_discarded_id_stays_structural(db):
    repo,_,sid=db;before=setup(repo,sid);p=payload([A,B])
    p['world_delta']['events'][0]['fact_ids']=['unknown']
    del p['world_delta']['facts'][0]['evidence']
    with pytest.raises(StructuralDeltaError):apply(before,p)


def test_discarded_update_does_not_delete_existing_fact(db):
    repo,_,sid=db;before=setup(repo,sid);p=payload([A,B])
    before['world']['facts']['f']=dict(id='f',text='Старый факт',evidence=[QUOTE])
    del p['world_delta']['facts'][0]['evidence']
    after=apply(before,p)[0]['world']
    assert after['facts']['f']['text']=='Старый факт' and B+':f' in after['knowledge']


@pytest.mark.parametrize('missing',[True,False])
def test_unsourced_transition_dropped_and_final_snapshot_resolves_position(db,missing):
    repo,_,sid=db;before=setup(repo,sid)
    p=payload([A,B],transitions=[move(B,'кабинет','коридор')])
    if missing:del p['world_delta']['transitions'][0]['evidence']
    else:p['world_delta']['transitions'][0]['evidence']='Нет цитаты'
    after,_,_,_,warnings=apply(before,p)
    assert after['world']['characters'][B]['location']=='кабинет'
    assert warnings[0]['code']==('evidence_missing' if missing else 'evidence_unsupported')
    p['scene'].update(location='коридор',present_ids=[A,B])
    job=repo.begin_job(sid,'','start',CONFIG)
    assert len(execute(repo,job,p,QUOTE))==2
    assert repo.get_job(job)['status']=='saved'
    assert repo.get_save(sid)['state']['world']['characters'][B]['location']=='коридор'
    assert not repo.turn_diagnostics(sid)[0]['repairs']


def test_canonical_schema_stays_strict_and_origin_is_optional():
    schema=WorldDelta.model_json_schema()
    required=schema['$defs']['Transition']['required']
    assert set(required)=={'actor_id','to_location','evidence'}
    for name in ('Fact','Event','Character','Relationship','Knowledge','Thread','Transition'):
        assert 'evidence' in schema['$defs'][name]['required']
    with pytest.raises(ValidationError):WorldDelta.model_validate({'facts':[dict(id='f',text='x')]})


def test_realistic_turn_omitted_origin_two_calls(db):
    repo,_,sid=db;setup(repo,sid)
    t=move(A,'кабинет','коридор');del t['from_location']
    p=payload([A],location='коридор',transitions=[t])
    calls,diag=run(repo,sid,p)
    w=repo.get_save(sid)['state']['world']
    assert len(calls)==2 and not diag['repairs'] and not diag['warnings']
    assert 'f' in w['facts'] and B+':f' in w['knowledge']
    assert w['characters'][A]['location']=='коридор' and w['characters'][B]['location']=='кабинет'
    assert w['scenes'][w['events']['e']['scene_id']]['participants']==[A,B]
    assert repo.get_save(sid)['state']['scene_meta']['present_ids']==[A]


def test_sequential_origins_and_intermediate_event(db):
    repo,_,sid=db;before=setup(repo,sid)
    before['world']['characters'][B]['location']='коридор'
    before['world']['scenes']['office']['participants']=[A]
    before['scene_meta']['present_ids']=[A]
    transitions=[move(A,None,'коридор',541),move(A,None,'лифт',542),move(A,None,'улица',543)]
    for t in transitions:del t['from_location']
    p=payload([A],location='улица',transitions=transitions,event_minute=541,event_order=1)
    p['world_delta']['events'][0]['location']='коридор'
    after=apply(before,p)[0]['world']
    assert after['characters'][A]['location']=='улица' and after['events']['e']['location']=='коридор'
    assert B+':f' in after['knowledge']


def correction_setup(repo,sid):
    state=setup(repo,sid)
    state['characters'][0]['name']='Илья'
    with repo.connect() as conn:conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(state),sid))
    p=payload([A],location='коридор',transitions=[move(A,'кабинет №1','коридор')])
    for entries in p['world_delta'].values():
        for item in entries:item['evidence']=DIRECT
    return state,p


def test_legacy_origin_is_ignored_and_derivation_is_not_repair(db):
    repo,_,sid=db;_,p=correction_setup(repo,sid)
    del p['world_delta']['facts'][0]['evidence']
    p['world_delta']['relationships']=[dict(relation(),evidence='Нет цитаты')]
    calls,diag=run(repo,sid,p,DIRECT)
    counts=Counter(w['code'] for w in diag['warnings'])
    assert counts['evidence_missing']==counts['evidence_unsupported']==1
    assert counts['transition_from_location_corrected']==0
    assert len(calls)==2 and not diag['repairs']
    assert diag['derivations'][0]['origin']=='кабинет' and diag['derivations'][0]['destination']=='коридор'
    assert repo.get_save(sid)['state']['world']['characters'][A]['location']=='коридор'


@pytest.mark.parametrize('quote',[
    'Илья вышел из кабинета, зашёл в палату, после разговора вышел на улицу.',
    'Илья вышел из палаты на улицу.',
    'Илья покинул помещение.',
    'Илья направился в коридор.',
])
def test_language_and_legacy_origin_do_not_control_movement(db,quote):
    repo,_,sid=db;before,p=correction_setup(repo,sid)
    p['world_delta']['transitions'][0]['from_location']='палата'
    for entries in p['world_delta'].values():
        for item in entries:item['evidence']=quote
    state=apply_world_updates(before,p,quote,'',1,discard_unsupported=True)[0]
    assert state['world']['characters'][A]['location']=='коридор'
    calls,diag=run(repo,sid,p,quote)
    assert len(calls)==2 and not diag['repairs'] and not diag['warnings']


def test_correct_origin_legacy_output_accepted(db):
    repo,_,sid=db;before,p=correction_setup(repo,sid)
    p['world_delta']['transitions'][0]['from_location']='кабинет'
    assert apply_world_updates(before,p,DIRECT,'',1,discard_unsupported=True)[4]==[]


@pytest.mark.parametrize('section,record',[
    ('characters',dict(id=B,situation='После разговора')),
    ('knowledge',dict(actor_id=B,fact_id='f',status='known',source_event_id='e')),
    ('relationships',dict(source_id=B,target_id=A,dimensions={'respect':20},context='Уважает')),
    ('threads',dict(id='t',description='Линия',character_ids=[A],status='active',state='',relevance=.5,last_event_id='e')),
    ('scheduled_events',dict(id='s',due_minute=550,type='meeting',participants=[A],description='Встреча')),
])
def test_whitelist_removes_only_missing_provenance_record(db,section,record):
    repo,_,sid=db;before=setup(repo,sid);p=payload([A,B])
    p['world_delta'][section]=[record]
    state,_,changes,_,warnings=apply(before,p)
    assert changes['world_delta'][section]==[]
    assert warnings[0]['code']=='evidence_missing' and warnings[0]['section']==section
    assert 'e' in state['world']['events']


def test_discarded_event_does_not_resolve_scheduled_obligation(db):
    repo,_,sid=db;before=setup(repo,sid)
    scheduled=dict(id='s',due_minute=540,type='meeting',participants=[A],description='Встреча',status='pending')
    before['world']['scheduled_events']['s']=deepcopy(scheduled)
    p=payload([A,B]);del p['world_delta']['events'][0]['evidence']
    p['world_delta']['scheduled_events']=[dict(scheduled,status='resolved',resolved_event_id='e',evidence=QUOTE)]
    after=apply(before,p)[0]['world']
    assert after['scheduled_events']['s']==scheduled and 'e' not in after['events']


def test_variant_restores_salvage_warnings_and_its_request_count(db):
    repo,_,sid=db;setup(repo,sid)
    p=payload([A,B]);del p['world_delta']['events'][0]['evidence']
    _,diag=run(repo,sid,p)
    first=repo.list_turns(sid)[0]
    second=repo.begin_job(sid,'','regenerate',CONFIG)
    assert len(execute(repo,second,payload([A,B]),QUOTE))==2
    assert repo.turn_diagnostics(sid)[0]['warnings']==[]
    repo.select_variant(sid,first['id'],first['active_variant_id'],repo.get_save(sid)['revision'])
    restored=repo.turn_diagnostics(sid)[0]
    assert restored['warnings']==diag['warnings'] and not restored['repairs'] and len(restored['requests'])==2
