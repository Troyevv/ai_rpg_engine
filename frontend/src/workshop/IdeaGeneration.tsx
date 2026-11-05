import {ArrowRight,Check,LoaderCircle,Pause,AlertCircle} from 'lucide-react';
import {active,type Job} from '../types';
export type GenerationSnapshot={version_id:number|null;technical_valid?:boolean;creative_status?:string|null;review?:{status:string}|null};
export function generationSteps(job:Job,draft:GenerationSnapshot){
 const phase=job.phase||'';
 const current=/world|continuing/.test(phase)?0:phase==='validating'?1:/developing|improving|retrying/.test(phase)?2:/review/.test(phase)?3:phase==='saving'?4:-1;
 const candidate=!!draft.version_id&&!(job as Job&{transport_incomplete?:boolean}).transport_incomplete;
 return [
  {title:'Основа мира',done:candidate,detail:'Первый черновик по вашему замыслу'},
  {title:'Проверка структуры',done:candidate&&!!draft.technical_valid,detail:'Типы данных и связи между записями'},
  {title:'Творческое развитие',done:draft.creative_status==='applied',detail:draft.creative_status?({applied:'Дополнения применены',running:'Модель связывает и развивает детали',rejected:'Дополнения отклонены',cancelled:'Этап остановлен',interrupted:'Этап прерван'} as Record<string,string>)[draft.creative_status]:'Этап ещё не подтверждён сервером'},
  {title:'Смысловая проверка',done:draft.review?.status==='completed',detail:draft.review?.status==='stale'?'Мир изменён — проверку нужно повторить':'Согласованность мира и знаний персонажей'},
  {title:'Сохранение версии',done:job.status==='saved'&&candidate,detail:candidate?`Версия ${draft.version_id} сохранена`:'Результат останется в Мастерской'}
 ].map((step,i)=>({...step,state:active(job)&&i===current?'current':step.done?'done':!active(job)&&i===current?'paused':'pending'}));
}
export function IdeaGeneration({job,draft,title,description,onEditor,onEdit}:{job:Job;draft:GenerationSnapshot;title:string;description:string;onEditor:()=>void;onEdit:()=>void}){
 const running=active(job);const steps=generationSteps(job,draft);
 return <section className="atelier-generation" aria-label="Этапы создания мира"><p className="atelier-eyebrow">Генерация мира</p><h2>{running?'Замысел становится миром':job.status==='saved'?'Новая версия готова':job.status==='stopped'?'Генерация остановлена':'Генерация требует внимания'}</h2>
 <ol aria-live="polite">{steps.map(s=><li key={s.title} data-state={s.state} aria-current={s.state==='current'?'step':undefined}><strong>{s.title}</strong>{s.state==='done'?<Check size={16} aria-label="Завершено"/>:s.state==='current'?<LoaderCircle size={16} aria-label="В работе"/>:s.state==='paused'?<Pause size={16} aria-label="Прервано"/>:null}<small>{s.detail}</small></li>)}</ol>
 {!running&&<div className="atelier-result"><h3>{title}</h3>{description&&<p>{description}</p>}<p>{draft.version_id?'Сохранённая версия доступна. Начало игры — отдельное действие в верхней панели.':'Готовой версии пока нет. Полученные части и доступные действия восстановления показаны ниже.'}</p>{!draft.technical_valid&&draft.version_id&&<p><AlertCircle size={16}/>Структура требует исправления в авторском редакторе.</p>}<div className="atelier-generation-actions">{draft.version_id&&<button className="atelier-primary" onClick={onEditor}>Открыть в редакторе<ArrowRight size={16}/></button>}<button className="atelier-link" onClick={onEdit}>Изменить замысел</button></div></div>}
 </section>;
}
