import {useEffect,useRef,useState,type ReactNode} from 'react';
import {Menu} from 'lucide-react';
import {Dialog,DialogContent,DialogTitle} from './components/ui/dialog';
import {Button} from './components/ui/button';

export function appIsMobile(){
 return (document.getElementById('root')?.clientWidth || window.innerWidth)<=680;
}
export function useMobile(){
 const [mobile,set]=useState(appIsMobile);
 useEffect(()=>{
   const root=document.getElementById('root');
   if(!root)return;
   const update=()=>set(appIsMobile());
   const observer=new ResizeObserver(update);
   observer.observe(root);update();
   return ()=>observer.disconnect();
 },[]);
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
  return()=>{vv?.removeEventListener('resize',update);vv?.removeEventListener('scroll',update);window.removeEventListener('resize',update);document.removeEventListener('focusin',update);document.removeEventListener('focusout',update);document.documentElement.classList.remove('keyboard-open');document.documentElement.style.removeProperty('--app-height');document.documentElement.style.removeProperty('--app-top')};
 },[mobile]);
}
export function MobileNavigation({open,setOpen,children}:{
 open:boolean;setOpen:(v:boolean)=>void;children:(act:(action:()=>void)=>void)=>ReactNode;
}){
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
 return <><Button ref={trigger} data-mobile-menu-trigger size="icon" variant="ghost" aria-label="Меню игры" onClick={()=>setOpen(true)}><Menu/></Button>
   <Dialog open={open} onOpenChange={v=>v?setOpen(true):close()}>
     <DialogContent className="mobile-game-menu narrative-drawer" aria-describedby={undefined} onCloseAutoFocus={e=>{
       e.preventDefault();const action=pending.current;pending.current=null;
       if(action)action();else trigger.current?.focus({preventScroll:true});
     }}><DialogTitle className="sr-only">Меню игры</DialogTitle>{children(close)}</DialogContent>
   </Dialog></>;
}
