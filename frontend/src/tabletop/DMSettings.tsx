import { useState } from "react";
export type Settings = {
  style: string;
  custom_style: string;
  strictness: string;
  difficulty: string;
  hints: boolean;
  length: string;
};
export function DMSettings({
  value,
  busy,
  save,
  provider,
}: {
  value: Settings;
  busy: boolean;
  save: (s: Settings) => void;
  provider: () => void;
}) {
  const [s, set] = useState(value);
  const select = (key: keyof Settings, label: string, options: string[][]) => (
    <label>
      {label}
      <select
        aria-label={label}
        value={String(s[key])}
        onChange={(e) => set({ ...s, [key]: e.target.value })}
      >
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
  return (
    <section className="tt-panel tt-settings">
      <h1>AI-ведущий</h1>
      <button onClick={provider}>Провайдер, модель и Thinking</button>
      <div className="tt-form-grid">
        {select("style", "Стиль", [
          ["cinematic", "Кинематографичный"],
          ["concise", "Лаконичный"],
          ["detailed", "Подробный"],
          ["dark", "Мрачный"],
          ["custom", "Пользовательский"],
        ])}
        {select("strictness", "Строгость трактовки", [
          ["strict", "Строгая"],
          ["normal", "Обычная"],
          ["soft", "Мягкая"],
        ])}
        {select("difficulty", "Сложность проверок", [
          ["hidden", "Скрывать"],
          ["after", "Показывать после броска"],
          ["always", "Показывать всегда"],
        ])}
        {select("length", "Подробность описаний", [
          ["short", "Коротко"],
          ["medium", "Средне"],
          ["long", "Подробно"],
        ])}
      </div>
      {s.style === "custom" && (
        <label>
          Свой стиль
          <textarea
            maxLength={1000}
            value={s.custom_style}
            onChange={(e) => set({ ...s, custom_style: e.target.value })}
          />
        </label>
      )}
      <label className="tt-toggle">
        <input
          type="checkbox"
          checked={s.hints}
          onChange={(e) => set({ ...s, hints: e.target.checked })}
        />
        Подсказки действий
      </label>
      <p className="tt-note">
        Строгость меняет трактовку неоднозначных намерений. Броски, стоимость
        действий и правила остаются обязательными.
      </p>
      <button className="tt-primary" disabled={busy} onClick={() => save(s)}>
        Сохранить настройки ведущего
      </button>
    </section>
  );
}
