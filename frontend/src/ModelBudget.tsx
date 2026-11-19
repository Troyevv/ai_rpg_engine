import { useEffect, useState } from "react";
import { api } from "./api";
import { Input } from "./components/ui/input";
import { gameLocale } from "./gameDate";
import type { ModelConfig } from "./types";

type Limits = {context_length: number | null; max_input?: number; max_output?: number; source: string};
export function ModelBudget({value, stage, change}: {
  value: ModelConfig; stage: "idea" | "summary" | "game"; change: (patch: Partial<ModelConfig>) => void;
}) {
  const [caps, setCaps] = useState<Limits | null>(null);
  const [failed, setFailed] = useState(false);
  const en = gameLocale().startsWith("en");
  const t = (ru: string, english: string) => en ? english : ru;
  const auto = value.budget_mode === "auto";
  useEffect(() => {
    const controller = new AbortController();
    setCaps(null); setFailed(false);
    if (!value.model.trim()) return;
    const timer = setTimeout(() => api<Limits>("/capabilities", {provider:value.provider, model:value.model},
      "POST", controller.signal).then(result => { if (!controller.signal.aborted) setCaps(result); })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); }), 250);
    return () => {clearTimeout(timer); controller.abort();};
  }, [value.provider, value.model]);
  const window = caps?.context_length;
  const invalid = !auto && value.budget_mode === "manual" && window && value.context_length > window;
  return <section className="model-budget">
    <label className="check"><input type="checkbox" checked={auto}
      aria-label={t("Автоматические лимиты", "Automatic limits") + " " + stage}
      onChange={e => change({budget_mode:e.target.checked ? "auto" : "manual"})}/>
      {t("Контекст и лимиты — автоматически", "Automatic context and response limits")}
    </label>
    <p className="small muted" role="status">{!value.model.trim() ? t("Выберите модель.", "Choose a model.") :
      failed ? t("Сведения о модели недоступны. Проверьте подключение.", "Model information is unavailable. Check the connection.") :
      !caps ? t("Проверяем характеристики…", "Checking model limits…") :
      window ? t("Окно модели", "Model window") + " · " + window.toLocaleString() + " " + t("токенов", "tokens") :
      caps.max_input && caps.max_output ? t("Вход до ", "Input up to ") + caps.max_input.toLocaleString() + t(", ответ до ", ", output up to ") + caps.max_output.toLocaleString() :
      t("Окно неизвестно. Загрузите выбранную модель или задайте проверенные лимиты вручную.",
        "Window unknown. Load the selected model or enter verified limits manually.")}</p>
    {invalid ? <p role="alert">{t("Ручное окно больше доступного. Уменьшите его до", "Reduce the manual window to")} {window.toLocaleString()}.</p> : null}
    <details><summary>{t("Расширенные настройки", "Advanced settings")}</summary>
      {caps && <p className="muted small">{caps.source}{caps.max_output ? " · " + t("Максимум ответа", "Maximum output") + " " + caps.max_output.toLocaleString() : ""}</p>}
      <div className="form-grid">
        <label>{t("Бюджет контекста", "Context window")}<Input aria-label={`Контекст ${stage}`} type="number" min={value.budget_mode ? 2048 : 8192} step={1}
          disabled={auto} value={value.context_length} onChange={e=>change({context_length:+e.target.value})}/></label>
        <label>{t("Лимит ответа", "Response limit")}<Input type="number" min={256} max={caps?.max_output ?? 1048576} disabled={auto}
          value={value.max_tokens} onChange={e=>change({max_tokens:+e.target.value})}/></label>
        {stage === "game" && <label>{t("Лимит обработки мира", "Extraction limit")}<Input type="number" min={1024} max={caps?.max_output ?? 1048576}
          disabled={auto} value={value.update_tokens} onChange={e=>change({update_tokens:+e.target.value})}/></label>}
        <label>Temperature<Input type="number" min={0} max={1.5} step={0.05} value={value.temperature}
          onChange={e=>change({temperature:+e.target.value})}/></label>
      </div>
      {auto && <p className="muted small">{t("Числа сохранены для ручного режима. Сейчас бюджет каждого запроса рассчитывает сервер.",
        "These values are saved for manual mode. The server budgets each request automatically.")}</p>}
      {!auto && value.budget_mode == null && value.auto_context && <p className="muted small">{t("Сохранена прежняя настройка определения окна по модели.", "Your legacy automatic window setting is active.")}</p>}
    </details>
  </section>;
}
