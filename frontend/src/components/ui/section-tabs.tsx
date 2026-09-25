import {useId, useRef} from 'react';
import {motion, useReducedMotion} from 'framer-motion';
import {motionTiming,ease} from '../../motion';

type Item<T extends string>={id:T;label:string};
/** Shared segmented navigation. Existing button semantics remain for navigation groups. */
export function SectionTabs<T extends string>({items,value,onChange,label,className='',tablist=false,panelId}:{items:readonly Item<T>[];value:T;onChange:(id:T)=>void;label:string;className?:string;tablist?:boolean;panelId?:string}){
 const id=useId();const ref=useRef<HTMLDivElement>(null);const reduced=useReducedMotion();
 return <div ref={ref} className={`section-tabs ${className}`} role={tablist?'tablist':'group'} aria-label={label}
 onKeyDown={e=>{
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
  e.preventDefault();const i=items.findIndex(t=>t.id===value);
  const next=e.key==='Home'?0:e.key==='End'?items.length-1:(i+(e.key==='ArrowRight'?1:-1)+items.length)%items.length;
  onChange(items[next].id);ref.current?.querySelectorAll('button')[next]?.focus();
 }}>
 {items.map(t=><button key={t.id} type="button" role={tablist?'tab':undefined} id={tablist?`${panelId}-tab-${t.id}`:undefined} aria-controls={tablist?panelId:undefined} aria-selected={tablist?value===t.id:undefined} aria-pressed={!tablist?value===t.id:undefined} tabIndex={tablist&&value!==t.id?-1:0} className={value===t.id?'selected':''} onClick={()=>onChange(t.id)}>
 {value===t.id&&<motion.span className="tab-indicator" layoutId={reduced?undefined:`tabs-${id}`} transition={{duration:motionTiming.fast,ease}} aria-hidden="true"/>}<span className="tab-label">{t.label}</span>
 </button>)}
 </div>;
}
