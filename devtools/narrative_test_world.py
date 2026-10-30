"""Repository-owned Initial World State for Epic #36 manual/integration QA.

This is the supported draft aggregate, not another Runtime schema. All loads go
through JSON import, draft validation/confirmation and the normal migration.
"""
import json
from copy import deepcopy

from backend.services import draft_world
from backend.services.world import KINDS

FIXTURE_VERSION = 2
TITLE = 'DEV · Narrative QA · Два берега'
START_MINUTE = 540  # Monday 2026-10-05, 09:00; Day 1 stays campaign-relative.
SCENE_ID = 'qa_opening'
ACTOR_ID = 'qa_kirill'
HOME = 'Озёрск — дом Лариных'
WORKSHOP = 'Озёрск — мастерская'
LIBRARY = 'Озёрск — библиотека'
PIER = 'Озёрск — пристань'
GARDEN = 'Речной Посад — сад'
CAFE = 'Речной Посад — кафе'
PRESENT = (ACTOR_ID, 'qa_vera', 'qa_timur')

# The stable base keeps ages, kinship and occupations as card prose. Owning
# issue checkpoints add explicit canonical records without rewriting the base.
PEOPLE = (
    ('qa_kirill', 'Кирилл Ларин', '34 года', 'Реставратор, основной герой', HOME,
     'Супруг Веры, отец Аси, сын Нины и Павла. Работает вместе с Олегом.'),
    ('qa_vera', 'Вера Ларина', '32 года', 'Библиотекарь, супруга Кирилла', HOME,
     'Мать Аси. Давно дружит с Мариной.'),
    ('qa_asya', 'Ася Ларина', '9 лет', 'Школьница, дочь Кирилла и Веры', LIBRARY,
     'Пришла с бабушкой Ниной на занятие по рисованию.'),
    ('qa_nina', 'Нина Ларина', '61 год', 'Мать Кирилла, бабушка Аси', LIBRARY,
     'Бывшая учительница. Супруга Павла.'),
    ('qa_pavel', 'Павел Ларин', '64 года', 'Отец Кирилла, дедушка Аси', PIER,
     'Ремонтировал лодки; знаком с работником пристани Борисом.'),
    ('qa_timur', 'Тимур Серов', '35 лет', 'Близкий друг Кирилла, фотограф', HOME,
     'Дружит с Кириллом со школы. Принёс снимки старой карты.'),
    ('qa_oleg', 'Олег Рудин', '42 года', 'Коллега Кирилла, переплётчик', WORKSHOP,
     'Работает в мастерской. Утром получил личное письмо.'),
    ('qa_marina', 'Марина Белова', '32 года', 'Знакомая Кирилла, подруга Веры', LIBRARY,
     'Организует занятия по рисованию в библиотеке.'),
    ('qa_boris', 'Борис Туманов', '49 лет', 'Работник пристани', PIER,
     'Знаком с Павлом по ремонту лодок.'),
    ('qa_zoya', 'Зоя Лесная', '28 лет', 'Посетительница библиотеки', LIBRARY,
     'Ищет старые краеведческие альбомы; с Лариными ещё не знакома.'),
    ('qa_elena', 'Елена Ветрова', '59 лет', 'Тётя Веры, садовод', GARDEN,
     'Живёт в Речном Посаде, в Южной долине.'),
    ('qa_roman', 'Роман Луговой', '26 лет', 'Работник кафе', CAFE,
     'Живёт в Речном Посаде. Иногда покупает травы у Елены.'),
)


def _base_world():
    world = {'version': 2, **{kind: {} for kind in KINDS}}
    cards = []
    for cid, name, age, role, location, biography in PEOPLE:
        cards.append(dict(id=cid, name=name, aliases=[], fields={
            'Возраст': age, 'Роль': role, 'Статус': 'Живёт обычной жизнью.',
            'Биография': biography,
            'Характер': 'Внимателен к деталям, ценит ясность и доброжелательный разговор.',
            'Стиль общения': 'Спокойные короткие фразы, уточняющие вопросы.',
        }))
        world['characters'][cid] = dict(
            id=cid, location=location, situation='Находится в месте, указанном в карточке состояния.',
            goals=[], intentions=[], obligations=[], emotion='', minute=START_MINUTE,
            scene_id=SCENE_ID if cid in PRESENT else None, last_event_id=None)
    world['characters']['qa_vera']['birth_date'] = '1993-10-06'
    world['characters']['qa_oleg']['goals'] = ['Подготовить старую карту к реставрации.']
    world['characters']['qa_timur']['intentions'] = ['Показать Кириллу фотографии карты.']
    world['characters']['qa_vera']['emotion'] = 'Спокойное любопытство.'
    world['scenes'][SCENE_ID] = dict(
        id=SCENE_ID, location=HOME, participants=list(PRESENT),
        text='Утро в доме Лариных. Кирилл, Вера и Тимур сидят у стола. '
             'Тимур положил рядом фотографии старой карты; разговор ещё не начался.',
        start_minute=START_MINUTE, end_minute=START_MINUTE, status='active', event_ids=[])
    for source, target, context, dimensions in (
        (ACTOR_ID, 'qa_vera', 'Кирилл доверяет Вере.', {'trust': 70, 'affection': 65}),
        ('qa_vera', ACTOR_ID, 'Вера тепло относится к Кириллу.', {'trust': 60, 'affection': 75}),
        (ACTOR_ID, 'qa_timur', 'Давняя дружба.', {'trust': 55}),
        ('qa_oleg', ACTOR_ID, 'Уважает аккуратность коллеги.', {'trust': 40}),
    ):
        world['relationships'][source + ':' + target] = dict(
            source_id=source, target_id=target, context=context, dimensions=dimensions)
    world['facts'] = {
        'qa_library_open': dict(id='qa_library_open', text='Библиотека Озёрска вновь открыта после ремонта.',
                                secret=False, character_ids=[], evidence=['Объявление у входа.']),
        'qa_private_letter': dict(id='qa_private_letter', text='Олег получил предложение работать в Речном Посаде и ещё не ответил.',
                                  secret=True, owner_id='qa_oleg', character_ids=['qa_oleg'], evidence=['Личное письмо.']),
    }
    # Historical acquisition is grounded; a public world fact is not broadcast
    # to every Character. Knowledge and its absence are intentional QA inputs.
    for eid, fid, witnesses, medium in (
        ('qa_read_notice', 'qa_library_open', list(PRESENT), 'observation'),
        ('qa_read_letter', 'qa_private_letter', ['qa_oleg'], 'message'),
    ):
        world['events'][eid] = dict(id=eid, text=world['facts'][fid]['text'],
            participants=witnesses, witnesses=witnesses, fact_ids=[fid],
            minute=480, medium=medium, evidence=world['facts'][fid]['evidence'][0],
            player_observed=ACTOR_ID in witnesses)
        for cid in witnesses:
            world['knowledge'][cid + ':' + fid] = dict(
                actor_id=cid, fact_id=fid, status='known', source_event_id=eid)
    world['threads']['qa_map'] = dict(id='qa_map', description='Реставрация старой карты двух берегов.',
        state='Фотографии готовы; работу над оригиналом ещё не начали.', public_state='Фотографии готовы.',
        status='active', character_ids=[ACTOR_ID, 'qa_timur', 'qa_oleg'],
        visible_to_ids=[ACTOR_ID, 'qa_timur', 'qa_oleg'], relevance=0.6)
    locations = [dict(id=key, name=name, text=description) for key, name, description in (
        ('qa_home', HOME, 'Дом в Озёрске, Северный край. Общий стол у окна.'),
        ('qa_workshop', WORKSHOP, 'Мастерская Озёрска, Северный край. Рабочий стол для реставрации.'),
        ('qa_library', LIBRARY, 'Библиотека Озёрска, Северный край. Читальный зал и стол для рисования.'),
        ('qa_pier', PIER, 'Пристань Озёрска, Северный край. Здесь ремонтируют лодки.'),
        ('qa_garden', GARDEN, 'Сад Речного Посада, Южная долина. Здесь живёт Елена.'),
        ('qa_cafe', CAFE, 'Кафе Речного Посада, Южная долина. Здесь работает Роман.'),
    )]
    return dict(characters=cards, locations=locations, world=world,
        protagonist_id=ACTOR_ID, controlled_actor_id=ACTOR_ID,
        camera=dict(scene_id=SCENE_ID, mode='actor'), world_clock=dict(minute=START_MINUTE,calendar=dict(start_minute=START_MINUTE,start_weekday=0,start_date='2026-10-05',profile=dict(id='two-shores',observances=[dict(id='map-day',name='День старых карт',month=10,day=5)],seasons=[]))),
        campaign=dict(title=TITLE, setting='Вымышленные современные города Озёрск и Речной Посад.',
            era='Современность', genre='Повседневная история', tone='Спокойный, внимательный к деталям.',
            description='Технический мир для ручной проверки Narrative. Все персонажи вымышлены.',
            public_description='Утренний разговор о старой карте.',
            rules='Добровольные решения Кирилла задаёт игрок. Скрытые знания не передаются автоматически.'))


# Later issues register small deterministic transformations of a fresh base
# aggregate here. Never add independently maintained copies of the whole world.
def _calendar_evening(state):
    clock = 3*1440+20*60+42
    state['world_clock'].update(minute=clock,calendar=dict(start_minute=clock,start_weekday=3,start_date='2026-10-08',
        profile=dict(id='two-shores',observances=[dict(id='bridge-day',name='День моста',month=10,day=9)])))
    scene = state['world']['scenes'][SCENE_ID]
    scene.update(start_minute=clock,end_minute=clock,text='Вечер в доме Лариных. Кирилл, Вера и Тимур рассматривают карту.')
    for actor in state['world']['characters'].values(): actor['minute']=clock
    state['world']['characters']['qa_vera']['birth_date']='1993-10-09'
    state['world']['facts']['qa_vera_birthday']=dict(id='qa_vera_birthday',text='Вера сообщила Кириллу дату рождения: 9 октября 1993 года.',secret=False,character_ids=['qa_vera'],claim=dict(subject_id='qa_vera',predicate='birth_date',value='1993-10-09'),evidence=[])
    state['world']['knowledge'][ACTOR_ID+':qa_vera_birthday']=dict(actor_id=ACTOR_ID,fact_id='qa_vera_birthday',status='known')
    state['world']['scheduled_events']['qa_friday_trip'] = dict(id='qa_friday_trip',description='Поездка в сад в пятницу вечером.',
        participants=[ACTOR_ID,'qa_elena'],due_minute=0,status='pending',condition='В пятницу вечером')
    return state


def _calendar_leap(state):
    state = _calendar_evening(state)
    state['world_clock'].update(minute=1439,calendar=dict(start_minute=1439,start_weekday=2,start_date='2024-02-28'))
    state['world']['characters']['qa_vera']['birth_date']='1992-02-29'
    state['world']['scheduled_events']={}
    scene=state['world']['scenes'][SCENE_ID]
    scene.update(start_minute=1439,end_minute=1439,text='Поздний вечер в доме Лариных.')
    for actor in state['world']['characters'].values(): actor['minute']=1439
    return state


def _commitments(state):
    state = _calendar_evening(state)
    events = state['world']['scheduled_events']
    events['qa_friday_trip'].update(commitment=True, temporal=dict(weekday=4,day_period='evening'),
        condition='После работы', evidence='Кирилл и Елена договорились о поездке.', source_turn=0)
    state['world']['facts']['qa_school_calendar']=dict(id='qa_school_calendar',text='Кирилл прочитал школьный календарь каникул.',secret=False,character_ids=[ACTOR_ID],claim=dict(subject_id='qa_school_break',predicate='scheduled_event',value='known'),evidence=[])
    state['world']['knowledge'][ACTOR_ID+':qa_school_calendar']=dict(actor_id=ACTOR_ID,fact_id='qa_school_calendar',status='known')
    events['qa_sunday_return'] = dict(id='qa_sunday_return', description='Возвращение из сада домой.',
        participants=[ACTOR_ID], due_minute=0, status='pending', commitment=True,
        temporal=dict(weekday=6,day_period='evening'), depends_on=['qa_friday_trip'],
        evidence='Кирилл подтвердил возвращение в воскресенье.', source_turn=0)
    events['qa_school_break'] = dict(id='qa_school_break', description='Каникулы Аси.',
        participants=['qa_asya'], due_minute=0, status='pending', commitment=True, type='school_break',
        temporal=dict(date='2026-10-10'), end_temporal=dict(date='2026-10-17'),
        evidence='Установлены даты школьных каникул.', source_turn=0)
    return state


def _family(state):
    from backend.runtime_v3.models import ObjectiveRelation, Condition
    world=state['world']
    world['objective_relations']={}
    world['conditions']={}
    for cid,c in world['characters'].items():
        c.update(life_status='alive',developmental_stage='child' if cid=='qa_asya' else 'adult')
    world['characters']['qa_asya']['birth_date']='2017-02-12'
    def relation(rid,kind,a,b,observers):
        fid=rid+'_fact'
        world['facts'][fid]=dict(id=fid,text=f'Установленная связь: {kind}, {a}, {b}.',secret=True,
                                character_ids=[a,b],evidence=['Исходные сведения QA.'])
        eid=rid+'_event'
        world['events'][eid]=dict(id=eid,text='Ранее установлена семейная связь.',participants=[a,b],
            witnesses=observers,fact_ids=[fid],minute=0,medium='testimony',evidence='Исходные сведения QA.',player_observed=ACTOR_ID in observers)
        for observer in observers:
            world['knowledge'][observer+':'+fid]=dict(actor_id=observer,fact_id=fid,status='known',source_event_id=eid)
        if kind in ('spouse','friend','partner','engaged'):a,b=sorted((a,b))
        world['objective_relations'][rid]=ObjectiveRelation(id=rid,kind=kind,source_id=a,target_id=b,
            since=0,fact_id=fid,evidence='Исходные сведения QA.',source_turn=0).model_dump()
    for rid,kind,a,b in (
        ('qa_marriage','spouse',ACTOR_ID,'qa_vera'),
        ('qa_father','parent',ACTOR_ID,'qa_asya'),('qa_mother','parent','qa_vera','qa_asya'),
        ('qa_grandmother','parent','qa_nina',ACTOR_ID),('qa_grandfather','parent','qa_pavel',ACTOR_ID),
        ('qa_friend','friend',ACTOR_ID,'qa_timur')):
        relation(rid,kind,a,b,[ACTOR_ID,'qa_vera'])
    # Deliberately unknown to Kirill; never visible via genealogy IDs/counts.
    relation('qa_secret_parent','parent','qa_elena','qa_zoya',['qa_elena'])
    world['conditions']['qa_hand_injury']=Condition(id='qa_hand_injury',actor_id='qa_oleg',
        description='Восстановление после травмы руки.',duration='temporary',effects=dict(can_act=False),
        since=0,evidence='Исходные сведения QA.',source_turn=0).model_dump()
    return state


def _family_incapacitated(state):
    from backend.runtime_v3.models import Condition
    state=_family(state)
    for cid,description,effects,duration in (
        ('qa_unconscious','Кирилл без сознания; исход ещё не установлен.',{'conscious':False},'temporary'),
        ('qa_leg','У Кирилла сохраняется ограничение движения.',{'can_move':False},'persistent')):
        state['world']['conditions'][cid]=Condition(id=cid,actor_id=ACTOR_ID,description=description,
            effects=effects,duration=duration,since=START_MINUTE,evidence='Установленное исходное состояние QA.',source_turn=0).model_dump()
    return state


def _family_care(state):
    from backend.runtime_v3.models import ObjectiveRelation
    state=_family(state);world=state['world']
    # Care is legally established in this fictional setting, not inferred from affection.
    # Kirill intentionally does not yet know: Vera is the observer for this checkpoint.
    fid='qa_care_fact';actors=['qa_elena','qa_asya']
    world['facts'][fid]=dict(id=fid,text='Елена стала опекуном Аси. Биологические родители не изменились.',
        secret=True,character_ids=actors,evidence=['Ранее завершена процедура опеки.'])
    world['events']['qa_care_event']=dict(id='qa_care_event',text=world['facts'][fid]['text'],participants=actors,
        witnesses=['qa_vera','qa_elena'],fact_ids=[fid],minute=0,medium='testimony',
        evidence='Ранее завершена процедура опеки.',player_observed=False)
    for observer in ('qa_vera','qa_elena'):
        world['knowledge'][observer+':'+fid]=dict(actor_id=observer,fact_id=fid,status='known',source_event_id='qa_care_event')
    world['objective_relations']['qa_guardianship']=ObjectiveRelation(id='qa_guardianship',kind='guardian',
        source_id='qa_elena',target_id='qa_asya',since=0,fact_id=fid,evidence='Ранее завершена процедура опеки.',source_turn=0).model_dump()
    return state


def _residence_roles(state):
    """#39 extends the same world; base and earlier checkpoints remain unchanged."""
    from backend.runtime_v3.models import Residence, NarrativeRole, Organization
    world=state['world']
    for loc in state['locations']:
        loc.update(kind='building',parent_id='qa_south_city' if loc['id'] in ('qa_garden','qa_cafe') else 'qa_north_city')
    state['locations'] += [dict(id=key,name=name,text='',kind=kind,parent_id=parent) for key,name,kind,parent in (
        ('qa_realm','Два берега','realm',None),('qa_north','Северный край','region','qa_realm'),
        ('qa_south','Южная долина','region','qa_realm'),('qa_north_city','Озёрск','settlement','qa_north'),
        ('qa_south_city','Речной Посад','settlement','qa_south'),
        ('qa_room','Комната у окна','room','qa_home'))]
    def proof(fid,text,actors,observers):
        eid=fid+'_event'
        world['facts'][fid]=dict(id=fid,text=text,secret=True,character_ids=actors,evidence=[text])
        world['events'][eid]=dict(id=eid,text=text,participants=observers,witnesses=observers,fact_ids=[fid],
            minute=0,medium='conversation',evidence=text,player_observed=ACTOR_ID in observers)
        for cid in observers: world['knowledge'][cid+':'+fid]=dict(actor_id=cid,fact_id=fid,status='known',source_event_id=eid)
    world['organizations']={key:Organization(id=key,name=name,kind=kind,status='active',location_ids=[loc],since=0).model_dump()
        for key,name,kind,loc in [('qa_restorers','Мастерская карт','workshop','qa_workshop'),
            ('qa_school','Школа Озёрска','school','qa_library'),('qa_academy','Академия двух берегов','academy','qa_cafe')]}
    proof('qa_home_fact','Кирилл постоянно живёт в доме Лариных.',[ACTOR_ID],list(PRESENT))
    proof('qa_elena_home','Дом Елены — в Речном Посаде.',['qa_elena'],['qa_elena'])
    proof('qa_work_fact','Кирилл работает реставратором в Мастерской карт.',[ACTOR_ID],list(PRESENT))
    proof('qa_school_fact','Ася учится в Школе Озёрска.',['qa_asya'],[ACTOR_ID,'qa_vera','qa_asya'])
    world['residences']={r.id:r.model_dump() for r in (
        Residence(id='qa_home_residence',actor_id=ACTOR_ID,location_id='qa_home',since=0,fact_id='qa_home_fact'),
        Residence(id='qa_elena_residence',actor_id='qa_elena',location_id='qa_garden',since=0,fact_id='qa_elena_home'))}
    world['roles']={r.id:r.model_dump() for r in (
        NarrativeRole(id='qa_job',actor_id=ACTOR_ID,kind='employment',title='Реставратор',organization_id='qa_restorers',since=0,fact_id='qa_work_fact'),
        NarrativeRole(id='qa_pupil',actor_id='qa_asya',kind='education',title='Ученица',organization_id='qa_school',since=0,fact_id='qa_school_fact'))}
    return state


def _goals(state):
    """#75 regression actors in the same #78 world, immediately before meeting."""
    from copy import deepcopy
    for cid,name in (('qa_ilya','Илья'),('qa_sonya','Соня')):
        card=dict(id=cid,name=name,aliases=[],fields={'Роль':'Друг Лариных',
            'Характер':'Внимательный, с чувством юмора.', 'Ценности':'Ценит честность в близких отношениях.'})
        state['characters'].append(card)
        actor=deepcopy(state['world']['characters'][ACTOR_ID]);actor.update(id=cid,goals=[],intentions=[],obligations=[])
        state['world']['characters'][cid]=actor
    state['world']['characters']['qa_ilya'].update(goals=['Развивать отношения с Соней.'],
        intentions=['После «Критического успеха» встретиться с Соней'])
    state['world']['characters']['qa_sonya'].update(goals=['Провести выходные вместе.'],
        intentions=['Предложить Илье поездку в коттедж'])
    state['protagonist_id']=state['controlled_actor_id']='qa_ilya'
    state['world']['scenes'][SCENE_ID].update(participants=['qa_ilya'],
        text='Илья ждёт Соню после «Критического успеха». Встреча и предложение поездки ещё впереди.')
    for cid,actor in state['world']['characters'].items(): actor['scene_id']=SCENE_ID if cid=='qa_ilya' else None
    return state


CHECKPOINTS = {'residence-roles':_residence_roles,'family':_family,'family-care':_family_care,'family-incapacitated':_family_incapacitated,'calendar-evening' :_calendar_evening,'calendar-leap':_calendar_leap,'commitments':_commitments}
CHECKPOINTS['goals'] = _goals
CHECKPOINTS['knowledge'] = _residence_roles
def _appearance(state):
    from backend.runtime_v3.models import AppearanceFeature, AppearanceProfile
    state = _family(state)
    state['world']['characters']['qa_vera']['appearance'] = AppearanceProfile(items={
        'eye_color': AppearanceFeature(category='intrinsic',kind='eye_color',text='Серые глаза'),
        'hairstyle': AppearanceFeature(category='presentation',kind='hairstyle',text='Волосы до плеч'),
    }).model_dump()
    return state


CHECKPOINTS['appearance'] = _appearance
CHECKPOINTS['personality'] = lambda state: _family(state)
CHECKPOINTS['milestones'] = lambda state: _residence_roles(_family(state))


def _choices(state):
    cards = {c['id']:c for c in state['characters']}
    cards[ACTOR_ID]['fields']['Привычки'] = 'Прежде чем решать, рассматривает детали.'
    cards['qa_vera']['fields'].update({'Характер':'Решительна, любит пробовать новые подходы.',
        'Стиль общения':'Развёрнутые фразы с мягкой иронией.', 'Привычки':'Предлагает сравнить несколько версий.'})
    state['world']['characters'][ACTOR_ID].update(goals=['Разобраться в происхождении карты.'],
        intentions=['Сравнить снимки Тимура.'], obligations=['Вернуть Вере библиотечный альбом.'])
    state['world']['characters']['qa_vera']['goals'] = ['Подготовить выставку карт в библиотеке.']
    return state


CHECKPOINTS['choices'] = _choices

# Demonstration output only, never production generation or a personality score.
CHOICE_EXAMPLES = [
    dict(action='Рассмотреть пометки на снимках.', speech='Тимур, покажи этот угол крупнее.'),
    dict(action='Сравнить два снимка.', speech='Давайте сначала проверим различия.'),
    dict(action='Вернуть Вере библиотечный альбом.', speech='Спасибо, он помог разобраться.'),
    dict(action='Поблагодарить Тимура за помощь.', speech='Рад, что мы взялись за это вместе.'),
    dict(action='Предложить смелую версию происхождения карты.', speech='А если мы смотрим на неё не с той стороны?'),
    dict(action='Отложить обсуждение и сделать перерыв.', speech='Вернёмся к этому позже.'),
]


def _seed_milestones(repository, save_id):
    """Replay accepted transitions in the same QA world, through normal commit code.

    Initial imported biography is deliberately NOT treated as transition History.
    Routine batches age the index beyond the recent-history window without inventing
    protagonist changes or implementing future pregnancy/advance mechanics.
    """
    from backend.runtime_v3.repository import committed_snapshot, append_history
    from backend.runtime_v3.resolver import StateResolver
    from backend.repositories.living_world import project
    snapshot = repository.get_snapshot(save_id)
    steps = [
        ('qa_engagement_fact','Тимур и Марина объявили о помолвке.',['qa_timur','qa_marina'],
         {'social_relation_changes':[dict(id='qa_new_engagement',kind='engaged',source_id='qa_timur',target_id='qa_marina')]}),
        ('qa_wedding_fact','Тимур и Марина заключили брак.',['qa_timur','qa_marina'],
         {'social_relation_changes':[dict(id='qa_new_engagement',status='closed',outcome='superseded'),
            dict(id='qa_new_marriage',kind='spouse',source_id='qa_timur',target_id='qa_marina')]}),
        ('qa_divorce_fact','Тимур и Марина развелись.',['qa_timur','qa_marina'],
         {'social_relation_changes':[dict(id='qa_new_marriage',status='closed',outcome='divorced')]}),
        ('qa_move_fact','Кирилл решил постоянно жить в Речном Посаде.',[ACTOR_ID],
         {'residence_changes':[dict(id='qa_new_home',actor_id=ACTOR_ID,location_id='qa_garden',replaces=['qa_home_residence'])]}),
        ('qa_graduation_fact','Ася закончила обучение в Школе Озёрска.',['qa_asya'],
         {'role_changes':[dict(id='qa_pupil',status='closed',outcome='graduated')]}),
        ('qa_death_fact','Павел умер.',['qa_pavel'],
         {'life_changes':[dict(id='qa_pavel',life_status='dead')]}),
    ]
    with repository.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        for fid,text,actors,changes in steps:
            camera=snapshot['world_state']['camera']
            event=fid+'_event'; witnesses=[ACTOR_ID,'qa_vera']
            raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=1),
                facts=[dict(id=fid,text=text,character_ids=actors,evidence=text)],
                events=[dict(id=event,text=text,participants=list(dict.fromkeys(actors+witnesses)),witnesses=witnesses,
                    fact_ids=[fid],medium='testimony',evidence=text)],
                knowledge_gained=[dict(actor_id=cid,fact_id=fid,source_event_id=event,evidence=text) for cid in witnesses])
            for section,rows in changes.items():
                raw[section]=[dict(row,evidence=text,assertion='established',source_event_id=event,
                    **({'closure_fact_id':fid} if row.get('status')=='closed' else {'fact_id':fid}),
                    **({'player_assertion':'explicit_choice','player_evidence':text} if section in ('residence_changes','life_changes') else {})) for row in rows]
            resolved=StateResolver(snapshot['world_state'],text,text,turn_id=0,
                actor_names={c['id']:c['name'] for c in snapshot['character_cards']}).resolve(raw)
            if resolved.warnings: raise ValueError('Milestone QA replay: '+str(resolved.warnings))
            snapshot=committed_snapshot(conn,snapshot,resolved)
        for n in range(80):
            snapshot['history_head']=append_history(conn,snapshot['history_head'],
                {'events':[dict(id=f'qa_routine_{n}',text='Обычный разговор.',participants=[ACTOR_ID]) ]})
        conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot,ensure_ascii=False),save_id))
        project(conn,save_id,snapshot)


def build_fixture(checkpoint='base'):
    if checkpoint != 'base' and checkpoint not in CHECKPOINTS:
        raise ValueError(f'Неизвестный checkpoint: {checkpoint}')
    state = _base_world()
    if checkpoint != 'base':
        state = CHECKPOINTS[checkpoint](state)
    state = draft_world.prepare(state)
    report = draft_world.validate(state)
    if report['errors']:
        raise ValueError('Некорректная QA fixture: ' + '; '.join(report['errors']))
    return state


def load_fixture(repository, checkpoint='base'):
    """Reset by creating a fresh save. No target save ID, UPDATE or DELETE path.

    Storage IDs/timestamps/history pointers are ordinary persistence metadata;
    fixture entity IDs and canonical starting values are deterministic.
    """
    state = build_fixture(checkpoint)
    workspace = repository.create_workspace(f'{TITLE} · v{FIXTURE_VERSION} · {checkpoint}')
    repository.import_draft(workspace['id'], json.dumps(state, ensure_ascii=False),
                            workspace['revision'], format='json')
    draft = repository.draft(workspace['id'], author=True)
    result = repository.confirm_draft(workspace['id'], draft['revision'], draft['version_id'])
    if checkpoint in ('milestones','pacing'): _seed_milestones(repository,result['save'])
    if checkpoint == 'personality': _seed_personality(repository,result['save'])
    if checkpoint == 'goals': _seed_goals(repository,result['save'])
    if checkpoint == 'knowledge': _seed_knowledge(repository,result['save'])
    if checkpoint == 'choices': _seed_choices(repository,result['save'])
    if checkpoint == 'long-term': _seed_long_term(repository, result['save'])
    if checkpoint.startswith(('pregnancy','newborn')): _seed_reproduction(repository,result['save'],checkpoint)
    if checkpoint=='protagonist-infant':
        _seed_reproduction(repository,result['save'],'newborn')
        snapshot=repository.get_snapshot(result['save'])
        from backend.runtime_v3.birth_identity import is_game_birth
        child=next(cid for cid in snapshot['world_state']['characters'] if is_game_birth(snapshot['world_state'],cid))
        repository.transition_protagonist(result['save'],repository.get_save(result['save'])['revision'],
            'qa-infant-protagonist','permanent',actor_id=child)
    return dict(result, workspace=workspace['id'], fixture_version=FIXTURE_VERSION, checkpoint=checkpoint)


def _seed_choices(repository, save_id):
    """Three player-owned sources refine canonical voice; the card stays old."""
    from backend.runtime_v3.resolver import StateResolver
    from backend.runtime_v3.context import build_context
    snapshot = repository.get_snapshot(save_id)
    texts = ['Сначала проверим детали. Кирилл спокойно попросил показать снимки крупнее.',
             'Давайте проверим различия. Кирилл спокойно сравнил два снимка.',
             'Я объясню прямо. Кирилл спокойно и прямо объяснил свою позицию.']
    config = dict(model='deterministic-fixture',context_length=32768,max_tokens=2000,update_tokens=4096)
    for index, text in enumerate(texts):
        s = snapshot['world_state']; camera = s['camera']
        raw = dict(final_scene={k:camera[k] for k in ('location_id','present_character_ids')},
            choices=CHOICE_EXAMPLES,
            events=[dict(id='qa_expression',text=text,evidence=text,participants=[ACTOR_ID],
                         witnesses=list(PRESENT),fact_ids=[])],
            development_evidence=[dict(id='qa_expression_proof',actor_id=ACTOR_ID,source_event_id='qa_expression',
                meaning='Выражает позицию прямо и спокойно.',kind='behavior',assertion='completed',
                evidence=text,player_evidence=text,player_assertion='completed_voluntary_behavior')])
        if index == 2:
            profile = s['characters'][ACTOR_ID]['personality']
            raw['personality_deltas'] = [dict(actor_id=ACTOR_ID,
                evidence_ids=list(profile['evidence'])+['qa_expression_proof'],
                rationale='Три завершённых действия игрока подтверждают более прямую манеру речи.',
                developmental_fit='established_capability',evidence=text,
                operations=[dict(item_id='communication',field='communication',operation='refine',
                    expected_text=profile['items']['communication']['text'],expected_revision=0,
                    text='Говорит прямо и спокойно, короткими утверждениями; уточняет детали.')])]
        r = StateResolver(s,text,text).resolve(raw)
        if r.warnings: raise ValueError('Choices QA replay: '+str(r.warnings))
        kind = 'start' if index == 0 else 'turn'
        jid = repository.begin_job(save_id,text,kind,config)
        repository.save_context(jid,build_context(snapshot,repository.list_turns(save_id),text,kind,32768,2000),snapshot)
        repository.job_progress(jid,'validating',narrative=text,complete=True)
        snapshot['world_state'] = r.state
        repository.commit_job(jid,snapshot,r.choices,{},history_batch=r.history)
        snapshot = repository.get_snapshot(save_id)


def _seed_personality(repository, save_id):
    """Replay three accepted developmental scenes, no paid model calls."""
    from backend.runtime_v3.models import PersonalityProfile
    from backend.runtime_v3.resolver import StateResolver
    from backend.runtime_v3.context import build_context
    from backend.repositories.living_world import project
    snapshot=repository.get_snapshot(save_id)
    snapshot['world_state']['characters']['qa_asya']['personality']=PersonalityProfile().model_dump()
    with repository.connect() as conn:
        conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot,ensure_ascii=False),save_id))
    texts=['Ася выбрала рисование и закончила рисунок.',
           'На следующем занятии Ася снова выбрала рисовать и закончила пейзаж.',
           'На третьем занятии Ася закончила рисунок и сказала, что любит рисовать.']
    for index,text in enumerate(texts):
        camera=snapshot['world_state']['camera']
        raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids']),
            events=[dict(id='drawing',text=text,evidence=text,participants=['qa_asya'],witnesses=['qa_vera'],fact_ids=[])],
            development_evidence=[dict(id='drawing_evidence',actor_id='qa_asya',source_event_id='drawing',
                meaning='Самостоятельно выбирает и завершает рисование.',kind='behavior',assertion='completed',evidence=text)])
        if index==2:
            refs=list(snapshot['world_state']['characters']['qa_asya']['personality']['evidence'])+['drawing_evidence']
            raw['personality_deltas']=[dict(actor_id='qa_asya',evidence_ids=refs,
                rationale='Повторяющийся выбор и явное самоописание подтверждают предпочтение.',
                developmental_fit='established_capability',evidence=text,
                operations=[dict(item_id='drawing',field='preferences',operation='establish',text='Любит рисовать.',expected_text=None,expected_revision=0)])]
        r=StateResolver(snapshot['world_state'],text,'').resolve(raw)
        if r.warnings: raise ValueError('Personality QA replay: '+str(r.warnings))
        config=dict(model='deterministic-fixture',context_length=32768,max_tokens=2000,update_tokens=4096)
        jid=repository.begin_job(save_id,'Рассматриваю карту.', 'start' if index==0 else 'turn',config)
        repository.save_context(jid,build_context(snapshot,[],text,'turn',32768,2000),snapshot)
        repository.job_progress(jid,'validating',narrative=text,complete=True)
        snapshot['world_state']=r.state
        repository.commit_job(jid,snapshot,[],{},history_batch=r.history)
        snapshot=repository.get_snapshot(save_id)
    with repository.connect() as conn: project(conn,save_id,snapshot)


def _seed_goals(repository, save_id):
    from backend.runtime_v3.resolver import StateResolver
    from backend.runtime_v3.context import build_context
    from backend.repositories.living_world import project
    snapshot=repository.get_snapshot(save_id)
    for cid,rid in (('qa_ilya','intentions_4d05e847cba4c0a38a98'),('qa_sonya','intentions_ef4ffaa2b77eac28626d')):
        row=snapshot['world_state']['characters'][cid]['intentions'][0]
        row.update(id=rid,source_sequence=50)
    with repository.connect() as conn:
        conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot,ensure_ascii=False),save_id))
    text='Илья ждёт у входа. Соня ещё не пришла.'
    camera=snapshot['world_state']['camera']
    raw=dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids']))
    r=StateResolver(snapshot['world_state'],text,'').resolve(raw)
    config=dict(model='deterministic-fixture',context_length=32768,max_tokens=2000,update_tokens=4096)
    jid=repository.begin_job(save_id,'','start',config)
    repository.save_context(jid,build_context(snapshot,[],'','start',32768,2000),snapshot)
    repository.job_progress(jid,'validating',narrative=text,complete=True)
    snapshot['world_state']=r.state
    repository.commit_job(jid,snapshot,[],{},history_batch=r.history)
    with repository.connect() as conn: project(conn,save_id,repository.get_snapshot(save_id))


def knowledge_correction(snapshot, actor=ACTOR_ID):
    """Deterministic semantic output for manual/browser/ordinary-job regression."""
    camera=snapshot['world_state']['camera']
    text='Олег сообщил Кириллу: «Теперь я работаю в Академии двух берегов, из Мастерской карт я ушёл».'
    return text, dict(final_scene={k:camera[k] for k in ('location_id','present_character_ids')},
        events=[dict(id='qa_job_message',text=text,evidence=text,participants=['qa_oleg',actor],
            witnesses=[actor],fact_ids=['qa_oleg_academy'],medium='message',author_id='qa_oleg')],
        knowledge_gained=[dict(actor_id=actor,fact_id='qa_oleg_academy',source_event_id='qa_job_message',evidence=text)])


def _seed_knowledge(repository, save_id):
    """Existing checkpoint loader, ordinary start commit; no extra fixture format."""
    from backend.runtime_v3.models import Fact, Knowledge, NarrativeRole
    from backend.runtime_v3.resolver import StateResolver
    from backend.runtime_v3.context import build_context
    from backend.repositories.living_world import project
    snapshot=repository.get_snapshot(save_id);s=snapshot['world_state']
    for fid,oid,text in (
        ('qa_oleg_workshop','qa_restorers','Олег работает в Мастерской карт.'),
        ('qa_oleg_academy','qa_academy','Олег теперь работает в Академии двух берегов.')):
        s['facts'][fid]=Fact(id=fid,text=text,character_ids=['qa_oleg'],visibility='secret',
            claim=dict(subject_id='qa_oleg',predicate='primary_employment',value=oid)).model_dump()
    # Explicit authored baseline, not an inferred migration or simulated broadcast.
    for cid in (ACTOR_ID,'qa_vera','qa_timur'):
        s['knowledge'][cid+':qa_oleg_workshop']=Knowledge(actor_id=cid,fact_id='qa_oleg_workshop').model_dump()
    s['knowledge']['qa_oleg:qa_oleg_academy']=Knowledge(actor_id='qa_oleg',fact_id='qa_oleg_academy').model_dump()
    s['roles']['qa_oleg_job']=NarrativeRole(id='qa_oleg_job',actor_id='qa_oleg',kind='employment',
        title='Реставратор',organization_id='qa_academy',fact_id='qa_oleg_academy').model_dump()
    with repository.connect() as conn:
        conn.execute('UPDATE saves SET state_json=? WHERE id=?',(json.dumps(snapshot,ensure_ascii=False),save_id))
    text='Кирилл дома с Верой и Тимуром. Новостей о работе Олега они ещё не получали.'
    camera=s['camera'];raw=dict(final_scene={k:camera[k] for k in ('location_id','present_character_ids')})
    r=StateResolver(s,text,'').resolve(raw)
    config=dict(model='deterministic-fixture',context_length=32768,max_tokens=2000,update_tokens=4096)
    jid=repository.begin_job(save_id,'','start',config)
    repository.save_context(jid,build_context(snapshot,[],'','start',32768,2000),snapshot)
    repository.job_progress(jid,'validating',narrative=text,complete=True)
    snapshot['world_state']=r.state
    repository.commit_job(jid,snapshot,[],{},history_batch=r.history)
    with repository.connect() as conn:project(conn,save_id,repository.get_snapshot(save_id))


# #41 uses the same world/loader. One-day gestation is ONLY a compressed QA rule.
def _pregnancy(state, count=1):
    state=deepcopy(state)
    world=state['world']
    world['reproduction_policy']=dict(unprotected=1.0,protected=0.0,unknown=0.0,
        child_weights=[0.0]*(count-1)+[1.0],gestation_days=1)
    for cid,cap in ((ACTOR_ID,'can_impregnate'),('qa_vera','can_become_pregnant')):
        world['characters'][cid].update(life_status='alive',developmental_stage='adult',
            birth_date='1990-01-01',reproductive_capability=cap,identity_components={'family_name':'Ларин'})
    return state


CHECKPOINTS.update({'pregnancy':_pregnancy,'newborn':_pregnancy,
    'pregnancy-twins':lambda s:_pregnancy(s,2),'pregnancy-triplets':lambda s:_pregnancy(s,3),
    'newborn-twins':lambda s:_pregnancy(s,2),'newborn-triplets':lambda s:_pregnancy(s,3)})


def _seed_reproduction(repository,save_id,checkpoint):
    """Run structured accepted events through normal save jobs; never an LLM call."""
    from backend.runtime_v3.resolver import StateResolver
    from backend.runtime_v3.context import build_context
    snapshot=repository.get_snapshot(save_id)
    config=dict(model='deterministic-fixture',context_length=32768,max_tokens=2000,update_tokens=4096)
    text='Кирилл и Вера подтвердили взаимное согласие; интимная встреча взрослых состоялась.'
    def commit(text,raw,kind):
        nonlocal snapshot
        r=StateResolver(snapshot['world_state'],text,text).resolve(raw)
        if r.warnings: raise ValueError('Reproduction QA replay: '+str(r.warnings))
        jid=repository.begin_job(save_id,text,kind,config)
        repository.save_context(jid,build_context(snapshot,repository.list_turns(save_id),text,kind,32768,2000),snapshot)
        repository.job_progress(jid,'validating',narrative=text,complete=True)
        snapshot['world_state']=r.state;snapshot['character_cards'].extend(r.cards)
        repository.commit_job(jid,snapshot,[],{},history_batch=r.history)
        snapshot=repository.get_snapshot(save_id)
    def raw(text,elapsed=0):
        camera=snapshot['world_state']['camera']
        return dict(final_scene=dict(location_id=camera['location_id'],present_character_ids=camera['present_character_ids'],elapsed_minutes=elapsed),
            events=[dict(id='qa_reproduction_event',text=text,evidence=text,participants=[ACTOR_ID,'qa_vera'],
                witnesses=[ACTOR_ID,'qa_vera'],fact_ids=[],medium='observation')])
    claim=dict(id='qa_encounter',kind='sexual_intercourse',source_event_id='qa_reproduction_event',
        gestational_actor_id='qa_vera',impregnating_actor_id=ACTOR_ID,protection='unprotected',
        consent_actor_ids=[ACTOR_ID,'qa_vera'],parent_ids=[ACTOR_ID,'qa_vera'],
        assertion='completed_consensual_adult_event',evidence=text,player_evidence=text,player_assertion='explicit_choice')
    commit(text,dict(raw(text),reproductive_events=[claim]),'start')
    if checkpoint.startswith('newborn'):
        p=next(iter(snapshot['world_state']['pregnancies'].values()))
        text='Роды Веры завершились в доме. Кирилл присутствовал при рождении детей. Вера и Кирилл подтвердили, что они родители.'
        commit(text,dict(raw(text,1440),births=[dict(pregnancy_id=p['id'],source_event_id='qa_reproduction_event',
            assertion='birth_completed',disclosed_parent_ids=p['parent_ids'],location_id=snapshot['world_state']['camera']['location_id'],evidence=text)]),'turn')


def _possessions(state):
    from backend.runtime_v3.models import SignificantPossession, identity
    world = state['world']
    world['possessions'] = {}
    for pid, name, kind, owner, holder, place, witnesses in (
        ('qa_ring', 'Фамильное кольцо Кирилла', 'heirloom', ACTOR_ID, ACTOR_ID, HOME, list(PRESENT)),
        ('qa_camera', 'Плёночная камера Тимура', 'camera', 'qa_timur', 'qa_vera', HOME, list(PRESENT)),
        ('qa_letter', 'Личное письмо Олега', 'document', 'qa_oleg', 'qa_oleg', WORKSHOP, ['qa_oleg']),
    ):
        fid = pid + '_established'
        world['facts'][fid] = dict(id=fid, text=name + ': владелец ' + owner + ', хранитель ' + holder + ', место — ' + place + '. Вещь доступна.',
            secret=True, character_ids=[owner, holder] if owner != holder else [owner], evidence=['Исходное установленное состояние.'])
        eid = pid + '_seen'
        world['events'][eid] = dict(id=eid, text=world['facts'][fid]['text'], participants=witnesses,
            witnesses=witnesses, fact_ids=[fid], medium='observation', minute=START_MINUTE,
            evidence='Исходное установленное состояние.', player_observed=ACTOR_ID in witnesses)
        for cid in witnesses:
            world['knowledge'][cid+':'+fid] = dict(actor_id=cid, fact_id=fid, status='known', source_event_id=eid)
        world['possessions'][pid] = SignificantPossession(id=pid, name=name, kind=kind,
            owner_id=owner, holder_id=holder, location_id=identity('location', place.casefold()), status='available',
            fact_id=fid, field_facts={key:fid for key in ('owner_id','holder_id','location_id','status')}).model_dump()
    return state


CHECKPOINTS['possessions'] = _possessions


def _protagonist(state):
    state=_family(state)
    actor=state['world']['characters']['qa_asya']
    actor.update(birth_date='2016-10-05',developmental_stage='child',life_status='alive')
    next(c for c in state['characters'] if c['id']=='qa_asya')['fields']['Возраст']='10 лет'
    return state


CHECKPOINTS['protagonist'] = _protagonist
CHECKPOINTS['protagonist-infant'] = _pregnancy

# #68 reuses established residence/roles and significant transition provenance.
CHECKPOINTS["pacing"] = lambda state: _residence_roles(_family(state))


def _initiative(state):
    """#69 uses the same people, location, secrets and family provenance."""
    state = _family(state)
    for card in state['characters']:
        if card['id'] == 'qa_vera':
            card['fields']['Характер'] = 'Сдержанная, внимательная; умеет первой предложить близость, когда доверяет.'
            card['fields']['Стиль общения'] = 'Короткие тихие фразы, точные вопросы, тёплая ирония.'
        elif card['id'] == 'qa_timur':
            card['fields']['Характер'] = 'Прямой и импульсивный, но способен отступить и уважает отказ.'
            card['fields']['Стиль общения'] = 'Живой разговор, шутки; может прямо сказать, что пора уходить.'
    state['world']['characters']['qa_vera']['intentions'] = ['Предложить Кириллу провести вечер вдвоём.']
    state['world']['characters']['qa_timur']['intentions'] = ['Показать фотографии, затем отправиться в мастерскую.']
    return state


CHECKPOINTS['initiative'] = _initiative


def _continuity(state):
    """Same #78 world, focused Ilya/Sonya meeting regression with stable QA IDs."""
    for card in state['characters']:
        if card['id'] == ACTOR_ID: card['name'] = 'Илья'
        if card['id'] == 'qa_vera': card['name'] = 'Соня'
    state['campaign']['title'] += ' · Continuity'
    state['world']['characters'][ACTOR_ID]['situation'] = 'Ждёт Соню в «Гвозде».'
    state['world']['characters']['qa_vera']['situation'] = 'Идёт в «Гвоздь» к Илье.'
    state['world']['characters'][ACTOR_ID]['intentions'] = ['Встретиться с Соней.']
    state['world']['threads']['qa_meeting'] = dict(id='qa_meeting',
        description='Развивающиеся отношения Ильи и Сони.',
        state='Илья ждёт Соню в «Гвозде»; она обещала быть через пять минут.',
        public_state='Договорились встретиться.', status='developing',
        character_ids=[ACTOR_ID,'qa_vera'], visible_to_ids=[ACTOR_ID,'qa_vera'], relevance=.8)
    return json.loads(json.dumps(state, ensure_ascii=False).replace(HOME, '«Гвоздь»'))


CHECKPOINTS['continuity'] = _continuity


def _phone(state):
    from backend.runtime_v3.remote_models import CommunicationCapabilities, Contact, Conversation
    world=state['world'];now=state['world_clock']['minute']
    world['communication']=CommunicationCapabilities(text_message=True,voice_call=True,presentation='phone',
        region='QA-fiction',emergency_numbers={'medical':'qa-medical','police':'qa-police','fire':'qa-fire'}).model_dump()
    world['contacts']={}
    for owner,target,label,address in [(ACTOR_ID,'qa_vera','Вера работа','qa-vera'),('qa_vera',ACTOR_ID,'Кирилл','qa-kirill'),
        (ACTOR_ID,None,'Мастерская','qa-workshop'),(ACTOR_ID,None,'Новый знакомый','qa-unknown')]:
        cid='phone-'+owner+'-'+address
        world['contacts'][cid]=Contact(id=cid,owner_id=owner,character_id=target,label=label,address=address,
            kind='shared' if address=='qa-workshop' else 'person',identity_visible=target is not None,
            provenance='QA explicit import',created_at=now).model_dump()
    world['conversations']={'qa-group':Conversation(id='qa-group',title='Общая переписка',group=True,
        members=[dict(actor_id=a,joined_at=now,provenance='QA explicit membership') for a in (ACTOR_ID,'qa_vera')],
        provenance='QA explicit group').model_dump()}
    return state


CHECKPOINTS['phone'] = _phone


def _ui_calendar(state):
    state = _commitments(state)
    state['world_clock']['calendar']['profile']['observances'] += [
        dict(id='private-date',name='Скрытая личная дата',month=10,day=8,character_ids=['qa_oleg']),
        dict(id='own-date',name='Годовщина первой восстановленной карты',month=10,day=8,character_ids=[ACTOR_ID]),
    ]
    for i,status in enumerate(('pending','resolved','cancelled')):
        state['world']['scheduled_events'][f'qa_ui_{i}']=dict(id=f'qa_ui_{i}',description=['Встреча реставраторов и обсуждение очень длинного названия выставки','Получение архивных материалов','Отменённая поездка на пристань'][i],participants=[ACTOR_ID],due_minute=0,status=status,commitment=True,temporal=dict(date='2026-10-08',time='10:00'),evidence='Исходный план QA.',source_turn=0)
    return state


def _ui_custom_calendar(state):
    for actor in state['world']['characters'].values():
        actor.pop('birth_date',None)
    state['world_clock']['calendar']=dict(start_minute=START_MINUTE,start_date='0042-02-25',start_weekday=4,profile=dict(id='qa-custom',system='custom',month_lengths=[20,25],month_names=['Свет','Тень'],weekday_names=['Первый','Второй','Третий','Четвёртый','Пятый'],observances=[dict(id='oath',name='Годовщина клятвы',month=2,day=25)]))
    return state


def _ui_family(state):
    from backend.runtime_v3.models import ObjectiveRelation
    state=_family(state);world=state['world']
    def relation(rid,kind,a,b,status='active',certainty='known',outcome=''):
        fid=rid+'-fact'
        world['facts'][fid]=dict(id=fid,text=f'Семейная связь {a}, {b}.',secret=True,character_ids=[a,b],evidence=['QA'])
        world['knowledge'][ACTOR_ID+':'+fid]=dict(actor_id=ACTOR_ID,fact_id=fid,status=certainty)
        if kind in ('spouse','partner'):a,b=sorted((a,b))
        world['objective_relations'][rid]=ObjectiveRelation(id=rid,kind=kind,source_id=a,target_id=b,fact_id=fid,status=status,outcome=outcome,since=0,until=1 if status=='closed' else None,closure_fact_id=fid if status=='closed' else None,evidence='QA',source_turn=0).model_dump()
    relation('ui-ex','spouse','qa_timur','qa_marina','closed',outcome='divorced')
    relation('ui-partner','partner','qa_timur','qa_elena')
    relation('ui-adoption','adoptive_parent','qa_timur','qa_roman')
    relation('ui-guardian','guardian','qa_marina','qa_roman',certainty='suspected')
    # Oleg has no relatives; Zoya tests the public directory without Knowledge.
    fid='ui-known-oleg'
    world['facts'][fid]=dict(id=fid,text='Кирилл знаком с Олегом.',secret=False,character_ids=['qa_oleg'],evidence=['QA'])
    world['knowledge'][ACTOR_ID+':'+fid]=dict(actor_id=ACTOR_ID,fact_id=fid,status='known')
    return state


def _ui_dense_family(state):
    state=_ui_family(state);world=state['world']
    from backend.runtime_v3.models import ObjectiveRelation
    for i in range(100):
        cid=f'qa_family_{i}'
        card=deepcopy(state['characters'][1]);card.update(id=cid,name=f'Родственник {i+1} с длинным именем',is_player=False)
        state['characters'].append(card)
        world['characters'][cid]=deepcopy(world['characters']['qa_roman']);world['characters'][cid]['id']=cid
        parent='qa_timur' if i<10 else f'qa_family_{i//10-1}'
        fid=f'ui-dense-{i}'
        world['facts'][fid]=dict(id=fid,text=f'Известное родство {parent} и {cid}.',secret=True,character_ids=[parent,cid],evidence=['QA'])
        world['knowledge'][ACTOR_ID+':'+fid]=dict(actor_id=ACTOR_ID,fact_id=fid,status='known')
        world['objective_relations'][fid]=ObjectiveRelation(id=fid,kind='parent',source_id=parent,target_id=cid,fact_id=fid,evidence='QA',source_turn=0).model_dump()
    return state


CHECKPOINTS.update({'ui-calendar':_ui_calendar,'ui-calendar-custom':_ui_custom_calendar,'ui-family':_ui_family,'ui-family-dense':_ui_dense_family})


# #43 extends the same #78 fixture; original checkpoints stay unchanged.
CHECKPOINTS['long-term'] = _pregnancy

def _seed_long_term(repository, save_id):
    from backend.runtime_v3.models import Character, Thread
    snapshot = repository.get_snapshot(save_id)
    state = snapshot['world_state']
    for n in range(120):
        cid = f'qa_background_{n:03}'
        state['characters'][cid] = Character(id=cid, life_status='alive').model_dump()
        snapshot['character_cards'].append(dict(id=cid, name=f'Фоновый персонаж {n}', fields={}, aliases=[], is_player=False))
        if n < 12:
            state['threads'][cid] = Thread(id=cid, description='Незавершённое обучение', character_ids=[cid], relevance=.6).model_dump()
    with repository.connect() as db:
        db.execute('UPDATE saves SET state_json=? WHERE id=?', (json.dumps(snapshot, ensure_ascii=False), save_id))
    _seed_reproduction(repository, save_id, 'newborn')


def _ui_public_directory(state):
    state=_ui_family(state)
    state['world']['knowledge']={}
    state['world']['contacts']={}
    state['world']['characters']['qa_zoya']['birth_date']='2000-10-09'
    return state

CHECKPOINTS['ui-public-directory']=_ui_public_directory


def _ui_dossier(state):
    """#83 dense, sparse and restricted records in the shared #78 world."""
    from backend.runtime_v3.models import Condition
    state=_ui_family(state)
    world=state['world']
    for card in state['characters']:
        if card['id']==ACTOR_ID:
            card['fields'].update({'Биография':'Кирилл вернулся в город после работы в архиве. '+('Он восстанавливает старые карты и ищет историю своей семьи. '*18),
                'Характер':'Внимателен к деталям, сдержан в незнакомой компании.', 'Стиль общения':'Говорит спокойно, иногда шутит.',
                'Внешность':'Короткие тёмные волосы, светлая рубашка, следы краски на руках.'})
    world['characters'][ACTOR_ID]['physical_state']='Устал после дороги, промок под дождём.'
    world['characters'][ACTOR_ID]['biological_sex']='male'
    world['characters']['qa_vera']['biological_sex']='female'
    world['conditions']['dossier-known']=Condition(id='dossier-known',actor_id=ACTOR_ID,description='Повреждение ноги',effects={'can_move':False},evidence='Осторожно опирается на трость.').model_dump()
    world['facts']['dossier-hidden']=dict(id='dossier-hidden',text='PRIVATE DOSSIER CONDITION',secret=True,character_ids=['qa_vera'],evidence=['QA'])
    world['conditions']['dossier-hidden']=Condition(id='dossier-hidden',actor_id='qa_vera',description='PRIVATE DOSSIER CONDITION',fact_id='dossier-hidden',effects={'can_speak':False},evidence='PRIVATE EVIDENCE').model_dump()
    world['knowledge']['qa_vera:dossier-hidden']=dict(actor_id='qa_vera',fact_id='dossier-hidden',status='known')
    return state


CHECKPOINTS['ui-dossier']=_ui_dossier


def _ui_personal(state):
    """#141: known concurrent romance and a suspected relation, using #78 data."""
    from backend.runtime_v3.models import ObjectiveRelation
    state = _ui_dossier(state)
    world = state['world']
    for cid, kind, certainty in [('qa_elena', 'partner', 'known'), ('qa_marina', 'engaged', 'suspected')]:
        rid = 'ui-personal-' + cid
        world['facts'][rid] = dict(id=rid, text='Личные отношения установлены.', secret=True,
                                  character_ids=[ACTOR_ID, cid], evidence=['QA'])
        world['knowledge'][ACTOR_ID + ':' + rid] = dict(actor_id=ACTOR_ID, fact_id=rid, status=certainty)
        a, b = sorted((ACTOR_ID, cid))
        world['objective_relations'][rid] = ObjectiveRelation(id=rid, kind=kind, source_id=a,
            target_id=b, fact_id=rid, since=0, evidence='QA', source_turn=0).model_dump()
    return state


CHECKPOINTS['ui-personal'] = _ui_personal



def _ui_portrait_polish(state):
    """#121: shared dossier/phone regression fixture, canonical identities only."""
    from backend.runtime_v3.remote_models import Contact
    state = _phone(_ui_dossier(state))
    world = state['world']; now = state['world_clock']['minute']
    ids = [ACTOR_ID, 'qa_vera', 'qa_timur']
    for owner in ids:
        for target in ids:
            if owner == target:
                continue
            cid = f'polish-{owner}-{target}'
            world['contacts'][cid] = Contact(id=cid, owner_id=owner, character_id=target,
                label=next(c['name'] for c in state['characters'] if c['id']==target), address='qa-'+target,
                identity_visible=True, provenance='QA explicit import', created_at=now).model_dump()
    world['conversations']['qa-group']['members'].append(dict(actor_id='qa_timur', joined_at=now,
        left_at=None, provenance='QA explicit membership'))
    world['characters'][ACTOR_ID]['situation'] = 'Сравнивает старую карту с записями семьи. ' * 8
    return state


CHECKPOINTS['ui-portrait-polish'] = _ui_portrait_polish


def _ui_inspector(state):
    """#86 presentation checkpoint: existing canonical fields, no new mechanics."""
    from backend.runtime_v3.models import Relationship, Thread
    state = _ui_dossier(_commitments(state))
    world = state['world']
    world['relationships']['qa_vera:'+ACTOR_ID] = Relationship(
        source_id='qa_vera', target_id=ACTOR_ID,
        context='Вера ценит заботу Кирилла, но не согласна с его решением.',
        dimensions={'trust': -20, 'respect': 45}).model_dump()
    for status, text in [('developing','Подготовка выставки карт'),('dormant','Возвращение на пристань'),
                         ('resolved','Завершённая реставрация')]:
        tid='qa_inspector_'+status
        world['threads'][tid]=Thread(id=tid, description=text, state='Записанное состояние линии: '+text+'.',
            status=status, character_ids=[ACTOR_ID,'qa_vera'], relevance=.5).model_dump()
    return state


CHECKPOINTS['ui-inspector'] = _ui_inspector


def _phone_office(state):
    """#133 continuity checkpoint, retaining the #78 import/schema and stable IDs."""
    state=_phone(state)
    names={ACTOR_ID:'Илья','qa_vera':'Катя','qa_marina':'Виктория'}
    for card in state['characters']:
        if card['id'] in names:card['name']=names[card['id']]
    scene=state['world']['scenes'][SCENE_ID]
    scene.update(location='Кабинет Ильи',participants=[ACTOR_ID],text='Илья в кабинете. Виктория ждёт за дверью и пока не стучит.')
    for cid,place in [(ACTOR_ID,'Кабинет Ильи'),('qa_vera',LIBRARY),('qa_marina','Коридор перед кабинетом')]:
        state['world']['characters'][cid].update(location=place,scene_id=SCENE_ID if cid==ACTOR_ID else None)
    state['world']['contacts']['phone-qa_kirill-qa-vera']['label']='Катя'
    return state


CHECKPOINTS['phone-office']=_phone_office


def _ui_canonical_personal(state):
    """#150: authoring canon exists without any observer knowledge fact."""
    from backend.runtime_v3.models import ObjectiveRelation
    state = _ui_dossier(state)
    names = {'qa_marina': 'Марина Волкова', 'qa_timur': 'Сергей Волков'}
    for card in state['characters']:
        if card['id'] in names:
            card['name'] = names[card['id']]
    # This checkpoint intentionally starts before any marriage/closure phases.
    state['world']['objective_relations'] = {
        'volkov-marriage': ObjectiveRelation(id='volkov-marriage', kind='spouse',
            source_id='qa_marina', target_id='qa_timur', since_date='1999-06-12').model_dump()}
    return state


CHECKPOINTS['ui-canonical-personal'] = _ui_canonical_personal
