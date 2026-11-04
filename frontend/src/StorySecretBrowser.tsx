import {useEffect, useId, useRef, useState} from 'react';
import {Eye, EyeOff, LoaderCircle, Search, RotateCcw} from 'lucide-react';
import {api} from './api';
import {StorySecrets} from './StorySecrets';
import type {Save, State, StorySecret} from './types';

type Props = {state:State; save?:Save|null; characterId?:string; active?:boolean; target?:string};
type Group = 'own'|'related'|'hidden'|'world'|'additional';
type Preview = {rows:StorySecret[]; pendingFog:Set<string>};

function safeGroup(row:StorySecret):Group {
 if(row.category==='world')return 'world';
 if(row.status==='hidden')return 'hidden';
 return row.category==='own'?'own':'related';
}

// A new identity destroys all transient author data BEFORE rendering another scope.
export function StorySecretBrowser(props:Props) {
 const {save,state,characterId,active=true}=props;
 if(!active)return null;
 const scope=JSON.stringify([save?.id,save?.revision,state.controlled_actor_id,characterId,active]);
 return <SecretBrowser key={scope} {...props} active={active}/>;
}

function SecretBrowser({state,save,characterId,active=true,target}:Props) {
 const [enabled,setEnabled]=useState(false),[preview,setPreview]=useState<Preview|null>(null);
 const [query,setQuery]=useState(''),[error,setError]=useState(false),[attempt,setAttempt]=useState(0);
 const request=useRef<AbortController|null>(null),switchButton=useRef<HTMLButtonElement>(null);
 const description=useId();
 useEffect(()=>{if(target)setQuery('')},[target]);
 useEffect(()=>{
  if(!enabled||!save||!active)return;
  const controller=new AbortController();request.current=controller;
  const scope=characterId?`&character_id=${encodeURIComponent(characterId)}`:'';
  api<{rows:StorySecret[];revision:number;character_id:string|null}>(`/saves/${save.id}/story-secret-spoilers?revision=${save.revision}${scope}`,undefined,'GET',controller.signal)
   .then(result=>{
    if(controller.signal.aborted||result.revision!==save.revision||result.character_id!==(characterId||null))return;
    // One pass per deliberate activation. This set never goes into save data or storage.
    const pendingFog=new Set(result.rows.filter(r=>r.status==='spoiler').map(r=>r.slot_id||r.id));
    setPreview({rows:result.rows,pendingFog});
   })
   .catch(()=>{if(!controller.signal.aborted)setError(true)});
  return()=>controller.abort();
 },[enabled,attempt,save?.id,save?.revision,characterId,active]);
 const toggle=()=>{
  request.current?.abort();setPreview(null);setError(false);setQuery('');setEnabled(!enabled);
  switchButton.current?.focus({preventScroll:true});
 };
 const retry=()=>{setError(false);setAttempt(n=>n+1);switchButton.current?.focus({preventScroll:true})};
 const search=(value:string)=>{
  // Filtering is reading, not another request to lift the fog.
  preview?.pendingFog.clear();setQuery(value);
 };
 const personal=state.story_secrets?.personal||{};
 const ownIds=new Set((personal[state.controlled_actor_id||'']||[]).filter(r=>r.category==='own').map(r=>r.id));
 const ordinary=characterId?(personal[characterId]||[]):[
  ...new Map(Object.values(personal).flat().map(r=>[r.id,{...r,category:ownIds.has(r.id)?'own' as const:'related' as const}])).values(),
  ...(state.story_secrets?.world||[]).map(r=>({...r,category:'world' as const})),
 ];
 const groups:Record<Group,StorySecret[]>={own:[],related:[],hidden:[],world:[],additional:[]};
 const bySlot=new Map(preview?.rows.filter(r=>r.slot_id).map(r=>[r.slot_id,r]));
 const normalizedQuery=query.trim().toLocaleLowerCase();
 const append=(group:Group,row:StorySecret)=>{
  if(!normalizedQuery||row.text?.toLocaleLowerCase().includes(normalizedQuery))groups[group].push(row);
 };
 // Keep both the original group AND row key for existing cards. Moving rows between
 // titled sections would unmount the very canvas that is meant to clear in place.
 for(const safe of ordinary){
  const full=bySlot.get(safe.id);
  if(!preview||full)append(safeGroup(safe),full?{...safe,...full,id:safe.id}:safe);
 }
 if(preview){
  const slots=new Set(ordinary.map(r=>r.id));
  for(const row of preview.rows)if(!row.slot_id||!slots.has(row.slot_id))append('additional',row);
 }
 const isSelf=characterId===state.controlled_actor_id;
 const titles:Record<Group,string>={
  own:isSelf||!characterId?'Мои тайны':'Собственные тайны персонажа',
  related:characterId?(preview?'Связанные тайны':'Известные связанные тайны'):'Тайны персонажей',
  hidden:isSelf?'Неизвестное обо мне':characterId?'Неизвестное о персонаже':'Неизвестные тайны персонажей',
  world:'Тайны мира',additional:'Только в режиме спойлеров'
 };
 const categoryLabels={own:titles.own,related:characterId?'Связанная тайна персонажа':'Связанная с персонажем тайна',world:'Тайна мира'};
 const sections=(Object.keys(groups) as Group[]).filter(key=>groups[key].length);
 const count=sections.reduce((n,key)=>n+groups[key].length,0);
 const loading=enabled&&!preview&&!error;
 return <div className={`secret-browser ${enabled?'spoilers-enabled':''}`}>
  <header className="spoiler-toolbar">
   <div><h3>Сюжетные тайны</h3><p id={description}>{characterId?'Тайны этого персонажа':'Все сюжетные тайны мира'}</p></div>
   <button ref={switchButton} type="button" role="switch" aria-checked={enabled} aria-describedby={description} disabled={!save||!active} className="spoiler-switch" onClick={toggle}>
    {enabled?<Eye size={18} aria-hidden/>:<EyeOff size={18} aria-hidden/>}<span>Показать спойлеры</span><span className="spoiler-track" aria-hidden><span/></span>
   </button>
  </header>
  <div className="spoiler-mode">
   {loading?<><span role="status"><LoaderCircle className="secret-spinner" size={17} aria-hidden/> Загружаем тайны…</span><button type="button" onClick={toggle}>Отмена</button></>:
    error?<><span role="alert">Не удалось загрузить тайны.</span><button type="button" onClick={retry}><RotateCcw size={15} aria-hidden/>Повторить</button></>:
    <span role="status">{enabled?'Спойлеры включены · знания персонажа не меняются':'Показано только доступное вашему персонажу'}</span>}
  </div>
  {!characterId&&<label className="secret-search"><Search size={18} aria-hidden/><span className="sr-only">Поиск тайн</span><input type="text" aria-label="Поиск тайн" placeholder="Найти тайну" value={query} onChange={e=>search(e.target.value)}/><span className="muted">{count}</span></label>}
  {sections.map(key=><StorySecrets key={key} title={titles[key]} rows={groups[key]} save={save} active={active} target={target} preview={enabled}
   previewFog={preview?.pendingFog} categoryLabels={preview&&(key==='hidden'||key==='additional')?categoryLabels:undefined}/>)}
  {!count&&<p className="dossier-empty">{query?'По этому запросу ничего не найдено.':preview?'В этой области нет сюжетных тайн.':'Нет доступных записей о тайнах.'}</p>}
 </div>;
}
