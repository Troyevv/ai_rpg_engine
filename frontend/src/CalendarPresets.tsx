import {useEffect,useState} from 'react';
import {api} from './api';
export type Presets={holidays:string;country:string|null;subdivision:string|null;observed:boolean;seasons:string};
export const defaultPresets:Presets={holidays:'auto',country:null,subdivision:null,observed:false,seasons:'auto'};
type Catalog={min_year:number;max_year:number;countries:{code:string;name:string;group:string;subdivisions:string[]}[]};
export type Preview={current:{date:string|null;season:string|null};events:{id:string;date:string;name:string;observed:boolean}[];notices:string[];regional:{country:string;display_name?:string;subdivision:string|null}|null};
export function PresetPreview({value}:{value:Preview|null}){return value&&<div aria-label="Предпросмотр календаря"><p>{value.regional?`${value.regional.display_name||value.regional.country} · ${value.regional.subdivision||'общенациональные праздники'}`:'Без регионального набора'} · {value.current.date||'Год неизвестен'} · {value.current.season||'Сезон не задан'}</p>{value.notices.map(n=><p key={n} role="status">{n}</p>)}<ul>{value.events.slice(0,12).map(e=><li key={e.id}>{e.date} · {e.name}{e.observed?' (перенесённая дата)':''}</li>)}</ul></div>}
export function CalendarPresets({value,onChange}:{value:Presets;onChange:(v:Presets)=>void}){
 const [catalog,setCatalog]=useState<Catalog|null>(null);const [error,setError]=useState('');
 useEffect(()=>{api<Catalog>('/calendar/presets').then(setCatalog).catch(e=>setError(e.message));},[]);
 const change=(v:Partial<Presets>)=>onChange({...value,...v});
 const country=catalog?.countries.find(c=>c.code===value.country);
 return <fieldset><legend>Праздники и календарные сезоны</legend>{error&&<p role="alert">{error}</p>}
 <label>Праздники<select aria-label="Праздники" value={value.holidays} onChange={e=>change({holidays:e.target.value})}>{[['auto','Автоматически по миру'],['country','Выбрать страну'],['none','Без праздников'],['custom','Свой набор']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>
 {value.holidays==='country'&&<><label>Страна праздников<select aria-label="Страна праздников" value={value.country||''} onChange={e=>change({country:e.target.value||null,subdivision:null})}><option value="">Выберите страну</option>{['Россия','Европа','Америка'].map(g=><optgroup label={g} key={g}>{catalog?.countries.filter(c=>c.group===g).map(c=><option key={c.code} value={c.code}>{c.name}</option>)}</optgroup>)}</select></label>{!!country?.subdivisions.length&&<label>Область / земля / штат<select aria-label="Область праздников" value={value.subdivision||''} onChange={e=>change({subdivision:e.target.value||null})}><option value="">Общенациональные</option>{country.subdivisions.map(s=><option key={s}>{s}</option>)}</select></label>}</>}
 <label>Сезоны<select aria-label="Сезоны" value={value.seasons} onChange={e=>change({seasons:e.target.value})}>{[['auto','Автоматически по миру'],['north','Северные календарные сезоны'],['south','Южные календарные сезоны'],['none','Без сезонов'],['custom','Свои сезоны']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>
 <details><summary>Покрытие и перенесённые даты</summary><label><input type="checkbox" checked={value.observed} onChange={e=>change({observed:e.target.checked})}/> Показывать перенесённые даты соблюдения</label><p>Правила holidays 0.87, {catalog?.min_year}–{catalog?.max_year}. Названия праздников — на английском. Разовые решения будущих лет могут отсутствовать. Это не производственный календарь и не график NPC. Сезоны — трёхмесячная игровая модель, не прогноз климата.</p><p>Авторские даты сохраняются. Изменения отдельных региональных вхождений относятся только к выбранному году.</p></details>
 </fieldset>;
}
