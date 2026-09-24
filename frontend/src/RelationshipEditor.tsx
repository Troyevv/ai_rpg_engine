import {useEffect,useState} from 'react';
import {MoreHorizontal} from 'lucide-react';
import {toast} from 'sonner';
import {api} from './api';
import type {Save,Character,WorldRelation} from './types';
import {Button} from './components/ui/button';
import {Textarea} from './components/ui/textarea';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './components/ui/dialog';

const labels:Record<string,string>={trust:'Доверие',affection:'Привязанность',attraction:'Влечение',irritation:'Раздражение',fear:'Страх',jealousy:'Ревность',respect:'Уважение'};
type Edit={target_id:string;context:string;dimensions:Record<string,number>;delete?:boolean};
export function RelationshipEditor({save,card,refresh}:{save:Save;card:Character;refresh:()=>void}){
 const relations=Object.values(save.state.world?.relationships||{}).filter(r=>r.source_id===card.id);
 const targets=save.state.characters.filter(c=>c.id!==card.id);
 const [dimensions,setDimensions]=useState<string[]>([]);
 const [edit,setEdit]=useState<Edit|null>(null);
 const [busy,setBusy]=useState(false);
 useEffect(()=>{let active=true;api<string[]>('/relationships/dimensions').then(value=>{if(active)setDimensions(value)}).catch(()=>{});return()=>{active=false}},[]);
 const name=(id:string)=>save.state.characters.find(c=>c.id===id)?.name||id;
 const open=(r?:WorldRelation,remove=false)=>setEdit({target_id:r?.target_id||targets.find(c=>!relations.some(v=>v.target_id===c.id))?.id||'',context:r?.context||'',dimensions:Object.fromEntries(Object.entries(r?.dimensions||{}).filter(([,v])=>typeof v==='number')) as Record<string,number>,delete:remove});
 const persist=async()=>{if(!edit)return;setBusy(true);try{
  await api(`/saves/${save.id}/characters/${encodeURIComponent(card.id)}/relationships`,{...edit,revision:save.revision},'PATCH');
  await refresh();setEdit(null);toast.success('Отношение сохранено');
 }catch(e){toast.error((e as Error).message)}finally{setBusy(false)}};
 return <div className="motivation-editor">
  {relations.map(r=><div key={r.target_id} className="motivation-row"><p><strong>{card.name} → {name(r.target_id)}</strong><br/>{r.context}</p><details className="motivation-menu"><summary aria-label={`Действия с отношением к ${name(r.target_id)}`}><MoreHorizontal size={20}/></summary><div><Button variant="ghost" onClick={e=>{e.currentTarget.closest('details')?.removeAttribute('open');open(r)}}>Редактировать</Button><Button variant="ghost" onClick={e=>{e.currentTarget.closest('details')?.removeAttribute('open');open(r,true)}}>Удалить</Button></div></details></div>)}
  {!relations.length&&<p className="muted small">Отношения этого персонажа ещё не записаны.</p>}
  <Button variant="ghost" disabled={!targets.some(c=>!relations.some(r=>r.target_id===c.id))} onClick={()=>open()}>+ Добавить отношение</Button>
  <Dialog open={!!edit} onOpenChange={value=>{if(!value&&!busy)setEdit(null)}}><DialogContent><DialogHeader><DialogTitle>{edit?.delete?'Удалить отношение?':'Отношение персонажа'}</DialogTitle><DialogDescription>{edit?.delete?'Текущая запись будет удалена из этого прохождения.':'Меняется только направление от управляемого персонажа к выбранному персонажу.'}</DialogDescription></DialogHeader>
  {edit?.delete?<p>{card.name} → {name(edit.target_id)}</p>:<><label>К кому<select aria-label="Персонаж-адресат" value={edit?.target_id||''} disabled={!!relations.find(r=>r.target_id===edit?.target_id)} onChange={e=>setEdit(prev=>prev&&({...prev,target_id:e.target.value}))}>{targets.filter(c=>c.id===edit?.target_id||!relations.some(r=>r.target_id===c.id)).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label><Textarea aria-label="Контекст отношения" value={edit?.context||''} onChange={e=>setEdit(prev=>prev&&({...prev,context:e.target.value}))} placeholder="Как персонаж относится к нему сейчас и почему"/>{dimensions.map(key=><label key={key} className="relationship-dimension">{labels[key]||key}<input aria-label={labels[key]||key} type="number" min={-100} max={100} step="1" placeholder="Не задано" value={edit?.dimensions[key]??''} onChange={e=>setEdit(prev=>{if(!prev)return prev;const next={...prev.dimensions};if(e.target.value==='')delete next[key];else next[key]=Number(e.target.value);return {...prev,dimensions:next}})}/></label>)}</>}
  <div className="actions"><Button variant="ghost" disabled={busy} onClick={()=>setEdit(null)}>Отмена</Button><Button disabled={busy||!edit?.target_id||(!edit.delete&&!edit.context.trim())} onClick={()=>void persist()}>{edit?.delete?'Удалить':'Сохранить'}</Button></div></DialogContent></Dialog>
 </div>
}
