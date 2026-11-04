import {useState} from 'react';

/** A view of existing references; filtering never changes the selected IDs. */
export function ReferenceChecklist({label,options,value,onChange}:{label:string;options:[string,string][];value:unknown[];onChange:(value:unknown[])=>void}){
 const [query,setQuery]=useState('');
 const matches=options.filter(([,name])=>name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
 return <div className="ww-reference-checklist">
  {options.length>12&&<input type="search" aria-label={`Поиск: ${label}`} placeholder="Найти по имени" value={query} onChange={e=>setQuery(e.target.value)}/>}
  <p className="workshop-hint" role="status">Выбрано: {value.length} · Найдено: {matches.length}</p>
  <div className="draft-options">{matches.map(([id,name])=><label className="ww-reference-option" key={id}><input type="checkbox" checked={value.includes(id)} onChange={e=>onChange(e.target.checked?[...value,id]:value.filter(v=>v!==id))}/><span>{name}</span></label>)}</div>
  {!matches.length&&<p className="workshop-hint">Ничего не найдено. Измени запрос.</p>}
 </div>;
}
