import { createContext, useContext, useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "./api";
import type { Save, Preferences } from "./types";
import { Button } from "./components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "./components/ui/dialog";
import { Textarea } from "./components/ui/textarea";
import { Input } from "./components/ui/input";

type Json = any;
type Schema = {
  type?: string;
  properties?: Record<string, Schema>;
  items?: Schema;
  additionalProperties?: Schema | boolean;
  anyOf?: Schema[];
  $ref?: string;
  enum?: Json[];
  default?: Json;
  const?: Json;
};
const labels: Record<string, string> = {
  due_minute: "Срок (минута мира)",
  dependencies: "Зависимости",
  condition_id: "Связанное состояние",
  location_ids: "Места организации",
  since_date: "Дата начала",
  until_date: "Дата окончания",
  min_age: "Начиная с возраста",
  max_age: "До возраста",
  stage: "Этап",
  meaning: "Значение",
  label: "Подпись",
  mode: "Связь с миром",
  card: "Карточка",
  character: "Каноническое состояние",
  starting_scene: "Стартовая сцена / Обстоятельства появления",
  proposals: "Предложения связей и новых сущностей",
  knowledge: "Знания",
  secrets: "Личные тайны",
  name: "Имя",
  aliases: "Другие имена",
  fields: "Поля карточки",
  id: "ID",
  location_id: "Начальное место",
  situation: "Текущая ситуация",
  birth_date: "Дата рождения",
  life_status: "Жизненный статус",
  life_fact_id: "Основание жизненного статуса",
  display_name: "Отображаемое имя",
  name_history: "История имён",
  capabilities: "Способности",
  developmental_stage: "Этап развития",
  parentage_complete_fact_id: "Основание происхождения",
  reproductive_capability: "Репродуктивные возможности",
  biological_sex: "Пол",
  identity_components: "Состав имени",
  birth_provenance: "Происхождение при рождении",
  appearance: "Внешность",
  portraits: "Портреты",
  personality: "Личность",
  values: "Долговременные ценности",
  physical_state: "Физическое состояние",
  emotion: "Эмоция",
  emotion_source_sequence: "Ход основания эмоции",
  goals: "Цели",
  intentions: "Намерения",
  obligations: "Обязательства",
  kind: "Тип",
  value: "Значение",
  evidence: "Основание",
  approved: "Я подтверждаю это предложение",
  fact_id: "ID существующего факта",
  source_actor_id: "Кто сообщил",
  text: "Описание",
  holders: "Кто знает (ID персонажей)",
  conscious: "В сознании",
  can_perceive: "Может воспринимать",
  can_act: "Может действовать",
  can_speak: "Может говорить",
  can_move: "Может двигаться",
  items: "Элементы",
  legacy_text: "Описание внешности",
  applied: "Применённые изменения",
  revision: "Версия",
  status: "Состояние",
  source_ids: "Источники",
  fact_ids: "Факты",
  witnesses: "Свидетели",
  field: "Поле",
  evidence_ids: "Подтверждения",
  history: "История",
  source_turn: "Ход основания",
  source_event_id: "Событие-основание",
  category: "Категория",
  expected_revision: "Ожидаемая версия",
  created_turn: "Ход создания",
  updated_turn: "Ход изменения",
  closed_turn: "Ход завершения",
  reason: "Причина",
  superseded_by: "Заменено",
  source_id: "От персонажа",
  target_id: "К персонажу",
  context: "Контекст",
  dimensions: "Чувства",
  actor_id: "Персонаж",
  organization_id: "Организация",
  title: "Название",
  description: "Описание",
  parent_id: "Родительское место",
  since: "Начало",
  until: "Окончание",
  outcome: "Итог",
  traits: "Характер",
  communication: "Стиль общения",
  habits: "Привычки",
  strengths: "Сильные стороны",
  weaknesses: "Слабости",
  fears: "Страхи",
  preferences: "Предпочтения",
  temperament: "Темперамент",
};
const choices: Record<string, string> = {
  newcomer: "Без установленных знакомств",
  integrated: "Связать с существующим миром",
  alive: "Жив",
  dead: "Мёртв",
  unknown: "Не установлено",
  missing: "Пропал",
  infant: "Младенец",
  child: "Ребёнок",
  adolescent: "Подросток",
  adult: "Взрослый",
  female: "Женский",
  male: "Мужской",
  active: "Активно",
  completed: "Выполнено",
  failed: "Не удалось",
  cancelled: "Отменено",
  expired: "Утратило актуальность",
  superseded: "Заменено",
  known: "Известно",
  suspected: "Предположение",
  location: "Место",
  organization: "Организация",
  objective_relation: "Объективная связь",
  relationship: "Направленные чувства",
  residence: "Место жительства",
  role: "Роль",
  can_become_pregnant: "Может вынашивать",
  can_impregnate: "Может зачать с партнёром",
  neither: "Ни то ни другое",
};
const EditorContext = createContext<Json>({});
const systemFields = new Set([
  "revision",
  "source_sequence",
  "source_turn",
  "source_event_id",
  "life_fact_id",
  "parentage_complete_fact_id",
  "closure_fact_id",
  "fact_ids",
  "fact_id",
  "source_ids",
  "witnesses",
  "seen_sources",
  "applied",
  "review_required",
  "reviewed_signature",
  "birth_provenance",
  "name_history",
]);
const owned = new Set([
  "character.id",
  "character.name_history",
  "character.birth_provenance",
  "character.portraits",
  "character.life_fact_id",
  "character.parentage_complete_fact_id",
  "character.emotion_source_sequence",
  "character.display_name",
  "character.situation",
]);
function resolved(s: Schema, defs: Record<string, Schema>): Schema {
  if (s.$ref) return resolved(defs[s.$ref.split("/").at(-1)!] || {}, defs);
  return s;
}
function initial(s: Schema, defs: Record<string, Schema>): Json {
  s = resolved(s, defs);
  if (s.default !== undefined) return structuredClone(s.default);
  if (s.const !== undefined) return s.const;
  if (s.anyOf)
    return initial(s.anyOf.find((x) => x.type !== "null") || {}, defs);
  if (s.enum) return s.enum[0];
  if (s.type === "object")
    return Object.fromEntries(
      Object.entries(s.properties || {}).map(([k, v]) => [
        k,
        k === "id" ? crypto.randomUUID() : initial(v, defs),
      ]),
    );
  if (s.type === "array") return [];
  if (s.type === "boolean") return false;
  if (s.type === "number" || s.type === "integer") return 0;
  return "";
}
function Editor({
  value,
  schema,
  defs,
  path,
  label,
  onChange,
  generate,
  busy,
}: {
  value: Json;
  schema: Schema;
  defs: Record<string, Schema>;
  path: string;
  label: string;
  onChange: (v: Json) => void;
  generate: (path: string) => void;
  busy: boolean;
}) {
  const context = useContext(EditorContext);
  const [key, setKey] = useState("");
  const parts = path.split(".");
  const field = parts.at(-1)!;
  if (parts[0] === "proposals" && parts.length === 3 && field === "value") {
    schema =
      context.data.proposal_schemas[
        context.draft.proposals[Number(parts[1])]?.kind
      ] || schema;
  }
  let s = resolved(schema, defs);
  const nullable = !!s.anyOf?.some((x) => x.type === "null");
  if (s.anyOf) s = resolved(s.anyOf.find((x) => x.type !== "null") || {}, defs);
  if (owned.has(path) || (parts[0] === "character" && systemFields.has(field)))
    return null;
  const refKind =
    field === "location_id" || field === "parent_id"
      ? "locations"
      : field === "organization_id"
        ? "organizations"
        : [
              "actor_id",
              "source_id",
              "target_id",
              "source_actor_id",
              "pov_actor_id",
            ].includes(field) ||
            (parts.includes("holders") && !Array.isArray(value))
          ? "characters"
          : field === "fact_id"
            ? "knowledge_facts"
            : field === "source_event_id"
              ? "events"
              : null;
  if (refKind) {
    const options = [
      ...(context.data.context[refKind] || []),
      ...context.draft.proposals
        .filter(
          (p: Json) =>
            p.kind ===
              (refKind === "locations"
                ? "location"
                : refKind === "organizations"
                  ? "organization"
                  : "_") && p.value.id,
        )
        .map((p: Json) => p.value),
    ];
    if (refKind === "characters")
      options.unshift({
        id: context.draft.character.id,
        name: context.draft.card.name || "Новый персонаж",
      });
    return (
      <div className="protagonist-field">
        <label>
          {label}
          <select
            aria-label={label}
            value={value || ""}
            disabled={busy}
            onChange={(e) => onChange(e.target.value || null)}
          >
            <option value="">Не выбрано</option>
            {options.map((x: Json) => (
              <option key={x.id} value={x.id}>
                {x.name || x.text}
              </option>
            ))}
          </select>
        </label>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={busy}
          onClick={() => generate(path)}
        >
          Предложить
        </Button>
      </div>
    );
  }
  const gen = (
    <Button
      type="button"
      size="sm"
      variant="ghost"
      disabled={busy}
      onClick={() => generate(path)}
    >
      Предложить
    </Button>
  );
  if (value === null)
    return (
      <div className="protagonist-field">
        <span>{label}: не задано</span>
        <Button
          size="sm"
          variant="ghost"
          disabled={busy}
          onClick={() => onChange(initial(s, defs))}
        >
          Заполнить
        </Button>
        {gen}
      </div>
    );
  if (Array.isArray(value))
    return (
      <details>
        <summary>
          {label} · {value.length}
        </summary>
        {gen}
        {value.map((v, i) => (
          <div key={i}>
            <Editor
              value={v}
              schema={s.items || {}}
              defs={defs}
              path={path + "." + i}
              label={label + " " + (i + 1)}
              onChange={(x) =>
                onChange(value.map((old, j) => (i === j ? x : old)))
              }
              generate={generate}
              busy={busy}
            />
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => onChange(value.filter((_, j) => j !== i))}
            >
              Удалить
            </Button>
          </div>
        ))}
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => onChange([...value, initial(s.items || {}, defs)])}
        >
          Добавить
        </Button>
      </details>
    );
  if (typeof value === "object")
    return (
      <details open={path === "card"}>
        <summary>{label}</summary>
        {gen}
        {Object.entries({
          ...Object.fromEntries(
            Object.keys(s.properties || {}).map((k) => [k, value[k]]),
          ),
          ...value,
        }).map(([k, v]) => (
          <Editor
            key={k}
            value={v ?? null}
            schema={
              s.properties?.[k] ||
              (typeof s.additionalProperties === "object"
                ? s.additionalProperties
                : {})
            }
            defs={defs}
            path={path + "." + k}
            label={labels[k] || k}
            onChange={(x) =>
              onChange(
                k === "kind" && parts[0] === "proposals" && parts.length === 2
                  ? {
                      ...value,
                      kind: x,
                      value: initial(
                        context.data.proposal_schemas[x] || {},
                        defs,
                      ),
                      approved: false,
                    }
                  : { ...value, [k]: x },
              )
            }
            generate={generate}
            busy={busy}
          />
        ))}
        {!s.properties && (
          <div>
            <Input
              aria-label="Название поля"
              value={key}
              onChange={(e) => setKey(e.target.value)}
            />
            <Button
              size="sm"
              disabled={busy || !key.trim()}
              onClick={() => {
                const added = initial(
                  typeof s.additionalProperties === "object"
                    ? s.additionalProperties
                    : {},
                  defs,
                );
                if (
                  added &&
                  typeof added === "object" &&
                  !Array.isArray(added) &&
                  "id" in added
                )
                  added.id = key.trim();
                onChange({
                  ...value,
                  [key.trim()]: added,
                });
                setKey("");
              }}
            >
              Добавить поле
            </Button>
          </div>
        )}
        {nullable && (
          <Button size="sm" variant="ghost" onClick={() => onChange(null)}>
            Не задавать
          </Button>
        )}
      </details>
    );
  return (
    <div className="protagonist-field">
      <label>
        {label}
        {s.enum ? (
          <select
            aria-label={label}
            value={String(value)}
            disabled={busy}
            onChange={(e) => onChange(e.target.value)}
          >
            {s.enum.map((v) => (
              <option key={String(v)} value={String(v)}>
                {choices[String(v)] || String(v)}
              </option>
            ))}
          </select>
        ) : typeof value === "boolean" ? (
          <input
            type="checkbox"
            checked={value}
            disabled={busy}
            onChange={(e) => onChange(e.target.checked)}
          />
        ) : typeof value === "number" ? (
          <Input
            aria-label={label}
            type="number"
            value={value}
            disabled={busy}
            onChange={(e) => onChange(Number(e.target.value))}
          />
        ) : (
          <Textarea
            aria-label={label}
            value={String(value)}
            disabled={busy}
            onChange={(e) => onChange(e.target.value)}
          />
        )}
      </label>
      {gen}
      {nullable && (
        <Button
          size="sm"
          variant="ghost"
          disabled={busy}
          onClick={() => onChange(null)}
        >
          Не задавать
        </Button>
      )}
    </div>
  );
}
export function Protagonist({
  save,
  open,
  onOpenChange,
  refresh,
  prefs,
  apiKey,
}: {
  save: Save;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  refresh: (after: Save) => void;
  prefs: Preferences;
  apiKey: string;
}) {
  const [revision, setRevision] = useState(save.revision);
  const [operationId, setOperationId] = useState("");
  const [data, setData] = useState<Json>(null);
  const [draft, setDraft] = useState<Json>(null);
  const [create, setCreate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [actor, setActor] = useState("");
  useEffect(() => {
    if (!open) return;
    const id = crypto.randomUUID();
    setRevision(save.revision);
    setOperationId(id);
    setData(null);
    setDraft(null);
    setCreate(false);
    setPreview(false);
    setError("");
    setActor("");
    let active = true;
    api<Json>(`/saves/${save.id}/protagonist/draft?operation_id=${id}`)
      .then((d) => {
        if (active) {
          setData(d);
          setDraft(d.draft);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [open, save.id]);
  const change = (value: Json) => {
    setDraft(value);
    setPreview(false);
  };
  const generate = async (path: string) => {
    setBusy(true);
    setError("");
    try {
      const result = await api<Json>(`/saves/${save.id}/protagonist/generate`, {
        revision,
        draft,
        path,
        instruction,
        config: prefs.game,
        api_key: apiKey,
      });
      change(result.draft);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const commit = async (check: boolean) => {
    setBusy(true);
    setError("");
    try {
      const after=await api<Save>(`/saves/${save.id}/protagonist`, {
        revision,
        operation_id: operationId,
        operation: "permanent",
        actor_id: create ? null : actor,
        draft: create ? draft : null,
        preview: check,
      });
      if (check) setPreview(true);
      else {
        onOpenChange(false);
        refresh(after);
        toast.success("Главный герой выбран");
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!busy) onOpenChange(v);
      }}
    >
      <DialogContent className="protagonist-dialog mobile-sheet">
        <DialogHeader>
          <DialogTitle>Смена главного героя</DialogTitle>
          <DialogDescription>
            Мир и время сохраняются. У каждого персонажа остаются собственные
            знания, личность и прошлое.
          </DialogDescription>
        </DialogHeader>
        <div className="protagonist-paths">
          <Button
            variant={create ? "outline" : "default"}
            disabled={busy}
            onClick={() => {
              setCreate(false);
              setPreview(false);
            }}
          >
            Выбрать персонажа
          </Button>
          <Button
            variant={create ? "default" : "outline"}
            disabled={busy || !draft}
            onClick={() => {
              setCreate(true);
              setPreview(false);
            }}
          >
            Создать нового
          </Button>
        </div>
        {!create ? (
          <label>
            Новый главный герой
            <select
              aria-label="Новый главный герой"
              value={actor}
              disabled={busy}
              onChange={(e) => {
                setActor(e.target.value);
                setPreview(false);
              }}
            >
              <option value="">Выбери персонажа</option>
              {save.state.characters
                .filter(
                  (c) =>
                    save.state.world?.characters[c.id]?.life_status !== "dead",
                )
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
            </select>
          </label>
        ) : draft && data ? (
          <>
            <p className="muted">
              Все изменения остаются черновиком до подтверждения. Для младенца
              или недееспособного персонажа начнётся наблюдение.
            </p>
            <label>
              Пожелания для генерации
              <Textarea
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                disabled={busy}
              />
            </label>
            <Button disabled={busy} onClick={() => void generate("")}>
              Создать полный черновик моделью
            </Button>
            <details>
              <summary>Существующие персонажи, места и организации</summary>
              {["characters", "locations", "organizations", "public_facts"].map(
                (kind) => (
                  <ul key={kind}>
                    {data.context[kind]?.map((x: Json) => (
                      <li key={x.id}>
                        {x.name || x.text} — <code>{x.id}</code>
                      </li>
                    ))}
                  </ul>
                ),
              )}
            </details>
            <EditorContext.Provider value={{ data, draft }}>
              {Object.entries(
                data.schema.properties as Record<string, Schema>,
              ).map(([k, s]) => (
                <Editor
                  key={k}
                  value={draft[k]}
                  schema={s}
                  defs={data.schema.$defs || {}}
                  path={k}
                  label={labels[k] || k}
                  onChange={(v) => change({ ...draft, [k]: v })}
                  generate={(path) => void generate(path)}
                  busy={busy}
                />
              ))}{" "}
            </EditorContext.Provider>
          </>
        ) : (
          <p>Загрузка редактора…</p>
        )}
        {error && <p role="alert">{error}</p>}
        {preview && (
          <section aria-label="Предпросмотр">
            <h3>Готово к подтверждению</h3>
            <p>
              {create
                ? draft.card.name
                : save.state.characters.find((c) => c.id === actor)?.name}
            </p>
            {create && <p>{draft.starting_scene}</p>}
            <p>Данные проверены. Время мира не изменится.</p>
          </section>
        )}
        <div className="protagonist-actions">
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() => onOpenChange(false)}
          >
            Отмена
          </Button>
          <Button
            disabled={busy || (!create && !actor)}
            onClick={() => void commit(!preview)}
          >
            {busy
              ? "Обработка…"
              : preview
                ? "Подтвердить смену"
                : "Проверить и посмотреть"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
