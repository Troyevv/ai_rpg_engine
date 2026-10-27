import type {Job,Save,Turn} from './types';
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
    kind:target?.kind||job.kind,user_text:target?.user_text||job.user_text||'',
    assistant_text:job.narrative,choices:[],pov_actor_id:target?.pov_actor_id||save.state.camera?.pov_actor_id,
  }});
  return entries;
}
