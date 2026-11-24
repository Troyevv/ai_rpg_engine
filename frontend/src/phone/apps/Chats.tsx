import { ArrowDown, Send, SquarePen, Users } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { phoneText as t } from '../../lib/phone';
import { PhoneChatList, PhoneMessages } from '../../PhoneContent';
import { active } from '../../types';
import { useDevice } from '../usePhone';

export function Chats() {
  const {
    arrivals,
    away,
    canSend,
    contact,
    continueMessage,
    conversation,
    drafts,
    groupMembers,
    groupName,
    grouping,
    hasReply,
    input,
    job,
    latestOutgoing,
    locked,
    membersOpen,
    messageKey,
    messages,
    openChat,
    perform,
    phone,
    reading,
    recipient,
    recipients,
    revealComposer,
    save,
    selected,
    send,
    setAway,
    setConversation,
    setDetail,
    setGroupMembers,
    setGroupName,
    setGrouping,
    setSearch,
    setTab,
    setText,
    text,
  } = useDevice();
  return (
    <>
      {!conversation && !contact && !recipient ? (
        <>
          {!grouping && phone.capabilities.text_message && (
            <div className="phone-list-actions">
              <Button
                variant="secondary"
                onClick={() => {
                  setTab('contacts');
                  setDetail(null);
                  setSearch('');
                }}
              >
                <SquarePen size={18} />
                {t('write')}
              </Button>
              <Button variant="ghost" onClick={() => setGrouping(true)}>
                <Users size={18} />
                Создать группу
              </Button>
            </div>
          )}
          {grouping && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void perform({
                  action: 'create_group',
                  label: groupName,
                  member_ids: groupMembers,
                }).then((next) => {
                  if (next) {
                    setGrouping(false);
                    setGroupMembers([]);
                    setGroupName('');
                  }
                });
              }}
            >
              <label>
                Название группы
                <input value={groupName} onChange={(e) => setGroupName(e.target.value)} maxLength={160} />
              </label>
              <fieldset>
                <legend>{t('directory')}</legend>
                {recipients
                  .filter((c) => c.can_send)
                  .map((c) => (
                    <label key={c.id}>
                      <input
                        type="checkbox"
                        checked={groupMembers.includes(c.subject.id)}
                        onChange={(e) =>
                          setGroupMembers(
                            e.target.checked
                              ? [...groupMembers, c.subject.id]
                              : groupMembers.filter((id) => id !== c.subject.id),
                          )
                        }
                      />
                      {c.subject.name}
                    </label>
                  ))}
              </fieldset>
              <button disabled={locked || !groupMembers.length}>Создать переписку</button>
            </form>
          )}
          {!grouping && <PhoneChatList phone={phone} saveId={save.id} openChat={openChat} />}
        </>
      ) : (
        <>
          {membersOpen && selected?.group && selected.active && (
            <fieldset className="phone-member-list">
              <legend>Управление участниками</legend>
              {selected.participants
                .filter((p) => p.id && p.id !== phone.actor_id)
                .map((p) => (
                  <button
                    key={p.id}
                    disabled={locked}
                    onClick={() =>
                      void perform({
                        action: 'remove',
                        conversation_id: selected.id,
                        member_ids: [p.id],
                      })
                    }
                  >
                    Удалить: {p.name}
                  </button>
                ))}
              {recipients
                .filter((c) => c.can_send && !selected.participants.some((p) => p.id === c.subject.id))
                .map((c) => (
                  <button
                    key={c.id}
                    disabled={locked}
                    onClick={() =>
                      void perform({
                        action: 'join',
                        conversation_id: selected.id,
                        member_ids: [c.subject.id],
                      })
                    }
                  >
                    Добавить: {c.subject.name}
                  </button>
                ))}
            </fieldset>
          )}
          {membersOpen && selected?.group && selected.active && (
            <button
              disabled={locked}
              onClick={() =>
                void perform({
                  action: 'leave',
                  conversation_id: selected.id,
                }).then((next) => {
                  if (next) setConversation(null);
                })
              }
            >
              Выйти из группы
            </button>
          )}
          {!membersOpen && (
            <>
              <div
                ref={messages}
                className="phone-messages"
                aria-label="Сообщения"
                onScroll={(e) => {
                  const el = e.currentTarget;
                  const pinned = el.scrollHeight - el.scrollTop - el.clientHeight < 32;
                  reading.current[messageKey] = { top: el.scrollTop, pinned };
                  setAway(!pinned);
                }}
              >
                <PhoneMessages
                  events={phone.events.filter(
                    (e) =>
                      e.channel === 'TEXT_MESSAGE' &&
                      !!conversation &&
                      e.conversation_id === conversation &&
                      !arrivals.hidden.has(e.id),
                  )}
                  animated={arrivals.animated}
                  group={!!selected?.group}
                  locked={locked}
                  read={(id) => void perform({ action: 'read', event_id: id })}
                />
              </div>
              {away && (
                <button
                  className="phone-latest"
                  onClick={() => {
                    const el = messages.current;
                    if (el) {
                      el.scrollTop = el.scrollHeight;
                      reading.current[messageKey] = { top: el.scrollTop, pinned: true };
                      setAway(false);
                    }
                  }}
                >
                  <ArrowDown size={16} />К последнему сообщению
                </button>
              )}
              {selected?.awaiting_response && (
                <p className="phone-response-wait" role="status">
                  Ждут твоего ответа
                </p>
              )}
              {!canSend && (
                <p className="muted" role="status">
                  {t('recipientUnavailable')}
                </p>
              )}
              {phone.capabilities.text_message && (!selected || selected.active) && (
                <form
                  className="phone-composer"
                  onFocusCapture={revealComposer}
                  onSubmit={(e) => {
                    e.preventDefault();
                    void send();
                  }}
                >
                  <div className="phone-compose-row">
                    <textarea
                      ref={input}
                      rows={1}
                      placeholder="Сообщение…"
                      aria-label="Сообщение в телефоне"
                      value={text}
                      onChange={(e) => {
                        setText(e.target.value);
                        drafts.current[messageKey] = e.target.value;
                        sessionStorage.setItem(`phone-draft:${messageKey}`, e.target.value);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !e.nativeEvent.isComposing) {
                          e.preventDefault();
                          e.stopPropagation();
                          if (!locked && canSend && text.trim()) void send();
                        }
                      }}
                    />
                    <Button
                      type="submit"
                      size="icon"
                      aria-label="Отправить сообщение"
                      disabled={locked || !canSend || !text.trim()}
                    >
                      <Send size={20} />
                    </Button>
                  </div>
                  <small className="muted">1 игровая минута · ответ не гарантирован</small>
                  {latestOutgoing && !hasReply && !active(job) && (
                    <button
                      type="button"
                      disabled={locked}
                      onClick={() => void continueMessage(latestOutgoing)}
                    >
                      Подождать ещё · 1 мин
                    </button>
                  )}
                </form>
              )}
            </>
          )}
        </>
      )}
    </>
  );
}
