import {useEffect,useRef} from 'react';
import {Heart,MapPin,Briefcase,SlidersHorizontal,Compass,ArrowRight,Send} from 'lucide-react';
import {CharacterAvatar} from '../../Portrait';
import {useDevice} from '../usePhone';
import {useRecords,Generation,useDraft} from '../data';

type Filters={gender:string;min_age:number;max_age:number;location:string;interests:string;wishes:string};
type Candidate={id:string;name:string;age:number;occupation:string;location:string;appearance:string;personality:string;bio:string;interests:string[];skipped:boolean;character_id:string|null};
type Shelf={searched:boolean;filters:Filters;results:Candidate[];liked:Candidate[]};

function Search({initial}:{initial:Filters}){
  const {command,locked,back}=useDevice();
  const [raw,store]=useDraft('dating-filters',JSON.stringify(initial));
  const filters:Filters=JSON.parse(raw);
  const set=(key:keyof Filters,value:string|number)=>store(JSON.stringify({...filters,[key]:value}));
  return <form className="smart-compose" onSubmit={async e=>{e.preventDefault();if(await command('dating','search',{filters},true))back()}}>
    <fieldset><legend>Кого искать</legend><div className="smart-segments">{[['any','Всех'],['female','Женщин'],['male','Мужчин']].map(([id,label])=><button key={id} type="button" aria-pressed={filters.gender===id} onClick={()=>set('gender',id)}>{label}</button>)}</div></fieldset>
    <div className="smart-range">{(['min_age','max_age'] as const).map((key,i)=><label key={key}>{i?'Возраст до':'Возраст от'}<input type="number" required min={i?filters.min_age:18} max={150} value={filters[key]||''} onChange={e=>set(key,Number(e.target.value))}/></label>)}</div>
    <label>Местоположение<input value={filters.location} maxLength={240} onChange={e=>set('location',e.target.value)}/></label>
    <label>Интересы<input value={filters.interests} maxLength={1000} onChange={e=>set('interests',e.target.value)}/></label>
    <label>Пожелания к внешности и характеру<textarea value={filters.wishes} rows={3} maxLength={1500} onChange={e=>set('wishes',e.target.value)}/></label>
    <button className="smart-primary" disabled={locked}><Compass/>Найти анкеты</button>
  </form>
}

function Profile({c,details=false}:{c:Candidate;details?:boolean}){
  const {push,back,command,locked,dossier,writeTo,phone,save}=useDevice();
  const character=save.state.characters.find(person=>person.id===c.character_id);
  return <article className="dating-card"><div className="dating-art" aria-hidden>{character?<CharacterAvatar subject={character} saveId={save.id} size={72}/>:<span className="dating-monogram">{c.name.split(/\s+/).slice(0,2).map(n=>n[0]).join('')}</span>}<i/></div>
    <div className="dating-copy"><h2>{c.name}, {c.age}</h2><p className="dating-place"><MapPin/>{c.location}</p>
    <p className="dating-place"><Briefcase/>{c.occupation}</p><p>{c.bio}</p><div className="dating-tags">{c.interests.map((v,i)=><span key={i}>{v}</span>)}</div>
    {details?<><h3>Внешность</h3><p>{c.appearance}</p><h3>Характер</h3><p>{c.personality}</p></>:<button className="smart-text" onClick={()=>push('candidate',c.id)}>Подробнее <ArrowRight size={15}/></button>}
    {c.character_id?<div className="smart-actions"><button onClick={()=>dossier(c.character_id!)}>Карточка NPC</button>{phone.recipients?.some(r=>r.id===c.character_id&&r.can_send)&&<button onClick={()=>writeTo(c.character_id!)}><Send/>Написать</button>}</div>:
      <div className="dating-controls"><button disabled={locked} onClick={async()=>{if(await command('dating','skip',{target:c.id})&&details)back()}}>Пропустить</button><button className="smart-primary" disabled={locked} onClick={()=>void command('dating','accept',{target:c.id},true)}><Heart size={16}/>Лайк</button></div>}</div></article>
}

export function Dating(){
  const {route,push,navigate,job,save}=useDevice();
  const {data,status}=useRecords<Shelf>('dating');
  const target=job?.kind==='smartphone'&&job.presentation?.action==='accept'?job.presentation.target:null;
  const accepted=data?.liked.find(c=>c.id===target);
  const presented=useRef<string|null>(null);
  useEffect(()=>{if(accepted&&job?.status==='saved'&&job.revision+1===save.revision&&presented.current!==job.id){
    presented.current=job.id;navigate('dating',{screen:'candidate',id:accepted.id});
  }},[accepted,job?.id,job?.status,save.revision]);
  const c=route?.screen==='candidate'?[...(data?.results||[]),...(data?.liked||[])].find(c=>c.id===route.id&&!c.skipped):data?.results.find(c=>!c.skipped&&!c.character_id);
  return <div className="smart-app"><Generation app="dating"/>{status}{data&&(route?.screen==='filters'?<Search initial={data.filters}/>:<>
    <nav className="smart-toolbar"><button onClick={()=>push('filters')}><SlidersHorizontal/>Параметры поиска</button><button aria-label="Понравившиеся анкеты" onClick={()=>push('liked')}><Heart/>{data.liked.length}</button></nav>
    {route?.screen==='liked'?<><h3>Понравившиеся</h3>{!data.liked.length&&<p>Здесь появятся выбранные анкеты.</p>}{data.liked.map(c=><button className="smart-notice" key={c.id} onClick={()=>push('candidate',c.id)}>{c.name}, {c.age}<ArrowRight size={16}/></button>)}</>:c?<Profile c={c} details={route?.screen==='candidate'}/>:<div className="smart-empty"><Compass/><h3>{data.results.length?'Вы просмотрели анкеты':data.searched?'По этим параметрам анкет пока нет':'Новые знакомства'}</h3><button className="smart-primary" onClick={()=>push('filters')}>Настроить поиск</button></div>}</>)}</div>
}
