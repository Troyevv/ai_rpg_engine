import {useEffect,useRef,useState} from 'react';
import {api,download} from './api';
import {Button} from './components/ui/button';
import {Input} from './components/ui/input';
import {Textarea} from './components/ui/textarea';
import {Markdown} from './Markdown';
import {ChatSettingsEditor} from './ChatSettings';
import type {ChatCampaign,ChatCreation,ChatJob,ChatSettings,ChatSource} from './chatTypes';

const token=()=>crypto.randomUUID();
const read=(key:string)=>{try{return localStorage.getItem(key)||''}catch{return ''}};
const write=(key:string,value:string)=>{try{localStorage.setItem(key,value)}catch{/* server drafts remain available */}};
const forget=(key:string)=>{try{localStorage.removeItem(key)}catch{/* keep server state */}};
const localEdit=(id:string,fallback:string)=>{try{return localStorage.getItem(`chat-creation-edit:${id}`)??fallback}catch{return fallback}};
const savedForm=()=>{try{return JSON.parse(read('chat-create-form'))}catch{return null}};
export function ChatCreationEditor({defaults,source,onCreated,onConnections}:{defaults:{template:string;settings:ChatSettings};source?:ChatSource;onCreated:(c:ChatCampaign)=>void;onConnections:()=>void}){
  const [saved]=useState(()=>source?null:savedForm());
  const [mode,setMode]=useState<'idea'|'ready'|'source'>(source?'source':['idea','ready','source'].includes(saved?.mode)?saved.mode:'idea');
  const [d,setD]=useState<ChatCreation|null>(null);
  const [drafts,setDrafts]=useState<ChatCreation[]>([]);
  const [name,setName]=useState(saved?.name||'Новая RP-кампания');
  const [idea,setIdea]=useState(()=>saved?.idea??read('chat-create-idea'));
  const [text,setText]=useState(()=>saved?.text??read('chat-create-memory'));
  const [settings,setSettings]=useState(saved?.settings?.reply&&saved?.settings?.summary?saved.settings:defaults.settings);
  const [worlds,setWorlds]=useState<{id:number;name:string}[]>([]);
  const [world,setWorld]=useState<number|undefined>(source?.world_id||saved?.world);
  const [job,setJob]=useState<ChatJob|null>(null);
  const [partial,setPartial]=useState(false);
  const [approved,setApproved]=useState(false);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const lock=useRef(false);
  const resultRef=useRef<HTMLDivElement>(null);
  const [restoring,setRestoring]=useState(!source&&!!read('chat-create-active'));
  const creationToken=useRef(read('chat-creation-token')||token());
  const active=job?.status==='running';
  const adopt=(v:ChatCreation)=>{let form;try{form=JSON.parse(read(`chat-creation-form:${v.id}`))}catch{/* use server values */}setD(v);write('chat-create-active',v.id);setError('');setWorld(v.source?.world_id);setName(form?.name??v.name);setIdea(form?.idea??v.idea);setText(localEdit(v.id,v.text));setSettings(form?.settings?.reply&&form?.settings?.summary?form.settings:v.settings);setJob(v.jobs.at(-1)||null);setMode(v.source?'source':v.idea?'idea':'ready');setApproved(false);setPartial(false)};
  const run=async(fn:()=>Promise<void>)=>{if(lock.current)return;lock.current=true;setBusy(true);setError('');try{await fn()}catch(e){setError((e as Error).message)}finally{lock.current=false;setBusy(false)}};
  useEffect(()=>{void api<ChatCreation[]>('/chat/creations').then(setDrafts).catch(e=>setError(e.message));void api<{id:number;name:string}[]>('/worlds').then(setWorlds).catch(()=>{})},[]);
  useEffect(()=>{const id=!source&&read('chat-create-active');if(!id)return;let live=true;void api<ChatCreation>(`/chat/creations/${id}`).then(v=>{if(live){if(v.campaign_id)write('chat-create-active','');else adopt(v)}}).catch(e=>{if(live)setError(e.message)}).finally(()=>{if(live)setRestoring(false)});return()=>{live=false}},[]);
  useEffect(()=>{if(!d&&!restoring)write('chat-create-form',JSON.stringify({mode,name,idea,text,settings,world}))},[mode,name,idea,text,settings,world,d,restoring]);
  useEffect(()=>{if(d)write(`chat-creation-form:${d.id}`,JSON.stringify({name,idea,settings}))},[d?.id,name,idea,settings]);
  // Scroll only the document body: scrollIntoView also scrolls overflow-hidden
  // ancestors and can move the fixed dialog heading/close button off screen.
  const revealResult=()=>{const result=resultRef.current;const body=result?.closest<HTMLElement>('.chat-dialog-body');if(result&&body)body.scrollTop+=result.getBoundingClientRect().top-body.getBoundingClientRect().top};
  useEffect(()=>{if(job?.id)revealResult()},[job?.id]);
  useEffect(()=>{if(error)revealResult()},[error]);
  useEffect(()=>{
    if(!d||!job||job.status!=='running')return;
    const events=new EventSource(`/api/chat/creations/${d.id}/jobs/${job.id}/events`);
    events.addEventListener('snapshot',((e:MessageEvent)=>{
      const j=JSON.parse(e.data) as ChatJob;setText(j.response);forget(`chat-creation-edit:${d.id}`);
      // Keep editors locked until the final snapshot is applied, so a late GET cannot overwrite new edits.
      if(j.status==='running')setJob(j);
      else{events.close();void api<ChatCreation>(`/chat/creations/${d.id}`).then(adopt).catch(e=>{setJob(j);setError(e.message)})}
    }) as EventListener);
    events.onerror=()=>setError('Переподключаемся к сохранённому запросу. Нового LLM-вызова нет.');
    return()=>events.close();
  },[d?.id,job?.id,job?.status]);
  const sourceValue=mode==='source'?(source||{world_id:world}):null;
  const save=async()=>{
    const payload={token:d?token():creationToken.current,name,idea:mode==='idea'?idea:'',text,settings,source:sourceValue};
    if(!d)write('chat-creation-token',creationToken.current);
    const next=await api<ChatCreation>(d?`/chat/creations/${d.id}`:'/chat/creations',d?{...payload,revision:d.revision}:payload,d?'PUT':'POST');
    setD(next);write('chat-create-active',next.id);write('chat-creation-token','');forget(`chat-creation-edit:${next.id}`);return next;
  };
  const generate=(kind:'initial'|'continue')=>void run(async()=>{
    const next=await save();setApproved(false);setPartial(false);
    const j=await api<ChatJob>(`/chat/creations/${next.id}/generate`,{token:token(),revision:next.revision,kind});
    setJob(j);setText(j.response);setD(await api<ChatCreation>(`/chat/creations/${next.id}`));
  });
  const edit=(v:string)=>{setText(v);setApproved(false);write(d?`chat-creation-edit:${d.id}`:'chat-create-memory',v)};
  const reset=(next:'idea'|'ready'|'source')=>{write('chat-create-active','');setD(null);setJob(null);setMode(next);setApproved(false);setPartial(false);creationToken.current=token();setText('');setError('')};
  if(restoring)return <p role="status">Восстанавливаем черновик создания…</p>;
  return <section className="chat-creation">
    {!d&&<><div className="chat-creation-methods" aria-label="Способ создания кампании">{(['idea','ready','source'] as const).map((m,i)=><Button key={m} aria-pressed={mode===m} disabled={active||busy} variant={mode===m?'default':'outline'} onClick={()=>{if(m!==mode)reset(m)}}>{['Создать по идее','Использовать готовую выжимку','Импортировать существующий мир'][i]}</Button>)}</div>
    {drafts.length>0&&<details><summary>Сохранённые черновики создания</summary>{drafts.map(x=><Button key={x.id} disabled={active||busy} variant="ghost" onClick={()=>void run(async()=>adopt(await api(`/chat/creations/${x.id}`)))}>{x.name} · {x.status}</Button>)}</details>}</>}
    <details className="chat-creation-setup" open={!job}><summary>Идея и параметры кампании</summary><div className="chat-form-stack">
    <label>Название кампании<Input value={name} disabled={active||busy} onChange={e=>setName(e.target.value)}/></label>
    {mode==='idea'&&<><label>Идея игры<Textarea rows={6} disabled={active||busy} placeholder="Мир, персонажи, жанр, обстоятельства и сюжетные предпосылки…" value={idea} onChange={e=>{setIdea(e.target.value);write('chat-create-idea',e.target.value)}}/></label><p className="muted">Один отдельный вызов создаст полный авторский документ. Кампания появится только после вашей проверки и подтверждения.</p></>}
    {mode==='source'&&<div className="chat-notice"><p>Отдельная копия исходного мира или принятого состояния Narrative. Оригинал не изменится.</p>{!source&&!d?.source?.save_id&&<label>Исходный мир<select disabled={!!d||active||busy} value={world||''} onChange={e=>setWorld(Number(e.target.value))}><option value="">Выберите мир</option>{worlds.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select></label>}<Button disabled={active||busy||(!source&&!world)||!!d} onClick={()=>void run(async()=>{const next=await save();adopt(next)})}>Подготовить снимок бесплатно</Button>{d&&<span>Снимок подготовлен</span>}</div>}
    <fieldset className="chat-creation-settings" disabled={active||busy}><ChatSettingsEditor value={settings} onChange={setSettings}/></fieldset>
    <Button variant="ghost" onClick={onConnections}>Подключения и серверный ключ</Button>
    {mode==='idea'&&!job&&<Button disabled={active||busy||!idea.trim()} onClick={()=>generate('initial')}>Сгенерировать первоначальную выжимку</Button>}
    </div></details>
    <div ref={resultRef} className="chat-creation-result">
    {active&&<Button disabled={busy} variant="outline" onClick={()=>void run(async()=>{setJob(await api(`/chat/creations/${d!.id}/jobs/${job!.id}/stop`,{}));adopt(await api(`/chat/creations/${d!.id}`))})}>Остановить генерацию выжимки</Button>}
    {job&&<div className="chat-receipt" role="status"><p>{active?'Выжимка поступает…':job.status==='complete'?'Выжимка сохранена. Проверьте весь документ.':'Ответ неполный. Исправьте его, запросите продолжение или повторите генерацию.'}</p>{job.error&&<p>{job.error}</p>}{job.usage.map((u,i)=><p key={i}>input {u.input_tokens??'неизвестно'}, output {u.output_tokens??'неизвестно'} · {u.cost_usd===null?'Стоимость неизвестна':`Стоимость по ставкам: ≈ $${u.cost_usd}`}</p>)}</div>}
    {(mode!=='idea'||job||text)&&<><h3>Проверка первоначальной выжимки</h3><p className="muted">Авторский документ может содержать спойлеры. Измените любые сведения перед началом игры.</p>
    {active&&<div className="chat-initial-stream" aria-label="Поступающая выжимка"><Markdown text={text} links={false} streaming liveMarkdown/></div>}
    <div hidden={active}><label htmlFor="chat-initial-memory">Стартовая выжимка</label><Textarea className="chat-document-input" id="chat-initial-memory" rows={16} disabled={active||busy} value={text} onChange={e=>edit(e.target.value)}/></div>
    <div className="actions"><Button disabled={active||busy} variant="ghost" onClick={()=>edit(defaults.template)}>Полный шаблон</Button><label className="chat-import">Импорт Markdown<input aria-label="Импорт первоначальной выжимки" type="file" accept=".md,.txt,text/plain,text/markdown" disabled={active||busy} onChange={async e=>{const f=e.target.files?.[0];if(f){if(f.size>500000){setError('Файл слишком большой.');return}edit(await f.text())}e.target.value=''}}/></label><Button variant="ghost" onClick={()=>download(text,'initial-memory.md')}>Экспорт Markdown</Button></div>
    <details><summary>Предпросмотр Markdown</summary><Markdown text={text} links={false}/></details>
    {d&&d.jobs.length>1&&<details><summary>Предыдущие варианты и расход</summary>{d.jobs.map(j=><div key={j.id}><p>{j.kind} · {j.status} · {j.usage.map(u=>`input ${u.input_tokens??'?'} / output ${u.output_tokens??'?'}`).join(', ')}</p><Button disabled={active||busy} variant="ghost" onClick={()=>edit(j.response)}>Открыть этот вариант в редакторе</Button></div>)}</details>}
    {job&&!active&&job.status!=='complete'&&<><Button disabled={busy||!text.trim()} onClick={()=>generate('continue')}>Продолжить неполную выжимку (новый вызов)</Button><label className="chat-check"><input type="checkbox" disabled={active||busy} checked={partial} onChange={e=>setPartial(e.target.checked)}/> Я исправил и проверил неполный документ, принимаю его явно</label></>}
    <Button variant="outline" disabled={busy||active} onClick={()=>void run(async()=>{await save()})}>Сохранить черновик создания</Button>
    {mode==='idea'&&job&&<Button variant="outline" disabled={active||busy||!idea.trim()} onClick={()=>generate('initial')}>Сгенерировать заново</Button>}
    <label className="chat-check"><input type="checkbox" checked={approved} disabled={active||busy} onChange={e=>setApproved(e.target.checked)}/> Подтверждаю первоначальную выжимку</label>
    <Button disabled={busy||active||!approved||!text.trim()||!!job&&job.status!=='complete'&&!partial||mode==='source'&&!d} onClick={()=>void run(async()=>{
      const next=await save();const c=await api<ChatCampaign>(`/chat/creations/${next.id}/confirm`,{revision:next.revision,token:token(),accept_partial:partial});
      write('chat-create-memory','');write('chat-create-idea','');write('chat-create-form','');write('chat-create-active','');onCreated(c);
    })}>Начать игру</Button></>}
    {d&&<Button disabled={busy} variant="ghost" onClick={()=>void run(async()=>{const next=await api<ChatCreation>(`/chat/creations/${d.id}`);if(next.campaign_id)onCreated(await api(`/chat/campaigns/${next.campaign_id}`));else adopt(next)})}>Восстановить сохранённое состояние</Button>}
    {d&&<Button disabled={active||busy} variant="ghost" onClick={()=>reset(mode)}>Другой черновик</Button>}
    {error&&<p className="chat-error" role="alert">{error}</p>}
    </div>
  </section>;
}
