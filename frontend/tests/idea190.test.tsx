import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,expect,it,vi} from 'vitest';
import {IdeaAtelier,creationError} from '../src/workshop/IdeaAtelier';
import {generationSteps} from '../src/workshop/IdeaGeneration';
import {defaultCreation} from '../src/WorldCreationSettings';
import {readIdeaBuffer,writeIdeaBuffer} from '../src/workshop/ideaBuffer';
import {ApiError} from '../src/api';
import type {Job} from '../src/types';
vi.mock('../src/api',async original=>({...await original<typeof import('../src/api')>(),api:vi.fn(async()=>({}))}));
afterEach(()=>{sessionStorage.clear();document.body.innerHTML=''});
it('isolates complete input by workspace without sharing mutable defaults',()=>{
 const a={text:'private A',name:'A',useIdea:true,creation:{...structuredClone(defaultCreation),custom_genre:'жанр A'}};
 writeIdeaBuffer('a',a);writeIdeaBuffer('b',{...a,text:'B',name:'B',useIdea:false,creation:structuredClone(defaultCreation)});
 expect(readIdeaBuffer('a')).toEqual(a);expect(readIdeaBuffer('b')?.creation.custom_genre).toBe('');expect(readIdeaBuffer('c')).toBeNull();
});
it('maps server model errors into the appropriate parameter group',()=>{
 expect(creationError(new ApiError('Некорректный запрос',{detail:[{loc:['body','creation_settings','calendar_start'],msg:'Value error, День вне месяца'}]}))).toMatchObject({group:'calendar',message:'День вне месяца'});
 expect(creationError(new ApiError('Некорректный запрос',{detail:[{loc:['body','creation_settings'],msg:'Value error, Добавьте описание своего жанра.'}]})).group).toBe('genre');
});
it('uses only server-confirmed stage completion and never labels a failed review complete',()=>{
 const job={kind:'draft_world',status:'error',phase:'reviewing'} as Job;
 const steps=generationSteps(job,{version_id:3,technical_valid:true,creative_status:'applied',review:{status:'failed'}});
 expect(steps.map(s=>s.state)).toEqual(['done','done','done','paused','pending']);
 expect(generationSteps({...job,status:'saved'},{version_id:4,technical_valid:true,review:{status:'stale'}})[3].done).toBe(false);
});
it('review has no generation side effects and pending validation ignores duplicate clicks',async()=>{
 const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
 let resolve!:()=>void;const validate=vi.fn(()=>new Promise<void>(r=>resolve=r));const launch=vi.fn(async()=>{});
 await act(()=>root.render(<IdeaAtelier id="" name="История" text="Город у моря" useIdea={false} creation={structuredClone(defaultCreation)} disabled={false} saved onName={()=>{}} onText={()=>{}} onScenario={()=>{}} onCreation={()=>{}} onMethod={()=>{}} validate={validate} launch={launch}/>));
 const button=Array.from(host.querySelectorAll('button')).find(b=>b.textContent?.includes('Проверить замысел'))!;
 await act(()=>{button.click();button.click()});expect(validate).toHaveBeenCalledTimes(1);expect(launch).not.toHaveBeenCalled();
 await act(()=>resolve());expect(host.querySelector('[aria-label="Сводка замысла"]')).not.toBeNull();expect(launch).not.toHaveBeenCalled();
 await act(()=>root.unmount());
});

it('does not launch a different draft after leaving a pending preflight',async()=>{
 const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
 let finish!:()=>void;const validate=vi.fn().mockResolvedValueOnce(undefined).mockImplementationOnce(()=>new Promise<void>(r=>finish=r));const launch=vi.fn(async()=>{});
 await act(()=>root.render(<IdeaAtelier id="old" name="Мир" text="Идея" useIdea={false} creation={structuredClone(defaultCreation)} disabled={false} saved onName={()=>{}} onText={()=>{}} onScenario={()=>{}} onCreation={()=>{}} onMethod={()=>{}} validate={validate} launch={launch}/>));
 await act(()=>Array.from(host.querySelectorAll('button')).find(b=>b.textContent?.includes('Проверить замысел'))!.click());
 await act(()=>Array.from(host.querySelectorAll('button')).find(b=>b.textContent?.includes('Создать мир'))!.click());
 expect(validate).toHaveBeenCalledTimes(2);
 await act(()=>root.unmount());await act(()=>finish());expect(launch).not.toHaveBeenCalled();
});
