import {ProposalAdjustment,type ProposalChange} from './workshop/ProposalAdjustment';
import {ReviewCalendarConfirmation,type LegacyFamily,type FamilyInput} from './workshop/ReviewCalendarConfirmation';
import {requestId as newRequestId} from './lib/requestId';
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
type ReviewAction = 'fix'|'recheck';
const outcomeLabels:Record<string,string>={proposed:'Предложена правка',fixed:'Исправлено',remaining:'Осталось',ambiguous:'Отклонено как неоднозначное',disproved:'Замечание опровергнуто',unapplied:'Не удалось применить'};
const findingLabels:Record<string,string>={contradiction:'Подтверждённое противоречие',incomplete_description:'Неполное описание',uncertainty:'Неопределённость',false_positive:'Ложное замечание'};
type FamilyChronology = {child:string;name:string;date:string;age:number|null;reference:string;options:number;first:string;last:string;
  parents:{id:string;name:string;age:number|null;birth_date:string|null;died:boolean;quote:string}[];marriage_ids:string[];inventions:{name:string;date:string}[]};
type Edit = {removable?:number[];original_indices?:number[];omitted?:number[];related_records?:{section:string;id:string;links:{kind:string;id:string}[]}[];family_impacts?:{parent:string;child:string;day:string;age:number|null}[];author_idea?:string;can_replay?:boolean;warnings?:{message:string;path:string}[];diagnostics?:{operation:number;path:string;message:string}[];original_proposal?:{changes:ProposalChange[]};amended_indices?:number[];superseded_dates?:boolean;legacy_families?:LegacyFamily[];chronologies?:FamilyChronology[];action?:ReviewAction;failure?:string;outcomes?:{issue_id:string;message:string;paths:string[];outcome:string;category?:string|null;reason:string}[];id:string;status:string;instruction:string;stale:boolean;base_version:number;applied_version?:number;error:string;
  references?:Parameters<typeof resolver>[0];
  requests?:{id:string;stage:string;status:string;input_tokens:number|null;output_tokens:number|null;cost_usd:string|null}[];
  proposal?:{rationale:string;conflicts?:string[];changes:ProposalChange[]};diff?:Diff[];conflicts?:string[];
  review?:{status:string;issues:{message:string;severity?:string}[]}};
type Edits = {edits:Edit[];started:boolean};
const sectionNames:Record<string,string>={characters:'Карточки персонажей',locations:'Места',campaign:'Замысел мира',
 'world/characters':'Состояние персонажей','world/objective_relations':'Родство и социальные связи',
 'world/relationships':'Направленные отношения','world/organizations':'Организации','world/roles':'Профессии и роли',
 'world/knowledge':'Знания','world/facts':'Факты и тайны','world/events':'Предыстория','world/threads':'Сюжетные линии'};
const operations={add:'Добавление',replace:'Изменение',remove:'Удаление'};
const statuses:Record<string,string>={preview:'Ожидает решения',assessed:'Рассмотрено без изменений',reviewed:'Повторная проверка завершена',unapplied:'Не удалось применить',accepted:'Применено',rejected:'Отклонено',running:'Подготовка',error:'Запрос прерван',stopped:'Остановлено'};

type EditorProps = {
 wid:string;revision:number;job:Job|null;locked:boolean;prefs:Preferences;apiKey:string;
 reviewCount?:number;pendingPreview?:boolean;title?:string;version?:number|null;example?:string;onCharacters?:()=>void;onHistory?:(version:number)=>void;onObject?:(section:string,id:string)=>void;
 onJob:(job:Job)=>void;refresh:()=>Promise<void>;resolve:ReturnType<typeof resolver>;
};

// Own the workspace boundary here: callers need not remember a React key.
export function WorldAIEditor(props:EditorProps) {
 return <WorkspaceEditor key={props.wid} {...props}/>;
}

function WorkspaceEditor({wid,revision,job,locked,prefs,apiKey,onJob,refresh,resolve,title,version,example,onHistory,onCharacters,onObject,reviewCount,pendingPreview}:EditorProps) {
 const storageKey=`world-editor:${wid}`;
 const [instruction,setInstruction]=useState(()=>localStorage.getItem(storageKey)||example||'');
 const textarea=useRef<HTMLTextAreaElement>(null);
 const [replacement,setReplacement]=useState<string|null>(null);
 const [data,setData]=useState<Edits>({edits:[],started:false});
 const [error,setError]=useState('');const [busy,setBusy]=useState(false);
 const [selected,setSelected]=useState<string|null>(null);
 const [adjust,setAdjust]=useState<string|null>(null);
 const [confirm,setConfirm]=useState(false);const [conflicts,setConflicts]=useState(false);const [warnings,setWarnings]=useState(false);
 const acceptButton=useRef<HTMLButtonElement>(null);
 const guard=useRef(false);const requestId=useRef<string|null>(null);const alive=useRef(true);
 const changeInstruction=(text:string)=>{setInstruction(text);requestId.current=null};
 const useExample=(text:string)=>{if(instruction.trim())setReplacement(text);else{changeInstruction(text);textarea.current?.focus()}};
 useEffect(()=>{alive.current=true;return()=>{alive.current=false}},[]);
 useEffect(()=>{localStorage.setItem(storageKey,instruction)},[storageKey,instruction]);
 const load=async()=>{const next=await api<Edits>(`/workspaces/${wid}/draft/edits?author=true`);if(alive.current)setData(next)};
 useEffect(()=>{const controller=new AbortController();void api<Edits>(`/workspaces/${wid}/draft/edits?author=true`,undefined,'GET',controller.signal)
  .then(next=>{if(!controller.signal.aborted)setData(next)}).catch(e=>{if(!controller.signal.aborted)setError(e.message)});return()=>controller.abort()},[wid,revision,job?.status]);
 const execute=async(fn:()=>Promise<void>)=>{if(guard.current)return;guard.current=true;setBusy(true);setError('');try{await fn()}catch(e){if(alive.current)setError((e as Error).message)}finally{guard.current=false;if(alive.current)setBusy(false)}};
 const reviewMode=reviewCount!==undefined;
 const history=data.edits.filter(e=>!!e.action===reviewMode);
 const current=history.find(e=>e.id===selected)||history[0];
 const startReview=(action:ReviewAction)=>execute(async()=>{
  const key=`review-request:${wid}:${revision}:${action}`;
  const token=sessionStorage.getItem(key)||newRequestId();
  sessionStorage.setItem(key,token);
  const next=await api<Job>(`/workspaces/${wid}/draft/edits`,{revision,action,request_id:token,config:prefs.summary,api_key:apiKey});
  sessionStorage.removeItem(key);
  if(alive.current){onJob(next);setSelected(next.id);await refresh();await load()}
 });
 const changed=current?.diff||[];
 const previewResolve=current?.references ? resolver(current.references) : resolve;
 const destructive=!!current?.conflicts?.length||changed.some(d=>d.operation==='remove');
 const issues=current?.review?.issues||[];
 const disabled=busy||locked;
 const appliedFix=current?.action==='recheck'&&history.find(e=>e.action==='fix'&&e.applied_version===current.base_version);
 const samePreview=current?.status==='preview'&&!current.stale&&current.instruction===instruction;
 useEffect(()=>{if(job && !active(job))requestId.current=null},[job?.status]);
 const decision=(choice:'accept'|'reject'|'recalculate_dates'|'replay'|'omit_invalid',family?:FamilyInput[])=>execute(async()=>{
  await api(`/workspaces/${wid}/draft/edits/${current.id}`,{revision,decision:choice,family,accept_conflicts:conflicts,accept_warnings:warnings});
  if(alive.current){setConfirm(false);requestId.current=null;await load();await refresh()}
 });
 return <section className="world-ai-editor" aria-labelledby="world-ai-title">
  <div className="ai-editor-heading"><WandSparkles aria-hidden="true"/><div><h3 id="world-ai-title">{reviewMode?'Работа с замечаниями':'AI-редактор мира'}</h3></div></div>
  <p>{reviewMode?'Каждое действие отправляет один запрос к модели. До сохранения можно сравнить правки с исходной версией.':'Опишите любые связанные изменения. Сначала вы увидите предложение, затем решите, что сохранить.'}</p>
  <div className="ww-ai-columns"><div className="ww-ai-compose"><p className="ww-eyebrow">{title} · версия #{version}</p>{!reviewMode&&<ol className="ww-ai-steps"><li>Замысел</li><li>Предложение</li><li>Ваше решение</li></ol>}
  {data.started && <p role="status">Изменения войдут в новое прохождение. Начатая игра останется без изменений.</p>}
  {reviewMode?<><p className="workshop-hint">Замечаний для рассмотрения · {reviewCount}</p><p className="workshop-hint">{prefs.summary.model} · {prefs.summary.provider==='local'?'Локальная модель':'Оплата по тарифу провайдера'}</p><div className="ai-editor-actions">
   <Button disabled={disabled||pendingPreview||!reviewCount||(job?.review_reply_saved&&job.review_action==='fix')} onClick={()=>void startReview('fix')}><WandSparkles size={16}/>Исправить замечания с помощью ИИ</Button>
   <Button variant="outline" disabled={disabled||pendingPreview||(job?.review_reply_saved&&job.review_action==='recheck')} onClick={()=>void startReview('recheck')}>Повторить смысловую проверку</Button>
  </div>{pendingPreview&&<p>Сначала примите или отклоните открытое предложение.</p>}</>:<>
   <label htmlFor="world-ai-instruction">Что изменить в мире?</label>
   <Textarea ref={textarea} id="world-ai-instruction" value={instruction} disabled={busy||active(job)} onChange={e=>changeInstruction(e.target.value)}
     placeholder="Добавь герою сестру, придумай её прошлое и отношения с друзьями. Измени историю их группы…"/>
   <div className="ww-ai-examples" aria-label="Примеры инструкции">{['Раскрой мотивы второстепенных персонажей, сохранив известные факты.','Добавь возможность нового знакомства без решения за героя.','Уточни противоречия в предыстории и предложи связанные исправления.'].map(text=><button disabled={disabled} key={text} onClick={()=>useExample(text)}>{text}</button>)}</div>
   <div className="ai-editor-actions"><Button disabled={disabled||!instruction.trim()||samePreview} onClick={()=>void execute(async()=>{
    requestId.current ||= newRequestId();
    const next=await api<Job>(`/workspaces/${wid}/draft/edits`,{revision,text:instruction,request_id:requestId.current,config:prefs.summary,api_key:apiKey});
    if(alive.current){onJob(next);setSelected(next.id);await refresh();await load()}
   })}><WandSparkles size={16}/>{busy?'Подготавливаем…':'Предложить изменения'}</Button><span>Текущая версия остаётся целой до подтверждения.</span></div>
  </>}
  {error && <p className="ai-editor-error" role="alert">{error}</p>}
  </div><div className="ww-ai-result">
  {active(job)&&job?.kind==='draft_editor'&&<div className="ww-ai-loading" role="status" aria-live="polite"><WandSparkles/><h4>{job.phase==='reviewing'?'Проверяем мир':'Готовим предложение'}</h4><p>Результат сохранится в этом черновике.</p><div className="ww-ai-stream"/>{[94,68,82,55].map(width=><span key={width} className="ww-ai-skeleton" style={{width:width+'%'}}/>)}</div>}
  {!reviewMode&&!current&&!active(job)&&<div className="ww-ai-empty"><WandSparkles size={40}/><h4>Здесь появится предложение</h4><p>Сценарист сопоставит ваш замысел с текущим миром. Вы увидите каждую правку, её связи до сохранения.</p></div>}
  {current && !(active(job)&&job?.kind==='draft_editor') && <div className="ai-preview" aria-label="Предпросмотр AI-изменений">
   <div className="ai-preview-title"><h4>{statuses[current.status]||'Сохранённый запрос'}</h4><span>На основе версии #{current.base_version}</span></div>
   {!reviewMode&&<details><summary>Инструкция автора</summary><p className="ai-prose">{current.instruction}</p></details>}
   {!!current.diagnostics?.length&&<ul className="ai-editor-error" role="alert" aria-label="Ошибки операций">{current.diagnostics.map(d=><li key={d.operation}><strong>Операция {d.operation}</strong> · {d.path}<p>{d.message}</p></li>)}</ul>}
   {!!current.removable?.length&&current.status==='unapplied'&&<div className="ai-editor-warning"><p>Можно исключить перечисленные операции и проверить оставшуюся часть пакета.</p><ul>{current.removable.map(i=><li key={i}>{current.proposal?.changes[i]?.path}</li>)}</ul><Button variant="outline" disabled={disabled||current.stale} onClick={()=>void decision('omit_invalid')}>Исключить указанные операции и проверить</Button></div>}
   {current.can_replay&&<Button variant="outline" disabled={disabled||current.stale} onClick={()=>void decision('replay')}>Открыть сохранённое предложение без нового запроса</Button>}
   {current.failure&&!current.diagnostics?.length&&<p className="ai-editor-error" role="alert">{current.failure}</p>}
   {!!current.outcomes?.length&&<section className="ai-review-outcomes" aria-label="Результаты по замечаниям">
    {current.outcomes.map(row=>{
     const path=row.paths[0];
     const subject=path?.match(/^\/world\/characters\/([^/]+)/)?.[1];
     const message=path&&row.message.startsWith(path+': ')?row.message.slice(path.length+2):row.message;
     const label=row.outcome==='proposed'&&current.status==='accepted'?'Правка применена':
       row.outcome==='proposed'&&current.status==='rejected'?'Правка отклонена':outcomeLabels[row.outcome];
     return <details key={row.issue_id}><summary><span className="ai-review-note">
       <strong>{label}</strong><span>{subject&&previewResolve('actor_id',subject)+' · '}{message}</span>
     </span></summary><p className="ai-prose">{row.category&&<strong>{findingLabels[row.category]}. </strong>}{row.reason}</p></details>;
    })}
   </section>}
   {current.status==='reviewed'&&!current.review?.issues.length&&!current.outcomes?.length&&<p>Замечаний к этой версии нет.</p>}
   {appliedFix&&onHistory&&<Button variant="outline" disabled={disabled} onClick={()=>onHistory(appliedFix.base_version)}>Посмотреть версию до исправления и откатить</Button>}
   {current.author_idea&&<details><summary>Исходный авторский замысел</summary><p className="ai-prose">{current.author_idea}</p></details>}
   {!!current.family_impacts?.length&&!current.chronologies?.length&&<section className="ai-family-chronology"><h5>Возраст родителей по предложенным датам</h5><ul>{current.family_impacts.map((r,i)=><li key={i}>{r.parent} · {r.age===null?'возраст неизвестен':r.age+' лет'} на {r.day} · рождение: {r.child}</li>)}</ul></section>}
   {current.chronologies?.map(family=><section className="ai-family-chronology" aria-label="Семейная хронология" key={family.child}>
    <h5>Семейная хронология</h5><p><strong>{family.date}</strong> · Рождение: {family.name}{family.age!==null&&<> · возраст на {family.reference}: {family.age}</>}</p>
    <p>{family.options===1?'Единственная совместимая дата.':<>Предложен один из допустимых дней ({family.options}). Границы выбора: {family.first} — {family.last}.</>}</p>
    {family.inventions.length>0&&<div><strong>Новые вымышленные детали</strong><ul>{family.inventions.map(item=><li key={item.name+item.date}>{item.name} · дата рождения {item.date}</li>)}</ul></div>}
    <ul>{family.parents.map(parent=><li key={parent.id}>{parent.name}{parent.age!==null&&<> · возраст при родах: {parent.age}</>}{parent.died&&<> · смерть при родах {family.date}</>}{parent.quote&&<details><summary>Основание</summary><p>{parent.quote}</p></details>}</li>)}</ul>
    {family.marriage_ids.length>0&&<p>Дата окончания брака по смерти супруга: {family.date}.</p>}
   </section>)}
   {current.proposal && <><p className="ai-prose">{current.proposal.rationale}</p>{current.proposal.changes.length>0&&<details><summary>План и зависимости изменений</summary><ol>{current.proposal.changes.map((c,i)=><li key={i}>{c.reason}<small>{current.amended_indices?.includes(i)?'Скорректировано вами':c.detail==='new_detail'?'Новая деталь модели':c.detail==='author_fact'?'По авторскому замыслу (по оценке модели)':'Предложение модели'} · {c.path}</small></li>)}</ol></details>}</>}
   {current.error && <p role="alert">{current.error}</p>}
   {current.status==='preview' && current.stale && <p className="ai-editor-error" role="alert">Предпросмотр устарел: мир изменился. Отправьте инструкцию заново.</p>}
   {current.diff && (!reviewMode||changed.length>0) && <>
    <div className="ai-diff-counts" aria-label="Состав изменений">{(['add','replace','remove'] as const).map(op=><span key={op}>{op==='add'?<Plus size={14}/>:op==='remove'?<Minus size={14}/>:<Pencil size={14}/>} {operations[op]}: {changed.filter(d=>d.operation===op).length}</span>)}</div>
    {!reviewMode&&!changed.length && <p>Модель не предложила изменений. Уточните инструкцию или отклоните пакет.</p>}
    {[...new Set(changed.map(d=>d.section))].map(section=><section className="ai-diff-group" key={section}><h5>{sectionNames[section]||runtimeLabels[section.split('/').pop()!]||section}</h5>{changed.filter(d=>d.section===section).map(d=><details open={d===changed[0]||undefined} className={`ai-diff-entity ai-diff-${d.operation}`} key={d.id}>
      <summary><span>{d.name}</span><span>{operations[d.operation]} · {d.fields.length}</span></summary>
      {current.related_records?.filter(r=>r.id===d.id&&r.section===section).map(r=><details key="links"><summary>Связанные записи · {r.links.length}</summary><ul>{r.links.map(link=>{
       const group=sectionNames['world/'+link.kind]||runtimeLabels[link.kind]||(link.kind==='start'?'Начало истории':link.kind);
       const record=(current.references?.world[link.kind] as Record<string,{text?:string;name?:string;title?:string}>|undefined)?.[link.id];
       return <li key={link.kind+link.id}>{group} · {record?.name||record?.title||record?.text||link.id}</li>
      })}</ul></details>)}
      {d.fields.map((f,i)=><div className="ai-diff-field" key={i}><h6>{f.field==='/'?'Вся сущность':runtimeLabels[f.field.split('/').pop()!]||f.field}</h6><div className="ai-diff-values">
        <div><span className="ai-diff-label">До</span>{f.before==null?<p>Отсутствует</p>:<RuntimeValue field={f.field.split('/').pop()!} value={f.before} resolve={previewResolve} author/>}</div><ArrowRight className="ai-diff-arrow" aria-hidden="true" size={16}/>
        <div><span className="ai-diff-label">После</span>{f.after==null?<p>{reviewMode&&f.field.endsWith('/birth_date')?'Точная дата неизвестна':'Отсутствует'}</p>:<RuntimeValue field={f.field.split('/').pop()!} value={f.after} resolve={previewResolve} author/>}</div>
      </div></div>)}
    </details>)}</section>)}
   </>}
   {!!current.conflicts?.length && <div className="ai-editor-warning"><strong>Затронуты ручные авторские решения</strong><p>Эти значения изменятся только с вашим отдельным подтверждением.</p><ul>{current.conflicts.map(p=><li key={p}>{p}</li>)}</ul></div>}
   {issues.map((issue,i)=><p className="ai-editor-warning" key={i}>{issue.severity==='blocker'?'Противоречие':'Замечание'}: {issue.message}</p>)}
   {current.status==='assessed'&&<p role="status">Модель завершила разбор. Правок нет. Сохранена исходная версия #{current.base_version}.</p>}
   {!!current.proposal?.conflicts?.length&&<section aria-label="Неоднозначности"><h5>Что требует решения автора</h5>{!!current.amended_indices?.length&&<p>Модель отметила эти расхождения до вашей корректировки.</p>}<ul>{current.proposal.conflicts.map((text,i)=><li key={i}>{text}</li>)}</ul></section>}
   {current.status==='assessed'&&onCharacters&&current.outcomes?.some(row=>row.outcome==='ambiguous')&&<Button variant="outline" disabled={disabled} onClick={onCharacters}>Уточнить данные в карточках персонажей</Button>}
   {!!current.warnings?.length&&<section className="ai-editor-warning"><h5>Смысловые предупреждения</h5><ul>{current.warnings.map(w=><li key={w.path+w.message}>{w.message}</li>)}</ul></section>}
   {current.original_proposal&&<details><summary>Исходные значения модели</summary>{[...(current.amended_indices||[]).map(i=>current.original_indices?.[i]??i),...(current.omitted||[])].map(i=>{const c=current.original_proposal!.changes[i];return c&&<div key={i}><small>{current.omitted?.includes(i)&&'Исключено автором · '}{c.path}</small><RuntimeValue field={c.path.split('/').pop()!} value={c.value} resolve={previewResolve} author/></div>})}</details>}
   {['preview','unapplied'].includes(current.status)&&current.proposal?.changes.some(c=>c.op!=='remove')&&<Button variant="outline" disabled={disabled||current.stale} onClick={()=>setAdjust(current.id)}><Pencil size={16}/>Скорректировать значения</Button>}
   {adjust===current.id&&current.proposal&&<ProposalAdjustment references={current.references} changes={current.proposal.changes} revision={revision} resolve={previewResolve}
    disabled={busy} onClose={()=>setAdjust(null)} onSave={async(values,baseRevision)=>{
     if(guard.current)throw new Error('Сохранение уже выполняется.');
     guard.current=true;setBusy(true);
     try{await api(`/workspaces/${wid}/draft/edits/${current.id}`,{revision:baseRevision,decision:'revise',values});await load();await refresh()}
     finally{guard.current=false;if(alive.current)setBusy(false)}
    }}/>}
   {current.superseded_dates&&<ReviewCalendarConfirmation key={current.id} families={current.legacy_families||[]} disabled={disabled||current.stale} onCalculate={family=>void decision('recalculate_dates',family)}/>}
   {current.status==='preview' && <div className="ai-editor-actions"><Button ref={acceptButton} disabled={disabled||current.stale||!changed.length} onClick={()=>{setError('');setConflicts(false);setWarnings(false);setConfirm(true)}}><Check size={16}/>Применить пакет…</Button><Button variant="outline" disabled={disabled} onClick={()=>void decision('reject')}>Отклонить пакет</Button></div>}
   {current.status==='unapplied'&&current.proposal&&<Button variant="outline" disabled={disabled} onClick={()=>void decision('reject')}>Отклонить пакет</Button>}
   {current.status==='accepted' && <section><p role="status">Изменения сохранены в версии #{current.applied_version}.</p>{onHistory&&<Button variant="outline" disabled={disabled} onClick={()=>onHistory(current.base_version)}>{reviewMode?'Посмотреть исходную версию и откатить':'Посмотреть исходную версию'}</Button>}{onObject&&changed.filter(d=>d.operation!=='remove').map(d=><Button key={d.section+d.id} variant="ghost" onClick={()=>onObject(d.section,d.id)}>Открыть: {d.name}</Button>)}</section>}
   {!!current.requests?.length && <details><summary>Запросы и расходы · {current.requests.length}</summary>{current.requests.map((r,i)=><p key={r.id}>Запрос {i+1}: {r.input_tokens ?? 'неизвестно'} входных / {r.output_tokens ?? 'неизвестно'} выходных токенов · {r.cost_usd===null?'стоимость неизвестна':`оценка $${Number(r.cost_usd).toFixed(6)}`}</p>)}</details>}
   <Button variant="ghost" disabled={busy} onClick={()=>void execute(async()=>{download(JSON.stringify(current,null,2),'world-edit.json')})}>{current.action==='recheck'?'Скачать отчёт':'Скачать предложение'}</Button>
  </div>}
  {history.length>1 && <details className="ai-editor-history"><summary><History size={16}/>История AI-редакций · {history.length}</summary>{history.map(e=><button key={e.id} onClick={()=>setSelected(e.id)} aria-pressed={current?.id===e.id}><strong>{statuses[e.status]||e.status}</strong><span>{e.instruction}</span></button>)}</details>}
  </div></div>
  <Dialog open={replacement!==null} onOpenChange={o=>!o&&setReplacement(null)}><DialogContent><DialogTitle>Заменить текущую инструкцию примером?</DialogTitle><DialogDescription>Несохранённая инструкция будет заменена. Запрос к модели не отправляется.</DialogDescription><Button variant="ghost" onClick={()=>setReplacement(null)}>Оставить мой текст</Button><Button onClick={()=>{changeInstruction(replacement||'');setReplacement(null);requestAnimationFrame(()=>textarea.current?.focus())}}>Вставить пример</Button></DialogContent></Dialog>
  <Dialog open={confirm} onOpenChange={setConfirm}><DialogContent onCloseAutoFocus={event=>{event.preventDefault();acceptButton.current?.focus()}}><DialogHeader><DialogTitle>Применить изменения мира?</DialogTitle><DialogDescription>Будет сохранён весь показанный пакет: {changed.length} изменённых сущностей. Предыдущая версия останется доступна для отката.</DialogDescription></DialogHeader>
   {error && <p className="ai-editor-error" role="alert">{error}</p>}
   {destructive && <label className="ai-confirm-option"><input type="checkbox" checked={conflicts} onChange={e=>setConflicts(e.target.checked)}/>Подтверждаю удаления и замену указанных ручных решений</label>}
   {!!issues.length && <label className="ai-confirm-option"><input type="checkbox" checked={warnings} onChange={e=>setWarnings(e.target.checked)}/>Принимаю предупреждения смысловой проверки</label>}
   <div className="ai-editor-actions"><Button variant="outline" disabled={busy} onClick={()=>setConfirm(false)}>Вернуться к просмотру</Button><Button disabled={disabled||destructive&&!conflicts||!!issues.length&&!warnings} onClick={()=>void decision('accept')}>Подтвердить изменения</Button></div>
  </DialogContent></Dialog>
 </section>
}
