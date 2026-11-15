"""Unmodified provider outputs; no successful authored JSON in baseline replays."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from backend.runtime_v3.scene_repair import SceneCandidate
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.player_actions import resolver_options
from backend.services.world_delta_errors import StructuralDeltaError

pytestmark = pytest.mark.extraction_v7

ROOT = Path(__file__).parent / 'fixtures/issue256'


def original(name):
    return json.loads((ROOT / (name + '.json')).read_text())


def candidate(data, first):
    meta = first['candidate']
    return SceneCandidate(data['snapshot']['world_state'], data['narrative'],
                          data['player_input'], meta['turn_id'], namespace=meta['namespace'])


def replay(data, first, repair):
    c = candidate(data, first)
    with pytest.raises(StructuralDeltaError) as e:
        c.parse(first['response'])
    feedback = json.loads(c.feedback(e.value.diagnostics('extraction_repair'), first['response']))
    assert feedback['candidate_hash'] == json.loads(repair['response'])['candidate_hash']
    return c, c.parse(repair['response'])


def resolve(data, raw, turn):
    state = data['snapshot']['world_state']
    return StateResolver(state, data['narrative'], data['player_input'], turn_id=turn,
                         **resolver_options(state, data['player_input'], contract_version=6)).resolve(raw)


def test_original_river_false_saved_characterization():
    d = original('river'); saved = deepcopy(d)
    first, repair = d['responses']
    c, raw = replay(d, first, repair)
    result = resolve(d, raw, first['candidate']['turn_id'])
    assert not raw.records['movements']
    assert result.state['characters']['char_alexey']['location_id'] == 'loc_home_galina'
    assert result.state['characters']['char_galina']['location_id'] == 'loc_home_galina'
    assert d == saved


@pytest.mark.parametrize('epoch', [0, 1])
def test_cafe_unproven_final_arrival_does_not_invalidate_earlier_conversation(epoch):
    d = original('cafe'); saved = deepcopy(d)
    responses = [r for r in d['responses'] if r['stage'].startswith('extraction')]
    first, repair = responses[epoch*2:epoch*2+2]
    c, raw = replay(d, first, repair)
    resolver = StateResolver(d['snapshot']['world_state'], d['narrative'], d['player_input'],
                            turn_id=first['candidate']['turn_id'],
                            **resolver_options(d['snapshot']['world_state'], d['player_input'], contract_version=6))
    with pytest.raises(StructuralDeltaError) as e:
        resolver.resolve(raw)
    errors = e.value.diagnostics('validation_failed')
    assert 'scene_arrival_unproven' in {r['code'] for r in errors}
    assert any(r['code']=='event_presence_invalid' for r in errors)  # Late impossible encounter still fails.
    assert not any(r['code']=='event_presence_invalid' and r.get('index') in (0,1) for r in errors)
    assert not any(m.get('derived_from')=='final_scene' and m['actor_id']=='char_galina' for m in resolver.history.movements)
    assert resolver.state['characters']['char_galina']['location_id'] == 'loc_home_galina'
    assert d == saved


def test_group_route_one_source_no_npc_player_authority():
    from test_scene_steps255 import fixture
    from backend.runtime_v3.scene_steps import compile_scene
    state, _ = fixture()
    text = 'Иду вместе с b в парк.'
    payload = dict(scene=dict(elapsed_minutes=3, visible_character_ids=['a','b']), scene_steps=[
        dict(id='together',kind='movement',actor_ids=['a','b'],assertion='completed_arrival',endpoint='park',
             text='Вместе дошли.',input_source=dict(quote=text,meaning='preserved')),
        dict(id='reply',kind='interaction',actor_id='b',target_ids=['a'],outcome='completed',text='b говорит.')])
    raw = compile_scene(payload,state,'Проза.',1,version=7)
    assert len(raw.records['movements'])==2
    assert 'player_action_id' not in raw.records['movements'][1]
    assert len(raw.player_agency['actions'])==1
    result=StateResolver(state,'Проза.',text,turn_id=1,**resolver_options(state,text,contract_version=7)).resolve(raw)
    assert [result.state['characters'][c]['location_id'] for c in ['a','b']]==['park','park']
    assert not result.history['knowledge_acquisitions']


def test_local_exit_keeps_address_without_implicit_knowledge():
    from test_scene_steps255 import fixture
    from backend.runtime_v3.scene_steps import compile_scene
    state,_=fixture()
    payload=dict(scene=dict(elapsed_minutes=1),scene_steps=[dict(id='room',kind='movement',actor_ids=['b'],assertion='local_exit',endpoint=None,text='b уходит в другую комнату.')])
    raw=compile_scene(payload,state,'Проза.','1',version=7)
    assert not raw.records['movements']
    result=StateResolver(state,'Проза.','Жду.',turn_id=1,**resolver_options(state,'Жду.',contract_version=7)).resolve(raw)
    assert result.state['characters']['b']['location_id']=='home'
    assert 'b' not in result.state['camera']['present_character_ids']
    assert not result.history['knowledge_acquisitions']


def test_actor_observer_schema_projection_and_legacy():
    from backend.runtime_v3.scene_steps import input_schema,validate
    from test_scene_steps255 import fixture
    state,_=fixture()
    assert 'observer_location_id' not in input_schema(7,'actor')['properties']['scene']['properties']
    assert 'observer_location_id' in input_schema(7,'observer')['properties']['scene']['properties']
    assert 'observer_location_id' in input_schema(6,'actor')['properties']['scene']['properties']
    with pytest.raises(StructuralDeltaError):
        validate(dict(scene={'observer_location_id':'home'},scene_steps=[]),state,version=7)


@pytest.mark.parametrize('epoch',[0,1])
def test_cafe_first_feedback_collects_route_camera_and_agency(epoch):
    d=original('cafe');responses=[r for r in d['responses'] if r['stage'].startswith('extraction')]
    first=responses[epoch*2];c=candidate(d,first)
    raw=c.parse(first['response'],defer_errors=True)
    with pytest.raises(StructuralDeltaError) as e: resolve(d,raw,first['candidate']['turn_id'])
    rows=e.value.diagnostics('repair')
    assert {'movement_agency','camera_invalid','scene_arrival_unproven'} <= {r['code'] for r in rows}
    assert not any(r['code']=='event_presence_invalid' and r.get('index') in (0,1) for r in rows)
    feedback=json.loads(c.feedback(rows,first['response']))
    assert 'char_galina' in feedback['scope']['actor_ids']


def test_legacy_river_repair_can_add_related_route_and_location():
    d=original('river');first=d['responses'][0];c=candidate(d,first)
    with pytest.raises(StructuralDeltaError) as e:c.parse(first['response'])
    fb=json.loads(c.feedback(e.value.diagnostics('repair'),first['response']))
    base=json.loads(first['response']);anchor=base['scene_steps'][0]['id']
    assert anchor in fb['scope']['step_ids'] and 'locations' in fb['scope']['sections']
    # Explicit authored interpretation; not a replacement for real model acceptance.
    patch=dict(candidate_hash=fb['candidate_hash'],replacements=[],sections=dict(
        scene=dict(observer_location_id=None),locations=[dict(id='authored_shore',name='Берег',evidence='Контроль теста')]),
        additions=[dict(after_id=anchor,step=dict(id='walk_'+actor,kind='movement',actor_id=actor,assertion='completed_arrival',endpoint='authored_shore',text='Дошёл до берега.',
            **(dict(input_source=dict(quote='Иду рядом с мамой к Березянке, подстраиваясь под её шаг.',meaning='preserved')) if actor=='char_alexey' else {}))) for actor in ['char_alexey','char_galina']],reason='Authored control: omitted shared route.')
    raw=c.parse(patch)
    result=resolve(d,raw,first['candidate']['turn_id'])
    assert all(result.state['characters'][a]['location_id']=='authored_shore' for a in ['char_alexey','char_galina'])
    assert raw.semantic_candidate['facts']==base['facts']
    assert raw.semantic_candidate['scene_steps'][-1]==base['scene_steps'][-1]


@pytest.mark.parametrize('assertion',['intent','preparation','attempt'])
def test_group_unfinished_outcomes_do_not_move(assertion):
    from test_scene_steps255 import fixture
    from backend.runtime_v3.scene_steps import compile_scene
    s,_=fixture();p=dict(scene=dict(elapsed_minutes=1),scene_steps=[dict(id='plan',kind='movement',actor_ids=['a','b'],assertion=assertion,endpoint='park',text='Планируют.')])
    raw=compile_scene(p,s,'Проза.',1,version=7)
    result=StateResolver(s,'Проза.','Жду.',turn_id=1,**resolver_options(s,'Жду.',contract_version=7)).resolve(raw)
    assert not result.history['movements']
    assert result.state['characters']['a']['location_id']==result.state['characters']['b']['location_id']=='home'


@pytest.mark.parametrize('listener',['a','c'])
def test_conversation_during_shared_route_only_for_explicit_travellers(listener):
    from test_scene_steps255 import fixture
    from backend.runtime_v3.scene_steps import compile_scene
    s,_=fixture();text='Иду с b в парк и говорю с ним.'
    p=dict(scene=dict(elapsed_minutes=2),scene_steps=[dict(id='trip',kind='movement',actor_ids=['a','b'],assertion='completed_arrival',endpoint='park',text='Дошли.',input_source=dict(quote='Иду с b в парк',meaning='preserved')),
        dict(id='talk',kind='information',source_actor_id='b',target_ids=[listener],medium='conversation',during_step_id='trip',text='Разговор по дороге.',claims=[dict(fact=dict(text='Новость.'),assertion='testimony',status='known',perceived_by=[listener])])])
    raw=compile_scene(p,s,'Проза.',1,version=7)
    resolver=StateResolver(s,'Проза.',text,turn_id=1,**resolver_options(s,text,contract_version=7))
    if listener=='c':
        with pytest.raises(StructuralDeltaError):resolver.resolve(raw)
    else:
        result=resolver.resolve(raw)
        assert len(result.history['knowledge_acquisitions'])==1
        assert result.state['characters']['a']['location_id']=='park'


def test_original_walk_quote_error_is_not_hidden_by_camera():
    d=original('walk');first=d['responses'][0];c=candidate(d,first)
    raw=c.parse(first['response'],defer_errors=True)
    with pytest.raises(StructuralDeltaError) as e:resolve(d,raw,first['candidate']['turn_id'])
    rows=e.value.diagnostics('repair')
    assert {'camera_invalid','player_action_source_invalid'} <= {r['code'] for r in rows}
    assert any(r['code']=='player_action_source_invalid' and r['section']=='scene_steps' and r['index']==0 for r in rows)


def test_original_room_exit_and_authored_local_interpretation():
    from backend.runtime_v3.scene_steps import compile_scene
    d=original('room');first=d['responses'][0];c=candidate(d,first)
    assert c.binding==first['candidate']['binding']
    before=deepcopy(d['snapshot']['world_state']);raw=c.parse(first['response'])
    result=StateResolver(before,d['narrative'],'',turn_id=first['candidate']['turn_id'],**d['resolver_options']).resolve(raw)
    assert result.state['characters']['char_olga']['location_id'] is None  # Original false outcome.
    p=json.loads(first['response']);step=p['scene_steps'][0]
    step['actor_ids']=[step.pop('actor_id')];step['assertion']='local_exit'
    raw=compile_scene(p,before,d['narrative'],first['candidate']['turn_id'],version=7)
    result=StateResolver(before,d['narrative'],'',turn_id=first['candidate']['turn_id'],**d['resolver_options']).resolve(raw)
    assert result.state['characters']['char_olga']['location_id']=='loc_home_sokolov'
    assert 'char_olga' not in result.state['camera']['present_character_ids']
    assert result.state['knowledge']==before['knowledge']
    assert result.state['characters']['char_alexey']==before['characters']['char_alexey']
    assert d['snapshot']['world_state']==before


def test_legacy_redundant_camera_does_not_need_repair_when_full_route_is_valid():
    from test_scene_steps255 import fixture,INPUT
    s,p=fixture();p['scene']['observer_location_id']='park'
    c=SceneCandidate(s,'Проза.',INPUT,1)
    raw=c.parse(p,defer_errors=True)
    result=StateResolver(s,'Проза.',INPUT,turn_id=1,**resolver_options(s,INPUT,contract_version=6)).resolve(raw)
    assert result.state['characters']['a']['location_id']=='park'
    assert any(w['code']=='camera_annotation_ignored' for w in result.warnings)


def test_v7_one_feedback_for_independent_route_agency_camera_and_one_repair():
    from test_scene_steps255 import fixture
    from backend.runtime_v3.scene_steps import input_schema
    from backend.runtime_v3.scene_repair import repair_schema
    s,_=fixture();text='Иду в парк.'
    p=dict(scene=dict(elapsed_minutes=1,observer_location_id='missing'),scene_steps=[
        dict(id='bad',kind='movement',actor_ids=['a'],assertion='completed_arrival',endpoint='missing',text='Пришёл.',input_source=dict(quote='Несуществующий ввод',meaning='preserved')),
        dict(id='independent',kind='occurrence',actor_ids=['c'],text='c занимается своим делом.')])
    c=SceneCandidate(s,'Проза.',text,1,version=7)
    raw=c.parse(p,defer_errors=True)
    with pytest.raises(StructuralDeltaError) as e:
        StateResolver(s,'Проза.',text,turn_id=1,**resolver_options(s,text,contract_version=7)).resolve(raw)
    rows=e.value.diagnostics('repair');codes={r['code'] for r in rows}
    assert {'camera_invalid','player_action_source_invalid'}<=codes
    assert 'movement_endpoint_invalid' in codes,rows
    fb=c.feedback(rows,p)
    schema=repair_schema(input_schema(7,'actor'),fb)
    assert 'observer_location_id' not in schema['properties']['sections']['properties']['scene']['properties']
    replacement=deepcopy(p['scene_steps'][0]);replacement['endpoint']='park';replacement['input_source']['quote']=text
    fixed=dict(candidate_hash=json.loads(fb)['candidate_hash'],replacements=[replacement],sections=dict(scene={}),reason='Исправлен связанный маршрут и источник; снята аннотация камеры.')
    raw=c.parse(fixed,defer_errors=True)
    result=StateResolver(s,'Проза.',text,turn_id=1,**resolver_options(s,text,contract_version=7)).resolve(raw)
    assert result.state['characters']['a']['location_id']=='park'
    assert raw.semantic_candidate['scene_steps'][1]==p['scene_steps'][1]


def test_v7_schema_addresses_group_duplicates_and_missing_nested_fact():
    from test_scene_steps255 import fixture
    from backend.runtime_v3.scene_steps import validate
    s,_=fixture()
    p=dict(scene=dict(elapsed_minutes=1),scene_steps=[
        dict(id='trip',kind='movement',actor_ids=['b','b'],assertion='completed_arrival',endpoint='park',text='Путь.'),
        dict(id='news',kind='information',source_actor_id='b',medium='conversation',text='Новость.',claims=[dict(fact={},perceived_by=['a'],assertion='testimony',status='known')])])
    with pytest.raises(StructuralDeltaError) as e:validate(p,s,version=7)
    rows=e.value.diagnostics('repair')
    assert any(r.get('path')=='scene_steps[0].actor_ids' for r in rows)
    assert any(r.get('path')=='scene_steps[1].claims[0].fact.text' for r in rows)


def test_v7_lta_npc_arrival_keeps_player_camera_and_private_knowledge():
    from test_long_term_advance import fixture
    from backend.runtime_v3.long_term import plan,run
    from backend.runtime_v3.models import Thread
    before=fixture();s=before['world_state']
    s['threads']['education']=Thread(id='education',description='Учёба',character_ids=['c'],relevance=1).model_dump()
    request=dict(amount=1,unit='months',max_llm_calls=2)
    cause=next(c for c in plan(before,request).candidates if c.source_id=='education')
    p=dict(scene=dict(elapsed_minutes=0),locations=[dict(id='new_school',name='Школа',evidence='Тестовый контроль')],scene_steps=[
        dict(id='go',kind='movement',actor_ids=['c'],assertion='completed_arrival',endpoint='new_school',text='c самостоятельно приехал в школу.',advance_candidate_ids=[cause.id]),
        dict(id='notice',kind='information',source_actor_id='c',medium='discovery',text='c прочёл объявление.',advance_candidate_ids=[cause.id],claims=[dict(fact=dict(text='Занятия начинаются в среду.'),perceived_by=['c'],assertion='observation',status='known')])])
    stages=[]
    def generate(stage,messages,*args,**kwargs):
        stages.append(stage)
        return [json.dumps(p) if 'extraction' in stage else 'c самостоятельно приехал в школу и прочёл объявление.']
    after,batch,report=run(before,request,generate=generate,config=dict(_extraction_contract=7,context_length=65536))
    assert report['accepted'],report['diagnostics']
    assert stages==['long_term_narrative','long_term_extraction']
    assert after['world_state']['characters']['c']['location_id']=='new_school'
    assert after['world_state']['characters']['a']['location_id']==s['characters']['a']['location_id']
    assert after['world_state']['camera']==s['camera']
    assert len(batch['movements'])==1
    assert len(batch['knowledge_acquisitions'])==1
    assert batch['knowledge_acquisitions'][0]['actor_id']=='c'


def test_group_return_route_leaves_nontraveller_and_preserves_order():
    from test_scene_steps255 import fixture
    s,_=fixture();text='Иду с b в парк, потом возвращаюсь домой.'
    p=dict(scene=dict(elapsed_minutes=3),scene_steps=[
        dict(id='out',kind='movement',actor_ids=['a','b'],assertion='completed_arrival',endpoint='park',text='Пришли.',input_source=dict(quote='Иду с b в парк',meaning='preserved')),
        dict(id='npc',kind='movement',actor_ids=['c'],assertion='departure',endpoint=None,text='c самостоятельно уходит.'),
        dict(id='back',kind='movement',actor_ids=['a','b'],assertion='completed_arrival',endpoint='home',text='Вернулись.',input_source=dict(quote='возвращаюсь домой',meaning='preserved'))])
    out=StateResolver(s,'Проза.',text,turn_id=1,**resolver_options(s,text,contract_version=7)).resolve(p)
    assert [out.state['characters'][a]['location_id'] for a in ['a','b','c']]==['home','home',None]
    assert [e['order'] for e in out.history['events']]==[0,1,2]
    assert len(out.history['movements'])==5
    assert sum(bool(m.get('player_action')) for m in out.history['movements'])==2
    assert out.state['knowledge']==s['knowledge']


def test_conversation_on_earlier_trip_cannot_anchor_departed_npc_situation():
    from test_scene_steps255 import fixture
    s,_=fixture();text='Иду с b в парк.'
    p=dict(scene=dict(elapsed_minutes=3),scene_steps=[
        dict(id='trip',kind='movement',actor_ids=['a','b'],assertion='completed_arrival',endpoint='park',text='Дошли.',input_source=dict(quote=text,meaning='preserved')),
        dict(id='talk',kind='interaction',actor_id='b',target_ids=['a'],outcome='completed',during_step_id='trip',text='Говорит по пути.'),
        dict(id='away',kind='movement',actor_ids=['b'],assertion='departure',endpoint=None,text='b затем уходит в неизвестном направлении.')],
        character_changes=[dict(id='b',situation='Всё ещё разговаривает с a в пути.',source_event_id='talk',evidence='Контроль')])
    out=StateResolver(s,'Проза.',text,turn_id=1,**resolver_options(s,text,contract_version=7)).resolve(p)
    assert out.state['characters']['b']['location_id'] is None
    assert out.state['characters']['b']['situation']==s['characters']['b']['situation']
    assert len(out.history['events'])==3


def test_independent_actor_routes_survive_an_ambiguous_route_for_diagnostics():
    from test_scene_steps255 import fixture
    s,_=fixture();text='Иду в парк и возвращаюсь домой.'
    p=dict(scene=dict(elapsed_minutes=3,visible_character_ids=['b']),scene_steps=[
        dict(id='out',kind='movement',actor_ids=['a'],assertion='completed_arrival',endpoint='park',text='Идёт.',input_source=dict(quote='Иду в парк',meaning='preserved')),
        dict(id='back',kind='movement',actor_ids=['a'],assertion='completed_arrival',endpoint='home',text='Возвращается.',timing='simultaneous',input_source=dict(quote='Не было во вводе.',meaning='preserved')),
        dict(id='npc',kind='movement',actor_ids=['b'],assertion='completed_arrival',endpoint='unknown',text='Приходит.')])
    resolver=StateResolver(s,'Проза.',text,turn_id=1,**resolver_options(s,text,contract_version=7))
    with pytest.raises(StructuralDeltaError) as e:resolver.resolve(p)
    codes={r['code'] for r in e.value.diagnostics('repair')}
    assert {'camera_actor_missing','movement_ambiguous','movement_endpoint_invalid','player_action_source_invalid'}<=codes
    assert not resolver.history.movements
    assert resolver.state['characters']['a']['location_id']=='home'
    assert resolver.state['characters']['b']['location_id']=='home'
