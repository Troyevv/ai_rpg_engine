import {useEffect,useRef,useState} from 'react';
import {ArrowLeft,Bookmark,Search,Users,History,Pencil,ArrowUpRight,RefreshCw} from 'lucide-react';
import {api} from './api';
import {Button} from './components/ui/button';
import {Textarea} from './components/ui/textarea';
import {SectionTabs} from './components/ui/section-tabs';
import {Markdown} from './Markdown';
import type {ChatCampaign,ChatMemory,ChatMessage} from './chatTypes';

type Tab='bookmarks'|'characters'|'history';
export type JournalStart={tab:Tab;message?:ChatMessage;version?:string};
type BackRef={current:(()=>boolean)|null};
type Common={campaign:ChatCampaign;disabled:boolean;backRef:BackRef;onRefresh:()=>Promise<ChatCampaign>};
type BookmarkItem={message_id:string;seq:number;chapter_id:string;chapter_name:string;role:string;note:string;priority:number;excerpt:string};
type CardBrief={key:string;name:string;kind:'hero'|'npc'|'source'};
type Card=CardBrief&{text:string;memory_id:string;branch:string;fields:{group:string;label:string;value:string}[];blocks?:{title:string;text:string}[]};
type Version=ChatMemory&{branch_name:string;characters:number};
type DiffLine={kind:'added'|'removed'|'context';text:string;old_line:number|null;new_line:number|null};
type HistoryDetail={memory:ChatMemory;previous:ChatMemory|null;provenance:{id:string;job_id:string|null;source_revision:number}|null;changes:{changed:boolean;interpretation:string;groups:{title:string;kind:string;before:string;after:string}[];hunks:{old_start:number;new_start:number;lines:DiffLine[]}[]}};
const local=(key:string,fallback:string)=>{try{return localStorage.getItem(key)??fallback}catch{return fallback}};
const save=(key:string,text:string)=>{try{localStorage.setItem(key,text)}catch{/* approved source remains on server */}};
const forget=(key:string)=>{try{localStorage.removeItem(key)}catch{/* durable drafts remain on server */}};
const base=(c:ChatCampaign)=>`/chat/campaigns/${c.id}`;
const revision=(c:ChatCampaign)=>({revision:c.revision,token:crypto.randomUUID()});
const sourceName=(source:string)=>({initial:'Первоначальная выжимка',author:'Авторская правка',summary:'Утверждённое обновление'}[source]||source);

function useBack(ref:BackRef,back:()=>boolean){useEffect(()=>{ref.current=back;return()=>{if(ref.current===back)ref.current=null}},[ref,back])}
function useSearch(){const [query,setQuery]=useState('');const [search,setSearch]=useState('');useEffect(()=>{const t=setTimeout(()=>setSearch(query),180);return()=>clearTimeout(t)},[query]);return {query,setQuery,search}}
function useList<T>(url:string){
  const [page,setPage]=useState<{items:T[];more:boolean;sources?:CardBrief[];total?:number}|null>(null);
  const [loading,setLoading]=useState(false),[error,setError]=useState(''),[nonce,setNonce]=useState(0);
  const epoch=useRef(0);const controller=useRef<AbortController|null>(null);
  useEffect(()=>{const e=++epoch.current;const c=new AbortController();controller.current=c;setPage(null);setLoading(true);setError('');
    void api<NonNullable<typeof page>>(url,undefined,'GET',c.signal).then(p=>{if(e===epoch.current)setPage(p)}).catch(err=>{if(!c.signal.aborted)setError(err.message)}).finally(()=>{if(e===epoch.current)setLoading(false)});
    return()=>{c.abort();epoch.current++};
  },[url,nonce]);
  const more=async(next:string)=>{if(loading)return;const e=epoch.current;setLoading(true);setError('');try{const p=await api<NonNullable<typeof page>>(next,undefined,'GET',controller.current?.signal);if(e===epoch.current)setPage(old=>({...p,items:[...(old?.items||[]),...p.items]}))}catch(err){if(e===epoch.current)setError((err as Error).message)}finally{if(e===epoch.current)setLoading(false)}};
  return {page,loading,error,more,reload:()=>setNonce(n=>n+1)};
}
function Feedback({loading,error,retry}:{loading:boolean;error:string;retry:()=>void}){return <>{loading&&<p role="status">Загружаем…</p>}{error&&<div className="chat-error" role="alert"><p>{error}</p><Button variant="outline" onClick={retry}>Повторить загрузку</Button></div>}</>}
function SearchField({label,value,onChange}:{label:string;value:string;onChange:(value:string)=>void}){return <label className="chat-journal-search"><span><Search size={16}/>{label}</span><input type="search" value={value} onChange={e=>onChange(e.target.value)} maxLength={200}/></label>}

export function ChatJournal(props:Common&{initial:JournalStart;onBookmark:(item:BookmarkItem,enabled:boolean,note:string,priority:number)=>Promise<void>;onJump:(id:string)=>Promise<void>;onReview:(id:string)=>Promise<void>;onRestore:(text:string)=>void;onClose:()=>void}){
  const [tab,setTab]=useState<Tab>(props.initial.tab);
  return <section className="chat-journal">
    <SectionTabs label="Журнал кампании" className="chat-journal-tabs" tablist panelId="chat-journal-panel" value={tab} onChange={setTab} items={[{id:'bookmarks',label:'Закладки',icon:<Bookmark size={16}/>},{id:'characters',label:'Персонажи',icon:<Users size={16}/>},{id:'history',label:'Изменения',icon:<History size={16}/>}]}/>
    <div id="chat-journal-panel" role="tabpanel" aria-labelledby={`chat-journal-panel-tab-${tab}`}>
      {tab==='bookmarks'&&<BookmarksPanel {...props} initial={props.initial.tab==='bookmarks'?props.initial.message:undefined}/>}
      {tab==='characters'&&<CharactersPanel {...props}/>}
      {tab==='history'&&<HistoryPanel {...props} initial={props.initial.tab==='history'?props.initial.version:undefined}/>}
    </div>
    <Button variant="outline" onClick={props.onClose}>Вернуться в игру</Button>
  </section>;
}

function BookmarksPanel({campaign,disabled,backRef,onRefresh,initial,onBookmark,onJump}:Common&{initial?:ChatMessage;onBookmark:(item:BookmarkItem,enabled:boolean,note:string,priority:number)=>Promise<void>;onJump:(id:string)=>Promise<void>}){
  const {query,setQuery,search}=useSearch();const path=base(campaign);const url=`${path}/bookmarks?branch=${campaign.active_branch}&q=${encodeURIComponent(search)}`;
  const list=useList<BookmarkItem>(url);
  const [editing,setEditing]=useState<BookmarkItem|null>(()=>initial?{message_id:initial.id,seq:initial.seq,chapter_id:initial.chapter_id,chapter_name:campaign.chapters.find(c=>c.id===initial.chapter_id)?.name||'Глава',role:initial.role,note:initial.bookmark?.note||'',priority:initial.bookmark?.priority??1,excerpt:initial.content.slice(0,400)}:null);
  const [existing,setExisting]=useState(!!initial?.bookmark);const [note,setNote]=useState(''),[priority,setPriority]=useState(1),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const key=editing?`chat-bookmark:${campaign.id}:${editing.message_id}`:'';
  useEffect(()=>{if(!editing)return;let data={note:editing.note,priority:editing.priority};try{data=JSON.parse(local(key,JSON.stringify(data)))}catch{/* use server bookmark */}setNote(data.note);setPriority(data.priority);setError('')},[editing?.message_id]);
  const change=(n:string,p:number)=>{setNote(n);setPriority(p);save(key,JSON.stringify({note:n,priority:p}))};
  useBack(backRef,()=>{if(editing){setEditing(null);return true}return false});
  const persist=async(enabled:boolean)=>{if(!editing||busy)return;setBusy(true);setError('');try{await onBookmark(editing,enabled,note,priority);forget(key);setEditing(null);list.reload()}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
  return editing?<div className="chat-journal-detail">
    <Button variant="ghost" onClick={()=>setEditing(null)}><ArrowLeft size={16}/>К списку закладок</Button>
    <h3>{existing?'Заметка к закладке':'Новая закладка'}</h3><p className="muted small">{editing.chapter_name} · сообщение № {editing.seq} · {editing.role==='user'?'Игрок':'История'}</p>
    <blockquote className="chat-source-excerpt">{editing.excerpt}{editing.excerpt.length===400?'…':''}</blockquote>
    <label htmlFor="chat-bookmark-note">Заметка автора</label><Textarea id="chat-bookmark-note" value={note} maxLength={2000} rows={4} onChange={e=>change(e.target.value,priority)}/>
    <label htmlFor="chat-bookmark-priority">Приоритет при обновлении выжимки</label><select id="chat-bookmark-priority" value={priority} onChange={e=>change(note,Number(e.target.value))}><option value={2}>Высокий — передать модели</option><option value={1}>Обычный — передать модели</option><option value={0}>Только навигация — не передавать</option></select>
    <p className="muted small">Закладка относится к исходному сообщению и общему префиксу веток. Заметка не делает предложенные варианты совершёнными действиями. Удаление уберёт закладку во всех ветках, где есть это же сообщение.</p>
    {error&&<div className="chat-error" role="alert"><p>{error}</p><Button variant="outline" onClick={()=>void onRefresh().then(()=>setError('Состояние обновлено. Проверьте заметку и сохраните её явно.')).catch(e=>setError(e.message))}>Обновить состояние, сохранив правку</Button></div>}
    <div className="actions"><Button disabled={busy||disabled} onClick={()=>void persist(true)}>Сохранить закладку</Button>{existing&&<Button disabled={busy||disabled} variant="outline" onClick={()=>void persist(false)}>Удалить закладку</Button>}<Button disabled={busy} variant="ghost" onClick={()=>void onJump(editing.message_id).catch(e=>setError(e.message))}>Открыть сообщение<ArrowUpRight size={16}/></Button></div>
  </div>:<>
    <p className="muted small">Только сообщения выбранной ветки, включая её общий префикс и архивные главы. Исключённые варианты других веток здесь не появляются.</p>
    <SearchField label="Поиск по закладкам и заметкам" value={query} onChange={setQuery}/>
    <p className="chat-journal-budget">В следующее обновление памяти: {campaign.budgets.summary.bookmarks_included||0}. Только для навигации: {campaign.budgets.summary.bookmarks_excluded||0}. {campaign.budgets.summary.fits?'Контекст обновления помещается.':'Контекст обновления не помещается. Измените приоритет на «Только навигация» у отдельных закладок или увеличьте доступное окно. Ничего не исключено автоматически.'}</p>
    <Feedback {...list} retry={list.reload}/>{list.page&&!list.page.items.length&&<div className="chat-journal-empty"><Bookmark size={24}/><h3>{search?'Совпадений нет':'Сохраните важный момент'}</h3><p>Кнопка закладки есть у каждого сохранённого сообщения. Отсюда можно вернуться к нему даже через много глав.</p></div>}
    <div className="chat-journal-list">{list.page?.items.map(item=><article className="chat-bookmark-card" key={item.message_id}><span className="muted small">{item.chapter_name} · № {item.seq} · {item.priority===2?'Высокий приоритет':item.priority===1?'В обновлении памяти':'Только навигация'}</span><p>{item.note||item.excerpt.slice(0,180)}</p>{item.note&&<p className="muted small">{item.excerpt.slice(0,160)}…</p>}<div className="actions"><Button variant="outline" onClick={()=>void onJump(item.message_id).catch(e=>setError(e.message))}>К сообщению<ArrowUpRight size={16}/></Button><Button variant="ghost" onClick={()=>{setExisting(true);setEditing(item)}}><Pencil size={16}/>Заметка и приоритет</Button></div></article>)}</div>
    {error&&<p role="alert">{error}</p>}{list.page?.more&&<Button disabled={list.loading} variant="outline" onClick={()=>void list.more(`${url}&before=${list.page!.items.at(-1)!.seq}`)}>Ещё закладки</Button>}
  </>;
}

function CharactersPanel({campaign,disabled,backRef,onRefresh,onReview}:Common&{onReview:(id:string)=>Promise<void>}){
  const {query,setQuery,search}=useSearch();const path=base(campaign);const url=`${path}/characters?branch=${campaign.active_branch}&memory=${campaign.memory.id}&q=${encodeURIComponent(search)}`;
  const list=useList<CardBrief>(url);const [card,setCard]=useState<Card|null>(null),[editing,setEditing]=useState(false),[preview,setPreview]=useState(false),[text,setText]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [latest,setLatest]=useState<string|null>(null),[conflictCard,setConflictCard]=useState<Card|null>(null);const request=useRef(0);useEffect(()=>()=>{request.current++},[]);
  const draftKey=card?`chat-character:${campaign.id}:${card.memory_id}:${card.key}`:'';
  const open=async(item:CardBrief)=>{const n=++request.current;setBusy(true);setError('');try{const c=await api<Card>(`${path}/characters/${item.key}?branch=${campaign.active_branch}&memory=${campaign.memory.id}`);if(n===request.current){setCard(c);setText(local(`chat-character:${campaign.id}:${c.memory_id}:${c.key}`,c.text));setEditing(false);setPreview(false);setLatest(null)}}catch(e){if(n===request.current)setError((e as Error).message)}finally{if(n===request.current)setBusy(false)}};
  const back=()=>{if(preview){setPreview(false);return true}if(editing){setEditing(false);return true}if(card){setCard(null);return true}return false};useBack(backRef,back);
  const saveDraft=async()=>{if(!card||busy)return;const n=++request.current;setBusy(true);setError('');try{const d=await api<{draft:string}>(`${path}/characters/${card.key}/draft`,{...revision(campaign),branch:campaign.active_branch,memory_id:card.memory_id,text});if(n!==request.current)return;await onReview(d.draft);if(local(draftKey,'')===text)forget(draftKey)}catch(e){if(n===request.current)setError((e as Error).message)}finally{if(n===request.current)setBusy(false)}};
  const compareCurrent=async()=>{
    if(!card||busy)return;setBusy(true);
    try{
      const current=await onRefresh();setLatest(current.memory.text);setConflictCard(null);
      const candidates=await api<{items:CardBrief[];sources:CardBrief[];more:boolean}>(`${path}/characters?branch=${current.active_branch}&memory=${current.memory.id}&q=${encodeURIComponent(card.name)}`);
      const matches=[...candidates.items,...candidates.sources].filter(c=>c.name===card.name&&c.kind===card.kind);
      if(matches.length===1&&!candidates.more)setConflictCard(await api<Card>(`${path}/characters/${matches[0].key}?branch=${current.active_branch}&memory=${current.memory.id}`));
    }catch(e){setError((e as Error).message)}finally{setBusy(false)}
  };
  return <>
    {!card&&<><p className="muted small">Персонажи — представление утверждённой выжимки. Это авторский справочник со спойлерами: просмотр тайны не сообщает её ГГ или NPC.</p><SearchField label="Поиск персонажей и сведений" value={query} onChange={setQuery}/><Feedback loading={list.loading||busy} error={list.error||error} retry={list.reload}/>
      {list.page&&!list.page.items.length&&<div className="chat-journal-empty"><Users size={24}/><h3>{search?'Совпадений нет':'Карточки пока не распознаны'}</h3><p>Откройте исходный раздел ниже. Неизвестные структуры остаются текстом; сведения не угадываются.</p></div>}
      <div className="chat-character-grid">{list.page?.items.map(item=><button className="chat-character-card" key={item.key} disabled={busy} onClick={()=>void open(item)}><span className="chat-character-avatar" aria-hidden="true">{Array.from(item.name)[0]}</span><span><strong>{item.name}</strong><small>{item.kind==='hero'?'Главный герой':'Персонаж'}</small></span><ArrowUpRight size={16}/></button>)}</div>
      {list.page?.more&&<Button disabled={list.loading} variant="outline" onClick={()=>void list.more(`${url}&offset=${list.page!.items.length}`)}>Ещё персонажи</Button>}
      <section className="chat-journal-sources"><h3>Исходные разделы</h3><p className="muted small">Полный текст, включая нераспознанные сведения, направленные отношения и авторские тайны.</p>{list.page?.sources?.map(item=><Button key={item.key} disabled={busy} variant="outline" onClick={()=>void open(item)}>{item.name}</Button>)}</section>
    </>}
    {card&&<div className="chat-journal-detail"><Button variant="ghost" onClick={back}><ArrowLeft size={16}/>{preview?'К правке':editing?'К карточке':'К списку персонажей'}</Button><div className="chat-character-heading"><span className="chat-character-avatar" aria-hidden="true">{Array.from(card.name)[0]}</span><div><h3>{card.name}</h3><p className="muted small">{card.kind==='hero'?'Главный герой':card.kind==='npc'?'Персонаж':'Исходный раздел'} · утверждённая память</p></div></div>
      {!editing&&<>{card.blocks&&card.blocks.length>1?<><div className="chat-character-sections">{card.blocks.map((block,i)=><section key={i}><h4>{block.title}</h4><Markdown text={block.text} links={false} liveMarkdown/></section>)}</div><details><summary>Полный исходный раздел</summary><Markdown text={card.text} links={false} liveMarkdown/></details></>:<Markdown text={card.text} links={false} liveMarkdown/>}<Button disabled={disabled||busy} variant="outline" onClick={()=>setEditing(true)}><Pencil size={16}/>Редактировать раздел персонажа</Button>{text!==card.text&&<p className="chat-notice">Есть несохранённая правка на этом устройстве.</p>}</>}
      {editing&&<><p className="muted small">Изменяется только этот фрагмент. Остальная выжимка сохраняется дословно. Канон изменится после отдельного подтверждения новой версии.</p>{preview?<div className="chat-memory-columns"><section><h4>Было</h4><Markdown text={card.text} links={false} liveMarkdown/></section><section><h4>Предложенная правка</h4><Markdown text={text} links={false} liveMarkdown/></section></div>:<><label htmlFor="chat-character-source">Markdown раздела персонажа</label><Textarea id="chat-character-source" className="chat-document-input" rows={18} disabled={busy} value={text} onChange={e=>{setText(e.target.value);save(draftKey,e.target.value)}}/></>}
        <div className="actions"><Button variant="outline" onClick={()=>setPreview(!preview)}>{preview?'Продолжить редактирование':'Предпросмотр изменений'}</Button><Button disabled={disabled||busy||!text.trim()||card.memory_id!==campaign.memory.id} onClick={()=>void saveDraft()}>Проверить новую выжимку</Button></div>
      </>}
      {(error||card.memory_id!==campaign.memory.id)&&<div className="chat-error" role="alert"><p>{error||'Утверждённая память изменилась. Эта правка относится к прежней версии и не будет применена автоматически.'}</p><Button disabled={busy} variant="outline" onClick={()=>void compareCurrent()}><RefreshCw size={16}/>Загрузить актуальную память для сравнения</Button><p className="small">Ваш текст сохранён. Проверьте актуальный раздел перед переносом правки. При неоднозначном имени выберите нужную карточку самостоятельно.</p><Button variant="ghost" onClick={()=>void navigator.clipboard.writeText(text).catch(()=>setError('Копирование недоступно: выделите текст в редакторе.'))}>Копировать свою правку</Button><Button variant="outline" onClick={()=>{setCard(null);setEditing(false);list.reload()}}>К актуальным карточкам</Button></div>}
      {conflictCard&&<section className="chat-conflict-review"><h4>Актуальный раздел с тем же именем</h4><Markdown text={conflictCard.text} links={false} liveMarkdown/><p className="chat-notice">Перенос заменит этот фрагмент вашей правкой. Другие разделы останутся в актуальной версии. Сначала проверьте различия; автоматического объединения нет.</p><Button variant="outline" onClick={()=>{const c=conflictCard;setCard(c);save(`chat-character:${campaign.id}:${c.memory_id}:${c.key}`,text);setEditing(true);setPreview(true);setConflictCard(null);setLatest(null);setError('')}}>Перенести мою правку в актуальный раздел</Button></section>}
      {latest!==null&&<details><summary>Полная актуальная утверждённая выжимка</summary><Markdown text={latest} links={false} liveMarkdown/></details>}
    </div>}
  </>;
}

function HistoryPanel({campaign,backRef,onRestore,initial}:Common&{onRestore:(text:string)=>void;initial?:string}){
  const path=base(campaign);const url=`${path}/history?branch=${campaign.active_branch}`;const list=useList<Version>(url);
  const retryVersion=useRef<string|null>(initial||null);const [detail,setDetail]=useState<HistoryDetail|null>(null),[loading,setLoading]=useState(false),[error,setError]=useState(''),[visible,setVisible]=useState(30);const epoch=useRef(0);
  const open=async(id:string)=>{retryVersion.current=id;const e=++epoch.current;setLoading(true);setError('');try{const d=await api<HistoryDetail>(`${path}/history/${id}?branch=${campaign.active_branch}`);if(e===epoch.current){setDetail(d);setVisible(30)}}catch(err){if(e===epoch.current)setError((err as Error).message)}finally{if(e===epoch.current)setLoading(false)}};
  useEffect(()=>{if(initial)void open(initial);return()=>{epoch.current++}},[initial]);
  useBack(backRef,()=>{if(detail){setDetail(null);return true}return false});
  return <>
    <p className="muted small">История утверждённых версий этой ветки. Здесь сравнивается текст, а не делаются выводы о событиях: слух не становится фактом, новая формулировка не доказывает новое действие.</p>
    <Feedback loading={loading||list.loading} error={error||list.error} retry={()=>error&&retryVersion.current?void open(retryVersion.current):list.reload()}/>
    {!detail&&<div className="chat-journal-list">{list.page?.items.map(item=><button className="chat-version-card" key={item.id} onClick={()=>void open(item.id)}><span className="chat-version-dot" aria-hidden="true"/><span><strong>{sourceName(item.source)}</strong><small>{item.created_at} · до сообщения № {item.cutoff}</small><small>{item.branch_name}{item.id===campaign.memory.id?' · текущая версия':''}</small></span><ArrowUpRight size={16}/></button>)}</div>}
    {!detail&&list.page?.more&&<Button disabled={list.loading} variant="outline" onClick={()=>void list.more(`${url}&before=${list.page!.items.at(-1)!.cursor}`)}>Более ранние изменения</Button>}
    {detail&&<div className="chat-journal-detail"><Button variant="ghost" onClick={()=>setDetail(null)}><ArrowLeft size={16}/>К истории версий</Button><h3>{sourceName(detail.memory.source)}</h3><p className="muted small">{detail.memory.created_at} · покрытие до № {detail.memory.cutoff} · применение после № {detail.memory.applies_after||0}</p>
      <p className="chat-notice">{detail.changes.changed?'Изменения текста требуют проверки содержания.':'Текст совпадает с предыдущей версией; сохранена новая точка применения.'} {detail.previous?'Сравнение с непосредственной родительской версией.':'Первоначальная версия: предыдущего документа нет.'}</p>
      {detail.changes.groups.length>0&&<section><h4>Разделы с изменениями текста</h4><div className="chat-change-groups">{detail.changes.groups.map((g,i)=><details key={i}><summary><span>{g.kind==='added'?'Добавлен раздел':g.kind==='removed'?'Удалён раздел':'Изменён раздел'} · {g.title}</span></summary><div className="chat-memory-columns"><section><h4>Было</h4><pre>{g.before||'Раздел отсутствовал'}</pre></section><section><h4>Стало</h4><pre>{g.after||'Раздел отсутствует'}</pre></section></div></details>)}</div></section>}
      <section><h4>Точные текстовые различия</h4><p className="muted small">«−» — удалённая строка, «+» — добавленная. Повторы и порядок строк учитываются.</p>{detail.changes.hunks.slice(0,visible).map((h,i)=><div className="chat-text-hunk" key={i}><p className="muted small">Строки: раньше {h.old_start}, теперь {h.new_start}</p><pre>{h.lines.map((line,j)=><span key={j} className={line.kind==='removed'?'chat-removed':line.kind==='added'?'chat-added':''}>{line.kind==='removed'?'− ':line.kind==='added'?'+ ':'  '}{line.text.replace(/\r?\n$/,'')||'\u00a0'}</span>)}</pre></div>)}{visible<detail.changes.hunks.length&&<Button variant="outline" onClick={()=>setVisible(n=>n+30)}>Следующие различия</Button>}</section>
      <details><summary>Полная выжимка этой версии</summary><Markdown text={detail.memory.text} links={false} liveMarkdown/></details>{detail.previous&&<details><summary>Полная предыдущая версия</summary><Markdown text={detail.previous.text} links={false} liveMarkdown/></details>}
      <details><summary>Происхождение версии</summary><dl className="chat-provenance"><dt>Версия</dt><dd>{detail.memory.id}</dd><dt>Родительская версия</dt><dd>{detail.memory.parent_id||'Первоначальная'}</dd><dt>Ветка источника</dt><dd>{detail.memory.branch_id}</dd><dt>Источник</dt><dd>{sourceName(detail.memory.source)}</dd>{detail.provenance?.job_id&&<><dt>Записанный запрос</dt><dd>{detail.provenance.job_id}</dd></>}</dl></details>
      <Button variant="outline" onClick={()=>onRestore(detail.memory.text)}>Вернуть эту версию в редактор</Button><p className="muted small">Восстановление не меняет прошлое. После проверки будет создана новая авторская версия в текущей ветке.</p>
    </div>}
  </>;
}
