import { Choice } from "@/components/ui/choice";
import type {State} from './types';
import {Input} from './components/ui/input';

const actions = {engaged:'Помолвка',spouse:'Заключение брака',divorce:'Развод',parent:'Родство с ребёнком',
  move:'Постоянный переезд',hire:'Новая работа',leave_job:'Увольнение',death_notice:'Известие о смерти'} as const;
type Action = keyof typeof actions;
export type SocialEdit = {action:Action; actor_id:string; other_id:string; location_id:string; phase_id:string;
  title:string; description:string; known_by:string[]};

export function SocialCorrection({state,value,onChange}:{state:State;value:SocialEdit|null;onChange:(v:SocialEdit|null)=>void}) {
  const people=state.characters.map(c=><option key={c.id} value={c.id}>{c.name||'Без имени'}</option>);
  const relationship=value&&['engaged','spouse','divorce','parent'].includes(value.action);
  const phases=(value?.action==='move'?state.residence_roles?.residences:state.residence_roles?.roles)?.filter(
    r=>r.actor_id===value?.actor_id&&r.status==='active'&&(value?.action==='move'||r.kind==='employment'))||[];
  return <fieldset>
    <label>Исправить сведения о жизни персонажей
      <Choice value={value?.action||''} onValueChange={selectedValue => onChange(selectedValue?{
        action:selectedValue as Action, actor_id:state.controlled_actor_id||'',other_id:'',location_id:'',phase_id:'',
        title:'',description:selectedValue==='death_notice'?'Известие о смерти':'',known_by:state.controlled_actor_id?[state.controlled_actor_id]:[],
      }:null)}>
        <option value="">Без изменения</option>
        {(Object.entries(actions) as [Action,string][]).map(([id,name])=><option key={id} value={id}>{name}</option>)}
      </Choice>
    </label>
    {value&&<>
      <label>{value.action==='parent'?'Родитель':'Чья запись меняется'}
        <Choice required value={value.actor_id} onValueChange={selectedValue => onChange({...value,actor_id:selectedValue,phase_id:''})}>
          <option value="">Выберите персонажа</option>{people}
        </Choice>
      </label>
      {relationship&&<label>{value.action==='parent'?'Ребёнок':'Второй участник связи'}
        <Choice required value={value.other_id} onValueChange={selectedValue => onChange({...value,other_id:selectedValue})}>
          <option value="">Выберите персонажа</option>{people}
        </Choice>
      </label>}
      {value.action==='move'&&<label>Новое постоянное место жительства
        <Choice required value={value.location_id} onValueChange={selectedValue => onChange({...value,location_id:selectedValue})}>
          <option value="">Выберите место</option>{state.locations.filter(l=>l.id).map(l=><option key={l.id} value={l.id}>{l.name}</option>)}
        </Choice>
      </label>}
      {value.action==='hire'&&<label>Новая должность<Input required maxLength={200} value={value.title} onChange={e=>onChange({...value,title:e.target.value})}/></label>}
      {!relationship&&value.action!=='death_notice'&&(phases.length>0||value.action==='leave_job')&&<label>Какую запись закрыть
        <Choice required={value.action==='leave_job'} value={value.phase_id} onValueChange={selectedValue => onChange({...value,phase_id:selectedValue})}>
          <option value="">{value.action==='leave_job'?'Выберите место работы':'Сохранить прежние записи'}</option>
          {phases.map(r=><option key={r.id} value={r.id}>{r.label}</option>)}
        </Choice>
      </label>}
      {value.action!=='death_notice'&&<label>Что произошло<Input required value={value.description} maxLength={1000} onChange={e=>onChange({...value,description:e.target.value})}/></label>}
      <fieldset><legend>Кому известно это изменение?</legend>
        {state.characters.map(c=><label key={c.id}><input type="checkbox" checked={value.known_by.includes(c.id)}
          onChange={e=>onChange({...value,known_by:e.target.checked?[...value.known_by,c.id]:value.known_by.filter(id=>id!==c.id)})}/>{c.name||'Без имени'}</label>)}
      </fieldset>
    </>}
  </fieldset>;
}
