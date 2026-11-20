import {useEffect,useRef,useState} from 'react';
import {api} from '../api';
import {ProposalAdjustment} from './ProposalAdjustment';
import {Button} from '../components/ui/button';
import {RuntimeValue,resolver} from '../runtimePresentation';
type Proposal={status:string;stale:boolean;base_version:number;target:{kind:string;id:string;field:string};before:unknown;value:unknown;original_value?:unknown;warnings:string[]};
export function FieldProposal({wid,jobId,revision,resolve,onApplied,onRejected,refresh}:{wid:string;jobId:string;revision:number;resolve:ReturnType<typeof resolver>;onApplied:()=>Promise<void>;onRejected:()=>void;refresh:()=>Promise<void>}){
 const guard=useRef(false);
 const [adjust,setAdjust]=useState(false);
 const [data,setData]=useState<Proposal|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[ack,setAck]=useState(false);
 useEffect(()=>{const c=new AbortController();void api<Proposal>(`/workspaces/${wid}/draft/field-proposals/${jobId}?author=true`,undefined,'GET',c.signal).then(setData).catch(e=>{if(!c.signal.aborted)setError(e.message)});return()=>c.abort()},[wid,jobId,revision]);
 async function decide(decision:'accept'|'reject'){
  if(guard.current)return;guard.current=true;setBusy(true);setError('');try{await api(`/workspaces/${wid}/draft/field-proposals/${jobId}`,{revision,decision,accept_warnings:ack});if(decision==='accept')await onApplied();else onRejected()}catch(e){setError((e as Error).message)}finally{guard.current=false;setBusy(false)}
 }
 return <section className="ww-field-proposal"><h3>Вариант от ИИ</h3>{error&&<p role="alert">{error}</p>}{!data&&!error&&<p role="status">Загружаем предложение…</p>}{data&&<><p>На основе версии #{data.base_version}. Исходное значение ещё не изменено.</p><div className="ai-diff-values"><div><h4>Было</h4><RuntimeValue field={data.target.field} value={data.before} resolve={resolve} author/></div><div><h4>Предложено</h4><RuntimeValue field={data.target.field} value={data.value} resolve={resolve} author/></div></div>{'original_value' in data&&<details><summary>Исходное значение модели</summary><RuntimeValue field={data.target.field} value={data.original_value} resolve={resolve} author/></details>}
 <Button variant="outline" disabled={busy||data.stale||data.status!=='preview'} onClick={()=>setAdjust(true)}>Скорректировать значение</Button>
 {adjust&&<ProposalAdjustment revision={revision} disabled={busy} resolve={resolve} changes={[{op:'replace',path:'/characters/'+data.target.id+'/'+(data.target.field||'Карточка').replace(/^fields\./,''),value:data.value,reason:''}]}
  onClose={()=>setAdjust(false)} onSave={async(values,baseRevision)=>{
   if(guard.current)throw new Error('Сохранение уже выполняется.');
   guard.current=true;setBusy(true);
   try{await api(`/workspaces/${wid}/draft/field-proposals/${jobId}`,{revision:baseRevision,decision:'revise',value:values[0]});await refresh()}
   finally{guard.current=false;setBusy(false)}
  }}/>}
 {data.stale&&<p role="alert">Мир изменился: этот вариант нельзя применить. Создайте новый на основе текущей версии.</p>}{data.warnings.map((text,i)=><p key={i}>{text}</p>)}{!!data.warnings.length&&<label><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>Принимаю предупреждения</label>}<Button variant="ghost" disabled={busy||data.status!=='preview'} onClick={()=>void decide('reject')}>Отклонить вариант</Button><Button disabled={busy||data.stale||data.status!=='preview'||!!data.warnings.length&&!ack} onClick={()=>void decide('accept')}>Применить вариант</Button></>}</section>;
}
