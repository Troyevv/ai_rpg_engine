import {useMemo} from 'react';
import {Smartphone, Home} from 'lucide-react';
import {PhoneFrame} from './PhoneFrame';
import {usePhone, DeviceProvider, type PhoneProps} from './phone/usePhone';
import {apps,type PhoneApp} from './phone/registry';
import {Chrome} from './phone/apps/Chrome';
import {formatDateLabel} from './gameDate';
import './styles/phone.css';
import './styles/smartphone.css';

export type {PhoneEvent,PhoneState,Conversation} from './phone/types';

function branchScope(props:PhoneProps){
  const key='phone-lineage:'+props.save.id;
  const turns=props.save.turns.map(t=>t.active_variant_id);
  let generation=0;
  try{
    const last=JSON.parse(sessionStorage.getItem(key)||'null');
    if(last){generation=last.generation;if(last.turns.some((id:string,i:number)=>turns[i]!==id))generation++}
  }catch{/* A discarded presentation cache starts at Home. */}
  sessionStorage.setItem(key,JSON.stringify({turns,generation}));
  return [props.save.id,props.save.state.phone?.actor_id,generation].join(':');
}

export function Phone(props:PhoneProps & {registry?:readonly PhoneApp[]}){
  const scope=useMemo(()=>branchScope(props),[props.save.id,props.save.turns,props.save.state.phone?.actor_id]);
  if(!props.save.state.phone)return null;
  return <PhoneShell key={scope} scope={scope} {...props}/>;
}

function PhoneShell({registry=apps,scope,...props}:PhoneProps & {scope:string;registry?:readonly PhoneApp[]}){
  const d=usePhone(props,scope);
  const available=registry.filter(app=>app.available(d.phone.capabilities));
  const app=available.find(app=>app.id===d.tab);
  const Screen=app?.screen;
  const clock=d.save.state.world_clock?.projection;
  if(!available.length)return null;
  return <DeviceProvider value={d}>
    <button ref={d.trigger} className="phone-peek nr-phonebutton" aria-label={`Телефон${d.unread?', непрочитано: '+d.unread:''}`} aria-expanded={d.open}
      onClick={()=>{if(d.open)d.close();else{d.home();d.setOpen(true)}}}><Smartphone size={16}/><span className="nr-phone-label">Телефон</span>
      {(d.unread>0||d.call)&&<span className="nr-unread">{d.unread||'•'}</span>}</button>
    <PhoneFrame save={props.save} open={d.open} close={d.close} closeLabel="Свернуть телефон">
      <div ref={d.screen} className={'phone-screen'+(d.dialing?' phone-connecting':'')} role="region" aria-label="Телефон персонажа" tabIndex={-1} inert={!d.open} aria-hidden={!d.open}>
        <Chrome label={app?.title||''}/>
        <div ref={d.list} onScroll={e=>{d.listPositions.current[d.listKey]=e.currentTarget.scrollTop}}
          className={'phone-body '+(d.inChat&&!d.membersOpen?'phone-chat':'')+(!Screen?' smart-home':'')} >
          {!Screen?<><div className="smart-clock"><time>{clock?.time}</time><span>{clock?.date?formatDateLabel(clock.date):'День '+(clock?.day||1)}</span></div>
            <nav className="smart-grid" aria-label="Приложения">{available.map(({id,title,icon:Icon})=>{
              const count=d.displayBadge(id);
              return <button key={id} data-app={id} className={'smart-icon app-'+id} aria-label={title} onClick={()=>{
                d.navigate(id);
              }}><span className="smart-tile"><Icon/>{count>0&&<small aria-label={count+' новых'}>{count>99?'99+':count}</small>}</span><span>{title}</span></button>
            })}</nav>{d.phone.notices?.map(n=>{
              const target=available.find(a=>a.id===n.app);
              if(!target)return null;
              return <button key={n.app} className="smart-home-notice" onClick={()=>target.openNotice?target.openNotice(d,n.id):d.navigate(n.app,{screen:n.screen,id:n.id})}><target.icon size={17}/>{n.label}</button>
            })}</>:d.open&&<Screen/>}
        </div>
        {Screen&&<button className="smart-home-key" aria-label="Домой" onClick={d.home}><Home size={16}/>Домой</button>}
      </div>
    </PhoneFrame>
  </DeviceProvider>
}
