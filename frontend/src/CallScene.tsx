import {choiceText, NarrativeChoiceCard} from './NarrativeChoice';
import {useEffect,useLayoutEffect,useRef,useState,type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {PhoneFrame} from './PhoneFrame';
import {PhoneOff,Phone,Send,ArrowDown} from 'lucide-react';
import {CharacterAvatar} from './Portrait';
import {callActivity,canStopCall} from './callActivity';
import type {Choice,Job,Save} from './types';
import {useStoryScroll} from './useStoryScroll';
import {phoneText as t} from './lib/phone';
import './styles/call-scene.css';
export function CallScene({save,disabled,children,choices,submit,end,callId,onSelect,recovery,obscured,job,reconnecting,stop,stopping}: {
 job?:Job|null;reconnecting?:boolean;stop?:()=>void;stopping?:boolean;
 save:Save;choices:Choice[];disabled:boolean;children:ReactNode;submit:(text:string)=>Promise<void>;end:()=>Promise<void>;
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
 const {scroll,onScroll,away,jumpToLatest}=useStoryScroll(scope);
 const collapse=()=>{setMinimized(true);sessionStorage.setItem(`call-min:${scope}`,'true');requestAnimationFrame(()=>document.querySelector<HTMLButtonElement>('.phone-peek')?.focus({preventScroll:true}))};
 const expand=()=>{setMinimized(false);sessionStorage.setItem(`call-min:${scope}`,'false')};
 useEffect(()=>{
   if(minimized)return;
   panel.current?.focus();
   if(history.state?.phoneCall!==scope){
     const {phoneUI, ...state}=history.state||{};
     // Hand the phone's existing Back entry to the call; do not leave a ghost
     // phone screen below the independent call surface.
     if(phoneUI)history.replaceState({...state,phoneCall:scope},'');
     else history.pushState({...state,phoneCall:scope},'');
   }
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
 useLayoutEffect(()=>{
   const el=input.current;
   if(!el||minimized)return;
   el.style.height='auto';
   el.style.height=Math.min(el.scrollHeight,108)+'px';
 },[draft,minimized,active]);
 const sendingRef=useRef(false);
 const [sending,setSending]=useState(false);
 const send=async()=>{
   if(sendingRef.current||disabled||!active||!draft.trim())return;
   const text=draft;
   sendingRef.current=true;
   setSending(true);
   try {
     await submit(text);
     setDraft(current=>current===text?'':current);
     if(sessionStorage.getItem(key)===text)sessionStorage.removeItem(key);
   } catch {
     // The parent reports the failure; the editable draft stays available.
   } finally {
     sendingRef.current=false;
     setSending(false);
   }
 };
 if(!call)return null;
 return <>
   {minimized&&createPortal(<button className="call-chip" onClick={expand}><Phone size={18}/><span>{call.label}</span><strong>{t(active?'restore':'history')}</strong></button>,document.getElementById('root')!)}
   <PhoneFrame save={save} open={!minimized} close={collapse} closeLabel={t('minimize')} dialogLabel={t('scene')}>
     <section ref={panel} tabIndex={-1} className="call-scene">
       <header className="call-scene-header"><CharacterAvatar subject={call.subject} saveId={save.id} size={44}/><div><h2>{call.label}</h2><small title={call.time_label}><Phone size={12}/>{active?'На линии':t('ended')}</small></div>{active&&<button aria-label={t('end')} className="call-end" disabled={active&&disabled} onClick={()=>void end()}><PhoneOff size={18}/></button>}</header>
       <div className="call-scene-scroll" ref={scroll} onScroll={onScroll}><div className="call-scene-text">{children}{recovery}</div></div>
         {active&&!working&&choices.length>0&&<div className="call-suggestions" role="group" aria-label="Варианты продолжения звонка">
           {choices.map(c=>{
             const text=choiceText(c);
             const selected=draft===text || draft.endsWith('\n'+text);
             return <NarrativeChoiceCard key={JSON.stringify([c.action,c.speech])} choice={c} compact
               selected={selected} sending={false} disabled={disabled||sending} choose={value=>{
                 const next=draft.trim() ? draft+'\n'+value : value;
                 setDraft(next);sessionStorage.setItem(key,next);input.current?.focus({preventScroll:true});
               }}/>;
           })}
         </div>}
       <footer>
         {active&&<div className="call-activity" data-state={activity}><p role="status" aria-live="polite" aria-atomic="true">{working&&<span className="call-activity-dots" aria-hidden="true"><i/><i/><i/></span>}{t(activity)}</p>{stop&&canStopCall(job)&&<button disabled={stopping} onClick={stop}>{t('callStop')}</button>}</div>}
         {active&&restoreSpeech&&!draft&&<button disabled={disabled} onClick={()=>{const text=job!.user_text!;setDraft(text);sessionStorage.setItem(key,text);input.current?.focus()}}>{t('restoreSpeech')}</button>}
         {away&&<button onClick={jumpToLatest}><ArrowDown size={15}/>{t('latest')}</button>}
         {active?<><form onSubmit={e=>{e.preventDefault();void send()}}><textarea ref={input} rows={1} placeholder="Что ты говоришь?" aria-label={t('input')} value={draft} onChange={e=>{setDraft(e.target.value);sessionStorage.setItem(key,e.target.value)}} onKeyDown={e=>{if(e.key==='Enter'&&!e.nativeEvent.isComposing&&(e.ctrlKey||e.metaKey)){e.preventDefault();e.stopPropagation();void send()}}}/><button disabled={disabled||!draft.trim()} aria-label={t('send')}><Send size={21}/></button></form></>:<button onClick={()=>onSelect(null)}>{t('close')}</button>}
       </footer>
     </section>
   </PhoneFrame>
 </>;
}
