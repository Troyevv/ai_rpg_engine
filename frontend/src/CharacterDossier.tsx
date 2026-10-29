import {personalRelationships} from './lib/personalRelationships';
import {personalRelationshipLabel} from './lib/dossier';
import {phoneText} from './lib/phone';
import {useId, type ReactNode} from 'react';
import {UserRound,Brain,HeartHandshake,Users,BookOpen,MapPin,ArrowUpRight} from 'lucide-react';
import {CharacterAvatar,PortraitControl} from './Portrait';
import {SectionTabs} from './components/ui/section-tabs';
import {Reveal,KnowledgeRows,RelationsView,brief} from './InspectorViews';
import {MotivationEditor} from './MotivationEditor';
import {RelationshipEditor} from './RelationshipEditor';
import {SocialStateView} from './SocialStateView';
import {Markdown} from './Markdown';
import {calendarDate} from './gameDate';
import {worldTime} from './lib/worldTime';
import {lifeLabel} from './lib/social';
import {dossierText as t,capabilityLabel,personalityFields,type DossierTab} from './lib/dossier';
import type {State,Character,Save} from './types';
import './styles/dossier.css';

export function DossierSection({title,children,wide=false}:{title:string;children:ReactNode;wide?:boolean}){
 return <section className={`dossier-card${wide?' dossier-wide':''}`}><h3>{title}</h3>{children}</section>;
}
export function DossierEmpty({children}:{children?:ReactNode}){return <p className="dossier-empty">{children||t('unknown')}</p>}
export function DossierFact({label,children}:{label:string;children:ReactNode}){return <div className="dossier-fact"><dt>{label}</dt><dd>{children||t('unknown')}</dd></div>}
function Prose({text}:{text?:string}){
 return !text?<DossierEmpty/>:text.length>400?<Reveal title={brief(text,180)} text={text} preview={false}/>:<Markdown text={text}/>;
}
export function CharacterView({state,card,save,refresh,tab='overview',setTab=()=>{},onCharacter}:{state:State;card:Character;save?:Save|null;refresh?:()=>void;tab?:DossierTab;setTab?:(t:DossierTab)=>void;onCharacter:(id:string)=>void}){
 const panelId=useId();
 const c=state.world?.characters[card.id];
 const main=state.protagonist_id||state.characters.find(c=>c.is_player)?.id;
 const actor=state.controlled_actor_id===undefined?main:state.controlled_actor_id;
 const knowledge=Object.values(state.world?.knowledge||{}).filter(k=>k.actor_id===card.id&&k.status!=='unknown');
 const sex=card.dossier?.sex;
 const personal=personalRelationships(card.id,state.objective_relations,state.characters);
 const deceased=state.genealogy?.nodes.some(c=>c.id===card.id&&c.life_status==='dead');
 const partners=new Map(state.characters.map(c=>[c.id,c]));
 const age=c?.age??card.fields['Возраст'];
 const special=new Set(['Возраст','Пол','Статус','Место','Время','Сейчас','Чего хочет','Намерения','Обязательства','Физическое состояние']);
 const fields=Object.entries(card.fields).filter(([k])=>!special.has(k)&&!k.startsWith('Отношение к '));
 const items=([['overview',UserRound],['personality',Brain],['relationships',HeartHandshake],['family',Users],['history',BookOpen]] as const).map(([id,Icon])=>({id,label:t(id),icon:<Icon className={`dossier-icon-${id}`} size={16} aria-hidden="true"/>}));
 const conditions=card.dossier?.conditions||[];
 const activeConditions=conditions.filter(c=>['active','unknown_outcome'].includes(c.status));
 const conditionRows=(rows:typeof conditions)=>rows.map(r=><div className="dossier-condition" key={r.id}><strong>{r.description}</strong><span className="pill">{t(r.status as 'active')}</span>{r.duration==='persistent'&&<p>{t('persistent')}</p>}{r.since!=null&&<p className="muted small">{worldTime(r.since,state.world_clock?.calendar)}{r.until!=null?` → ${worldTime(r.until,state.world_clock?.calendar)}`:''}</p>}{r.restrictions.map(k=><p key={k}>{capabilityLabel(k)}</p>)}{r.evidence&&<Reveal title={t('evidence')} text={r.evidence} preview={false}/>}</div>);
 return <article className="inspector-content character-profile" aria-label={t('dossier')}>
  <header className="character-header dossier-header">
   {save&&refresh?<PortraitControl key={`${save.id}:${actor}:${card.id}`} card={card} save={save} refresh={refresh}/>:<CharacterAvatar subject={card} size="var(--dossier-portrait-size)"/>}
   <div className="dossier-identity"><p className="eyebrow">{t('dossier')}</p><div className="dossier-name"><h2>{card.name}</h2>{(sex==='male'||sex==='female')&&<span className={`dossier-sex ${sex}`} role="img" aria-label={t(sex)} title={t(sex)}>{sex==='male'?'♂':'♀'}</span>}</div>
    <div className="inspect-chips">{card.id===main&&<span className="pill">{t('protagonist')}</span>}{card.id===actor&&<span className="pill">{t('controlled')}</span>}{card.id===state.camera?.subject_id&&state.camera.mode==='observer'&&<span className="pill">{t('observed')}</span>}{age!==undefined&&age!==''&&<span className="pill">{t('age')}: {age}</span>}</div>
    {tab==='overview'&&<div className="dossier-personal" role="group" aria-label={t('personal')}>
     <div className="dossier-personal-label"><HeartHandshake size={15} aria-hidden="true"/><span>{t('personal')}</span></div>
     {personal.length?<ul>{personal.map(row=><li key={'partnerId' in row?row.partnerId:row.kind}>
      <span>{row.kind==='widowed'&&deceased?t('marriageEnded'):personalRelationshipLabel(row.kind,sex)}</span>{'partnerId' in row&&<button type="button" className="dossier-partner-link" data-partner-id={row.partnerId} aria-label={`${t('open')}: ${partners.get(row.partnerId)!.name}`} onClick={()=>onCharacter(row.partnerId)}>{partners.get(row.partnerId)!.name}</button>}
     </li>)}</ul>:<p className="dossier-personal-empty">{t('noPersonal')}</p>}
    </div>}
    {card.fields['Статус']&&<p className="character-lead">{brief(card.fields['Статус'],150)}</p>}
    <p className="dossier-location"><MapPin size={15} aria-hidden="true"/>{c?.location||card.fields['Место']||t('unknown')}</p>
   </div>
  </header>
  <SectionTabs items={items} value={tab} onChange={setTab} label={t('tabs')} tablist panelId={panelId} className="dossier-tabs"/>
  <div id={panelId} role="tabpanel" aria-labelledby={`${panelId}-tab-${tab}`} tabIndex={0} className="dossier-panel" key={`${card.id}:${actor}:${tab}`}>
   {tab==='overview'&&<div className="dossier-columns"><div className="dossier-column">
    <DossierSection title={t('current')}><Prose text={c?.situation||card.fields['Сейчас']}/>{c?.emotion&&<p className="dossier-emotion">{card.id===actor?'Последняя заявленная эмоция: ':''}{c.emotion}{card.id===actor&&c.emotion_source_sequence!=null?` · ход ${c.emotion_source_sequence+1}`:''}</p>}
     <dl><DossierFact label={t('birth')}>{c?.birth_date?calendarDate(c.birth_date):null}</DossierFact><DossierFact label={t('lastPoint')}>{c?.minute!=null?worldTime(c.minute,state.world_clock?.calendar):card.fields['Время']}</DossierFact></dl>
    </DossierSection>
    <DossierSection title={t('physical')}>{card.id===actor&&state.life_state&&<p className="muted small">{lifeLabel(state.life_state.life_status)}</p>}<Prose text={c?.physical_state||card.fields['Физическое состояние']}/><h4>{t('conditions')}</h4>{activeConditions.length?conditionRows(activeConditions):<DossierEmpty>{t('emptyConditions')}</DossierEmpty>}{card.dossier?.restrictions.map(k=><p key={k}>{capabilityLabel(k)}</p>)}</DossierSection>
    </div><div className="dossier-column">
    {fields.filter(([k,v])=>v.trim()&&!personalityFields.has(k)&&!['Тайны','Знания','Заметки','История'].includes(k)).map(([k,v])=><DossierSection key={k} title={k}><Prose text={v}/></DossierSection>)}
    <SocialStateView state={state} actor={card.id} saveId={save?.id} mode="context"/>
   </div></div>}
   {tab==='personality'&&<div className="dossier-grid">
    {!fields.some(([k,v])=>personalityFields.has(k)&&v.trim())&&<DossierEmpty/>}
    {fields.filter(([k,v])=>personalityFields.has(k)&&v.trim()).map(([k,v])=><DossierSection key={k} title={k}><Prose text={v}/></DossierSection>)}
    <DossierSection title="Цели, намерения и обязательства" wide><p className="muted small">Сведения ведущего; могут быть неизвестны другим персонажам.</p>{save&&refresh&&card.id===actor?<MotivationEditor key={`${save.id}:${card.id}`} save={save} card={card} refresh={refresh}/>:<><h4>Цель</h4><Prose text={c?.short_goal||card.fields['Чего хочет']}/><h4>Намерения</h4><Prose text={c?.intentions?.join('\n\n')||card.fields['Намерения']}/></>}
     <h4>{phoneText('plans')}</h4>{Object.values(state.world?.scheduled_events||{}).filter(p=>p.character_ids.includes(card.id)).map(p=><p key={p.id}>{p.description} · {p.start_label||'Время уточняется'} · {p.character_ids.map(id=>state.characters.find(c=>c.id===id)?.name||id).join(', ')} · {p.status==='pending'?'План':p.status==='resolved'?'Состоялось':'Отменено'}</p>)}
     <Reveal title="Обязательства" text={c?.obligations?.join('\n\n')||card.fields['Обязательства']} preview={false}/>
     {c?.lifecycle&&<details><summary>История целей и намерений</summary>{Object.values(c.lifecycle).flatMap(rows=>rows.filter(r=>r.status!=='active'||r.review_required?.length).map(r=><p key={r.id}>{r.review_required?.length?'Требует переоценки':({completed:'Завершено',cancelled:'Отменено',blocked:'Заблокировано',failed:'Не выполнено',expired:'Утратило актуальность',superseded:'Заменено'}[r.status]||r.status)} · {r.text}</p>))}</details>}
    </DossierSection>
   </div>}
   {tab==='relationships'&&<DossierSection title={t('relationships')}>
    <div className="dossier-people">{Array.from(new Set(state.relationships.filter(r=>r.source_id===card.id||r.target_id===card.id).map(r=>r.source_id===card.id?r.target_id:r.source_id))).map(id=>state.characters.find(c=>c.id===id)).filter((c):c is Character=>!!c).map(other=><button className="dossier-person" key={other.id} onClick={()=>onCharacter?.(other.id)}><CharacterAvatar subject={other} saveId={save?.id} size={40}/><span>{other.name}</span><ArrowUpRight size={16}/></button>)}</div>
    {save&&refresh&&card.id===actor&&<RelationshipEditor key={`${save.id}:${card.id}`} save={save} card={card} refresh={refresh}/>}
    <RelationsView state={state} actor={card.id} excludeSource={save&&refresh&&card.id===actor?actor:undefined}/>
   </DossierSection>}
   {tab==='family'&&<SocialStateView state={state} actor={card.id} saveId={save?.id} mode="family"/>}
   {tab==='history'&&<div className="dossier-grid">
    <DossierSection title="История персонажа" wide>{Object.values(state.world?.events||{}).filter(e=>e.player_observed&&e.participants.includes(card.id)).slice(-40).map(e=><p key={e.id}>{e.text}</p>)}
     {!!card.appearance_history?.length&&<details><summary>История внешности</summary>{card.appearance_history.map((r,i)=><p key={i}>{worldTime(r.minute,state.world_clock?.calendar)} · {r.before?r.before+' → ':''}{r.after||'Удалено'}</p>)}</details>}
     {!!c?.value_history?.length&&<details><summary>История ценностей</summary>{c.value_history.map(v=><p key={v.id}>{v.status==='retired'?'Больше не актуально':v.before?'Уточнено':'Установлено'} · {v.before&&v.before!==v.text?`${v.before} → `:''}{v.text}</p>)}</details>}
     {conditions.some(c=>!activeConditions.includes(c))&&<details><summary>История физических состояний</summary>{conditionRows(conditions.filter(c=>!activeConditions.includes(c)))}</details>}
     {card.id===actor&&!!state.life_state?.names.length&&<details><summary>История имени</summary>{state.life_state.names.map((n,i)=><p key={i}>{n.previous} → {n.current}{n.date?` · ${calendarDate(n.date)}`:''}</p>)}</details>}
     {fields.filter(([k])=>['Тайны','Знания','Заметки','История'].includes(k)).map(([k,v])=><Reveal key={k} title={k} text={v}/>)}
     <Reveal title={`Знания и подозрения · ${knowledge.length}`} preview={false}><KnowledgeRows state={state} rows={knowledge}/></Reveal>
     <Reveal title="Все исходные поля карточки" preview={false}>{Object.entries(card.fields).map(([k,v])=><Reveal key={k} title={k} text={v} preview={false}/>)}</Reveal>
    </DossierSection>
   </div>}
  </div>
 </article>;
}
