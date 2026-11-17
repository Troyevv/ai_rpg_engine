import {useCallback,useEffect,useRef,useState} from 'react';
import {ArrowLeft,BookOpen,Send,Square,Plus,Settings2,FileText,GitBranch} from 'lucide-react';
import {toast} from 'sonner';
import {api,download} from './api';
import {Button} from './components/ui/button';
import {Textarea} from './components/ui/textarea';
import {Input} from './components/ui/input';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './components/ui/dialog';
import {Markdown} from './Markdown';
import {ThemeSelector} from './ThemeProvider';
import {ChatCreationEditor} from './ChatCreation';
import {ChatSettingsEditor} from './ChatSettings';
import {useChatScroll} from './useChatScroll';
import type {ChatCampaign,ChatDraft,ChatJob,ChatMemory,ChatMessage,ChatSettings,ChatSource,Budgets} from './chatTypes';
import './styles/chat.css';

const token=()=>crypto.randomUUID();
const prefix='/chat/campaigns';
const readLocal=(key:string,fallback='')=>{try{return localStorage.getItem(key)||fallback}catch{return fallback}};
const saveLocal=(key:string,value:string)=>{try{localStorage.setItem(key,value)}catch{/* server-saved messages remain authoritative */}};
const statusText:Record<string,string>={running:'Ответ поступает…',complete:'Сохранено',stopped:'Остановлено · неполный текст',length:'Лимит ответа · неполный текст',error:'Ошибка · исход расхода может быть неизвестен',empty:'Пустой ответ',interrupted:'Прервано · повтор только вручную'};

type Panel='library'|'create'|'chapters'|'memory'|'settings'|'edit'|'request'|null;
export function ChatMode({onBack,onConnections,source}:{onBack:()=>void;onConnections:()=>void;source?:ChatSource}) {
  const [campaign,setCampaignState]=useState<ChatCampaign|null>(null);
  const campaignRef=useRef<ChatCampaign|null>(null);
  const pageEpoch=useRef(0);
  const [selected,setSelected]=useState(()=>readLocal('chat-selection'));
  const selectedRef=useRef(selected);selectedRef.current=selected;
  const [list,setList]=useState<{id:string;name:string;mode:string}[]>([]);
  const [panel,setPanel]=useState<Panel>(source?'create':selected?null:'library');
  const [defaults,setDefaults]=useState<{template:string;settings:ChatSettings}|null>(null);
  const [settings,setSettings]=useState<ChatSettings|null>(null);
  const [sourceSpec,setSourceSpec]=useState(source);
  const [draft,setDraft]=useState('');
  const [pending,setPending]=useState(false);
  const [busy,setBusy]=useState(false);
  const busyRef=useRef(false);
  const [error,setError]=useState('');
  const [messages,setMessages]=useState<ChatMessage[]>([]);
  const [more,setMore]=useState(false);
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
  const {viewport,content,sticky}=useChatScroll(`${selected}:${campaign?.active_branch}:${archive||''}`);
  const setCampaign=(next:ChatCampaign|null)=>{
    if(next&&(next.id!==selectedRef.current||(campaignRef.current?.id===next.id&&campaignRef.current.revision>next.revision)))return false;
    campaignRef.current=next;setCampaignState(next);return true;
  };
  const active=job?.status==='running';
  const path=`${prefix}/${selected}`;
  const revision=()=>({revision:campaign!.revision,token:token()});
  const panelRef=useRef(panel);panelRef.current=panel;
  const triggerRef=useRef<HTMLElement|null>(null);
  const openPanel=(value:Panel)=>{triggerRef.current=document.activeElement as HTMLElement;setPanel(value)};
  // Native Back closes an editor before leaving the campaign. Radix owns focus/Escape.
  useEffect(()=>{
    if(!panel)return;
    if(!history.state?.chatPanel)history.pushState({...history.state,chatPanel:true},'');
    const back=()=>{setPanel(null);triggerRef.current?.focus()};
    window.addEventListener('popstate',back);
    return()=>window.removeEventListener('popstate',back);
  },[!!panel]);
  const closePanel=()=>{setPanel(null);if(history.state?.chatPanel)history.back();triggerRef.current?.focus()};
  const run=async(fn:()=>Promise<void>)=>{
    if(busyRef.current)return;
    busyRef.current=true;setBusy(true);setError('');
    try{await fn()}catch(e){setError((e as Error).message);toast.error((e as Error).message)}
    finally{busyRef.current=false;setBusy(false)}
  };
  const loadPage=useCallback(async(cid:string,chapter:string|null,branch?:string)=>{
    const epoch=++pageEpoch.current;
    const query=new URLSearchParams();if(chapter)query.set('chapter',chapter);if(branch)query.set('branch',branch);
    const p=await api<{messages:ChatMessage[];more:boolean}>(`${prefix}/${cid}/messages?${query}`);
    if(selectedRef.current===cid&&pageEpoch.current===epoch){setMessages(p.messages);setMore(p.more)}
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
    saveLocal('chat-selection',selected);setCampaign(null);setMessages([]);setArchive(null);setJob(null);setLater(false);setError('');
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
      const j=JSON.parse(event.data) as ChatJob;setJob(j);
      if(j.kind!=='summary'&&!archive)setMessages(previous=>previous.map(m=>m.id===j.output_id?{...m,content:j.response,status:j.status}:m));
      if(j.status!=='running'){
        events.close();void refresh().then(c=>loadPage(c.id,archive,c.active_branch)).catch(e=>setError(e.message));
        if(j.kind==='summary')void api<ChatDraft>(`${path}/drafts/${j.output_id}`).then(d=>{setReview(d);setMemory(d.text);setNextChapter(!!d.next_chapter);setPartial(false);openPanel('memory')}).catch(e=>setError(e.message));
      }
    };
    events.addEventListener('snapshot',snapshot as EventListener);
    events.onerror=()=>setError('Поток отключён. Переподключаемся к сохранённому запросу; новая генерация не запускается.');
    return()=>events.close();
  },[selected,job?.id,job?.status,archive,refresh,loadPage]);
  const choose=(id:string)=>{setSelected(id);if(id===selected)void refresh();closePanel()};
  const writeDraft=(text:string)=>{setBudgets(null);setDraft(text);saveLocal(`chat-input:${selected}:${campaign!.active_branch}`,text);setLater(false)};
  const openMemory=()=>{setReview(null);setMemory(readLocal(`chat-memory:${selected}:${campaign!.memory.id}`,campaign!.memory.text));setPartial(false);setNextChapter(false);openPanel('memory');void api<ChatMemory[]>(`${path}/versions`).then(setVersions).catch(e=>setError(e.message))};
  const generate=async(kind='reply',target?:string,next=false)=>{
    const request={...revision(),kind,text:kind==='reply'?draft:'',target:target||null,next_chapter:next};
    if(kind==='reply'){saveLocal(`chat-pending:${selected}`,JSON.stringify(request));setPending(true)}
    const j=await api<ChatJob>(`${path}/generate`,request);setJob(j);setPending(false);saveLocal(`chat-pending:${selected}`,'');
    if(kind==='reply')writeDraft('');
    const c=await refresh();await loadPage(c.id,null,c.active_branch);setArchive(null);
    if(c.job?.kind==='summary'&&c.job.status!=='running'){const d=await api<ChatDraft>(`${path}/drafts/${c.job.output_id}`);setReview(d);setMemory(d.text);setNextChapter(!!d.next_chapter);setPartial(false);openPanel('memory')}
  };
  const summary=(next:boolean)=>void run(async()=>{setNextChapter(next);await generate('summary',undefined,next)});
  const changeChapter=(id:string|null)=>void run(async()=>{await loadPage(selected,id,campaign!.active_branch);setArchive(id);closePanel()});
  const changeBranch=(id:string)=>void run(async()=>{
    const c=await api<ChatCampaign>(`${path}/select`,{...revision(),branch:id});setCampaign(c);setJob(c.job);setBudgets(c.budgets);setArchive(null);setLater(false);await loadPage(c.id,null,c.active_branch);closePanel();
  });
  const commitMemory=()=>void run(async()=>{
    let id=review?.id;
    let rev=campaign!.revision;
    if(!id){const result=await api<{draft:string}>(`${path}/memory`,{...revision(),text:memory});id=result.draft;const c=await refresh();rev=c.revision;const d=await api<ChatDraft>(`${path}/drafts/${id}`);setReview(d)}
    const c=await api<ChatCampaign>(`${path}/drafts/${id}/confirm`,{revision:rev,token:token(),text:memory,next_chapter:nextChapter,accept_partial:partial,draft_revision:review?.edit_revision||0});
    saveLocal(`chat-memory:${selected}:${campaign!.memory.id}`,'');saveLocal(`chat-review:${id}`,'');setCampaign(c);setBudgets(c.budgets);setArchive(null);setLater(false);await loadPage(selected,null,c.active_branch);closePanel();
  });
  const loadReview=(id:string)=>void run(async()=>{
    const d=await api<ChatDraft>(`${path}/drafts/${id}`);setReview(d);setMemory(readLocal(`chat-review:${id}`,d.text));setNextChapter(!!d.next_chapter);setPartial(false);openPanel('memory');
  });
  const memoryEdit=(text:string)=>{setMemory(text);saveLocal(review?`chat-review:${review.id}`:`chat-memory:${selected}:${campaign!.memory.id}`,text)};
  const oldText=review?.previous||campaign?.memory.text||'';
  const oldLines=new Set(oldText.split('\n')),newLines=new Set(memory.split('\n'));
  return <main className="chat-mode" aria-label="RP-чат">
    <header className="chat-header">
      <Button variant="ghost" size="icon" aria-label="Вернуться в Narrative" onClick={onBack}><ArrowLeft size={20}/></Button>
      <div className="chat-heading"><span className="eyebrow">CHAT MODE · RP-ЧАТ</span><h1>{campaign?.name||'Твои RP-истории'}</h1><span className="muted small">{campaign?`${campaign.chapters.find(c=>c.id===(archive||campaign.branch.chapter_id))?.name||'Глава'} · ${archive?'архив, только чтение':'активное продолжение'}`:'Одна кампания, сколько угодно глав в пределах хранилища'}</span></div>
      <Button variant="ghost" aria-label="Кампании RP-чата" onClick={()=>openPanel('library')}><BookOpen size={18}/><span className="chat-desktop">Кампании</span></Button>
      <Button variant="ghost" aria-label="Настройки RP-чата" disabled={!campaign} onClick={()=>{setSettings(campaign!.settings);openPanel('settings')}}><Settings2 size={18}/></Button>
    </header>
    {campaign?<>
      <nav className="chat-toolbar" aria-label="Кампания"><Button variant="outline" onClick={()=>openPanel('chapters')}><GitBranch size={16}/>Главы и ветки</Button><Button variant="outline" onClick={openMemory}><FileText size={16}/>Выжимка</Button><Button disabled={busy||active} variant="ghost" onClick={()=>summary(false)}>Обновить выжимку</Button><Button disabled={busy||active} onClick={()=>summary(true)}>Обновить выжимку и продолжить</Button></nav>
      {error&&<div className="chat-notice" role="alert">{error}<Button variant="ghost" onClick={()=>void run(async()=>{const c=await refresh();await loadPage(c.id,archive,c.active_branch)})}>Обновить состояние</Button></div>}
      {budgets&&<div className="chat-budget"><span>Контекст ≈ {budgets.reply.estimated_tokens.toLocaleString()} / {budgets.reply.available.toLocaleString()} входных токенов</span><meter aria-label="Оценка контекста" min={0} max={1} value={Math.min(budgets.reply.ratio,1)}/><details><summary>Оценка и резервы</summary><p>{budgets.reply.token_method||'Консервативная оценка UTF-8'}. Окно: {budgets.reply.context_length}. Ответ: {budgets.reply.output}. Запас: {budgets.reply.margin}. Суммаризация: ≈ {budgets.summary.estimated_tokens} / {budgets.summary.available}, резерв выжимки {budgets.summary.output}, следующего RP-ответа {budgets.summary.next_reply_reserve||0}. Точный usage — в завершённых запросах.</p></details></div>}
      {budgets?.warning&&(!later||!budgets.reply.fits)&&<div className="chat-notice" role="status"><p>{budgets.reply.fits?'Контекст почти заполнен.':'Ввод не помещается в контекст.'} Обновите выжимку и начните следующую главу. Переписка останется в кампании.{!budgets.summary.fits?' Суммаризация тоже не помещается: отредактируйте память или настройте большее совместимое окно.':''}</p><Button disabled={busy||active||!budgets.summary.fits} onClick={()=>summary(true)}>Обновить и продолжить</Button>{budgets.reply.fits&&<Button variant="ghost" onClick={()=>setLater(true)}>Позже</Button>}<Button variant="ghost" onClick={openMemory}>Редактор памяти</Button></div>}
      {campaign.drafts.filter(d=>d.status!=='running').length>0&&<div className="chat-draft-links">{campaign.drafts.filter(d=>d.status!=='running').map(d=><Button key={d.id} size="sm" variant="ghost" onClick={()=>loadReview(d.id)}>Черновик выжимки{d.source_revision!==campaign.revision?' · устарел':''}</Button>)}</div>}
      {archive&&<div className="chat-notice">Архив: просмотр не меняет контекст. Редактирование создаст отдельную ветку.<Button onClick={()=>changeChapter(null)}>К активной главе</Button></div>}
      <div className="chat-scroll" ref={viewport} tabIndex={0} aria-label="Переписка"><div className="chat-column" ref={content}>
        {more&&<Button variant="ghost" disabled={busy} onClick={()=>void run(async()=>{
          const el=viewport.current;const height=el?.scrollHeight||0;sticky.current=false;
          const q=new URLSearchParams({before:String(messages[0].seq),branch:campaign.active_branch});if(archive)q.set('chapter',archive);
          const p=await api<{messages:ChatMessage[];more:boolean}>(`${path}/messages?${q}`);setMessages(m=>[...p.messages,...m]);setMore(p.more);
          requestAnimationFrame(()=>{if(el)el.scrollTop+=el.scrollHeight-height});
        })}>Ранее в истории</Button>}
        {!messages.length&&<div className="chat-empty"><FileText size={28}/><h2>{archive?'В этой главе пока нет сообщений':'Продолжим историю'}</h2><p>{campaign.branch.head?'Сцена и выжимка перенесены. Следующий ввод продолжит её без повторения последнего действия.':'Опишите действие, реплику или начальную сцену. Неизвестные поля выжимки можно оставить пустыми.'}</p></div>}
        {messages.map(m=><article className={`chat-message chat-${m.role}`} key={m.id} data-message-id={m.id}><header><strong>{m.role==='user'?'Ты':'История'}</strong><span>{statusText[m.status]||m.status}</span></header><Markdown text={m.content} links={false} streaming={m.status==='running'}/><footer><Button size="sm" variant="ghost" disabled={active||busy} onClick={()=>{setEditing(m);setEditText(m.content);openPanel('edit')}}>Редактировать</Button>{m.role==='assistant'&&m.job_id&&<Button size="sm" variant="ghost" disabled={active||busy} onClick={()=>void run(()=>generate('regenerate',m.id))}>Перегенерировать</Button>}{m.job_id&&<Button size="sm" variant="ghost" onClick={()=>void run(async()=>{const details=await api<Record<string,unknown>[]>(`${path}/jobs/${m.job_id}/requests`);setRequestDetails(details);openPanel('request')})}>Запрос и расход</Button>}</footer></article>)}
        {job&&<div className="chat-receipt"><span role="status">{statusText[job.status]||job.status}{job.kind==='summary'?' · обновление выжимки':''}</span>{job.error&&<p>{job.error}</p>}
          {job.usage.map((u,i)=><p key={i}>{u.stage} · {u.provider}/{u.model} · input {u.input_tokens??'неизвестно'}, output {u.output_tokens??'неизвестно'} · {u.cost_usd===null?'Стоимость неизвестна':`Стоимость по ставкам: ≈ $${u.cost_usd}`}</p>)}
          {job.status!=='running'&&job.status!=='complete'&&job.kind!=='summary'&&<Button disabled={busy} variant="outline" onClick={()=>void run(()=>generate('retry',job.id))}>Повторить явно (новый вызов)</Button>}
        </div>}
      </div></div>
      {!archive&&campaign.opening_required&&!campaign.branch.head&&<Button disabled={busy} onClick={()=>void run(()=>generate('start'))}>Начать игру</Button>}
      {!archive&&<form className="chat-composer" onSubmit={e=>{e.preventDefault();void run(()=>generate())}}><label className="sr-only" htmlFor="chat-input">Твоё сообщение</label><Textarea id="chat-input" disabled={!!campaign.opening_required&&(campaign.branch.head===0||!!budgets?.unfinished)} placeholder="Действие или реплика…" rows={3} value={draft} onChange={e=>writeDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();if(!active&&!busy&&!budgets?.unfinished&&(!campaign.opening_required||campaign.branch.head>0)&&budgets?.reply.fits)void run(()=>generate())}}}/><div><span className="muted small">Ctrl/⌘ + Enter · ввод сохраняется на этом устройстве</span>{active?<Button type="button" variant="outline" onClick={()=>void run(async()=>{setJob(await api(`${path}/jobs/${job.id}/stop`,{}));await refresh();await loadPage(selected,null,campaign.active_branch)})}><Square size={16}/>Остановить</Button>:<Button type="submit" disabled={busy||!!campaign.opening_required&&!campaign.branch.head||!draft.trim()||!budgets?.reply.fits||budgets.unfinished}><Send size={16}/>Отправить</Button>}</div>
        {pending&&<Button type="button" variant="ghost" onClick={()=>void run(async()=>{const payload=JSON.parse(readLocal(`chat-pending:${selected}`));await api(`${path}/generate`,payload);saveLocal(`chat-pending:${selected}`,'');setPending(false);writeDraft('');const c=await refresh();await loadPage(selected,null,c.active_branch)})}>Проверить отправку без повторного вызова</Button>}
        {budgets?.unfinished&&<p className="small">Примите частичный ответ через «Редактировать» или повторите его явно.</p>}
      </form>}
    </>:<section className="chat-welcome"><h2>История продолжается</h2><p>RP-чат хранит переписку, главы и авторскую память. Вы решаете, когда обновить выжимку и продолжить.</p><Button onClick={()=>{setSettings(defaults?.settings||null);openPanel('create')}}><Plus size={18}/>Новая RP-кампания</Button><Button variant="outline" onClick={()=>openPanel('library')}>Открыть кампанию</Button>{error&&<p role="alert">{error}</p>}</section>}
    <Dialog open={!!panel} onOpenChange={open=>{if(!open)closePanel()}}><DialogContent className={`chat-dialog ${panel==='memory'?'chat-memory-dialog':''}`}><DialogHeader><DialogTitle>{{library:'RP-кампании',create:'Новая история · Chat Mode',chapters:'Главы и варианты истории',memory:review?'Проверка новой выжимки':'Авторская выжимка',settings:'Настройки RP-чата',edit:'Редактировать сообщение',request:'Записанный запрос и расход'}[panel||'library']}</DialogTitle><DialogDescription>{panel==='memory'?'Авторский документ может содержать спойлеры. Просмотр тайны не передаёт её знания главному герою.':panel==='edit'?'Изменение создаст новую ветку без прежнего продолжения. Исходный текст и поздние главы сохранятся.':'Chat Mode хранится отдельно от Narrative. Режим существующего прохождения не меняется.'}</DialogDescription></DialogHeader>
      <div className="chat-dialog-body">
      {error&&<p className="chat-error" role="alert">{error}</p>}
      {panel==='library'&&<><Button onClick={()=>{setSourceSpec(undefined);setSettings(defaults!.settings);setPanel('create')}}><Plus size={16}/>Новая RP-кампания</Button>{!list.length&&<p>Пока нет кампаний.</p>}{list.map(c=><button className="chat-campaign-card" key={c.id} disabled={busy} onClick={()=>choose(c.id)}><strong>{c.name}</strong><span>RP-чат · продолжить →</span></button>)}</>}
      {panel==='create'&&defaults&&<ChatCreationEditor defaults={defaults} source={sourceSpec} onConnections={onConnections} onCreated={c=>{setSelected(c.id);closePanel()}}/>}
      {panel==='chapters'&&campaign&&<><h3>Главы активной ветки</h3>{campaign.chapters.map(c=><button className="chat-campaign-card" key={c.id} onClick={()=>changeChapter(c.id===campaign.branch.chapter_id?null:c.id)}><strong>{c.name}</strong><span>{c.id===campaign.branch.chapter_id?'Активная':'Архив · читать'}</span></button>)}<h3>Сохранённые ветки / варианты</h3><p>Выбор ветки меняет продолжение кампании. Просмотр главы выше — только чтение.</p>{campaign.branches.map(b=><Button key={b.id} disabled={active||busy||b.id===campaign.active_branch} variant="outline" onClick={()=>changeBranch(b.id)}>{b.name} · {b.head} сообщений{b.id===campaign.active_branch?' · активна':''}</Button>)}{campaign.source!=null&&<details><summary>Происхождение исходной копии</summary><pre>{JSON.stringify(campaign.source,null,2)}</pre></details>}</>}
      {panel==='request'&&<><p>Авторская диагностика: фактический usage хранится отдельно от оценки. Стоимость рассчитана по сохранённым ставкам; неизвестные значения не считаются нулём. Контекст содержит только эту точку истории.</p>{requestDetails.map((receipt,i)=><pre key={i}>{JSON.stringify(receipt,null,2)}</pre>)}</>}
      {panel==='settings'&&settings&&<><ChatSettingsEditor value={settings} onChange={setSettings}/><Button disabled={busy||active} onClick={()=>void run(async()=>{const c=await api<ChatCampaign>(`${path}/settings`,{...revision(),settings},'PUT');setCampaign(c);setBudgets(c.budgets);setLater(false);closePanel()})}>Сохранить настройки</Button><Button variant="ghost" onClick={onConnections}>Подключения и серверный ключ</Button><ThemeSelector/></>}
      {panel==='edit'&&editing&&<><label htmlFor="chat-edit-text">Новый текст</label><Textarea id="chat-edit-text" rows={14} value={editText} onChange={e=>setEditText(e.target.value)}/><Button disabled={busy||active||!editText.trim()} onClick={()=>void run(async()=>{const c=await api<ChatCampaign>(`${path}/edit`,{...revision(),branch:campaign!.active_branch,message:editing.id,text:editText});setCampaign(c);setJob(c.job);setBudgets(c.budgets);setArchive(null);await loadPage(selected,null,c.active_branch);closePanel()})}>Сохранить как новую ветку</Button></>}
      {panel==='memory'&&campaign&&<>
        {review&&<p className="chat-notice">{review.stale?'Черновик устарел. Его можно прочитать и скопировать, но нельзя применить к изменившейся истории.':`Покрывает сообщения до № ${review.cutoff}. Глава изменится только после подтверждения.`} Статус: {statusText[review.status]||review.status}.</p>}
        <div className="chat-memory-columns"><section><h3>Утверждённая память</h3><pre className="chat-diff">{oldText.split('\n').map((line,i)=><span className={!newLines.has(line)?'chat-removed':''} key={i}>{!newLines.has(line)?'− ':''}{line}{'\n'}</span>)}</pre></section><section><h3>{review?'Новый черновик':'Новая авторская версия'}</h3><label className="sr-only" htmlFor="chat-memory">Текст выжимки</label><Textarea id="chat-memory" rows={20} value={memory} onChange={e=>memoryEdit(e.target.value)}/></section></div>
        <details><summary>Добавленные / изменённые строки и предпросмотр</summary><pre className="chat-diff">{memory.split('\n').filter(line=>!oldLines.has(line)).map((line,i)=><span className="chat-added" key={i}>+ {line}{'\n'}</span>)}</pre><Markdown text={memory} links={false}/></details>
        {review&&<details><summary>Исходный ответ модели (неизменяемый)</summary><pre>{review.original}</pre></details>}
        <div className="actions"><Button variant="ghost" onClick={()=>void navigator.clipboard.writeText(memory).then(()=>toast.success('Выжимка скопирована')).catch(()=>toast.error('Копирование недоступно; используйте экспорт'))}>Копировать</Button><Button variant="ghost" onClick={()=>download(memory,'выжимка.md')}>Экспорт .md</Button><Button variant="ghost" onClick={()=>download(memory,'выжимка.txt')}>Экспорт .txt</Button><TextImport onText={memoryEdit}/></div>
        {review&&review.status!=='complete'&&<label className="chat-check"><input type="checkbox" checked={partial} onChange={e=>setPartial(e.target.checked)}/>Я проверил и исправил неполный текст; принять его как полную выжимку</label>}
        <label className="chat-check"><input type="checkbox" checked={nextChapter} onChange={e=>setNextChapter(e.target.checked)}/>После подтверждения продолжить в следующей главе</label>
        <div className="actions"><Button disabled={busy||active||review?.stale||!memory.trim()||!!review&&review.status!=='complete'&&!partial} onClick={commitMemory}>{nextChapter?'Утвердить и продолжить':'Утвердить в этой главе'}</Button>
        {review&&<Button variant="outline" disabled={busy||active} onClick={()=>void run(async()=>{const saved=await api<ChatDraft>(`${path}/drafts/${review.id}`,{...revision(),text:memory,draft_revision:review.edit_revision},'PUT');setReview(saved);toast.success('Черновик сохранён на сервере')})}>Сохранить черновик</Button>}
        <Button variant="ghost" disabled={busy||active} onClick={()=>summary(nextChapter)}>Сгенерировать заново (отдельный вызов)</Button>
        {review&&<Button variant="ghost" disabled={busy||active} onClick={()=>void run(async()=>{await api(`${path}/drafts/${review.id}/cancel`,revision());await refresh();closePanel()})}>Отменить черновик</Button>}</div>
        <details onToggle={e=>{if(e.currentTarget.open&&!versions.length)void api<ChatMemory[]>(`${path}/versions`).then(setVersions)}}><summary>Версии памяти · архив</summary>{versions.map(v=><details key={v.id}><summary>{v.created_at} · до № {v.cutoff} · {v.source}</summary><Markdown text={v.text} links={false}/><Button variant="ghost" onClick={()=>memoryEdit(v.text)}>Вернуть в редактор для проверки</Button></details>)}{versions.length>=30&&<Button variant="ghost" onClick={()=>void run(async()=>{const rows=await api<ChatMemory[]>(`${path}/versions?before=${versions[versions.length-1].cursor}`);setVersions(v=>[...v,...rows]);if(!rows.length)toast.info("Это все версии")})}>Более ранние версии</Button>}</details>
      </>}
      </div>
    </DialogContent></Dialog>
  </main>;
}

function TextImport({onText}:{onText:(s:string)=>void}) {
  return <label className="chat-import">Импорт .md / .txt<input type="file" accept=".md,.txt,text/plain,text/markdown" onChange={e=>{const f=e.target.files?.[0];if(!f)return;if(f.size>1000000){toast.error('Файл слишком большой (до 1 МБ)');return}void f.arrayBuffer().then(b=>onText(new TextDecoder('utf-8',{fatal:true}).decode(b))).catch(()=>toast.error('Нужен текст в UTF-8'));e.target.value=''}}/></label>;
}
