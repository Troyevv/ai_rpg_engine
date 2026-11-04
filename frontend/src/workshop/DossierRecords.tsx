import {useId,useState,type ReactNode} from 'react';
import {ChevronDown} from 'lucide-react';
import {enumLabels} from '../runtimePresentation';

type Item = Record<string,unknown>;
type Entry = [string, Item];
type Caption = {title:string; subtitle?:string|null};
const BATCH = 8;

/** Related records in one person's dossier. Expanding uses the same field
 * editor as the full catalogue; no second copy of the data or editor state. */
export function DossierRecords({heading,entries,describe,render}:{
 heading:string; entries:Entry[]; describe:(item:Item)=>Caption;
 render:(id:string,item:Item)=>ReactNode;
}) {
 const headingId=useId();
 const [query,setQuery]=useState('');
 const [limit,setLimit]=useState(BATCH);
 const [expanded,setExpanded]=useState<string|null>(null);
 if(!entries.length)return null;
 const search=entries.length>2*BATCH;
 const term=search?query.trim().toLocaleLowerCase('ru'):'';
 const rows=entries.map(([id,item])=>({id,item,...describe(item)}))
   .filter(({title,subtitle})=>!term||[title,subtitle].join(' ').toLocaleLowerCase('ru').includes(term));
 return <section className="ww-dossier-records" aria-labelledby={headingId}>
  <h3 id={headingId}>{heading}{entries.length>1&&<small>{entries.length}</small>}</h3>
  {search&&<input type="search" placeholder="Найти запись" aria-label={`Поиск: ${heading}`} value={query}
    onChange={e=>{setQuery(e.target.value);setLimit(BATCH)}}/>}
  {rows.slice(0,limit).map(({id,item,title,subtitle})=><div className="ww-dossier-record" key={id}>
   <button type="button" className="ww-dossier-record-toggle" aria-expanded={expanded===id}
     onClick={()=>setExpanded(expanded===id?null:id)}>
    <span><strong>{title}</strong>{subtitle&&<small>{subtitle}</small>}</span>
    {typeof item.status==='string'&&<span className="ww-dossier-record-status">{enumLabels[item.status]||item.status}</span>}
    <ChevronDown size={16} aria-hidden="true"/>
   </button>
   {expanded===id&&<div className="ww-dossier-record-fields">{render(id,item)}</div>}
  </div>)}
  {!rows.length&&<p className="ww-dossier-note">По этому запросу ничего не найдено.</p>}
  {rows.length>limit&&<button type="button" className="ww-text-button" onClick={()=>setLimit(n=>n+BATCH)}>Показать ещё ({rows.length-limit})</button>}
 </section>;
}
