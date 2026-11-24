import { afterDeviceClosed, useDeviceHistory } from './history';
import { useReadQueue } from './readQueue';
import { usePhoneNavigation } from './navigation';
import { useMobile } from '../mobile';
import { dismissTransient } from '../lib/transientBack';
import { phoneText as t } from '../lib/phone';
import { usePhoneArrivals } from '../lib/usePhoneArrivals';
import { phoneOperation } from '../lib/phoneRequests';
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  createContext,
  useContext,
  type ReactNode,
} from 'react';
import { api } from '../api';
import { active, type Save, type Job, type ModelConfig } from '../types';
import { CharacterAvatar, type PortraitSubject } from '../Portrait';
import type { Recipient, Conversation, PhoneEvent } from './types';
const status: Record<string, string> = {
  sent: 'Отправлено',
  delivered: 'Доставлено',
  ringing: 'Вызов',
  answered: 'Разговор',
  declined: 'Отклонён',
  missed: 'Пропущен',
  ended: 'Завершён',
};
const services: Record<string, string> = {
  medical: 'Скорая помощь',
  police: 'Полиция',
  fire: 'Пожарная служба',
};

export interface PhoneProps {
  save: Save;
  disabled: boolean;
  onCommit: (save: Save) => void;
  onBusyChange: (busy: boolean) => void;
  config: ModelConfig;
  apiKey: string;
  onJob: (job: Job) => void;
  job: Job | null;
  recovery?: ReactNode;
  chooseAction?: (text: string) => void;
  openCharacter: (id: string) => void;
}
export function usePhone(
  {
    save,
    disabled,
    onCommit,
    onBusyChange,
    config,
    apiKey,
    onJob,
    job: receivedJob,
    recovery,
    openCharacter,
    chooseAction,
  }: PhoneProps,
  scope: string,
) {
  const phone = save.state.phone!;
  const job =
    receivedJob?.presentation?.actor_id && receivedJob.presentation.actor_id !== phone?.actor_id
      ? null
      : receivedJob;
  const ownerKey = scope;
  const perceptions = useReadQueue(scope, save, phone.actor_id);

  const trigger = useRef<HTMLButtonElement>(null);
  const mobile = useMobile();
  const screen = useRef<HTMLDivElement>(null);
  const drafts = useRef<Record<string, string>>({});
  const requestLock = useRef(false);
  const autoReadAttempt = useRef<string | null>(null);
  const currentRevision = useRef(save.revision);
  currentRevision.current = Math.max(currentRevision.current, save.revision);
  const receiptTail = useRef(Promise.resolve());
  const currentOwner = useRef(ownerKey);
  currentOwner.current = ownerKey;
  useLayoutEffect(() => {
    currentOwner.current = ownerKey;
    return () => {
      currentOwner.current = '';
    };
  }, [ownerKey]);
  const commitReceipt = (next: Save) => {
    if (currentOwner.current === ownerKey && next.revision >= currentRevision.current) {
      currentRevision.current = next.revision;
      onCommit(next);
    }
  };
  // Passive receipts share one revision chain without disabling the button under
  // the player's pointer. Foreground commands wait for earlier receipts.
  const flushReceipts = (afterRead?: (revision: number) => Promise<void>) => {
    const task = receiptTail.current.then(async () => {
      if (currentOwner.current !== ownerKey) throw new Error('Владелец телефона изменился.');
      const revision = await perceptions.flush(currentRevision.current, commitReceipt);
      if (currentOwner.current !== ownerKey) throw new Error('Владелец телефона изменился.');
      if (afterRead) await afterRead(revision);
      return currentRevision.current;
    });
    receiptTail.current = task.then(
      () => {},
      () => {},
    );
    return task;
  };
  const [membersOpen, setMembersOpen] = useState(false);
  const [away, setAway] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const listPositions = useRef<Record<string, number>>({});
  const returnFocus = useRef<HTMLElement | null>(null);
  const focusKey = useRef<string | null>(null);
  const [detail, setDetail] = useState<string | null>(null);
  const [recipient, setRecipient] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  const messages = useRef<HTMLDivElement>(null);
  const reading = useRef<Record<string, { top: number; pinned: boolean }>>({});

  useEffect(() => {
    const close = () => setOpen(false);
    window.addEventListener('save-workspace-opened', close);
    return () => window.removeEventListener('save-workspace-opened', close);
  }, []);
  useEffect(() => {
    const show = () => {
      if (phone) {
        home();
        setOpen(true);
      }
    };
    window.addEventListener('phone-open', show);
    return () => window.removeEventListener('phone-open', show);
  }, [phone]);
  const [open, setOpen] = useState(false),
    [tab, setTab] = useState('home');
  const [conversation, setConversation] = useState<string | null>(null),
    [contact, setContact] = useState<string | null>(null);
  const [text, setText] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  // Phone mutations share the save revision with turns and control changes.
  // Keep the parent locked even when the phone is closed before a response arrives.
  useLayoutEffect(() => {
    onBusyChange(busy);
    return () => onBusyChange(false);
  }, [busy, onBusyChange]);
  const [editContact, setEditContact] = useState<string | null>(null);
  const contactLabels = useRef(new Map<string, string>());
  const [address, setAddress] = useState('');
  const [label, setLabel] = useState('');
  const [adding, setAdding] = useState(false),
    [grouping, setGrouping] = useState(false);
  const [groupMembers, setGroupMembers] = useState<string[]>([]),
    [groupName, setGroupName] = useState('');
  const messageKey = `${ownerKey}:${conversation || contact || recipient || ''}`;
  const currentMessage = useRef(messageKey);
  currentMessage.current = messageKey;
  const arrivals = usePhoneArrivals(
    phone?.events,
    ownerKey,
    open &&
      tab === 'messages' &&
      !membersOpen &&
      phone?.conversations.find((c) => c.id === conversation)?.group
      ? messageKey
      : '',
    conversation,
  );
  useEffect(() => {
    setText(drafts.current[messageKey] || sessionStorage.getItem(`phone-draft:${messageKey}`) || '');
  }, [messageKey]);
  const revealComposer = () => {
    const viewport = screen.current;
    const form = viewport?.querySelector<HTMLFormElement>('.phone-composer');
    if (!viewport || !form?.contains(document.activeElement) || !mobile) return;
    const bounds = viewport.getBoundingClientRect(),
      content = form.getBoundingClientRect();
    if (content.bottom > bounds.bottom) viewport.scrollTop += content.bottom - bounds.bottom;
    else if (content.top < bounds.top) viewport.scrollTop -= bounds.top - content.top;
  };
  const navigation = usePhoneNavigation(tab, setTab, screen);
  const { route, routes, home, navigate, push, pop } = navigation;
  const returnFromCall = useRef<string | null>(null);
  const restoreAfterCall = useRef(false);
  useEffect(() => {
    if (
      open ||
      !restoreAfterCall.current ||
      phone.events.some((e) => e.channel === 'VOICE_CALL' && e.status === 'answered')
    )
      return;
    const restore = () => {
      if (!document.querySelector('[role="dialog"]')) {
        restoreAfterCall.current = false;
        if (returnFromCall.current) {
          setTab(returnFromCall.current);
          returnFromCall.current = null;
        }
        setOpen(true);
      }
    };
    const observer = new MutationObserver(restore);
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['role'],
    });
    restore();
    return () => observer.disconnect();
  }, [open, phone.events]);
  const chatOrigin = useRef<string | null>(null);
  const externalOrigin = useRef<{ from: string; to: string } | null>(null);
  const visit = (id: string, path: { screen: string; id?: string }) => {
    if (tab === id) push(path.screen, path.id);
    else {
      externalOrigin.current = { from: tab, to: id };
      navigate(id, path);
    }
  };
  const back = () => {
    if (dismissTransient()) return;
    if (routes.length === 1 && externalOrigin.current?.to === tab) {
      const from = externalOrigin.current.from;
      externalOrigin.current = null;
      pop();
      navigate(from);
      return;
    }
    if (routes.length) {
      pop();
      return;
    }
    if (tab === 'home') {
      close();
      return;
    }
    if (tab === 'messages' && membersOpen) {
      setMembersOpen(false);
      requestAnimationFrame(() =>
        screen.current
          ?.querySelector<HTMLElement>('[aria-label="Управление участниками"]')
          ?.focus({ preventScroll: true }),
      );
      return;
    }
    if (tab === 'contacts' && adding) {
      setAdding(false);
      setEditContact(null);
      return;
    }
    if (tab === 'messages' && grouping) {
      setGrouping(false);
      return;
    }
    if (tab === 'messages' && (conversation || contact || recipient)) {
      setConversation(null);
      setContact(null);
      setRecipient(null);
      if (chatOrigin.current) {
        setTab(chatOrigin.current);
        chatOrigin.current = null;
      }
    } else if (tab === 'contacts' && detail) {
      setDetail(null);
    } else {
      home();
      return;
    }
    requestAnimationFrame(() => {
      if (returnFocus.current?.isConnected) returnFocus.current.focus({ preventScroll: true });
      else {
        const target = Array.from(
          screen.current?.querySelectorAll<HTMLElement>('[data-phone-focus]') || [],
        ).find((el) => el.dataset.phoneFocus === focusKey.current);
        (target || screen.current)?.focus({ preventScroll: true });
      }
    });
  };
  useDeviceHistory('phoneUI', 'phone:' + scope, open, () => {
    const keep = tab !== 'home';
    back();
    return keep;
  });
  const backRef = useRef(back);
  backRef.current = back;
  const close = () => {
    restoreAfterCall.current = false;
    setOpen(false);
    (document.activeElement as HTMLElement | null)?.blur();
    requestAnimationFrame(() => trigger.current?.focus({ preventScroll: true }));
  };
  useEffect(() => {
    if (!open) return;
    screen.current?.focus({ preventScroll: true });
    const resize = new ResizeObserver(revealComposer);
    if (screen.current) resize.observe(screen.current);
    const escape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        backRef.current();
      }
    };
    const modal = new MutationObserver(() => {
      const device = screen.current?.closest('.phone-device');
      const other = Array.from(document.querySelectorAll('[role="dialog"]')).find(
        (dialog) => dialog !== device,
      );
      if (other) {
        restoreAfterCall.current = !!other.querySelector('.call-scene');
        setOpen(false);
      }
    });
    modal.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['role'],
    });
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('keydown', escape);
      modal.disconnect();
      resize.disconnect();
    };
  }, [open]);
  useLayoutEffect(() => {
    if (!open) {
      autoReadAttempt.current = null;
      return;
    }
    if (
      tab !== 'messages' ||
      !conversation ||
      disabled ||
      busy ||
      requestLock.current ||
      !phone?.events.some((e) => e.conversation_id === conversation && e.unread)
    )
      return;
    const attempt = `${ownerKey}:${conversation}:${save.revision}`;
    if (autoReadAttempt.current === attempt) return;
    autoReadAttempt.current = attempt;
    const owner = ownerKey;
    requestLock.current = true;
    setBusy(true);
    flushReceipts()
      .then((revision) =>
        api<Save>(`/saves/${save.id}/phone`, {
          revision,
          command: { action: 'read', conversation_id: conversation, operation_id: crypto.randomUUID() },
        }),
      )
      .then((next) => {
        if (currentOwner.current === owner) onCommit(next);
      })
      .catch((e) => {
        if (currentOwner.current === owner) setError(t('failed'));
      })
      .finally(() => {
        requestLock.current = false;
        setBusy(false);
      });
  }, [save.revision, open, tab, conversation, disabled, busy]);
  useLayoutEffect(() => {
    const el = messages.current;
    if (el) {
      const position = reading.current[messageKey];
      el.scrollTop = position && !position.pinned ? position.top : el.scrollHeight;
    }
  }, [conversation, tab, open, membersOpen, phone?.events.length, save.revision, arrivals.hidden]);
  useLayoutEffect(() => {
    if (input.current) {
      input.current.style.height = 'auto';
      input.current.style.height = `${Math.min(input.current.scrollHeight, 120)}px`;
    }
  }, [text, open, conversation, recipient, contact]);
  useLayoutEffect(() => {
    if (open && screen.current && !screen.current.contains(document.activeElement))
      screen.current.focus({ preventScroll: true });
  }, [open, tab, conversation, contact, recipient, detail, membersOpen, grouping, adding]);
  const listKey = `${ownerKey}:${tab}:${route?.screen || ''}:${route?.id || ''}:${detail || ''}:${grouping}:${membersOpen}`;
  useLayoutEffect(() => {
    const viewport = list.current;
    if (!viewport || !open) return;
    const top = listPositions.current[listKey] || 0;
    const restore = () => {
      viewport.scrollTop = top;
      return viewport.scrollTop >= top - 1;
    };
    if (restore()) return;
    const observer = new MutationObserver(() => {
      if (restore()) stop();
    });
    const stop = () => {
      observer.disconnect();
      viewport.removeEventListener('wheel', stop);
      viewport.removeEventListener('touchstart', stop);
    };
    observer.observe(viewport, { childList: true, subtree: true });
    viewport.addEventListener('wheel', stop, { passive: true });
    viewport.addEventListener('touchstart', stop, { passive: true });
    return stop;
  }, [listKey, open, conversation, contact, recipient]);

  const locked =
    busy || disabled || save.state.actor_capabilities?.can_act === false || !!save.state.protagonist_required;
  const perform = async (command: Record<string, unknown>) => {
    if (locked || requestLock.current) return;
    requestLock.current = true;
    setBusy(true);
    setError('');
    const owner = ownerKey;
    const key = `phone-request:${owner}`;
    try {
      const revision = await flushReceipts();
      const request = phoneOperation(key, command);
      const payload = request.payload;
      const automatic = ['send', 'call'].includes(String(command.action));
      const response = await api<Save | { save: Save; job: Job }>(
        `/saves/${save.id}/phone${automatic ? '/dispatch' : ''}`,
        {
          revision,
          command: payload,
          ...(automatic ? { config, api_key: apiKey } : {}),
        },
      );
      request.complete();
      if (currentOwner.current !== owner) return;
      const next = 'save' in response ? response.save : response;
      if ('job' in response && 'save' in response) onJob(response.job);
      onCommit(next);

      if (command.action === 'answer') returnFromCall.current = tab;
      if (command.action === 'call') {
        returnFromCall.current = tab;
        setTab('calls');
      }
      return next;
    } catch (e) {
      if (currentOwner.current === owner) setError(e instanceof Error ? e.message : t('failed'));
    } finally {
      requestLock.current = false;
      setBusy(false);
    }
  };
  const call = phone.events.find(
    (e) => e.channel === 'VOICE_CALL' && ['ringing', 'answered'].includes(e.status),
  );
  const unread = phone.events.filter((e) => e.unread).length;
  const selected = phone.conversations.find((c) => c.id === conversation);
  const target = phone.contacts.find((c) => c.id === contact);
  const recipients = phone.recipients || [];
  const savedRecipient = (r: Recipient) => phone.contacts.find((c) => c.subject.id === r.id);
  const matchesSearch = (value: string) =>
    value.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase());
  const visibleRecipients = [...recipients]
    .sort((a, b) => Number(!!savedRecipient(b)) - Number(!!savedRecipient(a)))
    .filter((r) =>
      matchesSearch(
        r.subject.name +
          ' ' +
          (r.search_name || '') +
          ' ' +
          phone.contacts
            .filter((c) => c.subject.id === r.id)
            .map((c) => c.label)
            .join(' '),
      ),
    );
  const legacyContacts = phone.contacts.filter((c) => !recipients.some((r) => r.id === c.subject.id));
  const recipientTarget = recipients.find((r) => r.id === recipient);
  const canSend = selected
    ? selected.can_send !== false
    : recipient
      ? !!recipientTarget?.can_send
      : target?.can_send !== false;
  const chooseRecipient = (r: Recipient) => {
    returnFocus.current = document.activeElement as HTMLElement;
    focusKey.current = returnFocus.current?.dataset.phoneFocus || null;
    const existing = phone.conversations.find(
      (c) => !c.group && c.active && c.participants.some((p) => p.id === r.id),
    );
    if (existing) {
      void openChat(existing);
      return;
    }
    setRecipient(r.id);
    setContact(null);
    setConversation(null);
    setTab('messages');
  };
  const openChat = async (conversation: Conversation | string) => {
    const id = typeof conversation === 'string' ? conversation : conversation.id;
    chatOrigin.current = tab !== 'messages' && tab !== 'home' ? tab : null;
    returnFocus.current = document.activeElement as HTMLElement;
    focusKey.current = returnFocus.current?.dataset.phoneFocus || null;
    setMembersOpen(false);
    setRecipient(null);
    setConversation(id);
    setContact(null);
    setTab('messages');
    // An app's detail can already reference a delivered message while the shell
    // still has the snapshot from dispatch. Open the canonical thread by ID.
    if (!phone.conversations.some((c) => c.id === id)) {
      try {
        const next = await api<Save>(`/saves/${save.id}`);
        if (currentOwner.current === ownerKey && next.revision >= currentRevision.current) onCommit(next);
      } catch (e) {
        if (currentOwner.current === ownerKey) setError(e instanceof Error ? e.message : t('failed'));
      }
    } else if (phone.events.some((e) => e.conversation_id === id && e.unread)) {
      await perform({ action: 'read', conversation_id: id });
    }
  };
  const send = async () => {
    const next = await perform({
      action: 'send',
      content: text,
      ...(conversation
        ? { conversation_id: conversation }
        : recipient
          ? { character_id: recipient }
          : { contact_id: contact }),
    });
    if (next) {
      const remaining = drafts.current[messageKey] === text ? '' : drafts.current[messageKey] || '';
      drafts.current[messageKey] = remaining;
      if (remaining) sessionStorage.setItem(`phone-draft:${messageKey}`, remaining);
      else sessionStorage.removeItem(`phone-draft:${messageKey}`);
      if (currentMessage.current !== messageKey) return;
      setText((current) => (current === text ? '' : current));
      const last = next.state.phone?.events.filter((e) => e.channel === 'TEXT_MESSAGE' && e.outgoing).at(-1);
      if (last?.conversation_id) {
        const destination = `${ownerKey}:${last.conversation_id}`;
        if (destination !== messageKey && remaining) {
          drafts.current[destination] = remaining;
          sessionStorage.setItem(`phone-draft:${destination}`, remaining);
        }
        setConversation(last.conversation_id);
        setContact(null);
        setRecipient(null);
      }
    }
  };
  const avatar = (subject: PortraitSubject) => (
    <CharacterAvatar subject={subject} saveId={save.id} size={36} />
  );
  const continueMessage = async (event: PhoneEvent) => {
    if (locked || requestLock.current) return;
    requestLock.current = true;
    setBusy(true);
    setError('');
    const key = `phone-wait:${ownerKey}:${event.id}`;
    const requestId = sessionStorage.getItem(key) || crypto.randomUUID();
    sessionStorage.setItem(key, requestId);
    try {
      const result = await api<{ job: Job; save: Save }>(`/saves/${save.id}/phone/dispatch`, {
        revision: await flushReceipts(),
        config,
        api_key: apiKey,
        continuation: { source_event_id: event.id, owner_id: phone.actor_id, request_id: requestId },
      });
      sessionStorage.removeItem(key);
      if (currentOwner.current === ownerKey) {
        onJob(result.job);
        onCommit(result.save);
      }
    } catch (e) {
      if (currentOwner.current === ownerKey) setError(t('failed'));
    } finally {
      requestLock.current = false;
      setBusy(false);
    }
  };
  const latestOutgoing = phone.events
    .filter((e) => e.outgoing && e.channel === 'TEXT_MESSAGE' && e.conversation_id === conversation)
    .at(-1);
  const hasReply =
    !!latestOutgoing &&
    phone.events
      .slice(phone.events.findIndex((e) => e.id === latestOutgoing.id) + 1)
      .some((e) => !e.outgoing && e.conversation_id === conversation);
  const currentContact = phone.contacts.find((c) => c.id === detail);
  const endCall = async () => {
    if (!call || busy || requestLock.current) return;
    if (job?.kind !== 'communication' || job.revision !== save.revision) {
      await perform({ action: 'end', event_id: call.id });
      return;
    }
    requestLock.current = true;
    setBusy(true);
    try {
      if (active(job)) await api(`/jobs/${job.id}/stop`, {});
      const request = phoneOperation(`phone-request:${ownerKey}`, { action: 'end', event_id: call.id });
      const next = await api<Save>(`/saves/${save.id}/phone`, {
        revision: await flushReceipts(),
        command: request.payload,
      });
      request.complete();
      if (currentOwner.current === ownerKey) {
        onJob({ ...job, status: 'stopped' });
        onCommit(next);
      }
    } catch (e) {
      if (currentOwner.current === ownerKey) setError(t('failed'));
    } finally {
      requestLock.current = false;
      setBusy(false);
    }
  };
  const dialing = call?.outgoing && call.status === 'ringing' && tab === 'calls';
  const inChat = tab === 'messages' && !!(conversation || contact || recipient);
  const nested =
    !!route || inChat || (tab === 'contacts' && (!!detail || adding)) || (tab === 'messages' && grouping);
  const title =
    tab === 'contacts' && adding
      ? editContact
        ? 'Изменить контакт'
        : 'Новый контакт'
      : tab === 'messages' && membersOpen
        ? 'Участники группы'
        : grouping && tab === 'messages'
          ? 'Новая группа'
          : inChat
            ? selected?.title || target?.label || recipientTarget?.subject.name
            : tab === 'contacts'
              ? detail
                ? currentContact?.label
                : 'Контакты'
              : tab === 'calls'
                ? 'Звонки'
                : 'Сообщения';
  const chatRecipient = phone.capabilities.voice_call
    ? recipients.find(
        (r) =>
          r.id ===
          (recipient ||
            target?.subject.id ||
            selected?.participants.find((p) => p.id !== phone.actor_id)?.id),
      )
    : undefined;
  const jobHere =
    job?.kind === 'communication' &&
    (job.presentation?.call_id
      ? tab === 'calls'
      : tab === 'messages' && !!conversation && job.presentation?.conversation_id === conversation);

  const command = async (
    app: string,
    action: string,
    fields: Record<string, unknown> = {},
    generate = false,
  ) => {
    if (requestLock.current || disabled) return false;
    const pending = phoneOperation('app-request:' + ownerKey, {
      app,
      action,
      actor_id: phone.actor_id,
      ...fields,
    });
    requestLock.current = true;
    setBusy(true);
    setError('');
    try {
      const revision = await flushReceipts();
      const value = await api<Save | { save: Save; job: Job }>(
        `/saves/${save.id}/apps/${generate ? 'dispatch' : 'command'}`,
        {
          revision,
          command: pending.payload,
          ...(generate ? { config, api_key: apiKey } : {}),
        },
      );
      pending.complete();
      if (currentOwner.current !== ownerKey) return false;
      if ('save' in value) {
        onJob(value.job);
        onCommit(value.save);
      } else onCommit(value);
      return true;
    } catch (e) {
      if (currentOwner.current === ownerKey) setError(e instanceof Error ? e.message : t('failed'));
      return false;
    } finally {
      requestLock.current = false;
      setBusy(false);
    }
  };
  useEffect(() => {
    if (
      !Object.keys(perceptions.queue).length ||
      locked ||
      error ||
      requestLock.current ||
      (job?.kind === 'communication' &&
        job.revision === save.revision &&
        ['error', 'stopped'].includes(job.status))
    )
      return;
    const timer = setTimeout(() => {
      if (!requestLock.current)
        void flushReceipts().catch((e) => {
          if (currentOwner.current === ownerKey) setError(String(e));
        });
    }, 250);
    return () => clearTimeout(timer);
  }, [perceptions.queue, locked, error, save.revision, job?.status]);
  const lastMarkerAttempt = useRef('');
  const markerKey = 'phone-open-pending:' + scope;
  const [pendingMarkers, setPendingMarkers] = useState<Record<string, number>>(() => {
    try {
      return JSON.parse(sessionStorage.getItem(markerKey) || '{}');
    } catch {
      return {};
    }
  });
  useLayoutEffect(() => {
    sessionStorage.setItem(markerKey, JSON.stringify(pendingMarkers));
  }, [markerKey, pendingMarkers]);
  const markOpen = (id: string) => {
    if (!phone.badges?.[id]) return;
    const value = phone.markers?.[id] || 0;
    if (value > 0) {
      setPendingMarkers((prev) => ({ ...prev, [id]: value }));
    }
  };
  const wasTab = useRef('home');
  useLayoutEffect(() => {
    if (open && wasTab.current !== tab) markOpen(tab);
    wasTab.current = open ? tab : 'home';
  }, [open, tab]);
  useEffect(() => {
    if (
      locked ||
      requestLock.current ||
      (job?.kind === 'communication' &&
        job.revision === save.revision &&
        ['error', 'stopped'].includes(job.status))
    )
      return;
    const pair = Object.entries(pendingMarkers)[0];
    if (!pair) return;
    const [id, marker] = pair;
    if (!phone.badges?.[id] || (phone.opened?.[id] || 0) >= marker) {
      setPendingMarkers((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      return;
    }
    const attempt = id + ':' + marker + ':' + save.revision;
    if (lastMarkerAttempt.current === attempt) return;
    lastMarkerAttempt.current = attempt;
    void flushReceipts(async (revision) => {
      const operation = phoneOperation('app-open:' + ownerKey, {
        app: id,
        action: 'open',
        actor_id: phone.actor_id,
        marker,
      });
      const next = await api<Save>(`/saves/${save.id}/apps/command`, {
        revision,
        command: operation.payload,
      });
      operation.complete();
      commitReceipt(next);
    }).catch((e) => {
      if (currentOwner.current === ownerKey) setError(String(e));
    });
  }, [pendingMarkers, locked, save.revision, job?.status]);
  const displayBadge = (id: string) => {
    const count = phone.badges?.[id] || 0;
    if (!pendingMarkers[id]) return count;
    return Math.min(count, Math.max(0, (phone.markers?.[id] || 0) - pendingMarkers[id]));
  };
  const writeTo = (id: string) => {
    const r = recipients.find((row) => row.id === id);
    if (r) {
      chooseRecipient(r);
    }
  };
  const dossier = (id: string) => {
    close();
    openCharacter(id);
  };

  return {
    adding,
    address,
    apiKey,
    arrivals,
    avatar,
    away,
    back,
    busy,
    call,
    canSend,
    chatRecipient,
    chooseRecipient,
    close,
    command,
    config,
    contact,
    contactLabels,
    continueMessage,
    conversation,
    currentOwner,
    detail,
    dialing,
    disabled,
    displayBadge,
    dossier,
    visit,
    propose: (value: string) => {
      restoreAfterCall.current = false;
      afterDeviceClosed(() => {
        if (currentOwner.current === ownerKey) chooseAction?.(value);
      });
      setOpen(false);
    },
    drafts,
    editContact,
    endCall,
    error,
    focusKey,
    groupMembers,
    groupName,
    grouping,
    hasReply,
    home,
    inChat,
    input,
    job,
    jobHere,
    label,
    latestOutgoing,
    legacyContacts,
    list,
    listKey,
    listPositions,
    locked,
    matchesSearch,
    membersOpen,
    messageKey,
    messages,
    navigate,
    nested,
    onCommit,
    onJob,
    open,
    openChat,
    ownerKey,
    perform,
    observe: perceptions.observe,
    phone,
    push,
    reading,
    recipient,
    recipientTarget,
    recipients,
    recovery,
    requestLock,
    returnFocus,
    revealComposer,
    route,
    save,
    savedRecipient,
    scope,
    screen,
    search,
    selected,
    send,
    services,
    setAdding,
    setAddress,
    setAway,
    setBusy,
    setContact,
    setConversation,
    setDetail,
    setEditContact,
    setError,
    setGroupMembers,
    setGroupName,
    setGrouping,
    setLabel,
    setMembersOpen,
    setOpen,
    setRecipient,
    setSearch,
    setTab,
    setText,
    status,
    tab,
    target,
    text,
    title,
    trigger,
    unread,
    visibleRecipients,
    writeTo,
  };
}
const Device = createContext<ReturnType<typeof usePhone> | null>(null);
export const DeviceProvider = Device.Provider;
export function useDevice() {
  const value = useContext(Device);
  if (!value) throw new Error('Телефон закрыт');
  return value;
}
