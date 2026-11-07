import {afterEach,expect,it,vi} from 'vitest';
import {observeGenreMotion} from '../e2e/genre-motion';

afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();document.body.innerHTML=''});

it.each([16,100,400])('captures at least five frames and the 350 ms window at %i ms/frame',async interval=>{
 let now=0;const frames:FrameRequestCallback[]=[];
 vi.spyOn(performance,'now').mockImplementation(()=>now);
 vi.stubGlobal('requestAnimationFrame',(callback:FrameRequestCallback)=>{frames.push(callback);return frames.length});
 document.body.innerHTML='<div class="genre-settings"></div>';
 observeGenreMotion();
 const node=document.createElement('div');node.className='genre-results';
 document.querySelector('.genre-settings')!.append(node);
 await Promise.resolve(); // Deliver the real MutationObserver callback.
 for(let i=0;i<30 && frames.length;i++){
  now+=interval;node.style.opacity=String(Math.min(1,.4+now/1000));
  node.style.transform=now<350?'translateY(4px)':'none';
  frames.shift()!(now);
 }
 const samples=(window as any).genreMotion as {opacity:number;transform:string;elapsed:number}[];
 expect(samples.length).toBeGreaterThan(4);
 expect(samples.at(-1)!.elapsed).toBeGreaterThanOrEqual(350);
 expect(frames).toHaveLength(0); // Sampling terminates, including at low frame rates.
 expect(samples[0].elapsed).toBe(interval);
 expect(samples[0].opacity).toBeCloseTo(Math.min(1,.4+interval/1000));
 expect(samples.at(-1)!.transform).toBe('none');
});
