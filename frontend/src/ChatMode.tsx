import {useCallback,useEffect,useLayoutEffect,useRef,useState} from 'react';
import {ArrowLeft,ArrowDown,BookOpen,Send,Square,Plus,Settings2,FileText,GitBranch,Pencil,RefreshCw,Info,MoreHorizontal,Maximize2,Bookmark,BookmarkCheck,NotebookTabs} from 'lucide-react';
import {toast} from 'sonner';
import {api,download} from './api';
import {Button} from './components/ui/button';
import {Textarea} from './components/ui/textarea';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './components/ui/dialog';
import {Markdown} from './Markdown';
import {ThemeSelector} from './ThemeProvider';
import {ChatCreationEditor} from './ChatCreation';
import {ChatSettingsEditor} from './ChatSettings';
import {ChatIconButton} from './ChatIconButton';
import {ChatJournal,type JournalStart} from './ChatJournal';
import {SectionTabs} from './components/ui/section-tabs';
import {useChatNavigation} from './useChatNavigation';
import {useChatScroll} from './useChatScroll';
import type {ChatCampaign,ChatDraft,ChatJob,ChatMemory,ChatMessage,ChatSettings,ChatSource,Budgets} from './chatTypes';
import './styles/chat.css';

const token=()=>crypto.randomUUID();
const prefix='/chat/campaigns';
const readLocal=(key:string,fallback='')=>{try{return localStorage.getItem(key)??fallback}catch{return fallback}};
const saveLocal=(key:string,value:string)=>{try{localStorage.setItem(key,value)}catch{/* server-saved messages remain authoritative */}};
const forgetLocal=(key:string)=>{try{localStorage.removeItem(key)}catch{/* keep server state */}};
const statusText:Record<string,string>={running:'Ответ поступает…',complete:'Сохранено',stopped:'Остановлено · неполный текст',length:'Лимит ответа · неполный текст',error:'Ошибка · исход расхода может быть неизвестен',empty:'Пустой ответ',interrupted:'Прервано · повтор только вручную'};

type Panel='library'|'create'|'chapters'|'memory'|'settings'|'edit'|'request'|'menu'|'compose'|'journal'|'action'|null;
export function ChatMode({onBack,onConnections,source}:{onBack:()=>void;onConnections:()=>void;source?:ChatSource}) {
  const [campaign,setCampaignState]=useState<ChatCampaign|null>(null);
  const campaignRef=useRef<ChatCampaign|null>(null);
  const pageEpoch=useRef(0);
  const [selected,setSelected]=useState(()=>readLocal('chat-selection'));
  const selectedRef=useRef(selected);selectedRef.current=selected;
  const [list,setList]=useState<{id:string;name:string;mode:string}[]>([]);
  const [panel,setPanel]=useState<Panel>(source?'create':selected?null:'library');
  const lastPanel=useRef(panel);if(panel)lastPanel.current=panel;
  const shownPanel=panel||lastPanel.current;
  const [defaults,setDefaults]=useState<{template:string;settings:ChatSettings}|null>(null);
  const [settings,setSettings]=useState<ChatSettings|null>(null);
  const [sourceSpec,setSourceSpec]=useState(source);
  const [draft,setDraft]=useState('');
  const draftRef=useRef(draft);draftRef.current=draft;
  const [pending,setPending]=useState(false);
  const [busy,setBusy]=useState(false);
  const busyRef=useRef(false);
  const [error,setError]=useState('');
  const [messages,setMessages]=useState<ChatMessage[]>([]);
  const [more,setMore]=useState(false);
  const [moreAfter,setMoreAfter]=useState(false);
  const [journalStart,setJournalStart]=useState<JournalStart>({tab:'bookmarks'});
  const journalBack=useRef<(()=>boolean)|null>(null);
  const [action,setAction]=useState<{text:string;scope:string;archived:boolean}|null>(null);
  const jumpRef=useRef<string|null>(null);
  const [highlighted,setHighlighted]=useState<string|null>(null);
  const [archive,setArchive]=useState<string|null>(null);
  const [job,setJob]=useState<ChatJob|null>(null);
  const [budgets,setBudgets]=useState<Budgets|null>(null);
  const [later,setLater]=useState(false);
  const [memory,setMemory]=useState('');
  const [review,setReview]=useState<ChatDraft|null>(null);
  const [versions,setVersions]=useState<ChatMemory[]>([]);
  const [requestDetails,setRequestDetails]=useState<Record<string,unknown>[]>([]);
  const [partial,setPartial]=useState(false);
  const [nextChapter,setNextChapter]=useState(true);
  const [editing,setEditing]=useState<ChatMessage|null>(null);
  const [editText,setEditText]=useState('');
  const [memoryTab,setMemoryTab]=useState<'read'|'edit'|'compare'|'versions'>('read');
  const [requestLoading,setRequestLoading]=useState(false);
  const inputRef=useRef<HTMLTextAreaElement>(null);
  const dialogRef=useRef<HTMLDivElement>(null);
  const {viewport,content,sticky,following,toLatest}=useChatScroll(`${selected}:${campaign?.active_branch}:${archive||''}`);
  const innerBack=()=>panel==='journal'&&(journalBack.current?.()||false);
  const {open:openPanel,close:closePanel,back:goBack,trigger:triggerRef}=useChatNavigation(panel,setPanel,onBack,innerBack);
  const setCampaign=(next:ChatCampaign|null)=>{
    if(next&&(next.id!==selectedRef.current||(campaignRef.current?.id===next.id&&campaignRef.current.revision>next.revision)))return false;
    campaignRef.current=next;setCampaignState(next);return true;
  };
  const active=job?.status==='running';
  // Budget recalculation clears transient estimates; it must not unlock the opening.
  const openingPending=!!campaign?.opening_required&&(campaign.branch.head===0||(campaign.branch.head===1&&(active||campaign.budgets.unfinished)));
  const path=`${prefix}/${selected}`;
  const revision=()=>({revision:campaign!.revision,token:token()});
  useLayoutEffect(()=>{
    const el=inputRef.current;if(!el)return;
    const resize=()=>{el.style.height='0px';el.style.height=`${Math.min(el.scrollHeight,Math.max(80,Math.min(220,(window.visualViewport?.height||innerHeight)*.3)))}px`};
    resize();window.visualViewport?.addEventListener('resize',resize);window.addEventListener('resize',resize);
    return()=>{window.visualViewport?.removeEventListener('resize',resize);window.removeEventListener('resize',resize)};
  },[draft,!!campaign,archive]);
  useEffect(()=>{
    if(!panel)return;
    let frame=0;
    const reveal=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{
      if(innerWidth>=768)return;
      const field=document.activeElement as HTMLElement|null;
      const body=dialogRef.current?.querySelector<HTMLElement>('.chat-dialog-body');
      if(!field||!body?.contains(field)||!field.matches('textarea,input:not([type=checkbox])'))return;
      const bounds=body.getBoundingClientRect(),rect=field.getBoundingClientRect();
      const tabs=body.querySelector<HTMLElement>('.chat-journal-tabs,.chat-memory-tabs');
      const top=bounds.top+(tabs?.getBoundingClientRect().height||0)+12;
      if(rect.top<top||rect.bottom>bounds.bottom-12)body.scrollTop+=rect.top-top;
    })};
    // Scroll only this dialog's body after viewport CSS has settled. Native
    // scrollIntoView can move the fixed shell; ordinary reading scroll stays free.
    window.visualViewport?.addEventListener('resize',reveal);window.addEventListener('resize',reveal);document.addEventListener('focusin',reveal);
    return()=>{cancelAnimationFrame(frame);window.visualViewport?.removeEventListener('resize',reveal);window.removeEventListener('resize',reveal);document.removeEventListener('focusin',reveal)};
  },[!!panel]);
  const run=async(fn:()=>Promise<void>)=>{
    if(busyRef.current)return;
    busyRef.current=true;setBusy(true);setError('');
    try{await fn()}catch(e){setError((e as Error).message);toast.error((e as Error).message)}
    finally{busyRef.current=false;setBusy(false)}
  };
  const loadPage=useCallback(async(cid:string,chapter:string|null,branch?:string)=>{
    const epoch=++pageEpoch.current;
    const query=new URLSearchParams();if(chapter)query.set('chapter',chapter);if(branch)query.set('branch',branch);
    const p=await api<{messages:ChatMessage[];more:boolean;more_after?:boolean}>(`${prefix}/${cid}/messages?${query}`);
    if(selectedRef.current===cid&&pageEpoch.current===epoch){setMessages(p.messages);setMore(p.more);setMoreAfter(!!p.more_after)}
  },[]);
  const refresh=useCallback(async(cid=selectedRef.current)=>{
    const c=await api<ChatCampaign>(`${prefix}/${cid}`);
    if(selectedRef.current===cid&&setCampaign(c)){setJob(c.job);setBudgets(c.budgets)}
    return c;
  },[]);
  useEffect(()=>{void api<{template:string;settings:ChatSettings}>('/chat/defaults').then(d=>{setDefaults(d);setSettings(d.settings)}).catch(e=>setError(e.message))},[]);
  useEffect(()=>{
    if(panel==='library')void api<{id:string;name:string;mode:string}[]>(prefix).then(setList).catch(e=>setError(e.message));
  },[panel]);
  useEffect(()=>{
    if(!selected)return;
    saveLocal('chat-selection',selected);setCampaign(null);setMessages([]);setArchive(null);setJob(null);setLater(false);setError('');setMoreAfter(false);jumpRef.current=null;setHighlighted(null);
    setDraft('');setPending(!!readLocal(`chat-pending:${selected}`));
    void refresh(selected).then(c=>loadPage(selected,null,c.active_branch)).catch(e=>setError(e.message));
  },[selected,refresh,loadPage]);
  useEffect(()=>{
    if(campaign?.id===selected){setDraft(readLocal(`chat-input:${selected}:${campaign.active_branch}`));setLater(false)}
  },[selected,campaign?.active_branch]);
  useEffect(()=>{
    if(!campaign)return;
    const controller=new AbortController();
    setBudgets(null);
    const timeout=setTimeout(()=>void api<Budgets>(`${path}/budget`,{...revision(),text:draft},'POST',controller.signal)
      .then(setBudgets).catch(e=>{if(!controller.signal.aborted)setError(e.message)}),250);
    return()=>{clearTimeout(timeout);controller.abort()};
  },[draft,campaign,selected]);
  useEffect(()=>{
    if(!selected||!job||job.status!=='running')return;
    const events=new EventSource(`/api${path}/jobs/${job.id}/events`);
    const snapshot=(event:MessageEvent)=>{
      if(selectedRef.current!==selected)return;
      const j=JSON.parse(event.data) as ChatJob;setJob(j);
      if(j.kind!=='summary'&&!archive)setMessages(previous=>previous.map(m=>m.id===j.output_id?{...m,content:j.response,status:j.status}:m));
      if(j.status!=='running'){
        // The final snapshot already contains the durable response. Reloading
        // the last page here discarded an older page being read during a stream.
        events.close();void refresh().catch(e=>setError(e.message));
        if(j.kind==='summary')void api<ChatDraft>(`${path}/drafts/${j.output_id}`).then(d=>{setReview(d);setMemory(d.text);setMemoryTab('edit');setNextChapter(!!d.next_chapter);setPartial(false);openPanel('memory')}).catch(e=>setError(e.message));
      }
    };
    events.addEventListener('snapshot',snapshot as EventListener);
    events.onerror=()=>setError('Поток отключён. Переподключаемся к сохранённому запросу; новая генерация не запускается.');
    return()=>events.close();
  },[selected,job?.id,job?.status,archive,refresh,loadPage]);
  const choose=(id:string)=>{setSelected(id);if(id===selected)void refresh();closePanel()};
  const writeDraft=(text:string)=>{draftRef.current=text;setBudgets(null);setDraft(text);saveLocal(`chat-input:${selected}:${campaign!.active_branch}`,text);setLater(false)};
  const openJournal=(initial:JournalStart={tab:'bookmarks'})=>{setJournalStart(initial);openPanel('journal')};
  const focusJump=()=>{
    if(!jumpRef.current||!viewport.current)return;
    const target=content.current?.querySelector<HTMLElement>(`[data-message-id="${CSS.escape(jumpRef.current)}"]`);
    if(target){sticky.current=false;viewport.current.scrollTop+=target.getBoundingClientRect().top-viewport.current.getBoundingClientRect().top-12}
  };
  const jumpToMessage=async(id:string)=>{
    const cid=selected,bid=campaign!.active_branch,epoch=++pageEpoch.current;
    const location=await api<{seq:number;chapter:string}>(`${path}/messages/${id}/locate?branch=${bid}`);
    const p=await api<{messages:ChatMessage[];more:boolean;more_after:boolean}>(`${path}/messages?branch=${bid}&chapter=${location.chapter}&before=${location.seq+21}`);
    if(selectedRef.current!==cid||campaignRef.current?.active_branch!==bid||pageEpoch.current!==epoch)return;
    jumpRef.current=id;setHighlighted(id);setArchive(location.chapter===campaign!.branch.chapter_id?null:location.chapter);setMessages(p.messages);setMore(p.more);setMoreAfter(p.more_after);sticky.current=false;
    closePanel(()=>requestAnimationFrame(focusJump));
  };
  const chooseAction=(text:string)=>{
    if(active||busy||openingPending)return;
    if(draft.trim()||archive){setAction({text,scope:`${selected}:${campaign!.active_branch}`,archived:!!archive});openPanel('action')}
    else{writeDraft(text);inputRef.current?.focus({preventScroll:true})}
  };
  const applyAction=(append:boolean)=>void run(async()=>{
    if(!action||action.scope!==`${selected}:${campaign!.active_branch}`)throw Error('Ветка изменилась. Выберите вариант из нужной истории заново.');
    writeDraft(append&&draft.trim()?`${draft}\n\n${action.text}`:action.text);
    if(archive){await loadPage(selected,null,campaign!.active_branch);setArchive(null)}
    closePanel(()=>requestAnimationFrame(()=>inputRef.current?.focus({preventScroll:true})));
  });
  const saveBookmark=async(item:{message_id:string},enabled:boolean,note:string,priority:number)=>{
    const c=await api<ChatCampaign>(`${path}/bookmarks`,{...revision(),branch:campaign!.active_branch,message:item.message_id,enabled,note,priority},'PUT');
    if(setCampaign(c)){setBudgets(c.budgets);setMessages(rows=>rows.map(m=>m.id===item.message_id?{...m,bookmark:enabled?{note,priority}:null}:m))}
  };
  const openMemory=()=>{setReview(null);setMemory(readLocal(`chat-memory:${selected}:${campaign!.memory.id}`,campaign!.memory.text));setMemoryTab('read');setPartial(false);setNextChapter(false);openPanel('memory');void api<ChatMemory[]>(`${path}/versions`).then(setVersions).catch(e=>setError(e.message))};
  const settingsKey=`chat-settings:${selected}:${campaign?.branch.config_id||campaign?.active_branch}`;
  const openSettings=()=>{let saved=campaign!.settings;try{const local=JSON.parse(readLocal(settingsKey));if(local?.reply&&local?.summary&&typeof local.prompt==='string')saved=local}catch{/* use approved settings */}setSettings(saved);openPanel('settings')};
  const editKey=(id:string)=>`chat-edit:${selected}:${id}`;
  const openEdit=(m:ChatMessage)=>{setEditing(m);setEditText(readLocal(editKey(m.id),m.content));openPanel('edit')};
  const openRequest=(id:string)=>void run(async()=>{setRequestDetails([]);setRequestLoading(true);openPanel('request');try{setRequestDetails(await api<Record<string,unknown>[]>(`${path}/jobs/${id}/requests`))}finally{setRequestLoading(false)}});
  const connections=()=>closePanel(onConnections);
  const generate=async(kind='reply',target?:string,next=false)=>{
    const request={...revision(),kind,text:kind==='reply'?draft:'',target:target||null,next_chapter:next};
    if(kind==='reply'){saveLocal(`chat-pending:${selected}`,JSON.stringify(request));setPending(true)}
    const j=await api<ChatJob>(`${path}/generate`,request);saveLocal(`chat-pending:${selected}`,'');
    if(selectedRef.current!==selected)return;
    setJob(j);setPending(false);
    if(kind==='reply'&&draftRef.current===request.text)writeDraft('');
    const c=await refresh();await loadPage(c.id,null,c.active_branch);setArchive(null);
    if(c.job?.kind==='summary'&&c.job.status!=='running'){const d=await api<ChatDraft>(`${path}/drafts/${c.job.output_id}`);setReview(d);setMemory(d.text);setMemoryTab('edit');setNextChapter(!!d.next_chapter);setPartial(false);openPanel('memory')}
  };
  const summary=(next:boolean)=>{const start=()=>void run(async()=>{setNextChapter(next);await generate('summary',undefined,next)});if(panel)closePanel(start);else start()};
  const changeChapter=(id:string|null)=>void run(async()=>{await loadPage(selected,id,campaign!.active_branch);setArchive(id);closePanel()});
  const changeBranch=(id:string)=>void run(async()=>{
    const c=await api<ChatCampaign>(`${path}/select`,{...revision(),branch:id});setCampaign(c);setJob(c.job);setBudgets(c.budgets);setArchive(null);setLater(false);await loadPage(c.id,null,c.active_branch);closePanel();
  });
  const commitMemory=()=>void run(async()=>{
    let id=review?.id;
    let rev=campaign!.revision;
    if(!id){const result=await api<{draft:string}>(`${path}/memory`,{...revision(),text:memory});id=result.draft;const c=await refresh();rev=c.revision;const d=await api<ChatDraft>(`${path}/drafts/${id}`);setReview(d)}
    const c=await api<ChatCampaign>(`${path}/drafts/${id}/confirm`,{revision:rev,token:token(),text:memory,next_chapter:nextChapter,accept_partial:partial,draft_revision:review?.edit_revision||0});
    forgetLocal(`chat-memory:${selected}:${campaign!.memory.id}`);forgetLocal(`chat-review:${id}`);setCampaign(c);setBudgets(c.budgets);setArchive(null);setLater(false);await loadPage(selected,null,c.active_branch);openJournal({tab:'history',version:c.memory.id});
  });
  const loadReview=(id:string)=>void run(async()=>{
    const d=await api<ChatDraft>(`${path}/drafts/${id}`);setReview(d);setMemory(readLocal(`chat-review:${id}`,d.text));setMemoryTab('edit');setNextChapter(!!d.next_chapter);setPartial(false);openPanel('memory');
  });
  const memoryEdit=(text:string)=>{setMemory(text);saveLocal(review?`chat-review:${review.id}`:`chat-memory:${selected}:${campaign!.memory.id}`,text)};
  const oldText=review?.previous||campaign?.memory.text||'';
  const oldLines=new Set(oldText.split('\n')),newLines=new Set(memory.split('\n'));
  return <main className="chat-mode" aria-label="RP-чат">
    <header className="chat-header">
      <ChatIconButton label="Вернуться в Narrative" onClick={goBack}><ArrowLeft size={20}/></ChatIconButton>
      <div className="chat-heading"><span className="eyebrow">CHAT MODE · RP-ЧАТ</span><h1>{campaign?.name||'Твои RP-истории'}</h1><span className="muted small">{campaign?`${campaign.chapters.find(c=>c.id===(archive||campaign.branch.chapter_id))?.name||'Глава'} · ${archive?'архив, только чтение':'активное продолжение'}`:'Одна кампания, сколько угодно глав в пределах хранилища'}</span></div>
      <Button variant="ghost" aria-label="Кампании RP-чата" onClick={()=>openPanel('library')}><BookOpen size={18}/><span className="chat-desktop">Кампании</span></Button>
      <ChatIconButton label="Настройки RP-чата" disabled={!campaign} onClick={openSettings}><Settings2 size={18}/></ChatIconButton>
    </header>
    {campaign?<>
      <nav className="chat-toolbar" aria-label="Кампания"><Button variant="ghost" aria-label="Главы и ветки" onClick={()=>openPanel('chapters')}><GitBranch size={16}/><span className="chat-desktop">Главы и ветки</span><span className="chat-mobile">Главы</span></Button><Button variant="ghost" onClick={openMemory}><FileText size={16}/>Выжимка</Button><Button className="chat-desktop" disabled={busy||active} variant="ghost" onClick={()=>summary(false)}>Обновить выжимку</Button><Button className="chat-desktop" disabled={busy||active} onClick={()=>summary(true)}>Обновить выжимку и продолжить</Button><Button aria-label="Действия кампании" variant="ghost" onClick={()=>openPanel('menu')}><MoreHorizontal size={20}/>Ещё</Button></nav>
      {error&&<div className="chat-notice" role="alert">{error}<Button variant="ghost" onClick={()=>void run(async()=>{const c=await refresh();await loadPage(c.id,archive,c.active_branch)})}>Обновить состояние</Button></div>}
      <div className="chat-budget"><button aria-label="Оценка контекста и резервы" onClick={()=>openPanel('menu')}>Контекст {budgets?`≈ ${Math.round(budgets.reply.ratio*100)}%`:'· считаем…'}<Info size={14}/></button>{budgets&&<meter aria-label="Оценка контекста" min={0} max={1} value={Math.min(budgets.reply.ratio,1)}/>}</div>
      {budgets?.warning&&(!later||!budgets.reply.fits)&&<div className="chat-notice chat-context-warning" role="status"><p>{budgets.reply.fits?'Контекст почти заполнен.':'Ввод не помещается в контекст.'} Обновите выжимку и начните следующую главу. Переписка останется в кампании.{!budgets.summary.fits?' Суммаризация тоже не помещается: отредактируйте память или настройте большее совместимое окно.':''}</p><div className="chat-notice-actions"><Button disabled={busy||active||!budgets.summary.fits} onClick={()=>summary(true)}>Обновить и продолжить</Button>{budgets.reply.fits&&<Button variant="ghost" onClick={()=>setLater(true)}>Позже</Button>}<Button variant="ghost" onClick={openMemory}>Редактор памяти</Button>{!budgets.summary.fits&&!!budgets.summary.bookmarks_included&&<Button variant="ghost" onClick={()=>openJournal()}>Приоритеты закладок</Button>}</div></div>}
      {campaign.drafts.filter(d=>d.status!=='running').length>0&&<div className="chat-draft-links">{campaign.drafts.filter(d=>d.status!=='running').map(d=><Button key={d.id} size="sm" variant="ghost" onClick={()=>loadReview(d.id)}>Черновик выжимки{d.source_revision!==campaign.revision?' · устарел':''}</Button>)}</div>}
      {archive&&<div className="chat-notice">Архив: просмотр не меняет контекст. Редактирование создаст отдельную ветку.<Button onClick={()=>changeChapter(null)}>К активной главе</Button></div>}
      <div className="chat-scroll" ref={viewport} onWheel={()=>{jumpRef.current=null}} onTouchStart={()=>{jumpRef.current=null}} onKeyDown={()=>{jumpRef.current=null}} tabIndex={0} aria-label="Переписка"><div className="chat-column" ref={content}>
        {more&&<Button variant="ghost" disabled={busy} onClick={()=>void run(async()=>{
          const el=viewport.current;const height=el?.scrollHeight||0;sticky.current=false;
          const q=new URLSearchParams({before:String(messages[0].seq),branch:campaign.active_branch});if(archive)q.set('chapter',archive);
          const p=await api<{messages:ChatMessage[];more:boolean}>(`${path}/messages?${q}`);setMessages(m=>[...p.messages,...m]);setMore(p.more);
          requestAnimationFrame(()=>{if(el)el.scrollTop+=el.scrollHeight-height});
        })}>Ранее в истории</Button>}
        {!messages.length&&<div className="chat-empty"><FileText size={28}/><h2>{archive?'В этой главе пока нет сообщений':openingPending?'Готовим стартовую сцену…':'Продолжим историю'}</h2><p>{openingPending?'После стартовой сцены можно будет ввести действие или реплику.':campaign.branch.head?'Сцена и выжимка перенесены. Следующий ввод продолжит её без повторения последнего действия.':'Опишите действие, реплику или начальную сцену. Неизвестные поля выжимки можно оставить пустыми.'}</p></div>}
        {messages.map(m=><article className={`chat-message chat-${m.role}${highlighted===m.id?' chat-message-target':''}`} key={m.id} data-message-id={m.id}><header><strong>{m.role==='user'?'Ты':'История'}</strong><span>{statusText[m.status]||m.status}</span></header><Markdown text={m.content} links={false} streaming={m.status==='running'} liveMarkdown onReady={focusJump} onAction={m.role==='assistant'?chooseAction:undefined} actionsComplete={m.status==='complete'} actionsDisabled={!!active||busy||openingPending}/><footer aria-label="Действия над сообщением"><ChatIconButton label={m.bookmark?'Изменить закладку':'Добавить закладку'} aria-pressed={!!m.bookmark} disabled={active||busy||m.status==='running'} onClick={()=>openJournal({tab:'bookmarks',message:m})}>{m.bookmark?<BookmarkCheck size={18}/>:<Bookmark size={18}/>}</ChatIconButton><ChatIconButton label="Редактировать" disabled={active||busy} onClick={()=>openEdit(m)}><Pencil size={18}/></ChatIconButton>{m.role==='assistant'&&m.job_id&&<ChatIconButton label="Перегенерировать" disabled={active||busy} onClick={()=>void run(()=>generate('regenerate',m.id))}><RefreshCw size={18}/></ChatIconButton>}{m.job_id&&<ChatIconButton label="Запрос и расход" disabled={busy} onClick={()=>openRequest(m.job_id!)}><Info size={18}/></ChatIconButton>}</footer></article>)}
        {moreAfter&&<Button variant="outline" disabled={busy} onClick={()=>void run(async()=>{
          jumpRef.current=null;const q=new URLSearchParams({after:String(messages.at(-1)!.seq),branch:campaign.active_branch});if(archive)q.set('chapter',archive);
          const p=await api<{messages:ChatMessage[];more_after:boolean}>(`${path}/messages?${q}`);sticky.current=false;setMessages(rows=>[...rows,...p.messages]);setMoreAfter(p.more_after);
        })}>Позже в истории</Button>}
        {job&&(job.status!=='complete'||job.kind==='summary')&&<div className="chat-receipt"><span role="status">{statusText[job.status]||job.status}{job.kind==='summary'?' · обновление выжимки':''}</span>{job.error&&<p role="alert">{job.error}</p>}
          {job.status!=='running'&&job.status!=='complete'&&job.kind!=='summary'&&<Button disabled={busy} variant="outline" onClick={()=>void run(()=>generate('retry',job.id))}>Повторить явно (новый вызов)</Button>}
        </div>}
      </div></div>
      {!following&&<Button className="chat-latest" variant="secondary" onClick={()=>void run(async()=>{jumpRef.current=null;if(moreAfter)await loadPage(selected,archive,campaign.active_branch);requestAnimationFrame(toLatest)})}><ArrowDown size={16}/>К последнему сообщению</Button>}
      {!archive&&campaign.opening_required&&!campaign.branch.head&&<Button disabled={busy} onClick={()=>void run(()=>generate('start'))}>Начать игру</Button>}
      {!archive&&<form className="chat-composer" onSubmit={e=>{e.preventDefault();void run(()=>generate())}}><label className="sr-only" htmlFor="chat-input">Твоё сообщение</label><Textarea ref={inputRef} id="chat-input" disabled={openingPending} placeholder="Действие или реплика…" rows={2} value={draft} onChange={e=>writeDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();if(!active&&!busy&&!budgets?.unfinished&&!openingPending&&budgets?.reply.fits)void run(()=>generate())}}}/><div className="chat-composer-actions"><ChatIconButton label="Развернуть ввод" disabled={openingPending} onClick={()=>openPanel('compose')}><Maximize2 size={18}/></ChatIconButton><span className="muted small">Ctrl/⌘ + Enter · черновик сохранён</span>{active?<Button aria-label="Остановить" type="button" disabled={busy} variant="outline" onClick={()=>void run(async()=>{setJob(await api(`${path}/jobs/${job.id}/stop`,{}));await refresh();await loadPage(selected,null,campaign.active_branch)})}><Square size={18}/><span className="chat-desktop">Остановить</span></Button>:<Button aria-label="Отправить" type="submit" disabled={busy||openingPending||!draft.trim()||!budgets?.reply.fits||budgets.unfinished}><Send size={18}/><span className="chat-desktop">Отправить</span></Button>}</div>
        {pending&&<Button type="button" variant="ghost" onClick={()=>void run(async()=>{const payload=JSON.parse(readLocal(`chat-pending:${selected}`));await api(`${path}/generate`,payload);saveLocal(`chat-pending:${selected}`,'');setPending(false);if(draftRef.current===payload.text)writeDraft('');const c=await refresh();await loadPage(selected,null,c.active_branch)})}>Проверить отправку без повторного вызова</Button>}
        {budgets?.unfinished&&<p className="small">Примите частичный ответ через «Редактировать» или повторите его явно.</p>}
      </form>}
    </>:selected?<section className="chat-welcome" aria-live="polite"><h2>{error?'Не удалось открыть кампанию':'Открываем историю…'}</h2>{error&&<><p role="alert">{error}</p><Button onClick={()=>void run(async()=>{const c=await refresh();await loadPage(c.id,null,c.active_branch)})}>Повторить загрузку</Button></>}<Button variant="outline" onClick={()=>openPanel('library')}>Открыть другую кампанию</Button></section>:<section className="chat-welcome"><h2>История продолжается</h2><p>RP-чат хранит переписку, главы и авторскую память. Вы решаете, когда обновить выжимку и продолжить.</p><Button disabled={!defaults} onClick={()=>{setSettings(defaults?.settings||null);openPanel('create')}}><Plus size={18}/>Новая RP-кампания</Button><Button variant="outline" onClick={()=>openPanel('library')}>Открыть кампанию</Button>{error&&<p role="alert">{error}</p>}</section>}
    <Dialog open={!!panel} onOpenChange={open=>{if(!open)closePanel()}}><DialogContent ref={dialogRef} className={`chat-dialog ${shownPanel==='memory'?'chat-memory-dialog':''}`} onOpenAutoFocus={e=>{e.preventDefault();dialogRef.current?.querySelector<HTMLElement>('.dialog-title')?.focus({preventScroll:true})}} onEscapeKeyDown={e=>{if(innerBack())e.preventDefault()}} onCloseAutoFocus={e=>{e.preventDefault();triggerRef.current?.isConnected&&triggerRef.current.focus({preventScroll:true})}}><DialogHeader><DialogTitle tabIndex={-1}>{{library:'RP-кампании',create:'Новая история',chapters:'Главы и ветки',memory:review?'Проверка новой выжимки':'Авторская выжимка',settings:'Настройки RP-чата',edit:'Редактировать сообщение',request:'Запрос и расход',menu:'Управление историей',compose:'Твоё сообщение',journal:'Журнал кампании',action:'Вариант для твоего действия'}[shownPanel||'library']}</DialogTitle><DialogDescription>{shownPanel==='memory'?'Авторский документ со спойлерами. Знания игрока и ГГ различаются.':shownPanel==='edit'?'Правка создаст новую ветку. Исходная история сохранится.':shownPanel==='create'?'Сначала подготовьте и проверьте выжимку, затем начните игру.':shownPanel==='compose'?'Черновик сохраняется на этом устройстве.':shownPanel==='settings'?'Изменения действуют со следующего запроса.':shownPanel==='journal'?'Закладки, персонажи и изменения утверждённой памяти.':shownPanel==='action'?'Вариант попадёт только в черновик. Отправка — отдельным действием.':'История, главы и выжимки сохраняются в этой кампании.'}</DialogDescription></DialogHeader>
      <div className="chat-dialog-body">
      {error&&<p className="chat-error" role="alert">{error}</p>}
      {shownPanel==='journal'&&campaign&&<ChatJournal key={`${selected}:${campaign.active_branch}:${journalStart.message?.id||''}:${journalStart.version||''}`} campaign={campaign} disabled={busy||!!active} initial={journalStart} backRef={journalBack} onRefresh={refresh} onBookmark={saveBookmark} onJump={jumpToMessage} onClose={()=>closePanel()} onReview={async id=>{await refresh();const d=await api<ChatDraft>(`${path}/drafts/${id}`);setReview(d);setMemory(d.text);setMemoryTab('edit');setNextChapter(false);setPartial(false);openPanel('memory')}} onRestore={text=>{setReview(null);setMemory(text);saveLocal(`chat-memory:${selected}:${campaign.memory.id}`,text);setMemoryTab('edit');setNextChapter(false);setPartial(false);openPanel('memory')}}/>}
      {shownPanel==='action'&&action&&<><h3>Предложенное действие</h3><p className="chat-action-preview">{action.text}</p>{action.archived&&<p className="chat-notice">Это вариант из архивного сообщения. Он будет вставлен в текущий черновик активной ветки; архив не изменится.</p>}{draft.trim()&&<details open><summary>Текущий черновик сохранён</summary><pre>{draft}</pre></details>}<div className="actions"><Button disabled={busy||active} onClick={()=>applyAction(true)}>{draft.trim()?'Добавить к черновику':'Вставить в поле ввода'}</Button>{draft.trim()&&<Button disabled={busy||active} variant="outline" onClick={()=>applyAction(false)}>Заменить черновик этим вариантом</Button>}<Button variant="ghost" onClick={()=>closePanel()}>Оставить мой текст</Button></div></>}
      {shownPanel==='library'&&<><Button disabled={!defaults||busy} onClick={()=>{setSourceSpec(undefined);setSettings(defaults!.settings);setPanel('create')}}><Plus size={16}/>Новая RP-кампания</Button>{!list.length&&<p>Пока нет кампаний.</p>}{list.map(c=><button className="chat-campaign-card" key={c.id} disabled={busy} onClick={()=>choose(c.id)}><strong>{c.name}</strong><span>RP-чат · продолжить →</span></button>)}</>}
      {shownPanel==='create'&&!defaults&&!error&&<p role="status">Загружаем шаблон и настройки…</p>}
      {shownPanel==='create'&&defaults&&<ChatCreationEditor defaults={defaults} source={sourceSpec} onConnections={connections} onCreated={c=>{setSelected(c.id);closePanel()}}/>}
      {shownPanel==='chapters'&&campaign&&<><h3>Главы активной ветки</h3>{campaign.chapters.map(c=><button className="chat-campaign-card" key={c.id} onClick={()=>changeChapter(c.id===campaign.branch.chapter_id?null:c.id)}><strong>{c.name}</strong><span>{c.id===campaign.branch.chapter_id?'Активная':'Архив · читать'}</span></button>)}<h3>Сохранённые ветки / варианты</h3><p>Выбор ветки меняет продолжение кампании. Просмотр главы выше — только чтение.</p>{campaign.branches.map(b=><Button key={b.id} disabled={active||busy||b.id===campaign.active_branch} variant="outline" onClick={()=>changeBranch(b.id)}>{b.name} · {b.head} сообщений{b.id===campaign.active_branch?' · активна':''}</Button>)}{campaign.source!=null&&<details><summary>Происхождение исходной копии</summary><pre>{JSON.stringify(campaign.source,null,2)}</pre></details>}</>}
      {shownPanel==='menu'&&campaign&&<>
        <Button variant="outline" onClick={()=>openJournal()}><NotebookTabs size={18}/>Закладки, персонажи и изменения</Button>
        <Button disabled={busy||active} onClick={()=>summary(true)}>Обновить выжимку и продолжить</Button><p className="muted small">Проверьте новый документ перед переходом в следующую главу. История сохранится.</p>
        <Button disabled={busy||active} variant="outline" onClick={()=>summary(false)}>Обновить выжимку</Button>
        <Button variant="ghost" onClick={openSettings}><Settings2 size={18}/>Настройки RP-чата</Button>
        <Button variant="ghost" onClick={()=>openPanel('library')}><BookOpen size={18}/>Кампании RP-чата</Button>
        {budgets&&<section className="chat-context-details"><h3>Оценка и резервы</h3><p>Вход: ≈ {budgets.reply.estimated_tokens.toLocaleString()} / {budgets.reply.available.toLocaleString()} токенов.</p><p>{budgets.reply.token_method||'Консервативная оценка UTF-8'}. Окно: {budgets.reply.context_length}. Ответ: {budgets.reply.output}. Запас: {budgets.reply.margin}.</p><p>Суммаризация: ≈ {budgets.summary.estimated_tokens} / {budgets.summary.available}, резерв выжимки {budgets.summary.output}, следующего RP-ответа {budgets.summary.next_reply_reserve||0}. Фактический расход — у сообщения по кнопке информации.</p></section>}
      </>}
      {shownPanel==='request'&&<>{requestLoading?<p role="status">Загружаем сведения о запросе…</p>:!requestDetails.length?<p>Провайдер ещё не сообщил расход. Неизвестные значения не считаются нулём.</p>:requestDetails.map((receipt,i)=><section className="chat-request" key={i}><h3>{String(receipt.provider||'Провайдер')} · {String(receipt.model||'Модель неизвестна')}</h3><dl>{[['Статус',receipt.status],['Входные токены',receipt.input_tokens],['Выходные токены',receipt.output_tokens],['Стоимость по сохранённым ставкам',receipt.cost_usd==null?null:`≈ $${receipt.cost_usd}`]].map(([label,value])=><div key={String(label)}><dt>{String(label)}</dt><dd>{value==null?'Неизвестно':String(value)}</dd></div>)}</dl><details><summary>Записанный контекст и диагностика</summary><p className="small">Авторские данные могут содержать спойлеры.</p><pre>{JSON.stringify(receipt,null,2)}</pre></details></section>)}</>}
      {shownPanel==='settings'&&settings&&<><ChatSettingsEditor value={settings} onChange={value=>{setSettings(value);saveLocal(settingsKey,JSON.stringify(value))}}/><Button disabled={busy||active} onClick={()=>void run(async()=>{const c=await api<ChatCampaign>(`${path}/settings`,{...revision(),settings},'PUT');saveLocal(settingsKey,'');setCampaign(c);setBudgets(c.budgets);setLater(false);closePanel()})}>Сохранить настройки</Button><Button variant="ghost" onClick={connections}>Подключения и серверный ключ</Button><ThemeSelector/></>}
      {shownPanel==='compose'&&<><label htmlFor="chat-long-input">Действие или реплика</label><Textarea className="chat-document-input" id="chat-long-input" value={draft} onChange={e=>writeDraft(e.target.value)} rows={16}/><div className="actions"><Button disabled={busy||active||openingPending||!draft.trim()||!budgets?.reply.fits||budgets.unfinished} onClick={()=>void run(async()=>{await generate();closePanel()})}><Send size={18}/>Отправить</Button><Button variant="outline" onClick={()=>closePanel()}>Вернуться в чат</Button></div>{budgets&&!budgets.reply.fits&&<p role="alert">Ввод не помещается в контекст. Черновик сохранён; сократите его или обновите выжимку.</p>}</>}
      {shownPanel==='edit'&&editing&&<><label htmlFor="chat-edit-text">Новый текст</label><Textarea className="chat-document-input" id="chat-edit-text" rows={14} value={editText} onChange={e=>{setEditText(e.target.value);saveLocal(editKey(editing.id),e.target.value)}}/><p className="muted small">Правка сохраняется на этом устройстве до подтверждения.</p><Button disabled={busy||active||!editText.trim()} onClick={()=>void run(async()=>{const c=await api<ChatCampaign>(`${path}/edit`,{...revision(),branch:campaign!.active_branch,message:editing.id,text:editText});forgetLocal(editKey(editing.id));setCampaign(c);setJob(c.job);setBudgets(c.budgets);setArchive(null);await loadPage(selected,null,c.active_branch);closePanel()})}>Сохранить как новую ветку</Button></>}
      {shownPanel==='memory'&&campaign&&<>
        {review&&<p className="chat-notice">{review.stale?'Черновик устарел. Его можно прочитать и скопировать, но нельзя применить к изменившейся истории.':`Покрывает сообщения до № ${review.cutoff}. Глава изменится только после подтверждения.`} Статус: {statusText[review.status]||review.status}.</p>}
        <SectionTabs label="Разделы выжимки" className="chat-memory-tabs" tablist panelId="chat-memory-panel" value={memoryTab} items={[{id:'read',label:'Просмотр'},{id:'edit',label:'Правка'},{id:'compare',label:'Сравнение'},{id:'versions',label:'Версии'}]} onChange={value=>{setMemoryTab(value);if(value==='versions')void api<ChatMemory[]>(`${path}/versions`).then(setVersions).catch(e=>setError(e.message))}}/>
        <section id="chat-memory-panel" role="tabpanel" aria-labelledby={`chat-memory-panel-tab-${memoryTab}`}>
          {memoryTab==='read'&&<><h3>{review?'Предпросмотр черновика':'Утверждённая память'}</h3><Markdown text={review?memory:campaign.memory.text} links={false}/>{!review&&memory!==campaign.memory.text&&<p className="chat-notice">Есть несохранённые авторские правки во вкладке «Правка».</p>}<Button variant="outline" onClick={()=>setMemoryTab('edit')}>Редактировать выжимку</Button></>}
          {memoryTab==='edit'&&<><label htmlFor="chat-memory">Текст выжимки</label><Textarea className="chat-document-input" id="chat-memory" rows={20} value={memory} onChange={e=>memoryEdit(e.target.value)}/><p className="muted small">Правки сохраняются на этом устройстве. Утверждённая память изменится только после подтверждения.</p></>}
          {memoryTab==='compare'&&<><p className="muted small">Зачёркнутые строки удалены; жирные строки добавлены. Это сравнение текста, не оценка содержания.</p><div className="chat-memory-columns"><section><h3>Утверждённая память</h3><pre className="chat-diff">{oldText.split('\n').map((line,i)=><span className={!newLines.has(line)?'chat-removed':''} key={i}>{!newLines.has(line)?'− ':''}{line}{'\n'}</span>)}</pre></section><section><h3>Новая версия</h3><pre className="chat-diff">{memory.split('\n').map((line,i)=><span className={!oldLines.has(line)?'chat-added':''} key={i}>{!oldLines.has(line)?'+ ':''}{line}{'\n'}</span>)}</pre></section></div>{review&&<details><summary>Исходный ответ модели (неизменяемый)</summary><pre>{review.original}</pre></details>}</>}
          {memoryTab==='versions'&&<><h3>Версии памяти · архив</h3>{versions.map(v=><details key={v.id}><summary>{v.created_at} · до № {v.cutoff} · {v.source}</summary><Markdown text={v.text} links={false}/><Button variant="outline" onClick={()=>{memoryEdit(v.text);setMemoryTab('edit')}}>Вернуть в редактор для проверки</Button></details>)}{versions.length>=30&&<Button variant="ghost" onClick={()=>void run(async()=>{const rows=await api<ChatMemory[]>(`${path}/versions?before=${versions[versions.length-1].cursor}`);setVersions(v=>[...v,...rows]);if(!rows.length)toast.info("Это все версии")})}>Более ранние версии</Button>}</>}
        </section>
        {(memoryTab==='edit'||memoryTab==='read')&&<details><summary>Копирование, импорт и экспорт</summary><div className="actions"><Button variant="ghost" onClick={()=>void navigator.clipboard.writeText(memory).then(()=>toast.success('Выжимка скопирована')).catch(()=>toast.error('Копирование недоступно; используйте экспорт'))}>Копировать</Button><Button variant="ghost" onClick={()=>download(memory,'выжимка.md')}>Экспорт .md</Button><Button variant="ghost" onClick={()=>download(memory,'выжимка.txt')}>Экспорт .txt</Button><TextImport onText={text=>{memoryEdit(text);setMemoryTab('edit')}}/></div></details>}
        {memoryTab==='edit'&&<>
          {review&&review.status!=='complete'&&<label className="chat-check"><input type="checkbox" checked={partial} onChange={e=>setPartial(e.target.checked)}/>Я проверил и исправил неполный текст; принять его как полную выжимку</label>}
          <label className="chat-check"><input type="checkbox" checked={nextChapter} onChange={e=>setNextChapter(e.target.checked)}/>После подтверждения продолжить в следующей главе</label>
          <div className="actions"><Button disabled={busy||active||review?.stale||!memory.trim()||!!review&&review.status!=='complete'&&!partial} onClick={commitMemory}>{nextChapter?'Утвердить и продолжить':'Утвердить в этой главе'}</Button>
          {review&&<Button variant="outline" disabled={busy||active} onClick={()=>void run(async()=>{const saved=await api<ChatDraft>(`${path}/drafts/${review.id}`,{...revision(),text:memory,draft_revision:review.edit_revision},'PUT');setReview(saved);toast.success('Черновик сохранён на сервере')})}>Сохранить черновик</Button>}</div>
          {review&&<details><summary>Повторная генерация и отмена</summary><div className="actions"><Button variant="outline" disabled={busy||active} onClick={()=>summary(nextChapter)}>Сгенерировать заново (отдельный вызов)</Button><Button variant="ghost" disabled={busy||active} onClick={()=>void run(async()=>{await api(`${path}/drafts/${review.id}/cancel`,revision());await refresh();closePanel()})}>Отменить черновик</Button></div></details>}
        </>}

      </>}
      </div>
    </DialogContent></Dialog>
  </main>;
}

function TextImport({onText}:{onText:(s:string)=>void}) {
  return <label className="chat-import">Импорт .md / .txt<input type="file" accept=".md,.txt,text/plain,text/markdown" onChange={e=>{const f=e.target.files?.[0];if(!f)return;if(f.size>1000000){toast.error('Файл слишком большой (до 1 МБ)');return}void f.arrayBuffer().then(b=>onText(new TextDecoder('utf-8',{fatal:true}).decode(b))).catch(()=>toast.error('Нужен текст в UTF-8'));e.target.value=''}}/></label>;
}
