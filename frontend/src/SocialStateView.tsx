import type {State} from './types';
import {socialLabel, lifeLabel} from './lib/social';

/** Uses only the server-authorized projection, never reconstructs hidden links. */
export function SocialStateView({state,actor}:{state:State;actor?:string}) {
 const graph=state.genealogy;
 const names=new Map(graph?.nodes.map(n=>[n.id,n.name])||[]);
 const links=(state.objective_relations||[]).filter(r=>!actor||r.source_id===actor||r.target_id===actor);
 const derived=(graph?.kinship||[]).filter(r=>['sibling','half_sibling','ancestor'].includes(r.kind)&&(!actor||r.source_id===actor||r.target_id===actor));
 const life=(!actor||actor===state.controlled_actor_id)?state.life_state:null;
 if(!links.length&&!derived.length&&!life)return null;
 return <section aria-label="Семья и социальные связи"><h3>Семья и социальные связи</h3>
  <p className="muted small">Известно управляемому персонажу. Неизвестные связи не показаны.</p>
  {life&&<><p>Состояние персонажа: {lifeLabel(life.life_status)}</p>
   {life.conditions.map(c=><p key={c.id}>{c.description} · {{active:'Действует',resolved:'Завершено',cancelled:'Отменено',unknown_outcome:'Исход неизвестен'}[c.status]}{c.duration==='persistent'?' · длительное ограничение':''}</p>)}
   {!!life.names.length&&<details><summary>История имени</summary>{life.names.map((n,i)=><p key={i}>{n.previous} → {n.current}{n.date?` · ${n.date}`:''}</p>)}</details>}
  </>}
  {links.map(r=><p key={r.id}>{names.get(r.source_id)||state.characters.find(c=>c.id===r.source_id)?.name} → {names.get(r.target_id)||state.characters.find(c=>c.id===r.target_id)?.name}: {socialLabel(r.kind)}{r.certainty==='suspected'?' · подозрение':''}{r.status==='closed'?` · ${socialLabel(r.outcome)}`:''}{r.since_date?` · с ${r.since_date}`:''}{r.until_date?` до ${r.until_date}`:''}</p>)}
  {!!derived.length&&<details><summary>Родословная</summary>{derived.map((r,i)=><p key={i}>{names.get(r.source_id)} → {names.get(r.target_id)}: {socialLabel(r.kind)}{r.lineage==='adoptive_parent'?' · усыновление':''}{r.generations?` · поколений: ${r.generations}`:''}</p>)}</details>}
  {graph?.nodes.filter(n=>n.life_status==='dead'&&(!actor||actor===n.id)).map(n=><p key={n.id}>{n.name}: {lifeLabel(n.life_status)}</p>)}
  {graph?.truncated&&<p className="muted small">Показана ограниченная часть родословной.</p>}
 </section>;
}
