"""Read-only semantic validation within the existing bounded draft repair loop.

No prose inference in Python: the provider compares the intact author input with
one generated world. Its report can authorize only localized assignments.
"""
import json
import re
from copy import deepcopy
from backend.services.draft_initial import error, runtime_schema, EXTENSIONS
from backend.services.draft_response import strict_loads

MARKER = 'Проверка полноты начального мира Runtime v4.'
RULES = '''Проверь исходный замысел и уже утверждённые данные результата, не создавай мир заново.
Верни только {"issues":[{"path":"/world/roles/new_id","message":"конкретная проблема и требуемое исправление","related_paths":["/characters/0"]}]}.
Пустой issues допустим только после проверки всех пунктов. Не возвращай цитаты/spans, планы или новый мир.
Проверяй значимые обстоятельства, а не заполненность необязательных полей:
1. Родители/усыновители, братья/сёстры, дружба, коллеги должны иметь objective_relations; эмоциональный relationships не заменяет их. adoptive_parent не parent. Не требуй все пары. Социальный sibling не доказывает биологическое родство.
2. Указанные профессии и учёба требуют roles, известное постоянное проживание — residences. Текущее нахождение не означает проживание. Уход из дома не означает новую постоянную прописку.
3. Отдельные компании группы отражаются organizations и facts.claim(predicate=parent_organization). Направление деятельности/отдел не становится отдельным юридическим лицом без основания.
4. Сопоставь объективные facts, events, участников, свидетелей и knowledge К НАЧАЛУ игры. «Никто не знал» до раскрытия не означает unknown после него. Знание не распространяется на отсутствовавших. Уточнение автора о событии раскрытия важнее прежнего описания тайны. При неоднозначности выбери согласованную трактовку, сохраняя явные ограничения автора. Для раскрытия добавь событие и source_event_id; не переписывай истинность факта ради знания.
5. Числовое world_clock.minute авторитетно; строковые проекции не источник времени. Calendar должен соответствовать дате/дню недели/времени автора и сцены. Если только пятница 08:00 — start_date=null, start_weekday=4, время 08:00; календарный anchor может привязать пятницу к существующей минуте. Не назначай дату произвольно. Для обычного современного мира profile.system=gregorian. Для иной эпохи/мира учитывай заданный календарь.
6. Вчера вечером не час назад сегодняшним утром. Не придумывай точные минуты событий: если точное время неизвестно, minute=null, обстоятельства остаются в text/evidence и source_sequence. История предшествует сцене. Проверь связанные временные поля вместе.
7. controlled_actor_id: начальный образ, эмоции и предысторию можно творчески дополнить. Не выполняй будущие добровольные действия игрока, не предрешай согласие; активные intentions/obligations требуют явного основания в авторском вводе. Черта характера не намерение; не удаляй заданные автором стремления. NPC вправе иметь творчески дополненные цели.
8. Сцена должна сохранять заданные место, состав, время и действия на момент старта; не добавляй уже исполненные решения игрока после начала игры.
Каждая проблема указывает точный JSON Pointer к изменяемому полю. Для отсутствующей записи используй /world/<раздел>/<новый_ID>, не весь раздел. Для существующей записи укажи поле, не всю запись. Для массива исправляй только нужное поле целиком. Нельзя заменять весь world, персонажей, коллекцию записей или литературную карточку ради пропущенной связи. related_paths — только существующие необходимые связанные записи/поля, не весь мир. Не объявляй отсутствие optional ошибкой без смыслового основания. Идея — творческая основа, не перечень разрешённых фактов. Новые непротиворечивые персонажи, секреты, биографии и обстоятельства допустимы и становятся истиной мира. Используй их как основания для roles, objective_relations, residences, facts и knowledge. Отсутствие в исходном тексте не ошибка. Не требуй цитат или согласования дополнений. Необязательное литературное обогащение помечай severity="recommendation"; блокирующие противоречия — severity="blocker". Техническая ошибка самого отчёта не доказывает ошибку мира.'''
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


def messages(state, author_context):
    # Exclude compatibility copies only. Author cards/backstories are intact.
    candidate={k:deepcopy(state[k]) for k in ('campaign','characters','locations','world','world_clock','camera','controlled_actor_id','protagonist_id')}
    schema={k:runtime_schema(EXTENSIONS[k]) for k in ('objective_relations','roles','residences','organizations')}
    return [dict(role='system',content=MARKER+'\n'+RULES),dict(role='user',content=json.dumps(
        dict(author_context=author_context,world=candidate,record_schemas=schema),ensure_ascii=False))]


def parse(reply, state):
    report=strict_loads(reply)
    if not isinstance(report,dict) or set(report)!={'issues'} or not isinstance(report['issues'],list):
        raise ValueError('Проверка полноты вернула неверный отчёт; мир не принят.')
    problems=[]
    for item in report['issues']:
        if not isinstance(item,dict) or set(item)-{'path','message','related_paths','severity'}:
            raise ValueError('Некорректная диагностика полноты.')
        path=item.get('path');message=item.get('message');related=item.get('related_paths',[])
        if not isinstance(path,str) or not isinstance(message,str) or not message.strip() or not isinstance(related,list):
            raise ValueError('Нужны точный путь, описание ошибки и связанные записи.')
        parts=path.split('/')[1:]
        allowed=(len(parts)>=3 and parts[0]=='world' and parts[1] in SECTIONS) or (len(parts)>=2 and parts[0] in ('world_clock','camera'))
        allowed = allowed or path in ('/controlled_actor_id','/protagonist_id')
        if not allowed: raise ValueError('Проверка полноты запросила слишком широкое изменение: '+path)
        try:
            existing=pointer(state,path)
        except KeyError:
            # New entries/fields only in an existing parent, never a new root.
            pointer(state,path.rsplit('/',1)[0])
        else:
            if isinstance(existing,dict) and len(parts)==3 and parts[0]=='world':
                raise ValueError('Исправляйте поля существующей записи: '+path)
        for ref in related:
            if not isinstance(ref,str) or (len(ref.split('/'))<3 and ref not in ('/controlled_actor_id','/protagonist_id')):
                raise ValueError('Связанный контекст должен указывать запись или поле.')
            pointer(state,ref)
        severity=item.get('severity','blocker')
        if severity not in ('blocker','recommendation'):raise ValueError('Неизвестная категория замечания.')
        problems.append(error(path,message,'semantic_completeness',related_paths=related,severity=severity))
    # No arbitrary truncation of diagnostics.
    return problems
