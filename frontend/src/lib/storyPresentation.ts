import type {Save} from '../types';
/** Presentation receipts only. Canon and active event membership always come from the server. */
const prefix='story-presentation-v1';
const fallback=new Set<string>();
export const presentationKey=(save:number,actor:string|null|undefined,event:string,kind:'fog'|'toast')=>`${prefix}:${save}:${actor}:${kind}:${event}`;
export function wasPresented(key:string){try{return localStorage.getItem(key)==='1'||fallback.has(key)}catch{return fallback.has(key)}}
export function markPresented(key:string){fallback.add(key);try{localStorage.setItem(key,'1')}catch{/* Private mode / quota: the current session still deduplicates. */}}

/** Delivery bookkeeping contains opaque IDs only, never event text or Knowledge.
 * Observe at snapshot admission, before any game surface mounts. The first load
 * establishes a legacy baseline once; later additions survive remount/reload.
 * Pending IDs from inactive variants stay parked until the server exposes them.
 */
type Delivery={known:string[];pending:string[]};
const deliveries=new Map<string,Delivery>();
const deliveryKey=(save:Save)=>`story-delivery-v1:${save.id}:${save.state.controlled_actor_id}`;
function readDelivery(key:string):Delivery|undefined{
 if(deliveries.has(key))return deliveries.get(key);
 try{
  const raw=localStorage.getItem(key);
  if(raw){const value=JSON.parse(raw);if(Array.isArray(value.known)&&Array.isArray(value.pending)&&[...value.known,...value.pending].every(id=>typeof id==='string')){deliveries.set(key,value);return value}}
  return deliveries.get(key);
 }catch{return deliveries.get(key)}
}
function writeDelivery(key:string,value:Delivery){deliveries.set(key,value);try{localStorage.setItem(key,JSON.stringify(value))}catch{/* Session fallback; canonical state is unaffected. */}}
export function invalidateStoryDelivery(key:string|null){if(key===null)deliveries.clear();else deliveries.delete(key)}
export function observeStorySnapshot(save:Save){
 const key=deliveryKey(save),ids=(save.state.notification_history||[]).map(e=>e.id),prior=readDelivery(key);
 if(!prior){writeDelivery(key,{known:ids,pending:[]});return}
 const known=new Set(prior.known),added=ids.filter(id=>!known.has(id));
 if(added.length)writeDelivery(key,{known:[...prior.known,...added],pending:[...prior.pending,...added]});
}
export function pendingStoryNotices(save:Save){
 const pending=new Set(readDelivery(deliveryKey(save))?.pending||[]);
 return (save.state.notification_history||[]).filter(e=>pending.has(e.id)&&!wasPresented(presentationKey(save.id,save.state.controlled_actor_id,e.id,'toast')));
}
export function acknowledgeStoryNotice(save:Save,id:string){
 markPresented(presentationKey(save.id,save.state.controlled_actor_id,id,'toast'));
 const key=deliveryKey(save),prior=readDelivery(key);
 if(prior?.pending.includes(id))writeDelivery(key,{known:prior.known,pending:prior.pending.filter(e=>e!==id)});
}
