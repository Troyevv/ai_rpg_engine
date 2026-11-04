import {useEffect,useRef,useState} from 'react';
import {useReducedMotion} from 'framer-motion';
import {LockKeyhole,Eye,Sparkles} from 'lucide-react';
import {Markdown} from './Markdown';
import {useTheme} from './ThemeProvider';
import {animateFog,paintFog} from './lib/fogRenderer';
import {presentationKey,wasPresented,markPresented} from './lib/storyPresentation';
import type {Save,StorySecret} from './types';
import './styles/story-secrets.css';

function SecretRow({row,save,active,preview=false}:{row:StorySecret;save?:Save|null;active:boolean;preview?:boolean}){
 const element=useRef<HTMLElement>(null),canvas=useRef<HTMLCanvasElement>(null);
 const [visible,setVisible]=useState(false),[completed,setCompleted]=useState('');
 const reduced=useReducedMotion();const {presentation}=useTheme();
 const hidden=row.status==='hidden';
 const receipt=!preview&&save&&row.reveal_id?presentationKey(save.id,save.state.controlled_actor_id,row.reveal_id,'fog'):'';
 const revealing=active&&!hidden&&!!receipt&&completed!==receipt&&!wasPresented(receipt);
 const fog=hidden||revealing;
 const phase=[...row.id].reduce((n,c)=>(n*31+c.charCodeAt(0))%997,0)/13;
 useEffect(()=>{
  const node=element.current;if(!node)return;
  const observer=new IntersectionObserver(([entry])=>setVisible(entry.isIntersecting),{threshold:.1});
  observer.observe(node);return()=>observer.disconnect();
 },[]);
 useEffect(()=>{
  const surface=canvas.current,node=element.current;if(!surface||!node||!fog)return;
  let elapsed=0,previous=0;
  const resize=()=>{surface.width=Math.min(720,Math.ceil(node.clientWidth*1.25));surface.height=Math.min(320,Math.ceil(node.clientHeight*1.25));paintFog(surface,performance.now(),phase,revealing?Math.min(1,elapsed/2100):0)};
  resize();const observer=new ResizeObserver(resize);observer.observe(node);
  const finish=()=>{markPresented(receipt);setCompleted(receipt)};
  if(reduced){if(revealing&&visible&&active)finish();return()=>observer.disconnect()}
  const stop=visible&&active?animateFog(time=>{
   if(previous&&time-previous<200)elapsed+=time-previous;previous=time;
   const progress=revealing?Math.min(1,elapsed/2100):0;
   paintFog(surface,time,phase,progress);
   if(revealing&&progress===1)finish();
  }):()=>{};
  return()=>{stop();observer.disconnect()};
 },[fog,revealing,receipt,visible,active,reduced,phase,presentation.theme_id]);
 return <article ref={element} className={`secret-entry ${hidden?'is-hidden':'is-known'} ${revealing?'is-revealing':''} ${preview?'is-preview':''}`} data-secret-id={row.id} data-fog-active={fog&&visible&&active&&!reduced} tabIndex={-1}>
  {hidden?<div className="secret-placeholder"><LockKeyhole size={19} aria-hidden/><span>Скрытая тайна</span></div>:<div className="secret-disclosure"><div className="secret-kicker"><Eye size={15} aria-hidden/>{row.status==='spoiler'?(row.knowledge_status==='suspected'?'ГГ только подозревает':'Спойлер · ГГ не знает'):'Известно ГГ'}</div><div className="secret-prose" tabIndex={0} role="region" aria-label="Содержание раскрытой тайны"><Markdown text={row.text||''}/></div>{row.source&&<details className="secret-source"><summary>Как стало известно</summary><Markdown text={row.source}/></details>}</div>}
  {fog&&<canvas ref={canvas} className="secret-fog" aria-hidden="true"/>}
  {revealing&&<span className="sr-only" role="status">Тайна раскрыта</span>}
 </article>;
}
export function StorySecrets({rows,save,active=true,target,title,preview=false}:{title?:string;rows:StorySecret[];save?:Save|null;active?:boolean;target?:string;preview?:boolean}){
 const area=useRef<HTMLElement>(null);
 const targetVisible=rows.some(row=>row.id===target);
 useEffect(()=>{if(!active||!target)return;const row=[...(area.current?.querySelectorAll<HTMLElement>('[data-secret-id]')||[])].find(e=>e.dataset.secretId===target);row?.scrollIntoView({block:'nearest'});row?.focus({preventScroll:true})},[target,active,targetVisible]);
 const hidden=rows.filter(r=>r.status==='hidden').length;
 return <section ref={area} className="story-secrets" aria-label="Сюжетные тайны">
  <header className="secrets-heading"><Sparkles size={21} aria-hidden/><div><h3>{title||'За пределами известного'}</h3><p>{hidden?`Скрытых тайн: ${hidden}`:title?`Записей: ${rows.length}`:'Нет доступных скрытых записей'}</p></div></header>
  {rows.length?<div className="secret-list">{rows.map(row=><SecretRow key={`${save?.id}:${save?.state.controlled_actor_id}:${row.id}`} row={row} save={save} active={active} preview={preview}/>)}</div>:<p className="dossier-empty">Здесь появятся доступные вашему персонажу тайны.</p>}
 </section>;
}
