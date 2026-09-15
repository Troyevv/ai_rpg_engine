import {useEffect,useState} from "react";
import {toast} from "sonner";
import {api} from "./api";
import {Button} from "./components/ui/button";
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from "./components/ui/dialog";
import {Markdown} from "./Markdown";
export interface RequestRecord {
  id:string; job_id:string; stage:string; model:string; thinking:string; status:string; created_at:string;
  input_tokens:number|null; output_tokens:number|null; cached_input_tokens:number|null; cost_usd:string|null;
  pricing:{version:string;period?:string}|null;
  diagnostics:{estimated_tokens:number;overhead_tokens?:number;token_method?:string;parts:{name:string;role:string;estimated_tokens:number;content:string}[]};
  messages:{role:string;content:string}[];
}
interface Total {cost_usd:string;unknown_requests:number;input_tokens:number;output_tokens:number;cached_input_tokens:number}
interface Accounting {session_id:string|null;session:Total;game:Total;world:Total;requests:RequestRecord[]}
const money=(value:string|null)=>value===null?"неизвестно":`$${Number(value).toFixed(6)}`;
export function Diagnostics({saveId,workspaceId,jobId,open,onOpenChange}:{saveId?:number;workspaceId?:string;jobId?:string;open:boolean;onOpenChange:(v:boolean)=>void}) {
 const [data,setData]=useState<Accounting|null>(null);
 const [rows,setRows]=useState<RequestRecord[]>([]);
 const [selected,setSelected]=useState("");
 const [archive,setArchive]=useState<{id:number;reason:string;payload:string}[]>([]);
 const [busy,setBusy]=useState(false);
 const load=async()=>{
  setBusy(true);
  try {
   if(saveId){const a=await api<Accounting>(`/saves/${saveId}/accounting`);setData(a);setRows(a.requests)}
   else if(workspaceId){setRows(await api<RequestRecord[]>(`/workspaces/${workspaceId}/requests`));setData(null)}
  }catch(e){toast.error((e as Error).message)}finally{setBusy(false)}
 };
 useEffect(()=>{if(open){setSelected("");setArchive([]);void load()}},[open,saveId,workspaceId,jobId]);
 const filtered=jobId?rows.filter(r=>r.job_id===jobId):rows;
 const request=filtered.find(r=>r.id===selected)||filtered[0];
 return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="settings-dialog diagnostics">
  <DialogHeader><DialogTitle>Контекст ведущего и расходы</DialogTitle><DialogDescription>Снимки фактически отправленных запросов. Здесь есть тайны мира.</DialogDescription></DialogHeader>
  <div className="actions"><Button variant="outline" disabled={busy} onClick={()=>void load()}>Обновить</Button>
   {saveId&&<Button variant="ghost" disabled={busy} onClick={async()=>{try{await api(`/saves/${saveId}/sessions`,{});await load()}catch(e){toast.error((e as Error).message)}}}>Начать новую сессию расходов</Button>}
  </div>
  {data&&<div className="usage-grid">{([["Текущая сессия",data.session],["Всё прохождение",data.game],["Мир: все прохождения",data.world]] as const).map(([name,v])=><section key={name}><span>{name}</span><strong>{money(v.cost_usd)}</strong><small>input {v.input_tokens} · output {v.output_tokens} · cache {v.cached_input_tokens}</small>{v.unknown_requests>0&&<small>Без стоимости: {v.unknown_requests} запросов; итог неполный</small>}</section>)}</div>}
  <p className="muted small">Стоимость — расчёт по сохранённому тарифу USD, включая обработку мира, память, повторы и неактивные варианты. Списание в кабинете провайдера может отличаться. Сессия сохраняется до нажатия «Начать новую сессию».</p>
  <p>Запросов {jobId?"этого варианта":"в списке"}: {filtered.length} · Сумма: {money(String(filtered.reduce((s,r)=>s+Number(r.cost_usd||0),0)))}{filtered.some(r=>r.cost_usd===null)&&" + запросы с неизвестной стоимостью"}</p>
  <label>Запрос<select value={request?.id||""} onChange={e=>setSelected(e.target.value)}>{filtered.map(r=><option key={r.id} value={r.id}>{r.created_at} · {r.stage} · {r.model} · {money(r.cost_usd)}</option>)}</select></label>
  {!request&&<p className="muted">Запросов пока нет. У старых ходов usage и точный контекст не восстанавливаются задним числом.</p>}
  {request&&<>
   <p>{request.stage} · {request.status} · Thinking {request.thinking} · {money(request.cost_usd)}</p>
   <div className="usage-grid">{[["Input",request.input_tokens],["Output",request.output_tokens],["Cached input",request.cached_input_tokens]].map(([k,v])=><section key={String(k)}><span>{k}</span><strong>{v??"неизвестно"}</strong></section>)}</div>
   <p className="muted small">Тариф: {request.pricing?.version||"неизвестен"} {request.pricing?.period||""}. Размер контекста до отправки: ≈{request.diagnostics.estimated_tokens} токенов, включая служебный резерв {request.diagnostics.overhead_tokens??256}.</p>
   <p className="muted small">{request.diagnostics.token_method||"Размеры частей оценочные; usage API выше — фактический."}</p>
   {(request.diagnostics.parts.length?request.diagnostics.parts:request.messages.map(m=>({name:m.role,role:m.role,content:m.content,estimated_tokens:0}))).map((p,i)=><details key={i}><summary>{p.name.slice(0,100)} · ≈{p.estimated_tokens} токенов</summary><pre className="context-content">{p.content}</pre></details>)}
  </>}
  {saveId&&<><Button variant="ghost" onClick={async()=>{try{setArchive(await api(`/saves/${saveId}/archive`))}catch(e){toast.error((e as Error).message)}}}>Показать архив откатов</Button>
  {archive.map(r=>{const p=JSON.parse(r.payload);return <details key={r.id}><summary>Ход {p.sequence} · {r.reason}</summary><div className="player-action">{p.user_text}</div><Markdown text={p.assistant_text}/></details>})}</>}
 </DialogContent></Dialog>
}
