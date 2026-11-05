import {useRef,useState} from 'react';
import {Feather,NotebookPen,Sparkles,Maximize2,ArrowRight,SlidersHorizontal,Users,Globe2,CalendarDays,Activity,ChevronRight,Check,ArrowLeft} from 'lucide-react';
import {CreationFields,castCounts,type Creation,type CreationGroup} from '../WorldCreationSettings';
import {CommunicationSettings,channels,communicationNames} from '../CommunicationSettings';
import {genres} from '../GenreSettings';
import {ApiError} from '../api';
import {Dialog,DialogContent,DialogTitle,DialogDescription} from '../components/ui/dialog';
import '../styles/idea-atelier.css';
export const ideaGroups=[['genre','Жанры истории',Feather],['cast','Персонажи',Users],['world','Мир и география',Globe2],['calendar','Календарь и начало',CalendarDays],['narrative','Темп и последствия',Activity]] as const;
const pacing:Record<string,string>={calm:'Спокойный',moderate:'Умеренный',dynamic:'Динамичный',intense:'Интенсивный'};
const risks:Record<string,string>={safe:'Безопасный',realistic:'Реалистичный',harsh:'Суровый',unrestricted:'Без ограничений'};
export function describeCreation(group:CreationGroup,v:Creation):string {
  const counts=castCounts(v);
  switch(group){
    case 'genre':return [v.primary_genre?genres[v.primary_genre]:'Из описания мира',...v.secondary_genres.map(g=>genres[g])].join(' · ');
    case 'cast':return `${counts[0]} + ${counts[1]} персонажей · ${{realistic:'сдержанная',expressive:'выразительная',hyperbolized:'театральная'}[v.npc_expressiveness]||v.npc_expressiveness} подача`;
    case 'world':return [({unspecified:'Из описания',real_world:'Реальный мир',fictional:'Вымышленный мир',alternate:'Альтернативная реальность'} as Record<string,string>)[v.world_type],v.geography].filter(Boolean).join(' · ');
    case 'calendar':return [v.calendar_start.mode==='custom'?'Свой календарь':v.calendar_start.mode==='gregorian'?'Григорианский':'Из идеи мира',v.calendar_start.date,v.calendar_start.time].filter(Boolean).join(' · ');
    case 'narrative':return `${pacing[v.narrative_pacing.preset]} темп · ${risks[v.narrative_risk.preset]} риск`;
  }
}
const examples=[
 {name:'Письма с соляного берега',tag:'Городская тайна',idea:'Каждый ноябрь море уходит от старой пристани и обнажает улицы затопленного города. В этот раз в окне почтамта горит свет. Я играю за реставратора, который нашёл там конверт со своим почерком. История начинается за час до прилива.'},
 {name:'Последняя вышка Валлора',tag:'Средневековье и телефоны',idea:'В княжестве Валлор письма носят гонцы, но у каждой гильдии есть мобильный телефон. Башни связи принадлежат короне. Я играю за ученицу картографа. Накануне ярмарки на телефон мастера приходит звонок с башни, сгоревшей десять лет назад.'},
 {name:'Четверо после репетиции',tag:'Современная драма',idea:'Соня, Илья, Катя и Тимур дружат с института. Я играю за Илью, вокалиста группы, которая завтра уезжает в тур. Мы с Соней встречаемся всего неделю. После репетиции она позвала меня посмотреть фильм и собирается предложить мне переехать к ней.'}
];
export function creationError(error:unknown):{message:string;group?:CreationGroup;field?:string} {
 const details=error instanceof ApiError?error.details.detail:null;
 const first=Array.isArray(details)?details[0] as {loc?:string[];msg?:string}:null;
 const path=first?.loc?.join('.')||'';const message=(first?.msg|| (error as Error).message||'Не удалось проверить замысел.').replace(/^Value error, /,'');
 const group=path.includes('calendar')?'calendar':/genre|жанр/i.test(path+message)?'genre':/npc|cast/.test(path)?'cast':/pacing|risk/.test(path)?'narrative':/geography|world_type/.test(path)?'world':undefined;
 const field=group==='genre'?'Описание своего жанра':path.includes('core_npcs')?'Важные NPC':path.includes('secondary_npcs')?'Второстепенные NPC':group==='calendar'?'Календарь начала игры':undefined;
 return {message,group,field};
}
type Props={id:string;name:string;text:string;useIdea:boolean;creation:Creation;disabled:boolean;saved:boolean;
 onName:(v:string)=>void;onText:(v:string)=>void;onScenario:(v:boolean)=>void;onCreation:(v:Creation)=>void;
 validate:()=>Promise<void>;launch:()=>Promise<void>;onMethod:(v:string)=>void;onBack?:()=>void};
export function IdeaAtelier(p:Props) {
 const [panel,setPanel]=useState<CreationGroup|'expand'|'examples'|null>(null),[review,setReview]=useState(false),[checking,setChecking]=useState(false),[error,setError]=useState<ReturnType<typeof creationError>|null>(null),[overwrite,setOverwrite]=useState(-1);
 const trigger=useRef<HTMLElement|null>(null),editor=useRef<HTMLTextAreaElement>(null),dialog=useRef<HTMLDivElement>(null),guard=useRef(false),heading=useRef<HTMLHeadingElement>(null);
 const open=(next:typeof panel)=>{trigger.current=document.activeElement as HTMLElement;setError(null);setPanel(next)};
 const close=()=>{setPanel(null);setOverwrite(-1)};
 const focusError=()=>{const label=error?.field;const inputs=Array.from(dialog.current?.querySelectorAll<HTMLElement>('input,textarea,select')||[]);const el=inputs.find(el=>label&&(el.getAttribute('aria-label')===label||el.closest('label')?.textContent?.startsWith(label)))||inputs.find(el=>el.matches(':invalid'))||inputs[0];el?.focus()};
 async function check(start=false){
   if(guard.current||p.disabled)return;guard.current=true;setChecking(true);setError(null);
   try {await p.validate();if(start)await p.launch();else {setReview(true);requestAnimationFrame(()=>heading.current?.focus())}}
   catch(e){const problem=creationError(e);setError(problem);if(problem.group){trigger.current=document.activeElement as HTMLElement;setPanel(problem.group)}else editor.current?.focus()}
   finally{guard.current=false;setChecking(false)}
 }
 const comm=channels.filter(c=>p.creation.communication?.[c]).map(c=>communicationNames[channels.indexOf(c)]).join(', ')||'Личные разговоры';
 const saved=p.saved?'Сохранено в этой вкладке браузера':'Хранится в открытой форме';
 const busy=p.disabled||checking;
 const fill=(i:number)=>{if(p.text.trim()&&overwrite!==i){setOverwrite(i);return}p.onText(examples[i].idea);if(!p.name)p.onName(examples[i].name);close()};
 return <div className="idea-atelier">
  <header className="atelier-hero"><img src="/images/idea-folio.webp" alt=""/><div><p className="atelier-eyebrow">Генератор мира</p><h1>По моей <em>идее</em></h1><p>Опишите мир и людей, с которых начнётся ваша история.</p></div><details className="atelier-method"><summary>Способ создания</summary><button disabled={busy} onClick={()=>p.onMethod('scenario')}>Со Сценаристом</button><button disabled={busy} onClick={()=>p.onMethod('import')}>Импортировать</button></details></header>
  {review?<section className="atelier-review" aria-label="Сводка замысла"><button className="atelier-link" disabled={busy} onClick={()=>{setReview(false);requestAnimationFrame(()=>editor.current?.focus())}}><ArrowLeft size={16}/>К замыслу</button><p className="atelier-eyebrow">Перед началом</p><h2 ref={heading} tabIndex={-1}>Всё начинается с замысла</h2><p>Проверьте основу. После генерации мир можно будет изменить в редакторе.</p><div className="atelier-review-grid"><article><h3>{p.name||'Новая история'}</h3><p className="atelier-brief">{p.text||'Сохранённый сценарий черновика'}</p>{p.useIdea&&<p>Сценарий черновика включён</p>}</article><dl>{(['genre','cast'] as const).map(g=><div key={g}><dt>{ideaGroups.find(([id])=>id===g)![1]}</dt><dd>{describeCreation(g,p.creation)}</dd></div>)}<div><dt>Связь</dt><dd>{comm}</dd></div></dl></div><details><summary>Все параметры мира</summary><dl>{ideaGroups.map(([g,title])=><div key={g}><dt>{title}</dt><dd>{describeCreation(g,p.creation)}</dd></div>)}<div><dt>Свой жанр</dt><dd>{p.creation.custom_genre||'Не задан'}</dd></div><div><dt>Календарь</dt><dd>{p.creation.calendar_start.profile&&[p.creation.calendar_start.profile.month_names.join(', '),p.creation.calendar_start.profile.month_lengths.join(', '),p.creation.calendar_start.profile.weekday_names.join(', ')].join(' · ')}{p.creation.calendar_start.presets&&` · Праздники: ${p.creation.calendar_start.presets.holidays} ${p.creation.calendar_start.presets.country||''} ${p.creation.calendar_start.presets.subdivision||''} · Сезоны: ${p.creation.calendar_start.presets.seasons}`}</dd></div><div><dt>Особенности связи</dt><dd>{p.creation.communication?.author_note||'Не заданы'}</dd></div></dl></details>{error&&!panel&&<p role="alert">{error.message}</p>}<footer><span>Будет создана новая версия мира</span><button className="atelier-primary" disabled={busy} onClick={()=>void check(true)}>{checking?'Проверяем и запускаем…':'Создать мир'}<ArrowRight size={16}/></button></footer></section>:
  <div className="atelier-layout"><div className="atelier-board"><section className="atelier-paper atelier-idea"><header><h2><NotebookPen/>Замысел мира</h2><button className="atelier-link" disabled={busy} onClick={()=>open('examples')}><Sparkles size={15}/>Примеры</button></header><div className="atelier-idea-body">
   {!p.id?<label className="atelier-name">Название истории <small>необязательно</small><input aria-label="Название черновика" maxLength={120} value={p.name} disabled={busy} onChange={e=>p.onName(e.target.value)} placeholder="Как будет называться ваша история?"/></label>:<p className="atelier-existing-name">{p.name}</p>}
   <div className="atelier-editor"><div><label htmlFor="atelier-idea-text">Текст идеи</label><button aria-label="Развернуть редактор идеи" disabled={busy} onClick={()=>open('expand')}><Maximize2 size={15}/></button></div><textarea ref={editor} id="atelier-idea-text" aria-label="Описание мира или текст импорта" aria-describedby="atelier-idea-hint" maxLength={100000} value={p.text} disabled={busy} onChange={e=>p.onText(e.target.value)} placeholder="На старой пристани нашли письмо, которое никто не отправлял…"/><div className="atelier-editor-meta"><span id="atelier-idea-hint">Герои, место, первая сцена — начните с любого.</span><span>{p.text.length.toLocaleString('ru')} зн.</span></div></div>
   {p.id&&<label className="atelier-scenario"><input type="checkbox" checked={p.useIdea} disabled={busy} onChange={e=>p.onScenario(e.target.checked)}/>Взять за основу сценарий этого черновика</label>}
   {error&&!panel&&<p role="alert">{error.message}</p>}</div><footer><span className="atelier-saved" title="Ввод сохраняется для этого черновика до закрытия вкладки. Мир будет сохранён на сервере после генерации.">{saved}</span><button className="atelier-primary" disabled={busy} onClick={()=>void check()}>{checking?'Проверяем…':'Проверить замысел'}<ArrowRight size={16}/></button></footer></section>
   <section className="atelier-paper atelier-parameters"><header><h2><SlidersHorizontal/>Параметры мира</h2></header><div>{ideaGroups.map(([g,title,Icon])=><button key={g} disabled={busy} className="atelier-param" onClick={()=>open(g)}><span className={'atelier-icon '+g}><Icon size={18}/></span><span><strong>{title}</strong><small>{describeCreation(g,p.creation)}</small></span><ChevronRight size={15}/></button>)}</div><p><Feather size={14}/>По умолчанию генератор опирается на вашу идею.</p></section></div>
   <CommunicationSettings compact value={p.creation.communication} onChange={communication=>p.onCreation({...p.creation,communication})} disabled={busy}/><div className="atelier-page-foot">AI RPG ENGINE · МАСТЕРСКАЯ МИРОВ</div>{p.onBack&&<button className="atelier-link" onClick={p.onBack}>Вернуться к миру</button>}
  </div>}
  <Dialog open={!!panel} onOpenChange={v=>{if(!v)close()}}><DialogContent ref={dialog} className={'atelier-dialog '+(panel==='expand'?'atelier-expanded':'')} onOpenAutoFocus={e=>{if(error){e.preventDefault();requestAnimationFrame(focusError)}}} onCloseAutoFocus={e=>{e.preventDefault();trigger.current?.focus()}}>
   <DialogTitle>{ideaGroups.find(([g])=>g===panel)?.[1]||(panel==='expand'?'Замысел без границ':'Примеры замысла')}</DialogTitle><DialogDescription>{panel==='examples'?'Выберите завязку, затем перепишите её под себя.':'Изменения сохраняются в этой вкладке для текущего черновика.'}</DialogDescription>
   {error&&!(error.group==='genre'&&!p.creation.custom_genre.trim())&&<p role="alert">{error.message}</p>}
   {panel==='expand'?<><label htmlFor="atelier-expanded">Текст идеи · {p.text.length.toLocaleString('ru')} / 100 000</label><textarea id="atelier-expanded" maxLength={100000} value={p.text} onChange={e=>p.onText(e.target.value)}/></>:panel==='examples'?examples.map((e,i)=><article className="atelier-example" key={e.name}><small>{e.tag}</small><h3>{e.name}</h3><p>{e.idea}</p><button className="atelier-link" onClick={()=>fill(i)}>{overwrite===i?'Подтвердить замену текста':p.text.trim()?'Заменить текущий текст':'Вставить пример'}<ArrowRight size={15}/></button></article>):panel&&<CreationFields group={panel} value={p.creation} onChange={v=>{p.onCreation(v);setError(null)}} disabled={busy}/>}
   {panel!=='examples'&&<footer><span className="atelier-saved">{saved}</span><button className="atelier-primary" onClick={close}>Готово<Check size={15}/></button></footer>}
  </DialogContent></Dialog>
 </div>;
}
