/** Presentation receipts only. Canon and active event membership always come from the server. */
const prefix='story-presentation-v1';
const fallback=new Set<string>();
export const presentationKey=(save:number,actor:string|null|undefined,event:string,kind:'fog'|'toast')=>`${prefix}:${save}:${actor}:${kind}:${event}`;
export function wasPresented(key:string){try{return localStorage.getItem(key)==='1'||fallback.has(key)}catch{return fallback.has(key)}}
export function markPresented(key:string){fallback.add(key);try{localStorage.setItem(key,'1')}catch{/* Private mode / quota: the current session still deduplicates. */}}
