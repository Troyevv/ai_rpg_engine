import {useEffect,useRef,useState} from 'react';
import type {Save,Job} from './types';
import {relationshipLabel} from './lib/relationships';
export type RuntimeNotice={id:string;kind:'relationship'|'lifecycle';source_id?:string;target_id?:string;deltas?:Record<string,number>;direction?:'up'|'down'|'mixed';field?:string;status?:string;text?:string};
export function RuntimeNotifications({save,job,enabled}:{save:Save|null;job:Job|null|undefined;enabled:boolean}){
 const seen=useRef(new Set<string>());const [queue,setQueue]=useState<RuntimeNotice[]>([]);
 const variant=save?.turns.at(-1)?.active_variant_id;
 useEffect(()=>{setQueue([]);seen.current.clear()},[save?.id]);
 useEffect(()=>{
  setQueue([]);
  // A notification requires a live submitted job AND its newly committed variant.
  // Reload, playback, variant selection and regeneration never enqueue history.
  if(!enabled||!save||!job||job.status!=='saved'||job.kind!=='turn'||job.replaces_id!=null||seen.current.has(job.id))return;
  if(!save.turns.at(-1)?.variants?.some(v=>v.id===variant&&v.job_id===job.id))return;
  seen.current.add(job.id);setQueue(save.state.notifications||[]);
 },[save?.id,variant,job?.id,job?.status,enabled]);
 useEffect(()=>{if(!queue.length)return;const timer=setTimeout(()=>setQueue(q=>q.slice(1)),3500);return()=>clearTimeout(timer)},[queue]);
 const notice=queue[0];if(!notice)return null;
 const name=(id?:string)=>save?.state.characters.find(c=>c.id===id)?.name||id;
 const labels:Record<string,string>={goals:'Цель выполнена',intentions:'Намерение выполнено',obligations:notice.status==='completed'?'Обязательство выполнено':'Обязательство'};
 return <div className={`runtime-notice ${notice.direction||'up'}`} role="status" aria-live="polite">
 {notice.kind==='relationship'?<><strong>{name(notice.source_id)} → {name(notice.target_id)} {notice.direction==='mixed'?'↕':notice.direction==='up'?'↑':'↓'}</strong><p>{Object.entries(notice.deltas||{}).map(([key,n])=>`${relationshipLabel(key)} ${n>0?'+':''}${n}`).join(' · ')}</p></>:<><strong>{notice.status==='completed'?'✓':'+'} {labels[notice.field||'']}</strong><p>{notice.text}</p></>}
 </div>;
}
