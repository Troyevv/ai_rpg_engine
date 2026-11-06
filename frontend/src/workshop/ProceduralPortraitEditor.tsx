import {useState,useId,type ReactNode} from 'react';
import {type ProceduralPortrait} from './proceduralPortrait';
import {bodyFrames,facialHairStyles,type BodyFrame,type FacialHair} from './portraitAnatomy';
export type AnatomyReference = {body_frame:BodyFrame;facial_hair_allowed:boolean};
import {Button} from '../components/ui/button';
const choices = {face:['Овальное','Узкое','Угловатое','Широкое','Вытянутое','Округлое','Мягкое'],hair:['Короткие','Длинные','Каре','Кудрявые','Средние','Волнистые','Чёлка','Без волос'],skin:['Светлая','Тёплая','Бежевая','Смуглая','Оливковая','Персиковая','Песочная'],eyes:['Ореховые','Зелёные','Серые','Карие','Серо-зелёные','Голубые','Светло-зелёные','Серо-голубые'],clothing:['Нейтральная туника','Футболка','Рубашка','Жакет','Куртка','Кардиган','Джемпер','Свитер'],accessory:['Без аксессуаров','Цепочка','Серьги и подвеска','Длинные серьги','Без украшений','Кулон','Без украшений','Подвеска'],palette:['Графит','Шалфей','Терракота','Охра','Лён','Сланец','Песок']};
const ageLabels={infant:'Младенец',child:'Ребёнок',adolescent:'Подросток',young_adult:'Молодой взрослый',mature_adult:'Зрелый взрослый',elderly:'Пожилой'};
const colors={hair_color:['Чёрные','Каштановые','Светлые','Тёмно-русые','Рыжие','Седые','Белые'],clothing_color:['Тёмный','Светлый','Синий','Зелёный','Коричневый','Красный','Песочный']};
export function ProceduralPortraitEditor({descriptor,appearance,ageReference,anatomyReference,mode,disabled,onSave,renderPreview}:{renderPreview:(p:ProceduralPortrait)=>ReactNode;appearance?:string;anatomyReference?:AnatomyReference;ageReference?:{age?:number|null;stage:string;visual_age?:ProceduralPortrait['visual_age']|null};descriptor:ProceduralPortrait;mode:'auto'|'procedural';disabled:boolean;onSave:(p:ProceduralPortrait,mode:'auto'|'procedural')=>Promise<void>}) {
 const [open,setOpen]=useState(false);const panelId=useId();
 const [status,setStatus]=useState('');const [compare,setCompare]=useState(false);
 const [value,setValue]=useState(descriptor);const [selected,setSelected]=useState(mode);
 const ageSelection=value.visual_age_mode==='auto'?'auto':value.visual_age_mode==='manual'?value.visual_age:value.visual_age&&value.visual_age===ageReference?.visual_age?'auto':value.visual_age||'legacy';
 const adultArt=(p:ProceduralPortrait)=>['young_adult','mature_adult','elderly','adult'].includes(p.visual_age || p.stage);
 const selectAge=(choice:string)=>{
  setCompare(true);
  const next:ProceduralPortrait=choice==='auto'
   ? {...value,visual_age_mode:'auto',visual_age:ageReference?.visual_age||undefined,stage:ageReference?.stage||value.stage}
   : {...value,visual_age_mode:'manual',visual_age:choice as NonNullable<ProceduralPortrait['visual_age']>};
  if(next.version===2 && !adultArt(next))next.facial_hair='clean_shaven';
  setValue(next);
 };
 const setAnatomy=(change:{body_frame?:BodyFrame;facial_hair?:FacialHair})=>{
  setValue({...value,version:2,
   body_frame:value.version===2?value.body_frame:anatomyReference?.body_frame||'neutral',
   facial_hair:value.version===2?value.facial_hair:'clean_shaven',...change});
 };
 const dirty=JSON.stringify(value)!==JSON.stringify(descriptor)||selected!==mode;
 return <section className="procedural-editor"><button type="button" aria-expanded={open} aria-controls={panelId} onClick={()=>setOpen(!open)}>Настроить иллюстрацию</button><div id={panelId} hidden={!open}><p>При создании мира иллюстрация может учитывать заданные черты. Неописанные детали получают условный вариант. Редактирование текста не меняет сохранённый портрет.</p>
 <p>Иллюстрация условная: родинки, часы и медицинская форма не поддерживаются. Они остаются в литературном описании.</p>
 <button type="button" aria-pressed={compare} onClick={()=>setCompare(!compare)}>Свериться с описанием внешности</button>
 {compare&&<p>Сравните варианты с текстом и выберите поддерживаемые признаки ниже. Автоматическое распознавание текста здесь не выполняется. Изменения сохраняются только по подтверждению.</p>}
 <div className="portrait-age-reference">
 <p>Реальный возраст персонажа: {ageReference?.age!=null?new Intl.NumberFormat('ru',{style:'unit',unit:'year',unitDisplay:'long'}).format(ageReference.age):'не указан'}{ageReference?.visual_age?` · ${ageLabels[ageReference.visual_age]}`:''}.</p>
 <label>Визуальный возраст<select aria-label="Визуальный возраст" disabled={disabled} value={ageSelection} onChange={e=>selectAge(e.target.value)}>
 <option value="auto" disabled={!ageReference?.visual_age}>Автоматически — по текущему возрасту персонажа</option>
 {ageSelection==='legacy'&&<option value="legacy" disabled>Сохранённый исходный стиль</option>}
 {Object.entries(ageLabels).map(([key,label])=><option key={key} value={key}>{label}</option>)}
 </select></label>
 <p>Возраст на иллюстрации: {value.visual_age?ageLabels[value.visual_age]:'исходный стиль'}. {ageSelection==='auto'?'Категория определяется возрастом персонажа при сохранении.':'Художественный выбор автора.'} Дата рождения и жизненный цикл не меняются. Сохранённый рисунок не меняется сам при дне рождения.</p>
 <Button variant="ghost" disabled={disabled||!ageReference?.visual_age} onClick={()=>selectAge('auto')}>Вернуть возраст по персонажу</Button>
 </div>
 <div className="procedural-editor-grid"><div className="portrait-comparison">
 {compare&&<figure><figcaption>Сохранённый вариант</figcaption>{renderPreview(descriptor)}</figure>}
 <figure><figcaption>{dirty?'Предлагаемый вариант':'Текущий вариант'}</figcaption>{renderPreview(value)}</figure>
 <div className="portrait-literary-reference"><strong>Внешность</strong><p>{appearance||'Описание не задано. Неописанные признаки определяются по seed.'}</p></div>
 </div><div>
 <label>Предпочтение<select aria-label="Предпочтение" value={selected} onChange={e=>setSelected(e.target.value as typeof selected)}><option value="auto">Своя фотография, если применима</option><option value="procedural">Процедурная иллюстрация</option></select></label>
 <label>Вид изображения<select aria-label="Вид изображения" value={value.form} onChange={e=>{const form=e.target.value as ProceduralPortrait['form'];setValue(value.version===2&&form==='neutral'?{...value,form,facial_hair:'clean_shaven'}:{...value,form});setSelected('procedural')}}><option value="neutral">Нейтральный силуэт</option><option value="human">Человек · художественная условность</option></select></label>
 {value.form==='human'&&<fieldset className="portrait-anatomy"><legend>Силуэт и лицо</legend>
 <label>Основа тела<select disabled={disabled} value={value.version===2?value.body_frame:''} onChange={e=>setAnatomy({body_frame:e.target.value as BodyFrame})}>
 {value.version===1&&<option value="" disabled>Исходная иллюстрация</option>}
 {Object.entries(bodyFrames).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
 {anatomyReference?.facial_hair_allowed&&adultArt(value)&&<label>Растительность на лице<select disabled={disabled} value={value.version===2?value.facial_hair:''} onChange={e=>setAnatomy({facial_hair:e.target.value as FacialHair})}>
 {value.version===1&&<option value="" disabled>Исходная иллюстрация</option>}
 {Object.entries(facialHairStyles).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>}
 </fieldset>}
 {value.form==='human'&&Object.entries(choices).map(([key,labels])=><label key={key}>{{face:'Форма лица',hair:'Волосы',skin:'Тон кожи',eyes:'Глаза',clothing:'Одежда',accessory:'Аксессуары',palette:'Палитра'}[key]}<select aria-label={{face:'Форма лица',hair:'Волосы',skin:'Тон кожи',eyes:'Глаза',clothing:'Одежда',accessory:'Аксессуары',palette:'Палитра'}[key]} value={value[key as keyof typeof choices]} onChange={e=>setValue({...value,[key]:Number(e.target.value)})}>{labels.map((label,i)=><option key={i} value={i}>{label}</option>)}</select></label>)}
 {value.form==='human'&&(Object.keys(colors) as (keyof typeof colors)[]).map(key=><label key={key}>{key==='hair_color'?'Цвет волос':'Цвет одежды'}<select value={value[key]??''} onChange={e=>{const next={...value};if(e.target.value==='')delete next[key];else next[key]=Number(e.target.value);setValue(next)}}><option value="">Как в исходном рисунке</option>{colors[key].map((name,i)=><option key={name} value={i}>{name}</option>)}</select></label>)}
 </div></div><div className="portrait-actions"><p role="status">{disabled?'Сохранение…':dirty?'Есть несохранённые изменения':status}</p><Button disabled={disabled||!dirty} onClick={async()=>{setStatus('');try{await onSave(value,selected);setStatus('Иллюстрация сохранена')}catch{setStatus('Не удалось сохранить. Ваши настройки оставлены в редакторе.')}}}>Сохранить иллюстрацию</Button><Button variant="ghost" disabled={disabled} onClick={()=>{setValue(descriptor);setSelected(mode)}}>Отменить настройки</Button></div></div></section>;
}
