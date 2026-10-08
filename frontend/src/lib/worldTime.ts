export type WorldCalendar={start_minute:number;start_weekday:number;start_date?:string|null;labels?:Record<string,string>};
export function worldTime(minute:number|null|undefined,calendar?:WorldCalendar){
 if(minute==null)return 'Время не зафиксировано';
 if(calendar?.labels?.[String(minute)])return calendar.labels[String(minute)];
 const day=Math.floor(minute/1440)-Math.floor((calendar?.start_minute||0)/1440);
 const weekday=((calendar?.start_weekday||0)+day)%7;
 return `День ${day+1} · ${['Пн','Вт','Ср','Чт','Пт','Сб','Вс'][(weekday+7)%7]} · ${String(Math.floor(minute%1440/60)).padStart(2,'0')}:${String(minute%60).padStart(2,'0')}`;
}
