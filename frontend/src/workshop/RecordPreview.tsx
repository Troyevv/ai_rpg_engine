import {useState} from 'react';
import {Link,MapPin,Building2} from 'lucide-react';
import {CharacterAvatar} from '../Portrait';
import {enumLabels} from '../runtimePresentation';
import {ReadableText} from './ReadableText';
import type {WorkshopCharacter} from './CharacterCollection';
type Item=Record<string,unknown>;

export function PeopleChips({ids,characters,wid,author,onOpen}:{ids:unknown;characters:WorkshopCharacter[];wid:string;author:boolean;onOpen:(id:string)=>void}){
 const [expanded,setExpanded]=useState(false);
 const people=[...new Set(Array.isArray(ids)?ids:[])].map(id=>characters.find(c=>c.id===id)).filter((c):c is WorkshopCharacter=>!!c);
 if(!people.length)return null;
 return <div className="ww-people-chips">{(expanded?people:people.slice(0,6)).map(c=><button key={c.id} onClick={()=>onOpen(c.id)} aria-label={`Открыть досье ${c.name}`}><CharacterAvatar subject={c} workspaceId={wid} author={author} size={30}/><span>{c.name}</span></button>)}{people.length>6&&<button onClick={()=>setExpanded(!expanded)} aria-expanded={expanded}>{expanded?'Свернуть участников':`Ещё ${people.length-6}`}</button>}</div>;
}

/** Present the already authorized projection; no visibility or Knowledge rules live here. */
export function RecordPreview({kind,item,id,characters,wid,author,knowledge,onOpen,sceneLabel,currentScene}:{kind:string;item:Item;id:string;characters:WorkshopCharacter[];wid:string;author:boolean;knowledge:Record<string,Item>;sceneLabel?:string;currentScene?:boolean;onOpen:(id:string)=>void}){
 const people=(ids:unknown)=><PeopleChips {...{ids,characters,wid,author,onOpen}}/>;
 const name=(id:unknown)=>characters.find(c=>c.id===id)?.name||'Персонаж не указан';
 if(kind==='relationship'){const target=characters.find(c=>c.id===item.target_id);return <div className="ww-directed-row">{target&&<CharacterAvatar subject={target} workspaceId={wid} author={author} size={40}/>}<div><h3>{name(item.source_id)} → {name(item.target_id)}</h3><ReadableText text={String(item.context||'Отношение пока не описано.')} limit={220}/></div></div>}
 if(kind==='objective_relations')return <><div className="ww-relation-pair">{[item.source_id,item.target_id].map((id,i)=>{const c=characters.find(c=>c.id===id);return <span key={i}>{i>0&&<Link size={18}/>} {c&&<CharacterAvatar subject={c} workspaceId={wid} author={author} size={42}/>}</span>})}</div><h3>{name(item.source_id)} и {name(item.target_id)}</h3>{kind==='objective_relations'&&<span className="ww-record-badge">{enumLabels[String(item.kind)]||String(item.kind)}</span>}<ReadableText text={String(item.context||'Отношение пока не описано.')} limit={220}/></>;
 if(kind==='fact'){
  const known=Object.values(knowledge).filter(k=>k.fact_id===id&&k.status==='known').map(k=>k.actor_id);
  return <div className={item.secret?'ww-fact-copy is-secret':'ww-fact-copy'}><span className="ww-record-badge">{item.secret?'Тайна':'Открытый факт'}</span><ReadableText text={String(item.text||'Факт пока не описан.')} limit={400}/>{known.length>0&&<><small>Подтверждённое знание</small>{people(known)}</>}{Array.isArray(item.evidence)&&item.evidence.length>0&&<p className="ww-record-evidence">Источник: {item.evidence.join(' · ')}</p>}</div>;
 }
 if(kind==='thread')return <><h3>{String(item.description||'Сюжетная линия')}</h3>{!!(item.state||item.public_state)&&<div className="ww-inline-note"><ReadableText text={String(item.state||item.public_state)} limit={280}/></div>}{people(item.character_ids)}</>;
 if(kind==='scene')return <><span className="ww-record-badge">{currentScene?'Стартовая сцена':'Сцена'}</span><h3>{sceneLabel}</h3><ReadableText text={String(item.text||'Описание пока не задано.')} limit={300}/>{people(item.participants)}</>;
 if(kind==='event')return <><ReadableText text={String(item.text||'Событие пока не описано.')} limit={400}/>{people(item.participants)}</>;
 if(kind==='location'||kind==='organizations')return <>{kind==='location'?<MapPin size={21}/>:<Building2 size={21}/>}<h3>{String(item.name||'Без названия')}</h3><ReadableText text={String(item.text||item.context||'Описание пока не задано.')} limit={240}/></>;
 return null;
}
