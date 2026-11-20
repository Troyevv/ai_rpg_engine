"""One creative development batch, checkpointed in the existing response journal."""
import json
from backend.repositories.drafts import candidate_hash
from backend.services.draft_changes import Proposal, apply_proposal
from backend.services.draft_initial import prompt_schema

VALIDATION_VERSION = 3


def proposal_text(reply):
    """Accept one complete object plus one redundant outer brace from continuation."""
    from backend.services.draft_response import strict_loads
    try:
        strict_loads(reply)
    except json.JSONDecodeError as exc:
        if exc.msg != 'Extra data' or reply[exc.pos:].strip() != '}':
            raise
        prefix = reply[:exc.pos]
        if not isinstance(strict_loads(prefix), dict):
            raise
        return prefix, 'extra_outer_brace'
    return reply, None

MARKER = 'Творческое развитие начального мира / v1.'
RULES = '''Развивай мир свободно по замыслу автора. Сначала раскрой исходных NPC
(original_npc_gaps), свяжи их с миром, затем добавляй полезные лица, места и линии.
Масштаб — ориентир. Не требуй тайны, травмы или романтики. Уважай заданные факты,
намеренную неизвестность и различия в знаниях персонажей.
При создании или развитии внешности укажи portrait_traits из итогового открытого описания, для исходного NPC через add /characters/<id>/portrait_traits. Сохрани намеренную неизвестность и секреты.
Сохраняй эпоху, технологии, географию и календарь. Не подменяй неизвестность
знанием, предысторию будущим событием, приглашение согласием. Не назначай
управляемому персонажу намерения, чувства, решения и обязательства. Его
заданные характер, внешность, предыстория и начальное положение допустимы.
POV не передаёт управление; тайна мира не становится знанием наблюдателя.
Согласуй карточки с world.characters, семьи с objective_relations, профессии
с roles, организации с фактами, знания с источниками и свидетелями событий.
Новые события — только предыстория; неизвестная минута null. Новые планы не
гарантируют будущего выбора игрока. Не меняй время начала, камеру, управление,
настройки, authoring и серверные provenance. Не копируй технические поля
revision, source_turn, applied, field_facts, remote_source_ids, confirmed_once,
birth_provenance, birth_date_provenance из кандидата в новые записи.
Их значения назначает сервер. Сохрани существующие IDs.
Верни один JSON-объект по response_schema, без Markdown и пояснений: атомарный пакет, не полный мир. candidate_hash
скопируй точно. Для новых карточек/мест op=add path=/characters/- или
/locations/-. Для новых записей op=add path=/world/<section>/<новый ID>.
Зависимые записи добавляй в том же пакете: ссылки проверяются после всех
изменений. Для существующих карточек используй стабильный ID: /characters/<id>/fields/Внешность или /locations/<id>/text. Существующие записи меняй по полям op=replace (op=add только для
отсутствующего поля), списки заменяй целиком. Не удаляй существующие сущности.
reason объясняет художественную связь изменения с миром, а не выдаёт вымысел
за факт автора. rationale объясняет замысел пакета. Если мир уже развит и
осмысленных дополнений нет, допустим changes=[] с содержательным объяснением.
'''


def creative_schema():
    from backend.services.draft_initial import compact_schema
    return compact_schema(prompt_schema(initial_portraits=True))


def npc_gaps(state):
    from backend.services.draft_quality import minimum
    result = {}
    for finding in minimum(state, '', creative=True):
        _, _, index, _, field = finding['path'].split('/')
        card = state['characters'][int(index)]
        result.setdefault(card['id'], dict(id=card['id'],name=card['name'],fields=[]))['fields'].append(field)
    return list(result.values())


def messages(state, author_context):
    # Entire canonical content, no clipping, retrieval sampling, or second canon.
    # Transport preflight refuses contexts that cannot fit it before spending.
    from backend.services.draft_initial import SECRET_AUTHORING_RULES
    return [dict(role='system', content=MARKER+'\n'+RULES+'\n'+SECRET_AUTHORING_RULES),
            dict(role='user', content=json.dumps(dict(
                author_context=author_context, original_npc_gaps={c['id']:c['fields'] for c in npc_gaps(state)}, candidate={k:state[k] for k in ('campaign','characters','locations','world','world_clock','camera','controlled_actor_id','protagonist_id','creation_settings','authoring','story_notes','sections') if k in state},
                candidate_hash=candidate_hash(state), world_schema=creative_schema(),
                response_schema=Proposal.model_json_schema()), ensure_ascii=False, separators=(',', ':')))]


def recoverable(journal):
    records=[*journal.get('creative_history',[]),journal.get('creative') or {}]
    return {r['before_hash']:r for r in records if r.get('before_hash') and r.get('current_reply')
            and (r.get('status')=='rejected' or r['before_hash'] in journal.get('creative_recoveries',{}))}


def response_slot(journal, record, request_key):
    """A changed policy may recover failed transport, never discard paid text."""
    slot=record['slot'];seen=set()
    while slot in journal.get('response_retries',{}) and slot not in seen:
        seen.add(slot);slot=journal['response_retries'][slot]
    transport=journal.get('responses',{}).get(slot,{})
    grant=any(r.get('slot')==slot and not r.get('used') and r.get('epoch')==journal.get('recovery_epoch',0)
              for r in journal.get('empty_retries',{}).values())
    if request_key is not None and record.get('request_key')!=request_key:
        if not journal.get('pending') and not grant and (not transport.get('parts') or transport.get('failure')):
            record['slot']=record.setdefault('base_slot',record['slot'])+'_'+request_key
        record['request_key']=request_key
    return record['slot']


def develop(state, author_context, journal, call, save, *, request_key=None):
    art_version=journal.get('generation_contract',{}).get('portrait_version',2)
    art_job=journal.get('binding',{}).get('job_id') if art_version==3 else None
    record = journal.get('creative')
    if record and record.get('status') == 'applied':
        # Recover a crash between the journal checkpoint and version append.
        if candidate_hash(state) == record['before_hash'] and record['after_hash'] != record['before_hash']:
            enhanced, _ = apply_proposal(state, json.dumps(record['proposal'], ensure_ascii=False),portrait_version=art_version,creation_job=art_job)
            journal['candidate_text'] = json.dumps(enhanced, ensure_ascii=False)
            save()
            return enhanced
        return state  # Manual edits/repair/resume never trigger enrichment again.
    before = candidate_hash(state)
    if record and record.get('before_hash') != before:
        if record.get('current_reply') and journal.get('generation_contract',{}).get('audit_policy')==2:
            # A different revision can preview the paid batch on its own base.
            # Resuming another stage must never buy a replacement for it.
            return state
        journal.setdefault('creative_history', []).append(record)
        record = None
    if record is None:
        if len(journal.get('creative_history', [])) >= 2:
            raise ValueError('Бюджет творческого развития исчерпан; кандидат сохранён для редактора.')
        record = dict(status='running', before_hash=before, slot='creative_'+before)
        journal['creative'] = record
    exhausted = record.get('status') == 'rejected' and record.get('correction_complete')
    revalidate = exhausted and record.get('validation_version', 1) < VALIDATION_VERSION and isinstance(record.get('current_reply'), str)
    if exhausted and not revalidate:
        raise ValueError(record['reason'])
    # A validator upgrade may recheck paid text once, without resetting correction
    # budgets, replacing the candidate, or issuing another creative request.
    record['validation_version'] = VALIDATION_VERSION
    record['status'] = 'running'
    save()
    try:
        from backend.services import draft_creative_repair as correction
        answer = record.get('current_reply')
        if answer is None:
            slot=response_slot(journal,record,request_key)
            save()
            answer = call(slot, messages(state, author_context))
            if answer is None:
                record['status'] = 'cancelled'
                save()
                return None
            record['original_reply'] = answer
            record['current_reply'] = answer
            save()
        attempts = record.setdefault('corrections', [])
        while True:
            try:
                answer, normalization = proposal_text(answer)
                if normalization:
                    record['normalization'] = normalization
                warnings=[]
                enhanced, proposal = apply_proposal(state, answer,portrait_version=art_version,creation_job=art_job,warnings=warnings)
                if warnings: record['warnings']=warnings
                break
            except ValueError as invalid:
                allowed = correction.scope(state, answer, invalid)
                if revalidate or allowed is None or len(attempts) >= 2:
                    record['correction_complete'] = True
                    raise
                # Slot identity survives transport interruptions and resume epochs.
                slot = 'creative_correction_'+before+'_'+str(len(attempts))
                pending=record.setdefault('correction_pending',dict(slot=slot,scope=allowed))
                slot=response_slot(journal,pending,request_key)
                save()
                feedback = attempts[-1].get('error') if attempts else None
                reply = call(slot, correction.messages(state, answer, author_context, allowed, feedback))
                if reply is None:
                    record['status'] = 'cancelled'
                    save()
                    return None
                attempt = dict(slot=slot, scope=allowed, response=reply)
                attempts.append(attempt)
                record.pop('correction_pending', None)
                try:
                    answer = correction.apply(answer, reply, allowed)
                    record['current_reply'] = answer
                except ValueError as error:
                    attempt['error'] = str(error)
                save()
        record.pop('correction_complete', None)
        record.update(status='applied', after_hash=candidate_hash(enhanced), proposal=proposal,
                      provenance=dict(source='creative_model', author_context_hash=candidate_hash(author_context)))
        # A single journal write binds the accepted batch and its resulting text.
        # DraftStorage subsequently appends a version using the same job epoch.
        journal['candidate_text'] = json.dumps(enhanced, ensure_ascii=False)
        save()
        return enhanced
    except ValueError as exc:
        from backend.services.draft_response import TransportError
        from backend.services.token_budget import BudgetError
        diagnostics=getattr(exc, 'diagnostic', None) or getattr(exc, 'errors', None)
        if diagnostics is None and getattr(exc, 'world_paths', None):
            diagnostics=[dict(path=p,category='server_metadata',message=str(exc)) for p in exc.world_paths]
        if callable(diagnostics):diagnostics=diagnostics(include_url=False,include_context=False,include_input=False)
        record.update(status='interrupted' if isinstance(exc, (TransportError, BudgetError)) else 'rejected', reason=str(exc),
                      diagnostics=diagnostics)
        save()
        raise
