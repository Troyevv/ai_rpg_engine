import { formatDateLabel } from "./gameDate";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import {
  Phone as PhoneIcon,
  MessageCircle,
  ContactRound,
  X,
} from "lucide-react";
import { api } from "./api";
import type { Save } from "./types";
import { CharacterAvatar, type PortraitSubject } from "./Portrait";
import "./styles/phone.css";

type Contact = {
  id: string;
  label: string;
  address: string;
  blocked: boolean;
  available: boolean;
  subject: PortraitSubject;
};
type Conversation = {
  id: string;
  title: string;
  group: boolean;
  contact_id: string | null;
  active: boolean;
  participants: PortraitSubject[];
};
type Event = {
  id: string;
  channel: "TEXT_MESSAGE" | "VOICE_CALL";
  conversation_id: string | null;
  world_time: number;
  time_label: string;
  status: string;
  read_count: number | null;
  recipient_count: number | null;
  outgoing: boolean;
  unread: boolean;
  content: string | null;
  label: string;
  subject: PortraitSubject;
  destination: string;
};
export type PhoneState = {
  actor_id: string;
  capabilities: { text_message: boolean; voice_call: boolean };
  contacts: Contact[];
  conversations: Conversation[];
  events: Event[];
  focus: "physical" | "call";
  emergency: { service: string; number: string | null }[];
};
const status: Record<string, string> = {
  sent: "Отправляется",
  delivered: "Доставлено",
  ringing: "Вызов",
  answered: "Разговор",
  declined: "Отклонён",
  missed: "Пропущен",
  ended: "Завершён",
};
const services: Record<string, string> = {
  medical: "Скорая помощь",
  police: "Полиция",
  fire: "Пожарная служба",
};

export function Phone({
  save,
  disabled,
  onCommit,
}: {
  save: Save;
  disabled: boolean;
  onCommit: (save: Save) => void;
}) {
  const phone = save.state.phone;
  const ownerKey = `${save.id}:${phone?.actor_id}`;
  const [owner, setOwner] = useState(ownerKey);
  const trigger = useRef<HTMLButtonElement>(null);
  const [dock, setDock] = useState(110);
  useEffect(() => {
    const composer = trigger.current?.closest(".composer");
    if (!composer) return;
    const observer = new ResizeObserver(() =>
      setDock(Math.ceil(composer.getBoundingClientRect().height) + 8),
    );
    observer.observe(composer);
    return () => observer.disconnect();
  }, [ownerKey]);
  const screen = useRef<HTMLDivElement>(null);
  const drafts = useRef<Record<string, string>>({});

  useEffect(()=>{const close=()=>setOpen(false);window.addEventListener("save-workspace-opened",close);return()=>window.removeEventListener("save-workspace-opened",close)},[]);
  const [open, setOpen] = useState(false),
    [tab, setTab] = useState("contacts");
  const [conversation, setConversation] = useState<string | null>(null),
    [contact, setContact] = useState<string | null>(null);
  const [text, setText] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [editContact, setEditContact] = useState<string | null>(null),
    [contactKind, setContactKind] = useState("person");
  const [label, setLabel] = useState(""),
    [address, setAddress] = useState("");
  const [adding, setAdding] = useState(false),
    [grouping, setGrouping] = useState(false);
  const [groupMembers, setGroupMembers] = useState<string[]>([]),
    [groupName, setGroupName] = useState("");
  const messageKey = `${save.id}:${phone?.actor_id}:${conversation || contact || ""}`;
  useEffect(() => {
    setText(drafts.current[messageKey] || "");
  }, [messageKey]);
  const close = () => {
    setOpen(false);
    trigger.current?.focus();
  };
  useEffect(() => {
    if (!open) return;
    screen.current?.focus();
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
      }
    };
    const modal = new MutationObserver(() => {
      if (document.querySelector('[role="dialog"]')) setOpen(false);
    });
    modal.observe(document.body, { childList: true, subtree: true });
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("keydown", escape);
      modal.disconnect();
    };
  }, [open]);
  useEffect(() => {
    setOwner(ownerKey);
    setOpen(false);
    setContact(null);
    setConversation(null);
    setText("");
    setError("");
    setEditContact(null);
    setAdding(false);
    setTab("contacts");
    setLabel("");
    setAddress("");
    setContactKind("person");
    setGrouping(false);
    setGroupMembers([]);
    setGroupName("");
  }, [save.id, phone?.actor_id]);
  if (!phone || owner !== ownerKey) return null;
  const locked = busy || disabled;
  const perform = async (command: Record<string, unknown>) => {
    if (locked) return;
    setBusy(true);
    setError("");
    try {
      const next = await api<Save>(`/saves/${save.id}/phone`, {
        revision: save.revision,
        command: { operation_id: crypto.randomUUID(), ...command },
      });
      onCommit(next);
      return next;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const call = phone.events.find(
    (e) =>
      e.channel === "VOICE_CALL" && ["ringing", "answered"].includes(e.status),
  );
  const unread = phone.events.filter((e) => e.unread).length;
  const selected = phone.conversations.find((c) => c.id === conversation);
  const target = phone.contacts.find((c) => c.id === contact);
  const openChat = async (c: Conversation) => {
    setConversation(c.id);
    setContact(null);
    setTab("messages");
    if (phone.events.some((e) => e.conversation_id === c.id && e.unread))
      await perform({ action: "read", conversation_id: c.id });
  };
  const send = async () => {
    const next = await perform({
      action: "send",
      content: text,
      ...(conversation
        ? { conversation_id: conversation }
        : { contact_id: contact }),
    });
    if (next) {
      drafts.current[messageKey] = "";
      setText("");
      const last = next.state.phone?.events
        .filter((e) => e.channel === "TEXT_MESSAGE" && e.outgoing)
        .at(-1);
      if (last?.conversation_id) {
        setConversation(last.conversation_id);
        setContact(null);
      }
    }
  };
  const avatar = (subject: PortraitSubject) => (
    <CharacterAvatar subject={subject} saveId={save.id} size={36} />
  );
  return (
    <div
      className="phone-affordance"
      style={{ "--phone-dock-bottom": `${dock}px` } as CSSProperties}
    >
      {call?.status === "answered" && (
        <label>
          Адресация действий
          <select
            aria-label="Адресация действий"
            value={phone.focus}
            disabled={locked}
            onChange={(e) =>
              void perform({ action: "focus", focus: e.target.value })
            }
          >
            <option value="call">Разговор по телефону</option>
            <option value="physical">Физическая сцена</option>
          </select>
        </label>
      )}
      <div
        className={`phone-device ${open ? "is-open" : ""} ${call?.status === "ringing" ? "is-ringing" : ""}`}
        data-testid="phone-device"
      >
        <button
          ref={trigger}
          className="phone-peek"
          aria-label={`Телефон${unread ? `, непрочитано: ${unread}` : ""}`}
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          <span className="phone-camera" />
          <PhoneIcon size={18} />
          <span>Телефон</span>
          {(unread > 0 || call) && (
            <span
              className="phone-led"
              aria-label={
                call ? "Входящий или активный звонок" : "Новые сообщения"
              }
            />
          )}
        </button>
        <div
          className="phone-screen"
          ref={screen}
          role="region"
          aria-label="Телефон персонажа"
          tabIndex={-1}
          inert={!open}
          aria-hidden={!open}
        >
          <header className="phone-top">
            <strong>
              {save.state.characters.find((c) => c.id === phone.actor_id)?.name}
            </strong>
            <button aria-label="Свернуть телефон" onClick={close}>
              <X size={18} />
            </button>
          </header>
          <p className="muted small">Внутриигровая связь</p>
          {error && <p role="alert">{error}</p>}
          {call && (
            <section className="phone-call" aria-label="Текущий звонок">
              {avatar(call.subject)}
              <strong>{call.label}</strong>
              <span>
                {status[call.status]} ·{" "}
                {call.outgoing ? "Исходящий" : "Входящий"}
              </span>
              {!call.outgoing && call.status === "ringing" ? (
                <div>
                  {[
                    ["answer", "Ответить"],
                    ["decline", "Отклонить"],
                    ["ignore", "Игнорировать"],
                  ].map(([action, title]) => (
                    <button
                      key={action}
                      disabled={locked}
                      onClick={() =>
                        void perform({ action, event_id: call.id })
                      }
                    >
                      {title}
                    </button>
                  ))}
                </div>
              ) : (
                <button
                  disabled={locked}
                  onClick={() =>
                    void perform({ action: "end", event_id: call.id })
                  }
                >
                  Завершить звонок
                </button>
              )}
            </section>
          )}
          <div className="phone-body">
            {tab === "contacts" && (
              <>
                <button
                  onClick={() => {
                    setEditContact(null);
                    setLabel("");
                    setAddress("");
                    setContactKind("person");
                    setAdding(!adding);
                  }}
                >
                  Добавить контакт
                </button>
                {adding && (
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      void perform({
                        action: editContact ? "edit_contact" : "add_contact",
                        contact_id: editContact,
                        label,
                        address,
                        kind: contactKind,
                        blocked:
                          phone.contacts.find((c) => c.id === editContact)
                            ?.blocked || false,
                      }).then((next) => {
                        if (next) {
                          setAdding(false);
                          setLabel("");
                          setAddress("");
                        }
                      });
                    }}
                  >
                    <label>
                      Сохранённое имя
                      <input
                        value={label}
                        onChange={(e) => setLabel(e.target.value)}
                        maxLength={160}
                        required
                      />
                    </label>
                    {!editContact && (
                      <>
                        <label>
                          Тип контакта
                          <select
                            value={contactKind}
                            onChange={(e) => setContactKind(e.target.value)}
                          >
                            <option value="person">Человек</option>
                            <option value="service">Служба</option>
                            <option value="shared">
                              Общий номер организации
                            </option>
                          </select>
                        </label>
                        <label>
                          Номер или адрес
                          <input
                            value={address}
                            onChange={(e) => setAddress(e.target.value)}
                            maxLength={160}
                            required
                          />
                        </label>
                      </>
                    )}
                    <button disabled={locked}>Сохранить контакт</button>
                  </form>
                )}
                {phone.contacts.length === 0 && (
                  <p>Сохранённых контактов нет.</p>
                )}
                {phone.contacts.map((c) => (
                  <article className="phone-row" key={c.id}>
                    {avatar(c.subject)}
                    <div>
                      <strong>{c.label}</strong>
                      <small>
                        {c.address}
                        {c.blocked
                          ? " · заблокирован"
                          : !c.available
                            ? " · недоступен"
                            : ""}
                      </small>
                    </div>
                    <div>
                      {phone.capabilities.text_message && (
                        <button
                          disabled={locked || c.blocked || !c.available}
                          onClick={() => {
                            const existing = phone.conversations.find(
                              (t) =>
                                !t.group &&
                                (t.contact_id === c.id ||
                                  (c.subject.id &&
                                    t.participants.some(
                                      (p) => p.id === c.subject.id,
                                    ))),
                            );
                            if (existing) {
                              void openChat(existing);
                            } else {
                              setContact(c.id);
                              setConversation(null);
                              setText("");
                              setTab("messages");
                            }
                          }}
                        >
                          Написать
                        </button>
                      )}
                      {phone.capabilities.voice_call && (
                        <button
                          disabled={
                            locked || !!call || c.blocked || !c.available
                          }
                          onClick={() =>
                            void perform({ action: "call", contact_id: c.id })
                          }
                        >
                          Позвонить
                        </button>
                      )}
                      <button
                        disabled={locked}
                        onClick={() => {
                          setEditContact(c.id);
                          setLabel(c.label);
                          setAdding(true);
                        }}
                      >
                        Переименовать
                      </button>
                      <button
                        disabled={locked}
                        onClick={() =>
                          void perform({
                            action: "edit_contact",
                            contact_id: c.id,
                            blocked: !c.blocked,
                          })
                        }
                      >
                        {c.blocked ? "Разблокировать" : "Блокировать"}
                      </button>
                    </div>
                  </article>
                ))}
                <h3>Экстренные службы · в игре</h3>
                {phone.emergency.map((e) => (
                  <div className="phone-row" key={e.service}>
                    <span>
                      {services[e.service]} · {e.number || "Номер не настроен"}
                    </span>
                    <button
                      disabled={locked || !!call || !e.number}
                      onClick={() =>
                        void perform({ action: "call", service: e.service })
                      }
                    >
                      Позвонить: {services[e.service]}
                    </button>
                  </div>
                ))}
              </>
            )}
            {tab === "messages" && (
              <>
                {!conversation && !contact ? (
                  <>
                    <button onClick={() => setGrouping(!grouping)}>
                      Создать группу
                    </button>
                    {grouping && (
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          void perform({
                            action: "create_group",
                            label: groupName,
                            member_ids: groupMembers,
                          }).then((next) => {
                            if (next) {
                              setGrouping(false);
                              setGroupMembers([]);
                              setGroupName("");
                            }
                          });
                        }}
                      >
                        <label>
                          Название группы
                          <input
                            value={groupName}
                            onChange={(e) => setGroupName(e.target.value)}
                            maxLength={160}
                          />
                        </label>
                        <fieldset>
                          <legend>Участники из контактов</legend>
                          {phone.contacts
                            .filter(
                              (c) => c.subject.id && !c.blocked && c.available,
                            )
                            .map((c) => (
                              <label key={c.id}>
                                <input
                                  type="checkbox"
                                  checked={groupMembers.includes(c.subject.id)}
                                  onChange={(e) =>
                                    setGroupMembers(
                                      e.target.checked
                                        ? [...groupMembers, c.subject.id]
                                        : groupMembers.filter(
                                            (id) => id !== c.subject.id,
                                          ),
                                    )
                                  }
                                />
                                {c.label}
                              </label>
                            ))}
                        </fieldset>
                        <button disabled={locked || !groupMembers.length}>
                          Создать переписку
                        </button>
                      </form>
                    )}
                    {phone.conversations.map((c) => (
                      <button
                        className="phone-row"
                        key={c.id}
                        disabled={locked}
                        onClick={() => void openChat(c)}
                      >
                        <span className="phone-avatars">
                          {c.participants.slice(0, 3).map((p, i) => (
                            <span key={i}>{avatar(p)}</span>
                          ))}
                        </span>
                        <strong>{c.title}</strong>
                        {phone.events.some(
                          (e) => e.conversation_id === c.id && e.unread,
                        ) && <span>Новое</span>}
                      </button>
                    ))}
                    {!phone.conversations.length && (
                      <p>Открой контакт, чтобы написать первое сообщение.</p>
                    )}
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => {
                        setContact(null);
                        setConversation(null);
                        setText("");
                      }}
                    >
                      К перепискам
                    </button>
                    <h3>{selected?.title || target?.label}</h3>
                    <div
                      className="phone-avatars"
                      aria-label="Участники переписки"
                    >
                      {(
                        selected?.participants ||
                        (target ? [target.subject] : [])
                      ).map((p, i) => (
                        <span key={i}>
                          {avatar(p)}
                          {p.name}
                        </span>
                      ))}
                    </div>
                    {selected?.group && selected.active && (
                      <fieldset>
                        <legend>Управление участниками</legend>
                        {selected.participants
                          .filter((p) => p.id && p.id !== phone.actor_id)
                          .map((p) => (
                            <button
                              key={p.id}
                              disabled={locked}
                              onClick={() =>
                                void perform({
                                  action: "remove",
                                  conversation_id: selected.id,
                                  member_ids: [p.id],
                                })
                              }
                            >
                              Удалить: {p.name}
                            </button>
                          ))}
                        {phone.contacts
                          .filter(
                            (c) =>
                              c.subject.id &&
                              !c.blocked &&
                              c.available &&
                              !selected.participants.some(
                                (p) => p.id === c.subject.id,
                              ),
                          )
                          .map((c) => (
                            <button
                              key={c.id}
                              disabled={locked}
                              onClick={() =>
                                void perform({
                                  action: "join",
                                  conversation_id: selected.id,
                                  member_ids: [c.subject.id],
                                })
                              }
                            >
                              Добавить: {c.label}
                            </button>
                          ))}
                      </fieldset>
                    )}
                    {selected?.group && selected.active && (
                      <button
                        disabled={locked}
                        onClick={() =>
                          void perform({
                            action: "leave",
                            conversation_id: selected.id,
                          }).then((next) => {
                            if (next) setConversation(null);
                          })
                        }
                      >
                        Выйти из группы
                      </button>
                    )}
                    <div className="phone-messages" aria-label="Сообщения">
                      {phone.events
                        .filter(
                          (e) =>
                            e.channel === "TEXT_MESSAGE" &&
                            e.conversation_id === conversation &&
                            conversation,
                        )
                        .map((e) => (
                          <article
                            key={e.id}
                            className={
                              e.outgoing
                                ? "phone-message outgoing"
                                : "phone-message"
                            }
                          >
                            {avatar(e.subject)}
                            <div>
                              <small>
                                {e.outgoing ? "Ты" : e.label} · {formatDateLabel(e.time_label)}
                              </small>
                              <p>{e.content ?? "Непрочитанное сообщение"}</p>
                              <small>
                                {e.outgoing && e.read_count
                                  ? `Прочитано: ${e.read_count} из ${e.recipient_count}`
                                  : status[e.status]}
                              </small>
                              {e.unread && (
                                <button
                                  disabled={locked}
                                  onClick={() =>
                                    void perform({
                                      action: "read",
                                      event_id: e.id,
                                    })
                                  }
                                >
                                  Прочитать
                                </button>
                              )}
                            </div>
                          </article>
                        ))}
                    </div>
                    {phone.capabilities.text_message &&
                      (!selected || selected.active) && (
                        <form
                          onSubmit={(e) => {
                            e.preventDefault();
                            void send();
                          }}
                        >
                          <label>
                            Сообщение
                            <textarea
                              aria-label="Сообщение в телефоне"
                              value={text}
                              onChange={(e) => {
                                setText(e.target.value);
                                drafts.current[messageKey] = e.target.value;
                              }}
                              maxLength={4000}
                            />
                          </label>
                          <button disabled={locked || !text.trim()}>
                            Отправить сообщение
                          </button>
                        </form>
                      )}
                  </>
                )}
              </>
            )}
            {tab === "calls" && (
              <>
                <h3>История звонков</h3>
                {phone.events
                  .filter((e) => e.channel === "VOICE_CALL")
                  .slice()
                  .reverse()
                  .map((e) => (
                    <article className="phone-row" key={e.id}>
                      {avatar(e.subject)}
                      <div>
                        <strong>{e.label}</strong>
                        <small>
                          {e.outgoing ? "Исходящий" : "Входящий"} ·{" "}
                          {status[e.status]} · {formatDateLabel(e.time_label)}
                        </small>
                      </div>
                    </article>
                  ))}
              </>
            )}
          </div>
          <nav className="phone-bottom" aria-label="Разделы телефона">
            {(
              [
                ["calls", "Звонки", PhoneIcon],
                ["messages", "Переписки", MessageCircle],
                ["contacts", "Контакты", ContactRound],
              ] as const
            ).map(([key, label, Icon]) => (
              <button
                key={key}
                aria-label={label}
                title={label}
                aria-pressed={tab === key}
                onClick={() => setTab(key)}
              >
                <Icon size={23} />
                {key === "messages" && unread > 0 && <small>{unread}</small>}
              </button>
            ))}
          </nav>
        </div>
      </div>
    </div>
  );
}
