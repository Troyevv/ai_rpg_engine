import {useEffect,useRef} from 'react';

/** Chat owns one route entry and one modal entry; Back consumes only the top layer. */
export function useChatNavigation<T extends string>(panel:T|null,setPanel:(panel:T|null)=>void,onBack:()=>void,onInnerBack?:()=>boolean) {
  const current=useRef(panel);current.current=panel;
  const leave=useRef(onBack);leave.current=onBack;
  const trigger=useRef<HTMLElement|null>(null);
  const after=useRef<(()=>void)|null>(null);
  const closing=useRef(false);
  const inner=useRef(onInnerBack);inner.current=onInnerBack;
  useEffect(()=>{
    if(!history.state?.chatMode)history.pushState({...history.state,chatMode:true},'');
    const back=(event:PopStateEvent)=>{
      event.stopImmediatePropagation();
      // Shared connection settings (and its prompt viewer) sit above Chat.
      // Consume Back there first, preserving the Chat route and its drafts.
      const nested=!current.current?document.querySelectorAll<HTMLButtonElement>('[role="dialog"]:not([data-state="closed"]):not(.chat-dialog) .dialog-close'):null;
      if(nested?.length){history.pushState({...history.state,chatMode:true},'');nested[nested.length-1].click();return}
      if(!closing.current&&current.current&&inner.current?.()){
        history.pushState({...history.state,chatMode:true,chatPanel:true},'');return;
      }
      closing.current=false;
      if(current.current){setPanel(null);requestAnimationFrame(()=>trigger.current?.isConnected&&trigger.current.focus({preventScroll:true}))}
      if(!history.state?.chatMode)leave.current();
      const done=after.current;after.current=null;done?.();
    };
    window.addEventListener('popstate',back,true);
    return()=>window.removeEventListener('popstate',back,true);
  },[setPanel]);
  useEffect(()=>{
    if(panel&&!history.state?.chatPanel)history.pushState({...history.state,chatPanel:true},'');
  },[!!panel]);
  const open=(value:T)=>{if(!current.current)trigger.current=document.activeElement as HTMLElement;setPanel(value)};
  const close=(done?:()=>void)=>{
    if(closing.current)return;
    after.current=done||null;
    if(history.state?.chatPanel){closing.current=true;history.back()}
    else{setPanel(null);done?.()}
  };
  const back=()=>{if(history.state?.chatMode)history.back();else onBack()};
  return {open,close,back,trigger};
}
