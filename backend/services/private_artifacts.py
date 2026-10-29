"""Typed Narrative transport for historical worlds, never an in-prose delimiter.

The provider's single forced tool result is buffered and validated before ANY
bytes are published. Modern/plain Narrative keeps its original wire contract.
"""
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class LetterArtifact(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: str = Field(min_length=1, max_length=100)
    type: Literal['letter']
    channel: Literal['LETTER', 'COURIER_LETTER', 'TELEGRAM']
    sender_id: str
    recipient_id: str
    content: str = Field(min_length=1, max_length=4000)


class NarrativeResult(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    narrative: str = Field(min_length=1)
    artifacts: list[LetterArtifact] = Field(max_length=16)


def enabled(state):
    return any(state['meta']['communication'].get(k) for k in ('letter', 'courier', 'telegram')) or any(e['channel'] in ('LETTER','COURIER_LETTER','TELEGRAM') for e in state.get('remote_events',{}).values())


CONTRACT = ('Use publish_narrative exactly once for this historical-channel world. '
    'narrative contains ONLY the public scene, never the contents of sealed correspondence. '
    'artifacts holds private letters authored by NPCs during this same generation, including off-camera writing. '
    'Use stable local artifact IDs, canonical sender/recipient IDs and the enabled channel. '
    'Do not author a voluntary letter for the controlled actor. No invented letters on delivery or reading. '
    'Use an empty artifacts list when nobody writes a letter. SMS/chat and CallScene retain their semantics. '
    'Delivery is not reading. Only Runtime determines delivery. A reply is optional. '
    'Never put private contents in narration, choices, metadata, error text or tool-call names.')


def tool_spec():
    return {'type': 'function', 'function': {'name': 'publish_narrative',
            'description': CONTRACT, 'parameters': NarrativeResult.model_json_schema()}}


def parse(arguments):
    try:
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result: raise ValueError('duplicate key')
                result[key] = value
            return result
        value = NarrativeResult.model_validate(json.loads(arguments, object_pairs_hook=unique))
        if len({a.id for a in value.artifacts}) != len(value.artifacts):
            raise ValueError('duplicate ID')
        if not value.narrative.strip() or any(not a.content.strip() for a in value.artifacts):
            raise ValueError('empty text')
        return value
    except (ValidationError, ValueError):
        # Pydantic errors can echo the private input; only this static code escapes.
        raise ValueError('private_artifact_payload_invalid') from None


def metadata(artifacts):
    return [{k: v for k, v in a.items() if k != 'content'} for a in artifacts]


def author_context(state):
    """Bounded GM input, not a public projection or Character Knowledge grant."""
    from backend.runtime_v3.remote_models import HISTORICAL_CHANNELS
    controlled = state['camera']['controlled_actor_id']
    rows = []
    for e in sorted(state['remote_events'].values(), key=lambda e: (-e['world_time'], e['id'])):
        if e['channel'] not in HISTORICAL_CHANNELS:
            continue
        row = {k: e[k] for k in ('id','channel','sender_id','recipient_ids','status','read_by','delivered_to')}
        if controlled == e['sender_id'] or controlled in e['read_by'] or any(a != controlled for a in e['delivered_to']):
            row['content'] = e['content']
        rows.append(row)
        if len(rows) == 6: break
    return {'role':'system', 'content':CONTRACT + '\nGM-only correspondence: ' + json.dumps(rows,ensure_ascii=False) +
        '\nNPCs may explicitly read delivered letters, or leave them unread. An optional response must be a new private artifact. '
        'Never reveal NPC-only text in public narrative. Reference existing letter IDs when depicting reads; never duplicate sends.'}


def extraction_context(artifacts):
    return {'role':'system', 'content':'Author-created private artifacts: '+json.dumps(metadata(artifacts),ensure_ascii=False)+
        '. Bind every completed send using remote_events.artifact_id, channel, sender_id, recipient_ids. '
        'Never invent or copy content. For an established NPC read use existing_event_id, its sender/recipients/channel and reader_id. '
        'Only delivered letters can be read. Never grant recipient Knowledge on send/delivery or invent controlled actor reading.'}


def generate_result(generate, stage, messages, limit, temperature, state, **kwargs):
    artifacts = []
    options = {}
    if enabled(state):
        from copy import copy
        messages = copy(messages)
        messages.append(author_context(state))
        options['on_private_result'] = artifacts.extend
    narrative = ''.join(generate(stage, messages, limit, temperature, **kwargs, **options))
    return narrative, artifacts
