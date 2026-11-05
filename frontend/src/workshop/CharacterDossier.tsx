import {Children,useId,useState,type ReactNode} from 'react';
import {Dialog,DialogContent,DialogTitle,DialogDescription} from '../components/ui/dialog';
import {CharacterAvatar,PortraitControl} from '../Portrait';
import {SectionTabs} from '../components/ui/section-tabs';
import type {WorkshopCharacter} from './CharacterCollection';

type Item=Record<string,unknown>;
const tabs=[['profile','Основное'],['personality','Личность'],['life','Сейчас'],['goals','Цели'],['connections','Связи'],['knowledge','Знания']] as const;
type Tab=typeof tabs[number][0];
const cardSection=(key:string):Tab=>['Внешность','Роль','Возраст','Пол'].includes(key)?'profile':['Сейчас','Статус'].includes(key)?'life':['Чего хочет','Намерения','Обязательства'].includes(key)?'goals':'personality';
const actorSection=(key:string):Tab=>['goals','intentions','obligations'].includes(key)?'goals':['personality','values','appearance'].includes(key)?'personality':['birth_date','biological_sex','life_status','developmental_stage','identity_components','name_history','display_name'].includes(key)?'profile':'life';
const dynamic:Record<string,string>={'Сейчас':'situation','Чего хочет':'goals','Намерения':'intentions','Обязательства':'obligations'};
const filled=(v:unknown)=> v!=null && v!=='' && (typeof v!=='object'||Object.keys(v).length>0);
const unavailable:Record<Tab,string>={
 profile:'Общие сведения пока не указаны.',personality:'Сведений о характере и биографии пока нет.',
 life:'Текущее положение пока не описано.',goals:'Целей, намерений и обязательств для показа нет.',
 connections:'Для показа нет связей.',knowledge:'Для показа нет известных фактов.'
};
type Props={
 open:boolean;onClose:()=>void;card?:WorkshopCharacter;characters:WorkshopCharacter[];wid:string;author:boolean;locked:boolean;
 actor:Item;actorFields:string[];row:(kind:string,id:string,field:string,value:unknown,editable?:boolean)=>ReactNode;
 onAddValues:()=>void;connections:ReactNode[];knowledge:ReactNode[];life:ReactNode[];refresh:()=>void|Promise<void>;onSelect:(id:string)=>void;
 onEdit:()=>void;protagonist?:string;locationLabel:string;onRegenerate:()=>void;onDelete:()=>void;returnFocus:()=>void;
};
export function CharacterDossier({open,onClose,card,characters,wid,author,locked,actor,actorFields,row,onAddValues,connections,knowledge,life,refresh,onSelect,onRegenerate,onDelete,returnFocus,onEdit,protagonist,locationLabel}:Props) {
 const [tab,setTab]=useState<Tab>('profile');const panel=useId();const [query,setQuery]=useState('');
 const appearance=actor.appearance as {items?:Item;legacy_text?:string}|undefined;
 const personality=actor.personality as {items?:Item;evidence?:Item}|undefined;
 const hasValues=filled(actor.values);
 const entries:ReactNode[]=[];
 if(card){
  if(tab==='connections')entries.push(...connections);
  else if(tab==='knowledge')entries.push(...knowledge);
  else{
   if(tab==='profile'){
    entries.push(row('character',card.id,'name',card.name));
    if(author||card.aliases?.length)entries.push(row('character',card.id,'aliases',card.aliases||[]));
   }
   for(const [key,value] of Object.entries(card.fields)){
    if(cardSection(key)===tab && (author||filled(value)) && !(dynamic[key]&&filled(actor[dynamic[key]])))
     entries.push(row('character',card.id,'fields.'+key,value));
   }
   const mechanics:ReactNode[]=[];
   for(const key of actorFields){
    if(['portraits','procedural_portrait','portrait_mode','appearance'].includes(key)||actorSection(key)!==tab)continue;
    if(!author&&!filled(actor[key]))continue;
    if(key==='personality'&&!filled(personality?.items)&&!filled(personality?.evidence))continue;
    if(key==='values'&&!hasValues)continue;
    const dest=tab==='life'&&!['situation','location','emotion','physical_state'].includes(key)?mechanics:entries;
    dest.push(row('actor',card.id,key,actor[key]??null));
   }
   if(tab==='profile'&&appearance&&(filled(appearance.items)||appearance.legacy_text))
    entries.push(row('actor',card.id,'appearance',{items:appearance.items||{},legacy_text:appearance.legacy_text||''},false));
   if(tab==='personality'&&author&&!hasValues)
    entries.push(<button key="add-values" className="ww-soft" disabled={locked} onClick={onAddValues}>Добавить ценности</button>);
   if(tab==='life')entries.push(...life,...mechanics);
  }
 }
 const rows=Children.toArray(entries),index=characters.findIndex(c=>c.id===card?.id);
 return <Dialog open={open&&!!card} onOpenChange={v=>!v&&onClose()}>
  <DialogContent className="ww-dossier-dialog" onCloseAutoFocus={e=>{e.preventDefault();returnFocus()}}>
   <header className="ww-dossier-header"><DialogTitle>Досье персонажа</DialogTitle>
    <DialogDescription>Мастерская миров · {author?'авторское редактирование':'просмотр игрока'}</DialogDescription></header>
   {card&&<div className="ww-dossier"><aside className="ww-dossier-aside">
    {author?<PortraitControl key={wid+card.id} card={card} workspaceId={wid} refresh={refresh} disabled={locked}/>:<CharacterAvatar subject={card} workspaceId={wid} size="100%"/>}
    {!card.portrait&&card.procedural_portrait&&<small className="ww-dossier-illustration-note">Стилизованная иллюстрация</small>}
    <h2>{card.name}</h2>{card.id===protagonist&&<span className="ww-record-badge">Главный герой</span>}<p>{locationLabel}</p><p>{[card.fields['Возраст'],card.fields['Роль']].filter(Boolean).join(' · ')}</p>
    <label>Найти персонажа<input type="search" aria-label="Найти персонажа в досье" value={query} onChange={e=>setQuery(e.target.value)}/></label><label>Другие персонажи<select aria-label="Переключить досье" value={card.id} onChange={e=>onSelect(e.target.value)}>
     {characters.filter(c=>c.id===card.id||c.name.toLocaleLowerCase('ru').includes(query.trim().toLocaleLowerCase('ru'))).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
    <div className="ww-dossier-nav">{characters.slice(Math.max(0,index-3),Math.max(0,index-3)+7).map(c=>
     <button key={c.id} onClick={()=>onSelect(c.id)} aria-label={`Досье ${c.name}`} aria-pressed={c.id===card.id}>
      <CharacterAvatar subject={c} workspaceId={wid} author={author} size={32}/></button>)}</div>
    {author&&<div className="ww-dossier-actions"><button disabled={locked} onClick={onEdit}>Редактировать карточку</button><button disabled={locked} onClick={onRegenerate}>Вариант всей карточки</button>
     <button disabled={locked} onClick={onDelete}>Удалить персонажа</button></div>}
   </aside><section className="ww-dossier-body">
    <SectionTabs tablist panelId={panel} label="Разделы досье" value={tab} onChange={setTab} items={tabs.map(([id,label])=>({id,label}))}/>
    <div role="tabpanel" id={panel} aria-labelledby={`${panel}-tab-${tab}`} className="ww-dossier-fields" key={card.id+tab}>{rows.length?rows:<p className="ww-dossier-note">{unavailable[tab]}</p>}</div>
   </section></div>}
   <footer className="ww-dossier-footer"><span>{author?'Правки поля сохраняются после подтверждения. История версий доступна в мастерской.':'Режим игрока · только чтение'}</span><button onClick={onClose}>Готово</button></footer>
  </DialogContent>
 </Dialog>;
}
