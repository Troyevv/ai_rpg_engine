"""v3 contract tests: no live state depends on historical provenance."""
from copy import deepcopy
from backend.runtime_v3.lifecycle import active_texts
import pytest
from backend.runtime_v3.models import WorldStateV3, Character, Location, assert_world_state_v3_invariants
from backend.runtime_v3.resolver import StateResolver
from backend.runtime_v3.history import audit_world_history
from backend.services.world_delta_errors import StructuralDeltaError

QUOTE='Я злюсь на неё. Люда рассказала о письме. Мы вышли в коридор.'


def initial():
    return WorldStateV3(camera=dict(location_id='room',present_character_ids=['a','b'],controlled_actor_id='a'),
        characters={c:Character(id=c,location_id='room',goals=['найти сестру']) for c in ('a','b','c')},
        locations={c:Location(id=c,name=c) for c in ('room','hall')}).model_dump()


def payload():
    return dict(final_scene=dict(location_id='hall',present_character_ids=['a'],elapsed_minutes=5),
        facts=[dict(id='f',text='Есть письмо',evidence=QUOTE)],
        events=[dict(id='e',text='Разговор',participants=['a','b'],witnesses=['a','b'],fact_ids=['f'],medium='conversation',evidence=QUOTE)],
        knowledge_gained=[dict(actor_id='a',fact_id='f',source_event_id='e',evidence=QUOTE)])


def test_final_camera_and_offcamera_preservation():
    result=StateResolver(initial(),QUOTE,'').resolve(payload())
    assert result.state['characters']['a']['location_id']=='hall'
    assert result.state['characters']['b']['location_id']=='room'
    assert result.history['movements'][0]['from_location_id']=='room'
    assert result.state['knowledge']['a:f']==dict(actor_id='a',fact_id='f',status='known')
    assert not audit_world_history(result.history)


@pytest.mark.parametrize('damage',['witness','fact','source','medium'])
def test_invalid_new_knowledge_is_optional(damage):
    p=payload()
    if damage=='witness':p['events'][0]['witnesses']=[]
    if damage=='fact':p['events'][0]['fact_ids']=[]
    if damage=='source':p['knowledge_gained'][0]['source_event_id']='missing'
    if damage=='medium':p['events'][0]['medium']='action'
    result=StateResolver(initial(),QUOTE,'').resolve(p)
    assert not result.state['knowledge']
    assert result.state['facts']['f']
    assert result.warnings[0]['code']=='knowledge_path_invalid'


def test_old_knowledge_survives_deleted_history_and_next_turn():
    first=StateResolver(initial(),QUOTE,'').resolve(payload())
    damaged=deepcopy(first.history);damaged['events']=[]
    assert audit_world_history(damaged)
    second=StateResolver(first.state,'Пауза.','').resolve(dict(final_scene=dict(location_id='hall',present_character_ids=['a'])))
    assert second.state['knowledge']==first.state['knowledge']


def test_mixed_local_drops_do_not_lose_other_changes():
    p=payload();p['knowledge_gained'][0]['source_event_id']='missing'
    p['character_changes']=[dict(id='a',situation='У двери',emotion='ревнует',intentions=['заставить'],evidence=QUOTE),dict(id='b',situation='У окна',evidence=QUOTE)]
    p['relationship_changes']=[dict(source_id='a',target_id='b',context='Недоверие',dimensions=dict(trust=55,sympathy=20),evidence=QUOTE)]
    result=StateResolver(initial(),QUOTE,'Я подхожу к окну.').resolve(p)
    assert result.state['characters']['a']['situation']=='У двери'
    assert result.state['characters']['a']['emotion']==''
    assert active_texts(result.state['characters']['a']['goals'])==['найти сестру']
    assert result.state['characters']['b']['situation']=='У окна'
    assert result.state['relationships']['a:b']['dimensions']=={'trust':55}
    assert len(result.warnings)==4 and result.history['events']


@pytest.mark.parametrize('field,value,player,evidence',[
    ('emotion','злится','Я злюсь на неё.','Я злюсь на неё'),
    ('intentions',['поговорить с Людой завтра'],'Решаю завтра поговорить с Людой.',['Решаю завтра поговорить с Людой'])])
def test_player_source_is_accepted(field,value,player,evidence):
    p=payload();p['character_changes']=[dict(id='a',**{field:value},player_evidence={field:evidence})]
    result=StateResolver(initial(),QUOTE,player).resolve(p)
    actual=result.state['characters']['a'][field]
    assert (actual if field=='emotion' else active_texts(actual))==value


def test_offcamera_ambiguous_route_fatal():
    p=payload();p['movements']=[dict(actor_id='b',to_location_id=lid,evidence=QUOTE) for lid in ('room','hall')]
    with pytest.raises(StructuralDeltaError,match='неоднозначное'):
        StateResolver(initial(),QUOTE,'').resolve(p)


def test_current_corruption_still_fatal():
    state=initial();state['characters']['a']['location_id']='missing'
    with pytest.raises(StructuralDeltaError): assert_world_state_v3_invariants(state)


def test_patch_cannot_apply_to_other_before():
    result=StateResolver(initial(),QUOTE,'').resolve(payload())
    state=initial();state['characters']['b']['situation']='Другое'
    with pytest.raises(StructuralDeltaError): result.patch.apply(state)


def test_ambiguous_duplicate_character_patch_is_fatal():
    p=payload();p['character_changes']=[dict(id='b',situation=s,evidence=QUOTE) for s in ('Здесь','Там')]
    with pytest.raises(StructuralDeltaError,match='повторный canonical'):
        StateResolver(initial(),QUOTE,'').resolve(p)


def test_new_knowledge_never_uses_event_from_prior_turn():
    first=StateResolver(initial(),QUOTE,'').resolve(payload())
    p=dict(final_scene=dict(location_id='hall',present_character_ids=['a']),knowledge_gained=[dict(actor_id='b',fact_id='f',source_event_id=first.history['events'][0]['id'],evidence=QUOTE)])
    second=StateResolver(first.state,QUOTE,'').resolve(p)
    assert 'b:f' not in second.state['knowledge']
    assert second.state['knowledge']['a:f']==first.state['knowledge']['a:f']
