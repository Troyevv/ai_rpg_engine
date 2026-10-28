"""Issue #134: synthetic provider replies, never a replay of the user's job."""
from copy import deepcopy
import json
from unittest.mock import patch
import pytest
from test_api import api, wait_job
from test_runtime_handoff import imported, submit, arrival, snapshot_state

ENTRY = 'Виктория Соловьёва открыла дверь и вошла внутрь. Илья поднял голову.'
DOORWAY = ('В замке поворачивается ключ, дверь приоткрывается на ладонь. '
           'Виктория стоит в проёме, в куртке поверх рабочего фартука, с сумкой на плече; '
           'за её спиной пустой коридор и наполовину погашенные лампы. '
           'Она смотрит на разбросанные бумаги на столе, потом на Илью — и не спешит уходить')


def contextual_arrival():
    raw = arrival(evidence=ENTRY)
    raw['movements'][0].update(destination_evidence='внутрь',
        destination_reference='camera_location', anchor_location_id='ilya_cabinet')
    return raw


def test_first_scene_contextual_entry_real_api(api):
    client, app = api
    sid = imported(client)
    before = app.state.repository.get_snapshot(sid)
    calls = []
    def provider(**kw):
        calls.append(kw)
        yield json.dumps(contextual_arrival(), ensure_ascii=False) if kw.get('response_format') else ENTRY
    with patch('engine.chat_stream', side_effect=provider):
        jid = submit(client, sid)
        job = wait_job(client, jid)
    assert job['status'] == 'saved', (job.get('error'), job.get('repairs'))
    after = app.state.repository.get_snapshot(sid)
    assert after['world_state']['characters']['viktoria_solovyova']['location_id'] == 'ilya_cabinet'
    assert len(calls) == 2
    assert after['world_state']['meta']['world_time'] == before['world_state']['meta']['world_time'] + 1


def doorway_payload(origin='salon_lak'):
    return dict(final_scene=dict(location_id='ilya_cabinet', present_character_ids=['ilya'],
                    observed_character_ids=['viktoria_solovyova'], elapsed_minutes=0),
        locations=[dict(id='cabinet_threshold', name='Порог кабинета', kind='boundary',
                        parent_id='ilya_cabinet', evidence=DOORWAY)],
        movements=[dict(actor_id='viktoria_solovyova', from_location_id=origin,
            to_location_id='cabinet_threshold', assertion='observed_at_boundary',
            actor_evidence='Виктория', destination_evidence='в проёме',
            destination_reference='scene_boundary', anchor_location_id='ilya_cabinet', evidence=DOORWAY)])


def test_doorway_real_api_preserves_boundary_and_context(api):
    from backend.runtime_v3.context import build_context
    client, app = api; sid = imported(client)
    def provider(**kw):
        yield json.dumps(doorway_payload(), ensure_ascii=False) if kw.get('response_format') else DOORWAY
    with patch('engine.chat_stream', side_effect=provider):
        job = wait_job(client, submit(client, sid))
    assert job['status'] == 'saved', job
    snap = app.state.repository.get_snapshot(sid)
    s = snap['world_state']
    assert s['camera'].get('observed_character_ids') == ['viktoria_solovyova']
    assert s['camera']['present_character_ids'] == ['ilya']
    assert s['characters']['viktoria_solovyova']['location_id'] == 'cabinet_threshold'
    messages = build_context(snap, [], 'Я спрашиваю: «Как дела?»', 'turn', 131072, 2000)
    assert messages.selection['characters']['FULL_OBSERVED'] == 1


def resolve(snap, text, payload, player=''):
    from backend.runtime_v3.resolver import StateResolver
    return StateResolver(snap['world_state'], text, player,
        actor_names={c['id']:c['name'] for c in snap['character_cards']}).resolve(payload)


@pytest.mark.parametrize('change,condition', [
    ({'actor_evidence':'Илья'}, 'actor_anchor_mismatch'),
    ({'actor_id':'marina_volkova'}, None),
    ({'from_location_id':'moscow'}, 'origin_mismatch'),
    ({'anchor_location_id':'salon_lak'}, 'camera_anchor_mismatch'),
    ({'to_location_id':'salon_lak'}, None),
    ({'evidence':'Виктория уже вошла.'}, 'evidence_unsupported'),
    ({'destination_evidence':'кухню'}, 'destination_quote_mismatch'),
    ({'assertion':'future_arrival'}, 'assertion_not_completed'),
    ({'assertion':'negated'}, 'assertion_not_completed'),
])
def test_wrong_spatial_claim_never_mutates_input(api, change, condition):
    from backend.services.world_delta_errors import StructuralDeltaError
    client, app = api; sid = imported(client)
    snap = app.state.repository.get_snapshot(sid); original = deepcopy(snap)
    raw = contextual_arrival(); raw['movements'][0].update(change)
    with pytest.raises(StructuralDeltaError) as error:
        resolve(snap, ENTRY, raw)
    if condition: assert error.value.path['condition'] == condition
    assert snap == original


@pytest.mark.parametrize('text', [
    'Виктория обещала прийти завтра.', 'Виктория звонит Илье из салона.',
    'Виктория пишет: «Я скоро буду».', 'Илья упоминает Викторию за закрытой дверью.',
    'Виктория проходит мимо и не входит.', 'Виктория не вошла.',
    'За дверью кто-то шевельнулся; Илья не знает, кто там.',
])
def test_nonarrival_real_api_keeps_geography(api, text):
    client, app = api; sid = imported(client)
    repo = app.state.repository; before = repo.get_snapshot(sid)['world_state']
    raw = dict(final_scene=dict(location_id='ilya_cabinet',present_character_ids=['ilya'],elapsed_minutes=0))
    def provider(**kw): yield json.dumps(raw) if kw.get('response_format') else text
    with patch('engine.chat_stream',side_effect=provider):
        assert wait_job(client, submit(client,sid))['status']=='saved'
    after = repo.get_snapshot(sid)['world_state']
    assert after['camera']['present_character_ids']==['ilya']
    assert after['camera']['observed_character_ids']==[]
    assert {cid:c['location_id'] for cid,c in after['characters'].items()} == {cid:c['location_id'] for cid,c in before['characters'].items()}
    assert after['meta']['world_time']==before['meta']['world_time']


@pytest.mark.parametrize('origin', [None, 'salon_lak'])
@pytest.mark.parametrize('length', [0, 16000])
def test_contextual_entry_unknown_origin_and_long_narrative(api, origin, length):
    client, app = api; sid=imported(client)
    snap=app.state.repository.get_snapshot(sid)
    snap['world_state']['characters']['viktoria_solovyova']['location_id']=origin
    raw=contextual_arrival();raw['movements'][0]['from_location_id']=origin
    result=resolve(snap, 'Тихий вечер. '*length+ENTRY, raw)
    assert result.state['characters']['viktoria_solovyova']['location_id']=='ilya_cabinet'
    assert result.history['movements'][0]['from_location_id']==origin


def test_named_inflected_place_group_route_exit_and_alias_reuse(api):
    client, app=api;sid=imported(client);snap=app.state.repository.get_snapshot(sid)
    text='Илья и Виктория Соловьёва прошли через коридор в новую кофейню. Затем Илья остался, а Виктория Соловьёва вышла в коридор.'
    s=snap['world_state'];s['characters']['viktoria_solovyova']['location_id']='ilya_cabinet'
    s['camera']['present_character_ids'].append('viktoria_solovyova')
    places=[dict(id='corridor',name='Коридор',parent_id='ilya_cabinet',evidence=text),
            dict(id='cafe',name='Новая кофейня',aliases=['Кафе'],evidence=text)]
    def movement(cid,origin,target,order,span,name):
        return dict(actor_id=cid,from_location_id=origin,to_location_id=target,order=order,
            assertion='completed_arrival',actor_evidence='Илья' if cid=='ilya' else 'Виктория Соловьёва',
            destination_reference='named_location',destination_name=name,destination_evidence=span,evidence=text)
    moves=[]
    for cid in ('ilya','viktoria_solovyova'):
        moves += [movement(cid,'ilya_cabinet','corridor',1,'коридор','Коридор'),
                  movement(cid,'corridor','cafe',2,'новую кофейню','Кафе')]
    moves.append(movement('viktoria_solovyova','cafe','corridor',3,'коридор','Коридор'))
    raw=dict(final_scene=dict(location_id='cafe',present_character_ids=['ilya'],elapsed_minutes=0),locations=places,movements=moves)
    result=resolve(snap,text,raw,player='Я иду в кофейню.')
    assert result.state['camera']['location_id']=='cafe'
    assert result.state['characters']['ilya']['location_id']=='cafe'
    assert result.state['characters']['viktoria_solovyova']['location_id']=='corridor'
    assert len(result.history['movements'])==5
    assert [(m['from_location_id'],m['to_location_id']) for m in result.history['movements'] if m['actor_id']=='ilya']==[('ilya_cabinet','corridor'),('corridor','cafe')]
    for m in moves: m['from_location_id']='moscow'
    from backend.services.world_delta_errors import StructuralDeltaError
    with pytest.raises(StructuralDeltaError):resolve(snap,text,raw)
    follow=deepcopy(snap);follow['world_state']=result.state
    reused=dict(final_scene=dict(location_id='cafe_copy',present_character_ids=['ilya']),locations=[dict(id='cafe_copy',name='Кафе',evidence='Илья остался в Кафе.')])
    again=resolve(follow,'Илья остался в Кафе.',reused)
    assert 'cafe_copy' not in again.state['locations']
    assert again.state['camera']['location_id']=='cafe'


@pytest.mark.parametrize('retry', [False, True])
def test_repair_or_restart_retry_then_turn_reload_turn(api, retry):
    from backend.api.app import create_app
    from fastapi.testclient import TestClient
    from backend.runtime_v3.repository import read_history
    client, app=api;sid=imported(client);repo=app.state.repository
    before=snapshot_state(repo,sid);snap_before=repo.get_snapshot(sid);calls=[]
    bad=arrival(evidence=DOORWAY);bad.pop('movements')
    def provider(**kw):
        calls.append(kw)
        if not kw.get('response_format'):yield DOORWAY;return
        extraction_count=sum(bool(c.get('response_format')) for c in calls)
        if extraction_count <= (2 if retry else 1):yield json.dumps(bad);return
        current=json.loads(next(m['content'].split('\n',1)[1] for m in kw['messages'] if m['content'].startswith('Текущее состояние / GM-only\n')))
        raw=doorway_payload(current['characters']['viktoria_solovyova']['location_id'])
        raw['final_scene']['elapsed_minutes']=1
        raw['events']=[dict(id='doorway_exchange',text='Виктория стоит в проёме.',participants=['ilya','viktoria_solovyova'],witnesses=['ilya'],medium='observation',evidence=DOORWAY)]
        yield json.dumps(raw,ensure_ascii=False)
    with patch('engine.chat_stream',side_effect=provider):
        jid=submit(client,sid);job=wait_job(client,jid)
        if retry:
            assert job['status']=='error' and job['narrative_complete']
            assert snapshot_state(repo,sid)==before and not repo.list_turns(sid)
        else: assert job['status']=='saved',job
        original=repo.get_job(jid)
        # New app, repository, SQLite connection and actual retry HTTP endpoint.
        with TestClient(create_app(repo.path)) as reopened:
            if retry:
                from test_runtime_handoff import REMOTE
                response=reopened.post(f'/api/jobs/{jid}/retry',json=dict(config=REMOTE,api_key='test-secret'))
                assert response.status_code==200,response.text
                job=wait_job(reopened,jid)
                assert job['status']=='saved',job
                assert reopened.post(f'/api/jobs/{jid}/retry',json=dict(config=REMOTE,api_key='test-secret')).status_code==409
            first=repo.get_job(jid)
            assert first['narrative']==original['narrative']==DOORWAY
            assert first['before_json']==original['before_json']
            assert sum(not c.get('response_format') for c in calls)==1
            assert len(repo.list_turns(sid))==1
            assert wait_job(reopened,submit(reopened,sid,'turn','Я спрашиваю: «Как дела?»'))['status']=='saved'
        with TestClient(create_app(repo.path)) as reopened:
            assert wait_job(reopened,submit(reopened,sid,'turn','Я жду ответа.'))['status']=='saved'
    final=repo.get_snapshot(sid)['world_state']
    assert len(repo.list_turns(sid))==3
    assert final['meta']['world_time']==snap_before['world_state']['meta']['world_time']+3
    assert final['knowledge']==snap_before['world_state']['knowledge']
    assert len(final['characters'])==19
    assert final['characters']['viktoria_solovyova']['location_id']=='cabinet_threshold'
    assert final['camera']['observed_character_ids']==['viktoria_solovyova']
    for cid,c in final['characters'].items():
        if cid!='viktoria_solovyova':assert c['location_id']==snap_before['world_state']['characters'][cid]['location_id']
    with repo.connect() as db: history,_=read_history(db,repo.get_snapshot(sid)['history_head'])
    assert len(history['turns'])==3 and len({e['id'] for e in history['events']})==len(history['events'])
    diagnostics=json.loads(repo.get_job(jid)['repair_diagnostics_json'])
    assert diagnostics[0]['condition']=='completed_arrival_required'
    assert diagnostics[0]['before_camera']==snap_before['world_state']['camera']
    assert len(diagnostics)==(2 if retry else 1)
    assert sum(not c.get('response_format') for c in calls)==3


def test_boundary_visibility_control_and_initiative(api):
    from backend.runtime_v3.context import build_context
    from backend.runtime_v3.camera import observe
    client, app = api; sid = imported(client)
    snapshot = app.state.repository.get_snapshot(sid)
    result = resolve(snapshot, DOORWAY, doorway_payload())
    snapshot['world_state'] = result.state
    context = build_context(snapshot, [], 'Я отвечаю Виктории.', 'turn', 131072, 2000)
    actor = next(a for a in context.selection['initiative']['actors'] if a['actor_id']=='viktoria_solovyova')
    assert actor['channel']=='boundary'
    switched = observe(snapshot, actor_id='viktoria_solovyova')
    assert switched['world_state']['camera']['observed_character_ids']==[]
    assert switched['world_state']['characters']['ilya']['location_id']=='ilya_cabinet'
    closed = resolve(snapshot, 'Дверь закрывается.', dict(final_scene=dict(location_id='ilya_cabinet',present_character_ids=['ilya'])))
    assert closed.state['camera']['observed_character_ids']==[]
    assert closed.state['characters']['viktoria_solovyova']['location_id']=='cabinet_threshold'
    raw=contextual_arrival();raw['movements'][0]['from_location_id']='cabinet_threshold'
    entered=resolve(snapshot,ENTRY,raw)
    assert entered.state['camera']['observed_character_ids']==[]
    assert entered.state['characters']['viktoria_solovyova']['location_id']=='ilya_cabinet'
    assert entered.history['movements'][0]['from_location_id']=='cabinet_threshold'


def test_explicit_hero_claim_cannot_fall_back_after_filtering(api):
    from backend.services.world_delta_errors import StructuralDeltaError
    client,app=api;sid=imported(client);snap=app.state.repository.get_snapshot(sid)
    original=deepcopy(snap)
    raw=dict(final_scene=dict(location_id='salon_lak',present_character_ids=['ilya']),movements=[dict(
        actor_id='ilya',from_location_id='ilya_cabinet',to_location_id='salon_lak',assertion='completed_arrival',
        actor_evidence='Илья',destination_evidence='салон',evidence='Илья вошёл в салон.')])
    with pytest.raises(StructuralDeltaError) as error:resolve(snap,'Илья остался в кабинете.',raw)
    assert error.value.path['condition']=='evidence_unsupported'
    assert snap==original


def test_boundary_regenerate_variant_rollback_keeps_original_before(api):
    client,app=api;sid=imported(client);repo=app.state.repository
    before=repo.get_snapshot(sid)
    def provider(**kw): yield json.dumps(doorway_payload()) if kw.get('response_format') else DOORWAY
    with patch('engine.chat_stream',side_effect=provider):
        jid=submit(client,sid);assert wait_job(client,jid)['status']=='saved'
        first=repo.list_turns(sid)[0];saved=repo.get_snapshot(sid)
        first_before=repo.get_job(jid)['before_json']
        assert wait_job(client,submit(client,sid,'regenerate'))['status']=='saved'
    repo.select_variant(sid,first['id'],first['active_variant_id'],repo.get_save(sid)['revision'])
    assert repo.get_snapshot(sid)==saved
    repo.rollback_last(sid)
    assert repo.get_snapshot(sid)['world_state']==before['world_state']
    assert not repo.list_turns(sid)
    with repo.connect() as db:
        variants=[json.loads(r[0]) for r in db.execute('SELECT payload FROM response_variants WHERE save_id=?',(sid,))]
    assert next(v for v in variants if v['active_variant_id']==first['active_variant_id'])['before_json']==first_before


def test_unknown_camera_new_place_uses_named_anchor_not_deictic_guess(api):
    from backend.runtime_v3.context import build_context
    from backend.services.world_delta_errors import StructuralDeltaError
    client,app=api;sid=imported(client);snapshot=app.state.repository.get_snapshot(sid)
    s=snapshot['world_state'];s['camera']['location_id']=None;s['characters']['ilya']['location_id']=None
    text='Илья вошёл в новую прихожую.'
    raw=dict(final_scene=dict(location_id='entry_hall',present_character_ids=['ilya'],elapsed_minutes=0),
        locations=[dict(id='entry_hall',name='Новая прихожая',evidence=text)],
        movements=[dict(actor_id='ilya',from_location_id=None,to_location_id='entry_hall',
            assertion='completed_arrival',actor_evidence='Илья',destination_evidence='новую прихожую',
            destination_name='Новая прихожая',destination_reference='named_location',evidence=text)])
    result=resolve(snapshot,text,raw,player='Я иду в прихожую.')
    assert result.state['characters']['ilya']['location_id']=='entry_hall'
    assert result.history['movements'][0]['from_location_id'] is None
    assert result.state['meta']['world_time']==s['meta']['world_time']
    messages=build_context(snapshot,[],'Я иду в прихожую.','turn',131072,2000,extraction_text=text)
    current=json.loads(next(m['content'].split('\n',1)[1] for m in messages if m['content'].startswith('Текущее состояние / GM-only\n')))
    assert 'location_id' in current['characters']['ilya'] and current['characters']['ilya']['location_id'] is None
    raw['movements'][0].update(destination_reference='camera_location',anchor_location_id='entry_hall')
    with pytest.raises(StructuralDeltaError) as error:resolve(snapshot,text,raw)
    assert error.value.path['condition']=='camera_anchor_mismatch'
