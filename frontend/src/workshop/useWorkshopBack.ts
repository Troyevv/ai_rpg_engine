import {dismissTransient} from '../lib/transientBack';
import {requestId} from '../lib/requestId';
import {useEffect,useRef} from 'react';

export function isWorkshopRoute() {
 return location.hash==='#workshop' || Boolean(history.state?.worldWorkshop);
}

/** Promoting an open library consumes its entry, so Back returns to the game. */
export function enterWorkshop() {
 const {rootDialog, ...state}=history.state || {};
 if(state.worldWorkshop)return;
 const next={...state,worldWorkshop:requestId()};
 if(rootDialog)history.replaceState(next,'','#workshop');
 else history.pushState(next,'','#workshop');
}

/** Own one same-document Back entry; nested Radix dialogs close from the top. */
export function useWorkshopBack(onBack?:()=>void,onInnerBack?:()=>boolean){
 const inner=useRef(onInnerBack);inner.current=onInnerBack;
 const back=useRef(onBack);back.current=onBack;
 useEffect(()=>{
  if(!back.current)return;
  let mounted=true;
  let installed=false;
  const key=history.state?.worldWorkshop || requestId();
  const pushRoute=()=>history.pushState({...history.state,worldWorkshop:key},'','#workshop');
  // StrictMode's probe must not create or pop a browser history entry.
  queueMicrotask(()=>{
   if(!mounted)return;
   installed=true;
   if(history.state?.worldWorkshop===key)return;
   // A direct link needs a same-document Narrative destination for Back.
   if(location.hash==='#workshop')history.replaceState(history.state,'',location.pathname+location.search);
   pushRoute();
  });
  const pop=(event:PopStateEvent)=>{
   event.stopImmediatePropagation();
   if(dismissTransient()){pushRoute();return;}
   const dialogs=document.querySelectorAll<HTMLButtonElement>('[role="dialog"][data-state="open"] .dialog-close');
   const close=dialogs.item(dialogs.length-1);
   if(close){pushRoute();close.click()}
   else if(inner.current?.())pushRoute();
   else back.current?.();
  };
  window.addEventListener('popstate',pop,true);
  return()=>{
   mounted=false;window.removeEventListener('popstate',pop,true);
   if(installed && history.state?.worldWorkshop===key){
    window.addEventListener('popstate',event=>event.stopImmediatePropagation(),{once:true,capture:true});
    history.back();
   }
  };
 },[]);
}
