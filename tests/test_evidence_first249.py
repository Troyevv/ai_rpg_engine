"""Evidence-first contract: controlled transport; no model accuracy claims."""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator

from backend.repositories.preparation import Repository
from backend.runtime_v3.context import build_context
from backend.runtime_v3.player_actions import PlayerAgencyReview, PlayerAction
from backend.runtime_v3.raw import prompt_schema
from backend.runtime_v3.resolver import StateResolver
from backend.services.world_delta_errors import StructuralDeltaError
from test_extraction_semantics248 import final_live
from test_integrated_repair247 import seed, execute, history, CONFIG


def control(data, classification='authorized', reference=True):
    """Explicit authored classification over an unchanged archived response copy."""
    raw = json.loads(data['responses'][-1]['response_text'])
    review = raw['player_agency']
    for action in review['actions']:
        action.setdefault('target_mode', 'interaction')
    review['narrative_audit'] = [dict(narrative_evidence='Кирилл продолжает заниматься фотографиями.',
        classification=classification, player_action_id=review['actions'][0]['id'] if reference else None)]
    return raw


def resolve(data, raw):
    return StateResolver(data['before'], data['narrative'], data['player_input'],
                         agency_audit_required=True).resolve(raw)


@pytest.mark.parametrize('classification,reference', [('authorized',True),('execution_detail',True),
    ('involuntary',False),('npc_interpretation',False)])
def test_typed_permitted_findings_do_not_block_runtime(classification, reference):
    data=final_live('phone');raw=control(data,classification,reference)
    # Classification is scripted, not inferred by Python from the real tea scene.
    assert resolve(data,raw).state


@pytest.mark.parametrize('classification', ['unauthorized_choice','uncertain'])
def test_preserved_cannot_override_negative_audit_even_outside_events(tmp_path, classification):
    data=final_live('phone');raw=control(data,classification,False)
    raw['player_agency']['narrative_audit'][0]['narrative_evidence']='Кирилл молча отказался от чая.'
    repo=Repository(tmp_path/'game.sqlite');sid=seed(repo,data)['save']
    before,hist=repo.get_snapshot(sid),history(repo,sid)
    job,calls=execute(repo,sid,data,[raw],legacy=False)
    if classification == 'uncertain':
        assert job['status']=='saved' and len(calls)==2
        assert any(w['code']=='player_agency_audit_advisory' for w in json.loads(job['warnings_json']))
        return
    assert job['status']=='error' and len(calls)==2
    diagnostics=json.loads(job['repair_diagnostics_json'])
    assert diagnostics[0]['code']=='narrative_agency_conflict'
    assert diagnostics[0]['reason']=='audit_status_conflict'
    assert repo.public_job(job)['narrative_reauthor_required']
    with pytest.raises(ValueError,match='противоречит'):
        repo.retry_job(job['id'], CONFIG)
    assert Repository(repo.path).get_snapshot(sid)==before and history(repo,sid)==hist
    repo.abandon_job(sid,job['id'],repo.get_save(sid)['revision'],job['attempt_epoch'])
    assert repo.get_snapshot(sid)==before


@pytest.mark.parametrize('field,code', [('audit','player_agency_audit_missing'),
    ('target_mode','player_action_target_mode_missing'),('reference','player_agency_audit_reference_invalid'),
    ('quote','player_action_source_invalid')])
def test_missing_or_bad_new_fields_are_repairable_and_cannot_choose_legacy(tmp_path,field,code):
    data=final_live('phone');good=control(data);bad=deepcopy(good)
    if field=='audit':bad['player_agency'].pop('narrative_audit')
    elif field=='target_mode':bad['player_agency']['actions'][0].pop('target_mode')
    elif field=='reference':bad['player_agency']['narrative_audit'][0]['player_action_id']='other-input'
    else:bad['player_agency']['actions'][0]['player_evidence']='NPC biography permits this'
    bad['metadata']={'_extraction_contract':1}
    with pytest.raises(StructuralDeltaError) as exc:resolve(data,bad)
    assert exc.value.code==code
    repo=Repository(tmp_path/'game.sqlite');sid=seed(repo,data)['save']
    # Caller configuration cannot downgrade a newly created producer either.
    job,calls=execute(repo,sid,data,[bad,good],legacy=False,config=dict(CONFIG,_extraction_contract=1))
    assert json.loads(job['config_json'])['_extraction_contract']==4
    # This archived action is unreferenced bookkeeping; it cannot authorize a domain.
    assert job['status']=='saved' and len(calls)==2,job['error']
    assert not json.loads(job['repair_diagnostics_json'])


def test_empty_audit_is_not_an_independent_semantic_proof():
    data=final_live('phone');raw=control(data);raw['player_agency']['narrative_audit']=[]
    # Explicit limitation: the same model may omit/misclassify a decision.
    assert resolve(data,raw).state


def test_legacy_raw_stays_readable_without_defaults_becoming_new_authorization():
    data=final_live('phone');raw=json.loads(data['responses'][0]['response_text'])
    raw['player_agency']['actions'][0].pop('target_mode')
    assert PlayerAgencyReview.model_validate(raw['player_agency']).actions[0].target_mode=='interaction'
    assert StateResolver(data['before'],data['narrative'],data['player_input']).resolve(raw).state
    with pytest.raises(StructuralDeltaError,match='narrative_audit'):resolve(data,raw)


def test_new_job_retry_regeneration_and_siblings_keep_contract_and_provenance(tmp_path):
    data=final_live('phone');raw=control(data)
    # This test proves persistence only, not correct classification of the original prose.
    repo=Repository(tmp_path/'game.sqlite');sid=seed(repo,data)['save']
    before,hist=repo.get_snapshot(sid),history(repo,sid)
    bad=deepcopy(raw);bad['final_scene']['location_id']='unknown'
    failed,calls=execute(repo,sid,data,[bad,bad],legacy=False)
    assert failed['status']=='error' and len(calls)==3
    repo.retry_job(failed['id'],dict(CONFIG,_extraction_contract=1))
    assert json.loads(repo.get_job(failed['id'])['config_json'])['_extraction_contract']==4
    # Already reset to extracting: run using the recorded job without retrying again.
    import engine
    def stream(**kwargs):yield json.dumps(raw,ensure_ascii=False)
    with patch('engine.find_loaded_model',return_value={'config':{}}),patch('engine.chat_stream',side_effect=stream):
        engine.run_job(repo.path,failed['id'],engine.Worker(epoch=repo.get_job(failed['id'])['attempt_epoch']))
    saved=repo.get_job(failed['id']);assert saved['status']=='saved',saved['error']
    after=repo.get_snapshot(sid);turn=repo.list_turns(sid)[-1]
    sibling,_=execute(repo,sid,data,[raw],kind='regenerate',legacy=False)
    assert sibling['status']=='saved',sibling['error']
    assert json.loads(sibling['config_json'])['_extraction_contract']==4
    assert sibling['context_json']==saved['context_json']
    assert len(repo.variants(turn['node_id']))==2
    repo.select_variant(sid,turn['id'],turn['active_variant_id'],repo.get_save(sid)['revision'])
    assert Repository(repo.path).get_snapshot(sid)==after
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==before and history(repo,sid)==hist


def test_legacy_variant_regeneration_retains_recorded_version(tmp_path):
    data=final_live('phone');raw=json.loads(data['responses'][0]['response_text'])
    repo=Repository(tmp_path/'game.sqlite');sid=seed(repo,data)['save']
    first,_=execute(repo,sid,data,[raw])
    assert first['status']=='saved'
    sibling,_=execute(repo,sid,data,[raw],kind='regenerate',legacy=False)
    assert sibling['status']=='saved',sibling['error']
    assert json.loads(sibling['config_json'])['_extraction_contract']==1
    assert sibling['context_json']==first['context_json']


def test_schema_and_assembled_requests_require_audit_only_for_current_producer(tmp_path):
    data=final_live('phone');raw=control(data)
    repo=Repository(tmp_path/'game.sqlite');sid=seed(repo,data)['save'];snap=repo.get_snapshot(sid)
    for version in (1,2):
        messages=build_context(snap,[],data['player_input'],'turn',65536,8192,
            extraction_text=data['narrative'],extraction_contract=version)
        schema=next(json.loads(m['content'].split('\n',1)[1]) for m in messages if m['content'].startswith('JSON Schema\n'))
        Draft202012Validator.check_schema(schema)
        assert ('narrative_audit' in schema['properties']['player_agency']['required'])==(version==2)
        assert data['narrative'] in json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('completed_narrative\n')))
    Draft202012Validator(prompt_schema(player_agency_required=True)).validate(raw)
    narrative=build_context(snap,[],data['player_input'],'turn',65536,8192)
    text='\n'.join(m['content'] for m in narrative)
    assert 'An unanswered NPC question stays open' in text
    assert 'Keep NPCs and the environment moving' in text

from test_api import api
from test_event_presence import crisis, NINA
from test_player_action_targets import claim, payload, play, saved_events, MARINA, GOOD_INPUT
from test_player_action_group_completion import group, QUOTE, TEXT


@pytest.mark.parametrize('split', [True,False])
def test_quote_inherited_once_for_group_events_and_persisted(tmp_path,crisis,split):
    _,repo,sid=crisis;before=repo.get_snapshot(sid)
    raw=group(before['world_state'],split=split)
    for event in raw['events']:event.pop('player_evidence')
    original=deepcopy(raw)
    Draft202012Validator(prompt_schema(player_agency_required=True)).validate(raw)
    job,calls=play(crisis,[raw],QUOTE,TEXT)
    assert job['status']=='saved' and len(calls)==2,job.get('error')
    events=saved_events(repo,sid)[-len(raw['events']):]
    assert all(e['player_evidence']==QUOTE and e['player_action']['player_evidence']==QUOTE for e in events)
    assert [e['target_ids'] for e in events]==[e['target_ids'] for e in raw['events']]
    assert raw==original  # immutable provider payload
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==before


@pytest.mark.parametrize('mutation,expected', [('conflict','action_evidence_mismatch'),
    ('null','missing_player_evidence'),('unknown','unknown_player_action_id'),
    ('actor','wrong_actor'),('targets','target_ids_mismatch')])
def test_compact_events_do_not_hide_invalid_provenance(crisis,mutation,expected):
    _,repo,sid=crisis;s=repo.get_snapshot(sid)['world_state']
    raw=payload(s,[claim([MARINA],quote=GOOD_INPUT)],completed=False)
    event=raw['events'][0];event.pop('player_evidence')
    if mutation=='conflict':event['player_evidence']='Чужой ввод'
    elif mutation=='null':event['player_evidence']=None
    elif mutation=='unknown':event['player_action_id']='unknown'
    elif mutation=='actor':event['actor_id']=MARINA
    else:event['target_ids']=['qa_vera']
    with pytest.raises(StructuralDeltaError) as exc:
        StateResolver(s,'Нина спрашивает Марину.',GOOD_INPUT,agency_audit_required=True).resolve(raw)
    assert expected in {d.get('reason') for d in exc.value.diagnostics('test')}


def test_compact_two_actions_do_not_infer_targets_or_convert_npc_reply(crisis):
    _,repo,sid=crisis;s=repo.get_snapshot(sid)['world_state']
    first='Спрашиваю Марину о Кирилле.';second='Прошу Асю принести книгу.'
    raw=payload(s,[claim([MARINA],quote=first),claim(['qa_asya'],quote=second,id='second')],completed=False)
    for event in raw['events']:event.pop('player_evidence')
    raw['events'].append(dict(id='reply',text='Марина отвечает.',actor_id=MARINA,participants=[MARINA,NINA],witnesses=[NINA],medium='conversation'))
    result=StateResolver(s,'Нина задаёт вопросы. Марина отвечает.',first+' '+second,agency_audit_required=True).resolve(raw)
    assert [e['player_evidence'] for e in result.history['events'][:2]]==[first,second]
    assert 'player_action' not in result.history['events'][2]
    # Explicit quote from another action must not be overwritten by normalization.
    raw['events'][1]['player_evidence']=first
    with pytest.raises(StructuralDeltaError) as exc:
        StateResolver(s,'Нина задаёт вопросы.',first+' '+second,agency_audit_required=True).resolve(raw)
    assert 'other_action_evidence' in {d.get('reason') for d in exc.value.diagnostics('test')}


def test_compact_event_cannot_create_delivery_or_event_from_intent(crisis):
    _,repo,sid=crisis;s=repo.get_snapshot(sid)['world_state']
    raw=payload(s,[claim([MARINA],quote=GOOD_INPUT)]);raw['events']=[]
    with pytest.raises(StructuralDeltaError) as exc:
        StateResolver(s,'Нина спрашивает Марину.',GOOD_INPUT,agency_audit_required=True).resolve(raw)
    assert exc.value.code=='player_action_completion_invalid'
    raw['player_agency']['actions'][0].update(outcome='deferred',narrative_target_ids=[])
    result=StateResolver(s,'Нина ждёт.',GOOD_INPUT,agency_audit_required=True).resolve(raw)
    assert not result.history['events']


def test_confirmed_prose_violation_cannot_be_laundered_by_repairing_other_fields():
    data=final_live('phone');raw=control(data,'unauthorized_choice',False)
    raw['player_agency']['actions'][0]['player_evidence']='Wrong source'
    with pytest.raises(StructuralDeltaError) as exc:resolve(data,raw)
    assert exc.value.code=='narrative_agency_conflict' and not exc.value.repairable


def test_prompt_examples_are_complete_typed_audit_items():
    from backend.runtime_v3.player_actions import EXTRACTION_CONTRACT, NarrativeAgencyItem
    examples=[json.loads(line) for line in EXTRACTION_CONTRACT.splitlines() if line.startswith('{')]
    assert len(examples)==2
    for example in examples:NarrativeAgencyItem.model_validate(example)
    assert examples[0]['classification']=='execution_detail' and examples[0]['player_action_id']=='a'
    assert examples[1]['classification']=='unauthorized_choice' and examples[1]['player_action_id'] is None


@pytest.mark.parametrize('case,expected', [('knowledge',4),('family',10)])
def test_current_producer_retains_real_knowledge_birth_provenance(tmp_path,case,expected):
    from test_live248_recovery import live, control as corrected
    data=live(case);raw=corrected(data)
    # Existing human-reviewed domain control + explicit new protocol annotations.
    for action in raw['player_agency']['actions']:
        action.setdefault('target_mode','interaction')
    raw['player_agency']['narrative_audit']=[]
    if case=='family':
        raw['player_agency']['narrative_audit']=[dict(
            narrative_evidence='Рука её сжимает пальцы Кирилла так, что чувствуется каждая косточка.',
            classification='involuntary',player_action_id=None)]
    for event in raw['events']:
        if event.get('player_action_id'):event.pop('player_evidence',None)
    repo=Repository(tmp_path/'game.sqlite');sid=seed(repo,data)['save']
    before,hist=repo.get_snapshot(sid),history(repo,sid)
    job,calls=execute(repo,sid,data,[raw],legacy=False)
    assert job['status']=='saved' and len(calls)==2,job['error']
    out=history(Repository(repo.path),sid)
    gains=out['knowledge_acquisitions'][len(hist['knowledge_acquisitions']):]
    assert len(gains)==expected
    for acquisition in gains:
        event=next(e for e in out['events'] if e['id']==acquisition['source_event_id'])
        assert acquisition['actor_id'] in event['witnesses'] and acquisition['fact_id'] in event['fact_ids']
    if case=='family':
        assert {k['actor_id'] for k in gains}=={'qa_kirill','qa_vera'}
        assert raw['births'][0]['sex_observations'][0]['source_actor_id'] is None
    else:
        assert {k['actor_id'] for k in gains}=={'qa_kirill','qa_timur'}
        player=next(e for e in out['events'] if e.get('player_action'))
        assert player['player_evidence']==raw['player_agency']['actions'][0]['player_evidence']
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==before and history(repo,sid)==hist
