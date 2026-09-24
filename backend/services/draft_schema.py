"""Canonical JSON Schema contract for a newly generated World State.

The runtime accepts older saves via prepare/normalize; this contract describes
the richer initial output expected from the single world generation request.
"""
from backend.services.world import CARD_FIELDS


def obj(properties, required=(), description='', additional=True):
    return {'type': 'object', 'description': description, 'properties': properties,
            'required': list(required), 'additionalProperties': additional}


def text(description, minimum=1):
    return {'type': 'string', 'minLength': minimum, 'description': description}


def array(items, description='', minimum=0):
    return {'type': 'array', 'items': items, 'minItems': minimum, 'description': description}


def entries(item, description):
    return {'type': 'object', 'description': description, 'additionalProperties': item}


ID = text('Устойчивый уникальный ID, согласованный со всеми ссылками.')
IDS = array(ID, 'Ссылки на существующие ID.')
MINUTE = {'type': 'integer', 'minimum': 0, 'description': 'Минуты от начала понедельника; не игровое время в виде текста.'}
OPTIONAL_ID = {'type': ['string', 'null'], 'description': 'ID существующего события/сцены или null, если его нет.'}
OPTIONAL_MINUTE = {'type': ['integer', 'null'], 'minimum': 0}

CARD_DESCRIPTIONS = {
    'Возраст': 'Конкретный возраст персонажа, без заглушек; заданный пользователем возраст является каноном.',
    'Роль': 'Профессия и положение в истории, с конкретными обязанностями и связью с окружением.',
    'Статус': 'Устойчивое социальное и профессиональное положение, не текущее настроение или занятие.',
    'Внешность': 'Целостный физический портрет: телосложение и рост или визуальная оценка, цвет/длина/укладка волос, цвет глаз, типичная одежда, уместные приметы, лицо и осанка. Без одинаковых искусственных шрамов.',
    'Характер': 'Устойчивое поведение, реакции под давлением, противоречия, отношение к людям, конфликтам и ответственности.',
    'Стиль общения': 'Фактическая речь: длина фраз, прямота, лексика, эмоциональность, юмор, формальность, конфликт и общение с разными людьми. Ведущий использует это для реплик.',
    'Привычки': 'Повторяемые жесты, бытовые действия и ритуалы, которые можно показывать в сценах.',
    'Сильные стороны': 'Конкретные качества и способности, реально влияющие на решения и поступки.',
    'Слабости': 'Конкретные недостатки и ограничения, способные приводить к ошибкам и конфликтам.',
    'Страхи и уязвимости': 'Чего человек боится потерять, какие темы задевают и влияют на поступки.',
    'Биография': 'Значимое прошлое и его причинная связь с характером, привычками, отношениями, страхами и целями.',
}


def world_state_schema():
    """Construct once from the same permanent card keys used by normalization."""
    card = obj({key: text(CARD_DESCRIPTIONS[key]) for key in CARD_FIELDS}, CARD_FIELDS,
               'Постоянные характеристики человека. Каждое поле должно быть содержательным; отсутствие в идее разрешает придумать. Динамика хранится отдельно в world.characters.')
    character = obj({'id': ID, 'name': text('Имя персонажа'), 'is_player': {'type': 'boolean'},
                     'aliases': array(text('Другое имя')),'fields': card},
                    ('id','name','is_player','fields'), 'Карточка значимого персонажа.')
    actor = obj({'id': ID, 'location': {'type':['string','null']},
                 'situation': text('Что происходит с персонажем сейчас.'), 'goals': array(text('Краткосрочная цель')),
                 'intentions': array(text('Намерение и ближайшее действие')), 'obligations': array(text('Игровое обязательство')),
                 'emotion': text('Текущее эмоциональное состояние'), 'minute': OPTIONAL_MINUTE,
                 'scene_id': OPTIONAL_ID, 'last_event_id': OPTIONAL_ID},
                ('id','location','situation','goals','intentions','emotion','minute','scene_id'),
                'Изменяемое состояние; по одному объекту для каждой карточки, включая персонажей вне камеры.')
    scene = obj({'id': ID,'location': text('Место сцены'),'participants': IDS,
                 'text': text('Текущая ситуация и условия для первого решения, без принятия решения за героя.'),
                 'start_minute': MINUTE,'end_minute': MINUTE,
                 'status': {'type':'string','enum':['active','ended','paused']},'event_ids': IDS},
                ('id','location','participants','text','start_minute','end_minute','status','event_ids'))
    relation = obj({'source_id': ID,'target_id': ID,'context': text('Разная в каждом направлении история и эмоциональная динамика.'),
                    'dimensions': entries({'type':'number','minimum':-100,'maximum':100},'Только уместные trust, affection, attraction, irritation, fear, jealousy, respect.'),
                    'visible_to_ids': IDS},('source_id','target_id','context','dimensions'))
    fact = obj({'id':ID,'text':text('Объективный факт мира, включая собственные тайны значимых персонажей.'),
                'secret':{'type':'boolean'},'owner_id':OPTIONAL_ID,'character_ids':IDS,
                'evidence':array(text('Основание для раскрытия'))},('id','text','secret','character_ids','evidence'))
    knowledge = obj({'actor_id':ID,'fact_id':ID,'status':{'type':'string','enum':['known','suspected','unknown']},
                     'source_event_id':OPTIONAL_ID},('actor_id','fact_id','status'),
                    'Укажи отдельно, кто знает факт, кто лишь подозревает; отсутствие записи значит отсутствие знания.')
    thread = obj({'id':ID,'description':text('Открытая сюжетная линия.'),'state':text('Текущее положение линии.'),
                  'public_state':text('Часть состояния, известная игроку.'),'status':{'type':'string','enum':['active','developing','dormant','resolved']},
                  'character_ids':IDS,'visible_to_ids':IDS,'relevance':{'type':'number','minimum':0,'maximum':1},
                  'last_event_id':OPTIONAL_ID},('id','description','state','status','character_ids','relevance'))
    event = obj({'id':ID,'text':text('Уже произошедшее значимое событие.'),'participants':IDS,'witnesses':IDS,
                 'minute':OPTIONAL_MINUTE,'scene_id':OPTIONAL_ID,'fact_ids':IDS,'medium':text('Канал события.'),
                 'evidence':{'type':'string'},'source_sequence':{'type':'integer','minimum':0},
                 'player_observed':{'type':'boolean'}},('id','text','participants','witnesses','minute','scene_id','fact_ids','player_observed'))
    scheduled = obj({'id':ID,'description':text('Отложенное событие при наличии причин и сроков.'),
                     'due_minute':MINUTE,'participants':IDS,'status':{'type':'string','enum':['pending','resolved','cancelled']},
                     'resolved_event_id':OPTIONAL_ID},('id','description','due_minute','participants','status'))
    world = obj({'version':{'const':2},'characters':entries(actor,'Ключ — тот же ID, что в characters.'),
                 'relationships':entries(relation,'Направленные связи A→B и B→A независимы.'),
                 'facts':entries(fact,'Объективные факты; не автоматически знания ГГ.'),
                 'knowledge':entries(knowledge,'Знания отдельных персонажей об объективных фактах.'),
                 'threads':entries(thread,'Активные и отложенные линии.'),
                 'events':entries(event,'Только уже случившиеся события.'),
                 'scheduled_events':entries(scheduled,'Будущие события, только если они мотивированы.'),
                 'scenes':entries(scene,'Сцены с независимыми участниками и игровым временем.'),
                 'scene_records':entries(obj({}, description='До начала игры обычно нет записанных игровых ответов.'),'Исторические записи сцен.')},
                ('version','characters','relationships','facts','knowledge','threads','events','scheduled_events','scenes'),
                'Объективное состояние живого мира, связи, знания, сюжетные линии и сцены.')
    campaign = obj({key:text(desc) for key,desc in {
        'title':'Название мира.','setting':'Место и обстоятельства мира.','era':'Эпоха.',
        'genre':'Жанр повествования.','tone':'Эмоциональный тон.',
        'description':'Подробная концепция мира, включая закрытые вводные.',
        'public_description':'Краткое описание без спойлеров.','rules':'Правила авторского повествования.'}.items()},
        ('title','setting','era','genre','tone','description','public_description','rules'))
    return {'$schema':'https://json-schema.org/draft/2020-12/schema','title':'WorldState',
            'description':'Один готовый к игре мир; пользовательская идея — канон, остальные детали придумываются творчески.',
            **obj({'schema_version':{'const':1},'campaign':campaign,'sections':obj({}),
                   'story_notes':{'type':'string'},
                   'locations':array(obj({'id':ID,'name':text('Название локации'),'text':text('Физические детали и игровые возможности.')},('id','name','text')),minimum=1),
                   'characters':array(character,'Значимые персонажи, каждый с полной постоянной карточкой.',1),
                   'protagonist_id':ID,'controlled_actor_id':ID,
                   'camera':obj({'scene_id':ID,'mode':{'type':'string','enum':['actor','observer']}},('scene_id','mode')),
                   'world_clock':obj({'minute':MINUTE,'last_event_time':text('День N (день недели) HH:MM, согласован с minute.')},('minute','last_event_time')),
                   'world':world},('schema_version','campaign','locations','characters','protagonist_id',
                                  'controlled_actor_id','camera','world_clock','world'))}
