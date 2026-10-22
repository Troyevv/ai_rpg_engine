import {Textarea} from './components/ui/textarea';
export const defaultCreation={primary_genre:null as string|null,secondary_genres:[] as string[],custom_genre:'',npc_expressiveness:'expressive',cast_preset:'medium',core_npcs:6,secondary_npcs:12,world_type:'unspecified',geography:'',narrative_pacing:{preset:'moderate'},narrative_risk:{preset:'realistic'}};
export type Creation=typeof defaultCreation;
const genres:Record<string,string>={slice_of_life:'Повседневность',family_saga:'Семейная сага',romance:'Романтика',drama:'Драма',detective:'Детектив',thriller:'Триллер',science_fiction:'Научная фантастика',fantasy:'Фэнтези',horror:'Ужасы',adventure:'Приключения',post_apocalyptic:'Постапокалипсис',historical:'Исторический',custom:'Свой жанр'};
const descriptions:Record<string,string>={
 slice_of_life:'Повседневные занятия, отношения и небольшие перемены в жизни.',
 family_saga:'История семьи на протяжении лет и поколений. Будущие браки, дети и переходы героя заранее не определены.',
 romance:'Сближение и личные отношения, когда они согласуются с желаниями персонажей и вашим замыслом.',
 drama:'Внутренние противоречия и сложные отношения без обязательной трагедии.',
 detective:'Наблюдения, улики и поиск объяснений. Преступление не обязательно.',
 thriller:'Ожидание, неопределённость и напряжение без предрешённого насилия.',
 science_fiction:'Научные идеи, технологии и их влияние на жизнь общества.',
 fantasy:'Необычный мир и возможное волшебство в пределах заданных правил.',
 horror:'Неизвестность и тревожная атмосфера. Не задаёт уровень риска или обязательные травмы.',
 adventure:'Открытия, путешествия и новые обстоятельства без обязательного героического подвига.',
 post_apocalyptic:'Жизнь после крупных перемен мира; причины и последствия определяет ваш замысел.',
 historical:'Жизнь в выбранной эпохе. Страна, даты и биографии не выводятся из названия жанра.',
 custom:'Направление задаётся вашим описанием ниже.'};
const expressions:Record<string,string>={
 realistic:'Сдержанная естественная подача. Например: NPC на миг отводит взгляд и тихо благодарит.',
 expressive:'Живые, правдоподобные реакции. Например: NPC улыбается, оживлённо благодарит и уточняет детали.',
 hyperbolized:'Театральная или комедийная подача, если она подходит персонажу. Например: NPC драматично хватается за сердце от приятного удивления.'};
export function WorldCreationSettings({value,onChange,disabled=false}:{value:Creation;onChange:(value:Creation)=>void;disabled?:boolean}){
 const counts=value.cast_preset==='custom'?[value.core_npcs,value.secondary_npcs]:value.cast_preset==='small'?[3,5]:value.cast_preset==='large'?[10,25]:[6,12];
 const change=(patch:Partial<Creation>)=>onChange({...value,...patch});
 return <details className="workshop-detail"><summary>Настройки генератора</summary><fieldset disabled={disabled}>
 <p>Настройки заполняют пробелы замысла. Заданные персонажи сохраняются независимо от размера мира.</p>
 <label>Основной жанр<select aria-label="Основной жанр" value={value.primary_genre||''} onChange={e=>change({primary_genre:e.target.value||null,secondary_genres:value.secondary_genres.filter(g=>g!==e.target.value)})}><option value="">Из описания мира</option>{Object.entries(genres).map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
 {value.primary_genre&&<p aria-label="Описание основного жанра">{descriptions[value.primary_genre]}</p>}
 <fieldset><legend>Дополнительные жанры · до трёх</legend>{Object.entries(genres).map(([id,name])=><label key={id}><input type="checkbox" checked={value.secondary_genres.includes(id)} disabled={disabled||id===value.primary_genre||value.secondary_genres.length>=3&&!value.secondary_genres.includes(id)} onChange={e=>change({secondary_genres:e.target.checked?[...value.secondary_genres,id]:value.secondary_genres.filter(g=>g!==id)})}/>{name}</label>)}</fieldset>
 {value.secondary_genres.map(id=><p key={id} aria-label={'Описание жанра '+genres[id]}><strong>{genres[id]}: </strong>{descriptions[id]}</p>)}
 {[value.primary_genre,...value.secondary_genres].includes('custom')&&<label>Описание своего жанра<Textarea value={value.custom_genre} maxLength={2000} onChange={e=>change({custom_genre:e.target.value})}/></label>}
 <label>Выразительность NPC<select aria-label="Выразительность NPC" value={value.npc_expressiveness} onChange={e=>change({npc_expressiveness:e.target.value})}><option value="realistic">Реалистичная</option><option value="expressive">Выразительная</option><option value="hyperbolized">Гиперболизированная</option></select></label><p aria-label="Пример выразительности">{expressions[value.npc_expressiveness]}</p><p>Меняет речь, жесты и эмоциональную подачу, сохраняя характер, знания и самостоятельность NPC.</p>
 <label>Масштаб состава<select aria-label="Масштаб состава" value={value.cast_preset} onChange={e=>change({cast_preset:e.target.value})}><option value="small">Камерный · 3 важных и 5 второстепенных NPC</option><option value="medium">Средний · 6 и 12 NPC</option><option value="large">Большой · 10 и 25 NPC</option><option value="custom">Настроить количество</option></select></label>
 <p aria-label="Целевой состав мира">Важных NPC: {counts[0]}, второстепенных: {counts[1]}, всего: {counts[0]+counts[1]}. Это ориентир, а не обязательное заполнение. Указанные вами NPC входят в эти числа; будущие персонажи игры ими не ограничены.</p>
 {value.cast_preset==='custom'&&<><label>Важные NPC<input type="number" min={1} max={15} value={value.core_npcs} onChange={e=>change({core_npcs:Number(e.target.value)})}/></label><label>Второстепенные NPC<input type="number" min={0} max={40} value={value.secondary_npcs} onChange={e=>change({secondary_npcs:Number(e.target.value)})}/></label></>}
 <label>Тип мира<select aria-label="Тип мира" value={value.world_type} onChange={e=>change({world_type:e.target.value})}><option value="unspecified">Из описания</option><option value="real_world">Реальный мир</option><option value="fictional">Вымышленный мир</option><option value="alternate">Альтернативная реальность</option></select></label>
 <label>География<Textarea value={value.geography} maxLength={5000} placeholder="Страна, город, районы, расстояния и важные места" onChange={e=>change({geography:e.target.value})}/></label>
 <label>Темп истории<select aria-label="Темп истории" value={value.narrative_pacing.preset} onChange={e=>change({narrative_pacing:{preset:e.target.value}})}>{Object.entries({calm:'Спокойный',moderate:'Умеренный',dynamic:'Динамичный',intense:'Интенсивный'}).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
 <label>Риск последствий<select aria-label="Риск последствий" value={value.narrative_risk.preset} onChange={e=>change({narrative_risk:{preset:e.target.value}})}>{Object.entries({safe:'Безопасный',realistic:'Реалистичный',harsh:'Суровый',unrestricted:'Без ограничений'}).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label><p>Темп и риск задают правила будущей игры. Они не создают события предыстории.</p>
 </fieldset></details>;
}
