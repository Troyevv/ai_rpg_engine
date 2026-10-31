"""Text-channel author context is personal, not a shared physical scene."""
import json
from copy import deepcopy
from backend.runtime_v3.group_planning import context, opportunities, reaction_context, GROUP_TEXT_CONTEXT
from backend.runtime_v3.remote_initiative import stage, planning_context
from backend.services.communication_profile import catalog
from backend.runtime_v3.remote_authoring import DIGITAL_TEXT_STYLE
from backend.runtime_v3.models import PersonalityProfile, PersonalityItem
from test_group152 import group, provider
from test_remote_communication import command


def test_reaction_and_autonomy_share_explicit_text_channel_without_physical_inference():
    snapshot, gid = group()
    state = snapshot['world_state']
    state['characters']['b']['location_id'] = 'away'
    state['characters']['b']['personality'] = PersonalityProfile(items={'voice':PersonalityItem(field='communication',text='Говорит образно, любит грубые шутки')}).model_dump()
    state['characters']['c']['location_id'] = 'secret-place'
    state['locations']['secret-place'] = dict(state['locations']['away'], id='secret-place', name='Закрытое место')
    # Group membership must never manufacture mutual perception.
    state['camera']['present_character_ids'] = ['a']
    snapshot['character_cards'] += [dict(id='c', fields={'Стиль общения':'Сухой юмор', 'Характер':'Упрямый'})]
    original = deepcopy(snapshot)
    ctx = context(snapshot, opportunities(state))[0]
    assert ctx['channel'] == 'TEXT_MESSAGE'
    assert ctx['communication_profile'] == state['meta']['communication']
    actors = {a['id']:a for a in ctx['actors']}
    assert actors['b']['personal_context'] == dict(own_location_id='away',present_character_ids=[])
    assert actors['c']['personal_context']['own_location_id'] == 'secret-place'
    assert actors['c']['legacy_voice']['Стиль общения'] == 'Сухой юмор'
    assert actors['b']['personality']['items']['voice']['text'] == 'Говорит образно, любит грубые шутки'
    assert actors['c']['personality'] is None
    assert 'secret-place' not in json.dumps(actors['b'])
    assert snapshot == original
    sent = command(snapshot, 'send', conversation_id=gid, content='Привет!')
    source = list(sent['world_state']['remote_events'])[-1]
    messages = reaction_context(sent, source)
    assert GROUP_TEXT_CONTEXT in messages[0]['content']
    assert json.loads(messages[1]['content'])['source_message']['channel'] == 'TEXT_MESSAGE'
    assert 'JSON' in messages[0]['content']
    gen, calls = provider(gid, question=False)
    after = stage(original, gen, 'channel-autonomy')
    assert GROUP_TEXT_CONTEXT in calls[0][1][0]['content']
    assert len(calls) == 2
    assert len(after['world_state']['remote_events']) == 3
    assert after['world_state']['camera'] == original['world_state']['camera']


def test_personal_knowledge_read_history_and_real_copresence_remain_separate():
    snapshot, gid = group(); state = snapshot['world_state']
    state['camera']['present_character_ids'] = ['a','b']
    state['characters']['b']['location_id'] = state['camera']['location_id']
    state['characters']['c']['location_id'] = state['camera']['location_id']
    state['facts']['secret'] = dict(id='secret',text='Приватная новость B',character_ids=['b'])
    state['knowledge']['b:secret'] = dict(actor_id='b',fact_id='secret',status='known')
    snapshot = command(snapshot, 'send', conversation_id=gid, content='Ещё не прочитано')
    ctx = context(snapshot, opportunities(snapshot['world_state']))[0]
    actors = {a['id']:a for a in ctx['actors']}
    assert actors['b']['personal_context']['present_character_ids'] == ['a','b']
    assert actors['c']['personal_context']['present_character_ids'] == []
    assert any(k['text']=='Приватная новость B' for k in actors['b']['knowledge'])
    assert not actors['c']['knowledge']
    assert all(not a['history'] for a in actors.values())
    assert 'when supported' in GROUP_TEXT_CONTEXT


def test_profile_controls_group_availability_and_does_not_rewrite_other_channels():
    snapshot, gid = group()
    original = planning_context(snapshot, [])[0]['content']
    for preset in ('letters','1939','fantastic','none'):
        snapshot['world_state']['meta']['communication'] = catalog()[preset]
        assert not opportunities(snapshot['world_state'])
        assert planning_context(snapshot, [])[0]['content'] == original.replace(DIGITAL_TEXT_STYLE, '')
    snapshot['world_state']['meta']['communication'] = dict(catalog()['custom'],text_message=True,
        delivery_policy={'text_message':'delayed'})
    ctx = context(snapshot, opportunities(snapshot['world_state']))[0]
    assert ctx['communication_profile']['delivery_policy']['text_message'] == 'delayed'
    assert ctx['communication_profile']['preset'] == 'custom'
