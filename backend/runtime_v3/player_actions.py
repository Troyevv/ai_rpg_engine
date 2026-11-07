"""Player action provenance within Extraction, not a second intent interpreter.

Extraction resolves language/aliases and reviews the *unchanged* Narrative. Runtime
compares typed identities and outcomes; it never parses names or prose semantics.
"""
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
    target_mode: Literal['interaction', 'reference'] = 'interaction'


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
PLAYER ACTION REVIEW: ALL Narrative/input; changed act/target/consent or impossible completion=violated;
unprovable=uncertain. Never launder/delete/downgrade. NPCs independent.
Acts: IDs/exact full quotes. Event: initiator actor_id, ONE player_action_id,
same player_evidence; no mixed/other quotes. Split independent acts into Events.
Targets: attempted keeps; partial=subset; deferred/not_performed may actual=[]; untargeted=[].
Event targets=subset actual; union covers actual. completed_interaction needs completed.
Completed contact needs presence/call/bound delivery, marker or not; no reply needed.
reference=noncontact: watch Vera=reference; ask Vera=interaction; ask doctor to help Vera targets doctor.
Silence isn't delivery. Impossible Narrative contact=violated; JSON-only participant error=repair JSON.
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
        intended, actual = set(action.target_ids), set(action.narrative_target_ids)
        partial_subset = action.outcome == 'partial' and actual <= intended
        deferred = action.outcome in ('deferred', 'not_performed') and not actual
        if action.meaning != 'preserved' or (actual != intended and not (partial_subset or deferred)):
            narrative_conflict(**path)
        actions[action.id] = action
    return actions



def validate_targets(resolver, actions):
    # All domain handlers have finished, including newly established objects,
    # threads and NPCs. Only accepted canonical entities can prove a target.
    known = set().union(*(set(resolver.state.get(section, {})) for section in
                         ('characters', 'locations', 'possessions', 'organizations', 'facts', 'threads', 'scheduled_events')))
    for i, action in enumerate(actions.values()):
        for ids in (action.target_ids, action.narrative_target_ids):
            if len(ids) != len(set(ids)) or any(cid not in known for cid in ids):
                fatal('Цель действия должна ссылаться на принятую каноническую сущность.',
                      'player_action_target_invalid', repairable=True,
                      section='player_agency', path=f'player_agency.actions[{i}]')


def narrative_conflict(**path):
    fatal('Повествование изменило или не подтвердило выбранное действие игрока. '
          'Ход не сохранён. Отмените его и отправьте исходное действие заново.',
          'narrative_agency_conflict', repairable=False, action='reauthor_narrative', **path)


def event_provenance(resolver, item, event, index, actions):
    """Check independent provenance fields together; never infer literary intent."""
    from backend.runtime_v3.resolver import normalized
    from backend.services.world_delta_errors import StructuralDeltaError
    reference = item.get('player_action_id')
    completed = item.get('player_assertion') == 'completed_interaction'
    if reference is None and not completed and not (resolver.protected_actor_id and item.get('actor_id') == resolver.protected_actor_id):
        return
    errors = []
    action = actions.get(reference) if isinstance(reference, str) else None
    sources = [item['id']] + ([reference] if isinstance(reference, str) else [])

    def invalid(field, reason, detail, *, completion=False):
        errors.append(StructuralDeltaError(
            f'Event {item["id"]}: {detail}',
            'player_action_completion_invalid' if completion else 'player_action_event_mismatch',
            repairable=True, section='events', index=index, field=field,
            entity=item['id'], source_ids=sources, reason=reason))

    if reference is None:
        invalid('player_action_id', 'missing_player_action_id', 'отсутствует player_action_id; укажите ID исходного PlayerAction.')
    elif action is None:
        invalid('player_action_id', 'unknown_player_action_id', 'player_action_id не ссылается на PlayerAction этого ввода.')
    if (resolver.mode != 'turn' or item.get('actor_id') != resolver.protected_actor_id
            or resolver.protected_actor_id not in event['participants']):
        invalid('actor_id', 'wrong_actor', 'actor_id и participants должны подтверждать управляемого автора действия.')
    if event['medium'] == 'message' and event.get('author_id') != resolver.protected_actor_id:
        invalid('author_id', 'wrong_actor', 'author_id сообщения не соответствует автору PlayerAction.')
    targets = item.get('target_ids')
    valid_targets = (isinstance(targets, list) and all(isinstance(t, str) for t in targets)
                     and len(targets) == len(set(targets)))
    if not valid_targets or action and not set(targets) <= set(action.narrative_target_ids):
        invalid('target_ids', 'target_ids_mismatch', 'target_ids должны быть собственным подмножеством narrative_target_ids связанного PlayerAction.')
    quote = item.get('player_evidence')
    if not isinstance(quote, str) or not normalized(quote):
        invalid('player_evidence', 'missing_player_evidence', 'отсутствует player_evidence; скопируйте точную цитату связанного PlayerAction.', completion=completed)
    elif action and normalized(quote) != normalized(action.player_evidence):
        value = normalized(quote)
        other = [a for a in actions.values() if a.id != action.id]
        if any(value == normalized(a.player_evidence) for a in other):
            reason, detail = 'other_action_evidence', 'player_evidence принадлежит другому PlayerAction.'
        elif (normalized(action.player_evidence) in value
              and any(normalized(a.player_evidence) in value for a in other)):
            reason, detail = 'multiple_action_evidence', 'player_evidence охватывает несколько отдельных PlayerActions.'
        else:
            reason, detail = 'action_evidence_mismatch', 'player_evidence не совпадает с цитатой связанного PlayerAction.'
        invalid('player_evidence', reason, detail + ' Используйте только его точную цитату; несколько действий требуют отдельных Events.', completion=completed)
    if completed and action:
        if action.outcome != 'completed':
            invalid('player_assertion', 'outcome_not_completed', 'completed_interaction требует outcome=completed в исходном действии; не меняйте исход ради проверки.', completion=True)
        if valid_targets and not (set(targets) & resolver.state['characters'].keys()) <= set(event['participants']):
            invalid('participants', 'target_participation_missing', 'completed_interaction требует участия собственных адресатов Event.', completion=True)
    if errors:
        raise StructuralDeltaError.combine(errors)
    event.update(actor_id=resolver.protected_actor_id, target_ids=list(targets),
                 player_action=action.model_dump(), player_evidence=action.player_evidence)
    if completed:
        event.update(player_interaction=True, player_evidence=action.player_evidence)


def validate_completions(resolver, actions, events, indices, written_sources):
    """Validate typed completion after canonical presence/Remote, before Knowledge.

    Presence owns the shared movement timeline and call endpoints. This gate only
    binds completed delivery to those accepted participants, never calculates a
    second geography or interprets prose. A written artifact's author is not a
    live endpoint, so messages additionally require an explicit delivery binding.
    """
    covered = {}
    for eid, event in events.items():
        provenance = event.get('player_action')
        if not provenance:
            continue
        action = actions[provenance['id']]
        # Only this Event's explicit targets count. Other participants/witnesses
        # cannot supply delivery for a different part of the grouped action.
        targets = set(event['target_ids']) & resolver.state['characters'].keys()
        communicative = event['medium'] in ('conversation', 'testimony', 'message') or event.get('interaction_channel') in ('physical', 'call')

        def reject(reason):
            fatal(f'Действие {action.id}: {reason} Сверьте outcome с неизменным Narrative; '
                  'не удаляйте Event/адресата и не выдумывайте канал. Если Narrative явно '
                  'завершает невозможный контакт, player_agency.status=violated (нужен новый Narrative).',
                  'player_action_completion_invalid', repairable=True, section='events',
                  index=indices[eid], field='player_action_id', entity=eid,
                  source_ids=[eid, action.id, *sorted(targets)])

        if targets and action.target_mode == 'reference' and communicative:
            reject('target_mode=reference несовместим с Event общения/контакта.')
        if action.outcome == 'completed' and targets and action.target_mode == 'interaction':
            missing = targets - set(event['participants'])
            if missing:
                reject('outcome=completed не подтверждён участием адресатов: '+', '.join(sorted(missing))+'.')
            if event['medium'] == 'message' and event.get('interaction_channel') != 'physical':
                written = written_sources.get(eid)
                if (not written or written['sender_id'] != resolver.protected_actor_id
                        or written['status'] != 'delivered'
                        or not targets <= set(written['delivered_to'])):
                    reject('outcome=completed требует принятого источника доставки сообщения всем адресатам; ответ/чтение не обязательны.')
        covered.setdefault(action.id, set()).update(event['target_ids'])
    for i, action in enumerate(actions.values()):
        required = set(action.narrative_target_ids)
        requires_contact = (action.outcome == 'completed' and action.target_mode == 'interaction'
                            and required & resolver.state['characters'].keys())
        missing = required - covered.get(action.id, set())
        # Preserve noncontact/untargeted actions without an Event. Once Events
        # reference an action, their own targets must cover its actual scope.
        if missing and (requires_contact or action.id in covered):
            fatal(f'Действие {action.id}: {action.outcome} не подтверждён принятыми Events для адресатов: '
                  + ', '.join(sorted(missing)) + '. '
                  'Не удаляйте Event для обхода проверки; классифицируйте исход по неизменному Narrative. '
                  'Пассивное наблюдение/упоминание использует target_mode=reference; обращение требует interaction. '
                  'Не создавайте фиктивный контакт для наблюдения.',
                  'player_action_completion_invalid' if action.outcome == 'completed' else 'player_action_event_mismatch',
                  repairable=True, section='player_agency',
                  path=f'player_agency.actions[{i}].outcome', source_ids=[action.id, *sorted(missing)])
