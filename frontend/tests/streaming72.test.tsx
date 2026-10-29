import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest';
import {act,Profiler} from 'react';
import {createRoot,type Root} from 'react-dom/client';
import {NarrativeTurn} from '../src/NarrativeTurn';
import {NarrativeText} from '../src/NarrativeText';
import {Markdown} from '../src/Markdown';
import {presentationEntries} from '../src/presentationEntries';
import {revealEnd} from '../src/narrativePresentation';
import {useStoryScroll} from '../src/useStoryScroll';
import {useJob} from '../src/hooks';
import {defaults,type Job,type Save,type Turn,type World} from '../src/types';
const noop=()=>{};
let reduced=false;
vi.mock('framer-motion',async original=>({...await original<any>(),useReducedMotion:()=>reduced}));
let root:Root,host:HTMLDivElement;
beforeEach(()=>{vi.useFakeTimers();reduced=false;sessionStorage.clear();host=document.createElement('div');document.body.append(host);root=createRoot(host);vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({html:'<p>Rendered <button data-character-id="npc">NPC</button></p>'})})));});
afterEach(async()=>{await act(()=>root.unmount());host.remove();vi.useRealTimers();vi.unstubAllGlobals()});
async function render(ui:React.ReactNode){await act(()=>root.render(ui))}
async function advance(ms:number){await act(()=>vi.advanceTimersByTimeAsync(ms))}
const text='Первый абзац. 🕯️\n\n'+('Продолжается повествование. '.repeat(100));
const initialJob:Job={id:'job72',status:'generating',narrative:'',error:'',kind:'turn',revision:0,user_text:'Открываю книгу.'};
const save={id:1,world_id:1,revision:0,turns:[],job:null,state:{characters:[],camera:{},protagonist_id:'hero'}} as unknown as Save;
const world={id:1} as World;
const done=vi.fn();
const shared={save,world,prefs:defaults,mobile:false,busy:false,running:true,mainActor:'hero',turn:async()=>{},run:async()=>{},setSubmitted:noop,refresh:noop,setDiagnosticJob:noop,setDiagnostics:noop,openCharacter:noop,reconnecting:false,stop:noop,onPresented:done};
function Journal({snapshot=save,job}:{snapshot?:Save;job:Job}){return <>{presentationEntries(snapshot,job).map((e,i)=><NarrativeTurn {...shared} save={snapshot} key={e.identity} identity={e.identity} t={e.turn} i={i} committed={e.committed} job={e.job}/>)}</>}
it('bursty snapshots reveal intermediate exact prefixes without HTTP; drain survives commit with the same DOM identity',async()=>{
 await render(<Journal job={initialJob}/>);
 await render(<Journal job={{...initialJob,narrative:text}}/>);
 const node=host.querySelector('.narrative-text')!;
 await advance(64);
 const partial=node.textContent!;
 expect(partial.length).toBeGreaterThan(0);expect(partial.length).toBeLessThan(text.length);
 expect(text.replace(/\n\n/g,'').startsWith(partial)).toBe(true);
 // Only the player's static action may render; narrative must not.
 expect(vi.mocked(fetch).mock.calls.every(c=>!JSON.parse(c[1]!.body as string).text.includes('Первый абзац'))).toBe(true);
 for(const status of ['extracting','validating'])await render(<Journal job={{...initialJob,narrative:text,narrative_complete:true,status}}/>);
 const committed={id:1,node_id:'node',active_variant_id:'v',sequence:1,kind:'turn',assistant_text:text,user_text:initialJob.user_text,variants:[{id:'v',job_id:initialJob.id,ordinal:1,can_regenerate:true}],choices:[],memory_archived:false} as Turn;
 await render(<Journal snapshot={{...save,revision:1,turns:[committed]}} job={{...initialJob,narrative:text,status:'saved'}}/>);
 expect(host.querySelector('.narrative-text')).toBe(node);expect(host.querySelectorAll('.narrative-text')).toHaveLength(1);
 expect(node.textContent!.length).toBeGreaterThanOrEqual(partial.length);
 await advance(5000);
 expect(node.getAttribute('data-revealing')).toBe('false');
 await advance(100);
 const requests=vi.mocked(fetch).mock.calls.filter(c=>JSON.parse(c[1]!.body as string).text===text);
 expect(requests).toHaveLength(1);expect(done).toHaveBeenCalledWith(initialJob.id);
 expect(host.querySelector('.job')).toBeNull();
});
it('reduced motion shows whole snapshots immediately and still defers Markdown until complete',async()=>{
 reduced=true;
 await render(<NarrativeText text={text} identity="reduced" complete={false} onPresented={noop} saveId={1} worldId={1} links onCharacter={noop}/>);
 expect(host.querySelector('.narrative-text')!.getAttribute('data-revealing')).toBe('false');
 await advance(500);expect(fetch).not.toHaveBeenCalled();
 await render(<NarrativeText text={text} identity="reduced" complete onPresented={noop} saveId={1} worldId={1} links onCharacter={noop}/>);
 await advance(100);expect(fetch).toHaveBeenCalledTimes(1);
});
it('error, retry and reconnect snapshots keep the article and displayed prefix',async()=>{
 await render(<Journal job={initialJob}/>);
 await render(<Journal job={{...initialJob,narrative:text,narrative_complete:true,status:'error'}}/>);await advance(100);
 const node=host.querySelector('.narrative-text');const prefix=node!.textContent!;
 await render(<Journal job={{...initialJob,narrative:text,narrative_complete:true,status:'extracting',attempt_epoch:1}}/>);
 expect(host.querySelector('.narrative-text')).toBe(node);expect(node!.textContent).toBe(prefix);
 await advance(5000);expect(node!.getAttribute('data-revealing')).toBe('false');
});
it('navigation remount resumes the shown prefix instead of replaying it',async()=>{
 const props={text,identity:'nav',complete:false,onPresented:noop,saveId:1,worldId:1,links:true,onCharacter:noop};
 await render(<NarrativeText {...props}/>);await advance(100);
 const before=host.textContent;await render(null);await render(<NarrativeText {...props}/>);
 expect(host.textContent).toBe(before);
});
it('Markdown failure retains readable text and link_names survives final render',async()=>{
 vi.mocked(fetch).mockRejectedValueOnce(new Error('offline'));
 await render(<Markdown text="Текст **не теряется**" links={false}/>);await advance(100);
 expect(host.textContent).toBe('Текст **не теряется**');
 const clicked=vi.fn();await render(<Markdown text="NPC" links onCharacter={clicked}/>);await advance(100);
 await act(()=>host.querySelector('button')!.click());expect(clicked).toHaveBeenCalledWith('npc');
 expect(JSON.parse(vi.mocked(fetch).mock.calls.at(-1)![1]!.body as string).link_names).toBe(true);
});
it('a new attempt replaces stale HTML instead of displaying the previous response',async()=>{
 await render(<Markdown text="old"/>);await advance(100);
 await render(<Markdown text="new" streaming/>);expect(host.textContent).toBe('new');
 await render(<Markdown text="new"/>);expect(host.textContent).toBe('new');
});
it('regeneration commit keeps identity; old/stale job does not duplicate a variant',()=>{
 const turn={id:7,active_variant_id:'v0',variants:[{id:'v0',job_id:'old'}],sequence:4,kind:'turn',user_text:'original'} as Turn;
 const j={...initialJob,replaces_id:7,kind:'regenerate'};
 const before=presentationEntries({...save,turns:[turn]},j);
 expect(before[1].turn.sequence).toBe(4);expect(before[1].turn.user_text).toBe('original');
 const after=presentationEntries({...save,revision:1,turns:[{...turn,active_variant_id:'v1',variants:[...turn.variants,{id:'v1',job_id:j.id,ordinal:2,can_regenerate:true}]}]}, {...j,status:'saved'});
 expect(after).toHaveLength(1);expect(after[0].identity).toBe(before[1].identity);
 expect(presentationEntries({...save,revision:1},j)).toHaveLength(0);
});
it('buffer bounds long frame gaps and never splits surrogate pairs',()=>{
 for(let n=0;n<text.length;){const next=revealEnd(text,n,10000);expect(next).toBeGreaterThan(n);expect(next).toBeLessThanOrEqual(text.length);expect(/[\uD800-\uDBFF]$/.test(text.slice(0,next))).toBe(false);n=next}
 expect(revealEnd('x'.repeat(10000),0,10000)).toBeLessThan(3000);
});

describe('single scroll owner',()=>{
 let resize:()=>void;
 beforeEach(()=>{vi.stubGlobal('ResizeObserver',class {constructor(cb:()=>void){resize=cb}observe(){}disconnect(){}})});
 function Reader(){const {scroll,onScroll,jumpToLatest,away}=useStoryScroll(72);return <><div ref={scroll} onScroll={onScroll}><article data-reading-id="one">Scene</article></div><button onClick={jumpToLatest}>{away?'away':'bottom'}</button></>}
 it('follows resize, preserves manual scroll, and jump-to-latest re-enables following without smooth animations',async()=>{
 await render(<Reader/>);const el=host.firstElementChild as HTMLElement;
 let height=1000;Object.defineProperties(el,{scrollHeight:{get:()=>height},clientHeight:{get:()=>200}});
 await act(()=>resize());await advance(20);expect(el.scrollTop).toBe(1000);
 await act(()=>{el.scrollTop=300;el.dispatchEvent(new Event('scroll',{bubbles:true}))});expect(host.querySelector('button')!.textContent).toBe('away');
 height=2000;await act(()=>resize());await advance(20);expect(el.scrollTop).toBe(300);
 await act(()=>host.querySelector('button')!.click());await advance(20);expect(el.scrollTop).toBe(2000);
 height=2500;await act(()=>{resize();resize();resize()});await advance(20);expect(el.scrollTop).toBe(2500);
 });
});

it('SSE reconnect retains text; stale parent refresh cannot regress status; Retry owns one subscription',async()=>{
 class Stream extends EventTarget {static all:Stream[]=[];onopen:()=>void=noop;onerror:()=>void=noop;closed=false;constructor(public url:string){super();Stream.all.push(this)}close(){this.closed=true}}
 vi.stubGlobal('EventSource',Stream);const complete=vi.fn();
 function JobReader({initial}:{initial:Job}){const {job,reconnecting}=useJob(initial,complete);return <div data-reconnecting={reconnecting} data-status={job?.status}>{job?.narrative}</div>}
 await render(<JobReader initial={initialJob}/>);const stream=Stream.all[0];
 const emit=async(job:Job)=>act(()=>stream.dispatchEvent(new MessageEvent('snapshot',{data:JSON.stringify(job)})));
 await emit({...initialJob,narrative:text,status:'extracting',narrative_complete:true});
 await act(()=>stream.onerror());expect(host.firstElementChild?.getAttribute('data-reconnecting')).toBe('true');expect(host.textContent).toBe(text);
 await render(<JobReader initial={{...initialJob}}/>);expect(host.textContent).toBe(text);expect(host.firstElementChild?.getAttribute('data-status')).toBe('extracting');expect(Stream.all).toHaveLength(1);
 await emit({...initialJob,narrative:text,status:'error',narrative_complete:true});expect(complete).toHaveBeenCalledTimes(1);expect(stream.closed).toBe(true);
 await render(<JobReader initial={{...initialJob,narrative:text,status:'extracting',attempt_epoch:1}}/>);
 expect(Stream.all).toHaveLength(2);expect(Stream.all.filter(s=>!s.closed)).toHaveLength(1);expect(host.textContent).toBe(text);
});

it('fast snapshots update one running frame instead of restarting it for every chunk',async()=>{
 const props={identity:'fast',complete:false,onPresented:noop,saveId:1,worldId:1,links:true,onCharacter:noop};
 const cancel=vi.spyOn(window,'cancelAnimationFrame');
 await render(<NarrativeText {...props} text=""/>);
 for(let i=1;i<=10;i++){await render(<NarrativeText {...props} text={text.slice(0,i*100)}/>);await advance(2)}
 expect(cancel).not.toHaveBeenCalled();
 expect(host.textContent!.length).toBeGreaterThan(0);
 await advance(5000);expect(host.querySelector('.narrative-text')!.getAttribute('data-revealing')).toBe('false');
 cancel.mockRestore();
});

it('layout clamping when choices disappear does not turn off bottom-follow',async()=>{
 let resize=noop;
 vi.stubGlobal('ResizeObserver',class {constructor(cb:()=>void){resize=cb}observe(){}disconnect(){}});
 function Reader(){const {scroll,onScroll,away}=useStoryScroll(73);return <div ref={scroll} onScroll={onScroll} data-away={away}><article data-reading-id="one">Scene</article></div>}
 await render(<Reader/>);const el=host.firstElementChild as HTMLElement;let height=1000,top=0;
 Object.defineProperties(el,{scrollHeight:{get:()=>height},clientHeight:{get:()=>200},scrollTop:{get:()=>top,set:v=>{top=Math.min(height-200,v)}}});
 await act(()=>resize());await advance(20);expect(top).toBe(800);
 height=600;top=400;await act(()=>el.dispatchEvent(new Event('scroll',{bubbles:true})));
 expect(el.dataset.away).toBe('false');
 height=1200;await act(()=>resize());await advance(20);expect(top).toBe(1000);
});

it('Stop keeps the existing SSE recovery until the worker is no longer live, so Retry can unlock',async()=>{
 class Stream extends EventTarget {static last:Stream;onopen=noop;onerror=noop;closed=false;constructor(){super();Stream.last=this}close(){this.closed=true}}
 vi.stubGlobal('EventSource',Stream);const complete=vi.fn();
 function Reader({initial}:{initial:Job}){const {job}=useJob(initial,complete);return <button disabled={job?.live}>{job?.narrative}</button>}
 const stopped={...initialJob,status:'stopped',narrative:'Сохранённый текст',narrative_complete:true,live:true};
 await render(<Reader initial={stopped}/>);const stream=Stream.last;
 await act(()=>stream.dispatchEvent(new MessageEvent('snapshot',{data:JSON.stringify(stopped)})));
 expect(stream.closed).toBe(false);expect(complete).not.toHaveBeenCalled();expect(host.querySelector('button')!.disabled).toBe(true);
 await act(()=>stream.dispatchEvent(new MessageEvent('snapshot',{data:JSON.stringify({...stopped,live:false})})));
 expect(stream.closed).toBe(true);expect(complete).toHaveBeenCalledOnce();expect(host.querySelector('button')!.disabled).toBe(false);expect(host.textContent).toBe(stopped.narrative);
});

it('animation frames do not commit renders in the historical journal',async()=>{
 const historical=vi.fn();const t={id:1,active_variant_id:'old',node_id:'old',sequence:1,kind:'turn',assistant_text:'История',user_text:'',variants:[],choices:[],memory_archived:false} as Turn;
 const history=<Profiler id="history" onRender={historical}><NarrativeTurn {...shared} identity="old" t={t} i={0} job={null} committed/></Profiler>;
 const props={identity:'isolated',complete:false,onPresented:noop,saveId:1,worldId:1,links:true,onCharacter:noop};
 await render(<>{history}<NarrativeText {...props} text=""/></>);await advance(100);
 await render(<>{history}<NarrativeText {...props} text={text}/></>);historical.mockClear();
 await advance(5000);expect(historical).not.toHaveBeenCalled();
});

it('historical prose stays readable but formats links only near the reading viewport',async()=>{
 let intersect:IntersectionObserverCallback=()=>{};
 const disconnect=vi.fn();
 vi.stubGlobal('IntersectionObserver',class {constructor(callback:IntersectionObserverCallback){intersect=callback}observe(){}disconnect=disconnect});
 await render(<NarrativeText text="Длинная архивная сцена." identity="archive87" complete deferFormatting onPresented={noop} saveId={1} worldId={1} links onCharacter={noop}/>);
 await advance(200);
 expect(host.textContent).toContain('Длинная архивная сцена.');expect(fetch).not.toHaveBeenCalled();
 await act(()=>intersect([{isIntersecting:true}] as IntersectionObserverEntry[],{} as IntersectionObserver));
 await advance(100);
 expect(fetch).toHaveBeenCalledTimes(1);expect(disconnect).toHaveBeenCalled();
 expect(host.querySelector('[data-character-id="npc"]')).not.toBeNull();
});
