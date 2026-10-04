import {worldTime} from './lib/worldTime';
import {useState} from 'react';
import {Button} from './components/ui/button';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './components/ui/dialog';
import type {Save} from './types';
export function TimeSkip({save,disabled,submit}:{save:Save;disabled:boolean;submit:(duration:number,reason:string)=>void}){
 const [open,setOpen]=useState(false);const [duration,setDuration]=useState(60);const [reason,setReason]=useState('');
 const now=save.state.world_clock?.minute||0;const cal=save.state.world_clock?.calendar;
 const label=(minute:number)=>worldTime(minute,cal);
 const until=(clock:number)=>{const diff=clock-now%1440;setDuration(diff>0?diff:diff+1440)};
 const target=now+duration;
 return <><Button variant="ghost" disabled={disabled} onClick={()=>setOpen(true)}>Пропустить время</Button><Dialog open={open} onOpenChange={setOpen}><DialogContent className="time-skip-sheet"><DialogHeader><DialogTitle>Пропустить время</DialogTitle><DialogDescription>Мир продолжит жить. Событие, требующее твоего участия, может прервать ожидание.</DialogDescription></DialogHeader>
 <p className="eyebrow">Сейчас</p><strong>{label(now)}</strong>
 <input aria-label="Длительность пропуска времени" type="range" min={1} max={1440} value={Math.min(duration,1440)} onChange={e=>setDuration(Number(e.target.value))}/>
 <div className="skip-presets">{[[10,'+10 мин'],[60,'+1 час']].map(([n,text])=><Button key={n} variant="outline" onClick={()=>setDuration(Number(n))}>{text}</Button>)}<Button variant="outline" onClick={()=>until(1080)}>До вечера</Button><Button variant="outline" onClick={()=>until(0)}>До полуночи</Button><Button variant="outline" onClick={()=>until(420)}>До утра</Button></div>
 <div className="skip-time-fields"><label>Дней вперёд<input type="number" aria-label="Дней вперёд" min={0} max={7} value={Math.floor(target/1440)-Math.floor(now/1440)} onChange={e=>setDuration(Math.max(1,Math.min(10080,Number(e.target.value)*1440+target%1440-now%1440)))}/></label><label>Конечное время<input type="time" aria-label="Конечное время" value={`${String(Math.floor(target%1440/60)).padStart(2,'0')}:${String(target%60).padStart(2,'0')}`} onChange={e=>{const [h,m]=e.target.value.split(':').map(Number);if(Number.isFinite(h)&&Number.isFinite(m)){let d=Math.floor(target/1440)*1440+h*60+m-now;if(d<=0)d+=1440;setDuration(Math.min(10080,d))}}}/></label></div>
 <p className="eyebrow">После</p><strong>{label(target)}</strong><p>{Math.floor(duration/60)} ч {duration%60} мин</p>
 <label>Причина (необязательно)<input value={reason} maxLength={1000} onChange={e=>setReason(e.target.value)}/></label>
 <Button disabled={disabled} onClick={()=>{submit(duration,reason);setOpen(false)}}>Пропустить {Math.floor(duration/60)} ч {duration%60} мин</Button>
 </DialogContent></Dialog></>;
}
