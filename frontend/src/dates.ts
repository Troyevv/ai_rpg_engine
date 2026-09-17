export function localDate(value?: string | null): string {
    if (!value?.trim())
        return "Дата неизвестна";
    let normalized = value.trim().replace(" ", "T");
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(normalized))
        normalized += "Z";
    const date = new Date(normalized);
    return Number.isNaN(date.getTime()) ? "Дата неизвестна" : date.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
