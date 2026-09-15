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
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState<Job | null>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const reduced = useReducedMotion();
  useEffect(() => {
    setDraft(sessionStorage.getItem(`draft-${save?.id}`) || "");
    setSubmitted(null);
    pinned.current = true;
  }, [save?.id]);
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
  const turn = (kind: "start" | "turn" | "regenerate", text = draft) =>
    run(async () => {
      if (!save) return;
      const j = await api<Job>(`/saves/${save.id}/turns`, {
        kind,
        text,
        config: prefs.game,
        revision: save.revision,
        api_key: apiKey,
      });
      setSubmitted(j);
      pinned.current = true;
      if (kind === "turn" && text === draft) {
        setDraft("");
        sessionStorage.removeItem(`draft-${save.id}`);
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
                    <div className="player-action">
                      <span className="eyebrow">Твоё действие</span>
                      <Markdown text={t.user_text} />
                    </div>
                  )}
                  <p className="turn-number">
                    {i === 0 ? "Первая сцена" : `Ход ${t.sequence}`}
                  </p>
                  <Markdown
                    text={t.assistant_text}
                    saveId={save.id}
                    worldId={world.id}
                    links={prefs.link_names}
                    onCharacter={openCharacter}
                  />
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
                    {save.turns.at(-1)?.choices.map((c, i) => (
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
                      disabled={busy}
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
                sessionStorage.setItem(`draft-${save.id}`, e.target.value);
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
