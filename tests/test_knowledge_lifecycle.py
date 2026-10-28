"""#76: subjective belief transitions, grounding, chronology and ordinary jobs."""
from copy import deepcopy
import json
import pytest
from hypothesis import given, settings, strategies as st
from backend.runtime_v3.models import Fact, Knowledge, Character, assert_world_state_v3_invariants
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.knowledge import slot
from backend.runtime_v3.context import build_context
from backend.runtime_v3.history import audit_world_history
from backend.runtime_v3.repository import committed_snapshot, read_history
from backend.runtime_v3.migration import migrate_v2
from test_milestones import snapshot, db
from test_goals_values import raw

TEXT = 'Борис рассказал Анне: теперь он работает в больнице, а не в банке.'


def initial():
    snap = migrate_v2(snapshot()).snapshot
    s = snap['world_state']
    for fid, value in (('bank', 'bank_a'), ('hospital', 'hospital_b')):
        s['facts'][fid] = Fact(id=fid, text='Борис работает в '+value,
            character_ids=['b'], claim=dict(subject_id='b', predicate='primary_employment', value=value)).model_dump()
    for actor in 'ac':
        s['knowledge'][actor+':bank'] = Knowledge(actor_id=actor, fact_id='bank').model_dump()
    return snap


def acquisition(s, fid='hospital', actor='a', **fields):
    return raw(s, events=[dict(id='news', text=TEXT, evidence=TEXT, participants=['b',actor],
        witnesses=[actor], fact_ids=[fid], medium='conversation')],
        knowledge_gained=[dict(actor_id=actor, fact_id=fid, source_event_id='news', evidence=TEXT, **fields)])


def test_correction_preserves_other_minds_facts_and_before_after_history():
    s = initial()['world_state']; before = deepcopy(s)
    r = StateResolver(s,TEXT,'Слушаю.').resolve(acquisition(s))
    assert not r.warnings
    assert r.state['facts'] == before['facts']
    assert s == before
    assert r.state['knowledge']['a:bank']['status'] == 'superseded'
    assert r.state['knowledge']['a:bank']['replaced_by'] == 'hospital'
    assert r.state['knowledge']['a:hospital']['status'] == 'known'
    assert r.state['knowledge']['c:bank'] == before['knowledge']['c:bank']
    assert 'c:hospital' not in r.state['knowledge']
    old, new = r.history['knowledge_acquisitions']
    assert old['before'] == before['knowledge']['a:bank']
    assert old['after']['status'] == 'superseded' and new['before'] is None
    assert all(row['source_event_id'] == r.history['events'][0]['id'] for row in (old,new))
    assert not audit_world_history(r.history)


def test_objective_role_changes_and_decades_do_not_rewrite_beliefs():
    s = initial()['world_state']; beliefs = deepcopy(s['knowledge'])
    p=raw(s,role_changes=[dict(id='new_job',actor_id='b',kind='employment',title='Врач',
        assertion='established',transition='external',fact_id='hospital',evidence=TEXT)])
    r=StateResolver(s,TEXT,'').resolve(p)
    assert r.state['roles']['new_job']['title']=='Врач'
    r.state['meta']['world_time'] += 20*365*1440
    r=StateResolver(r.state,'Прошли годы.','').resolve(raw(r.state))
    assert r.state['knowledge']==beliefs
    snap=initial();snap['world_state']=r.state
    messages=build_context(snap,[],'Борис работает в hospital_b?','turn',32768,2000)
    beliefs_block=next(m['content'] for m in messages if m['content'].startswith('Знания POV'))
    assert 'bank' in beliefs_block and 'hospital' not in beliefs_block


@pytest.mark.parametrize('status',['suspected','unknown','outdated','refuted'])
def test_supported_status_transitions_preserve_history(status):
    s=initial()['world_state']
    r=StateResolver(s,TEXT,'').resolve(acquisition(s,'bank',status=status,expected_revision=0))
    assert r.state['knowledge']['a:bank']['status']==status
    assert r.history['knowledge_acquisitions'][0]['before']['status']=='known'
    assert r.state['knowledge']['c:bank']['status']=='known'


def test_suspected_alternative_can_coexist_and_known_correction_retires_old_known():
    s=initial()['world_state']
    r=StateResolver(s,TEXT,'').resolve(acquisition(s,status='suspected'))
    assert r.state['knowledge']['a:bank']['status']=='known'
    assert r.state['knowledge']['a:hospital']['status']=='suspected'
    corrected=StateResolver(r.state,TEXT,'').resolve(acquisition(r.state,expected_revision=1))
    assert corrected.state['knowledge']['a:bank']['status']=='superseded'
    assert corrected.state['knowledge']['a:hospital']['revision']==2


@pytest.mark.parametrize('damage',['witness','source','medium','fact','future','revision','status','revision_type','dead','unconscious'])
def test_invalid_updates_never_retire_or_broadcast(damage):
    s=initial()['world_state'];p=acquisition(s);text=TEXT;player=''
    if damage=='witness':p['events'][0]['witnesses']=[]
    if damage=='source':p['knowledge_gained'][0]['source_event_id']='old-event'
    if damage=='medium':p['events'][0]['medium']='action'
    if damage=='fact':p['events'][0]['fact_ids']=[]
    if damage=='future':text='Анна ещё не получила сообщение.';player=TEXT
    if damage=='revision':p['knowledge_gained'][0]['expected_revision']=9
    if damage=='revision_type':p['knowledge_gained'][0]['expected_revision']=False
    if damage=='status':p['knowledge_gained'][0]['status']=[]
    if damage in ('dead','unconscious'):
        # Use an off-camera actor to preserve valid camera invariants.
        p=acquisition(s,actor='c')
        if damage=='dead':s['characters']['c']['life_status']='dead'
        else:s['characters']['c']['capabilities']['conscious']=False
    before=deepcopy(s['knowledge'])
    r=StateResolver(s,text,player).resolve(p)
    assert r.state['knowledge']==before and r.warnings


def test_scope_disambiguates_parallel_roles_and_no_text_matching():
    s=initial()['world_state'];s['facts']['hospital']['claim']['scope']='weekends'
    r=StateResolver(s,TEXT,'').resolve(acquisition(s))
    assert r.state['knowledge']['a:bank']['status']=='known'
    s['facts']['hospital']['claim']=None
    r=StateResolver(s,TEXT,'').resolve(acquisition(s))
    assert r.state['knowledge']['a:bank']['status']=='known'


def test_explicit_legacy_correction_needs_both_claims_in_grounded_event():
    s=initial()['world_state']
    for f in s['facts'].values():f['claim']=None
    p=acquisition(s,supersedes=['bank'])
    assert StateResolver(s,TEXT,'').resolve(p).state['knowledge']==s['knowledge']
    p['events'][0]['fact_ids'].append('bank')
    r=StateResolver(s,TEXT,'').resolve(p)
    assert r.state['knowledge']['a:bank']['status']=='superseded'


def test_replay_and_retired_revival_require_revision():
    s=initial()['world_state'];r=StateResolver(s,TEXT,'').resolve(acquisition(s))
    replay=StateResolver(r.state,TEXT,'').resolve(acquisition(r.state))
    assert replay.state['knowledge']==r.state['knowledge'] and not replay.history['knowledge_acquisitions']
    stale=StateResolver(r.state,TEXT,'').resolve(acquisition(r.state,'bank'))
    assert stale.state['knowledge']==r.state['knowledge']
    renewed=StateResolver(r.state,TEXT,'').resolve(acquisition(r.state,'bank',expected_revision=1))
    assert renewed.state['knowledge']['a:bank']['status']=='known'
    assert renewed.state['knowledge']['a:bank']['replaced_by'] is None
    assert renewed.state['knowledge']['a:hospital']['status']=='superseded'


@pytest.mark.parametrize('ordered',[False,True])
def test_multiple_conflicting_acquisitions_need_event_order(ordered):
    s=initial()['world_state'];s['knowledge']={}
    p=acquisition(s)
    p['events'].append(dict(p['events'][0],id='previous',fact_ids=['bank']))
    p['knowledge_gained'].append(dict(p['knowledge_gained'][0],fact_id='bank',source_event_id='previous'))
    if ordered:
        p['events'][0]['order']=2;p['events'][1]['order']=1
    r=StateResolver(s,TEXT,'').resolve(p)
    if ordered:
        assert r.state['knowledge']['a:bank']['status']=='superseded'
        assert r.state['knowledge']['a:hospital']['status']=='known'
    else:
        assert not r.state['knowledge'] and r.warnings


def test_background_acquires_only_for_grounded_unprotected_witnesses():
    s=initial()['world_state'];p=acquisition(s,actor='c')
    r=StateResolver(s,TEXT,'',observed=False,mode='background',protected_actor_id='a').resolve(p)
    assert r.state['knowledge']['c:hospital']['status']=='known'
    assert r.state['knowledge']['a:bank']==s['knowledge']['a:bank']
    protected=StateResolver(s,TEXT,'',observed=False,mode='background',protected_actor_id='a',
        protected_knowledge_actor_ids=['a','c']).resolve(p)
    assert protected.state['knowledge']==s['knowledge']


def test_120_npcs_no_propagation_and_bounded_context():
    snap=initial();s=snap['world_state']
    for n in range(120):
        cid=f'npc_{n}';s['characters'][cid]=Character(id=cid).model_dump()
        s['knowledge'][cid+':bank']=Knowledge(actor_id=cid,fact_id='bank').model_dump()
    before=deepcopy(s['knowledge']);r=StateResolver(s,TEXT,'').resolve(acquisition(s))
    for key,row in before.items():
        if row['actor_id']!='a':assert r.state['knowledge'][key]==row
    assert len(r.history['knowledge_acquisitions'])==2
    snap['world_state']=r.state
    messages=build_context(snap,[],'Борис работает в bank_a?','turn',32768,2000)
    block=next(m['content'] for m in messages if m['content'].startswith('Знания POV'))
    assert 'hospital' in block and 'bank' not in block
    assert 'npc_119' not in str(messages)


def test_conservative_old_v3_migration_and_optional_metadata_salvage():
    snap=initial();s=snap['world_state']
    for fact in s['facts'].values():fact.pop('claim')
    for key,row in list(s['knowledge'].items()):s['knowledge'][key]={f:row[f] for f in ('actor_id','fact_id','status')}
    before=deepcopy(snap)
    migrated=migrate_v2(snap).snapshot
    assert snap==before
    assert all(row['revision']==0 and row['source_event_id'] is None for row in migrated['world_state']['knowledge'].values())
    assert all(row['claim'] is None for row in migrated['world_state']['facts'].values())
    s['facts']['bank']['claim']={'subject_id':[]}
    s['knowledge']['a:bank'].update(revision='bad',evidence=[])
    assert migrate_v2(snap).snapshot['world_state']['knowledge']['a:bank']['status']=='known'


def test_branches_and_json_reload_keep_independent_chronology():
    conn=db();base=initial();s=base['world_state']
    r=StateResolver(s,TEXT,'').resolve(acquisition(s))
    left=committed_snapshot(conn,base,r)
    right=committed_snapshot(conn,base,StateResolver(s,'Тишина.','').resolve(raw(s)))
    loaded=json.loads(json.dumps(left));assert loaded==left
    assert left['world_state']['knowledge']['a:bank']['status']=='superseded'
    assert right['world_state']['knowledge']['a:bank']['status']=='known'
    assert len(read_history(conn,left['history_head'])[0]['knowledge_acquisitions'])==2
    assert not read_history(conn,right['history_head'])[0]['knowledge_acquisitions']


# This checks state invariants, not performance; 25 Resolver runs exceed 200ms
# on constrained workers (also reproduced on the unchanged master).
@settings(deadline=None)
@given(st.lists(st.sampled_from(['bank','hospital']),min_size=1,max_size=25))
def test_property_one_current_known_value_per_exclusive_slot(sequence):
    s=initial()['world_state']
    for fid in sequence:
        revision=s['knowledge'].get('a:'+fid,{}).get('revision',0)
        r=StateResolver(s,TEXT,'').resolve(acquisition(s,fid,expected_revision=revision));s=r.state
        known=[row for row in s['knowledge'].values() if row['actor_id']=='a' and row['status']=='known']
        assert len({s['facts'][row['fact_id']]['claim']['value'] for row in known})==1
        assert_world_state_v3_invariants(s)


def test_checkpoint_ordinary_turn_reload_next_turn_regenerate_and_rollback(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture, knowledge_correction
    from test_narrative_test_world import CONFIG
    from runtime_v3_fixture import execute
    repo=Repository(tmp_path/'knowledge.sqlite');sid=load_fixture(repo,'knowledge')['save']
    before=repo.get_snapshot(sid);text,p=knowledge_correction(before)
    jid=repo.begin_job(sid,'Читаю сообщение.','turn',CONFIG)
    assert len(execute(repo,jid,p,text))==2
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    after=repo.get_snapshot(sid);turn=repo.list_turns(sid)[-1]
    assert after['world_state']['knowledge']['qa_kirill:qa_oleg_workshop']['status']=='superseded'
    repo=Repository(repo.path);assert repo.get_snapshot(sid)==after
    jid=repo.begin_job(sid,'','regenerate',CONFIG)
    execute(repo,jid,raw(before['world_state']),'Кирилл ещё не прочитал сообщение.')
    assert repo.get_job(jid)['status']=='saved'
    assert repo.get_snapshot(sid)['world_state']['knowledge']['qa_kirill:qa_oleg_workshop']['status']=='known'
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)['world_state']['knowledge']==after['world_state']['knowledge']
    jid=repo.begin_job(sid,'Жду.','turn',CONFIG);execute(repo,jid,raw(after['world_state']),'Кирилл ждёт.')
    assert repo.get_job(jid)['status']=='saved'
    assert repo.get_snapshot(sid)['world_state']['knowledge']==after['world_state']['knowledge']
    repo.rollback_last(sid);repo.rollback_last(sid)
    assert repo.get_snapshot(sid)['world_state']['knowledge']==before['world_state']['knowledge']


def test_legacy_knowledge_migration_start_turn_save_reload_next_turn(tmp_path):
    from backend.repositories.preparation import Repository
    from devtools.narrative_test_world import load_fixture
    from test_narrative_test_world import ordinary_job
    repo=Repository(tmp_path/'legacy-knowledge.sqlite');sid=load_fixture(repo)['save'];snap=repo.get_snapshot(sid)
    for f in snap['world_state']['facts'].values(): f.pop('claim',None)
    for key,row in list(snap['world_state']['knowledge'].items()):
        snap['world_state']['knowledge'][key]={k:row[k] for k in ('actor_id','fact_id','status')}
    expected=deepcopy(snap['world_state']['knowledge'])
    with repo.connect() as conn:conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snap),sid))
    ordinary_job(repo,sid,'start');ordinary_job(repo,sid)
    repo=Repository(repo.path);ordinary_job(repo,sid)
    for key,row in expected.items():
        assert all(repo.get_snapshot(sid)['world_state']['knowledge'][key][k]==v for k,v in row.items())


def test_legacy_explicit_replacement_is_retrieved_when_only_old_assertion_matches():
    snap=initial();s=snap['world_state']
    for f in s['facts'].values():f['claim']=None
    p=acquisition(s,supersedes=['bank']);p['events'][0]['fact_ids'].append('bank')
    r=StateResolver(s,TEXT,'').resolve(p);snap['world_state']=r.state
    messages=build_context(snap,[],'bank_a','turn',32768,2000)
    block=next(m['content'] for m in messages if m['content'].startswith('Знания POV'))
    assert 'hospital' in block and 'bank' not in block


def test_malformed_optional_claim_keeps_fact_and_existing_identity_is_immutable():
    from backend.services.world_delta_errors import StructuralDeltaError
    s=initial()['world_state']
    p=raw(s,facts=[dict(id='new',text='Новый факт.',claim={'subject_id':[]},evidence=TEXT)])
    r=StateResolver(s,TEXT,'').resolve(p)
    assert r.state['facts']['new']['claim'] is None and r.warnings
    p=raw(s,facts=[dict(s['facts']['bank'],text='Изменённый текст.',evidence=TEXT)])
    with pytest.raises(StructuralDeltaError):StateResolver(s,TEXT,'').resolve(p)


def test_acquisition_and_projection_budgets_do_not_expand_with_npc_count():
    s=initial()['world_state'];s['knowledge']={}
    p=raw(s,events=[],knowledge_gained=[])
    for n in range(100):
        fid=f'f{n}';s['facts'][fid]=Fact(id=fid,text='topic',character_ids=['a','b']).model_dump()
        p['events'].append(dict(id=f'e{n}',text=TEXT,evidence=TEXT,witnesses=['a'],fact_ids=[fid],medium='observation'))
        p['knowledge_gained'].append(dict(actor_id='a',fact_id=fid,source_event_id=f'e{n}',evidence=TEXT))
    r=StateResolver(s,TEXT,'').resolve(p)
    assert len(r.history['knowledge_acquisitions'])==64
    assert any(w['code']=='knowledge_budget' for w in r.warnings)
    snap=initial();snap['world_state']=r.state
    context=build_context(snap,[],'topic','turn',32768,2000)
    assert context.selection['knowledge']['selected']<=48


def test_refuted_relationship_fact_cannot_authorize_social_projection():
    from backend.runtime_v3.models import ObjectiveRelation
    from backend.runtime_v3.kinship import visible_relations
    s=initial()['world_state']
    s['facts']['bank']['character_ids']=['a','b']
    s['objective_relations']['friend']=ObjectiveRelation(id='friend',kind='friend',source_id='a',target_id='b',fact_id='bank').model_dump()
    assert visible_relations(s,'a')
    r=StateResolver(s,TEXT,'').resolve(acquisition(s,'bank',status='refuted'))
    assert not visible_relations(r.state,'a')


def test_ordered_same_fact_updates_use_evolving_revisions_and_preserve_both_sources():
    s=initial()['world_state'];s['knowledge'].pop('a:bank')
    p=acquisition(s,'bank',status='suspected',expected_revision=0)
    p['events'][0]['order']=1
    p['events'].append(dict(p['events'][0],id='confirm',order=2))
    p['knowledge_gained'].append(dict(p['knowledge_gained'][0],source_event_id='confirm',status='known',expected_revision=1))
    r=StateResolver(s,TEXT,'').resolve(p)
    assert not r.warnings
    assert r.state['knowledge']['a:bank']['revision']==2
    first,second=r.history['knowledge_acquisitions']
    assert first['after']['status']=='suspected' and second['before']==first['after']
    assert second['after']['status']=='known' and first['source_event_id']!=second['source_event_id']


def test_new_belief_can_be_refuted_by_later_ordered_event_in_same_turn():
    s=initial()['world_state'];s['knowledge'].pop('a:bank')
    p=acquisition(s,'bank');p['events'][0]['order']=1
    p['events'].append(dict(p['events'][0],id='refutation',order=2))
    p['knowledge_gained'].append(dict(p['knowledge_gained'][0],source_event_id='refutation',status='refuted',expected_revision=1))
    r=StateResolver(s,TEXT,'').resolve(p)
    assert not r.warnings and r.state['knowledge']['a:bank']['status']=='refuted'
    assert len(r.history['knowledge_acquisitions'])==2
