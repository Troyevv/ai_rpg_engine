import {useEffect,useState,type ReactNode} from 'react';
import {CharacterAvatar} from '../Portrait';
import type {WorkshopCharacter} from './CharacterCollection';
type Item=Record<string,unknown>;

/** A bounded view of existing edges. Selecting a node never creates a relationship. */
export function RelationshipMap({characters,entries,wid,author,actor,initialActor,onOpen,children}:{characters:WorkshopCharacter[];entries:[string,Item][];wid:string;author:boolean;actor?:string|null;initialActor?:string;onOpen:(id:string)=>void;children:(source:string)=>ReactNode}){
 const key=`workshop:${wid}:relationship-person:${author}`;
 const [selected,setSelected]=useState(()=>initialActor||sessionStorage.getItem(key)||actor||characters[0]?.id||'');
 useEffect(()=>{if(initialActor)setSelected(initialActor)},[initialActor]);
 const person=characters.find(c=>c.id===selected)||characters.find(c=>c.id===actor)||characters[0];
 const source=person?.id||'';
 const select=(id:string)=>{setSelected(id);sessionStorage.setItem(key,id)};
 const neighbors=[...new Set(entries.flatMap(([,r])=>r.source_id===source?[String(r.target_id)]:r.target_id===source?[String(r.source_id)]:[]))].filter(id=>id!==source&&characters.some(c=>c.id===id));
 const positions=[[22.5,21.4],[77.5,21.4],[81.7,71.4],[18.3,73.8],[50,86.9]];
 return <div className="ww-relations-layout"><section className="ww-relation-map-panel"><label className="ww-relation-picker">Чьи отношения показать<select aria-label="Чьи отношения показать" value={source} onChange={e=>select(e.target.value)}>{characters.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label><div className="ww-relation-map" aria-label="Карта отношений выбранного персонажа"><svg viewBox="0 0 600 420" preserveAspectRatio="none" aria-hidden="true">{neighbors.slice(0,5).map((id,i)=><path key={id} d={`M300 210 L${positions[i][0]*6} ${positions[i][1]*4.2}`}/>)}</svg>{person&&<button className="ww-graph-node is-center" style={{left:'50%',top:'50%'}} onClick={()=>onOpen(source)} aria-label={`Открыть досье ${person.name}`}><CharacterAvatar subject={person} workspaceId={wid} author={author} size={68}/><span>{person.name}</span></button>}{neighbors.slice(0,5).map((id,i)=>{const c=characters.find(c=>c.id===id)!;return <button className="ww-graph-node" key={id} style={{left:positions[i][0]+'%',top:positions[i][1]+'%'}} onClick={()=>select(id)} aria-label={`Отношения ${c.name}`}><CharacterAvatar subject={c} workspaceId={wid} author={author} size={54}/><span>{c.name}</span></button>})}</div><p className="ww-graph-caption">{neighbors.length?`Связи выбранного персонажа · показано ${Math.min(neighbors.length,5)} из ${neighbors.length}. Выберите человека на карте или в списке.`:'Связей пока нет. Можно выбрать другого персонажа или добавить отношение.'}</p></section><section className="ww-relation-list">{children(source)}<p className="ww-inline-note">Направление важно: отношение одного человека к другому редактируется отдельно от ответного чувства. Семья и социальные связи хранятся отдельно.</p></section></div>;
}
