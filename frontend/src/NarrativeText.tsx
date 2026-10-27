import {memo, useEffect, useRef, useState} from 'react';
import {useReducedMotion} from 'framer-motion';
import {Markdown} from './Markdown';
import {revealEnd} from './narrativePresentation';

/** One local animation loop, isolated from Game and the historical journal. */
export const NarrativeText = memo(function NarrativeText({text, complete, identity, onPresented, ...markdown}: {
  text:string; complete:boolean; identity:string; onPresented:(id:string)=>void; saveId:number; worldId:number; links:boolean;
  onCharacter:(id:string)=>void;
}) {
  const reduced=useReducedMotion();
  const [shown,setShown]=useState(()=>complete?text:text.slice(0,Number(sessionStorage.getItem(`reveal-${identity}`)||0)));
  const visible=useRef(shown);
  useEffect(()=>()=>{sessionStorage.setItem(`reveal-${identity}`,String(visible.current.length))},[identity]);
  useEffect(()=>{
    let frame=0, previous=0;
    if(reduced || !text.startsWith(visible.current)) {
      visible.current=text;setShown(text);return;
    }
    const tick=(now:number)=>{
      const end=revealEnd(text,visible.current.length,previous?now-previous:16);
      previous=now;
      visible.current=text.slice(0,end);setShown(visible.current);
      if(end<text.length)frame=requestAnimationFrame(tick);
    };
    if(visible.current.length<text.length)frame=requestAnimationFrame(tick);
    return()=>cancelAnimationFrame(frame);
  },[text,reduced]);
  const displayed=reduced?text:shown;
  useEffect(()=>{if(complete&&displayed===text)onPresented(identity)},[complete,displayed,text,identity,onPresented]);
  return <div className="narrative-text" data-revealing={displayed!==text}>
    <Markdown {...markdown} text={displayed} streaming={!complete||displayed!==text}/>
  </div>;
});
