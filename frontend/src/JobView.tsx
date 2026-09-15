import { LoaderCircle, Square, WifiOff } from "lucide-react";
import { Button } from "./components/ui/button";
import { Markdown } from "./Markdown";
import { active, type Job } from "./types";
const labels: Record<string, string> = {
  generating: "Пишет продолжение",
  extracting: "Обновляет мир и готовит 6 действий",
  validating: "Проверяет и сохраняет",
  saved: "Готово",
  error: "Не удалось завершить",
  stopped: "Генерация остановлена",
};
export function JobView({
  job,
  reconnecting,
  stop,
  worldId,
  saveId,
  onCharacter,
  links = true,
}: {
  job: Job | null;
  reconnecting?: boolean;
  stop: () => void;
  worldId?: number;
  saveId?: number;
  onCharacter?: (id: string) => void;
  links?: boolean;
}) {
  if (!job) return null;
  if (job.status === "saved") return job.warnings?.length ? <details className="job warning">
    <summary>Ход сохранён. Не подтверждено изменений: {job.warnings.length}</summary>
    <p>Эти пункты не добавлены в состояние мира. Текст хода сохранён полностью.</p>
    {job.warnings.map((w,i)=><div key={i}><strong>{w.section}</strong>: {w.reason}<pre>{JSON.stringify(w.rejected,null,2)}</pre></div>)}
  </details> : null;
  return (
    <section className="job" aria-live="polite">
      <details open>
        <summary>
          <span className="job-label">
            {active(job) ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <span className="status-dot" />
            )}
            {labels[job.status] || job.status}
          </span>
          <span className="muted">Свернуть / раскрыть</span>
        </summary>
        {job.user_text && <div className="player-action"><span className="eyebrow">Твоё действие</span><Markdown text={job.user_text}/></div>}
        {job.narrative && (
          <Markdown
            text={job.narrative}
            worldId={worldId}
            saveId={saveId}
            onCharacter={onCharacter}
            links={links}
          />
        )}
      </details>
      {reconnecting && (
        <p className="muted flex gap-2">
          <WifiOff size={16} />
          Восстанавливаем соединение…
        </p>
      )}
      {job.error && (
        <p role="alert" className="error">
          {job.error}
        </p>
      )}
      {active(job) && (
        <Button variant="outline" size="sm" onClick={stop}>
          <Square size={13} />
          Остановить генерацию
        </Button>
      )}
    </section>
  );
}
