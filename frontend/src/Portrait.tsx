import {useEffect, useRef, useState, type CSSProperties} from 'react';
import {Pencil} from 'lucide-react';
import {api} from './api';
import type {Save} from './types';
import {Dialog, DialogContent, DialogTitle, DialogDescription} from './components/ui/dialog';
import './styles/portraits.css';
import {proceduralPortrait,type ProceduralPortrait} from './workshop/proceduralPortrait';
import {ProceduralPortraitEditor} from './workshop/ProceduralPortraitEditor';

export interface PortraitRef {
 id:string;asset_id:string;width:number;height:number;crop:{x:number;y:number;zoom:number};
 label:string;stage?:string;min_age?:number|null;max_age?:number|null;order?:number;
}
export type PortraitSubject={id:string;name:string;fields?:Record<string,string>;portrait?:PortraitRef|null;silhouette?:string;procedural_portrait?:ProceduralPortrait|null};
type Listing={revision:number;portraits:PortraitRef[];portrait:PortraitRef|null;descriptor?:ProceduralPortrait;portrait_mode?:'auto'|'procedural'};
const cropDefault={x:0.5,y:0.5,zoom:1};
const path=(sid:number|undefined,cid:string,wid?:string)=>wid?`/workspaces/${encodeURIComponent(wid)}/draft/characters/${encodeURIComponent(cid)}/portraits`:`/saves/${sid}/characters/${encodeURIComponent(cid)}/portraits`;
export const portraitUrl=(sid:number|undefined,cid:string,p:PortraitRef,wid?:string,author=false)=>'/api'+path(sid,cid,wid)+'/assets/'+p.asset_id+(wid?'?author='+author:'');
function cropStyle(p:PortraitRef):CSSProperties {
 const {width:w,height:h,crop:c}=p;
 const rw=w/Math.min(w,h)*c.zoom, rh=h/Math.min(w,h)*c.zoom;
 return {width:`${rw*100}%`,height:`${rh*100}%`,maxWidth:'none',left:`${-(rw-1)*c.x*100}%`,top:`${-(rh-1)*c.y*100}%`};
}
export function CharacterAvatar({subject,saveId,workspaceId,author=false,onClick,size=48}:{subject:PortraitSubject;saveId?:number;workspaceId?:string;author?:boolean;onClick?:()=>void;size?:number|string}) {
 const p=subject.portrait;
 // Keep failed requests tied to their identity: a late error cannot hide a new owner's image.
 const imageKey=`${workspaceId||saveId}:${author}:${subject.id}:${p?.asset_id}`;
 const [failedKey,setFailedKey]=useState<string|null>(null);
 useEffect(()=>setFailedKey(null),[imageKey]);
 const hasImage=!!(p&&(saveId||workspaceId)&&failedKey!==imageKey);
 const silhouette=subject.silhouette==='male'||subject.silhouette==='female'?subject.silhouette:'neutral';
 const initials=subject.name.trim().split(/\s+/).slice(0,2).map(s=>Array.from(s)[0]).join('').toUpperCase()||'?';
 const style={'--avatar-size':typeof size==='number'?`${size}px`:size} as CSSProperties;
 const generated=proceduralPortrait(subject.procedural_portrait);
 const content=hasImage?<img key={imageKey} alt="" loading="lazy" decoding="async" src={portraitUrl(saveId,subject.id,p!,workspaceId,author)} style={cropStyle(p!)} onError={()=>setFailedKey(imageKey)}/>:generated?<img className="procedural-portrait" src={generated} alt="" loading="lazy" decoding="async"/>:<>
  <svg viewBox="0 0 100 100" aria-hidden="true" data-silhouette={silhouette}>
   {silhouette==='female'?<>
    <path d="M67 27 C92 20 84 47 91 57 C77 59 69 49 73 35Z"/>
    <path d="M29 34 C24 8 66 5 70 29 L65 43 L33 43Z"/>
    <ellipse cx="49" cy="34" rx="16" ry="20"/>
    <path d="M44 51 L56 51 L59 60 Q76 62 79 96 H19 Q22 62 39 60Z"/>
   </>:silhouette==='male'?<>
    <path d="M29 29 L31 16 Q50 8 69 18 L71 31 L65 24 L35 24Z"/>
    <path d="M32 26 H68 L65 45 L56 54 H44 L35 45Z"/>
    <path d="M43 52 H57 L60 59 Q82 60 89 77 L93 96 H7 L11 77 Q18 60 40 59Z"/>
   </>:<><circle cx="50" cy="32" r="18"/><path d="M18 96 V82 A32 27 0 0 1 82 82 V96Z"/></>}
  </svg><span className="portrait-initials">{initials}</span></>;
 const className=`character-avatar${hasImage||generated?'':` avatar-fallback avatar-${silhouette}`}`;
 return onClick&&hasImage?<button type="button" className={className} style={style} onClick={onClick} aria-label={`Открыть портрет: ${subject.name}`}>{content}</button>:<span className={className} style={style} role="img" aria-label={`Портрет: ${subject.name}`}>{content}</span>;
}
function OriginalViewer({p,sid,cid,wid,onClose}:{p:PortraitRef;sid?:number;cid:string;wid?:string;onClose:()=>void}) {
 const [zoom,setZoom]=useState(1);const pane=useRef<HTMLDivElement>(null);const drag=useRef<{x:number;y:number;l:number;t:number}|null>(null);
 return <Dialog open onOpenChange={v=>!v&&onClose()}><DialogContent className="portrait-dialog"><DialogTitle>Портрет в полном размере</DialogTitle><DialogDescription>Оригинал без кадрирования. Увеличивай и перемещай изображение.</DialogDescription>
  <label>Масштаб<input aria-label="Масштаб просмотра" type="range" min="1" max="4" step="0.1" value={zoom} onChange={e=>setZoom(+e.target.value)}/></label>
  <div className="portrait-original" ref={pane} tabIndex={0} aria-label="Оригинал портрета" onPointerDown={e=>{const el=pane.current!;drag.current={x:e.clientX,y:e.clientY,l:el.scrollLeft,t:el.scrollTop};el.setPointerCapture(e.pointerId)}} onPointerUp={()=>drag.current=null} onPointerCancel={()=>drag.current=null} onPointerMove={e=>{const d=drag.current;if(d&&pane.current){pane.current.scrollLeft=d.l+d.x-e.clientX;pane.current.scrollTop=d.t+d.y-e.clientY}}}>
   <img src={portraitUrl(sid,cid,p,wid,true)} alt={p.label||'Полный портрет'} draggable={false} style={{width:`${zoom*100}%`,height:`${zoom*100}%`,objectFit:'contain',maxWidth:'none'}}/>
  </div>
 </DialogContent></Dialog>;
}
export function PortraitControl({card,save,workspaceId,refresh,disabled=false}:{card:PortraitSubject;save?:Pick<Save,'id'>;workspaceId?:string;refresh:()=>void|Promise<void>;disabled?:boolean}) {
 const sid=save?.id;
 const [mode,setMode]=useState<'edit'|'view'|null>(null);const [data,setData]=useState<Listing|null>(null);
 const [selected,setSelected]=useState<PortraitRef|null>(null);const [file,setFile]=useState<File|null>(null);const [preview,setPreview]=useState('');
 const [crop,setCrop]=useState(cropDefault);const [dims,setDims]=useState({width:768,height:1024});const [label,setLabel]=useState('');
 const [stage,setStage]=useState('');const [minAge,setMinAge]=useState('');const [maxAge,setMaxAge]=useState('');
 const fileInput=useRef<HTMLInputElement>(null);const [showHistory,setShowHistory]=useState(false);
 const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [confirmDelete,setConfirmDelete]=useState(false);
 const choose=(p:PortraitRef|null)=>{setSelected(p);setFile(null);setCrop(p?.crop||cropDefault);setLabel(p?.label||'');setStage(p?.stage||'');setMinAge(p?.min_age==null?'':String(p.min_age));setMaxAge(p?.max_age==null?'':String(p.max_age));setDims(p||{width:768,height:1024});setConfirmDelete(false);setError('')};
 useEffect(()=>{setMode(null);setData(null)},[card.id,sid,workspaceId]);
 useEffect(()=>{if(!file){setPreview('');return}const url=URL.createObjectURL(file);setPreview(url);return()=>URL.revokeObjectURL(url)},[file]);
 const open=async()=>{setMode('edit');setError('');setData(null);try{const d=await api<Listing>(path(sid,card.id,workspaceId)+(workspaceId?'?author=true':''));setData(d);choose(d.portraits.find(p=>p.id===d.portrait?.id)||d.portraits.at(-1)||null)}catch(e){setError(String(e))}};
 const upload=async()=>{
  if(!data)return;setBusy(true);setError('');
  try{
   const settings={crop,label,...(stage?{stage}:{}),min_age:minAge===''?null:Number(minAge),max_age:maxAge===''?null:Number(maxAge),make_current:true};
   if(file){
    const params=new URLSearchParams({revision:String(data.revision),settings:JSON.stringify(settings)});if(selected)params.set('replace_id',selected.id);
    const res=await fetch('/api'+path(sid,card.id,workspaceId)+'?'+params,{method:'POST',headers:{'Content-Type':file.type},body:file});
    if(!res.ok)throw new Error((await res.json()).detail||'Ошибка загрузки');
   }else if(selected)await api(path(sid,card.id,workspaceId)+'/'+selected.id,{revision:data.revision,...settings},'PATCH');
   await refresh();setMode(null);
  }catch(e){setError(String(e))}finally{setBusy(false)}
 };
 const remove=async()=>{if(!data||!selected)return;setBusy(true);try{await api(path(sid,card.id,workspaceId)+'/'+selected.id+'?revision='+data.revision,undefined,'DELETE');await refresh();setMode(null)}catch(e){setError(String(e))}finally{setBusy(false)}};
 const source=preview||(selected?portraitUrl(sid,card.id,selected,workspaceId,true):'');
 const loadFile=(f:File|undefined)=>{if(!f)return;setError('');if(f.size>10*1024*1024||!['image/png','image/jpeg','image/webp'].includes(f.type)){setError('Нужен PNG, JPEG или WebP до 10 MiB.');return}setFile(f);setCrop(cropDefault)};
 return <div className="portrait-control">
  <CharacterAvatar subject={card} saveId={sid} workspaceId={workspaceId} author size="var(--dossier-portrait-size)" onClick={()=>{if(card.portrait){setSelected(card.portrait);setMode('view')}}}/>
  <button type="button" className="portrait-pencil" aria-label="Редактировать портрет" disabled={disabled} onClick={()=>void open()}><span className="portrait-pencil-face"><Pencil size={16}/></span></button>
  {mode==='view'&&selected&&<OriginalViewer p={selected} sid={sid} wid={workspaceId} cid={card.id} onClose={()=>setMode(null)}/>}
  <Dialog open={mode==='edit'} onOpenChange={v=>{if(!v&&!busy)setMode(null)}}><DialogContent className="portrait-dialog"><DialogTitle>Портрет персонажа</DialogTitle><DialogDescription>PNG, JPEG или WebP · до 10 MiB · Размер автоматически приводится к 256–4096 px по каждой стороне без обрезки и искажения. Рекомендуется 3:4.</DialogDescription>
   {!data&&!error&&<p role="status">Загрузка портретов…</p>}
   {error&&<p role="alert">{error}</p>}
   {data&&<>{workspaceId&&data.descriptor&&<ProceduralPortraitEditor renderPreview={descriptor=><CharacterAvatar subject={{...card,portrait:null,procedural_portrait:descriptor}} size={130}/>} appearance={card.fields?.['Внешность']} descriptor={data.descriptor} mode={data.portrait_mode||'auto'} disabled={busy} onSave={async(descriptor,mode)=>{setBusy(true);setError('');try{await api(path(sid,card.id,workspaceId)+'/procedural',{revision:data.revision,descriptor,mode},'PUT');await refresh();setMode(null)}catch(e){setError(String(e));throw e}finally{setBusy(false)}}}/>}<div className="portrait-actions"><button type="button" onClick={()=>{choose(null);fileInput.current?.click()}}>Загрузить новый портрет</button><button type="button" disabled={!selected} onClick={()=>document.querySelector<HTMLInputElement>('[aria-label="Масштаб кадрирования"]')?.focus()}>Изменить кадрирование</button><button type="button" onClick={()=>setShowHistory(!showHistory)}>История портретов</button></div><div hidden={!showHistory} className="portrait-history" aria-label="История портретов"><button type="button" onClick={()=>choose(null)}>Новый портрет</button>{data.portraits.map(p=><button type="button" key={p.id} aria-pressed={selected?.id===p.id} onClick={()=>choose(p)}><CharacterAvatar subject={{...card,portrait:p}} saveId={sid} workspaceId={workspaceId} author/><span>{p.label||'Портрет'}{p.id===data.portrait?.id?' · текущий':' · исторический'}</span></button>)}</div>
    {file&&Math.min(dims.width,dims.height)<256&&<p role="status">Маленькое изображение будет увеличено. Возможны размытость и ухудшение качества.</p>}
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
