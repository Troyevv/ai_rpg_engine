"""Partial promotions retain canonical consequences and snapshot lineage."""
import json
from copy import deepcopy
from unittest.mock import patch
import pytest
import engine
from test_engine import db, CONFIG
from test_runtime_v3_engine import run, raw_for
from backend.services.npc_review import edit, card_fields, generate, review_projection
from backend.services.world import CARD_FIELDS
from backend.runtime_v3.raw import RawTurnResult, extraction_schema
from backend.runtime_v3.models import assert_world_state_v3_invariants
from backend.services.world_delta_errors import StructuralDeltaError


def promoted(snapshot, fields=None, cid='new_npc'):
    raw=raw_for(snapshot)
    actor=snapshot['world_state']['camera']['controlled_actor_id']
    raw['promotions']=[dict(id=cid,name='Лада',fields=fields or {},evidence='Лада пришла.')]
    raw['final_scene']['present_character_ids']=[*raw['final_scene']['present_character_ids'],cid]
    raw['events']=[dict(id='meeting',text='Лада рассказала о мастерской.',participants=[actor,cid],witnesses=[actor,cid],fact_ids=['workshop'],medium='conversation',evidence='Рассказала.')]
    raw['facts']=[dict(id='workshop',text='Мастерская открыта.',character_ids=[cid],evidence='Рассказала.')]
    raw['knowledge_gained']=[dict(actor_id=actor,fact_id='workshop',source_event_id='meeting',evidence='Рассказала.')]
    raw['character_changes']=[dict(id=cid,situation='Встретилась с героем',obligations=['Показать мастерскую'],evidence='Договорились.')]
    raw['relationship_changes']=[dict(source_id=actor,target_id=cid,context='Познакомились.',dimensions={'trust':5},player_assertion='explicit_directed_feelings',player_evidence='Я доверяю Ладе.',evidence='Познакомились.')]
    return raw


def start(repo,sid,fields=None):
    job=repo.begin_job(sid,'Я доверяю Ладе.','start',CONFIG)
    run(repo,job,promoted(repo.get_snapshot(sid),fields))
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    return job


def command(repo,sid,action='save',fields=None,operation='review-operation',**kw):
    record=repo.get_snapshot(sid)['pending_reviews']['new_npc']
    return dict(revision=repo.get_save(sid)['revision'],review_revision=record['revision'],operation_id=operation,
        fields=record['card']['fields'] if fields is None else fields,action=action,**kw)


@pytest.mark.parametrize('fields',[{}, {'Возраст':'27'}, dict.fromkeys(CARD_FIELDS,''),dict.fromkeys(CARD_FIELDS,'Описание')])
def test_partial_full_commit_and_reload(db,fields):
    repo,_,sid=db;start(repo,sid,fields)
    from storage import Storage
    repo=Storage(repo.path);snapshot=repo.get_snapshot(sid);state=snapshot['world_state']
    assert 'new_npc' in state['camera']['present_character_ids']
    assert state['characters']['new_npc']['situation']=='Встретилась с героем'
    assert state['characters']['new_npc']['obligations']
    actor=state['camera']['controlled_actor_id']
    assert state['knowledge'][actor+':workshop']['status']=='known'
    assert state['relationships'][actor+':new_npc']['context']=='Познакомились.'
    assert len(json.loads(repo.list_turns(sid)[0]['choices_json']))==6
    card=next(c for c in snapshot['character_cards'] if c['id']=='new_npc')
    assert not any(card['fields'].values())
    record=snapshot['pending_reviews']['new_npc']
    assert record['card']['fields']==card_fields(fields)
    assert record['status']=='pending_review'
    assert_world_state_v3_invariants(state)
    # A later ordinary turn uses the identity without approving its biography.
    job=repo.begin_job(sid,'Продолжаю разговор','turn',CONFIG);run(repo,job,raw_for(snapshot))
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    assert repo.get_snapshot(sid)['pending_reviews']==snapshot['pending_reviews']


@pytest.mark.parametrize('damage',[{'evidence':None},{'fields':{'Возраст':4}},{'fields':[]},{'id':''},{'name':' '},{'fields':{'unknown':'x'}}])
def test_structural_errors_are_not_partial_cards(db,damage):
    repo,_,sid=db;raw=promoted(repo.get_snapshot(sid));raw['promotions'][0].update(damage)
    with pytest.raises(StructuralDeltaError):RawTurnResult.parse(raw)


def test_confirm_concurrency_idempotence_preserves_state(db):
    repo,_,sid=db;start(repo,sid)
    with pytest.raises(ValueError):edit(repo,sid,'new_npc',**command(repo,sid,'confirm'))
    stale=command(repo,sid)
    fields=dict.fromkeys(CARD_FIELDS,'Описание');fields['Характер']='Самостоятельная'
    edit(repo,sid,'new_npc',**command(repo,sid,'defer',fields,proposals={'Биография':'Предложение'}))
    assert repo.get_snapshot(sid)['pending_reviews']['new_npc']['proposals']['Биография']=='Предложение'
    with pytest.raises(ValueError):edit(repo,sid,'new_npc',**stale)
    before=repo.get_snapshot(sid);cmd=command(repo,sid,'confirm',operation='confirm-operation')
    edit(repo,sid,'new_npc',**cmd);after=repo.get_snapshot(sid)
    edit(repo,sid,'new_npc',**cmd);assert repo.get_snapshot(sid)==after
    assert len([c for c in after['character_cards'] if c['id']=='new_npc'])==1
    assert after['world_state']['knowledge']==before['world_state']['knowledge']
    assert after['world_state']['relationships']==before['world_state']['relationships']
    assert after['world_state']['characters']['new_npc']['obligations']==before['world_state']['characters']['new_npc']['obligations']
    from backend.runtime_v3.selectors import ui_view
    card=next(c for c in ui_view(after)['characters'] if c['id']=='new_npc')
    assert card['fields']['Характер']=='Самостоятельная'
    assert after['pending_reviews']['new_npc']['status']=='confirmed'


def test_retry_regenerate_variants_and_rollback(db):
    repo,_,sid=db;before=repo.get_snapshot(sid)
    raw=promoted(before);bad=deepcopy(raw);bad['final_scene']['present_character_ids'].append('missing')
    job=repo.begin_job(sid,'Я доверяю Ладе.','start',CONFIG);run(repo,job,bad)
    assert repo.get_job(job)['status']=='error'
    assert repo.get_snapshot(sid)==before
    repo.retry_job(job,CONFIG);run(repo,job,raw)
    assert repo.get_job(job)['status']=='saved'
    first=repo.list_turns(sid)[0];after=repo.get_snapshot(sid)
    # Re-running publication of an already saved job cannot duplicate its identity.
    run(repo,job,raw);assert repo.get_snapshot(sid)==after
    job=repo.begin_job(sid,'','regenerate',CONFIG);run(repo,job,raw_for(before))
    assert repo.get_job(job)['status']=='saved'
    assert not repo.get_snapshot(sid).get('pending_reviews')
    assert 'new_npc' not in repo.get_snapshot(sid)['world_state']['characters']
    repo.select_variant(sid,first['id'],first['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==after
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)==before


def test_draft_not_in_other_actor_projection_and_old_save(db):
    repo,_,sid=db;before=repo.get_snapshot(sid)
    assert review_projection(before)['records']==[]
    start(repo,sid);snapshot=repo.get_snapshot(sid)
    assert len(review_projection(snapshot)['records'])==1
    snapshot['world_state']['camera']['controlled_actor_id']='new_npc'
    assert review_projection(snapshot)['records']==[]


def test_single_field_generation_is_read_only(db):
    repo,_,sid=db;start(repo,sid);before=repo.get_snapshot(sid)
    record=before['pending_reviews']['new_npc']
    with patch('llm.chat_stream',return_value=iter(['{"value":"Новая биография"}'])):
        result=generate(repo,sid,'new_npc',field='Биография',revision=repo.get_save(sid)['revision'],review_revision=record['revision'],config=dict(CONFIG,provider="compatible"),api_key=None)
    assert result['value']=='Новая биография'
    assert repo.get_snapshot(sid)==before
    with patch('llm.chat_stream',return_value=iter(['{"value":{},"Характер":"подмена"}'])):
        with pytest.raises(ValueError):generate(repo,sid,'new_npc',field='Биография',revision=repo.get_save(sid)['revision'],review_revision=0,config=dict(CONFIG,provider="compatible"),api_key=None)
    assert repo.get_snapshot(sid)==before


@pytest.mark.parametrize('sex',['male','female',None,'unknown'])
def test_initial_character_matches_startup_contract(db,sex):
    from backend.runtime_v3.npc_identity import INITIAL_FIELDS
    from backend.runtime_v3.models import Character
    from backend.services.draft_initial import ACTOR_FIELDS
    repo,_,sid=db;snapshot=repo.get_snapshot(sid)
    raw=promoted(snapshot)
    attrs=dict(biological_sex=sex,birth_date='1999-04-12',developmental_stage='adult',life_status='alive',
        reproductive_capability='unknown',capabilities=dict(can_speak=False,can_move=True),
        identity_components={'given':'Лада'},physical_state='Устала',emotion='Рада встрече',goals=['Открыть мастерскую'])
    raw['promotions'][0]['character']=attrs
    jid=repo.begin_job(sid,'Я доверяю Ладе.','start',CONFIG);run(repo,jid,raw)
    assert repo.get_job(jid)['status']=='saved',repo.get_job(jid)['error']
    actual=repo.get_snapshot(sid)['world_state']['characters']['new_npc']
    expected=Character(id='new_npc',**dict(attrs,biological_sex=None if sex=='unknown' else sex)).model_dump()
    assert set(actual)==set(expected)==set(Character.model_fields)
    for key in attrs:assert actual[key]==expected[key]
    # Exercise the actual startup validation/migration boundary, not a second
    # hand-maintained list of defaults. Motivation IDs belong to each identity.
    from test_initial_draft_v4 import rich
    from backend.services.draft_initial import normalize, canonical_check
    from backend.runtime_v3.lifecycle import active_texts
    startup=rich();startup_id=startup['characters'][1]['id']
    startup['world']['characters'][startup_id].update(dict(attrs,biological_sex=expected['biological_sex']))
    startup_actor=canonical_check(normalize(startup)).snapshot['world_state']['characters'][startup_id]
    assert set(actual)==set(startup_actor)
    for key in attrs:
        if key in ('goals','intentions','obligations'):
            assert active_texts(actual[key])==active_texts(startup_actor[key])
        else: assert actual[key]==startup_actor[key]
    assert set(INITIAL_FIELDS)|{'birth_provenance','birth_date_provenance','name_history','life_fact_id','parentage_complete_fact_id'}>=set(ACTOR_FIELDS)
    assert repo.get_save(sid)['state']['npc_reviews']['records'][0]['current']['biological_sex']==expected['biological_sex']


def test_canonical_edit_conflict_after_next_turn_and_safe_resolution(db):
    repo,_,sid=db;start(repo,sid)
    fields=dict.fromkeys(CARD_FIELDS,'Описание')
    edit(repo,sid,'new_npc',**command(repo,sid,'defer',fields,character={'situation':'Ждёт снаружи','biological_sex':'female'}))
    snapshot=repo.get_snapshot(sid);raw=raw_for(snapshot)
    raw['character_changes']=[dict(id='new_npc',situation='Ушла в мастерскую',evidence='Ушла.')]
    jid=repo.begin_job(sid,'Продолжаю','turn',CONFIG);run(repo,jid,raw)
    assert repo.get_job(jid)['status']=='saved'
    before=repo.get_snapshot(sid)
    with pytest.raises(ValueError,match='Текущая ситуация'):
        edit(repo,sid,'new_npc',**command(repo,sid,'confirm',fields,operation='conflict-operation',character={'situation':'Ждёт снаружи','biological_sex':'female'}))
    assert repo.get_snapshot(sid)==before
    edit(repo,sid,'new_npc',**command(repo,sid,'confirm',fields,operation='resolved-operation',character={'biological_sex':'female'}))
    after=repo.get_snapshot(sid)
    assert after['world_state']['characters']['new_npc']['situation']=='Ушла в мастерскую'
    assert after['world_state']['characters']['new_npc']['biological_sex']=='female'


def test_recipients_without_contacts_and_channel_restrictions(db):
    from backend.runtime_v3.remote import projection
    repo,_,sid=db;start(repo,sid);snapshot=repo.get_snapshot(sid);state=snapshot['world_state']
    state['characters']['new_npc'].update(life_status='alive',developmental_stage='adult')
    state['characters'][state['camera']['controlled_actor_id']].update(life_status='alive',developmental_stage='adult')
    # Use the canonical modern communication fixture, not invented contacts.
    from backend.services.communication_profile import catalog
    state['meta']['communication']=catalog()['modern']
    view=projection(snapshot)
    assert any(r['id']=='new_npc' for r in view['recipients'])
    assert not any(c.get('target_id')=='new_npc' for c in state['contacts'].values())
    state['characters']['new_npc']['life_status']='dead'
    assert not any(r['id']=='new_npc' for r in projection(snapshot)['recipients'])


def test_duplicate_promotion_cannot_replace_existing_identity(db):
    repo,_,sid=db;start(repo,sid);before=repo.get_snapshot(sid)
    job=repo.begin_job(sid,'Снова','turn',CONFIG);run(repo,job,promoted(before))
    assert repo.get_job(job)['status']=='error'
    assert repo.get_snapshot(sid)==before


def test_invalid_canonical_payload_rolls_back_atomically(db):
    repo,_,sid=db;before=repo.get_snapshot(sid)
    raw=promoted(before);raw['promotions'][0]['character']={'birth_date':'2099-99-99','capabilities':{'can_speak':'yes'}}
    job=repo.begin_job(sid,'','start',CONFIG);run(repo,job,raw)
    assert repo.get_job(job)['status']=='error'
    assert repo.get_snapshot(sid)==before


def test_multiple_reviews_defer_queue_without_deleting_identities(db):
    repo,_,sid=db;raw=promoted(repo.get_snapshot(sid))
    raw['promotions'].append(dict(id='other',name='Другой',fields={},evidence='Вошёл.'))
    job=repo.begin_job(sid,'','start',CONFIG);run(repo,job,raw)
    edit(repo,sid,'new_npc',**command(repo,sid,'defer'))
    snap=repo.get_snapshot(sid)
    assert {r['status'] for r in snap['pending_reviews'].values()}=={'deferred'}
    assert {'new_npc','other'}<=snap['world_state']['characters'].keys()


def test_provider_schema_anchors_preserve_validation():
    from jsonschema import Draft202012Validator
    from backend.runtime_v3.raw import prompt_schema
    compact=prompt_schema();full=extraction_schema()
    a=Draft202012Validator({'$defs':compact['$defs'],'properties':{'promotions':compact['properties']['promotions']}})
    b=Draft202012Validator({'properties':{'promotions':full['properties']['promotions']}})
    base=dict(promotions=[dict(id='npc',name='Лада',fields=dict.fromkeys(CARD_FIELDS,'Описание'),character={'biological_sex':'female'},evidence='Вошла.')])
    assert a.is_valid(base) and b.is_valid(base)
    for damage in [None,1,[],{'biological_sex':'invented'},{'capabilities':{'can_speak':'yes'}}]:
        value=deepcopy(base);value['promotions'][0]['character']=damage
        assert not a.is_valid(value) and not b.is_valid(value)


def test_confirmation_preserves_extracted_profiles(db):
    repo,_,sid=db;raw=promoted(repo.get_snapshot(sid))
    raw['promotions'][0]['character']={
        'personality':{'items':{'temperament':{'field':'traits','text':'Сдержанная и осторожная'}}},
        'appearance':{'items':{'eyes':{'category':'intrinsic','kind':'eye_color','text':'Серые глаза'}}}}
    job=repo.begin_job(sid,'Я доверяю Ладе.','start',CONFIG);run(repo,job,raw)
    assert repo.get_job(job)['status']=='saved',repo.get_job(job)['error']
    before=repo.get_snapshot(sid)['world_state']['characters']['new_npc']
    fields=dict.fromkeys(CARD_FIELDS,'Полное описание')
    fields['Характер']='Новое описание не заменяет канонический профиль'
    edit(repo,sid,'new_npc',**command(repo,sid,'confirm',fields))
    after=repo.get_snapshot(sid)['world_state']['characters']['new_npc']
    assert after['appearance']==before['appearance']
    assert after['personality']['items']['temperament']==before['personality']['items']['temperament']
    assert len([v for v in after['personality']['items'].values() if v['field']=='traits'])==1
    projected=next(c for c in repo.get_save(sid)['state']['characters'] if c['id']=='new_npc')
    assert projected['fields']['Характер']=='Сдержанная и осторожная'
    assert 'Серые глаза' in projected['fields']['Внешность']
