import {useEffect,useLayoutEffect,useReducer,useRef,useState} from 'react';
import {useReducedMotion} from 'framer-motion';
import {LockKeyhole,Eye,Sparkles} from 'lucide-react';
import {Markdown} from './Markdown';
import {useTheme} from './ThemeProvider';
import {animateFog,paintFog} from './lib/fogRenderer';
import {presentationKey,wasPresented,markPresented} from './lib/storyPresentation';
import {CharacterPeople} from './CharacterPeople';
import type {Save,State,StorySecret} from './types';
import './styles/story-secrets.css';

type CategoryLabels=Record<NonNullable<StorySecret['category']>,string>;
type RowProps={state?:State;onCharacter?:(id:string)=>void;row:StorySecret;save?:Save|null;active:boolean;preview?:boolean;previewFog?:Set<string>;categoryLabels?:CategoryLabels};

function SecretAudience({audience,preview,state,save,onCharacter}:{audience:NonNullable<StorySecret['audience']>;preview:boolean}&Pick<RowProps,'state'|'save'|'onCharacter'>){
 const visible=(ids:string[])=>ids.filter(id=>state?.characters?.some(c=>c.id===id));
 const people=(ids:string[])=><CharacterPeople ids={visible(ids)} state={state!} save={save} onCharacter={onCharacter!} hideUnavailable/>;
 if(!state||!onCharacter)return null;
 return <div className="secret-audience">
  <p>Кому известна тайна{!preview&&' · по сведениям ГГ'}</p>
  <dl>
   <div><dt>Знают:</dt> <dd>{visible(audience.known).length?people(audience.known):'Нет подтверждённых сведений'}</dd></div>
   {visible(audience.suspected).length>0&&<div><dt>Подозревают:</dt> <dd>{people(audience.suspected)}</dd></div>}
  </dl>
 </div>;
}

function SecretRow({row,save,active,preview=false,previewFog,categoryLabels,state,onCharacter}:RowProps){
 const element=useRef<HTMLElement>(null),canvas=useRef<HTMLCanvasElement>(null);
 const [visible,setVisible]=useState(false),[,refresh]=useReducer((n:number)=>n+1,0);
 const reduced=useReducedMotion();const {presentation}=useTheme();
 const hidden=row.status==='hidden',key=row.slot_id||row.id;
 const receipt=!preview&&save&&row.reveal_id?presentationKey(save.id,save.state.controlled_actor_id,row.reveal_id,'fog'):'';
 const revealing=active&&!hidden&&!!receipt&&!wasPresented(receipt);
 const previewPending=!!previewFog?.has(key)&&row.status==='spoiler';
 const previewRevealing=active&&preview&&previewPending&&!reduced;
 const dissolving=revealing||previewRevealing;
 const fog=hidden||dissolving;
 const phase=[...key].reduce((n,c)=>(n*31+c.charCodeAt(0))%997,0)/13;
 const clock=useRef<{pass:unknown;elapsed:number}>({pass:null,elapsed:0});
 useEffect(()=>{
  const node=element.current;if(!node)return;
  const observer=new IntersectionObserver(([entry])=>setVisible(entry.isIntersecting),{threshold:.01});
  observer.observe(node);return()=>observer.disconnect();
 },[]);
 useLayoutEffect(()=>{
  if(reduced&&previewPending)previewFog?.delete(key);
  const surface=canvas.current,node=element.current;
  if(!surface||!node||!fog||!visible||!active)return;
  const pass=previewRevealing?previewFog:revealing?receipt:null;
  if(clock.current.pass!==pass)clock.current={pass,elapsed:0};
  const progress=()=>dissolving?Math.min(1,clock.current.elapsed/2100):0;
  const resize=()=>{
   surface.width=Math.min(720,Math.ceil(node.clientWidth*1.25));
   surface.height=Math.min(320,Math.ceil(node.clientHeight*1.25));
   paintFog(surface,performance.now(),phase,progress());surface.dataset.painted='true';
  };
  resize();const observer=new ResizeObserver(resize);observer.observe(node);
  let finished=false,previous=0;
  const finish=()=>{
   if(finished)return;
   finished=true;
   if(previewRevealing)previewFog?.delete(key);
   else if(revealing)markPresented(receipt);
   refresh();
  };
  if(reduced){if(revealing)finish();return()=>observer.disconnect()}
  const stop=animateFog(time=>{
   if(previous&&time-previous<200)clock.current.elapsed+=time-previous;previous=time;
   const p=progress();paintFog(surface,time,phase,p);
   if(dissolving&&p===1)finish();
  });
  return()=>{stop();observer.disconnect()};
 },[fog,dissolving,revealing,previewPending,previewRevealing,previewFog,key,receipt,visible,active,reduced,phase,presentation.theme_id]);

 const status=row.status==='spoiler'?(row.knowledge_status==='suspected'?'ГГ только подозревает':'Спойлер · ГГ не знает'):'Известно ГГ';
 const category=row.category&&categoryLabels?.[row.category];
 return <article ref={element} className={`secret-entry ${hidden?'is-hidden':'is-known'} ${revealing?'is-revealing':''} ${previewRevealing?'is-preview-revealing':''} ${preview?'is-preview':''}`} data-secret-id={key} data-fog-active={fog&&visible&&active&&!reduced} tabIndex={-1}>
  {hidden?<div className="secret-placeholder"><LockKeyhole size={19} aria-hidden/><span>Скрытая тайна</span></div>:<div className="secret-disclosure">
   <div className="secret-kicker"><Eye size={15} aria-hidden/>{status}{category&&<span className="secret-category">{category}</span>}</div>
   <div className="secret-prose" tabIndex={0} role="region" aria-label={row.status==='spoiler'?'Содержание спойлера':'Содержание раскрытой тайны'}><Markdown text={row.text||''}/></div>
   {row.audience&&<SecretAudience audience={row.audience} preview={preview&&!!previewFog} state={state} save={save} onCharacter={onCharacter}/>}
   {row.source&&<details className="secret-source"><summary>Как стало известно</summary><Markdown text={row.source}/></details>}
  </div>}
  {fog&&<canvas ref={canvas} className="secret-fog" aria-hidden="true"/>}
  {revealing&&<span className="sr-only" role="status">Тайна раскрыта</span>}
 </article>;
}
type GroupProps=Omit<RowProps,'row'|'active'>&{title?:string;rows:StorySecret[];active?:boolean;target?:string};
export function StorySecrets({rows,save,active=true,target,title,preview=false,previewFog,categoryLabels,state,onCharacter}:GroupProps){
 const area=useRef<HTMLElement>(null);
 const targetVisible=rows.some(row=>(row.slot_id||row.id)===target);
 useEffect(()=>{if(!active||!target)return;const row=[...(area.current?.querySelectorAll<HTMLElement>('[data-secret-id]')||[])].find(e=>e.dataset.secretId===target);row?.scrollIntoView({block:'nearest'});row?.focus({preventScroll:true})},[target,active,targetVisible]);
 const hidden=rows.filter(r=>r.status==='hidden').length;
 return <section ref={area} className="story-secrets" aria-label="Сюжетные тайны">
  <header className="secrets-heading"><Sparkles size={21} aria-hidden/><div><h3>{title||'За пределами известного'}</h3><p>{hidden?`Скрытых тайн: ${hidden}`:title?`Записей: ${rows.length}`:'Нет доступных скрытых записей'}</p></div></header>
  {rows.length?<div className="secret-list">{rows.map(row=><SecretRow key={`${save?.id}:${save?.state.controlled_actor_id}:${row.slot_id||row.id}`} row={row} save={save} active={active} preview={preview} previewFog={previewFog} categoryLabels={categoryLabels} state={state} onCharacter={onCharacter}/>)}</div>:<p className="dossier-empty">Здесь появятся доступные вашему персонажу тайны.</p>}
 </section>;
}
