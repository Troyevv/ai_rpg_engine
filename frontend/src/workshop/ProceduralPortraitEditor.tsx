import {useRef,useState,type ReactNode} from 'react';
import {Check,RotateCcw} from 'lucide-react';
import {IllustrationControls} from './portraitV4/IllustrationControls';
import {Choice} from '../components/ui/choice';
import {Button} from '../components/ui/button';
import catalog from '../../../shared/portrait-catalog.json';
import {proceduralPortrait,type ProceduralPortrait,type Layers} from './proceduralPortrait';
import {figureFeatures,type FeatureChoices} from './portraitFigure';
import {bodyFrames,facialHairStyles,type BodyFrame,type FacialHair} from './portraitAnatomy';
const detailNames={eye_shape:'Разрез глаз',nose_shape:'Форма носа',lip_shape:'Форма губ'};


export type AnatomyReference={body_frame:BodyFrame;facial_hair_allowed:boolean};
type Age=NonNullable<ProceduralPortrait['visual_age']>;
const ages:Record<Age,string>={infant:'Младенец',child:'Ребёнок',adolescent:'Подросток',young_adult:'Молодой взрослый',mature_adult:'Зрелый взрослый',elderly:'Пожилой'};
const categories={hair:'Волосы',clothing:'Одежда',face:'Лицо',color:'Цвета',details:'Образ'};
type Category=keyof typeof categories;
const layers={hair:'hairstyle',clothing:'garment',face:'visage'} as const;
const swatches={
 hair_color:catalog.hair_materials.map(material=>material[0]),
 clothing_color:catalog.cloth_materials.map(material=>material[0]),
 accent_color:catalog.cloth_materials.map(material=>material[0]),
 skin:Object.values(catalog.skin_materials).map(colors=>colors[1]),
 eyes:Object.values(catalog.eye_colors),
};
const swatchLabels={hair_color:'Цвет волос',clothing_color:'Цвет одежды',accent_color:'Цвет отделки',skin:'Тон кожи',eyes:'Цвет глаз'};
const accessories=[[0,'Без украшений'],[1,'Цепочка'],[2,'Серьги и подвеска'],[3,'Длинные серьги'],[5,'Кулон'],[7,'Подвеска']] as const;
const backgrounds=['Графит','Шалфей','Терракота','Охра','Лён','Сланец','Песок'];
type Props={descriptor:ProceduralPortrait;appearance?:string;ageReference?:{stage:string;age?:number|null;visual_age?:Age|null};
 anatomyReference?:AnatomyReference;mode:'auto'|'procedural';disabled:boolean;renderPreview:(p:ProceduralPortrait)=>ReactNode;
 savedPreview?:ReactNode;open:boolean;onOpen:(open:boolean)=>void;onSave:(p:ProceduralPortrait,mode:'auto'|'procedural')=>Promise<void>;
 commission?:(accept:(p:ProceduralPortrait)=>void)=>ReactNode};
export function ProceduralPortraitEditor({descriptor,appearance,ageReference,anatomyReference,mode,disabled,renderPreview,savedPreview,open,onOpen,onSave,commission}:Props){
 const [value,setValue]=useState(descriptor),[selected,setSelected]=useState(mode);
 const [section,setSection]=useState<Category>('hair'),[source,setSource]=useState(''),[error,setError]=useState('');
 const [filter,setFilter]=useState(''),[search,setSearch]=useState('');
 const [colorField,setColorField]=useState<keyof typeof swatches>('hair_color');
 const settings=useRef<HTMLFieldSetElement>(null);
 const reset=()=>{setValue(descriptor);setSelected(mode);setSource('');setError('')};
 const change=(next:ProceduralPortrait)=>{setValue(next);if(next.version!==4)setSelected('procedural');setSource('Ручной выбор');setError('')};
 const modern=():Extract<ProceduralPortrait,{version:3}>=>{if(value.version===4)throw new Error('Недоступно для этого рисунка.');return value.version===3?value:{...value,version:3,base_version:value.version,
    body_frame:value.version===2?value.body_frame:anatomyReference?.body_frame||'neutral',
    facial_hair:value.version===2?value.facial_hair:'clean_shaven'}};
 const withLayer=(group:keyof typeof layers,id:string):ProceduralPortrait=>{
   const art=modern();
   const beyondOriginal=Object.keys(catalog.styles[group]).indexOf(id)>={hair:16,face:7,clothing:15}[group];
   const figure=art.face_revision===3||art.face_revision===4;
   const upgrade=(!figure && (group==='face'||beyondOriginal)) || (group==='face' && beyondOriginal && art.face_revision!==4);
   return {...art,form:'human',[layers[group]]:id,...(upgrade?{face_revision:4,eye_revision:2}:{})};
 };
 const featureEdit=(key:keyof FeatureChoices,id:string)=>{
   const art=modern();
   if(id==='auto'){const next={...art};delete next[key];return next}
   const newer=(figureFeatures[key] as readonly string[]).indexOf(id)>=3;
   return {...art,[key]:id,...(newer?{eye_revision:2 as const}:{}),
     ...(newer&&key!=='eye_shape'?{face_revision:4 as const}:{})};
 };
 const thumbnail=(art:ProceduralPortrait,crop:string)=><span className={'portrait-option-crop '+crop}><img alt="" loading="lazy" src={proceduralPortrait(art)||undefined}/></span>;
 const dirty=JSON.stringify(value)!==JSON.stringify(descriptor)||selected!==mode;
 const ageSelection=value.visual_age_mode==='auto'?'auto':value.visual_age_mode==='manual'?value.visual_age:value.visual_age&&value.visual_age===ageReference?.visual_age?'auto':value.visual_age||'legacy';
 const adult=(p:ProceduralPortrait)=>['adult','young_adult','mature_adult','elderly'].includes(p.visual_age||p.stage);
 const setAge=(id:string)=>{
   const next:ProceduralPortrait=id==='auto'?{...value,visual_age_mode:'auto',visual_age:ageReference?.visual_age||undefined,stage:ageReference?.stage||value.stage}:
      {...value,visual_age_mode:'manual',visual_age:id as Age};
   if(next.version!==1&&next.version!==4&&!adult(next))next.facial_hair='clean_shaven';
   change(next);
 };
 if(!open)return <Button variant="outline" disabled={disabled} onClick={()=>{reset();onOpen(true)}}>Настроить иллюстрацию</Button>;
 return <section className="portrait-studio" aria-label="Настроить иллюстрацию">
 <div className="studio-main"><div className="studio-reference"><div className="portrait-comparison">
 <figure><figcaption>Сохранённый вариант</figcaption>{savedPreview||renderPreview(descriptor)}</figure>
 <figure><figcaption>{source||'Предпросмотр'}</figcaption>{renderPreview(value)}</figure></div>
 {commission?.(p=>{setValue(p);setSelected('procedural');setSource('Предложение модели');setError('')})}
 </div><fieldset ref={settings} disabled={disabled} className="studio-settings">
 {value.version===4?<IllustrationControls value={value} onChange={change} eligible={!!anatomyReference?.facial_hair_allowed} ageReference={ageReference} mode={selected} setMode={setSelected}/>:<>
 <div className="studio-tabs" role="group" aria-label="Раздел настройки">{(Object.keys(categories) as Category[]).map(key=>
  <button type="button" key={key} aria-pressed={section===key} onClick={()=>{setSection(key);setFilter('');setSearch('');settings.current?.scrollTo(0,0)}}>{categories[key]}</button>)}</div>
 {section in layers&&(()=>{const group=section as keyof typeof layers;
 const current=value.version===3 && (group!=='face'||(value.face_revision===3||value.face_revision===4))?value[layers[group] as keyof Layers]:null;
 const groups:Record<string,string[]>=group==='face'?{}:catalog.groups[group];
 const options=Object.entries(catalog.styles[group]).filter(([id,label])=>(!filter||groups[filter]?.includes(id))&&label.toLocaleLowerCase('ru').includes(search.trim().toLocaleLowerCase('ru')));
 return <>{group!=='face'&&<div className="portrait-catalog-filters">
 <input type="search" aria-label={'Поиск · '+categories[group]} placeholder={group==='hair'?'Найти причёску':'Найти одежду'} value={search} onChange={e=>setSearch(e.target.value)}/>
 <div role="group" aria-label="Группа вариантов">{['',...Object.keys(groups)].map(key=><button type="button" key={key} aria-pressed={filter===key} onClick={()=>setFilter(key)}>{key||'Все'}</button>)}</div></div>}
 {!options.length&&<p role="status">Подходящих вариантов нет.</p>}
 <div className="studio-gallery" aria-label={categories[group]}>{options.map(([id,label])=>{
  const art=withLayer(group,id);return <button type="button" key={id} aria-pressed={current===id} onClick={()=>change(art)}>
  <img alt="" loading="lazy" decoding="async" src={proceduralPortrait(art)||undefined}/><span>{label}</span>{current===id&&<Check size={14} aria-hidden="true"/>}</button>
 })}</div></>})()}
 {section==='face'&&<div className="studio-face-details">

 {value.version===3&&(value.face_revision===3||value.face_revision===4)&&!value.eye_revision&&<Button variant="outline" onClick={()=>change({...value,eye_revision:2})}>Примерить новую посадку глаз</Button>}
 {value.version===3&&(value.face_revision===3||value.face_revision===4)?(Object.keys(figureFeatures) as (keyof FeatureChoices)[]).map(key=><label key={key}>{detailNames[key]}
 <Choice aria-label={detailNames[key]} optionPreview={id=>id==='auto'?null:thumbnail(featureEdit(key,id),'feature')} value={value[key]||'auto'} onValueChange={id=>change(featureEdit(key,id))}><option value="auto">По рисунку</option>
 {figureFeatures[key].map(id=><option key={id} value={id}>{(catalog.features[key] as Record<string,string>)[id]}</option>)}</Choice></label>):
 <p>Выберите форму лица, чтобы примерить новый рисунок. Сохранённый портрет виден рядом.</p>}
 </div>}
 {section==='color'&&<>
 <div className="portrait-catalog-filters"><div role="group" aria-label="Материал">{(Object.keys(swatches) as (keyof typeof swatches)[]).map(field=><button type="button" key={field} aria-pressed={colorField===field} onClick={()=>setColorField(field)}>{swatchLabels[field]}</button>)}</div></div>
 <div className="studio-colors" role="group" aria-label={swatchLabels[colorField]}>
 {Object.values(catalog.styles[colorField==='accent_color'?'clothing_color':colorField]).map((label,i)=><button key={label} type="button" title={label} aria-label={label} aria-pressed={modern()[colorField]===i}
 onClick={()=>change({...modern(),form:'human',[colorField]:i,...(colorField==='skin'?{skin_swatch:true}:colorField==='eyes'?{eye_swatch:true}:colorField==='accent_color'&&!(value.version===3&&(value.face_revision===3||value.face_revision===4))?{face_revision:4,eye_revision:2}:{})})}><i style={{backgroundColor:swatches[colorField][i]}}/>{label}</button>)}</div></>}
 {section==='details'&&<>
 {(['body_build','eyewear','face_detail'] as const).map(key=>{
   const label={body_build:'Телосложение',eyewear:'Очки',face_detail:'Особые приметы'}[key];
   const art=modern();
   const illustrated=(id:string)=>({...art,form:'human' as const,[key]:id,
     ...(key==='body_build'||!art.face_revision||art.face_revision===2?{face_revision:4 as const,eye_revision:2 as const}:{})});
   return <label key={key}>{label}<Choice aria-label={label} disabled={disabled} value={art[key]||(key==='body_build'?'average':'none')}
     optionPreview={id=>thumbnail(illustrated(id),key==='body_build'?'body':'feature')}
     onValueChange={id=>change(illustrated(id))}>{Object.entries(catalog.features[key]).map(([id,name])=><option key={id} value={id}>{name}</option>)}</Choice></label>;
 })}
 <label>Вид изображения<Choice aria-label="Вид изображения" disabled={disabled} value={value.form} onValueChange={v=>change({...value,form:v as 'neutral'|'human',...(v==='neutral'&&value.version!==1?{facial_hair:'clean_shaven'}:{})})}><option value="human">Человек</option><option value="neutral">Нейтральный силуэт</option></Choice></label>
 <label>Предпочтение<Choice aria-label="Предпочтение" disabled={disabled} value={selected} onValueChange={v=>setSelected(v as typeof selected)}><option value="auto">Фотография, если подходит</option><option value="procedural">Процедурная иллюстрация</option></Choice></label>
 {value.form==='human'&&<>
 <div className="portrait-age-reference"><p>Возраст персонажа · {ageReference?.age==null?'неизвестен':new Intl.NumberFormat('ru',{style:'unit',unit:'year',unitDisplay:'long'}).format(ageReference.age)}{ageReference?.visual_age?' · '+ages[ageReference.visual_age]:''}</p>
 <label>Визуальный возраст<Choice aria-label="Визуальный возраст" disabled={disabled} value={ageSelection||'legacy'} onValueChange={setAge}><option value="auto" disabled={!ageReference?.visual_age}>По возрасту персонажа</option>{ageSelection==='legacy'&&<option disabled value="legacy">Сохранённый стиль</option>}{Object.entries(ages).map(([k,v])=><option key={k} value={k}>{v}</option>)}</Choice></label>
 <Button variant="ghost" disabled={disabled||!ageReference?.visual_age} onClick={()=>setAge('auto')}>Вернуть возраст по персонажу</Button></div>
 {adult(value)&&<label>Основа тела<Choice aria-label="Основа тела" disabled={disabled} value={value.version===1?'':value.body_frame} onValueChange={v=>change({...modern(),base_version:2,body_frame:v as BodyFrame})}>{value.version===1&&<option disabled value="">Исходная иллюстрация</option>}{Object.entries(bodyFrames).map(([k,v])=><option key={k} value={k}>{v}</option>)}</Choice></label>}
 {anatomyReference?.facial_hair_allowed&&adult(value)&&<label>Растительность на лице<Choice aria-label="Растительность на лице" disabled={disabled} value={value.version===1?'':value.facial_hair} optionPreview={v=>thumbnail({...modern(),facial_hair:v as FacialHair,...(['goatee','sideburns'].includes(v)?{face_revision:4,eye_revision:2}:{})},'feature')}
 onValueChange={v=>change({...modern(),facial_hair:v as FacialHair,...(['goatee','sideburns'].includes(v)?{face_revision:4,eye_revision:2}:{})})}>{value.version===1&&<option disabled value="">Исходная иллюстрация</option>}{Object.entries(facialHairStyles).map(([k,v])=><option value={k} key={k}>{v}</option>)}</Choice></label>}
 <label>Аксессуары<Choice aria-label="Аксессуары" disabled={disabled} value={value.accessory===4||value.accessory===6?0:value.accessory} onValueChange={v=>change({...value,accessory:Number(v)})}>{accessories.map(([k,v])=><option value={k} key={k}>{v}</option>)}</Choice></label>
 <label>Палитра фона<Choice aria-label="Палитра фона" disabled={disabled} value={value.palette} onValueChange={v=>change({...value,palette:Number(v)})}>{backgrounds.map((v,i)=><option value={i} key={v}>{v}</option>)}</Choice></label></>}</>}
 </>}
 <details className="portrait-literary-reference"><summary>Свериться с описанием внешности</summary><p>{appearance||'Внешность пока не описана.'}</p></details>

 </fieldset></div>
 <footer>{descriptor.version===1&&value.version===3&&value.base_version===2&&<p>Новая основа тела также меняет посадку исходной одежды. Сравните варианты перед сохранением.</p>}{error&&<p role="alert">{error}</p>}
 <Button variant="ghost" aria-label="Сбросить несохранённые изменения" title="Сбросить несохранённые изменения" disabled={disabled||!dirty} onClick={reset}><RotateCcw size={16}/></Button>
 <Button variant="outline" disabled={disabled} onClick={()=>{reset();onOpen(false)}}>Отмена</Button>
 <Button disabled={disabled||!dirty} onClick={async()=>{try{await onSave(value,selected)}catch(e){setError(String(e))}}}>{disabled?'Сохранение…':'Сохранить иллюстрацию'}</Button>
 </footer></section>;
}
