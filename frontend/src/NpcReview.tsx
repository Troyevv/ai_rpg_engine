import {
  NpcAttributes,
  NpcConnections,
  describeAttribute,
  type AttributeValue,
  type AttributeSchema,
} from "./NpcAttributes";
import { useEffect, useRef, useState } from "react";
import {
  Check,
  CheckCheck,
  ChevronRight,
  Clock3,
  LoaderCircle,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { api } from "./api";
import type { Save, Preferences } from "./types";
import { Button } from "./components/ui/button";
import { Textarea } from "./components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "./components/ui/dialog";
import "./npc-review.css";

export type NpcReviewRecord = {
  id: string;
  age: number | null;
  extracted_fields: Record<string, string>;
  card: { id: string; name: string; fields: Record<string, string> };
  status: "pending_review" | "deferred" | "confirmed";
  revision: number;
  created_turn: number;
  creation_id: string;
  proposals: Record<string, string>;
  character: Record<string, AttributeValue>;
  baseline: Record<string, AttributeValue>;
  current: Record<string, AttributeValue>;
};
export type NpcReviews = {
  fields: string[];
  attributes: AttributeSchema[];
  records: NpcReviewRecord[];
};
const groups = [
  {
    name: "Образ",
    hint: "Первое впечатление",
    fields: ["Возраст", "Роль", "Статус", "Внешность"],
  },
  {
    name: "Личность",
    hint: "Голос и характер",
    fields: ["Характер", "Стиль общения", "Привычки"],
  },
  {
    name: "Глубина",
    hint: "Опыт и противоречия",
    fields: ["Сильные стороны", "Слабости", "Страхи и уязвимости", "Биография"],
  },
  { name: "Состояние", hint: "Факты и способности", fields: [] },
  { name: "Связи", hint: "Уже в мире", fields: [] },
];

type Conflict = {
  label: string;
  mine: unknown;
  server: unknown;
  canonical: boolean;
};
type Draft = {
  conflicts?: Record<string, Conflict>;
  fields: Record<string, string>;
  proposals: Record<string, string>;
  character: Record<string, AttributeValue>;
};
export function NpcReview({
  save,
  locked,
  prefs,
  apiKey,
  onCommit,
}: {
  save: Save;
  locked: boolean;
  prefs: Preferences;
  apiKey: string;
  onCommit: (save: Save) => void;
}) {
  const [override, setOverride] = useState<Save | null>(null);
  const current =
    override && override.id === save.id && override.revision > save.revision
      ? override
      : save;
  const reviews = current.state.npc_reviews;
  const records =
    reviews?.records.filter((r) => r.status !== "confirmed") || [];
  const fields = reviews?.fields || [];
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState("");
  const [section, setSection] = useState(0);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [canCompare, setCanCompare] = useState(false);
  const [notice, setNotice] = useState("");
  const gate = useRef(false);
  const seen = useRef(new Set<string>());
  const record = records.find((r) => r.id === selected) || records[0];
  const storageKey = (r: NpcReviewRecord) =>
    `npc-review:${save.id}:${r.id}:${r.creation_id}:${r.revision}`;
  const draft = record
    ? drafts[storageKey(record)] || {
        fields: record.card.fields,
        proposals: record.proposals,
        character: record.character,
      }
    : null;
  const completed = draft
    ? fields.filter((f) => draft.fields[f]?.trim()).length
    : 0;
  useEffect(() => {
    if (locked) return;
    const fresh = records.find(
      (r) =>
        r.status === "pending_review" &&
        !seen.current.has(`${save.id}:${r.id}:${r.creation_id}`),
    );
    records.forEach((r) =>
      seen.current.add(`${save.id}:${r.id}:${r.creation_id}`),
    );
    if (fresh) {
      setSelected(fresh.id);
      setOpen(true);
    }
  }, [save.id, reviews, locked]);
  useEffect(() => {
    if (!record) return;
    const key = storageKey(record);
    try {
      const raw = localStorage.getItem(key);
      if (raw) {
        const restored = JSON.parse(raw) as Draft;
        if (restored.fields && restored.proposals)
          setDrafts((d) => ({ ...d, [key]: restored }));
      }
    } catch {
      /* Server draft remains available. */
    }
  }, [save.id, record?.id, record?.revision]);
  const change = (next: Draft) => {
    if (!record) return;
    const key = storageKey(record);
    setDrafts((d) => ({ ...d, [key]: next }));
    setNotice("Есть несохранённые правки");
    try {
      localStorage.setItem(key, JSON.stringify(next));
    } catch {
      setNotice("Сохрани черновик: локальное восстановление недоступно");
    }
  };
  const commit = async (action: "save" | "defer" | "confirm") => {
    if (!record || !draft) return;
    if (Object.keys(draft.conflicts || {}).length)
      throw new Error("Сначала сравни конфликтующие правки ниже.");
    const after = await api<Save>(
      `/saves/${save.id}/npc-reviews/${encodeURIComponent(record.id)}`,
      {
        revision: current.revision,
        review_revision: record.revision,
        operation_id: crypto.randomUUID(),
        fields: draft.fields,
        proposals: draft.proposals,
        character: draft.character,
        action,
      },
    ).catch((error) => {
      setCanCompare(true);
      throw error;
    });
    const updated = after.state.npc_reviews?.records.find(
      (r) => r.id === record.id,
    );
    try {
      localStorage.removeItem(storageKey(record));
    } catch {
      /* Server commit succeeded. */
    }
    if (updated && action !== "confirm") {
      const key = storageKey(updated);
      setDrafts((d) => ({ ...d, [key]: draft }));
      try {
        localStorage.setItem(key, JSON.stringify(draft));
      } catch {
        /* Server owns the saved draft. */
      }
    }
    setOverride(after);
    onCommit(after);
    setNotice(
      action === "confirm" ? "Карточка подтверждена" : "Черновик сохранён",
    );
    return after;
  };
  const act = async (label: string, fn: () => Promise<void>) => {
    if (gate.current || locked) return;
    gate.current = true;
    setBusy(label);
    setError("");
    setCanCompare(false);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      gate.current = false;
      setBusy("");
    }
  };
  const compareLatest = () =>
    void act("compare", async () => {
      if (!record || !draft) return;
      const latest = await api<Save>(`/saves/${save.id}`);
      const remote = latest.state.npc_reviews?.records.find(
        (r) => r.id === record.id,
      );
      if (!remote || remote.creation_id !== record.creation_id)
        throw new Error(
          "Исходный ход заменён. Эта локальная копия не будет применена к другой версии NPC.",
        );
      const conflicts: Record<string, Conflict> = {};
      if (remote.revision !== record.revision) {
        for (const field of fields)
          if (draft.fields[field] !== remote.card.fields[field])
            conflicts[field] = {
              label: field,
              mine: draft.fields[field],
              server: remote.card.fields[field],
              canonical: false,
            };
        for (const attribute of reviews?.attributes || []) {
          const mine =
            attribute.key in draft.character
              ? draft.character[attribute.key]
              : record.current[attribute.key];
          const server =
            attribute.key in remote.character
              ? remote.character[attribute.key]
              : remote.current[attribute.key];
          if (JSON.stringify(mine) !== JSON.stringify(server))
            conflicts[attribute.key] = {
              label: attribute.label,
              mine,
              server,
              canonical: true,
            };
        }
      }
      const next = { ...draft, conflicts };
      const key = storageKey(remote);
      try {
        localStorage.setItem(key, JSON.stringify(next));
      } catch {
        /* Keep the in-memory draft available for explicit save. */
      }
      setDrafts((d) => ({ ...d, [key]: next }));
      setOverride(latest);
      onCommit(latest);
      setNotice(
        Object.keys(conflicts).length
          ? "Сравни параллельные правки. Ни одна не применится автоматически."
          : "Контекст обновлён. Твои правки сохранены в редакторе.",
      );
    });
  const resolveConflict = (key: string, server: boolean) => {
    if (!draft) return;
    const conflict = draft.conflicts?.[key];
    if (!conflict) return;
    const conflicts = { ...draft.conflicts };
    delete conflicts[key];
    const value = server ? conflict.server : conflict.mine;
    change({
      ...draft,
      conflicts,
      ...(conflict.canonical
        ? { character: { ...draft.character, [key]: value as AttributeValue } }
        : { fields: { ...draft.fields, [key]: String(value ?? "") } }),
    });
  };
  const defer = () =>
    void act("save", async () => {
      await commit("defer");
      setOpen(false);
    });
  const generate = (field: string) =>
    void act(field, async () => {
      const after = await commit("save");
      if (!after || !record || !draft) return;
      const updated = after.state.npc_reviews!.records.find(
        (r) => r.id === record.id,
      )!;
      const proposal = await api<{ value: string }>(
        `/saves/${save.id}/npc-reviews/${encodeURIComponent(record.id)}/generate`,
        {
          field,
          revision: after.revision,
          review_revision: updated.revision,
          config: prefs.game,
          api_key: apiKey,
        },
      );
      const next = {
        ...draft,
        proposals: { ...draft.proposals, [field]: proposal.value },
      };
      const key = storageKey(updated);
      setDrafts((d) => ({ ...d, [key]: next }));
      try {
        localStorage.setItem(key, JSON.stringify(next));
      } catch {
        /* Keep the in-memory draft available for explicit save. */
      }
      setNotice("Предложение готово — сравни с текущим текстом");
    });
  if (!records.length) return null;
  return (
    <>
      <button
        className="npc-review-entry"
        disabled={locked}
        onClick={() => {
          setOpen(true);
          setError("");
        }}
      >
        <span className="npc-review-entry-icon">
          <Users size={19} />
        </span>
        <span>
          <strong>Новые лица в истории</strong>
          <small>
            {records.length}{" "}
            {records.length === 1 ? "карточка ждёт" : "карточек ждут"} проверки
          </small>
        </span>
        <ChevronRight size={18} />
      </button>
      <Dialog
        open={open && !!record}
        onOpenChange={(value) => {
          if (!value) defer();
          else setOpen(true);
        }}
      >
        <DialogContent
          className="npc-review-dialog"
          onInteractOutside={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => {
            e.preventDefault();
            defer();
          }}
        >
          <header className="npc-review-header">
            <div className="npc-review-monogram" aria-hidden="true">
              {record?.card.name.slice(0, 1)}
            </div>
            <div>
              <p className="eyebrow">Новое лицо · проверка карточки</p>
              <DialogTitle>{record?.card.name}</DialogTitle>
              <DialogDescription>
                Персонаж уже участвует в истории. Проверь описание сейчас или
                вернись к нему позже.
              </DialogDescription>
            </div>
          </header>
          <div className="npc-review-progress">
            <span>
              {completed} из {fields.length} полей заполнено
            </span>
            <progress
              value={completed}
              max={fields.length}
              aria-label="Заполнение карточки"
            />
            <span>
              {Math.round((completed / Math.max(1, fields.length)) * 100)}%
            </span>
          </div>
          <div className="npc-review-layout">
            <aside className="npc-review-sidebar">
              <p className="eyebrow">Ожидают проверки</p>
              <nav aria-label="Ожидающие карточки">
                {records.map((r) => (
                  <button
                    key={r.id}
                    aria-current={r.id === record?.id ? "true" : undefined}
                    disabled={!!busy || locked}
                    onClick={() =>
                      void act("save", async () => {
                        if (r.id !== record?.id) {
                          await commit("save");
                          setSelected(r.id);
                          setSection(0);
                          setNotice("");
                        }
                      })
                    }
                  >
                    <span className="npc-review-avatar">
                      {r.card.name.slice(0, 1)}
                    </span>
                    <span>
                      {r.card.name}
                      <small>
                        {r.status === "deferred"
                          ? "Отложена"
                          : "Новое предложение"}
                      </small>
                    </span>
                  </button>
                ))}
              </nav>
            </aside>
            <main className="npc-review-main">
              <div
                className="npc-review-tabs"
                role="tablist"
                aria-label="Разделы карточки"
              >
                {groups.map((g, i) => (
                  <button
                    id={`npc-tab-${i}`}
                    role="tab"
                    tabIndex={section === i ? 0 : -1}
                    onKeyDown={(e) => {
                      const next =
                        e.key === "ArrowRight"
                          ? (i + 1) % groups.length
                          : e.key === "ArrowLeft"
                            ? (i + groups.length - 1) % groups.length
                            : e.key === "Home"
                              ? 0
                              : e.key === "End"
                                ? groups.length - 1
                                : null;
                      if (next !== null) {
                        e.preventDefault();
                        setSection(next);
                        document.getElementById(`npc-tab-${next}`)?.focus();
                      }
                    }}
                    aria-selected={section === i}
                    aria-controls="npc-field-panel"
                    key={g.name}
                    onClick={() => setSection(i)}
                  >
                    {g.name}
                    <small>{g.hint}</small>
                  </button>
                ))}
              </div>
              <div
                className="npc-review-fields"
                role="tabpanel"
                id="npc-field-panel"
                aria-labelledby={`npc-tab-${section}`}
                key={`${record?.id}:${section}`}
              >
                {Object.entries(draft?.conflicts || {}).map(([key, c]) => (
                  <section className="npc-review-conflict" key={key}>
                    <h3>{c.label}: параллельные правки</h3>
                    <div>
                      <article>
                        <strong>Моя версия</strong>
                        <p>{describeAttribute(c.mine)}</p>
                        <Button
                          variant="outline"
                          disabled={!!busy || locked}
                          onClick={() => resolveConflict(key, false)}
                        >
                          Оставить мою
                        </Button>
                      </article>
                      <article>
                        <strong>Версия сервера</strong>
                        <p>{describeAttribute(c.server)}</p>
                        <Button
                          variant="outline"
                          disabled={!!busy || locked}
                          onClick={() => resolveConflict(key, true)}
                        >
                          Принять серверную
                        </Button>
                      </article>
                    </div>
                  </section>
                ))}
                {section === 3 && record && draft && (
                  <NpcAttributes
                    record={record}
                    attributes={reviews?.attributes || []}
                    patch={draft.character || {}}
                    onChange={(character) => change({ ...draft, character })}
                    disabled={!!busy || locked}
                  />
                )}
                {section === 4 && record && (
                  <NpcConnections save={current} id={record.id} />
                )}
                {fields
                  .filter((f) => groups[section].fields.includes(f))
                  .map((field) => {
                    const value = draft?.fields[field] || "";
                    const proposal = draft?.proposals[field];
                    return (
                      <section className="npc-review-field" key={field}>
                        <div className="npc-review-field-heading">
                          <label htmlFor={`npc-${field}`}>{field}</label>
                          <span>
                            {value.trim() ? (
                              <>
                                {value === record?.extracted_fields[field]
                                  ? "Извлечено из хода"
                                  : "Отредактировано"}{" "}
                                <Check size={13} aria-label="Заполнено" />
                              </>
                            ) : (
                              "Не заполнено"
                            )}
                          </span>
                        </div>
                        <Textarea
                          id={`npc-${field}`}
                          value={value}
                          disabled={!!busy || locked}
                          placeholder="Добавь описание или предложи DeepSeek заполнить поле"
                          onChange={(e) =>
                            draft &&
                            change({
                              ...draft,
                              fields: {
                                ...draft.fields,
                                [field]: e.target.value,
                              },
                            })
                          }
                          rows={field === "Биография" ? 8 : 4}
                        />
                        <div className="npc-review-field-actions">
                          <span>
                            {value.length
                              ? `${value.length} знаков`
                              : "Пустое поле сохранится в черновике"}
                          </span>
                          <Button
                            variant="ghost"
                            disabled={!!busy || locked}
                            onClick={() => generate(field)}
                          >
                            {busy === field ? (
                              <LoaderCircle
                                className="npc-review-spin"
                                size={15}
                              />
                            ) : (
                              <Sparkles size={15} />
                            )}{" "}
                            {busy === field
                              ? "Генерирует…"
                              : proposal
                                ? "Предложить ещё"
                                : "Предложить текст"}
                          </Button>
                        </div>
                        {proposal && (
                          <div className="npc-review-proposal">
                            <p className="eyebrow">
                              <Sparkles size={14} /> Предложение для сравнения
                            </p>
                            <p className="npc-review-proposal-text">
                              {proposal}
                            </p>
                            <div>
                              <Button
                                disabled={!!busy || locked}
                                onClick={() => {
                                  if (!draft) return;
                                  const proposals = { ...draft.proposals };
                                  delete proposals[field];
                                  change({
                                    ...draft,
                                    fields: {
                                      ...draft.fields,
                                      [field]: proposal,
                                    },
                                    proposals,
                                  });
                                }}
                              >
                                <Check size={15} />
                                Принять текст
                              </Button>
                              <Button
                                variant="ghost"
                                disabled={!!busy || locked}
                                onClick={() => {
                                  if (!draft) return;
                                  const proposals = { ...draft.proposals };
                                  delete proposals[field];
                                  change({ ...draft, proposals });
                                }}
                              >
                                <X size={15} />
                                Оставить мой
                              </Button>
                            </div>
                          </div>
                        )}
                      </section>
                    );
                  })}
              </div>
            </main>
          </div>
          <footer className="npc-review-footer">
            <div aria-live="polite">
              {error ? (
                <p role="alert" className="npc-review-error">
                  {error}
                </p>
              ) : (
                <p>
                  {notice ||
                    "Описание станет каноном только после подтверждения."}
                </p>
              )}
            </div>
            {error && canCompare && (
              <Button
                variant="outline"
                disabled={!!busy || locked}
                onClick={compareLatest}
              >
                Сверить с сервером
              </Button>
            )}
            <div className="npc-review-footer-actions">
              <Button
                variant="ghost"
                disabled={!!busy || locked}
                onClick={defer}
              >
                <Clock3 size={16} />
                Отложить
              </Button>
              <Button
                variant="outline"
                disabled={!!busy || locked}
                onClick={() =>
                  void act("save", async () => {
                    await commit("save");
                  })
                }
              >
                Сохранить черновик
              </Button>
              <Button
                disabled={!!busy || locked || completed !== fields.length}
                onClick={() =>
                  void act("confirm", async () => {
                    await commit("confirm");
                    if (records.length === 1) setOpen(false);
                  })
                }
              >
                <CheckCheck size={16} />
                Подтвердить
              </Button>
            </div>
          </footer>
        </DialogContent>
      </Dialog>
    </>
  );
}
