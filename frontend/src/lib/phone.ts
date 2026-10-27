import {gameLocale} from '../gameDate';
// Same locale-keyed label convention as dossier/social. No runtime semantics depend on labels.
const ru = {
  scene: 'Сцена звонка', minimize: 'Свернуть звонок', end: 'Завершить звонок',
  restore: 'Вернуться к звонку', history: 'Разговор из журнала', close: 'Закрыть разговор',
  input: 'Реплика в звонке', send: 'Сказать собеседнику', connected: 'Соединение установлено',
  ended: 'Разговор завершён', physical: 'Действия рядом — в основной сцене', latest: 'К последней реплике',
  plans: 'Планы и договорённости',
};
const en:typeof ru={scene:'Call scene',minimize:'Minimize call',end:'End call',restore:'Return to call',history:'Call history',close:'Close conversation',input:'Call speech',send:'Speak to caller',connected:'Connected',ended:'Call ended',physical:'Physical actions in the main scene',latest:'Latest reply',plans:'Plans and agreements'};
export const phoneText = (key: keyof typeof ru) => (gameLocale().startsWith('en')?en:ru)[key];
