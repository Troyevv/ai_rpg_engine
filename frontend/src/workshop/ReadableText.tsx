import {useState} from 'react';
export function ReadableText({text,limit=360}:{text:string;limit?:number}){
 const [expanded,setExpanded]=useState(false);const long=text.length>limit;
 return <div className="ww-readable"><p className="workshop-literary">{long&&!expanded?text.slice(0,limit).trimEnd()+'…':text}</p>{long&&<button className="ww-text-button" aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>{expanded?'Свернуть описание':'Читать полностью'}</button>}</div>;
}
