import {useId,useRef,useState} from 'react';
import {motion,useReducedMotion} from 'framer-motion';
import {Check,Feather,Plus,Search,Star,Undo2,X} from 'lucide-react';
import {AtelierDisclosure} from './workshop/AtelierDisclosure';
import './styles/genre-settings.css';
import {gameLocale} from './gameDate';
import {Textarea} from './components/ui/textarea';
import {genreCatalog,genreGroups,genreLabels,matchingGenres,selectPrimary,toggleSecondary,type GenreConfig} from './genreCatalog';
export {genres,descriptions,genreLabels,type GenreConfig} from './genreCatalog';
export const genreFutureHint=()=>gameLocale().startsWith('en')?'Genre changes affect new turns only. Regeneration uses the original turn settings.':'Смена жанров влияет только на новые ходы. Перегенерация использует исходные настройки хода.';

/** Shared authoring/policy control. Filters are local; the parent owns the persisted policy. */
export function GenreSettings({value,onChange,disabled=false,creation=false}:{value:GenreConfig;onChange:(value:GenreConfig)=>void;disabled?:boolean;creation?:boolean}){
 const locale=gameLocale().startsWith('en')?'en':'ru';const en=locale==='en';const names=genreLabels();
 const [query,setQuery]=useState('');const [group,setGroup]=useState('life');const [target,setTarget]=useState<'primary'|'secondary'>('primary');
 const [undo,setUndo]=useState<GenreConfig|null>(null);const [announcement,setAnnouncement]=useState('');
 const search=useRef<HTMLInputElement>(null);const primaryControl=useRef<HTMLButtonElement>(null);
 const id=useId();const reduce=useReducedMotion();
 const custom=[value.primary_genre,...value.secondary_genres].includes('custom');
 const primary=genreCatalog.find(g=>g.id===value.primary_genre);
 const results=matchingGenres(query,group);
 const t=(ru:string,english:string)=>en?english:ru;
 const change=(next:GenreConfig,message='')=>{setUndo(null);onChange(next);setAnnouncement(message)};
 const clearFilters=()=>{setQuery('');setGroup('all');search.current?.focus()};
 const choose=(genre:string)=>{
  const next=target==='primary'?selectPrimary(value,genre):toggleSecondary(value,genre);
  if(next!==value)change(next,`${names[genre]} · ${target==='primary'?t('основной жанр','primary genre'):next.secondary_genres.includes(genre)?t('добавлен','added'):t('убран','removed')}`);
 };
 return <fieldset disabled={disabled} className="genre-settings" aria-describedby={`${id}-hint`}>
  <legend>{t('Жанры истории','Story genres')}</legend>
  <p id={`${id}-hint`} className="genre-intro">{t('Основной жанр задаёт акцент, дополнительные — оттенки истории.','The primary genre sets the emphasis; secondary genres add accents.')}</p>
  <div className="genre-selection" aria-label={t('Выбранные жанры','Selected genres')}>
   <div className="genre-primary">
    <div className="genre-eyebrow"><Star size={14}/>{t('Основной жанр','Primary genre')}</div>
    <motion.div key={value.primary_genre||'neutral'} initial={reduce?false:{opacity:.4,y:6}} animate={{opacity:1,y:0}} transition={{duration:.2}}>
     <strong className="genre-primary-name" data-testid="primary-genre">{primary?.[locale].name||t('Из описания мира','From world description')}</strong>
     <p>{primary?.[locale].description||t('Настроение и события определяет ваш замысел.','Your concept defines the mood and events.')}</p>
    </motion.div>
    {value.primary_genre&&<button type="button" className="genre-text-action" onClick={()=>{change(selectPrimary(value,null));primaryControl.current?.focus()}}>{t('Из описания мира','From world description')}</button>}
   </div>
   <div className="genre-secondary-summary">
    <div className="genre-summary-heading"><span>{t('Дополнительные оттенки','Supporting accents')}</span><span className="genre-count">{value.secondary_genres.length} {t('из','of')} 3</span></div>
    <div className="genre-chips">
     {value.secondary_genres.map(g=><motion.div key={g} layout={reduce?false:'position'} initial={reduce?false:{opacity:.4,y:6}} animate={{opacity:1,y:0}} transition={{duration:.2}}><button type="button" className="genre-chip" aria-label={`${t('Убрать','Remove')} ${names[g]}`} onClick={e=>{
      const buttons=Array.from(e.currentTarget.closest('.genre-chips')?.querySelectorAll<HTMLButtonElement>('button')||[]);
      const index=buttons.indexOf(e.currentTarget);const sibling=buttons[index+1]||buttons[index-1];
      change(toggleSecondary(value,g),`${names[g]} · ${t('убран','removed')}`);
      if(sibling)sibling.focus();else primaryControl.current?.focus();
     }}><span>{names[g]}</span><X size={13}/></button></motion.div>)}
     {!value.secondary_genres.length&&<span className="genre-empty-selection">{t('Можно оставить только основной жанр','A primary genre is enough')}</span>}
    </div>
   </div>
  </div>
  {custom&&<label className="genre-custom" htmlFor={`${id}-custom`}>{t('Описание своего жанра','Custom genre description')}
   <Textarea id={`${id}-custom`} required aria-invalid={!value.custom_genre.trim()} aria-describedby={`${id}-custom-help`} value={value.custom_genre} maxLength={2000} onChange={e=>change({...value,custom_genre:e.target.value})}/>
   <span id={`${id}-custom-help`} className="genre-custom-help"><small>{value.custom_genre.length} / 2000</small>{!value.custom_genre.trim()&&<span role="alert">{t('Добавьте описание своего жанра.','Add a custom genre description.')}</span>}</span>
  </label>}
  <div className="genre-toolbar">
   <div className="genre-target" role="group" aria-label={t('Назначение выбора','Selection role')}>
    <button ref={primaryControl} type="button" aria-pressed={target==='primary'} onClick={()=>setTarget('primary')}><Star size={14}/>{t('Основной','Primary')}</button>
    <button type="button" aria-pressed={target==='secondary'} onClick={()=>setTarget('secondary')}><Plus size={14}/>{t('Дополнительные','Secondary')} <span>{value.secondary_genres.length}/3</span></button>
   </div>
   <div className="genre-search"><Search size={17} aria-hidden="true"/><input ref={search} type="search" aria-label={t('Найти жанр','Find a genre')} placeholder={t('Название или синоним…','Name or synonym…')} value={query} onChange={e=>{setQuery(e.target.value);setGroup('all')}}/>{query&&<button type="button" aria-label={t('Очистить поиск','Clear search')} onClick={()=>{setQuery('');search.current?.focus()}}><X size={16}/></button>}</div>
  </div>
  <AtelierDisclosure className="genre-group-picker" title={<span className="genre-group-current"><span>{t('Группа','Group')}</span><strong>{group==='all'?t('Все жанры','All genres'):genreGroups.find(g=>g.id===group)?.[locale]}</strong></span>}>
  <div className="genre-groups" role="group" aria-label={t('Группы жанров','Genre groups')}>
   <button type="button" aria-pressed={group==='all'} onClick={()=>setGroup('all')}>{t('Все','All')} <span>{genreCatalog.length}</span></button>
   {genreGroups.map(g=><button type="button" key={g.id} aria-pressed={group===g.id} onClick={()=>setGroup(g.id)}>{g[locale]}</button>)}
  </div></AtelierDisclosure>
  <div className="genre-result-heading"><span role="status">{t('Найдено','Found')}: {results.length}</span><span>{target==='primary'?t('Нажмите, чтобы сделать основным','Choose a primary genre'):t('Нажмите, чтобы добавить или убрать','Choose to add or remove')}</span></div>
  {target==='secondary'&&<p id={`${id}-limit`} className="genre-limit" data-full={value.secondary_genres.length===3}>{value.secondary_genres.length===3?t('Выбраны все 3 оттенка. Уберите один, чтобы добавить другой. Основной жанр можно менять свободно.','All 3 accents are selected. Remove one to add another. You can still change the primary genre.'):t('До 3 дополнительных жанров. Уже основной жанр нельзя добавить повторно.','Up to 3 secondary genres. The primary genre cannot be added twice.')}</p>}
  <motion.div className="genre-results" key={`${group}:${query}`} initial={reduce?false:{opacity:.4,y:8}} animate={{opacity:1,y:0}} transition={{duration:.2}}>
   {results.length?genreGroups.filter(g=>results.some(r=>r.group===g.id)).map(g=><section key={g.id} className="genre-group-section" aria-label={g[locale]}>
    <h3>{g[locale]}<span>{results.filter(r=>r.group===g.id).length}</span></h3>
    <div className="genre-grid">{results.filter(r=>r.group===g.id).map(item=>{
     const isPrimary=value.primary_genre===item.id;const isSecondary=value.secondary_genres.includes(item.id);
     const selected=target==='primary'?isPrimary:isSecondary;
     const blocked=target==='secondary'&&(isPrimary||value.secondary_genres.length>=3&&!isSecondary);
     return <button type="button" key={item.id} className="genre-card" data-genre={item.id} data-selected={isPrimary?'primary':isSecondary?'secondary':'none'} aria-label={`${target==='primary'?t('Основной жанр','Primary genre'):t('Дополнительный жанр','Secondary genre')}: ${item[locale].name}`} aria-pressed={selected} aria-disabled={blocked||disabled} aria-describedby={blocked?`${id}-limit`:undefined} onClick={()=>{if(!blocked&&!disabled)choose(item.id)}}>
      <span className="genre-card-top"><span className="genre-card-title">{item[locale].name}</span><span className="genre-card-mark">{isPrimary?<Star size={16}/>:isSecondary?<Check size={16}/>:item.id==='custom'?<Feather size={16}/>:<Plus size={16}/>}</span></span>
      <span className="genre-card-description">{item[locale].description}</span>
      <span className="genre-card-state">{isPrimary?t('Основной жанр','Primary genre'):isSecondary?t('Дополнительный жанр','Secondary genre'):blocked?t('Лимит: 3 из 3','Limit: 3 of 3'):target==='primary'?t('Сделать основным','Set as primary'):t('Добавить оттенок','Add an accent')}</span>
     </button>
    })}</div>
   </section>):<div className="genre-no-results"><Search size={28}/><strong>{t('Жанры не найдены','No genres found')}</strong><p>{t('Попробуйте другое название или уберите фильтры. Ваш выбор сохранён.','Try another name or clear the filters. Your selection is preserved.')}</p><button type="button" onClick={clearFilters}>{t('Сбросить поиск и группы','Clear search and groups')}</button></div>}
  </motion.div>
  <AtelierDisclosure className="genre-guidance" title={t('Как жанры влияют на историю','How genres shape the story')}><p>{t('Это творческие ориентиры, а не обязательные события. Жанры не задают эпоху, технологии, географию, темп или риск и не принимают решения за персонажей.','These are creative preferences, not required events. Genres do not set the era, technology, geography, pacing or risk, or decide for characters.')}</p>{!creation&&<p>{genreFutureHint()}</p>}</AtelierDisclosure>
  <div className="genre-reset">
   <button type="button" disabled={!value.primary_genre&&!value.secondary_genres.length} onClick={()=>{setUndo({...value,secondary_genres:[...value.secondary_genres]});onChange({...value,primary_genre:null,secondary_genres:[]});setAnnouncement(t('Выбор сброшен. Его можно восстановить.','Selection cleared. You can restore it.'))}}>{t('Сбросить выбор','Clear selection')}</button>
   {undo&&<button type="button" onClick={()=>{onChange(undo);setUndo(null);primaryControl.current?.focus()}}><Undo2 size={14}/>{t('Восстановить выбор','Restore selection')}</button>}
  </div>
  <span className="sr-only" role="status" aria-live="polite">{announcement}</span>
 </fieldset>;
}
