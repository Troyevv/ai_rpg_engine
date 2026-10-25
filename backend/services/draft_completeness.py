"""Read-only semantic validation within the existing bounded draft repair loop.

No prose inference in Python: the provider compares the intact author input with
one generated world. Its report can authorize only localized assignments.
"""
import json
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from copy import deepcopy
from backend.services.draft_initial import error, runtime_schema, EXTENSIONS
from backend.services.draft_response import strict_loads

MARKER = 'Проверка полноты начального мира Runtime v4.'
RULES = '''Проверь исходный замысел и уже утверждённые данные результата, не создавай мир заново.
Верни JSON по приложенной report_schema. В issues включай только проблемы: не добавляй записи «всё корректно», «соответствует», «противоречий нет». Не помечай реальное противоречие recommendation только потому, что оно литературное. Сверь возраст и порядок рождения/усыновления в биографиях, location с situation. facts.character_ids — участники факта, НЕ список знающих; знание определяется knowledge.
Пустой issues допустим только после проверки всех пунктов. Не возвращай цитаты/spans, планы или новый мир.
Проверяй значимые обстоятельства, а не заполненность необязательных полей:
1. Родители/усыновители, братья/сёстры, дружба, коллеги должны иметь objective_relations; эмоциональный relationships не заменяет их. adoptive_parent не parent. Не требуй все пары. Социальный sibling не доказывает биологическое родство. В context/evidence могут быть сохранены несколько описаний одной симметричной активной связи. Разные формулировки и обратный порядок участников сами по себе не противоречие. Проверь согласованность всех описаний с фактами и биографиями; реальное противоречие требует локального patch точных полей, а не закрытия связи ради удаления дубля.
Отсутствующее неизвестное жильё, неизвестная дата рождения и неполные необязательные dimensions не являются блокерами. Не требуй взаимности чувств, attraction в ответ на любовь, связей каждой пары, обязательных целей/тайн/травм. Работа, текущая локация и город не доказывают проживание в здании; проживание при мастерской допустимо при сюжетном основании. При ошибочном residence разреши локально удалить запись или создать подходящую локацию вместе с привязкой. Не превращай приглашение в переезд или согласие игрока.
2. Указанные профессии и учёба требуют roles, известное постоянное проживание — residences. Текущее нахождение не означает проживание. Уход из дома не означает новую постоянную прописку.
3. Отдельные компании группы отражаются organizations и facts.claim(predicate=parent_organization). Направление деятельности/отдел не становится отдельным юридическим лицом без основания.
4. Сопоставь объективные facts, events, участников, свидетелей и knowledge К НАЧАЛУ игры. «Никто не знал» до раскрытия не означает unknown после него. Знание не распространяется на отсутствовавших. Уточнение автора о событии раскрытия важнее прежнего описания тайны. При неоднозначности выбери согласованную трактовку, сохраняя явные ограничения автора. При явно описанном событии раскрытия сохрани событие и его ссылку; source_event_id=null допустим для исходного знания без отдельного события; не переписывай истинность факта ради знания.
5. Начало игры разрешается кодом из явных настроек, затем авторского начала. Числовой ответ модели не переопределяет эти значения. Календарная арифметика и DOB проверяются кодом; не запрашивай повторные технические исправления корректных значений. Calendar должен соответствовать дате/дню недели/времени автора и сцены. Если только пятница 08:00 — start_date=null, start_weekday=4, время 08:00; календарный anchor может привязать пятницу к существующей минуте. Не назначай дату произвольно. Для обычного современного мира profile.system=gregorian. Для иной эпохи/мира учитывай заданный календарь.
6. Вчера вечером не час назад сегодняшним утром. Не придумывай точные минуты событий: если точное время неизвестно, minute=null, обстоятельства остаются в text/evidence и source_sequence. История предшествует сцене. Проверь связанные временные поля вместе.
7. controlled_actor_id: начальный образ, эмоции и предысторию можно творчески дополнить. Не выполняй будущие добровольные действия игрока, не предрешай согласие; активные intentions/obligations требуют явного основания в авторском вводе. Черта характера не намерение; не удаляй заданные автором стремления. NPC вправе иметь творчески дополненные цели.
8. При новой генерации допустима творчески выбранная дата рождения, согласованная с точным возрастом и текущей датой календаря; авторские даты и запреты сохраняются. Старое birth_date=null не ошибка и не требует заполнения.
9. Сцена должна сохранять заданные место, состав, время и действия на момент старта; не добавляй уже исполненные решения игрока после начала игры.
Для утверждения об отсутствии значения используй assertion="missing_value" и точный path поля; для отсутствующей ссылки assertion="missing_reference", path поля ссылки и target_path коллекции целей; необязательное обогащение assertion="optional_detail". Код сверит такие утверждения с кандидатом. Остальные противоречия assertion="semantic".
path — диагностический JSON Pointer относительно candidate (не обёртки запроса): /world/roles/id, НЕ /candidate/world/roles/id и НЕ /world/world/roles/id. Диагностика может указывать существующую запись целиком, но это НЕ разрешение заменить запись. patch_paths — отдельный список точных полей для исправления; для новой записи разрешён /world/<раздел>/<новый_ID> при существующем родителе. Не заменяй существующие записи, карточки, коллекции или весь мир. Для recommendation допустим path=null и пустой patch_paths. Для blocker уточни patch_paths до конкретных полей; если это невозможно, сохрани замечание без разрешения на patch. related_paths — существующие связанные записи/поля. Не объявляй отсутствие optional ошибкой без смыслового основания. Идея — творческая основа, не перечень разрешённых фактов. Новые непротиворечивые персонажи, секреты, биографии и обстоятельства допустимы и становятся истиной мира. Используй их как основания для roles, objective_relations, residences, facts и knowledge. Отсутствие в исходном тексте не ошибка. Не требуй цитат или согласования дополнений. Необязательное литературное обогащение помечай severity="recommendation"; блокирующие противоречия — severity="blocker". Техническая ошибка самого отчёта не доказывает ошибку мира.'''
SECTIONS = {'objective_relations','roles','residences','organizations','facts','knowledge','events','scenes','characters','relationships','threads','conditions','possessions','scheduled_events'}


def pointer(value, path):
    if not isinstance(path,str) or not path.startswith('/') or re.search(r'~(?![01])',path):
        raise ValueError('Некорректный JSON Pointer проверки полноты.')
    parts=[p.replace('~1','/').replace('~0','~') for p in path[1:].split('/')]
    current=value
    for p in parts:
        if isinstance(current,list):
            if not re.fullmatch(r'0|[1-9]\d*',p):raise ValueError('Некорректный индекс массива.')
            current=current[int(p)]
        else:current=current[p]
    return current


CONTRACT_VERSION = 4

class ReviewIssue(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    path: str | None = None
    message: str = Field(min_length=1)
    related_paths: list[str] = Field(default_factory=list)
    severity: Literal['blocker', 'recommendation'] = 'blocker'
    patch_paths: list[str] | None = None
    assertion: Literal['semantic','missing_value','missing_reference','optional_detail'] = 'semantic'
    target_path: str | None = None

class ReviewReport(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    issues: list[ReviewIssue]

class ReportError(ValueError):
    def __init__(self, errors, issues=None):
        self.errors = errors
        self.issues = issues or []
        super().__init__('; '.join(e['report_path']+': '+e['message'] for e in errors))


def report_schema():
    return ReviewReport.model_json_schema()


def patch_allowed(state, path):
    """Exact assignment permission, independent of diagnostic scope."""
    if not isinstance(path,str) or not path.startswith('/') or path=='/':return False
    parts=path[1:].split('/')
    allowed=(len(parts)>=3 and parts[0]=='world' and parts[1] in SECTIONS)
    allowed=allowed or (len(parts)>=2 and parts[0] in ('world_clock','camera','campaign'))
    allowed=allowed or (len(parts)>=3 and parts[0] in ('characters','locations'))
    allowed=allowed or path in ('/controlled_actor_id','/protagonist_id','/scene')
    if not allowed:return False
    try:existing=pointer(state,path)
    except KeyError:
        parent=pointer(state,path.rsplit('/',1)[0])
        if not isinstance(parent,dict):return False
        # New canonical records and existing schema-defined fields only.
        if len(parts)==3 and parts[0]=='world':return True
        from backend.services.draft_initial import prompt_schema
        schema=prompt_schema()
        for part in parts:
            if schema.get('type')=='array':schema=schema.get('items',{})
            elif part in schema.get('properties',{}):schema=schema['properties'][part]
            elif isinstance(schema.get('additionalProperties'),dict):schema=schema['additionalProperties']
            else:return False
        return bool(schema)
    else:
        if isinstance(existing,dict):return False
        return True


def address_guide(state):
    return dict(roots=list(state), records={
        key:[dict(id=row.get('id'),path=f'/{key}/{i}') for i,row in enumerate(state.get(key,[]))]
        for key in ('characters','locations')},
        examples=['/world_clock/calendar','/characters/0/fields/Биография','/locations/0/name','/world/characters/<ID>/situation'])


def diagnostic_alias(state, path):
    """Resolve only enumerated structural aliases with one existing target.

    Never used for mutation permissions; never strip arbitrary world prefixes.
    """
    if not isinstance(path,str) or re.search(r'~(?![01])',path):return None
    choices=[]
    for old,new in (('/world/world_clock/','/world_clock/'),('/world/calendar/','/world_clock/calendar/')):
        if path.startswith(old):choices.append(new+path[len(old):])
    for key in ('characters','locations'):
        prefix='/'+key+'/'
        # world.characters is a different, canonical dynamic map: do not redirect it.
        prefixes=[prefix]+(['/world/locations/'] if key=='locations' else [])
        for prefix in prefixes:
            if not path.startswith(prefix):continue
            tail=path[len(prefix):].split('/');ident=tail[0].replace('~1','/').replace('~0','~')
            matches=[i for i,row in enumerate(state.get(key,[])) if row.get('id')==ident]
            if len(matches)==1:choices.append('/'+key+'/'+str(matches[0])+('/'+'/'.join(tail[1:]) if len(tail)>1 else ''))
    valid=[]
    for target in set(choices):
        try:pointer(state,target)
        except (ValueError,KeyError,IndexError,TypeError):continue
        valid.append(target)
    return valid[0] if len(valid)==1 else None


def messages(state, author_context):
    candidate={k:deepcopy(state[k]) for k in ('campaign','characters','locations','world','world_clock','camera','controlled_actor_id','protagonist_id')}
    schema={k:runtime_schema(EXTENSIONS[k]) for k in ('objective_relations','roles','residences','organizations')}
    example=ReviewReport(issues=[ReviewIssue(path='/world/roles/new_id',message='Конкретное противоречие',patch_paths=['/world/roles/new_id'])]).model_dump()
    return [dict(role='system',content=MARKER+'\n'+RULES),dict(role='user',content=json.dumps(
        dict(author_context=author_context,candidate=candidate,address_guide=address_guide(candidate),record_schemas=schema,report_schema=report_schema(),example=example,contract_version=CONTRACT_VERSION),ensure_ascii=False))]


def correction_indices(reply, errors):
    try:report=strict_loads(reply)
    except ValueError:return None
    if not isinstance(report,dict) or set(report)!={'issues'} or not isinstance(report['issues'],list):return None
    indices=set()
    for err in errors:
        match=re.match(r'^/issues/(\d+)(?:/|$)',err.get('report_path',''))
        if not match or int(match[1])>=len(report['issues']):return None
        indices.add(int(match[1]))
    return sorted(indices) or None


def merge_correction(reply, previous, errors):
    indices=correction_indices(previous,errors)
    if indices is None:return reply
    report=strict_loads(reply)
    if not isinstance(report,dict) or set(report)!={'issues'} or not isinstance(report['issues'],list) or len(report['issues'])!=len(indices):
        raise ReportError([dict(report_path='/',world_path=None,message='Коррекция должна вернуть по одному пункту на каждый отклонённый, в том же порядке.')])
    original=strict_loads(previous)
    for i,item in zip(indices,report['issues']):original['issues'][i]=item
    return json.dumps(original,ensure_ascii=False)


def correction(messages, reply, errors):
    # Do not append a growing chain of full audits for a single bad address.
    payload=json.loads(messages[1]['content'])
    state=payload.get('candidate',{})
    context={}
    for err in errors:
        path=err.get('world_path')
        if not isinstance(path,str):continue
        alias=diagnostic_alias(state,path)
        for ref in (alias,path):
            if not ref:continue
            try:context[ref]=pointer(state,ref)
            except (ValueError,KeyError,IndexError,TypeError):pass
    indices=correction_indices(reply,errors)
    if indices is not None:
        rejected=strict_loads(reply)
        reply=json.dumps({'issues':[rejected['issues'][i] for i in indices]},ensure_ascii=False)
    return [messages[0],dict(role='user',content=json.dumps(dict(
        original_indices=indices,reply_scope='Верни только отклонённые пункты, по одному в исходном порядке; остальные сохранены кодом.' if indices is not None else 'Исправь внешнюю структуру отчёта.',
        instruction='Исправь только отчёт по конкретным ошибкам валидации, не выполняй новый аудит мира. Не меняй мир. Не удаляй замечания ради прохождения проверки. Сохрани корректные замечания и их содержание. Корень JSON Pointer — candidate, без префикса candidate.',
        author_context=payload.get('author_context'),address_guide=payload.get('address_guide',{}),related_context=context,
        rejected_response=reply,validation_errors=errors,report_schema=report_schema()),ensure_ascii=False))]


def parse(reply, state):
    try:report=strict_loads(reply)
    except ValueError as exc:raise ReportError([dict(report_path='/',world_path=None,message=str(exc))]) from exc
    try:
        # Validate envelope independently so valid items survive an invalid sibling.
        ReviewReport.model_validate(dict(report,issues=[]) if isinstance(report,dict) and 'issues' in report and isinstance(report['issues'],list) else report)
    except ValidationError as exc:
        raise ReportError([dict(report_path='/'+ '/'.join(map(str,e['loc'])),world_path=None,message=e['msg']) for e in exc.errors(include_input=False)]) from exc
    problems=[];errors=[]
    for i,item in enumerate(report['issues']):
        base=f'/issues/{i}'
        try:issue=ReviewIssue.model_validate(item)
        except ValidationError as exc:
            errors.extend(dict(report_path=base+'/'+ '/'.join(map(str,e['loc'])),world_path=item.get('path') if isinstance(item,dict) else None,message=e['msg']) for e in exc.errors(include_input=False));continue
        before=len(errors);warnings=[]
        # Machine-verifiable claims use a typed predicate, never prose matching.
        if issue.assertion != 'semantic':
            if issue.assertion == 'optional_detail':
                issue.severity='recommendation';issue.patch_paths=[]
            else:
                try:
                    actual=pointer(state,issue.path)
                    if issue.assertion=='missing_value': disproved=actual is not None
                    else:
                        if not issue.target_path:raise ValueError('Для missing_reference нужен target_path.')
                        target=pointer(state,issue.target_path)
                        disproved=isinstance(target,dict) and actual in target
                except KeyError:disproved=False
                except (TypeError,ValueError,IndexError) as exc:
                    errors.append(dict(report_path=base+'/assertion',world_path=issue.path,message=str(exc)));continue
                if disproved:
                    problems.append(error(issue.path,issue.message,'review_disproved',severity='recommendation',patch_paths=[],assertion=issue.assertion))
                    continue

        def invalid(field,path,exc):
            entry=dict(report_path=base+'/'+field,world_path=path,message=str(exc))
            if issue.severity=='recommendation' and field!='message':warnings.append(entry)
            else:errors.append(entry)
        original=issue.model_dump()
        def resolve(ref,field):
            try:pointer(state,ref);return ref
            except (ValueError,KeyError,IndexError,TypeError):
                target=diagnostic_alias(state,ref)
                if target:
                    warnings.append(dict(report_path=base+'/'+field,world_path=ref,resolved_path=target,message='Однозначный адресный алиас. Разрешение patch не расширено.'))
                    return target
                return ref
        if issue.path is not None:issue.path=resolve(issue.path,'path')
        issue.related_paths=[resolve(ref,f'related_paths/{j}') for j,ref in enumerate(issue.related_paths)]
        if not issue.message.strip():invalid('message',issue.path,'Описание пустое.')
        if issue.path is not None:
            try:
                try:pointer(state,issue.path)
                except KeyError:
                    if not patch_allowed(state,issue.path):raise ValueError('Адрес отсутствует; требуется существующий родитель и допустимое поле.')
            except (ValueError,KeyError,IndexError,TypeError) as exc:
                invalid('path',issue.path,exc)
                if issue.severity=='recommendation':issue.path=None
        elif issue.severity=='blocker':invalid('path',None,'Для противоречия нужен диагностический адрес.')
        valid_related=[]
        for j,ref in enumerate(issue.related_paths):
            try:
                if ref in ('','/','/world') or len(ref.split('/'))<3 and ref not in ('/controlled_actor_id','/protagonist_id'):raise ValueError('Связанный адрес слишком широкий.')
                pointer(state,ref);valid_related.append(ref)
            except (ValueError,KeyError,IndexError,TypeError) as exc:invalid(f'related_paths/{j}',ref,exc)
        paths=issue.patch_paths
        # Backward-compatible normalization: only an already exact safe field.
        if paths is None:
            try:paths=[original['path']] if patch_allowed(state,original['path']) else []
            except (ValueError,KeyError,IndexError,TypeError):paths=[]
        safe_paths=[]
        for j,path in enumerate(paths):
            try:
                if not patch_allowed(state,path):raise ValueError('Не разрешено заменять этот объект; укажите точное поле.')
                safe_paths.append(path)
            except (ValueError,KeyError,IndexError,TypeError) as exc:invalid(f'patch_paths/{j}',path,exc)
        if issue.message.strip():
            warnings+=errors[before:]
            problems.append(error(issue.path or '',issue.message,'semantic_completeness',related_paths=valid_related,severity=issue.severity,patch_paths=safe_paths,**(dict(protocol_warnings=warnings,original_issue=original) if warnings else {})))
    if errors:raise ReportError(errors,problems)
    return problems
