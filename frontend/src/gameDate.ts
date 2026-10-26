export const gameLocale = () => document.documentElement.lang || "ru-RU";
export function calendarDate(
  value?: string | null,
  style: "long" | "short" | "month" | "weekday" = "long",
  locale = gameLocale(),
) {
  if (!value) return "Дата неизвестна";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return value;
  const [, y, m, d] = match;
  const date = new Date(0);
  date.setUTCFullYear(+y, +m - 1, +d);
  date.setUTCHours(12, 0, 0, 0);
  if (date.getUTCMonth() !== +m - 1 || date.getUTCDate() !== +d) return value;
  const opts: Intl.DateTimeFormatOptions =
    style === "short"
      ? { day: "2-digit", month: "2-digit", year: "numeric" }
      : style === "month"
        ? { month: "long", year: "numeric" }
        : {
            day: "numeric",
            month: "long",
            year: "numeric",
            ...(style === "weekday" ? { weekday: "long" as const } : {}),
          };
  let text = new Intl.DateTimeFormat(locale, {
    ...opts,
    timeZone: "UTC",
  }).format(date);
  if (locale.startsWith("ru") && style !== "short")
    text = text.replace(/ г\.$/, " года");
  if (style === "month")
    text = text.replace(/ года$/, "").replace(/^./, (c) => c.toUpperCase());
  return text;
}

export function formatDateLabel(label: string, locale = gameLocale()) {
  return label.replace(/\b\d{4}-\d{2}-\d{2}\b/g, (value) =>
    calendarDate(value, "long", locale),
  );
}
export function profileDate(
  value: string,
  profile?: { system?: string; month_names?: string[] },
  style: "long" | "weekday" = "long",
) {
  if (profile?.system !== "custom") return calendarDate(value, style);
  const [y, m, d] = value.split("-").map(Number);
  return `${d} ${profile.month_names?.[m - 1] || m} · ${y}`;
}
