import {CheckpointRecordForm,schemaAt,type Schema,type Reference} from './CheckpointRecordForm';
import {useState} from 'react';
import {api} from './api';
import {Button} from './components/ui/button';
import {Textarea} from './components/ui/textarea';
import {WorldCreationSettings,defaultCreation,type Creation} from './WorldCreationSettings';
type Checkpoint={stage:string;unit:string;artifact_version:number;artifact?:unknown;locked_paths?:string[];editor_schema?:Schema;reference_options?:Reference[]};
type Impact={stale_units:string[];locked_paths:string[]};
const names:Record<string,string>={campaign:'Описание мира',characters:'Персонажи',cards:'Карточки',locations:'Локации',organizations:'Организации',objective_relations:'Семейные связи',relationships:'Отношения',residences:'Жильё',roles:'Роли',facts:'Факты',knowledge:'Знания',initial_history:'Предыстория',camera:'Начальная сцена',world_time:'Время мира',claims:'Ограничения',entities:'Сущности',name:'Имя',display_name:'Имя',text:'Описание',description:'Описание',situation:'Ситуация',classification:'Статус',value:'Значение',blocking:'Требует решения',time_scope:'Когда',holder_ids:'Кто знает',rules:'Проверки'};
const printable=(v:unknown)=>v!==null&&typeof v==='object'?JSON.stringify(v,null,2):String(v??'');
function fields(value:unknown,path='',label=''): {path:string;label:string;value:unknown}[]{
 if(value===null||typeof value!=='object')return [{path,label,value}];
 return [...(path?[{path,label:label+' · запись целиком',value}]:[]),...Object.entries(value).flatMap(([key,item])=>['id','existing_id','key','spans','brief','amendments','constraint_revision','fixed_claim_ids','blocking_ids','version','registry'].includes(key)?[]:fields(item,path+'/'+key.replaceAll('~','~0').replaceAll('/','~1'),[label,names[key]||key].filter(Boolean).join(' · ')))];
}
export function CheckpointEditor({checkpoint,revision,workspaceId,jobId,onSaved}:{checkpoint:Checkpoint;revision:number;workspaceId:string;jobId:string;onSaved:()=>void}){
 const options=fields(checkpoint.artifact).filter(r=>checkpoint.stage!=='interpret'||/^\/(claims\/\d+(\/(value|description|classification|blocking|time_scope|subject_id|holder_ids|related_ids|rules))?|entities\/\d+\/(name|tier))$/.test(r.path));
 const [index,setIndex]=useState(0),[value,setValue]=useState(printable(options[0]?.value));
 const [ack,setAck]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [impact,setImpact]=useState<Impact|null>(null),[operation,setOperation]=useState('patch');
 const [creation,setCreation]=useState<Creation>({...defaultCreation,...(checkpoint.artifact as {creation?:Creation})?.creation});
 const [advanced,setAdvanced]=useState(false);
 const [settings,setSettings]=useState(false);const field=options[index];
 const submit=async(preview:boolean,action=operation)=>{setBusy(true);setError('');setOperation(action);try{
 const parsed=settings?creation:field?.value!==null&&typeof field?.value==='object'?JSON.parse(value):typeof field?.value==='boolean'?value==='true':typeof field?.value==='number'?Number(value):field?.value===null&&value===''?null:value;
 const result=await api<Impact>(`/workspaces/${workspaceId}/draft`,{operation:action,kind:'checkpoint',generation_job:jobId,generation_unit:checkpoint.unit,artifact_version:checkpoint.artifact_version,revision,field:settings?'/creation':field?.path||'',value:parsed,preview,warnings_ack:ack},'PATCH');
 if(preview)setImpact(result);else onSaved();
 }catch(e){setImpact(null);setError((e as Error).message)}finally{setBusy(false)}};
 return <section aria-label="Редактирование этапа на паузе"><h3>Изменить результат этапа</h3><p>Правка сохраняется новой версией и защищается от автоматической перезаписи.</p>
 {checkpoint.stage==='interpret'&&<label><input type="checkbox" checked={settings} onChange={e=>{setSettings(e.target.checked);setImpact(null)}}/>Пересмотреть настройки генератора</label>}
 {settings?<WorldCreationSettings value={creation} onChange={v=>{setCreation(v);setImpact(null)}} disabled={busy}/>:field&&<><label>Поле этапа<select aria-label="Поле этапа" value={index} disabled={busy} onChange={e=>{const i=Number(e.target.value);setIndex(i);setValue(printable(options[i].value));setImpact(null);setError('')}}>{options.map((r,i)=><option key={r.path} value={i}>{r.label}</option>)}</select></label>
 {field.value!==null&&typeof field.value==='object'&&checkpoint.stage!=='interpret'&&<label><input type="checkbox" checked={advanced} onChange={e=>{if(!e.target.checked){try{JSON.parse(value)}catch{setError('Исправьте JSON перед переходом к форме');return}}setAdvanced(e.target.checked)}}/>Расширенный JSON</label>}
 {field.value!==null&&typeof field.value==='object'&&checkpoint.stage!=='interpret'&&!advanced?<CheckpointRecordForm value={JSON.parse(value)} onChange={v=>{setValue(JSON.stringify(v));setImpact(null)}} schema={schemaAt(checkpoint.editor_schema||{},field.path)} root={checkpoint.editor_schema||{}} references={checkpoint.reference_options} disabled={busy}/>:typeof field.value==='boolean'?<label><input type="checkbox" checked={value==='true'} onChange={e=>{setValue(String(e.target.checked));setImpact(null)}}/>Да</label>:<Textarea aria-label="Значение поля этапа" value={value} onChange={e=>{setValue(e.target.value);setImpact(null)}}/>}
 {field.value!==null&&typeof field.value==='object'&&(advanced||checkpoint.stage==='interpret')&&<p>Расширенное редактирование записи в JSON. Сервер проверит структуру и ограничения. Идентификаторы и источник ограничения сохраняются.</p>}</>}
 {checkpoint.stage==='interpret'&&<label><input type="checkbox" checked={ack} onChange={e=>{setAck(e.target.checked);setImpact(null)}}/>Я явно пересматриваю ограничение. Исходный текст останется в истории.</label>}
 <Button disabled={busy||checkpoint.stage==='interpret'&&!ack} onClick={()=>void submit(true,'patch')}>Проверить изменение этапа</Button>
 {!settings&&checkpoint.locked_paths?.includes(field?.path)&&<Button disabled={busy} variant="outline" onClick={()=>void submit(true,'unlock')}>Снять блокировку поля</Button>}
 {checkpoint.stage!=='interpret'&&<Button disabled={busy} variant="outline" onClick={()=>void submit(true,'regenerate')}>Перегенерировать этот этап</Button>}
 {error&&<p role="alert">{error}</p>}{impact&&<div role="status"><p>Повторная генерация: {impact.stale_units.join(', ')||'не требуется'}. Остальные результаты сохраняются.</p><p>Защищено полей: {impact.locked_paths.length}.</p><Button disabled={busy} onClick={()=>void submit(false)}>Применить изменение этапа</Button></div>}
 </section>;
}
