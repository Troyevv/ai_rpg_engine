import {act,useState} from 'react';
import {createRoot,type Root} from 'react-dom/client';
import {afterEach,expect,it} from 'vitest';
import {GenreSettings} from '../src/GenreSettings';
import {genreCatalog,matchingGenres,selectPrimary,toggleSecondary,type GenreConfig} from '../src/genreCatalog';
let root:Root;let host:HTMLDivElement;
const empty:GenreConfig={primary_genre:null,secondary_genres:[],custom_genre:''};
afterEach(async()=>{if(root)await act(()=>root.unmount());document.body.innerHTML='';document.documentElement.lang='ru'});
async function mount(initial=empty,disabled=false){
 host=document.createElement('div');document.body.append(host);root=createRoot(host);
 function Example(){const [value,setValue]=useState(initial);return <><GenreSettings value={value} onChange={setValue} disabled={disabled}/><output>{JSON.stringify(value)}</output></>}
 await act(()=>root.render(<Example/>));
 await act(()=>host.querySelector<HTMLButtonElement>('.genre-group-picker .atelier-disclosure-trigger')!.click());
 await act(()=>host.querySelector<HTMLButtonElement>('.genre-groups button')!.click());
}
const button=(label:string)=>Array.from(host.querySelectorAll('button')).find(b=>b.getAttribute('aria-label')===label||b.textContent===label)!;
const click=async(label:string)=>{await act(()=>button(label).click())};
const state=()=>JSON.parse(host.querySelector('output')!.textContent!);
it('has stable IDs, bilingual copy, groups and useful normalized aliases',()=>{
 expect(genreCatalog).toHaveLength(38);
 for(const [query,id] of [['темное фентези','dark_fantasy'],['sci-fi','science_fiction'],['чёрный юмор','black_comedy'],['business drama','business_drama'],['космоопера','space_opera']])expect(matchingGenres(query,'all').map(g=>g.id)).toContain(id);
 expect(matchingGenres('music','fantasy')).toEqual([]);
 expect(matchingGenres('unknown','all')).toEqual([]);
 for(const row of genreCatalog){expect(row.ru.description).toBeTruthy();expect(row.en.description).toBeTruthy()}
});
it('promotes secondary without duplicates and preserves unselected custom text',()=>{
 const v={primary_genre:'romance',secondary_genres:['music_drama','cyberpunk'],custom_genre:'сохранённый текст'};
 expect(selectPrimary(v,'music_drama')).toEqual({...v,primary_genre:'music_drama',secondary_genres:['cyberpunk']});
 expect(toggleSecondary(v,'romance')).toBe(v);
 const full={...v,secondary_genres:['music_drama','cyberpunk','comedy']};
 expect(toggleSecondary(full,'gothic')).toBe(full);
 expect(toggleSecondary(full,'comedy').secondary_genres).toHaveLength(2);
});
it('selects, explains the cap, removes, promotes and restores the actual policy',async()=>{
 await mount();await click('Основной жанр: Киберпанк');await click('Дополнительные 0/3');
 for(const name of ['Музыкальная драма','Придворные интриги','Чёрная комедия'])await click('Дополнительный жанр: '+name);
 expect(state().secondary_genres).toHaveLength(3);
 expect(button('Дополнительный жанр: Готика').getAttribute('aria-disabled')).toBe('true');
 await click('Дополнительный жанр: Готика');expect(state().secondary_genres).toHaveLength(3);
 await click('Убрать Музыкальная драма');expect(state().secondary_genres).toHaveLength(2);
 expect(document.activeElement).toBe(button('Убрать Придворные интриги'));
 await click('Основной');await click('Основной жанр: Придворные интриги');
 expect(state().secondary_genres).toEqual(['black_comedy']);
 const selected=state();await click('Сбросить выбор');expect(state().primary_genre).toBeNull();
 await click('Восстановить выбор');expect(state()).toEqual(selected);
});
it('groups and filters never clear the selection; custom retains validation and text',async()=>{
 await mount({primary_genre:'custom',secondary_genres:['music_drama'],custom_genre:''});
 expect(host.querySelector('textarea')?.getAttribute('aria-invalid')).toBe('true');
 await click('Фэнтези');expect(host.querySelectorAll('.genre-card')).toHaveLength(4);
 expect(state().primary_genre).toBe('custom');
 await click('Основной жанр: Тёмное фэнтези');expect(host.querySelector('textarea')).toBeNull();
 await click('Авторский жанр');await click('Основной жанр: Свой жанр');
 expect(host.querySelector('textarea')?.getAttribute('aria-invalid')).toBe('true');
});
it('English names, descriptions and actions come from the same catalog',async()=>{
 document.documentElement.lang='en';await mount();
 await click('Primary genre: Supernatural thriller');
 expect(host.querySelector('[data-testid=primary-genre]')?.textContent).toBe('Supernatural thriller');
 expect(host.querySelector('.genre-primary p')?.textContent).toContain('unexplained');
 expect(host.querySelector('input')?.getAttribute('aria-label')).toBe('Find a genre');
});
it('disabled parent prevents policy changes',async()=>{
 await mount(empty,true);await click('Основной жанр: Романтика');expect(state()).toEqual(empty);
});
it('search spans all groups and resetting an empty result preserves the chosen policy',async()=>{
 await mount({primary_genre:'music_drama',secondary_genres:['gothic'],custom_genre:'черновик'});
 await click('Фэнтези');
 const input=host.querySelector<HTMLInputElement>('input[type=search]')!;
 const fill=async(text:string)=>{await act(()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(input,text);input.dispatchEvent(new Event('input',{bubbles:true}))})};
 await fill('космоопера');expect(host.querySelectorAll('.genre-card')).toHaveLength(1);expect(host.querySelector('.genre-card')?.getAttribute('data-genre')).toBe('space_opera');
 await fill('неизвестный жанр');expect(host.querySelector('.genre-no-results')).not.toBeNull();
 const before=state();await click('Сбросить поиск и группы');expect(state()).toEqual(before);expect(document.activeElement).toBe(input);
 expect(host.querySelectorAll('.genre-card')).toHaveLength(38);
});
