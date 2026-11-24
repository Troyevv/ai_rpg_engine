import {useEffect,useRef,useState} from 'react';
import {Heart,Repeat2,MessageCircle,Bell,PenLine,Users,UserRound,Send} from 'lucide-react';
import {CharacterAvatar,type PortraitSubject} from '../../Portrait';
import {useDevice} from '../usePhone';
import {useRecords,useDraft,Generation} from '../data';

type Post={id:string;author:string;subject:PortraitSubject;text:string;minute:number;likes:number;liked:boolean;reposts:number;reposted:boolean;comments:number;post_id:string|null;reply_to:string|null};
type Feed={entries:{sequence:number;post:Post;by:PortraitSubject|null}[];next:string|null;profile:{subject:PortraitSubject;bio:string}|null};
type Notice={subject:PortraitSubject;kind:string;post_id:string;sequence:number};

function Author({subject}:{subject:PortraitSubject}){
  const {save,push}=useDevice();
  return <button className="smart-author" onClick={()=>push('profile',subject.id)}>
    <CharacterAvatar subject={subject} saveId={save.id} size={34}/><strong>{subject.name}</strong></button>
}

function PostCard({post,reply,full=false}:{post:Post;reply?:(id:string)=>void;full?:boolean}){
  const {push,command,locked}=useDevice();
  return <article className="smart-post" data-publication={post.id}>
    <Author subject={post.subject}/><p className={full?'':'smart-excerpt'}>{post.text}</p>
    <div className="smart-actions">
      <button aria-pressed={post.liked} aria-label="Нравится" disabled={locked} onClick={()=>void command('social','like',{target:post.id,desired:!post.liked})}><Heart/>{post.likes}</button>
      {!post.post_id&&<button aria-pressed={post.reposted} aria-label="Репост" disabled={locked} onClick={()=>void command('social','repost',{target:post.id,desired:!post.reposted})}><Repeat2/>{post.reposts}</button>}
      {reply?<button onClick={()=>reply(post.id)}><MessageCircle/>Ответить</button>:<button aria-label="Открыть обсуждение" onClick={()=>push('post',post.id)}><MessageCircle/>{post.comments}</button>}
    </div>
  </article>
}

function Page({profile,cursor,pages,more}:{profile?:string;cursor:string;pages:number;more:()=>void}){
  const {data,status}=useRecords<Feed>('social?'+new URLSearchParams({...profile?{profile}:{},...cursor?{cursor}:{}}));
  const {push,phone,writeTo,dossier}=useDevice();
  const p=data?.profile;
  return <>{status}
    {p&&!cursor&&<section className="smart-profile"><Author subject={p.subject}/><p>{p.bio||'Публичное описание пока не заполнено.'}</p>
      <div className="smart-actions">{p.subject.id===phone.actor_id?<button onClick={()=>push('edit')}><PenLine/>О себе</button>:<>
        <button onClick={()=>dossier(p.subject.id)}>Карточка NPC</button>
        {phone.recipients?.some(r=>r.id===p.subject.id&&r.can_send)&&<button onClick={()=>writeTo(p.subject.id)}><Send/>Написать</button>}</>}</div></section>}
    {data&&!cursor&&!data.entries.length&&<div className="smart-empty"><MessageCircle/><p>Публикаций пока нет.</p></div>}
    {data?.entries.map(e=><div key={e.sequence}>{e.by&&<div className="smart-repost"><Repeat2 size={14}/><Author subject={e.by}/></div>}<PostCard post={e.post}/></div>)}
    {data?.next&&(pages>1?<Page key={data.next} profile={profile} cursor={data.next} pages={pages-1} more={more}/>:<button className="smart-more" onClick={more}>Показать ещё</button>)}</>
}

function Timeline({profile}:{profile?:string}){
  const {scope}=useDevice();
  const key='feed-depth:'+scope+':'+(profile||'all');
  const [pages,setPages]=useState(()=>Number(sessionStorage.getItem(key))||1);
  const more=()=>{setPages(pages+1);sessionStorage.setItem(key,String(pages+1))};
  return <div className="smart-feed"><Page profile={profile} cursor="" pages={pages} more={more}/></div>
}

function Compose({target,initial='',mode}:{target?:string;initial?:string;mode:'post'|'comment'|'profile'}){
  const {command,locked,back}=useDevice();
  const [text,setText]=useDraft(mode+':'+(target||''),initial);
  const label={comment:'Ваш комментарий',post:'Текст публикации',profile:'Публичное описание'}[mode];
  return <form className="smart-compose" onSubmit={async e=>{
    e.preventDefault();
    if(await command('social',mode,{text,...target?{target}:{}},mode!=='profile')){
      setText('');if(mode!=='comment')back();
    }
  }}><label>{label}<textarea rows={mode==='comment'?3:7} maxLength={5000} value={text} onChange={e=>setText(e.target.value)} placeholder={mode==='post'?'Чем хочется поделиться?':undefined}/></label>
    <button className="smart-primary" disabled={locked||(!text.trim()&&mode!=='profile')}><Send size={16}/>{mode==='profile'?'Сохранить':mode==='comment'?'Отправить комментарий':'Опубликовать'}</button></form>
}

function EditProfile(){
  const {phone}=useDevice();const {data,status}=useRecords<Feed>('social?profile='+encodeURIComponent(phone.actor_id));
  return <>{status}{data&&<Compose mode="profile" initial={data.profile?.bio}/>}</>
}

function Discussion({id}:{id:string}){
  const {data,status}=useRecords<{post:Post;comments:Post[]}>('social?post='+encodeURIComponent(id));
  const [target,setTarget]=useState(id);
  const reply=(cid:string)=>{setTarget(cid);requestAnimationFrame(()=>document.querySelector<HTMLTextAreaElement>('.smart-compose textarea')?.focus())};
  return <>{status}{data&&<><PostCard post={data.post} full reply={reply}/><h3>Обсуждение · {data.comments.length}</h3>
    {data.comments.map(c=><div key={c.id}>{c.reply_to!==data.post.id&&<small>Ответ для {data.comments.find(v=>v.id===c.reply_to)?.subject.name}</small>}<PostCard post={c} full reply={reply}/></div>)}
    {target!==data.post.id&&<small>Ответ для {data.comments.find(v=>v.id===target)?.subject.name}</small>}<Compose mode="comment" target={target}/></>}</>
}

function Notifications(){
  const {data,status}=useRecords<Notice[]>('social/notifications');const {push}=useDevice();
  return <>{status}<h3>Уведомления</h3>{data&&!data.length&&<p>Реакций на ваши записи пока нет.</p>}{data?.map(n=><button className="smart-notice" key={n.sequence} onClick={()=>push('post',n.post_id)}>
    <strong>{n.subject.name}</strong> · {{comment:'комментарий',like:'отметка «Нравится»',repost:'репост'}[n.kind]}</button>)}</>
}

function useVisiblePublications(){
  const device=useDevice();const latest=useRef(device);latest.current=device;
  const read=useRef(new Set<string>());
  useEffect(()=>{
    const root=device.list.current;if(!root||device.locked||device.error||device.job?.kind==='smartphone'&&['error','stopped'].includes(device.job.status))return;
    const pending=new Set<string>();let timer:ReturnType<typeof setTimeout>;
    const observer=new IntersectionObserver(entries=>{
      for(const e of entries){
        const id=(e.target as HTMLElement).dataset.publication;
        if(e.isIntersecting&&id&&!read.current.has(id))pending.add(id);
      }
      if(!pending.size)return;
      clearTimeout(timer);
      timer=setTimeout(async()=>{
        const ids=[...pending].slice(0,80);
        if(ids.length&&await latest.current.command('social','read',{ids}))ids.forEach(id=>read.current.add(id));
      },600);
    },{root});
    const attach=()=>root.querySelectorAll('[data-publication]').forEach(el=>observer.observe(el));
    const changes=new MutationObserver(attach);changes.observe(root,{childList:true,subtree:true});attach();
    return ()=>{clearTimeout(timer);observer.disconnect();changes.disconnect()};
  },[device.locked,device.error,device.job?.status,device.route,device.save.revision]);
}

export function Social(){
  const {route,push,phone}=useDevice();
  useVisiblePublications();
  return <div className="smart-app"><Generation app="social"/>
    {!route&&<nav className="smart-toolbar"><button onClick={()=>push('compose')}><PenLine/>Пост</button><button onClick={()=>push('profile',phone.actor_id)}><UserRound/>Профиль</button><button aria-label="Все профили" onClick={()=>push('people')}><Users/></button><button aria-label="Уведомления" onClick={()=>push('notifications')}><Bell/></button></nav>}
    {route?.screen==='people'?<People/>:route?.screen==='compose'?<Compose mode="post"/>:route?.screen==='edit'?<EditProfile/>:route?.screen==='notifications'?<Notifications/>:route?.screen==='post'?<Discussion key={route.id} id={route.id!}/>:<Timeline key={route?.id||'feed'} profile={route?.id}/>}
  </div>
}

function People(){
  const {save,push}=useDevice();
  return <div className="smart-people">{save.state.characters.map(c=><button key={c.id} onClick={()=>push('profile',c.id)}><UserRound/>{c.name}</button>)}</div>
}
