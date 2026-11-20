"""Pre-game editorial proposals. Uses the generation transport and validators.

A job owns a frozen base and a private preview, never a mutable draft head.
Only DraftStorage.decide_world_edit can publish the reviewed snapshot.
"""
import json
from copy import deepcopy
from backend.repositories.drafts import candidate_hash
from backend.services.draft_changes import Change, Proposal, apply_proposal
from typing import Literal
from backend.services.draft_completeness import pointer

MARKER = 'AI-редактор начального мира / v1.'
RULES = '''Ты автор-редактор ещё не запущенного мира. Выполни текущую инструкцию
автора свободно и связно во всех затронутых сущностях. Текущая инструкция имеет
приоритет над прежней идеей и модельными деталями. Не игнорируй намеренную смену
замысла. Остальные явные ограничения и ручные правки сохраняй. Если инструкция
неоднозначно требует разрушительного изменения, объясни конфликт в rationale;
не выбирай молча. Укажи такие нерешённые противоречия в conflicts (массив строк);
пустой массив означает отсутствие нерешённых конфликтов. Все изменения будут показаны автору до подтверждения.
Это авторское редактирование предыстории, включая характер, мотивы и поступки героя. Для новых вымышленных деталей укажи detail=new_detail, для сведений из замысла — author_fact.
Не передавай управление; сохраняй камеру, время начала и настройки. Тайна не
становится знанием героя автоматически. Согласуй Knowledge, свидетельства,
предысторию, родство, направленные отношения, организации и сюжетные линии.
Верни один JSON-пакет response_schema. Сохраняй IDs существующих сущностей.
Карточки characters/locations — массивы: предпочитай точный стабильный ID, например
/characters/ilya/fields/Биография. Сервер разрешит ID в индекс; имена не являются ID.
/world/characters — словарь: /world/characters/ilya/biography.
Для нового NPC добавь portrait_traits в карточку тем же ответом: только поддерживаемые
открытые признаки из fields.Внешность по world_schema. Литературный текст первичен;
не меняй его ради рисунка. Тёмно-русые → dark_blond, до подбородка → bob,
серо-голубые → grey_blue. Учитывай отрицания и контекст, не выдумывай отсутствующие
признаки. Неподдерживаемые детали пропускай. Существующие портреты не изменяй.
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


class EditorialChange(Change):
    detail: Literal['proposal','author_fact','new_detail'] = 'proposal'
    reason: str = ''


class EditorialProposal(Proposal):
    changes: list[EditorialChange]
    rationale: str = ''


def family_impacts(before, after):
    """Display consequences of the shown dates, without deriving more operations."""
    from backend.runtime_v3.calendar import age_on
    world=after['world']
    names={c['id']:c['name'] for c in after['characters']}
    profile=(after['world_clock'].get('calendar') or {}).get('profile',{})
    impacts=[]
    for relation in world['objective_relations'].values():
        if relation['kind']!='parent':continue
        parent,child=relation['source_id'],relation['target_id']
        actors=world['characters']
        day=actors[child].get('birth_date')
        def dates(who):
            return [actors[who].get(k)!=before['world']['characters'].get(who,{}).get(k) for k in ('birth_date','death_date')]
        if day and (any(dates(parent)) or any(dates(child))):
            impacts.append(dict(parent=names[parent],child=names[child],day=day,
                                age=age_on(actors[parent].get('birth_date'),day,profile)))
    return impacts


def preview(state, packet):
    """One authoring boundary for suggestions, review fixes and local amendments."""
    from backend.services.draft_initial import DraftErrors
    raw=packet.model_dump()
    for row in raw['changes']:
        row.pop('detail')
        row['reason']=row['reason'] or 'Предложенное изменение.'
    raw['rationale']=raw['rationale'] or 'Предложение к этой версии мира.'
    warnings=[]
    try:
        candidate,proposal=apply_proposal(state,json.dumps(raw),editing=True,warnings=warnings)
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        paths=[item['path'] for item in exc.errors] if isinstance(exc,DraftErrors) else getattr(exc,'world_paths',[])
        indices={int(p.split('/')[2]) for p in getattr(exc,'proposal_paths',[]) if p.startswith('/changes/')}
        for i,change in enumerate(packet.changes):
            if any(p==change.path or p.startswith(change.path+'/') or change.path.startswith(p+'/') for p in paths):
                indices.add(i)
        diagnostics=[dict(operation=i+1,path=packet.changes[i].path,message=str(exc)) for i in sorted(indices)]
        failure=str(exc)
        if diagnostics:
            failure='; '.join(f"Операция {d['operation']} ({d['path']}): {d['message']}" for d in diagnostics)
        return dict(status='unapplied',proposal=packet.model_dump(),failure=failure,diagnostics=diagnostics)
    for row,original in zip(proposal['changes'],packet.changes):
        row['detail']=original.detail
    diff=differences(state,candidate)
    return dict(status='preview' if diff else 'assessed',proposal=proposal,candidate=candidate,diff=diff,
                conflicts=manual_conflicts(state,candidate),family_impacts=family_impacts(state,candidate),warnings=warnings)


def messages(base, instruction):
    from backend.services.draft_initial import prompt_schema, compact_schema
    from backend.services.draft_initial import SECRET_AUTHORING_RULES
    state=base['state']
    return [dict(role='system',content=MARKER+'\n'+RULES+'\n'+SECRET_AUTHORING_RULES),
            dict(role='user',content=json.dumps(dict(author_context=author_context(base,instruction),
                candidate=state,candidate_hash=candidate_hash(state),
                world_schema=compact_schema(prompt_schema(initial_portraits=True)),response_schema=EditorialProposal.model_json_schema()),ensure_ascii=False,separators=(',',':')))]


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
    from backend.runtime_v3.birth_identity import dob_metadata
    from backend.services.draft_initial import escape
    for cid,actor in before['world']['characters'].items():
        other=after['world']['characters'].get(cid,{})
        if dob_metadata(actor).get('source')=='manual' and actor.get('birth_date')!=other.get('birth_date'):
            path='/world/characters/'+escape(cid)+'/birth_date'
            if path not in conflicts:conflicts.append(path)
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
    from backend.services.draft_response import response
    from backend.services.usage import tracked_stream
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
        return tracked_stream(repo,stream_fn,jid,stage,config,request_messages,model=config['model'],
            provider=config['provider'],api_key=api_key,temperature=config['temperature'],max_tokens=limit,
            require_complete=True,cancel_event=handle.cancel,on_stream=opened,
            **({'response_format':{'type':'json_object'}} if config['provider']=='deepseek' and not any(m['role']=='assistant' for m in request_messages) else {}))
    def call(slot,request_messages):
        return response(repo,jid,journal,slot,request_messages,config,context,generate,handle.cancel)
    if edit.get('action'):
        from backend.services import draft_review_actions
        if edit['action']=='recheck':
            stage='draft_world_validation'
        return draft_review_actions.run(repo,jid,journal,edit,call,epoch,handle.cancel)
    repo.draft_phase(jid,'proposing',reset_progress=True)
    request=journal.setdefault('messages',messages(base,edit['instruction']));save()
    from backend.services.draft_creative import response_slot
    slot=response_slot(journal,edit,candidate_hash([context,config.get('max_tokens')]))
    reply=call(slot,request)
    if reply is None:return
    from backend.services.draft_response import strict_loads
    # Previously completed technical corrections remain reusable on recovery.
    packet=EditorialProposal.model_validate(strict_loads(edit.get('corrected_reply',reply)))
    edit.update(preview(state,packet))
    save()
    repo.finish_world_edit(jid,epoch)
