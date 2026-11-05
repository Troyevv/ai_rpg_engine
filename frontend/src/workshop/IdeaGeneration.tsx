import {useEffect,useRef,type ReactNode} from 'react';
import {ArrowRight,ArrowLeft,BookOpen,Check,Pause,AlertCircle,ShieldCheck} from 'lucide-react';
import {active,type Job} from '../types';
import '../styles/idea-atelier.css';
export type GenerationSnapshot={version_id:number|null;version_origin_job_id?:string|null;version_is_candidate?:boolean;technical_valid?:boolean;creative_status?:string|null;review?:{status:string}|null};
export function generationSteps(job:Job,draft:GenerationSnapshot){
 const phase=job.phase||'';
 // A previous head (including its successful review) is not evidence for this job.
 const belongs=!!draft.version_id&&draft.version_origin_job_id===job.id;
 const candidate=belongs&&!(job as Job&{transport_incomplete?:boolean}).transport_incomplete;
 const current=/^(world|continuing)$/.test(phase)||job.status==='queued'?0:phase==='validating'?1:phase==='developing'||phase==='retrying'&&draft.creative_status==='running'?2:phase==='retrying'?1:/review|improving/.test(phase)?3:phase==='saving'?4:-1;
 return [
  {title:'Основа мира',done:candidate,detail:'Генератор раскрывает замысел, создаёт персонажей, места и связи.'},
  {title:'Проверка структуры',done:candidate&&!!draft.technical_valid,detail:'Проверяем типы данных и связи между записями мира.'},
  {title:'Творческое развитие',done:candidate&&draft.creative_status==='applied',detail:({applied:'Дополнения применены к кандидату.',running:'Модель связывает и развивает детали.',rejected:'Дополнения отклонены; кандидат сохранён.',cancelled:'Этап остановлен.',interrupted:'Этап прерван.'} as Record<string,string>)[draft.creative_status||'']||'Дополняем персонажей, отношения и завязки в рамках замысла.'},
  {title:'Смысловая проверка',done:candidate&&draft.review?.status==='completed',detail:belongs&&draft.review?.status==='stale'?'Мир изменён — проверку нужно повторить.':'Проверяем согласованность истории и знаний персонажей.'},
  {title:'Сохранение версии',done:job.status==='saved'&&candidate&&!draft.version_is_candidate,detail:candidate?`Кандидат текущего задания сохранён в версии ${draft.version_id}.`:'Результат останется в Мастерской.'}
 ].map((step,i)=>({...step,state:active(job)&&i===current?'current':step.done?'done':!active(job)&&i===current?(job.status==='stopped'?'paused':'error'):'pending'}));
}
export function IdeaGeneration({job,draft,title,description,onEditor,onEdit,activity}:{job:Job;activity?:ReactNode;draft:GenerationSnapshot;title:string;description:string;onEditor:()=>void;onEdit:()=>void}){
 const running=active(job),belongs=!!draft.version_id&&draft.version_origin_job_id===job.id;
 const complete=job.status==='saved'&&belongs&&!draft.version_is_candidate;
 const steps=generationSteps(job,draft),current=steps.findIndex(s=>s.state==='current'||s.state==='error'||s.state==='paused');
 const heading=useRef<HTMLHeadingElement>(null);
 useEffect(()=>{heading.current?.focus({preventScroll:true})},[job.id,complete]);
 return <div className="atelier-scope atelier-generation"><section className="flow-root flow-wrap" aria-label="Этапы создания мира" data-result={complete}>
  <div className="fl-kicker"><i/>МАСТЕРСКАЯ МИРОВ <b>/</b>{complete?'04':'03'}<span>{complete?'Результат':running?'Генерация':'Восстановление'}</span></div>
  <h2 className="fl-title" ref={heading} tabIndex={-1}>{complete?'Мир готов к редактированию':running?'Создание мира':job.status==='stopped'?'Генерация остановлена':'Задание требует внимания'}</h2>
  <p className="fl-deck">{complete?'Черновик сохранён. Теперь его можно открыть в Мастерской и отредактировать.':running?'Следите за этапами. Исходный замысел сохранён.':'Ниже — сохранённый результат и доступные действия восстановления.'}</p>
  {!belongs&&draft.version_id&&<div className="fl-alert" role="status"><BookOpen size={20}/><p>Доступна предыдущая версия № {draft.version_id}. Текущее задание ещё не сохранило новый мир.</p></div>}
  {!running&&!complete&&<div className="fl-alert" role={job.error?"alert":"status"}><AlertCircle size={20}/><div>{job.error&&<p>{job.response_diagnostic?.message||job.error}</p>}<p>{belongs?'Промежуточный кандидат сохранён. Можно открыть его или продолжить доступный этап ниже.':'Готового результата текущего задания пока нет. Полученные части остаются в журнале.'}</p></div></div>}
  {complete?<article className="fl-card fl-result" key="result"><div className="fl-card-head"><Check size={18}/><span>Версия сохранена</span><small>№ {draft.version_id}</small></div><span className="fl-bookmark" aria-hidden="true"><BookOpen/></span><h2>{title}</h2>
   <section className="fl-excerpt"><h3>Первая встреча с миром</h3>{description?<blockquote>{description}</blockquote>:<p>Публичная аннотация в этой версии не задана. Исходный замысел доступен в авторском редакторе.</p>}</section>
   <div className="fl-seals"><span>{draft.technical_valid?<ShieldCheck size={16}/>:<AlertCircle size={16}/>}Структура {draft.technical_valid?'проверена':'требует исправления'}</span><span>{draft.review?.status==='completed'?<Check size={16}/>:<AlertCircle size={16}/>} {draft.review?.status==='completed'?'Смысловая проверка завершена':draft.review?.status==='stale'?'После правки нужна повторная проверка':'Смысловая проверка не завершена'}</span></div>
  </article>:<article className="fl-card" key="journal"><div className="fl-card-head"><BookOpen size={18}/><span>Журнал генерации</span>{current>=0&&<small>Этап {current+1} из {steps.length}</small>}</div>
   <div className="fl-progress" aria-hidden="true">{steps.map(s=><i key={s.title} className={s.state}/>)}</div>
   <ol className="fl-stages" aria-live="polite">{steps.map((s,i)=><li key={s.title} className={s.state} data-state={s.state} aria-current={s.state==='current'?'step':undefined}><span className="fl-stage-no">{s.state==='done'?<Check size={15} className="selection-mark"/>:s.state==='error'?<AlertCircle size={15}/>:s.state==='paused'?<Pause size={15}/>:String(i+1).padStart(2,'0')}</span><div><strong>{s.title}</strong>{s.state!=='pending'&&<p>{s.detail}</p>}</div><small>{({done:'Готово',current:'В работе',error:'Ошибка',paused:'Остановлено',pending:'Ожидание'} as Record<string,string>)[s.state]}</small></li>)}</ol>{activity}
  </article>}
  {!running&&<div className="fl-actions"><button className="fl-sub" onClick={onEdit}><ArrowLeft size={16}/>Изменить замысел</button>{draft.version_id&&<button className="fl-primary" onClick={onEditor}>{complete?'Открыть в редакторе':belongs?'Открыть сохранённый мир':'Открыть предыдущий мир'}<ArrowRight size={16}/></button>}</div>}
 </section></div>;
}
