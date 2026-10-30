import { useEffect, useRef, useState, type ReactNode } from "react";
import { MoreHorizontal } from "lucide-react";
import { toast } from "sonner";
import { api } from "./api";
import type { Save, Character, WorldRelation } from "./types";
import { Button } from "./components/ui/button";
import { Textarea } from "./components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "./components/ui/dialog";
import { RelationshipCard, RelationshipPair } from "./RelationshipCard";
import { relationshipLabel } from "./lib/relationships";
type Edit = {
  target_id: string;
  context: string;
  dimensions: Record<string, number>;
  delete: boolean;
  revision: number;
};
type Controls = { actions: (r: WorldRelation) => ReactNode; add: ReactNode };
export function RelationshipEditor({
  save,
  card,
  refresh,
  children,
  onCharacter,
}: {
  save: Save;
  card: Character;
  refresh: () => void;
  children?: (controls: Controls) => ReactNode;
  onCharacter?: (id: string) => void;
}) {
  const relations = Object.values(save.state.world?.relationships || {}).filter(
    (r) => r.source_id === card.id,
  );
  const targets = save.state.characters.filter((c) => c.id !== card.id);
  const controlled =
    save.state.controlled_actor_id === undefined
      ? save.state.protagonist_id ||
        save.state.characters.find((c) => c.is_player)?.id
      : save.state.controlled_actor_id;
  const permitted =
    controlled === card.id &&
    save.state.world?.characters[card.id]?.life_status !== "dead";
  const [dimensions, setDimensions] = useState<string[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [edit, setEdit] = useState<Edit | null>(null);
  const baseline = useRef("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState("");
  const [discard, setDiscard] = useState(false);
  const [committed, setCommitted] = useState(false);
  const trigger = useRef<HTMLElement | null>(null);
  const addTrigger = useRef<HTMLButtonElement | null>(null);
  const dirty =
    !!edit && !edit.delete && JSON.stringify(edit) !== baseline.current;
  const identity = `${save.id}:${card.id}:${controlled}`;
  const currentIdentity = useRef(identity);
  currentIdentity.current = identity;
  const close = () => {
    if (lock.current) return;
    if (dirty && !committed) setDiscard(true);
    else setEdit(null);
  };
  useEffect(() => {
    setEdit(null);
    setError("");
    setDiscard(false);
    setCommitted(false);
  }, [identity]);
  useEffect(() => {
    let active = true;
    setLoadError("");
    api<string[]>("/relationships/dimensions")
      .then((value) => {
        if (active) setDimensions(value);
      })
      .catch((e) => {
        if (active) setLoadError((e as Error).message);
      });
    return () => {
      active = false;
    };
  }, [loadAttempt]);
  // Inspector/App already routes Back to the top dialog; reuse that layer.
  useEffect(() => {
    if (!dirty) return;
    const leave = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", leave);
    return () => window.removeEventListener("beforeunload", leave);
  }, [dirty]);
  const name = (id: string) =>
    save.state.characters.find((c) => c.id === id)?.name || id;
  const open = (r?: WorldRelation, remove = false) => {
    const active = document.activeElement as HTMLElement;
    trigger.current =
      active?.closest("details")?.querySelector("summary") || active;
    setError("");
    setDiscard(false);
    setCommitted(false);
    const next: Edit = {
      target_id:
        r?.target_id ||
        targets.find((c) => !relations.some((v) => v.target_id === c.id))?.id ||
        "",
      context: r?.context || "",
      dimensions: Object.fromEntries(
        Object.entries(r?.dimensions || {}).filter(
          ([, v]) => typeof v === "number",
        ),
      ) as Record<string, number>,
      delete: remove,
      revision: save.revision,
    };
    baseline.current = JSON.stringify(next);
    setEdit(next);
  };
  const invalid =
    !!edit &&
    !edit.delete &&
    (!edit.context.trim() ||
      edit.context.length > 12000 ||
      Object.values(edit.dimensions).some(
        (v) => !Number.isFinite(v) || v < -100 || v > 100,
      ));
  const persist = async () => {
    if (!edit || lock.current || !permitted || invalid) return;
    const started = identity;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      if (!committed) {
        await api(
          `/saves/${save.id}/characters/${encodeURIComponent(card.id)}/relationships`,
          edit,
          "PATCH",
        );
        if (currentIdentity.current !== started) return;
        setCommitted(true);
      }
      const refreshed: unknown = await refresh();
      if (refreshed === false)
        throw new Error(
          "Запись сохранена, но обновить экран не удалось. Повтори загрузку данных.",
        );
      if (currentIdentity.current !== started) return;
      setEdit(null);
      toast.success("Отношение сохранено");
    } catch (e) {
      if (currentIdentity.current === started) setError((e as Error).message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  const actions = (r: WorldRelation) =>
    permitted && r.source_id === card.id ? (
      <details className="motivation-menu">
        <summary aria-label={`Действия с отношением к ${name(r.target_id)}`}>
          <MoreHorizontal size={20} />
        </summary>
        <div>
          <Button
            variant="ghost"
            onClick={(e) => {
              e.currentTarget.closest("details")?.removeAttribute("open");
              open(r);
            }}
          >
            Редактировать
          </Button>
          <Button
            variant="ghost"
            onClick={(e) => {
              e.currentTarget.closest("details")?.removeAttribute("open");
              open(r, true);
            }}
          >
            Удалить
          </Button>
        </div>
      </details>
    ) : null;
  const add = permitted ? (
    <Button
      ref={addTrigger}
      variant="ghost"
      disabled={
        !targets.some((c) => !relations.some((r) => r.target_id === c.id))
      }
      onClick={() => open()}
    >
      + Добавить отношение
    </Button>
  ) : null;
  return (
    <div className="motivation-editor relationship-editor">
      {children ? (
        children({ actions, add })
      ) : (
        <>
          {relations.map((r) => (
            <RelationshipCard
              key={r.target_id}
              state={save.state}
              relation={r}
              saveId={save.id}
              onCharacter={onCharacter}
              actions={actions(r)}
            />
          ))}
          {!relations.length && (
            <p className="muted small">
              Отношения этого персонажа ещё не записаны.
            </p>
          )}
          {add}
        </>
      )}
      <Dialog
        open={!!edit && permitted}
        onOpenChange={(value) => {
          if (!value) close();
        }}
      >
        <DialogContent
          className="relationship-dialog"
          aria-busy={busy}
          onCloseAutoFocus={(e) => {
            e.preventDefault();
            if (trigger.current?.isConnected) trigger.current.focus();
            else addTrigger.current?.focus();
          }}
          onEscapeKeyDown={(e) => {
            e.preventDefault();
            close();
          }}
        >
          <DialogHeader>
            <DialogTitle>
              {edit?.delete ? "Удалить отношение?" : "Отношение персонажа"}
            </DialogTitle>
            <DialogDescription>
              Меняется только направление от управляемого персонажа. Обратная
              связь остаётся прежней.
            </DialogDescription>
          </DialogHeader>
          {edit && (
            <>
              <div className="relationship-form-scroll">
                <RelationshipPair
                  state={save.state}
                  source={card.id}
                  target={edit.target_id}
                  saveId={save.id}
                />
                {edit.delete ? (
                  <p>
                    Эта направленная связь будет удалена из текущего
                    прохождения.
                  </p>
                ) : (
                  <fieldset
                    disabled={busy || committed}
                    className="relationship-fields"
                  >
                    <label>
                      К кому
                      <select
                        aria-label="Персонаж-адресат"
                        value={edit.target_id}
                        disabled={relations.some(
                          (r) => r.target_id === edit.target_id,
                        )}
                        onChange={(e) =>
                          setEdit({ ...edit, target_id: e.target.value })
                        }
                      >
                        {targets
                          .filter(
                            (c) =>
                              c.id === edit.target_id ||
                              !relations.some((r) => r.target_id === c.id),
                          )
                          .map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name}
                            </option>
                          ))}
                      </select>
                    </label>
                    <label>
                      Описание отношения
                      <Textarea
                        aria-label="Контекст отношения"
                        rows={5}
                        value={edit.context}
                        onChange={(e) =>
                          setEdit({ ...edit, context: e.target.value })
                        }
                        placeholder="Как персонаж относится к нему сейчас и почему"
                      />
                    </label>
                    <p className="muted small">
                      Показатели от −100 до 100. Пустое поле — «Не задано», 0 —
                      заданное нулевое значение.
                    </p>
                    {loadError ? (
                      <div role="alert">
                        {loadError}
                        <Button onClick={() => setLoadAttempt((n) => n + 1)}>
                          Повторить загрузку
                        </Button>
                      </div>
                    ) : dimensions === null ? (
                      <p role="status">Загрузка параметров…</p>
                    ) : (
                      <div className="relationship-dimensions">
                        {Array.from(
                          new Set([
                            ...dimensions,
                            ...Object.keys(edit.dimensions),
                          ]),
                        ).map((key) => (
                          <label key={key} className="relationship-dimension">
                            <span>{relationshipLabel(key)}</span>
                            <input
                              aria-label={relationshipLabel(key)}
                              type="number"
                              min={-100}
                              max={100}
                              step="any"
                              placeholder="Не задано"
                              value={edit.dimensions[key] ?? ""}
                              aria-invalid={
                                edit.dimensions[key] != null &&
                                (edit.dimensions[key] < -100 ||
                                  edit.dimensions[key] > 100)
                              }
                              onChange={(e) => {
                                const next = { ...edit.dimensions };
                                if (e.target.value === "") delete next[key];
                                else next[key] = Number(e.target.value);
                                setEdit({ ...edit, dimensions: next });
                              }}
                            />
                            <small>
                              {edit.dimensions[key] === undefined
                                ? "Не задано"
                                : "−100…100"}
                            </small>
                          </label>
                        ))}
                      </div>
                    )}
                  </fieldset>
                )}
                {invalid && (
                  <p role="alert">
                    Нужно описание до 12 000 символов и значения от −100 до 100.
                  </p>
                )}
                {error && (
                  <div role="alert">
                    <p>{error}</p>
                    {!committed && (
                      <Button
                        disabled={busy}
                        variant="ghost"
                        onClick={async () => {
                          setBusy(true);
                          try {
                            const fresh = await api<Save>(`/saves/${save.id}`);
                            if (currentIdentity.current !== identity) return;
                            const actor = fresh.state.controlled_actor_id;
                            if (actor !== card.id) {
                              setEdit(null);
                              await refresh();
                              return;
                            }
                            setEdit({ ...edit, revision: fresh.revision });
                            setError(
                              "Ревизия обновлена. Проверь черновик перед повторным сохранением.",
                            );
                            await refresh();
                          } catch (e) {
                            setError((e as Error).message);
                          } finally {
                            setBusy(false);
                          }
                        }}
                      >
                        Обновить ревизию, сохранив черновик
                      </Button>
                    )}
                  </div>
                )}
                {discard && (
                  <div className="relationship-discard" role="alert">
                    <strong>Отбросить несохранённые изменения?</strong>
                    <div className="actions">
                      <Button variant="ghost" onClick={() => setDiscard(false)}>
                        Продолжить редактирование
                      </Button>
                      <Button variant="danger" onClick={() => setEdit(null)}>
                        Отбросить изменения
                      </Button>
                    </div>
                  </div>
                )}
              </div>
              <footer className="relationship-form-actions">
                <Button variant="ghost" disabled={busy} onClick={close}>
                  Отмена
                </Button>
                <Button
                  variant={edit.delete ? "danger" : "primary"}
                  disabled={
                    busy ||
                    !edit.target_id ||
                    invalid ||
                    (!edit.delete && (!dimensions || !!loadError))
                  }
                  onClick={() => void persist()}
                >
                  {busy
                    ? "Сохранение…"
                    : committed
                      ? "Обновить данные"
                      : edit.delete
                        ? "Удалить"
                        : "Сохранить"}
                </Button>
              </footer>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
