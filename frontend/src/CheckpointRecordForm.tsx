import {useState} from 'react';
import {Button} from './components/ui/button';
import {Textarea} from './components/ui/textarea';
import {socialLabel} from './lib/social';
export type Schema={readOnly?:boolean;$ref?:string;type?:string;properties?:Record<string,Schema>;additionalProperties?:Schema|boolean;items?:Schema;anyOf?:Schema[];enum?:unknown[];default?:unknown;minimum?:number;maximum?:number;maxLength?:number;$defs?:Record<string,Schema>};
export type Reference={id:string;name:string};
const labels:Record<string,string>={holder_id:'Кто знает',related_id:'Связанная сущность',section:'Раздел',subject_id:'О ком',stage:'Этап',path:'Путь поля',operator:'Условие',expected:'Ожидаемое значение',where:'Отбор записей',select:'Сравниваемое поле',physical_state:'Физическое состояние',emotion:'Эмоциональное состояние',name:'Название',display_name:'Имя',text:'Описание',description:'Описание',public_description:'Описание для игрока',kind:'Тип',status:'Состояние',source_id:'От кого',target_id:'К кому',actor_id:'Персонаж',character_id:'Персонаж',location_id:'Локация',organization_id:'Организация',parent_id:'Родительская локация',fact_id:'Факт',visibility:'Доступность',evidence:'Основание',certainty:'Уверенность',since:'Начало',until:'Окончание',start_minute:'Начальная минута',end_minute:'Конечная минута',due_minute:'Назначенная минута',world_time:'Время мира',situation:'Текущая ситуация',controlled_actor_id:'Управляемый герой',pov_actor_id:'Точка зрения',present_character_ids:'Участники сцены',character_ids:'Связанные персонажи',biological_sex:'Биологический пол',birth_date:'Дата рождения',life_status:'Жизненное состояние',personality:'Личность',items:'Черты',field:'Категория',goals:'Цели',intentions:'Намерения',obligations:'Обязательства',values:'Ценности',aliases:'Другие названия',title:'Название',setting:'Сеттинг',era:'Эпоха',genre:'Жанр',tone:'Тон',rules:'Правила',holder_ids:'Кто знает',related_ids:'Связанные сущности',time_scope:'Когда',classification:'Статус ограничения',blocking:'Требует решения',value:'Значение'};
function resolved(schema:Schema|undefined,root:Schema):Schema{
 if(!schema)return {};
 if(schema.$ref)return resolved(root.$defs?.[schema.$ref.split('/').at(-1)||''],root);
 if(schema.anyOf)return resolved(schema.anyOf.find(s=>s.type!=='null'),root);
 return schema;
}
export function schemaAt(root:Schema,path:string):Schema{
 let schema=root;
 for(const part of path.split('/').slice(1)){
  const node=resolved(schema,root);const key=part.replaceAll('~1','/').replaceAll('~0','~');
  schema=node.properties?.[key]||node.items||(typeof node.additionalProperties==='object'?node.additionalProperties:{});
 }
 return schema;
}
function empty(schema:Schema,root:Schema,activate=false):unknown{
 if(!activate&&(schema.default===null||schema.anyOf?.some(part=>part.type==='null')))return null;
 const s=resolved(schema,root);
 if(s.default!==undefined&&s.default!==null)return structuredClone(s.default);
 if(s.enum)return s.enum[0];
 if(s.type==='array')return [];
 if(s.type==='object'||s.properties)return Object.fromEntries(Object.entries(s.properties||{}).map(([k,v])=>[k,k==='id'?crypto.randomUUID():empty(v,root)]));
 if(s.type==='boolean')return false;
 if(s.type==='number'||s.type==='integer')return s.minimum??0;
 return '';
}
export function CheckpointRecordForm({value,onChange,schema={},root=schema,references=[],name='Запись',disabled=false}:{value:unknown;onChange:(value:unknown)=>void;schema?:Schema;root?:Schema;references?:Reference[];name?:string;disabled?:boolean}){
 const [error,setError]=useState('');
 const s=resolved(schema,root),label=labels[name]||references.find(r=>r.id===name)?.name||name;
 const child=(item:unknown,key:string,childSchema:Schema,change:(value:unknown)=>void)=><CheckpointRecordForm key={key} name={key} value={item} schema={childSchema} root={root} references={references} onChange={change} disabled={disabled||Boolean(childSchema.readOnly)}/>;
 if(value!==null&&schema.anyOf?.some(part=>part.type==='null'))return <fieldset disabled={disabled}><legend>{label}</legend>{child(value,name,s,onChange)}<Button type="button" variant="ghost" onClick={()=>onChange(null)}>Не указывать {label.toLowerCase()}</Button></fieldset>;
 if(value===null)return <div><span>{label}: не указано</span> <Button type="button" variant="outline" disabled={disabled} onClick={()=>onChange(empty(schema,root,true))}>Задать {label.toLowerCase()}</Button></div>;
 if(Array.isArray(value))return <fieldset disabled={disabled}><legend>{label}</legend>{value.map((v,i)=><div key={i}>{child(v,name.endsWith('_ids')?name.slice(0,-1):String(i+1),s.items||{},next=>onChange(value.map((old,j)=>j===i?next:old)))}<Button type="button" variant="ghost" onClick={()=>onChange(value.filter((_,j)=>j!==i))}>Удалить элемент {i+1}</Button></div>)}<Button type="button" variant="outline" onClick={()=>onChange([...value,empty(s.items||{},root)])}>Добавить элемент</Button></fieldset>;
 if(typeof value==='object'){
  const record=value as Record<string,unknown>;
  const update=(key:string,next:unknown)=>{
   const itemSchema=resolved(typeof s.additionalProperties==='object'?s.additionalProperties:undefined,root);
   // Knowledge uses the canonical actor:fact key, not a new identity.
   const row=next as Record<string,unknown>|null;
   const nextKey=itemSchema.properties?.actor_id&&itemSchema.properties?.fact_id&&!itemSchema.properties?.id&&row?.actor_id&&row?.fact_id?`${row.actor_id}:${row.fact_id}`:key;
   if(nextKey!==key&&Object.hasOwn(record,nextKey)){setError('Запись для этого персонажа и факта уже существует');return}
   setError('');onChange({...Object.fromEntries(Object.entries(record).filter(([k])=>k!==key)),[nextKey]:next});
  };
  const itemSchema=resolved(typeof s.additionalProperties==='object'?s.additionalProperties:undefined,root);
  const editableKey=typeof s.additionalProperties==='object'&&!itemSchema.properties?.id&&!(itemSchema.properties?.actor_id&&itemSchema.properties?.fact_id);
  const rename=(key:string,next:string)=>{
   if(next===key)return;
   if(!next.trim()||Object.hasOwn(record,next)){setError('Ключ записи должен быть непустым и уникальным');return}
   setError('');onChange({...Object.fromEntries(Object.entries(record).filter(([k])=>k!==key)),[next]:record[key]});
  };
  return <fieldset disabled={disabled}><legend>{label}</legend>{Object.entries(record).map(([key,v])=>['id','existing_id','key','spans','revision'].includes(key)?null:<div key={key}>{editableKey&&<label>Ключ записи{name==='parent_organizations'?<select aria-label="Дочерняя организация" value={key} onChange={e=>rename(key,e.target.value)}><option value={key}>{references.find(r=>r.id===key)?.name||'Выберите организацию'}</option>{references.filter(r=>r.id!==key).map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select>:<input aria-label="Ключ записи" defaultValue={key} onBlur={e=>rename(key,e.target.value)}/>}</label>}{child(v,key,s.properties?.[key]||(typeof s.additionalProperties==='object'?s.additionalProperties:{}),next=>update(key,next))}{typeof s.additionalProperties==='object'&&<Button type="button" variant="ghost" onClick={()=>onChange(Object.fromEntries(Object.entries(record).filter(([k])=>k!==key)))}>Удалить запись</Button>}</div>)}
  {typeof s.additionalProperties==='object'&&<Button type="button" variant="outline" onClick={()=>{const next=empty(s.additionalProperties as Schema,root);const key=next&&typeof next==='object'&&!Array.isArray(next)&&'id' in next?String(next.id):crypto.randomUUID();onChange({...record,[key]:next})}}>Добавить запись</Button>}
  {error&&<p role="alert">{error}</p>}</fieldset>;
 }
 if(typeof value==='boolean')return <label><input type="checkbox" checked={value} disabled={disabled} onChange={e=>onChange(e.target.checked)}/>{label}</label>;
 const refs=name.endsWith('_id')?references:[];
 if(s.enum||refs.length)return <label>{label}<select aria-label={label} value={String(value)} disabled={disabled} onChange={e=>onChange(e.target.value===''&&schema.anyOf?.some(v=>v.type==='null')?null:e.target.value)}>{!s.enum&&<option value="">Не указано</option>}{s.enum?s.enum.map(v=><option key={String(v)} value={String(v)}>{socialLabel(String(v))==='Связь'?({explicit:'Задано пользователем',inferred:'Вывод из контекста',open:'Можно дополнить',prohibition:'Запрет',ambiguity:'Требует уточнения',equals:'Равно',contains:'Содержит запись',absent:'Не содержит запись',only:'Точный состав',setting:'Мир',places:'Места и организации',characters:'Персонажи',life:'Связи и обстоятельства',lore:'Факты и знания',opening:'Начальная сцена',alive:'Жив',dead:'Умер',missing:'Пропал',unknown:'Неизвестно',female:'Женский',male:'Мужской',public:'Открыто',secret:'Секрет',known:'Знает',suspected:'Предполагает',active:'Действует',blocked:'Заблокировано',completed:'Завершено'} as Record<string,string>)[String(v)]||String(v):socialLabel(String(v))}</option>):<>{!refs.some(r=>r.id===value)&&value!==''&&<option value={String(value)}>{String(value)}</option>}{refs.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</>}</select></label>;
 if(typeof value==='number')return <label>{label}<input type="number" value={value} disabled={disabled} min={s.minimum} max={s.maximum} onChange={e=>onChange(Number(e.target.value))}/></label>;
 return <label>{label}<Textarea aria-label={label} value={String(value)} disabled={disabled} maxLength={s.maxLength} onChange={e=>onChange(e.target.value)}/></label>;
}
