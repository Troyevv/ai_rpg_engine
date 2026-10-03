import { AuthoringProgress, useAuthoring } from "./AuthoringProgress";
import { SettingEditor } from "./SettingEditor";
import {
  ChoiceControl,
  ChoiceOption,
  Stepper,
  SegmentedControl,
} from "@/components/choice/ChoiceControl";
import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { CharacterCreator } from "./CharacterCreator";
import type { Preferences } from "../types";
import {
  type Build,
  type Catalog,
  type Draft,
  type Game,
  type ValidationDiagnostics,
} from "./types";

export function Wizard({
  prefs,
  apiKey,
  done,
  cancel,
}: {
  prefs: Preferences;
  apiKey: string;
  done: (game: Game) => void;
  cancel: () => void;
}) {
  const authoring = useAuthoring("campaign");
  const [settingId, setSettingId] = useState<string | null>(null);
  const [worldEditor, setWorldEditor] = useState(true);
  const [progressionMode, setProgressionMode] = useState("xp");
  const [creatorValid, setCreatorValid] = useState(false);
  const [catalog, setCatalog] = useState<Catalog | null>(null),
    [build, setBuild] = useState<Build | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null),
    [step, setStep] = useState(0),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [diagnostics, setDiagnostics] = useState<ValidationDiagnostics | null>(
    null,
  );
  const [json, setJson] = useState(""),
    [advanced, setAdvanced] = useState(false),
    [author, setAuthor] = useState(false),
    [drafts, setDrafts] = useState<
      { id: string; name: string; generation_status: string }[]
    >([]);
  const [options, setOptions] = useState({
    idea: "",
    title: "",
    genre: "Фэнтези",
    setting: "",
    tone: "Мрачное приключение",
    technology: "Средневековье",
    magic: "Низкая",
    scale: "Город и окрестности",
    adventure_type: "Расследование",
    difficulty: "MEDIUM",
    party_size: 1,
    starting_situation: "",
    wishes: "",
  });
  useEffect(() => {
    api<Catalog>("/tabletop/catalog")
      .then((c) => {
        setCatalog(c);
        setBuild(c.default_build);
      })
      .catch((e) => setError(e.message));
    api<{ id: string; name: string; generation_status: string }[]>(
      "/tabletop/drafts",
    )
      .then(setDrafts)
      .catch((e) => setError(e.message));
  }, []);
  async function run(fn: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError("");
    setDiagnostics(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
      if (e instanceof ApiError)
        setDiagnostics(e.details as ValidationDiagnostics);
    } finally {
      setBusy(false);
    }
  }
  const choose = async (d: Draft) => {
    const c = await api<Catalog>(
      `/tabletop/catalog?draft_id=${encodeURIComponent(d.id)}&ruleset_id=${encodeURIComponent(String(d.definition.ruleset_id))}${d.definition.setting_definition ? `&setting_id=${(d.definition.setting_definition as { id: string }).id}&setting_revision=${(d.definition.setting_definition as { revision: number }).revision}` : ""}`,
    );
    if (
      catalog?.id !== c.id ||
      catalog?.setting_id !== c.setting_id ||
      catalog?.setting_revision !== c.setting_revision
    )
      setBuild(c.default_build);
    setCatalog(c);
    setDraft(d);
    setDiagnostics(null);
    setAuthor(false);
    setJson(JSON.stringify(d.definition, null, 2));
    setStep(1);
  };
  const change = (key: string, value: unknown) =>
    setOptions((prev) => ({ ...prev, [key]: value }));
  if (!catalog || !build)
    return <p className="tt-panel">Загрузка каталога правил… {error}</p>;
  const issues =
    diagnostics?.validation_issues ?? draft?.validation_issues ?? [];
  const issueStage = diagnostics?.stage ?? draft?.validation_stage;
  const cls = catalog.classes[build.character_class];
  return (
    <main className="tt-wizard tt-panel">
      {step === 0 && (
        <>
          <button onClick={() => setWorldEditor(!worldEditor)}>
            {worldEditor ? "Скрыть редактор мира" : "Создать или выбрать мир"}
          </button>
          {worldEditor && (
            <SettingEditor
              prefs={prefs}
              apiKey={apiKey}
              onUse={(world) => {
                setSettingId(world.id);
                setWorldEditor(false);
                setOptions((o) => ({
                  ...o,
                  genre: world.definition.genre as string,
                  setting: world.definition.description,
                  technology: world.definition.technology_description as string,
                  magic: world.definition.supernatural_description as string,
                }));
              }}
            />
          )}
          {settingId && <p>Приключение использует выбранный мир.</p>}
        </>
      )}
      <AuthoringProgress
        job={authoring.job}
        busy={busy}
        resume={() =>
          void run(async () =>
            choose(
              await authoring.generate<Draft>(
                {
                  ...authoring.job!.request,
                  config: prefs.summary,
                  api_key: apiKey,
                },
                true,
              ),
            ),
          )
        }
      />
      {!settingId && step === 0 && (
        <p>
          Сначала создай или выбери мир выше. Сохранённые черновики доступны без
          повторной генерации.
        </p>
      )}
      <span className="tt-eyebrow">Новая кампания · {step + 1} / 4</span>
      <h1>
        {
          [
            "Идея приключения",
            "Мир и стартовая сцена",
            "Создание персонажа",
            "Начало кампании",
          ][step]
        }
      </h1>
      {error && (
        <p role="alert" className="tt-error" style={{ whiteSpace: "pre-line" }}>
          {error}
        </p>
      )}
      {draft?.generation_status === "INVALID" && step > 0 && (
        <p role="alert" className="tt-error">
          Черновик содержит ошибки. Исправь его в режиме автора или вернись к
          генерации. Начать игру пока нельзя.
        </p>
      )}
      {!!issues.length && (
        <details className="tt-diagnostics">
          <summary>Диагностика проверки ({issues.length})</summary>
          <p>Этап: {issueStage}</p>
          <ul>
            {issues.map((issue, i) => (
              <li key={i}>
                <p>{issue.message}</p>
                <code>
                  {issue.code} · {issue.entity_type}:{issue.entity_id} ·{" "}
                  {issue.field} → {issue.reference}
                </code>
              </li>
            ))}
          </ul>
        </details>
      )}
      {diagnostics?.draft_id && diagnostics.draft_id !== draft?.id && (
        <button
          disabled={busy}
          onClick={() =>
            void run(async () =>
              choose(
                await api<Draft>(`/tabletop/drafts/${diagnostics.draft_id}`),
              ),
            )
          }
        >
          Открыть невалидный черновик
        </button>
      )}
      {step === 0 ? (
        <>
          <label>
            Идея приключения
            <textarea
              value={options.idea}
              onChange={(e) => change("idea", e.target.value)}
              maxLength={6000}
              placeholder="Кто герой, что произошло и с какой ситуации начинается приключение?"
            />
          </label>
          <label className="tt-toggle">
            <input
              type="checkbox"
              checked={advanced}
              onChange={(e) => setAdvanced(e.target.checked)}
            />{" "}
            Подробная настройка
          </label>
          {advanced && (
            <div className="tt-form-grid">
              {Object.entries({
                title: "Название",
                genre: "Жанр",
                setting: "Сеттинг",
                tone: "Тон",
                technology: "Технологии",
                magic: "Магия",
                scale: "Масштаб",
                adventure_type: "Тип приключения",
                starting_situation: "Стартовая ситуация",
                wishes: "Пожелания",
              })
                .filter(
                  ([key]) =>
                    !["genre", "setting", "technology", "magic"].includes(key),
                )
                .map(([key, label]) => (
                  <label key={key}>
                    {label}
                    <input
                      value={String(options[key as keyof typeof options])}
                      maxLength={key === "wishes" ? 3000 : 120}
                      onChange={(e) => change(key, e.target.value)}
                    />
                  </label>
                ))}
              <label>
                Размер партии
                <Stepper
                  label="Размер партии"
                  min={1}
                  max={4}
                  value={options.party_size}
                  onChange={(value) => change("party_size", value)}
                />
              </label>
              <label>
                Сложность
                <SegmentedControl
                  value={options.difficulty}
                  onChange={(e) => change("difficulty", e.target.value)}
                >
                  <ChoiceOption value="EASY">Легко</ChoiceOption>
                  <ChoiceOption value="MEDIUM">Средне</ChoiceOption>
                  <ChoiceOption value="HARD">Сложно</ChoiceOption>
                </SegmentedControl>
              </label>
            </div>
          )}
          <p className="tt-note">
            Генерация создаёт связанный мир, NPC, задания, предметы и
            столкновения. Используется модель из общих настроек игры:{" "}
            {prefs.game.model || "модель не выбрана"}.
          </p>
          <button
            className="tt-primary"
            disabled={
              busy ||
              !settingId ||
              options.idea.trim().length < 3 ||
              !prefs.summary.model
            }
            onClick={() =>
              void run(async () =>
                choose(
                  await authoring.generate<Draft>({
                    options,
                    setting_id: settingId,
                    config: {
                      ...prefs.summary,
                      max_tokens: Math.max(10000, prefs.summary.max_tokens),
                    },
                    api_key: apiKey || undefined,
                  }),
                ),
              )
            }
          >
            {busy ? "Генерация и проверка мира…" : "Сгенерировать мир"}
          </button>
          {!!drafts.length && (
            <label>
              Продолжить черновик
              <ChoiceControl
                defaultValue=""
                onChange={(e) =>
                  e.target.value &&
                  void run(async () =>
                    choose(
                      await api<Draft>(`/tabletop/drafts/${e.target.value}`),
                    ),
                  )
                }
              >
                <ChoiceOption value="">Выбрать</ChoiceOption>
                {drafts.map((d) => (
                  <ChoiceOption key={d.id} value={d.id}>
                    {d.name}
                    {d.generation_status === "INVALID" ? " (ошибки)" : ""}
                  </ChoiceOption>
                ))}
              </ChoiceControl>
            </label>
          )}
          <details>
            <summary>Импорт готовой кампании (JSON)</summary>
            <textarea
              aria-label="Импорт кампании"
              value={json}
              onChange={(e) => setJson(e.target.value)}
            />
            <button
              disabled={busy || !json.trim()}
              onClick={() =>
                void run(async () =>
                  choose(
                    await api<Draft>("/tabletop/drafts", {
                      definition: JSON.parse(json),
                    }),
                  ),
                )
              }
            >
              Проверить и импортировать
            </button>
          </details>
        </>
      ) : step === 1 && draft ? (
        <>
          <h2>{draft.definition.name}</h2>
          <p>{draft.definition.starting_scene}</p>
          <h3>Локации</h3>
          {draft.definition.locations.map((l) => (
            <details key={l.id}>
              <summary>{l.name}</summary>
              <p>{l.description}</p>
            </details>
          ))}
          <label className="tt-toggle">
            <input
              type="checkbox"
              checked={author}
              onChange={(e) => setAuthor(e.target.checked)}
            />{" "}
            Режим автора: редактирование со спойлерами
          </label>
          {author && (
            <>
              <p className="tt-note">
                Определение содержит секреты. В игровой интерфейс они не попадут
                до обнаружения.
              </p>
              <textarea
                className="tt-json"
                aria-label="Определение кампании"
                value={json}
                onChange={(e) => setJson(e.target.value)}
              />
              <button
                disabled={busy}
                onClick={() =>
                  void run(async () =>
                    choose(
                      await api<Draft>(
                        `/tabletop/drafts/${draft.id}`,
                        {
                          revision: draft.revision,
                          definition: JSON.parse(json),
                        },
                        "PUT",
                      ),
                    ),
                  )
                }
              >
                Проверить и сохранить мир
              </button>
            </>
          )}
          {draft.usage.map((u, i) => (
            <p className="tt-note" key={i}>
              {u.stage}: {u.seconds} с · вход {u.input_tokens ?? "—"} · выход{" "}
              {u.output_tokens ?? "—"} · ${u.cost ?? "неизвестно"}
            </p>
          ))}
        </>
      ) : step === 2 && draft ? (
        <CharacterCreator
          build={build}
          catalog={catalog}
          onChange={setBuild}
          onValidity={setCreatorValid}
          draftId={draft.id}
          prefs={prefs}
          apiKey={apiKey}
        />
      ) : draft ? (
        <>
          <h2>
            {build.name} · {catalog.classes[build.character_class].name}
          </h2>
          <p>{draft.definition.name}</p>
          <p>
            Кубики бросаются на сервере по твоему нажатию. Сложность проверок и
            нераскрытые секреты остаются скрытыми.
          </p>
        </>
      ) : null}
      {step === 3 && (
        <label>
          Развитие персонажа
          <ChoiceControl
            aria-label="Развитие персонажа"
            value={progressionMode}
            onChange={(e) => setProgressionMode(e.target.value)}
          >
            <ChoiceOption value="xp">
              Опыт за завершённые задания и бои
            </ChoiceOption>
            <ChoiceOption value="milestone">
              Вехи за завершённые задания
            </ChoiceOption>
          </ChoiceControl>
        </label>
      )}
      <footer>
        <button
          disabled={busy}
          onClick={step ? () => setStep(step - 1) : cancel}
        >
          {step ? "Назад" : "Отмена"}
        </button>
        {step > 0 && (
          <button
            className="tt-primary"
            disabled={
              busy ||
              draft?.generation_status === "INVALID" ||
              (step === 2 &&
                (!creatorValid || build.skills.length !== cls.skill_count))
            }
            onClick={() =>
              void run(async () => {
                if (step === 2)
                  await api("/tabletop/build/validate", {
                    build,
                    ruleset_id: catalog.id,
                    setting_id: catalog.setting_id,
                    setting_revision: catalog.setting_revision,
                    draft_id: catalog.draft_id,
                  });
                if (step < 3) setStep(step + 1);
                else if (draft)
                  done(
                    await api<Game>("/tabletop/games", {
                      draft_id: draft.id,
                      draft_revision: draft.revision,
                      character: build,
                      progression_mode: progressionMode,
                      config: prefs.game,
                      api_key: apiKey || undefined,
                    }),
                  );
              })
            }
          >
            {busy ? "Проверка…" : step < 3 ? "Далее" : "Начать приключение"}
          </button>
        )}
      </footer>
    </main>
  );
}
