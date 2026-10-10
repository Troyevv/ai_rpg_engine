"""Repository-owned Initial World State for Epic #36 manual/integration QA.

This is the supported draft aggregate, not another Runtime schema. All loads go
through JSON import, draft validation/confirmation and the normal migration.
"""
import json

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


CHECKPOINTS = {'residence-roles':_residence_roles,'family':_family,'family-care':_family_care,'family-incapacitated':_family_incapacitated,'calendar-evening' :_calendar_evening,'calendar-leap':_calendar_leap,'commitments':_commitments}
CHECKPOINTS['milestones'] = lambda state: _residence_roles(_family(state))


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
                    **({'player_assertion':'explicit_choice','player_evidence':text} if section=='residence_changes' else {})) for row in rows]
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
    if checkpoint == 'milestones': _seed_milestones(repository,result['save'])
    return dict(result, workspace=workspace['id'], fixture_version=FIXTURE_VERSION, checkpoint=checkpoint)
