import {useCallback,useLayoutEffect,useRef,useState} from 'react';

/** One scroll owner. ResizeObserver covers text, choices, panels and keyboard.
 * Never start smooth-scroll animations: a single pending frame coalesces resizes.
 * Keep a visible article anchor while unpinned, including regeneration above it.
 */
export function useStoryScroll(saveId?:number){
  const scroll=useRef<HTMLDivElement>(null),pinned=useRef(true);
  const [away,setAway]=useState(false);
  const frame=useRef(0),lastTop=useRef(0);
  const anchor=useRef<{id:string;offset:number}|null>(null);
  const key=`story-scroll-${saveId}`;
  const remember=useCallback(()=>{
    const el=scroll.current;if(!el||!el.clientHeight)return;
    lastTop.current=el.scrollTop;
    if(!pinned.current){
      const rect=el.getBoundingClientRect(),top=rect.top;
      // Hit-test the reading line; do not measure every historical article per frame.
      const hit=document.elementFromPoint?.(rect.left+el.clientWidth/2,top+4)?.closest<HTMLElement>('[data-reading-id]');
      const node=hit&&el.contains(hit)?hit:anchor.current?Array.from(el.querySelectorAll<HTMLElement>('[data-reading-id]')).find(n=>n.dataset.readingId===anchor.current!.id):el.querySelector<HTMLElement>('[data-reading-id]');
      anchor.current=node?{id:node.dataset.readingId!,offset:node.getBoundingClientRect().top-top}:null;
    }
    sessionStorage.setItem(key,JSON.stringify({top:el.scrollTop,pinned:pinned.current}));
  },[key]);
  const schedule=useCallback(()=>{
    if(frame.current)return;
    frame.current=requestAnimationFrame(()=>{
      frame.current=0;const el=scroll.current;if(!el||!el.clientHeight)return;
      if(pinned.current)el.scrollTop=el.scrollHeight;
      else if(anchor.current){
        const a=anchor.current;
        const node=Array.from(el.querySelectorAll<HTMLElement>('[data-reading-id]')).find(n=>n.dataset.readingId===a.id);
        if(node){
          const delta=node.getBoundingClientRect().top-el.getBoundingClientRect().top-a.offset;
          if(Math.abs(delta)>.5)el.scrollTop+=delta;
        }
      }
      remember();
    });
  },[remember]);
  const jumpToLatest=useCallback(()=>{pinned.current=true;anchor.current=null;setAway(false);schedule()},[schedule]);
  const onScroll=useCallback(()=>{
    const el=scroll.current;if(!el)return;
    const top=el.scrollTop;
    // Moving upwards is user intent even inside the near-bottom threshold.
    if(top<lastTop.current-1)pinned.current=false;
    else if(el.scrollHeight-el.clientHeight-top<2)pinned.current=true;
    setAway(!pinned.current);remember();
  },[remember]);
  useLayoutEffect(()=>{
    const el=scroll.current;if(!el)return;
    try {const saved=JSON.parse(sessionStorage.getItem(key)||'null');if(saved){pinned.current=saved.pinned;el.scrollTop=saved.top;setAway(!saved.pinned)}}catch{/* old UI preference */}
    remember();schedule();
    const observer=new ResizeObserver(schedule);observer.observe(el);
    if(el.firstElementChild)observer.observe(el.firstElementChild);
    const upward=(e:WheelEvent)=>{if(e.deltaY<0){pinned.current=false;setAway(true);remember()}};
    el.addEventListener('wheel',upward,{passive:true});
    return()=>{remember();observer.disconnect();el.removeEventListener('wheel',upward);cancelAnimationFrame(frame.current);frame.current=0};
  },[key,remember,schedule]);
  return {scroll,pinned,away,jumpToLatest,onScroll};
}
