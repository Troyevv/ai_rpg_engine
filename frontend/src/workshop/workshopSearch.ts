/** Index only the currently authorized server projection. */
type Item=Record<string,unknown>;
export type SearchEntry={id:string;kind:string;label:string;type:string;text:string};
export function workshopSearch(state:{characters:Item[];locations:Item[];world:Record<string,Record<string,Item>>}|null|undefined,query:string):SearchEntry[]{
 if(!state)return [];
 const entries:SearchEntry[]=[];
 const push=(kind:string,type:string,id:string,item:Item)=>{const label=String(item.name||item.text||item.description||'Без названия');entries.push({kind,type,id,label,text:[label,item.text,item.description,item.context,...Array.isArray(item.aliases)?item.aliases:[],...Object.values(item.fields as Item||{})].filter(Boolean).join(' ').toLocaleLowerCase('ru')})};
 state.characters.forEach(c=>push('character','Персонаж',String(c.id),c));state.locations.forEach(l=>push('location','Место',String(l.id),l));
 for(const [group,kind,type] of [['organizations','organizations','Сообщество'],['threads','thread','Сюжетная линия'],['facts','fact','Факт']])Object.entries(state.world[group]||{}).forEach(([id,item])=>push(kind,type,id,item));
 const q=query.trim().toLocaleLowerCase('ru');return entries.filter(e=>!q||e.text.includes(q)).slice(0,q?30:20);
}
