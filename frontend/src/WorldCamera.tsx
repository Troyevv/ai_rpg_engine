import {SectionTabs} from "./components/ui/section-tabs";
import {useEffect,useState} from 'react';
import {toast} from 'sonner';
import {api} from './api';
import {Button} from './components/ui/button';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './components/ui/dialog';
import {Markdown} from './Markdown';
import type {Save,Scene} from './types';

type WorldEvent={id:string;text:string;minute:number|null;source_sequence:number|null;source_record_id?:string;scene_id:string|null;medium:string};
type Playback={mode:'playback';sequence:number;narrative:string;user_text:string;scene:Scene};
const time=(m:number|null|undefined)=>m==null?'Время не зафиксировано':`День ${Math.floor(m/1440)+1} · ${String(Math.floor(m%1440/60)).padStart(2,'0')}:${String(m%60).padStart(2,'0')}`;

export function WorldCamera({save,open,onOpenChange,busy,observe,control}:{save:Save;open:boolean;onOpenChange:(v:boolean)=>void;busy:boolean;observe:(actor?:string,scene?:string)=>void;control:(id:string)=>void}){
 const [tab,setTab]=useState<'camera'|'timeline'>('camera');
 const [filter,setFilter]=useState<'player'|'actor'>('player');
 const [events,setEvents]=useState<WorldEvent[]>([]);
 const [loading,setLoading]=useState(false);
 const [playback,setPlayback]=useState<Playback|null>(null);
 const [playbackLoading,setPlaybackLoading]=useState(false);
 useEffect(()=>{if(!open)return;setPlayback(null)},[open,save.id]);
 useEffect(()=>{if(!open||tab!=='timeline')return;let cancelled=false;setLoading(true);setEvents([]);
  api<WorldEvent[]>(`/saves/${save.id}/timeline?visibility=${filter}`).then(rows=>{if(!cancelled)setEvents(rows)}).catch(e=>{if(!cancelled)toast.error(e.message)}).finally(()=>{if(!cancelled)setLoading(false)});
  return()=>{cancelled=true};
 },[open,tab,filter,save.id,save.revision]);
 const view=async(event:WorldEvent)=>{const turn=save.turns.find(t=>t.sequence===event.source_sequence);if(!turn&&!event.source_record_id)return;setPlaybackLoading(true);
  try{setPlayback(await api<Playback>(event.source_record_id?`/saves/${save.id}/scene-records/${event.source_record_id}`:`/saves/${save.id}/playback/${turn!.id}`))}catch(e){toast.error((e as Error).message)}finally{setPlaybackLoading(false)};
 };
 const choose=(fn:()=>void)=>{onOpenChange(false);fn()};
 return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="world-camera mobile-sheet"><DialogHeader>
 <DialogTitle>{playback?'Записанная сцена':'Камера мира'}</DialogTitle><DialogDescription>{playback?'Просмотр прошлого. Состояние игры и время не меняются.':'Наблюдение и управление — разные действия.'}</DialogDescription></DialogHeader>
 {playback?<><Button variant="ghost" onClick={()=>setPlayback(null)}>← К журналу</Button><p className="muted small">{playback.scene.time} · {playback.scene.location}</p>{playback.user_text&&<div className="player-action"><Markdown text={playback.user_text}/></div>}<Markdown text={playback.narrative}/></>:<>
 <SectionTabs className="camera-tabs" label="Камера мира" value={tab} onChange={setTab} items={[{id:'camera',label:'Персонажи и сцены'},{id:'timeline',label:'Журнал событий'}]}/>
 {tab==='camera'?<div className="camera-cast">{save.state.characters.map(c=>{const point=save.state.world?.characters[c.id];const scene=point?.scene_id?save.state.world?.scenes[point.scene_id]:undefined;
 return <article key={c.id}><div><strong>{c.name}</strong><p className="muted small">{point?.location||'Местоположение неизвестно'}</p>{point?.minute!=null&&<p className="muted small">Последняя точка: {time(point.minute)}</p>}{scene&&<p className="muted small">{scene.participants.map(id=>save.state.characters.find(c=>c.id===id)?.name).join(' · ')}</p>}</div><div className="camera-actions"><Button variant="ghost" size="sm" disabled={busy||!save.turns.length} onClick={()=>choose(()=>observe(c.id))}>Наблюдать</Button><Button variant="outline" size="sm" disabled={busy||save.state.controlled_actor_id===c.id} onClick={()=>choose(()=>control(c.id))}>Играть за персонажа</Button></div></article>})}</div>:<>
 <label className="timeline-filter">Показать<select aria-label="Видимость событий" value={filter} onChange={e=>setFilter(e.target.value as 'player'|'actor')}><option value="player">Известно игроку</option><option value="actor">Известно текущему персонажу</option></select></label>
 {filter==='actor'&&save.state.controlled_actor_id===null&&<p className="muted">Сейчас камера наблюдает мир. Выбери управляемого персонажа для его журнала.</p>}
 {loading?<p role="status">Загружаю события…</p>:events.length?<ol className="world-timeline">{events.map(e=><li key={e.id}><span className="eyebrow">{time(e.minute)}</span><p>{e.text}</p>{e.source_sequence!=null&&save.turns.some(t=>t.sequence===e.source_sequence)&&<Button size="sm" variant="ghost" disabled={playbackLoading} onClick={()=>void view(e)}>Посмотреть сцену</Button>}</li>)}</ol>:<p className="muted">Пока нет подтверждённых событий для этого фильтра.</p>}
 </>}
 </>}
 </DialogContent></Dialog>;
}
