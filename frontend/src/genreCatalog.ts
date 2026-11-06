import catalog from '../../backend/runtime_v3/genre_catalog.json';
import {gameLocale} from './gameDate';
export type GenreConfig={primary_genre:string|null;secondary_genres:string[];custom_genre:string};
export const genreCatalog=catalog.genres;
export const genreGroups=catalog.groups;
export const genres:Record<string,string>=Object.fromEntries(genreCatalog.map(g=>[g.id,g.ru.name]));
export const descriptions:Record<string,string>=Object.fromEntries(genreCatalog.map(g=>[g.id,g.ru.description]));
export const genreLabels=()=>Object.fromEntries(genreCatalog.map(g=>[g.id,g[gameLocale().startsWith('en')?'en':'ru'].name]));
const normalize=(text:string)=>text.toLocaleLowerCase().replaceAll('ё','е').replaceAll(/[_-]/g,' ').trim();
export function matchingGenres(query:string,group:string){
 const terms=normalize(query).split(/\s+/).filter(Boolean);
 return genreCatalog.filter(g=>(group==='all'||group===g.group)&&terms.every(term=>normalize([g.id,g.ru.name,g.en.name,...g.aliases].join(' ')).includes(term)));
}
export function selectPrimary(value:GenreConfig,id:string|null):GenreConfig{
 return {...value,primary_genre:id,secondary_genres:value.secondary_genres.filter(g=>g!==id)};
}
export function toggleSecondary(value:GenreConfig,id:string):GenreConfig{
 if(value.secondary_genres.includes(id))return {...value,secondary_genres:value.secondary_genres.filter(g=>g!==id)};
 if(value.primary_genre===id||value.secondary_genres.length>=3)return value;
 return {...value,secondary_genres:[...value.secondary_genres,id]};
}
