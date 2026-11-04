import {useState} from 'react';
import {runtimeLabels,enumLabels} from '../runtimePresentation';
type Schema=Record<string,any>;
function schemaOf(schema:Schema|undefined,defs:Record<string,Schema>):Schema {
 if(!schema)return {};
 if(schema.$ref)return defs[schema.$ref.split('/').pop()]||{};
 if(schema.anyOf){const nonNull=schema.anyOf.find((s:Schema)=>s.type!=='null');return {...schemaOf(nonNull,defs),nullable:schema.anyOf.some((s:Schema)=>s.type==='null')}}
 return schema;
}
export function StructuredValueEditor({value,onChange,schema,definitions={},label,field='',references,required=false}:{value:unknown;onChange:(v:unknown)=>void;schema?:Schema;definitions?:Record<string,Schema>;label:string;field?:string;required?:boolean;references?:(field:string)=>[string,string][]|null}) {
 const s=schemaOf(schema,definitions);const [newKey,setNewKey]=useState('');
 const type=s.type||(Array.isArray(value)?'array':value!==null&&typeof value==='object'?'object':typeof value==='boolean'?'boolean':typeof value==='number'?'number':'string');
 const empty=()=>s.default!=null?s.default:s.enum?.length?s.enum[0]:type==='array'?[]:type==='object'?{}:type==='boolean'?false:type==='number'||type==='integer'?0:'';
 const refs=references?.(field);
 if(value===null||value===undefined&&!required)return <div className="ww-unset"><span>{value===null?'Неизвестно':'Не задано'}</span><button type="button" onClick={()=>onChange(empty())}>Задать {label.toLowerCase()}</button></div>;
 const reset=<>{s.nullable&&<button type="button" className="ww-text-button" onClick={()=>onChange(null)}>Оставить неизвестным</button>}</>;
 if(s.enum||refs&&type!=='array')return <label>{label}<select aria-label={label} aria-required={required||undefined} value={String(value??'')} onChange={e=>onChange(e.target.value)}>{value===undefined&&<option value="">Выберите значение</option>}{(s.enum?s.enum.map((v:string)=>[v,enumLabels[v]||v]):refs!).map(([v,n]:[string,string])=><option key={v} value={v}>{n}</option>)}</select>{reset}</label>;
 if(type==='boolean')return <label>{label}<select aria-label={label} aria-required={required||undefined} value={String(value??'')} onChange={e=>onChange(e.target.value==='true')}>{value===undefined&&<option value="">Выберите значение</option>}<option value="true">Да</option><option value="false">Нет</option></select>{reset}</label>;
 if(type==='number'||type==='integer')return <label>{label}<input aria-label={label} aria-required={required||undefined} min={s.minimum} max={s.maximum} type="number" step={type==='integer'?1:'any'} value={String(value??'')} onChange={e=>{if(e.target.value!==''&&Number.isFinite(Number(e.target.value)))onChange(Number(e.target.value))}}/>{reset}</label>;
 if(type==='array'){
  const rows=Array.isArray(value)?value:[];
  if(refs)return <fieldset><legend>{label}</legend>{refs.map(([id,name])=><label key={id}><input type="checkbox" checked={rows.includes(id)} onChange={e=>onChange(e.target.checked?[...rows,id]:rows.filter(v=>v!==id))}/>{name}</label>)}{reset}</fieldset>;
  const item=schemaOf(s.items,definitions);const add=()=>onChange([...rows,item.default??(item.type==='object'||item.properties?{}:item.type==='number'||item.type==='integer'?0:'')]);
  return <fieldset className="ww-structured"><legend>{label}</legend>{rows.map((row,i)=><div className="ww-structured-row" key={i}><StructuredValueEditor value={row} schema={s.items} definitions={definitions} label={`${label} · ${i+1}`} onChange={v=>onChange(rows.map((r,j)=>i===j?v:r))} references={references}/><div className="ww-record-actions"><button type="button" onClick={()=>onChange(rows.filter((_,j)=>j!==i))}>Удалить запись {i+1}</button><button type="button" disabled={!i} onClick={()=>{const next=[...rows];[next[i],next[i-1]]=[next[i-1],next[i]];onChange(next)}}>Выше</button></div></div>)}<button type="button" onClick={add}>Добавить запись</button>{reset}</fieldset>;
 }
 if(type==='object'){
  const record=(value||{}) as Record<string,unknown>;const keys=[...new Set([...Object.keys(s.properties||{}),...Object.keys(record)])];
  const technical=['source_sequence','revision','source_event_id','reviewed_signature','review_required'];
  const emptyField=(value:unknown)=>value==null||value===''||typeof value==='object'&&Object.keys(value).length===0;
  const extra=keys.filter(key=>!s.required?.includes(key)&&(technical.includes(key)||emptyField(record[key])));
  const renderField=(key:string)=><div key={key}>{s.required?.includes(key)&&<span className="ww-required">Обязательное поле{record[key]===undefined?' · не заполнено':''}</span>}<StructuredValueEditor value={record[key]} required={s.required?.includes(key)} schema={s.properties?.[key]||s.additionalProperties} definitions={definitions} field={key} label={runtimeLabels[key]||s.properties?.[key]?.title||key} references={references} onChange={v=>onChange({...record,[key]:v})}/>{key in record&&!s.required?.includes(key)&&<button type="button" className="ww-text-button" onClick={()=>{const next={...record};delete next[key];onChange(next)}}>Не задавать поле</button>}</div>;
  return <fieldset className="ww-structured"><legend>{label}</legend>{keys.filter(key=>!extra.includes(key)).map(renderField)}{extra.length>0&&<details className="ww-optional-fields"><summary>Дополнительные поля · {extra.length}</summary>{extra.map(renderField)}</details>}{!s.properties&&<div className="ww-record-actions"><input aria-label={`Название записи · ${label}`} value={newKey} onChange={e=>setNewKey(e.target.value)}/><button type="button" disabled={!newKey.trim()||newKey in record||['__proto__','constructor','prototype'].includes(newKey)} onClick={()=>{const spec=schemaOf(s.additionalProperties,definitions);onChange({...record,[newKey]:spec.default??(spec.type==='array'?[]:spec.type==='object'?{}:spec.type==='number'||spec.type==='integer'?0:spec.type==='boolean'?false:'')});setNewKey('')}}>Добавить свойство</button></div>}{reset}</fieldset>;
 }
 if(['id','name','title','label','date','time'].includes(field)||field.endsWith('_id'))return <label>{label}<input aria-label={label} aria-required={required||undefined} value={String(value??'')} onChange={e=>onChange(e.target.value)}/>{reset}</label>;
 return <label>{label}<textarea aria-label={label} aria-required={required||undefined} value={String(value??'')} onChange={e=>onChange(e.target.value)}/>{reset}</label>;
}
