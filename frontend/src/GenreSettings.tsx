import './styles/genre-settings.css';
import {gameLocale} from './gameDate';
import {Textarea} from './components/ui/textarea';
export type GenreConfig={primary_genre:string|null;secondary_genres:string[];custom_genre:string};
export const genres:Record<string,string>={slice_of_life:'Повседневность',family_saga:'Семейная сага',romance:'Романтика',drama:'Драма',detective:'Детектив',thriller:'Триллер',science_fiction:'Научная фантастика',fantasy:'Фэнтези',horror:'Ужасы',adventure:'Приключения',post_apocalyptic:'Постапокалипсис',historical:'Исторический',custom:'Свой жанр'};
export const descriptions:Record<string,string>={
 slice_of_life:'Повседневные занятия, отношения и небольшие перемены в жизни.',
 family_saga:'История семьи на протяжении лет и поколений. Будущие браки, дети и переходы героя заранее не определены.',
 romance:'Сближение и личные отношения, когда они согласуются с желаниями персонажей и вашим замыслом.',
 drama:'Внутренние противоречия и сложные отношения без обязательной трагедии.',
 detective:'Наблюдения, улики и поиск объяснений. Преступление не обязательно.',
 thriller:'Ожидание, неопределённость и напряжение без предрешённого насилия.',
 science_fiction:'Научные идеи, технологии и их влияние на жизнь общества.',
 fantasy:'Необычный мир и возможное волшебство в пределах заданных правил.',
 horror:'Неизвестность и тревожная атмосфера. Не задаёт уровень риска или обязательные травмы.',
 adventure:'Открытия, путешествия и новые обстоятельства без обязательного героического подвига.',
 post_apocalyptic:'Жизнь после крупных перемен мира; причины и последствия определяет ваш замысел.',
 historical:'Жизнь в выбранной эпохе. Страна, даты и биографии не выводятся из названия жанра.',
 custom:'Направление задаётся вашим описанием ниже.'};

const enGenres:Record<string,string>={slice_of_life:'Everyday life',family_saga:'Family saga',romance:'Romance',drama:'Drama',detective:'Detective',thriller:'Thriller',science_fiction:'Science fiction',fantasy:'Fantasy',horror:'Horror',adventure:'Adventure',post_apocalyptic:'Post-apocalyptic',historical:'Historical',custom:'Custom genre'};
const enDescriptions:Record<string,string>={slice_of_life:'Everyday activities, relationships and small changes.',family_saga:'Family ties across generations, without predetermined marriages or children.',romance:'Closeness and relationships consistent with character intentions.',drama:'Conflicting values and relationships without mandatory tragedy.',detective:'Clues and competing explanations; crime is optional.',thriller:'Suspense and uncertainty without predetermined violence.',science_fiction:'Science, technology and their human consequences.',fantasy:'Wonder within the established rules of the world.',horror:'Unease and the unknown; does not set risk or require injuries.',adventure:'Discovery and exploration without mandatory heroism.',post_apocalyptic:'Life after major disruption; the world defines its causes.',historical:'Life in the established era, without inventing dates or biographies.',custom:'Themes from your description below.'};
export const genreLabels=()=>gameLocale().startsWith('en')?enGenres:genres;
export const genreFutureHint=()=>gameLocale().startsWith('en')?'Genre changes affect new turns only. Regeneration uses the original turn settings.':'Смена жанров влияет только на новые ходы. Перегенерация использует исходные настройки хода.';
export function GenreSettings({value,onChange,disabled=false,creation=false}:{value:GenreConfig;onChange:(value:GenreConfig)=>void;disabled?:boolean;creation?:boolean}){
 const en=gameLocale().startsWith('en'); const names=genreLabels(); const details=en?enDescriptions:descriptions;
 const change=(patch:Partial<GenreConfig>)=>onChange({...value,...patch});
 const custom=[value.primary_genre,...value.secondary_genres].includes('custom');
 return <fieldset disabled={disabled} className="genre-settings">
  <legend>{en?'Story genres':'Жанры истории'}</legend>
  <p>{en?'The primary genre sets the main emphasis; secondary genres add accents. Unexpected off-genre events remain possible. Genres do not change risk or character decisions.':'Основной жанр задаёт главный акцент, дополнительные — оттенки. Неожиданные события вне жанра возможны. Жанры не меняют риск и решения персонажей.'}</p>
  <label>{en?'Primary genre':'Основной жанр'}<select aria-label={en?'Primary genre':'Основной жанр'} className="w-full" value={value.primary_genre||''} onChange={e=>change({primary_genre:e.target.value||null,secondary_genres:value.secondary_genres.filter(g=>g!==e.target.value)})}>
   <option value="">{creation?(en?'From world description':'Из описания мира'):(en?'No primary genre':'Без основного жанра')}</option>{Object.entries(names).map(([id,name])=><option key={id} value={id}>{name}</option>)}
  </select></label>
  {value.primary_genre&&<p aria-label={en?'Primary genre description':'Описание основного жанра'}>{details[value.primary_genre]}</p>}
  <fieldset className="genre-secondary"><legend>{en?'Secondary genres · up to three':'Дополнительные жанры · до трёх'}</legend>{Object.entries(names).map(([id,name])=><label key={id} className="check"><input type="checkbox" checked={value.secondary_genres.includes(id)} disabled={disabled||id===value.primary_genre||value.secondary_genres.length>=3&&!value.secondary_genres.includes(id)} onChange={e=>change({secondary_genres:e.target.checked?[...value.secondary_genres,id]:value.secondary_genres.filter(g=>g!==id)})}/>{name}</label>)}</fieldset>
  {value.secondary_genres.map(id=><p key={id} aria-label={(en?'Genre description ':'Описание жанра ')+names[id]}><strong>{names[id]}: </strong>{details[id]}</p>)}
  {custom&&<label>{en?'Custom genre description':'Описание своего жанра'}<Textarea required value={value.custom_genre} maxLength={2000} onChange={e=>change({custom_genre:e.target.value})}/>{!value.custom_genre.trim()&&<span role="alert">{en?'Add a custom genre description.':'Добавьте описание своего жанра.'}</span>}</label>}
 </fieldset>
}
