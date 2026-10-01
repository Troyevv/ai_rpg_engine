import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Preferences } from "./types";
import { Wizard } from "./tabletop/Wizard";
import {
  abilities,
  skills,
  purposes,
  signed,
  type Command,
  type Game,
  type Sheet,
} from "./tabletop/types";
import "./styles/tabletop.css";
const modeNames: Record<string, string> = {
  EXPLORATION: "Исследование",
  DIALOGUE: "Разговор",
  ENCOUNTER: "Бой",
  AWAITING_ROLL: "Ожидание броска",
};
const controlNames: Record<string, string> = {
  PLAYER: "Игрок",
  AI: "Автоматическое управление",
  DM: "Ведущий",
};
const questNames: Record<string, string> = {
  available: "Доступно",
  active: "В процессе",
  completed: "Выполнено",
};
export function Tabletop({
  onBack,
  onSettings,
  prefs,
  apiKey,
}: {
  onBack: () => void;
  onSettings: () => void;
  prefs: Preferences;
  apiKey: string;
}) {
  const [games, setGames] = useState<{ id: string; name: string }[]>([]),
    [game, setGame] = useState<Game | null>(null),
    [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [tab, setTab] = useState("Игра"),
    [text, setText] = useState(""),
    [context, setContext] = useState("");
  const lock = useRef(false);
  const refresh = () =>
    api<{ id: string; name: string }[]>("/tabletop/games").then(setGames);
  useEffect(() => {
    let active = true;
    api<{ id: string; name: string }[]>("/tabletop/games")
      .then(async (list) => {
        if (!active) return;
        setGames(list);
        const id = localStorage.getItem("tabletop-game");
        if (list.some((g) => g.id === id)) {
          const g = await api<Game>(`/tabletop/games/${id}`);
          if (active) setGame(g);
        }
      })
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, []);
  async function run(fn: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  const accept = (g: Game) => {
    setGame(g);
    setCreating(false);
    setTab("Игра");
    localStorage.setItem("tabletop-game", g.id);
    void refresh();
  };
  async function perform(path: string, payload: object, model = true) {
    if (!game) return;
    await run(async () => {
      try {
        setGame(
          await api<Game>(`/tabletop/games/${game.id}/${path}`, {
            ...payload,
            revision: game.revision,
            request_id: crypto.randomUUID(),
            ...(model
              ? { config: prefs.game, api_key: apiKey || undefined }
              : {}),
          }),
        );
        setText("");
        setContext("");
      } catch (e) {
        setGame(await api<Game>(`/tabletop/games/${game.id}`));
        throw e;
      }
    });
  }
  const s = game?.state,
    enc = s?.encounter,
    pending = s?.pending,
    acting =
      s?.reaction?.actor || enc?.current_actor || s?.controlled_actor || "";
  const hero = s?.characters[acting] || s?.characters[s.controlled_actor];
  const blocked =
    busy ||
    !!s?.choice ||
    !!pending ||
    !!s?.reaction ||
    !hero ||
    hero.hp <= 0 ||
    hero.controller.controller !== "PLAYER";
  const act = (command: Command) =>
    void perform("actions", { command: { actor_id: acting, ...command } });
  const name = (id: string) =>
    s?.characters[id]?.name || s?.npcs[id]?.name || id;
  const button = (
    label: string,
    command: Command,
    disabled = command.type === "rest" && hero?.conditions.includes("stable")
      ? busy || !!pending || !!enc
      : blocked,
  ) => (
    <button key={label} disabled={disabled} onClick={() => act(command)}>
      {label}
    </button>
  );
  const sheet = (a: Sheet) => (
    <article className="tt-panel" key={a.id}>
      <h2>{a.name}</h2>
      <p>
        {a.character_class_name} · {a.species_name} · уровень {a.level} ·{" "}
        {controlNames[a.controller.controller]}
      </p>
      <p>
        <strong>
          {a.hp} / {a.max_hp} HP
        </strong>{" "}
        · КД {a.armor_class} · скорость {a.speed} · позиция {a.position}
      </p>
      <p>{a.conditions.join(", ")}</p>
      <div className="tt-form-grid">
        {Object.entries(a.abilities).map(([k, v]) => (
          <div key={k}>
            {abilities[k]}{" "}
            <strong>
              {v} ({signed(a.modifiers[k])})
            </strong>{" "}
            · спасбросок {signed(a.save_modifiers[k])}
          </div>
        ))}
      </div>
      <h3>Навыки</h3>
      <p>
        {Object.entries(a.skill_modifiers)
          .map(([k, v]) => `${skills[k] || k} ${signed(v)}`)
          .join(" · ")}
      </p>
      <h3>Оружие</h3>
      {Object.entries(a.attacks).map(([id, w]) => (
        <p key={id}>
          {w.name}: {signed(a.attack_modifiers[id])} · 1d{w.die} · дистанция{" "}
          {w.reach}
        </p>
      ))}
      {Object.entries({
        appearance: "Внешность",
        biography: "Биография",
        personality: "Характер",
        ideals: "Идеалы",
        bonds: "Привязанности",
        flaws: "Слабости",
      }).map(
        ([key, label]) =>
          a[key as keyof Sheet] && (
            <p key={key}>
              <strong>{label}:</strong> {String(a[key as keyof Sheet])}
            </p>
          ),
      )}
    </article>
  );
  return (
    <div className="tt-shell">
      <header className="tt-header">
        <button onClick={onBack} disabled={busy}>
          Истории
        </button>
        <div>
          <strong>Настольная RPG</strong>
          <small>{game?.state.ruleset.name || "D20 Fantasy"}</small>
        </div>
        <button onClick={onSettings}>Настройки DM</button>
      </header>
      <div className="tt-toolbar">
        <button disabled={busy} onClick={() => setCreating(true)}>
          Новая кампания
        </button>
        <select
          aria-label="Сохранённая кампания"
          value={game?.id || ""}
          disabled={busy}
          onChange={(e) =>
            void run(async () =>
              accept(await api<Game>(`/tabletop/games/${e.target.value}`)),
            )
          }
        >
          <option value="" disabled>
            Выбрать кампанию
          </option>
          {games.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
        <span className="tt-note">
          AI-ведущий · {prefs.game.model || "выбери модель в настройках"}
        </span>
      </div>
      {error && (
        <p role="alert" className="tt-error">
          {error}
        </p>
      )}
      {creating ? (
        <Wizard
          prefs={prefs}
          apiKey={apiKey}
          done={accept}
          cancel={() => setCreating(false)}
        />
      ) : !s || !game ? (
        <main className="tt-panel">
          <h1>Твоя настольная кампания</h1>
          <p>
            Создай мир по своей идее, собери героя и исследуй его с ведущим.
          </p>
          <button onClick={() => setCreating(true)}>Создать кампанию</button>
        </main>
      ) : (
        <>
          <section className="tt-panel">
            <h1>{s.campaign}</h1>
            <p>
              {s.location} · {modeNames[s.mode]} ·{" "}
              {Math.floor(s.game_time / 60)} мин.
            </p>
            {enc && (
              <p>
                Раунд {enc.round} · ход:{" "}
                <strong>{name(enc.current_actor)}</strong> · действие{" "}
                {enc.action ? "доступно" : "потрачено"} · бонус{" "}
                {enc.bonus_action ? "доступен" : "потрачен"} · движение{" "}
                {enc.movement} · реакция{" "}
                {enc.reaction[acting] ? "доступна" : "потрачена"} ·
                взаимодействие {enc.free_interaction ? "доступно" : "потрачено"}
              </p>
            )}
            {s.choice && (
              <div className="tt-roll-prompt" role="status">
                <h2>{s.choice.prompt}</h2>
                {s.choice.options.map((option) => (
                  <button
                    key={option.id}
                    disabled={busy}
                    onClick={() =>
                      void perform("actions", {
                        command: {
                          type: "resolve_choice",
                          actor_id: s.choice!.actor,
                          pending_id: s.choice!.id,
                          option_id: option.id,
                        },
                      })
                    }
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            )}
            {pending && (
              <div className="tt-roll-prompt" role="status">
                <h2>
                  {name(pending.actor)}:{" "}
                  {purposes[pending.purpose] || pending.purpose}
                </h2>
                <p>
                  {pending.reason && (
                    <span>
                      {pending.reason}
                      <br />
                    </span>
                  )}
                  {pending.advantage_sources?.length > 0 && (
                    <span className="tt-advantage">
                      {pending.advantage > 0
                        ? "Преимущество"
                        : pending.advantage < 0
                          ? "Помеха"
                          : "Преимущество и помеха отменены"}
                      :{" "}
                      {pending.advantage_sources.map((x) => x.name).join(" · ")}
                    </span>
                  )}
                  {pending.expression} {signed(pending.modifier)}
                  {pending.critical ? " · критический урон" : ""}
                </p>
                <button
                  className="tt-primary"
                  disabled={busy}
                  onClick={() =>
                    void perform("roll", { pending_id: pending.id })
                  }
                >
                  Бросить кубик
                </button>
              </div>
            )}
            {s.reaction && !pending && (
              <div role="status">
                <p>
                  {name(s.reaction.actor)} может атаковать{" "}
                  {name(s.reaction.mover)} реакцией.
                </p>
                {button(
                  "Атаковать реакцией",
                  { type: "reaction_attack" },
                  busy,
                )}
                {button(
                  "Пропустить реакцию",
                  { type: "decline_reaction" },
                  busy,
                )}
              </div>
            )}
          </section>
          <nav className="tt-tabs" aria-label="Разделы кампании">
            {[
              "Игра",
              "Персонаж",
              "Инвентарь",
              "Журнал",
              "Партия",
              "Карта",
              "Броски",
              "DM",
            ].map((t) => (
              <button
                key={t}
                aria-pressed={tab === t}
                onClick={() => setTab(t)}
              >
                {t}
              </button>
            ))}
          </nav>
          {tab === "Игра" ? (
            <main className="tt-game-grid">
              <section className="tt-panel">
                <h2>{s.location}</h2>
                <p>{s.scene}</p>
                <div className="tt-history">
                  {game.history.map((h) => (
                    <article key={h.revision}>
                      <small>
                        #{h.revision} · {h.user_text}
                      </small>
                      {h.narrative && (
                        <p
                          className="tt-narration"
                          style={{ whiteSpace: "pre-wrap" }}
                        >
                          {h.narrative}
                        </p>
                      )}
                      <div className="tt-mechanics" aria-label="События правил">
                        {h.events
                          .filter((e) => !e.roll)
                          .map((e, i) => (
                            <p key={i}>{e.text}</p>
                          ))}
                      </div>
                      {h.events
                        .filter((e) => e.roll)
                        .map((e, i) => (
                          <p key={i}>
                            {name(e.roll!.actor)} ·{" "}
                            {purposes[e.roll!.purpose] || e.roll!.purpose}: [
                            {e.roll!.raw.join(", ")}]{" "}
                            {e.roll!.advantage !== 0
                              ? `выбрано ${e.roll!.selected} · `
                              : ""}
                            {signed(e.roll!.modifier)} ={" "}
                            <strong>{e.roll!.total}</strong>
                          </p>
                        ))}
                    </article>
                  ))}
                </div>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void perform("actions", { text });
                  }}
                >
                  <label>
                    Твоё действие
                    <textarea
                      disabled={blocked}
                      value={text}
                      onChange={(e) => setText(e.target.value)}
                      placeholder="Опиши, что хочешь сделать…"
                    />
                  </label>
                  <button disabled={blocked || !text.trim()}>
                    Отправить DM
                  </button>
                </form>

                <button
                  disabled={busy || game.revision < 2}
                  onClick={() => void perform("rollback", {})}
                >
                  Откатить действие
                </button>
              </section>
              <aside className="tt-panel">
                <h2>Действия · {hero?.name}</h2>
                <div className="tt-actions">
                  {button("Осмотреться", { type: "look" })}
                  {button("Обыскать место", {
                    type: "check",
                    purpose: "search",
                    ability: "wisdom",
                    skill: "perception",
                  })}
                  {enc ? (
                    <>
                      {[
                        ["dodge", "Уклонение"],
                        ["dash", "Рывок"],
                        ["disengage", "Отход"],
                        ["guard", "Защититься"],
                        ["recover", "Восстановиться"],
                        ["hide", "Скрыться"],
                        ["stand", "Встать"],
                        ["escape", "Освободиться"],
                        ["flee", "Сбежать"],
                        ["end_turn", "Закончить ход"],
                      ].map(([type, label]) => button(label, { type }))}
                      {[-5, 5].map((distance) =>
                        button(`Движение ${signed(distance)}`, {
                          type: "move",
                          distance,
                        }),
                      )}
                    </>
                  ) : (
                    <>
                      {s.exits.map((l) =>
                        button(`Перейти: ${l.name}`, {
                          type: "move",
                          target: l.id,
                        }),
                      )}
                      {s.encounters.map((e) =>
                        button(`Начать бой: ${e.name}`, {
                          type: "start_encounter",
                          target: e.id,
                        }),
                      )}
                      {button("Короткий отдых", {
                        type: "rest",
                        rest: "short",
                      })}
                      {button("Долгий отдых", { type: "rest", rest: "long" })}
                    </>
                  )}
                </div>
                {hero?.feature_definitions?.some(
                  (f) => f.activation !== "PASSIVE",
                ) && (
                  <>
                    <h3>Способности</h3>
                    {hero.feature_definitions
                      .filter((f) => f.activation !== "PASSIVE")
                      .map((f) => (
                        <article key={f.id}>
                          <strong>{f.name}</strong>
                          <p>{f.description}</p>
                          {f.resource && (
                            <p>
                              Осталось: {hero.resources[f.resource] || 0} /{" "}
                              {f.uses}
                            </p>
                          )}
                          {(f.target === "ally" ? s.party : [acting]).map(
                            (target) =>
                              button(
                                `${f.name}${f.target === "ally" ? `: ${name(target)}` : ""}`,
                                {
                                  type: "use_feature",
                                  feature_id: f.id,
                                  target,
                                },
                                blocked ||
                                  (!!f.resource &&
                                    !hero.resources[f.resource]) ||
                                  (!!enc &&
                                    !(f.activation === "BONUS_ACTION"
                                      ? enc.bonus_action
                                      : enc.action)),
                              ),
                          )}
                        </article>
                      ))}
                  </>
                )}
                <h3>На сцене</h3>
                {Object.values(s.npcs).map((n) => (
                  <article key={n.id}>
                    <strong>{n.name}</strong>
                    <p>
                      {n.status} · позиция {n.position}
                    </p>
                    {!enc ? (
                      <>
                        {button(`Поговорить: ${n.name}`, {
                          type: "dialogue",
                          target: n.id,
                        })}
                        {button(`Убедить: ${n.name}`, {
                          type: "check",
                          purpose: "persuade",
                          target: n.id,
                          ability: "charisma",
                          skill: "persuasion",
                        })}
                      </>
                    ) : (
                      n.hostile &&
                      Object.entries(hero?.attacks || {}).map(([id, w]) =>
                        button(
                          `Атаковать ${n.name}: ${w.name}`,
                          { type: "attack", target: n.id, weapon: id },
                          blocked || !enc.action,
                        ),
                      )
                    )}
                    {enc &&
                      n.hostile &&
                      [
                        ["grapple", "Захватить"],
                        ["shove", "Сбить с ног"],
                        ["ready", "Подготовить атаку"],
                      ].map(([type, label]) =>
                        button(
                          `${label}: ${n.name}`,
                          { type, target: n.id },
                          blocked || !enc.action,
                        ),
                      )}
                  </article>
                ))}
                {enc &&
                  s.party
                    .filter((id) => id !== acting)
                    .map((id) =>
                      button(`Помочь: ${name(id)}`, {
                        type: "help",
                        target: id,
                      }),
                    )}
                <h3>Объекты</h3>
                {s.objects.map((o) => (
                  <article key={o.id}>
                    <h4>{o.name}</h4>
                    <p>{o.description}</p>
                    {button(`Открыть: ${o.name}`, {
                      type: "interact",
                      target: o.id,
                    })}
                    {button(`Вскрыть: ${o.name}`, {
                      type: "check",
                      purpose: "unlock",
                      target: o.id,
                    })}
                    {o.contents.map((x) =>
                      button(
                        `Взять: ${s.items[x.item_id]?.name || x.item_id} ×${x.quantity}`,
                        {
                          type: "take_item",
                          target: o.id,
                          item_id: x.item_id,
                          quantity: x.quantity,
                        },
                      ),
                    )}
                  </article>
                ))}
                {!enc && (
                  <details>
                    <summary>Расширить мир</summary>
                    <p>
                      Напиши запрос нового места в поле действия и нажми кнопку
                      ниже. Генерация использует модель из настроек.
                    </p>
                    <button
                      disabled={blocked || !text.trim() || !prefs.game.model}
                      onClick={() =>
                        void perform(
                          "actions",
                          { command: { type: "expand", topic: text } },
                          true,
                        )
                      }
                    >
                      Создать новое место
                    </button>
                  </details>
                )}
              </aside>
            </main>
          ) : tab === "Персонаж" ? (
            s.party.map((id) => sheet(s.characters[id]))
          ) : tab === "Инвентарь" ? (
            s.party.map((id) => {
              const a = s.characters[id];
              return (
                <section className="tt-panel" key={id}>
                  <h2>{a.name}</h2>
                  {a.inventory.map((entry, i) => {
                    const item = s.items[entry.item_id];
                    return (
                      <article key={`${entry.item_id}-${i}`}>
                        <h3>
                          {item?.name || entry.item_id} ×{entry.quantity}
                          {entry.equipped ? " · экипировано" : ""}
                        </h3>
                        <p>{item?.description}</p>
                        <p>
                          Вес {item?.weight} · ценность {item?.value}
                        </p>
                        {a.controller.controller === "PLAYER" && (
                          <>
                            {button(entry.equipped ? "Снять" : "Экипировать", {
                              type: entry.equipped ? "unequip" : "equip",
                              actor_id: id,
                              item_id: entry.item_id,
                            })}
                            {item?.type === "consumable" &&
                              s.party.map((target) =>
                                button(`Использовать на ${name(target)}`, {
                                  type: "use_item",
                                  actor_id: id,
                                  item_id: entry.item_id,
                                  target,
                                }),
                              )}
                            {button("Оставить один", {
                              type: "drop_item",
                              actor_id: id,
                              item_id: entry.item_id,
                              quantity: 1,
                            })}
                          </>
                        )}
                      </article>
                    );
                  })}
                </section>
              );
            })
          ) : tab === "Журнал" ? (
            <section className="tt-panel">
              <h2>Задания</h2>
              {Object.entries(s.quests).map(([id, q]) => (
                <article key={id}>
                  <h3>
                    {q.name} · {questNames[q.status]}
                  </h3>
                  <p>{q.description}</p>
                </article>
              ))}
              <h2>Известные сведения</h2>
              {Object.entries(s.knowledge).map(([id, k]) => (
                <p key={id}>{k}</p>
              ))}
            </section>
          ) : tab === "Партия" ? (
            <section className="tt-panel">
              <h2>Участники</h2>
              {s.party.map((id) => (
                <article key={id}>
                  <h3>{name(id)}</h3>
                  <p>
                    {s.characters[id].hp}/{s.characters[id].max_hp} HP ·{" "}
                    {controlNames[s.characters[id].controller.controller]}
                  </p>
                  {button(
                    `Управлять: ${name(id)}`,
                    { type: "select_actor", target: id },
                    busy ||
                      !!pending ||
                      !!enc ||
                      s.characters[id].controller.controller !== "PLAYER",
                  )}
                </article>
              ))}
            </section>
          ) : tab === "Карта" ? (
            <section className="tt-panel">
              <h2>Известные места</h2>
              <div className="tt-form-grid">
                {s.locations.map((l) => (
                  <article key={l.id}>
                    <h3>
                      {l.name}
                      {l.id === s.location_id ? " · ты здесь" : ""}
                    </h3>
                    <p>{l.description || "Ещё не исследовано"}</p>
                    <p>
                      Переходы:{" "}
                      {l.connections
                        .map(
                          (id) =>
                            s.locations.find((x) => x.id === id)?.name || id,
                        )
                        .join(", ") || "неизвестны"}
                    </p>
                    {s.exits.some((x) => x.id === l.id) &&
                      button(
                        `Перейти: ${l.name}`,
                        { type: "move", target: l.id },
                        blocked || !!enc,
                      )}
                  </article>
                ))}
              </div>
            </section>
          ) : tab === "Броски" ? (
            <section className="tt-panel">
              <h2>История бросков</h2>
              {game.history.flatMap((h) =>
                h.events
                  .filter((e) => e.roll)
                  .map((e, i) => (
                    <p key={`${h.revision}-${i}`}>
                      #{h.revision} · {name(e.roll!.actor)} ·{" "}
                      {purposes[e.roll!.purpose] || e.roll!.purpose}:{" "}
                      {e.roll!.expression} [{e.roll!.raw.join(", ")}]{" "}
                      {signed(e.roll!.modifier)} ={" "}
                      <strong>{e.roll!.total}</strong>
                    </p>
                  )),
              )}
            </section>
          ) : (
            <section className="tt-panel">
              <h2>Диагностика DM</h2>
              <p>
                Механика, проверки и изменения мира выполняются сервером. LLM
                интерпретирует намерение и описывает утверждённый результат.
              </p>
              <button
                disabled={busy}
                onClick={() =>
                  void run(async () =>
                    setContext(
                      JSON.stringify(
                        await api(`/tabletop/games/${game.id}/context`),
                        null,
                        2,
                      ),
                    ),
                  )
                }
              >
                Показать публичный контекст
              </button>
              {context && <pre className="tt-json">{context}</pre>}
              <div className="tt-table-scroll">
                <table>
                  <thead>
                    <tr>
                      {[
                        "Этап",
                        "Модель",
                        "Статус",
                        "Вход",
                        "Выход",
                        "Кэш",
                        "USD",
                        "Секунды",
                      ].map((x) => (
                        <th key={x}>{x}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {game.usage.map((u, i) => (
                      <tr key={i}>
                        <td>{u.stage}</td>
                        <td>
                          {u.provider}/{u.model}
                        </td>
                        <td>{u.status}</td>
                        <td>{u.input_tokens ?? "—"}</td>
                        <td>{u.output_tokens ?? "—"}</td>
                        <td>{u.cached_tokens ?? "—"}</td>
                        <td>{u.cost ?? "—"}</td>
                        <td>{u.seconds}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
