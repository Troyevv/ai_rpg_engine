import {useState} from 'react';
import {Button} from '../components/ui/button';
import {Choice} from '../components/ui/choice';
import {Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle} from '../components/ui/dialog';
import {runtimeLabels,type DisplayState} from '../runtimePresentation';
import {StructuredValueEditor} from './StructuredValueEditor';

export type ProposalChange = {op:'add'|'remove'|'replace';path:string;value:unknown;reason:string;detail?:string};

export function ProposalAdjustment({changes,revision,resolve,references,disabled,onSave,onClose}:{
 changes:ProposalChange[];references?:DisplayState;revision:number;disabled:boolean;resolve:(field:string,value:string)=>string|null;
 onSave:(values:Record<number,unknown>,revision:number)=>Promise<void>;onClose:()=>void;
}){
 const options=changes.flatMap((change,index)=>{
  if(change.op==='remove')return [];
  const parts=change.path.split('/').slice(1).map(p=>p.replace(/~1/g,'/').replace(/~0/g,'~'));
  const id=parts[0]==='world'?parts[2]:parts[1];
  const field=parts.at(-1)!;
  const record=change.value!==null&&typeof change.value==='object'?change.value as {name?:string;id?:string}:null;
  let subject=id;
  if(parts[0]==='campaign')subject='Мир';
  if(parts[1]==='characters')subject=resolve('actor_id',id)||id;
  if(parts[0]==='characters'||parts[0]==='locations'){
   const cards=references?.[parts[0]];
   const name=cards?.find(card=>card.id===id)?.name||cards?.[Number(id)]?.name;
   subject=name||record?.name||(parts[0]==='characters'?resolve('actor_id',id):resolve('location_id',id))||id;
  }
  const label=field==='-'||field==='__character'?'Карточка':runtimeLabels[field]||field;
  return [{index,field,label,title:subject&&subject!==field?subject+' · '+label:label}];
 });
 const [index,setIndex]=useState(options[0]?.index);
 const [values,setValues]=useState<Record<number,unknown>>({});
 const [baseRevision]=useState(revision);
 const [error,setError]=useState('');
 const selected=options.find(item=>item.index===index);
 if(!selected)return null;
 const change=changes[index], value=index in values?values[index]:change.value;
 async function save(){
  setError('');
  try{await onSave(values,baseRevision);onClose()}catch(e){setError((e as Error).message)}
 }
 return <Dialog open onOpenChange={open=>{if(!open&&!disabled)onClose()}}>
  <DialogContent className="ww-record-editor ai-adjust-dialog"><DialogHeader>
   <DialogTitle>Скорректировать предложение</DialogTitle>
   <DialogDescription>Можно изменить несколько значений. Сравните обновлённый пакет с миром перед применением.</DialogDescription>
  </DialogHeader><fieldset disabled={disabled}>
   <label>Что изменить<Choice aria-label="Что изменить в предложении" value={String(index)} onValueChange={v=>setIndex(Number(v))}>
    {options.map(o=><option key={o.index} value={o.index}>{o.title}</option>)}
   </Choice></label>
   {change.reason&&change.reason!=='Предложенное изменение.'&&<p>{change.reason}</p>}
   {selected.field.endsWith('_date')&&typeof value==='string'
    ?<label>{selected.label}<input type="text" aria-label={selected.label} placeholder="ГГГГ-ММ-ДД" value={value}
      onChange={e=>{setError('');setValues(prev=>({...prev,[index]:e.target.value}))}}/></label>
    :<StructuredValueEditor key={index} field={selected.field} label={selected.label} value={value}
      onChange={next=>{setError('');setValues(prev=>({...prev,[index]:next}))}}/>}
  </fieldset>{error&&<p role="alert">{error}</p>}{baseRevision!==revision&&<p role="alert">Предпросмотр изменился. Откройте актуальные значения.</p>}
  <footer><Button variant="ghost" disabled={disabled} onClick={onClose}>Отмена</Button>
   <Button disabled={disabled||baseRevision!==revision||!Object.keys(values).length} onClick={()=>void save()}>Обновить предпросмотр</Button></footer>
  </DialogContent></Dialog>;
}
