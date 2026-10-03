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
    previews.find((p) => `${p.weapon}:${p.target}` === selection) ||
    previews[0];
  if (!p) return null;
  return (
    <section className="tt-combat-preview" aria-label="Предпросмотр атаки">
      <h3>Атака</h3>
      <label>
        Оружие и цель
        <select
          value={`${p.weapon}:${p.target}`}
          onChange={(e) => setSelection(e.target.value)}
        >
          {previews.map((p) => (
            <option
              key={`${p.weapon}:${p.target}`}
              value={`${p.weapon}:${p.target}`}
            >
              {p.name} → {p.target_name}
            </option>
          ))}
        </select>
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
        Урон: 1d{p.die} {signed(p.damage_modifier)} · {p.damage.join("–")} ·
        критический {p.critical_damage.join("–")}
      </p>
      <small>{p.damage_note}</small>
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
          act({ type: "attack", weapon: p.weapon, target: p.target })
        }
      >
        Атаковать: {p.target_name}
      </button>
    </section>
  );
}
