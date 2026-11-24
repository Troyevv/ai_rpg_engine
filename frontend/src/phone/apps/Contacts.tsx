import { MessageCircle, Phone as PhoneIcon, Plus, Search } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { phoneText as t } from '../../lib/phone';
import { useDevice } from '../usePhone';

export function Contacts() {
  const {
    adding,
    address,
    avatar,
    call,
    chooseRecipient,
    contactLabels,
    detail,
    editContact,
    focusKey,
    label,
    legacyContacts,
    locked,
    matchesSearch,
    openChat,
    perform,
    phone,
    returnFocus,
    savedRecipient,
    search,
    services,
    setAdding,
    setAddress,
    setContact,
    setConversation,
    setDetail,
    setEditContact,
    setLabel,
    setRecipient,
    setSearch,
    setTab,
    visibleRecipients,
  } = useDevice();
  return (
    <>
      {!detail && !adding && (
        <>
          <Button
            variant="secondary"
            onClick={() => {
              setAddress('');
              setLabel('');
              setEditContact(null);
              setAdding(true);
            }}
          >
            <Plus />
            Добавить контакт
          </Button>
          <label className="phone-search">
            <Search aria-hidden size={17} />
            <input
              aria-label={t('searchRecipient')}
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('searchPlaceholder')}
            />
          </label>
          <section className="phone-directory" aria-label={t('directory')}>
            {visibleRecipients.map((r) => {
              const saved = savedRecipient(r);
              return (
                <article className="phone-row phone-recipient" key={r.id}>
                  {avatar(r.subject)}
                  <button
                    className="phone-contact-name"
                    data-phone-focus={`recipient:${r.id}`}
                    disabled={locked || (!saved && !r.can_send)}
                    onClick={() => {
                      if (saved) {
                        returnFocus.current = document.activeElement as HTMLElement;
                        focusKey.current = `recipient:${r.id}`;
                        setDetail(saved.id);
                      } else chooseRecipient(r);
                    }}
                  >
                    <strong>{saved?.label || r.subject.name}</strong>
                    {saved && saved.label !== r.subject.name && <small>{r.subject.name}</small>}
                  </button>
                  <div className="phone-recipient-actions">
                    {phone.capabilities.text_message && (
                      <button
                        title={t('write')}
                        aria-label={t('writeTo') + ' ' + r.subject.name}
                        disabled={locked || !r.can_send}
                        onClick={() => chooseRecipient(r)}
                      >
                        <MessageCircle size={18} aria-hidden="true" />
                      </button>
                    )}
                    {phone.capabilities.voice_call && (
                      <button
                        title={t('call')}
                        aria-label={t('callTo') + ' ' + r.subject.name}
                        disabled={locked || !!call || !r.can_call}
                        onClick={() => void perform({ action: 'call', character_id: r.id })}
                      >
                        <PhoneIcon size={18} aria-hidden="true" />
                      </button>
                    )}
                  </div>
                </article>
              );
            })}
            {!visibleRecipients.length &&
              !legacyContacts.some((c) => matchesSearch(c.label + ' ' + c.address)) && (
                <p role="status">{t('noRecipients')}</p>
              )}
          </section>
        </>
      )}

      {adding && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void perform(
              editContact
                ? {
                    action: 'edit_contact',
                    contact_id: editContact,
                    label,
                    blocked: phone.contacts.find((c) => c.id === editContact)?.blocked || false,
                  }
                : { action: 'add_contact', label: label.trim(), address: address.trim() },
            ).then((next) => {
              if (next) {
                if (editContact) contactLabels.current.delete(editContact);
                setEditContact(null);
                setAdding(false);
                setLabel('');
                setAddress('');
              }
            });
          }}
        >
          <label>
            Сохранённое имя
            <input
              value={label}
              onChange={(e) => {
                setLabel(e.target.value);
                if (editContact) contactLabels.current.set(editContact, e.target.value);
              }}
              maxLength={160}
              required
            />
          </label>
          {!editContact && (
            <label>
              Адрес или номер
              <input required value={address} maxLength={160} onChange={(e) => setAddress(e.target.value)} />
            </label>
          )}
          <button disabled={locked || !label.trim() || (!editContact && !address.trim())}>
            Сохранить контакт
          </button>
        </form>
      )}
      {!adding &&
        (detail
          ? phone.contacts.filter((c) => c.id === detail)
          : legacyContacts.filter((c) => matchesSearch(c.label + ' ' + c.address))
        ).map((c) => (
          <article className={`phone-row ${detail ? 'phone-contact-detail' : ''}`} key={c.id}>
            {avatar(c.subject)}
            <div>
              <button
                className="phone-contact-name"
                onClick={() => {
                  setDetail(c.id);
                }}
              >
                <strong>{c.label}</strong>
              </button>
              <small>
                {c.address}
                {c.blocked ? ' · заблокирован' : !c.available ? ' · недоступен' : ''}
              </small>
            </div>
            {detail === c.id && (
              <div className="phone-contact-actions">
                {phone.capabilities.text_message && (
                  <button
                    disabled={locked || c.can_send === false}
                    onClick={() => {
                      const existing = phone.conversations.find(
                        (t) =>
                          !t.group &&
                          (t.contact_id === c.id ||
                            (c.subject.id && t.participants.some((p) => p.id === c.subject.id))),
                      );
                      if (existing) {
                        void openChat(existing);
                      } else {
                        setRecipient(null);
                        setContact(c.id);
                        setConversation(null);
                        setTab('messages');
                      }
                    }}
                  >
                    Написать
                  </button>
                )}
                {phone.capabilities.voice_call && (
                  <button
                    disabled={locked || !!call || c.can_call === false}
                    onClick={() => void perform({ action: 'call', contact_id: c.id })}
                  >
                    Позвонить
                  </button>
                )}
                <details className="phone-contact-manage">
                  <summary>Управление контактом</summary>
                  <button
                    disabled={locked}
                    onClick={() => {
                      setEditContact(c.id);
                      setLabel(contactLabels.current.get(c.id) ?? c.label);
                      setAdding(true);
                    }}
                  >
                    Переименовать
                  </button>
                  <button
                    disabled={locked}
                    onClick={() =>
                      void perform({
                        action: 'edit_contact',
                        contact_id: c.id,
                        blocked: !c.blocked,
                      })
                    }
                  >
                    {c.blocked ? 'Разблокировать' : 'Блокировать'}
                  </button>
                </details>
              </div>
            )}
          </article>
        ))}
      {!adding && !detail && <h3>Экстренные службы · в игре</h3>}
      {!adding &&
        !detail &&
        phone.emergency.map((e) => (
          <div className="phone-row" key={e.service}>
            <span>
              {services[e.service]} · {e.number || 'Номер не настроен'}
            </span>
            <button
              disabled={locked || !!call || !e.number}
              onClick={() => void perform({ action: 'call', service: e.service })}
            >
              Позвонить: {services[e.service]}
            </button>
          </div>
        ))}
    </>
  );
}
