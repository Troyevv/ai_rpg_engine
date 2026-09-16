import {useEffect,useState} from 'react';
import {BookOpen,Globe,Users,Brain,GitBranch,Menu,Settings2,Feather,Eye,EyeOff} from 'lucide-react';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './components/ui/dialog';
import {Button} from './components/ui/button';
import type {Save,Scene} from './types';

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
export function MobileNavigation({open,setOpen,world,go,inspect,settings,reading,toggleReading,branches}:{open:boolean;setOpen:(v:boolean)=>void;world:boolean;go:(v:'game'|'prepare')=>void;inspect:(v:'Мир'|'Персонажи'|'Память')=>void;settings:()=>void;reading:boolean;toggleReading:()=>void;branches:()=>void}){
 const act=(fn:()=>void)=>{setOpen(false);fn()};
 return <><Button size="icon" variant="ghost" aria-label="Меню игры" onClick={()=>setOpen(true)}><Menu/></Button>
 <Dialog open={open} onOpenChange={setOpen}><DialogContent className="mobile-sheet"><DialogHeader><DialogTitle>Меню игры</DialogTitle><DialogDescription>История, мир и инструменты</DialogDescription></DialogHeader>
 <nav className="mobile-nav" aria-label="Мобильная навигация">
 <button onClick={()=>act(()=>go('game'))}><BookOpen/>Игра</button>
 <button disabled={!world} onClick={()=>act(()=>inspect('Мир'))}><Globe/>Мир</button>
 <button disabled={!world} onClick={()=>act(()=>inspect('Персонажи'))}><Users/>NPC</button>
 <button disabled={!world} onClick={()=>act(()=>inspect('Память'))}><Brain/>Память</button>
 <button disabled={!world} onClick={()=>act(branches)}><GitBranch/>Ветки</button>
 </nav><div className="mobile-menu-tools">
 <Button variant="ghost" onClick={()=>act(()=>go('prepare'))}><Feather/>Создать</Button>
 <Button variant="ghost" onClick={()=>act(settings)}><Settings2/>Настройки</Button>
 <Button variant="ghost" onClick={()=>act(toggleReading)}>{reading?<EyeOff/>:<Eye/>}{reading?'Выйти из чтения':'Режим чтения'}</Button>
 </div></DialogContent></Dialog></>;
}
export function MobileScene({save,meta,busy,switchActor,background,openCharacter}:{save:Save;meta?:Scene;busy:boolean;switchActor:(id:string,source?:number)=>void;background:()=>void;openCharacter:(id:string)=>void}){
 const [sheet,setSheet]=useState<'pov'|'scene'|null>(null);
 const main=save.state.protagonist_id||save.state.characters.find(c=>c.is_player)?.id;
 const actor=save.state.controlled_actor_id||main;
 const name=(id?:string)=>save.state.characters.find(c=>c.id===id)?.name.replace(' (ГГ)','')||'Персонаж';
 const nearby=meta?.present_ids.filter(id=>id!==actor)||[];
 return <div className="mobile-context">
 <div className="mobile-pov"><button disabled={busy} onClick={()=>setSheet('pov')}>{name(actor)} ▾</button><button disabled={busy||!save.turns.length} onClick={background}>Мир без ГГ</button></div>
 <button className="mobile-scene-line" onClick={()=>setSheet('scene')}>{meta?.time||'Время не задано'} · {meta?.location||'Место не задано'}{nearby.length?` · ${nearby.map(name).join(', ')}`:''} ▾</button>
 <Dialog open={!!sheet} onOpenChange={v=>{if(!v)setSheet(null)}}><DialogContent className="mobile-sheet"><DialogHeader><DialogTitle>{sheet==='pov'?'За кого играть':'Текущая сцена'}</DialogTitle><DialogDescription>{sheet==='pov'?'Переход откроет сцену персонажа и варианты действий.':`${meta?.time||''} · ${meta?.location||''}`}</DialogDescription></DialogHeader>
 {sheet==='pov'?<div className="actor-list">{actor!==main&&<Button disabled={busy} onClick={()=>{setSheet(null);switchActor(main!)}}>Вернуться к {name(main)}</Button>}{save.state.characters.map(c=><button key={c.id} disabled={busy||c.id===actor} onClick={()=>{setSheet(null);switchActor(c.id)}}>{name(c.id)}{c.id===main?' (ГГ)':''}{c.id===actor?' · сейчас':''}</button>)}</div>:<><p>{save.state.scene}</p><div className="actor-list">{nearby.map(id=><button key={id} onClick={()=>{setSheet(null);openCharacter(id)}}>{name(id)}</button>)}</div></>}
 </DialogContent></Dialog></div>;
}
