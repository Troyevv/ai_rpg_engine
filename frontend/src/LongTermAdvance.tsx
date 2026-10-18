import {useEffect, useState} from 'react';
import {api} from './api';
import {Button} from './components/ui/button';
import {Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription} from './components/ui/dialog';
import type {Save} from './types';

export type AdvanceRequest = {amount:number;unit:'weeks'|'months'|'years';max_llm_calls:number;reason:string};
type Preview = {revision:number;label:string;interruption:{kind:string}|null;candidate_count:number;decisions:{id:string;context:string;kind:string}[]};

export function LongTermAdvance({save,disabled,submit}:{save:Save;disabled:boolean;submit:(request:AdvanceRequest)=>void}) {
  const [open,setOpen]=useState(false);
  const [request,setRequest]=useState<AdvanceRequest>({amount:1,unit:'years',max_llm_calls:4,reason:''});
  const [preview,setPreview]=useState<Preview|null>(null);
  const [error,setError]=useState('');
  useEffect(()=>{
    if(!open)return;
    const controller=new AbortController();setPreview(null);setError('');
    api<Preview>(`/saves/${save.id}/long-term/preview`,request,'POST',controller.signal)
      .then(setPreview).catch(e=>{if(!controller.signal.aborted)setError(e.message)});
    return ()=>controller.abort();
  },[open,request,save.id,save.revision]);
  return <><Button variant="ghost" disabled={disabled} onClick={()=>setOpen(true)}>Длительный переход</Button>
    <Dialog open={open} onOpenChange={setOpen}><DialogContent className="time-skip-sheet"><DialogHeader>
      <DialogTitle>Длительный переход</DialogTitle>
      <DialogDescription>Недели, месяцы или годы. Обязательства могут прервать переход. Возможности не становятся событиями без подтверждённого исхода; решения героя остаются за тобой.</DialogDescription>
    </DialogHeader>
    <label>Интервал<input aria-label="Количество единиц перехода" type="number" min={1} max={200} value={request.amount} onChange={e=>setRequest({...request,amount:Number(e.target.value)})}/></label>
    <label>Единица<select aria-label="Единица перехода" value={request.unit} onChange={e=>setRequest({...request,unit:e.target.value as AdvanceRequest['unit']})}>
      <option value="weeks">Недели</option><option value="months">Месяцы</option><option value="years">Годы</option>
    </select></label>
    <label>Лимит обращений к модели<input aria-label="Лимит обращений к модели" type="number" min={0} max={8} value={request.max_llm_calls} onChange={e=>setRequest({...request,max_llm_calls:Number(e.target.value)})}/></label>
    <p>Одна группа исходов требует двух обращений. При нулевом лимите выполняются только определённые переходы, остальные причины остаются нерешёнными.</p>
    <label>Причина<input value={request.reason} maxLength={1000} onChange={e=>setRequest({...request,reason:e.target.value})}/></label>
    {error&&<p role="alert">{error}</p>}
    {preview&&<div aria-live="polite"><strong>{preview.label}</strong>{preview.interruption&&<p>Переход остановится для решения игрока.</p>}<p>Причин для рассмотрения: {preview.candidate_count}. Возможностей для героя: {preview.decisions.length}.</p></div>}
    <Button disabled={disabled||!preview||preview.revision!==save.revision} onClick={()=>{submit(request);setOpen(false)}}>Подтвердить длительный переход</Button>
    </DialogContent></Dialog></>;
}
