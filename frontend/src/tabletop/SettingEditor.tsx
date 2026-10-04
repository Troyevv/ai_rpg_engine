import { AuthoringProgress, useAuthoring } from "./AuthoringProgress";
import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { Preferences } from "../types";
import { ChoiceControl } from "@/components/choice/ChoiceControl";

type Value =
  null | string | number | boolean | Value[] | { [key: string]: Value };
type Schema = {
  type?: string;
  title?: string;
  description?: string;
  default?: Value;
  const?: Value;
  enum?: Value[];
  $ref?: string;
  properties?: Record<string, Schema>;
  additionalProperties?: Schema | boolean;
  items?: Schema;
  anyOf?: Schema[];
  oneOf?: Schema[];
  minimum?: number;
  maximum?: number;
};
type Definition = {
  id: string;
  name: string;
  description: string;
  content: Record<string, Value>;
  [key: string]: Value;
};
type World = {
  id: string;
  revision: number;
  status: string;
  definition: Definition;
};
const labels: Record<string, string> = {
  name: "Название",
  description: "Описание",
  genre: "Жанр",
  tone: "Тон",
  world_rules: "Законы мира",
  themes: "Темы",
  technology_description: "Технологии",
  supernatural_description: "Необычные явления",
  society_description: "Общество",
  conflict_description: "Конфликты",
  custom_lore: "Лор",
  archetype_label: "Название ролей",
  currency_label: "Валюта",
  starting_currency: "Стартовые средства",
  skills: "Навыки",
  species: "Разумные существа",
  archetypes: "Профессии и роли",
  backgrounds: "Происхождения",
  features: "Способности",
  powers: "Силы и заклинания",
  spellcasting: "Применение сил",
  levels: "Развитие",
  subclasses: "Специализации",
  feats: "Черты",
  creatures: "Опасности и существа",
  items: "Предметы и снаряжение",
  damage_types: "Типы урона",
  resources: "Ресурсы",
  equipment_profiles: "Слоты снаряжения",
  world_mechanics: "Особые системы мира",
  components: "Компоненты",
  equipment_slots: "Слоты",
  value: "Цена",
  weight: "Вес",
  default_ability: "Характеристика",
  alternate_abilities: "Другие допустимые характеристики",
  tags: "Метки",
  damage_expression: "Кубики урона",
  damage_type: "Тип урона",
  capacity: "Вместимость",
  initial: "Начальное количество",
  maximum: "Максимум",
  recovery: "Восстановление",
  recovery_amount: "Объём восстановления",
  skill_count: "Навыков на выбор",
  hit_die: "Кость здоровья",
  saves: "Спасброски",
  equipment: "Начальное снаряжение",
  primary_abilities: "Основные характеристики",
  base_hp: "Здоровье",
  base_armor: "Защита",
  attacks: "Атаки",
  attributes: "Характеристики",
  movement: "Перемещение",
  category: "Категория",
  threat: "Угроза (расчёт движка)",
  id: "Идентификатор",
  type: "Вид компонента",
};
function resolve(schema: Schema, defs: Record<string, Schema>): Schema {
  return schema.$ref ? defs[schema.$ref.split("/").at(-1)!] || schema : schema;
}
function initial(raw: Schema, defs: Record<string, Schema>): Value {
  const s = resolve(raw, defs);
  if (s.default !== undefined) return structuredClone(s.default);
  if (s.const !== undefined) return s.const;
  if (s.enum) return s.enum[0];
  if (s.anyOf || s.oneOf) return initial((s.anyOf || s.oneOf)![0], defs);
  if (s.type === "array") return [];
  if (s.type === "object")
    return Object.fromEntries(
      Object.entries(s.properties || {}).map(([k, v]) => [k, initial(v, defs)]),
    );
  if (s.type === "number" || s.type === "integer") return s.minimum ?? 0;
  if (s.type === "boolean") return false;
  return "";
}
function EditorField({
  raw,
  value,
  onChange,
  defs,
  label,
}: {
  raw: Schema;
  value: Value;
  onChange: (v: Value) => void;
  defs: Record<string, Schema>;
  label: string;
}) {
  const [key, setKey] = useState("");
  const s = resolve(raw, defs),
    variants = s.oneOf || s.anyOf;
  if (variants) {
    const models = variants.map((v) => resolve(v, defs));
    const index = Math.max(
      0,
      models.findIndex((m) =>
        m.type === "null"
          ? value === null
          : m.properties?.type?.const
            ? typeof value === "object" &&
              value !== null &&
              !Array.isArray(value) &&
              value.type === m.properties.type.const
            : m.type === typeof value,
      ),
    );
    return (
      <div>
        <ChoiceControl
          aria-label={`${label}: тип`}
          value={String(index)}
          options={models.map((v, i) => ({
            value: String(i),
            label: String(v.properties?.type?.const || v.title || v.type || i),
          }))}
          onValueChange={(v) => onChange(initial(variants[Number(v)], defs))}
        />
        <EditorField
          raw={variants[index]}
          value={value}
          onChange={onChange}
          defs={defs}
          label={label}
        />
      </div>
    );
  }
  if (s.const !== undefined)
    return (
      <p>
        {label}: {String(s.const)}
      </p>
    );
  if (s.enum)
    return (
      <label>
        {label}
        <ChoiceControl
          aria-label={label}
          value={String(value ?? "")}
          options={s.enum.map((v) => ({ value: String(v), label: String(v) }))}
          onValueChange={(v) => onChange(s.enum!.find((e) => String(e) === v)!)}
        />
      </label>
    );
  if (s.type === "array") {
    const list = Array.isArray(value) ? value : [];
    return (
      <details>
        <summary>
          {label} · {list.length}
        </summary>
        {list.map((entry, i) => (
          <div className="setting-entry" key={i}>
            <EditorField
              raw={s.items || { type: "string" }}
              value={entry}
              onChange={(v) => onChange(list.map((e, n) => (n === i ? v : e)))}
              defs={defs}
              label={`${label} ${i + 1}`}
            />
            <button
              type="button"
              onClick={() => onChange(list.filter((_, n) => n !== i))}
            >
              Удалить {i + 1}
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() =>
            onChange([...list, initial(s.items || { type: "string" }, defs)])
          }
        >
          Добавить: {label}
        </button>
      </details>
    );
  }
  if (s.type === "object" || s.properties) {
    const object =
      value && typeof value === "object" && !Array.isArray(value) ? value : {};
    return (
      <div className="setting-fields">
        {s.properties ? (
          Object.entries(s.properties)
            .filter(([k]) => !["schema_version", "revision"].includes(k))
            .map(([k, v]) => (
              <EditorField
                key={k}
                raw={v}
                value={object[k] ?? initial(v, defs)}
                onChange={(next) => onChange({ ...object, [k]: next })}
                defs={defs}
                label={labels[k] || k}
              />
            ))
        ) : (
          <>
            {Object.entries(object).map(([k, v]) => (
              <details key={k}>
                <summary>
                  {typeof v === "object" && v && !Array.isArray(v)
                    ? String(v.name || k)
                    : k}
                </summary>
                <EditorField
                  raw={
                    typeof s.additionalProperties === "object"
                      ? s.additionalProperties
                      : { type: "string" }
                  }
                  value={v}
                  onChange={(next) => onChange({ ...object, [k]: next })}
                  defs={defs}
                  label={k}
                />
                <button
                  type="button"
                  onClick={() =>
                    onChange(
                      Object.fromEntries(
                        Object.entries(object).filter(([id]) => id !== k),
                      ),
                    )
                  }
                >
                  Удалить: {k}
                </button>
              </details>
            ))}
            <div className="setting-add">
              <input
                aria-label={`Новый идентификатор: ${label}`}
                placeholder="Новый идентификатор"
                value={key}
                onChange={(e) => setKey(e.target.value)}
              />
              <button
                type="button"
                disabled={!/^[a-zA-Z0-9_-]+$/.test(key) || key in object}
                onClick={() => {
                  const item = initial(
                    typeof s.additionalProperties === "object"
                      ? s.additionalProperties
                      : { type: "string" },
                    defs,
                  );
                  onChange({
                    ...object,
                    [key]:
                      item &&
                      typeof item === "object" &&
                      !Array.isArray(item) &&
                      "id" in item
                        ? { ...item, id: key }
                        : item,
                  });
                  setKey("");
                }}
              >
                Добавить
              </button>
            </div>
          </>
        )}
      </div>
    );
  }
  if (s.type === "boolean")
    return (
      <label>
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(e.target.checked)}
        />
        {label}
      </label>
    );
  if (s.type === "null") return null;
  return (
    <label>
      {label}
      {s.type === "integer" || s.type === "number" ? (
        <input
          type="number"
          aria-label={label}
          min={s.minimum}
          max={s.maximum}
          value={Number(value || 0)}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      ) : (
        <textarea
          aria-label={label}
          rows={label.includes("Описание") ? 3 : 1}
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </label>
  );
}
export function SettingEditor({
  prefs,
  apiKey,
  onUse,
}: {
  prefs: Preferences;
  apiKey: string;
  onUse: (world: World) => void;
}) {
  const authoring = useAuthoring("setting");
  const [list, setList] = useState<{ id: string; name: string }[]>([]),
    [world, setWorld] = useState<World | null>(null),
    [draft, setDraft] = useState<Definition | null>(null),
    [schema, setSchema] = useState<
      (Schema & { $defs: Record<string, Schema> }) | null
    >(null),
    [concept, setConcept] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [section, setSection] = useState("overview");
  const [profiles, setProfiles] = useState<string[]>([]);
  const [profile, setProfile] = useState("NORMAL");
  const [seed, setSeed] = useState(0);
  const refresh = () =>
    api<{ id: string; name: string }[]>("/tabletop/settings/worlds").then(
      setList,
    );
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
    api<{ profiles: Record<string, unknown> }>("/tabletop/settings/generation-profiles")
      .then((v) => setProfiles(Object.keys(v.profiles)))
      .catch((e) => setError(e.message));
    api<Schema & { $defs: Record<string, Schema> }>("/tabletop/settings/schema")
      .then(setSchema)
      .catch((e) => setError(e.message));
  }, []);
  const accept = (value: World) => {
    setWorld(value);
    setDraft(value.definition);
  };
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const save = async (confirm = false) => {
    const value = await api<World>("/tabletop/settings/worlds", {
      definition: draft,
      revision: world?.revision,
      confirm,
    });
    accept(value);
    await refresh();
    return value;
  };
  return (
    <section className="tt-panel setting-editor">
      <h2>Миры</h2>
      <AuthoringProgress
        job={authoring.job}
        busy={busy}
        resume={() =>
          void run(async () => {
            accept(
              await authoring.generate<World>(
                {
                  ...authoring.job!.request,
                  config: prefs.summary,
                  api_key: apiKey,
                },
                true,
              ),
            );
            await refresh();
          })
        }
      />
      <p>Создай вселенную один раз и используй её в разных приключениях.</p>
      {error && (
        <p role="alert" className="tt-error">
          {error}
        </p>
      )}
      {Array.isArray(draft?.diagnostics) && draft.diagnostics.length > 0 && (
        <details><summary>Ограничения генерации ({draft.diagnostics.length})</summary>
          <ul>{draft.diagnostics.map((value, index) => <li key={index}>{String((value as Record<string, Value>).message)}</li>)}</ul>
        </details>
      )}
      <ChoiceControl
        aria-label="Сохранённый мир"
        value={world?.id || ""}
        options={[
          { value: "", label: "Выбрать мир", disabled: true },
          ...list.map((w) => ({ value: w.id, label: w.name })),
        ]}
        onValueChange={(id) =>
          void run(async () =>
            accept(await api<World>("/tabletop/settings/worlds/" + id)),
          )
        }
      />
      <label>
        Опишите ваш мир
        <textarea
          aria-label="Описание нового мира"
          value={concept}
          onChange={(e) => setConcept(e.target.value)}
        />
      </label>
      <label>Объём мира
        <ChoiceControl value={profile} options={profiles.map((v) => ({value:v,label:({SMALL:"Небольшой",NORMAL:"Обычный",LARGE:"Большой"} as Record<string,string>)[v] || v}))} onValueChange={setProfile} />
      </label>
      <label>Seed мира
        <input type="number" min={0} max={2147483647} value={seed} onChange={(e) => setSeed(Math.max(0,Math.min(2147483647,Math.trunc(Number(e.target.value)))))} />
      </label>
      <div className="setting-actions">
        <button
          disabled={busy || concept.trim().length < 3}
          onClick={() =>
            void run(async () => {
              accept(
                await authoring.generate<World>({
                  concept,
                  generation: {profile,seed},
                  config: prefs.summary,
                  api_key: apiKey,
                }),
              );
              await refresh();
            })
          }
        >
          Создать структуру мира
        </button>
        <button
          disabled={busy}
          onClick={() =>
            void run(async () => {
              accept(
                await api<World>(
                  "/tabletop/settings/worlds/import-catalog",
                  {},
                ),
              );
              await refresh();
            })
          }
        >
          Открыть существующий каталог
        </button>
      </div>
      {busy && <p role="status">Создание и проверка структуры…</p>}
      {draft && schema && (
        <>
          <ChoiceControl
            aria-label="Раздел мира"
            value={section}
            options={[
              { value: "overview", label: "Обзор мира" },
              ...Object.keys(draft.content).map((k) => ({
                value: k,
                label: labels[k] || k,
              })),
            ]}
            onValueChange={setSection}
          />
          {section === "overview" ? (
            <div className="setting-fields">
              {Object.entries(schema.properties || {})
                .filter(
                  ([k]) =>
                    !["content", "schema_version", "revision", "id", "semantic_source", "compiler_version", "diagnostics", "generation_config", "generation_metadata"].includes(
                      k,
                    ),
                )
                .map(([key, raw]) => (
                  <EditorField
                    key={key}
                    raw={raw}
                    value={draft[key]}
                    defs={schema.$defs}
                    label={labels[key] || key}
                    onChange={(v) => setDraft({ ...draft, [key]: v })}
                  />
                ))}
            </div>
          ) : (
            <EditorField
              raw={
                resolve(schema.properties!.content, schema.$defs).properties![
                  section
                ]
              }
              value={draft.content[section]}
              onChange={(v) =>
                setDraft({
                  ...draft,
                  content: { ...draft.content, [section]: v },
                })
              }
              defs={schema.$defs}
              label={labels[section] || section}
            />
          )}
          <p>
            Изменения проверяются перед сохранением. Кампании сохраняют
            выбранную версию мира.
          </p>
          <div className="setting-actions">
            <button
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  await save();
                })
              }
            >
              Сохранить мир
            </button>
            <button
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  const saved = await save(true);
                  onUse(saved);
                })
              }
            >
              Подтвердить мир и создать кампанию
            </button>
            {section !== "overview" && draft.semantic_source && Object.keys(draft.semantic_source as object).length > 0 && (
              <button
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    await save();
                    accept(
                      await authoring.generate<World>({
                        concept: concept || draft.description || draft.name,
                        config: prefs.summary,
                        api_key: apiKey,
                        setting_id: world!.id,
                        section,
                      }),
                    );
                  })
                }
              >
                Перегенерировать раздел
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}
