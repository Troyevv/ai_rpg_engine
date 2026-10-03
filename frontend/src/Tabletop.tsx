import {
  HeroSummary,
  CombatHUD,
  RollCard,
  RollResult,
  CharacterSheet,
} from "./tabletop/GamePanels";
import { ActionImpact } from "./tabletop/ActionImpact";
import { CombatActions } from "./tabletop/CombatActions";
import { DMSettings } from "./tabletop/DMSettings";
import { LevelUp } from "./tabletop/LevelUp";
import { Spellbook } from "./tabletop/Spellbook";
import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Preferences } from "./types";
import { Wizard } from "./tabletop/Wizard";
import { signed, type Command, type Game } from "./tabletop/types";
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
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [tab, setTab] = useState("Игра"),
    [text, setText] = useState(""),
    [context, setContext] = useState(""),
    [mobileActions, setMobileActions] = useState(false),
    [campaignMenu, setCampaignMenu] = useState(false),
    [olderHistory, setOlderHistory] = useState(false);
  const [runtimeStage, setRuntimeStage] = useState("");
  const lock = useRef(false);
  const historyEnd = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (game?.state.pending || game?.state.choice || game?.state.reaction) {
      setTab("Игра");
      setMobileActions(false);
      document
        .querySelector(".tt-roll-card, .tt-roll-prompt")
        ?.scrollIntoView({ block: "center", behavior: "smooth" });
    } else if (window.innerWidth >= 768 && historyEnd.current) {
      historyEnd.current.parentElement?.scrollTo({
        top: historyEnd.current.parentElement.scrollHeight,
      });
    }
  }, [game?.revision]);
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
      .catch((e) => active && setError(e.message))
      .finally(() => active && setLoading(false));
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
      const requestId = crypto.randomUUID();
      let active = true;
      setRuntimeStage("Отправка запроса");
      const labels: Record<string, string> = {
        waiting: "Ожидание обработки",
        validation: "Проверка запроса",
        interpretation: "DM разбирает намерение",
        rules: "Проверка правил действия",
        generation: "Создание контента",
        roll: "Разрешение серверного броска",
        saving: "Сохранение результата",
        narration: "DM описывает результат",
        complete: "Готово",
        failed: "Обработка завершилась ошибкой",
      };
      const poll = setInterval(() => {
        void api<{ stage: string }>(
          `/tabletop/games/${game.id}/progress/${requestId}`,
        )
          .then((r) => {
            if (active) setRuntimeStage(labels[r.stage] || r.stage);
          })
          .catch(() => {});
      }, 500);
      try {
        setGame(
          await api<Game>(`/tabletop/games/${game.id}/${path}`, {
            ...payload,
            revision: game.revision,
            request_id: requestId,
            ...(model
              ? { config: prefs.game, api_key: apiKey || undefined }
              : {}),
          }),
        );
        setText("");
        setContext("");
        setMobileActions(false);
      } catch (e) {
        setGame(await api<Game>(`/tabletop/games/${game.id}`));
        throw e;
      } finally {
        active = false;
        clearInterval(poll);
        setRuntimeStage("");
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
  return (
    <div className={`tt-shell ${s && !creating ? "tt-playing" : ""}`}>
      <header className="tt-header">
        <button onClick={onBack} disabled={busy}>
          Истории
        </button>
        <div>
          <strong>{s && !creating ? s.location : "Настольная RPG"}</strong>
          <small>{game?.state.ruleset.name || "D20 Fantasy"}</small>
        </div>
        <button
          disabled={loading}
          onClick={() => (s ? setTab("Настройки") : onSettings())}
        >
          Настройки DM
        </button>
      </header>
      <button
        className="tt-campaign-toggle"
        aria-expanded={campaignMenu}
        onClick={() => setCampaignMenu(!campaignMenu)}
      >
        Кампании
      </button>
      <div className={`tt-toolbar ${campaignMenu ? "is-open" : ""}`}>
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
      {loading ? (
        <main className="tt-panel" role="status">
          Загружаю кампанию…
        </main>
      ) : creating ? (
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
          <section className="tt-campaign-bar">
            <h1>{s.campaign}</h1>
            <p>
              {s.location} · {modeNames[s.mode]} ·{" "}
              {Math.floor(s.game_time / 60)} мин.
            </p>
            {hero && (
              <LevelUp
                key={`${hero.id}-${hero.level}`}
                hero={hero}
                gameId={game.id}
                blocked={blocked || !!enc}
                act={act}
              />
            )}
            <CombatHUD state={s} />
          </section>
          <button
            className="tt-mobile-actions"
            aria-expanded={mobileActions}
            onClick={() => {
              setTab("Игра");
              setMobileActions(!mobileActions);
            }}
          >
            {mobileActions ? "Вернуться к истории" : "Действия"}
          </button>
          <nav className="tt-tabs" aria-label="Разделы кампании">
            {[
              "Игра",
              "Персонаж",
              "Инвентарь",
              "Журнал",
              "Партия",
              "Карта",
              ...(hero?.spells?.length ? ["Заклинания"] : []),
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
          {tab === "Настройки" ? (
            <DMSettings
              key={game.revision}
              value={s.dm_settings}
              busy={busy}
              save={(settings) => void perform("settings", { settings }, false)}
              provider={onSettings}
            />
          ) : tab === "Заклинания" && hero ? (
            <Spellbook hero={hero} state={s} blocked={blocked} act={act} />
          ) : tab === "Игра" ? (
            <main
              className={`tt-game-grid ${mobileActions && !pending && !s.choice && !s.reaction ? "tt-show-actions" : ""}`}
            >
              <aside className="tt-panel tt-party-summary">
                <span className="tt-eyebrow">Партия</span>
                {s.party.map((id) => (
                  <button
                    className="tt-member"
                    key={id}
                    onClick={() => setTab("Партия")}
                  >
                    <strong>{name(id)}</strong>
                    <span>
                      {s.characters[id].hp}/{s.characters[id].max_hp} HP ·
                      уровень {s.characters[id].level}
                    </span>
                    <progress
                      value={s.characters[id].hp}
                      max={s.characters[id].max_hp}
                    />
                  </button>
                ))}
                <h3>Текущие задания</h3>
                {Object.values(s.quests)
                  .filter((q) => q.status === "active")
                  .map((q) => (
                    <p key={q.name}>{q.name}</p>
                  ))}
                <button onClick={() => setTab("Журнал")}>Открыть журнал</button>
              </aside>
              <section className="tt-panel tt-story-panel">
                <h2>{s.location}</h2>
                <p>{s.scene}</p>
                <div className="tt-history">
                  {game.history.length > 3 && (
                    <button onClick={() => setOlderHistory(!olderHistory)}>
                      {olderHistory
                        ? "Скрыть ранние события"
                        : "Предыдущие события"}
                    </button>
                  )}
                  {(olderHistory ? game.history : game.history.slice(-3)).map(
                    (h) => (
                      <article key={h.revision}>
                        <div className="tt-player-text">{h.user_text}</div>
                        <div
                          className="tt-mechanics"
                          aria-label="События правил"
                        >
                          {h.events
                            .filter(
                              (e) =>
                                e.kind !== "opening" ||
                                !h.narrative?.includes(e.text),
                            )
                            .map((e, i) =>
                              e.roll ? (
                                <RollResult
                                  key={i}
                                  event={e}
                                  name={name(e.roll.actor)}
                                />
                              ) : (
                                <div key={i}>
                                  <p>{e.text}</p>
                                  {e.hp_before !== undefined && (
                                    <div className="tt-hp-event">
                                      <strong>
                                        {name(e.target || "")}: {e.hp_before} →{" "}
                                        {e.hp_after} HP
                                      </strong>
                                      <progress
                                        aria-label="Здоровье после действия"
                                        value={e.hp_after}
                                        max={
                                          e.maximum ||
                                          Math.max(
                                            e.hp_before,
                                            e.hp_after || 0,
                                            1,
                                          )
                                        }
                                      />
                                    </div>
                                  )}
                                </div>
                              ),
                            )}
                        </div>
                        {h.narrative && (
                          <p
                            className="tt-narration"
                            style={{ whiteSpace: "pre-wrap" }}
                          >
                            {h.narrative}
                          </p>
                        )}
                      </article>
                    ),
                  )}
                  <div ref={historyEnd} />
                </div>
                {enc && hero && !pending && !s.choice && !s.reaction && (
                  <CombatActions
                    state={s}
                    hero={hero}
                    blocked={blocked}
                    act={act}
                  />
                )}
                {!enc &&
                  s.checks?.map((c) => (
                    <button
                      key={c.id}
                      disabled={blocked}
                      title={c.description}
                      onClick={() =>
                        act({ type: c.save ? "save" : "check", check_id: c.id })
                      }
                    >
                      {c.name}
                    </button>
                  ))}
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
                  <RollCard
                    pending={pending}
                    name={name(pending.actor)}
                    busy={busy}
                    roll={() =>
                      void perform("roll", { pending_id: pending.id })
                    }
                  />
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
                {busy && runtimeStage && (
                  <p role="status" aria-live="polite">
                    {runtimeStage}
                  </p>
                )}
                <form
                  className="tt-compose"
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
                  {s.dm_settings.hints && (
                    <small>
                      {pending
                        ? "Сначала заверши бросок выше."
                        : "Опиши намерение своими словами или выбери действие."}
                    </small>
                  )}
                  <button
                    className="tt-primary"
                    disabled={blocked || !text.trim()}
                  >
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
              <aside className="tt-panel tt-action-panel">
                {hero && <HeroSummary hero={hero} />}
                {!(s.ruleset.id === "d20-fantasy-v2" && enc) && (
                  <>
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
                          {button("Долгий отдых", {
                            type: "rest",
                            rest: "long",
                          })}
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
                              blocked ||
                                (!enc.action && !enc.attacks_remaining),
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
                        <p>Опиши место, которое хочешь исследовать.</p>
                        <label>
                          Новое место
                          <textarea
                            value={text}
                            onChange={(e) => setText(e.target.value)}
                            placeholder="Обсерватория за городом…"
                          />
                        </label>
                        <button
                          disabled={
                            blocked || !text.trim() || !prefs.game.model
                          }
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
                  </>
                )}
              </aside>
            </main>
          ) : tab === "Персонаж" ? (
            s.party.map((id) => (
              <CharacterSheet key={id} hero={s.characters[id]} open={setTab} />
            ))
          ) : tab === "Инвентарь" ? (
            s.party.map((id) => {
              const a = s.characters[id];
              return (
                <section className="tt-panel" key={id}>
                  <h2>{a.name}</h2>
                  <p>
                    Золото: {a.gold || 0} · Вес:{" "}
                    {a.inventory.reduce(
                      (n, e) =>
                        n + (s.items[e.item_id]?.weight || 0) * e.quantity,
                      0,
                    )}{" "}
                    · КД {a.armor_class}
                  </p>
                  {a.equipment_bonuses?.stealth_disadvantage ? (
                    <p>Тяжёлая броня: помеха Скрытности</p>
                  ) : null}
                  <div className="tt-paper-doll" aria-label="Слоты экипировки">
                    {Object.entries(a.equipment_slots || {}).map(
                      ([slot, label]) => {
                        const entry = a.inventory.find(
                          (e) => e.equipped && e.slot === slot,
                        );
                        return (
                          <div key={slot} style={{ gridArea: slot }}>
                            <small>{label}</small>
                            <strong>
                              {entry ? s.items[entry.item_id]?.name : "Пусто"}
                            </strong>
                          </div>
                        );
                      },
                    )}
                  </div>
                  <div className="tt-inventory-grid">
                    {a.inventory.map((entry, i) => {
                      const item = s.items[entry.item_id];
                      return (
                        <article key={`${entry.item_id}-${i}`}>
                          <h3>
                            {item?.name || entry.item_id} ×{entry.quantity}
                            {entry.equipped ? " · экипировано" : ""}
                          </h3>
                          <details>
                            <summary>Осмотреть и действия</summary>
                            <p>{item?.description}</p>
                            <p>
                              Вес {item?.weight} · ценность {item?.value}
                            </p>
                            {a.controller.controller === "PLAYER" && (
                              <>
                                {item.slots?.length > 0 && (
                                  <ActionImpact
                                    gameId={game.id}
                                    command={{
                                      type: entry.equipped
                                        ? "unequip"
                                        : "equip",
                                      actor_id: id,
                                      item_id: entry.item_id,
                                    }}
                                  />
                                )}
                                {(!a.equipment_slots ||
                                  !Object.keys(a.equipment_slots).length ||
                                  item.slots?.length > 0) &&
                                  button(
                                    entry.equipped ? "Снять" : "Экипировать",
                                    {
                                      type: entry.equipped
                                        ? "unequip"
                                        : "equip",
                                      actor_id: id,
                                      item_id: entry.item_id,
                                      slot: entry.equipped
                                        ? entry.slot
                                        : undefined,
                                    },
                                  )}
                                {item?.type === "consumable" &&
                                  s.party.map((target) =>
                                    button(`Использовать на ${name(target)}`, {
                                      type: "use_item",
                                      actor_id: id,
                                      item_id: entry.item_id,
                                      slot: entry.equipped
                                        ? entry.slot
                                        : undefined,
                                      target,
                                    }),
                                  )}
                                {s.party
                                  .filter((target) => target !== id)
                                  .map((target) =>
                                    button(`Передать: ${name(target)}`, {
                                      type: "transfer_item",
                                      actor_id: id,
                                      item_id: entry.item_id,
                                      slot: entry.equipped
                                        ? entry.slot
                                        : undefined,
                                      target,
                                      quantity: 1,
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
                          </details>
                        </article>
                      );
                    })}
                  </div>
                </section>
              );
            })
          ) : tab === "Журнал" ? (
            <section className="tt-panel">
              {s.initial_conflict && (
                <>
                  <h2>История кампании</h2>
                  <p>{s.initial_conflict}</p>
                </>
              )}
              {s.plot_hooks?.length > 0 && (
                <>
                  <h2>Зацепки</h2>
                  {s.plot_hooks.map((hook, i) => (
                    <p key={i}>{hook}</p>
                  ))}
                </>
              )}
              <h2>Задания</h2>
              {Object.entries(s.quests).map(([id, q]) => (
                <article key={id}>
                  <h3>
                    {q.name} · {questNames[q.status]}
                  </h3>
                  <p>{q.description}</p>
                </article>
              ))}
              {s.factions?.length > 0 && (
                <>
                  <h2>Знакомые фракции</h2>
                  {s.factions.map((f) => (
                    <article key={f.id}>
                      <h3>
                        {f.name} · репутация {signed(f.reputation)}
                      </h3>
                      <p>{f.description}</p>
                      <p>{f.public_goal}</p>
                    </article>
                  ))}
                </>
              )}
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
                    <RollResult
                      key={`${h.revision}-${i}`}
                      event={e}
                      name={name(e.roll!.actor)}
                    />
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
