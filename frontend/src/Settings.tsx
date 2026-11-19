import { ModelBudget } from "./ModelBudget";
import { Choice } from "@/components/ui/choice";
import {ThemeSelector} from "./ThemeProvider";
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
  const [models, setModels] = useState<Partial<Record<ModelConfig["provider"],string[]>>>({});
  const [loaded, setLoaded] = useState<string[]>([]);
  const [promptNames,setPromptNames] = useState<string[]>([]);
  const [prompt,setPrompt] = useState("");
  const [stored, setStored] = useState(false);
  const [capabilities, setCapabilities] = useState<Record<string,{thinking_models:string[]}>>({});
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
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
        if (saving) return;
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
          Ключ сохраняется зашифрованным на сервере и работает после перезапуска и с телефона. Для DeepSeek текст и контекст отправляются в API. OpenAI-совместимый провайдер использует отдельные COMPATIBLE_BASE_URL и COMPATIBLE_API_KEY на сервере.
        </p>
        {stored && <Button variant="ghost" size="sm" onClick={()=>run(async()=>{
          const status = await api<{deepseek:boolean}>("/credentials/deepseek",undefined,"DELETE");
          setStored(status.deepseek); setApiKey(""); toast.success(status.deepseek ? "Сохранённый ключ удалён; ключ окружения остаётся доступен" : "Ключ удалён");
        })}>Удалить сохранённый ключ</Button>}
        {(["idea", "summary", "game"] as const).map((key, index) => (
          <fieldset key={key}>
            <legend>
              {["Сценарист", "Генератор мира и выжимки", "Ведущий"][index]}
            </legend>
            <div className="form-grid">
              <label>
                Провайдер
                <Choice
                  aria-label={`Провайдер ${key}`}
                  value={draft[key].provider}
                  onValueChange={selectedValue => update(key, {
                      provider: selectedValue as ModelConfig["provider"],
                      model:
                        selectedValue === "deepseek"
                          ? "deepseek-flash"
                          : draft.local.model,
                    })}
                >
                  <option value="local">Локальная модель · LM Studio</option>
                  <option value="deepseek">DeepSeek API</option>
                  <option value="compatible">OpenAI-совместимый API · настройка сервера</option>
                </Choice>
              </label>
              <label>
                Модель
                <ModelName label={`Модель ${key}`} options={models[draft[key].provider]} value={draft[key].model}
                  onChange={model=>update(key,{model})}/>
              </label>
              {(capabilities[draft[key].provider]?.thinking_models || []).includes(draft[key].model) && <label>
                Thinking
                <Choice aria-label={`Thinking ${key}`} value={draft[key].thinking || "off"} onValueChange={selectedValue => update(key,{thinking:selectedValue as ModelConfig["thinking"]})}>
                  <option value="off">Off</option><option value="low">Low</option><option value="high">High</option>
                </Choice>
                <span className="muted small">Размышления входят в лимит ответа. Temperature при Thinking не применяется. {key==='summary' && 'При чтении нового мира используется выбранный доступный режим.'}</span>
              </label>}
            </div>
            <ModelBudget stage={key} value={draft[key]} change={patch=>update(key,patch)}/>
            {key==="game" && <details><summary>Память истории</summary>
              <label>Последних ходов в контексте<Input type="number" min="2" max="20" value={draft.game.recent_turns} onChange={e=>update(key,{recent_turns:+e.target.value})}/></label>
            </details>}
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
                    api_key: draft[key].provider === "deepseek" ? apiKey : undefined,
                  });
                  setModels(previous=>({...previous,[draft[key].provider]:r.models}));
                  if (draft[key].provider==="local") setLoaded(r.loaded.map((m) => m.model_key));
                  toast.success(r.models.length ? "Список моделей обновлён" : "Провайдер вернул пустой список. Можно ввести имя модели.");
                })
              }
            >
              Обновить список моделей
            </Button>
          </fieldset>
        ))}
        <fieldset>
          <legend>Загрузка локальной модели</legend>
          <div className="form-grid">
            <label>
              Модель
              <ModelName label="Модель для загрузки" options={models.local} value={draft.local.model}
                onChange={model=>setDraft(d=>({...d,local:{...d.local,model}}))}/>
            </label>
            <label>
              Контекст
              <Input
                aria-label="Контекст загрузки локальной модели"
                type="number"
                min="8192"
                step="1"
                value={draft.local.context_length}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    local: { ...d.local, context_length: +e.target.value },
                  }))
                }
              />
              <span className="muted small">Для локальных запросов учитывается фактический контекст загруженной модели.</span>
            </label>
            <label>
              Eval Batch Size
              <Choice
                value={draft.local.eval_batch_size}
                onValueChange={selectedValue => setDraft((d) => ({
                    ...d,
                    local: {
                      ...d.local,
                      eval_batch_size: +selectedValue as 512,
                    },
                  }))}
              >
                {[256, 512, 1024, 2048].map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </Choice>
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
        <details className="theme-disclosure"><summary>Тема мира</summary><ThemeSelector/></details>
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
                setSaving(true);
                try {
                  if (apiKey.trim()) {
                    await api("/credentials/deepseek",{api_key:apiKey},"PUT");
                    setStored(true); setApiKey("");
                  }
                  await save(draft);
                  onOpenChange(false);
                } finally { setSaving(false); }
                toast.success("Настройки сохранены");
              })
            }
          >
            {saving ? 'Сохраняем…' : 'Сохранить настройки'}
          </Button>
          <Button variant="ghost" onClick={() => setDraft(defaults)}>
            По умолчанию
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ModelName({label,options,value,onChange}:{label:string;options?:string[];value:string;onChange:(name:string)=>void}) {
  const [custom,setCustom]=useState(false);
  if (!options?.length || custom) return <>
    <Input aria-label={label} value={value} onChange={e=>onChange(e.target.value)}/>
    {!!options?.length && <button type="button" className="model-list-action" onClick={()=>setCustom(false)}>Выбрать из списка</button>}
  </>;
  const names=options.includes(value) || !value ? options : [value,...options];
  return <>
    <Choice aria-label={label} value={value} onValueChange={onChange}>
      {!value && <option value="">Выберите модель</option>}
      {names.map(name=><option key={name} value={name}>{name}</option>)}
    </Choice>
    <button type="button" className="model-list-action" onClick={()=>setCustom(true)}>Ввести имя вручную</button>
  </>;
}
