import {useEffect,useRef,useState,type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {PhoneOff,Minimize2,Phone,Send,ArrowDown} from 'lucide-react';
import {CharacterAvatar} from './Portrait';
import {callActivity,canStopCall} from './callActivity';
import type {Job,Save} from './types';
import {useStoryScroll} from './useStoryScroll';
import {phoneText as t} from './lib/phone';
import './styles/call-scene.css';
export function CallScene({save,disabled,children,submit,end,callId,onSelect,recovery,obscured,job,reconnecting,stop,stopping}: {
 job?:Job|null;reconnecting?:boolean;stop?:()=>void;stopping?:boolean;
 save:Save;disabled:boolean;children:ReactNode;submit:(text:string)=>Promise<void>;end:()=>Promise<void>;
 obscured?:boolean;callId:string;onSelect:(id:string|null)=>void;recovery?:ReactNode;
}) {
 const call=save.state.phone?.events.find(e=>e.id===callId);
 const active=call?.status==='answered';
 const activity=callActivity(job,reconnecting);
 const restoreSpeech=!!job&&['error','stopped'].includes(job.status)&&!job.narrative_complete&&!job.live&&job.revision===save.revision&&!!job.user_text;
 const working=active&&['callWaiting','callStreaming','callApplying','callReconnecting'].includes(activity);
 const scope=`${save.id}:${save.state.phone?.actor_id}:${save.state.camera?.pov_actor_id}:${callId}`;
 const key=`call-draft:${scope}`;
 const [minimized,setMinimized]=useState(sessionStorage.getItem(`call-min:${scope}`)==='true');
 const [draft,setDraft]=useState(()=>sessionStorage.getItem(key)||'');
 const input=useRef<HTMLTextAreaElement>(null),panel=useRef<HTMLDivElement>(null);
 const priorFocus=useRef<HTMLElement|null>(document.activeElement as HTMLElement);
 const {scroll,onScroll,away,jumpToLatest}=useStoryScroll(scope);
 const collapse=()=>{setMinimized(true);sessionStorage.setItem(`call-min:${scope}`,'true');priorFocus.current?.focus({preventScroll:true})};
 const expand=()=>{setMinimized(false);sessionStorage.setItem(`call-min:${scope}`,'false')};
 useEffect(()=>{
   if(minimized)return;
   panel.current?.focus();
   if(history.state?.phoneCall!==scope)history.pushState({...history.state,phoneCall:scope},'');
   return()=>{if(history.state?.phoneCall===scope&&!history.state?.inspectorOpen)history.back()};
 },[minimized,scope]);
 useEffect(()=>{
   const show=(event:Event)=>{if((event as CustomEvent).detail===callId)expand()};
   const back=()=>collapse();
   window.addEventListener('phone-call-open',show);window.addEventListener('popstate',back);window.addEventListener('save-workspace-opened',back);
   return()=>{window.removeEventListener('phone-call-open',show);window.removeEventListener('popstate',back);window.removeEventListener('save-workspace-opened',back)};
 },[callId,scope]);
 useEffect(()=>{if(obscured)collapse()},[obscured]);
 const wasActive=useRef(active);
 useEffect(()=>{if(wasActive.current&&!active){collapse();onSelect(null)}wasActive.current=active},[active]);
 const send=async()=>{if(disabled||!active||!draft.trim())return;const text=draft;try{await submit(text)}catch{return}setDraft(current=>current===text?'':current);if(sessionStorage.getItem(key)===text)sessionStorage.removeItem(key)};
 if(!call)return null;
 return createPortal(<>
   {minimized&&<button className="call-chip" onClick={expand}><Phone size={18}/><span>{call.label}</span><strong>{t(active?'restore':'history')}</strong></button>}
   <div className="call-scene-backdrop" hidden={minimized} onClick={collapse}>
     <section ref={panel} tabIndex={-1} role={minimized?undefined:'dialog'} aria-modal={minimized?undefined:true} aria-label={t('scene')} className="call-scene" onClick={e=>e.stopPropagation()} onKeyDown={e=>{
       if(e.key==='Escape'){e.preventDefault();e.stopPropagation();collapse()}
       if(e.key==='Tab'){
         const nodes=Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),textarea:not(:disabled),a[href]')||[]).filter(el=>el.getClientRects().length);
         const first=nodes[0],last=nodes.at(-1);
         if(e.shiftKey&&(document.activeElement===first||document.activeElement===panel.current)){e.preventDefault();last?.focus()}
         else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}
       }
     }}>
       <header className="call-scene-header"><CharacterAvatar subject={call.subject} saveId={save.id} size={76}/><div><p>{t(active?'connected':'ended')}</p><h2>{call.label}</h2><small>{call.time_label}</small></div><button aria-label={t('minimize')} onClick={collapse}><Minimize2 size={22}/></button></header>
       <div className="call-scene-scroll" ref={scroll} onScroll={onScroll}><div className="call-scene-text">{children}{recovery}</div></div>
       <footer>
         {active&&<div className="call-activity" data-state={activity}><p role="status" aria-live="polite" aria-atomic="true">{working&&<span className="call-activity-dots" aria-hidden="true"><i/><i/><i/></span>}{t(activity)}</p>{stop&&canStopCall(job)&&<button disabled={stopping} onClick={stop}>{t('callStop')}</button>}</div>}
         {active&&restoreSpeech&&!draft&&<button disabled={disabled} onClick={()=>{const text=job!.user_text!;setDraft(text);sessionStorage.setItem(key,text);input.current?.focus()}}>{t('restoreSpeech')}</button>}
         {away&&<button onClick={jumpToLatest}><ArrowDown size={15}/>{t('latest')}</button>}
         {active?<><form onSubmit={e=>{e.preventDefault();void send()}}><textarea ref={input} aria-label={t('input')} value={draft} onChange={e=>{setDraft(e.target.value);sessionStorage.setItem(key,e.target.value)}} onKeyDown={e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();e.stopPropagation();void send()}}}/><button disabled={disabled||!draft.trim()} aria-label={t('send')}><Send size={21}/></button></form><div className="call-scene-actions"><button onClick={collapse}>{t('physical')}</button><button className="call-end" disabled={disabled} onClick={()=>void end()}><PhoneOff size={18}/>{t('end')}</button></div></>:<button onClick={()=>onSelect(null)}>{t('close')}</button>}
       </footer>
     </section>
   </div>
 </>,document.body);
}
