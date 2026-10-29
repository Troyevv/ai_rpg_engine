import {gameLocale} from '../gameDate';
// Same locale-keyed label convention as dossier/social. No runtime semantics depend on labels.
const ru = {
  directory:'Адресаты', savedContacts:'Сохранённые', allRecipients:'Все персонажи',
  searchRecipient:'Поиск адресата', searchPlaceholder:'Имя или сохранённая подпись',
  directoryHint:'Можно обратиться без знакомства и сохранённого контакта. Ответ остаётся за собеседником.',
  noRecipients:'Адресаты не найдены.', write:'Написать', call:'Позвонить',
  writeTo:'Написать:', callTo:'Позвонить:', newMessage:'Новое сообщение',
  recipientUnavailable:'Новое обращение недоступно. История сохранена.',

  scene: 'Сцена звонка', minimize: 'Свернуть звонок', end: 'Завершить звонок',
  restore: 'Вернуться к звонку', history: 'Разговор из журнала', close: 'Закрыть разговор',
  input: 'Реплика в звонке', send: 'Сказать собеседнику', connected: 'Соединение установлено',
  ended: 'Разговор завершён', physical: 'Действия рядом — в основной сцене', latest: 'К последней реплике',
  plans: 'Планы и договорённости',
  physicalReconciled:'Неподтверждённые изменения окружения не применены. Актуальная физическая сцена — в основной истории. Можно продолжить своим действием.',
  callApplyFailed:'Не удалось сохранить последствия разговора. Можно повторить.',
  responseFailed:'Не удалось завершить ответ. Вернись к разговору, чтобы продолжить.',
  restoreSpeech:'Вернуть реплику в поле ввода', dialing:'Соединяем…',
  callWaiting:'Собеседник готовит ответ…', callStreaming:'Собеседник говорит…',
  callApplying:'Сохраняем последствия разговора…', callReconnecting:'Восстанавливаем связь…',
  callStopped:'Ответ остановлен. Разговор остаётся открытым.', callStop:'Остановить ответ',
  waiting:'Ожидаем ответа…', failed:'Не получилось. Попробуй ещё раз.',
  reactionFailed:'Не удалось получить ответ. Можно повторить.',retry:'Повторить',
};
const en:typeof ru={
  directory:'Recipients', savedContacts:'Saved', allRecipients:'All characters',
  searchRecipient:'Find a recipient', searchPlaceholder:'Name or saved label',
  directoryHint:'No introduction or saved contact needed. The recipient may choose not to reply.',
  noRecipients:'No recipients found.', write:'Message', call:'Call',
  writeTo:'Message:', callTo:'Call:', newMessage:'New message',
  recipientUnavailable:'New messages are unavailable. History is preserved.',
physicalReconciled:"Unconfirmed changes to the surroundings were not applied. The main story shows the current physical scene. You can continue with your own action.",callApplyFailed:'Could not save the conversation’s consequences. You can retry.',responseFailed:'Could not finish the response. Return to the conversation to continue.',restoreSpeech:'Restore speech to the input',dialing:'Connecting…',callWaiting:'Waiting for the caller’s response…',callStreaming:'The caller is speaking…',callApplying:'Saving the conversation’s consequences…',callReconnecting:'Reconnecting…',callStopped:'Response stopped. The call is still open.',callStop:'Stop response',waiting:'Waiting for a reply…',failed:'Could not complete this. Try again.',reactionFailed:'Could not receive a reply. You can retry.',retry:'Retry',scene:'Call scene',minimize:'Minimize call',end:'End call',restore:'Return to call',history:'Call history',close:'Close conversation',input:'Call speech',send:'Speak to caller',connected:'Connected',ended:'Call ended',physical:'Physical actions in the main scene',latest:'Latest reply',plans:'Plans and agreements'};
export const phoneText = (key: keyof typeof ru) => (gameLocale().startsWith('en')?en:ru)[key];
