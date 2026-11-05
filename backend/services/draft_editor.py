"""Pre-game editorial proposals. Uses the generation transport and validators.

A job owns a frozen base and a private preview, never a mutable draft head.
Only DraftStorage.decide_world_edit can publish the reviewed snapshot.
"""
import json
from copy import deepcopy
from backend.repositories.drafts import candidate_hash
from backend.services.draft_changes import Proposal, apply_proposal, validate_candidate, author_value
from backend.services.draft_completeness import pointer

MARKER = 'AI-редактор начального мира / v1.'
RULES = '''Ты автор-редактор ещё не запущенного мира. Выполни текущую инструкцию
автора свободно и связно во всех затронутых сущностях. Текущая инструкция имеет
приоритет над прежней идеей и модельными деталями. Не игнорируй намеренную смену
замысла. Остальные явные ограничения и ручные правки сохраняй. Если инструкция
неоднозначно требует разрушительного изменения, объясни конфликт в rationale;
не выбирай молча. Укажи такие нерешённые противоречия в conflicts (массив строк);
пустой массив означает отсутствие нерешённых конфликтов. Все изменения будут показаны автору до подтверждения.
Не выполняй будущие добровольные решения, согласия и обязательства игрока.
Не передавай управление; сохраняй камеру, время начала и настройки. Тайна не
становится знанием героя автоматически. Согласуй Knowledge, свидетельства,
предысторию, родство, направленные отношения, организации и сюжетные линии.
Верни один JSON-пакет response_schema. Сохраняй IDs существующих сущностей.
Карточки characters/locations — массивы: предпочитай точный стабильный ID, например
/characters/ilya/fields/Биография. Сервер разрешит ID в индекс; имена не являются ID.
/world/characters — словарь: /world/characters/ilya/biography.
Новые карточки добавляй /characters/- или /locations/-, новые записи —
/world/<section>/<id>. Существующие записи меняй по полям; списки целиком.
Удаление: op=remove, path целой сущности, value — её точное прежнее значение.
Удаляй/меняй все зависимые ссылки тем же пакетом. Индексы карточек относятся к
исходному кандидату и не сдвигаются внутри пакета. Не меняй authoring, provenance,
технические поля. reason объясняет каждое изменение, rationale — общий план,
последствия и нерешённые противоречия. Не обрезай художественные тексты.
Контекст candidate — снимок для понимания мира, НЕ шаблон новых объектов.
Разрешённые авторские поля заданы world_schema; серверные поля из candidate
не копируй. Цели/намерения/обязательства создавай с id, text, status и
содержательными зависимостями, без revision, source_sequence, source_event_id,
review_required, reviewed_signature. Их назначает сервер. При изменении
существующей цели сохраняй id; пропущенные служебные поля сервер сохранит.
Knowledge.source_event_id — ссылка на реальное событие знания, не источник
ревизии цели. Все знания и отношения из контекста учитывай полностью.
Новый NPC находится в указанной им локации; не добавляй его в текущую сцену
без причины. /sections/* — производные представления, не разрешённые пути.'''


def author_context(base, instruction):
    manual={}
    for path in base['state'].get('authoring',{}).get('manual_paths',[]):
        try:manual[path]=pointer(base['state'],path)
        except (KeyError,IndexError,TypeError,ValueError):pass
    return json.dumps(dict(original_idea=base.get('source',''),
        creation_settings=base['state'].get('creation_settings',{}),manual_decisions=manual,
        previous_instructions=base['state'].get('authoring',{}).get('editor_instructions',[]),
        current_instruction=instruction,
        priority='Текущая инструкция заменяет противоречащие ей прежние детали. Остальные ограничения сохраняются.'), ensure_ascii=False)


def messages(base, instruction):
    from backend.services.draft_creative import creative_schema
    from backend.services.draft_initial import SECRET_AUTHORING_RULES
    state=base['state']
    return [dict(role='system',content=MARKER+'\n'+RULES+'\n'+SECRET_AUTHORING_RULES),
            dict(role='user',content=json.dumps(dict(author_context=author_context(base,instruction),
                candidate=state,candidate_hash=candidate_hash(state),
                world_schema=creative_schema(),response_schema=Proposal.model_json_schema()),ensure_ascii=False))]


def rebased_path(before, after, path):
    parts=path.split('/')
    if len(parts)>2 and parts[1] in ('characters','locations'):
        try:
            cid=before[parts[1]][int(parts[2])]['id']
            parts[2]=str(next(i for i,row in enumerate(after[parts[1]]) if row['id']==cid))
        except (ValueError,IndexError,KeyError,StopIteration):return None
    return '/'.join(parts)


def manual_conflicts(before, after):
    conflicts=[]
    for path in before.get('authoring',{}).get('manual_paths',[]):
        destination=rebased_path(before,after,path)
        try:
            if destination is not None and pointer(before,path)==pointer(after,destination):continue
        except (KeyError,IndexError,TypeError,ValueError):pass
        conflicts.append(path)
    return conflicts


def differences(before, after):
    """Identity-based entity groups, with full changed fields and dependency refs."""
    result=[]
    names={row['id']:row['name'] for root in ('characters','locations') for row in before[root]+after[root]}
    def fields(old,new,path=''):
        if old==new:return []
        if isinstance(old,dict) and isinstance(new,dict):
            return [d for key in sorted(old.keys()|new.keys()) for d in fields(old.get(key),new.get(key),path+'/'+key)]
        return [dict(field=path or '/',before=old,after=new)]
    def group(section, old, new):
        for ident in sorted(old.keys()|new.keys()):
            a,b=old.get(ident),new.get(ident)
            if a==b:continue
            record=b or a
            name=record.get('name') or record.get('title') or names.get(ident)
            if not name and record.get('source_id') and record.get('target_id'):
                name=names.get(record['source_id'],record['source_id'])+' → '+names.get(record['target_id'],record['target_id'])
            if not name:name=record.get('description') or record.get('text') or (names.get(record.get('actor_id'),'')+' · '+record.get('fact_id','') if record.get('fact_id') else ident)
            result.append(dict(section=section,id=ident,name=name,
                operation='add' if a is None else 'remove' if b is None else 'replace',
                fields=fields(a,b)))
    for root in ('characters','locations'):
        group(root,{r['id']:r for r in before[root]},{r['id']:r for r in after[root]})
    group('campaign',{'world':before['campaign']},{'world':after['campaign']})
    for section in sorted(before['world'].keys()|after['world'].keys()):
        a,b=before['world'].get(section),after['world'].get(section)
        if isinstance(a,dict) and isinstance(b,dict) and a!=b:
            group('world/'+section,a,b)
    return result


def references(before,after):
    keys=('id','name','title','description','text','label')
    def brief(row):return {k:v for k,v in row.items() if k in keys}
    result={root:list({r['id']:brief(r) for r in before[root]+after[root]}.values()) for root in ('characters','locations')}
    result['world']={section:{k:brief(v) for k,v in dict(before['world'].get(section,{}),**rows).items() if isinstance(v,dict)}
                     for section,rows in after['world'].items() if isinstance(rows,dict)}
    return result


def manual_paths(before, after):
    paths=[]
    for old in before.get('authoring',{}).get('manual_paths',[]):
        path=rebased_path(before,after,old)
        try:
            if path is not None:
                pointer(after,path)
                paths.append(path)
        except (KeyError,IndexError,ValueError,TypeError):pass  # Deleted entity; the immutable base retains its intent.
    return paths


def accepted_state(before, after, instruction, jid):
    state=deepcopy(after)
    meta=state.setdefault('authoring',{})
    meta['manual_paths']=manual_paths(before,state)
    meta.setdefault('editor_instructions',[]).append(dict(job_id=jid,instruction=instruction))
    return state


def run(preparation,jid,config,api_key,handle,loaded,stream_fn):
    from backend.services.draft_response import response, review_config
    from backend.services.usage import tracked_stream
    from backend.services import draft_completeness, draft_repair
    from backend.services.draft_generation import review_signature
    from backend.services.draft_review_recovery import obtain
    repo=preparation.repo;job=repo.preparation_job(jid)
    journal=json.loads(job['response_journal']);edit=journal['editor'];base=edit['base']
    state=base['state'];context=config['context_length']
    if loaded:context=min(context,int(loaded.get('config',{}).get('context_length') or context))
    stage='draft_editor';epoch=journal.get('recovery_epoch',0)
    def save():repo.save_response_journal(jid,journal)
    def opened(stream):
        handle.stream=stream
        if handle.cancel.is_set():stream.close()
    def generate(request_messages,limit):
        effective=review_config(config) if stage=='draft_world_validation' else config
        return tracked_stream(repo,stream_fn,jid,stage,effective,request_messages,model=effective['model'],
            provider=effective['provider'],api_key=api_key,temperature=effective['temperature'],max_tokens=limit,
            require_complete=True,cancel_event=handle.cancel,on_stream=opened,
            **({'response_format':{'type':'json_object'}} if effective['provider']=='deepseek' and not any(m['role']=='assistant' for m in request_messages) else {}))
    def call(slot,request_messages):
        return response(repo,jid,journal,slot,request_messages,review_config(config) if stage=='draft_world_validation' else config,context,generate,handle.cancel)
    repo.draft_phase(jid,'proposing',reset_progress=True)
    request=journal.setdefault('messages',messages(base,edit['instruction']));save()
    from backend.services.draft_creative import response_slot
    slot=response_slot(journal,edit,candidate_hash([context,config.get('max_tokens')]))
    reply=call(slot,request)
    if reply is None:return
    from backend.services import draft_creative_repair as correction
    reply=edit.get('corrected_reply',reply)
    corrections=edit.setdefault('corrections',[])
    while True:
        try:
            trial,proposal=apply_proposal(state,reply,editing=True)
            break
        except ValueError as error:
            allowed=correction.scope(state,reply,error)
            if allowed is None or len(corrections)>=2:raise
            stage='draft_editor_repair';repo.draft_phase(jid,'retrying')
            fixed=call('editor_correction_'+str(len(corrections)),correction.messages(state,reply,author_context(base,edit['instruction']),allowed))
            if fixed is None:return
            corrections.append(dict(scope=allowed,response=fixed));save()
            reply=correction.apply(reply,fixed,allowed)
            edit['corrected_reply']=reply;save()
    edit['proposal']=proposal;save()
    # Reuse bounded address-scoped repairs, retaining every intermediate response.
    for attempt in range(3):
        if handle.cancel.is_set():return
        trial=validate_candidate(state,trial,editing=True)
        stage='draft_world_validation';repo.draft_phase(jid,'reviewing',reset_progress=True)
        review_messages=draft_completeness.messages(trial,author_context(base,edit['instruction']))
        signature=review_signature(review_messages,config)
        issues=obtain(trial,review_messages,signature,journal,call,save)
        if issues is None:return
        edit.update(review=dict(status='completed',candidate_hash=candidate_hash(trial),issues=issues),candidate=trial)
        save()
        blockers=[i for i in issues if i.get('severity','blocker')=='blocker']
        if not blockers or attempt==2:break
        # The standard repair protects manual paths. Explicit replacements are
        # already visible conflicts, never permission to silently repair others.
        repair_input=deepcopy(trial)
        if 'authoring' in repair_input:
            repair_input['authoring']['manual_paths']=manual_paths(state,trial)
        request,paths=draft_repair.request(json.dumps(repair_input,ensure_ascii=False),blockers,author_context(base,edit['instruction']))
        stage='draft_editor_repair';repo.draft_phase(jid,'retrying')
        repaired=call('editor_repair_'+candidate_hash([trial,blockers]),request)
        if repaired is None:return
        repaired_value=json.loads(draft_repair.apply(json.dumps(repair_input,ensure_ascii=False),repaired,paths))
        trial=author_value(repair_input,repaired_value)
        if 'authoring' in state:trial['authoring']=deepcopy(state['authoring'])
        else:trial.pop('authoring',None)
    edit.update(status='preview',candidate=trial,diff=differences(state,trial),
                conflicts=manual_conflicts(state,trial))
    save()
    repo.finish_world_edit(jid,epoch)
