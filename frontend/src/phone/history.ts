import {useLayoutEffect,useRef} from 'react';

type Surface='phoneUI'|'phoneCall';
type Entry={key:string;back:()=>boolean};
const surfaces=new Map<Surface,Entry>();
const current=()=>surfaces.has('phoneCall')?'phoneCall':surfaces.has('phoneUI')?'phoneUI':null;
let removing=false;

function sync(){
  const surface=current();
  const state=history.state||{};
  if(state.inspectorOpen||state.saveWorkspace||state.mobileMenu)return;
  if(surface){
    const key=surfaces.get(surface)!.key;
    if(state[surface]===key)return;
    const {phoneUI,phoneCall,...rest}=state;
    if(phoneUI||phoneCall)history.replaceState({...rest,[surface]:key},'');
    else if(!removing)history.pushState({...rest,[surface]:key},'');
  }else if((state.phoneUI||state.phoneCall)&&!removing){
    removing=true;
    history.back();
  }
}

function onPop(event:PopStateEvent){
  if(removing){removing=false;event.stopImmediatePropagation();sync();return}
  const surface=current();
  if(!surface)return;
  event.stopImmediatePropagation();
  if(surfaces.get(surface)!.back())sync();
}

/** Both presentations occupy a single browser history entry. A call takes over the device. */
export function useDeviceHistory(surface:Surface,key:string,visible:boolean,back:()=>boolean){
  const callback=useRef(back);callback.current=back;
  useLayoutEffect(()=>{
    if(!visible)return;
    const entry={key,back:()=>callback.current()};
    surfaces.set(surface,entry);
    window.addEventListener('popstate',onPop,true);
    sync();
    return ()=>{
      if(surfaces.get(surface)===entry)surfaces.delete(surface);
      // React can hand the same device to another presentation in this commit.
      queueMicrotask(()=>{
        sync();
        if(!current()&&!removing)window.removeEventListener('popstate',onPop,true);
      });
    };
  },[surface,key,visible]);
}
