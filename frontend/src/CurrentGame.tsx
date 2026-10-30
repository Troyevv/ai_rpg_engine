import { CommunicationSettings } from "./CommunicationSettings";
import { WeatherSettings } from "./WeatherSettings";
import { useEffect, useState, useRef } from "react";
import {
  Settings2,
  Clock,
  Users,
  History,
  ArrowRight,
  Search,
  Hourglass,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "./components/ui/dialog";
import { SectionTabs } from "./components/ui/section-tabs";
import { Button } from "./components/ui/button";
import { CharacterAvatar } from "./Portrait";
import { worldTime } from "./lib/worldTime";
import { formatDateLabel, profileDate } from "./gameDate";
import { SceneClock } from "./SceneClock";
import { api } from "./api";
import type { Save } from "./types";
import "./styles/current-game.css";
import "./styles/game-management.css";

type Milestone = {
  id: string;
  summary: string;
  minute: number | null;
  date: string | null;
  actor_ids: string[];
  category: string;
};
function Chronology({ save }: { save: Save }) {
  const [actor, setActor] = useState("");
  const [page, setPage] = useState(0);
  const [retry, setRetry] = useState(0);
  const [result, setResult] = useState<{
    key: string;
    rows: Milestone[];
  } | null>(null);
  const [failure, setFailure] = useState<{
    key: string;
    message: string;
  } | null>(null);
  const key = `${save.id}:${save.revision}:${save.state.controlled_actor_id}:${actor}:${page}:${retry}`;
  useEffect(() => {
    const controller = new AbortController();
    setResult(null);
    setFailure(null);
    const params = new URLSearchParams({
      limit: "32",
      offset: String(page * 32),
    });
    if (actor) params.set("actor_id", actor);
    api<Milestone[]>(
      `/saves/${save.id}/milestones?${params}`,
      undefined,
      "GET",
      controller.signal,
    )
      .then((rows) => {
        if (!controller.signal.aborted) setResult({ key, rows });
      })
      .catch((e) => {
        if (!controller.signal.aborted) setFailure({ key, message: e.message });
      });
    return () => controller.abort();
  }, [key, save.id, actor, page]);
  const rows = result?.key === key ? result.rows : null;
  const error = failure?.key === key ? failure.message : null;
  const groups = new Map<string, Milestone[]>();
  rows?.forEach((m) => {
    const date = m.date
      ? profileDate(m.date, save.state.world_clock?.calendar?.profile)
      : m.minute !== null
        ? formatDateLabel(worldTime(m.minute, save.state.world_clock?.calendar))
        : "Дата не указана";
    groups.set(date, [...(groups.get(date) || []), m]);
  });
  return (
    <section className="management-stack">
      <header>
        <h3>Хронология</h3>
        <p className="muted">
          Известные события этого прохождения, от новых к ранним.
        </p>
      </header>
      <details className="management-card">
        <summary>История главных героев</summary>
        {save.state.protagonist_periods?.length ? (
          save.state.protagonist_periods.map((p: any, i: number) => (
            <p key={i}>
              <strong>
                {save.state.characters.find((c) => c.id === p.actor_id)?.name ||
                  "Персонаж"}
              </strong>
              <br />
              {p.since != null
                ? formatDateLabel(
                    worldTime(p.since, save.state.world_clock?.calendar),
                  )
                : "Дата не указана"}
              {p.until != null
                ? ` → ${formatDateLabel(worldTime(p.until, save.state.world_clock?.calendar))}`
                : " · по настоящее время"}
            </p>
          ))
        ) : (
          <p className="muted">Смена главного героя пока не записана.</p>
        )}
      </details>
      <label className="management-field">
        События персонажа
        <select
          value={actor}
          onChange={(e) => {
            setActor(e.target.value);
            setPage(0);
          }}
        >
          <option value="">Все доступные события</option>
          {save.state.characters.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      {error ? (
        <div className="management-state" role="alert">
          <p>{error}</p>
          <Button variant="outline" onClick={() => setRetry((v) => v + 1)}>
            Повторить загрузку
          </Button>
        </div>
      ) : !rows ? (
        <p role="status" className="management-state">
          Загрузка хронологии…
        </p>
      ) : rows.length ? (
        <div className="management-timeline">
          {Array.from(groups, ([date, events]) => (
            <section key={date}>
              <h4>{date}</h4>
              {events.map((m) => (
                <article key={m.id}>
                  {m.summary.length > 180 ? (
                    <details>
                      <summary>{m.summary.slice(0, 160)}…</summary>
                      <p>{m.summary}</p>
                    </details>
                  ) : (
                    <p>{m.summary}</p>
                  )}
                </article>
              ))}
            </section>
          ))}
        </div>
      ) : (
        <p className="management-state">
          Известных вех нет{actor ? " для этого персонажа" : ""}.
        </p>
      )}
      <div className="management-pagination">
        <Button
          variant="outline"
          disabled={!page}
          onClick={() => setPage((v) => v - 1)}
        >
          Более новые
        </Button>
        <span>Страница {page + 1}</span>
        <Button
          variant="outline"
          disabled={!rows || rows.length < 32}
          onClick={() => setPage((v) => v + 1)}
        >
          Более ранние
        </Button>
      </div>
    </section>
  );
}
const tabs = [
  { id: "time", label: "Время", icon: <Clock size={17} /> },
  { id: "characters", label: "Персонажи", icon: <Users size={17} /> },
  { id: "history", label: "Хронология", icon: <History size={17} /> },
  { id: "settings", label: "Настройки", icon: <Settings2 size={17} /> },
];
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
  const pendingAction = useRef<(() => void) | null>(null);
  const [open, setOpen] = useState(false),
    [tab, setTab] = useState("time"),
    [query, setQuery] = useState("");
  useEffect(() => {
    setOpen(false);
    setQuery("");
  }, [save.id]);
  // A successful settings commit temporarily disables commands while the new
  // revision loads. Keep this read surface (and its confirmation) mounted.
  // Individual mutation controls retain their disabled guards.
  const act = (fn: () => void) => {
    pendingAction.current = fn;
    setOpen(false);
  };
  const blocked =
    disabled || !save.turns.length || !!save.state.protagonist_required;
  const main = save.state.characters.find(
    (c) => c.id === save.state.protagonist_id,
  );
  const characters = save.state.characters.filter((c) =>
    c.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()),
  );
  return (
    <>
      <div className="current-game-entry">
        <Button
          ref={trigger}
          variant="outline"
          onClick={() => {
            pendingAction.current = null;
            setOpen(true);
          }}
        >
          <Settings2 size={16} />
          Управление игрой
        </Button>
      </div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          className="current-game-panel"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            const action = pendingAction.current;
            pendingAction.current = null;
            if (action) action();
            else trigger.current?.focus();
          }}
        >
          <header className="management-header">
            <span className="management-kicker">Управление прохождением</span>
            <DialogTitle>Текущая игра</DialogTitle>
            <DialogDescription>
              Время, персонажи и настройки этого прохождения.
            </DialogDescription>
          </header>
          <SectionTabs
            items={tabs}
            value={tab}
            onChange={setTab}
            label="Разделы текущей игры"
            className="management-tabs"
            tablist
            panelId="management-panel"
          />
          <div
            className="current-game-content"
            id="management-panel"
            role="tabpanel"
            tabIndex={0}
            aria-labelledby={`management-panel-tab-${tab}`}
          >
            {tab === "time" && (
              <section className="management-stack">
                <div className="management-clock">
                  <span className="management-kicker">Сейчас в мире</span>
                  <SceneClock save={save} />
                  <p>{save.state.scene_meta?.location || "Место не указано"}</p>
                </div>
                <div className="management-time-options">
                  <article className="management-card">
                    <Clock className="management-icon" />
                    <h3>Пропустить время</h3>
                    <p>
                      Подождать до нужного часа или дня. Мир продолжит жить, а
                      важное событие может прервать ожидание.
                    </p>
                    <Button disabled={blocked} onClick={() => act(timeSkip)}>
                      Пропустить время <ArrowRight size={16} />
                    </Button>
                  </article>
                  <article className="management-card">
                    <Hourglass className="management-icon" />
                    <h3>Длительный переход</h3>
                    <p>
                      Перейти на недели, месяцы или годы вперёд. Обязательства
                      сохраняются; решения героя остаются за тобой.
                    </p>
                    <Button
                      variant="outline"
                      disabled={blocked}
                      onClick={() => act(longTerm)}
                    >
                      Длительный переход <ArrowRight size={16} />
                    </Button>
                  </article>
                </div>
                {blocked && (
                  <p role="status" className="management-state">
                    {save.state.protagonist_required
                      ? "Выбери нового главного героя, чтобы продолжить."
                      : !save.turns.length
                        ? "Начни историю, чтобы открыть переходы времени."
                        : "Дождись завершения текущего действия."}
                  </p>
                )}
              </section>
            )}
            {tab === "history" && (
              <Chronology
                key={`${save.id}:${save.state.controlled_actor_id}`}
                save={save}
              />
            )}
            {tab === "settings" && (
              <section className="management-stack">
                <article className="management-card management-setting">
                  <div>
                    <h3>История</h3>
                    <p>
                      Интенсивность, риск последствий и предпочтение исходов
                      влияют только на будущие события.
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    disabled={disabled}
                    onClick={() => act(policy)}
                  >
                    Политика истории <ArrowRight size={16} />
                  </Button>
                </article>
                <label className="management-card management-toggle">
                  <span>
                    <strong>Показывать изменения отношений</strong>
                    <small>Уведомления об изменениях во время игры.</small>
                  </span>
                  <input
                    type="checkbox"
                    role="switch"
                    checked={notices}
                    onChange={(e) => onNotices(e.target.checked)}
                  />
                </label>
                <div className="management-card">
                  <CommunicationSettings
                    value={save.state.communication_profile || null}
                  />
                </div>
                <div className="management-card management-weather">
                  <WeatherSettings save={save} refresh={refresh} disabled={disabled} />
                </div>
              </section>
            )}
            {tab === "characters" && (
              <section className="management-stack">
                <div className="management-card">
                  <span className="management-kicker">Главный герой</span>
                  <h3>{main?.name || "Не выбран"}</h3>
                  <div className="current-game-actions">
                    <Button
                      disabled={disabled}
                      onClick={() => act(protagonist)}
                    >
                      Сменить главного героя
                    </Button>
                    <Button
                      variant="outline"
                      disabled={disabled}
                      onClick={() => act(camera)}
                    >
                      Наблюдение и временное управление
                    </Button>
                  </div>
                </div>
                <label className="management-search">
                  <Search size={18} />
                  <input
                    aria-label="Поиск персонажей"
                    type="search"
                    placeholder="Найти персонажа по имени"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </label>
                <p className="muted" role="status">
                  {query
                    ? `Найдено: ${characters.length}`
                    : `Персонажи: ${characters.length}`}
                </p>
                <div className="current-character-list">
                  {characters.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => act(() => openCharacter(c.id))}
                    >
                      <CharacterAvatar subject={c} saveId={save.id} size={44} />
                      <span>
                        <strong>{c.name}</strong>
                        <small>
                          {c.id === save.state.protagonist_id
                            ? "Главный герой"
                            : c.id === save.state.controlled_actor_id
                              ? "Под управлением игрока"
                              : "Открыть карточку"}
                        </small>
                      </span>
                      <ArrowRight size={16} />
                    </button>
                  ))}
                </div>
                {!characters.length && (
                  <div className="management-state">
                    <p>
                      {query
                        ? "Персонажи не найдены. Попробуй другое имя."
                        : "Нет доступных персонажей."}
                    </p>
                    {query && (
                      <Button variant="outline" onClick={() => setQuery("")}>
                        Сбросить поиск
                      </Button>
                    )}
                  </div>
                )}
              </section>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
