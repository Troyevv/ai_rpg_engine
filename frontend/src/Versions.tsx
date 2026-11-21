import {DraftDialog} from './components/ui/draft-dialog';
import { Choice } from "@/components/ui/choice";
import {useEffect,useState} from "react";
import {toast} from "sonner";
import {api} from "./api";
import {Button} from "./components/ui/button";
import {Textarea} from "./components/ui/textarea";
import {Dialog,DialogContent,DialogTrigger,DialogHeader,DialogTitle,DialogDescription} from "./components/ui/dialog";
import {Markdown} from "./Markdown";
interface Version {id:number;content:string;complete:boolean;created_at:string;reason:string;source_version_id:number|null}
interface History {template?:string;prompt_origin?:string;active_id:number|null;versions:Version[]}
export function Versions({kind,owner,open,close,changed}:{kind:string;owner:string;open:boolean;close:()=>void;changed?:()=>void}){
 const [loading,setLoading]=useState(true);
 const [rollback,setRollback]=useState(false);
 const [history,setHistory]=useState<History>({active_id:null,versions:[]});
 const [selected,setSelected]=useState<number>();const [content,setContent]=useState("");const [busy,setBusy]=useState(false);
 const load=async()=>{const h=await api<History>(`/documents/${kind}/${owner}`);setHistory(h);setSelected(h.active_id||undefined);setContent(h.versions.find(v=>v.id===h.active_id)?.content||"")};
 useEffect(()=>{if(open){setLoading(true);void load().catch(e=>toast.error(e.message)).finally(()=>setLoading(false))}},[open,kind,owner]);
 const commit=async(source?:number)=>{setBusy(true);try{await api(`/documents/${kind}/${owner}`,{content,expected_head:history.active_id,source_id:source});await load();changed?.();toast.success("Новая версия сохранена")}catch(e){toast.error((e as Error).message)}finally{setBusy(false)}};
 return <DraftDialog dirty={content!==(history.versions.find(v=>v.id===selected)?.content||'')} open={open} onOpenChange={v=>{if(!v)close()}}><DialogContent className="settings-dialog"><DialogHeader><DialogTitle>История версий · {kind==="prompt"?owner:kind==="idea"?"Сценарий":"Выжимка"}</DialogTitle><DialogDescription>Сохранение и откат создают новую версию. Старые записи остаются в истории. Новые промпты применяются к следующим запросам.</DialogDescription></DialogHeader>
 <label>Версия<Choice disabled={loading||busy} value={selected||""} onValueChange={selectedValue => {const id=+selectedValue;setSelected(id);setContent(history.versions.find(v=>v.id===id)?.content||"")}}>{history.versions.map(v=><option key={v.id} value={v.id}>#{v.id} · {v.created_at} · {v.reason}{v.id===history.active_id?" · активная":""}{!v.complete?" · черновик/удалено":""}</option>)}</Choice></label>
 <details><summary>Просмотр выбранной версии</summary><Markdown text={content||"Документ пуст"}/></details>
 {history.template && <div>{owner==="draft_world_prompt.md"?<p>{history.prompt_origin==="bundled"?"Активен актуальный встроенный промпт генерации.":history.prompt_origin==="historical_builtin"?"Активна историческая версия встроенного промпта.":"Активен авторский промпт. Его совместимость с текущим форматом мира не проверена."} Вы можете сравнить шаблон и сохранить новую версию.</p>:<p>Технический контракт новых ходов задаёт Runtime. Авторские дополнения редактируются в extraction_author.md. Старые версии доступны ниже.</p>}<details><summary>Актуальный шаблон {owner==="draft_world_prompt.md"?"генерации мира":"Extraction"}</summary><Markdown text={history.template}/></details>{content!==history.template&&<Button variant="outline" onClick={()=>setContent(history.template!)}>Подставить актуальный шаблон для сохранения</Button>}</div>}
 <Textarea readOnly={!!history.template&&owner==="state_update_prompt.md"} disabled={loading||busy} aria-label="Содержимое версии" value={content} onChange={e=>setContent(e.target.value)} style={{minHeight:260}}/>
 <div className="actions">
   <Button disabled={busy||loading} onClick={()=>void commit()}>Сохранить новую версию</Button>
   <Dialog open={rollback} onOpenChange={setRollback}>
     <DialogTrigger asChild><Button variant="outline" disabled={busy||loading||!selected||selected===history.active_id}>Откатить к выбранной</Button></DialogTrigger>
     <DialogContent><DialogHeader><DialogTitle>Восстановить версию № {selected}?</DialogTitle>
       <DialogDescription>Выбранная версия станет активной. Текущая сохранится в истории.</DialogDescription></DialogHeader>
       <div className="actions"><Button variant="outline" onClick={()=>setRollback(false)}>Отмена</Button>
         <Button disabled={busy} onClick={()=>{setRollback(false);void commit(selected)}}>Восстановить версию</Button></div>
     </DialogContent>
   </Dialog>
 </div>
 </DialogContent></DraftDialog>
}
