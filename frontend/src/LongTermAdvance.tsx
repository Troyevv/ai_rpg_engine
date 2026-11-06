import { formatDateLabel } from "./gameDate";
import { useEffect, useRef, useState } from "react";
import { Hourglass, ArrowRight } from "lucide-react";
import { api } from "./api";
import { Button } from "./components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "./components/ui/dialog";
import { SceneClock } from "./SceneClock";
import type { Save } from "./types";
import "./styles/game-management.css";

export type AdvanceRequest = {
  amount: number;
  unit: "weeks" | "months" | "years";
  max_llm_calls: number;
  reason: string;
};
type Preview = {
  revision: number;
  label: string;
  interruption: { kind: string } | null;
  candidate_count: number;
  decisions: { id: string; context: string; kind: string }[];
};

export function LongTermAdvance({
  save,
  disabled,
  submit,
  open,
  onOpenChange: setOpen,
}: {
  save: Save;
  disabled: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  submit: (request: AdvanceRequest) => Promise<void>;
}) {
  const [request, setRequest] = useState<AdvanceRequest>({
    amount: 1,
    unit: "years",
    max_llm_calls: 4,
    reason: "",
  });
  const [result, setResult] = useState<{ key: string; value: Preview } | null>(
    null,
  );
  const [failure, setFailure] = useState<{
    key: string;
    message: string;
  } | null>(null);
  const [retry, setRetry] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const locked = useRef(false);
  const key = JSON.stringify([save.id, save.revision, request, retry, open]);
  // These bounds mirror the existing API schema, not additional simulation limits.
  const valid =
    Number.isInteger(request.amount) &&
    request.amount >= 1 &&
    request.amount <= 200 &&
    Number.isInteger(request.max_llm_calls) &&
    request.max_llm_calls >= 0 &&
    request.max_llm_calls <= 8;
  useEffect(() => {
    if (!open || !valid) return;
    const controller = new AbortController();
    setResult(null);
    setFailure(null);
    api<Preview>(
      `/saves/${save.id}/long-term/preview`,
      request,
      "POST",
      controller.signal,
    )
      .then((value) => {
        if (!controller.signal.aborted) setResult({ key, value });
      })
      .catch((e) => {
        if (!controller.signal.aborted) setFailure({ key, message: e.message });
      });
    return () => controller.abort();
  }, [key, valid]);
  useEffect(() => {
    setSubmitError("");
  }, [open, request]);
  const preview = result?.key === key ? result.value : null;
  const error = failure?.key === key ? failure.message : null;
  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!locked.current) setOpen(v);
      }}
    >
      <DialogContent
        className="advance-panel"
        onCloseAutoFocus={(e) => {
          e.preventDefault();
          document
            .querySelector<HTMLButtonElement>(".current-game-entry button")
            ?.focus();
        }}
        onEscapeKeyDown={(e) => {
          if (locked.current) e.preventDefault();
        }}
        onPointerDownOutside={(e) => {
          if (locked.current) e.preventDefault();
        }}
      >
        <DialogHeader>
          <span className="management-kicker">
            <Hourglass size={16} /> Следующая глава
          </span>
          <DialogTitle>Длительный переход</DialogTitle>
          <DialogDescription>
            Недели, месяцы или годы. Обязательства могут прервать переход;
            решения героя остаются за тобой.
          </DialogDescription>
        </DialogHeader>
        <form
          className="advance-form"
          onSubmit={async (e) => {
            e.preventDefault();
            if (
              locked.current ||
              disabled ||
              !valid ||
              !preview ||
              preview.revision !== save.revision
            )
              return;
            locked.current = true;
            setSubmitting(true);
            setSubmitError("");
            try {
              await submit(request);
              setOpen(false);
            } catch (e) {
              setSubmitError((e as Error).message);
            } finally {
              locked.current = false;
              setSubmitting(false);
            }
          }}
        >
          <fieldset disabled={submitting}>
            <div className="advance-interval">
              <label className="management-field">
                Интервал
                <input
                  aria-label="Количество единиц перехода"
                  type="number"
                  min={1}
                  max={200}
                  step={1}
                  required
                  value={request.amount || ""}
                  onChange={(e) =>
                    setRequest({ ...request, amount: Number(e.target.value) })
                  }
                />
              </label>
              <label className="management-field">
                Единица
                <select
                  aria-label="Единица перехода"
                  value={request.unit}
                  onChange={(e) =>
                    setRequest({
                      ...request,
                      unit: e.target.value as AdvanceRequest["unit"],
                    })
                  }
                >
                  <option value="weeks">Недели</option>
                  <option value="months">Месяцы</option>
                  <option value="years">Годы</option>
                </select>
              </label>
            </div>
            <label className="management-field">
              Причина <span className="muted">Необязательно</span>
              <textarea
                rows={3}
                value={request.reason}
                maxLength={1000}
                placeholder="Почему проходит это время?"
                onChange={(e) =>
                  setRequest({ ...request, reason: e.target.value })
                }
              />
            </label>
            <details className="advance-details">
              <summary>
                Подробности симуляции · лимит {request.max_llm_calls}
              </summary>
              <label className="management-field">
                Лимит обращений к модели
                <input
                  aria-label="Лимит обращений к модели"
                  type="number"
                  min={0}
                  max={8}
                  step={1}
                  required
                  value={request.max_llm_calls}
                  onChange={(e) =>
                    setRequest({
                      ...request,
                      max_llm_calls: Number(e.target.value),
                    })
                  }
                />
              </label>
              <p className="muted">
                Одна группа исходов требует двух обращений. При нулевом лимите
                выполняются только определённые переходы, остальные причины
                остаются нерешёнными.
              </p>
              {preview && (
                <p>
                  Причин для рассмотрения: {preview.candidate_count}.
                  Возможностей для героя: {preview.decisions.length}.
                </p>
              )}
            </details>
          </fieldset>
          <div
            className="advance-destination"
            aria-live="polite"
            aria-busy={valid && !preview && !error}
          >
            <div>
              <span className="management-kicker">Сейчас</span>
              <SceneClock save={save} />
            </div>
            <ArrowRight size={20} aria-hidden="true" />
            <div>
              <span className="management-kicker">
                {preview?.interruption
                  ? "Остановка перехода"
                  : "Дата окончания"}
              </span>
              <strong>
                {!valid
                  ? "Проверь интервал и лимит"
                  : error
                    ? "Дата недоступна"
                    : preview
                      ? formatDateLabel(preview.label)
                      : "Рассчитываем дату…"}
              </strong>
            </div>
          </div>
          {error && (
            <div role="alert" className="management-state">
              <p>{error}</p>
              <Button
                type="button"
                variant="outline"
                onClick={() => setRetry((v) => v + 1)}
              >
                Повторить расчёт
              </Button>
            </div>
          )}
          {preview?.interruption && (
            <p className="advance-warning" role="status">
              Переход остановится для решения игрока. Обязательства не будут
              пропущены.
            </p>
          )}
          <footer className="advance-confirmation">
            <p>
              Возможности не становятся событиями без подтверждённого исхода.
              Действия героя выбираешь ты.
            </p>
            {submitError && <p role="alert">{submitError}</p>}
            {submitting && <p role="status">Запускаем переход…</p>}
            <div>
              <Button
                type="button"
                variant="outline"
                disabled={submitting}
                onClick={() => setOpen(false)}
              >
                Отмена
              </Button>
              <Button
                type="submit"
                disabled={
                  disabled ||
                  submitting ||
                  !valid ||
                  !preview ||
                  preview.revision !== save.revision
                }
              >
                Подтвердить длительный переход
              </Button>
            </div>
          </footer>
        </form>
      </DialogContent>
    </Dialog>
  );
}
