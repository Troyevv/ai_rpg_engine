import {useEffect,useRef,useState} from 'react';
import {Bell,BookOpen,KeyRound,Sparkles,ArrowUpRight,X} from 'lucide-react';
import {Dialog,DialogContent,DialogTitle,DialogDescription} from './components/ui/dialog';
import {presentationKey,markPresented,wasPresented} from './lib/storyPresentation';
import type {Save,StoryNotice} from './types';
import './styles/story-notifications.css';
export const storyNoticeTitle=(kind:StoryNotice['kind'])=>({thread_new:'Новая сюжетная линия',secret_new:'Новая тайна',secret_revealed:'Раскрыта тайна'}[kind]);
const icons={thread_new:BookOpen,secret_new:Sparkles,secret_revealed:KeyRound};
export function StoryNotifications({save,enabled,onOpen}:{save:Save;enabled:boolean;onOpen:(notice:StoryNotice)=>void}){
 const events=save.state.notification_history||[];
 const scope=`${save.id}:${save.state.controlled_actor_id}`;
 const navigating=useRef(false);
 const baseline=useRef<{scope:string;ids:Set<string>}|null>(null);
 const [queue,setQueue]=useState<StoryNotice[]>([]),[history,setHistory]=useState(false);
 const [filter,setFilter]=useState('all'),[paused,setPaused]=useState(false),[blocked,setBlocked]=useState(false);
 useEffect(()=>{
  // Workspace/phone overlays must never be covered or have announcements steal attention.
  const check=()=>setBlocked(!!document.querySelector('.phone-device.is-open,.inspector-open,[role="dialog"]')||document.hidden);
  const observer=new MutationObserver(check);observer.observe(document.body,{subtree:true,attributes:true,attributeFilter:['class','hidden'],childList:true});
  document.addEventListener('visibilitychange',check);check();
  return()=>{observer.disconnect();document.removeEventListener('visibilitychange',check)};
 },[]);
 useEffect(()=>{
  const ids=new Set(events.map(e=>e.id));
  if(!baseline.current||baseline.current.scope!==scope){baseline.current={scope,ids};setQueue([]);return}
  const next=events.filter(e=>!baseline.current!.ids.has(e.id)&&!wasPresented(presentationKey(save.id,save.state.controlled_actor_id,e.id,'toast')));
  baseline.current={scope,ids};
  setQueue(q=>enabled?[...q.filter(e=>ids.has(e.id)),...next.filter(e=>!q.some(old=>old.id===e.id))]:[]);
 },[scope,save.revision,enabled]);
 const notice=queue[0];
 useEffect(()=>{
  if(!notice||blocked)return;
  markPresented(presentationKey(save.id,save.state.controlled_actor_id,notice.id,'toast'));
  if(paused)return;
  const timer=setTimeout(()=>setQueue(q=>q.slice(1)),6500);return()=>clearTimeout(timer);
 },[notice?.id,blocked,paused,scope]);
 const open=(event:StoryNotice)=>{if(event.available===false)return;navigating.current=true;setHistory(false);setQueue(q=>q.filter(n=>n.id!==event.id));onOpen(event)};
 const current=notice&&events.find(e=>e.id===notice.id); // Never render a stale payload after rollback/POV change.
 const Icon=current?icons[current.kind]:Bell;
 return <>
  <button className="story-journal-trigger" onClick={()=>setHistory(true)} aria-label={`История уведомлений, ${events.length}`}><Bell size={17} aria-hidden/><span>События истории</span><b>{events.length}</b></button>
  {current&&!blocked&&<aside className={`story-toast ${current.kind}`} aria-label="Событие истории" onMouseEnter={()=>setPaused(true)} onMouseLeave={()=>setPaused(false)} onFocusCapture={()=>setPaused(true)} onBlurCapture={e=>{if(!e.currentTarget.contains(e.relatedTarget))setPaused(false)}}>
   <div className="story-toast-icon"><Icon size={23} aria-hidden/></div><div className="story-toast-body"><div role="status" aria-live="polite" aria-atomic="true"><strong>{storyNoticeTitle(current.kind)}</strong><p>{current.text}</p></div><button onClick={()=>open(current)}>Подробнее <ArrowUpRight size={15} aria-hidden/></button></div><button className="story-toast-close" aria-label="Скрыть уведомление" onClick={()=>setQueue(q=>q.slice(1))}><X size={17}/></button>{queue.length>1&&<small className="story-toast-count">Ещё {queue.length-1}</small>}
  </aside>}
  <Dialog open={history} onOpenChange={setHistory}><DialogContent className="story-journal" onCloseAutoFocus={e=>{if(navigating.current){e.preventDefault();navigating.current=false}}}><DialogTitle>События истории</DialogTitle><DialogDescription>Открытия вашего персонажа в текущей ветке истории.</DialogDescription>
   <div className="story-journal-filters" role="group" aria-label="Тип уведомлений">{[['all','Все'],['thread_new','Сюжет'],['secrets','Тайны']].map(([value,label])=><button key={value} aria-pressed={filter===value} onClick={()=>setFilter(value)}>{label}</button>)}</div>
   <ol className="story-journal-list">{events.slice().reverse().filter(e=>filter==='all'||(filter==='secrets'?e.kind!=='thread_new':e.kind===filter)).map(e=>{const EventIcon=icons[e.kind];return <li key={e.id}><button disabled={e.available===false} onClick={()=>open(e)}><EventIcon size={21} aria-hidden/><span><small>{storyNoticeTitle(e.kind)} · Ход {e.turn_id}</small><span className="story-journal-text">{e.text}</span><span className="story-journal-link">{e.available===false?'Знание больше не подтверждено':<>Открыть запись <ArrowUpRight size={14}/></>}</span></span></button></li>})}</ol>
   {!events.length&&<div className="story-journal-empty"><BookOpen size={32} aria-hidden/><p>История открытий ещё не началась.</p><small>Здесь сохраняются новые сюжетные линии и подтверждённые тайны.</small></div>}
  </DialogContent></Dialog>
 </>;
}
