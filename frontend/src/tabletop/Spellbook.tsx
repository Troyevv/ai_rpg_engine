import { useEffect, useState } from "react";
import type { Command, Game, Sheet } from "./types";

export function Spellbook({
  hero,
  state,
  blocked,
  act,
}: {
  hero: Sheet;
  state: Game["state"];
  blocked: boolean;
  act: (command: Command) => void;
}) {
  const [target, setTarget] = useState(hero.id);
  const [slot, setSlot] = useState(0);
  const [prepared, setPrepared] = useState(hero.prepared_spells);
  useEffect(() => setPrepared(hero.prepared_spells), [hero.prepared_spells]);
  const targets = [
    ...state.party.map((id) => ({ id, name: state.characters[id].name })),
    ...Object.values(state.npcs),
  ];
  return (
    <section className="tt-panel" aria-label="Книга заклинаний">
      <h2>Книга заклинаний · {hero.name}</h2>
      <p>
        {Object.entries(hero.spell_slots)
          .map(
            ([level, count]) =>
              `Ячейки ${level} круга: ${count.remaining}/${count.maximum}`,
          )
          .join(" · ")}
      </p>
      {hero.concentration && (
        <p>
          Концентрация:{" "}
          {
            hero.spell_definitions.find(
              (s) => s.id === hero.concentration?.spell_id,
            )?.name
          }
        </p>
      )}
      <div className="tt-form-grid">
        <label>
          Цель заклинания
          <select
            aria-label="Цель заклинания"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          >
            {targets.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Усиление
          <select
            aria-label="Круг ячейки"
            value={slot}
            onChange={(e) => setSlot(Number(e.target.value))}
          >
            <option value={0}>Минимальная ячейка</option>
            {Object.keys(hero.spell_slots).map((level) => (
              <option key={level} value={level}>
                {level} круг
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="tt-catalog-grid">
        {hero.spell_definitions.map((spell) => {
          const level = spell.level ? slot || spell.level : 0;
          const available =
            !spell.level || hero.prepared_spells.includes(spell.id);
          const hasSlot =
            !level || !!hero.spell_slots[String(level)]?.remaining;
          return (
            <article key={spell.id} className="tt-feature">
              <h3>
                {spell.name} · {spell.level ? `${spell.level} круг` : "Заговор"}
              </h3>
              <p>{spell.description}</p>
              <p>
                {spell.casting_time === "BONUS_ACTION"
                  ? "Бонусное действие"
                  : "Действие"}{" "}
                · {spell.range} футов
                {spell.concentration ? " · концентрация" : ""}
              </p>
              {spell.target_type === "area" && (
                <p>
                  Область {spell.area} футов вокруг цели затрагивает союзников.
                </p>
              )}
              {spell.level > 0 && !state.encounter && (
                <label>
                  <input
                    type="checkbox"
                    checked={prepared.includes(spell.id)}
                    onChange={(e) =>
                      setPrepared(
                        e.target.checked
                          ? [...prepared, spell.id]
                          : prepared.filter((i) => i !== spell.id),
                      )
                    }
                  />
                  Подготовить {spell.name}
                </label>
              )}
              <button
                disabled={
                  blocked ||
                  !available ||
                  !hasSlot ||
                  !state.usable_actions?.some(
                    (a) =>
                      a.kind === "spell" &&
                      a.id === spell.id &&
                      a.slot_level === level &&
                      a.targets.some((t) => t.id === target),
                  ) ||
                  level < spell.level ||
                  (!!state.encounter &&
                    !(spell.casting_time === "BONUS_ACTION"
                      ? state.encounter.bonus_action
                      : state.encounter.action))
                }
                onClick={() =>
                  act({
                    type: "cast_spell",
                    spell_id: spell.id,
                    target,
                    slot_level: level,
                  })
                }
              >
                Сотворить: {spell.name}
              </button>
            </article>
          );
        })}
      </div>
      {!state.encounter && (
        <button
          disabled={blocked}
          onClick={() => act({ type: "prepare_spells", spells: prepared })}
        >
          Сохранить подготовку
        </button>
      )}
    </section>
  );
}
