import { ChoiceControl, ChoiceOption } from "@/components/choice/ChoiceControl";
import { ActionImpact } from "./ActionImpact";
import { useState } from "react";
import { abilities, signed, type Command, type Sheet } from "./types";

export function LevelUp({
  hero,
  gameId,
  blocked,
  act,
}: {
  hero: Sheet;
  gameId: string;
  blocked: boolean;
  act: (command: Command) => void;
}) {
  const [open, setOpen] = useState(false),
    [subclass, setSubclass] = useState(""),
    [feat, setFeat] = useState(""),
    [first, setFirst] = useState("strength"),
    [second, setSecond] = useState("strength"),
    [spells, setSpells] = useState<string[]>([]);
  const options = hero.progression;
  if (!options?.available) return null;
  const increases = feat ? [] : options.asi ? [first, second] : [];
  const con =
    hero.abilities.constitution +
    increases.filter((a) => a === "constitution").length;
  const oldCon = Math.floor((hero.abilities.constitution - 10) / 2),
    newCon = Math.floor((con - 10) / 2);
  const extraHp = [
    ...options.features,
    ...options.feats.filter((f) => f.id === feat),
  ]
    .flatMap((f) => f.effects)
    .filter((e) => e.type === "max_hp")
    .reduce((n, e) => n + e.value, 0);
  const hp =
    Math.max(1, options.hp_base + newCon) +
    (newCon - oldCon) * hero.level +
    extraHp;
  return (
    <section className="tt-level-up">
      <button disabled={blocked} onClick={() => setOpen(!open)}>
        Новый уровень: {options.level}
      </button>
      {open && (
        <div className="tt-panel" role="dialog" aria-label="Повышение уровня">
          <h2>
            Уровень {hero.level} → {options.level}
          </h2>
          <p>
            HP +{hp} · мастерство {signed(options.proficiency)}
          </p>
          {options.features.map((f) => (
            <p key={f.id}>
              <strong>{f.name}</strong>: {f.description}
            </p>
          ))}
          {options.subclasses.length > 0 && (
            <label>
              Подкласс
              <ChoiceControl
                aria-label="Подкласс"
                value={subclass}
                onChange={(e) => setSubclass(e.target.value)}
              >
                <ChoiceOption value="">Выбери путь</ChoiceOption>
                {options.subclasses.map((s) => (
                  <ChoiceOption key={s.id} value={s.id}>
                    {s.name} — {s.description}
                  </ChoiceOption>
                ))}
              </ChoiceControl>
            </label>
          )}
          {options.asi && (
            <>
              <label>
                Характеристики или черта
                <ChoiceControl
                  aria-label="Улучшение уровня"
                  value={feat}
                  onChange={(e) => setFeat(e.target.value)}
                >
                  <ChoiceOption value="">Два очка характеристик</ChoiceOption>
                  {options.feats.map((f) => (
                    <ChoiceOption key={f.id} value={f.id}>
                      {f.name} — {f.description}
                    </ChoiceOption>
                  ))}
                </ChoiceControl>
              </label>
              {!feat && (
                <div className="tt-form-grid">
                  {[
                    [first, setFirst],
                    [second, setSecond],
                  ].map(([value, setter], i) => (
                    <label key={i}>
                      Очко {i + 1}
                      <ChoiceControl
                        aria-label={`Очко характеристики ${i + 1}`}
                        value={value as string}
                        onChange={(e) =>
                          (setter as (s: string) => void)(e.target.value)
                        }
                      >
                        {Object.entries(abilities).map(([id, name]) => (
                          <ChoiceOption key={id} value={id}>
                            {name} ({hero.abilities[id]})
                          </ChoiceOption>
                        ))}
                      </ChoiceControl>
                    </label>
                  ))}
                </div>
              )}
            </>
          )}
          {options.spells.length > 0 && (
            <>
              <h3>Новые заклинания: до {options.learn_spells}</h3>
              {options.spells.map((s) => (
                <label key={s.id}>
                  <input
                    type="checkbox"
                    checked={spells.includes(s.id)}
                    onChange={(e) =>
                      setSpells(
                        e.target.checked
                          ? [...spells, s.id]
                          : spells.filter((id) => id !== s.id),
                      )
                    }
                  />
                  {s.name} · {s.level} круг
                </label>
              ))}
            </>
          )}
          {Object.keys(options.spell_slots).length > 0 && (
            <p>
              Максимум ячеек:{" "}
              {Object.entries(options.spell_slots)
                .map(([tier, count]) => `${tier} круг ×${count}`)
                .join(" · ")}
            </p>
          )}
          <ActionImpact
            gameId={gameId}
            command={{
              type: "level_up",
              actor_id: hero.id,
              subclass,
              feat_id: feat,
              ability_increases: increases,
              learn_spells: spells,
            }}
          />
          <button
            disabled={
              blocked ||
              (options.subclasses.length > 0 && !subclass) ||
              spells.length > options.learn_spells ||
              increases.some(
                (a) =>
                  hero.abilities[a] + increases.filter((x) => x === a).length >
                  20,
              )
            }
            onClick={() => {
              act({
                type: "level_up",
                subclass,
                feat_id: feat,
                ability_increases: increases,
                learn_spells: spells,
              });
              setOpen(false);
            }}
          >
            Подтвердить уровень
          </button>
          <button onClick={() => setOpen(false)}>Вернуться к игре</button>
        </div>
      )}
    </section>
  );
}
