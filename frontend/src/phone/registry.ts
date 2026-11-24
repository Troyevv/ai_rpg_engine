import type {ComponentType} from 'react';
import {Phone, MessagesSquare, ContactRound, Orbit, Heart, type LucideIcon} from 'lucide-react';
import {Calls} from './apps/Calls';
import {Chats} from './apps/Chats';
import {Contacts} from './apps/Contacts';
import {Social} from './apps/Social';
import {Dating} from './apps/Dating';
import type {useDevice} from './usePhone';
import type {PhoneState} from './types';

export interface PhoneApp {
  id:string;
  title:string;
  icon:LucideIcon;
  screen:ComponentType;
  openNotice?:(device:ReturnType<typeof useDevice>,id:string)=>void;
  available:(capabilities:PhoneState['capabilities'])=>boolean;
}

export const apps:readonly PhoneApp[]=[
  {id:'calls',title:'Звонки',icon:Phone,screen:Calls,available:c=>c.voice_call},
  {id:'messages',title:'Чаты',icon:MessagesSquare,screen:Chats,available:c=>c.text_message,openNotice:(d,id)=>{const c=d.phone.conversations.find(c=>c.id===id);if(c)void d.openChat(c)}},
  {id:'contacts',title:'Контакты',icon:ContactRound,screen:Contacts,available:c=>c.text_message||c.voice_call},
  {id:'social',title:'Соцсеть',icon:Orbit,screen:Social,available:c=>!!c.social},
  {id:'dating',title:'Знакомства',icon:Heart,screen:Dating,available:c=>!!c.dating},
];
