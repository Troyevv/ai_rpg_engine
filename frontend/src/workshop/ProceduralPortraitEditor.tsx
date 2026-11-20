import {useRef,useState,type ReactNode} from 'react';
import {Check,RotateCcw} from 'lucide-react';
import {Choice} from '../components/ui/choice';
import {Button} from '../components/ui/button';
import catalog from '../../../shared/portrait-catalog.json';
import {proceduralPortrait,type ProceduralPortrait,type Layers} from './proceduralPortrait';
import {bodyFrames,facialHairStyles,type BodyFrame,type FacialHair} from './portraitAnatomy';

export type AnatomyReference={body_frame:BodyFrame;facial_hair_allowed:boolean};
type Age=NonNullable<ProceduralPortrait['visual_age']>;
const ages:Record<Age,string>={infant:'Младенец',child:'Ребёнок',adolescent:'Подросток',young_adult:'Молодой взрослый',mature_adult:'Зрелый взрослый',elderly:'Пожилой'};
const categories={hair:'Волосы',clothing:'Одежда',face:'Лицо',color:'Цвета',details:'Образ'};
type Category=keyof typeof categories;
const layers={hair:'hairstyle',clothing:'garment',face:'visage'} as const;
const swatches={
 hair_color:['#373437','#795737','#e5ca93','#99876c','#ad6742','#aaa6a0','#f1ead8'],
 clothing_color:['#393b40','#e7e1d7','#637c97','#788673','#876651','#a4665c','#c4b395'],
 skin:Object.values(catalog.skin_materials).map(colors=>colors[1]),
 eyes:Object.values(catalog.eye_colors),
};
const swatchLabels={hair_color:'Цвет волос',clothing_color:'Цвет одежды',skin:'Тон кожи',eyes:'Цвет глаз'};
const accessories=[[0,'Без украшений'],[1,'Цепочка'],[2,'Серьги и подвеска'],[3,'Длинные серьги'],[5,'Кулон'],[7,'Подвеска']] as const;
const backgrounds=['Графит','Шалфей','Терракота','Охра','Лён','Сланец','Песок'];
type Props={descriptor:ProceduralPortrait;appearance?:string;ageReference?:{stage:string;age?:number|null;visual_age?:Age|null};
 anatomyReference?:AnatomyReference;mode:'auto'|'procedural';disabled:boolean;renderPreview:(p:ProceduralPortrait)=>ReactNode;
 savedPreview?:ReactNode;open:boolean;onOpen:(open:boolean)=>void;onSave:(p:ProceduralPortrait,mode:'auto'|'procedural')=>Promise<void>;
 commission?:(accept:(p:ProceduralPortrait)=>void)=>ReactNode};
export function ProceduralPortraitEditor({descriptor,appearance,ageReference,anatomyReference,mode,disabled,renderPreview,savedPreview,open,onOpen,onSave,commission}:Props){
 const [value,setValue]=useState(descriptor),[selected,setSelected]=useState(mode);
 const [section,setSection]=useState<Category>('hair'),[source,setSource]=useState(''),[error,setError]=useState('');
 const settings=useRef<HTMLFieldSetElement>(null);
 const reset=()=>{setValue(descriptor);setSelected(mode);setSource('');setError('')};
 const change=(next:ProceduralPortrait)=>{setValue(next);setSelected('procedural');setSource('Ручной выбор');setError('')};
 const modern=():Extract<ProceduralPortrait,{version:3}>=>value.version===3?value:{...value,version:3,base_version:value.version,
    body_frame:value.version===2?value.body_frame:anatomyReference?.body_frame||'neutral',
    facial_hair:value.version===2?value.facial_hair:'clean_shaven'};
 const withLayer=(group:keyof typeof layers,id:string):ProceduralPortrait=>({...modern(),form:'human',[layers[group]]:id} as ProceduralPortrait);
 const dirty=JSON.stringify(value)!==JSON.stringify(descriptor)||selected!==mode;
 const ageSelection=value.visual_age_mode==='auto'?'auto':value.visual_age_mode==='manual'?value.visual_age:value.visual_age&&value.visual_age===ageReference?.visual_age?'auto':value.visual_age||'legacy';
 const adult=(p:ProceduralPortrait)=>['adult','young_adult','mature_adult','elderly'].includes(p.visual_age||p.stage);
 const setAge=(id:string)=>{
   const next:ProceduralPortrait=id==='auto'?{...value,visual_age_mode:'auto',visual_age:ageReference?.visual_age||undefined,stage:ageReference?.stage||value.stage}:
      {...value,visual_age_mode:'manual',visual_age:id as Age};
   if(next.version!==1&&!adult(next))next.facial_hair='clean_shaven';
   change(next);
 };
 if(!open)return <Button variant="outline" disabled={disabled} onClick={()=>{reset();onOpen(true)}}>Настроить иллюстрацию</Button>;
 return <section className="portrait-studio" aria-label="Настроить иллюстрацию">
 <div className="studio-main"><div className="studio-reference"><div className="portrait-comparison">
 <figure><figcaption>Сохранённый вариант</figcaption>{savedPreview||renderPreview(descriptor)}</figure>
 <figure><figcaption>{source||'Предпросмотр'}</figcaption>{renderPreview(value)}</figure></div>
 {commission?.(p=>{setValue(p);setSelected('procedural');setSource('Предложение модели');setError('')})}
 </div><fieldset ref={settings} disabled={disabled} className="studio-settings">
 <div className="studio-tabs" role="group" aria-label="Раздел настройки">{(Object.keys(categories) as Category[]).map(key=>
  <button type="button" key={key} aria-pressed={section===key} onClick={()=>{setSection(key);settings.current?.scrollTo(0,0)}}>{categories[key]}</button>)}</div>
 {section in layers&&(()=>{const group=section as keyof typeof layers;
 const current=value.version===3?value[layers[group] as keyof Layers]:null;
 return <div className="studio-gallery" aria-label={categories[group]}>{Object.entries(catalog.styles[group]).map(([id,label])=>{
  const art=withLayer(group,id);return <button type="button" key={id} aria-pressed={current===id} onClick={()=>change(art)}>
  <img alt="" loading="lazy" decoding="async" src={proceduralPortrait(art)||undefined}/><span>{label}</span>{current===id&&<Check size={14} aria-hidden="true"/>}</button>
 })}</div>})()}
 {section==='color'&&(Object.keys(swatches) as (keyof typeof swatches)[]).map(field=><div key={field} className="studio-colors" role="group" aria-label={swatchLabels[field]}>
 <h3>{swatchLabels[field]}</h3>{Object.values(catalog.styles[field]).map((label,i)=><button key={label} type="button" title={label} aria-label={label} aria-pressed={value[field]===i}
 onClick={()=>change({...modern(),form:'human',[field]:i,...(field==='skin'?{skin_swatch:true}:field==='eyes'?{eye_swatch:true}:{})})}><i style={{backgroundColor:swatches[field][i]}}/>{label}</button>)}</div>)}
 {section==='details'&&<>
 <label>Вид изображения<Choice aria-label="Вид изображения" disabled={disabled} value={value.form} onValueChange={v=>change({...value,form:v as 'neutral'|'human',...(v==='neutral'&&value.version!==1?{facial_hair:'clean_shaven'}:{})})}><option value="human">Человек</option><option value="neutral">Нейтральный силуэт</option></Choice></label>
 <label>Предпочтение<Choice aria-label="Предпочтение" disabled={disabled} value={selected} onValueChange={v=>setSelected(v as typeof selected)}><option value="auto">Фотография, если подходит</option><option value="procedural">Процедурная иллюстрация</option></Choice></label>
 {value.form==='human'&&<>
 <div className="portrait-age-reference"><p>Возраст персонажа · {ageReference?.age==null?'неизвестен':new Intl.NumberFormat('ru',{style:'unit',unit:'year',unitDisplay:'long'}).format(ageReference.age)}{ageReference?.visual_age?' · '+ages[ageReference.visual_age]:''}</p>
 <label>Визуальный возраст<Choice aria-label="Визуальный возраст" disabled={disabled} value={ageSelection||'legacy'} onValueChange={setAge}><option value="auto" disabled={!ageReference?.visual_age}>По возрасту персонажа</option>{ageSelection==='legacy'&&<option disabled value="legacy">Сохранённый стиль</option>}{Object.entries(ages).map(([k,v])=><option key={k} value={k}>{v}</option>)}</Choice></label>
 <Button variant="ghost" disabled={disabled||!ageReference?.visual_age} onClick={()=>setAge('auto')}>Вернуть возраст по персонажу</Button></div>
 {adult(value)&&<label>Основа тела<Choice aria-label="Основа тела" disabled={disabled} value={value.version===1?'':value.body_frame} onValueChange={v=>change({...modern(),base_version:2,body_frame:v as BodyFrame})}>{value.version===1&&<option disabled value="">Исходная иллюстрация</option>}{Object.entries(bodyFrames).map(([k,v])=><option key={k} value={k}>{v}</option>)}</Choice></label>}
 {anatomyReference?.facial_hair_allowed&&adult(value)&&<label>Растительность на лице<Choice aria-label="Растительность на лице" disabled={disabled} value={value.version===1?'':value.facial_hair} onValueChange={v=>change({...modern(),facial_hair:v as FacialHair})}>{value.version===1&&<option disabled value="">Исходная иллюстрация</option>}{Object.entries(facialHairStyles).map(([k,v])=><option value={k} key={k}>{v}</option>)}</Choice></label>}
 <label>Аксессуары<Choice aria-label="Аксессуары" disabled={disabled} value={value.accessory===4||value.accessory===6?0:value.accessory} onValueChange={v=>change({...value,accessory:Number(v)})}>{accessories.map(([k,v])=><option value={k} key={k}>{v}</option>)}</Choice></label>
 <label>Палитра фона<Choice aria-label="Палитра фона" disabled={disabled} value={value.palette} onValueChange={v=>change({...value,palette:Number(v)})}>{backgrounds.map((v,i)=><option value={i} key={v}>{v}</option>)}</Choice></label></>}</>}
 <details className="portrait-literary-reference"><summary>Свериться с описанием внешности</summary><p>{appearance||'Внешность пока не описана.'}</p></details>

 </fieldset></div>
 <footer>{descriptor.version===1&&value.version===3&&value.base_version===2&&<p>Новая основа тела также меняет посадку исходной одежды. Сравните варианты перед сохранением.</p>}{error&&<p role="alert">{error}</p>}
 <Button variant="ghost" aria-label="Сбросить несохранённые изменения" title="Сбросить несохранённые изменения" disabled={disabled||!dirty} onClick={reset}><RotateCcw size={16}/></Button>
 <Button variant="outline" disabled={disabled} onClick={()=>{reset();onOpen(false)}}>Отмена</Button>
 <Button disabled={disabled||!dirty} onClick={async()=>{try{await onSave(value,selected)}catch(e){setError(String(e))}}}>{disabled?'Сохранение…':'Сохранить иллюстрацию'}</Button>
 </footer></section>;
}
