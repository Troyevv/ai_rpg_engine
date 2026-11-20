import {createContext,useContext,useState} from 'react';
import {Sparkles} from 'lucide-react';
import {api} from '../api';
import {defaults,type Preferences} from '../types';
import {Dialog,DialogContent,DialogTitle,DialogDescription} from '../components/ui/dialog';
import {Button} from '../components/ui/button';
import {type ProceduralPortrait} from './proceduralPortrait';
import {CharacterAvatar,type PortraitSubject} from '../Portrait';

export const PortraitModels=createContext({prefs:defaults as Preferences,apiKey:''});
type Ticket={id:string;revision:number;model:string;thinking:string;input:number;output:number;cost:string|null;requests:number;count:number;status?:string;message?:string;
 proposals?:Record<string,{descriptor:ProceduralPortrait;warnings:string[]}>;errors?:Record<string,string>};
type Props={workspaceId?:string;saveId?:number;revision:number;cards:PortraitSubject[];disabled?:boolean;onPreview?:(p:ProceduralPortrait)=>void;refresh?:()=>void|Promise<void>};
export function PortraitCommission({workspaceId,saveId,revision,cards,disabled,onPreview,refresh}:Props){
 const {prefs,apiKey}=useContext(PortraitModels);
 const config=workspaceId?prefs.summary:prefs.game;
 const base='/portrait-proposals/'+(workspaceId?'workspace/'+encodeURIComponent(workspaceId):'save/'+saveId);
 const cacheKey=[base,revision,onPreview?cards[0]?.id:'batch'].join('/');
 const [open,setOpen]=useState(false),[pending,setPending]=useState(false),[sending,setSending]=useState(false);
 const [ticket,setTicket]=useState<Ticket|null>(null),[ids,setIds]=useState<string[]>([]),[chosen,setChosen]=useState<string[]>([]);
 const [error,setError]=useState('');
 const task=async(fn:()=>Promise<void>)=>{setPending(true);setError('');try{await fn()}catch(e){setError(String(e))}finally{setPending(false)}};
 const show=async()=>{
  setOpen(true);setIds(onPreview?[cards[0].id]:[]);setChosen([]);setTicket(null);
  const stored=sessionStorage.getItem(cacheKey);
  if(stored)await task(async()=>setTicket(await api<Ticket>(base+'/'+stored)));
 };
 const quote=()=>task(async()=>{
  const t=await api<Ticket>(base,{revision,ids,config,api_key:apiKey});
  sessionStorage.setItem(cacheKey,t.id);setTicket({...t,status:'quoted'});setChosen([]);
 });
 const generate=()=>task(async()=>{
  if(!ticket)return;
  setSending(true);
  try{setTicket(await api<Ticket>(base+'/'+ticket.id+'/generate',{api_key:config.provider==='deepseek'?apiKey:undefined}))}
  catch(e){setTicket({...ticket,status:'unknown'});throw e}
  finally{setSending(false)}
 });
 const results=Object.entries(ticket?.proposals||{});
 const title=onPreview?'Создать по описанию':'Создать портреты по описаниям';
 const label=(cid:string)=>cards.find(c=>c.id===cid)?.name||cid;
 const toggle=(values:string[],id:string)=>values.includes(id)?values.filter(v=>v!==id):[...values,id];
 return <><Button variant="outline" disabled={disabled} onClick={()=>void show()}><Sparkles size={16}/>{title}</Button>
 <Dialog open={open} onOpenChange={v=>{if(!pending)setOpen(v)}}><DialogContent className="portrait-commission"><DialogTitle>{title}</DialogTitle>
 <DialogDescription>Модель подберёт параметры иллюстрации по сохранённой внешности. Перед применением вы увидите результат.</DialogDescription>
 {error&&<p role="alert">{error}</p>}
 {!ticket&&<>{!onPreview&&<fieldset><legend>Персонажи · {ids.length} из 64</legend>{cards.map(c=><label key={c.id}><input type="checkbox" checked={ids.includes(c.id)} disabled={!ids.includes(c.id)&&ids.length>=64} onChange={()=>setIds(toggle(ids,c.id))}/>{c.name}</label>)}</fieldset>}
 <p>{config.model} · Thinking {config.thinking}</p><Button disabled={pending||!ids.length} onClick={()=>void quote()}>Рассчитать расход</Button></>}
 {ticket&&<><p><strong>{ticket.model}</strong> · Thinking {ticket.thinking}</p>
 <p>Персонажей — {ticket.count}, запросов — {ticket.requests}. Вход ≈ {ticket.input} токенов, на ответ до {ticket.output}.
 {' '}{ticket.cost===null?'Тариф неизвестен.':`Оценка при полном ответе ≈ $${Number(ticket.cost).toFixed(5)}.`}</p>
 {ticket.status==='quoted'&&!sending&&<Button disabled={pending} onClick={()=>void generate()}>Подтвердить запрос</Button>}
 {(sending||ticket.status==='running'||ticket.status==='unknown')&&<><p role="status">Проверка состояния запроса. Повторная отправка требует нового подтверждения.</p>
 <Button variant="outline" onClick={async()=>{try{setTicket(await api<Ticket>(base+'/'+ticket.id+'/cancel',{}))}catch(e){setError(String(e))}}}>Остановить запрос</Button>
 {!sending&&<Button onClick={()=>void task(async()=>setTicket(await api<Ticket>(base+'/'+ticket.id)))}>Обновить состояние</Button>}</>}
 {ticket.message&&<p role="status">{ticket.message}</p>}
 {ticket.status==='interrupted'&&!ticket.message&&<p role="status">Отправка прервана. Списание может быть неизвестно. Доступные предложения сохранены.</p>}
 {ticket.status==='cancelled'&&<p>Запрос остановлен.</p>}
 {Object.entries(ticket.errors||{}).map(([cid,reason])=><p key={cid}>{label(cid)} · {reason}</p>)}
 {results.map(([cid,row])=><div className="commission-result" key={cid}>
 <CharacterAvatar subject={cards.find(c=>c.id===cid)!} workspaceId={workspaceId} saveId={saveId} author size={64}/>
 <span aria-hidden="true">→</span><CharacterAvatar subject={{id:cid,name:label(cid),procedural_portrait:row.descriptor}} size={64}/>
 <div><strong>{label(cid)}</strong><p>{row.warnings.join(' ')}</p>
 {onPreview?<Button onClick={()=>{onPreview(row.descriptor);setOpen(false)}}>В предпросмотр</Button>:<label><input type="checkbox" checked={chosen.includes(cid)} onChange={()=>setChosen(toggle(chosen,cid))}/>Заменить текущий портрет</label>}</div></div>)}
 {!onPreview&&results.length>0&&<Button disabled={!chosen.length||pending} onClick={()=>void task(async()=>{
    await api(base+'/'+ticket.id+'/apply',{ids:chosen,revision:ticket.revision});await refresh?.();setOpen(false);
 })}>Применить выбранные · {chosen.length}</Button>}
 {!sending&&ticket.status!=='running'&&<Button variant="ghost" disabled={pending} onClick={()=>{setTicket(null);setError('');sessionStorage.removeItem(cacheKey)}}>{ticket.status==='quoted'?'Изменить выбор':'Новый запрос'}</Button>}</>}
 <Button variant="ghost" disabled={pending} onClick={()=>setOpen(false)}>Закрыть окно</Button>
 </DialogContent></Dialog></>;
}
