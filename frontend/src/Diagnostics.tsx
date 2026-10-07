import {SectionTabs} from "./components/ui/section-tabs";
import {useEffect,useState} from "react";
import {toast} from "sonner";
import {api} from "./api";
import {Button} from "./components/ui/button";
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from "./components/ui/dialog";
import {Markdown} from "./Markdown";
import {Timing,stages} from './Timing';
export interface RequestRecord {
 id:string; job_id:string; stage:string; provider:string; model:string; thinking:string; status:string; created_at:string;
 input_tokens:number|null; output_tokens:number|null; cached_input_tokens:number|null; cost_usd:string|null;
 response_text?:string|null; duration?:number|null; finish_reason?:string|null; max_tokens?:number|null;
 pricing:{version:string;period?:string}|null;
 diagnostics:{selection?:{mode:string;characters:Record<string,number>;character_total:number;character_included?:Record<string,number>;knowledge?:Record<string,number>;semantic?:Record<string,unknown>;entities?:{entity_type:string;entity_id:string;semantic_similarity:number|null;selection_reasons:string[];selected:boolean;included:boolean}[];sections:Record<string,{selected:number;included?:number;total:number}>;narrative_continuity:number;previous_player_inputs:number;target_context_budget:number;hard_context_limit:number;target_exceeded:boolean}|null;estimated_tokens:number;overhead_tokens?:number;token_method?:string;parts:{name:string;role:string;estimated_tokens:number;content:string}[]};
 messages:{role:string;content:string}[];
}
interface Total {cost_usd:string;unknown_requests:number;input_tokens:number;output_tokens:number;cached_input_tokens:number}
interface RepairDiagnostic {repair_reason:string;repair_error_type:string;repair_error_code:string;stage:string;section?:string;index?:number;field?:string;entity?:string}
interface TurnDiagnostic {derivations?:{section:string;index?:number;code?:string;entity:string;origin:string|null;destination:string}[];repairs?:RepairDiagnostic[];id:number;sequence:number;active_variant_id:string;job_id:string|null;timing:Record<string,number>|null;warnings:{action?:string;type?:string;code?:string;section:string;index?:number;field?:string;entity?:string;reason:string}[];requests:RequestRecord[]}
interface Accounting {history_audit?:{section:string;code:string;reason:string}[];session_id:string|null;session:Total;game:Total;world:Total;requests:RequestRecord[];turns:TurnDiagnostic[]}
const money=(value:string|null)=>value===null?"неизвестно":`$${Number(value).toFixed(6)}`;
function RequestTotals({rows}:{rows:RequestRecord[]}){
 const sum=(key:'input_tokens'|'output_tokens'|'cached_input_tokens')=>`${rows.reduce((s,r)=>s+(r[key]??0),0).toLocaleString()}${rows.some(r=>r[key]==null)?' + неизвестно':''}`;
 return <div className="usage-grid">{[['Input',sum('input_tokens')],['Output',sum('output_tokens')],['Cache',sum('cached_input_tokens')],['LLM-вызовов',rows.length],['Стоимость',money(String(rows.reduce((s,r)=>s+Number(r.cost_usd??0),0)))+(rows.some(r=>r.cost_usd==null)?' + неизвестно':'')]].map(([k,v])=><section key={k}><span>{k}</span><strong>{v}</strong></section>)}</div>;
}
export function Diagnostics({saveId,workspaceId,jobId,open,onOpenChange}:{saveId?:number;workspaceId?:string;jobId?:string;open:boolean;onOpenChange:(v:boolean)=>void}) {
 const [data,setData]=useState<Accounting|null>(null);
 const [rows,setRows]=useState<RequestRecord[]>([]);
 const [selected,setSelected]=useState('');
 const [turnId,setTurnId]=useState('');
 const [jobDetails,setJobDetails]=useState<{timing_json?:string|null;warnings:TurnDiagnostic['warnings'];repairs?:RepairDiagnostic[]}|null>(null);
 const [tab,setTab]=useState('context');
 const [archive,setArchive]=useState<{id:number;reason:string;payload:string}[]>([]);
 const [busy,setBusy]=useState(false);
 const load=async()=>{
  setBusy(true);
  try {
   if(saveId){const a=await api<Accounting>(`/saves/${saveId}/accounting`);setData(a);setRows(a.requests);if(jobId)setJobDetails(await api(`/jobs/${jobId}`))}
   else if(workspaceId){setRows(await api<RequestRecord[]>(`/workspaces/${workspaceId}/requests`));setData(null)}
  }catch(e){toast.error((e as Error).message)}finally{setBusy(false)}
 };
 useEffect(()=>{if(open){setData(null);setRows([]);setSelected('');setTurnId('');setJobDetails(null);setTab('context');setArchive([]);void load()}},[open,saveId,workspaceId,jobId]);
 const turns=data?.turns||[];
 const turn=turnId==='all'?undefined:turns.find(t=>t.active_variant_id===turnId)||(jobId?turns.find(t=>t.job_id===jobId):turns[0]);
 const filtered=turnId==='all'?rows:turnId?turn?.requests||[]:jobId?rows.filter(r=>r.job_id===jobId):turn?.requests||rows;
 const timing=turn?.timing||(!turnId&&jobDetails?.timing_json?JSON.parse(jobDetails.timing_json):null);
 const warnings=turn?.warnings||(!turnId?jobDetails?.warnings:[])||[];
 const repairs=turn?.repairs||(!turnId?jobDetails?.repairs:[])||[];
 const request=filtered.find(r=>r.id===selected)||filtered[0];
 return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="settings-dialog diagnostics">
  <DialogHeader><DialogTitle>Диагностика</DialogTitle><DialogDescription>Снимки фактически отправленных запросов. Здесь есть GM-only данные и тайны мира.</DialogDescription></DialogHeader>
  <SectionTabs className="diagnostic-tabs" label="Раздел диагностики" tablist panelId="diagnostic-panel" value={tab} onChange={setTab} items={[{id:'context',label:'Контекст'},{id:'performance',label:'Производительность'},{id:'cost',label:'Расходы'}]}/>
  <Button variant="outline" disabled={busy} onClick={()=>void load()}>Обновить</Button>
  {!!data?.history_audit?.length&&<details className="delta-warnings"><summary>Аудит истории · ⚠ {data.history_audit.length}</summary><p>Исторические сведения неполны. Текущее состояние и сохранённые знания не отменены.</p>{data.history_audit.map((w,i)=><p key={i}><code>{w.section} · {w.code}</code><br/>{w.reason}</p>)}</details>}
  {turns.length>0&&<label>Ход<select aria-label="Ход диагностики" value={turnId==='all'?'all':turn?.active_variant_id||''} onChange={e=>{setTurnId(e.target.value);setSelected('')}}><option value="all">Все запросы прохождения</option>{turns.map(t=><option key={t.active_variant_id} value={t.active_variant_id}>#{t.sequence} · {t.timing?.total==null?'нет timing':t.timing.total.toFixed(1)+' с'}</option>)}</select></label>}
  <div role="tabpanel" id="diagnostic-panel" aria-labelledby={`diagnostic-panel-tab-${tab}`}>
  {tab==='performance'&&<>
   <h3>{turn?`Ход #${turn.sequence}`:'Выбранный вариант'}</h3><Timing timing={timing}/>
   <RequestTotals rows={filtered}/>
   <p className="small">LLM памяти: {filtered.filter(r=>r.stage==='memory').length} · Narrative: {filtered.filter(r=>r.stage==='narrative').length} · Extraction: {filtered.filter(r=>r.stage==='extraction').length} · Living World: {filtered.filter(r=>r.stage.startsWith('world_simulation')).length}</p>
   {filtered.some(r=>isRepair(r.stage))?<section><h4>Причина repair</h4>{repairs.length?repairs.map((r,i)=><details key={i} open><summary>{r.stage} · {r.repair_error_code}</summary><p>{r.repair_error_type}: {r.repair_reason}</p><p>{r.section} {r.index!=null?`[${r.index}]`:''} {r.field} {r.entity}</p></details>):<p>Причина не сохранена для старого хода.</p>}</section>:<p>Repair: не выполнялся</p>}
   <RepairStatistics turns={turns}/>
   {!!turn?.derivations?.length&&<details className="delta-derivations"><summary>DERIVE · Вычислено движком (без LLM)</summary>{turn.derivations.map((d,i)=><p key={i}>{d.entity}: {d.origin??'неизвестное место'} → {d.destination}{d.code==='final_location_derived_from_scene'?' (из конечной сцены)':d.code==='initial_location_derived_from_scene'?' (из исходной сцены)':''}</p>)}</details>}
   {!!warnings.length&&<section className="delta-warnings"><h4>Предупреждения WorldState · ⚠ {warnings.length}</h4>{warnings.map((w,i)=><p key={i}><strong>{w.section}{w.index!=null?`[${w.index}]`:''} {w.entity} {w.field}</strong><br/>{w.code&&<code>{w.code} · </code>}{w.reason}<br/>{w.action==='correct_field'?'Использовано каноническое значение.':w.action==='drop_record'?'Запись отброшена.':w.field?'Поле отброшено.':'Запись отброшена.'} Остальные изменения применены.</p>)}</section>}
   <h3>Последние ходы</h3><div className="diagnostic-history">{turns.slice(0,30).map(t=><button key={t.active_variant_id} aria-pressed={t===turn} onClick={()=>{setTurnId(t.active_variant_id);setSelected('')}}><strong>#{t.sequence}</strong><span>{t.timing?.total==null?'—':t.timing.total.toFixed(1)+' с'}</span><span>{t.requests.length} LLM</span><span>{money(String(t.requests.reduce((s,r)=>s+Number(r.cost_usd??0),0)))}{t.requests.some(r=>r.cost_usd==null)?' + ?':''}</span>{t.requests.some(r=>isRepair(r.stage))&&<span>repair</span>}{!!t.warnings.length&&<span>⚠ {t.warnings.length}</span>}</button>)}</div>
   {!turns.length&&<p className="muted">Сохранённых ходов пока нет.</p>}
  </>}
  {tab==='cost'&&<>
   {data&&<div className="usage-grid">{([["Текущая сессия",data.session],["Всё прохождение",data.game],["Мир: все прохождения",data.world]] as const).map(([name,v])=><section key={name}><span>{name}</span><strong>{money(v.cost_usd)}</strong><small>input {v.input_tokens} · output {v.output_tokens} · cache {v.cached_input_tokens}</small>{v.unknown_requests>0&&<small>Без стоимости: {v.unknown_requests} запросов; итог неполный</small>}</section>)}</div>}
   <p className="muted small">Стоимость по сохранённому тарифу USD, включая память, повторы и неактивные варианты. Списание провайдера может отличаться.</p>
   {saveId&&<Button variant="ghost" disabled={busy} onClick={async()=>{try{await api(`/saves/${saveId}/sessions`,{});await load()}catch(e){toast.error((e as Error).message)}}}>Начать новую сессию расходов</Button>}
   <h3>{turn?`Ход #${turn.sequence}`:'Выбранные запросы'}</h3><RequestTotals rows={filtered}/>
   <details><summary>Расходы отдельных LLM requests</summary>{filtered.map(r=><div key={r.id}><p>{stages[r.stage]||r.stage} · {r.model} · {money(r.cost_usd)}</p><small>Input {r.input_tokens??'—'} · Output {r.output_tokens??'—'} · Cache {r.cached_input_tokens??'—'}</small></div>)}</details>
  </>}
  {tab==='context'&&<>
   <label>Запрос<select aria-label="Запрос диагностики" value={request?.id||''} onChange={e=>setSelected(e.target.value)}>{filtered.map(r=><option key={r.id} value={r.id}>{r.created_at} · {stages[r.stage]||r.stage} · {r.model}</option>)}</select></label>
   {!request&&<p className="muted">Запросов пока нет. У старых ходов usage и точный контекст не восстанавливаются задним числом.</p>}
   {request&&<>
    <p>{stages[request.stage]||request.stage} · {request.provider} / {request.model} · {request.status}</p>
    <RequestTotals rows={[request]}/>
    <p className="muted small">Контекст: ≈{request.diagnostics.estimated_tokens} токенов · max_tokens: {request.max_tokens??'—'} · Finish: {request.finish_reason??'—'} · Время: {request.duration==null?'—':request.duration.toFixed(1)+' с'} · Thinking: {request.thinking}</p>
    <p className="muted small">Тариф: {request.pricing?.version||'неизвестен'} {request.pricing?.period||''}. {request.diagnostics.token_method||'Размер контекста оценочный; usage API выше — фактический.'}</p>
    {request.diagnostics.selection&&<section aria-label="Context Selection"><h4>Context Selection · {request.diagnostics.selection.mode}</h4>
     <p className="small">Персонажи: выбрано / включено / всего</p><div className="usage-grid">{Object.entries(request.diagnostics.selection.characters).map(([mode,count])=><section key={mode}><span>{mode}</span><strong>{count} / {request.diagnostics.selection!.character_included?.[mode]??count} / {request.diagnostics.selection!.character_total}</strong></section>)}</div>
     <table><thead><tr><th>Данные</th><th>Выбрано / включено / всего</th></tr></thead><tbody>{Object.entries(request.diagnostics.selection.sections).map(([name,v])=><tr key={name}><td>{name}</td><td>{v.selected} / {v.included??v.selected} / {v.total}</td></tr>)}</tbody></table>
     {request.diagnostics.selection.knowledge&&<p>Knowledge: {Object.entries(request.diagnostics.selection.knowledge).map(([k,v])=>`${k}: ${v}`).join(' · ')}</p>}
     {request.diagnostics.selection.semantic&&<details><summary>Semantic retrieval · производительность</summary><pre className="context-content">{JSON.stringify(request.diagnostics.selection.semantic,null,2)}</pre></details>}
     {request.diagnostics.selection.entities&&<details><summary>Причины выбора сущностей</summary><table><thead><tr><th>Сущность</th><th>Similarity / reasons</th><th>Выбрано / включено</th></tr></thead><tbody>{request.diagnostics.selection.entities.map(e=><tr key={`${e.entity_type}:${e.entity_id}`}><td>{e.entity_type}: {e.entity_id}</td><td>{e.semantic_similarity?.toFixed(3)??'—'} · {e.selection_reasons.join(', ')}</td><td>{e.selected?'да':'нет'} / {e.included?'да':'нет'}</td></tr>)}</tbody></table></details>}
     <p>Narrative continuity: {request.diagnostics.selection.narrative_continuity} · Previous player inputs: {request.diagnostics.selection.previous_player_inputs}</p>
     <p>Мягкая цель: {request.diagnostics.selection.target_context_budget} · Предел входа: {request.diagnostics.selection.hard_context_limit}{request.diagnostics.selection.target_exceeded?' · Цель превышена для сохранения сцены':''}</p>
    </section>}
    {request.response_text!=null&&<details><summary>Фактический ответ extraction</summary><pre className="context-content">{request.response_text}</pre></details>}
    {request.messages.map((m,i)=><details key={i}><summary>{i+1}. {request.diagnostics.parts?.[i]?.name||m.role} · ≈{request.diagnostics.parts?.[i]?.estimated_tokens??'—'} токенов</summary><pre className="context-content">{m.content}</pre></details>)}
   </>}
   {saveId&&<><Button variant="ghost" onClick={async()=>{try{setArchive(await api(`/saves/${saveId}/archive`))}catch(e){toast.error((e as Error).message)}}}>Показать архив откатов</Button>{archive.map(r=>{const p=JSON.parse(r.payload);return <details key={r.id}><summary>Ход {p.sequence} · {r.reason}</summary><div className="player-action">{p.user_text}</div><Markdown text={p.assistant_text}/></details>})}</>}
  </>}
  </div>
 </DialogContent></Dialog>
}

const isRepair=(stage:string)=>stage==='extraction_repair'||stage==='world_simulation_repair';
function RepairStatistics({turns}:{turns:TurnDiagnostic[]}){
 const recent=turns.slice(0,30);
 const repaired=recent.filter(t=>t.requests.some(r=>isRepair(r.stage))).length;
 const unknown=recent.filter(t=>!t.requests.length).length;
 const reasons:Record<string,number>={},sanitized:Record<string,number>={};
 for(const t of recent){
  for(const request of t.requests.filter(r=>isRepair(r.stage))){
   const code=t.repairs?.find(r=>r.stage===request.stage)?.repair_error_code||'unknown';
   reasons[code]=(reasons[code]||0)+1;
  }
  for(const w of t.warnings.filter(w=>w.type==='sanitized_delta')){const code=w.code||'legacy_warning';sanitized[code]=(sanitized[code]||0)+1;}
 }
 const known=recent.length-unknown;
 return <details><summary>Статистика extraction · последние {recent.length} ходов</summary><p>Ходов: {recent.length} · Без repair: {known-repaired} · С repair: {repaired} · Нет данных: {unknown}</p><p>Repair rate: {known?`${(100*repaired/known).toFixed(1)}%`:'—'} (по ходам с сохранёнными запросами)</p><h4>Причины LLM repair</h4>{Object.entries(reasons).map(([code,n])=><p key={code}>{code}: {n}</p>)}<h4>Deterministic sanitization (без LLM)</h4>{Object.entries(sanitized).map(([code,n])=><p key={code}>{code}: {n}</p>)}</details>;
}
