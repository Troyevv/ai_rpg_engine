import {useEffect,useState} from 'react';
import {toast} from 'sonner';
import {api} from './api';
import {InterpretationPreview} from './InterpretationPreview';
import {CheckpointEditor} from './CheckpointEditor';
import type {Job} from './types';
import {Textarea} from './components/ui/textarea';
import {Button} from './components/ui/button';
import {Dialog,DialogContent,DialogDescription,DialogHeader,DialogTitle} from './components/ui/dialog';

type Unit={unit_id:string;stage:string;status:string;weight:number;attempts:number;error:string};
type Checkpoint={stage:string;artifact_version:number;artifact?:unknown;unit:string};
type Impact={revision:number;artifact_version:number;stale_units:string[]};
type Progress={revision:number;overall_progress:number;units:Unit[]};
const stages:Record<string,string>={interpret:'Понимание замысла',setting:'Сеттинг и план',places:'Локации и организации',characters:'Персонажи',life:'Отношения и обстоятельства',lore:'Предыстория и знания',opening:'Начальная сцена',assembly:'Сборка и проверка'};
const statuses:Record<string,string>={pending:'Ожидает',running:'Выполняется',completed:'Проверено',saved:'Готово',failed:'Ошибка',stale:'Нужна повторная проверка',uncertain:'Исход запроса неизвестен',cancelled:'Отменено',generating:'Создаём мир',pause_requested:'Завершаем текущий этап перед паузой',paused:'На паузе',waiting_for_credentials:'Нужен доступ к провайдеру'};

export function WorldGenerationProgress({job,workspaceId,apiKey,refresh}:{job:Job;workspaceId:string;apiKey:string;refresh:()=>void}){
  const [data,setData]=useState<Progress|null>(null);
  const [busy,setBusy]=useState(false);
  const [uncertain,setUncertain]=useState(false);
  const [author,setAuthor]=useState(false);
  const [inspected,setInspected]=useState<Checkpoint|null>(null);
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
          {author&&unit.status==='completed'&&<Button variant="ghost" disabled={busy} onClick={()=>void api<Omit<Checkpoint,'unit'>>(`/jobs/${job.id}/generation/checkpoints/${unit.unit_id}?author=true`).then(value=>setInspected({...value,unit:unit.unit_id})).catch(e=>toast.error(e.message))}>Посмотреть результат</Button>}
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
    <Dialog open={author&&!!inspected} onOpenChange={open=>{if(!open)setInspected(null)}}><DialogContent className="max-h-[85dvh] overflow-y-auto"><DialogHeader><DialogTitle>{stages[inspected?.stage||'']||'Результат этапа'}</DialogTitle><DialogDescription>Авторские данные, включая секреты. Просмотр не останавливает генерацию и не изменяет checkpoint.</DialogDescription></DialogHeader>{inspected?.stage==='characters'&&job.status==='paused'&&<CharacterCheckpointEdit key={inspected.artifact_version} checkpoint={inspected} revision={data.revision} workspaceId={workspaceId} jobId={job.id} onSaved={()=>{setInspected(null);void api<Progress>(`/jobs/${job.id}/generation`).then(setData);refresh()}}/>}{inspected&&inspected.stage!=='assembly'&&job.status==='paused'&&<CheckpointEditor key={'stage'+inspected.artifact_version} checkpoint={inspected} revision={data.revision} workspaceId={workspaceId} jobId={job.id} onSaved={()=>{setInspected(null);void api<Progress>(`/jobs/${job.id}/generation`).then(setData);refresh()}}/>}{inspected?.stage==='interpret'?<InterpretationPreview value={inspected.artifact}/>:<CheckpointValue value={inspected?.artifact}/>}</DialogContent></Dialog>
  </section>;
}

function CheckpointValue({value}:{value:unknown}){
  if(value===null||value===undefined)return <span>Не указано</span>;
  if(typeof value!=='object')return <span className="break-words whitespace-pre-wrap">{String(value)}</span>;
  const rows=Object.entries(value);
  return <dl>{rows.map(([key,item])=><div key={key} className="draft-field"><dt className="break-words">{key}</dt><dd><CheckpointValue value={item}/></dd></div>)}</dl>;
}


const personalityLabels:Record<string,string>={traits:'Черты характера',communication:'Манера общения',habits:'Привычки',strengths:'Сильные стороны',weaknesses:'Слабые стороны',fears:'Страхи',preferences:'Предпочтения',temperament:'Темперамент'};
function CharacterCheckpointEdit({checkpoint,revision,workspaceId,jobId,onSaved}:{checkpoint:Checkpoint;revision:number;workspaceId:string;jobId:string;onSaved:()=>void}){
  const artifact=checkpoint.artifact as {characters:Record<string,{display_name:string;personality?:{items:Record<string,{field:string;text:string}>}|null}>};
  const choices=Object.entries(artifact.characters).flatMap(([id,actor])=>{
    const items=Object.entries(actor.personality?.items||{});
    return [...items.map(([key,item])=>({id,field:`personality.items.${key}.text`,label:`${actor.display_name} · ${personalityLabels[item.field]||item.field}`,text:item.text})),
      ...Object.entries(personalityLabels).filter(([category])=>!items.some(([,item])=>item.field===category)).map(([category,label])=>({id,field:`personality.${category}`,label:`${actor.display_name} · ${label}`,text:''}))];
  });
  const [selected,setSelected]=useState(0);
  const [value,setValue]=useState(choices[0]?.text||'');
  const [impact,setImpact]=useState<Impact|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const target=choices[selected];
  if(!target)return null;
  const submit=async(preview:boolean)=>{setBusy(true);setError('');try{
    const result=await api<Impact>(`/workspaces/${workspaceId}/draft`,{operation:'patch',kind:'character',entity_id:target.id,field:target.field,value,
      generation_job:jobId,generation_unit:checkpoint.unit,artifact_version:checkpoint.artifact_version,revision,preview},'PATCH');
    if(preview)setImpact(result);else onSaved();
  }catch(e){setImpact(null);setError((e as Error).message)}finally{setBusy(false)}};
  return <section aria-label="Редактирование персонажа на паузе">
    <p>Правка сохраняется отдельной версией. Изменённая черта защищается от перегенерации. Явные ограничения исходного описания менять здесь нельзя.</p>
    <label>Черта персонажа<select value={selected} disabled={busy} onChange={e=>{const index=Number(e.target.value);setSelected(index);setValue(choices[index].text);setImpact(null);setError('')}}>{choices.map((choice,index)=><option key={choice.id+choice.field} value={index}>{choice.label}</option>)}</select></label>
    <Textarea aria-label="Описание черты" value={value} maxLength={3000} disabled={busy} onChange={e=>{setValue(e.target.value);setImpact(null)}}/>
    {error&&<p role="alert">{error}</p>}
    <Button disabled={busy||!value.trim()} onClick={()=>void submit(true)}>Проверить влияние правки</Button>
    {impact&&<div role="status"><p>{impact.stale_units.length?'После продолжения будут пересозданы зависимые результаты:':'Зависимые результаты не изменятся.'}</p>
      <ul>{impact.stale_units.map(unit=><li key={unit}>{stages[unit]||unit}</li>)}</ul>
      <Button disabled={busy} onClick={()=>void submit(false)}>Сохранить правку</Button></div>}
  </section>;
}
