import {Versions} from "./Versions";
import { useState, useEffect } from "react";
import { toast } from "sonner";
import { api } from "./api";
import { defaults, type Preferences, type ModelConfig } from "./types";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "./components/ui/dialog";
export function Settings({
  open,
  onOpenChange,
  value,
  save,
  apiKey,
  setApiKey,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  value: Preferences;
  save: (v: Preferences) => Promise<void>;
  apiKey: string;
  setApiKey: (v: string) => void;
}) {
  const [draft, setDraft] = useState(value);
  const [models, setModels] = useState<string[]>([]);
  const [loaded, setLoaded] = useState<string[]>([]);
  const [promptNames,setPromptNames] = useState<string[]>([]);
  const [prompt,setPrompt] = useState("");
  const [stored, setStored] = useState(false);
  const [capabilities, setCapabilities] = useState<Record<string,{thinking_models:string[]}>>({});
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (open) {
      setDraft(value);
      api<Record<string,unknown>>("/prompts").then(v=>setPromptNames(Object.keys(v))).catch(e=>toast.error(e.message));
      api<{deepseek:boolean}>("/credentials").then(v=>setStored(v.deepseek)).catch(e=>toast.error(e.message));
      api<Record<string,{thinking_models:string[]}>>("/capabilities").then(setCapabilities).catch(e=>toast.error(e.message));
    }
  }, [open, value]);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const update = (
    key: "idea" | "summary" | "game",
    patch: Partial<ModelConfig>,
  ) => setDraft((d) => ({ ...d, [key]: { ...d[key], ...patch } }));
  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (v) setDraft(value);
        onOpenChange(v);
      }}
    >
      <DialogContent className="settings-dialog">
        <DialogHeader>
          <DialogTitle>Настройки</DialogTitle>
          <DialogDescription>
            Модели работают за сценой. Здесь можно настроить каждую задачу.
          </DialogDescription>
        </DialogHeader>
        <details><summary>Основные промпты и версии</summary>{promptNames.map(name=><Button key={name} size="sm" variant="ghost" onClick={()=>setPrompt(name)}>{name}</Button>)}</details>
        <Versions kind="prompt" owner={prompt} open={!!prompt} close={()=>setPrompt("")}/>
        <label>
          API-ключ DeepSeek
          <Input
            type="password"
            autoComplete="off"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={stored ? "Ключ сохранён на сервере. Введи новый для замены" : "Или переменная DEEPSEEK_API_KEY"}
          />
        </label>
        <p className="muted small">
          Ключ сохраняется зашифрованным на сервере и работает после перезапуска и с телефона. Для DeepSeek текст и контекст отправляются в API.
        </p>
        {stored && <Button variant="ghost" size="sm" onClick={()=>run(async()=>{
          const status = await api<{deepseek:boolean}>("/credentials/deepseek",undefined,"DELETE");
          setStored(status.deepseek); setApiKey(""); toast.success(status.deepseek ? "Сохранённый ключ удалён; ключ окружения остаётся доступен" : "Ключ удалён");
        })}>Удалить сохранённый ключ</Button>}
        {(["idea", "summary", "game"] as const).map((key, index) => (
          <fieldset key={key}>
            <legend>
              {["Сценарист", "Генератор выжимки", "Ведущий"][index]}
            </legend>
            <div className="form-grid">
              <label>
                Провайдер
                <select
                  aria-label={`Провайдер ${key}`}
                  value={draft[key].provider}
                  onChange={(e) =>
                    update(key, {
                      provider: e.target.value as ModelConfig["provider"],
                      model:
                        e.target.value === "deepseek"
                          ? "deepseek-flash"
                          : draft.local.model,
                    })
                  }
                >
                  <option value="local">Локальная модель · LM Studio</option>
                  <option value="deepseek">DeepSeek API</option>
                </select>
              </label>
              <label>
                Модель
                <Input
                  aria-label={`Модель ${key}`}
                  list="model-list"
                  value={draft[key].model}
                  onChange={(e) => update(key, { model: e.target.value })}
                />
              </label>
              {(capabilities[draft[key].provider]?.thinking_models || []).includes(draft[key].model) && <label>
                Thinking
                <select aria-label={`Thinking ${key}`} value={draft[key].thinking || "off"} onChange={e=>update(key,{thinking:e.target.value as ModelConfig["thinking"]})}>
                  <option value="off">Off</option><option value="low">Low</option><option value="high">High</option>
                </select>
                <span className="muted small">Размышления входят в лимит ответа. Temperature при Thinking не применяется.</span>
              </label>}
              <label>
                Temperature
                <Input
                  type="number"
                  min="0"
                  max="1.5"
                  step="0.05"
                  value={draft[key].temperature}
                  onChange={(e) =>
                    update(key, { temperature: +e.target.value })
                  }
                />
              </label>
              <label>
                Лимит ответа
                <Input
                  type="number"
                  min="256"
                  max="32000"
                  value={draft[key].max_tokens}
                  onChange={(e) => update(key, { max_tokens: +e.target.value })}
                />
              </label>
              {key === "game" && (
                <>
                  <details>
                    <summary>Память — автоматически</summary>
                    <p className="muted">Движок сам сжимает историю, уменьшает большие пакеты и повторяет неудачные попытки. Ручное обслуживание не требуется.</p>
                  <label>Последних ходов в контексте<Input type="number" min="2" max="20" value={draft.game.recent_turns} onChange={e=>update(key,{recent_turns:+e.target.value})}/></label>
                  <label>Максимум ходов в пакете памяти<Input type="number" min="2" max="20" value={draft.game.memory_batch} onChange={e=>update(key,{memory_batch:+e.target.value})}/></label>
                  </details>
                  <label>
                    Бюджет контекста
                    <select
                      value={draft.game.context_length}
                      onChange={(e) =>
                        update(key, { context_length: +e.target.value })
                      }
                    >
                      {[8192, 16384, 32768, 65536, 131072].map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Лимит обработки мира
                    <Input
                      type="number"
                      min="1024"
                      max="16000"
                      value={draft.game.update_tokens}
                      onChange={(e) =>
                        update(key, { update_tokens: +e.target.value })
                      }
                    />
                  </label>
                </>
              )}
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const r = await api<{
                    models: string[];
                    loaded: { model_key: string }[];
                  }>("/models/list", {
                    provider: draft[key].provider,
                    api_key: apiKey,
                  });
                  setModels(r.models);
                  setLoaded(r.loaded.map((m) => m.model_key));
                  toast.success("Список моделей обновлён");
                })
              }
            >
              Обновить список моделей
            </Button>
          </fieldset>
        ))}
        <datalist id="model-list">
          {models.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
        {models.length > 0 && (
          <p className="muted small">Доступны: {models.join(", ")}</p>
        )}
        <fieldset>
          <legend>Загрузка локальной модели</legend>
          <div className="form-grid">
            <label>
              Модель
              <Input
                list="model-list"
                value={draft.local.model}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    local: { ...d.local, model: e.target.value },
                  }))
                }
              />
            </label>
            <label>
              Контекст
              <select
                value={draft.local.context_length}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    local: { ...d.local, context_length: +e.target.value },
                  }))
                }
              >
                {[8192, 16384, 32768].map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </label>
            <label>
              Eval Batch Size
              <select
                value={draft.local.eval_batch_size}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    local: {
                      ...d.local,
                      eval_batch_size: +e.target.value as 512,
                    },
                  }))
                }
              >
                {[256, 512, 1024, 2048].map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </label>
          </div>
          <label className="check">
            <input
              type="checkbox"
              checked={draft.local.flash_attention}
              onChange={(e) =>
                setDraft((d) => ({
                  ...d,
                  local: { ...d.local, flash_attention: e.target.checked },
                }))
              }
            />
            Flash Attention
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={draft.local.offload_kv_cache_to_gpu}
              onChange={(e) =>
                setDraft((d) => ({
                  ...d,
                  local: {
                    ...d.local,
                    offload_kv_cache_to_gpu: e.target.checked,
                  },
                }))
              }
            />
            KV-cache на GPU
          </label>
          <div className="actions">
            <Button
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const r = await api<{ loaded: { model_key: string }[] }>(
                    "/models/load",
                    draft.local,
                  );
                  setLoaded(r.loaded.map((m) => m.model_key));
                  toast.success("Модель загружена");
                })
              }
            >
              Загрузить
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() =>
                run(async () => {
                  await api("/models/unload", {});
                  setLoaded([]);
                  toast.success("Модель выгружена");
                })
              }
            >
              Выгрузить
            </Button>
          </div>
          <p className="muted small">
            {loaded.length
              ? "Загружена: " + loaded.join(", ")
              : "Статус появится после обновления списка или загрузки."}
          </p>
        </fieldset>
        <fieldset>
          <legend>Чтение</legend>
          {(["font_size", "line_height", "reading_width"] as const).map(
            (key, i) => (
              <label key={key}>
                {["Размер текста", "Межстрочный интервал", "Ширина текста"][i]}{" "}
                · {draft[key]}
                <input
                  type="range"
                  min={[14, 1.3, 600][i]}
                  max={[24, 2.2, 1100][i]}
                  step={[1, 0.1, 50][i]}
                  value={draft[key]}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, [key]: +e.target.value }))
                  }
                />
              </label>
            ),
          )}
          <label className="check">
            <input
              type="checkbox"
              checked={draft.link_names}
              onChange={(e) =>
                setDraft((d) => ({ ...d, link_names: e.target.checked }))
              }
            />
            Ссылки на персонажей в истории
          </label>
        </fieldset>
        <div className="actions sticky-actions">
          <Button
            disabled={busy}
            onClick={() =>
              run(async () => {
                if (apiKey.trim()) {
                  await api("/credentials/deepseek",{api_key:apiKey},"PUT");
                  setStored(true); setApiKey("");
                }
                await save(draft);
                onOpenChange(false);
                toast.success("Настройки сохранены");
              })
            }
          >
            Сохранить настройки
          </Button>
          <Button variant="ghost" onClick={() => setDraft(defaults)}>
            По умолчанию
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
