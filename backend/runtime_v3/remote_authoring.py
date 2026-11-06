"""Disposable author context shared by direct and group communication.

Existing Character/Relationship/CommunicationProfile remain the sources of truth.
No style decisions, text transformations or additional generation stages live here.
"""
from copy import deepcopy
import json
from backend.runtime_v3.personality import context_profile


DIGITAL_TEXT_STYLE = (
    'For TEXT_MESSAGE only, use the CommunicationProfile technology and setting to decide whether modern digital '
    'writing fits; never import messenger habits into historical letters, couriers, telegrams or spoken calls. '
    'Write messages people would actually send, not literary dialogue merely split into bubbles. '
    'You choose each speaker\'s written voice from their personality/legacy_voice, directed relationships, '
    'own emotion and situation, and what they know. Keep the same recognizable person as in Narrative while '
    'adapting naturally to the channel and audience: intimacy or conflict in private, social dynamics and '
    'the full membership in groups. Another speaker\'s personal context is not shared Knowledge. '
    'Where appropriate, emoji, abbreviations, colloquialisms, slang, profanity, informal punctuation, varied '
    'message lengths and personal writing habits can convey emotion. These are optional expressive choices, '
    'not templates: no emoji is equally valid; no quotas, probabilities or uniform style. A serious situation '
    'may change familiar habits. Do not infer writing style solely from gender, age or other stereotypes. '
)


def text_style_instructions(profile):
    return DIGITAL_TEXT_STYLE if profile.get('text_message') else ''


def speaker_context(snapshot, actor_id, audience):
    state = snapshot['world_state']; actor = state['characters'][actor_id]
    card = next((c for c in snapshot.get('character_cards', []) if c['id'] == actor_id), {})
    return dict(personality=context_profile(actor),
        legacy_voice=({k:v for k,v in card.get('fields', {}).items() if k in ('Характер','Стиль общения')}
                      if actor.get('personality') is None else {}),
        relationships=[deepcopy(r) for r in state['relationships'].values()
                       if r['source_id'] == actor_id and r['target_id'] in audience][:8],
        emotion=actor.get('emotion', ''), situation=actor.get('situation', ''))


def option_audience(state, actor_id, options):
    """Only actual offered interlocutors/members, never an omniscient directory."""
    from backend.runtime_v3.remote import members, participants
    audience = set()
    for option in options:
        if option['actor_id'] != actor_id:
            continue
        for eid in [option.get('event_id'), *option.get('basis_ids', [])]:
            event = state['remote_events'].get(eid)
            if event:
                audience.update(participants(event))
        for path in option.get('paths', []):
            group = state['conversations'].get(path.get('conversation_id'))
            contact = state['contacts'].get(path.get('contact_id'))
            if group: audience.update(members(group))
            if contact and contact.get('character_id'): audience.add(contact['character_id'])
    return audience - {actor_id}


def pre_style_context(messages, snapshot, *, group):
    """Exact prior prompt shape for accepted checkpoints, not a second author.

    The original job snapshot supplies the former bounded personality list.
    Source/history/Knowledge and all unrelated fields must still match on replay.
    """
    previous = deepcopy(messages)
    previous[0]['content'] = previous[0]['content'].replace(DIGITAL_TEXT_STYLE, '', 1)
    data = json.loads(previous[1]['content'])
    if group:
        for item in data['groups']:
            for actor in item['actors']:
                actor.pop('emotion', None); actor.pop('situation', None)
                actor['relationships'] = [r for r in actor['relationships'] if r['target_id'] in item['actor_ids']]
    else:
        data.pop('communication_profile', None)
        for actor in data['actors']:
            for field in ('legacy_voice', 'relationships', 'emotion'):
                actor.pop(field, None)
            actor['situation'] = actor['situation'][:400]
            character = snapshot['world_state']['characters'][actor['id']]
            actor['personality'] = [dict(field=i['field'], text=i['text'][:200])
                for i in list((character.get('personality') or {}).get('items', {}).values())[:6]]
    previous[1]['content'] = json.dumps(data, ensure_ascii=False)
    return previous
