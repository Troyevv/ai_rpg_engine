import { useEffect, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  CalendarDays,
  Cake,
  Flag,
  Handshake,
  Clock,
  CalendarRange,
} from "lucide-react";
import { DayPicker, DayButton } from "react-day-picker";
import { ru, enUS } from "react-day-picker/locale";
import "react-day-picker/style.css";
import "./styles/game-calendar.css";
import { useWorkspaceView, type WorkspaceView } from "./lib/workspaceView";
import { api } from "./api";
import type { Save } from "./types";
import { calendarDate, profileDate, gameLocale } from "./gameDate";
import { WeatherBadge } from "./SceneClock";
import {
  category,
  statusLabel,
  monthCount,
  monthLength,
  shiftMonth,
  projectionItems,
  itemsOnDay,
  upcomingItems,
  type CalendarProfile,
  type CalendarItem as Item,
  type CalendarProjection as Projection,
} from "./calendarView";
const iso = (d: Date) =>
  `${String(d.getFullYear()).padStart(4, "0")}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parse = (v: string) => {
  const [y, m, d] = v.split("-").map(Number);
  const date = new Date(0);
  date.setFullYear(y, m - 1, d);
  date.setHours(12, 0, 0, 0);
  return date;
};
const weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const weekdayLabels = (profile: CalendarProfile) =>
  profile.weekday_names?.length
    ? profile.weekday_names
    : gameLocale().startsWith("ru")
      ? weekdays
      : ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const icons = {
  birthday: Cake,
  observance: Flag,
  personal: Flag,
  commitment: Handshake,
  scheduled_event: Clock,
  interval: CalendarRange,
};
function EventIcon({ kind }: { kind: string }) {
  const Icon = icons[kind as keyof typeof icons] || CalendarDays;
  return <Icon size={14} aria-hidden="true" />;
}
function itemName(e: Item, save: Save) {
  return e.kind === "birthday"
    ? `День рождения: ${e.name || e.character_ids.map((id) => save.state.characters.find((c) => c.id === id)?.name || "Персонаж").join(", ")}`
    : e.name || category(e.kind);
}
function Markers({
  items,
  save,
  mini = false,
}: {
  items: Item[];
  save: Save;
  mini?: boolean;
}) {
  if (!items.length) return null;
  return (
    <span
      className={`calendar-markers${mini ? " is-mini" : ""}`}
      aria-hidden="true"
    >
      <span className="calendar-event-count">{items.length}</span>
      {!mini &&
        items.slice(0, 2).map((e) => (
          <span className="calendar-event-label" key={e.id} data-kind={e.kind}>
            <EventIcon kind={e.kind} />
            <span>{itemName(e, save)}</span>
          </span>
        ))}
      {!mini && items.length > 2 && (
        <span className="calendar-event-more">Ещё {items.length - 2}</span>
      )}
    </span>
  );
}
function Notices({ data }: { data: Projection }) {
  return (
    <>
      {data.notices.map((n) => (
        <p className="calendar-notice" role="status" key={n}>
          {n}
        </p>
      ))}
      {data.scheduled.truncated && (
        <p className="calendar-notice" role="status">
          Показана часть событий. Список и индикаторы могут быть неполными.
        </p>
      )}
    </>
  );
}
function EventCard({
  item,
  save,
  profile,
}: {
  item: Item;
  save: Save;
  profile?: CalendarProfile;
}) {
  return (
    <article data-status={item.status || "date"} data-kind={item.kind}>
      <small className="calendar-category">
        <EventIcon kind={item.kind} />
        {category(item.kind)}
        {item.window?.exact_time && <time>{item.window.exact_time}</time>}
      </small>
      <strong>{itemName(item, save)}</strong>
      {item.end_date && item.end_date !== item.date && (
        <p>
          {profileDate(item.date, profile)} →{" "}
          {profileDate(item.end_date, profile)}
        </p>
      )}
      {statusLabel(item) && (
        <p className="calendar-event-status">{statusLabel(item)}</p>
      )}
      {item.kind !== "birthday" && item.character_ids.length > 0 && (
        <small>
          {item.character_ids
            .map(
              (id) =>
                save.state.characters.find((c) => c.id === id)?.name ||
                "Персонаж",
            )
            .join(", ")}
        </small>
      )}
    </article>
  );
}
// UI preference only. Never persist events, weather, or other actor-projected data.
function storedView(key: string, today: string, profile?: CalendarProfile) {
  try {
    const v = JSON.parse(localStorage.getItem(key) || "null");
    if (
      v &&
      /^\d{4}-\d{2}-\d{2}$/.test(v.selected) &&
      v.month === v.selected.slice(0, 7) &&
      +v.month.slice(0, 4) > 0 &&
      +v.month.slice(5) <= monthCount(profile) &&
      +v.month.slice(5) > 0 &&
      +v.selected.slice(8) > 0 &&
      +v.selected.slice(8) <= monthLength(v.month, profile)
    )
      return {
        month: v.month as string,
        selected: v.selected as string,
        year: v.year === true,
      };
  } catch {
    /* Storage can be unavailable. In-memory navigation still works. */
  }
  return { month: today.slice(0, 7), selected: today, year: false };
}
export function GameCalendar({
  save,
  viewState,
}: {
  save: Save;
  viewState?: WorkspaceView;
}) {
  const today = save.state.world_clock?.projection?.date || "";
  const profile = (
    save.state.world_clock?.calendar as
      { profile?: CalendarProfile } | undefined
  )?.profile;
  const custom = profile?.system === "custom";
  const storageKey = `calendar-view:${save.id}:${save.state.controlled_actor_id || "none"}`;
  const initial = storedView(storageKey, today, profile);
  const [month, setMonth] = useWorkspaceView(viewState, "month", initial.month),
    [selected, setSelected] = useWorkspaceView(
      viewState,
      "selected",
      initial.selected,
    ),
    [yearView, setYearView] = useWorkspaceView(viewState, "year", initial.year);
  const [retry, setRetry] = useState(0);
  const key = `${save.id}:${save.revision}:${save.state.controlled_actor_id}:${month}:${retry}`;
  const [record, setRecord] = useState<{
    key: string;
    data?: Projection;
    error?: string;
  }>({ key: "" });
  const data = record.key === key ? record.data : undefined,
    error = record.key === key ? record.error : undefined;
  const length = month ? monthLength(month, profile) : 0;
  useEffect(() => {
    try {
      if (today)
        localStorage.setItem(
          storageKey,
          JSON.stringify({ month, selected, year: yearView }),
        );
    } catch {
      /* Optional UI storage. */
    }
  }, [storageKey, month, selected, yearView, today]);
  useEffect(() => {
    if (!month || yearView) return;
    const controller = new AbortController();
    setRecord({ key });
    api<Projection>(
      `/saves/${save.id}/calendar?start_date=${month}-01&end_date=${month}-${String(length).padStart(2, "0")}`,
      undefined,
      undefined,
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted) setRecord({ key, data });
      })
      .catch((e) => {
        if (!controller.signal.aborted) setRecord({ key, error: e.message });
      });
    return () => controller.abort();
  }, [key, month, length, yearView, save.id]);
  if (!today)
    return (
      <p className="calendar-empty">
        Календарная дата не установлена. Относительное время мира сохраняется.
      </p>
    );
  const choose = (date: string) => {
    setMonth(date.slice(0, 7));
    setSelected(date);
    setYearView(false);
  };
  const move = (delta: number) => {
    const next = shiftMonth(month, delta, profile);
    if (next) {
      setMonth(next);
      setSelected(next + "-01");
    }
  };
  const year = +month.slice(0, 4),
    number = +month.slice(5, 7),
    step = yearView ? monthCount(profile) : 1;
  const title = custom
    ? `${profile?.month_names?.[number - 1] || number} · ${year}`
    : calendarDate(month + "-01", "month");
  const items = projectionItems(data),
    onDay = (date: string) => itemsOnDay(items, date);
  const agenda = upcomingItems(items, today);
  const dayLabel = (date: string) =>
    `${profileDate(date, profile)}, событий: ${onDay(date).length}${date === today ? ", сегодня в игре" : ""}${data?.scheduled.truncated ? ", список неполный" : ""}`;
  return (
    <section
      className="game-calendar calendar-screen"
      aria-label="Календарь игры"
    >
      <div className="calendar-toolbar">
        <div className="calendar-period">
          <button
            aria-label={yearView ? "Предыдущий год" : "Предыдущий месяц"}
            disabled={!shiftMonth(month, -step, profile)}
            onClick={() => move(-step)}
          >
            <ChevronLeft size={20} />
          </button>
          <h3 aria-live="polite">{yearView ? year : title}</h3>
          <button
            aria-label={yearView ? "Следующий год" : "Следующий месяц"}
            disabled={!shiftMonth(month, step, profile)}
            onClick={() => move(step)}
          >
            <ChevronRight size={20} />
          </button>
        </div>
        <button className="calendar-today" onClick={() => choose(today)}>
          <CalendarDays size={17} />
          Сегодня в игре
        </button>
        <div
          className="calendar-view-switch"
          role="group"
          aria-label="Представление календаря"
        >
          <button aria-pressed={!yearView} onClick={() => setYearView(false)}>
            Месяц
          </button>
          <button aria-pressed={yearView} onClick={() => setYearView(true)}>
            Год
          </button>
        </div>
      </div>
      <div className="calendar-context">
        <span>Сегодня · {profileDate(today, profile)}</span>
        <span>Известные даты и планы · время мира не меняется</span>
      </div>
      {yearView ? (
        <CalendarYear
          key={`${key}:${year}`}
          save={save}
          year={year}
          profile={profile}
          today={today}
          selected={selected}
          choose={choose}
        />
      ) : (
        <div className="calendar-layout">
          <div className="calendar-main">
            {error ? (
              <div role="alert" className="calendar-empty">
                <strong>Не удалось загрузить календарь</strong>
                <p>{error}</p>
                <button onClick={() => setRetry((v) => v + 1)}>
                  Повторить
                </button>
              </div>
            ) : !data ? (
              <p className="calendar-empty" role="status">
                Загрузка календаря…
              </p>
            ) : (
              <>
                {custom ? (
                  <div
                    className="custom-calendar"
                    style={{
                      gridTemplateColumns: `repeat(${data.profile.weekday_names?.length || 7},minmax(0,1fr))`,
                    }}
                  >
                    {weekdayLabels(data.profile).map((d, i) => (
                      <small key={i} title={d}>
                        {d}
                      </small>
                    ))}
                    {Array.from(
                      { length: data.days[0]?.weekday || 0 },
                      (_, i) => (
                        <span key={"b" + i} />
                      ),
                    )}
                    {data.days.map((d) => (
                      <button
                        key={d.date}
                        aria-label={dayLabel(d.date)}
                        aria-current={d.date === today ? "date" : undefined}
                        aria-pressed={d.date === selected}
                        data-past={d.date < today}
                        onClick={() => setSelected(d.date)}
                      >
                        <span className="calendar-day-number">
                          {d.day}
                          <WeatherBadge weather={d.weather} compact />
                        </span>
                        <Markers items={onDay(d.date)} save={save} />
                      </button>
                    ))}
                  </div>
                ) : (
                  <DayPicker
                    mode="single"
                    month={parse(month + "-01")}
                    onMonthChange={(d) => choose(iso(d).slice(0, 7) + "-01")}
                    selected={parse(selected)}
                    onSelect={(d) => d && setSelected(iso(d))}
                    today={parse(today)}
                    locale={gameLocale().startsWith("ru") ? ru : enUS}
                    weekStartsOn={1}
                    hideNavigation
                    startMonth={parse("0001-01-01")}
                    endMonth={parse("9999-12-01")}
                    components={{
                      DayButton: ({ day, modifiers, ...props }) => (
                        <DayButton
                          day={day}
                          modifiers={modifiers}
                          {...props}
                          aria-label={dayLabel(iso(day.date))}
                          aria-pressed={iso(day.date) === selected}
                          data-past={iso(day.date) < today}
                        >
                          <span className="calendar-day-number">
                            {day.date.getDate()}
                            <WeatherBadge
                              compact
                              weather={
                                data.days.find((d) => d.date === iso(day.date))
                                  ?.weather
                              }
                            />
                          </span>
                          <Markers items={onDay(iso(day.date))} save={save} />
                        </DayButton>
                      ),
                    }}
                  />
                )}
                <div
                  className="calendar-legend"
                  aria-label="Обозначения событий"
                >
                  {Object.keys(icons).map((kind) => (
                    <span key={kind}>
                      <EventIcon kind={kind} />
                      {category(kind)}
                    </span>
                  ))}
                </div>
                <Notices data={data} />
                <section
                  className="calendar-agenda"
                  aria-label="Ближайшие известные события"
                >
                  <header>
                    <h4>Ближайшие события</h4>
                    <span>В пределах: {title}</span>
                  </header>
                  <p className="muted">
                    Даты и незавершённые планы с сегодняшнего дня. План не
                    означает, что событие состоялось.
                  </p>
                  {agenda.length ? (
                    agenda.map((e) => (
                      <button
                        key={e.id}
                        onClick={() =>
                          setSelected(
                            e.date < month + "-01" ? month + "-01" : e.date,
                          )
                        }
                      >
                        <span className="calendar-agenda-date">
                          {profileDate(e.date, profile)}
                        </span>
                        <span>
                          <span className="calendar-category">
                            <EventIcon kind={e.kind} />
                            {category(e.kind)}
                            {e.window?.exact_time &&
                              ` · ${e.window.exact_time}`}
                          </span>
                          <strong>{itemName(e, save)}</strong>
                          {statusLabel(e) && <small>{statusLabel(e)}</small>}
                        </span>
                        <ChevronRight size={16} />
                      </button>
                    ))
                  ) : (
                    <p className="calendar-empty">
                      В этом месяце нет известных предстоящих событий.
                    </p>
                  )}
                </section>
              </>
            )}
          </div>
          <section
            className="calendar-detail"
            aria-label="События дня"
            aria-busy={!data && !error}
          >
            <header>
              <span className="calendar-eyebrow">
                {selected === today ? "Сегодня в игре" : "Выбранный день"}
              </span>
              <h4>{profileDate(selected, profile, "weekday")}</h4>
              <WeatherBadge
                weather={data?.days.find((d) => d.date === selected)?.weather}
              />
              {data?.days.find((d) => d.date === selected)?.weather
                ?.forecast && (
                <small className="calendar-forecast">Прогноз погоды</small>
              )}
            </header>
            {error ? (
              <p>События недоступны. Повторите загрузку.</p>
            ) : !data ? (
              <p role="status">Загрузка событий…</p>
            ) : (
              <>
                <p className="calendar-detail-count">
                  Событий: {onDay(selected).length}
                  {data.scheduled.truncated ? " · список неполный" : ""}
                </p>
                {!onDay(selected).length && (
                  <p className="calendar-empty">
                    {data.scheduled.truncated
                      ? "В загруженной части событий нет."
                      : "Известных событий нет."}
                  </p>
                )}
                {onDay(selected).map((e) => (
                  <EventCard
                    key={e.id}
                    item={e}
                    save={save}
                    profile={profile}
                  />
                ))}
              </>
            )}
          </section>
        </div>
      )}
    </section>
  );
}
function CalendarYear({
  save,
  year,
  profile,
  today,
  selected,
  choose,
}: {
  save: Save;
  year: number;
  profile?: CalendarProfile;
  today: string;
  selected: string;
  choose: (d: string) => void;
}) {
  const [months, setMonths] = useState<Projection[]>([]),
    [error, setError] = useState(""),
    [retry, setRetry] = useState(0);
  const count = monthCount(profile);
  useEffect(() => {
    const controller = new AbortController();
    setMonths([]);
    setError("");
    Promise.all(
      Array.from({ length: count }, (_, i) => {
        const prefix = `${String(year).padStart(4, "0")}-${String(i + 1).padStart(2, "0")}`;
        return api<Projection>(
          `/saves/${save.id}/calendar?start_date=${prefix}-01&end_date=${prefix}-${String(monthLength(prefix, profile)).padStart(2, "0")}`,
          undefined,
          undefined,
          controller.signal,
        );
      }),
    )
      .then((rows) => {
        if (!controller.signal.aborted) setMonths(rows);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [
    save.id,
    save.revision,
    save.state.controlled_actor_id,
    year,
    count,
    profile,
    retry,
  ]);
  if (error)
    return (
      <div className="calendar-empty" role="alert">
        <p>{error}</p>
        <button onClick={() => setRetry((n) => n + 1)}>Повторить</button>
      </div>
    );
  if (!months.length)
    return (
      <p role="status" className="calendar-empty">
        Загрузка года…
      </p>
    );
  return (
    <div className="calendar-year">
      {months.map((month, i) => {
        const items = projectionItems(month);
        return (
          <section className="calendar-mini" key={i}>
            <h4>
              {profile?.system === "custom"
                ? profile.month_names?.[i] || i + 1
                : calendarDate(month.days[0]?.date, "month")}
            </h4>
            <p className="calendar-mini-summary">
              Событий: {items.length}
              {month.scheduled.truncated ? " · не все" : ""}
            </p>
            <div
              className="calendar-mini-grid"
              style={{
                gridTemplateColumns: `repeat(${month.profile.weekday_names?.length || 7},minmax(0,1fr))`,
              }}
            >
              {weekdayLabels(month.profile).map((w, j) => (
                <small key={j} title={w}>
                  {w}
                </small>
              ))}
              {Array.from({ length: month.days[0]?.weekday || 0 }, (_, j) => (
                <span key={"b" + j} />
              ))}
              {month.days.map((day) => {
                const events = itemsOnDay(items, day.date);
                return (
                  <button
                    key={day.date}
                    aria-label={`${profileDate(day.date, profile)}, событий: ${events.length}${month.scheduled.truncated ? ", список неполный" : ""}`}
                    aria-current={day.date === today ? "date" : undefined}
                    aria-pressed={day.date === selected}
                    data-past={day.date < today}
                    onClick={() => choose(day.date)}
                  >
                    {day.day}
                    <Markers items={events} save={save} mini />
                  </button>
                );
              })}
            </div>
            <Notices data={month} />
          </section>
        );
      })}
    </div>
  );
}
