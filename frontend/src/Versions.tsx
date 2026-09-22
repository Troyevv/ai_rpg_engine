import {useEffect,useState} from "react";
import {toast} from "sonner";
import {api} from "./api";
import {Button} from "./components/ui/button";
import {Textarea} from "./components/ui/textarea";
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from "./components/ui/dialog";
import {Markdown} from "./Markdown";
interface Version {id:number;content:string;complete:boolean;created_at:string;reason:string;source_version_id:number|null}
interface History {active_id:number|null;versions:Version[]}
export function Versions({kind,owner,open,close,changed}:{kind:string;owner:string;open:boolean;close:()=>void;changed?:()=>void}){
 const [loading,setLoading]=useState(true);
 const [history,setHistory]=useState<History>({active_id:null,versions:[]});
 const [selected,setSelected]=useState<number>();const [content,setContent]=useState("");const [busy,setBusy]=useState(false);
 const load=async()=>{const h=await api<History>(`/documents/${kind}/${owner}`);setHistory(h);setSelected(h.active_id||undefined);setContent(h.versions.find(v=>v.id===h.active_id)?.content||"")};
 useEffect(()=>{if(open){setLoading(true);void load().catch(e=>toast.error(e.message)).finally(()=>setLoading(false))}},[open,kind,owner]);
 const commit=async(source?:number)=>{setBusy(true);try{await api(`/documents/${kind}/${owner}`,{content,expected_head:history.active_id,source_id:source});await load();changed?.();toast.success("Новая версия сохранена")}catch(e){toast.error((e as Error).message)}finally{setBusy(false)}};
 return <Dialog open={open} onOpenChange={v=>{if(!v)close()}}><DialogContent className="settings-dialog"><DialogHeader><DialogTitle>История версий · {kind==="prompt"?owner:kind==="idea"?"Сценарий":"Выжимка"}</DialogTitle><DialogDescription>Сохранение и откат создают новую версию. Старые записи остаются в истории. Новые промпты применяются к следующим запросам.</DialogDescription></DialogHeader>
 <label>Версия<select disabled={loading||busy} value={selected||""} onChange={e=>{const id=+e.target.value;setSelected(id);setContent(history.versions.find(v=>v.id===id)?.content||"")}}>{history.versions.map(v=><option key={v.id} value={v.id}>#{v.id} · {v.created_at} · {v.reason}{v.id===history.active_id?" · активная":""}{!v.complete?" · черновик/удалено":""}</option>)}</select></label>
 <details><summary>Просмотр выбранной версии</summary><Markdown text={content||"Документ пуст"}/></details>
 <Textarea disabled={loading||busy} aria-label="Содержимое версии" value={content} onChange={e=>setContent(e.target.value)} style={{minHeight:260}}/>
 <div className="actions"><Button disabled={busy||loading} onClick={()=>void commit()}>Сохранить новую версию</Button><Button variant="outline" disabled={busy||loading||!selected||selected===history.active_id} onClick={()=>{if(window.confirm("Сделать выбранную версию активной? Текущая останется в истории."))void commit(selected)}}>Откатить к выбранной</Button></div>
 </DialogContent></Dialog>
}
