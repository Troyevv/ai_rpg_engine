import {useEffect,useRef,useState} from 'react';
import {Dialog,DialogContent,DialogTitle,DialogDescription} from '../components/ui/dialog';
import {Button} from '../components/ui/button';
import {api} from '../api';

type Item=Record<string,unknown>;
export type CreationTarget={kind:string;source?:string;revision:number};
const names:Record<string,string>={character:'персонажа',location:'место',relationship:'направленное отношение',fact:'факт',thread:'сюжетную линию',event:'событие',scene:'сцену',knowledge:'знание'};
/** Local form only. Opening, typing and cancelling never mutate the draft. */
export function CreateRecordDialog({wid,target,characters,facts,onClose,onCreated}:{wid:string;target:CreationTarget;characters:{id:string;name:string}[];facts:[string,Item][];onClose:()=>void;onCreated:(kind:string,id:string)=>Promise<void>}){
 const {kind,revision}=target;const alive=useRef(true);useEffect(()=>{alive.current=true;return()=>{alive.current=false}},[]);
 const [title,setTitle]=useState(''),[description,setDescription]=useState('');
 const [source,setSource]=useState(target.source||''),[destination,setDestination]=useState('');
 const [fact,setFact]=useState('');const [busy,setBusy]=useState(false),[error,setError]=useState('');const guard=useRef(false);
 const pair=kind==='relationship',belief=kind==='knowledge';
 const valid=pair?!!source&&!!destination&&source!==destination:belief?!!source&&!!fact:!!title.trim();
 const personSelect=(label:string,value:string,change:(value:string)=>void)=><label>{label}<select aria-label={label} value={value} onChange={e=>change(e.target.value)}><option value="">Выберите персонажа</option>{characters.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>;
 async function save(){
  if(guard.current||!valid)return;guard.current=true;setBusy(true);setError('');
  const value:Item=pair?{source_id:source,target_id:destination,context:description}:belief?{actor_id:source,fact_id:fact,status:'unknown'}:
   kind==='character'?{name:title.trim(),'fields.Биография':description}:kind==='location'?{name:title.trim(),text:description}:
   {[kind==='thread'?'description':'text']:[title.trim(),description.trim()].filter(Boolean).join('\n\n')};
  try {const result=await api<{entity_id:string}>(`/workspaces/${wid}/draft`,{revision,operation:'add',kind,value},'PATCH');if(alive.current){await onCreated(kind,result.entity_id);if(alive.current)onClose()}}
  catch(e){setError((e as Error).message)}finally{guard.current=false;setBusy(false)}
 }
 return <Dialog open onOpenChange={open=>{if(!open&&!busy)onClose()}}><DialogContent className="ww-create-dialog"><DialogTitle>Добавить {names[kind]||'запись'}</DialogTitle><DialogDescription>Запись появится в мире только после создания. Все введённые поля сохраняются одной версией.</DialogDescription><fieldset disabled={busy}>
 {pair||belief?personSelect(pair?'От кого':'Кто знает',source,setSource):<label>{kind==='character'?'Имя':'Название или краткое описание'}<input autoFocus value={title} onChange={e=>setTitle(e.target.value)}/></label>}
 {pair&&personSelect('К кому',destination,setDestination)}
 {belief&&<label>Факт<select value={fact} onChange={e=>setFact(e.target.value)}><option value="">Выберите факт</option>{facts.map(([id,f])=><option key={id} value={id}>{String(f.text)}</option>)}</select></label>}
 {!belief&&<label>{pair?'Контекст отношения':'Описание'}<textarea rows={5} value={description} onChange={e=>setDescription(e.target.value)}/></label>}
 </fieldset>{error&&<p role="alert">{error}</p>}<footer className="workshop-dialog-actions"><Button variant="ghost" disabled={busy} onClick={onClose}>Отмена</Button><Button disabled={busy||!valid} onClick={()=>void save()}>{busy?'Создаём…':'Создать запись'}</Button></footer></DialogContent></Dialog>;
}
