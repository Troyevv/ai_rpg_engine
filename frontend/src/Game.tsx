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
  const mainActor=save?.state.protagonist_id||save?.state.characters.find(c=>c.is_player)?.id;
  const actorId=save?.state.controlled_actor_id||mainActor;
  const draftKey=`draft-${save?.id}-${actorId}`;
  const [diagnostics, setDiagnostics] = useState(false);
  const [diagnosticJob, setDiagnosticJob] = useState<string|undefined>();
  const [draft, setDraft] = useState("");
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
  const { job, reconnecting } = useJob(submitted ?? save?.job, () => {
    setSubmitted(null);
    refresh();
  });
  const pending = active(job);
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
      if (kind === "turn" && text === draft) {
        setDraft("");
        sessionStorage.removeItem(draftKey);
      }
    });
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
      {save&&<Diagnostics saveId={save.id} jobId={diagnosticJob} open={diagnostics} onOpenChange={setDiagnostics}/>}
      {save&&<div className="pov-controls">
        <label>Управляемый персонаж<select aria-label="Управляемый персонаж" value={actorId||""} disabled={busy||pending} onChange={e=>void run(async()=>{await api(`/saves/${save.id}/actor`,{actor_id:e.target.value,revision:save.revision});setSubmitted(null);refresh()})}>{save.state.characters.map(c=><option key={c.id} value={c.id}>{c.name}{c.id===mainActor?" · основной герой":""}</option>)}</select></label>
        {actorId!==mainActor&&<Button variant="ghost" size="sm" disabled={busy||pending} onClick={()=>void run(async()=>{await api(`/saves/${save.id}/actor`,{actor_id:mainActor,revision:save.revision});refresh()})}>Вернуться к основному ГГ</Button>}
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
      <div
        className="story-scroll"
        ref={scroll}
        onScroll={() => {
          if (scroll.current)
            pinned.current =
              scroll.current.scrollHeight -
                scroll.current.scrollTop -
                scroll.current.clientHeight <
              180;
        }}
      >
        <div
          className="story"
          style={{
            maxWidth: prefs.reading_width,
            fontSize: prefs.font_size,
            lineHeight: prefs.line_height,
          }}
        >
          {save&&<Button size="sm" variant="ghost" onClick={()=>{setDiagnosticJob(undefined);setDiagnostics(true)}}>Контекст ведущего · Расходы</Button>}
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
                  className="turn"
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
                    {t.kind==="background"?`За кулисами · ход ${t.sequence} · не знание ГГ`:i === 0 ? "Первая сцена" : `Ход ${t.sequence}`}
                    {t.kind!=="background"&&<span> · POV: {save.state.characters.find(c=>c.id===(t.pov_actor_id||mainActor))?.name}</span>}
                  </p>
                  <Markdown
                    text={t.assistant_text}
                    saveId={save.id}
                    worldId={world.id}
                    links={prefs.link_names}
                    onCharacter={openCharacter}
                  />
                  <div className="variant-controls">
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
                  </div>
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
                job={job}
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
              aria-label="Своё действие или реплика"
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                sessionStorage.setItem(draftKey, e.target.value);
              }}
              placeholder="Что ты делаешь или говоришь?"
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  (e.ctrlKey || e.metaKey) &&
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
              disabled={busy || pending || !save.turns.length || !draft.trim()}
              onClick={() => turn("turn")}
            >
              <Send size={19} />
            </Button>
          </div>
          <div className="composer-footer">
            <span>Твоё действие всегда важнее предложенных вариантов.</span>
            <button
              onClick={() => {
                pinned.current = true;
                scroll.current?.scrollTo({
                  top: scroll.current.scrollHeight,
                  behavior: "smooth",
                });
              }}
            >
              <ArrowDown size={13} />К последней сцене
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
