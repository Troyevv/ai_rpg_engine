import {phoneText as t} from "./lib/phone";
import {CurrentGame} from './CurrentGame';
import {SceneClock} from './SceneClock';
import {calendarDate} from './gameDate';
import {advanceDomainLabel} from './lib/longTerm';
import {LongTermAdvance} from './LongTermAdvance';
import {SkinHeader} from './ThemeDecorationLayer';
import {useTheme,themes} from './ThemeProvider';
import {Phone} from './Phone';
import {CallScene} from './CallScene';
import {TimeSkip} from './TimeSkip';
import {RuntimeNotifications} from './RuntimeNotifications';
import {useMotionPreset} from "./motion";
import {NarrativeTurn} from "./NarrativeTurn";
import {useStableEvent} from "./hooks";
import {useStoryScroll} from "./useStoryScroll";
import {presentationEntries,surfaceEntries,physicalChoiceTurn} from "./presentationEntries";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  BookOpen,
  Clock,
  MapPin,
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
import { Markdown } from "./Markdown";
import { Diagnostics } from "./Diagnostics";

import { Button } from "./components/ui/button";
import { Textarea } from "./components/ui/textarea";
import {NarrativePolicy} from './NarrativePolicy';
import {Protagonist} from './Protagonist';
import {WorldCamera} from "./WorldCamera";
import {useMobile,MobileScene} from './mobile';
export function Game({
  world,
  save,
  refresh,
  choose,
  openLibrary,
  openCharacter,
  prefs,
  apiKey,
}: {
  world: World | null;
  save: Save | null;
  refresh: () => void;
  choose: (w: number, s?: number) => void;
  openLibrary: () => void;
  openCharacter: (id: string) => void;
  prefs: Preferences;
  apiKey: string;
}) {
  const {presentation}=useTheme();
  const decoration=themes.find(t=>t.id===presentation.theme_id)?.decoration||'none';
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
  const [submitted, setSubmitted] = useState<Job | null>(null);
  const viewScope=`${save?.id}:${actorId}:${save?.state.camera?.pov_actor_id}`;
  const {scroll,away,jumpToLatest,onScroll}=useStoryScroll(viewScope);
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
  const reduced = useReducedMotion();
  const choicesMotion=useMotionPreset('staggerContainer');
  const choiceMotion=useMotionPreset('staggerItem');
  // The loaded journal is already visible. Animate only records added in this session.
  const choiceTurn=physicalChoiceTurn(save);
  const choiceKey=`${viewScope}:${choiceTurn?.id}:${choiceTurn?.active_variant_id}`;
  const initialChoice=useRef(choiceKey);
  const [selectedChoice,setSelectedChoice]=useState<number|null>(null);
  useEffect(()=>{setSelectedChoice(null)},[choiceKey]);
  useEffect(() => {
    setDraft(sessionStorage.getItem(draftKey) || "");
    setSubmitted(null);
  }, [draftKey]);
  const { job, reconnecting } = useJob(submitted ?? save?.job, refresh);
  const awaitingCommit=job?.status==='saved'&&job.revision===save?.revision&&!save?.turns.some(t=>t.variants?.some(v=>v.job_id===job.id));
  const unapplied = !!job && ['error','stopped'].includes(job.status) && !!job.narrative_complete && job.revision === save?.revision;
  const running = active(job)||!!job?.live&&job.status!=="saved"||!!awaitingCommit;
  const [presented,setPresented]=useState<string|null>(null);
  const streamedJob=useRef<string|null>(null);
  if(active(job))streamedJob.current=job?.id||null;
  const onPresented=useStableEvent((id:string)=>{if(id===job?.id)setPresented(id)});
  const revealingCommit=(job?.presentation?.surface!=='call'||activeCall?.id===job.presentation.call_id)&&(submitted?.id===job?.id||streamedJob.current===job?.id)&&job?.kind!=='communication'&&job?.status==='saved'&&save?.turns.some(t=>t.variants?.find(v=>v.id===t.active_variant_id)?.job_id===job.id)&&presented!==job.id;
  const pending = running||unapplied||!!revealingCommit;
  const canAct = !!save && !!actorId && !save.state.protagonist_required && save.state.actor_capabilities?.can_act!==false;
  const canSubmit = canAct && !busy && !pending && !!save?.turns.length;
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
        interaction_channel: kind==='turn'?channel:undefined,
        rollback_following: rollback,
        config: prefs.game,
        revision: save.revision,
        api_key: apiKey,
      });
      setSubmitted(j);
      if (kind === "turn" && channel === "physical" && text === draftRef.current) {
        setDraft("");
        sessionStorage.removeItem(draftKey);
      }
    });
  const switchActor=(actor:string,source?:number)=>void run(async()=>{
    if(!save)return;
    const after=await api<Save>(`/saves/${save.id}/protagonist`,{actor_id:actor,operation:'temporary',operation_id:crypto.randomUUID(),revision:save.revision});
    refreshControl(after);jumpToLatest();
  });
  const observe=(actor?:string,scene?:string)=>void run(async()=>{
    if(!save)return;
    if(actor){const after=await api<Save>(`/saves/${save.id}/protagonist`,{actor_id:actor,operation:'observe',operation_id:crypto.randomUUID(),revision:save.revision});refreshControl(after);return;}
    const j=await api<Job>(`/saves/${save.id}/camera`,{actor_id:actor,scene_id:scene,revision:save.revision,config:prefs.game,api_key:apiKey});
    setSubmitted(j);jumpToLatest();
  });
  // Grow on desktop as well as mobile, including width/font changes. The existing
  // story ResizeObserver remains the only owner of reading-position adjustments.
  useLayoutEffect(()=>{
    const el=input.current;if(!el)return;
    const resize=()=>{el.style.height='0px';el.style.height=Math.min(el.scrollHeight,132)+'px'};
    resize();let width=el.clientWidth;
    const observer=new ResizeObserver(()=>{if(el.clientWidth!==width){width=el.clientWidth;resize()}});
    observer.observe(el);return()=>observer.disconnect();
  },[draft,mobile,prefs.font_size,save?.id]);

  const stableRun=useStableEvent(run);
  const stableTurn=useStableEvent(turn);
  const stopJob=useStableEvent(()=>void run(async()=>{
    if(!job)return;
    const stopped=await api<Job>(`/jobs/${job.id}/stop`,{});
    setSubmitted(stopped);refresh();
  }));
  const allEntries=presentationEntries(save,job);
  const entries=surfaceEntries(allEntries,'physical');
  const turnIndices=useMemo(()=>new Map(save?.turns.map((t,i)=>[t.id,i])),[save?.turns]);
  const renderEntry=(entry:typeof allEntries[number],toolsOnly=false)=>world&&save?<NarrativeTurn toolsOnly={toolsOnly} showTools={toolsOnly||entry.turn.presentation?.surface!=='call'} key={entry.identity} identity={entry.identity} t={entry.turn} i={turnIndices.get(entry.turn.id)??-1} save={save} world={world} prefs={prefs} mobile={mobile} busy={busy} running={pending} mainActor={mainActor} turn={stableTurn} run={stableRun} setSubmitted={setSubmitted} refresh={refresh} setDiagnosticJob={setDiagnosticJob} setDiagnostics={setDiagnostics} openCharacter={openCharacter} job={entry.job} reconnecting={entry.job?reconnecting:false} stop={stopJob} committed={entry.committed} onPresented={onPresented}/>:null;
  const retry=job&&unapplied?<Button disabled={busy||job.live} onClick={()=>void run(async()=>{setSubmitted(await api<Job>(`/jobs/${job.id}/retry`,{config:prefs.game,api_key:apiKey}))})}>{t('retry')}</Button>:null;
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
  return (
    <main className="game">
      {save&&selectedCall&&<CallScene key={`${viewScope}:${selectedCall}`} save={save} callId={selectedCall} onSelect={setSelectedCall} obscured={diagnostics} job={job?.presentation?.call_id===selectedCall?job:null} reconnecting={reconnecting} stop={stopJob} stopping={busy} disabled={busy||pending||!canAct} recovery={job?.presentation?.call_id===selectedCall?retry:null} submit={async text=>{
        let sent=false;
        await run(async()=>{const j=await api<Job>(`/saves/${save.id}/turns`,{kind:'turn',text,interaction_channel:'call',config:prefs.game,revision:save.revision,api_key:apiKey});setSubmitted(j);sent=true});
        if(!sent)throw new Error('Не удалось отправить реплику');
      }} end={async()=>{await run(async()=>{const after=await api<Save>(`/saves/${save.id}/phone`,{revision:save.revision,command:{action:'end',event_id:selectedCall,operation_id:crypto.randomUUID()}});refreshControl(after);setSelectedCall(null);input.current?.focus()})}}>
        {surfaceEntries(allEntries,'call',actorId,selectedCall).map(e=>renderEntry(e))}
      </CallScene>}
      {save&&<CurrentGame refresh={refreshControl} save={save} disabled={busy||pending} notices={notices} onNotices={v=>{setNotices(v);localStorage.setItem('relationship-notices',v?'on':'off')}} policy={()=>setPolicyOpen(true)} protagonist={()=>setProtagonistOpen(true)} camera={()=>setCameraOpen(true)} openCharacter={openCharacter} timeSkip={()=>setTimeSkipOpen(true)} longTerm={()=>setLongTermOpen(true)}/>}
      {save&&<> <LongTermAdvance open={longTermOpen} onOpenChange={setLongTermOpen} save={save} disabled={busy||pending||!save.turns.length||!!save.state.protagonist_required} submit={request=>void run(async()=>{
                      const j=await api<Job>(`/saves/${save.id}/long-term`,{request,config:prefs.game,revision:save.revision,api_key:apiKey});
                      setSubmitted(j);jumpToLatest();
                    })}/>
                    <TimeSkip open={timeSkipOpen} onOpenChange={setTimeSkipOpen} save={save} disabled={busy||pending||!save.turns.length||!!save.state.protagonist_required} submit={(duration,reason)=>void turn('turn',actorId===null||save.state.actor_capabilities?.can_act===false?'':`Жду ${duration} минут.${reason?' '+reason:''}`,undefined,false,{duration,reason})}/>
</>}
      <RuntimeNotifications save={save} job={submitted?job:null} enabled={notices}/>
      {save&&<>{save.state.protagonist_required&&<p role="alert">Главный герой умер. История продолжается: выбери или создай нового героя.</p>}<Protagonist save={save} open={protagonistOpen} onOpenChange={setProtagonistOpen} refresh={refreshControl} prefs={prefs} apiKey={apiKey}/></>}
      {save&&<><NarrativePolicy save={save} open={policyOpen} onOpenChange={setPolicyOpen} refresh={refreshControl}/></>}
      {save&&<WorldCamera save={save} open={cameraOpen} onOpenChange={setCameraOpen} busy={busy||pending} observe={observe} control={switchActor}/>}
      {save&&<Diagnostics saveId={save.id} jobId={diagnosticJob} open={diagnostics} onOpenChange={setDiagnostics} historyTools={<>{allEntries.filter(e=>e.committed&&e.turn.presentation?.surface!=='physical').map(e=>renderEntry(e,true))}{job&&['error','stopped'].includes(job.status)&&<><p role="alert">{job.error}</p>{retry}</>}</>}/>}
      {mobile&&save?<MobileScene save={save} meta={meta} busy={busy||pending} switchActor={switchActor} background={()=>void turn("background","")} openCharacter={openCharacter} openCamera={()=>setCameraOpen(true)}/>:<>{save&&<div className="pov-controls">
        <label>Управляемый персонаж<select aria-label="Управляемый персонаж" value={actorId||""} disabled={busy||pending} onChange={e=>switchActor(e.target.value)}>{!actorId&&<option value="">Камера наблюдателя</option>}{save.state.characters.map(c=><option key={c.id} value={c.id}>{c.name}{c.id===mainActor?" · основной герой":""}</option>)}</select></label>
        {actorId!==mainActor&&<Button variant="ghost" size="sm" disabled={busy||pending} onClick={()=>switchActor(mainActor!)}>Вернуться к {save.state.characters.find(c=>c.id===mainActor)?.name.replace(" (ГГ)","")}</Button>}
        <Button variant="ghost" size="sm" onClick={()=>setCameraOpen(true)}>Камера · Журнал</Button>
        <Button variant="outline" size="sm" disabled={busy||pending||!save.turns.length} onClick={()=>void turn("background","")}>Мир без ГГ</Button>
      </div>}
      <div className="scene-bar">
        <button className="scene-calendar-entry" aria-label="Открыть календарь" disabled={!save} onClick={()=>window.dispatchEvent(new CustomEvent('save-workspace',{detail:{section:'calendar'}}))}>
          <Clock size={14} />
          <SceneClock save={save} fallback={meta?.time}/>
        </button>
        <span>
          <MapPin size={14} />
          {meta?.location || "Место не указано"}
        </span>
        <div className="scene-near">
          <span className="muted">Рядом</span>
          {state?.characters
            .filter((c) => meta?.present_ids.includes(c.id) && !c.is_player)
            .map((c) => (
              <button key={c.id} onClick={() => openCharacter(c.id)}>
                {c.name.replace(" (ГГ)", "")}
              </button>
            ))}
          {!meta?.present_ids.length && <span className="muted">—</span>}
        </div>
      </div>
      </>}
      <div
        className="story-scroll"
        role="region" aria-label="История" tabIndex={0}
        ref={scroll}
        onScroll={onScroll}
      >
        <div
          className="story"
          style={{
            maxWidth: prefs.reading_width,
            fontSize: prefs.font_size,
            lineHeight: prefs.line_height,
          }}
        >
      {!!save?.state.world_clock?.nearby?.length&&<details className="skip-diagnostics"><summary>Ближайшие даты</summary><p className="muted small">Дата в календаре не означает, что запланировано празднование.</p>{save.state.world_clock.nearby.map(e=><p key={e.id}>{calendarDate(e.date)} · {e.kind==='birthday'?`День рождения: ${e.character_ids.map(id=>save.state.characters.find(c=>c.id===id)?.name||id).join(', ')}`:e.name}</p>)}</details>}
      {save?.state.last_long_term_advance&&<details className="skip-diagnostics" open><summary>Длительный переход{save.state.last_long_term_advance.interruption?' · прерван':''}</summary>
        <p>Обращений к модели: {save.state.last_long_term_advance.llm_calls} / {save.state.last_long_term_advance.max_llm_calls}. Нерешённых причин: {save.state.last_long_term_advance.unresolved.length}.</p>
        {save.state.last_long_term_advance.accepted.length>0&&<><strong>События вне сцены — сведения для игрока</strong><p>Герой не узнаёт эти сведения автоматически.</p><ul>{save.state.last_long_term_advance.accepted.flatMap(g=>g.summaries).map((text,i)=><li key={i}>{text}</li>)}</ul></>}
        {save.state.last_long_term_advance.decisions.length>0&&<><strong>Требуется твоё решение</strong><ul>{save.state.last_long_term_advance.decisions.map(c=><li key={c.id}>{c.context||'Есть нерешённая возможность или обязательство героя.'}{c.domains?.length?` — ${c.domains.map(advanceDomainLabel).join(', ')}`:''}</li>)}</ul><p>Продолжи обычный ход, чтобы принять решение.</p></>}
      </details>}
      {save?.state.last_time_skip&&<details className="skip-diagnostics"><summary>Пропуск времени: {save.state.last_time_skip.elapsed_minutes} мин{save.state.last_time_skip.interrupted?' · прерван':''}</summary><p>Запрошено: {save.state.last_time_skip.requested_duration} мин · Кандидатов: {save.state.last_time_skip.background_candidates} · Симуляций: {save.state.last_time_skip.simulated_candidates||0} · Объединено: {save.state.last_time_skip.merged_candidates||0} · Пропущено: {save.state.last_time_skip.skipped_candidates||0} · LLM мира: {save.state.last_time_skip.living_world_llm_calls||0}</p></details>}
          {save&&mobile&&<details className="mobile-story-tools"><summary>Диагностика</summary><Button size="sm" variant="ghost" onClick={()=>{setDiagnosticJob(undefined);setDiagnostics(true)}}>Диагностика</Button></details>}{save&&!mobile&&<Button className="story-diagnostics" size="sm" variant="ghost" onClick={()=>{setDiagnosticJob(undefined);setDiagnostics(true)}}>Диагностика</Button>}
          <div className="story-heading">
            <SkinHeader pack={decoration}/>
            <p className="eyebrow">
              {save ? save.name : "Начало истории"}
            </p>
            <h1 title={world.name}>{world.name}</h1>
            <div className="chapter-rule" aria-hidden="true">✦</div>
          </div>
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
              {entries.map(e=>renderEntry(e))}
              {!save.turns.length && !job && (
                <div className="empty-state">
                  <p>
                    Всё готово. Начни историю — ведущий разыграет первую сцену.
                  </p>
                </div>
              )}
              {unapplied && (!job?.presentation||job.presentation.surface==='physical') && <p role="status">{job?.kind==='communication'?'Действие связи сохранено. Повтори обработку, чтобы завершить цикл.':'Текст сцены сохранён, состояние ещё не применено. Повтори обработку состояния.'}</p>}
              {job && (!job.presentation||job.presentation.surface==='physical') &&
                ["error", "stopped"].includes(job.status) &&
                job.narrative_complete &&
                job.revision === save.revision && (
                  <Button
                    variant="outline"
                    disabled={busy || job.live}
                    onClick={() =>
                      run(async () => {
                        const j = await api<Job>(`/jobs/${job.id}/retry`, {
                          config: prefs.game,
                          api_key: apiKey,
                        });
                        setSubmitted(j);
                      })
                    }
                  >
                    Повторить обработку состояния
                  </Button>
                )}
              {!save.turns.length && !pending && (
                <Button size="lg" disabled={busy} onClick={() => turn("start")}>
                  Начать игру
                </Button>
              )}
              {save.turns.length > 0 && (
                <>
                  {actorId===null&&<div className="background-exit">
                    <Button variant="outline" disabled={busy||pending} onClick={()=>observe(undefined,save.state.camera?.scene_id)}>Продолжить наблюдать</Button>
                    <Button disabled={busy||pending} onClick={()=>switchActor(mainActor!)}>Вернуться к {save.state.characters.find(c=>c.id===mainActor)?.name.replace(' (ГГ)','')}</Button>
                    <label>Продолжить за персонажа…<select aria-label="Участник фоновой сцены" value="" disabled={busy||pending} onChange={e=>switchActor(e.target.value,save.turns.at(-1)!.id)}><option value="">Выбрать участника</option>{save.state.characters.filter(c=>JSON.parse(save.turns.at(-1)?.audience_json||'[]').includes(c.id)).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
                  </div>}
                  {save.state.actor_capabilities?.can_act===false&&<div><p role="status">Персонаж сейчас не может действовать. Можно продолжить течение времени или наблюдать за миром.</p>{actorId&&<Button disabled={busy||pending} onClick={()=>observe(actorId)}>Продолжить наблюдать за героем</Button>}</div>}
                  <motion.div aria-label="Варианты действия" role="group" className="choices" key={choiceKey} variants={choicesMotion} initial={reduced||initialChoice.current===choiceKey?false:"hidden"} animate="visible">
                    {(save.state.actor_capabilities?.can_act!==false&&(choiceTurn?.pov_actor_id||mainActor)===actorId?choiceTurn?.choices:[])?.filter(c=>(c.interaction_channel||"physical")==="physical").map((c, i) => (
                      <motion.button
                        variants={choiceMotion}
                        className={selectedChoice===i?"choice-selected":""}
                        key={i}
                        disabled={!canSubmit}
                        onClick={() => {
                          setSelectedChoice(i); void turn(
                            "turn",
                            c.action + (c.speech ? `: «${c.speech}»` : ""),
                          );}
                        }
                      >
                        <span className="choice-index" aria-hidden="true">{String(i + 1).padStart(2,"0")}</span>
                        <span className="choice-copy">
                          <strong>{c.action}</strong>
                          {c.speech && <span className="choice-speech">«{c.speech}»</span>}
                        </span>
                      </motion.button>
                    ))}
                  </motion.div>
                  {!pending&&entries.at(-1)?.turn.id===save.turns.at(-1)?.id&&<div className="turn-actions">
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label="Перегенерировать последний ход"
                      disabled={busy||!save.turns.at(-1)?.variants?.some(v=>v.can_regenerate)}
                      onClick={() => turn("regenerate", "")}
                    >
                      <RotateCcw size={14} />
                      <span className="regenerate-long">Перегенерировать последний ход</span><span className="regenerate-short" aria-hidden="true">Ещё вариант</span>
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
        <div className="composer">
          <Phone save={save} onBusyChange={setPhoneBusy} disabled={busy||pending} onCommit={refreshControl} config={prefs.game} apiKey={apiKey} onJob={setSubmitted} job={job}/>
          <form className="composer-inner" onSubmit={e=>{e.preventDefault();if(canSubmit&&draft.trim())void turn("turn")}}>
            <Textarea
              ref={input}
              rows={1}
              aria-describedby="narrative-composer-hint"
              aria-label="Своё действие или реплика"
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                sessionStorage.setItem(draftKey, e.target.value);
              }}
              disabled={!canAct}
              placeholder={activeCall?"Физическая сцена: что ты делаешь рядом?":actorId===null?"Камера наблюдает мир — выбери персонажа для управления":"Что ты делаешь или говоришь?"}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  (e.ctrlKey || e.metaKey) &&
                  !e.nativeEvent.isComposing &&
                  canSubmit &&
                  draft.trim()
                ) {
                  e.preventDefault();
                  turn("turn");
                }
              }}
            />
            <Button
              aria-label="Отправить действие"
              size="icon"
              disabled={!canSubmit || !draft.trim()}
              type="submit"
            >
              <Send size={19} />
            </Button>
          </form>
          <div className="composer-footer">
            <span id="narrative-composer-hint">Свободное действие <kbd>Ctrl / ⌘ + Enter</kbd></span>
            {away&&<button
              onClick={jumpToLatest}
            >
              <ArrowDown size={13} />К последней сцене
            </button>}
          </div>
        </div>
      )}
    </main>
  );
}
