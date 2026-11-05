import {useEffect, useRef, useState} from 'react';
import {WandSparkles, Plus, Minus, Pencil, Check, History, ArrowRight} from 'lucide-react';
import {api, download} from './api';
import {Button} from './components/ui/button';
import {Textarea} from './components/ui/textarea';
import {Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription} from './components/ui/dialog';
import {RuntimeValue, runtimeLabels, resolver} from './runtimePresentation';
import {active, type Job, type Preferences} from './types';
import './styles/world-ai-editor.css';

type Diff = {section:string;id:string;name:string;operation:'add'|'replace'|'remove';fields:{field:string;before:unknown;after:unknown}[]};
type Edit = {id:string;status:string;instruction:string;stale:boolean;base_version:number;applied_version?:number;error:string;
  references?:Parameters<typeof resolver>[0];
  requests?:{id:string;stage:string;status:string;input_tokens:number|null;output_tokens:number|null;cost_usd:string|null}[];
  proposal?:{rationale:string;conflicts?:string[];changes:{path:string;reason:string}[]};diff?:Diff[];conflicts?:string[];
  review?:{status:string;issues:{message:string;severity?:string}[]}};
type Edits = {edits:Edit[];started:boolean};
const sectionNames:Record<string,string>={characters:'Карточки персонажей',locations:'Места',campaign:'Замысел мира',
 'world/characters':'Состояние персонажей','world/objective_relations':'Родство и социальные связи',
 'world/relationships':'Направленные отношения','world/organizations':'Организации','world/roles':'Профессии и роли',
 'world/knowledge':'Знания','world/facts':'Факты и тайны','world/events':'Предыстория','world/threads':'Сюжетные линии'};
const operations={add:'Добавление',replace:'Изменение',remove:'Удаление'};
const statuses:Record<string,string>={preview:'Ожидает решения',accepted:'Применено',rejected:'Отклонено',running:'Подготовка',error:'Запрос прерван',stopped:'Остановлено'};

type EditorProps = {
 wid:string;revision:number;job:Job|null;locked:boolean;prefs:Preferences;apiKey:string;
 title?:string;version?:number|null;example?:string;onHistory?:(version:number)=>void;onObject?:(section:string,id:string)=>void;
 onJob:(job:Job)=>void;refresh:()=>Promise<void>;resolve:ReturnType<typeof resolver>;
};

// Own the workspace boundary here: callers need not remember a React key.
export function WorldAIEditor(props:EditorProps) {
 return <WorkspaceEditor key={props.wid} {...props}/>;
}

function WorkspaceEditor({wid,revision,job,locked,prefs,apiKey,onJob,refresh,resolve,title,version,example,onHistory,onObject}:EditorProps) {
 const storageKey=`world-editor:${wid}`;
 const [instruction,setInstruction]=useState(()=>localStorage.getItem(storageKey)||example||'');
 const textarea=useRef<HTMLTextAreaElement>(null);
 const [replacement,setReplacement]=useState<string|null>(null);
 const useExample=(text:string)=>{if(instruction.trim())setReplacement(text);else{setInstruction(text);textarea.current?.focus()}};
 const [data,setData]=useState<Edits>({edits:[],started:false});
 const [error,setError]=useState('');const [busy,setBusy]=useState(false);
 const [selected,setSelected]=useState<string|null>(null);
 const [confirm,setConfirm]=useState(false);const [conflicts,setConflicts]=useState(false);const [warnings,setWarnings]=useState(false);
 const acceptButton=useRef<HTMLButtonElement>(null);
 const guard=useRef(false);const requestId=useRef<string|null>(null);const alive=useRef(true);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false}},[]);
 useEffect(()=>{localStorage.setItem(storageKey,instruction)},[storageKey,instruction]);
 const load=async()=>{const next=await api<Edits>(`/workspaces/${wid}/draft/edits?author=true`);if(alive.current)setData(next)};
 useEffect(()=>{const controller=new AbortController();void api<Edits>(`/workspaces/${wid}/draft/edits?author=true`,undefined,'GET',controller.signal)
  .then(next=>{if(!controller.signal.aborted)setData(next)}).catch(e=>{if(!controller.signal.aborted)setError(e.message)});return()=>controller.abort()},[wid,revision,job?.status]);
 const execute=async(fn:()=>Promise<void>)=>{if(guard.current)return;guard.current=true;setBusy(true);setError('');try{await fn()}catch(e){if(alive.current)setError((e as Error).message)}finally{guard.current=false;if(alive.current)setBusy(false)}};
 const current=data.edits.find(e=>e.id===selected)||data.edits[0];
 const changed=current?.diff||[];
 const previewResolve=current?.references ? resolver(current.references) : resolve;
 const destructive=!!current?.conflicts?.length||changed.some(d=>d.operation==='remove');
 const issues=current?.review?.issues||[];const blocked=!!current?.proposal?.conflicts?.length||issues.some(i=>(i.severity||'blocker')==='blocker');
 const disabled=busy||locked;
 const samePreview=current?.status==='preview'&&!current.stale&&current.instruction===instruction;
 useEffect(()=>{if(job && !active(job))requestId.current=null},[job?.status]);
 const decision=(choice:'accept'|'reject')=>execute(async()=>{
  await api(`/workspaces/${wid}/draft/edits/${current.id}`,{revision,decision:choice,accept_conflicts:conflicts,accept_warnings:warnings});
  if(alive.current){setConfirm(false);requestId.current=null;await load();await refresh()}
 });
 return <section className="world-ai-editor" aria-labelledby="world-ai-title">
  <div className="ai-editor-heading"><WandSparkles aria-hidden="true"/><div><p className="eyebrow">Изменения по вашему замыслу</p><h3 id="world-ai-title">AI-редактор мира</h3></div></div>
  <p>Опишите любые связанные изменения. Сначала вы увидите предложение и результаты проверки, затем решите, что сохранить.</p>
  <div className="ww-ai-columns"><div className="ww-ai-compose"><p className="ww-eyebrow">{title} · версия #{version}</p><ol className="ww-ai-steps"><li>Замысел</li><li>Предложение</li><li>Ваше решение</li></ol>
  {data.started && <p role="status">Изменения войдут в новое прохождение. Начатая игра останется без изменений.</p>}
  <>
   <label htmlFor="world-ai-instruction">Что изменить в мире?</label>
   <Textarea ref={textarea} id="world-ai-instruction" value={instruction} disabled={busy||active(job)} onChange={e=>{setInstruction(e.target.value);requestId.current=null}}
     placeholder="Добавь герою сестру, придумай её прошлое и отношения с друзьями. Измени историю их группы…"/>
   <div className="ww-ai-examples" aria-label="Примеры инструкции">{['Раскрой мотивы второстепенных персонажей, сохранив известные факты.','Добавь возможность нового знакомства без решения за героя.','Уточни противоречия в предыстории и предложи связанные исправления.'].map(text=><button disabled={disabled} key={text} onClick={()=>useExample(text)}>{text}</button>)}</div>
   <div className="ai-editor-actions"><Button disabled={disabled||!instruction.trim()||samePreview} onClick={()=>void execute(async()=>{
    requestId.current ||= crypto.randomUUID();
    const next=await api<Job>(`/workspaces/${wid}/draft/edits`,{revision,text:instruction,request_id:requestId.current,config:prefs.summary,api_key:apiKey});
    if(alive.current){onJob(next);setSelected(next.id);await refresh();await load()}
   })}><WandSparkles size={16}/>{busy?'Подготавливаем…':'Предложить изменения'}</Button><span>Текущая версия остаётся целой до подтверждения.</span></div>
  </>
  {error && <p className="ai-editor-error" role="alert">{error}</p>}
  </div><div className="ww-ai-result">
  {active(job)&&job?.kind==='draft_editor'&&<div className="ww-ai-loading" role="status" aria-live="polite"><WandSparkles/><h4>Готовим предложение</h4><p>Сопоставляем инструкцию с текущим миром. Канон ещё не изменён.</p><div className="ww-ai-stream"/>{[94,68,82,55].map(width=><span key={width} className="ww-ai-skeleton" style={{width:width+'%'}}/>)}</div>}
  {!current&&!active(job)&&<div className="ww-ai-empty"><WandSparkles size={40}/><h4>Здесь появится предложение</h4><p>Сценарист сопоставит ваш замысел с текущим миром. Вы увидите каждую правку, её связи и результаты проверки до сохранения.</p></div>}
  {current && !(active(job)&&job?.kind==='draft_editor') && <div className="ai-preview" aria-label="Предпросмотр AI-изменений">
   <div className="ai-preview-title"><h4>{statuses[current.status]||'Сохранённый запрос'}</h4><span>На основе версии #{current.base_version}</span></div>
   <details><summary>Инструкция автора</summary><p className="ai-prose">{current.instruction}</p></details>
   {current.proposal && <><p className="ai-prose">{current.proposal.rationale}</p><details><summary>План и зависимости изменений</summary><ol>{current.proposal.changes.map((c,i)=><li key={i}>{c.reason}<small>{c.path}</small></li>)}</ol></details></>}
   {current.error && <p role="alert">{current.error}</p>}
   {current.status==='preview' && current.stale && <p className="ai-editor-error" role="alert">Предпросмотр устарел: мир изменился. Отправьте инструкцию заново.</p>}
   {current.diff && <>
    <div className="ai-diff-counts" aria-label="Состав изменений">{(['add','replace','remove'] as const).map(op=><span key={op}>{op==='add'?<Plus size={14}/>:op==='remove'?<Minus size={14}/>:<Pencil size={14}/>} {operations[op]}: {changed.filter(d=>d.operation===op).length}</span>)}</div>
    {!changed.length && <p>Модель не предложила изменений. Уточните инструкцию или отклоните пакет.</p>}
    {[...new Set(changed.map(d=>d.section))].map(section=><section className="ai-diff-group" key={section}><h5>{sectionNames[section]||runtimeLabels[section.split('/').pop()!]||section}</h5>{changed.filter(d=>d.section===section).map(d=><details open={d===changed[0]||undefined} className={`ai-diff-entity ai-diff-${d.operation}`} key={d.id}>
      <summary><span>{d.name}</span><span>{operations[d.operation]} · {d.fields.length}</span></summary>
      {d.fields.map((f,i)=><div className="ai-diff-field" key={i}><h6>{f.field==='/'?'Вся сущность':runtimeLabels[f.field.split('/').pop()!]||f.field}</h6><div className="ai-diff-values">
        <div><span className="ai-diff-label">До</span>{f.before==null?<p>Отсутствует</p>:<RuntimeValue field={f.field.split('/').pop()!} value={f.before} resolve={previewResolve} author/>}</div><ArrowRight className="ai-diff-arrow" aria-hidden="true" size={16}/>
        <div><span className="ai-diff-label">После</span>{f.after==null?<p>Отсутствует</p>:<RuntimeValue field={f.field.split('/').pop()!} value={f.after} resolve={previewResolve} author/>}</div>
      </div></div>)}
    </details>)}</section>)}
   </>}
   {!!current.conflicts?.length && <div className="ai-editor-warning"><strong>Затронуты ручные авторские решения</strong><p>Эти значения изменятся только с вашим отдельным подтверждением.</p><ul>{current.conflicts.map(p=><li key={p}>{p}</li>)}</ul></div>}
   {issues.map((issue,i)=><p className="ai-editor-warning" key={i}>{issue.severity==='blocker'?'Противоречие':'Замечание'}: {issue.message}</p>)}
   {current.proposal?.conflicts?.map((text,i)=><p role="alert" className="ai-editor-warning" key={i}>{text}</p>)}
   {blocked && <p>Уточните инструкцию с учётом противоречий. Применение заблокировано.</p>}
   {current.status==='preview' && <div className="ai-editor-actions"><Button ref={acceptButton} disabled={disabled||current.stale||blocked||!changed.length} onClick={()=>{setError('');setConflicts(false);setWarnings(false);setConfirm(true)}}><Check size={16}/>Применить пакет…</Button><Button variant="outline" disabled={disabled} onClick={()=>void decision('reject')}>Отклонить пакет</Button></div>}
   {current.status==='accepted' && <section><p role="status">Изменения сохранены в версии #{current.applied_version}.</p>{onHistory&&<Button variant="outline" onClick={()=>onHistory(current.base_version)}>Посмотреть исходную версию</Button>}{onObject&&changed.filter(d=>d.operation!=='remove').map(d=><Button key={d.section+d.id} variant="ghost" onClick={()=>onObject(d.section,d.id)}>Открыть: {d.name}</Button>)}</section>}
   {!!current.requests?.length && <details><summary>Запросы и расходы · {current.requests.length}</summary>{current.requests.map((r,i)=><p key={r.id}>Запрос {i+1}: {r.input_tokens ?? 'неизвестно'} входных / {r.output_tokens ?? 'неизвестно'} выходных токенов · {r.cost_usd===null?'стоимость неизвестна':`оценка $${Number(r.cost_usd).toFixed(6)}`}</p>)}</details>}
   <Button variant="ghost" disabled={busy} onClick={()=>void execute(async()=>{download(JSON.stringify(current,null,2),'world-edit.json')})}>Скачать предложение</Button>
  </div>}
  {data.edits.length>1 && <details className="ai-editor-history"><summary><History size={16}/>История AI-редакций · {data.edits.length}</summary>{data.edits.map(e=><button key={e.id} onClick={()=>setSelected(e.id)} aria-pressed={current?.id===e.id}><strong>{statuses[e.status]||e.status}</strong><span>{e.instruction}</span></button>)}</details>}
  </div></div>
  <Dialog open={replacement!==null} onOpenChange={o=>!o&&setReplacement(null)}><DialogContent><DialogTitle>Заменить текущую инструкцию примером?</DialogTitle><DialogDescription>Несохранённая инструкция будет заменена. Запрос к модели не отправляется.</DialogDescription><Button variant="ghost" onClick={()=>setReplacement(null)}>Оставить мой текст</Button><Button onClick={()=>{setInstruction(replacement||'');setReplacement(null);requestAnimationFrame(()=>textarea.current?.focus())}}>Вставить пример</Button></DialogContent></Dialog>
  <Dialog open={confirm} onOpenChange={setConfirm}><DialogContent onCloseAutoFocus={event=>{event.preventDefault();acceptButton.current?.focus()}}><DialogHeader><DialogTitle>Применить изменения мира?</DialogTitle><DialogDescription>Будет сохранён весь показанный пакет: {changed.length} изменённых сущностей. Предыдущая версия останется доступна для отката.</DialogDescription></DialogHeader>
   {error && <p className="ai-editor-error" role="alert">{error}</p>}
   {destructive && <label className="ai-confirm-option"><input type="checkbox" checked={conflicts} onChange={e=>setConflicts(e.target.checked)}/>Подтверждаю удаления и замену указанных ручных решений</label>}
   {!!issues.length && <label className="ai-confirm-option"><input type="checkbox" checked={warnings} onChange={e=>setWarnings(e.target.checked)}/>Принимаю предупреждения смысловой проверки</label>}
   <div className="ai-editor-actions"><Button variant="outline" disabled={busy} onClick={()=>setConfirm(false)}>Вернуться к просмотру</Button><Button disabled={disabled||destructive&&!conflicts||!!issues.length&&!warnings} onClick={()=>void decision('accept')}>Подтвердить изменения</Button></div>
  </DialogContent></Dialog>
 </section>
}
