import { Work } from './apps/Work';
import { Events } from './apps/Events';
import { Questions } from './apps/Questions';
import { News } from './apps/News';
import type { ComponentType } from 'react';
import {
  Phone,
  MessagesSquare,
  ContactRound,
  Orbit,
  Heart,
  Newspaper,
  CalendarDays,
  BriefcaseBusiness,
  CircleHelp,
  type LucideIcon,
} from 'lucide-react';
import { Calls } from './apps/Calls';
import { Chats } from './apps/Chats';
import { Contacts } from './apps/Contacts';
import { Social } from './apps/Social';
import { Dating } from './apps/Dating';
import type { useDevice } from './usePhone';
import type { PhoneState } from './types';

export interface PhoneApp {
  id: string;
  title: string;
  icon: LucideIcon;
  screen: ComponentType;
  openNotice?: (device: ReturnType<typeof useDevice>, id: string) => void;
  available: (capabilities: PhoneState['capabilities']) => boolean;
}

export const apps: readonly PhoneApp[] = [
  { id: 'calls', title: 'Звонки', icon: Phone, screen: Calls, available: (c) => c.voice_call },
  {
    id: 'messages',
    title: 'Чаты',
    icon: MessagesSquare,
    screen: Chats,
    available: (c) => c.text_message,
    openNotice: (d, id) => {
      const c = d.phone.conversations.find((c) => c.id === id);
      if (c) void d.openChat(c);
    },
  },
  {
    id: 'contacts',
    title: 'Контакты',
    icon: ContactRound,
    screen: Contacts,
    available: (c) => c.text_message || c.voice_call,
  },
  { id: 'social', title: 'Соцсеть', icon: Orbit, screen: Social, available: (c) => !!c.social },
  { id: 'dating', title: 'Знакомства', icon: Heart, screen: Dating, available: (c) => !!c.dating },
  { id: 'news', title: 'Новости', icon: Newspaper, screen: News, available: (c) => !!c.social },
  { id: 'questions', title: 'Вопросы', icon: CircleHelp, screen: Questions, available: (c) => !!c.social },
  {
    id: 'events',
    title: 'Афиша',
    icon: CalendarDays,
    screen: Events,
    available: (c) => !!c.social && c.text_message,
  },
  {
    id: 'work',
    title: 'Работа и вакансии',
    icon: BriefcaseBusiness,
    screen: Work,
    available: (c) => !!c.social && c.text_message,
  },
];
