import { Fragment } from 'react';
import { MessageCircle, Users, Check, CheckCheck } from 'lucide-react';
import { CharacterAvatar } from './Portrait';
import { formatDateLabel } from './gameDate';
import type { PhoneState, PhoneEvent, Conversation } from './Phone';

// These are read-only views of the authorized API projection, never a chat store.
export function messageStatus(event: PhoneEvent) {
  if (event.outgoing && event.read_count) return `Прочитано: ${event.read_count} из ${event.recipient_count}`;
  return ({sent:'Отправлено', delivered:'Доставлено'} as Record<string,string>)[event.status] || event.status;
}
const clock = (label: string) => label.match(/\d{2}:\d{2}/)?.[0] || formatDateLabel(label);
const date = (label: string) => formatDateLabel(label.replace(/\s*\d{2}:\d{2}\s*/, '').replace(/[·,\s]+$/, ''));
export function conversationRows(phone: PhoneState) {
  const latest = new Map<string, {event:PhoneEvent; index:number; unread:number}>();
  phone.events.forEach((event,index)=>{
    if(event.channel!=='TEXT_MESSAGE'||!event.conversation_id)return;
    latest.set(event.conversation_id,{event,index,unread:(latest.get(event.conversation_id)?.unread||0)+Number(event.unread)});
  });
  return phone.conversations.map(conversation=>({conversation,...latest.get(conversation.id)}))
    .sort((a,b)=>(b.event?.world_time ?? -Infinity)-(a.event?.world_time ?? -Infinity)||(b.index??-1)-(a.index??-1));
}
export function PhoneChatList({phone,saveId,openChat}:{phone:PhoneState;saveId:number;openChat:(c:Conversation)=>void}) {
  if(!phone.conversations.length)return <div className="phone-empty"><MessageCircle size={32}/><strong>Здесь начнётся разговор</strong><p>Выбери адресата или создай группу.</p></div>;
  return <div className="phone-conversations">{conversationRows(phone).map(({conversation:c,event,unread})=><button className="phone-thread" data-phone-focus={`chat:${c.id}`} key={c.id} onClick={()=>openChat(c)}>
    <span className="phone-thread-avatar">{c.group?<Users size={24}/>:<CharacterAvatar subject={c.participants.find(p=>p.id!==phone.actor_id)||{id:'',name:c.title,silhouette:'neutral'}} saveId={saveId} size={44}/>}</span>
    <span className="phone-thread-copy"><strong>{c.title}</strong><span className="phone-preview">{c.awaiting_response ? 'Ждут твоего ответа' : event ? event.content===null ? 'Непрочитанное сообщение' : `${event.outgoing?'Ты: ':c.group?`${event.sender?.name||'Неизвестный участник'}: `:''}${event.content}` : 'Сообщений пока нет'}</span></span>
    <span className="phone-thread-meta">{event&&<time title={formatDateLabel(event.time_label)}>{clock(event.time_label)}</time>}{event?.outgoing&&<span role="img" aria-label={messageStatus(event)} title={messageStatus(event)}>{event.read_count||event.status==='delivered'?<CheckCheck size={15}/>:<Check size={15}/>}</span>}{!!unread&&<span className="phone-unread" aria-label={`Непрочитано: ${unread}`}>{unread}</span>}</span>
  </button>)}</div>;
}
export function PhoneMessages({events,group,locked,read}:{events:PhoneEvent[];group:boolean;locked:boolean;read:(id:string)=>void}) {
  if(!events.length)return <div className="phone-empty"><MessageCircle size={28}/><p>Сообщений пока нет.</p></div>;
  return <>{events.map((event,index)=><Fragment key={event.id}>
    {(!index||date(events[index-1].time_label)!==date(event.time_label))&&<div className="phone-day"><time>{date(event.time_label)}</time></div>}
    <article className={`phone-message ${event.outgoing?'outgoing':'incoming'}`} data-event-id={event.id}>
      {group&&!event.outgoing&&<strong className="phone-message-sender">{event.sender?.name||'Неизвестный участник'}</strong>}
      <p>{event.content ?? 'Непрочитанное сообщение'}</p>
      <footer><time title={formatDateLabel(event.time_label)}>{clock(event.time_label)}</time><span>{messageStatus(event)}</span></footer>
      {event.unread&&<button disabled={locked} onClick={()=>read(event.id)}>Прочитать</button>}
    </article>
  </Fragment>)}</>;
}
