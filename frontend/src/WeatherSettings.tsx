import { useEffect, useState } from "react";
import { api } from "./api";
import type { Save } from "./types";
export function WeatherSettings({
  save,
  refresh,
  disabled = false,
}: {
  save: Save;
  refresh: (s: Save) => void;
  disabled?: boolean;
}) {
  const [configured, setConfigured] = useState<boolean | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);
  const [region, setRegion] = useState(""),
    [climate, setClimate] = useState("temperate"),
    [hemisphere, setHemisphere] = useState("north"),
    [unit, setUnit] = useState("C");
  useEffect(() => {
    let live = true;
    setConfigured(null);
    setError("");
    api<any>(`/saves/${save.id}/weather`)
      .then((p) => {
        if (live) setConfigured(!!p);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [save.id, save.revision, retry]);
  return (
    <details>
      <summary>Климат и погода</summary>
      {error && (
        <div role="alert">
          <p>{error}</p>
          <button type="button" onClick={() => setRetry((v) => v + 1)}>
            Повторить загрузку погоды
          </button>
        </div>
      )}
      {configured === null ? (
        error ? null : (
          <p role="status">Загрузка…</p>
        )
      ) : configured ? (
        <p>
          Климат установлен. Погода следует времени и региону мира; просмотр
          календаря её не меняет.
        </p>
      ) : (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (busy || disabled) return;
            setBusy(true);
            setError("");
            try {
              refresh(
                await api<Save>(
                  `/saves/${save.id}/weather`,
                  {
                    revision: save.revision,
                    profile: {
                      seed: crypto.randomUUID(),
                      temperature_unit: unit,
                      regions: {
                        [region]: { climate, hemisphere: hemisphere || null },
                      },
                    },
                  },
                  "PUT",
                ),
              );
              setConfigured(true);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <p>
            Неизвестный климат не угадывается. Явно задай регион — погода
            появится с текущего игрового момента. Выбор фиксируется в этом
            сохранении; прошлое не меняется.
          </p>
          <label>
            Регион
            <select
              aria-label="Регион климата"
              required
              value={region}
              onChange={(e) => setRegion(e.target.value)}
            >
              <option value="">Выбрать место</option>
              {save.state.locations
                .filter((l) => l.id)
                .map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name || l.text}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Климат
            <select
              value={climate}
              onChange={(e) => setClimate(e.target.value)}
            >
              {[
                ["temperate", "Умеренный"],
                ["tropical", "Тропический"],
                ["arid", "Засушливый"],
                ["polar", "Полярный"],
              ].map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label>
            Полушарие
            <select
              value={hemisphere}
              onChange={(e) => setHemisphere(e.target.value)}
            >
              <option value="">Не задано</option>
              <option value="north">Северное</option>
              <option value="south">Южное</option>
            </select>
          </label>
          <label>
            Температура
            <select value={unit} onChange={(e) => setUnit(e.target.value)}>
              <option>C</option>
              <option>F</option>
            </select>
          </label>
          <button disabled={busy || disabled || !region}>
            {busy ? "Сохранение…" : "Установить климат"}
          </button>
        </form>
      )}
    </details>
  );
}
