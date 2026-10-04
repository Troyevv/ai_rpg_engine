export type WorldImportFormat = 'text' | 'json';

// A chosen file supplies its format. Manual input is classified only after
// parsing, and broken JSON-looking input must never fall back to prose.
export function detectWorldImport(text: string, fileFormat?: WorldImportFormat): {
    format: WorldImportFormat;
    error: string | null;
} {
    const trimmed = text.trim();
    if (fileFormat === 'text' || (fileFormat !== 'json' && !trimmed.startsWith('{')))
        return {format: 'text', error: null};
    try {
        const value: unknown = JSON.parse(trimmed);
        if (value !== null && typeof value === 'object' && !Array.isArray(value))
            return {format: 'json', error: null};
        if (fileFormat === 'json')
            return {format: 'json', error: 'JSON не содержит корректный World State. Нужен объект.'};
        return {format: 'text', error: null};
    } catch {
        return {format: 'json', error: 'Не удалось прочитать JSON: ошибка синтаксиса.'};
    }
}
