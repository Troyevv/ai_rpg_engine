import {useEffect,useRef,useState} from 'react';
import {Bell,BookOpen,KeyRound,Sparkles,ArrowUpRight,X} from 'lucide-react';
import {Dialog,DialogContent,DialogTitle,DialogDescription} from './components/ui/dialog';
import {observeStorySnapshot,pendingStoryNotices,acknowledgeStoryNotice,invalidateStoryDelivery} from './lib/storyPresentation';
import type {Save,StoryNotice} from './types';
import './styles/story-notifications.css';
export const storyNoticeTitle=(kind:StoryNotice['kind'])=>({thread_new:'Новая сюжетная линия',secret_new:'Новая тайна',secret_revealed:'Раскрыта тайна'}[kind]);
const icons={thread_new:BookOpen,secret_new:Sparkles,secret_revealed:KeyRound};
export function StoryNotifications({save,enabled,active=true,onOpen}:{save:Save;enabled:boolean;active?:boolean;onOpen:(notice:StoryNotice)=>void}){
 const events=save.state.notification_history||[];
 const scope=`${save.id}:${save.state.controlled_actor_id}`;
 const navigating=useRef(false),trigger=useRef<HTMLButtonElement>(null);
 const [,refreshDelivery]=useState(0);
 const [history,setHistory]=useState(false),[filter,setFilter]=useState('all');
 const [paused,setPaused]=useState(false),[blocked,setBlocked]=useState(true);
 useEffect(()=>{
  // Presentation is suspended when its workspace is hidden/inert, including
  // calendar/workshop navigation. A DOM overlay never consumes a delivery.
  const check=()=>setBlocked(!!trigger.current?.closest('[inert],[hidden],[aria-hidden="true"]')||!!document.querySelector('.phone-device.is-open,.inspector-open,[role="dialog"]:not([data-state="closed"])')||document.hidden);
  const observer=new MutationObserver(check);observer.observe(document.body,{subtree:true,attributes:true,attributeFilter:['class','hidden','inert','aria-hidden','data-state'],childList:true});
  document.addEventListener('visibilitychange',check);check();
  return()=>{observer.disconnect();document.removeEventListener('visibilitychange',check)};
 },[]);
 useEffect(()=>{
  // Also supports isolated consumers; App normally admits the snapshot first.
  observeStorySnapshot(save);refreshDelivery(n=>n+1);
 },[scope,save.revision]);
 useEffect(()=>{const changed=(event:StorageEvent)=>{invalidateStoryDelivery(event.key);refreshDelivery(n=>n+1)};window.addEventListener('storage',changed);return()=>window.removeEventListener('storage',changed)},[]);
 const queue=pendingStoryNotices(save),current=queue[0];
 const suspended=blocked||!active||!enabled;
 const acknowledge=(id:string)=>{acknowledgeStoryNotice(save,id);setPaused(false);refreshDelivery(n=>n+1)};
 useEffect(()=>{
  if(!current||suspended||paused)return;
  // Completion means a full visible interval, not a claim about cognitive reading.
  // Interruption restarts the interval; it never settles a pending delivery.
  const timer=setTimeout(()=>acknowledge(current.id),6500);return()=>clearTimeout(timer);
 },[current?.id,scope,suspended,paused]);
 useEffect(()=>{if(suspended)setPaused(false)},[suspended]);
 const open=(event:StoryNotice)=>{if(event.available===false)return;acknowledge(event.id);navigating.current=true;setHistory(false);onOpen(event)};
 const Icon=current?icons[current.kind]:Bell;
 return <>
  <button ref={trigger} className="story-journal-trigger" onClick={()=>setHistory(true)} aria-label={`История уведомлений, ${events.length}`}><Bell size={17} aria-hidden/><span>События истории</span><b>{events.length}</b></button>
  {current&&!suspended&&<aside className={`story-toast ${current.kind}`} data-notice-id={current.id} aria-label="Событие истории" onMouseEnter={()=>setPaused(true)} onMouseLeave={()=>setPaused(false)} onFocusCapture={()=>setPaused(true)} onBlurCapture={e=>{if(!e.currentTarget.contains(e.relatedTarget))setPaused(false)}}>
   <div className="story-toast-icon"><Icon size={23} aria-hidden/></div><div className="story-toast-body"><div role="status" aria-live="polite" aria-atomic="true"><strong>{storyNoticeTitle(current.kind)}</strong><p>{current.text}</p></div><button onClick={()=>open(current)}>Подробнее <ArrowUpRight size={15} aria-hidden/></button></div><button className="story-toast-close" aria-label="Скрыть уведомление" onClick={()=>acknowledge(current.id)}><X size={17}/></button>{queue.length>1&&<small className="story-toast-count">Ещё {queue.length-1}</small>}
  </aside>}
  <Dialog open={history} onOpenChange={setHistory}><DialogContent className="story-journal" onCloseAutoFocus={e=>{if(navigating.current){e.preventDefault();navigating.current=false}}}><DialogTitle>События истории</DialogTitle><DialogDescription>Открытия вашего персонажа в текущей ветке истории.</DialogDescription>
   <div className="story-journal-filters" role="group" aria-label="Тип уведомлений">{[['all','Все'],['thread_new','Сюжет'],['secrets','Тайны']].map(([value,label])=><button key={value} aria-pressed={filter===value} onClick={()=>setFilter(value)}>{label}</button>)}</div>
   <ol className="story-journal-list">{events.slice().reverse().filter(e=>filter==='all'||(filter==='secrets'?e.kind!=='thread_new':e.kind===filter)).map(e=>{const EventIcon=icons[e.kind];return <li key={e.id}><button disabled={e.available===false} onClick={()=>open(e)}><EventIcon size={21} aria-hidden/><span><small>{storyNoticeTitle(e.kind)} · Ход {e.turn_id}</small><span className="story-journal-text">{e.text}</span><span className="story-journal-link">{e.available===false?'Знание больше не подтверждено':<>Открыть запись <ArrowUpRight size={14}/></>}</span></span></button></li>})}</ol>
   {!events.length&&<div className="story-journal-empty"><BookOpen size={32} aria-hidden/><p>История открытий ещё не началась.</p><small>Здесь сохраняются новые сюжетные линии и подтверждённые тайны.</small></div>}
  </DialogContent></Dialog>
 </>;
}
