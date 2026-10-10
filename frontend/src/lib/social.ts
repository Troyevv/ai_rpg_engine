// Presentation labels follow the existing lib/relationships.ts localization boundary.
const social:Record<string,string>={spouse:'Брак',partner:'Партнёрство',engaged:'Помолвка',parent:'Родитель → ребёнок',adoptive_parent:'Приёмный родитель → ребёнок',guardian:'Опека',foster_parent:'Приёмная семья',step_parent:'Отчим / мачеха',sibling:'Брат / сестра',half_sibling:'Неполнородные брат / сестра',ancestor:'Предок',contact:'Знакомство',friend:'Дружба',close_friend:'Близкая дружба',coworker:'Коллеги',ended:'Завершено',divorced:'Развод',widowed:'Смерть супруга',superseded:'Сменился статус',revoked:'Прекращено'};
export const socialLabel=(value:string)=>social[value]||'Связь';
export const lifeLabel=(value:string)=>({alive:'Жив',dead:'Умер',missing:'Пропал',unknown:'Неизвестно'}[value]||'Неизвестно');

export const phaseLabel=(value:string)=>({active:'Действует',closed:'Завершено',replaced:'Заменено',organization_closed:'Организация закрыта',ended:'Завершено',graduated:'Выпуск',completed:'Завершено',resigned:'Увольнение по собственному желанию',fired:'Увольнение',expelled:'Отчисление',retired:'Выход на пенсию'}[value]||'Завершено');
