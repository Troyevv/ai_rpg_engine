import {dismissTransient} from '../lib/transientBack';
import {requestId} from '../lib/requestId';
import {useEffect,useRef} from 'react';

/** Own one same-document Back entry; nested Radix dialogs close from the top. */
export function useWorkshopBack(onBack?:()=>void,onInnerBack?:()=>boolean){
 const inner=useRef(onInnerBack);inner.current=onInnerBack;
 const back=useRef(onBack);back.current=onBack;
 useEffect(()=>{
  if(!back.current)return;
  let mounted=true;
  const key=requestId();
  // StrictMode's probe must not create or pop a browser history entry.
  queueMicrotask(()=>{if(mounted)history.pushState({...history.state,worldWorkshop:key},'')});
  const pop=(event:PopStateEvent)=>{
   event.stopImmediatePropagation();
   if(dismissTransient()){history.pushState({...history.state,worldWorkshop:key},'');return;}
   const dialogs=document.querySelectorAll<HTMLButtonElement>('[role="dialog"][data-state="open"] .dialog-close');
   const close=dialogs.item(dialogs.length-1);
   if(close){history.pushState({...history.state,worldWorkshop:key},'');close.click()}
   else if(inner.current?.())history.pushState({...history.state,worldWorkshop:key},'');
   else back.current?.();
  };
  window.addEventListener('popstate',pop,true);
  return()=>{
   mounted=false;window.removeEventListener('popstate',pop,true);
   if(history.state?.worldWorkshop===key){
    window.addEventListener('popstate',event=>event.stopImmediatePropagation(),{once:true,capture:true});
    history.back();
   }
  };
 },[]);
}
