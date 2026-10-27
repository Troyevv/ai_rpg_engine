import {memo, useCallback, useEffect, useRef, useState} from 'react';
import {useReducedMotion} from 'framer-motion';
import {Markdown} from './Markdown';
import {revealEnd} from './narrativePresentation';

/** One local animation loop, isolated from Game and the historical journal. */
export const NarrativeText = memo(function NarrativeText({text, complete, identity, onPresented, ...markdown}: {
  text:string; complete:boolean; identity:string; onPresented:(id:string)=>void;
  saveId:number; worldId:number; links:boolean; onCharacter:(id:string)=>void;
}) {
  const reduced=useReducedMotion();
  const [shown,setShown]=useState(()=>complete?text:text.slice(0,Number(sessionStorage.getItem(`reveal-${identity}`)||0)));
  const visible=useRef(shown),target=useRef(text),frame=useRef(0);
  target.current=text;
  useEffect(()=>()=>{
    cancelAnimationFrame(frame.current);frame.current=0;
    sessionStorage.setItem(`reveal-${identity}`,String(visible.current.length));
  },[identity]);
  useEffect(()=>{
    if(reduced || !text.startsWith(visible.current)) {
      cancelAnimationFrame(frame.current);frame.current=0;
      visible.current=text;setShown(text);return;
    }
    // Incoming snapshots update the target, never cancel/restart a running loop.
    if(frame.current||visible.current.length>=text.length)return;
    let previous=0;
    const tick=(now:number)=>{
      const full=target.current;
      const end=revealEnd(full,visible.current.length,previous?now-previous:16);
      previous=now;
      visible.current=full.slice(0,end);setShown(visible.current);
      frame.current=end<full.length?requestAnimationFrame(tick):0;
    };
    frame.current=requestAnimationFrame(tick);
  },[text,reduced]);
  const displayed=reduced?text:shown;
  const ready=useCallback(()=>onPresented(identity),[identity,onPresented]);
  return <div className="narrative-text" data-revealing={displayed!==text}>
    <Markdown {...markdown} onReady={ready} text={displayed} streaming={!complete||displayed!==text}/>
  </div>;
});
