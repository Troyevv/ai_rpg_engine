import {useEffect,useState} from 'react';
export type CalendarStart={mode:string;date:string|null;time:string|null;weekday:number|null;profile:{id:string;system:string;month_lengths:number[];month_names:string[];weekday_names:string[]}|null};
export const defaultCalendarStart:CalendarStart={mode:'auto',date:null,time:null,weekday:null,profile:null};
export function CalendarStartSettings({value,onChange}:{value:CalendarStart;onChange:(v:CalendarStart)=>void}){
 const change=(p:Partial<CalendarStart>)=>onChange({...value,...p});
 const profile=value.profile||{id:'custom',system:'custom',month_lengths:[30],month_names:['Первый'],weekday_names:['Первый','Второй','Третий']};
 const [dateParts,setDateParts]=useState((value.date||'').split('-'));
 const [lengths,setLengths]=useState(profile.month_lengths.join(', '));
 const [months,setMonths]=useState(profile.month_names.join(', '));
 const [weekdays,setWeekdays]=useState(profile.weekday_names.join(', '));
 useEffect(()=>{setDateParts((value.date||'').split('-'));},[value.date]);
 useEffect(()=>{setLengths(profile.month_lengths.join(', '));setMonths(profile.month_names.join(', '));setWeekdays(profile.weekday_names.join(', '));},[value.mode]);
 const parts=dateParts;

 const setDatePart=(index:number,text:string)=>{const next=[parts[0]||'',parts[1]||'',parts[2]||''];next[index]=text;setDateParts(next);};
 const saveDate=()=>change({date:parts.length===3&&parts.every(p=>/^\d+$/.test(p))?parts.map((p,i)=>p.padStart(i===0?4:2,'0')).join('-'):parts.every(p=>!p)?null:parts.join('-')});

 return <fieldset><legend>Календарь и начало игры</legend>
 <label>Календарь<select aria-label="Календарь начала игры" value={value.mode} onChange={e=>change({mode:e.target.value,profile:e.target.value==='custom'?profile:null})}><option value="auto">Из идеи мира / автоматически</option><option value="gregorian">Григорианский</option><option value="custom">Свой календарь</option></select></label>
 {value.mode==='custom'?<>
 <label>Длины месяцев<input aria-label="Длины месяцев" value={lengths} onChange={e=>{setLengths(e.target.value);change({profile:{...profile,month_lengths:e.target.value.split(',').map(v=>Number(v.trim()))}})}}/></label>
 <label>Названия месяцев<input aria-label="Названия месяцев" value={months} onChange={e=>{setMonths(e.target.value);change({profile:{...profile,month_names:e.target.value.split(',').map(v=>v.trim())}})}}/></label>
 <label>Дни недели<input aria-label="Дни недели" value={weekdays} onChange={e=>{setWeekdays(e.target.value);change({profile:{...profile,weekday_names:e.target.value.split(',').map(v=>v.trim())}})}}/></label>
 <p>Месяцы: от 1 до 24, длина от 1 до 99 дней. Названия перечисляйте через запятую. Неделя: от 1 до 14 дней.</p>
 {(profile.month_lengths.some(n=>!Number.isInteger(n)||n<1||n>99)||profile.month_lengths.length!==profile.month_names.length)&&<p role="alert">Проверьте длины и названия месяцев: количество должно совпадать.</p>}
 <div>{['Год начала','Месяц начала','День начала'].map((label,i)=><label key={label}>{label}<input aria-label={label} inputMode="numeric" value={parts[i]||''} onChange={e=>setDatePart(i,e.target.value)} onBlur={saveDate}/></label>)}</div>
 <label>Первый день недели<select aria-label="Первый день недели" value={value.weekday??''} onChange={e=>change({weekday:e.target.value===''?null:Number(e.target.value)})}><option value="">Из идеи мира</option>{profile.weekday_names.map((name,i)=><option key={i} value={i}>{name}</option>)}</select></label>
 </>:<label>Дата начала<input aria-label="Дата начала" type="date" min="0001-01-01" max="9999-12-31" value={value.date||''} onChange={e=>change({date:e.target.value||null})}/></label>}
 <label>Время начала<input aria-label="Время начала" type="time" value={value.time||''} onChange={e=>change({time:e.target.value||null})}/></label>
 <p>Если не заполнено, используем дату и время из идеи мира</p>
 </fieldset>;
}
