import { useEffect, useState } from "react";
import { api } from "../api";
import type { Preferences } from "../types";
import { abilities, skills, signed, type Build, type Catalog } from "./types";

type Preview = {
  sheet: {
    hp: number;
    armor_class: number;
    speed: number;
    features: string[];
    proficiencies: string[];
    attacks: Record<string, { name: string; die: number }>;
  };
  modifiers: Record<string, number>;
  skills: Record<string, number>;
  saves: Record<string, number>;
  points_remaining: number | null;
};
const proficiencyNames: Record<string, string> = {
  light: "Лёгкая броня",
  medium: "Средняя броня",
  heavy: "Тяжёлая броня",
  shield: "Щиты",
  simple: "Простое оружие",
  martial: "Воинское оружие",
  finesse: "Фехтовальное оружие",
  navigation: "Навигация",
  vehicles: "Транспорт",
  languages: "Языки",
  rituals: "Ритуалы",
  crafting: "Ремесло",
  thieves_tools: "Воровские инструменты",
  music: "Музыкальные инструменты",
};
const baseStages = [
  "Концепция",
  "Вид",
  "Класс",
  "Происхождение",
  "Характеристики",
  "Навыки",
  "Особенности",
  "Снаряжение",
  "Личность",
  "Внешность",
  "Обзор",
];
const prose = {
  name: "Имя героя",
  appearance: "Внешность",
  biography: "Биография",
  personality: "Характер",
  ideals: "Идеалы",
  bonds: "Привязанности",
  flaws: "Слабости",
};
export function CharacterCreator({
  build,
  catalog,
  onChange,
  onValidity,
  draftId,
  prefs,
  apiKey,
}: {
  build: Build;
  catalog: Catalog;
  onChange: (b: Build) => void;
  onValidity: (valid: boolean) => void;
  draftId: string;
  prefs: Preferences;
  apiKey: string;
}) {
  const casting = catalog.spellcasting?.[build.character_class];
  const stages = casting
    ? [...baseStages.slice(0, 8), "Заклинания", ...baseStages.slice(8)]
    : baseStages;
  const [step, setStep] = useState(0),
    [preview, setPreview] = useState<Preview | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const spellStep = !!casting && step === 8;
  const contentStep = casting && step > 8 ? step - 1 : step;
  const [proposal, setProposal] = useState<Partial<Build> | null>(null),
    [generationField, setGenerationField] = useState("all"),
    [generationError, setGenerationError] = useState("");
  const cls = catalog.classes[build.character_class];
  const change = (key: keyof Build, value: unknown) =>
    onChange({ ...build, [key]: value });
  useEffect(() => {
    const controller = new AbortController();
    onValidity(false);
    const timer = setTimeout(() => {
      api<Preview>(
        "/tabletop/build/preview",
        { build, ruleset_id: catalog.id },
        "POST",
        controller.signal,
      )
        .then((p) => {
          setPreview(p);
          setError("");
          onValidity(true);
        })
        .catch((e) => {
          if (e.name !== "AbortError") {
            setError(e.message);
            onValidity(false);
          }
        });
    }, 150);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [build, catalog.id, onValidity]);
  const generate = async (field: string) => {
    setBusy(true);
    setGenerationError("");
    setGenerationField(field);
    try {
      const result = await api<{ fields: Partial<Build> }>(
        "/tabletop/characters/generate",
        {
          draft_id: draftId,
          build,
          field,
          config: prefs.game,
          api_key: apiKey || undefined,
        },
      );
      setProposal(result.fields);
    } catch (e) {
      setGenerationError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const roleField = (key: keyof typeof prose) => (
    <label key={key}>
      {prose[key]}
      {key === "name" ? (
        <input
          aria-label={prose[key]}
          value={build[key]}
          maxLength={120}
          onChange={(e) => change(key, e.target.value)}
        />
      ) : (
        <textarea
          aria-label={prose[key]}
          value={build[key]}
          maxLength={
            key === "biography" ? 3000 : key === "appearance" ? 2000 : 1000
          }
          onChange={(e) => change(key, e.target.value)}
        />
      )}
      <button type="button" disabled={busy} onClick={() => void generate(key)}>
        Сгенерировать: {prose[key].toLowerCase()}
      </button>
    </label>
  );
  const totalCost = Object.values(build.abilities).reduce(
    (n, v) => n + (catalog.point_buy.costs?.[String(v)] ?? 0),
    0,
  );
  const setScore = (ability: string, value: number) => {
    if (build.ability_method === "standard_array") {
      const other = Object.keys(build.abilities).find(
        (a) => build.abilities[a] === value,
      )!;
      change("abilities", {
        ...build.abilities,
        [ability]: value,
        [other]: build.abilities[ability],
      });
    } else change("abilities", { ...build.abilities, [ability]: value });
  };
  const featureCard = (id: string) => (
    <article className="tt-feature" key={id}>
      <strong>{catalog.features[id]?.name || id}</strong>
      <p>{catalog.features[id]?.description}</p>
    </article>
  );
  return (
    <div className="tt-creator">
      <nav aria-label="Этапы создания персонажа" className="tt-creator-steps">
        {stages.map((s, i) => (
          <button
            type="button"
            aria-current={step === i ? "step" : undefined}
            key={s}
            onClick={() => setStep(i)}
          >
            {i + 1}. {s}
          </button>
        ))}
      </nav>
      <div className="tt-creator-layout">
        <section>
          <h2>{stages[step]}</h2>
          {!spellStep && contentStep === 0 && (
            <>
              {roleField("name")}
              <label>
                Концепция героя
                <textarea
                  value={build.concept}
                  onChange={(e) => change("concept", e.target.value)}
                  maxLength={2000}
                  placeholder="Бывший стражник, немногословный, защищает слабых…"
                />
              </label>
              <button disabled={busy} onClick={() => void generate("all")}>
                {busy ? "Создание портрета…" : "✨ Сгенерировать персонажа"}
              </button>
              <p className="tt-note">
                Генерация предлагает имя, внешность и личность. Характеристики и
                снаряжение выбираешь ты.
              </p>
            </>
          )}
          {!spellStep && contentStep === 1 && (
            <div className="tt-choice-grid">
              {Object.entries(catalog.species).map(([id, s]) => (
                <button
                  className="tt-choice-card"
                  aria-pressed={build.species === id}
                  key={id}
                  onClick={() => change("species", id)}
                >
                  <strong>{s.name}</strong>
                  <span>Скорость {s.speed}</span>
                  {(s.features || []).map((f) => (
                    <span key={f}>
                      {catalog.features[f]?.name}:{" "}
                      {catalog.features[f]?.description}
                    </span>
                  ))}
                </button>
              ))}
            </div>
          )}
          {!spellStep && contentStep === 2 && (
            <div className="tt-choice-grid">
              {Object.entries(catalog.classes).map(([id, c]) => (
                <button
                  className="tt-choice-card"
                  aria-pressed={build.character_class === id}
                  key={id}
                  onClick={() =>
                    onChange({
                      ...build,
                      character_class: id,
                      spells: null,
                      prepared_spells: null,
                      skills: c.skills.slice(0, c.skill_count),
                      equipment: c.equipment,
                      feature_choices: (c.feature_choices || []).slice(
                        0,
                        c.feature_choice_count || 0,
                      ),
                    })
                  }
                >
                  <strong>{c.name}</strong>
                  <span>Кость здоровья d{c.hit_die}</span>
                  <span>
                    Спасброски: {c.saves.map((x) => abilities[x]).join(", ")}
                  </span>
                  <span>
                    Броня:{" "}
                    {(c.armor || [])
                      .map((x) => proficiencyNames[x] || x)
                      .join(", ") || "нет"}
                  </span>
                  <span>
                    Оружие:{" "}
                    {(c.weapons || [])
                      .map((x) => proficiencyNames[x] || x)
                      .join(", ") || "по набору"}
                  </span>
                  {(c.features || []).map((f) => (
                    <span key={f}>
                      {catalog.features[f]?.name}:{" "}
                      {catalog.features[f]?.description}
                    </span>
                  ))}
                </button>
              ))}
            </div>
          )}
          {!spellStep && contentStep === 3 && (
            <div className="tt-choice-grid">
              {Object.entries(catalog.backgrounds).map(([id, b]) => (
                <button
                  className="tt-choice-card"
                  aria-pressed={build.background === id}
                  key={id}
                  onClick={() => change("background", id)}
                >
                  <strong>{b.name}</strong>
                  <span>{b.description}</span>
                  <span>
                    {(b.skills || []).map((s) => skills[s] || s).join(", ")}
                  </span>
                  <span>
                    {(b.equipment || [])
                      .map(
                        (i) => catalog.items.find((x) => x.id === i)?.name || i,
                      )
                      .join(", ")}
                  </span>
                </button>
              ))}
            </div>
          )}
          {!spellStep && contentStep === 4 && (
            <>
              <label>
                Метод характеристик
                <select
                  aria-label="Метод характеристик"
                  value={build.ability_method}
                  onChange={(e) =>
                    onChange({
                      ...build,
                      ability_method: e.target.value as Build["ability_method"],
                      abilities:
                        e.target.value === "point_buy"
                          ? Object.fromEntries(
                              catalog.abilities.map((a) => [
                                a,
                                catalog.point_buy.minimum!,
                              ]),
                            )
                          : { ...catalog.default_build.abilities },
                    })
                  }
                >
                  <option value="standard_array">Стандартный массив</option>
                  {catalog.point_buy.costs && (
                    <option value="point_buy">Point buy</option>
                  )}
                </select>
              </label>
              {build.ability_method === "point_buy" && (
                <p role="status" aria-label="Бюджет характеристик">
                  Осталось очков: {(catalog.point_buy.budget || 0) - totalCost}
                </p>
              )}
              <div className="tt-ability-grid">
                {catalog.abilities.map((a) => (
                  <div className="tt-score" key={a}>
                    <strong>{abilities[a]}</strong>
                    {build.ability_method === "point_buy" ? (
                      <div>
                        <button
                          aria-label={`Уменьшить: ${abilities[a]}`}
                          disabled={
                            build.abilities[a] <= catalog.point_buy.minimum!
                          }
                          onClick={() => setScore(a, build.abilities[a] - 1)}
                        >
                          −
                        </button>
                        <output>{build.abilities[a]}</output>
                        <button
                          aria-label={`Увеличить: ${abilities[a]}`}
                          disabled={
                            build.abilities[a] >= catalog.point_buy.maximum! ||
                            totalCost +
                              (catalog.point_buy.costs?.[
                                String(build.abilities[a] + 1)
                              ] ?? Infinity) -
                              (catalog.point_buy.costs?.[
                                String(build.abilities[a])
                              ] ?? 0) >
                              catalog.point_buy.budget!
                          }
                          onClick={() => setScore(a, build.abilities[a] + 1)}
                        >
                          +
                        </button>
                      </div>
                    ) : (
                      <select
                        aria-label={abilities[a]}
                        value={build.abilities[a]}
                        onChange={(e) => setScore(a, Number(e.target.value))}
                      >
                        {catalog.ability_array.map((v) => (
                          <option key={v}>{v}</option>
                        ))}
                      </select>
                    )}
                    <span>
                      Модификатор{" "}
                      {preview?.modifiers[a] !== undefined
                        ? signed(preview.modifiers[a])
                        : "…"}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
          {!spellStep && contentStep === 5 && (
            <>
              <p>
                Навыки класса: {build.skills.length} / {cls.skill_count}
              </p>
              {cls.skills.map((s) => (
                <label className="tt-toggle" key={s}>
                  <input
                    type="checkbox"
                    checked={build.skills.includes(s)}
                    onChange={(e) =>
                      change(
                        "skills",
                        e.target.checked
                          ? [...build.skills, s]
                          : build.skills.filter((x) => x !== s),
                      )
                    }
                  />
                  {skills[s] || s}
                </label>
              ))}
              <p>
                Происхождение добавит:{" "}
                {(catalog.backgrounds[build.background].skills || [])
                  .map((x) => skills[x] || x)
                  .join(", ") || "нет"}
                . Повторное владение не удваивает бонус.
              </p>
            </>
          )}
          {!spellStep && contentStep === 6 && (
            <>
              {(cls.features || []).map(featureCard)}
              {(catalog.species[build.species].features || []).map(featureCard)}
              {!!cls.feature_choice_count && (
                <>
                  <p>Выбери особенностей: {cls.feature_choice_count}</p>
                  {(cls.feature_choices || []).map((id) => (
                    <label className="tt-toggle" key={id}>
                      <input
                        type="checkbox"
                        checked={build.feature_choices.includes(id)}
                        onChange={(e) =>
                          change(
                            "feature_choices",
                            e.target.checked
                              ? [...build.feature_choices, id]
                              : build.feature_choices.filter((x) => x !== id),
                          )
                        }
                      />
                      {catalog.features[id]?.name}:{" "}
                      {catalog.features[id]?.description}
                    </label>
                  ))}
                </>
              )}
            </>
          )}
          {!spellStep && contentStep === 7 && (
            <label>
              Стартовый набор
              <select
                value={JSON.stringify(build.equipment)}
                onChange={(e) =>
                  change("equipment", JSON.parse(e.target.value))
                }
              >
                {(cls.equipment_choices || [cls.equipment]).map((items) => (
                  <option key={items.join("-")} value={JSON.stringify(items)}>
                    {items
                      .map(
                        (i) => catalog.items.find((x) => x.id === i)?.name || i,
                      )
                      .join(", ")}
                  </option>
                ))}
              </select>
              <p>Предметы происхождения добавляются отдельно.</p>
            </label>
          )}
          {spellStep && casting && (
            <section>
              <h2>Известные заклинания</h2>
              <p>
                Выбери до {casting.known} заклинаний; до {casting.prepared}{" "}
                заклинаний с ячейками можно подготовить. Заговоры доступны
                всегда.
              </p>
              <div className="tt-catalog-grid">
                {Object.values(catalog.spells)
                  .filter(
                    (s) =>
                      s.classes.includes(build.character_class) && s.level <= 1,
                  )
                  .map((s) => {
                    const known = build.spells ?? casting.defaults;
                    const prepared =
                      build.prepared_spells ??
                      known
                        .filter((id) => catalog.spells[id].level > 0)
                        .slice(0, casting.prepared);
                    return (
                      <article className="tt-feature" key={s.id}>
                        <h3>{s.name}</h3>
                        <p>{s.description}</p>
                        <label>
                          <input
                            type="checkbox"
                            checked={known.includes(s.id)}
                            onChange={(e) =>
                              onChange({
                                ...build,
                                spells: e.target.checked
                                  ? [...known, s.id]
                                  : known.filter((id) => id !== s.id),
                                prepared_spells: prepared.filter(
                                  (id) => id !== s.id,
                                ),
                              })
                            }
                          />
                          Знать {s.name}
                        </label>
                        {s.level > 0 && known.includes(s.id) && (
                          <label>
                            <input
                              type="checkbox"
                              checked={prepared.includes(s.id)}
                              onChange={(e) =>
                                onChange({
                                  ...build,
                                  spells: known,
                                  prepared_spells: e.target.checked
                                    ? [...prepared, s.id]
                                    : prepared.filter((id) => id !== s.id),
                                })
                              }
                            />
                            Подготовить {s.name}
                          </label>
                        )}
                      </article>
                    );
                  })}
              </div>
            </section>
          )}
          {!spellStep && contentStep === 8 && (
            <>
              <p className="tt-note">
                Ведущий использует эти поля в диалогах, реакции мира и сюжетных
                зацепках. Числовых бонусов они не дают.
              </p>
              {(
                [
                  "biography",
                  "personality",
                  "ideals",
                  "bonds",
                  "flaws",
                ] as const
              ).map(roleField)}
            </>
          )}
          {!spellStep && contentStep === 9 && roleField("appearance")}
          {!spellStep && contentStep === 10 && (
            <>
              <h3>{build.name}</h3>
              <p>
                {catalog.species[build.species].name} · {cls.name} ·{" "}
                {catalog.backgrounds[build.background].name}
              </p>
              <p>{build.appearance}</p>
              <p>{build.biography}</p>
              <p>{build.personality}</p>
              <p>{build.ideals}</p>
              <p>{build.bonds}</p>
              <p>{build.flaws}</p>
              <p>
                Зацепки:{" "}
                {(catalog.backgrounds[build.background].hooks || []).join(" ")}
              </p>
            </>
          )}
          {error && (
            <p role="alert" className="tt-error">
              {error}
            </p>
          )}
          <div className="tt-creator-navigation">
            <button disabled={step === 0} onClick={() => setStep(step - 1)}>
              Предыдущий шаг
            </button>
            <button
              disabled={step === stages.length - 1}
              onClick={() => setStep(step + 1)}
            >
              Следующий шаг
            </button>
          </div>
        </section>
        <aside
          className="tt-live-sheet"
          aria-label="Предварительный лист персонажа"
        >
          <h3>Твой персонаж</h3>
          {preview ? (
            <>
              <div className="tt-live-stats">
                <span>
                  HP <strong>{preview.sheet.hp}</strong>
                </span>
                <span>
                  КД <strong>{preview.sheet.armor_class}</strong>
                </span>
                <span>
                  Скорость <strong>{preview.sheet.speed}</strong>
                </span>
              </div>
              <p>
                {Object.entries(preview.modifiers)
                  .map(([k, v]) => `${abilities[k]} ${signed(v)}`)
                  .join(" · ")}
              </p>
              <h4>Спасброски</h4>
              <p>
                {Object.entries(preview.saves)
                  .map(([k, v]) => `${abilities[k]} ${signed(v)}`)
                  .join(" · ")}
              </p>
              <h4>Навыки</h4>
              <p>
                {Object.entries(preview.skills)
                  .map(([k, v]) => `${skills[k] || k} ${signed(v)}`)
                  .join(" · ")}
              </p>
              <h4>Атаки</h4>
              {Object.entries(preview.sheet.attacks).map(([id, a]) => (
                <p key={id}>
                  {a.name}: d{a.die}
                </p>
              ))}
              <h4>Особенности</h4>
              {preview.sheet.features.map(featureCard)}
              <p>
                Владения:{" "}
                {preview.sheet.proficiencies
                  .map((x) => proficiencyNames[x] || x)
                  .join(", ")}
              </p>
            </>
          ) : (
            <p>Расчёт листа…</p>
          )}
          {error && (
            <p>
              Показан последний корректный расчёт. Исправь выбор для
              продолжения.
            </p>
          )}
        </aside>
      </div>
      {generationError && (
        <p role="alert" className="tt-error">
          {generationError}
        </p>
      )}
      {proposal && (
        <section className="tt-proposal" aria-label="Предложение ведущего">
          <h3>Предложение ведущего</h3>
          {Object.entries(proposal).map(([key, value]) => (
            <p key={key}>
              <strong>{prose[key as keyof typeof prose]}</strong>:{" "}
              {String(value)}
            </p>
          ))}
          <button
            disabled={busy}
            onClick={() => {
              onChange({ ...build, ...proposal });
              setProposal(null);
            }}
          >
            Принять портрет
          </button>
          <button
            disabled={busy}
            onClick={() => void generate(generationField)}
          >
            Перегенерировать
          </button>
          <button disabled={busy} onClick={() => setProposal(null)}>
            Отклонить
          </button>
          <p>После принятия любое поле можно отредактировать.</p>
        </section>
      )}
    </div>
  );
}
