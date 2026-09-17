import {useState} from 'react';
import {MoreHorizontal} from 'lucide-react';
import {toast} from 'sonner';
import {api} from './api';
import type {Save,Character} from './types';
import {Button} from './components/ui/button';
import {Textarea} from './components/ui/textarea';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './components/ui/dialog';

type Entry={kind:'goal'|'intention';index:number;remove?:boolean};
export function MotivationEditor({save,card,refresh}:{save:Save;card:Character;refresh:()=>void}){
 const current=save.state.world?.characters[card.id];
 const goal=current?.short_goal??card.fields['Чего хочет']??'';
 const goals=current?.goals??(goal?[goal]:[]);
 const intentions=current?.intentions??[];
 const [entry,setEntry]=useState<Entry|null>(null);
 const [text,setText]=useState('');const [busy,setBusy]=useState(false);
 const open=(value:Entry,initial='')=>{setEntry(value);setText(initial)};
 const persist=async()=>{
  if(!entry)return;setBusy(true);
  const nextGoals=[...goals],nextIntentions=[...intentions];
  const next=entry.kind==='goal'?nextGoals:nextIntentions;
  if(entry.remove)next.splice(entry.index,1);
  else if(entry.index<0)next.push(text.trim());else next[entry.index]=text.trim();
  try{
   await api(`/saves/${save.id}/characters/${encodeURIComponent(card.id)}/motivation`,{revision:save.revision,goals:nextGoals,intentions:nextIntentions},'PATCH');
   await refresh();setEntry(null);toast.success('Сохранено');
  }catch(e){toast.error((e as Error).message)}finally{setBusy(false)}
 };
 const row=(value:string,kind:Entry['kind'],index:number)=><div className="motivation-row" key={`${kind}-${index}`}>
  <p>{value}</p><details className="motivation-menu"><summary aria-label={kind==='goal'?`Действия с целью ${index+1}`:`Действия с намерением ${index+1}`}><MoreHorizontal size={20}/></summary><div>
   <Button variant="ghost" onClick={e=>{e.currentTarget.closest('details')?.removeAttribute('open');open({kind,index},value)}}>Редактировать</Button>
   <Button variant="ghost" onClick={e=>{e.currentTarget.closest('details')?.removeAttribute('open');open({kind,index,remove:true},value)}}>Удалить</Button>
  </div></details>
 </div>;
 return <div className="motivation-editor">
  <h4>Цели</h4>{goals.map((value,i)=>row(value,'goal',i))}<Button variant="ghost" disabled={goals.length>=20} onClick={()=>open({kind:'goal',index:-1})}>+ Добавить цель</Button>
  <h4>Намерения</h4>{intentions.map((value,i)=>row(value,'intention',i))}
  <Button variant="ghost" disabled={intentions.length>=20} onClick={()=>open({kind:'intention',index:-1})}>+ Добавить намерение</Button>
  <Dialog open={!!entry} onOpenChange={v=>{if(!v&&!busy)setEntry(null)}}><DialogContent>
   <DialogHeader><DialogTitle>{entry?.remove?'Удалить запись?':entry?.kind==='goal'?'Цель персонажа':'Намерение персонажа'}</DialogTitle><DialogDescription>{entry?.remove?'Запись будет удалена из текущего состояния. Отменить это действие кнопкой нельзя.':'Изменение сохранится в этом прохождении и будет учтено в следующем ходе.'}</DialogDescription></DialogHeader>
   {entry?.remove?<p className="motivation-delete-text">{text}</p>:<Textarea aria-label="Текст цели или намерения" value={text} maxLength={entry?.kind==='goal'?4000:2000} onChange={e=>setText(e.target.value)} autoFocus/>}
   <div className="actions"><Button variant="ghost" disabled={busy} onClick={()=>setEntry(null)}>Отмена</Button><Button disabled={busy||(!entry?.remove&&!text.trim())} onClick={()=>void persist()}>{entry?.remove?'Удалить':'Сохранить'}</Button></div>
  </DialogContent></Dialog>
 </div>;
}
