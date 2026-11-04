"""One creative development batch, checkpointed in the existing response journal."""
import json
from backend.repositories.drafts import candidate_hash
from backend.services.draft_changes import Proposal, apply_proposal
from backend.services.draft_initial import prompt_schema

MARKER = 'Творческое развитие начального мира / v1.'
RULES = '''Идея автора — творческий бриф, не исчерпывающая спецификация. Развей
неописанные стороны мира свободно, связно и художественно: людей, их прошлое,
семьи, отношения, места, организации, экономику, повседневность, конфликты,
тайны, события и открытые сюжетные линии. Это направления возможностей,
не обязательный набор: никаких квот, шаблонных травм, обязательных секретов
или заполнения всего ради количества. Создавай причинные связи и возможности
будущей игры; не пересказывай уже хорошие фрагменты. Новые сущности разрешены.
Явные факты, ограничения и намеренная неизвестность автора приоритетны.
Сохраняй эпоху, технологии, географию и календарь. Не подменяй неизвестность
знанием, предысторию будущим событием, приглашение согласием. Не назначай
управляемому персонажу намерения, чувства, решения и обязательства. Его
заданные характер, внешность, предыстория и начальное положение допустимы.
POV не передаёт управление; тайна мира не становится знанием наблюдателя.
Согласуй карточки с world.characters, семьи с objective_relations, профессии
с roles, организации с фактами, знания с источниками и свидетелями событий.
Новые события — только предыстория; неизвестная минута null. Новые планы не
гарантируют будущего выбора игрока. Не меняй время начала, камеру, управление,
настройки, authoring и серверные provenance. Сохрани существующие IDs.
Верни один атомарный пакет по response_schema, не полный мир. candidate_hash
скопируй точно. Для новых карточек/мест op=add path=/characters/- или
/locations/-. Для новых записей op=add path=/world/<section>/<новый ID>.
Зависимые записи добавляй в том же пакете: ссылки проверяются после всех
изменений. Существующие записи меняй по полям op=replace (op=add только для
отсутствующего поля), списки заменяй целиком. Не удаляй существующие сущности.
reason объясняет художественную связь изменения с миром, а не выдаёт вымысел
за факт автора. rationale объясняет замысел пакета. Если мир уже развит и
осмысленных дополнений нет, допустим changes=[] с содержательным объяснением.
'''


def creative_schema():
    """Factor repeated schema nodes without dropping constraints or canon."""
    from collections import Counter
    schema=prompt_schema();counts=Counter();definitions={};names={}
    def key(node):return json.dumps(node,sort_keys=True,separators=(',', ':'))
    def count(node):
        if isinstance(node,dict):
            if len(key(node))>160:counts[key(node)]+=1
            for value in node.values():count(value)
        elif isinstance(node,list):
            for value in node:count(value)
    count(schema)
    def compact(node, properties=False):
        if isinstance(node,list):return [compact(v) for v in node]
        if not isinstance(node,dict):return node
        signature=key(node)
        # Property maps are not schemas; never replace them with a $ref.
        if not properties and counts[signature]>1:
            if signature not in names:
                name='creative_'+str(len(names));names[signature]=name
                definitions[name]={k:compact(v,k=='properties') for k,v in node.items()}
            return {'$ref':'#/$defs/'+names[signature]}
        return {k:compact(v,k=='properties') for k,v in node.items()}
    result=compact(schema)
    result['$defs']=definitions
    return result


def messages(state, author_context):
    # Entire canonical content, no clipping, retrieval sampling, or second canon.
    # Transport preflight refuses contexts that cannot fit it before spending.
    return [dict(role='system', content=MARKER+'\n'+RULES),
            dict(role='user', content=json.dumps(dict(
                author_context=author_context, candidate={k:state[k] for k in ('campaign','characters','locations','world','world_clock','camera','controlled_actor_id','protagonist_id','creation_settings','authoring','story_notes','sections') if k in state},
                candidate_hash=candidate_hash(state), world_schema=creative_schema(),
                response_schema=Proposal.model_json_schema()), ensure_ascii=False, separators=(',', ':')))]


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
    record = journal.get('creative')
    if record and record.get('status') == 'applied':
        # Recover a crash between the journal checkpoint and version append.
        if candidate_hash(state) == record['before_hash'] and record['after_hash'] != record['before_hash']:
            enhanced, _ = apply_proposal(state, json.dumps(record['proposal'], ensure_ascii=False))
            journal['candidate_text'] = json.dumps(enhanced, ensure_ascii=False)
            save()
            return enhanced
        return state  # Manual edits/repair/resume never trigger enrichment again.
    before = candidate_hash(state)
    if record and record.get('before_hash') != before:
        journal.setdefault('creative_history', []).append(record)
        record = None
    if record is None:
        if len(journal.get('creative_history', [])) >= 2:
            raise ValueError('Бюджет творческого развития исчерпан; кандидат сохранён для редактора.')
        record = dict(status='running', before_hash=before, slot='creative_'+before)
        journal['creative'] = record
    if record.get('status') == 'rejected' and record.get('correction_complete'):
        raise ValueError(record['reason'])
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
                enhanced, proposal = apply_proposal(state, answer)
                break
            except ValueError as invalid:
                allowed = correction.scope(state, answer, invalid)
                if allowed is None or len(attempts) >= 2:
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
        record.update(status='applied', after_hash=candidate_hash(enhanced), proposal=proposal,
                      provenance=dict(source='creative_model', author_context_hash=candidate_hash(author_context)))
        # A single journal write binds the accepted batch and its resulting text.
        # DraftStorage subsequently appends a version using the same job epoch.
        journal['candidate_text'] = json.dumps(enhanced, ensure_ascii=False)
        save()
        return enhanced
    except ValueError as exc:
        from backend.services.draft_response import TransportError
        diagnostics=getattr(exc, 'errors', None)
        if callable(diagnostics):diagnostics=diagnostics(include_url=False,include_context=False,include_input=False)
        record.update(status='interrupted' if isinstance(exc, TransportError) else 'rejected', reason=str(exc),
                      diagnostics=diagnostics)
        save()
        raise
