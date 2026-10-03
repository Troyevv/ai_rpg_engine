import { useState } from "react";
import {
  abilities,
  skills,
  purposes,
  signed,
  type Game,
  type Sheet,
  type Roll,
} from "./types";

export function HeroSummary({ hero }: { hero: Sheet }) {
  return (
    <>
      <span className="tt-eyebrow">Твой герой · уровень {hero.level}</span>
      <h2>{hero.name}</h2>
      <p className="tt-note">
        {hero.species_name} · {hero.character_class_name}
      </p>
      <div className="tt-health">
        <strong>
          {hero.hp} / {hero.max_hp} HP
        </strong>
        <progress aria-label="Здоровье" value={hero.hp} max={hero.max_hp} />
      </div>
      <div className="tt-stat-grid">
        <div>
          <strong>{hero.armor_class}</strong>
          <small>Класс доспеха</small>
        </div>
        <div>
          <strong>{hero.speed}</strong>
          <small>Скорость</small>
        </div>
      </div>
      <p>{hero.conditions.join(" · ") || "Нет состояний"}</p>
      {hero.feature_definitions
        .filter((f) => f.resource)
        .map((f) => (
          <p key={f.id}>
            {f.name}:{" "}
            <strong>
              {hero.resources[f.resource] || 0}/{f.uses}
            </strong>
          </p>
        ))}
      {hero.concentration && (
        <p>
          Концентрация:{" "}
          {
            hero.spell_definitions.find(
              (x) => x.id === hero.concentration?.spell_id,
            )?.name
          }
        </p>
      )}
    </>
  );
}
export function CombatHUD({ state }: { state: Game["state"] }) {
  const e = state.encounter;
  if (!e) return null;
  const name = (id: string) =>
    state.characters[id]?.name || state.npcs[id]?.name || id;
  return (
    <section className="tt-encounter" aria-label="Боевой HUD">
      <span className="tt-eyebrow">Раунд {e.round}</span>
      <h2>Ход: {name(e.current_actor)}</h2>
      <div className="tt-order">
        {e.order.map((id) => (
          <span key={id} className={id === e.current_actor ? "active" : ""}>
            {id === e.current_actor ? "▶ " : ""}
            {name(id)} · {e.initiative[id]}
          </span>
        ))}
      </div>
      <div className="tt-budgets">
        <span>Действие {e.action ? "●" : "○"}</span>
        <span>Бонус {e.bonus_action ? "●" : "○"}</span>
        <span>Реакция {e.reaction[e.current_actor] ? "●" : "○"}</span>
        <span>Движение {e.movement}</span>
      </div>
    </section>
  );
}
export function RollCard({
  pending: p,
  name,
  busy,
  roll,
}: {
  pending: NonNullable<Game["state"]["pending"]>;
  name: string;
  busy: boolean;
  roll: () => void;
}) {
  return (
    <section className="tt-roll-card" role="status">
      <div>
        <span className="tt-eyebrow">Ожидается бросок · {name}</span>
        <h2>{skills[p.skill] || purposes[p.purpose] || p.purpose}</h2>
        {p.reason && <p>{p.reason}</p>}
        <p>
          {[
            "check",
            "save",
            "attack",
            "spell_save",
            "concentration",
            "initiative",
          ].includes(p.purpose)
            ? `${abilities[p.ability]} · `
            : ""}
          <strong>
            {p.expression} {signed(p.modifier)}
          </strong>
          {p.critical ? " · критический урон" : ""}
        </p>
        {["check", "save", "spell_save", "concentration"].includes(
          p.purpose,
        ) && <small>Сложность: {p.dc ?? "скрыта"}</small>}
        {p.advantage_sources?.length > 0 && (
          <p>
            {p.advantage > 0
              ? "Преимущество"
              : p.advantage < 0
                ? "Помеха"
                : "Преимущество и помеха отменены"}
            : {p.advantage_sources.map((x) => x.name).join(" · ")}
          </p>
        )}
      </div>
      <button className="tt-primary" disabled={busy} onClick={roll}>
        Бросить кубик
      </button>
    </section>
  );
}
export function RollResult({
  event: e,
  name,
}: {
  event: {
    roll?: Roll;
    success?: boolean;
    dc?: number;
    skill?: string;
    outcome?: string;
  };
  name: string;
}) {
  const r = e.roll!;
  return (
    <div className="tt-roll-result">
      <div>
        <small>
          {name} · {skills[e.skill || ""] || purposes[r.purpose] || r.purpose}
        </small>
        {r.components && (
          <div className="tt-dice-tray" aria-label="Результаты кубиков">
            {r.components.map((c, i) => (
              <div key={i}>
                {c.raw.map((v, j) => (
                  <span
                    className={`tt-die tt-d${c.die} ${r.advantage && c.die === 20 ? (j === c.raw.indexOf(c.selected) ? "tt-selected-die" : "tt-discarded-die") : ""}`}
                    key={j}
                  >
                    <small>d{c.die}</small>
                    <b>{v}</b>
                  </span>
                ))}
                <small>
                  {c.sign < 0 ? "−" : "+"}
                  {c.selected}
                </small>
              </div>
            ))}
          </div>
        )}
        <p>
          [{r.raw.join(", ")}]{" "}
          {r.advantage !== 0 ? `выбрано ${r.selected} · ` : ""}
          {signed(r.modifier)} = <b>{r.total}</b>
        </p>
        {e.dc !== undefined && <small>Сложность {e.dc}</small>}
      </div>
      <strong>
        {e.outcome === "CRITICAL_SUCCESS"
          ? "Критический успех"
          : e.outcome === "CRITICAL_FAILURE"
            ? "Критическая неудача"
            : e.outcome === "PARTIAL_SUCCESS"
              ? "Частичный успех"
              : e.success === undefined
                ? r.total
                : e.success
                  ? "✓ Успех"
                  : "Неудача"}
      </strong>
    </div>
  );
}
export function CharacterSheet({
  hero: a,
  open,
}: {
  hero: Sheet;
  open: (tab: string) => void;
}) {
  const [section, setSection] = useState("Обзор");
  return (
    <section className="tt-panel tt-sheet">
      <h1>{a.name}</h1>
      <nav className="tt-sheet-tabs" aria-label="Разделы персонажа">
        {[
          "Обзор",
          "Характеристики",
          "Навыки",
          "Бой",
          "Способности",
          "Биография",
        ].map((t) => (
          <button
            key={t}
            aria-current={section === t ? "page" : undefined}
            onClick={() => setSection(t)}
          >
            {t}
          </button>
        ))}
        <button onClick={() => open("Инвентарь")}>Снаряжение</button>
        {a.spells.length > 0 && (
          <button onClick={() => open("Заклинания")}>Магия</button>
        )}
      </nav>
      {section === "Обзор" ? (
        <>
          <HeroSummary hero={a} />
          <p>
            Опыт: {a.xp}
            {!a.progression.maximum && ` / ${a.progression.required_xp}`}
          </p>
          <p>{a.appearance}</p>
        </>
      ) : section === "Характеристики" ? (
        <div className="tt-stat-grid">
          {Object.entries(a.abilities).map(([k, v]) => (
            <div key={k}>
              <small>{abilities[k]}</small>
              <strong>
                {v} ({signed(a.modifiers[k])})
              </strong>
              <small>Спасбросок {signed(a.save_modifiers[k])}</small>
            </div>
          ))}
        </div>
      ) : section === "Навыки" ? (
        <div className="tt-skill-list">
          {Object.entries(a.skill_modifiers).map(([k, v]) => (
            <p key={k}>
              <span>{skills[k] || k}</span>
              <strong>{signed(v)}</strong>
            </p>
          ))}
        </div>
      ) : section === "Бой" ? (
        <>
          <p>
            КД {a.armor_class} · скорость {a.speed}
          </p>
          {Object.entries(a.attacks).map(([id, w]) => (
            <article key={id}>
              <h3>{w.name}</h3>
              <p>
                Атака {signed(a.attack_modifiers[id])} · урон 1d{w.die}{" "}
                {signed(a.damage_modifiers[id])} · дистанция {w.reach}
              </p>
            </article>
          ))}
        </>
      ) : section === "Способности" ? (
        a.feature_definitions.map((f) => (
          <article key={f.id}>
            <h3>{f.name}</h3>
            <small>
              Источник:{" "}
              {{
                CLASS: "класс",
                SUBCLASS: "подкласс",
                SPECIES: "вид",
                BACKGROUND: "происхождение",
                FEAT: "черта",
                ITEM: "предмет",
                CONDITION: "состояние",
              }[f.source] || f.source}{" "}
              · уровень {f.level}
            </small>
            <p>{f.description}</p>
            <small>
              {f.activation === "PASSIVE"
                ? "Постоянный эффект"
                : f.activation === "BONUS_ACTION"
                  ? "Бонусное действие"
                  : "Действие"}
              {f.resource &&
                ` · осталось ${a.resources[f.resource] || 0}/${f.uses} · восстановление: ${f.recharge === "short" ? "короткий отдых" : f.recharge === "long" ? "долгий отдых" : "нет"}`}
            </small>
          </article>
        ))
      ) : (
        Object.entries({
          appearance: "Внешность",
          biography: "Биография",
          personality: "Характер",
          ideals: "Идеалы",
          bonds: "Привязанности",
          flaws: "Слабости",
        }).map(([k, label]) => (
          <article key={k}>
            <h3>{label}</h3>
            <p>{String(a[k as keyof Sheet] || "Не заполнено")}</p>
          </article>
        ))
      )}
    </section>
  );
}
