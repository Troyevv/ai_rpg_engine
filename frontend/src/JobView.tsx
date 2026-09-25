import { LoaderCircle, Square, WifiOff } from "lucide-react";
import { Button } from "./components/ui/button";
import { Markdown } from "./Markdown";
import { active, type Job } from "./types";
const labels: Record<string, string> = {
  generating: "Ведущий продолжает историю…",
  extracting: "Обновляет состояние мира",
  validating: "Завершает ход",
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
  if (job.status === "saved") return null;
  return (
    <section className={`job ${job.narrative ? "job-streaming" : ""}`}>
      <details open>
        <summary>
          <span className="job-label" role="status" aria-live="polite">
            {active(job) ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <span className="status-dot" />
            )}
            {job.kind === "background" && job.status === "extracting" ? "Обновляет последствия закулисной сцены" : labels[job.status] || job.status}
          </span>
          <span className="muted">Свернуть / раскрыть</span>
        </summary>
        {active(job)&&<ol className="generation-stages" aria-label="Продолжение истории">{[['generating','Создаёт сцену'],['extracting','Обновляет мир'],['validating','Завершает ход']].map(([stage,label])=><li key={stage} aria-current={job.status===stage?'step':undefined}><span aria-hidden="true">{job.status===stage?'●':'○'}</span> {label}</li>)}</ol>}
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
