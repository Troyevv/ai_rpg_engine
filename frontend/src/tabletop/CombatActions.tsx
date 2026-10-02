import { useState } from "react";
import { AttackPreview } from "./AttackPreview";
import {
  abilities,
  signed,
  type Game,
  type Sheet,
  type Command,
} from "./types";
export function CombatActions({
  state: s,
  hero,
  blocked,
  act,
}: {
  state: Game["state"];
  hero: Sheet;
  blocked: boolean;
  act: (c: Command) => void;
}) {
  const [category, setCategory] = useState("Атака");
  const [chosen, setChosen] = useState("");
  const [target, setTarget] = useState("");
  const e = s.encounter!;
  const options = (s.usable_actions || []).filter(
    (a) => a.kind === (category === "Заклинания" ? "spell" : "feature"),
  );
  const a =
    options.find((a) => `${a.id}:${a.slot_level}` === chosen) || options[0];
  const t = a?.targets.find((t) => t.id === target) || a?.targets[0];
  const action = (label: string, c: Command, disabled = false) => (
    <button key={label} disabled={blocked || disabled} onClick={() => act(c)}>
      {label}
    </button>
  );
  return (
    <section className="tt-combat-actions" aria-label="Боевые действия">
      <nav aria-label="Категории боевых действий">
        {[
          "Атака",
          "Заклинания",
          "Способности",
          "Предметы",
          "Движение",
          "Другое",
        ].map((c) => (
          <button
            key={c}
            aria-pressed={category === c}
            onClick={() => setCategory(c)}
          >
            {c}
          </button>
        ))}
      </nav>
      {category === "Атака" ? (
        <AttackPreview
          previews={s.attack_previews || []}
          blocked={blocked}
          act={act}
        />
      ) : category === "Заклинания" || category === "Способности" ? (
        <>
          {!a ? (
            <p>Сейчас нет доступных действий этой категории.</p>
          ) : (
            <>
              <label>
                Выбрать действие
                <select
                  value={`${a.id}:${a.slot_level}`}
                  onChange={(ev) => setChosen(ev.target.value)}
                >
                  {options.map((o) => (
                    <option
                      key={`${o.id}:${o.slot_level}`}
                      value={`${o.id}:${o.slot_level}`}
                    >
                      {o.name}
                      {o.slot_level ? ` · ячейка ${o.slot_level}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <p>{a.description}</p>
              <p>
                {a.cost === "BONUS_ACTION"
                  ? "Бонусное действие"
                  : a.cost === "REACTION"
                    ? "Реакция"
                    : "Действие"}
              </p>
              <label>
                Цель
                <select
                  value={t?.id || ""}
                  onChange={(ev) => setTarget(ev.target.value)}
                >
                  {a.targets.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} · {t.distance} футов
                    </option>
                  ))}
                </select>
              </label>
              {t && (
                <p>
                  {t.hit_percent !== undefined
                    ? `Попадание ${t.hit_percent}% · модификатор ${t.modifier} · КД цели ${t.target_ac}`
                    : ""}{" "}
                  {t.expression
                    ? `Кубики ${t.expression}${t.healing_modifier ? ` ${signed(t.healing_modifier)}` : ""}`
                    : ""}{" "}
                  {t.save
                    ? `Спасбросок ${abilities[t.save] || t.save}, сложность ${t.save_dc}${t.half_on_save ? " · успех: половина урона" : ""}`
                    : ""}
                </p>
              )}
              {action(
                `Использовать: ${a.name}`,
                a.kind === "spell"
                  ? {
                      type: "cast_spell",
                      spell_id: a.id,
                      slot_level: a.slot_level,
                      target: t?.id,
                    }
                  : { type: "use_feature", feature_id: a.id, target: t?.id },
                !t,
              )}
            </>
          )}
        </>
      ) : category === "Предметы" ? (
        <>
          {hero.inventory
            .filter((i) => s.items[i.item_id]?.healing > 0)
            .map((i) => (
              <div key={i.item_id}>
                <p>
                  {s.items[i.item_id].name} ×{i.quantity} · лечение{" "}
                  {s.items[i.item_id].healing} HP · действие
                </p>
                {s.party
                  .filter(
                    (id) =>
                      Math.abs(s.characters[id].position - hero.position) <= 5,
                  )
                  .map((id) =>
                    action(
                      `Использовать на ${s.characters[id].name}`,
                      { type: "use_item", item_id: i.item_id, target: id },
                      !e.action,
                    ),
                  )}
              </div>
            ))}
        </>
      ) : category === "Движение" ? (
        <>
          <p>
            Осталось {e.movement} футов · скорость {hero.speed}
          </p>
          {Object.values(s.npcs).map((n) => (
            <p key={n.id}>
              {n.name}: {Math.abs(n.position - hero.position)} футов
            </p>
          ))}
          {[-5, 5].map((distance) =>
            action(
              `Движение ${distance > 0 ? "+" : ""}${distance}`,
              { type: "move", distance },
              e.movement < Math.abs(distance),
            ),
          )}
          {action("Рывок", { type: "dash" }, !e.action)}
          {action("Отход", { type: "disengage" }, !e.action)}
        </>
      ) : (
        <>
          {action("Уклонение", { type: "dodge" }, !e.action)}
          {action("Защититься", { type: "guard" }, !e.reaction[hero.id])}
          {action(
            "Скрыться",
            { type: "hide" },
            !e.action ||
              Object.values(s.npcs).some(
                (n) => n.hostile && Math.abs(n.position - hero.position) <= 5,
              ),
          )}
          {hero.conditions.includes("prone") &&
            action("Встать", { type: "stand" }, e.movement < hero.speed / 2)}
          {hero.conditions.includes("grappled") &&
            action("Освободиться", { type: "escape" }, !e.action)}
          {action("Занять укрытие", { type: "seek_cover" }, !e.action)}
          {Object.values(s.npcs)
            .filter(
              (n) =>
                n.hostile &&
                n.status === "на сцене" &&
                Math.abs(n.position - hero.position) <= 5,
            )
            .map((n) => (
              <div key={n.id}>
                {action(
                  `Сбить с ног: ${n.name}`,
                  { type: "shove", target: n.id },
                  !e.action,
                )}
                {action(
                  `Подготовить атаку: ${n.name}`,
                  { type: "ready", target: n.id },
                  !e.action || !e.reaction[hero.id],
                )}
              </div>
            ))}
          {action("Закончить ход", { type: "end_turn" })}
        </>
      )}
    </section>
  );
}
