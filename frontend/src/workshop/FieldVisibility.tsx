import {ReferenceChecklist} from './ReferenceChecklist';

export type FieldPolicy='default'|'public'|{after:string[]};
export function fromBinding(ids?:string[]):FieldPolicy{
 return !ids?'default':ids.length?{after:ids}:'public';
}
export function wirePolicy(p:FieldPolicy):'default'|string[]{
 return p==='default'?p:p==='public'?[]:[...p.after].sort();
}

/** The server enforces this declaration when it builds the reader projection. */
export function FieldVisibility({policy,onChange,facts}:{policy:FieldPolicy;onChange:(v:FieldPolicy)=>void;facts:[string,string][]}){
 const mode=typeof policy==='object'?'after':policy;
 return <details className="ww-field-visibility">
  <summary>Видимость для игрока</summary>
  <label>Правило показа<select value={mode} onChange={e=>onChange(
   e.target.value==='after'?{after:[]}:e.target.value==='public'?'public':'default'
  )}>
   <option value="default">Автоматически</option>
   <option value="public">Показывать всем</option>
   <option value="after">После раскрытия тайны</option>
  </select></label>
  <p className="workshop-hint">{mode==='default'?'Действуют обычные правила мастерской.':mode==='public'?'Текст этого поля виден в режиме игрока, даже если герой не знает связанной с ним тайны.':'Текст будет доступен, когда управляемый герой узнает все выбранные факты. Просмотр автором не меняет знания героя.'}</p>
  {typeof policy==='object'&&(facts.length?<ReferenceChecklist label="Тайны для открытия поля" value={policy.after} options={facts}
    onChange={ids=>onChange({after:ids.map(String)})}/>:<p>В мире ещё нет доступных для привязки тайн.</p>)}
  {typeof policy==='object'&&!policy.after.length&&<p className="workshop-hint">Для сохранения выберите хотя бы одну тайну.</p>}
 </details>;
}
