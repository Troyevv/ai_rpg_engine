import { Work } from './apps/Work';
import { Events } from './apps/Events';
import { Questions } from './apps/Questions';
import { News } from './apps/News';
import type { ComponentType } from 'react';
import { appArtwork } from './AppArtwork';
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
  icon: ComponentType<{ size?: number }>;
  screen: ComponentType;
  openNotice?: (device: ReturnType<typeof useDevice>, id: string) => void;
  available: (capabilities: PhoneState['capabilities']) => boolean;
}

export const apps: readonly PhoneApp[] = [
  { id: 'calls', title: 'Звонки', icon: appArtwork('calls'), screen: Calls, available: (c) => c.voice_call },
  {
    id: 'messages',
    title: 'Чаты',
    icon: appArtwork('messages'),
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
    icon: appArtwork('contacts'),
    screen: Contacts,
    available: (c) => c.text_message || c.voice_call,
  },
  { id: 'social', title: 'Соцсеть', icon: appArtwork('social'), screen: Social, available: (c) => !!c.social },
  { id: 'dating', title: 'Знакомства', icon: appArtwork('dating'), screen: Dating, available: (c) => !!c.dating },
  { id: 'news', title: 'Новости', icon: appArtwork('news'), screen: News, available: (c) => !!c.social },
  { id: 'questions', title: 'Вопросы', icon: appArtwork('questions'), screen: Questions, available: (c) => !!c.social },
  {
    id: 'events',
    title: 'Афиша',
    icon: appArtwork('events'),
    screen: Events,
    available: (c) => !!c.social && c.text_message,
  },
  {
    id: 'work',
    title: 'Работа и вакансии',
    icon: appArtwork('work'),
    screen: Work,
    available: (c) => !!c.social && c.text_message,
  },
];
