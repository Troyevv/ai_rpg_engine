import {useState} from 'react';
import {castCounts,defaultCreation,type Creation} from './WorldCreationSettings';
type Plan={creation?:Creation;entities:{id:string;name:string;kind:string;tier:string|null}[];claims:{id:string;description:string;section:string;classification:string;subject_id:string|null;related_ids:string[];holder_ids:string[];time_scope:string;blocking:boolean;spans:{quote:string}[]}[];constraint_revision:number};
const sections:Record<string,string>={character:'Персонажи',appearance:'Внешность',personality:'Характер',location:'Места',organization:'Организации',family:'Семья',relationship:'Отношения',residence:'Жильё',role:'Занятия и роли',fact:'Факты',knowledge:'Знания',history:'Предыстория',opening:'Начальная сцена',setting:'Мир',possession:'Имущество',contact:'Контакты',commitment:'Планы'};
const classes:Record<string,string>={explicit:'Задано пользователем',inferred:'Вывод из контекста',open:'Можно дополнить',prohibition:'Запрет',ambiguity:'Требует уточнения'};
export function InterpretationPreview({value}:{value:unknown}){
 const [focus,setFocus]=useState('');
 const plan=value as Plan;if(!plan?.entities||!plan.claims)return null;
 const [core,secondary]=castCounts({...defaultCreation,...plan.creation});
 const specified=plan.entities.filter(e=>e.kind==='character'&&e.tier!=='protagonist');
 const over=specified.filter(e=>e.tier!=='secondary').length>core||specified.filter(e=>e.tier==='secondary').length>secondary;
 const name=(id:string|null)=>plan.entities.find(e=>e.id===id)?.name||id||'Мир';
 return <section aria-label="Разбор замысла"><h3>Разбор замысла · версия {plan.constraint_revision}</h3><p>Авторский просмотр содержит секреты. Выводы модели не являются фактами пользователя.</p>
 <h4>Состав мира</h4>{over&&<p role="status">Заданных NPC больше выбранного целевого состава. Все они сохранятся; потребуется больше генерации и токенов.</p>}<ul>{plan.entities.map(e=><li key={e.id}>{e.name} · {e.kind==='character'?e.tier==='protagonist'?'Главный герой':'NPC':e.kind==='organization'?'Организация':'Место'}</li>)}</ul>
 <section aria-label="Связи замысла"><h4>Семья, отношения и организации</h4>
 <label>Показать связи<select aria-label="Показать связи" value={focus} onChange={e=>setFocus(e.target.value)}><option value="">Все сущности</option>{plan.entities.map(e=><option key={e.id} value={e.id}>{e.name}</option>)}</select></label>
 <p>Это утверждения исходного замысла: планы и предположения ещё не означают установленную связь.</p>
 <ul>{plan.claims.filter(c=>['family','relationship','organization'].includes(c.section)&&(!focus||c.subject_id===focus||c.related_ids.includes(focus))).map(c=><li key={c.id}><strong>{name(c.subject_id)}{c.related_ids.length>0&&' → '+c.related_ids.map(name).join(', ')}</strong>: {c.description} · {classes[c.classification]}{c.time_scope&&' · '+c.time_scope}</li>)}</ul>
 </section>
 <section aria-label="Хронология замысла"><h4>Время, открытия и начальная сцена</h4>
 <p>Время показано словами источника. Неопределённые даты не превращаются в точные; порядок записей не устанавливает порядок событий.</p>
 <ul>{plan.claims.filter(c=>c.time_scope||['history','opening','commitment'].includes(c.section)).map(c=><li key={c.id}><strong>{c.time_scope||'Точное время не задано'}</strong> · {name(c.subject_id)}: {c.description}<br/>{classes[c.classification]}{c.holder_ids.length>0&&' · Кто знает: '+c.holder_ids.map(name).join(', ')}</li>)}</ul>
 </section>
 {Object.entries(sections).map(([section,label])=>{const rows=plan.claims.filter(c=>c.section===section);return rows.length>0&&<section key={section}><h4>{label}</h4>{rows.map(c=><article key={c.id} className="draft-field"><strong>{name(c.subject_id)}{c.related_ids.length>0&&' → '+c.related_ids.map(name).join(', ')}</strong><p>{c.description}</p><small>{classes[c.classification]}{c.time_scope&&' · '+c.time_scope}</small>{c.holder_ids.length>0&&<p>Кто знает: {c.holder_ids.map(name).join(', ')}</p>}{c.blocking&&<p role="alert">Нужно разрешить противоречие перед продолжением.</p>}{c.spans.length>0&&<details><summary>Источник</summary>{c.spans.map((s,i)=><blockquote key={i}>{s.quote}</blockquote>)}</details>}</article>)}</section>})}
 </section>;
}
