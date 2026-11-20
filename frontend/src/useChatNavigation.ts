import {dismissTransient} from './lib/transientBack';
import {useEffect,useRef} from 'react';

/** Browser entries identify both the Chat route and nested panel destinations.
 * A completed command can return to the conversation in one traversal. */
export function useChatNavigation<T extends string>(panel:T|null,setPanel:(panel:T|null)=>void,onBack:()=>void,onInnerBack?:()=>boolean) {
  const current=useRef(panel);current.current=panel;
  const leave=useRef(onBack);leave.current=onBack;
  const trigger=useRef<HTMLElement|null>(null);
  const after=useRef<(()=>void)|null>(null);
  const closing=useRef(false);
  const inner=useRef(onInnerBack);inner.current=onInnerBack;
  const entry=useRef(history.state);
  useEffect(()=>{
    if(!history.state?.chatMode)history.pushState({...history.state,chatMode:true},'');
    const back=(event:PopStateEvent)=>{
      event.stopImmediatePropagation();
      if(!closing.current && dismissTransient()){history.pushState(entry.current,'');return;}
      const dialogs=document.querySelectorAll<HTMLElement>('[role="dialog"]:not([data-state="closed"])');
      const top=dialogs[dialogs.length-1];
      if(top&&!top.classList.contains('chat-dialog')){
        history.pushState(entry.current,'');
        top.querySelector<HTMLButtonElement>(':scope > .dialog-close')?.click();return;
      }
      if(!closing.current&&current.current&&inner.current?.()){
        history.pushState(entry.current,'');return;
      }
      closing.current=false;
      const destination=typeof history.state?.chatPanel==='string'?history.state.chatPanel as T:null;
      setPanel(destination);
      if(!destination)requestAnimationFrame(()=>trigger.current?.isConnected&&trigger.current.focus({preventScroll:true}));
      if(!history.state?.chatMode)leave.current();
      entry.current=history.state;
      const done=after.current;after.current=null;done?.();
    };
    window.addEventListener('popstate',back,true);
    return()=>window.removeEventListener('popstate',back,true);
  },[setPanel]);
  useEffect(()=>{
    if(panel){
      if(!history.state?.chatPanel)history.pushState({...history.state,chatPanel:panel,chatDepth:1},'');
      else if(history.state.chatPanel!==panel)history.replaceState({...history.state,chatPanel:panel},'');
    }
    entry.current=history.state;
  },[panel]);
  const open=(value:T,nested=false)=>{
    if(!current.current)trigger.current=document.activeElement as HTMLElement;
    if(nested&&current.current&&value!==current.current){
      history.pushState({...history.state,chatPanel:value,chatDepth:(history.state?.chatDepth||1)+1},'');
    }
    setPanel(value);
  };
  const close=(done?:()=>void)=>{
    if(closing.current)return;
    after.current=done||null;
    if(history.state?.chatPanel){closing.current=true;history.go(-(history.state.chatDepth||1))}
    else{setPanel(null);done?.()}
  };
  const back=()=>{if(history.state?.chatMode)history.back();else onBack()};
  return {open,close,back,trigger};
}
