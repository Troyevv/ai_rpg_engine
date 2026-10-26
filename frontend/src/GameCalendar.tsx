import { useEffect, useState } from "react";
import { DayPicker, DayButton } from "react-day-picker";
import { ru, enUS } from "react-day-picker/locale";
import "react-day-picker/style.css";
import { api } from "./api";
import type { Save } from "./types";
import { calendarDate, gameLocale } from "./gameDate";
import { WeatherBadge, type Weather } from "./SceneClock";
type Item = {
  id: string;
  date: string;
  end_date?: string;
  kind: string;
  name: string | null;
  character_ids: string[];
  status?: string;
  window?: { exact_time?: string; relevance?: string };
  interval_state?: string;
};
type Day = {
  date: string;
  day: number;
  weekday: number;
  month: number;
  year: number;
  weather?: Weather;
};
type Projection = {
  days: Day[];
  events: Item[];
  scheduled: { items: Item[]; truncated: boolean };
  notices: string[];
  profile: { system: string; month_names?: string[]; weekday_names?: string[] };
};
const iso = (date: Date) =>
  `${String(date.getFullYear()).padStart(4, "0")}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const parse = (value: string) => {
  const [y, m, d] = value.split("-").map(Number);
  const date = new Date(0);
  date.setFullYear(y, m - 1, d);
  date.setHours(12, 0, 0, 0);
  return date;
};
export function GameCalendar({ save }: { save: Save }) {
  const today = save.state.world_clock?.projection?.date;
  const [month, setMonth] = useState(today?.slice(0, 7) || ""),
    [selected, setSelected] = useState(today || ""),
    [yearView, setYearView] = useState(false);
  const [data, setData] = useState<Projection | null>(null),
    [error, setError] = useState("");
  const profile = (save.state.world_clock?.calendar as any)?.profile;
  const custom = profile?.system === "custom";
  const monthCount = custom ? profile.month_lengths.length : 12;
  const year = Number(month.slice(0, 4)),
    number = Number(month.slice(5, 7));
  const length = custom
    ? profile.month_lengths[number - 1]
    : new Date(year, number, 0).getDate();
  useEffect(() => {
    if (!month) return;
    let live = true;
    setData(null);
    setError("");
    api<Projection>(
      `/saves/${save.id}/calendar?start_date=${month}-01&end_date=${month}-${String(length).padStart(2, "0")}`,
    )
      .then((d) => {
        if (live) setData(d);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [save.id, save.revision, save.state.controlled_actor_id, month, length]);
  if (!today)
    return (
      <p>
        Календарная дата не установлена. Относительное время мира сохраняется.
      </p>
    );
  const move = (delta: number) => {
    const offset = (year - 1) * monthCount + number - 1 + delta;
    const y = Math.floor(offset / monthCount) + 1;
    if (y < 1 || y > 9999) return;
    setMonth(
      `${String(y).padStart(4, "0")}-${String((offset % monthCount) + 1).padStart(2, "0")}`,
    );
  };
  const items = [...(data?.events || []), ...(data?.scheduled.items || [])];
  const onDay = (date: string) =>
    items.filter((e) => e.date <= date && (e.end_date || e.date) >= date);
  const title = custom
    ? `${profile.month_names?.[number - 1] || number} · ${year}`
    : calendarDate(month + "-01", "month");
  const itemName = (e: Item) =>
    e.kind === "birthday"
      ? `День рождения: ${e.character_ids.map((id) => save.state.characters.find((c) => c.id === id)?.name || "Персонаж").join(", ")}`
      : e.name || "Дата";
  return (
    <section className="game-calendar" aria-label="Календарь игры">
      <div className="calendar-toolbar">
        <button
          aria-label="Предыдущий месяц"
          onClick={() => move(yearView ? -monthCount : -1)}
        >
          ‹
        </button>
        <h3>{yearView ? year : title}</h3>
        <button
          aria-label="Следующий месяц"
          onClick={() => move(yearView ? monthCount : 1)}
        >
          ›
        </button>
        <button
          onClick={() => {
            setMonth(today.slice(0, 7));
            setSelected(today);
          }}
        >
          Сегодня в игре
        </button>
        <button aria-pressed={yearView} onClick={() => setYearView(!yearView)}>
          {yearView ? "Месяц" : "Год"}
        </button>
      </div>
      {yearView ? (
        <div className="calendar-year">
          {Array.from({ length: monthCount }, (_, i) => (
            <button
              key={i}
              onClick={() => {
                setMonth(
                  `${String(year).padStart(4, "0")}-${String(i + 1).padStart(2, "0")}`,
                );
                setYearView(false);
              }}
            >
              {custom
                ? profile.month_names?.[i] || i + 1
                : calendarDate(
                    `${String(year).padStart(4, "0")}-${String(i + 1).padStart(2, "0")}-01`,
                    "month",
                  )}
            </button>
          ))}
        </div>
      ) : (
        <>
          {error ? (
            <p role="alert">{error}</p>
          ) : !data ? (
            <p role="status">Загрузка календаря…</p>
          ) : custom ? (
            <div
              className="custom-calendar"
              style={{
                gridTemplateColumns: `repeat(${data.profile.weekday_names?.length || 7},minmax(0,1fr))`,
              }}
            >
              {(
                data.profile.weekday_names || [
                  "Пн",
                  "Вт",
                  "Ср",
                  "Чт",
                  "Пт",
                  "Сб",
                  "Вс",
                ]
              ).map((d, i) => (
                <small key={i}>{d}</small>
              ))}
              {Array.from({ length: data.days[0]?.weekday || 0 }, (_, i) => (
                <span key={"blank" + i} />
              ))}
              {data.days.map((d) => (
                <button
                  key={d.date}
                  aria-current={d.date === today ? "date" : undefined}
                  aria-pressed={d.date === selected}
                  onClick={() => setSelected(d.date)}
                >
                  {d.day}
                  {onDay(d.date).length > 0 && (
                    <span aria-label="Есть события"> •</span>
                  )}
                  <WeatherBadge weather={d.weather} compact />
                </button>
              ))}
            </div>
          ) : (
            <DayPicker
              mode="single"
              month={parse(month + "-01")}
              onMonthChange={(d) => setMonth(iso(d).slice(0, 7))}
              selected={parse(selected)}
              onSelect={(d) => d && setSelected(iso(d))}
              today={parse(today)}
              locale={gameLocale().startsWith("ru") ? ru : enUS}
              weekStartsOn={1}
              hideNavigation
              modifiers={{
                events: data.days
                  .filter((d) => onDay(d.date).length)
                  .map((d) => parse(d.date)),
              }}
              modifiersClassNames={{ events: "calendar-has-events" }}
              components={{
                DayButton: ({ day, modifiers, ...props }) => (
                  <DayButton day={day} modifiers={modifiers} {...props}>
                    <span>{day.date.getDate()}</span>
                    <WeatherBadge
                      compact
                      weather={
                        data.days.find((d) => d.date === iso(day.date))?.weather
                      }
                    />
                  </DayButton>
                ),
              }}
            />
          )}
          <section className="calendar-detail" aria-label="События дня">
            <h4>{custom ? selected : calendarDate(selected, "weekday")}</h4>
            <WeatherBadge
              weather={data?.days.find((d) => d.date === selected)?.weather}
            />
            {data && onDay(selected).length === 0 && (
              <p className="muted">Известных событий нет.</p>
            )}
            {onDay(selected).map((e) => (
              <article key={e.id} data-status={e.status || "date"}>
                <strong>{itemName(e)}</strong>
                {e.status && (
                  <p>
                    {{
                      pending: "Запланировано",
                      resolved: "Завершено",
                      cancelled: "Отменено",
                    }[e.status] || e.status}
                    {e.status === "pending" && e.window?.relevance === "overdue"
                      ? " · срок прошёл"
                      : ""}
                    {e.window?.exact_time ? ` · ${e.window.exact_time}` : ""}
                  </p>
                )}
                {e.kind !== "birthday" && e.character_ids.length > 0 && (
                  <small>
                    {e.character_ids
                      .map(
                        (id) =>
                          save.state.characters.find((c) => c.id === id)
                            ?.name || "Персонаж",
                      )
                      .join(", ")}
                  </small>
                )}
              </article>
            ))}
          </section>
        </>
      )}
      {data?.notices.map((n) => (
        <p role="status" key={n}>
          {n}
        </p>
      ))}
      {data?.scheduled.truncated && (
        <p>Показана часть событий. Выбери более узкий период.</p>
      )}
    </section>
  );
}
