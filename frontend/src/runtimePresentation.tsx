/** Read-only projections of the supplied (server-filtered) draft. Never resolve from a global cache. */
import type {ReactNode} from 'react';
type RecordValue = Record<string, unknown>;
export type DisplayState = {characters: {id:string;name:string}[];locations:{id:string;name:string}[];world:Record<string,unknown>};
export const runtimeLabels: Record<string,string> = {
 id:'Идентификатор', status:'Статус',kind:'Тип', source_id:'От кого',target_id:'К кому',actor_id:'Персонаж',owner_id:'Владелец',holder_id:'Текущий держатель',character_id:'Адресат',character_ids:'Персонажи',location:'Местоположение',location_id:'Место',location_ids:'Места',organization_id:'Организация',parent_id:'Родительское место',
 conscious:'В сознании',can_perceive:'Может воспринимать',can_act:'Может действовать',can_speak:'Может говорить',can_move:'Может передвигаться',effects:'Влияние на возможности',capabilities:'Возможности',physical_state:'Физическое состояние',life_status:'Жизненный статус',developmental_stage:'Этап жизни',birth_date:'Дата рождения',biological_sex:'Биологический пол',reproductive_capability:'Репродуктивные возможности',
 text:'Описание',description:'Описание',title:'Название',name:'Название',label:'Подпись',address:'Адрес',blocked:'Заблокирован',available:'Доступен',identity_visible:'Личность раскрыта',context:'Контекст',evidence:'Основания',provenance:'Происхождение',revision:'Ревизия',source_turn:'Исходный ход',fact_id:'Факт',fact_ids:'Факты',source_event_id:'Событие-источник',closure_fact_id:'Основание завершения',life_fact_id:'Факт жизненного статуса',parentage_complete_fact_id:'Основание полноты родства',
 since:'С минуты',until:'До минуты',since_date:'Дата начала',until_date:'Дата завершения',outcome:'Результат',duration:'Длительность',minute:'Минута мира',date:'Дата',time:'Время',start_minute:'Начальная минута',start_weekday:'Начальный день недели',start_date:'Начальная дата',profile:'Профиль календаря',system:'Система',month_lengths:'Длины месяцев',month_names:'Названия месяцев',weekday_names:'Дни недели',seasons:'Сезоны',observances:'Памятные даты',month:'Месяц',day:'День',calendar:'Календарь',
 personality:'Личность',appearance:'Внешность',values:'Ценности',items:'Элементы',traits:'Черты',communication:'Речь',habits:'Привычки',strengths:'Сильные стороны',weaknesses:'Слабости',fears:'Страхи',preferences:'Предпочтения',temperament:'Темперамент',intensity:'Выраженность',category:'Категория',field:'Область',value:'Значение',history:'История',name_history:'История имён',previous:'Ранее',current:'Сейчас',identity_components:'Составляющие личности',
 goals:'Цели',intentions:'Намерения',obligations:'Обязательства',dependencies:'Зависимости',review_required:'Требует проверки',reviewed_signature:'Подпись проверки',due_minute:'Срок · минута мира',source_fact_id:'Факт-источник',source_event_ids:'События-источники',source_turn_id:'Ход-источник',
 trust:'Доверие',affection:'Привязанность',attraction:'Влечение',irritation:'Раздражение',fear:'Страх',jealousy:'Ревность',respect:'Уважение',dimensions:'Чувства',visibility:'Видимость',secret:'Тайна',visible_to_ids:'Кому известно',claim:'Утверждение',subject_id:'Субъект',predicate:'Свойство',participants:'Участники',witnesses:'Свидетели',player_observed:'Наблюдал игрок',
 temporal:'Время события',end_temporal:'Окончание',day_offset:'Сдвиг дней',weekday:'День недели',day_period:'Время суток',condition:'Условие',commitment:'Договорённость',depends_on:'Зависит от',started_minute:'Начато на минуте',resolved_minute:'Завершено на минуте',
 members:'Участники',joined_at:'Присоединился',left_at:'Покинул',created_at:'Создано на минуте',channel:'Канал',content:'Содержание',sender_id:'Отправитель',recipient_ids:'Получатели',contact_id:'Контакт',conversation_id:'Разговор',destination:'Адрес доставки',group:'Группа',service:'Служба',
 mother_id:'Мать',father_id:'Отец',child_id:'Ребёнок',child_ids:'Дети',pregnancy_id:'Беременность',conception_minute:'Минута зачатия',due_date:'Ожидаемая дата',birth_minute:'Минута рождения',sex:'Пол',children:'Дети',proposed_name:'Предложенное имя',given_name:'Имя',family_name:'Фамилия',patronymic:'Отчество',
 text_message:'Сообщения',voice_call:'Звонки',presentation:'Представление',region:'Регион',ring_timeout_minutes:'Ожидание звонка · минуты',emergency_numbers:'Экстренные номера',reproduction_policy:'Правила репродукции',communication_capabilities:'Возможности общения',aliases:'Другие названия',public_state:'Известное герою состояние',state:'Состояние',relevance:'Значимость',situation:'Сейчас',emotion:'Эмоции',event_ids:'События',end_minute:'Конечная минута',
};
Object.assign(runtimeLabels,{
 adult_age:'Возраст совершеннолетия',applied:'Применённые изменения',asset_id:'Ресурс портрета',birth_event_id:'Событие рождения',birth_provenance:'Происхождение даты рождения',child_weights:'Распределение числа детей',closed:'Завершено',components:'Составляющие имени',conceived:'Зачатие состоялось',condition_id:'Обстоятельство',count_fact_id:'Факт количества детей',crop:'Кадрирование',decision_actor_ids:'Кто выбрал имя',delegated_to:'Кому поручено',deleted:'Удалено',display_name:'Отображаемое имя',earliest_minute:'Не ранее минуты',latest_minute:'Не позднее минуты',exact_minute:'Точная минута',emotion_source_sequence:'Источник эмоции',established:'Установлено',event_id:'Событие',field_facts:'Основания полей',gestation_days:'Срок вынашивания · дни',gestational_actor_id:'Вынашивающий персонаж',impregnating_actor_id:'Биологический отец',height:'Высота',width:'Ширина',interrupts:'Прерывает сцену',last_attempt_minute:'Последняя попытка',legacy_text:'Исходное описание',min_age:'Минимальный возраст',max_age:'Максимальный возраст',meaning:'Значение опыта',order:'Порядок',parent_ids:'Родители',player_owned:'Задано игроком',policy:'Правила',portraits:'Портреты',protected:'С защитой',unprotected:'Без защиты',unknown:'Неизвестно',protection:'Защита',remote_source_ids:'Источники общения',replaces:'Заменяет',seen_sources:'Учтённые источники',sex_fact_ids:'Факты о поле детей',shared_family_name:'Общая фамилия',source_ids:'Источники',source_sequence:'Порядок источника',stage:'Этап жизни',time_reference_minute:'Опорная минута',turn_id:'Ход',type:'Тип',x:'Координата X',y:'Координата Y',zoom:'Масштаб',conversations:'Разговоры',remote_events:'События общения',reproductive_events:'Репродуктивные события',naming_decisions:'Выбор имён',
});
export const enumLabels:Record<string,string>={
 alive:'Жив',dead:'Умер',missing:'Пропал',unknown:'Неизвестно',infant:'Младенец',child:'Ребёнок',adolescent:'Подросток',adult:'Взрослый',female:'Женский',male:'Мужской',active:'Действует',closed:'Завершено',completed:'Выполнено',cancelled:'Отменено',failed:'Не выполнено',superseded:'Заменено',expired:'Срок истёк',blocked:'Заблокировано',retired:'Больше не действует',resolved:'Разрешено',pending:'Ожидается',unknown_outcome:'Исход неизвестен',temporary:'Временное',persistent:'Постоянное',
 spouse:'Супруги',partner:'Партнёры',engaged:'Помолвлены',parent:'Родитель',adoptive_parent:'Приёмный родитель',guardian:'Опекун',foster_parent:'Воспитывающий родитель',step_parent:'Отчим / мачеха',sibling:'Брат / сестра',contact:'Знакомство',friend:'Друзья',close_friend:'Близкие друзья',coworker:'Коллеги',ended:'Окончилось',divorced:'Развод',widowed:'Вдовство',revoked:'Отозвано',
 known:'Известно',suspected:'Предположение',outdated:'Устарело',refuted:'Опровергнуто',public:'Общедоступно',secret:'Тайна',developing:'Развивается',dormant:'Неактивно',paused:'Приостановлено',available:'Доступно',lost:'Потеряно',destroyed:'Уничтожено',person:'Человек',service:'Служба',shared:'Общий',
 gregorian:'Григорианский календарь',custom:'Особый календарь',none:'Отсутствует',phone:'Телефон',message:'Сообщение',video:'Видео',radio:'Радио',other:'Другое',TEXT_MESSAGE:'Сообщение',VOICE_CALL:'Звонок',medical:'Медицинская помощь',police:'Полиция',fire:'Пожарная служба',night:'Ночь',morning:'Утро',afternoon:'День',evening:'Вечер',
 can_become_pregnant:'Может забеременеть',can_impregnate:'Может стать биологическим отцом',neither:'Не обладает указанными возможностями',due:'Ожидается рождение',born:'Рождение состоялось',proposed:'Предложено',agreed:'Согласовано',replaced:'Заменено',protected:'С защитой',unprotected:'Без защиты',behavior:'Поведение',experience:'Опыт',turning_point:'Поворотное событие',intrinsic:'Врождённое',body:'Тело',modification:'Изменение',presentation:'Внешний образ',condition:'Состояние',
 eye_color:'Цвет глаз',natural_hair_color:'Природный цвет волос',skin:'Кожа',face:'Лицо',build:'Телосложение',height:'Рост',scar:'Шрам',tattoo:'Татуировка',piercing:'Пирсинг',hairstyle:'Причёска',facial_hair:'Растительность на лице',cosmetic:'Косметика',fulfilled:'Выполнено',missed:'Пропущено',dependency_cancelled:'Отменено вслед за зависимостью',profession:'Профессия',occupation:'Занятие',study:'Учёба',parent_organization:'Материнская организация',
};
const technical=new Set(['id','revision','source_turn','source_turn_id','reviewed_signature','provenance','field_facts','remote_source_ids','source_ids','seen_sources','applied','source_sequence','emotion_source_sequence']);
const characterRefs=new Set(['source_id','target_id','actor_id','owner_id','holder_id','character_id','character_ids','visible_to_ids','participants','witnesses','sender_id','recipient_ids','mother_id','father_id','child_id','child_ids','protagonist_id','controlled_actor_id','parent_ids','decision_actor_ids','gestational_actor_id','impregnating_actor_id','delegated_to']);
export function resolver(state:DisplayState) {
 const world=state.world;
 const entries=(key:string)=>Object.entries((world[key] || {}) as Record<string,RecordValue>).map(([id,item])=>({id,...item}));
 const find=(id:unknown,list:RecordValue[])=>list.find(r=>r.id===id);
 return (field:string,id:unknown):string|null=>{
  if(id==null || id==='')return null;
  let item:RecordValue|undefined;let type='запись';
  if(characterRefs.has(field)){item=find(id,state.characters);type='персонаж';}
  else if(['location','location_id','location_ids','parent_id'].includes(field)){item=find(id,state.locations);type='место'; if(!item && field==='location' && typeof id==='string' && !id.startsWith('loc_'))return id;}
  else {const group=field==='organization_id'?'organizations':field.includes('fact')?'facts':field==='scene_id'?'scenes':field==='contact_id'?'contacts':field==='conversation_id'?'conversations':field==='condition_id'?'conditions':field==='pregnancy_id'?'pregnancies':field==='depends_on'?'scheduled_events':field.includes('event_id')?'events':null;
   if(!group){
    if(field==='subject_id' || field.endsWith('_id') || field.endsWith('_ids') || field==='replaces'){
     const matches=[...state.characters,...state.locations,...['organizations','roles','residences','contacts','pregnancies','naming_decisions','reproductive_events','conditions','possessions','facts','knowledge','relationships','objective_relations','threads','events','scenes','scheduled_events','conversations'].flatMap(entries)].filter(r=>r.id===id);
     if(matches.length===1)return String((matches[0] as RecordValue).name || (matches[0] as RecordValue).title || (matches[0] as RecordValue).text || 'Связанная запись');
     return 'Неизвестная запись (ссылка не найдена или неоднозначна)';
    }
    return null;
   }
   item=find(id,entries(group));}
  return item ? String(item.name || item.label || item.title || item.text || item.description || 'Запись без названия') : `Неизвестный ${type} (ссылка не найдена)`;
 };
}
export function recordTitle(section:string,item:RecordValue,resolve:ReturnType<typeof resolver>,author=true):string {
 const ref=(field:string)=>resolve(field,item[field]) || 'Неизвестно';
 if(section==='objective_relations')return `${ref('source_id')} ${['spouse','partner','engaged','sibling','contact','friend','close_friend','coworker'].includes(String(item.kind))?'↔':'→'} ${ref('target_id')} · ${enumLabels[String(item.kind)] || String(item.kind)}`;
 if(section==='residences')return `${ref('actor_id')} → ${ref('location_id')}`;
 if(section==='roles')return `${ref('actor_id')} · ${item.title || 'Роль'}${item.organization_id?' · '+ref('organization_id'):''}`;
 if(section==='contacts')return `${ref('owner_id')} · ${item.label || 'Контакт'}${item.character_id && (author || item.identity_visible)?' · '+ref('character_id'):''}`;
 if(section==='pregnancies')return `${ref('gestational_actor_id')} · беременность`;
 if(section==='reproductive_events')return `${ref('gestational_actor_id')} и ${ref('impregnating_actor_id')} · событие предыстории`;
 if(section==='naming_decisions')return `Выбор имени · ${item.display_name || (item.components as RecordValue)?.given_name || 'Имя не определено'}`;
 if(section==='knowledge')return `${ref('actor_id')} · ${ref('fact_id')}`;
 return String(item.name || item.title || item.description || item.text || (item.actor_id?ref('actor_id'):'Запись'));
}
export function RuntimeValue({field,value,resolve,author=false}:{field:string;value:unknown;resolve:ReturnType<typeof resolver>;author?:boolean}):ReactNode {
 if(value===null || value===undefined)return <span className="workshop-hint">Неизвестно</span>;
 if(typeof value==='boolean')return <span>{value?'Да':'Нет'}</span>;
 if(Array.isArray(value))return value.length?<ul>{value.map((v,i)=><li key={i}><RuntimeValue field={field} value={v} resolve={resolve} author={author}/></li>)}</ul>:<span className="workshop-hint">Нет записей</span>;
 if(typeof value==='object') {
  const entries=Object.entries(value as RecordValue);
  if(['items','values','sex_fact_ids','characters','locations','organizations','roles','residences','contacts','pregnancies','naming_decisions','reproductive_events','conditions','possessions','facts','knowledge','relationships','objective_relations','threads','events','scenes','scheduled_events'].includes(field))return <div className="runtime-value">{entries.length?entries.map(([id,v],i)=><section key={id}><h5>{v && typeof v==='object'?recordTitle(field,v as RecordValue,resolve,author):`Элемент ${i+1}`}</h5><RuntimeValue field={field==='sex_fact_ids'?'fact_id':'record'} value={v} resolve={resolve} author={author}/>{author && <details><summary>Технические сведения</summary><code>{id}</code></details>}</section>):<span className="workshop-hint">Нет записей</span>}</div>;
  const main=entries.filter(([k])=>!technical.has(k));const meta=entries.filter(([k])=>technical.has(k));
  return <div className="runtime-value">{main.length?<dl>{main.map(([k,v])=><div key={k}><dt>{runtimeLabels[k] || k}</dt><dd><RuntimeValue field={k} value={v} resolve={resolve} author={author}/></dd></div>)}</dl>:<span className="workshop-hint">Нет сведений</span>}{author && meta.length>0 && <details><summary>Технические сведения</summary><pre>{JSON.stringify(Object.fromEntries(meta),null,2)}</pre></details>}</div>;
 }
 if(typeof value==='number')return <span>{String(value)}</span>;
 return <span>{resolve(field,value) || (['status','kind','life_status','developmental_stage','reproductive_capability','biological_sex','sex','system','visibility','duration','category','outcome','channel','presentation','day_period','protection','stage','field','predicate','type'].includes(field)?enumLabels[String(value)] || runtimeLabels[String(value)] || String(value):String(value)) || 'Не указано'}</span>;
}
