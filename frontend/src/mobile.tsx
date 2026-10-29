import {inspectorSections,it,panelLabel,type Panel} from './lib/inspector';
import {gameLocale,profileDate} from './gameDate';
import {CharacterAvatar} from './Portrait';
import {SceneClock} from './SceneClock';
import {useEffect,useState,useRef} from 'react';
import {CalendarDays,BookOpen,GitBranch,Menu,Settings2,Feather,Eye,ArrowRight,X} from 'lucide-react';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription,DialogClose} from './components/ui/dialog';
import {Button} from './components/ui/button';
import type {Save,Scene,World} from './types';

export function useMobile(){
 const [mobile,set]=useState(()=>matchMedia('(max-width:767px)').matches);
 useEffect(()=>{const q=matchMedia('(max-width:767px)');const change=()=>set(q.matches);q.addEventListener('change',change);return()=>q.removeEventListener('change',change)},[]);
 return mobile;
}
export function useMobileViewport(mobile:boolean){
 useEffect(()=>{
  if(!mobile)return;
  const vv=window.visualViewport;let baseline=window.innerHeight;
  const update=()=>{const height=vv?.height||window.innerHeight;baseline=Math.max(baseline,window.innerHeight);
   document.documentElement.style.setProperty('--app-height',`${height}px`);
   document.documentElement.style.setProperty('--app-top',`${vv?.offsetTop||0}px`);
   const typing=/INPUT|TEXTAREA/.test(document.activeElement?.tagName||'');
   document.documentElement.classList.toggle('keyboard-open',typing&&baseline-height>100);
  };
  update();vv?.addEventListener('resize',update);vv?.addEventListener('scroll',update);window.addEventListener('resize',update);document.addEventListener('focusin',update);document.addEventListener('focusout',update);
  return()=>{vv?.removeEventListener('resize',update);vv?.removeEventListener('scroll',update);window.removeEventListener('resize',update);document.removeEventListener('focusin',update);document.removeEventListener('focusout',update);document.documentElement.classList.remove('keyboard-open')};
 },[mobile]);
}
const menuCopy = {
 ru: {title:'Меню игры', subtitle:'Мир, персонажи и управление историей', resume:'Продолжить историю', events:'История и события', tools:'Инструменты', create:'Создать мир', settings:'Настройки', reading:'Режим чтения', calendar:'Календарь', family:'Родословная', noWorld:'Мир не выбран', noSave:'Нет активного прохождения', observer:'Без управляемого персонажа', unknownActor:'Персонаж не указан', location:'Место не указано', time:'Время не указано', day:'День', close:'Закрыть', navigation:'Мобильная навигация'},
 en: {title:'Game menu', subtitle:'World, characters and story controls', resume:'Continue story', events:'Story & events', tools:'Tools', create:'Create world', settings:'Settings', reading:'Reading mode', calendar:'Calendar', family:'Genealogy', noWorld:'No world selected', noSave:'No active playthrough', observer:'No controlled character', unknownActor:'Character not recorded', location:'Location not recorded', time:'Time not recorded', day:'Day', close:'Close', navigation:'Mobile navigation'},
};
export function MobileNavigation({activePanel,workspace,open,setOpen,world,save,go,inspect,settings,reading,toggleReading}:{activePanel?:Panel;workspace:(section:"calendar"|"family")=>void;open:boolean;setOpen:(v:boolean)=>void;world:World|null;save:Save|null;go:(v:'game'|'prepare')=>void;inspect:(v:Panel)=>void;settings:()=>void;reading:boolean;toggleReading:()=>void}){
 const [locale,setLocale]=useState(gameLocale);
 useEffect(()=>{
  const observer=new MutationObserver(()=>setLocale(gameLocale()));
  observer.observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
  return()=>observer.disconnect();
 },[]);
 const copy=menuCopy[locale.startsWith('en')?'en':'ru'];
 const trigger=useRef<HTMLButtonElement>(null);
 const pending=useRef<(()=>void)|null>(null);
 // Consume the menu's own history entry before opening another workspace.
 // Capture prevents the Inspector beneath it from also consuming Android Back.
 useEffect(()=>{
  if(!open)return;
  history.pushState({...history.state,mobileMenu:true},'');
  const back=(event:PopStateEvent)=>{
   event.stopImmediatePropagation();
   setOpen(false);
  };
  window.addEventListener('popstate',back,true);
  return()=>window.removeEventListener('popstate',back,true);
 },[open,setOpen]);
 const close=(action?:()=>void)=>{
  pending.current=action||null;
  if(history.state?.mobileMenu)history.back();
  else setOpen(false);
 };
 const state=save?.state;
 const actorId=state?.controlled_actor_id===undefined?(state?.protagonist_id||state?.characters.find(c=>c.is_player)?.id):state.controlled_actor_id;
 const actor=state?.characters.find(c=>c.id===actorId);
 const clock=state?.world_clock;
 const time=clock?.projection;
 const date=time?.date?profileDate(time.date,(clock?.calendar as {profile?:Parameters<typeof profileDate>[1]})?.profile,'weekday'):time?`${copy.day} ${time.day}`:'';
 const sections=(group:'worldGroup'|'storyGroup')=>inspectorSections.filter(s=>s.group===group).map(({id,key,icon:Icon})=><button key={id} disabled={!world} aria-current={activePanel===id?'page':undefined} className={`mobile-menu-card menu-${key}`} onClick={()=>close(()=>inspect(id))}><span className="mobile-menu-icon"><Icon aria-hidden="true"/></span><span>{panelLabel(id)}</span></button>);
 return <><Button ref={trigger} data-mobile-menu-trigger size="icon" variant="ghost" aria-label={copy.title} onClick={()=>setOpen(true)}><Menu/></Button>
 <Dialog open={open} onOpenChange={value=>value?setOpen(true):close()}><DialogContent className="mobile-game-menu inspector-mobile-palette" onCloseAutoFocus={event=>{
  event.preventDefault();
  // Wait for Radix to remove the exiting dialog/focus trap before opening
  // the destination; a requestAnimationFrame can still precede that removal.
  const action=pending.current;pending.current=null;
  if(action)action();else trigger.current?.focus({preventScroll:true});
 }}>
 <header className="mobile-menu-brand"><BookOpen aria-hidden="true"/><div><small>NARRATIVE WORLD</small><strong>{world?.name||copy.noWorld}</strong></div><DialogClose className="mobile-menu-close" aria-label={copy.close}><X aria-hidden="true"/></DialogClose></header>
 <div className="mobile-menu-scroll">
 <DialogHeader><DialogTitle>{copy.title}</DialogTitle><DialogDescription>{copy.subtitle}</DialogDescription></DialogHeader>
 <button className="mobile-menu-resume" disabled={!save} onClick={()=>close(()=>go('game'))}>
 {actor?<CharacterAvatar subject={actor} saveId={save?.id} size={44}/>:<BookOpen aria-hidden="true"/>}
 <span><strong>{copy.resume}</strong><small>{!save?copy.noSave:actor?.name|| (actorId===null?copy.observer:copy.unknownActor)}</small>{save&&<small>{save.scene_meta?.location||state?.scene_meta?.location||copy.location} · {time?`${date} · ${time.time}`:copy.time}</small>}</span><ArrowRight aria-hidden="true"/>
 </button>
 <nav aria-label={copy.navigation}>
 <section className="mobile-menu-group"><h3>{it('worldGroup')}</h3><div className="mobile-menu-grid mobile-menu-primary">{sections('worldGroup')}</div></section>
 <section className="mobile-menu-group"><h3>{copy.events}</h3><div className="mobile-menu-grid">{sections('storyGroup')}<button className="mobile-menu-card menu-calendar" disabled={!save} onClick={()=>close(()=>workspace('calendar'))}><span className="mobile-menu-icon"><CalendarDays aria-hidden="true"/></span><span>{copy.calendar}</span></button><button className="mobile-menu-card menu-family" disabled={!save} onClick={()=>close(()=>workspace('family'))}><span className="mobile-menu-icon"><GitBranch aria-hidden="true"/></span><span>{copy.family}</span></button></div></section>
 <section className="mobile-menu-group"><h3>{copy.tools}</h3><div className="mobile-menu-tools">
 <button onClick={()=>close(()=>go('prepare'))}><Feather aria-hidden="true"/><span>{copy.create}</span><ArrowRight aria-hidden="true"/></button>
 <button onClick={()=>close(settings)}><Settings2 aria-hidden="true"/><span>{copy.settings}</span><ArrowRight aria-hidden="true"/></button>
 <button role="switch" aria-checked={reading} onClick={toggleReading}><Eye aria-hidden="true"/><span>{copy.reading}</span><span className="mobile-menu-switch" aria-hidden="true"/></button>
 </div></section>
 </nav></div></DialogContent></Dialog></>;
}
export function MobileScene({save,meta,busy,switchActor,background,openCharacter,openCamera}:{openCamera:()=>void;save:Save;meta?:Scene;busy:boolean;switchActor:(id:string,source?:number)=>void;background:()=>void;openCharacter:(id:string)=>void}){
 const [sheet,setSheet]=useState<'pov'|'scene'|null>(null);
 const main=save.state.protagonist_id||save.state.characters.find(c=>c.is_player)?.id;
 const actor=save.state.controlled_actor_id===undefined?main:save.state.controlled_actor_id;
 const name=(id?:string|null)=>save.state.characters.find(c=>c.id===id)?.name.replace(' (ГГ)','')||'Персонаж';
 const nearby=meta?.present_ids.filter(id=>id!==actor)||[];
 return <div className="mobile-context">
 <div className="mobile-pov"><button disabled={busy} onClick={()=>setSheet('pov')}>{actor===null?"Наблюдение":name(actor)} ▾</button><button disabled={busy||!save.turns.length} onClick={background}>Мир без ГГ</button><button aria-label="Камера и журнал мира" onClick={openCamera}>◎</button></div>
 <button className="mobile-scene-line" onClick={()=>setSheet('scene')}><SceneClock save={save} fallback={meta?.time}/> · {meta?.location||'Место не задано'}{nearby.length?` · ${nearby.map(name).join(', ')}`:''} ▾</button>
 <Dialog open={!!sheet} onOpenChange={v=>{if(!v)setSheet(null)}}><DialogContent className="mobile-sheet"><DialogHeader><DialogTitle>{sheet==='pov'?'За кого играть':'Текущая сцена'}</DialogTitle><DialogDescription>{sheet==='pov'?'Переход откроет сцену персонажа и варианты действий.':`${meta?.time||''} · ${meta?.location||''}`}</DialogDescription></DialogHeader>
 {sheet==='pov'?<div className="actor-list">{actor!==main&&<Button disabled={busy} onClick={()=>{setSheet(null);switchActor(main!)}}>Вернуться к {name(main)}</Button>}{save.state.characters.map(c=><button key={c.id} disabled={busy||c.id===actor} onClick={()=>{setSheet(null);switchActor(c.id)}}>{name(c.id)}{c.id===main?' (ГГ)':''}{c.id===actor?' · сейчас':''}</button>)}</div>:<><Button onClick={()=>{setSheet(null);window.dispatchEvent(new CustomEvent('save-workspace',{detail:{section:'calendar'}}))}}>Открыть календарь</Button><p>{save.state.scene}</p><div className="actor-list">{nearby.map(id=><button key={id} onClick={()=>{setSheet(null);openCharacter(id)}}>{name(id)}</button>)}</div></>}
 </DialogContent></Dialog></div>;
}
