import type { Weather } from "./SceneClock";
export type CalendarProfile = {
  system?: string;
  month_lengths?: number[];
  month_names?: string[];
  weekday_names?: string[];
};
export type CalendarItem = {
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
export type CalendarDay = {
  date: string;
  day: number;
  weekday: number;
  month: number;
  year: number;
  weather?: Weather;
};
export type CalendarProjection = {
  days: CalendarDay[];
  events: CalendarItem[];
  scheduled: { items: CalendarItem[]; truncated: boolean };
  notices: string[];
  profile: CalendarProfile;
};
export const category = (kind: string) =>
  ({
    birthday: "День рождения",
    observance: "Памятная дата",
    personal: "Личная дата",
    commitment: "Договорённость",
    scheduled_event: "План",
    interval: "Период",
  })[kind] || "Событие";
export const statusLabel = (item: CalendarItem) =>
  [
    item.status &&
      ({
        pending: "Запланировано",
        resolved: "Завершено",
        cancelled: "Отменено",
        overdue: "Срок прошёл",
      }[item.status] ||
        item.status),
    item.status === "pending" &&
      item.window?.relevance === "overdue" &&
      "срок прошёл",
    item.interval_state &&
      {
        active: "Идёт сейчас",
        upcoming: "Предстоит",
        planned: "Предстоит",
        completed: "Период завершён",
        elapsed: "Период истёк",
      }[item.interval_state],
  ]
    .filter(Boolean)
    .join(" · ");
export const monthCount = (p?: CalendarProfile) =>
  p?.system === "custom" ? p.month_lengths!.length : 12;
export function monthLength(month: string, p?: CalendarProfile) {
  const [y, m] = month.split("-").map(Number);
  if (p?.system === "custom") return p.month_lengths![m - 1];
  // Date's numeric constructor treats years 0–99 as 1900–1999.
  return m === 2
    ? y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0)
      ? 29
      : 28
    : [4, 6, 9, 11].includes(m)
      ? 30
      : 31;
}
export function shiftMonth(month: string, delta: number, p?: CalendarProfile) {
  const [year, number] = month.split("-").map(Number),
    count = monthCount(p);
  const offset = (year - 1) * count + number - 1 + delta;
  if (offset < 0 || offset >= 9999 * count) return null;
  return `${String(Math.floor(offset / count) + 1).padStart(4, "0")}-${String((offset % count) + 1).padStart(2, "0")}`;
}
export const projectionItems = (data?: CalendarProjection | null) => [
  ...(data?.events || []),
  ...(data?.scheduled.items || []),
];
export const itemsOnDay = (items: CalendarItem[], date: string) =>
  items.filter((e) => e.date <= date && (e.end_date || e.date) >= date);
export function upcomingItems(items: CalendarItem[], today: string) {
  return items
    .filter(
      (e) =>
        (e.end_date || e.date) >= today &&
        (!e.status || e.status === "pending"),
    )
    .sort(
      (a, b) =>
        a.date.localeCompare(b.date) ||
        (a.window?.exact_time || "").localeCompare(
          b.window?.exact_time || "",
        ) ||
        a.id.localeCompare(b.id),
    );
}
