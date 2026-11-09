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


# Producer version is recorded by the server, never selected by model output.
EXTRACTION_VERSION = 4


class NarrativeAgencyItem(BaseModel):
    """Compact semantic finding, not a reasoning trace or a prose parser."""
    model_config = ConfigDict(extra='forbid', strict=True)
    narrative_evidence: str = Field(min_length=1)
    classification: Literal['authorized', 'execution_detail', 'involuntary',
                            'npc_interpretation', 'unauthorized_choice', 'uncertain', 'incidental_detail']
    player_action_id: str | None


class PlayerAgencyReview(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    actions: list[PlayerAction]
    narrative_audit: list[NarrativeAgencyItem] | None = None
    status: Literal['preserved', 'violated', 'uncertain']


NARRATIVE_CONTRACT = '''
PLAYER ACTION AGENCY: retain meaning/targets, partial/deferred/group too.
Absent addressee: attempt/no reply, no substitute. Mention isn't contact; no invented contact.
An unanswered NPC question stays open: no unchosen player reply/consent/refusal/promise via
speech, gesture, silence or continued activity. NPCs may misread silence, granting no player
choice/commitment. Allow execution detail/involuntary reactions/external consequences.
Keep NPCs and the environment moving; choices stay open.
'''

LEGACY_EXTRACTION_CONTRACT = '''
PLAYER ACTION REVIEW: both directions over WHOLE Narrative, beyond Events:
(1) Account for every input action: meaning, targets, actual outcome.
(2) Find new EXTERNAL speech/reply/consent/refusal (also gestures)/promise/choice absent from
input. Omission from JSON never repairs prose.
Physical detail of an authorized act is allowed, a separate response is not.
Changed act/target/consent, new decision or impossible completion => status=violated;
unprovable => uncertain. Use reauthor/abandon, never deletion/downgrade/fake evidence.
NPC acts remain independent and authorize no EXTERNAL choice.
Action: ID + exact full input quote. Player Event: actual actor_id, ONE player_action_id +
same player_evidence. Split acts; separate player-address/NPC-reply Events. Keep replies,
fact_ids and ALL confirmed acquisitions.
Targets: attempted=chosen; partial=subset; deferred/not_performed may have
actual=[]; untargeted=[]. Event targets subset actual, union=actual. completed_interaction needs
completed action; question needs no reply, silence proves no delivery.
reference=watch Vera; interaction=ask Vera; ask doctor ABOUT Vera targets doctor. Reference
sets match without contact; JSON mismatch is repairable, impossible prose contact is violated.
'''


EXTRACTION_CONTRACT = """
PLAYER ACTION REVIEW: evidence-first, WHOLE prose beyond Events; no reasoning.
actions: all input acts. Only current input authorizes.
narrative_audit: significant acts + NEW replies/consent/refusal/promises/choices (also gestures).
authorized/execution_detail links verified action; involuntary is no choice;
npc_interpretation grants no player decision. Others use null action ID.
unauthorized_choice/changed act or target/impossible contact => violated; uncertain => uncertain.
Audit BEFORE status. Deleting Events cannot repair prose; use reauthor/abandon.
Omit duplicate Event quote; reject explicit conflicts. Keep NPC reply/facts/ALL learning.
partial=subset; attempted=chosen; deferred/not_performed may have actual=[]; untargeted=[].
interaction needs delivery, not reply. Addressing mother ABOUT grandfather targets mother,
not grandfather. Reference targets remain the same mentioned IDs in both target arrays.
For EACH completed/partial interaction emit an Event for the player's delivered act:
actor_id=controlled actor, participants include actor and reached targets,
player_action_id=that action.id, target_ids=subset of that action.narrative_target_ids.
All reached targets must be covered across its Events. An NPC answer is a SEPARATE
Event with its own actor_id; it cannot stand in for the player's question.
Do not attach player_action_id to an NPC reply. Execution details need no invented
new player decision. Use the current action's quote once, in player_evidence.
Arrival Event.order and Movement.order MUST match; farewell precedes arrival.
NarrativeAgencyItem examples: a=verified "Open folder" action:
{"narrative_evidence":"Turns a page","classification":"execution_detail","player_action_id":"a"}
{"narrative_evidence":"Agrees to travel","classification":"unauthorized_choice","player_action_id":null}
"""

CONSEQUENCE_CONTRACT = """
PLAYER AGENCY: preserve input meaning/targets; no unchosen substantial decisions.
Review/audit optional; uncertain/incidental_detail advisory, never domain authority.
No Event per everyday act; NPC replies support ALL heard Knowledge.
Unlinked inventory proves nothing. Canonical player Events require verified PlayerAction;
use schema provenance/targets/delivery/coverage. Omit duplicate quotes; conflicts reject.
No duplicate arrival Event/quote. unauthorized_choice/violated means SIGNIFICANT choice,
not a gesture. Report unsupported substantial outcomes, never delete them to fake success.
NPC acts grant no player consent.
Split compound input by actual actor/targets/channel/location when these differ. A trip toward
someone is reference, not automatically a conversation. Shared PlayerAction is legal for truly
shared consent/targets; its Events inherit ONE full quote. If Event quotes identify distinct
input clauses, use distinct PlayerActions, never join unrelated addresses or fabricate Events.
Strangers need no fake ID/self-target. Arrival proves no contact.
"""




def required(state, player_input, kind='turn'):
    return bool(state['camera']['controlled_actor_id'] and player_input.strip()
                and kind not in ('background', 'pov'))


def resolver_options(state, player_input, kind='turn', contract_version=1, *, time_skip=False):
    """The ordinary production/QA boundary; no caller guesses agency by mode."""
    needed = required(state, player_input, kind)
    return dict(require_player_agency=needed, agency_audit_required=needed and contract_version >= 2,
                consequence_first=contract_version >= 3,
                preserve_scene_locations=contract_version >= 4, choice_grounding_required=contract_version >= 4,
                require_elapsed=kind == 'turn' and not time_skip)


def review(resolver, raw):
    """Run before any domain application, including optional Event salvage."""
    from backend.runtime_v3.resolver import normalized
    value = raw.player_agency
    referenced = {row.get('player_action_id') for row in raw.records['events']
                  if isinstance(row, dict) and isinstance(row.get('player_action_id'), str)}
    referenced.update(row['player_action_id'] for row in raw.records['movements']
                      if isinstance(row, dict) and isinstance(row.get('player_action_id'), str))
    if value is None:
        if resolver.require_player_agency and not resolver.consequence_first:
            fatal('Extraction не проверил соответствие Narrative действию игрока.',
                  'player_agency_missing', repairable=True, section='player_agency')
        return {}
    if resolver.consequence_first and isinstance(value, dict):
        # Audit has no canonical consumers and never grants authority. Parse its
        # entries independently so malformed annotations cannot suppress actions.
        value = dict(value)
        if value.get('status') == 'violated':
            narrative_conflict()
        audit = value.pop('narrative_audit', None)
        valid = []
        for i, item in enumerate(audit if isinstance(audit, list) else []):
            if isinstance(item, dict) and item.get('classification') == 'unauthorized_choice':
                narrative_conflict(reason='audit_status_conflict', section='player_agency',
                                   path=f'player_agency.narrative_audit[{i}]')
            try:
                valid.append(NarrativeAgencyItem.model_validate(item).model_dump())
            except ValidationError:
                resolver.warn('player_agency', i, 'Некорректная вспомогательная запись аудита.',
                              code='player_agency_audit_ignored')
        value['narrative_audit'] = valid
        if isinstance(value.get('actions'), list):
            linked = []
            for i, action in enumerate(value['actions']):
                if isinstance(action, dict) and action.get('meaning') == 'changed':
                    narrative_conflict(section='player_agency', path=f'player_agency.actions[{i}]')
                if isinstance(action, dict) and isinstance(action.get('id'), str) and action['id'] in referenced:
                    linked.append(action)
                else:
                    resolver.warn('player_agency', i, 'Неподтверждённая запись action-list не даёт полномочий.',
                                  code='player_action_unattested')
            value['actions'] = linked
    try:
        parsed = PlayerAgencyReview.model_validate(value)
    except ValidationError:
        fatal('Некорректная типизированная проверка действий игрока.',
              'player_agency_invalid', repairable=True, section='player_agency')
    if parsed.status == 'violated' or (parsed.status == 'uncertain' and not resolver.consequence_first):
        narrative_conflict()
    if parsed.status == 'uncertain':
        resolver.warn('player_agency', 0, 'Общее сомнение аудита; последствия проверяются отдельно.',
                      code='player_agency_uncertain')
    for i, finding in enumerate(parsed.narrative_audit or []):
        if finding.classification == 'unauthorized_choice' or (finding.classification == 'uncertain' and not resolver.consequence_first):
            narrative_conflict(reason='audit_status_conflict', section='player_agency',
                               path=f'player_agency.narrative_audit[{i}]')
        if finding.classification in ('uncertain', 'incidental_detail') and resolver.consequence_first:
            resolver.warn('player_agency', i, 'Вспомогательное замечание к повествованию, без полномочий на изменения.',
                          code='player_agency_audit_advisory')
    if resolver.agency_audit_required and not resolver.consequence_first and parsed.narrative_audit is None:
        fatal('Новый Extraction требует narrative_audit всего Narrative, даже вне Events.',
              'player_agency_audit_missing', repairable=True, section='player_agency')
    actions = {}
    for i, action in enumerate(parsed.actions):
        path = dict(section='player_agency', path=f'player_agency.actions[{i}]')
        if resolver.agency_audit_required and 'target_mode' not in action.model_fields_set:
            fatal('Укажите явный target_mode: interaction или reference.',
                  'player_action_target_mode_missing', repairable=True, **path)
        if (resolver.mode != 'turn' or not resolver.protected_actor_id
                or action.id in actions or not normalized(action.player_evidence)
                or normalized(action.player_evidence) not in normalized(resolver.player_input)):
            fatal('Нет однозначного источника действия в текущем вводе игрока.',
                  'player_action_source_invalid', repairable=True, **path)
        intended, actual = set(action.target_ids), set(action.narrative_target_ids)
        partial_subset = action.outcome == 'partial' and actual <= intended
        deferred = action.outcome in ('deferred', 'not_performed') and not actual
        if action.meaning != 'preserved':
            narrative_conflict(**path)
        if actual != intended and not (partial_subset or deferred):
            fatal('Extraction пометила смысл как preserved, но target_ids и narrative_target_ids противоречат друг другу. '
                  'Перечитайте исходный ввод и неизменный Narrative, исправьте классификацию и ID целей вместе. '
                  'Упоминание/невмешательство использует reference и не требует контакта. '
                  'Если сама проза изменила выбранное действие или адресата, укажите meaning=changed/status=violated; '
                  'не подменяйте цели ради сохранения.',
                  'player_action_targets_inconsistent', repairable=True, **path)
        actions[action.id] = action
    for i, finding in enumerate(parsed.narrative_audit or []):
        path = dict(section='player_agency', path=f'player_agency.narrative_audit[{i}]')
        reference = finding.player_action_id
        if ((reference is not None and reference not in actions)
                or (finding.classification in ('authorized', 'execution_detail') and reference is None)
                or (finding.classification == 'npc_interpretation' and reference is not None)):
            if resolver.consequence_first:
                resolver.warn('player_agency', i, 'Ссылка вспомогательного аудита не подтверждена.',
                              code='player_agency_audit_reference_ignored')
                continue
            fatal('Audit должен ссылаться на проверенный PlayerAction текущего ввода; '
                  'интерпретация NPC не является разрешением игрока.',
                  'player_agency_audit_reference_invalid', repairable=True, **path)
    return actions


def movement_component(resolver, raw, item, actions, index):
    """Remove contact authority from an otherwise independent arrival component.

    A compound input may include a trip and a greeting. An action-only arrival
    with just the traveller proves neither delivery nor consent. No participant,
    Action target or domain outcome is invented. Domain consumers keep the marker
    blocking; optional annotations will have to prove themselves independently.
    """
    reference = item.get('player_action_id')
    action = actions.get(reference) if isinstance(reference, str) else None
    actor = resolver.protected_actor_id
    targets = item.get('target_ids')
    if (not resolver.consequence_first or not action or action.outcome not in ('completed', 'partial')
            or item.get('actor_id') != actor or item.get('participants') != [actor]
            or item.get('medium', 'action') != 'action' or item.get('interaction_channel')
            or item.get('player_assertion') not in (None, 'completed_interaction')
            or not isinstance(targets, list) or not targets
            or not all(isinstance(t, str) for t in targets)
            or not set(targets) <= set(action.narrative_target_ids)
            or not (set(targets) & resolver.state['characters'].keys()) - {actor}):
        return item
    eid = item.get('id')
    from backend.runtime_v3.raw import OPTIONAL_SECTIONS
    # No substantial consumer may lose its stated contact/consent source.
    for section, rows in raw.records.items():
        if section in OPTIONAL_SECTIONS or section in ('events', 'movements'):
            continue
        for row in rows:
            if isinstance(row, dict) and (row.get('source_event_id') == eid
                    or any(isinstance(row.get(key), list) and eid in row[key]
                           for key in ('source_event_ids', 'event_ids'))):
                return item
    if not any(isinstance(m, dict) and m.get('source_event_id') == eid
               and m.get('actor_id') == actor and m.get('assertion') == 'completed_arrival'
               and m.get('to_location_id') == item.get('location_id') for m in raw.records['movements']):
        return item
    candidate = dict(item, target_ids=[])
    candidate.pop('player_assertion', None)
    resolver.warn('events', index, 'Компонент прибытия не подтверждает обращение; сняты только полномочия контакта.',
                  field='player_assertion', entity=eid, code='movement_contact_annotation_ignored')
    return candidate



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
    # Only absence is inherited. Explicit null/empty/conflicting quotes stay errors.
    # Wrong actor/targets above still reject; never mutate the original response.
    if 'player_evidence' not in item and action and resolver.agency_audit_required:
        quote = action.player_evidence
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
        invalid('player_evidence', reason, detail + ' Сверьте границы составного ввода: разные действия/адресаты могут требовать отдельных PlayerActions и соответствующих Events. '
                'При действительно общем действии наследуйте единственную полную цитату; не создавайте фиктивные Events и не объединяйте чужие полномочия.', completion=completed)
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


def validate_completions(resolver, actions, events, indices, written_sources, *, rejected_actions=()):
    """Validate typed completion after canonical presence/Remote, before Knowledge.

    Presence owns the shared movement timeline and call endpoints. This gate only
    binds completed delivery to those accepted participants, never calculates a
    second geography or interprets prose. A written artifact's author is not a
    live endpoint, so messages additionally require an explicit delivery binding.
    """
    from backend.services.world_delta_errors import StructuralDeltaError
    covered, errors, invalid_actions = {}, [], set()
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
            invalid_actions.add(action.id)
            errors.append(StructuralDeltaError(f'Действие {action.id}: {reason} Сверьте outcome с неизменным Narrative; '
                  'не удаляйте Event/адресата и не выдумывайте канал. Если Narrative явно '
                  'завершает невозможный контакт, player_agency.status=violated (нужен новый Narrative).',
                  'player_action_completion_invalid', repairable=True, section='events',
                  index=indices[eid], field='player_action_id', entity=eid,
                  source_ids=[eid, action.id, *sorted(targets)]))

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
        if action.id in rejected_actions or action.id in invalid_actions:
            continue  # Diagnose the invalid source, not its downstream coverage.
        required = set(action.narrative_target_ids)
        requires_contact = (action.outcome == 'completed' and action.target_mode == 'interaction'
                            and required & resolver.state['characters'].keys())
        missing = required - covered.get(action.id, set())
        # Legacy producers required complete Event coverage. Current inventories
        # cannot demand Events per gesture; each supplied contact was checked above.
        if missing and not resolver.consequence_first and (requires_contact or action.id in covered):
            errors.append(StructuralDeltaError(f'Действие {action.id}: {action.outcome} не подтверждён принятыми Events для адресатов: '
                  + ', '.join(sorted(missing)) + '. '
                  'Если Narrative подтверждает обращение игрока, добавьте отдельный Event этого обращения: '
                  f'actor_id={resolver.protected_actor_id}, player_action_id={action.id}, '
                  + ('target_ids — фактически достигнутые адресаты; цитата наследуется из PlayerAction. ' if resolver.agency_audit_required
                   else f'player_evidence={action.player_evidence!r}, target_ids — фактически достигнутые адресаты. ')
                  + 'Сохраните отдельный Event ответа NPC с его настоящим actor_id; не превращайте ответ NPC в действие игрока. '
                  'Ответ не обязателен для доставленного обращения. Не удаляйте Event для обхода проверки; классифицируйте исход по неизменному Narrative. '
                  'Пассивное наблюдение/упоминание использует target_mode=reference; обращение требует interaction. '
                  'Не создавайте фиктивный контакт для наблюдения.',
                  'player_action_completion_invalid' if action.outcome == 'completed' else 'player_action_event_mismatch',
                  repairable=True, section='player_agency',
                  path=f'player_agency.actions[{i}].outcome', reason='missing_player_action_event',
                  source_ids=[action.id, *sorted(missing)]))
    if errors:
        raise StructuralDeltaError.combine(errors)
