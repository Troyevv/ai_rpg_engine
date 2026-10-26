"""Read-only semantic validation within the existing bounded draft repair loop.

No prose inference in Python: the provider compares the intact author input with
one generated world. Its report can authorize only localized assignments.
"""
import json
import re
from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, ValidationError, TypeAdapter, model_validator
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
8. Даты рождения и календарная арифметика проверяются и дополняются кодом; null в старом мире допустим. Поездка, война или присутствие в сцене не закрывают постоянное проживание. sibling симметричен и не требует обратной записи. Для качественного дополнения укажи выбранные слабые поля в patch_paths, severity=recommendation, assertion=optional_detail; оценивай полезность для игры, не длину текста.
9. Сцена должна сохранять заданные место, состав, время и действия на момент старта; не добавляй уже исполненные решения игрока после начала игры.
Для утверждения об отсутствии значения используй assertion="missing_value" и точный path поля; для отсутствующей ссылки assertion="missing_reference", path одиночного строкового ID и target_path словаря целей. Для отсутствующей структурированной записи assertion="missing_record", section с именем коллекции и record_match с её идентифицирующими полями (например actor_id и kind). Технический ID и patch_paths новой записи определит сервер. Не применяй missing_reference к dict/list и не заменяй коллекцию; необязательное обогащение assertion="optional_detail". Код сверит такие утверждения с кандидатом. Остальные противоречия assertion="semantic": укажи basis из ссылок {path}; значения прочитает сервер несовместимых утверждений и объясни несовместимость в message. Разное текущее место и постоянное жильё совместимы. Неоднозначность требует уточнения, не закрытия проживания. Для явного окончания проживания укажи lifecycle_decision=close и basis со ссылкой на подтверждающее обстоятельство вне самой residence; количество оснований само по себе ничего не доказывает. Для исправления ошибочного закрытия используй lifecycle_decision=correct. Для удаления ошибочной residence отдельно укажи remove_paths; path или patch_paths сами не разрешают удаление.
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


CONTRACT_VERSION = 7
RECOVERY_POLICY = 3

class ReviewBasis(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    path: str
    value: object = None


class ReviewIssue(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    path: str | None = None
    section: str | None = None
    entity_id: str | None = None
    field: str | None = None
    issue_id: str | None = None
    message: str = Field(min_length=1)
    related_paths: list[str] = Field(default_factory=list)
    severity: Literal['blocker', 'recommendation'] = 'blocker'
    patch_paths: list[str] | None = None
    assertion: Literal['semantic','missing_value','missing_reference','missing_record','optional_detail'] = 'semantic'
    target_path: str | None = None
    record_match: dict[str, str | int | bool | None] | None = None
    basis: list[ReviewBasis] = Field(default_factory=list)
    remove_paths: list[str] = Field(default_factory=list)
    lifecycle_decision: Literal['retain','correct','close'] | None = None

    @model_validator(mode='after')
    def conditional_shape(self):
        if self.assertion=='optional_detail' and self.severity=='blocker' and 'severity' in self.model_fields_set:
            raise ValueError('optional_detail несовместим с явным blocker.')
        if self.assertion=='optional_detail':self.severity='recommendation'
        if self.assertion=='missing_record':
            # Explicit v1–v5 adapter; new requests use section and server IDs.
            if not self.section and isinstance(self.path,str) and self.path.startswith('/world/') and len(self.path.split('/'))==3:
                self.section=self.path.split('/')[2]
            if not self.section or not self.record_match:raise ValueError('missing_record требует section и непустой record_match.')
        elif self.assertion in ('missing_value','missing_reference'):
            if not isinstance(self.path,str):raise ValueError('Для утверждения требуется path одиночного поля.')
            if self.assertion=='missing_reference' and not isinstance(self.target_path,str):raise ValueError('Для missing_reference нужен target_path.')
        elif self.assertion=='semantic' and self.severity=='blocker':
            if not isinstance(self.path,str) and not (self.section and self.entity_id):raise ValueError('Для противоречия нужен path или section/entity_id.')
        return self

class ReviewReport(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    issues: list[ReviewIssue]

class ReportError(ValueError):
    def __init__(self, errors, issues=None):
        self.errors = [{'stage':'review','contract_version':CONTRACT_VERSION,'code':'invalid_report',**e} for e in errors]
        self.issues = issues or []
        super().__init__('; '.join(e['report_path']+': '+e['message'] for e in errors))


def report_schema():
    schema = ReviewReport.model_json_schema()
    item = schema['$defs']['ReviewIssue']
    # The provider sees the same conditional contract that parse enforces.
    item['allOf'] = [
        {'if': {'properties': {'assertion': {'const': kind}}, 'required': ['assertion']},
         'then': {'required': required, 'properties': properties}}
        for kind, required, properties in [
            ('missing_reference', ['path', 'target_path'], {'path': {'type': 'string'}, 'target_path': {'type': 'string'}}),
            ('missing_value', ['path'], {'path': {'type': 'string'}}),
            ('missing_record', ['section', 'record_match'], {'section': {'enum': sorted(EXTENSIONS)}, 'record_match': {'type': 'object', 'minProperties': 1}}),
        ]]
    item['allOf'].append({'if':{'properties':{'assertion':{'const':'semantic'},'severity':{'not':{'const':'recommendation'}}}},'then':{'anyOf':[{'required':['path'],'properties':{'path':{'type':'string'}}},{'required':['section','entity_id'],'properties':{'section':{'type':'string'},'entity_id':{'type':'string'}}}]}})
    item['allOf'].append({'if':{'properties':{'assertion':{'const':'optional_detail'}},'required':['assertion']},'then':{'properties':{'severity':{'const':'recommendation'}}}})
    return schema


def typed_schema(model):
    schema=model.model_json_schema();definitions=report_schema()['$defs']
    schema.setdefault('$defs',{}).update(definitions)
    for node in [schema,*schema['$defs'].values()]:
        if 'issues' in node.get('properties',{}):node['properties']['issues']['items']={'$ref':'#/$defs/ReviewIssue'}
    return schema


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


def escape(value):
    return value.replace('~','~0').replace('/','~1')


def issue_identity(item):
    """Stable across array reordering and recovery epochs; never mutation rights."""
    import hashlib
    return hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def record_predicate(state, issue):
    section=issue.section or (issue.path.split('/')[2] if isinstance(issue.path,str) and issue.path.startswith('/world/') and len(issue.path.split('/'))==3 else None)
    if section not in EXTENSIONS:raise ValueError('missing_record требует известный тип коллекции section.')
    issue.section=section;issue.path='/world/'+section
    matcher=issue.record_match
    if not matcher:raise ValueError('Нужен непустой типизированный record_match.')
    model=EXTENSIONS[section]
    for key,value in matcher.items():
        if key not in model.model_fields:raise ValueError('Неизвестное поле matcher: '+key)
        field=model.model_fields[key]
        TypeAdapter(Annotated[field.annotation, *field.metadata] if field.metadata else field.annotation).validate_python(value, strict=True)
    required={'objective_relations':{'source_id','target_id','kind'},'roles':{'actor_id','kind'},'residences':{'actor_id','location_id'},'organizations':{'name'},'possessions':{'name','owner_id'}}.get(section,{'id'})
    if not required <= matcher.keys():raise ValueError('Matcher должен идентифицировать запись: '+', '.join(sorted(required)))
    if 'source_id' in matcher and matcher.get('source_id')==matcher.get('target_id'):raise ValueError('Участники связи должны различаться.')
    for key in ('actor_id','source_id','target_id'):
        if key in matcher and matcher[key] not in state['world']['characters']:raise ValueError('Неизвестный участник matcher: '+key)
    if 'location_id' in matcher and matcher['location_id'] not in {r['id'] for r in state['locations']}:raise ValueError('Неизвестная локация matcher.')
    if len(issue.patch_paths or [])>1:raise ValueError('Один matcher описывает одну запись. Разделите объединённое замечание.')
    actual=pointer(state,issue.path)
    if not isinstance(actual,dict):raise ValueError('Ожидалась коллекция записей.')
    def matches(row, match):return isinstance(row,dict) and all(k in row and type(row[k]) is type(v) and row[k]==v for k,v in match.items())
    candidates=[matcher]
    if section=='objective_relations' and matcher['kind'] in ('spouse','partner','engaged','sibling','friend','close_friend','coworker'):
        candidates.append(dict(matcher,source_id=matcher['target_id'],target_id=matcher['source_id']))
    # An omitted phase means the requested current record, never a historical one.
    if 'status' in model.model_fields:
        candidates=[{'status':'active',**m} for m in candidates]
    disproved=any(matches(dict(status='active',**row) if 'status' not in row and 'status' in model.model_fields else row,m) for row in actual.values() if isinstance(row,dict) for m in candidates)
    if not disproved:
        ident='generated_'+issue_identity({'section':section,'match':matcher})
        issue.patch_paths=['/world/'+section+'/'+ident]
    return disproved


def resolve_subject(state, issue):
    if issue.assertion=='missing_record':return
    if issue.section and issue.entity_id:
        if issue.section in ('characters','locations'):
            indexes=[i for i,r in enumerate(state.get(issue.section,[])) if r.get('id')==issue.entity_id]
            if len(indexes)!=1:raise ValueError('Неоднозначный адрес сущности.')
            path='/'+issue.section+'/'+str(indexes[0])
        elif issue.section in SECTIONS:path='/world/'+issue.section+'/'+escape(issue.entity_id)
        else:raise ValueError('Неизвестный раздел.')
        if issue.field:path+='/'+escape(issue.field)
        pointer(state,path)
        issue.path=path
        if issue.field and issue.patch_paths is None:issue.patch_paths=[path]


def messages(state, author_context):
    candidate={k:deepcopy(state[k]) for k in ('campaign','characters','locations','world','world_clock','camera','controlled_actor_id','protagonist_id')}
    schema={k:runtime_schema(EXTENSIONS[k]) for k in ('objective_relations','roles','residences','organizations')}
    example=ReviewReport(issues=[ReviewIssue(path='/world/roles/new_id',message='Конкретное противоречие',patch_paths=['/world/roles/new_id'])]).model_dump()
    return [dict(role='system',content=MARKER+'\n'+RULES),dict(role='user',content=json.dumps(
        dict(author_context=author_context,candidate=candidate,address_guide=address_guide(candidate),record_schemas=schema,report_schema=report_schema(),example=example,contract_version=CONTRACT_VERSION),ensure_ascii=False,separators=(',',':')))]


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
    original=strict_loads(previous)
    if isinstance(report,dict) and set(report)=={'replacements'}:
        from backend.services.draft_protocol import Correction,decode
        replacements=decode(Correction,reply,'correction').model_dump()['replacements']
        expected={issue_identity(original['issues'][i]):i for i in indices}
        if not isinstance(replacements,list) or len(replacements)!=len(expected):
            raise ReportError([dict(report_path='/',world_path=None,message='Нужна замена каждого отклонённого issue_id.')])
        changes={}
        for replacement in replacements:
            if not isinstance(replacement,dict) or set(replacement)!={'issue_id','issues'} or replacement['issue_id'] not in expected or replacement['issue_id'] in changes or not isinstance(replacement['issues'],list) or not replacement['issues']:
                raise ReportError([dict(report_path='/',world_path=None,message='Пустая, повторная или неизвестная замена замечания.')])
            changes[replacement['issue_id']]=replacement['issues']
        original['issues']=[new for item in original['issues'] for new in changes.get(issue_identity(item),[item])]
        return json.dumps(original,ensure_ascii=False)
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
    rejected_items=[]
    if indices is not None:
        rejected=strict_loads(reply)
        rejected_items=[dict(issue_id=issue_identity(rejected['issues'][i]),issue=rejected['issues'][i]) for i in indices]
        for entry in rejected_items:
            item=entry['issue']
            if not isinstance(item,dict):continue
            def array(key):return item[key] if isinstance(item.get(key),list) else []
            refs=[r for r in array('related_paths') if isinstance(r,str)] + [b['path'] for b in array('basis') if isinstance(b,dict) and isinstance(b.get('path'),str)]
            for path in array('patch_paths'):
                if isinstance(path,str):refs.append(path.rsplit('/',1)[0])
            for ref in refs:
                try:context[ref]=pointer(state,ref)
                except (ValueError,KeyError,IndexError,TypeError):pass
        reply=json.dumps({'issues':[rejected['issues'][i] for i in indices]},ensure_ascii=False)
    from backend.services.draft_protocol import Correction
    return [dict(role='system',content=MARKER+' Исправь повреждённые пункты отчёта по response_schema. Мир не изменяй.'),dict(role='user',content=json.dumps(dict(
        response_schema=typed_schema(Correction) if indices is not None else report_schema(),rejected_items=rejected_items,replacement_contract='Верни replacements: [{issue_id, issues:[исправленные пункты]}]. Можно разделить пункт; сохрани соседей.' if indices is not None else 'Верни полный исправленный report с issues.',
        original_indices=indices,reply_scope='Верни replacements по issue_id; остальные пункты сохранены кодом.' if indices is not None else 'Исправь внешнюю структуру отчёта.',
        instruction='Исправь только отчёт по конкретным ошибкам валидации, не выполняй новый аудит мира. Не меняй мир. Не удаляй замечания ради прохождения проверки. Сохрани корректные замечания и их содержание. Корень JSON Pointer — candidate, без префикса candidate.',
        author_context=payload.get('author_context'),address_guide=payload.get('address_guide',{}),related_context=context,
        rejected_response=reply,validation_errors=errors,report_schema=report_schema()),ensure_ascii=False,separators=(',',':')))]


def _parse(reply, state):
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
            if advisory(item):
                problems.append(error('',str(item.get('message') or 'Неверное необязательное замечание'),'review_advisory_invalid',severity='recommendation',patch_paths=[],protocol_warnings=[dict(report_path=base,message=e['msg']) for e in exc.errors(include_input=False)],original_issue=item))
                continue
            errors.extend(dict(report_path=base+'/'+ '/'.join(map(str,e['loc'])),world_path=item.get('path') if isinstance(item,dict) else None,message=e['msg']) for e in exc.errors(include_input=False));continue
        before=len(errors);warnings=[];verified_basis=[]
        try:resolve_subject(state,issue)
        except (ValueError,KeyError,IndexError,TypeError) as exc:
            errors.append(dict(report_path=base+'/section',world_path=issue.path,message=str(exc)));continue
        for j,basis in enumerate(issue.basis):
            try:
                if 'value' in basis.model_fields_set and pointer(state,basis.path)!=basis.value:raise ValueError('Основание не совпадает с кандидатом.')
                verified_basis.append(dict(path=basis.path,value=pointer(state,basis.path)))
            except (ValueError,KeyError,IndexError,TypeError) as exc:
                entry=dict(report_path=base+f'/basis/{j}',world_path=basis.path,message=str(exc))
                if issue.severity=='recommendation' or issue.assertion=='optional_detail':
                    warnings.append(entry);issue.patch_paths=[];issue.remove_paths=[]
                else:errors.append(entry)
        for j,path in enumerate(issue.remove_paths):
            try:
                parts=path.split('/')
                if len(parts)!=4 or parts[1:3]!=['world','residences'] or not isinstance(pointer(state,path),dict):
                    raise ValueError('Удаление требует точного адреса существующего проживания.')
            except (ValueError,KeyError,IndexError,TypeError) as exc:
                errors.append(dict(report_path=base+f'/remove_paths/{j}',world_path=path,message=str(exc)))
        # Machine-verifiable claims use a typed predicate, never prose matching.
        if issue.assertion != 'semantic':
            if issue.assertion == 'optional_detail':
                issue.severity='recommendation'
            else:
                try:
                    actual=None if issue.assertion=='missing_record' else pointer(state,issue.path)
                    if issue.assertion=='missing_value': disproved=actual is not None and actual != '' and actual != [] and actual != {} and (not isinstance(actual,str) or bool(actual.strip()))
                    elif issue.assertion=='missing_record':
                        disproved=record_predicate(state,issue)
                    else:
                        if not isinstance(actual,str) or not actual.strip():
                            raise ValueError('missing_reference требует одиночный непустой строковый ID в path. Для отсутствующей записи используй missing_record, section и record_match; технический ID определит сервер, коллекцию заменять нельзя.')
                        if not issue.target_path:raise ValueError('Для missing_reference нужен target_path.')
                        if issue.target_path not in {'/world/'+name for name in SECTIONS}:raise ValueError('target_path должен указывать каноническую коллекцию по ID.')
                        try:target=pointer(state,issue.target_path)
                        except KeyError as exc:raise ValueError('Коллекция target_path отсутствует.') from exc
                        if not isinstance(target,dict):raise ValueError('target_path должен указывать словарь записей по ID.')
                        disproved=actual in target
                except KeyError:disproved=False
                except (TypeError,ValueError,IndexError) as exc:
                    errors.append(dict(report_path=base+'/assertion',world_path=issue.path,message=str(exc)));continue
                if disproved:
                    problems.append(error(issue.path,issue.message,'review_disproved',severity='recommendation',patch_paths=[],assertion=issue.assertion,target_path=issue.target_path,record_match=issue.record_match,original_issue=item,server_verification='disproved'))
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
            problems.append(error(issue.path or '',issue.message,'semantic_completeness',related_paths=valid_related,severity=issue.severity,patch_paths=safe_paths,remove_paths=issue.remove_paths,lifecycle_decision=issue.lifecycle_decision,basis=verified_basis,assertion=issue.assertion,target_path=issue.target_path,record_match=issue.record_match,original_issue=original,**(dict(protocol_warnings=warnings) if warnings else {})))
    for problem in problems:problem['issue_id']=issue_identity(problem.get('original_issue',problem))
    if errors:raise ReportError(errors,problems)
    return problems


def advisory(item):
    if not isinstance(item,dict):return False
    kind=item.get('assertion','semantic');severity=item.get('severity')
    if kind not in ('semantic','missing_value','missing_reference','missing_record','optional_detail'):return False
    return severity=='recommendation' or (kind=='optional_detail' and severity is None)


def parse(reply,state):
    try:report=strict_loads(reply)
    except ValueError:return _parse(reply,state)
    if not isinstance(report,dict) or set(report)!={'issues'} or not isinstance(report['issues'],list):return _parse(reply,state)
    problems=[];errors=[]
    for i,item in enumerate(report['issues']):
        def addressed(entries):
            return [dict(e,report_path=re.sub(r'^/issues/0(?=/|$)',f'/issues/{i}',e['report_path']),issue_id=issue_identity(item)) for e in entries]
        try:rows=_parse(json.dumps({'issues':[item]},ensure_ascii=False),state)
        except ReportError as exc:
            if not advisory(item):
                errors.extend(addressed(exc.errors));problems.extend(exc.issues);continue
            rows=[error('',str(item.get('message') or 'Неверный совет'),'review_advisory_invalid',severity='recommendation',original_issue=item,protocol_warnings=addressed(exc.errors))]
        for row in rows:
            if row.get('protocol_warnings'):row['protocol_warnings']=addressed(row['protocol_warnings'])
            if row.get('protocol_warnings') and advisory(item):
                row.update(patch_paths=[],remove_paths=[],related_paths=[],basis=[],lifecycle_decision=None,original_issue=item)
            row['issue_id']=issue_identity(item)
        problems.extend(rows)
    if errors:raise ReportError(errors,problems)
    return problems
