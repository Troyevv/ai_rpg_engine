"""User-requested editorial passes on a frozen, already saved world."""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from backend.repositories.drafts import candidate_hash
from backend.services import draft_completeness, draft_editor
from backend.services import draft_review_chronology as chronology
from backend.services.draft_response import strict_loads

TITLES = {'fix': 'Исправить замечания с помощью ИИ', 'recheck': 'Повторить смысловую проверку'}
GUIDANCE = """Замечания рекомендательны. Различай противоречия, неполные описания,
неопределённость и ложные замечания. Не требуй целей от всех персонажей или умерших.
Сохраняй контекст тайн, знаний и ручных решений. Автор принимает окончательное решение."""


class Assessment(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    issue_id: str
    category: Literal['contradiction', 'incomplete_description', 'uncertainty', 'false_positive'] | None = None
    reason: str = Field(min_length=1)


class EditAssessment(Assessment):
    outcome: Literal['proposed', 'remaining', 'ambiguous', 'disproved']
    change_indices: list[int] = Field(default_factory=list)


class ReviewProposal(draft_editor.EditorialProposal):
    decisions: list[EditAssessment] = Field(default_factory=list)


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
        prompt = """Ты автор-редактор сохранённого мира. Предложи адресные изменения
по замечаниям. Выбирай художественное решение самостоятельно. Можно менять биографии,
характер, внешность, предысторию героя, события, отношения, даты рождения и смерти.
В value укажи готовое значение, для даты — YYYY-MM-DD календаря мира. Сопоставь возрасты
каждого родителя на дату родов, смерть при родах и окончание брака. Сам выбери
недостающие точные дни в рамках замысла, перечисли все зависимые правки отдельными
операциями. Сохраняй известный год. Пометь новые детали detail=new_detail, сведения
из замысла — author_fact. Объясни расхождения и возможные варианты в conflicts.
Замечания можно оставить, опровергнуть или передать на выбор пользователя. Для
decisions используй issue_id из findings. Классификация и привязка индексов необязательны.
Верни один JSON по response_schema с candidate_hash данной версии. Для существующего
поля используй replace, для отсутствующего add. Не назначай серверное происхождение."""
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


def legacy_dates(base, raw):
    """Decode *recorded* null placeholders. New proposals contain concrete values."""
    from backend.services.draft_calendar import review_birth_date
    state=base['state']
    changes=raw['changes']
    dates={}
    decisions={}
    reports=[]
    warnings=[]
    deferred=[]
    for row in changes:
        basis=row.pop('date_basis',None)
        if not basis or row.get('value') is not None or not row.get('path','').endswith('/birth_date'):
            continue
        cid=row['path'].split('/')[3].replace('~1','/').replace('~0','~')
        if basis.get('kind') in ('year_only','creative_year'):
            deferred.append((cid,row,basis))
        elif basis.get('kind') in ('birthday_at_start','month_day'):
            try:
                decisions[cid]=review_birth_date(base,row['path'],basis)
                dates[cid]=row['value']=decisions[cid]['value']
                row['detail']='author_fact'
            except (ValueError,KeyError) as exc:
                row['value']=state['world']['characters'][cid].get('birth_date')
                warnings.append(str(exc))
    for cid,row,basis in deferred:
        preferred=basis.get('preferred_date')
        try:
            data=chronology.RecordedYear.model_validate(basis)
            computed,linked,report=chronology.plan_birth(base,cid,data,dates)
            if preferred and preferred!=report['date']:
                raise ValueError('Предложенный день расходится с другими датами семьи.')
            reports.append(report)
            decisions.update(computed)
            linked.update({chronology.birth_path(k):v['value'] for k,v in computed.items() if k!=cid})
            row['value']=report['date']
        except (ValueError,KeyError,TypeError) as exc:
            warnings.append(str(exc))
            row['value']=preferred or state['world']['characters'][cid].get('birth_date')
            linked={}
            if preferred:
                for p in basis.get('parents',[]):
                    if p.get('died_at_birth'):
                        linked[chronology.birth_path(p['actor_id']).rsplit('/',1)[0]+'/death_date']=preferred
                for m in basis.get('conditional_marriages',[]):
                    from backend.services.draft_initial import escape
                    linked['/world/objective_relations/'+escape(m['relation_id'])+'/until_date']=preferred
        row['detail']='new_detail'
        for path,value in linked.items():
            if any(c['path']==path for c in changes):continue
            owner,field=path.rsplit('/',1)
            container=draft_completeness.pointer(state,owner)
            if container.get(field)!=value:
                changes.append(dict(path=path,value=value,op='replace' if field in container else 'add',
                                    detail='new_detail',reason=row.get('reason','Связанная дата.')))
    raw.setdefault('conflicts',[]).extend(warnings)
    return decisions,reports


def proposal_result(edit, reply):
    state=edit['base']['state']
    raw=strict_loads(reply)
    decisions,reports=({},[])
    if isinstance(raw,dict) and isinstance(raw.get('changes'),list) and any(isinstance(c,dict) and 'date_basis' in c for c in raw['changes']):
        decisions,reports=legacy_dates(edit['base'],raw)
    annotations=raw.pop('decisions',[]) if isinstance(raw,dict) else []
    packet=ReviewProposal.model_validate(raw)
    known={n['issue_id'] for n in edit['findings']}
    decisions_by_id={}
    for item in annotations if isinstance(annotations,list) else []:
        try:
            annotation=EditAssessment.model_validate(item)
        except ValueError:
            continue
        if annotation.issue_id in known:
            decisions_by_id[annotation.issue_id]=annotation
    outcomes=assessments(edit['findings'],decisions_by_id.values())
    if not packet.changes:
        if packet.candidate_hash!=(edit.get('before_hash') or candidate_hash(state)):
            raise ValueError('Разбор замечаний относится к другой версии мира.')
        return dict(status='assessed',outcomes=outcomes,proposal=packet.model_dump(exclude={'decisions'}),diff=[])
    result=draft_editor.preview(state,draft_editor.EditorialProposal.model_validate(packet.model_dump(exclude={'decisions'})))
    if result['status']=='unapplied':
        for row in outcomes:
            if row['outcome']=='proposed':row['outcome']='unapplied'
    return dict(result,outcomes=outcomes,calendar_decisions=decisions,chronologies=reports)


def superseded_year_preview(edit):
    """Do not accept an old pending proposal that would erase an exact generated date."""
    return (edit.get('action')=='fix' and edit.get('status')=='preview' and 'chronologies' not in edit
            and any(record.get('source')=='unknown' and record.get('known_year') and record.get('value') is None
                    for record in (edit.get('calendar_decisions') or {}).values()))


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
    for cid,actor in trial['world']['characters'].items():
        if actor.get('birth_date')==before['world']['characters'].get(cid,{}).get('birth_date'):
            continue
        value=actor.get('birth_date')
        record=(decisions or {}).get(cid)
        if not record or record.get('value')!=value:
            record=dict(source='explicit' if value is not None else 'unknown',value=value)
        ledger=trial.setdefault('authoring',{}).setdefault('calendar_completion',{}).setdefault('birth_dates',{})
        ledger[cid]=record
        source='authoring_automatic' if record['source']=='review_creative' else record['source']
        actor['birth_date_provenance']=dict(actor.get('birth_date_provenance') or {},source=source)


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
        existing = known.get(row['message'])
        if existing is not None:
            # A reader may restate a finding without its original object references.
            existing.update(issue_from_finding(row), severity=existing['severity'])
        elif row['outcome'] in ('remaining','ambiguous') or row['message'] in edit.get('calendar_conflicts',[]):
            issues.append(issue_from_finding(row))
    return dict(status='reviewed', outcomes=outcomes, review=dict(status='completed', advisory=True,
                candidate_hash=edit['before_hash'], issues=issues))


def response_key(edit):
    prefix='completeness_advisory_' if edit['action']=='recheck' else 'editor_proposal_findings_'
    return prefix+edit['before_hash']


def saved_reply(journal):
    from backend.services.draft_response import response_slots
    edit=journal.get('editor') or {}
    if journal.get('pending'):return None
    if edit.get('action'):
        logical=response_key(edit)
    elif edit.get('slot'):
        logical=edit['slot']
    else:
        logical=next((slot for slot in ('draft_field','draft_character') if slot in journal.get('responses',{})),None)
        if not logical:return None
    slot=response_slots(journal,logical)[-1]
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
