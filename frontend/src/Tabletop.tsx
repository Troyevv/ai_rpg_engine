import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Dice5,
  Settings2,
  Shield,
  Swords,
  ScrollText,
  Plus,
  RotateCcw,
} from "lucide-react";
import { api } from "./api";
import type { Preferences } from "./types";
import "./styles/tabletop.css";

type Command = {
  type: string;
  target?: string;
  ability?: string;
  skill?: string;
  distance?: number;
  rest?: string;
};
type Sheet = {
  id: string;
  name: string;
  character_class: string;
  species: string;
  level: number;
  hp: number;
  max_hp: number;
  armor_class: number;
  speed: number;
  position: number;
  abilities: Record<string, number>;
  modifiers: Record<string, number>;
  skill_modifiers: Record<string, number>;
  save_modifiers: Record<string, number>;
  attack_modifiers: Record<string, number>;
  attacks: Record<
    string,
    { name: string; ability: string; die: number; reach: number }
  >;
  skill_proficiencies: string[];
  save_proficiencies: string[];
  inventory: string[];
  features: string[];
  spells: string[];
  resources: Record<string, number>;
  conditions: string[];
  biography: string;
};
type Roll = {
  expression: string;
  raw: number[];
  modifier: number;
  total: number;
  purpose: string;
  actor: string;
  advantage: number;
};
type Entry = {
  revision: number;
  user_text: string;
  narrative: string;
  events: { text: string; roll?: Roll }[];
};
type Game = {
  id: string;
  revision: number;
  state: {
    campaign: string;
    ruleset: { name: string };
    world: { name: string; description: string };
    location: string;
    mode: string;
    controlled_actor: string;
    characters: Record<string, Sheet>;
    party: string[];
    npcs: Record<
      string,
      { id: string; name: string; position: number; status: string }
    >;
    knowledge: Record<string, string>;
    quests: Record<string, string>;
    game_time: number;
    pending: null | {
      id: string;
      purpose: string;
      expression: string;
      modifier: number;
      critical: boolean;
      ability: string;
      skill: string;
    };
    encounter: null | {
      round: number;
      current_actor: string;
      order: string[];
      initiative: Record<string, number>;
      action: boolean;
      bonus_action: boolean;
      reaction: boolean;
      movement: number;
    };
  };
  history: Entry[];
  usage: {
    stage: string;
    status: string;
    input_tokens: number | null;
    output_tokens: number | null;
    cached_tokens: number | null;
    cost: string | null;
    seconds: number;
  }[];
};
type Item = { id: string; name: string; revision: number };
const abilities: Record<string, string> = {
  strength: "Сила",
  dexterity: "Ловкость",
  constitution: "Телосложение",
  intelligence: "Интеллект",
  wisdom: "Мудрость",
  charisma: "Харизма",
};
const purposes: Record<string, string> = {
  check: "Проверка",
  save: "Спасбросок",
  initiative: "Инициатива",
  attack: "Атака",
  damage: "Урон",
  death: "Спасбросок от смерти",
};
const modes: Record<string, string> = {
  EXPLORATION: "Исследование",
  DIALOGUE: "Разговор",
  ENCOUNTER: "Бой",
  AWAITING_ROLL: "Ожидание броска",
};
const signed = (v: number) => (v >= 0 ? `+${v}` : String(v));
const requestId = () =>
  crypto.randomUUID?.() ||
  Array.from(crypto.getRandomValues(new Uint8Array(16)), (n) =>
    n.toString(16).padStart(2, "0"),
  ).join("");

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
  const [games, setGames] = useState<Item[]>([]);
  const [game, setGame] = useState<Game | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [text, setText] = useState("");
  const [tab, setTab] = useState("Игра");
  const [llm, setLlm] = useState(
    () => localStorage.getItem("tabletop-dm") === "true",
  );
  const [sheetId, setSheetId] = useState("hero");
  const lock = useRef(false);
  const generation = useRef(0);
  const bottom = useRef<HTMLDivElement>(null);
  const refreshList = () => api<Item[]>("/tabletop/games").then(setGames);
  useEffect(() => {
    let cancelled = false;
    api<Item[]>("/tabletop/games")
      .then((items) => {
        if (cancelled) return;
        setGames(items);
        const id = localStorage.getItem("tabletop-game");
        if (id && items.some((g) => g.id === id))
          api<Game>(`/tabletop/games/${id}`)
            .then((g) => {
              if (!cancelled) setGame(g);
            })
            .catch((e) => {
              if (!cancelled) setError(e.message);
            });
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
      generation.current++;
    };
  }, []);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [game?.revision, tab]);
  const open = async (id: string) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      const g = await api<Game>(`/tabletop/games/${id}`);
      setGame(g);
      setCreating(false);
      setTab("Игра");
      localStorage.setItem("tabletop-game", id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  const perform = async (path: string, payload: object) => {
    if (!game || lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    const gen = generation.current;
    try {
      const next = await api<Game>(`/tabletop/games/${game.id}/${path}`, {
        ...payload,
        revision: game.revision,
        request_id: requestId(),
        ...(llm ? { config: prefs.game, api_key: apiKey || undefined } : {}),
      });
      if (gen === generation.current) {
        setGame(next);
        setText("");
      }
    } catch (e) {
      if (gen === generation.current) {
        setError((e as Error).message);
        try {
          setGame(await api<Game>(`/tabletop/games/${game.id}`));
        } catch {
          /* retain visible snapshot */
        }
      }
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  const act = (command: Command) => void perform("actions", { command });
  const state = game?.state;
  const hero = state?.characters[state.controlled_actor];
  const pending = state?.pending;
  const encounter = state?.encounter;
  const blocked = busy || !!pending || (!!hero && hero.hp === 0);
  const name = (id: string) =>
    state?.characters[id]?.name || state?.npcs[id]?.name || id;
  const party = (
    <section className="tt-panel">
      <h2>
        <Shield size={17} /> Партия
      </h2>
      {state?.party.map((id) => {
        const a = state.characters[id];
        return (
          <button
            className="tt-member"
            key={id}
            onClick={() => {
              setSheetId(id);
              setTab("Персонаж");
            }}
          >
            <strong>
              {a.name} {id === state.controlled_actor ? "· ты" : ""}
            </strong>
            <span>
              {a.character_class} · уровень {a.level}
            </span>
            <progress max={a.max_hp} value={a.hp} />
            <span>
              {a.hp} / {a.max_hp} HP · AC {a.armor_class}
            </span>
            {a.conditions.length > 0 && (
              <small>{a.conditions.join(", ")}</small>
            )}
          </button>
        );
      })}
      <p className="tt-note">
        Спутники выбирают действия сами. Сейчас доступен воин 1-го уровня.
      </p>
    </section>
  );
  return (
    <div className="tt-shell">
      <header className="tt-header">
        <button
          onClick={onBack}
          disabled={busy}
          aria-label="Вернуться к историям"
        >
          <ArrowLeft size={18} />
          <span>Истории</span>
        </button>
        <div>
          <strong>Настольная RPG</strong>
          <small>D20 Basic · отдельная кампания</small>
        </div>
        <button onClick={onSettings} aria-label="Настройки DM">
          <Settings2 size={19} />
        </button>
      </header>
      <div className="tt-toolbar">
        <select
          aria-label="Кампания"
          value={creating ? "" : game?.id || ""}
          disabled={busy}
          onChange={(e) => e.target.value && void open(e.target.value)}
        >
          <option value="">Выбрать кампанию</option>
          {games.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
        <button disabled={busy} onClick={() => setCreating(true)}>
          <Plus size={16} /> Новая игра
        </button>
        <label className="tt-toggle">
          <input
            type="checkbox"
            checked={llm}
            onChange={(e) => {
              setLlm(e.target.checked);
              localStorage.setItem("tabletop-dm", String(e.target.checked));
            }}
          />{" "}
          LLM DM
        </label>
      </div>
      {error && (
        <div className="tt-error" role="alert">
          {error}
          <button onClick={() => setError("")}>Закрыть</button>
        </div>
      )}
      {creating ? (
        <Wizard
          busy={busy}
          cancel={() => setCreating(false)}
          create={async (options) => {
            if (lock.current) return;
            lock.current = true;
            setBusy(true);
            setError("");
            try {
              const g = await api<Game>("/tabletop/games", options);
              setGame(g);
              setCreating(false);
              setTab("Игра");
              localStorage.setItem("tabletop-game", g.id);
              await refreshList();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              lock.current = false;
              setBusy(false);
            }
          }}
        />
      ) : !state ? (
        <main className="tt-empty">
          <Dice5 size={48} />
          <h1>Приключение начинается с броска</h1>
          <p>
            Создай героя, исследуй старую заставу и проведи первый бой. Правила
            и кубики работают даже без модели.
          </p>
          <button className="tt-primary" onClick={() => setCreating(true)}>
            Создать настольную игру
          </button>
        </main>
      ) : (
        <>
          <nav className="tt-tabs" aria-label="Разделы настольной игры">
            {["Игра", "Персонаж", "Партия", "Журнал", "Мир"].map((t) => (
              <button
                key={t}
                aria-current={tab === t ? "page" : undefined}
                onClick={() => setTab(t)}
              >
                {t}
              </button>
            ))}
          </nav>
          <div className={`tt-layout ${tab === "Игра" ? "tt-playing" : ""}`}>
            <aside className="tt-party">{party}</aside>
            <main className="tt-main">
              {tab === "Игра" ? (
                <>
                  <div className="tt-scene">
                    <span className="tt-eyebrow">{modes[state.mode]}</span>
                    <h1>{state.campaign}</h1>
                    <p>
                      {state.location} · {Math.floor(state.game_time / 60)} мин.
                    </p>
                  </div>
                  {encounter && (
                    <section className="tt-encounter" aria-label="Очередь боя">
                      <h2>
                        <Swords size={18} /> Раунд {encounter.round} · ход:{" "}
                        {name(encounter.current_actor)}
                      </h2>
                      <p>
                        {hero?.name}: HP {hero?.hp}/{hero?.max_hp} · AC{" "}
                        {hero?.armor_class}
                      </p>
                      <div className="tt-order">
                        {encounter.order.map((id) => (
                          <span
                            className={
                              id === encounter.current_actor ? "active" : ""
                            }
                            key={id}
                          >
                            {name(id)} <b>{encounter.initiative[id]}</b>
                          </span>
                        ))}
                      </div>
                      <p>
                        Действие: {encounter.action ? "доступно" : "потрачено"}{" "}
                        · Перемещение: {encounter.movement} футов
                      </p>
                      <small>
                        Бонусные действия и реакции: механики следующего этапа.
                      </small>
                    </section>
                  )}
                  <div className="tt-story" aria-live="polite">
                    {game?.history.map((h) => (
                      <article key={h.revision}>
                        {h.user_text && (
                          <div className="tt-player-text">{h.user_text}</div>
                        )}
                        <p>
                          {h.narrative ||
                            h.events.map((e) => e.text).join("\n")}
                        </p>
                        {h.events
                          .filter((e) => e.roll)
                          .map((e, i) => (
                            <div className="tt-roll-result" key={i}>
                              <Dice5 size={16} />
                              <span>
                                {name(e.roll!.actor)} ·{" "}
                                {purposes[e.roll!.purpose]} · [
                                {e.roll!.raw.join(", ")}]{" "}
                                {signed(e.roll!.modifier)}
                              </span>
                              <strong>{e.roll!.total}</strong>
                            </div>
                          ))}
                      </article>
                    ))}
                    <div ref={bottom} />
                  </div>
                  {pending && (
                    <section className="tt-roll-card">
                      <Dice5 size={30} />
                      <div>
                        <span className="tt-eyebrow">Твой бросок</span>
                        <h2>{purposes[pending.purpose]}</h2>
                        <p>
                          {pending.expression} {signed(pending.modifier)}{" "}
                          {pending.critical ? "· критический урон" : ""}
                        </p>
                        {pending.purpose === "check" && (
                          <small>
                            {abilities[pending.ability]} ·{" "}
                            {pending.skill || "без навыка"} · сложность скрыта
                          </small>
                        )}
                      </div>
                      <button
                        className="tt-primary"
                        disabled={busy}
                        onClick={() =>
                          void perform("roll", { pending_id: pending.id })
                        }
                      >
                        {busy ? "Бросаем…" : "Бросить кубик"}
                      </button>
                    </section>
                  )}
                  <section className="tt-actions" aria-label="Игровые действия">
                    {!encounter ? (
                      <>
                        <button
                          disabled={blocked}
                          onClick={() => act({ type: "look" })}
                        >
                          Осмотреться
                        </button>
                        <button
                          disabled={blocked}
                          onClick={() =>
                            act({
                              type: "check",
                              target: "chest",
                              ability: "wisdom",
                              skill: "perception",
                            })
                          }
                        >
                          Осмотреть сундук
                        </button>
                        <button
                          disabled={blocked}
                          onClick={() => act({ type: "start_encounter" })}
                        >
                          Начать бой
                        </button>
                        <button
                          disabled={blocked}
                          onClick={() => act({ type: "rest", rest: "short" })}
                        >
                          Короткий отдых
                        </button>
                        <button
                          disabled={blocked}
                          onClick={() => act({ type: "rest", rest: "long" })}
                        >
                          Долгий отдых
                        </button>
                      </>
                    ) : (
                      <>
                        {Object.values(state.npcs)
                          .filter((n) => n.status === "готов к бою")
                          .map((n) => (
                            <button
                              key={n.id}
                              disabled={blocked || !encounter.action}
                              onClick={() =>
                                act({ type: "attack", target: n.id })
                              }
                            >
                              Атаковать: {n.name}
                            </button>
                          ))}
                        <button
                          disabled={blocked || !encounter.action}
                          onClick={() => act({ type: "dodge" })}
                        >
                          Уклонение
                        </button>
                        <button
                          disabled={blocked || !encounter.action}
                          onClick={() => act({ type: "dash" })}
                        >
                          Рывок
                        </button>
                        <button
                          disabled={blocked || encounter.movement < 5}
                          onClick={() => act({ type: "move", distance: 5 })}
                        >
                          Вперёд 5 фт
                        </button>
                        <button
                          disabled={blocked || encounter.movement < 5}
                          onClick={() => act({ type: "move", distance: -5 })}
                        >
                          Назад 5 фт
                        </button>
                        <button
                          disabled={blocked}
                          onClick={() => act({ type: "end_turn" })}
                        >
                          Закончить ход
                        </button>
                      </>
                    )}
                  </section>
                  <form
                    className="tt-compose"
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (text.trim()) void perform("actions", { text });
                    }}
                  >
                    <label htmlFor="tt-action">Твоё действие</label>
                    <textarea
                      id="tt-action"
                      value={text}
                      disabled={blocked}
                      onChange={(e) => setText(e.target.value)}
                      maxLength={4000}
                      placeholder={
                        llm
                          ? "Что ты делаешь или говоришь?"
                          : "Например: осмотреть сундук"
                      }
                    />
                    <div>
                      <small>
                        {llm
                          ? `DM: ${prefs.game.model || "выбери модель в настройках"}`
                          : "Без LLM: кнопки и точные команды"}
                      </small>
                      <button
                        className="tt-primary"
                        disabled={blocked || !text.trim()}
                      >
                        {busy ? "Обработка…" : "Сделать ход"}
                      </button>
                    </div>
                  </form>
                  <button
                    className="tt-rollback"
                    disabled={busy || !game?.history.length}
                    onClick={() => {
                      if (
                        window.confirm(
                          "Вернуть состояние до последнего действия?",
                        )
                      )
                        void perform("rollback", {});
                    }}
                  >
                    <RotateCcw size={14} /> Откатить действие
                  </button>
                </>
              ) : tab === "Персонаж" ? (
                <CharacterSheet sheet={state.characters[sheetId] || hero!} />
              ) : tab === "Партия" ? (
                party
              ) : tab === "Мир" ? (
                <section className="tt-panel">
                  <h1>{state.world.name}</h1>
                  <p>{state.world.description}</p>
                  <h2>Задания</h2>
                  {Object.values(state.quests).map((v, i) => (
                    <p key={i}>{v}</p>
                  ))}
                  <h2>Известное герою</h2>
                  {Object.values(state.knowledge).length ? (
                    Object.values(state.knowledge).map((v, i) => (
                      <p key={i}>{v}</p>
                    ))
                  ) : (
                    <p className="tt-note">Пока ничего не обнаружено.</p>
                  )}
                </section>
              ) : (
                <section className="tt-panel">
                  <h1>
                    <ScrollText size={22} /> Журнал и расходы
                  </h1>
                  {game?.history.map((h) => (
                    <details key={h.revision}>
                      <summary>
                        Действие {h.revision} · {h.user_text || "Начало"}
                      </summary>
                      {h.events.map((e, i) => (
                        <p key={i}>{e.text}</p>
                      ))}
                    </details>
                  ))}
                  <h2>Вызовы DM</h2>
                  {!game?.usage.length && <p>Вызовов LLM не было.</p>}
                  {game?.usage.map((u, i) => (
                    <p key={i}>
                      {u.stage} · {u.status} · {u.seconds} с<br />
                      Вход: {u.input_tokens ?? "—"} · выход:{" "}
                      {u.output_tokens ?? "—"} · кеш: {u.cached_tokens ?? "—"} ·
                      ${u.cost ?? "неизвестно"}
                    </p>
                  ))}
                </section>
              )}
            </main>
            <aside className="tt-stats">
              <section className="tt-panel">
                <span className="tt-eyebrow">Твой герой</span>
                <h2>{hero?.name}</h2>
                <div className="tt-stat-grid">
                  <div>
                    <strong>
                      {hero?.hp}/{hero?.max_hp}
                    </strong>
                    <small>HP</small>
                  </div>
                  <div>
                    <strong>{hero?.armor_class}</strong>
                    <small>AC</small>
                  </div>
                </div>
                <button
                  onClick={() => {
                    setSheetId(state.controlled_actor);
                    setTab("Персонаж");
                  }}
                >
                  Открыть лист персонажа
                </button>
                <h3>На сцене</h3>
                {Object.values(state.npcs).map((n) => (
                  <p key={n.id}>
                    {n.name}
                    <br />
                    <small>
                      {n.status} · позиция {n.position} фт
                    </small>
                  </p>
                ))}
                <p className="tt-note">Твоя позиция: {hero?.position} фт</p>
              </section>
            </aside>
          </div>
        </>
      )}
    </div>
  );
}

function CharacterSheet({ sheet: a }: { sheet: Sheet }) {
  const [section, setSection] = useState("Обзор");
  return (
    <section className="tt-panel tt-sheet">
      <span className="tt-eyebrow">Лист персонажа</span>
      <h1>{a.name}</h1>
      <p>
        {a.species} · {a.character_class} · уровень {a.level}
      </p>
      <nav className="tt-sheet-tabs">
        {[
          "Обзор",
          "Навыки",
          "Спасброски",
          "Бой",
          "Инвентарь",
          "Особенности",
          "Заклинания",
          "Биография",
        ].map((s) => (
          <button
            key={s}
            aria-current={section === s ? "page" : undefined}
            onClick={() => setSection(s)}
          >
            {s}
          </button>
        ))}
      </nav>
      {section === "Обзор" ? (
        <>
          <div className="tt-stat-grid">
            {Object.entries(a.abilities).map(([key, v]) => (
              <div key={key}>
                <small>{abilities[key]}</small>
                <strong>{v}</strong>
                <span>{signed(a.modifiers[key])}</span>
              </div>
            ))}
          </div>
          <p>
            HP {a.hp}/{a.max_hp} · AC {a.armor_class} · скорость {a.speed} фт
          </p>
          <p>Состояния: {a.conditions.join(", ") || "нет"}</p>
        </>
      ) : section === "Навыки" ? (
        <div>
          {Object.entries(a.skill_modifiers).map(([key, value]) => (
            <p key={key}>
              {(
                {
                  athletics: "Атлетика",
                  stealth: "Скрытность",
                  perception: "Внимательность",
                  persuasion: "Убеждение",
                } as Record<string, string>
              )[key] || key}
              : <strong>{signed(value)}</strong>
              {a.skill_proficiencies.includes(key) ? " · владение" : ""}
            </p>
          ))}
        </div>
      ) : section === "Спасброски" ? (
        <div>
          {Object.entries(a.save_modifiers).map(([key, value]) => (
            <p key={key}>
              {abilities[key]}: <strong>{signed(value)}</strong>
              {a.save_proficiencies.includes(key) ? " · владение" : ""}
            </p>
          ))}
        </div>
      ) : section === "Бой" ? (
        <>
          {Object.entries(a.attacks).map(([key, attack]) => (
            <p key={key}>
              {attack.name} · атака {signed(a.attack_modifiers[key])} · 1d
              {attack.die} {signed(a.modifiers[attack.ability])} урона ·
              досягаемость {attack.reach} фт
            </p>
          ))}
          <p>
            Основное действие и перемещение обновляются в начале хода. Для атаки
            и урона броски выполняются отдельно.
          </p>
        </>
      ) : section === "Инвентарь" ? (
        <ul>
          {a.inventory.map((v) => (
            <li key={v}>{v}</li>
          ))}
        </ul>
      ) : section === "Особенности" ? (
        <>
          <p>{a.features.join(", ") || "Особенностей пока нет."}</p>
          <p>
            Ресурсы:{" "}
            {Object.entries(a.resources)
              .map(([k, v]) => `${k}: ${v}`)
              .join(", ")}
          </p>
        </>
      ) : section === "Заклинания" ? (
        <p>
          {a.spells.join(", ") ||
            "У этого персонажа нет заклинаний. Магия появится на следующем этапе."}
        </p>
      ) : (
        <p>{a.biography || "Биография не заполнена."}</p>
      )}
    </section>
  );
}

function Wizard({
  create,
  cancel,
  busy,
}: {
  create: (options: object) => Promise<void>;
  cancel: () => void;
  busy: boolean;
}) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState("Тайна заставы");
  const [hero, setHero] = useState("Искатель");
  const [bio, setBio] = useState("");
  const [companion, setCompanion] = useState(true);
  const [settingName, setSettingName] = useState("Старая застава");
  const [description, setDescription] = useState(
    "На границе леса стоит заброшенная застава. Ворота приоткрыты; во дворе виден старый сундук.",
  );
  const steps = [
    "Правила",
    "Мир",
    "Кампания",
    "Персонаж",
    "Партия",
    "DM",
    "Старт",
  ];
  return (
    <main className="tt-wizard tt-panel">
      <span className="tt-eyebrow">Новая настольная игра · {step + 1} / 7</span>
      <h1>{steps[step]}</h1>
      <div className="tt-steps">
        {steps.map((s, i) => (
          <span key={s} className={i === step ? "active" : ""}>
            {i + 1}. {s}
          </span>
        ))}
      </div>
      {step === 0 ? (
        <>
          <h2>D20 Basic</h2>
          <p>
            D&D-подобная основа: характеристики, проверки, инициатива, атаки и
            урон, критические попадания, уклонение, отдых.
          </p>
          <p className="tt-note">
            Это ограниченный ruleset, не полная редакция D&D. Пока без магии,
            реакций атак и развития по уровням. Короткий отдых восстанавливает
            фиксированное здоровье за кость здоровья.
          </p>
        </>
      ) : step === 1 ? (
        <>
          <label>
            Название мира
            <input
              value={settingName}
              maxLength={120}
              onChange={(e) => setSettingName(e.target.value)}
            />
          </label>
          <label>
            Описание
            <textarea
              value={description}
              maxLength={6000}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <p className="tt-note">
            Первый сценарий: двор, сундук и гоблин. Редактируется описание;
            генератор географии появится позднее.
          </p>
        </>
      ) : step === 2 ? (
        <label>
          Название кампании
          <input
            value={name}
            maxLength={120}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
      ) : step === 3 ? (
        <>
          <label>
            Имя героя
            <input
              value={hero}
              maxLength={120}
              onChange={(e) => setHero(e.target.value)}
            />
          </label>
          <p>Человек · воин · уровень 1 · HP 12 · AC 16</p>
          <label>
            Биография
            <textarea
              value={bio}
              maxLength={3000}
              onChange={(e) => setBio(e.target.value)}
            />
          </label>
        </>
      ) : step === 4 ? (
        <>
          <label className="tt-toggle">
            <input
              type="checkbox"
              checked={companion}
              onChange={(e) => setCompanion(e.target.checked)}
            />{" "}
            Взять Терона в партию
          </label>
          <p>
            Спутником управляет игровой AI: он выбирает цель, подходит и
            атакует.
          </p>
        </>
      ) : step === 5 ? (
        <>
          <h2>Механика работает без модели</h2>
          <p>
            В игре включи «LLM DM» для свободных действий и описания
            результатов. Модель, режим Thinking и ключ берутся из общих настроек
            игры.
          </p>
          <p>
            Каждый бросок героя ждёт твоего нажатия. Сложность проверок и
            секреты скрыты.
          </p>
        </>
      ) : (
        <>
          <h2>{name}</h2>
          <p>
            {hero} отправляется в мир «{settingName}»{" "}
            {companion ? "вместе с Тероном" : "в одиночку"}.
          </p>
          <p>Начни с осмотра сундука, затем проведи первый бой.</p>
        </>
      )}
      <footer>
        <button
          disabled={busy}
          onClick={step ? () => setStep(step - 1) : cancel}
        >
          {step ? "Назад" : "Отмена"}
        </button>
        <button
          className="tt-primary"
          disabled={busy || !name.trim() || !hero.trim() || !settingName.trim()}
          onClick={() =>
            step < 6
              ? setStep(step + 1)
              : void create({
                  name,
                  character_name: hero,
                  biography: bio,
                  companion,
                  setting: { id: requestId(), name: settingName, description },
                })
          }
        >
          {busy ? "Создаём…" : step < 6 ? "Далее" : "Начать приключение"}
        </button>
      </footer>
    </main>
  );
}
