import { ChevronLeft, Phone as PhoneIcon, Users } from 'lucide-react';
import { api } from '../../api';
import { Button } from '../../components/ui/button';
import { phoneText as t } from '../../lib/phone';
import { CharacterAvatar } from '../../Portrait';
import { active, type Save } from '../../types';
import { useDevice } from '../usePhone';

export function Chrome({ label }: { label: string }) {
  const {
    avatar,
    back,
    busy,
    call,
    chatOrigin,
    chatRecipient,
    contact,
    conversation,
    currentOwner,
    dialing,
    disabled,
    endCall,
    error,
    inChat,
    job,
    jobHere,
    locked,
    membersOpen,
    nested,
    onCommit,
    ownerKey,
    perform,
    phone,
    recipient,
    recipientTarget,
    recovery,
    requestLock,
    save,
    selected,
    setBusy,
    setError,
    setMembersOpen,
    setTab,
    status,
    tab,
    target,
    title,
  } = useDevice();
  const appTitle = nested && (tab === 'contacts' || tab === 'messages') ? title : label;
  return (
    <>
      <header
        hidden={!!dialing || tab === 'home'}
        className={'phone-top' + (nested ? '' : ' phone-page-heading')}
      >
        {
          <Button
            variant="ghost"
            size="icon"
            aria-label={membersOpen ? 'К диалогу' : inChat && !chatOrigin ? 'К перепискам' : 'Назад'}
            onClick={back}
          >
            <ChevronLeft size={20} />
          </Button>
        }
        {inChat && !membersOpen && (
          <span className="phone-header-avatar" aria-label="Участники переписки">
            {selected?.group ? (
              <Users size={24} />
            ) : selected?.participants.find((p) => p.id !== phone.actor_id) ||
              target?.subject ||
              recipientTarget?.subject ? (
              avatar(
                (selected?.participants.find((p) => p.id !== phone.actor_id) ||
                  target?.subject ||
                  recipientTarget?.subject)!,
              )
            ) : null}
          </span>
        )}
        <div className="phone-heading" aria-busy={busy}>
          <h2 title={appTitle}>{appTitle}</h2>
          <small>
            {inChat
              ? selected?.group
                ? `${selected.participants.length} участников`
                : 'Личная переписка'
              : null}
          </small>
        </div>
        {inChat && selected?.group && selected.active && !membersOpen && (
          <Button
            variant="ghost"
            size="icon"
            aria-label="Управление участниками"
            onClick={() => setMembersOpen(true)}
          >
            <Users size={20} />
          </Button>
        )}
        {inChat && !selected?.group && chatRecipient?.can_call && (
          <Button
            variant="ghost"
            size="icon"
            aria-label={'Позвонить: ' + chatRecipient.subject.name}
            disabled={locked || !!call}
            onClick={() => void perform({ action: 'call', character_id: chatRecipient.id })}
          >
            <PhoneIcon />
          </Button>
        )}
      </header>
      {error && (
        <div className="phone-error" role="alert">
          <span>{error}</span>
          <button
            disabled={busy}
            onClick={async () => {
              if (requestLock.current || locked) return;
              requestLock.current = true;
              setBusy(true);
              try {
                const fresh = await api<Save>(`/saves/${save.id}`);
                if (currentOwner.current === ownerKey) {
                  onCommit(fresh);
                  setError('');
                }
              } catch {
                if (currentOwner.current === ownerKey) setError(t('failed'));
              } finally {
                requestLock.current = false;
                setBusy(false);
              }
            }}
          >
            Обновить состояние
          </button>
        </div>
      )}
      {jobHere && active(job) && (
        <p className="phone-progress" role="status">
          {call?.status === 'ringing' ? t('dialing') : t('waiting')}
        </p>
      )}
      {jobHere && job && ['error', 'stopped'].includes(job.status) && job.revision === save.revision && (
        <div role="alert" className="phone-progress">
          <p>{t('reactionFailed')}</p>
          {recovery}
        </div>
      )}
      {call && tab === 'messages' && (conversation || contact || recipient) && (
        <button className="phone-call-link" onClick={() => setTab('calls')}>
          {call.status === 'ringing' ? 'Вызов' : 'Разговор'} · {call.label} →
        </button>
      )}
      {call && !(tab === 'messages' && (conversation || contact || recipient)) && (
        <section className="phone-call" aria-label="Текущий звонок">
          {dialing && (
            <header className="call-scene-header">
              {avatar(call.subject)}
              <div>
                <h2>{call.label}</h2>
                <small>
                  <PhoneIcon size={12} />
                  Вызов…
                </small>
              </div>
            </header>
          )}
          {dialing ? (
            <CharacterAvatar subject={call.subject} saveId={save.id} size={88} />
          ) : (
            avatar(call.subject)
          )}
          <strong>{call.label}</strong>
          <span role="status" aria-live="polite">
            {call.status === 'ringing' && (
              <span className="phone-dialing" aria-hidden="true">
                ●{' '}
              </span>
            )}
            {status[call.status]} · {call.outgoing ? 'Исходящий' : 'Входящий'}
          </span>
          {call.status === 'answered' && (
            <button
              onClick={() => {
                window.dispatchEvent(new CustomEvent('phone-call-open', { detail: call.id }));
              }}
            >
              Перейти к разговору
            </button>
          )}
          {!call.outgoing && call.status === 'ringing' ? (
            <div>
              {[
                ['answer', 'Ответить'],
                ['decline', 'Отклонить'],
                ['ignore', 'Игнорировать'],
              ].map(([action, title]) => (
                <button
                  key={action}
                  disabled={locked}
                  onClick={() => void perform({ action, event_id: call.id })}
                >
                  {title}
                </button>
              ))}
            </div>
          ) : (
            <button
              disabled={
                busy || (disabled && !(job?.kind === 'communication' && job.revision === save.revision))
              }
              onClick={() => void endCall()}
            >
              {call.status === 'ringing' ? 'Отменить вызов' : 'Завершить разговор'}
            </button>
          )}
        </section>
      )}
    </>
  );
}
