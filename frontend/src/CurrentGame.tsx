import { WeatherSettings } from "./WeatherSettings";
import { useEffect, useState, useRef } from "react";
import {
  Settings2,
  Clock,
  Users,
  History,
  CalendarDays,
  GitBranch,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "./components/ui/dialog";
import { Button } from "./components/ui/button";
import { worldTime } from "./lib/worldTime";
import { formatDateLabel } from "./gameDate";
import { SceneClock } from "./SceneClock";
import { api } from "./api";
import type { Save } from "./types";
import "./styles/current-game.css";
function Chronology({ save }: { save: Save }) {
  const [data, setData] = useState<any>(null),
    [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    api<any>(`/saves/${save.id}/milestones?limit=32`)
      .then((d) => {
        if (live) setData(d);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [save.id, save.revision]);
  return (
    <section>
      <h3>История главных героев</h3>
      {save.state.protagonist_periods?.map((p: any, i: number) => (
        <p key={i}>
          {save.state.characters.find((c) => c.id === p.actor_id)?.name ||
            "Персонаж"}{" "}
          · {p.since != null ? formatDateLabel(worldTime(p.since, save.state.world_clock?.calendar)) : "—"}
          {p.until != null ? ` → ${formatDateLabel(worldTime(p.until, save.state.world_clock?.calendar))}` : ""}
        </p>
      ))}
      <h3>Вехи</h3>
      {error ? (
        <p role="alert">{error}</p>
      ) : !data ? (
        <p>Загрузка…</p>
      ) : (data || []).length ? (
        (data || []).map((m: any) => (
          <article key={m.id}>
            <strong>{m.summary || m.text || m.description}</strong>
          </article>
        ))
      ) : (
        <p className="muted">Известных вех нет.</p>
      )}
    </section>
  );
}
export function CurrentGame({
  save,
  timeSkip,
  longTerm,
  notices,
  onNotices,
  policy,
  protagonist,
  camera,
  openCharacter,
  disabled,
  refresh,
}: {
  save: Save;
  timeSkip: () => void;
  longTerm: () => void;
  notices: boolean;
  onNotices: (v: boolean) => void;
  policy: () => void;
  protagonist: () => void;
  camera: () => void;
  openCharacter: (id: string) => void;
  disabled: boolean;
  refresh: (s: Save) => void;
}) {
  const trigger = useRef<HTMLButtonElement>(null);
  const transitioning = useRef(false);
  const [open, setOpen] = useState(false),
    [tab, setTab] = useState("time");
  useEffect(() => setOpen(false), [save.id]);
  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);
  const act = (fn: () => void) => {
    transitioning.current = true;
    setOpen(false);
    fn();
  };
  return (
    <>
      <div className="current-game-entry">
        <Button ref={trigger} variant="outline" onClick={() => { transitioning.current = false; setOpen(true); }}>
          <Settings2 size={16} />
          Управление игрой
        </Button>
      </div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="current-game-panel" onCloseAutoFocus={event => { event.preventDefault(); if (!transitioning.current) trigger.current?.focus(); }}>
          <DialogTitle>Текущая игра</DialogTitle>
          <DialogDescription>
            Время, персонажи и настройки этого прохождения.
          </DialogDescription>
          <nav aria-label="Разделы текущей игры" className="current-game-tabs">
            {(
              [
                ["time", "Время", Clock],
                ["calendar", "Календарь", CalendarDays],
                ["characters", "Персонажи", Users],
                ["family", "Родословная", GitBranch],
                ["history", "Хронология", History],
                ["settings", "Настройки", Settings2],
              ] as const
            ).map(([key, label, Icon]) => (
              <button
                key={key}
                aria-pressed={key === tab}
                onClick={() => {if(key==="calendar"||key==="family"){setOpen(false);window.dispatchEvent(new CustomEvent("save-workspace",{detail:{section:key}}))}else setTab(key)}}
              >
                <Icon size={16} />
                {label}
              </button>
            ))}
          </nav>
          <div className="current-game-content">

              {tab === "time" && (
                <section>
                  <h3>Время мира</h3>
                  <SceneClock save={save} />
                  <div className="current-game-actions">
                    <Button
                      disabled={
                        disabled ||
                        !save.turns.length ||
                        !!save.state.protagonist_required
                      }
                      onClick={() => act(timeSkip)}
                    >
                      Пропустить время
                    </Button>
                    <Button
                      disabled={
                        disabled ||
                        !save.turns.length ||
                        !!save.state.protagonist_required
                      }
                      onClick={() => act(longTerm)}
                    >
                      Длительный переход
                    </Button>
                  </div>
                  <p className="muted">
                    Подробный пропуск времени и длительный переход используют
                    разные механизмы.
                  </p>
                </section>
              )}

              {tab === "history" && <Chronology save={save} />}
              {tab === "settings" && (
                <section>
                  <Button disabled={disabled} onClick={() => act(policy)}>
                    Политика истории
                  </Button>
                  <p className="muted">
                    Интенсивность, риск последствий и предпочтение исходов
                    влияют только на будущие события.
                  </p>
                  <label>
                    <input
                      type="checkbox"
                      checked={notices}
                      onChange={(e) => onNotices(e.target.checked)}
                    />{" "}
                    Показывать изменения отношений
                  </label>
                  <WeatherSettings save={save} refresh={refresh} />
                </section>
              )}
              {tab === "characters" && (
                <section>
                  <p>
                    Главный герой:{" "}
                    {save.state.characters.find(
                      (c) => c.id === save.state.protagonist_id,
                    )?.name || "Не выбран"}
                  </p>
                  <div className="current-game-actions">
                    <Button
                      disabled={disabled}
                      onClick={() => act(protagonist)}
                    >
                      Сменить главного героя
                    </Button>
                    <Button disabled={disabled} onClick={() => act(camera)}>
                      Наблюдение и временное управление
                    </Button>
                  </div>
                  <div className="current-character-list">
                    {save.state.characters.map((c) => (
                      <button
                        key={c.id}
                        onClick={() => act(() => openCharacter(c.id))}
                      >
                        {c.name}
                      </button>
                    ))}
                  </div>
                </section>
              )}

          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
