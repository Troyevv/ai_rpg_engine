import {useEffect, useState, type RefObject} from 'react';
import {api, download} from './api';
import type {Turn} from './types';
import {Button} from './components/ui/button';

type Build = {id:string; revision:string|null};
type Counts = {rows:number; spoken:number; missing?:number; null?:number; empty?:number; invalid?:number};
type Receipt = {
  sequence:number; contract:string|null; generating_build:Build|null; wire_format:string|null;
  regenerated:boolean; recovered:boolean; created_at:string; raw:Counts|null; checkpoint:Counts|null;
  published:Counts|null; saved_variant:Counts|null; saved_turn:Counts|null; same_saved_choices:boolean|null;
};
type Health = {version:string; backend_build?:Build; choice_contract?:string};
export type ChoiceView = {turn?:Turn; revision:number; list:RefObject<HTMLDivElement|null>};

export function ChoiceDiagnostics({saveId, view, refresh}:{saveId:number; view:ChoiceView; refresh:number}) {
  const [health,setHealth]=useState<Health|null>(null);
  const [receipt,setReceipt]=useState<Receipt|null>(null);
  const [error,setError]=useState('');
  const {turn,list}=view;
  const tid=turn?.id, variant=turn?.active_variant_id;
  useEffect(()=>{
    const controller=new AbortController();
    setError('');setReceipt(null);setHealth(null);
    void api<Health>('/health',undefined,'GET',controller.signal).then(setHealth).catch(()=>{});
    if(tid!=null && variant) void api<Receipt>(`/saves/${saveId}/turns/${tid}/choice-diagnostics?variant=${encodeURIComponent(variant)}`,undefined,'GET',controller.signal)
      .then(setReceipt).catch(()=>{if(!controller.signal.aborted)setError('Отчёт этого варианта недоступен. Проверьте версию сервера и откройте диагностику заново.');});
    return ()=>controller.abort();
  },[saveId,tid,variant,view.revision,refresh]);
  const physical=turn?.choices.filter(c=>(c.interaction_channel||'physical')==='physical');
  const apiRows=physical?{rows:physical.length,spoken:physical.filter(c=>c.speech).length}:null;
  const cards=list.current;
  const rendered=cards?{rows:cards.querySelectorAll('button').length,spoken:cards.querySelectorAll('button .choice-speech').length}:null;
  const client={revision:import.meta.env.VITE_CLIENT_REVISION||null,asset:new URL(import.meta.url).pathname.split('/').pop()};
  const report={client, server:health?.backend_build||null, server_version:health?.version||null,
    supported_contract:health?.choice_contract||null, source:{turn:tid,variant,sequence:turn?.sequence},receipt,physical_api:apiRows,cards:rendered};
  const stages:[string,Counts|null|undefined][]=[
    ['Ответ модели',receipt?.raw],['После декодирования',receipt?.checkpoint],['При первой публикации',receipt?.published],['Вариант в SQLite',receipt?.saved_variant],
    ['Ход в SQLite',receipt?.saved_turn],['Получено для физической сцены',apiRows],['Карточки в интерфейсе',rendered]];
  return <section aria-label="Диагностика вариантов">
    <h3>Варианты на игровом экране</h3>
    <p>Клиент {client.revision||client.asset} · Сервер {health?.backend_build?.revision||health?.backend_build?.id||'сборка неизвестна'} · Текущий контракт сервера {health?.choice_contract||'не указан'}</p>
    {turn?<p>Источник — ход #{turn.sequence}. Контракт запроса {receipt?.contract||'неизвестен'}. {receipt?.regenerated?'Перегенерация. ':''}{receipt?.recovered?'Восстановленный ответ. ':''}{receipt?.created_at}</p>:<p>У текущей сцены нет источника вариантов.</p>}
    {health&&!health.choice_contract&&<p role="status">Сервер не сообщает версию контракта. Если приложение обновлено, завершите активный ход и перезапустите сервер.</p>}
    {receipt&&<p className="muted small">Сборка при генерации: {receipt.generating_build?.revision||receipt.generating_build?.id||'не записана'}. Формат ответа: {receipt.wire_format||'не записан'}.</p>}
    {error&&<p role="status">{error}</p>}
    {receipt?.contract==='narrative-actions/1'&&<p>Этот вариант сохранён с прежним контрактом, допускавшим одно поле text. Обычный следующий ход получает контракт работающего сервера. Точная перегенерация использует записанный запрос.</p>}
    {receipt?.raw&&receipt.raw.missing===receipt.raw.rows&&receipt.raw.rows>0&&<p>В исходном ответе поле speech отсутствовало у всех вариантов.</p>}
    {receipt?.raw&&<p className="muted small">Поле speech в ответе модели: с репликой — {receipt.raw.spoken}, null — {receipt.raw.null}, пустая строка — {receipt.raw.empty}, отсутствует — {receipt.raw.missing}, другой тип — {receipt.raw.invalid}.</p>}
    <table><thead><tr><th>Этап</th><th>Вариантов</th><th>С репликой</th></tr></thead>
      <tbody>{stages.map(([label,count])=><tr key={label}><th scope="row">{label}</th><td>{count?.rows??'—'}</td><td>{count?.spoken??'—'}</td></tr>)}</tbody></table>
    <p className="muted small">Прочерк означает, что запись этапа недоступна. В отчёт входят идентификаторы сборок и счётчики полей. Его можно приложить к сообщению об ошибке.</p>
    <Button variant="outline" onClick={()=>download(JSON.stringify(report,null,2),'narrative-choices.json','application/json')}>Скачать диагностику вариантов</Button>
  </section>;
}
