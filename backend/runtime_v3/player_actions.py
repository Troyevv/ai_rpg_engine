"""Player action provenance within Extraction, not a second intent interpreter.

Extraction resolves language/aliases and reviews the *unchanged* Narrative. Runtime
compares typed identities and outcomes; it never parses names or prose semantics.
"""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.runtime_v3.models import fatal


class PlayerAction(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: str = Field(min_length=1)
    player_evidence: str = Field(min_length=1)
    target_ids: list[str]
    narrative_target_ids: list[str]
    outcome: Literal['completed', 'partial', 'attempted', 'deferred', 'not_performed']
    meaning: Literal['preserved', 'changed', 'uncertain']


class PlayerAgencyReview(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    status: Literal['preserved', 'violated', 'uncertain']
    actions: list[PlayerAction]


NARRATIVE_CONTRACT = '''
PLAYER ACTION AGENCY: preserve the player's chosen addressee, target and meaning.
An unavailable addressee does not authorize addressing someone else. Describe an
unsuccessful attempt/no reply, or an independent NPC response, without inventing a
new choice for the controlled actor. Mentioning someone is not addressing them.
Do not invent presence, calls or messages. Group/partial/deferred actions retain
their chosen targets. NPC initiative is welcome; it never substitutes player agency.
'''

EXTRACTION_CONTRACT = '''
PLAYER ACTION REVIEW: player_agency reviews input + controlled actor.
Review ALL acts in unchanged Narrative, even without Events.
Substitution/invented decision/consent: status=violated; ambiguity=uncertain.
Never fix prose via JSON or relabel player acts as NPC initiative.
actions: id per input act; full player_evidence; target_ids from INPUT;
narrative_target_ids/outcome/meaning from actual act. Resolve aliases/pronouns/groups from context. Unresolved=uncertain; untargeted=[]; no player act=actions[].
Absent addressee: attempt keeps intended target, no invented participant/channel.
Deferred/not_performed may have narrative_target_ids=[]. No reply is no completed exchange.
Events reference player_action_id + actual actor_id/target_ids. completed_interaction
requires completed matching act + same player_evidence, all targets participating.
Other outcomes must not claim completion. Split different acts. NPC initiative: own Event, no player_action_id/assertion.
Quotes prove source, not meaning. Narrative violations reject the whole turn.
'''


def required(state, player_input, kind='turn'):
    return bool(state['camera']['controlled_actor_id'] and player_input.strip()
                and kind not in ('background', 'pov'))


def review(resolver, raw):
    """Run before any domain application, including optional Event salvage."""
    from backend.runtime_v3.resolver import normalized
    value = raw.player_agency
    if value is None:
        if resolver.require_player_agency:
            fatal('Extraction не проверил соответствие Narrative действию игрока.',
                  'player_agency_missing', repairable=True, section='player_agency')
        return {}
    try:
        parsed = PlayerAgencyReview.model_validate(value)
    except ValidationError:
        fatal('Некорректная типизированная проверка действий игрока.',
              'player_agency_invalid', repairable=True, section='player_agency')
    if parsed.status != 'preserved':
        narrative_conflict()
    actions = {}
    for i, action in enumerate(parsed.actions):
        path = dict(section='player_agency', path=f'player_agency.actions[{i}]')
        if (resolver.mode != 'turn' or not resolver.protected_actor_id
                or action.id in actions or not normalized(action.player_evidence)
                or normalized(action.player_evidence) not in normalized(resolver.player_input)):
            fatal('Нет однозначного источника действия в текущем вводе игрока.',
                  'player_action_source_invalid', repairable=True, **path)
        for ids in (action.target_ids, action.narrative_target_ids):
            # Targets can be characters, items, locations, etc., not just addressees.
            known = set().union(*(set(resolver.before.get(section, {})) for section in
                                  ('characters', 'locations', 'items', 'organizations', 'facts', 'threads', 'scheduled_events')))
            if len(ids) != len(set(ids)) or any(cid not in known for cid in ids):
                fatal('Цель действия должна ссылаться на известную каноническую сущность.',
                      'player_action_target_invalid', repairable=True, **path)
        if (action.meaning != 'preserved'
                or set(action.target_ids) != set(action.narrative_target_ids)
                and not (action.outcome in ('deferred', 'not_performed') and not action.narrative_target_ids)):
            narrative_conflict(**path)
        actions[action.id] = action
    return actions


def narrative_conflict(**path):
    fatal('Повествование изменило или не подтвердило выбранное действие игрока. '
          'Ход не сохранён. Отмените его и отправьте исходное действие заново.',
          'narrative_agency_conflict', repairable=False, **path)


def event_provenance(resolver, item, event, index, actions):
    """No completed player interaction from a copied quote or mere participation."""
    from backend.runtime_v3.resolver import normalized
    reference = item.get('player_action_id')
    completed = item.get('player_assertion') == 'completed_interaction'
    if reference is None and not completed:
        return
    path = dict(section='events', index=index, field='player_action_id', entity=item['id'])
    action = actions.get(reference) if isinstance(reference, str) else None
    targets = item.get('target_ids')
    if (action is None or resolver.mode != 'turn'
            or item.get('actor_id') != resolver.protected_actor_id
            or resolver.protected_actor_id not in event['participants']
            or not isinstance(targets, list) or any(not isinstance(t, str) for t in targets)
            or len(targets) != len(set(targets)) or set(targets) != set(action.narrative_target_ids)
            or event['medium'] == 'message' and event.get('author_id') != resolver.protected_actor_id):
        fatal('Event не соответствует автору/целям проверенного действия игрока.',
              'player_action_event_mismatch', repairable=True, **path)
    if completed and (action.outcome != 'completed'
                      or not isinstance(item.get('player_evidence'), str)
                      or normalized(item.get('player_evidence') or '') != normalized(action.player_evidence)
                      or not (set(targets) & resolver.state['characters'].keys()) <= set(event['participants'])):
        fatal('completed_interaction требует выполненного исходного действия с теми же целями.',
              'player_action_completion_invalid', repairable=True, **path)
    event.update(actor_id=resolver.protected_actor_id, target_ids=list(targets),
                 player_action=action.model_dump())
    if completed:
        event.update(player_interaction=True, player_evidence=action.player_evidence)


def retry_allowed(job):
    """A proven/uncertain Narrative violation cannot be repaired by re-extraction."""
    return not any(d.get('code') == 'narrative_agency_conflict'
                   for d in json.loads(job.get('repair_diagnostics_json') or '[]'))
