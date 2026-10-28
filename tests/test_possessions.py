"""Issue #77: lifecycle, evidence, agency, bounded perception and real persistence."""
from copy import deepcopy
import json
from unittest.mock import patch
import pytest
from hypothesis import given, strategies as st
from backend.runtime_v3.models import Fact, Knowledge, SignificantPossession, assert_world_state_v3_invariants
from backend.runtime_v3.migration import migrate_v2
from backend.runtime_v3.possessions import context_possessions
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.scope import ContextScope
from backend.runtime_v3.milestones import derive, query
from backend.runtime_v3.repository import committed_snapshot, read_history
from test_milestones import snapshot, db

TEXT = 'Вера закончила передачу семейного кольца.'


def state():
    return migrate_v2(snapshot()).snapshot['world_state']


def delta(s, operation='introduce', **kw):
    row = dict(item_id='ring', operation=operation, expected_revision=s.get('possessions', {}).get('ring', {}).get('revision', 0),
        updates=dict(owner_id='b', holder_id='b', location_id=None, status='available'),
        assertion='completed_outcome', significance='continuity_required', transition='established' if operation=='introduce' else 'voluntary',
        decision_actor_id='b', source_event_id='event', fact_id='p'+str(s['meta']['turn_id']), evidence=TEXT)
    if operation=='introduce': row.update(name='Семейное кольцо', kind='heirloom')
    row.update(kw)
    return row


def payload(s, c, witnesses=()):
    return dict(final_scene=dict(location_id=s['camera']['location_id'],present_character_ids=s['camera']['present_character_ids']),
        facts=[dict(id=c['fact_id'], text=TEXT, character_ids=list(s['characters']), visibility='secret', evidence=TEXT)],
        events=[dict(id=c['source_event_id'],text=TEXT, participants=list(s['characters']),witnesses=list(witnesses),
            fact_ids=[c['fact_id']],medium='observation',evidence=TEXT)], possession_deltas=[c],
        knowledge_gained=[dict(actor_id=cid, fact_id=c['fact_id'],status='known',source_event_id=c['source_event_id'],evidence=TEXT) for cid in witnesses])


def run(s, op='introduce', *, player='', witnesses=(), **kw):
    c=delta(s,op,**kw)
    return StateResolver(s,TEXT,player).resolve(payload(s,c,witnesses))


def test_lifecycle_owner_holder_location_and_history():
    s=state(); initial=deepcopy(s)
    r=run(s); assert not r.warnings; s=r.state
    assert initial['possessions']=={} and s['knowledge']==initial['knowledge']
    assert derive(r.history)[0]['category']=='possession_introduce'
    # Loan: owner stays b, holder c, location explicitly unknown.
    r=run(s,'transfer',updates=dict(holder_id='c',location_id=None));assert not r.warnings;s=r.state
    assert s['possessions']['ring']['owner_id']=='b' and s['possessions']['ring']['holder_id']=='c'
    r=run(s,'return',decision_actor_id='c',updates=dict(holder_id='b',location_id='home'));assert not r.warnings;s=r.state
    r=run(s,'sell',updates=dict(owner_id='c',holder_id='c',location_id='second'));assert not r.warnings;s=r.state
    r=run(s,'gift',decision_actor_id='c',updates=dict(owner_id='b',holder_id='b',location_id=None));assert not r.warnings;s=r.state
    r=run(s,'relocate',updates=dict(location_id='home'));assert not r.warnings;s=r.state
    assert derive(r.history)==[]  # routine relocation does not flood milestones
    r=run(s,'lose',transition='involuntary',updates=dict(holder_id=None,location_id=None,status='lost'));assert not r.warnings;s=r.state
    assert s['possessions']['ring']['owner_id']=='b'
    assert run(s,'transfer',updates=dict(holder_id='c',location_id='home')).warnings
    r=run(s,'recover',transition='involuntary',updates=dict(status='available',holder_id='c',location_id='home'));assert not r.warnings;s=r.state
    r=run(s,'return',decision_actor_id='c',updates=dict(holder_id='b',location_id=None));assert not r.warnings;s=r.state
    r=run(s,'destroy',transition='involuntary',updates=dict(status='destroyed',holder_id=None,location_id=None));assert not r.warnings;s=r.state
    for op in ('recover','introduce','acquire','relocate'):
        rejected=run(s,op)
        assert rejected.warnings and rejected.state['possessions']==s['possessions']
    change=next(c for c in r.history['state_changes'] if c.get('kind')=='possession_delta')
    assert change['before']['status']=='available' and change['after']['status']=='destroyed'
    assert change['source_record_id'] and change['source_event_id'] and change['fact_id']


@pytest.mark.parametrize('update', [dict(assertion='planned'), dict(significance='incidental'),
    dict(expected_revision=2),dict(source_event_id='missing'),dict(fact_id='missing'),
    dict(updates={'owner_id':'missing'}),dict(updates={'location_id':'missing'}),dict(updates={'price':'20'}),
    dict(updates={'status':'lost','holder_id':'b'})])
def test_bad_records_are_local_and_no_phantom_objects(update):
    s=state(); c=delta(s);raw=payload(s,c);raw['possession_deltas'][0].update(update)
    r=StateResolver(s,TEXT,'').resolve(raw)
    assert r.warnings and not r.state['possessions']


def test_intention_player_only_evidence_and_mentions_do_not_create_objects():
    s=state(); c=delta(s);raw=payload(s,c)
    raw['possession_deltas'][0]['assertion']='planned'
    r=StateResolver(s,'Она только думает о подарке.',TEXT).resolve(raw)
    assert r.warnings and not r.state['possessions']
    raw['possession_deltas']=[]
    assert not StateResolver(s,TEXT,'').resolve(raw).state['possessions']


def test_agency_external_ownership_and_custody_are_both_protected():
    s=run(state(),updates=dict(owner_id='a',holder_id='a',location_id=None,status='available')).state
    opts=dict(updates=dict(owner_id='b',holder_id='b',location_id=None), decision_actor_id='a')
    assert run(s,'sell',**opts).warnings
    r=run(s,'sell',player='Продаю кольцо Вере.',player_evidence='Продаю кольцо Вере.',player_assertion='explicit_choice',**opts)
    assert not r.warnings and r.state['possessions']['ring']['owner_id']=='b'
    assert run(s,'sell',decision_actor_id='b',updates=opts['updates']).warnings
    assert run(s,'gift',transition='involuntary',**opts).warnings
    assert not run(s,'lose',transition='involuntary',updates=dict(status='lost',holder_id=None,location_id=None)).warnings
    # Changing holder cannot smuggle an EXTERNAL handover under an NPC decision.
    assert run(s,'transfer',updates=dict(holder_id='b',location_id=None)).warnings
    c=delta(s,'sell',player_evidence='Продаю.',player_assertion='explicit_choice',**opts)
    assert StateResolver(s,TEXT,'Продаю.',mode='background').resolve(payload(s,c)).warnings


def test_reacquisition_unknowns_and_transition_guards():
    s=run(state()).state
    r=run(s,'sell',updates=dict(owner_id='c',holder_id=None,location_id=None));assert not r.warnings
    s=r.state
    r=run(s,'acquire',decision_actor_id='c',updates=dict(owner_id='b',holder_id='b',location_id=None));assert not r.warnings
    assert r.state['possessions']['ring']['owner_id']=='b'
    for op, updates in [('sell',dict(owner_id='a')),('transfer',dict(holder_id='c')),
        ('relocate',dict(location_id='home',owner_id='c')),('return',dict(holder_id='c',location_id=None))]:
        assert run(r.state,op,updates=updates).warnings
    unknown=run(state(),updates=dict(location_id=None)).state['possessions']['ring']
    assert unknown['owner_id'] is None and unknown['holder_id'] is None and unknown['status']=='unknown'


def test_idempotency_same_turn_later_reextraction_and_renamed_ids():
    s=state();c=delta(s);first=StateResolver(s,TEXT,'').resolve(payload(s,c))
    for tid in (first.state['meta']['turn_id'], first.state['meta']['turn_id']+1):
        for itemid in ('ring','ring-renamed'):
            retry=deepcopy(c);retry['item_id']=itemid;retry['source_event_id']='renamed'
            result=StateResolver(first.state,TEXT,'',turn_id=tid).resolve(payload(first.state,retry))
            assert result.state['possessions']==first.state['possessions']
            assert not any(c.get('kind')=='possession_delta' for c in result.history['state_changes'])
    duplicate=delta(first.state,item_id='duplicate',expected_revision=0)
    r=StateResolver(first.state,TEXT,'').resolve(payload(first.state,duplicate))
    assert r.warnings and len(r.state['possessions'])==1


def test_knowledge_is_field_specific_and_hidden_change_is_not_broadcast():
    from backend.runtime_v3.context import canonical_slice
    s=run(state(),witnesses=('a','b')).state
    scope=ContextScope('a',relevant_actor_ids={'a','b','c'},location_ids=['home'],present_actor_ids={'a'})
    before=context_possessions(s,scope)[0];assert before['holder_id']=='b'
    r=run(s,'transfer',updates=dict(holder_id='c',location_id='second'));assert not r.warnings
    s=r.state;rows=context_possessions(s,scope)
    assert rows[0]['owner_id']=='b' and 'holder_id' not in rows[0] and 'location_id' not in rows[0]
    # The world change doesn't supersede an uninformed person's old belief.
    oldfid=next(iter(s['possessions']['ring']['applied'].values()))
    assert s['knowledge']['a:'+oldfid]['status']=='known'
    scope.fact_ids=list(s['facts']);scope.knowledge_ids=list(s['knowledge'])
    current=canonical_slice(s,scope)
    hidden=next(reversed(s['possessions']['ring']['applied'].values()))
    assert hidden not in current['facts']
    extraction=context_possessions(s,scope,extraction=True)[0]
    assert extraction['holder_id']=='c' and extraction['known_by']['holder_id']==[]
    s['knowledge']['a:'+hidden]=Knowledge(actor_id='a',fact_id=hidden,status='known').model_dump()
    assert context_possessions(s,scope)[0]['holder_id']=='c'


def test_large_world_context_bounded_and_query_prioritized():
    s=run(state(),witnesses=('a',)).state;base=s['possessions']['ring']
    s['possessions']={str(i):dict(deepcopy(base),id=str(i),name='Документ '+str(i)) for i in range(1500)}
    scope=ContextScope('a',relevant_actor_ids={'a','b'},location_ids=['home'])
    rows=context_possessions(s,scope,extraction=True,query='Документ 1499')
    assert len(rows)<=12 and len(json.dumps(rows,ensure_ascii=False))<6100
    assert any(r['id']=='1499' for r in rows)
    empty=ContextScope('c',relevant_actor_ids={'c'},location_ids=['second'])
    assert context_possessions(s,empty)==[]


def test_persistence_atomic_history_siblings_migration_and_salvage():
    snap=migrate_v2(snapshot()).snapshot;r=run(snap['world_state']);conn=db()
    with pytest.raises(RuntimeError),conn:
        committed_snapshot(conn,snap,r);raise RuntimeError('abort transaction')
    assert not query(conn,snap['history_head'])
    with conn:
        after=committed_snapshot(conn,snap,r)
        sibling=committed_snapshot(conn,snap,StateResolver(snap['world_state'],'Тишина.','').resolve({'final_scene':{'location_id':'home','present_character_ids':['a']}}))
    assert len(query(conn,after['history_head']))==1 and query(conn,sibling['history_head'])==[]
    assert read_history(conn,after['history_head'])[0]['state_changes']
    assert migrate_v2(json.loads(json.dumps(after))).snapshot['world_state']==after['world_state']
    assert not sibling['world_state']['possessions'] and not snap['world_state']['possessions']
    bad=deepcopy(after['world_state']);bad['possessions']['broken']={'owner_id':'missing'}
    assert len(assert_world_state_v3_invariants(bad)['possessions'])==1 and 'broken' in bad['possessions']
    old=deepcopy(snap);old['world_state'].pop('possessions')
    assert not migrate_v2(old).snapshot['world_state']['possessions']
    assert 'possessions' not in old['world_state']


@given(st.integers(min_value=0,max_value=10080))
def test_time_never_restores_disposed_property(minutes):
    s=run(state()).state
    destroyed=run(s,'destroy',transition='involuntary',updates=dict(status='destroyed',holder_id=None,location_id=None))
    assert not destroyed.warnings
    s=destroyed.state
    after=StateResolver(s,'Прошло время.','').resolve(dict(final_scene=dict(location_id='home',present_character_ids=['a'],elapsed_minutes=minutes))).state
    assert after['possessions']==s['possessions']


def test_real_jobs_start_turn_reload_next_regenerate_variants_rollback(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job, CONFIG
    from runtime_v3_fixture import execute
    repo=Repository(tmp_path/'possessions.sqlite');sid=load_fixture(repo,'possessions')['save']
    initial=repo.get_snapshot(sid)['world_state']['possessions']
    assert len(initial)==3 and initial['qa_camera']['owner_id']!=initial['qa_camera']['holder_id']
    ordinary_job(repo,sid,'start');ordinary_job(repo,sid)
    repo=Repository(repo.path);ordinary_job(repo,sid)
    before=repo.get_snapshot(sid);s=before['world_state']
    assert s['possessions']==initial
    c=delta(s,'return',item_id='qa_camera',expected_revision=0,decision_actor_id='qa_vera',updates=dict(holder_id='qa_timur',location_id=None))
    raw=payload(s,c,('qa_kirill','qa_vera','qa_timur'))
    with patch('backend.runtime_v3.simulation.background_candidate',return_value=None):
        jid=repo.begin_job(sid,'Наблюдаю.','turn',CONFIG);execute(repo,jid,raw,TEXT)
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
        after=repo.get_snapshot(sid);turn=repo.list_turns(sid)[-1]
        assert after['world_state']['possessions']['qa_camera']['holder_id']=='qa_timur'
        jid=repo.begin_job(sid,'','regenerate',CONFIG);execute(repo,jid,raw,TEXT)
        assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
        assert repo.get_snapshot(sid)['world_state']==after['world_state']
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==after
    repo.rollback_last(sid);assert repo.get_snapshot(sid)==before
    ordinary_job(repo,sid)
    assert repo.get_snapshot(sid)['world_state']['possessions']==initial


def test_legacy_actual_save_migrates_and_remains_playable(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job
    repo=Repository(tmp_path/'legacy.sqlite');sid=load_fixture(repo)['save'];snap=repo.get_snapshot(sid)
    snap['world_state'].pop('possessions',None)
    snap['character_cards'][0]['fields']['Внешность']='Кольцо, часы, телефон — просто описание.'
    with repo.connect() as conn: conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snap),sid))
    ordinary_job(repo,sid,'start');ordinary_job(repo,sid);repo=Repository(repo.path);ordinary_job(repo,sid)
    assert repo.get_snapshot(sid)['world_state']['possessions']=={}


def test_ordered_transitions_and_ambiguous_order_rejected():
    s=run(state()).state;c=delta(s,'sell',updates=dict(owner_id='c',holder_id='c',location_id=None))
    raw=payload(s,c)
    second=dict(c,operation='gift',fact_id='gift',source_event_id='gift_event',expected_revision=2,decision_actor_id='c',updates=dict(owner_id='b',holder_id='b',location_id=None))
    raw['possession_deltas'].append(second)
    raw['facts'].append(dict(raw['facts'][0],id='gift'))
    raw['events'].append(dict(raw['events'][0],id='gift_event',fact_ids=['gift']))
    rejected=StateResolver(s,TEXT,'').resolve(raw)
    assert rejected.warnings and rejected.state['possessions']==s['possessions']
    raw['events'][0]['order']=1;raw['events'][1]['order']=2
    raw['possession_deltas'].reverse()
    r=StateResolver(s,TEXT,'').resolve(raw)
    assert not r.warnings and r.state['possessions']['ring']['revision']==3
    assert r.state['possessions']['ring']['owner_id']=='b'


def test_full_context_hides_secret_possession_history_and_milestones():
    from backend.runtime_v3.context import build_context
    s=run(state(),witnesses=('a',)).state
    r=run(s,'transfer',updates=dict(holder_id='c',location_id='second'))
    snap=snapshot(r.state);conn=db();committed=committed_snapshot(conn,snap,r)
    from backend.runtime_v3.milestones import reader
    history=dict(r.history,_milestone_query=lambda **filters: query(conn,committed['history_head'],**filters))
    messages=build_context(snap,[],'Семейное кольцо','turn',32768,3000,world_history=history)
    hidden=next(reversed(r.state['possessions']['ring']['applied'].values()))
    data='\n'.join(m['content'] for m in messages)
    assert hidden not in data
    assert 'possession_transfer' not in data


def test_grounded_knowledge_correction_uses_existing_lifecycle_without_gossip():
    s=state();c=delta(s);raw=payload(s,c,('a','b'))
    raw['facts'][0]['claim']=dict(subject_id='ring',predicate='possession.holder_id',scope='ownership',value='b')
    first=StateResolver(s,TEXT,'').resolve(raw);assert not first.warnings
    oldfid=c['fact_id'];s=first.state
    c=delta(s,'transfer',updates=dict(holder_id='c',location_id=None));raw=payload(s,c,('c',))
    raw['facts'][0]['claim']=dict(subject_id='ring',predicate='possession.holder_id',scope='ownership',value='c')
    second=StateResolver(s,TEXT,'').resolve(raw);assert not second.warnings;s=second.state
    assert s['knowledge']['a:'+oldfid]['status']=='known'
    newfid=c['fact_id'];before=deepcopy(s['possessions'])
    raw=dict(final_scene=dict(location_id='home',present_character_ids=['a']),
        events=[dict(id='tell',text=TEXT,evidence=TEXT,participants=['a','c'],witnesses=['a'],fact_ids=[oldfid,newfid],medium='conversation')],
        knowledge_gained=[dict(actor_id='a',fact_id=newfid,status='known',source_event_id='tell',supersedes=[oldfid],evidence=TEXT)])
    r=StateResolver(s,TEXT,'').resolve(raw)
    assert not r.warnings and r.state['possessions']==before
    assert r.state['knowledge']['a:'+oldfid]['status']=='superseded'
    assert r.state['knowledge']['a:'+newfid]['status']=='known'
    assert r.state['knowledge']['b:'+oldfid]['status']=='known'
    assert 'b:'+newfid not in r.state['knowledge']


def test_delta_limit_and_transaction_retry_after_transfer():
    from backend.runtime_v3.raw import RawTurnResult
    s=run(state()).state;c=delta(s,'transfer',updates=dict(holder_id='c',location_id=None))
    raw=payload(s,c);first=StateResolver(s,TEXT,'').resolve(raw);assert not first.warnings
    c['source_event_id']='retry_renamed'
    replay=StateResolver(first.state,TEXT,'').resolve(payload(first.state,c))
    assert not replay.warnings and replay.state['possessions']==first.state['possessions']
    from backend.services.world_delta_errors import StructuralDeltaError
    with pytest.raises(StructuralDeltaError) as exc:
        RawTurnResult.parse(dict(final_scene={},possession_deltas=[c]*30))
    assert exc.value.code=='development_budget' and exc.value.repairable


def test_field_sources_cannot_be_rebound_using_a_noop_update():
    # Reasserting a current value under a more widely-known fact must not smuggle
    # a hidden holder into knowledge: only actual changed fields receive new sources.
    s=run(state(),witnesses=('b',)).state
    before=s['possessions']['ring']['field_facts']['holder_id']
    c=delta(s,'relocate',updates=dict(location_id='home'))
    r=StateResolver(s,TEXT,'').resolve(payload(s,c,('a',)))
    assert not r.warnings and r.state['possessions']['ring']['field_facts']['holder_id']==before


def test_context_hard_budget_prunes_incidental_property_but_keeps_named_item():
    from backend.runtime_v3.context import build_context
    from context_builder import estimate
    s=run(state(),witnesses=('a',)).state
    source=s['possessions']['ring']
    snap=snapshot(s)
    args=dict(extraction_text=TEXT, target_context_budget=1000)
    baseline=build_context(snap,[],'Семейное кольцо','turn',64000,2000,**args)
    limit=estimate(baseline)+200
    for i in range(100):
        s['possessions']['spare'+str(i)]=dict(deepcopy(source),id='spare'+str(i),name='Запасной предмет '+str(i),owner_id='a')
    result=build_context(snap,[],'Семейное кольцо','turn',limit+2000+256,2000,**args)
    current=json.loads(next(m['content'].split('\n',1)[1] for m in result if m['content'].startswith('Текущее состояние / GM-only')))
    assert estimate(result)<=limit
    assert any(p['id']=='ring' for p in current['possessions'])
    assert result.selection['sections']['possessions']['included'] < result.selection['sections']['possessions']['selected']
