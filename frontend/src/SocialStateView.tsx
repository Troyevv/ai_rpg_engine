import {useEffect,useState} from 'react';
import {api} from './api';
import type {Genealogy} from './types';
import {dossierText as t} from './lib/dossier';
import {CharacterAvatar} from "./Portrait";
import type {State} from './types';
import {socialLabel, lifeLabel, phaseLabel} from './lib/social';

/** Uses only the server-authorized projection, never reconstructs hidden links. */
export function SocialStateView({state,actor,saveId,mode='all'}:{state:State;actor?:string;saveId?:number;mode?:'all'|'context'|'family'}) {
 const key=`${saveId}:${actor}:${state.controlled_actor_id}:${state.world_clock?.minute}`;
 const [family,setFamily]=useState<{key:string;graph:Genealogy}|null>(null);
 const [error,setError]=useState('');
 useEffect(()=>{if(mode!=='family'||!saveId||!actor)return;let live=true;setError('');
 api<Genealogy>(`/saves/${saveId}/genealogy?root_id=${encodeURIComponent(actor)}&depth=2&limit=24`).then(graph=>{if(live)setFamily({key,graph})}).catch(e=>{if(live)setError(e.message)});return()=>{live=false};
 },[key,mode,state.genealogy]);
 const graph=mode==='family'&&saveId?(family?.key===key?family.graph:null):state.genealogy;
 const names=new Map(graph?.nodes.map(n=>[n.id,n.name])||[]);
 const links=(mode==='family'?graph?.edges||[]:state.objective_relations||[]).filter(r=>!actor||r.source_id===actor||r.target_id===actor);
 const derived=(graph?.kinship||[]).filter(r=>['sibling','half_sibling','ancestor'].includes(r.kind)&&(!actor||r.source_id===actor||r.target_id===actor));
 const life=(!actor||actor===state.controlled_actor_id)?state.life_state:null;
 const residences=(state.residence_roles?.residences||[]).filter(r=>!actor||r.actor_id===actor);
 const roles=(state.residence_roles?.roles||[]).filter(r=>!actor||r.actor_id===actor);

 if(mode==='family')return <section className="dossier-card dossier-family" aria-label={t('family')}><h3>{t('family')}</h3><p className="muted small">{t('publicFamily')}</p>{saveId&&<button className="dossier-family-open" onClick={()=>window.dispatchEvent(new CustomEvent('save-workspace',{detail:{section:'family',root:actor}}))}>{t('openFamily')}</button>}
 {error?<p role="alert">{error}</p>:saveId&&!graph?<p role="status">{t('loading')}</p>:<>
 {!links.length&&<p>{t('noFamily')}</p>}{links.map(r=>{const other=graph?.nodes.find(n=>n.id===(r.source_id===actor?r.target_id:r.source_id));return <div className="dossier-person" key={r.id}>{other&&<CharacterAvatar subject={other} saveId={saveId} size={44}/>}<div><strong>{other?.name}</strong><p>{names.get(r.source_id)} → {names.get(r.target_id)} · {socialLabel(r.kind)}{r.status==='closed'?` · ${socialLabel(r.outcome)}`:''}</p>{(r.since_date||r.until_date)&&<small>{r.since_date} — {r.until_date||'…'}</small>}</div></div>})}
 {!!derived.length&&<details><summary>Родословная</summary>{derived.map((r,i)=><p key={i}>{names.get(r.source_id)} → {names.get(r.target_id)}: {socialLabel(r.kind)}{r.lineage==='adoptive_parent'?' · усыновление':''}{r.generations?` · поколений: ${r.generations}`:''}</p>)}</details>}
 {graph?.truncated&&<p className="muted small">Показана часть семьи. Открой родословную для продолжения.</p>}</>}
 </section>;
 if(mode==='context')return <>{[["Проживание",residences],["Занятия и роли",roles]].map(([heading,items])=>{const rows=items as typeof roles;return !!rows.length&&<section className="dossier-card" key={heading as string}><h3>{heading as string}</h3>{rows.map(r=><p key={r.id}>{r.label}{r.organization?` · ${r.organization}`:''}{r.field?` · ${r.field}`:''} · {phaseLabel(r.status==='closed'?r.outcome:r.status)}{r.certainty==='suspected'?' · подозрение':''}{r.since_date?` · с ${r.since_date}`:''}{r.until_date?` до ${r.until_date}`:''}</p>)}</section>})}</>;
 return <section aria-label="Семья и социальные связи"><h3>Семья и социальные связи</h3>{saveId&&<button onClick={()=>{window.dispatchEvent(new CustomEvent('save-workspace',{detail:{section:'family',root:actor}}))}}>Открыть родословную</button>}
  <p className="muted small">Семейный справочник общедоступен. Остальные социальные сведения зависят от знаний персонажа.</p>
  {life&&<><p>Состояние персонажа: {lifeLabel(life.life_status)}</p>
   {life.conditions.map(c=><p key={c.id}>{c.description} · {{active:'Действует',resolved:'Завершено',cancelled:'Отменено',unknown_outcome:'Исход неизвестен'}[c.status]}{c.duration==='persistent'?' · длительное ограничение':''}</p>)}
   {!!life.names.length&&<details><summary>История имени</summary>{life.names.map((n,i)=><p key={i}>{n.previous} → {n.current}{n.date?` · ${n.date}`:''}</p>)}</details>}
  </>}
  {[["Проживание",residences],["Занятия и роли",roles]].map(([heading,items])=>{
   const rows=items as typeof roles;
   return !!rows.length&&<div key={heading as string}><h4>{heading as string}</h4>
    {rows.map(r=><p key={r.id}>{!actor&&<>{state.characters.find(c=>c.id===r.actor_id)?.name}: </>}{r.label}{r.organization?` · ${r.organization}`:''}{r.field?` · ${r.field}`:''} · {phaseLabel(r.status==='closed'?r.outcome:r.status)}{r.certainty==='suspected'?' · подозрение':''}{r.since_date?` · с ${r.since_date}`:''}{r.until_date?` до ${r.until_date}`:''}</p>)}
   </div>;
  })}
  {graph&&<div className="genealogy-avatars">{graph.nodes.map(n=><span key={n.id}><CharacterAvatar subject={n} saveId={saveId}/>{n.name}</span>)}</div>}
  {links.map(r=><p key={r.id}>{names.get(r.source_id)||state.characters.find(c=>c.id===r.source_id)?.name} → {names.get(r.target_id)||state.characters.find(c=>c.id===r.target_id)?.name}: {socialLabel(r.kind)}{r.certainty==='suspected'?' · подозрение':''}{r.status==='closed'?` · ${socialLabel(r.outcome)}`:''}{r.since_date?` · с ${r.since_date}`:''}{r.until_date?` до ${r.until_date}`:''}</p>)}
  {!!derived.length&&<details><summary>Родословная</summary>{derived.map((r,i)=><p key={i}>{names.get(r.source_id)} → {names.get(r.target_id)}: {socialLabel(r.kind)}{r.lineage==='adoptive_parent'?' · усыновление':''}{r.generations?` · поколений: ${r.generations}`:''}</p>)}</details>}
  {graph?.nodes.filter(n=>n.life_status==='dead'&&(!actor||actor===n.id)).map(n=><p key={n.id}>{n.name}: {lifeLabel(n.life_status)}</p>)}
  {graph?.truncated&&<p className="muted small">Показана ограниченная часть родословной.</p>}
 </section>;
}
