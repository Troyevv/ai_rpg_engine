import {useEffect,useRef,useState} from 'react';
import {api} from '../api';
import {Button} from '../components/ui/button';
import {Choice} from '../components/ui/choice';
import {Dialog,DialogContent,DialogHeader,DialogDescription,DialogTitle,DialogTrigger} from '../components/ui/dialog';

type Saved = {workspace_id:string;version_id:number};
export type Package = {base_hash:string;recovered?:Saved|null};
type Preview = {base_version:number;revision:number;mode:'current'|'copy';rationale:string;changes:string[];characters:number;locations:number;gaps:{name:string;fields:string[]}[]};

export function CreativeRecovery({workspace,job,packages,onOpen}:{workspace:string;job:string;packages:Package[];onOpen:(id:string)=>void}) {
 const [open,setOpen]=useState(false),[selected,setSelected]=useState(packages[0].base_hash);
 const [preview,setPreview]=useState<Preview|null>(null),[saved,setSaved]=useState<Saved|null>(null);
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[attempt,setAttempt]=useState(0);
 const submitting=useRef(false);
 const url=`/workspaces/${workspace}/draft/creative/${job}/${selected}`;
 useEffect(()=>{
   if(!open)return;
   const abort=new AbortController();
   setPreview(null);setError('');setSaved(null);
   api<Preview|Saved>(url,undefined,'GET',abort.signal).then(value=>{
     if(!abort.signal.aborted){if('workspace_id' in value)setSaved(value);else setPreview(value)}
   }).catch(e=>{if(!abort.signal.aborted)setError(e.message)});
   return ()=>abort.abort();
 },[open,url,attempt]);
 async function apply(){
   if(!preview||submitting.current)return;
   submitting.current=true;setBusy(true);setError('');
   try{setSaved(await api<Saved>(url,{revision:preview.revision,destination:preview.mode}))}
   catch(e){setPreview(null);setError((e as Error).message)}
   finally{submitting.current=false;setBusy(false)}
 }
 return <Dialog open={open} onOpenChange={v=>{if(!submitting.current)setOpen(v)}}>
   <DialogTrigger asChild><Button variant="outline">Восстановить полученное дополнение</Button></DialogTrigger>
   <DialogContent className="creative-recovery"><DialogHeader><DialogTitle>Сохранённое дополнение</DialogTitle>
   <DialogDescription>Предпросмотр собирается из уже полученного ответа. Обращение к модели не требуется.</DialogDescription></DialogHeader>
   <div className="creative-recovery-body">
   {packages.length>1&&<label>Полученный пакет<Choice aria-label="Полученный пакет" value={selected} disabled={busy} onValueChange={value=>{setPreview(null);setSaved(null);setSelected(value)}}>{packages.map((p,i)=><option key={p.base_hash} value={p.base_hash}>Дополнение {i+1}</option>)}</Choice></label>}
   {error?<div role="alert"><p>{error}</p><Button onClick={()=>setAttempt(n=>n+1)}>Обновить предпросмотр</Button></div>:
    saved?<div role="status"><p>Дополнение сохранено в версии № {saved.version_id}.</p><Button onClick={()=>{setOpen(false);onOpen(saved.workspace_id)}}>Открыть восстановленный мир</Button></div>:
    preview?<><p>{preview.rationale}</p><p>После применения · персонажей {preview.characters} · мест {preview.locations}</p>
    <details><summary>Изменения ({preview.changes.length})</summary><ul>{preview.changes.map((c,i)=><li key={i}>{c}</li>)}</ul></details>
    {!!preview.gaps.length&&<details><summary>Поля для просмотра</summary><ul>{preview.gaps.map(g=><li key={g.name}>{g.name} — {g.fields.join(', ')}</li>)}</ul></details>}
    <p>{preview.mode==='copy'?'Текущий черновик изменился. Дополнение можно открыть в отдельной копии исходной версии. Все последующие правки останутся в текущем черновике.':'Основа совпадает с текущим черновиком. Применение сохранит новую версию.'}</p>
    <Button disabled={busy} onClick={()=>void apply()}>{busy?'Сохраняем…':preview.mode==='copy'?'Создать отдельную копию':'Применить дополнение'}</Button></>:<p role="status">Проверяем сохранённый ответ…</p>}
   </div></DialogContent></Dialog>
}
