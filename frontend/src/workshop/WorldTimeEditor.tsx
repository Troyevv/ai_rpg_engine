import {useEffect,useRef,useState} from 'react';
import {api} from '../api';
type TimeView={label:string;date?:string;world_time?:number;effective?:{system:string}};
/** Dates use Runtime calendar arithmetic on the server; editing never writes the world. */
export function WorldTimeEditor({wid,value,onChange,label,onValidity}:{wid:string;value:unknown;onChange:(v:number)=>void;label:string;onValidity?:(valid:boolean)=>void}){
 const minute=typeof value==='number'?value:0;
 const [view,setView]=useState<TimeView|null>(null),[date,setDate]=useState(''),[error,setError]=useState('');
 const sequence=useRef(0);const day=Math.floor(minute/1440),hours=Math.floor(minute%1440/60),minutes=minute%60;
 useEffect(()=>{const c=new AbortController();const request=++sequence.current;void api<TimeView>(`/workspaces/${wid}/draft/time?minute=${minute}`,undefined,'GET',c.signal).then(r=>{if(request!==sequence.current||c.signal.aborted)return;setView(r);setDate(r.date||'');setError('')}).catch(()=>{if(!c.signal.aborted)setError('Предпросмотр даты недоступен')});return()=>{c.abort();sequence.current++}},[wid,minute]);
 useEffect(()=>{onValidity?.(!error&&(!view?.date||date===view.date))},[date,view,error,onValidity]);
 async function chooseDate(){if(!date||date===view?.date)return;const request=++sequence.current;try{const r=await api<TimeView>(`/workspaces/${wid}/draft/time?minute=${minute}&date=${encodeURIComponent(date)}`);if(request!==sequence.current)return;if(typeof r.world_time!=='number')throw new Error(r.label);onChange(r.world_time);setError('')}catch(e){if(request===sequence.current)setError((e as Error).message)}}
 return <div className="ww-time-editor">{view?.date?<label>Дата<input aria-label={`${label} · дата`} type={view.effective?.system==='custom'?'text':'date'} placeholder="ГГГГ-ММ-ДД" value={date} onChange={e=>setDate(e.target.value)} onBlur={()=>void chooseDate()}/></label>:<label>День мира (от начала отсчёта)<input aria-label={`${label} · день`} type="number" min={0} value={day} onChange={e=>onChange(Math.max(0,Math.floor(Number(e.target.value)))*1440+minute%1440)}/></label>}<label>Время<input aria-label={`${label} · время`} type="time" value={`${String(hours).padStart(2,'0')}:${String(minutes).padStart(2,'0')}`} onChange={e=>{if(e.target.value){const [h,m]=e.target.value.split(':').map(Number);onChange(day*1440+h*60+m)}}}/></label><p role="status">{view?.label}</p>{error&&<p role="alert">{error}</p>}</div>;
}
