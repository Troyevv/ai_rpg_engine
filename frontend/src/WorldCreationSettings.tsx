import {CommunicationSettings,type CommunicationProfile} from './CommunicationSettings';
import {GenreSettings} from './GenreSettings';
import {useState} from 'react';
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
export function WorldCreationSettings({value,onChange,disabled=false}:{value:Creation;onChange:(value:Creation)=>void;disabled?:boolean}){
 const [preview,setPreview]=useState<Preview|null>(null);const [previewError,setPreviewError]=useState('');
 const counts=castCounts(value);
 const change=(patch:Partial<Creation>)=>onChange({...value,...patch});
 return <details className="workshop-detail"><summary>Настройки генератора</summary><fieldset disabled={disabled}>
 <p>Настройки заполняют пробелы замысла. Заданные персонажи сохраняются независимо от размера мира.</p>
 <CommunicationSettings value={value.communication} onChange={communication=>change({communication})} disabled={disabled}/>
 <GenreSettings value={value} onChange={genre=>change(genre)} disabled={disabled} creation/>
 <label>Выразительность NPC<select aria-label="Выразительность NPC" value={value.npc_expressiveness} onChange={e=>change({npc_expressiveness:e.target.value})}><option value="realistic">Реалистичная</option><option value="expressive">Выразительная</option><option value="hyperbolized">Гиперболизированная</option></select></label><p aria-label="Пример выразительности">{expressions[value.npc_expressiveness]}</p><p>Меняет речь, жесты и эмоциональную подачу, сохраняя характер, знания и самостоятельность NPC.</p>
 <label>Масштаб состава<select aria-label="Масштаб состава" value={value.cast_preset} onChange={e=>change({cast_preset:e.target.value})}><option value="small">Камерный · 3 важных и 5 второстепенных NPC</option><option value="medium">Средний · 6 и 12 NPC</option><option value="large">Большой · 10 и 25 NPC</option><option value="custom">Настроить количество</option></select></label>
 <p aria-label="Целевой состав мира">Важных NPC: {counts[0]}, второстепенных: {counts[1]}, всего: {counts[0]+counts[1]}. Это ориентир, а не обязательное заполнение. Указанные вами NPC входят в эти числа; будущие персонажи игры ими не ограничены.</p>
 {value.cast_preset==='custom'&&<><label>Важные NPC<input type="number" min={1} max={15} value={value.core_npcs} onChange={e=>change({core_npcs:Number(e.target.value)})}/></label><label>Второстепенные NPC<input type="number" min={0} max={40} value={value.secondary_npcs} onChange={e=>change({secondary_npcs:Number(e.target.value)})}/></label></>}
 <label>Тип мира<select aria-label="Тип мира" value={value.world_type} onChange={e=>change({world_type:e.target.value})}><option value="unspecified">Из описания</option><option value="real_world">Реальный мир</option><option value="fictional">Вымышленный мир</option><option value="alternate">Альтернативная реальность</option></select></label>
 <label>География<Textarea value={value.geography} maxLength={5000} placeholder="Страна, город, районы, расстояния и важные места" onChange={e=>change({geography:e.target.value})}/></label>
 <CalendarStartSettings value={value.calendar_start||defaultCalendarStart} onChange={calendar_start=>change({calendar_start})}/><button type="button" onClick={()=>{setPreviewError('');api<Preview>('/calendar/preview',value).then(setPreview).catch(e=>setPreviewError(e.message));}}>Предпросмотр календаря</button>{previewError&&<p role="alert">{previewError}</p>}<PresetPreview value={preview}/>
 <label>Темп истории<select aria-label="Темп истории" value={value.narrative_pacing.preset} onChange={e=>change({narrative_pacing:{preset:e.target.value}})}>{Object.entries({calm:'Спокойный',moderate:'Умеренный',dynamic:'Динамичный',intense:'Интенсивный'}).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
 <label>Риск последствий<select aria-label="Риск последствий" value={value.narrative_risk.preset} onChange={e=>change({narrative_risk:{preset:e.target.value}})}>{Object.entries({safe:'Безопасный',realistic:'Реалистичный',harsh:'Суровый',unrestricted:'Без ограничений'}).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label><p>Темп и риск задают правила будущей игры. Они не создают события предыстории.</p>
 </fieldset></details>;
}
