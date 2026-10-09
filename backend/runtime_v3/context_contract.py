"""Semantic work stays in the existing extraction call; code verifies provenance."""
EXTRACTION_CONTRACT = '''
АКТУАЛЬНЫЙ КОНТРАКТ RUNTIME V3 имеет приоритет над сохранёнными инструкциями.
Верни RawTurnResult только для player_input и completed_narrative ЭТОГО хода.
Не продолжай рассказ. Существующие ID копируй. Evidence — точная цитата текущего хода.
Final_scene — фактическое состояние В КОНЦЕ completed_narrative, не исходная камера.
Не копируй прежние camera.location_id и present_character_ids механически.
Narrative может вводить новые места вне исходного мира. Если ход закончился в новом
конкретном месте, одновременно создай locations[] со стабильным canonical ID, name,
evidence из completed_narrative/player_input и укажи этот ID в final_scene.location_id.
При нескольких переходах выбери конечное место, не промежуточное.
Если место уже известно, используй существующий ID: «Гвоздь», «кофейня Гвоздь»,
«кафе Гвоздь» могут быть одним местом, не создавай дубль из-за формы названия.
Простое упоминание, обсуждение или план посетить место не меняют камеру.
Present_character_ids — только физически присутствующие в конце: ушедших исключи,
пришедших и оставшихся включи; сообщения/воспоминания не означают присутствия.
Для ушедших передай movements с конечным местом, только если оно установлено.
Movements описывают конечные перемещения остальных персонажей; если всё же передаёшь
маршрут участника final_scene, его последняя точка должна совпадать с final_scene.location_id.
Situation описывает конечную объективную ситуацию с situation_evidence, не старое место;
индивидуальные situation затронутых NPC обнови через character_changes с evidence.
Новый значимый NPC требует promotions с полной карточкой и evidence; если он остаётся
в сцене, тот же ID включи в present_character_ids. Упоминание NPC не означает приход.
Проверь все active goals / intentions / obligations затронутых персонажей:
завершено → completed; сорвано → failed; потеряло контекст (обед закончился) → expired;
отменено → cancelled; заменено → superseded. Передай *_updates со стабильным id и evidence.
«Поддеть Юру» завершается после язвительной шутки; «Поговорить с Соней» после разговора.
Семантику определяешь ты, словаря разрешённых глаголов нет. Намерение/обещание ещё не выполнение.
Создавать новые внутренние цели, намерения, обязательства controlled_actor можно только
из явного player_input. Завершать уже существующие можно по фактам completed_narrative.
Emotion controlled_actor: только явно выраженное внутреннее состояние из player_input;
никаких выводов из жестов, мимики, отношений, narrative или карточки. Свободный язык:
«Внутри привычная горечь», «На душе тревожно», «Меня это бесит», «Настроение в ноль»,
«Чувствую себя опустошённым» — явные состояния. «Сжимаю кулак», «Улыбаюсь»,
«Отвожу взгляд», «Вздыхаю» сами по себе — НЕ emotion. Вопрос, условие, речь другого — не источник.
Для emotion передай player_evidence.emotion (полное утверждение игрока) и
emotion_assertion="explicit_internal_state". Это твоя семантическая классификация, не угадывание Runtime.
Physical_state — текущая физика (боль, усталость, голод, холод и т.п.). Обновляй и очищай
physical_state="", если причина устранена: поел, согрелся, поспал. Сохраняй неустранённые симптомы.
Подтверждай evidence текущего хода, не выводи неизбежное выздоровление из одного упоминания сна.
Relationship и emotion различны. Автоматические relationship_changes разрешены одинаково
NPC → NPC, NPC → controlled_actor, controlled_actor → NPC. Player evidence для отношений НЕ нужен.
Отношения directed, не зеркаль A → B в B → A. Dimensions — новые абсолютные значения, не дельты.
Нейтральный разговор обычно означает отсутствие relationship_changes. Маленькое значимое событие
даёт небольшую динамику; накопление событий и серьёзное предательство/спасение допускают большую.
Сохраняй инерцию. Ручная правка — текущий baseline, а не запрет дальнейших изменений.
Final_scene.remote_interactions перечисляет только активные В КОНЦЕ хода переписку/звонок/рацию
с actor_id, channel и evidence. Перечитывание старого сообщения — не активное общение.
Подтверди текущую связь заново, завершившуюся опусти. При физическом приходе включи NPC в present.
Knowledge только через Fact → Event этого ответа → Witness → Knowledge: actor_id входит в event.witnesses, fact_id — в event.fact_ids;
medium observation/conversation/message/testimony/discovery. Нет цепочки — нет acquisition.
GM-only факты и карточки не становятся знаниями игрока/NPC. Учитывай ownership и visibility.
Final_scene задаёт конечное место/участников, situation — объективное положение, не emotion;
situation_evidence подтверждает общую ситуацию. Movements нужны только для остальных персонажей.
Elapsed_minutes — целая длительность показанных действий; не делай произвольных таймскипов.
Для Event сообщения передай author_id только установленного автора (он входит в participants).
Получатель/читатель — witnesses; не угадывай автора по присутствию в сцене.
Events не требуют микроскопической хронологии; неизвестные minute/order опусти.
Promotions только значимые постоянные роли с полной карточкой, не случайные прохожие.
Для controlled_actor choices — 6 объектов action/speech, для observer — [].
Не создавай scene_id, last_event_id, from_location или StatePatch.
'''

NARRATIVE_CONTRACT = '''
GM-only карточки и внутренние состояния не являются знанием POV.
FULL_REMOTE даёт личность для реплик, но не право показывать невидимые жесты/комнату собеседника.
ACTIVE_REFERENCED даёт поведенческий профиль автора сообщения, записи или действия вне сцены.
Это не физическое присутствие и не активный удалённый разговор. Воспроизводи характер/стиль автора.
Семантическая релевантность не означает истину, Knowledge или присутствие.
World Truth — facts. Знания POV и Знания действующих персонажей ссылаются на fact_id без повтора текста.
Отсутствие Knowledge не разрешает персонажу знать GM-only факт; unknown/suspected сохраняют смысл.
COMPACT_REFERENCED — обсуждаемый человек, а не участник разговора; INDEX — только разрешение имён.
Не назначай controlled_actor действия, слова, решения и эмоции. Situation — объективная ситуация.
При написании диалогов используй «Стиль общения» каждого персонажа: лексику, длину фраз, юмор и реакцию на конфликт. Сохраняй характер и подтекст последних сцен.
Знание персонажа определяется Knowledge, не наличием факта в GM context.
Не превращай засыпание в произвольный скачок времени.
Предложи 6 choices action/speech для controlled_actor; для observer choices=[].
'''


TIME_CONTRACT = """
current_time — единственная canonical проекция времени: Day N, date (если известна),
weekday_name, time HH:MM, day_period. Не вычисляй дни недели из world_time.
Сегодня/завтра/вчера и дни недели привязывай к этой проекции. Narrative и choices
уважают текущий период: в 20:42 вечер уже наступил, не предлагай ждать его сегодня.
Неизвестные даты и birthdays не выдумывай. age вычислен Runtime; статический возраст
карточки при известной birth_date не является текущим возрастом.
calendar_context сообщает только существование даты. Не выводи из праздника/дня
рождения выходной, празднование, подарки, присутствие, Knowledge или действия.
Если дан time_skip_target, завершай описание и формируй choices для этого конечного времени.
Scheduled temporal_projection future/unresolved не означает due или happened.
Даже due не означает, что событие произошло. temporal задавай структурно только
при явном сроке; Runtime привязывает относительное значение ко времени хода.
Используй язык активной кампании для прозы и choices, не язык технических ключей.
"""


COMMITMENT_CONTRACT = """
Scheduled_events — договорённости, не гарантированные будущие факты. PLAN и OVERDUE PLAN
не означают выполнение; FACT и CANCELLED PLAN нельзя повторно инициировать.
Исторический факт «договорились встретиться» остаётся фактом прошлого, не новым заданием.
CURRENT STATE интервала означает установленный отпуск/каникулы, не поездку или смену дома.
Не раскрывай GM-only планы персонажам без Knowledge. Препятствия учитывай вместе с планом.
Окно temporal_projection.start_minute/end_minute — границы релевантности, а не точное время;
condition «после работы» остаётся условием. Не выдумывай 18:00 из слова «вечером».
Срок свадьбы не означает брак, приглашение не означает присутствие; используй существующих
персонажей для установленных планов, не создавай обязательный свадебный checklist.
"""
NARRATIVE_CONTRACT += COMMITMENT_CONTRACT
EXTRACTION_CONTRACT += """
PLAN/OVERDUE PLAN — не факт выполнения. FACT/CANCELLED PLAN повторно не активировать.
Для scheduled_event_changes обязательно assertion и evidence текущего хода:
agreed — явная принятая договорённость с временной привязкой; rescheduled — перенос того же ID;
cancelled — явно отменён/неактуален; occurred — действие фактически состоялось;
blocked — препятствие без установленного исхода; missed — подтверждено невыполнение (не успех).
Для личного интервала temporal/end_temporal: started — установлен фактический старт/текущее
состояние («я в отпуске до ...»), ended — подтверждено окончание уже начатого интервала.
Может быть/мечта/непринятое предложение/обсуждение прошлого не создают agreed.
Не создавай план задним числом из старого факта. Завершай именно совпавший canonical ID:
встреча в кафе не закрывает отдельную поездку на дачу. Не создавай новый ID при переносе.
Для agreed/rescheduled/cancelled с controlled_actor нужны player_assertion=explicit_choice
и player_evidence — точная цитата явного решения из player_input, не из narrative.
При отмене другим участником укажи decision_actor_id этого NPC: его отказ не требует согласия игрока.
Проверяй добровольное участие, не приписывай согласие из чужого предложения или вопроса.
Времена извлекай как temporal: date ИЛИ weekday ИЛИ day_offset + time ИЛИ day_period.
Не вычисляй due_minute для human commitments. Условие после работы сохраняй в condition.
Для интервала end_temporal — отдельная привязка к времени этого хода, не к началу интервала.
Возвращение и выезд — разные ID; depends_on содержит только явные необходимые зависимости.
Отмена родителя делает зависимый план неактуальным, не отменяет прочие события группы.
Отпуск не перемещает персонажа; каникулы не убирают образование. Само время не начинает
и не завершает интервал. Не назначай штраф отношениям за срок/срыв автоматически.
"""

LIFE_CONTRACT = '''
Canonical life/social truth is separate from directed emotions and Character Knowledge.
life_changes, condition_changes and social_relation_changes require assertion=established
and a verbatim source proving completed/established truth, never a wish, proposal or future plan.
No spouse from attraction, no parent from age/surname, no friendship from scene count.
Intimacy does not imply affection, love, exclusivity, partnership or a promise: each
emotional delta needs its own evidence. Never assign voluntary feelings to EXTERNAL actor.
Family status changes do not alter names, residence, emotions, Knowledge or unrelated ties.
A name change needs explicit evidence; controlled actor voluntary choices also need
player_assertion=explicit_choice and player_evidence quoting player_input. NPC-initiated
closure uses decision_actor_id. Adoptive/legal parent, biological parent, guardian,
foster_parent and step_parent are distinct; an adoption must be completed and valid in setting.
Close a specific relation ID; a new phase/reconnection uses a new ID. Marriage can close
an established engagement via a separate explicit closure; never infer monogamy.
Use facts with character_ids covering the affected identities and fact_id on new life/social
records. Transfer Knowledge only through the existing witnessed informational event path;
closure_fact_id is separate so learning the old tie does not reveal its later ending.
Do not add fact IDs without creating the corresponding facts. No global disclosure.
Conditions persist across scenes; only evidenced resolution releases their capability effects.
condition effects only restrict capabilities (false); unknown_outcome does NOT mean recovered.
Respect capability_projection: no ordinary actions/choices while can_act=false, no speech
while can_speak=false, no self-movement while can_move=false. Dead actors stay historical,
never ordinary active scene/remote/background participants, never new goals/emotions.
Missing does not mean dead. Age does not create biography/roles/personality. Coarse
explicit developmental_stage is setting-dependent, unknown adulthood is not adult eligibility.
Current canonical display_name is authoritative; old prose retains historical names.
Return choices=[] for a blocked controlled actor; world time/observation can continue.
'''
NARRATIVE_CONTRACT += '\n' + LIFE_CONTRACT
EXTRACTION_CONTRACT += """
Life/social changes: assertion=established plus verbatim evidence of completed truth.
Never infer ties from attraction/age/names/scenes, adoption from affection, love from sex,
or death from absence/time. Missing != dead. Conditions persist until explicit resolution;
effects only restrict (false). Close a specific ID; reconnect with a new ID. No monogamy.
Marriage/adoption change neither names, residence, emotions nor Knowledge automatically.
Parent, adoptive_parent, guardian, foster_parent, step_parent are distinct; completed care
status must be valid in setting. Voluntary EXTERNAL relation/name choices require
player_assertion=explicit_choice + player_evidence. NPC closure: decision_actor_id.
New fact_id must link a fact naming all endpoints; closure_fact_id is separate. Knowledge
requires the normal witnessed event path. No disclosure or voluntary feeling fabrication.
Dead actors get no ordinary updates. Blocked can_act yields choices=[]. Developmental
stage needs explicit setting-aware evidence, never invented biography.
"""
