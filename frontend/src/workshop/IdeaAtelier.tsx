import {useEffect,useRef,useState,type CSSProperties} from 'react';
import {AnimatePresence,motion,useReducedMotion} from 'framer-motion';
import {AtelierDisclosure} from './AtelierDisclosure';
import {Feather,NotebookPen,Sparkles,Maximize2,ArrowRight,SlidersHorizontal,BookOpen,LoaderCircle,Layers,FileInput,PenLine,Users,Globe2,CalendarDays,Activity,ChevronRight,Check,ArrowLeft} from 'lucide-react';
import {CreationFields,castCounts,type Creation,type CreationGroup} from '../WorldCreationSettings';
import {CommunicationSettings,channels,communicationNames} from '../CommunicationSettings';
import {genres} from '../GenreSettings';
import {ApiError} from '../api';
import {Dialog,DialogContent,DialogTitle,DialogDescription} from '../components/ui/dialog';
import '../styles/idea-atelier.css';
import folio from '../assets/idea-folio.webp';
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
function calendarDetails(v:Creation){
 const c=v.calendar_start,p=c.presets;
 const holidays:Record<string,string>={auto:'по миру',country:'региональные',none:'отключены',custom:'авторский набор'};
 const seasons:Record<string,string>={auto:'по миру',north:'северные',south:'южные',none:'отключены',custom:'авторские'};
 return [c.profile&&`Месяцы: ${c.profile.month_names.map((n,i)=>`${n} (${c.profile!.month_lengths[i]} дн.)`).join(', ')}. Неделя: ${c.profile.weekday_names.join(', ')}`,
 c.weekday!=null&&`День недели: ${c.profile?.weekday_names[c.weekday]||c.weekday+1}`,
 p&&`Праздники: ${holidays[p.holidays]||p.holidays}${p.country?' · '+p.country:''}${p.subdivision?' · '+p.subdivision:''}. Перенесённые даты: ${p.observed?'включены':'выключены'}. Сезоны: ${seasons[p.seasons]||p.seasons}`].filter(Boolean).join('. ');
}
const examples=[
 {name:'Письма с соляного берега',tag:'Городская тайна',idea:'Каждый ноябрь море уходит от старой пристани и обнажает улицы затопленного города. В этот раз в окне почтамта горит свет. Я играю за реставратора, который нашёл там конверт со своим почерком. История начинается за час до прилива.'},
 {name:'Последняя вышка Валлора',tag:'Средневековье и телефоны',idea:'В княжестве Валлор письма носят гонцы, но у каждой гильдии есть мобильный телефон. Башни связи принадлежат короне. Я играю за ученицу картографа. Накануне ярмарки на телефон мастера приходит звонок с башни, сгоревшей десять лет назад.'},
 {name:'Четверо после репетиции',tag:'Современная драма',idea:'Соня, Илья, Катя и Тимур дружат с института. Я играю за Илью, вокалиста группы, которая завтра уезжает в тур. Мы с Соней встречаемся всего неделю. После репетиции она позвала меня посмотреть фильм и собирается предложить мне переехать к ней.'}
];
export function creationError(error:unknown):{message:string;group?:CreationGroup;field?:string} {
 const details=error instanceof ApiError?error.details.detail:null;
 const first=Array.isArray(details)?details[0] as {loc?:string[];msg?:string}:null;
 const path=first?.loc?.join('.')||'';const raw=(first?.msg|| (error as Error).message||'Не удалось проверить замысел.').replace(/^Value error, /,'');
 const message=raw==='custom genre requires a description'?'Добавьте описание своего жанра.':raw==='day is out of range for month'?'Дата отсутствует в выбранном календаре.':raw.replace('Input should be greater than or equal to','Значение должно быть не меньше').replace('Input should be less than or equal to','Значение должно быть не больше');
 const group=path.includes('calendar')?'calendar':/genre|жанр/i.test(path+message)?'genre':/npc|cast/.test(path)?'cast':/pacing|risk/.test(path)?'narrative':/geography|world_type/.test(path)?'world':undefined;
 const field=group==='genre'?'Описание своего жанра':path.includes('core_npcs')?'Важные NPC':path.includes('secondary_npcs')?'Второстепенные NPC':group==='calendar'?(path.includes('weekday')?'Первый день недели':path.includes('time')?'Время начала':/дат|день|месяц|day|month|year/i.test(message)?'День начала':path.includes('month_lengths')?'Длины месяцев':path.includes('month_names')?'Названия месяцев':path.includes('weekday_names')?'Дни недели':'Календарь начала игры'):undefined;
 return {message,group,field};
}
type Props={id:string;name:string;text:string;useIdea:boolean;creation:Creation;disabled:boolean;saved:boolean;
 onName:(v:string)=>void;onText:(v:string)=>void;onScenario:(v:boolean)=>void;onCreation:(v:Creation)=>void;
 validate:()=>Promise<void>;launch:()=>Promise<void>;onMethod:(v:string)=>void;onBack?:()=>void};
export function IdeaAtelier(p:Props) {
 const [panel,setPanel]=useState<CreationGroup|'expand'|'examples'|'methods'|null>(null),[review,setReview]=useState(false),[checking,setChecking]=useState(false),[error,setError]=useState<ReturnType<typeof creationError>|null>(null),[overwrite,setOverwrite]=useState(-1);
 const reduce=useReducedMotion();
 const mounted=useRef(true);
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[]);
 const trigger=useRef<HTMLElement|null>(null),editor=useRef<HTMLTextAreaElement>(null),dialog=useRef<HTMLDivElement>(null),guard=useRef(false),returnToIdea=useRef(false),heading=useRef<HTMLHeadingElement>(null);
 const open=(next:typeof panel)=>{trigger.current=document.activeElement as HTMLElement;setError(null);setPanel(next)};
 const close=()=>{setPanel(null);setOverwrite(-1)};
 const focusError=()=>{const label=error?.field;const inputs=Array.from(dialog.current?.querySelectorAll<HTMLElement>('input,textarea,select')||[]);const el=inputs.find(el=>label&&(el.getAttribute('aria-label')===label||el.closest('label')?.textContent?.startsWith(label)))||inputs.find(el=>label==='День начала'&&el.getAttribute('aria-label')==='Дата начала')||inputs.find(el=>el.matches(':invalid'))||inputs[0];el?.focus()};
 async function check(start=false){
   if(guard.current||p.disabled)return;guard.current=true;setChecking(true);setError(null);
   let launching=false;
   try {await p.validate();if(!mounted.current)return;if(start){launching=true;await p.launch()}else {setReview(true);document.querySelector(".ww-scroll")?.scrollTo({top:0});requestAnimationFrame(()=>heading.current?.focus())}}
   catch(e){if(!mounted.current||launching)return;const problem=creationError(e);setError(problem);if(problem.group){trigger.current=document.activeElement as HTMLElement;setPanel(problem.group)}else editor.current?.focus()}
   finally{guard.current=false;if(mounted.current)setChecking(false)}
 }
 const comm=channels.filter(c=>p.creation.communication?.[c]).map(c=>communicationNames[channels.indexOf(c)]).join(', ')||'Личные разговоры';
 const extraRows=[...ideaGroups.filter(([g])=>g!=='genre'&&g!=='cast').map(([g,label])=>({label,value:describeCreation(g,p.creation)})),
  {label:'Свой жанр',value:p.creation.custom_genre||'Не задан'},
  {label:'Праздники и календарная структура',value:calendarDetails(p.creation)||'Из замысла'},
  {label:'Интерфейс связи',value:p.creation.communication?.presentation==='phone'?'Телефон':'Без телефона'},
  {label:'Особенности связи',value:p.creation.communication?.author_note||'Не заданы'}];
 const saved=p.saved?'Сохранено во вкладке':'Хранится в открытой форме';
 const busy=p.disabled||checking;
 const fill=(i:number)=>{if(p.text.trim()&&overwrite!==i){setOverwrite(i);return}p.onText(examples[i].idea);if(!p.name)p.onName(examples[i].name);close()};
 const transition={duration:reduce?0:.2,ease:[.22,.68,0,1.01] as [number,number,number,number]};
 const move={initial:{opacity:0,y:reduce?0:8},animate:{opacity:1,y:0},exit:{opacity:0,y:reduce?0:-5},transition};
 return <div className="idea-atelier atelier-scope" data-view={review?'review':'brief'}>
 <AnimatePresence mode="wait" initial={false}>
 {review?<motion.section key="review" {...move} className="flow-wrap" aria-label="Сводка замысла" onAnimationComplete={()=>heading.current?.focus({preventScroll:true})}>
  <div className="flow-root"><div className="fl-kicker"><i/>МАСТЕРСКАЯ МИРОВ <b>/</b> 02 <span>Перед началом</span></div><h2 className="fl-title" ref={heading} tabIndex={-1}>Проверка замысла</h2><p className="fl-deck">Проверьте, с чем начнёт работу генератор. Замысел и настройки ещё можно изменить.</p>
  <article className="fl-card"><div className="fl-card-head"><Feather size={18}/><span>Исходный замысел</span><small>{p.text.length.toLocaleString('ru')} знаков</small></div><h2>{p.name||'Новая история'}</h2><div className="fl-prose" tabIndex={0}>{p.text||'Сохранённый сценарий черновика'}</div>{p.useIdea&&<p className="sp-note">Сценарий черновика включён</p>}
   <section className="fl-overview"><h3>Параметры генерации</h3><dl className="fl-lines">{(['genre','cast'] as const).map(g=><div key={g}><dt>{ideaGroups.find(([id])=>id===g)![1]}</dt><dd>{describeCreation(g,p.creation)}</dd></div>)}<div><dt>Технологии связи</dt><dd>{comm}</dd></div></dl></section>
   <AtelierDisclosure className="fl-other" title={<>Остальные параметры <small>{extraRows.length}</small></>}><dl className="fl-lines">{extraRows.map(row=><div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}</dl></AtelierDisclosure>
  </article>{error&&!panel&&<p className="sp-error" role="alert">{error.message}</p>}
  <div className="fl-actions"><button className="fl-sub" disabled={busy} onClick={()=>{returnToIdea.current=true;setReview(false)}}><ArrowLeft size={16}/>К замыслу</button><button className="fl-primary" disabled={busy} aria-busy={checking} onClick={()=>void check(true)}>{checking?<LoaderCircle size={16} className="atelier-spinner"/>:null}{checking?'Проверяем и запускаем…':'Создать мир'}<ArrowRight size={16}/></button></div></div>
 </motion.section>:<motion.div key="brief" {...move} onAnimationComplete={()=>{if(returnToIdea.current){returnToIdea.current=false;editor.current?.focus({preventScroll:true})}}}>
  <header className="hero atelier-hero"><div className="hero-art" style={{'--atelier-art':`url(${folio})`} as CSSProperties}/><div className="hero-copy"><div className="overline"><i/>Генератор мира</div><h1>По моей <em>идее</em></h1><p>Опишите мир и людей, с которых начнётся ваша история.</p></div><button className="atelier-method method" onClick={()=>open('methods')}><Layers size={14}/><span>Способ создания</span><ChevronRight size={13}/></button></header>
  <div className="folio-layout atelier-layout"><div className="board atelier-board">
   <section className="paper idea-card atelier-idea"><header className="card-head"><div className="title-line"><NotebookPen className="section-icon"/><h2>Замысел мира</h2></div><button className="subtle" disabled={busy} onClick={()=>open('examples')}><Sparkles size={15}/>Примеры</button></header>
    <div className="idea-body">{!p.id?<><label className="field-name" htmlFor="atelier-name">Название истории <span>необязательно</span></label><input className="name-input" id="atelier-name" aria-label="Название черновика" maxLength={120} value={p.name} disabled={busy} onChange={e=>p.onName(e.target.value)} placeholder="Новая история"/></>:<p className="existing-name">{p.name}</p>}
    <div className="editor-shell atelier-editor"><div className="editor-tools"><label htmlFor="atelier-idea-text"><Feather size={13}/>Текст идеи</label><button className="sq" aria-label="Развернуть редактор идеи" disabled={busy} onClick={()=>open('expand')}><Maximize2 size={15}/></button></div>
     <textarea ref={editor} id="atelier-idea-text" aria-label="Описание мира или текст импорта" aria-describedby="atelier-idea-hint" maxLength={100000} value={p.text} disabled={busy} onChange={e=>p.onText(e.target.value)} placeholder="На старой пристани нашли письмо, которое никто не отправлял…"/><div className="editor-meta"><span id="atelier-idea-hint">Герои, место, первая сцена — начните с любого.</span><span>{p.text.length.toLocaleString('ru')} зн.</span></div></div>
     {p.id&&<label className="basis"><input type="checkbox" checked={p.useIdea} disabled={busy} onChange={e=>p.onScenario(e.target.checked)}/>Взять за основу сценарий этого черновика</label>}{error&&!panel&&<p className="sp-error" role="alert">{error.message}</p>}</div>
    <footer className="idea-footer"><span className="saved" title="Ввод сохраняется для этого черновика до закрытия вкладки. Мир сохраняется на сервере после генерации."><i/>{saved}</span><button className="primary" disabled={busy||(!p.text.trim()&&!p.useIdea)} aria-busy={checking} onClick={()=>void check()}>{checking?<LoaderCircle size={16} className="atelier-spinner"/>:null}{checking?'Проверяем…':'Проверить замысел'}<ArrowRight size={16}/></button></footer></section>
   <section className="paper settings-card"><header className="card-head"><div className="title-line"><SlidersHorizontal className="section-icon"/><h2>Параметры мира</h2></div></header><div className="param-list">{ideaGroups.map(([g,title,Icon])=><button key={g} disabled={busy} className={'param atelier-param'+(error?.group===g?' bad':'')} onClick={()=>open(g)} title={describeCreation(g,p.creation)}><span className={'icon-tile tint-'+g}><Icon size={18}/></span><span><strong>{title}</strong><small>{describeCreation(g,p.creation)}</small></span><ChevronRight size={15}/></button>)}</div><div className="settings-note"><Feather size={14}/>По умолчанию генератор опирается на вашу идею.</div></section>
  </div><CommunicationSettings compact value={p.creation.communication} onChange={communication=>p.onCreation({...p.creation,communication})} disabled={busy}/><div className="page-foot"><i/>AI RPG ENGINE · МАСТЕРСКАЯ МИРОВ<i/></div>{p.onBack&&<button className="text-action" onClick={p.onBack}><ArrowLeft size={15}/>Вернуться к миру</button>}</div>
 </motion.div>}
 </AnimatePresence>
 <Dialog open={!!panel} onOpenChange={v=>{if(!v)close()}}><DialogContent ref={dialog} className={'atelier-scope folio-modal atelier-dialog '+(panel==='expand'?'wide atelier-expanded':panel==='examples'||panel==='methods'?'':'drawer')} onOpenAutoFocus={e=>{e.preventDefault();if(error)requestAnimationFrame(focusError);else dialog.current?.querySelector<HTMLElement>('.dialog-title')?.focus({preventScroll:true})}} onCloseAutoFocus={e=>{e.preventDefault();trigger.current?.focus()}}>
  <div className="modal-head"><div><div className="overline">{ideaGroups.some(([g])=>g===panel)?'Параметры мира':'Мастерская миров'}</div><DialogTitle tabIndex={-1}>{ideaGroups.find(([g])=>g===panel)?.[1]||(panel==='expand'?'Ваш замысел':panel==='methods'?'Способ создания':'Идеи для начала')}</DialogTitle></div></div>
  <div className="modal-body"><DialogDescription className={panel==='examples'?'modal-intro':'sr-only'}>{panel==='examples'?'Выберите завязку, затем перепишите её под себя.':panel==='methods'?'Выберите, с чего начнётся новый мир.':'Изменения сохраняются в этой вкладке для текущего черновика.'}</DialogDescription>
   {error&&!(error.group==='genre'&&!p.creation.custom_genre.trim())&&<p className="sp-error" role="alert">{error.message}</p>}
   {panel==='expand'?<><label className="field-name" htmlFor="atelier-expanded">Текст идеи <span>{p.text.length.toLocaleString('ru')} / 100 000</span></label><textarea className="expanded-editor" id="atelier-expanded" maxLength={100000} value={p.text} onChange={e=>p.onText(e.target.value)}/></>:panel==='examples'?examples.map((e,i)=><article className="example" key={e.name}><small>{e.tag}</small><h3>{e.name}</h3><p>{e.idea}</p><button className="text-action" onClick={()=>fill(i)}>{overwrite===i?'Подтвердить замену текста':p.text.trim()?'Заменить текущий текст':'Вставить пример'}<ArrowRight size={15}/></button></article>):panel==='methods'?<>{[['quick','По моей идее','Свободное описание и параметры генерации',Feather],['scenario','Со Сценаристом','Обсудить замысел и подготовить сценарий',PenLine],['import','Импортировать','Открыть готовую выжимку или файл мира',FileInput]].map(([id,title,desc,Icon])=>{const I=Icon as typeof BookOpen;return <button key={String(id)} className="list-option" aria-label={String(title)} disabled={busy} onClick={()=>id==='quick'?close():p.onMethod(String(id))}><I size={20}/><span>{String(title)}<small>{String(desc)}</small></span>{id==='quick'?<Check size={16}/>:<ChevronRight size={16}/>}</button>})}</>:panel&&<div key={panel} className="atelier-panel-content"><CreationFields group={panel} value={p.creation} onChange={v=>{p.onCreation(v);setError(null)}} disabled={busy}/></div>}
   {panel!=='examples'&&panel!=='methods'&&<footer className="modal-actions"><span className="saved"><i/>{saved}</span><button className="primary" onClick={close}>{panel==='expand'?'К параметрам':'Готово'}<Check size={15}/></button></footer>}
  </div>
 </DialogContent></Dialog>
 </div>;
}
