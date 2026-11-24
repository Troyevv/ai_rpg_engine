import {SkinStamp} from './ThemeProvider';
import {choiceText, NarrativeChoiceCard} from './NarrativeChoice';
import {ActionPanel} from './components/ui/action-panel';
import { Choice } from "@/components/ui/choice";
import {StoryNotifications} from './StoryNotifications';
import type {StoryNotice} from './types';
import {NpcReview} from './NpcReview';
import {phoneText as t} from "./lib/phone";
import {CurrentGame} from './CurrentGame';
import {SceneClock} from './SceneClock';
import {phoneOperation} from './lib/phoneRequests';
import {advanceDomainLabel} from './lib/longTerm';
import {LongTermAdvance} from './LongTermAdvance';


import {Phone} from './Phone';
import {CallScene} from './CallScene';
import {TimeSkip} from './TimeSkip';
import {RuntimeNotifications} from './RuntimeNotifications';
import {NarrativeTurn} from "./NarrativeTurn";
import {useStableEvent} from "./hooks";
import {useStoryScroll} from "./useStoryScroll";
import {presentationEntries,surfaceEntries,physicalChoiceTurn} from "./presentationEntries";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  BookOpen,
  Clock,
  CheckCheck, ChevronUp, Ellipsis, Orbit, ScanEye, Square, X,
  Send,
  RotateCcw,
  Undo2,
  ArrowDown,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "./api";
import { useJob } from "./hooks";
import {
  active,
  type World,
  type Save,
  type Job,
  type Preferences,
} from "./types";
import {Dialog, DialogContent, DialogTitle, DialogDescription} from "./components/ui/dialog";
import { Markdown } from "./Markdown";
import { Diagnostics } from "./Diagnostics";

import { Button } from "./components/ui/button";
import { Textarea } from "./components/ui/textarea";
import {NarrativePolicy} from './NarrativePolicy';
import {Protagonist} from './Protagonist';
import {WorldCamera} from "./WorldCamera";
import {useMobile} from './mobile';
export function Game({
  presentationActive=true, suspended=false,
  world,
  save,
  refresh,
  choose,
  openLibrary, openDisplay, openSettings, toggleFocus, reading,
  openStory,
  openCharacter,
  prefs,
  apiKey,
}: {
  presentationActive?: boolean; suspended?:boolean;
  world: World | null;
  save: Save | null;
  refresh: () => void;
  choose: (w: number, s?: number) => void;
  openLibrary: () => void; openDisplay: () => void; openSettings:()=>void; toggleFocus:()=>void; reading:boolean;
  openStory: (notice:StoryNotice) => void;
  openCharacter: (id: string) => void;
  prefs: Preferences;
  apiKey: string;
}) {
  const [more,setMore]=useState(false);
  const mobile=useMobile();
  const [notices,setNotices]=useState(()=>localStorage.getItem('relationship-notices')!=='off');

  const input=useRef<HTMLTextAreaElement>(null);
  const mainActor=save?.state.protagonist_id||save?.state.characters.find(c=>c.is_player)?.id;
  const actorId=save?.state.controlled_actor_id===undefined?mainActor:save.state.controlled_actor_id;
  const [policyOpen,setPolicyOpen]=useState(false);
  const [timeSkipOpen,setTimeSkipOpen]=useState(false);
  const [longTermOpen,setLongTermOpen]=useState(false);
  const [protagonistOpen,setProtagonistOpen]=useState(false);
  const [cameraOpen,setCameraOpen]=useState(false);
  const draftKey=`draft-${save?.id}-${actorId}-${save?.state.camera?.pov_actor_id}`;
  const [diagnostics, setDiagnostics] = useState(false);
  const [diagnosticJob, setDiagnosticJob] = useState<string|undefined>();
  const [draft, setDraft] = useState("");
  const draftRef=useRef(draft);draftRef.current=draft;
  const [requestBusy, setBusy] = useState(false);
  const [phoneBusy, setPhoneBusy] = useState(false);
  const [controlCommit,setControlCommit]=useState<{saveId:number;revision:number}|null>(null);
  // A committed control command is not ready for another action until its
  // revision has reached the parent projection. refresh() itself is asynchronous.
  const busy=requestBusy||phoneBusy||!!(controlCommit&&save?.id===controlCommit.saveId&&save.revision<controlCommit.revision);
  const refreshControl=(after:Save)=>{setControlCommit({saveId:after.id,revision:after.revision});refresh()};
  const [submitted, updateSubmitted] = useState<Job | null>(null);
  const viewScope=`${save?.id}:${actorId}:${save?.state.camera?.pov_actor_id}`;
  const currentScope=useRef(viewScope);
  currentScope.current=viewScope;
  const setSubmitted=useCallback((next:Job|null)=>{if(currentScope.current===viewScope)updateSubmitted(next)},[viewScope]);
  const {scroll,away,jumpToLatest,onScroll,revealMenu,liveText}=useStoryScroll(viewScope,true);
  const [selectedCall,setSelectedCall]=useState<string|null>(null);
  const activeCall=save?.state.phone?.events.find(e=>e.channel==='VOICE_CALL'&&e.status==='answered');
  useEffect(()=>{setSelectedCall(activeCall?.id||null)},[viewScope,activeCall?.id]);
  useEffect(()=>{const open=(e:Event)=>{
    const id=(e as CustomEvent<string>).detail;
    if(!save?.state.phone?.events.some(call=>call.id===id))return;
    // An explicit journal open must expand even if hang-up persisted a collapsed panel.
    sessionStorage.removeItem(`call-min:${save.id}:${save.state.phone.actor_id}:${save.state.camera?.pov_actor_id}:${id}`);
    setSelectedCall(id);
  };window.addEventListener('phone-call-open',open);return()=>window.removeEventListener('phone-call-open',open)},[save]);
  const choiceTurn=physicalChoiceTurn(save);
  const choicesBelongToActor=save?.state.camera?.mode==='observer'||(choiceTurn?.pov_actor_id||mainActor)===actorId;
  const physicalChoices=(choicesBelongToActor ? choiceTurn?.choices : [])?.filter(c=>(c.interaction_channel||"physical")==="physical") || [];
  const choiceKey=`${viewScope}:${choiceTurn?.id}:${choiceTurn?.active_variant_id}`;
  const [selectedChoice,setSelectedChoice]=useState<string|null>(null);
  const [sendingChoice,setSendingChoice]=useState<string|null>(null);
  const [pendingChoice,setPendingChoice]=useState<string|null>(null);
  useEffect(()=>{setSelectedChoice(null);setPendingChoice(null)},[choiceKey]);
  const writeChoice=(text:string, choice=text)=>{
    setSelectedChoice(choice);
    setDraft(text);
    sessionStorage.setItem(draftKey,text);
    input.current?.focus({preventScroll:true});
  };
  useEffect(()=>{
    if(pendingChoice===null)return;
    const back=(event:PopStateEvent)=>{event.stopImmediatePropagation();setPendingChoice(null)};
    window.addEventListener('popstate',back,true);
    return ()=>window.removeEventListener('popstate',back,true);
  },[pendingChoice]);
  const closeChoice=()=>{if(history.state?.choiceDraft)history.back();else setPendingChoice(null)};
  useEffect(() => {
    setDraft(sessionStorage.getItem(draftKey) || "");
    setSubmitted(null);
  }, [draftKey]);
  const { job: snapshot, reconnecting } = useJob(submitted ?? save?.job, refresh);
  const job = snapshot?.status === 'abandoned' ? null : snapshot;
  const awaitingCommit=job?.status==='saved'&&job.revision===save?.revision&&!save?.turns.some(t=>t.variants?.some(v=>v.job_id===job.id));
  const publishedHere = !!job?.published_revision && !!save?.turns.some(t=>t.variants?.some(v=>v.id===t.active_variant_id && v.job_id===job.id));
  const rejected = !!job && ['error','stopped'].includes(job.status) && (publishedHere || job.revision === save?.revision);
  const retryable = rejected && (job.published_revision ?? job.revision)===save?.revision && !!job.narrative_complete && !job.narrative_reauthor_required && job.retry_allowed !== false;
  const running = active(job)||!!job?.live&&job.status!=="saved"||!!awaitingCommit;
  const [presented,setPresented]=useState<string|null>(null);
  const streamedJob=useRef<string|null>(null);
  if(active(job))streamedJob.current=job?.id||null;
  const onPresented=useStableEvent((id:string)=>{if(id===job?.id)setPresented(id)});
  const revealingCommit=(job?.presentation?.surface!=='call'||activeCall?.id===job.presentation.call_id)&&(submitted?.id===job?.id||streamedJob.current===job?.id)&&job?.kind!=='communication'&&job?.status==='saved'&&save?.turns.some(t=>t.variants?.find(v=>v.id===t.active_variant_id)?.job_id===job.id)&&presented!==job.id;
  const generating = running || !!revealingCommit;
  const physicalStream = generating && (job?.presentation?.surface ?? (job?.kind === "communication" ? "phone" : "physical")) === "physical";
  const choicesElement = useRef<HTMLDivElement>(null);
  const wasStreaming = useRef(false);
  useLayoutEffect(() => {
    if (wasStreaming.current && !physicalStream && choicesElement.current)
      revealMenu(choicesElement.current);
    wasStreaming.current = physicalStream;
  }, [physicalStream, revealMenu]);
  const turnLocked = generating || (rejected && !!job.narrative_complete);
  const observer = save?.state.camera?.mode==='observer';
  const canAct = !!save && !save.state.protagonist_required && (observer || (!!actorId && save.state.actor_capabilities?.can_act!==false));
  const observeInstead = !observer && !!actorId && save?.state.actor_capabilities?.can_act===false && !save?.state.protagonist_required;
  const directionInput = observer || observeInstead;
  const canSubmit = (canAct || observeInstead) && !busy && !turnLocked && !!save?.turns.length;
  useEffect(()=>{if(save?.state.protagonist_required)setProtagonistOpen(true)},[save?.id,save?.state.protagonist_required]);

  const requestLock=useRef(false);
  const run = async (fn: () => Promise<void>) => {
    if(requestLock.current)return;
    requestLock.current=true;
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      toast.error((e as Error).message);
      refresh();
    } finally {
      requestLock.current=false;
      setBusy(false);
    }
  };
  const turn = (kind: "start" | "turn" | "regenerate" | "background", text = draft, target?:number, rollback=false, timeSkip?:{duration:number;reason:string},channel:"physical"|"call"="physical") =>
    run(async () => {
      if (!save || (kind === "turn" && !timeSkip && !canSubmit)) return;
      const j = await api<Job>(`/saves/${save.id}/turns`, {
        kind,
        text,
        target_turn_id: target,
        time_skip: timeSkip,
        observer_direction: kind==='turn' && observer,
        interaction_channel: kind==='turn'?channel:undefined,
        rollback_following: rollback,
        config: prefs.game,
        revision: save.revision,
        api_key: apiKey,
      });
      if(currentScope.current!==viewScope)return;
      setSubmitted(j);jumpToLatest();
      if (kind === "turn" && channel === "physical" && text === draftRef.current) {
        setDraft("");
        setSelectedChoice(null);
        sessionStorage.removeItem(draftKey);
      }
    });
  const switchActor=(actor:string,source?:number)=>void run(async()=>{
    if(!save)return;
    const after=await api<Save>(`/saves/${save.id}/protagonist`,{actor_id:actor,operation:'temporary',operation_id:crypto.randomUUID(),revision:save.revision});
    refreshControl(after);jumpToLatest();
  });
  const observe=(actor?:string,scene?:string,direction?:string)=>run(async()=>{
    if(!save)return;
    if(actor&&!direction){const after=await api<Save>(`/saves/${save.id}/protagonist`,{actor_id:actor,operation:'observe',operation_id:crypto.randomUUID(),revision:save.revision});refreshControl(after);return;}
    const j=await api<Job>(`/saves/${save.id}/camera`,{actor_id:actor,scene_id:scene,direction,revision:save.revision,config:prefs.game,api_key:apiKey});
    if(direction && direction===draftRef.current){setDraft("");setSelectedChoice(null);sessionStorage.removeItem(draftKey)}
    setSubmitted(j);jumpToLatest();
  });
  const chooseProposal=useStableEvent((text:string)=>{
    if(draftRef.current.trim() && draftRef.current!==text){
      history.pushState({...history.state,choiceDraft:true},'');
      setPendingChoice(text);
    } else writeChoice(text);
  });
  const submitDraft=async()=>{
    if(requestLock.current || !canSubmit || !draft.trim())return;
    setSendingChoice(selectedChoice);
    try {
      if(observeInstead && actorId) await observe(actorId,undefined,draft);
      else await turn("turn");
    } finally { setSendingChoice(null); }
  };
  useEffect(()=>{if(!input.current)return;const el=input.current;el.style.height='auto';el.style.height=Math.min(el.scrollHeight,108)+'px'},[draft,mobile]);

  const stableRun=useStableEvent(run);
  const stableTurn=useStableEvent(turn);
  const stopJob=useStableEvent(()=>void run(async()=>{
    if(!job)return;
    const stopped=await api<Job>(`/jobs/${job.id}/stop`,{});
    setSubmitted(stopped);refresh();
  }));
  const allEntries=presentationEntries(save,job);
  const entries=surfaceEntries(allEntries,'physical');
  const historyKey='history-expanded:'+viewScope;
  const [past,setPast]=useState(()=>sessionStorage.getItem(historyKey)==='true');
  const [historyBefore,setHistoryBefore]=useState(()=>entries.at(-1)?.turn.sequence??0);
  useLayoutEffect(()=>{
    setPast(sessionStorage.getItem(historyKey)==='true');
    setHistoryBefore(entries.at(-1)?.turn.sequence??0);
  },[historyKey]);
  const callEntries=surfaceEntries(allEntries,'call',actorId,selectedCall);
  const latestCall=callEntries.at(-1);
  const renderEntry=(entry:typeof allEntries[number],toolsOnly=false,hidden=false)=>world&&save?<NarrativeTurn latest={entry.identity===entries.at(-1)?.identity} hidden={hidden} liveTextRef={!toolsOnly && physicalStream && entry.identity===job?.id ? liveText : undefined} toolsOnly={toolsOnly} showTools={toolsOnly||entry.turn.presentation?.surface!=='call'} key={entry.identity} identity={entry.identity} t={entry.turn} i={save.turns.findIndex(t=>t.id===entry.turn.id)} save={save} world={world} prefs={prefs} mobile={mobile} busy={busy} running={turnLocked} mainActor={mainActor} turn={stableTurn} run={stableRun} setSubmitted={setSubmitted} refresh={refresh} setDiagnosticJob={setDiagnosticJob} setDiagnostics={setDiagnostics} openCharacter={openCharacter} job={entry.job} reconnecting={entry.job?reconnecting:false} stop={stopJob} committed={entry.committed} onPresented={onPresented}/>:null;
  const recovery = (physical: boolean) => rejected && job && save && (
    <div id={physical ? "turn-recovery" : undefined} className="flex flex-wrap gap-2" aria-busy={busy}>
      {!!job.narrative_complete && ['start','turn','background','pov'].includes(job.kind) && <Button disabled={busy || running} onClick={()=>void run(async()=>{
        setSubmitted(await api<Job>(`/jobs/${job.id}/save-scene`, {revision:save.revision, attempt_epoch:job.attempt_epoch ?? 0}));
        await refresh();
      })}>Сохранить исходную сцену без запроса к модели</Button>}
      {!job.published_revision && <Button disabled={busy || running} onClick={() => void run(async () => {
        try {
          const discarded = await api<Job>(`/saves/${save.id}/jobs/${job.id}/abandon`, {
            revision: save.revision, attempt_epoch: job.attempt_epoch ?? 0,
          });
          setSubmitted(discarded);
          if (physical && (!job.narrative_complete || job.narrative_reauthor_required || job.retry_allowed === false) && !draftRef.current && job.user_text) {
            setDraft(job.user_text);
            sessionStorage.setItem(draftKey, job.user_text);
          }
          if (physical) input.current?.focus({preventScroll:true});
        } finally {
          await refresh();
          setSubmitted(null);
        }
      })}>{physical ? 'Отменить неудачный ход' : t('abandonTurn')}</Button>}
      {(job.prose_correction_available || job.chronology_correction_available) && <div className="flex flex-col gap-2">
        <p className="text-sm text-muted-foreground">Адресная правка создаст новую редакцию и заново проверит состояние. Запросы к модели могут быть платными.</p>
        <Button variant="outline" disabled={busy || running} onClick={() => void run(async () => {
          setSubmitted(await api<Job>(`/jobs/${job.id}/retry`, {config:prefs.game, api_key:apiKey,
            correct_prose:true, revision:save.revision, attempt_epoch:job.attempt_epoch ?? 0}));
        })}>{job.chronology_correction_available?'Исправить хронологию сцены':'Исправить противоречие в сцене'}</Button>
      </div>}
      {retryable && <Button variant="outline" disabled={busy || running} onClick={() => void run(async () => {
        setSubmitted(await api<Job>(`/jobs/${job.id}/retry`, {config:prefs.game, api_key:apiKey}));
      })}>{physical ? 'Повторить обработку состояния' : t('retry')}</Button>}
    </div>
  );
  const meta = save?.scene_meta ?? world?.scene_meta;
  const state = save?.state ?? world?.state;
  if (!world)
    return (
      <main className="welcome">
        <div className="welcome-mark">
          <BookOpen size={38} />
        </div>
        <p className="eyebrow">AI RPG Engine</p>
        <h1>
          История ждёт
          <br />
          <em>твоего следующего шага.</em>
        </h1>
        <p className="muted">
          Живые персонажи. Разговоры без сценария.
          <br />
          Мир, в котором каждое действие имеет значение.
        </p>
        <Button size="lg" onClick={openLibrary}>
          Выбрать мир <span>→</span>
        </Button>
        <p className="welcome-foot">ТВОЙ МИР · ТВОЙ ТЕМП · ТВОЯ ИСТОРИЯ</p>
      </main>
    );
  const actorName=state?.characters.find(c=>c.id===actorId)?.name;
  const cameraActions=<>
    <button className="nr-camerabutton" onClick={()=>{setMore(false);setCameraOpen(true)}}><ScanEye/>Камера · Журнал</button>
    <button className="nr-backgroundbutton" disabled={busy||turnLocked||!save?.turns.length} onClick={()=>{setMore(false);void turn("background","")}}><Orbit/>Мир без ГГ</button>
    {actorId!==mainActor&&mainActor&&<Button variant="ghost" size="sm" disabled={busy||turnLocked} onClick={()=>{setMore(false);switchActor(mainActor)}}>Вернуться к {state?.characters.find(c=>c.id===mainActor)?.name}</Button>}
  </>;
  return (
    <main className="game" style={{"--sf-reading-width":prefs.reading_width+"px","--sf-font-size":prefs.font_size+"px","--sf-line-height":prefs.line_height} as React.CSSProperties}>
      {save&&!suspended&&selectedCall&&<CallScene key={`${viewScope}:${selectedCall}`} save={save} choices={latestCall?.committed ? latestCall.turn.choices.filter(c=>c.interaction_channel==='call') : []} callId={selectedCall} onSelect={setSelectedCall} obscured={diagnostics||!presentationActive} job={job?.presentation?.call_id===selectedCall?job:null} reconnecting={reconnecting} stop={stopJob} stopping={busy} disabled={busy||turnLocked||!canAct} recovery={job?.presentation?.call_id===selectedCall?recovery(false):null} submit={async text=>{
        let sent=false;
        await run(async()=>{const j=await api<Job>(`/saves/${save.id}/turns`,{kind:'turn',text,interaction_channel:'call',config:prefs.game,revision:save.revision,api_key:apiKey});setSubmitted(j);sent=true});
        if(!sent)throw new Error('Не удалось отправить реплику');
      }} end={async()=>{await run(async()=>{const request=phoneOperation(`phone-request:${save.id}:${save.state.phone?.actor_id}`,{action:'end',event_id:selectedCall});const after=await api<Save>(`/saves/${save.id}/phone`,{revision:save.revision,command:request.payload});request.complete();refreshControl(after);setSelectedCall(null);requestAnimationFrame(()=>input.current?.focus({preventScroll:true}))})}}>
        {callEntries.map(e=>renderEntry(e))}
      </CallScene>}
      {save&&<div className="narrative-toolbar nr-gamebar" role="group" aria-label="Действия истории">
        <CurrentGame refresh={refreshControl} save={save} disabled={busy||turnLocked} notices={notices} onNotices={v=>{setNotices(v);localStorage.setItem('relationship-notices',v?'on':'off')}} policy={()=>setPolicyOpen(true)} protagonist={()=>setProtagonistOpen(true)} camera={()=>setCameraOpen(true)} openCharacter={openCharacter} timeSkip={()=>setTimeSkipOpen(true)} longTerm={()=>setLongTermOpen(true)}/>

        <div className="nr-actorcontrol"><label className="nr-actorvalue">
          <span className="nr-miniav nr-avatarplayer" aria-hidden>{actorName?.slice(0,1)}</span>
          <Choice aria-label="Управляемый персонаж" value={actorId||""} disabled={busy||turnLocked} onValueChange={switchActor}>
            {!actorId&&<option value="">Наблюдение</option>}{save.state.characters.map(c=><option key={c.id} value={c.id}>{c.name}{c.id===mainActor?' · основной герой':''}</option>)}
          </Choice></label></div>
        {!mobile && cameraActions}
        {mobile && <Button className="nr-mobilemore" variant="outline" size="icon" aria-label="Ещё действия" onClick={()=>setMore(true)}><Ellipsis/></Button>}
        <Dialog open={mobile && more} onOpenChange={setMore}><DialogContent className="narrative-more"><DialogTitle>Ещё действия</DialogTitle>{cameraActions}
          <Button onClick={()=>{setMore(false);toggleFocus()}}>{reading?'Выйти из чтения':'Режим чтения'}</Button>
          <Button onClick={()=>{setMore(false);openDisplay()}}>Отображение</Button>
          <Button onClick={()=>{setMore(false);openSettings()}}>Настройки</Button>
          <Button onClick={()=>{setMore(false);setDiagnosticJob(undefined);setDiagnostics(true)}}>Диагностика</Button>
        </DialogContent></Dialog>
      </div>}
      {save&&<> <LongTermAdvance open={longTermOpen} onOpenChange={setLongTermOpen} save={save} disabled={busy||turnLocked||!save.turns.length||!!save.state.protagonist_required} submit={async request=>{
                      if(requestLock.current)throw new Error('Дождись завершения текущего действия.');
                      requestLock.current=true;setBusy(true);
                      try {
                      const j=await api<Job>(`/saves/${save.id}/long-term`,{request,config:prefs.game,revision:save.revision,api_key:apiKey});
                      setSubmitted(j);jumpToLatest();
                      } catch(e) {refresh();throw e}
                      finally {requestLock.current=false;setBusy(false)}
                    }}/>
                    <TimeSkip open={timeSkipOpen} onOpenChange={setTimeSkipOpen} save={save} disabled={busy||turnLocked||!save.turns.length||!!save.state.protagonist_required} submit={(duration,reason)=>void turn('turn',actorId===null||save.state.actor_capabilities?.can_act===false?'':`Жду ${duration} минут.${reason?' '+reason:''}`,undefined,false,{duration,reason})}/>
</>}
      {job?.published_revision && active(job) && <Button size="sm" variant="ghost" disabled={busy} onClick={stopJob}>Продолжить с сохранённой сценой</Button>}
      <RuntimeNotifications save={save} job={submitted?job:null} enabled={notices}/>
      {save&&<>{save.state.protagonist_required&&<p role="alert">Главный герой умер. История продолжается: выбери или создай нового героя.</p>}<Protagonist save={save} open={protagonistOpen} onOpenChange={setProtagonistOpen} refresh={refreshControl} prefs={prefs} apiKey={apiKey}/></>}
      {save&&<><NarrativePolicy save={save} open={policyOpen} onOpenChange={setPolicyOpen} refresh={refreshControl}/></>}
      {save&&<WorldCamera save={save} open={cameraOpen} onOpenChange={setCameraOpen} busy={busy||turnLocked} observe={observe} control={switchActor}/>}
      {save&&<NpcReview key={save.id} save={save} locked={busy||turnLocked} prefs={prefs} apiKey={apiKey} onCommit={refreshControl}/>}
      {save&&<Diagnostics saveId={save.id} choiceView={{turn:choiceTurn,list:choicesElement,revision:save.revision}} jobId={diagnosticJob} open={diagnostics} onOpenChange={setDiagnostics} historyTools={<>{allEntries.filter(e=>e.committed&&e.turn.presentation?.surface!=='physical').map(e=>renderEntry(e,true))}{job&&['error','stopped'].includes(job.status)&&<><p role="alert">{job.error}</p>{recovery(false)}</>}</>}/>}
      <div
        className="story-scroll nr-feed"
        ref={scroll}
        onScroll={onScroll}
      >
        <div
          className="story nr-content"
        >
          <section className="nr-context" aria-label="Текущая сцена">
            <div className="nr-contexttop"><div className="skin-heading"><SkinStamp/><div><h1>{meta?.location || world.name}</h1>
              <button className="nr-datetime" aria-label="Открыть календарь" disabled={!save} onClick={()=>window.dispatchEvent(new CustomEvent('save-workspace',{detail:{section:'calendar'}}))}><Clock/><SceneClock save={save} fallback={meta?.time}/></button>
            </div></div>{save&&<span className="nr-saved"><CheckCheck/>{running?'Идёт ход':'Сохранено'}</span>}</div>
            <div className="nr-contextbottom"><span className="nr-nearlabel">Рядом</span>
              <div className="nr-people">{state?.characters.filter(c=>meta?.present_ids.includes(c.id)&&c.id!==actorId).map(c=><button key={c.id} className="nr-person" onClick={()=>openCharacter(c.id)}><span className="nr-miniav" aria-hidden>{c.name.slice(0,1)}</span><span className="nr-person-name">{c.name.replace(" (ГГ)","")}</span></button>)}</div>
              {save&&<StoryNotifications key={`${save.id}:${actorId}`} save={save} active={presentationActive} enabled={notices} onOpen={openStory}/>}</div>
          </section>

          {save?.state.last_long_term_advance&&<details className="skip-diagnostics advance-result" open><summary>Длительный переход{save.state.last_long_term_advance.interruption?' · прерван':''}</summary>
            {save.state.last_long_term_advance.status==='incomplete'&&<p role="status">Симуляция неполная. Принятые события сохранены; часть причин осталась без результата.</p>}
            {save.state.last_long_term_advance.status==='calendar_only'&&<p>Изменился календарь. Жизнь NPC в этом переходе не моделировалась.</p>}
            {save.state.last_long_term_advance.status==='quiet'&&<p>Рассмотренные ситуации пока не привели к новым событиям.</p>}
            {save.state.last_long_term_advance.coverage&&<p>Принято групп: {save.state.last_long_term_advance.coverage.accepted_groups}. Без новых событий: {save.state.last_long_term_advance.coverage.quiet_groups}. Отклонено причин: {save.state.last_long_term_advance.coverage.rejected_causes}. Не рассмотрено из-за лимита: {save.state.last_long_term_advance.coverage.budget_unattempted}.</p>}
            <details className="advance-result-details"><summary>Подробности симуляции</summary><p>Обращений к модели: {save.state.last_long_term_advance.llm_calls} / {save.state.last_long_term_advance.max_llm_calls}. Нерешённых причин: {save.state.last_long_term_advance.unresolved.length}.</p></details>
            {save.state.last_long_term_advance.accepted.length>0&&<><strong>События вне сцены — сведения для игрока</strong><p>Герой не узнаёт эти сведения автоматически.</p><ul>{save.state.last_long_term_advance.accepted.flatMap(g=>g.summaries).map((text,i)=><li key={i}>{text}</li>)}</ul></>}
            {save.state.last_long_term_advance.decisions.length>0&&<><strong>Требуется твоё решение</strong><ul>{save.state.last_long_term_advance.decisions.map(c=><li key={c.id}>{c.context||'Есть нерешённая возможность или обязательство героя.'}{c.domains?.length?` — ${c.domains.map(advanceDomainLabel).join(', ')}`:''}</li>)}</ul><p>Продолжи обычный ход, чтобы принять решение.</p></>}
          </details>}
          {save?.state.last_time_skip&&<details className="skip-diagnostics"><summary>Пропуск времени: {save.state.last_time_skip.elapsed_minutes} мин{save.state.last_time_skip.interrupted?' · прерван':''}</summary><p>Запрошено: {save.state.last_time_skip.requested_duration} мин · Кандидатов: {save.state.last_time_skip.background_candidates} · Симуляций: {save.state.last_time_skip.simulated_candidates||0} · Объединено: {save.state.last_time_skip.merged_candidates||0} · Пропущено: {save.state.last_time_skip.skipped_candidates||0} · LLM мира: {save.state.last_time_skip.living_world_llm_calls||0}</p></details>}
          {!save ? (
            <div className="empty-state">
              <Markdown text={world.state.scene} />
              <Button
                onClick={() =>
                  run(async () => {
                    const s = await api<Save>(`/worlds/${world.id}/saves`, {
                      name: "Новое прохождение",
                    });
                    choose(world.id, s.id);
                  })
                }
                disabled={busy}
              >
                Создать прохождение
              </Button>
            </div>
          ) : (
            <>
              {entries.length>1 && <div className="nr-pasttoggle"><button className="nr-textbutton" aria-expanded={past} onClick={()=>{setHistoryBefore(entries.at(-1)?.turn.sequence??0);setPast(!past);sessionStorage.setItem(historyKey,String(!past))}}><ChevronUp/>Предыдущий ход</button><span className="nr-feedline"/></div>}
              {entries.map((e,i)=>renderEntry(e,false,!past && i<entries.length-1 && e.turn.sequence<historyBefore))}
              {!save.turns.length && !job && (
                <div className="empty-state">
                  <p>
                    Всё готово. Ведущий разыграет первую сцену и предложит возможные действия.
                  </p>
                </div>
              )}
              {rejected && (!job.presentation || job.presentation.surface === 'physical') && <>
                <p role="status">Ход не вошёл в историю. Можно отменить его и продолжить игру.</p>
                {recovery(true)}
              </>}
              {!save.turns.length && !turnLocked && (
                <Button size="lg" disabled={busy} onClick={() => turn("start")}>
                  Начать игру
                </Button>
              )}
              {save.turns.length > 0 && (
                <>
                  {actorId===null&&<div className="background-exit">
                    <Button variant="outline" disabled={busy||turnLocked} onClick={()=>observe(undefined,save.state.camera?.scene_id)}>Продолжить наблюдать</Button>
                    <Button disabled={busy||turnLocked} onClick={()=>switchActor(mainActor!)}>Вернуться к {save.state.characters.find(c=>c.id===mainActor)?.name.replace(' (ГГ)','')}</Button>
                    <label>Продолжить за персонажа…<Choice aria-label="Участник фоновой сцены" value="" disabled={busy||turnLocked} onValueChange={selectedValue => switchActor(selectedValue,save.turns.at(-1)!.id)}><option value="">Выбрать участника</option>{save.state.characters.filter(c=>JSON.parse(save.turns.at(-1)?.audience_json||'[]').includes(c.id)).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</Choice></label>
                  </div>}
                  {save.state.actor_capabilities?.can_act===false&&<div><p role="status">Персонаж сейчас не может действовать. Можно продолжить течение времени или наблюдать за миром.</p>{actorId&&<Button disabled={busy||turnLocked} onClick={()=>observe(actorId)}>Продолжить наблюдать за героем</Button>}</div>}
                  <ActionPanel count={physicalChoices.length} label="Варианты действий" hidden={physicalStream}><div className="choices" ref={choicesElement} key={choiceKey}>
                    {physicalChoices.map((c, i) => (
                      <NarrativeChoiceCard key={i} choice={c} disabled={!canSubmit}
                        selected={selectedChoice===choiceText(c)} sending={sendingChoice===choiceText(c)}
                        choose={chooseProposal}/>
                    ))}
                  </div></ActionPanel>
                  {!generating&&entries.filter(e=>e.committed).at(-1)?.turn.id===save.turns.at(-1)?.id&&<div className="turn-actions">
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busy||retryable||!save.turns.at(-1)?.variants?.some(v=>v.can_regenerate)}
                      onClick={() => turn("regenerate", "")}
                    >
                      <RotateCcw size={14} />
                      Перегенерировать последний ход
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busy}
                      onClick={() => {
                        if (
                          window.confirm(
                            "Откатить последний ход и восстановить состояние до него?",
                          )
                        )
                          run(async () => {
                            await api(`/saves/${save.id}/rollback`, {
                              revision: save.revision,
                            });
                            setSubmitted(null);
                            refresh();
                          });
                      }}
                    >
                      <Undo2 size={14} />
                      Откатить
                    </Button>
                  </div>}
                </>
              )}
            </>
          )}
        </div>
      </div>
      {save && (
        <div className="composer nr-composerarea">            {away&&<button className="nr-jump"
              onClick={jumpToLatest}
            >
              <ArrowDown size={13} />К последнему ответу
            </button>}<div className="nr-composercontent">
          <Dialog open={pendingChoice!==null} onOpenChange={open=>{if(!open)closeChoice()}}>
            <DialogContent onCloseAutoFocus={event=>{event.preventDefault();input.current?.focus({preventScroll:true})}}>
              <DialogTitle>В поле уже есть черновик</DialogTitle>
              <DialogDescription>Предложение: {pendingChoice}</DialogDescription>
              <div className="actions">
                <Button onClick={()=>{writeChoice(draftRef.current+'\n'+pendingChoice,pendingChoice!);closeChoice()}}>Добавить к черновику</Button>
                <Button variant="outline" onClick={()=>{writeChoice(pendingChoice!);closeChoice()}}>Заменить черновик</Button>
                <Button variant="ghost" onClick={closeChoice}>Отмена</Button>
              </div>
            </DialogContent>
          </Dialog>
          <div className="nr-writingstatus"><span className="nr-writeidentity"><i className="nr-smallstatus"/>{actorName || 'Наблюдение'}</span><span data-draft-status>{physicalStream?'Идёт ответ':draft?'Черновик':'Твой ход'}</span>{draft&&<button className="nr-clear" aria-label="Очистить черновик" onClick={()=>{writeChoice('');setSelectedChoice(null)}}><X/></button>}</div>
          <div className="composer-inner nr-composer">
            <Phone openCharacter={openCharacter} recovery={recovery(false)} save={save} onBusyChange={setPhoneBusy} disabled={busy||turnLocked} onCommit={refreshControl} config={prefs.game} apiKey={apiKey} onJob={setSubmitted} job={job}/>
            <Textarea
              ref={input}
              rows={1}
              aria-label={directionInput ? "Направление истории" : "Своё действие или реплика"}
              value={draft}
              onChange={(e) => {
                setSelectedChoice(null);
                setDraft(e.target.value);
                sessionStorage.setItem(draftKey, e.target.value);
              }}
              disabled={!canAct && !observeInstead}
              placeholder={directionInput?"Что показать дальше?":activeCall?"Физическая сцена: что ты делаешь рядом?":actorId===null?"В каком направлении продолжить историю?":mobile?"Твоё действие…":"Что ты делаешь или говоришь?"}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" && !e.nativeEvent.isComposing &&
                  (e.ctrlKey || e.metaKey) &&
                  canSubmit &&
                  draft.trim()
                ) {
                  e.preventDefault();
                  submitDraft();
                }
              }}
            />
            {physicalStream && active(job) ? <Button className="nr-stop" onClick={stopJob}><Square/>Стоп</Button> : <Button className="nr-send"
              aria-label={directionInput ? "Отправить направление истории" : "Отправить действие"}
              size="icon"
              disabled={!canSubmit || !draft.trim()}
              onClick={submitDraft}
            >
              <span>Отправить</span><Send size={19} />
            </Button>}
          </div>
          <div className="nr-composerhint"><span>Ctrl + Enter — отправить · Enter — новая строка</span><span data-counter>{draft ? draft.length : 'Действие определяешь ты'}</span><button className="nr-textsize" aria-label="Настройки отображения" onClick={openDisplay}>Аа</button>
            {!mobile && <button className="story-diagnostics" onClick={()=>{setDiagnosticJob(undefined);setDiagnostics(true)}}>Диагностика</button>}
            {rejected&&<button className="nr-recover" onClick={() => document.getElementById('turn-recovery')?.scrollIntoView({block:'center'})}>К восстановлению хода</button>}

          </div></div>
        </div>
      )}
    </main>
  );
}
