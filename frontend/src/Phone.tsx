import {phoneText as t} from "./lib/phone";
import {phoneOperation} from "./lib/phoneRequests";
import { formatDateLabel } from "./gameDate";
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import {
  Phone as PhoneIcon,
  MessageCircle,
  ContactRound,
  X, ArrowLeft, Send, Users, Plus, ArrowDown,
} from "lucide-react";
import { Button } from "./components/ui/button";
import { PhoneChatList, PhoneMessages } from "./PhoneContent";
import { api } from "./api";
import { active, type Save, type Job, type ModelConfig } from "./types";
import { CharacterAvatar, type PortraitSubject } from "./Portrait";
import "./styles/phone.css";

type Recipient = { id: string; search_name?: string; subject: PortraitSubject; can_send: boolean; can_call: boolean };
type Contact = {
  can_send?: boolean;
  awaiting_response?: boolean;
  can_call?: boolean;
  id: string;
  label: string;
  address: string;
  blocked: boolean;
  available: boolean;
  subject: PortraitSubject;
};
export type Conversation = {
  id: string;
  title: string;
  group: boolean;
  contact_id: string | null;
  active: boolean;
  can_send?: boolean;
  awaiting_response?: boolean;
  participants: PortraitSubject[];
};
export type PhoneEvent = {
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
  sender?: PortraitSubject;
  destination: string;
};
export type PhoneState = {
  actor_id: string;
  capabilities: { text_message: boolean; voice_call: boolean; ring_timeout_minutes: number };
  contacts: Contact[];
  recipients?: Recipient[];
  conversations: Conversation[];
  events: PhoneEvent[];
  focus: "physical" | "call";
  emergency: { service: string; number: string | null }[];
};
const status: Record<string, string> = {
  sent: "Отправлено",
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
  onBusyChange,
  config, apiKey, onJob, job: receivedJob,
}: {
  save: Save;
  disabled: boolean;
  onCommit: (save: Save) => void;
  onBusyChange: (busy: boolean) => void;
  config: ModelConfig;
  apiKey: string;
  onJob: (job: Job) => void;
  job: Job | null;
}) {
  const phone = save.state.phone;
  const job=receivedJob?.presentation?.actor_id&&receivedJob.presentation.actor_id!==phone?.actor_id?null:receivedJob;
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
  const requestLock = useRef(false);
  const autoReadAttempt = useRef<string | null>(null);
  const currentOwner = useRef(ownerKey); currentOwner.current = ownerKey;
  const [membersOpen, setMembersOpen] = useState(false);
  const [away, setAway] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const listPositions = useRef<Record<string, number>>({});
  const returnFocus = useRef<HTMLElement | null>(null);
  const focusKey = useRef<string | null>(null);
  const [detail, setDetail] = useState<string | null>(null);
  const [recipient, setRecipient] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [entry, setEntry] = useState(true);
  const messages = useRef<HTMLDivElement>(null);
  const reading = useRef<Record<string,{top:number;pinned:boolean}>>({});

  useEffect(()=>{const close=()=>setOpen(false);window.addEventListener("save-workspace-opened",close);return()=>window.removeEventListener("save-workspace-opened",close)},[]);
  useEffect(()=>{const show=()=>{if(phone)setOpen(true)};window.addEventListener("phone-open",show);return()=>window.removeEventListener("phone-open",show)},[phone]);
  const [open, setOpen] = useState(false),
    [tab, setTab] = useState("contacts");
  const [conversation, setConversation] = useState<string | null>(null),
    [contact, setContact] = useState<string | null>(null);
  const [text, setText] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  // Phone mutations share the save revision with turns and control changes.
  // Keep the parent locked even when the phone is closed before a response arrives.
  useLayoutEffect(() => {
    onBusyChange(busy);
    return () => onBusyChange(false);
  }, [busy, onBusyChange]);
  const [editContact, setEditContact] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [adding, setAdding] = useState(false),
    [grouping, setGrouping] = useState(false);
  const [groupMembers, setGroupMembers] = useState<string[]>([]),
    [groupName, setGroupName] = useState("");
  const messageKey = `${save.id}:${phone?.actor_id}:${conversation || contact || recipient || ""}`;
  const currentMessage = useRef(messageKey); currentMessage.current = messageKey;
  useEffect(() => {
    setText(drafts.current[messageKey] || sessionStorage.getItem(`phone-draft:${messageKey}`) || "");
  }, [messageKey]);
  const revealComposer = () => {
    const viewport = screen.current;
    const form = viewport?.querySelector<HTMLFormElement>('.phone-composer');
    if (!viewport || !form?.contains(document.activeElement) || !matchMedia('(max-width:767px)').matches) return;
    const bounds = viewport.getBoundingClientRect(), content = form.getBoundingClientRect();
    if (content.bottom > bounds.bottom) viewport.scrollTop += content.bottom - bounds.bottom;
    else if (content.top < bounds.top) viewport.scrollTop -= bounds.top - content.top;
  };
  const back = () => {
    if (membersOpen) { setMembersOpen(false); requestAnimationFrame(()=>screen.current?.querySelector<HTMLElement>('[aria-label="Управление участниками"]')?.focus({preventScroll:true})); return; }
    if (adding) { setAdding(false); return; }
    if (grouping) { setGrouping(false); return; }
    if (tab === 'messages' && (conversation || contact || recipient)) {
      setConversation(null); setContact(null); setRecipient(null);
    } else if (tab === 'contacts' && detail) { setDetail(null); }
    else { close(); return; }
    requestAnimationFrame(() => {
      if (returnFocus.current?.isConnected) returnFocus.current.focus({preventScroll:true});
      else {const target=Array.from(screen.current?.querySelectorAll<HTMLElement>('[data-phone-focus]')||[]).find(el=>el.dataset.phoneFocus===focusKey.current);(target||screen.current)?.focus({preventScroll:true});}
    });
  };
  const backRef = useRef(back); backRef.current = back;
  const close = () => {
    setOpen(false);
    (document.activeElement as HTMLElement | null)?.blur();
    requestAnimationFrame(()=>trigger.current?.focus({preventScroll:true}));
  };
  useEffect(() => {
    if (!open) return;
    screen.current?.focus();
    const resize = new ResizeObserver(revealComposer);
    if (screen.current) resize.observe(screen.current);
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        backRef.current();
      }
    };
    const modal = new MutationObserver(() => {
      if (document.querySelector('[role="dialog"]')) setOpen(false);
    });
    modal.observe(document.body, { childList: true, subtree: true });
    const historyKey = `phone:${ownerKey}`;
    history.pushState({...history.state, phoneUI:historyKey}, '');
    const browserBack = (event: PopStateEvent) => {
      event.stopImmediatePropagation();
      history.pushState({...history.state, phoneUI:historyKey}, '');
      backRef.current();
    };
    window.addEventListener('popstate', browserBack, true);
    document.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener('popstate', browserBack, true);
      if (history.state?.phoneUI === historyKey && !history.state?.phoneCall && !history.state?.saveWorkspace && !history.state?.mobileMenu) {
        // Consume our own entry without closing another surface underneath it.
        window.addEventListener('popstate', event => event.stopImmediatePropagation(), {once:true,capture:true});
        history.back();
      }
      document.removeEventListener("keydown", escape);
      modal.disconnect();
      resize.disconnect();
    };
  }, [open]);
  useEffect(() => {
    setOwner(ownerKey); setMembersOpen(false); setAway(false);
    setDetail(null); setSearch(""); setEntry(true);
    setRecipient(null);
    setOpen(false);
    setContact(null);
    setConversation(null);
    setText("");
    setError("");
    setEditContact(null);
    setAdding(false);
    setTab("contacts");
    setLabel("");
    setGrouping(false);
    setGroupMembers([]);
    setGroupName("");
  }, [save.id, phone?.actor_id]);
  useLayoutEffect(() => {
    if (!open) {autoReadAttempt.current=null;return;}
    if (tab !== 'messages' || !conversation || disabled || busy || requestLock.current || !phone?.events.some(e=>e.conversation_id===conversation&&e.unread)) return;
    const attempt=`${ownerKey}:${conversation}:${save.revision}`;
    if(autoReadAttempt.current===attempt)return;
    autoReadAttempt.current=attempt;
    const owner = ownerKey;
    requestLock.current = true;
    setBusy(true);
    api<Save>(`/saves/${save.id}/phone`, {revision:save.revision, command:{action:'read',conversation_id:conversation,operation_id:crypto.randomUUID()}})
      .then(next=>{if(currentOwner.current===owner)onCommit(next)})
      .catch(e=>{if(currentOwner.current===owner)setError(t("failed"))})
      .finally(()=>{requestLock.current=false;setBusy(false)});
  }, [save.revision, open, tab, conversation, disabled, busy]);
  useLayoutEffect(()=>{const el=messages.current;if(el){const position=reading.current[messageKey];el.scrollTop=position&&!position.pinned?position.top:el.scrollHeight}},[conversation,tab,open,membersOpen,phone?.events.length,save.revision]);
  useLayoutEffect(() => {
    if (input.current) { input.current.style.height='auto'; input.current.style.height=`${Math.min(input.current.scrollHeight, 120)}px`; }
  }, [text, open, conversation, recipient, contact]);
  useLayoutEffect(() => {
    if(open && screen.current && !screen.current.contains(document.activeElement)) screen.current.focus({preventScroll:true});
  }, [open,tab,conversation,contact,recipient,detail,membersOpen,grouping,adding]);
  const listKey = `${ownerKey}:${tab}:${detail || ''}:${grouping}:${membersOpen}`;
  useLayoutEffect(() => { if(list.current) list.current.scrollTop=listPositions.current[listKey] || 0; }, [listKey,open,conversation,contact,recipient]);

  if (!phone || owner !== ownerKey) return null;
  const locked = busy || disabled || save.state.actor_capabilities?.can_act===false || !!save.state.protagonist_required;
  const perform = async (command: Record<string, unknown>) => {
    if (locked || requestLock.current) return;
    requestLock.current = true;
    setBusy(true);
    setError("");
    const owner = ownerKey;
    const key = `phone-request:${owner}`;
    try {
      const request = phoneOperation(key, command);
      const payload = request.payload;
      const automatic = ['send','call'].includes(String(command.action));
      const response = await api<Save | {save:Save;job:Job}>(`/saves/${save.id}/phone${automatic?'/dispatch':''}`, {
        revision: save.revision,
        command: payload,
        ...(automatic ? {config,api_key:apiKey} : {}),
      });
      request.complete();
      if(currentOwner.current!==owner)return;
      const next = 'save' in response ? response.save : response;
      if('job' in response && 'save' in response)onJob(response.job);
      onCommit(next);
      if(command.action==='call'){setTab('calls');setEntry(false)}
      return next;
    } catch (e) {
      if(currentOwner.current===owner)setError(e instanceof Error ? e.message : t("failed"));
    } finally {
      requestLock.current = false;
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
  const recipients = phone.recipients || [];
  const savedRecipient = (r: Recipient) => phone.contacts.find(c => c.subject.id === r.id);
  const matchesSearch = (value: string) => value.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase());
  const visibleRecipients = [...recipients].sort((a,b) => Number(!!savedRecipient(b))-Number(!!savedRecipient(a)))
    .filter(r => matchesSearch(r.subject.name + " " + (r.search_name || "") + " " + phone.contacts.filter(c=>c.subject.id===r.id).map(c=>c.label).join(" ")));
  const legacyContacts = phone.contacts.filter(c => !recipients.some(r => r.id === c.subject.id));
  const recipientTarget = recipients.find(r => r.id === recipient);
  const canSend = selected ? selected.can_send !== false : recipient
    ? !!recipientTarget?.can_send : target?.can_send !== false;
  const chooseRecipient = (r: Recipient) => {
    returnFocus.current=document.activeElement as HTMLElement;
    focusKey.current=returnFocus.current?.dataset.phoneFocus || null;
    const existing = phone.conversations.find(c => !c.group && c.active && c.participants.some(p => p.id === r.id));
    if (existing) { void openChat(existing); return; }
    setRecipient(r.id); setContact(null); setConversation(null);
    setTab("messages"); setEntry(false);
  };
  const openChat = async (c: Conversation) => {
    returnFocus.current=document.activeElement as HTMLElement;
    focusKey.current=returnFocus.current?.dataset.phoneFocus || null;
    setMembersOpen(false);
    setRecipient(null);
    setConversation(c.id);
    setContact(null);
    setTab("messages");
    setEntry(false);
    if (phone.events.some((e) => e.conversation_id === c.id && e.unread))
      await perform({ action: "read", conversation_id: c.id });
  };
  const send = async () => {
    const next = await perform({
      action: "send",
      content: text,
      ...(conversation
        ? { conversation_id: conversation }
        : recipient ? { character_id: recipient } : { contact_id: contact }),
    });
    if (next) {
      const remaining=drafts.current[messageKey]===text?'':(drafts.current[messageKey]||'');
      drafts.current[messageKey]=remaining;
      if(remaining)sessionStorage.setItem(`phone-draft:${messageKey}`,remaining);
      else sessionStorage.removeItem(`phone-draft:${messageKey}`);
      if(currentMessage.current!==messageKey)return;
      setText(current=>current===text?'':current);
      const last = next.state.phone?.events
        .filter((e) => e.channel === "TEXT_MESSAGE" && e.outgoing)
        .at(-1);
      if (last?.conversation_id) {
        const destination=`${ownerKey}:${last.conversation_id}`;
        if(destination!==messageKey&&remaining){drafts.current[destination]=remaining;sessionStorage.setItem(`phone-draft:${destination}`,remaining)}
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
    if(locked||requestLock.current)return;
    requestLock.current=true;setBusy(true);setError('');
    const key=`phone-wait:${ownerKey}:${event.id}`;
    const requestId=sessionStorage.getItem(key)||crypto.randomUUID();sessionStorage.setItem(key,requestId);
    try {
      const result=await api<{job:Job;save:Save}>(`/saves/${save.id}/phone/dispatch`,{revision:save.revision,config,api_key:apiKey,continuation:{source_event_id:event.id,owner_id:phone.actor_id,request_id:requestId}});
      sessionStorage.removeItem(key);
      if(currentOwner.current===ownerKey){onJob(result.job);onCommit(result.save)}
    }catch(e){if(currentOwner.current===ownerKey)setError(t("failed"))}finally{requestLock.current=false;setBusy(false)}
  };
  const latestOutgoing = phone.events.filter(e=>e.outgoing&&e.channel==='TEXT_MESSAGE'&&e.conversation_id===conversation).at(-1);
  const hasReply = !!latestOutgoing && phone.events.slice(phone.events.findIndex(e=>e.id===latestOutgoing.id)+1).some(e=>!e.outgoing&&e.conversation_id===conversation);
  const currentContact = phone.contacts.find(c=>c.id===detail);
  const endCall = async () => {
    if(!call||busy||requestLock.current)return;
    if(job?.kind!=='communication'||job.revision!==save.revision){await perform({action:'end',event_id:call.id});return}
    requestLock.current=true;setBusy(true);
    try {
      if(active(job))await api(`/jobs/${job.id}/stop`,{});
      const next=await api<Save>(`/saves/${save.id}/phone`,{revision:save.revision,command:{action:'end',event_id:call.id,operation_id:crypto.randomUUID()}});
      if(currentOwner.current===ownerKey){onJob({...job,status:'stopped'});onCommit(next)}
    }catch(e){if(currentOwner.current===ownerKey)setError(t("failed"))}finally{requestLock.current=false;setBusy(false)}
  };
  const inChat = tab==='messages' && !!(conversation || contact || recipient);
  const nested = inChat || (tab==='contacts' && !!detail) || grouping;
  const title = membersOpen ? 'Участники группы' : grouping && tab==='messages' ? 'Новая группа' : inChat ? selected?.title || target?.label || recipientTarget?.subject.name : tab==='contacts' ? detail ? currentContact?.label : 'Контакты' : tab==='calls' ? 'Звонки' : 'Переписки';
  const jobHere=job?.kind==='communication'&&(job.presentation?.call_id?tab==='calls':tab==='messages'&&!!conversation&&job.presentation?.conversation_id===conversation);
  return (
    <div
      className="phone-affordance"
      style={{ "--phone-dock-bottom": `${dock}px` } as CSSProperties}
    >

      <div
        className={`phone-device ${open ? "is-open" : ""} ${call?.status === "ringing" ? "is-ringing" : ""}`}
        data-testid="phone-device"
      >
        <button
          ref={trigger}
          className="phone-peek"
          aria-label={`Телефон${unread ? `, непрочитано: ${unread}` : ""}`}
          aria-expanded={open}
          onClick={() => open ? close() : setOpen(true)}
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
          onKeyDown={e=>{
            if(e.key!=='Tab')return;
            const nodes=Array.from(screen.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),summary')||[]).filter(n=>n.getClientRects().length);
            const first=nodes[0], last=nodes.at(-1);
            if(e.shiftKey&&(document.activeElement===first||document.activeElement===screen.current)){e.preventDefault();last?.focus()}
            else if(!e.shiftKey&&(document.activeElement===last||document.activeElement===screen.current)){e.preventDefault();first?.focus()}
          }}
        >
          <header className="phone-top">
            {nested && <Button variant="ghost" size="icon" aria-label={membersOpen ? 'К диалогу' : inChat ? 'К перепискам' : 'Назад'} onClick={back}><ArrowLeft size={20}/></Button>}
            {inChat && !membersOpen && <span className="phone-header-avatar" aria-label="Участники переписки">{selected?.group ? <Users size={24}/> : (selected?.participants.find(p=>p.id!==phone.actor_id) || target?.subject || recipientTarget?.subject) ? avatar((selected?.participants.find(p=>p.id!==phone.actor_id) || target?.subject || recipientTarget?.subject)!) : null}</span>}
            <div className="phone-heading" aria-busy={busy}><strong title={title}>{title}</strong><small>{inChat ? selected?.group ? `${selected.participants.length} участников` : 'Личная переписка' : save.state.characters.find(c=>c.id===phone.actor_id)?.name}</small></div>
            {inChat && selected?.group && selected.active && !membersOpen && <Button variant="ghost" size="icon" aria-label="Управление участниками" onClick={()=>setMembersOpen(true)}><Users size={20}/></Button>}
            <Button variant="ghost" size="icon" aria-label="Свернуть телефон" onClick={close}><X size={20}/></Button>
          </header>
          {error && <div className="phone-error" role="alert"><span>{error}</span><button disabled={busy} onClick={async()=>{
            if(requestLock.current||locked)return;requestLock.current=true;setBusy(true);
            try {const fresh=await api<Save>(`/saves/${save.id}`);if(currentOwner.current===ownerKey){onCommit(fresh);setError('');}}
            catch {if(currentOwner.current===ownerKey)setError(t('failed'))}
            finally {requestLock.current=false;setBusy(false)}
          }}>Обновить состояние</button></div>}
          {jobHere&&active(job)&&<p className="phone-progress" role="status">{call?.status==='ringing'?t('dialing'):t('waiting')}</p>}
          {jobHere&&job&&['error','stopped'].includes(job.status)&&job.revision===save.revision&&<div role="alert" className="phone-progress"><p>{t('reactionFailed')}</p><button disabled={busy} onClick={async()=>{try{onJob(await api<Job>(`/jobs/${job.id}/retry`,{config,api_key:apiKey}))}catch{setError(t('failed'))}}}>{t('retry')}</button></div>}
          {call&&tab==='messages'&&(conversation||contact||recipient)&&<button className="phone-call-link" onClick={()=>setTab('calls')}>{call.status==='ringing'?'Вызов':'Разговор'} · {call.label} →</button>}
          {call && !(tab==='messages'&&(conversation||contact||recipient)) && (
            <section className="phone-call" aria-label="Текущий звонок">
              {avatar(call.subject)}
              <strong>{call.label}</strong>
              <span role="status" aria-live="polite">
                {call.status==='ringing'&&<span className="phone-dialing" aria-hidden="true">● </span>}{status[call.status]} ·{" "}
                {call.outgoing ? "Исходящий" : "Входящий"}
              </span>
              {call.status==='answered'&&<button onClick={()=>{window.dispatchEvent(new CustomEvent('phone-call-open',{detail:call.id}))}}>Перейти к разговору</button>}
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
                  disabled={busy || (disabled && !(job?.kind==='communication'&&job.revision===save.revision))}
                  onClick={() => void endCall()}
                >
                  {call.status==='ringing'?'Отменить вызов':'Завершить разговор'}
                </button>
              )}
            </section>
          )}
          <div ref={list} onScroll={e=>{listPositions.current[listKey]=e.currentTarget.scrollTop}} className={`phone-body ${inChat && !membersOpen ? 'phone-chat' : ''}`}>
            {entry&&unread>0&&<section className="phone-notifications"><h3>Новые сообщения · {unread}</h3>{phone.conversations.filter(c=>phone.events.some(e=>e.conversation_id===c.id&&e.unread)).map(c=><button key={c.id} onClick={()=>void openChat(c)}>{c.title}<small>Открыть сообщение</small></button>)}</section>}
            {tab === "contacts" && (
              <>
                {!detail&&<>
                  <label className="phone-search">{t("searchRecipient")}<input type="search" value={search} onChange={e=>setSearch(e.target.value)} placeholder={t("searchPlaceholder")}/></label>
                  <section className="phone-directory" aria-label={t("directory")}>
                    {visibleRecipients.map(r=>{
                      const saved = savedRecipient(r);
                      return <article className="phone-row phone-recipient" key={r.id}>
                        {avatar(r.subject)}
                        <button className="phone-contact-name" data-phone-focus={`recipient:${r.id}`} disabled={locked||(!saved&&!r.can_send)} onClick={()=>{if(saved){returnFocus.current=document.activeElement as HTMLElement;focusKey.current=`recipient:${r.id}`;setDetail(saved.id);setEntry(false)}else chooseRecipient(r)}}>
                          <strong>{saved?.label || r.subject.name}</strong>
                          {saved && saved.label !== r.subject.name && <small>{r.subject.name}</small>}
                        </button>
                        <div className="phone-recipient-actions">
                          {phone.capabilities.text_message&&<button title={t("write")} aria-label={t("writeTo")+" "+r.subject.name} disabled={locked||!r.can_send} onClick={()=>chooseRecipient(r)}><MessageCircle size={18} aria-hidden="true"/></button>}
                          {phone.capabilities.voice_call&&<button title={t("call")} aria-label={t("callTo")+" "+r.subject.name} disabled={locked||!!call||!r.can_call} onClick={()=>void perform({action:"call",character_id:r.id})}><PhoneIcon size={18} aria-hidden="true"/></button>}
                        </div>
                      </article>;
                    })}
                    {!visibleRecipients.length&&!legacyContacts.some(c=>matchesSearch(c.label+' '+c.address))&&<p role="status">{t("noRecipients")}</p>}
                  </section>
                </>}

                {adding && (
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      void perform({
                        action: "edit_contact",
                        contact_id: editContact,
                        label,
                        blocked:
                          phone.contacts.find((c) => c.id === editContact)
                            ?.blocked || false,
                      }).then((next) => {
                        if (next) {
                          setAdding(false);
                          setLabel("");
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
                    <button disabled={locked}>Сохранить контакт</button>
                  </form>
                )}
                {(detail?phone.contacts.filter(c=>c.id===detail):legacyContacts.filter(c=>matchesSearch(c.label+' '+c.address))).map((c) => (
                  <article className={`phone-row ${detail?'phone-contact-detail':''}`} key={c.id}>
                    {avatar(c.subject)}
                    <div>
                      <button className="phone-contact-name" onClick={()=>{setDetail(c.id);setEntry(false)}}><strong>{c.label}</strong></button>
                      <small>
                        {c.address}
                        {c.blocked
                          ? " · заблокирован"
                          : !c.available
                            ? " · недоступен"
                            : ""}
                      </small>
                    </div>
                    {detail===c.id&&<div className="phone-contact-actions">
                      {phone.capabilities.text_message && (
                        <button
                          disabled={locked || c.can_send === false}
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
                              setRecipient(null);
                              setContact(c.id);
                              setConversation(null);
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
                            locked || !!call || c.can_call === false
                          }
                          onClick={() =>
                            void perform({ action: "call", contact_id: c.id })
                          }
                        >
                          Позвонить
                        </button>
                      )}
                      <details className="phone-contact-manage"><summary>Управление контактом</summary><button
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
                      </button></details>
                    </div>}
                  </article>
                ))}
                {!detail&&<h3>Экстренные службы · в игре</h3>}
                {!detail&&phone.emergency.map((e) => (
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
                {!conversation && !contact && !recipient ? (
                  <>
                    {!grouping && <div className="phone-list-actions"><Button variant="secondary" onClick={()=>{setTab("contacts");setDetail(null);setSearch("")}}><Plus size={18}/>{t("newMessage")}</Button>
                    <Button variant="ghost" onClick={() => setGrouping(true)}><Users size={18}/>Создать группу</Button></div>}
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
                          <legend>{t("directory")}</legend>
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
                                        : groupMembers.filter(
                                            (id) => id !== c.subject.id,
                                          ),
                                    )
                                  }
                                />
                                {c.subject.name}
                              </label>
                            ))}
                        </fieldset>
                        <button disabled={locked || !groupMembers.length}>
                          Создать переписку
                        </button>
                      </form>
                    )}
                    {!grouping && <PhoneChatList phone={phone} saveId={save.id} openChat={openChat}/>}

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
                                  action: "remove",
                                  conversation_id: selected.id,
                                  member_ids: [p.id],
                                })
                              }
                            >
                              Удалить: {p.name}
                            </button>
                          ))}
                        {recipients
                          .filter(
                            (c) =>
                              c.can_send &&
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
                    {!membersOpen && <>
                    <div ref={messages} className="phone-messages" aria-label="Сообщения" onScroll={e=>{const el=e.currentTarget;const pinned=el.scrollHeight-el.scrollTop-el.clientHeight<32;reading.current[messageKey]={top:el.scrollTop,pinned};setAway(!pinned)}}>
                      <PhoneMessages events={phone.events.filter(e=>e.channel==='TEXT_MESSAGE'&&!!conversation&&e.conversation_id===conversation)} group={!!selected?.group} locked={locked} read={id=>void perform({action:'read',event_id:id})}/>
                    </div>
                    {away && <button className="phone-latest" onClick={()=>{const el=messages.current;if(el){el.scrollTop=el.scrollHeight;reading.current[messageKey]={top:el.scrollTop,pinned:true};setAway(false)}}}><ArrowDown size={16}/>К последнему сообщению</button>}
                    {selected?.awaiting_response&&<p className="phone-response-wait" role="status">Ждут твоего ответа</p>}
                    {!canSend&&<p className="muted" role="status">{t("recipientUnavailable")}</p>}
                    {phone.capabilities.text_message &&
                      (!selected || selected.active) && (
                        <form className="phone-composer"
                          onFocusCapture={revealComposer}
                          onSubmit={(e) => {
                            e.preventDefault();
                            void send();
                          }}
                        >
                          <div className="phone-compose-row">
                            <textarea ref={input} rows={1} placeholder="Сообщение…"
                              aria-label="Сообщение в телефоне"
                              value={text}
                              onChange={(e) => {
                                setText(e.target.value);
                                drafts.current[messageKey] = e.target.value;
                                sessionStorage.setItem(`phone-draft:${messageKey}`,e.target.value);
                              }}
                              onKeyDown={e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)&&!e.nativeEvent.isComposing){e.preventDefault();e.stopPropagation();if(!locked&&canSend&&text.trim())void send()}}}
                            />
                          <Button type="submit" size="icon" aria-label="Отправить сообщение" disabled={locked || !canSend || !text.trim()}><Send size={20}/></Button>
                          </div>
                          <small className="muted">1 игровая минута · ответ не гарантирован</small>
                          {latestOutgoing&&!hasReply&&!active(job)&&<button type="button" disabled={locked} onClick={()=>void continueMessage(latestOutgoing)}>Подождать ещё · 1 мин</button>}
                        </form>
                      )}
                    </>}
                  </>
                )}
              </>
            )}
            {tab === "calls" && (
              <>
                <p className="phone-section-label">История звонков</p>
                {!phone.events.some(e=>e.channel==='VOICE_CALL')&&<p>Звонков пока нет. Выбери контакт, чтобы позвонить.</p>}
                {phone.events
                  .filter((e) => e.channel === "VOICE_CALL")
                  .slice()
                  .reverse()
                  .map((e) => (
                    <article className={`phone-row phone-call-row ${e.status==='missed'?'is-missed':''}`} key={e.id}>
                      {avatar(e.subject)}
                      <div>
                        <strong>{e.label}</strong>
                        {(e.status==='answered'||(e.status==='ended'&&save.turns.some(turn=>turn.presentation?.call_id===e.id&&turn.assistant_text.trim())))&&<button onClick={()=>{window.dispatchEvent(new CustomEvent('phone-call-open',{detail:e.id}))}}>Читать разговор</button>}
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
                onClick={() => {setTab(key);setEntry(false);setMembersOpen(false);setGrouping(false)}}
              >
                <Icon size={20} /><span>{key==='messages'?'Чаты':label}</span>
                {key === "messages" && unread > 0 && <small>{unread}</small>}
              </button>
            ))}
          </nav>
        </div>
      </div>
    </div>
  );
}
