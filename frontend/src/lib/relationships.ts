export const relationshipLabels:Record<string,string>={trust:'Доверие',affection:'Привязанность',respect:'Уважение',irritation:'Раздражение',fear:'Страх',jealousy:'Ревность',attraction:'Влечение'};
export const relationshipLabel=(key:string)=>relationshipLabels[key]||key;
