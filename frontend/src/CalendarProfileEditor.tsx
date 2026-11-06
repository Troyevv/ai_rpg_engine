import {useEffect,useState} from 'react';
import {api} from './api';
import {CalendarPresets,defaultPresets,PresetPreview,type Preview,type Presets} from './CalendarPresets';
import {Button} from './components/ui/button';
type Row={id?:string;name:string;month:number;day:number;character_ids?:string[]};
type Override={id:string;removed?:boolean;name?:string;date?:string};
type Profile={observances?:Row[];seasons?:Row[];regional?:{overrides?:Override[]}|null;[key:string]:unknown};
export function CalendarProfileEditor({wid,revision,profile,selection,disabled,refresh}:{wid:string;revision:number;profile:Profile;selection?:Presets;disabled:boolean;refresh:()=>Promise<unknown>}){
 const [choice,setChoice]=useState(selection||defaultPresets);const [preview,setPreview]=useState<Preview|null>(null);
 const [value,setValue]=useState<Profile>(profile);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 useEffect(()=>{setValue(profile);setChoice(selection||defaultPresets);api<Preview>(`/workspaces/${wid}/draft/calendar-preview`).then(setPreview).catch(e=>setError(e.message));},[wid,revision]);
 const run=async(action:()=>Promise<unknown>)=>{setBusy(true);setError('');try{await action();}catch(e){setError((e as Error).message);}finally{setBusy(false);}};
 const update=(kind:'observances'|'seasons',index:number,p:Partial<Row>)=>setValue({...value,[kind]:(value[kind]||[]).map((r,i)=>i===index?{...r,...p}:r)});
 const override=(id:string,p:Partial<Override>)=>{const regional=value.regional;if(!regional)return;const old=regional.overrides||[];setValue({...value,regional:{...regional,overrides:[...old.filter(r=>r.id!==id),{...old.find(r=>r.id===id),id,...p}]}});};
 return <details><summary>Праздники и сезоны мира</summary><fieldset disabled={disabled||busy}>
 <CalendarPresets value={choice} onChange={setChoice}/>
 <Button variant="outline" onClick={()=>void run(async()=>setPreview(await api<Preview>(`/workspaces/${wid}/draft/calendar-preview`,choice)))}>Предпросмотр набора</Button>
 <Button onClick={()=>void run(async()=>{await api(`/workspaces/${wid}/draft/calendar-presets`,{revision,presets:choice});await refresh();})}>Применить набор</Button>
 <PresetPreview value={preview}/>
 {(['observances','seasons'] as const).map(kind=><section key={kind}><h4>{kind==='observances'?'Собственные праздники и годовщины':'Границы сезонов'}</h4>{(value[kind]||[]).map((r,i)=><div key={r.id||i} style={{display:'flex',flexWrap:'wrap',gap:8}}><label>Название<input aria-label={`${kind} ${i+1} название`} value={r.name} onChange={e=>update(kind,i,{name:e.target.value})}/></label><label>Месяц<input style={{width:75}} type="number" min={1} max={24} value={r.month} onChange={e=>update(kind,i,{month:Number(e.target.value)})}/></label><label>День<input style={{width:75}} type="number" min={1} max={99} value={r.day} onChange={e=>update(kind,i,{day:Number(e.target.value)})}/></label><Button variant="outline" onClick={()=>setValue({...value,[kind]:value[kind]?.filter((_,j)=>j!==i)})}>Удалить {kind==='seasons'?'сезон':'праздник'}</Button></div>)}<Button variant="outline" onClick={()=>setValue({...value,[kind]:[...(value[kind]||[]),{...(kind==='observances'?{id:'custom_'+crypto.randomUUID(),character_ids:[]}:{}),name:'',month:1,day:1}]})}>Добавить {kind==='seasons'?'сезон':'праздник'}</Button></section>)}
 {!!preview?.events.length&&<details><summary>Изменить конкретные вхождения (только этот год)</summary>{preview.events.map(e=>{const o=value.regional?.overrides?.find(r=>r.id===e.id);return <div key={e.id}><label>Название<input value={o?.name??e.name} onChange={v=>override(e.id,{name:v.target.value})}/></label><label>Дата<input type="date" value={o?.date??e.date} onChange={v=>override(e.id,{date:v.target.value})}/></label><label><input type="checkbox" checked={o?.removed||false} onChange={v=>override(e.id,{removed:v.target.checked})}/> Не показывать это вхождение</label></div>})}</details>}
 <Button onClick={()=>void run(async()=>{await api(`/workspaces/${wid}/draft/candidate`,{revision,path:'/world_clock/calendar/profile',value},'PATCH');await refresh();})}>Сохранить свои даты</Button>
 {error&&<p role="alert">{error}</p>}
 </fieldset></details>;
}
