import { Plus, RotateCcw, Trash2 } from "lucide-react";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Textarea } from "./components/ui/textarea";
import type { Save } from "./types";
import type { NpcReviewRecord } from "./NpcReview";
import { useState } from "react";
export type AttributeValue =
  string | null | boolean | string[] | Record<string, string | boolean | null>;
export type AttributeSchema = {
  key: string;
  label: string;
  schema: {
    type?: string;
    enum?: string[];
    anyOf?: { type?: string; enum?: string[] }[];
  };
};
const labels: Record<string, string> = {
  female: "Женский",
  male: "Мужской",
  unknown: "Неизвестно",
  alive: "Жив",
  dead: "Мёртв",
  missing: "Пропал",
  infant: "Младенец",
  child: "Ребёнок",
  adolescent: "Подросток",
  adult: "Взрослый",
  can_become_pregnant: "Может вынашивать",
  can_impregnate: "Может оплодотворять",
  neither: "Отсутствует",
  conscious: "Сознание",
  can_perceive: "Восприятие",
  can_act: "Действия",
  can_speak: "Речь",
  can_move: "Движение",
};
export function describeAttribute(value: unknown): string {
  if (value === null || value === undefined) return "Неизвестно";
  if (Array.isArray(value)) return value.map(describeAttribute).join("\n");
  if (typeof value === "object")
    return Object.entries(value)
      .map(([key, v]) => `${labels[key] || key}: ${describeAttribute(v)}`)
      .join("\n");
  if (typeof value === "boolean") return value ? "Да" : "Нет";
  return labels[String(value)] || String(value);
}
const equal = (a: unknown, b: unknown) =>
  JSON.stringify(a) === JSON.stringify(b);
function Choice({
  value,
  options,
  label,
  disabled,
  onChange,
}: {
  value: string;
  options: { value: string; label: string }[];
  label: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <div className="npc-attribute-choices" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={o.value === value}
          disabled={disabled}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
function Identity({
  value,
  onChange,
  disabled,
}: {
  value: Record<string, string>;
  onChange: (v: Record<string, string>) => void;
  disabled: boolean;
}) {
  const [key, setKey] = useState("");
  return (
    <div className="npc-attribute-list">
      {Object.entries(value).map(([k, v]) => (
        <div key={k}>
          <label>
            {k}
            <Input
              value={v}
              disabled={disabled}
              onChange={(e) => onChange({ ...value, [k]: e.target.value })}
            />
          </label>
          <Button
            variant="ghost"
            aria-label={`Удалить ${k}`}
            disabled={disabled}
            onClick={() => {
              const next = { ...value };
              delete next[k];
              onChange(next);
            }}
          >
            <Trash2 size={16} />
          </Button>
        </div>
      ))}
      <div>
        <Input
          aria-label="Название части имени"
          placeholder="Например, фамилия"
          value={key}
          disabled={disabled}
          onChange={(e) => setKey(e.target.value)}
        />
        <Button
          variant="outline"
          disabled={disabled || !key.trim() || key in value}
          onClick={() => {
            onChange({ ...value, [key]: "" });
            setKey("");
          }}
        >
          <Plus size={16} />
          Добавить
        </Button>
      </div>
    </div>
  );
}
export function NpcAttributes({
  record,
  attributes,
  patch,
  onChange,
  disabled,
}: {
  record: NpcReviewRecord;
  attributes: AttributeSchema[];
  patch: Record<string, AttributeValue>;
  onChange: (patch: Record<string, AttributeValue>) => void;
  disabled: boolean;
}) {
  return (
    <div className="npc-attributes">
      <p className="npc-review-explainer">
        Здесь — состояние, уже принятое миром. Изменяй только то, что нужно
        уточнить. Неизвестные сведения можно оставить неизвестными.
      </p>
      {attributes.map(({ key, label, schema }) => {
        const value = key in patch ? patch[key] : record.current[key];
        const changed = !equal(record.current[key], record.baseline[key]);
        const enums = schema.enum || schema.anyOf?.find((s) => s.enum)?.enum;
        const set = (v: AttributeValue) => onChange({ ...patch, [key]: v });
        return (
          <section className="npc-review-field" key={key}>
            <div className="npc-review-field-heading">
              <label htmlFor={`attribute-${key}`}>{label}</label>
              <span>
                {changed
                  ? "Изменилось в игре"
                  : value === null || value === "unknown"
                    ? "Неизвестно"
                    : value === "" || (Array.isArray(value) && !value.length)
                      ? "Не задано"
                      : "Установлено"}
              </span>
            </div>
            {enums ? (
              <Choice
                label={label}
                value={String(value ?? "null")}
                options={[
                  ...(schema.anyOf?.some((s) => s.type === "null")
                    ? [{ value: "null", label: "Неизвестно" }]
                    : []),
                  ...enums.map((v) => ({ value: v, label: labels[v] || v })),
                ]}
                disabled={disabled}
                onChange={(v) => set(v === "null" ? null : v)}
              />
            ) : key === "capabilities" ? (
              <div className="npc-capabilities">
                {Object.entries(value as Record<string, boolean | null>).map(
                  ([k, v]) => (
                    <div key={k}>
                      <span>{labels[k] || k}</span>
                      <Choice
                        label={labels[k] || k}
                        value={String(v)}
                        options={[
                          { value: "null", label: "Неизвестно" },
                          { value: "true", label: "Да" },
                          { value: "false", label: "Нет" },
                        ]}
                        disabled={disabled}
                        onChange={(next) =>
                          set({
                            ...(value as Record<string, boolean | null>),
                            [k]: next === "null" ? null : next === "true",
                          })
                        }
                      />
                    </div>
                  ),
                )}
              </div>
            ) : key === "identity_components" ? (
              <Identity
                value={value as Record<string, string>}
                disabled={disabled}
                onChange={set}
              />
            ) : Array.isArray(value) ? (
              <div className="npc-attribute-list">
                {value.map((v, i) => (
                  <div key={i}>
                    <Textarea
                      aria-label={`${label} ${i + 1}`}
                      value={v}
                      disabled={disabled}
                      rows={2}
                      onChange={(e) =>
                        set(value.map((s, n) => (n === i ? e.target.value : s)))
                      }
                    />
                    <Button
                      variant="ghost"
                      aria-label={`Удалить: ${label} ${i + 1}`}
                      disabled={disabled}
                      onClick={() => set(value.filter((_, n) => n !== i))}
                    >
                      <Trash2 size={16} />
                    </Button>
                  </div>
                ))}
                <Button
                  variant="outline"
                  disabled={disabled}
                  onClick={() => set([...value, ""])}
                >
                  <Plus size={16} />
                  Добавить: {label.toLowerCase()}
                </Button>
              </div>
            ) : key === "birth_date" ? (
              <div className="npc-birth-date">
                <Input
                  id={`attribute-${key}`}
                  value={String(value ?? "")}
                  disabled={disabled}
                  placeholder="ГГГГ-ММ-ДД · по календарю мира"
                  onChange={(e) => set(e.target.value || null)}
                />
                <small>
                  {record.age === null
                    ? "Возраст по дате не установлен."
                    : `Возраст по календарю: ${record.age}.`}{" "}
                  Если известен только возраст, укажи его в описании. Дата не
                  вычисляется автоматически.
                </small>
              </div>
            ) : (
              <Textarea
                id={`attribute-${key}`}
                value={String(value ?? "")}
                disabled={disabled}
                rows={3}
                onChange={(e) => set(e.target.value)}
              />
            )}
            {changed &&
              key in patch &&
              !equal(patch[key], record.current[key]) && (
                <div className="npc-attribute-conflict">
                  <p>
                    Мир уже изменил это поле. Твоя правка не заменит его
                    автоматически.
                  </p>
                  <Button
                    variant="outline"
                    disabled={disabled}
                    onClick={() => set(record.current[key])}
                  >
                    <RotateCcw size={14} />
                    Оставить актуальное
                  </Button>
                </div>
              )}
          </section>
        );
      })}
    </div>
  );
}
export function NpcConnections({ save, id }: { save: Save; id: string }) {
  const names = Object.fromEntries(
    save.state.characters.map((c) => [c.id, c.name]),
  );
  const relationships = Object.values(
    save.state.world?.relationships || {},
  ).filter((r) => r.source_id === id || r.target_id === id);
  const family =
    save.state.objective_relations?.filter(
      (r) => r.source_id === id || r.target_id === id,
    ) || [];
  const familyLabels: Record<string, string> = {
    spouse: "Супруги",
    partner: "Партнёры",
    engaged: "Помолвка",
    parent: "Родитель",
    adoptive_parent: "Приёмный родитель",
    sibling: "Брат / сестра",
    friend: "Друзья",
    close_friend: "Близкие друзья",
    coworker: "Коллеги",
    guardian: "Опекун",
  };
  const roles =
    save.state.residence_roles?.roles.filter((r) => r.actor_id === id) || [];
  const residences =
    save.state.residence_roles?.residences.filter((r) => r.actor_id === id) ||
    [];
  const actor = save.state.characters.find((c) => c.id === id);
  return (
    <div className="npc-connections">
      <p className="npc-review-explainer">
        Связи уже сохранены вместе с ходом. Подтверждение карточки не создаёт и
        не заменяет их.
      </p>
      <h3>Отношения</h3>
      {relationships.length ? (
        relationships.map((r) => (
          <article key={`${r.source_id}:${r.target_id}`}>
            <strong>
              {names[r.source_id]} → {names[r.target_id]}
            </strong>
            <p>{r.context}</p>
          </article>
        ))
      ) : (
        <p className="muted">Отношений пока нет.</p>
      )}
      <h3>Родство и социальные связи</h3>
      {family.length ? (
        family.map((r) => (
          <article key={r.id}>
            <strong>{familyLabels[r.kind] || r.kind}</strong>
            <p>
              {names[r.source_id]} · {names[r.target_id]}
            </p>
            <small>
              {r.status === "active" ? "Действует" : "Завершено"}
              {r.outcome ? ` · ${r.outcome}` : ""}
            </small>
          </article>
        ))
      ) : (
        <p className="muted">Связей пока нет.</p>
      )}
      <h3>Роли и проживание</h3>
      {[...roles, ...residences].length ? (
        [...roles, ...residences].map((r) => (
          <article key={r.id}>
            <strong>{r.label}</strong>
            <p>{r.organization || r.outcome}</p>
          </article>
        ))
      ) : (
        <p className="muted">Назначений пока нет.</p>
      )}
      <h3>Состояния и ограничения</h3>
      {actor?.dossier?.conditions.length ? (
        actor.dossier.conditions.map((condition) => (
          <article key={condition.id}>
            <strong>{condition.description}</strong>
            <p>{condition.restrictions.join(" · ")}</p>
            <small>
              {condition.status === "active" ? "Действует" : "Завершено"}
            </small>
          </article>
        ))
      ) : (
        <p className="muted">Состояний пока нет.</p>
      )}
      <h3>Установленная внешность и личность</h3>
      {[
        "Внешность",
        "Характер",
        "Стиль общения",
        "Привычки",
        "Сильные стороны",
        "Слабости",
        "Страхи и уязвимости",
        "Предпочтения",
        "Темперамент",
        "Ценности",
      ].map((f) =>
        actor?.fields[f] ? (
          <article key={f}>
            <strong>{f}</strong>
            <p>{actor.fields[f]}</p>
          </article>
        ) : null,
      )}
      <p className="muted">
        Изменения, накопленные в игре, сохраняются при подтверждении описания.
      </p>
    </div>
  );
}
