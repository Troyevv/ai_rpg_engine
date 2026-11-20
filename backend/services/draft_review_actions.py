"""User-requested editorial passes on a frozen, already saved world."""
from copy import deepcopy
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from backend.repositories.drafts import candidate_hash
from backend.services import draft_completeness, draft_editor
from backend.services.draft_changes import Change, Proposal, apply_proposal
from backend.services.draft_response import strict_loads

TITLES = {'fix': 'Исправить замечания с помощью ИИ', 'recheck': 'Повторить смысловую проверку'}
GUIDANCE = """Замечания — гипотезы. Опирайся на авторский замысел и ручные решения, факты,
индивидуальные знания, тайны и хронологию. Для дат сначала установи источник истины:
сопоставь текст автора, происхождение даты, календарь мира, датированные факты и события.
Автоматическая дата не опровергает явный возраст автора. Не переноси рождение или
историческое событие, чтобы согласовать вторичное описание. Если достоверный источник
отсутствует или два авторских факта противоречат друг другу, объясни неоднозначность.
Отделяй подтверждённое противоречие (contradiction) от неполного описания
(incomplete_description), неопределённости (uncertainty) и ложного замечания
(false_positive). Укажи category у каждого решения. Допустимо оставить все
предупреждения без правок, объяснив каждое. Цели нужны только когда следуют из мира. Не требуй целей у умерших и не назначай их
каждому NPC. Не придумывай решений игрока, скрытых знаний и намеренно неизвестных фактов."""


class Assessment(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    issue_id: str
    category: Literal['contradiction', 'incomplete_description', 'uncertainty', 'false_positive'] | None = None
    reason: str = Field(min_length=1)


class EditAssessment(Assessment):
    outcome: Literal['proposed', 'remaining', 'ambiguous', 'disproved']
    change_indices: list[int] = Field(default_factory=list)


class BirthdayAtStart(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['birthday_at_start']
    quote: str = Field(min_length=1)
    age_quote: str = Field(min_length=1)


class BirthdayMonthDay(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['month_day']
    quote: str = Field(min_length=1)
    age_quote: str = Field(min_length=1)
    month: int = Field(ge=1)
    day: int = Field(ge=1)


class BirthYearOnly(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['year_only']
    year: int = Field(ge=1, le=9999)
    quote: str = Field(min_length=1)


class ReviewChange(Change):
    date_basis: BirthdayAtStart | BirthdayMonthDay | BirthYearOnly | None = None


class ReviewProposal(Proposal):
    changes: list[ReviewChange]
    decisions: list[EditAssessment]


class ReadAssessment(Assessment):
    outcome: Literal['fixed', 'remaining', 'ambiguous', 'disproved']


def findings(base, report):
    rows = {}
    def add(message, paths=()):
        if message and message.strip():
            row = rows.setdefault(message, dict(issue_id=candidate_hash(message), message=message, paths=[]))
            row['paths'] = list(dict.fromkeys([*row['paths'], *(p for p in paths if p)]))
    for issue in (base.get('review') or {}).get('issues', []):
        add(issue['message'], [issue.get('path'), *issue.get('related_paths', [])])
        if issue.get('record_match') and issue['message'] in rows:
            rows[issue['message']]['reported_match'] = issue['record_match']
    for item in report.get('semantic_warnings', []):
        add(item['path']+': '+item['message'], [item['path'], *item.get('related_paths', [])])
    for message in report.get('warnings', []):
        add(message)
    dismissed = dismissed_hints(base)
    return [row for row in rows.values() if row['message'] not in dismissed]


def issue_from_finding(row):
    issue = dict(message=row['message'], severity='warning', related_paths=row['paths'], patch_paths=[])
    if row.get('reported_match'):
        issue['record_match'] = row['reported_match']
    return issue


def dismissed_hints(base):
    review = base.get('review') or {}
    if not review.get('outcomes') or review.get('candidate_hash') != candidate_hash(base['state']):
        return set()
    return {r['message'] for r in review['outcomes'] if r['outcome']=='disproved'}


def automatic_dates(state):
    """Use the calendar's own completion ledger. Never infer ownership from a date."""
    from backend.services.draft_calendar import fill_birth_dates
    meta = state.get('authoring', {}).get('calendar_completion', {})
    prior = meta.get('birth_dates', {})
    if not meta.get('seed') or not any(r.get('source') == 'automatic' for r in prior.values()):
        return {}
    calendar = state.get('world_clock', {}).get('calendar') or {}
    if not calendar.get('profile') or not calendar.get('start_date'):
        return {}
    computed = deepcopy(state)
    fill_birth_dates(computed)
    updated = computed['authoring']['calendar_completion']['birth_dates']
    result = {}
    for cid, original in prior.items():
        actor = state['world']['characters'].get(cid, {})
        if (original.get('source') == 'automatic' and actor.get('birth_date_provenance',{}).get('source')=='authoring_automatic'
                and actor.get('life_status') != 'dead'
                and actor.get('birth_date') == original.get('value') and updated[cid].get('value') != original.get('value')):
            result[cid] = updated[cid]
    return result


def calendar_evidence(state):
    from backend.runtime_v3.birth_identity import dob_metadata
    from backend.runtime_v3.calendar import age_on
    from backend.services.draft_calendar import age_reference_date
    clock = state['world_clock']
    calendar = clock.get('calendar') or {}
    result = {}
    card_ages = {c['id']: c.get('fields', {}).get('Возраст') for c in state['characters']}
    for cid, actor in state['world']['characters'].items():
        if not actor.get('birth_date'):
            continue
        date = age_reference_date(actor, clock)
        result[cid] = dict(date=date, birth_date=actor['birth_date'], card_age=card_ages.get(cid), provenance=dob_metadata(actor),
                           age=age_on(actor['birth_date'], date, calendar.get('profile', {})))

    return result


def messages(base, action, notes):
    context = json.loads(draft_editor.author_context(base, TITLES[action]))
    context.pop('priority')
    context['outline'] = base.get('outline', '')
    if action == 'fix':
        from backend.services.draft_initial import SECRET_AUTHORING_RULES
        request = draft_editor.messages(base, TITLES[action])
        request[0]['content'] = draft_editor.MARKER+'\n'+SECRET_AUTHORING_RULES
        payload = json.loads(request[1]['content'])
        payload['response_schema'] = ReviewProposal.model_json_schema()
        prompt = """Это адресная правка замечаний к сохранённому миру. Замечание не является
новым указанием автора и не отменяет прежний замысел. Предложи только необходимые
адресные правки описаний. Если автор уже задал связь, должность, организацию или
место жительства, можно добавить отсутствующую структурированную запись по ID.
В reason укажи конкретный источник. Не удаляй сущности, не переписывай факты,
знания, исторические события или ручные решения, не придумывай время начала связи. Для каждого issue_id верни decision: proposed
со списком индексов changes (с нуля), remaining, ambiguous или disproved. Объясни
основание и источник в reason. Для необоснованного замечания изменения не нужны.
Верни один JSON по response_schema. Скопируй candidate_hash. Используй стабильный ID
в пути карточки, например /characters/anya/fields/Биография. Адресуй конкретное поле:
replace для существующего, add для отсутствующего. Сохраняй привязки тайных полей.
Адресная правка допустима для описания, контекста связи или намерения живого NPC с
основанием в замысле. Для исправления автоматически назначенного birth_date передай
replace с value=null и date_basis. Если день рождения приходится на начало игры,
kind=birthday_at_start, quote — дословные слова автора об этом, age_quote — дословная
цитата о возрасте этого персонажа на начало. Если автор указал месяц и день,
kind=month_day, month, day и обе цитаты. Сервер вычислит год и точную дату.
Если установлен только год рождения, kind=year_only, year и дословная quote из
замысла или карточки этого персонажа: сервер предложит снять недостоверную точную
дату, сохранив год. Не используй год смерти другого персонажа как дату рождения.
Если источники расходятся, оставь ambiguous, без операции. Не передвигай брак
или смерть и не меняй биографию для формального закрытия замечания."""
    else:
        request = draft_completeness.advisory_messages(base['state'], '')
        payload = json.loads(request[1]['content'])
        prompt = """Это отдельное чтение текущей ревизии. Верни issues для новых замечаний и
decisions для прежних: issue_id, outcome (fixed, remaining, ambiguous или disproved),
reason с конкретным основанием в текущем мире. Исчезновение формулировки не доказывает
исправление. Не предлагай изменений. Если прежних замечаний нет, decisions пуст."""
    request[0]['content'] += '\n' + GUIDANCE + '\n' + prompt
    from backend.services.draft_presentation import event_times
    payload.update(author_context=context, findings=notes, calendar_evidence=calendar_evidence(base['state']),
                   event_dates=event_times(base['state']))
    request[1]['content'] = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    return request


def assessments(notes, decisions):
    by_id = {row['issue_id']: row for row in notes}
    answers = {}
    for decision in decisions:
        key = decision.issue_id
        if key not in by_id or key in answers or not decision.reason.strip():
            raise ValueError('Ответ содержит неизвестное или повторное замечание либо пустое обоснование.')
        answers[key] = decision.model_dump()
    missing = dict(outcome='remaining', reason='Модель не дала решения по этому замечанию.')
    return [{**row, **answers.get(row['issue_id'], missing)} for row in notes]


def check_scope(state, change, dates, birth_updates):
    """Protect the sources themselves while allowing corrections to derived descriptions."""
    parts = change['path'].split('/')[1:]
    root = parts[0]
    if change['op'] == 'remove':
        raise ValueError('Удаление канонических записей недоступно при исправлении замечаний.')
    if root == 'characters' and len(parts) == 4 and parts[2] == 'fields':
        card = state['characters'][int(parts[1])]
        from backend.services.draft_player_view import RESERVED_FIELDS
        if parts[3] in RESERVED_FIELDS:
            raise ValueError('Решения и намерения персонажей защищены.')
        # The authoritative source of an age must not be replaced by an inferred DOB.
        if parts[3] == 'Возраст':
            from backend.runtime_v3.birth_identity import dob_metadata
            actor = state['world']['characters'][card['id']]
            if dob_metadata(actor).get('source') == 'authoring_automatic':
                raise ValueError('Автоматическая дата рождения не является основанием менять возраст.')
            evidence=dates.get(card['id'])
            if actor.get('life_status')=='dead' and not (evidence and evidence['date']):
                raise ValueError('Для изменения возраста умершего персонажа неизвестна дата смерти.')
            if evidence and evidence['age'] is not None:
                exact=re.fullmatch(r'(\d{1,4})(?:\s+(?:лет|год|года))?',str(change['value']).strip())
                if not exact or int(exact[1])!=evidence['age']:
                    raise ValueError('Предложенный возраст не соответствует дате рождения и календарю мира.')
        return
    if root == 'locations' and len(parts) == 3 and parts[2] == 'text':
        return
    if root == 'campaign' and len(parts) == 2 and parts[1] in ('description','public_description'):
        return
    if root == 'world' and len(parts) == 3 and change['op']=='add' and parts[1] in (
            'relationships','objective_relations','roles','organizations','residences'):
        return
    if root == 'world' and len(parts) == 4 and parts[1]=='characters':
        cid = parts[2].replace('~1','/').replace('~0','~')
        if parts[3]=='situation' and cid==state.get('controlled_actor_id'):
            raise ValueError('Начальное действие управляемого персонажа защищено.')
        if parts[3]=='birth_date' and cid in birth_updates and birth_updates[cid]['value'] == change['value']:
            return
        if parts[3] in ('goals','intentions') and cid!=state.get('controlled_actor_id'):
            if state['world']['characters'][cid].get('life_status')=='alive':
                return
    if root == 'world' and len(parts) == 4 and parts[-1] in {
        'characters': ('biography','situation','physical_state'),
        'relationships': ('context',), 'organizations': ('description',),
        'threads': ('description',), 'roles': ('description',)
    }.get(parts[1], ()):
        return
    raise ValueError('Этот путь затрагивает канон, права персонажа или хронологию: '+change['path'])


def proposal_result(edit, reply):
    state = edit['base']['state']
    packet = ReviewProposal.model_validate(strict_loads(reply))
    outcomes = assessments(edit['findings'], packet.decisions)
    linked = set()
    for row in outcomes:
        indices = row.get('change_indices', [])
        if bool(indices) != (row['outcome'] == 'proposed') or any(i < 0 or i >= len(packet.changes) for i in indices):
            raise ValueError('Исправление не связано с конкретным изменением пакета.')
        linked.update(indices)
    if linked != set(range(len(packet.changes))):
        raise ValueError('В пакете есть правки без исходного замечания.')
    if not packet.changes:
        fingerprint = edit.get('before_hash') or candidate_hash(state)
        if packet.candidate_hash != fingerprint:
            raise ValueError('Разбор замечаний относится к другой версии мира.')
        return dict(status='assessed', outcomes=outcomes, proposal=packet.model_dump(exclude={'decisions'}), diff=[])
    proposal_data = packet.model_dump(exclude={'decisions', 'changes'})
    proposal_data['changes'] = []
    birth_updates = {}
    try:
        from backend.services.draft_calendar import review_birth_date
        for change in packet.changes:
            row = change.model_dump(exclude={'date_basis'})
            if change.date_basis is not None:
                record = review_birth_date(edit['base'], change.path, change.date_basis.model_dump())
                if change.op != 'replace' or (change.value is not None and change.value != record['value']):
                    raise ValueError('Правка не соответствует вычислению календаря.')
                cid = change.path.split('/')[3].replace('~1','/').replace('~0','~')
                birth_updates[cid] = record
                row['value'] = record['value']
                basis = record['basis']
                row['reason'] += ' Основание: «'+basis['quote']+'».'
                if basis['kind'] == 'year_only':
                    row['reason'] += f" Будет сохранён год {basis['year']}; точные месяц и день неизвестны."
                else:
                    row['reason'] += ' Возраст на начало истории: «'+basis['age_quote']+'».'
            proposal_data['changes'].append(row)
        trial, proposal = apply_proposal(state, json.dumps(proposal_data), review_fix=True)
        dates = calendar_evidence(state)
        for change in proposal['changes']:
            check_scope(state, change, dates, birth_updates)
            if change['op']=='replace' and draft_completeness.pointer(state,change['path'])==change['value']:
                raise ValueError('Предложение повторяет исходное значение: '+change['path'])
    except ValueError as exc:
        for row in outcomes:
            if row['outcome']=='proposed':
                row['outcome']='unapplied'
        return dict(status='unapplied', outcomes=outcomes, failure=str(exc), proposal=packet.model_dump(exclude={'decisions'}))
    return dict(status='preview', candidate=trial, proposal=proposal,
                outcomes=outcomes, calendar_decisions=birth_updates, diff=draft_editor.differences(state, trial))


def historical_assessment(edit):
    """Project only the old empty-package conflict failure. Keep its paid journal intact."""
    proposal = edit.get('proposal') or {}
    return (edit.get('action') == 'fix' and edit.get('status') == 'unapplied'
            and edit.get('failure') == 'Творческое предложение содержит нерешённые авторские конфликты.'
            and proposal.get('changes') == [] and bool(proposal.get('conflicts'))
            and bool(edit.get('before_hash')) and proposal.get('candidate_hash') == edit['before_hash']
            and all(r['outcome'] in ('ambiguous','disproved','remaining') for r in edit.get('outcomes', [])))


def accept_calendar_updates(before, trial, decisions=None):
    """Publish derived-date provenance together with its reviewed value."""
    calculated = None
    for cid, actor in trial['world']['characters'].items():
        if actor.get('birth_date') == before['world']['characters'][cid].get('birth_date'):
            continue
        if decisions is not None:
            record = decisions.get(cid)
            if not record or record['value'] != actor['birth_date']:
                raise ValueError('Дата не соответствует подтверждённому предпросмотру.')
            trial['authoring']['calendar_completion']['birth_dates'][cid] = record
            actor['birth_date_provenance'] = dict(actor.get('birth_date_provenance') or {}, source=record['source'])
            continue
        # Existing previews from the original review contract retain their recorded calculation.
        if calculated is None:
            calculated = automatic_dates(before)
        record = calculated.get(cid)
        if not record or record['value'] != actor['birth_date']:
            raise ValueError('Основание автоматической даты рождения изменилось.')
        trial['authoring']['calendar_completion']['birth_dates'][cid]=record
        actor['birth_date_provenance'] = dict(actor.get('birth_date_provenance') or {},
            source='authoring_automatic', input_signature=record['input_signature'])


def review_result(edit, reply):
    payload = strict_loads(reply)
    issues, complete = draft_completeness.advisory_issues(payload)
    if not complete:
        raise ValueError('Часть замечаний не удалось прочитать. Прежний отчёт сохранён.')
    decisions = payload.get('decisions', [])
    if not isinstance(decisions, list):
        raise ValueError('Ожидался список решений по замечаниям.')
    outcomes = assessments(edit['findings'], [ReadAssessment.model_validate(d) for d in decisions])
    known = {i['message']: i for i in issues}
    for row in outcomes:
        if row['outcome']=='fixed' and (edit['base'].get('review') or {}).get('candidate_hash')==edit['before_hash']:
            row['outcome']='disproved'
        if (row['outcome']=='fixed' and row['message'] in edit['current_hints']
                or row['outcome']=='disproved' and row['message'] in edit['calendar_conflicts']):
            row.update(outcome='remaining', reason='Условие замечания сохраняется в текущей ревизии.')
    for row in outcomes:
        existing = known.get(row['message'])
        if existing is not None:
            # A reader may restate a finding without its original object references.
            existing.update(issue_from_finding(row), severity=existing['severity'])
            if row['outcome'] in ('fixed','disproved'):
                row.update(outcome='remaining', reason='Замечание повторилось в новом отчёте.')
        elif row['outcome'] in ('remaining','ambiguous'):
            issues.append(issue_from_finding(row))
    return dict(status='reviewed', outcomes=outcomes, review=dict(status='completed', advisory=True,
                candidate_hash=edit['before_hash'], issues=issues))


def response_key(edit):
    prefix='completeness_advisory_' if edit['action']=='recheck' else 'editor_proposal_findings_'
    return prefix+edit['before_hash']


def saved_reply(journal):
    from backend.services.draft_response import response_slots
    edit=journal.get('editor') or {}
    if not edit.get('action') or journal.get('pending'):
        return None
    slot=response_slots(journal,response_key(edit))[-1]
    record=journal.get('responses',{}).get(slot,{})
    if record.get('parts') and not record.get('failure') and record['parts'][-1]['text'].strip():
        return record
    return None


def finish(repo, jid, edit, reply, epoch):
    action=edit['action']
    try:
        result = proposal_result(edit, reply) if action == 'fix' else review_result(edit, reply)
    except ValueError as exc:
        result = dict(status='unapplied', outcomes=[dict(row, outcome='unapplied', reason='Пакет не применён. См. причину выше.')
                                                  for row in edit['findings']], failure=str(exc))
    repo.finish_review_action(jid, epoch, result)


def run(repo, jid, journal, edit, call, epoch, cancel):
    action = edit['action']
    repo.draft_phase(jid, 'reviewing' if action == 'recheck' else 'proposing', reset_progress=True)
    slot = response_key(edit)
    if 'messages' not in journal:
        journal['messages'] = messages(edit['base'], action, edit['findings'])
        repo.save_response_journal(jid, journal)
    reply = call(slot, journal['messages'])
    if reply is None or cancel.is_set():
        return
    finish(repo,jid,edit,reply,epoch)
