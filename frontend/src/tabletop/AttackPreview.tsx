import { ChoiceControl, ChoiceOption } from "@/components/choice/ChoiceControl";
import { useState } from "react";
import { signed, type AttackPreview as Preview, type Command } from "./types";
export function AttackPreview({
  previews,
  blocked,
  act,
}: {
  previews: Preview[];
  blocked: boolean;
  act: (c: Command) => void;
}) {
  const [selection, setSelection] = useState("");
  const p =
    previews.find(
      (p) => `${p.weapon}:${p.target}:${p.mode || "single"}` === selection,
    ) || previews[0];
  if (!p) return null;
  return (
    <section className="tt-combat-preview" aria-label="Предпросмотр атаки">
      <h3>Атака</h3>
      <label>
        Оружие и цель
        <ChoiceControl
          value={`${p.weapon}:${p.target}:${p.mode || "single"}`}
          onChange={(e) => setSelection(e.target.value)}
        >
          {previews.map((p) => (
            <ChoiceOption
              key={`${p.weapon}:${p.target}:${p.mode || "single"}`}
              value={`${p.weapon}:${p.target}:${p.mode || "single"}`}
            >
              {p.name} → {p.target_name}
              {p.magazine
                ? ` · ${{ single: "Одиночный", burst: "Очередь", automatic: "Автоматический" }[p.mode || "single"] || p.mode}`
                : ""}
            </ChoiceOption>
          ))}
        </ChoiceControl>
      </label>
      <p>
        КД цели: {p.target_ac} · порог по сумме: {p.target_ac - p.modifier}+
      </p>
      <strong className="tt-hit-chance">{p.hit_percent}% попадания</strong>
      <p>
        1d20 {signed(p.modifier)} ·{" "}
        {p.advantage > 0
          ? "преимущество"
          : p.advantage < 0
            ? "помеха"
            : "обычный бросок"}
      </p>
      <p>
        Урон: {p.expression || `1d${p.die}`} {signed(p.damage_modifier)} ·{" "}
        {p.damage.join("–")} · критический {p.critical_damage.join("–")}
      </p>
      <small>{p.damage_note}</small>
      {p.damage_type && <p>Тип урона: {p.damage_type}</p>}
      {p.resource_cost?.map((cost) => (
        <p key={cost.resource_id}>
          Расход: {cost.resource_id} · {cost.amount}
        </p>
      ))}
      {p.magazine && (
        <p>
          Боеприпасы: {p.ammunition_remaining} / {p.magazine.capacity} · расход{" "}
          {p.ammunition_cost}
        </p>
      )}
      {p.magazine && (
        <button
          disabled={blocked}
          onClick={() => act({ type: "reload", item_id: p.weapon })}
        >
          Перезарядить ·{" "}
          {p.magazine.reload_cost === "BONUS_ACTION"
            ? "бонусное действие"
            : "действие"}
        </button>
      )}
      <p>
        Дистанция {p.distance} / {p.reach} футов · {p.cost}
      </p>
      <details>
        <summary>Расчёт попадания</summary>
        {Object.entries(p.breakdown).map(([k, v]) => (
          <p key={k}>
            {k}: {signed(v)}
          </p>
        ))}
        {p.sources.map((s, i) => (
          <p key={i}>{s.name}</p>
        ))}
        <p>Естественная 1 — промах, 20 — критическое попадание.</p>
      </details>
      {p.reason && <p role="status">{p.reason}</p>}
      <button
        className="tt-primary"
        disabled={blocked || !p.available}
        onClick={() =>
          act({
            type: "attack",
            weapon: p.weapon,
            target: p.target,
            mode: p.mode || "single",
          })
        }
      >
        Атаковать: {p.target_name}
      </button>
    </section>
  );
}
