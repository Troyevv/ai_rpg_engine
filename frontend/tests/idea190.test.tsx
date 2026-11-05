import {act,type ReactNode} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,expect,it,vi} from 'vitest';
import {IdeaAtelier,creationError} from '../src/workshop/IdeaAtelier';
import {generationSteps} from '../src/workshop/IdeaGeneration';
import {defaultCreation} from '../src/WorldCreationSettings';
import {readIdeaBuffer,writeIdeaBuffer} from '../src/workshop/ideaBuffer';
import {ApiError} from '../src/api';
import type {Job} from '../src/types';
// Motion timing is covered in Playwright; these tests exercise command guards.
vi.mock('framer-motion',()=>({AnimatePresence:({children}:{children:ReactNode})=>children,useReducedMotion:()=>true,motion:{div:({children,initial,animate,exit,transition,onAnimationComplete,...rest}:any)=><div {...rest}>{children}</div>,section:({children,initial,animate,exit,transition,onAnimationComplete,...rest}:any)=><section {...rest}>{children}</section>}}));
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
 const job={id:'current',kind:'draft_world',status:'error',phase:'reviewing'} as Job;
 const steps=generationSteps(job,{version_id:3,version_origin_job_id:'current',technical_valid:true,creative_status:'applied',review:{status:'failed'}});
 expect(steps.map(s=>s.state)).toEqual(['done','done','done','error','pending']);
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

it('does not treat a previous saved version or its review as progress of a new job',()=>{
 const job={id:'new',kind:'draft_world',status:'generating',phase:'world'} as Job;
 const old={version_id:8,version_origin_job_id:'old',technical_valid:true,creative_status:'applied',review:{status:'completed'}};
 expect(generationSteps(job,old).map(s=>s.done)).toEqual([false,false,false,false,false]);
 expect(generationSteps(job,old).map(s=>s.state)).toEqual(['current','pending','pending','pending','pending']);
 expect(generationSteps({...job,status:'saved'}, {...old,version_origin_job_id:'new',version_is_candidate:true})[4].done).toBe(false);
 expect(generationSteps({...job,status:'saved'}, {...old,version_origin_job_id:'new',version_is_candidate:false})[4].done).toBe(true);
});
