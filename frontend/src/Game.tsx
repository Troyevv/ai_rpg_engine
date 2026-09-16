import { useEffect, useRef, useState } from "react";
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
import { JobView } from "./JobView";
import { Button } from "./components/ui/button";
import { Textarea } from "./components/ui/textarea";
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
  const mobile=useMobile();
  const [away,setAway]=useState(false);
  const input=useRef<HTMLTextAreaElement>(null);
  const mainActor=save?.state.protagonist_id||save?.state.characters.find(c=>c.is_player)?.id;
  const actorId=save?.state.controlled_actor_id===undefined?mainActor:save.state.controlled_actor_id;
  const [cameraOpen,setCameraOpen]=useState(false);
  const draftKey=`draft-${save?.id}-${actorId}`;
  const [diagnostics, setDiagnostics] = useState(false);
  const [diagnosticJob, setDiagnosticJob] = useState<string|undefined>();
  const [draft, setDraft] = useState("");
  const draftRef=useRef(draft);draftRef.current=draft;
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState<Job | null>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const reduced = useReducedMotion();
  useEffect(() => {
    setDraft(sessionStorage.getItem(draftKey) || "");
    setSubmitted(null);
    pinned.current = true;
  }, [save?.id,actorId]);
  const { job, reconnecting } = useJob(submitted ?? save?.job, refresh);
  const awaitingCommit=job?.status==='saved'&&job.revision===save?.revision&&!save?.turns.some(t=>t.variants?.some(v=>v.job_id===job.id));
  const pending = active(job)||!!awaitingCommit;
  useEffect(()=>{if(submitted&&save?.job?.id===submitted.id&&!active(save.job))setSubmitted(null)},[save?.job,submitted]);
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      if (scroll.current && pinned.current)
        scroll.current.scrollTop = scroll.current.scrollHeight;
    });
    return () => cancelAnimationFrame(id);
  }, [job?.narrative, save?.turns.length]);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      toast.error((e as Error).message);
      refresh();
    } finally {
      setBusy(false);
    }
  };
  const turn = (kind: "start" | "turn" | "regenerate" | "background", text = draft, target?:number, rollback=false) =>
    run(async () => {
      if (!save) return;
      const j = await api<Job>(`/saves/${save.id}/turns`, {
        kind,
        text,
        target_turn_id: target,
        rollback_following: rollback,
        config: prefs.game,
        revision: save.revision,
        api_key: apiKey,
      });
      setSubmitted(j);
      pinned.current = true;
      if (kind === "turn" && text === draftRef.current) {
        setDraft("");
        sessionStorage.removeItem(draftKey);
      }
    });
  const switchActor=(actor:string,source?:number)=>void run(async()=>{
    if(!save)return;
    const j=await api<Job>(`/saves/${save.id}/actor`,{actor_id:actor,source_turn_id:source,revision:save.revision,config:prefs.game,api_key:apiKey});
    setSubmitted(j);pinned.current=true;setAway(false);
  });
  const observe=(actor?:string,scene?:string)=>void run(async()=>{
    if(!save)return;
    const j=await api<Job>(`/saves/${save.id}/camera`,{actor_id:actor,scene_id:scene,revision:save.revision,config:prefs.game,api_key:apiKey});
    setSubmitted(j);pinned.current=true;setAway(false);
  });
  useEffect(()=>{if(!mobile||!input.current)return;const el=input.current;el.style.height='auto';el.style.height=Math.min(el.scrollHeight,132)+'px'},[draft,mobile]);
  useEffect(()=>{if(!scroll.current)return;const observer=new ResizeObserver(()=>{if(pinned.current&&scroll.current)scroll.current.scrollTop=scroll.current.scrollHeight});const story=scroll.current.firstElementChild;if(story)observer.observe(story);return()=>observer.disconnect()},[world?.id,save?.id]);
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
      {save&&<WorldCamera save={save} open={cameraOpen} onOpenChange={setCameraOpen} busy={busy||pending} observe={observe} control={switchActor}/>}
      {save&&<Diagnostics saveId={save.id} jobId={diagnosticJob} open={diagnostics} onOpenChange={setDiagnostics}/>}
      {mobile&&save?<MobileScene save={save} meta={meta} busy={busy||pending} switchActor={switchActor} background={()=>void turn("background","")} openCharacter={openCharacter} openCamera={()=>setCameraOpen(true)}/>:<>{save&&<div className="pov-controls">
        <label>Управляемый персонаж<select aria-label="Управляемый персонаж" value={actorId||""} disabled={busy||pending} onChange={e=>switchActor(e.target.value)}>{!actorId&&<option value="">Камера наблюдателя</option>}{save.state.characters.map(c=><option key={c.id} value={c.id}>{c.name}{c.id===mainActor?" · основной герой":""}</option>)}</select></label>
        {actorId!==mainActor&&<Button variant="ghost" size="sm" disabled={busy||pending} onClick={()=>switchActor(mainActor!)}>Вернуться к {save.state.characters.find(c=>c.id===mainActor)?.name.replace(" (ГГ)","")}</Button>}
        <Button variant="ghost" size="sm" onClick={()=>setCameraOpen(true)}>Камера · Журнал</Button>
        <Button variant="outline" size="sm" disabled={busy||pending||!save.turns.length} onClick={()=>void turn("background","")}>Мир без ГГ</Button>
      </div>}
      <div className="scene-bar">
        <span>
          <Clock size={14} />
          {meta?.time || "Время не указано"}
        </span>
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
        ref={scroll}
        onScroll={() => {
          if (scroll.current){
            pinned.current =
              scroll.current.scrollHeight -
                scroll.current.scrollTop -
                scroll.current.clientHeight <
              80;
            setAway(!pinned.current);
          }
        }}
      >
        <div
          className="story"
          style={{
            maxWidth: prefs.reading_width,
            fontSize: mobile?Math.min(prefs.font_size,18):prefs.font_size,
            lineHeight: mobile?1.65:prefs.line_height,
          }}
        >
          {save&&mobile&&<details className="mobile-story-tools"><summary>Контекст и расходы</summary><Button size="sm" variant="ghost" onClick={()=>{setDiagnosticJob(undefined);setDiagnostics(true)}}>Контекст ведущего · Расходы</Button></details>}{save&&!mobile&&<Button size="sm" variant="ghost" onClick={()=>{setDiagnosticJob(undefined);setDiagnostics(true)}}>Контекст ведущего · Расходы</Button>}
          <div className="story-heading">
            <p className="eyebrow">
              {save ? save.name : "Начало истории"} · Мир v{world.version}
            </p>
            <h1>{world.name}</h1>
            <div className="chapter-rule">✦</div>
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
              {save.turns.map((t, i) => (
                <motion.article
                  key={t.id}
                  className={`turn ${t.kind==="background"?"background-turn":""}`}
                  initial={reduced ? false : { opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.22 }}
                >
                  {t.user_text && (
                    <div className="player-action" data-testid="player-action">
                      <span className="eyebrow">Твоё действие</span>
                      <Markdown text={t.user_text} />
                    </div>
                  )}
                  <p className="turn-number">
                    {t.kind==="background"?`Тем временем… · За кулисами · ход ${t.sequence}`:i === 0 ? "Первая сцена" : `Ход ${t.sequence}`}
                    {t.kind!=="background"&&<span> · POV: {save.state.characters.find(c=>c.id===(t.pov_actor_id||mainActor))?.name}</span>}
                  </p>
                  <Markdown
                    text={t.assistant_text}
                    saveId={save.id}
                    worldId={world.id}
                    links={prefs.link_names}
                    onCharacter={openCharacter}
                  />
                  {mobile?<div className="mobile-variants">
                    <Button size="icon" variant="ghost" aria-label="Ещё вариант" disabled={busy||pending||!t.variants?.some(v=>v.can_regenerate)} onClick={()=>{const later=i<save.turns.length-1;if(later&&!window.confirm('Откатить следующие ходы в архив?'))return;void turn('regenerate','',t.id,later)}}>↻</Button>
                    {[-1,1].map((step)=>{const list=t.variants||[];const index=list.findIndex(v=>v.id===t.active_variant_id);const v=list[index+step];return <span className="variant-step" key={step}>{step===1&&<span>{index+1} / {list.length||1}</span>}<Button size="icon" variant="ghost" aria-label={step<0?'Предыдущий вариант':'Следующий вариант'} disabled={busy||pending||!v} onClick={()=>{const later=i<save.turns.length-1;if(later&&!window.confirm('Откатить следующие ходы в архив?'))return;void run(async()=>{await api(`/saves/${save.id}/turns/${t.id}/variant`,{variant_id:v.id,revision:save.revision,rollback_following:later});setSubmitted(null);refresh()})}}>{step<0?'‹':'›'}</Button></span>})}
                    <Button size="icon" variant="ghost" aria-label="Контекст / usage" onClick={()=>{setDiagnosticJob(t.variants?.find(v=>v.id===t.active_variant_id)?.job_id||undefined);setDiagnostics(true)}}>⋯</Button>
                  </div>:<div className="variant-controls">
                    <span className="muted small">Вариант {(t.variants||[]).find(v=>v.id===t.active_variant_id)?.ordinal||1} / {t.variants?.length||1}</span>
                    {(t.variants||[]).map(v=><Button key={v.id} size="sm" variant={v.id===t.active_variant_id?"outline":"ghost"} disabled={busy||pending||v.id===t.active_variant_id} onClick={()=>{
                      const later = i<save.turns.length-1;
                      if(later&&!window.confirm("Смена варианта откатит все последующие ходы. Они сохранятся в архиве. Продолжить?"))return;
                      void run(async()=>{await api(`/saves/${save.id}/turns/${t.id}/variant`,{variant_id:v.id,revision:save.revision,rollback_following:later});setSubmitted(null);refresh()});
                    }}>{v.ordinal}</Button>)}
                    <Button size="sm" variant="ghost" title={t.variants?.some(v=>v.can_regenerate) ? "" : "У старого хода нет сохранённого контекста"} disabled={busy||pending||!t.variants?.some(v=>v.can_regenerate)} onClick={()=>{
                      const later=i<save.turns.length-1;
                      if(later&&!window.confirm("После успешной генерации последующие ходы будут откачены в архив. Продолжить?"))return;
                      void turn("regenerate","",t.id,later);
                    }}>Ещё вариант</Button>
                    <Button size="sm" variant="ghost" onClick={()=>{setDiagnosticJob(t.variants?.find(v=>v.id===t.active_variant_id)?.job_id||undefined);setDiagnostics(true)}}>Контекст / usage</Button>
                    {!!t.memory_archived&&<span className="muted small">В архиве памяти · полный текст сохранён</span>}
                  </div>}
                </motion.article>
              ))}
              {!save.turns.length && !job && (
                <div className="empty-state">
                  <p>
                    Всё готово. Ведущий разыграет первую сцену и предложит шесть
                    действий.
                  </p>
                </div>
              )}
              <JobView
                job={awaitingCommit&&job?{...job,status:"validating"}:job}
                reconnecting={reconnecting}
                worldId={world.id}
                saveId={save.id}
                onCharacter={openCharacter}
                links={prefs.link_names}
                stop={() =>
                  run(async () => {
                    await api(`/jobs/${job!.id}/stop`, {});
                    setSubmitted(null);
                    refresh();
                  })
                }
              />
              {job &&
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
              {save.turns.length > 0 && !pending && (
                <>
                  {actorId===null&&<div className="background-exit">
                    <Button variant="outline" disabled={busy} onClick={()=>observe(undefined,save.state.camera?.scene_id)}>Продолжить наблюдать</Button>
                    <Button disabled={busy} onClick={()=>switchActor(mainActor!)}>Вернуться к {save.state.characters.find(c=>c.id===mainActor)?.name.replace(' (ГГ)','')}</Button>
                    <label>Продолжить за персонажа…<select aria-label="Участник фоновой сцены" value="" disabled={busy} onChange={e=>switchActor(e.target.value,save.turns.at(-1)!.id)}><option value="">Выбрать участника</option>{save.state.characters.filter(c=>JSON.parse(save.turns.at(-1)?.audience_json||'[]').includes(c.id)).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
                  </div>}
                  <div className="choices">
                    {(save.turns.at(-1)?.kind!=="background"&&(save.turns.at(-1)?.pov_actor_id||mainActor)===actorId?save.turns.at(-1)?.choices:[])?.map((c, i) => (
                      <button
                        key={i}
                        disabled={busy}
                        onClick={() =>
                          turn(
                            "turn",
                            c.action + (c.speech ? `: «${c.speech}»` : ""),
                          )
                        }
                      >
                        <span className="choice-index">0{i + 1}</span>
                        <span>
                          <strong>{c.action}</strong>
                          {c.speech && <>: «{c.speech}»</>}
                        </span>
                      </button>
                    ))}
                  </div>
                  <div className="turn-actions">
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busy||!save.turns.at(-1)?.variants?.some(v=>v.can_regenerate)}
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
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>
      {save && (
        <div className="composer">
          <div className="composer-inner">
            <Textarea
              ref={input}
              rows={1}
              aria-label="Своё действие или реплика"
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                sessionStorage.setItem(draftKey, e.target.value);
              }}
              disabled={actorId===null}
              placeholder={actorId===null?"Камера наблюдает мир — выбери персонажа для управления":"Что ты делаешь или говоришь?"}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  (e.ctrlKey || e.metaKey) &&
                  actorId !== null &&
                  !pending &&
                  !busy &&
                  save.turns.length &&
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
              disabled={actorId===null || busy || pending || !save.turns.length || !draft.trim()}
              onClick={() => turn("turn")}
            >
              <Send size={19} />
            </Button>
          </div>
          <div className="composer-footer">
            <span>Твоё действие всегда важнее предложенных вариантов.</span>
            {away&&<button
              onClick={() => {
                pinned.current = true;setAway(false);
                scroll.current?.scrollTo({
                  top: scroll.current.scrollHeight,
                  behavior: "smooth",
                });
              }}
            >
              <ArrowDown size={13} />К последней сцене
            </button>}
          </div>
        </div>
      )}
    </main>
  );
}
