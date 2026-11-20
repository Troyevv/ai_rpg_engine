import {useState} from 'react';
import {Button} from '../components/ui/button';
import {Choice} from '../components/ui/choice';

export type LegacyFamily={id:string;name:string;year:number;parents:{id:string;name:string;dead:boolean;marriages:{id:string;partner:string;date:string|null}[]}[]};
export type FamilyInput={child:string;parent:string;died_at_birth:boolean;age:number|null;birth_year:number|null;conditional_marriages:string[]};

export function ReviewCalendarConfirmation({families,disabled,onCalculate}:{families:LegacyFamily[];disabled:boolean;onCalculate:(values:FamilyInput[])=>void}){
 const [values,setValues]=useState<Record<string,FamilyInput>>({});
 const [deathLinks,setDeathLinks]=useState<Record<string,string>>({});
 const missingLink=families.some(f=>f.parents.some(p=>{
  const key=JSON.stringify([f.id,p.id]), value=values[key];
  return p.dead&&value&&(value.age!==null||value.birth_year!==null)&&!deathLinks[key];
 }));
 return <div className="ai-family-chronology"><p>Прежний пакет снимает точную дату рождения. Для пересчёта можно уточнить семейные сведения. Новый вариант появится для просмотра.</p>
  {families.map(family=><section key={family.id}><h5>{family.name} · год рождения {family.year}</h5>
   {family.parents.map(parent=>{
    const key=JSON.stringify([family.id,parent.id]);
    const value=values[key]??{child:family.id,parent:parent.id,died_at_birth:false,age:null,birth_year:null,conditional_marriages:[]};
    const update=(changes:Partial<FamilyInput>)=>setValues(old=>({...old,[key]:{...value,...changes}}));
    return <details key={key}><summary>{parent.name} · сведения о родителе</summary><fieldset disabled={disabled}>
     <label>Возраст при рождении ребёнка<input type="number" min={0} max={9999} value={value.age??''} onChange={e=>update({age:e.target.value===''?null:Number(e.target.value)})}/></label>
     <label>Подтверждённый год рождения родителя<input type="number" min={1} max={9999} value={value.birth_year??''} onChange={e=>update({birth_year:e.target.value===''?null:Number(e.target.value)})}/></label>
     {parent.dead&&<label>Связь с родами<Choice aria-label={'Связь с родами · '+parent.name} value={deathLinks[key]||''} onValueChange={v=>{setDeathLinks(old=>({...old,[key]:v}));update({died_at_birth:v==='delivery',conditional_marriages:[]})}}>
      <option value="">Не указано</option><option value="delivery">Смерть при этих родах</option><option value="unrelated">Смерть не связана с родами</option></Choice></label>}
     {value.died_at_birth&&parent.marriages.map(m=><label key={m.id} className="ai-confirm-option"><input type="checkbox" checked={value.conditional_marriages.includes(m.id)} onChange={e=>update({conditional_marriages:e.target.checked?[...value.conditional_marriages,m.id]:value.conditional_marriages.filter(id=>id!==m.id)})}/>Подтверждаю, что дата окончания брака с {m.partner}{m.date?' ('+m.date+')':''} условна и брак закончился в день этой смерти.</label>)}
    </fieldset></details>;
   })}
  </section>)}
  {missingLink&&<p role="status">Уточните, связана ли смерть указанного родителя с родами.</p>}
  <Button variant="outline" disabled={disabled||missingLink} onClick={()=>onCalculate(Object.entries(values).filter(([k,v])=>v.age!==null||v.birth_year!==null||deathLinks[k]).map(([,v])=>v))}>Пересчитать без нового запроса</Button>
 </div>;
}
