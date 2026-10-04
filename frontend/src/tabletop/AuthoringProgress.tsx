import { useEffect, useState } from "react";
import { api } from "../api";
type Job = {
  id: string;
  status: string;
  stage: string;
  completed_stages: string[];
  request: Record<string, unknown>;
  issues: { field: string; message: string }[];
};
const labels: Record<string, string> = {
  setting_semantics: "Генерация мира",
  setting_compile: "Создание и проверка игрового контента",
  campaign_semantics: "Сюжетная ситуация, NPC и конфликты",
  campaign_compile: "Сборка и проверка кампании",
  foundation: "Основа мира",
  society: "Общество и роли",
  skills_features: "Навыки и способности",
  bestiary: "Существа",
  equipment: "Предметы",
  world_mechanics: "Механики мира",
  campaign_concept: "Замысел приключения",
  campaign_locations: "Локации",
  campaign_society: "Персонажи и фракции",
  campaign_objects: "Объекты и задания",
  campaign_encounters: "Столкновения",
  campaign_checks_schedules: "Проверки и события",
};
export function useAuthoring(kind: "setting" | "campaign") {
  const key = "tabletop-authoring-" + kind;
  const [id, setId] = useState(() => localStorage.getItem(key) || "");
  const [cycle, setCycle] = useState(0);
  const [running, setRunning] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  useEffect(() => {
    if (!id) return;
    let active = true;
    const poll = () =>
      void api<Job>("/tabletop/authoring/" + id)
        .then((j) => {
          if (active) {
            setJob(j);
            if (!running && j.status !== "RUNNING") clearInterval(timer);
          }
        })
        .catch(() => {});
    poll();
    const timer = setInterval(poll, 1000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [id, cycle, running]);
  async function generate<T>(
    body: Record<string, unknown>,
    resume = false,
  ): Promise<T> {
    setRunning(true);
    const next = resume ? id : crypto.randomUUID();
    localStorage.setItem(key, next);
    setId(next);
    setCycle((v) => v + 1);
    setJob(null);
    try {
      return await api<T>(
        kind === "setting"
          ? "/tabletop/settings/worlds/generate"
          : "/tabletop/generate",
        { ...body, authoring_id: next },
      );
    } finally {
      setRunning(false);
      void api<Job>("/tabletop/authoring/" + next)
        .then(setJob)
        .catch(() => {});
    }
  }
  return { job, generate };
}
export function AuthoringProgress({
  job,
  busy,
  resume,
}: {
  job: Job | null;
  busy: boolean;
  resume: () => void;
}) {
  if (!job || job.status === "COMPLETE") return null;
  return (
    <section className="tt-authoring-progress" role="status">
      <p>
        {job.status === "FAILED" ? "Генерация остановлена" : "Генерация"} ·{" "}
        {labels[job.stage] || job.stage}
      </p>
      <p>Сохранено этапов: {job.completed_stages.length}</p>
      {job.issues.map((issue, i) => (
        <p key={i}>
          {issue.field}: {issue.message}
        </p>
      ))}
      <button disabled={busy} onClick={resume}>
        Продолжить с сохранённого этапа
      </button>
    </section>
  );
}
