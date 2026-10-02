import { abilities, skills, signed, type Catalog } from "./types";
export type BuildPreview = {
  sheet: {
    hp: number;
    armor_class: number;
    speed: number;
    gold: number;
    equipment_bonuses?: Record<string, number>;
    features: string[];
    proficiencies: string[];
    attacks: Record<string, { name: string; die: number }>;
  };
  modifiers: Record<string, number>;
  skills: Record<string, number>;
  saves: Record<string, number>;
  attacks: Record<string, number>;
  damage: Record<string, number>;
  initiative: number;
  valid: boolean;
  points_remaining: number | null;
  gold_remaining: number;
};
export function BuildImpactPreview({
  before,
  after,
  catalog,
}: {
  before: BuildPreview | null;
  after: BuildPreview | null;
  catalog: Pick<Catalog, "features">;
}) {
  if (!before || !after)
    return (
      <p className="tt-note">
        Измени выбор — здесь появится его влияние на героя.
      </p>
    );
  const numbers = (p: BuildPreview): Record<string, number> =>
    Object.fromEntries([
      ["HP", p.sheet.hp],
      ["Класс брони", p.sheet.armor_class],
      ["Скорость", p.sheet.speed],
      ["Инициатива", p.initiative],
      ["Золото", p.gold_remaining],
      [
        "Помеха скрытности (1 = да)",
        p.sheet.equipment_bonuses?.stealth_disadvantage || 0,
      ],
      ...Object.entries(p.saves).map(([k, v]) => [
        "Спасбросок: " + abilities[k],
        v,
      ]),
      ...Object.entries(p.skills).map(([k, v]) => [skills[k] || k, v]),
      ...Object.entries(p.attacks).map(([k, v]) => [
        "Атака: " + (p.sheet.attacks[k]?.name || k),
        v,
      ]),
      ...Object.entries(p.damage).map(([k, v]) => [
        "Урон: " + (p.sheet.attacks[k]?.name || k),
        v,
      ]),
    ]) as Record<string, number>;
  const a = numbers(before),
    b = numbers(after);
  const changes = Object.entries(b).filter(([k, v]) => v !== a[k]);
  const gained = after.sheet.features.filter(
      (f) => !before.sheet.features.includes(f),
    ),
    lost = before.sheet.features.filter(
      (f) => !after.sheet.features.includes(f),
    );
  return (
    <section
      className="tt-impact"
      aria-label="Влияние выбора"
      aria-live="polite"
    >
      <h3>Что изменилось</h3>
      {changes.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Показатель</th>
              <th>Было</th>
              <th>Стало</th>
              <th>Разница</th>
            </tr>
          </thead>
          <tbody>
            {changes.map(([k, v]) => (
              <tr key={k}>
                <td>{k}</td>
                <td>{a[k] ?? "—"}</td>
                <td>{v}</td>
                <td>
                  {a[k] === undefined
                    ? "новое"
                    : signed(Number(v) - Number(a[k]))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {gained.map((f) => (
        <p key={f}>
          + {catalog.features[f]?.name}: {catalog.features[f]?.description}
        </p>
      ))}
      {lost.map((f) => (
        <p key={f}>− {catalog.features[f]?.name}</p>
      ))}
      {after.sheet.proficiencies
        .filter((p) => !before.sheet.proficiencies.includes(p))
        .map((p) => (
          <p key={p}>Новое владение: {p}</p>
        ))}
      {!changes.length && !gained.length && !lost.length && (
        <p>
          Численные показатели не изменились. Следующий порог характеристики
          может изменить модификатор.
        </p>
      )}
    </section>
  );
}
