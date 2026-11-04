import {useEffect, useId, useRef, useState} from 'react';
import {Eye, EyeOff, LoaderCircle, Search, RotateCcw} from 'lucide-react';
import {api} from './api';
import {StorySecrets} from './StorySecrets';
import type {Save, State, StorySecret} from './types';

type Props = {state:State; save?:Save|null; characterId?:string; active?:boolean; target?:string};

// A new identity destroys all transient author data BEFORE rendering another scope.
export function StorySecretBrowser(props:Props) {
 const {save,state,characterId,active=true}=props;
 if(!active)return null;
 const scope=`${save?.id}:${save?.revision}:${state.controlled_actor_id}:${characterId||'world'}:${active}`;
 return <SecretBrowser key={scope} {...props} active={active}/>;
}
function SecretBrowser({state,save,characterId,active=true,target}:Props) {
 const [enabled,setEnabled]=useState(false),[rows,setRows]=useState<StorySecret[]|null>(null);
 const [query,setQuery]=useState(''),[error,setError]=useState(false),[attempt,setAttempt]=useState(0);
 const request=useRef<AbortController|null>(null);const description=useId();
 useEffect(()=>{if(target)setQuery('')},[target]);
 useEffect(()=>{
  if(!enabled||!save||!active)return;
  const controller=new AbortController();request.current=controller;
  setRows(null);setError(false);
  const scope=characterId?`&character_id=${encodeURIComponent(characterId)}`:'';
  api<{rows:StorySecret[];revision:number;character_id:string|null}>(`/saves/${save.id}/story-secret-spoilers?revision=${save.revision}${scope}`,undefined,'GET',controller.signal)
   .then(result=>{if(!controller.signal.aborted&&result.revision===save.revision&&result.character_id===(characterId||null))setRows(result.rows)})
   .catch(()=>{if(!controller.signal.aborted)setError(true)});
  return()=>controller.abort();
 },[enabled,attempt,save?.id,save?.revision,characterId,active]);
 const toggle=()=>{
  request.current?.abort();setRows(null);setError(false);setQuery('');setEnabled(!enabled);
 };
 const personal=state.story_secrets?.personal||{};
 const ownIds=new Set((personal[state.controlled_actor_id||'']||[]).filter(r=>r.category==='own').map(r=>r.id));
 const ordinary=characterId?(personal[characterId]||[]):[
  ...new Map(Object.values(personal).flat().map(r=>[r.id,{...r,category:ownIds.has(r.id)?'own' as const:'related' as const}])).values(),
  ...(state.story_secrets?.world||[]).map(r=>({...r,category:'world' as const})),
 ];
 const current=enabled?(rows||[]):ordinary;
 const filtered=current.filter(row=>!query||!!row.text?.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
 const isSelf=characterId===state.controlled_actor_id;
 const groups:[string,StorySecret[]][]=[
  [isSelf||!characterId?'Мои тайны':'Собственные тайны персонажа',filtered.filter(r=>r.status!=='hidden'&&r.category==='own')],
  [characterId?(enabled?'Связанные тайны':'Известные связанные тайны'):'Тайны персонажей',filtered.filter(r=>r.status!=='hidden'&&r.category!=='own'&&r.category!=='world')],
  [isSelf?'Неизвестное обо мне':characterId?'Неизвестное о персонаже':'Неизвестные тайны персонажей',filtered.filter(r=>r.status==='hidden'&&r.category!=='world')],
  ['Тайны мира',filtered.filter(r=>r.category==='world')],
 ];
 return <div className={`secret-browser ${enabled?'spoilers-enabled':''}`}>
  <header className="spoiler-toolbar">
   <div><h3>Сюжетные тайны</h3><p id={description}>{characterId?'Тайны этого персонажа':'Все сюжетные тайны мира'}</p></div>
   <button type="button" role="switch" aria-checked={enabled} aria-describedby={description} disabled={!save||!active} className="spoiler-switch" onClick={toggle}>
    {enabled?<Eye size={18} aria-hidden/>:<EyeOff size={18} aria-hidden/>}<span>Показать спойлеры</span><span className="spoiler-track" aria-hidden><span/></span>
   </button>
  </header>
  <p className="spoiler-mode" role="status">{enabled?'Спойлеры включены · знания персонажа не меняются':'Показано только доступное вашему персонажу'}</p>
  {!characterId&&<label className="secret-search"><Search size={18} aria-hidden/><span className="sr-only">Поиск тайн</span><input type="text" aria-label="Поиск тайн" placeholder="Найти тайну" value={query} onChange={e=>setQuery(e.target.value)}/><span className="muted">{enabled&&rows===null?'—':filtered.length}</span></label>}
  {enabled&&rows===null&&!error?<div className="secret-loading" role="status"><LoaderCircle className="secret-spinner" size={22} aria-hidden/><span>Загружаем тайны…</span><button type="button" onClick={toggle}>Отмена</button></div>:
   error?<div className="secret-load-error" role="alert"><p>Не удалось загрузить тайны. Обновите раздел, если история изменилась.</p><button type="button" onClick={()=>setAttempt(n=>n+1)}><RotateCcw size={16} aria-hidden/>Повторить</button></div>:
   filtered.length?groups.filter(([,values])=>values.length).map(([title,values])=><StorySecrets key={title} title={title} rows={values} save={save} active={active} target={target} preview={enabled}/>):
   <p className="dossier-empty">{query?'По этому запросу ничего не найдено.':enabled?'В этой области нет сюжетных тайн.':'Нет доступных записей о тайнах.'}</p>}
 </div>;
}
