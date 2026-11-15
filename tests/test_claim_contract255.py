"""Archived provider replies + labelled controls, never a claim of Live PASS."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator
from backend.runtime_v3.scene_steps import input_schema, validate, compile_scene
from backend.runtime_v3.scene_repair import SceneCandidate, repair_schema
from backend.services.structured_extraction import wire_schema
from backend.services.world_delta_errors import StructuralDeltaError
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.player_actions import resolver_options
from backend.repositories.preparation import Repository

pytestmark = pytest.mark.extraction_v6
SOURCE = Path(__file__).parent / 'fixtures/issue255/perceived-fact-live.json'


def original():
    return json.loads(SOURCE.read_text())


def prepare():
    d=original(); c=SceneCandidate(d['before'],d['narrative'],d['player_input'],d['turn_id'])
    with pytest.raises(StructuralDeltaError) as failure:c.parse(d['extraction'])
    rows=failure.value.diagnostics('extraction_repair')
    feedback=json.loads(c.feedback(rows,d['extraction']))
    return d,c,rows,feedback


def authored_patch(d, feedback):
    # Control only: wrap the original explicitly supplied assertion in its
    # canonical slot and copy its own value as text. Never change provider files.
    replacements=[]
    for step in json.loads(d['extraction'])['scene_steps']:
        if step['kind']!='information':continue
        item=deepcopy(step)
        for claim in item['claims']:
            assertion=claim['fact'];claim['fact']={'text':assertion['value'],'claim':assertion}
        replacements.append(item)
    return dict(candidate_hash=feedback['candidate_hash'],replacements=replacements,sections={},reason='Authored structural control, not a DeepSeek response.')


def test_original_reply_has_exact_independent_field_diagnostics_and_immutable_source():
    d,c,rows,f=prepare()
    assert hashlib.sha256(d['extraction'].encode()).hexdigest()==d['provenance']['requests'][0]['response_sha256']
    assert {(r['path'],r['step_id'],r['claim_index']) for r in rows if r['path'].endswith('.text')}=={
        ('scene_steps[2].claims[0].fact.text','step_45_03',0),
        ('scene_steps[4].claims[0].fact.text','step_45_05',0)}
    assert all(r['repair_options'] for r in rows)
    assert f['scope']['claim_indexes']=={'step_45_03':[0],'step_45_05':[0]}
    assert f['scope']['step_ids']==['step_45_03','step_45_05']
    assert f['candidate_hash']==json.loads(d['repair'])['candidate_hash']
    assert c.base==json.loads(d['extraction']) and c.raw is None
    assert original()==d


def test_original_repair_does_not_fix_claims_by_adding_unreferenced_facts():
    d,c,_,f=prepare()
    with pytest.raises(StructuralDeltaError,match='claim.fact_id'):c.parse(d['repair'])
    # Even with no unrelated top-level Facts, both original malformed claims fail.
    d,c,_,f=prepare();reply=json.loads(d['repair']);reply['sections']={}
    with pytest.raises(StructuralDeltaError) as error:c.parse(reply)
    assert {r['index'] for r in error.value.diagnostics('failed')}=={2,4}


def test_one_control_repairs_both_keeps_unchanged_steps_and_compiles_knowledge():
    d,c,_,f=prepare();reply=authored_patch(d,f)
    schema=wire_schema(repair_schema(input_schema(),json.dumps(f)))
    Draft202012Validator.check_schema(schema);Draft202012Validator(schema).validate(reply)
    raw=c.parse(reply)
    initial=json.loads(d['extraction'])
    for i in (0,1,3,5):assert raw.semantic_candidate['scene_steps'][i]==initial['scene_steps'][i]
    assert raw.semantic_candidate['choices']==initial['choices']
    # The real reply has another, input-dependent error: its two quotes add
    # closing/opening quotation marks not present at those input boundaries.
    # A structural repair must not silently rewrite this independent provenance.
    with pytest.raises(StructuralDeltaError) as failure:
        StateResolver(d['before'],d['narrative'],d['player_input'],turn_id=d['turn_id'],
            **resolver_options(d['before'],d['player_input'],contract_version=6)).resolve(raw)
    assert failure.value.code=='player_action_source_invalid'
    full=authored_input_control(raw.semantic_candidate,d)
    result=StateResolver(d['before'],d['narrative'],d['player_input'],turn_id=d['turn_id'],
        **resolver_options(d['before'],d['player_input'],contract_version=6)).resolve(full)
    acquired=result.history['knowledge_acquisitions']
    assert len(acquired)==2
    assert {a['actor_id'] for a in acquired}=={'char_alexey'}
    assert len(result.state['facts'])==len(d['before']['facts'])+2
    events={e['id']:e for e in result.history['events']}
    for a in acquired:
        assert a['fact_id'] in events[a['source_event_id']]['fact_ids']
        assert a['actor_id'] in events[a['source_event_id']]['witnesses']


@pytest.mark.parametrize('change',['independent_step','remove_claim','change_step_text','add_unlinked_fact'])
def test_claim_repair_cannot_erase_or_change_independent_outcomes(change):
    d,c,_,f=prepare();reply=authored_patch(d,f)
    if change=='independent_step':reply['replacements'].append(json.loads(d['extraction'])['scene_steps'][0])
    elif change=='remove_claim':reply['replacements'][0]['claims']=[]
    elif change=='change_step_text':reply['replacements'][0]['text']='Changed unrelated event meaning'
    else:reply['sections']['facts']=[dict(id='unlinked',text='Unrelated')]
    with pytest.raises(StructuralDeltaError) as failure:c.parse(reply)
    assert failure.value.code=='scene_repair_scope'


def info(claims):
    return dict(scene={'elapsed_minutes':1},scene_steps=[dict(id='tell',kind='information',source_actor_id='b',
        target_ids=['a'],text='Сказал.',medium='conversation',claims=claims)])


def claim(**kw):
    return dict(assertion='testimony',status='known',perceived_by=['a'],**kw)


def authored_input_control(full,d):
    full=deepcopy(full)
    for step in full['scene_steps']:
        if 'input_source' in step:
            quote=step['input_source']['quote'].strip('«»')
            assert quote in d['player_input']
            step['input_source']['quote']=quote
    return full


@pytest.mark.parametrize('value',[
    claim(fact={}),claim(fact={'text':''}),claim(fact={'text':'  \n '}),
    claim(),claim(fact={'text':'Факт'},fact_id='existing'),
    dict(claim(fact={'text':'Факт'}),perceived_by=['a','a']),
    dict(claim(fact={'text':'Факт'}),expected_revisions={'a':-1}),
    dict(claim(fact={'text':'Факт'}),assertion='rumor'),
    claim(fact={'text':'Факт','claim':{'subject_id':'a','predicate':'p','value':'x'*501}}),
])
def test_provider_and_local_schema_reject_same_hidden_claim_shapes(value):
    p=info([value]);schema=wire_schema(input_schema())
    assert list(Draft202012Validator(schema).iter_errors(p))
    with pytest.raises(StructuralDeltaError):validate(p)


def test_existing_fact_reference_creates_no_duplicate_and_multiple_claim_errors_are_addressed():
    from test_scene_steps255 import fixture
    from backend.runtime_v3.models import Fact
    state,_=fixture();state['facts']['f']=Fact(id='f',text='Известное утверждение.').model_dump()
    p=info([claim(fact_id='f')]);raw=compile_scene(p,state,'Проза',1)
    assert not raw.records['facts']
    result=StateResolver(state,'Проза','Слушаю.',**resolver_options(state,'Слушаю.',contract_version=6)).resolve(raw)
    assert len(result.state['facts'])==1 and len(result.history['knowledge_acquisitions'])==1
    p=info([claim(fact={}),claim(fact_id='f'),claim(fact={})])
    c=SceneCandidate(state,'Проза','Слушаю.',1)
    with pytest.raises(StructuralDeltaError) as failure:c.parse(p)
    rows=failure.value.diagnostics('repair');assert {r['claim_index'] for r in rows}=={0,2}
    f=json.loads(c.feedback(rows,p));step=deepcopy(p['scene_steps'][0]);step['claims'][0]['fact']['text']='Первое';step['claims'][2]['fact']['text']='Второе'
    reply=dict(candidate_hash=f['candidate_hash'],replacements=[step],sections={},reason='Labelled control')
    step['claims'][1]['fact_id']='other'
    with pytest.raises(StructuralDeltaError,match='claim'):c.parse(reply)


@pytest.mark.parametrize('row',[
    dict(kind='event_elapsed',assertion='narrator',evidence='текст'),
    dict(kind='current_calendar',event_id='f',date='2026-01-01',assertion='narrator',evidence='текст'),
])
def test_chronology_structural_basis_is_in_provider_schema(row):
    p=dict(scene={},scene_steps=[],chronology_claims=[row])
    assert list(Draft202012Validator(wire_schema(input_schema())).iter_errors(p))
    with pytest.raises(StructuralDeltaError):validate(p)


def test_repair_schema_rejects_out_of_scope_step_ids():
    d,_,_,f=prepare();reply=authored_patch(d,f);reply['replacements'][0]['id']='not-selected'
    schema=wire_schema(repair_schema(input_schema(),json.dumps(f)))
    assert list(Draft202012Validator(schema).iter_errors(reply))


def test_production_retry_commit_reload_preserves_narrative_and_provenance(tmp_path):
    from test_integrated_repair247 import seed,execute,history,CONFIG
    d=original();repo=Repository(tmp_path/'facts.sqlite')
    with patch('backend.runtime_v3.player_actions.EXTRACTION_VERSION',5):sid=seed(repo,d)['save']
    # Test-only import: do not retain seed's unrelated campaign/card identities.
    imported=repo.get_snapshot(sid)
    imported['campaign']={}
    imported['character_cards']=[dict(id=cid,name=c['display_name'],fields={}) for cid,c in d['before']['characters'].items()]
    with repo.connect() as db:db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(imported),sid))
    original_state=repo.get_snapshot(sid)['world_state']
    old_acquisitions=history(repo,sid)['knowledge_acquisitions']
    first=json.loads(d['extraction'])
    # First saved Narrative fails on real provider content; the actual recorded
    # repair hash belongs to its original job, so return the same malformed first
    # body as a rejection control here. No candidate is accepted by this attempt.
    job,_=execute(repo,sid,d,[first,first],legacy=False,contract_version=6,config=dict(CONFIG,context_length=131072,update_tokens=8192))
    assert job['status']=='error' and repo.get_snapshot(sid)['world_state']==original_state
    assert job['narrative_complete'],job['error']
    before_context=job['context_json'];before=job['before_json'];narrative=job['narrative']
    c=SceneCandidate(d['before'],d['narrative'],d['player_input'],d['turn_id'])
    with pytest.raises(StructuralDeltaError) as failure:c.parse(first)
    reply=authored_patch(d,json.loads(c.feedback(failure.value.diagnostics('repair'),first)))
    full=deepcopy(first)
    edits={s['id']:s for s in reply['replacements']};full['scene_steps']=[edits.get(s['id'],s) for s in full['scene_steps']]
    full=authored_input_control(full,d)
    saved,calls=execute(repo,sid,d,[full],retry=job['id'],legacy=False,config=dict(CONFIG,context_length=131072,update_tokens=8192))
    assert saved['status']=='saved',saved['error']
    assert len(calls)==1 and calls[0].get('response_format')
    assert saved['narrative']==narrative and saved['context_json']==before_context and saved['before_json']==before
    after=repo.get_snapshot(sid);fresh=Repository(repo.path);assert fresh.get_snapshot(sid)==after
    all_acquired=history(fresh,sid)['knowledge_acquisitions']
    assert all_acquired[:len(old_acquisitions)]==old_acquisitions
    acquired=all_acquired[len(old_acquisitions):];assert len(acquired)==2
    for a in acquired:
        k=after['world_state']['knowledge'][a['actor_id']+':'+a['fact_id']]
        assert k['source_event_id']==a['source_event_id']
    fresh.rollback_last(sid);assert fresh.get_snapshot(sid)['world_state']==original_state


def test_domain_structural_shapes_and_valid_partial_forms():
    schema=wire_schema(input_schema());v=Draft202012Validator(schema)
    name=dict(id='name',pregnancy_id='p',child_id='c',source_event_id='e',status='proposed',decision_actor_ids=['b'])
    item=dict(item_id='i',operation='introduce',name='Камера',kind='камера',updates={'holder_id':'a'},expected_revision=0,
        assertion='completed_outcome',significance='continuity_required',transition='established',source_event_id='e',fact_id='f')
    appearance=dict(actor_id='a',item_id='hair',operation='remove',category='presentation',kind='hairstyle',expected_revision=0,
        source_event_id='e',fact_id='f',assertion='established_visual_outcome',transition='voluntary')
    cases=[('naming_decisions',dict(name,components={}),dict(name,delegated_to='b')),
        ('naming_decisions',dict(name,components={'given_name':' '}),dict(name,components={'given_name':'Анна'})),
        ('possession_deltas',dict(item,updates={}),item),
        ('possession_deltas',dict(item,name=None),item),
        ('appearance_deltas',dict(appearance,kind='scar'),appearance),
        ('appearance_deltas',dict(appearance,text='Новая причёска'),appearance),
        ('possession_deltas',dict(item,updates={'status':None}),dict(item,updates={'status':'available'})),
        ('possession_deltas',dict(item,operation='relocate',name=None,kind=None,updates={'holder_id':'b'}),
            dict(item,operation='relocate',name=None,kind=None,updates={'location_id':None})),
        ('appearance_deltas',dict(appearance,operation='update',text=' '),dict(appearance,operation='update',text='Короткая стрижка')),
        ('appearance_deltas',dict(appearance,condition_id='c'),appearance)]
    for section,bad,good in cases:
        p=dict(scene={},scene_steps=[],**{section:[bad]})
        assert list(v.iter_errors(p)),section
        with pytest.raises(StructuralDeltaError):validate(p)
        p[section]=[good];v.validate(p);validate(p)
    # Cancellation target depends on whether this canonical decision already
    # exists (idempotent replay); do not impose a new-record requirement globally.
    v.validate(dict(scene={},scene_steps=[],naming_decisions=[dict(name,status='cancelled')]))
    # Updates that depend on an existing canonical entity remain partial.
    v.validate(dict(scene={},scene_steps=[],role_changes=[dict(id='old-role',assertion='established',status='closed')]))


def test_provider_transport_uses_the_projected_fact_and_repair_constraints():
    from types import SimpleNamespace
    from llm import chat_stream
    from test_structured_extraction255 import events
    class Stream(list):
        def close(self):pass
    schema=wire_schema(input_schema());d,_,_,f=prepare();reply=authored_patch(d,f)
    for sent in (schema,wire_schema(repair_schema(input_schema(),json.dumps(f)))):
        with patch('llm.OpenAI') as factory:
            factory.return_value.responses.create.return_value=Stream(events())
            list(chat_stream(model='deepseek-flash',messages=[{'role':'user','content':'input'}],provider='deepseek',
                api_key='offline-control',thinking='off',structured_schema=sent,extraction_transport='responses_json_schema'))
            actual=factory.return_value.responses.create.call_args.kwargs['text']['format']['schema']
            assert actual==sent
            Draft202012Validator.check_schema(actual)
        if 'replacements' in actual['properties']:
            Draft202012Validator(actual).validate(reply)
            bad=deepcopy(reply);bad['replacements'][0]['claims'][0]['fact'].pop('text')
        else:bad=json.loads(d['extraction'])
        assert list(Draft202012Validator(actual).iter_errors(bad))


def test_production_one_bounded_repair_of_two_claims(tmp_path):
    import engine
    from test_integrated_repair247 import seed,CONFIG
    d=original();repo=Repository(tmp_path/'one-repair.sqlite')
    with patch('backend.runtime_v3.player_actions.EXTRACTION_VERSION',5):sid=seed(repo,d)['save']
    snap=repo.get_snapshot(sid);snap['campaign']={};snap['character_cards']=[dict(id=cid,name=c['display_name'],fields={}) for cid,c in d['before']['characters'].items()]
    with repo.connect() as db:db.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snap),sid))
    # Authored control fixes the separately documented input quote error before
    # testing one automatic repair of the TWO original structural Fact errors.
    first=authored_input_control(json.loads(d['extraction']),d)
    calls=[];narratives=[]
    def stream(**kw):
        rules=kw['messages'][0]['content']
        if rules.startswith('Select at most ONE optional grounded autonomous remote action.'):
            yield '{"action":null}';return
        if not kw.get('response_format'):
            narratives.append(True);yield d['narrative'];return
        calls.append(kw)
        if len(calls)==1:yield json.dumps(first,ensure_ascii=False);return
        assert len(calls)==2
        start=rules.index('{"repair_mode":"targeted"')
        feedback=json.JSONDecoder().raw_decode(rules[start:])[0]
        assert feedback['scope']['claim_indexes']=={'step_45_03':[0],'step_45_05':[0]}
        yield json.dumps(authored_patch(d,feedback),ensure_ascii=False)
    jid=repo.begin_job(sid,d['player_input'],'turn',dict(CONFIG,context_length=131072,update_tokens=8192))
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,jid,engine.Worker())
    job=repo.get_job(jid);assert job['status']=='saved',job['error']
    assert len(calls)==2 and len(narratives)==1 and job['narrative']==d['narrative']
    assert [r['stage'] for r in repo.request_log(job_id=jid) if r['stage'].startswith('extraction')]==['extraction_repair','extraction']
    assert Repository(repo.path).get_snapshot(sid)==repo.get_snapshot(sid)


@pytest.mark.parametrize('malformed', ['null_claim', 'nonstring_fact_id', 'null_facts', 'null_fact'])
def test_malformed_claim_repair_has_structural_diagnostics_not_parser_exception(malformed):
    d,c,_,f=prepare();reply=authored_patch(d,f)
    if malformed=='null_claim':reply['replacements'][0]['claims'][0]=None
    elif malformed=='nonstring_fact_id':reply['replacements'][0]['claims'][0]['fact_id']=[]
    elif malformed=='null_facts':reply['sections']['facts']=None
    else:reply['sections']['facts']=[None]
    with pytest.raises(StructuralDeltaError):c.parse(reply)


def test_each_missing_required_field_keeps_its_own_reason_without_cross_product():
    p=info([claim(fact={'text':'Утверждение','claim':{}})])
    with pytest.raises(StructuralDeltaError) as failure:validate(p)
    rows=[r for r in failure.value.diagnostics('repair') if 'required property' in r['repair_reason']]
    assert len(rows)==3
    for key in ('subject_id','predicate','value'):
        assert any(r['path']==f'scene_steps[0].claims[0].fact.claim.{key}' and r['repair_reason']==f"'{key}' is a required property" for r in rows)


def test_schema_error_does_not_hide_independent_claim_validator_error():
    p=info([claim(fact={}),dict(claim(fact={'text':'Другой факт'}),expected_revisions={'not-a-perceiver':0})])
    with pytest.raises(StructuralDeltaError) as failure:validate(p)
    rows=failure.value.diagnostics('repair')
    assert {r['claim_index'] for r in rows}=={0,1}
    assert any(r['path']=='scene_steps[0].claims[1]' and 'Invalid perception revision' in r['repair_reason'] for r in rows)
    from test_scene_steps255 import fixture
    state,_=fixture();c=SceneCandidate(state,'Проза','Слушаю.',1)
    with pytest.raises(StructuralDeltaError) as failure:c.parse(p)
    f=json.loads(c.feedback(failure.value.diagnostics('repair'),p))
    assert f['scope']['claim_indexes']=={'tell':[0,1]}
    step=deepcopy(p['scene_steps'][0]);step['claims'][0]['fact']['text']='Первый факт'
    step['claims'][1]['expected_revisions']={}
    raw=c.parse(dict(candidate_hash=f['candidate_hash'],replacements=[step],sections={},reason='Authored mixed-error control'))
    assert len(raw.records['facts'])==2
