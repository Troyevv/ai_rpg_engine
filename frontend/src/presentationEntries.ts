import type {Job,Save,Turn} from './types';
export function physicalChoiceTurn(save:Save|null):Turn|undefined {
 if(!save)return;
 if(save.physical_choice_source!==undefined){
   const source=save.physical_choice_source;
   return source?save.turns.find(t=>t.id===source.turn_id&&t.active_variant_id===source.variant_id):undefined;
 }
 // Older servers/fixtures: never cross a known physical event in a call.
 for(const t of [...save.turns].reverse()){
   if(t.presentation?.physical_text||t.read_only_projection)return;
   if((t.presentation?.surface||(t.kind==='communication'?'phone':'physical'))==='physical'&&['start','turn','pov'].includes(t.kind))return t;
 }
}
export function turnIdentity(turn:Turn):string {
  return turn.variants?.find(v=>v.id===turn.active_variant_id)?.job_id || `turn:${turn.id}:${turn.active_variant_id}`;
}
export function presentationEntries(save:Save|null,job:Job|null){
  const entries=(save?.turns||[]).map(turn=>({turn,identity:turnIdentity(turn),committed:true,job:null as Job|null}));
  if(!save||!job||entries.some(e=>e.identity===job.id)||job.revision!==save.revision)return entries;
  // Use the same key, component and narrative container before and after commit.
  // Regeneration stays a preview until the server atomically replaces its target.
  const target=save.turns.find(t=>t.id===job.replaces_id);
  entries.push({identity:job.id,committed:false,job,turn:{
    id:-1,node_id:job.id,active_variant_id:job.id,variants:[],memory_archived:false,
    sequence:target?.sequence??(save.turns.at(-1)?.sequence||0)+1,
    presentation:job.presentation,
    kind:target?.kind||job.kind,user_text:target?.user_text||job.user_text||'',
    assistant_text:job.narrative,choices:[],pov_actor_id:target?.pov_actor_id||save.state.camera?.pov_actor_id,
  }});
  return entries;
}

export function surfaceEntries(entries:ReturnType<typeof presentationEntries>,surface:'physical'|'phone'|'call',actor?:string|null,callId?:string|null){
 return entries.flatMap(entry=>{
   const route=entry.turn.presentation??{surface:entry.turn.kind==='communication'?'phone':'physical'};
   if(surface==='physical'&&route.surface==='call'&&route.physical_text){return [{...entry,identity:entry.identity+':physical',turn:{...entry.turn,read_only_projection:true,user_text:'',assistant_text:route.physical_text,variants:[],choices:[]}}]}
   if(route.surface!==surface)return [];
   if(surface!=='physical'&&(route.actor_id&&route.actor_id!==actor||surface==='call'&&route.call_id!==callId))return [];
   if(surface==='call'&&route.call_text!==undefined)return [{...entry,turn:{...entry.turn,assistant_text:route.call_text}}];
   return [entry];
 });
}
