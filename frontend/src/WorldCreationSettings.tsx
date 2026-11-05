import {Check} from "lucide-react";
import {CommunicationSettings,type CommunicationProfile} from './CommunicationSettings';
import {GenreSettings} from './GenreSettings';
import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import {PresetPreview,type Preview} from './CalendarPresets';
import {CalendarStartSettings,defaultCalendarStart} from './CalendarStartSettings';
import {Textarea} from './components/ui/textarea';
export const defaultCreation={communication:{preset:'none',presentation:'none'} as CommunicationProfile|null,calendar_start:defaultCalendarStart,primary_genre:null as string|null,secondary_genres:[] as string[],custom_genre:'',npc_expressiveness:'expressive',cast_preset:'medium',core_npcs:6,secondary_npcs:12,world_type:'unspecified',geography:'',narrative_pacing:{preset:'moderate'},narrative_risk:{preset:'realistic'}};
export type Creation=typeof defaultCreation;
export const castCounts=(value:Creation)=>value.cast_preset==='custom'?[value.core_npcs,value.secondary_npcs]:value.cast_preset==='small'?[3,5]:value.cast_preset==='large'?[10,25]:[6,12];
const expressions:Record<string,string>={
 realistic:'Сдержанная естественная подача. Например: NPC на миг отводит взгляд и тихо благодарит.',
 expressive:'Живые, правдоподобные реакции. Например: NPC улыбается, оживлённо благодарит и уточняет детали.',
 hyperbolized:'Театральная или комедийная подача, если она подходит персонажу. Например: NPC драматично хватается за сердце от приятного удивления.'};
export type CreationGroup='genre'|'cast'|'world'|'calendar'|'narrative';
export function CreationFields({value,onChange,disabled=false,group}:{value:Creation;onChange:(value:Creation)=>void;disabled?:boolean;group?:CreationGroup}){
 const [preview,setPreview]=useState<Preview|null>(null);const [previewError,setPreviewError]=useState('');
 const previewRequest=useRef<AbortController|null>(null);
 useEffect(()=>{previewRequest.current?.abort();setPreview(null);setPreviewError('');return()=>previewRequest.current?.abort()},[JSON.stringify(value)]);
 const counts=castCounts(value);
 const change=(patch:Partial<Creation>)=>onChange({...value,...patch});
 return <fieldset disabled={disabled} className="atelier-fields sp" data-group={group}>
 {!group&&<p>Настройки заполняют пробелы замысла. Заданные персонажи сохраняются независимо от размера мира.</p>}
 {!group&&<CommunicationSettings value={value.communication} onChange={communication=>change({communication})} disabled={disabled}/>}
 {(!group||group==='genre')&&<GenreSettings value={value} onChange={genre=>change(genre)} disabled={disabled} creation/>}
 {(!group||group==='cast')&&<>
 <p className="sp-lead">Персонажи из вашего замысла входят в состав. Если их больше цели, все указанные вами персонажи сохраняются.</p>
 <fieldset className="sp-block"><legend>Масштаб состава</legend><div className="sp-scale">{Object.entries({small:['Камерный','3 + 5 NPC'],medium:['Средний','6 + 12 NPC'],large:['Большой','10 + 25 NPC'],custom:['Свой состав','Свои числа']}).map(([id,[title,note]])=><label className={'sp-choice'+(value.cast_preset===id?' on':'')} key={id}><input type="radio" name="atelier-cast" aria-label={title} checked={value.cast_preset===id} onChange={()=>change({cast_preset:id})}/><strong>{title}</strong><small>{note}</small>{value.cast_preset===id&&<Check size={14} className="selection-mark"/>}</label>)}</div></fieldset>
 {value.cast_preset==='custom'&&<div className="sp-two"><label>Важные NPC<input type="number" min={1} max={15} aria-label="Важные NPC" value={value.core_npcs} onChange={e=>change({core_npcs:Number(e.target.value)})}/><small>От 1 до 15</small></label><label>Второстепенные NPC<input type="number" min={0} max={40} aria-label="Второстепенные NPC" value={value.secondary_npcs} onChange={e=>change({secondary_npcs:Number(e.target.value)})}/><small>От 0 до 40</small></label></div>}
 <p className="sp-note" aria-label="Целевой состав мира">Важных NPC: {counts[0]}, второстепенных: {counts[1]}, всего: {counts[0]+counts[1]}. Это ориентир; новые персонажи могут появляться в игре.</p>
 <label>Выразительность NPC<select aria-label="Выразительность NPC" value={value.npc_expressiveness} onChange={e=>change({npc_expressiveness:e.target.value})}><option value="realistic">Реалистичная</option><option value="expressive">Выразительная</option><option value="hyperbolized">Гиперболизированная</option></select></label>
 <blockquote className="sp-sample" key={value.npc_expressiveness}><small>Пример реакции</small><p aria-label="Пример выразительности">{expressions[value.npc_expressiveness]}</p></blockquote><p className="sp-note">Меняет речь, жесты и эмоциональную подачу, сохраняя характер, знания и самостоятельность NPC.</p>
 </>}
 {(!group||group==='world')&&<> <p className="sp-lead">Опишите пространственные ориентиры, которые генератору нужно учитывать с первой сцены.</p><label>Тип мира<select aria-label="Тип мира" value={value.world_type} onChange={e=>change({world_type:e.target.value})}><option value="unspecified">Из описания</option><option value="real_world">Реальный мир</option><option value="fictional">Вымышленный мир</option><option value="alternate">Альтернативная реальность</option></select></label>
 <label>География<Textarea aria-label="География" value={value.geography} maxLength={5000} placeholder="Страна, город, районы, расстояния и важные места" onChange={e=>change({geography:e.target.value})}/></label>
 </>}
 {(!group||group==='calendar')&&<> <p className="sp-lead">Оставьте дату и время пустыми, чтобы генератор взял их из замысла.</p><CalendarStartSettings atelier={!!group} value={value.calendar_start||defaultCalendarStart} onChange={calendar_start=>change({calendar_start})}/><button type="button" className="sp-preview-btn" onClick={()=>{previewRequest.current?.abort();const controller=new AbortController();previewRequest.current=controller;setPreviewError('');api<Preview>('/calendar/preview',value,'POST',controller.signal).then(v=>{if(!controller.signal.aborted)setPreview(v)}).catch(e=>{if(!controller.signal.aborted)setPreviewError(e.message)});}}>Предпросмотр календаря</button>{previewError&&<p role="alert">{previewError}</p>}<PresetPreview value={preview}/>
 </>}
 {(!group||group==='narrative')&&<> <p className="sp-lead">Эти настройки действуют в будущих ходах игры. Предысторию задаёт ваш замысел.</p><label>Темп истории<select aria-label="Темп истории" value={value.narrative_pacing.preset} onChange={e=>change({narrative_pacing:{preset:e.target.value}})}>{Object.entries({calm:'Спокойный',moderate:'Умеренный',dynamic:'Динамичный',intense:'Интенсивный'}).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
 <label>Риск последствий<select aria-label="Риск последствий" value={value.narrative_risk.preset} onChange={e=>change({narrative_risk:{preset:e.target.value}})}>{Object.entries({safe:'Безопасный',realistic:'Реалистичный',harsh:'Суровый',unrestricted:'Без ограничений'}).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label><p>Темп и риск задают правила будущей игры. Они не создают события предыстории.</p>
 </>}
 </fieldset>;
}

export function WorldCreationSettings(props:{value:Creation;onChange:(value:Creation)=>void;disabled?:boolean}) {return <details className="workshop-detail"><summary>Настройки генератора</summary><CreationFields {...props}/></details>}
