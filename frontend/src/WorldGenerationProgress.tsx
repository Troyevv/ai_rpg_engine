import {useEffect,useState} from 'react';
import {toast} from 'sonner';
import {api} from './api';
import type {Job} from './types';
import {Button} from './components/ui/button';
import {Dialog,DialogContent,DialogDescription,DialogHeader,DialogTitle} from './components/ui/dialog';

type Unit={unit_id:string;stage:string;status:string;weight:number;attempts:number;error:string};
type Progress={revision:number;overall_progress:number;units:Unit[]};
const stages:Record<string,string>={interpret:'Понимание замысла',setting:'Сеттинг и план',places:'Локации и организации',characters:'Персонажи',life:'Отношения и обстоятельства',lore:'Предыстория и знания',opening:'Начальная сцена',assembly:'Сборка и проверка'};
const statuses:Record<string,string>={pending:'Ожидает',running:'Выполняется',completed:'Проверено',saved:'Готово',failed:'Ошибка',stale:'Нужна повторная проверка',uncertain:'Исход запроса неизвестен',cancelled:'Отменено',generating:'Создаём мир',pause_requested:'Завершаем текущий этап перед паузой',paused:'На паузе',waiting_for_credentials:'Нужен доступ к провайдеру'};

export function WorldGenerationProgress({job,apiKey,refresh}:{job:Job;apiKey:string;refresh:()=>void}){
  const [data,setData]=useState<Progress|null>(null);
  const [busy,setBusy]=useState(false);
  const [uncertain,setUncertain]=useState(false);
  const [author,setAuthor]=useState(false);
  const [inspected,setInspected]=useState<{stage:string;artifact?:unknown}|null>(null);
  useEffect(()=>{setAuthor(false);setInspected(null);setData(null);setUncertain(false)},[job.id]);
  useEffect(()=>{let live=true;const controller=new AbortController();
    const load=()=>api<Progress>(`/jobs/${job.id}/generation`,undefined,'GET',controller.signal).then(next=>{if(live)setData(next)}).catch(()=>{});
    void load();const timer=setInterval(load,1500);
    return()=>{live=false;controller.abort();clearInterval(timer)};
  },[job.id,job.status]);
  const act=async(action:string)=>{if(!data)return;setBusy(true);try{
    await api(`/jobs/${job.id}/generation/${action}`,{revision:data.revision,api_key:apiKey,retry_uncertain:uncertain});
    setUncertain(false);refresh();
  }catch(e){toast.error((e as Error).message)}finally{setBusy(false)}};
  if(!data)return <p role="status">Загружаем состояние этапов…</p>;
  const hasUncertain=data.units.some(unit=>unit.status==='uncertain');
  const resumable=['paused','failed','waiting_for_credentials'].includes(job.status);
  return <section className="workshop-review" aria-label="Этапы генерации мира">
    <h2>{statuses[job.status]||job.status}</h2>
    <label>Общий прогресс · {Math.floor(data.overall_progress*100)}%<progress aria-label="Общий прогресс генерации" value={data.overall_progress} max={1}/></label>
    {job.status==='pause_requested'&&<p role="status">Сохраняем проверенный результат текущего запроса. Новые этапы не запускаются.</p>}
    {Object.entries(stages).map(([stage,label])=>{
      const units=data.units.filter(unit=>unit.stage===stage);
      const total=units.reduce((sum,unit)=>sum+unit.weight,0);
      const done=units.filter(unit=>unit.status==='completed').reduce((sum,unit)=>sum+unit.weight,0);
      return <details key={stage} open={units.some(unit=>['running','failed','uncertain'].includes(unit.status))}>
        <summary>{label} · {total?Math.floor(done/total*100):0}%</summary>
        {units.length?units.map(unit=><div key={unit.unit_id} className="draft-field">
          <span>{label}{stage==='characters'?` · пакет ${Number(unit.unit_id.split('_').at(-1))+1}`:''} · {statuses[unit.status]||unit.status}</span>
          {unit.status==='running'&&<progress aria-label={`${label}: запрос выполняется`}/>}
          <small>Попыток: {unit.attempts}</small>
          {unit.error&&<p role="alert">{unit.error}</p>}
          {author&&unit.status==='completed'&&<Button variant="ghost" disabled={busy} onClick={()=>void api<{stage:string;artifact?:unknown}>(`/jobs/${job.id}/generation/checkpoints/${unit.unit_id}?author=true`).then(setInspected).catch(e=>toast.error(e.message))}>Посмотреть результат</Button>}
        </div>):<p>Планируется после проверки входных данных.</p>}
      </details>;
    })}
    <label><input type="checkbox" checked={author} onChange={e=>{setAuthor(e.target.checked);setInspected(null)}}/> Авторский просмотр: содержит секреты мира и знания NPC</label>
    <div className="actions">
      {job.status==='generating'&&<Button variant="outline" disabled={busy} onClick={()=>void act('pause')}>Пауза после этапа</Button>}
      {hasUncertain&&<label><input type="checkbox" checked={uncertain} onChange={e=>setUncertain(e.target.checked)}/> Разрешаю повторить прерванный запрос; предыдущий мог быть оплачен</label>}
      {resumable&&<Button disabled={busy||hasUncertain&&!uncertain} onClick={()=>void act('resume')}>Продолжить генерацию</Button>}
      {!['saved','cancelled'].includes(job.status)&&<Button variant="ghost" disabled={busy} onClick={()=>{setBusy(true);void api(`/jobs/${job.id}/stop`,{}).then(refresh).catch(e=>toast.error(e.message)).finally(()=>setBusy(false))}}>Отменить генерацию</Button>}
    </div>
    <Dialog open={author&&!!inspected} onOpenChange={open=>{if(!open)setInspected(null)}}><DialogContent className="max-h-[85dvh] overflow-y-auto"><DialogHeader><DialogTitle>{stages[inspected?.stage||'']||'Результат этапа'}</DialogTitle><DialogDescription>Авторские данные, включая секреты. Просмотр не останавливает генерацию и не изменяет checkpoint.</DialogDescription></DialogHeader><CheckpointValue value={inspected?.artifact}/></DialogContent></Dialog>
  </section>;
}

function CheckpointValue({value}:{value:unknown}){
  if(value===null||value===undefined)return <span>Не указано</span>;
  if(typeof value!=='object')return <span className="break-words whitespace-pre-wrap">{String(value)}</span>;
  const rows=Object.entries(value);
  return <dl>{rows.map(([key,item])=><div key={key} className="draft-field"><dt className="break-words">{key}</dt><dd><CheckpointValue value={item}/></dd></div>)}</dl>;
}
