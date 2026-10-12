import {useEffect, useRef, useState, type CSSProperties} from 'react';
import {Pencil} from 'lucide-react';
import {api} from './api';
import type {Character, Save} from './types';
import {Dialog, DialogContent, DialogTitle, DialogDescription} from './components/ui/dialog';
import './styles/portraits.css';

export interface PortraitRef {
 id:string;asset_id:string;width:number;height:number;crop:{x:number;y:number;zoom:number};
 label:string;stage?:string;min_age?:number|null;max_age?:number|null;order?:number;
}
export type PortraitSubject={id:string;name:string;portrait?:PortraitRef|null;silhouette?:string};
type Listing={revision:number;portraits:PortraitRef[];portrait:PortraitRef|null};
const cropDefault={x:0.5,y:0.5,zoom:1};
const path=(sid:number,cid:string)=>`/saves/${sid}/characters/${encodeURIComponent(cid)}/portraits`;
export const portraitUrl=(sid:number,cid:string,p:PortraitRef)=>'/api'+path(sid,cid)+'/assets/'+p.asset_id;
function cropStyle(p:PortraitRef):CSSProperties {
 const {width:w,height:h,crop:c}=p;
 const rw=w/Math.min(w,h)*c.zoom, rh=h/Math.min(w,h)*c.zoom;
 return {width:`${rw*100}%`,height:`${rh*100}%`,maxWidth:'none',left:`${-(rw-1)*c.x*100}%`,top:`${-(rh-1)*c.y*100}%`};
}
export function CharacterAvatar({subject,saveId,onClick,size=48}:{subject:PortraitSubject;saveId?:number;onClick?:()=>void;size?:number}) {
 const [failed,setFailed]=useState(false);const p=subject.portrait;
 useEffect(()=>setFailed(false),[p?.asset_id,saveId]);
 const initials=subject.name.trim().split(/\s+/).slice(0,2).map(s=>s[0]).join('').toUpperCase()||'?';
 const content=p&&saveId&&!failed?<img alt="" src={portraitUrl(saveId,subject.id,p)} style={cropStyle(p)} onError={()=>setFailed(true)}/>:<>
  <svg viewBox="0 0 100 100" aria-hidden="true" data-silhouette={subject.silhouette||'neutral'}>
   {subject.silhouette==='female'?<path d="M25 62 Q18 15 50 13 Q82 15 75 62Z"/>:null}
   <circle cx="50" cy="36" r={subject.silhouette==='male'?19:17}/>
   <path d={subject.silhouette==='female'?'M25 90 Q25 56 50 57 Q75 56 75 90Z':subject.silhouette==='male'?'M12 90 Q10 58 50 58 Q90 58 88 90Z':'M18 90 Q18 60 50 60 Q82 60 82 90Z'}/>
  </svg><span className="portrait-initials" style={{fontSize:Math.max(9,Math.min(18,size*.22))}}>{initials}</span></>;
 return onClick&&p&&!failed?<button type="button" className="character-avatar" style={{width:size,height:size}} onClick={onClick} aria-label={`Открыть портрет: ${subject.name}`}>{content}</button>:<span className="character-avatar" style={{width:size,height:size}} role="img" aria-label={`Портрет: ${subject.name}`}>{content}</span>;
}
function OriginalViewer({p,sid,cid,onClose}:{p:PortraitRef;sid:number;cid:string;onClose:()=>void}) {
 const [zoom,setZoom]=useState(1);const pane=useRef<HTMLDivElement>(null);const drag=useRef<{x:number;y:number;l:number;t:number}|null>(null);
 return <Dialog open onOpenChange={v=>!v&&onClose()}><DialogContent className="portrait-dialog"><DialogTitle>Портрет в полном размере</DialogTitle><DialogDescription>Оригинал без кадрирования. Увеличивай и перемещай изображение.</DialogDescription>
  <label>Масштаб<input aria-label="Масштаб просмотра" type="range" min="1" max="4" step="0.1" value={zoom} onChange={e=>setZoom(+e.target.value)}/></label>
  <div className="portrait-original" ref={pane} tabIndex={0} aria-label="Оригинал портрета" onPointerDown={e=>{const el=pane.current!;drag.current={x:e.clientX,y:e.clientY,l:el.scrollLeft,t:el.scrollTop};el.setPointerCapture(e.pointerId)}} onPointerUp={()=>drag.current=null} onPointerCancel={()=>drag.current=null} onPointerMove={e=>{const d=drag.current;if(d&&pane.current){pane.current.scrollLeft=d.l+d.x-e.clientX;pane.current.scrollTop=d.t+d.y-e.clientY}}}>
   <img src={portraitUrl(sid,cid,p)} alt={p.label||'Полный портрет'} draggable={false} style={{width:`${zoom*100}%`,height:`${zoom*100}%`,objectFit:'contain',maxWidth:'none'}}/>
  </div>
 </DialogContent></Dialog>;
}
export function PortraitControl({card,save,refresh}:{card:Character;save:Save;refresh:()=>void}) {
 const [mode,setMode]=useState<'edit'|'view'|null>(null);const [data,setData]=useState<Listing|null>(null);
 const [selected,setSelected]=useState<PortraitRef|null>(null);const [file,setFile]=useState<File|null>(null);const [preview,setPreview]=useState('');
 const [crop,setCrop]=useState(cropDefault);const [dims,setDims]=useState({width:768,height:1024});const [label,setLabel]=useState('');
 const [stage,setStage]=useState('');const [minAge,setMinAge]=useState('');const [maxAge,setMaxAge]=useState('');
 const fileInput=useRef<HTMLInputElement>(null);const [showHistory,setShowHistory]=useState(false);
 const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [confirmDelete,setConfirmDelete]=useState(false);
 const choose=(p:PortraitRef|null)=>{setSelected(p);setFile(null);setCrop(p?.crop||cropDefault);setLabel(p?.label||'');setStage(p?.stage||'');setMinAge(p?.min_age==null?'':String(p.min_age));setMaxAge(p?.max_age==null?'':String(p.max_age));setDims(p||{width:768,height:1024});setConfirmDelete(false);setError('')};
 useEffect(()=>{setMode(null);setData(null)},[card.id,save.id]);
 useEffect(()=>{if(!file){setPreview('');return}const url=URL.createObjectURL(file);setPreview(url);return()=>URL.revokeObjectURL(url)},[file]);
 const open=async()=>{setMode('edit');setError('');setData(null);try{const d=await api<Listing>(path(save.id,card.id));setData(d);choose(d.portraits.find(p=>p.id===d.portrait?.id)||d.portraits.at(-1)||null)}catch(e){setError(String(e))}};
 const upload=async()=>{
  if(!data)return;setBusy(true);setError('');
  try{
   const settings={crop,label,...(stage?{stage}:{}),min_age:minAge===''?null:Number(minAge),max_age:maxAge===''?null:Number(maxAge),make_current:true};
   if(file){
    const params=new URLSearchParams({revision:String(data.revision),settings:JSON.stringify(settings)});if(selected)params.set('replace_id',selected.id);
    const res=await fetch('/api'+path(save.id,card.id)+'?'+params,{method:'POST',headers:{'Content-Type':file.type},body:file});
    if(!res.ok)throw new Error((await res.json()).detail||'Ошибка загрузки');
   }else if(selected)await api(path(save.id,card.id)+'/'+selected.id,{revision:data.revision,...settings},'PATCH');
   setMode(null);refresh();
  }catch(e){setError(String(e))}finally{setBusy(false)}
 };
 const remove=async()=>{if(!data||!selected)return;setBusy(true);try{await api(path(save.id,card.id)+'/'+selected.id+'?revision='+data.revision,undefined,'DELETE');setMode(null);refresh()}catch(e){setError(String(e))}finally{setBusy(false)}};
 const source=preview||(selected?portraitUrl(save.id,card.id,selected):'');
 const loadFile=(f:File|undefined)=>{if(!f)return;setError('');if(f.size>10*1024*1024||!['image/png','image/jpeg','image/webp'].includes(f.type)){setError('Нужен PNG, JPEG или WebP до 10 MiB.');return}setFile(f);setCrop(cropDefault)};
 return <div className="portrait-control">
  <CharacterAvatar subject={card} saveId={save.id} size={88} onClick={()=>{if(card.portrait){setSelected(card.portrait);setMode('view')}}}/>
  <button type="button" className="portrait-pencil" aria-label="Редактировать портрет" onClick={()=>void open()}><Pencil size={18}/></button>
  {mode==='view'&&selected&&<OriginalViewer p={selected} sid={save.id} cid={card.id} onClose={()=>setMode(null)}/>}
  <Dialog open={mode==='edit'} onOpenChange={v=>{if(!v&&!busy)setMode(null)}}><DialogContent className="portrait-dialog"><DialogTitle>Портрет персонажа</DialogTitle><DialogDescription>PNG, JPEG или WebP · до 10 MiB · 256–4096 px по каждой стороне. Рекомендуется 3:4. Оригинал сохраняется целиком.</DialogDescription>
   {error&&<p role="alert">{error}</p>}
   {data&&<><div className="portrait-actions"><button type="button" onClick={()=>{choose(null);fileInput.current?.click()}}>Загрузить новый портрет</button><button type="button" disabled={!selected} onClick={()=>document.querySelector<HTMLInputElement>('[aria-label="Масштаб кадрирования"]')?.focus()}>Изменить кадрирование</button><button type="button" onClick={()=>setShowHistory(!showHistory)}>История портретов</button></div><div hidden={!showHistory} className="portrait-history" aria-label="История портретов"><button type="button" onClick={()=>choose(null)}>Новый портрет</button>{data.portraits.map(p=><button type="button" key={p.id} aria-pressed={selected?.id===p.id} onClick={()=>choose(p)}><CharacterAvatar subject={{...card,portrait:p}} saveId={save.id}/><span>{p.label||'Портрет'}{p.id===data.portrait?.id?' · текущий':' · исторический'}</span></button>)}</div>
    {source&&<><div className="portrait-crop" aria-label="Квадратное кадрирование"><img src={source} alt="Предпросмотр кадрирования" style={cropStyle({...dims,crop} as PortraitRef)} onLoad={e=>setDims({width:e.currentTarget.naturalWidth,height:e.currentTarget.naturalHeight})}/><span className="portrait-crop-circle"/></div>
     {(['x','y','zoom'] as const).map(k=><label key={k}>{{x:'По горизонтали',y:'По вертикали',zoom:'Масштаб кадрирования'}[k]}<input aria-label={{x:'По горизонтали',y:'По вертикали',zoom:'Масштаб кадрирования'}[k]} type="range" min={k==='zoom'?1:0} max={k==='zoom'?4:1} step="0.01" value={crop[k]} onChange={e=>setCrop({...crop,[k]:+e.target.value})}/></label>)}</>}
    <label>{selected?'Заменить изображение':'Загрузить портрет'}<input ref={fileInput} aria-label="Файл портрета" type="file" accept="image/png,image/jpeg,image/webp" onChange={e=>loadFile(e.target.files?.[0])}/></label>
    <label>Название<input value={label} maxLength={120} onChange={e=>setLabel(e.target.value)}/></label>
    <fieldset><legend>Период жизни</legend><div className="portrait-actions">{[['','Текущий установленный период'],['unknown','Неизвестно'],['infant','Младенчество'],['child','Детство'],['adolescent','Подростковый возраст'],['adult','Взрослый возраст']].map(([value,text])=><button type="button" key={value} aria-pressed={stage===value} onClick={()=>setStage(value)}>{text}</button>)}</div></fieldset>
    <div className="portrait-ages"><label>Возраст от<input type="number" min="0" max="10000" value={minAge} onChange={e=>setMinAge(e.target.value)}/></label><label>Возраст до<input type="number" min="0" max="10000" value={maxAge} onChange={e=>setMaxAge(e.target.value)}/></label></div>
    {selected&&!file&&<button type="button" onClick={()=>setMode('view')}>Открыть оригинал</button>}
    <div className="portrait-actions"><button type="button" disabled={busy||(!file&&!selected)} onClick={()=>void upload()}>{busy?"Сохранение…":"Сохранить"}</button><button type="button" disabled={busy} onClick={()=>setMode(null)}>Отмена</button>{selected&&<button type="button" disabled={busy} onClick={()=>setConfirmDelete(true)}>Удалить портрет</button>}</div>
    {confirmDelete&&<div role="alert"><p>Удалить портрет из текущего сохранения? В старых ходах и ветках он останется.</p><button disabled={busy} onClick={()=>void remove()}>Подтвердить удаление</button><button onClick={()=>setConfirmDelete(false)}>Оставить</button></div>}
   </>}
  </DialogContent></Dialog>
 </div>;
}
