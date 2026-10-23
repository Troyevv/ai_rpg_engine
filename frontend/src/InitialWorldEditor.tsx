import {useState} from 'react';
import {api} from './api';
import {CheckpointRecordForm,type Schema,type Reference} from './CheckpointRecordForm';
import {Button} from './components/ui/button';
import {Textarea} from './components/ui/textarea';
type Data={compiled_conflict?:boolean;revision:number;values:Record<string,unknown>;sections:Record<string,string>;schema:Schema;references:Reference[]};
export function InitialWorldEditor({workspaceId,disabled,onSaved}:{workspaceId:string;disabled:boolean;onSaved:()=>void}){
 const [data,setData]=useState<Data|null>(null),[section,setSection]=useState('characters');
 const [value,setValue]=useState<unknown>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[advanced,setAdvanced]=useState(false),[text,setText]=useState('');
 const [replaceCompiled,setReplaceCompiled]=useState(false);
 const load=async()=>{setBusy(true);setError('');try{const next=await api<Data>(`/workspaces/${workspaceId}/draft/canonical?author=true`);setData(next);setValue(next.values[section]);setText(JSON.stringify(next.values[section],null,2))}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 const save=async()=>{if(!data)return;setBusy(true);setError('');try{await api(`/workspaces/${workspaceId}/draft`,{revision:data.revision,operation:'patch',kind:'canonical',field:section,value:advanced?JSON.parse(text):value,warnings_ack:!data.compiled_conflict||replaceCompiled},'PATCH');setData(null);onSaved()}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 return <section aria-label="Полный редактор начального мира" className="workshop-review"><h3>Начальное состояние мира</h3><p>Семья, организации, знания, история и время. Изменения сохраняются в существующем черновике; ссылки и игровые инварианты проверяются перед сохранением.</p>
 {!data?<Button disabled={disabled||busy} variant="outline" onClick={()=>void load()}>Открыть полный редактор</Button>:<>
 <label>Раздел мира<select aria-label="Раздел мира" disabled={busy} value={section} onChange={e=>{const key=e.target.value;setSection(key);setValue(data.values[key]);setText(JSON.stringify(data.values[key],null,2));setError('')}}>{Object.entries(data.sections).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
 <label><input type="checkbox" checked={advanced} onChange={e=>{if(e.target.checked)setText(JSON.stringify(value,null,2));else {try{setValue(JSON.parse(text))}catch{setError('Исправьте JSON перед переходом к форме');return}}setAdvanced(e.target.checked)}}/>Расширенный JSON</label>
 {advanced?<Textarea aria-label="JSON раздела мира" value={text} onChange={e=>setText(e.target.value)}/>:<CheckpointRecordForm key={section} value={value} onChange={setValue} schema={data.schema.properties?.[section]} root={data.schema} references={data.references} name={data.sections[section]} disabled={disabled||busy}/>}
 <>{data.compiled_conflict&&<label><input type="checkbox" checked={replaceCompiled} onChange={e=>setReplaceCompiled(e.target.checked)}/>Подтверждаю замену ручных правок скомпилированного мира</label>}</><Button disabled={disabled||busy||!!data.compiled_conflict&&!replaceCompiled} onClick={()=>void save()}>Сохранить раздел мира</Button><Button variant="ghost" onClick={()=>setData(null)}>Закрыть редактор</Button></>}
 {error&&<p role="alert">{error}</p>}</section>;
}
