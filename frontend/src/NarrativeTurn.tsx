import {Plus, ChartNoAxesCombined, ChevronLeft, ChevronRight} from 'lucide-react';
import {phoneText} from './lib/phone';
import {memo, useRef} from 'react';
import {motion,useReducedMotion} from 'framer-motion';
import {useMotionPreset} from './motion';
import {Markdown} from './Markdown';
import {NarrativeText} from './NarrativeText';
import {JobView} from './JobView';
import {Timing} from './Timing';
import {Button} from './components/ui/button';
import {api} from './api';
import type {Job,Save,World,Preferences,Turn} from './types';
export const NarrativeTurn=memo(function NarrativeTurn({latest,hidden,t,i,save,world,prefs,busy,running,mainActor,turn,run,setSubmitted,refresh,setDiagnosticJob,setDiagnostics,openCharacter,job,reconnecting,stop,identity,committed,onPresented,liveTextRef,showTools=true,toolsOnly=false}: {
 latest:boolean;hidden?:boolean;liveTextRef?:React.RefObject<HTMLDivElement|null>;
 showTools?:boolean;toolsOnly?:boolean;
 t:Turn;i:number;save:Save;world:World;prefs:Preferences;mobile:boolean;busy:boolean;running:boolean;mainActor?:string;
 turn:(kind:'start'|'turn'|'regenerate'|'background',text?:string,target?:number,rollback?:boolean)=>Promise<void>;
 run:(fn:()=>Promise<void>)=>Promise<void>;setSubmitted:(j:Job|null)=>void;refresh:()=>void;
 setDiagnosticJob:(id:string|undefined)=>void;setDiagnostics:(v:boolean)=>void;openCharacter:(id:string)=>void;
 job:Job|null;reconnecting:boolean;stop:()=>void;identity:string;committed:boolean;onPresented:(id:string)=>void;
}){
 const streamed=useRef(!committed).current;
 const initialTurns=useRef(new Set(committed?[t.id]:[]));
 const reduced=useReducedMotion();
 const turnMotion=useMotionPreset('fadeUp'),povMotion=useMotionPreset('povTransition');
 return (
                <motion.article
                  hidden={hidden}
                  data-reading-id={identity}
                  data-stream-id={streamed?identity:undefined}
                  className={`${committed?"turn":"pending-turn"} ${t.kind==="background"?"background-turn":""}`}
                  initial={streamed || reduced || initialTurns.current.has(t.id) ? false : "hidden"}
                  animate="visible"
                  variants={turnMotion}
                >
                  {toolsOnly&&<h4>Ход {t.sequence}</h4>}
                  {!toolsOnly&&<>
                  {t.kind==='communication'&&!!t.changes?.communication?.rejected?.length&&<div role="alert"><strong>Старая ошибочная обработка связи</strong><p>Этот результат был сохранён прежней версией. «Ещё вариант» повторит обработку от исходного события без повторной отправки. При наличии следующих ходов потребуется их откат в архив. Исходный вариант останется доступен.</p></div>}
                  {t.kind==='pov'&&<motion.div className="pov-divider" variants={povMotion}><span>Другая точка зрения</span><strong>{save.state.characters.find(c=>c.id===t.pov_actor_id)?.name}</strong></motion.div>}
                  {t.kind==='background'&&<div className="narrative-divider">Тем временем</div>}
                  {t.user_text && (
                    <div className="player-action" data-testid="player-action">
                      <span className="eyebrow">Твоё действие</span>
                      <Markdown text={t.user_text} />
                    </div>
                  )}
                  {t.presentation?.surface==='call' ? <p className="call-speaker">{save.state.phone?.events.find(e=>e.id===t.presentation?.call_id)?.label}</p> :
                    <p className="turn-number" title={`Ход ${t.sequence} · POV: ${save.state.characters.find(c=>c.id===(t.pov_actor_id||mainActor))?.name||''}`}>
                      {t.kind==='background'?`Тем временем… · За кулисами · ход ${t.sequence}`:latest?'Сейчас':i===0?'Первая сцена':`Ход ${t.sequence}`}
                      {latest&&t.kind!=='background'&&save.state.world_clock?.projection?.time&&<span className="turn-clock"> · {save.state.world_clock.projection.time}</span>}
                    </p>}
                  {committed&&t.presentation?.physical_reconciliation&&!t.read_only_projection&&<p role="status" className="muted small">{phoneText('physicalReconciled')}</p>}
                  <NarrativeText liveTextRef={liveTextRef} identity={identity} onPresented={onPresented} text={t.assistant_text} complete={committed||!!job?.narrative_complete||!!job&&['error','stopped'].includes(job.status)} saveId={save.id} worldId={world.id} links={prefs.link_names} onCharacter={openCharacter}/>
                  {!committed&&showTools&&<JobView job={job?.status==='saved'?{...job,status:'committing'}:job} statusOnly reconnecting={reconnecting} stop={stop}/>}
                  </>}
                  {committed&&showTools&&!t.read_only_projection&&<>
                  {t.changes?.menu_available!=null&&t.changes.interpretation!=='pending'&&
                    <p className="muted small">Варианты продолжения · {t.changes.menu_available} из 6. Можно ввести своё действие.</p>}
                  {t.changes?.interpretation==='pending'&&
                    <p role="status" className="muted small">Сцена сохранена. Время, место и последствия ещё уточняются.</p>}
                  {['partial','deferred'].includes(t.changes?.interpretation || '') &&
                    <details className="turn-timing"><summary>Сцена сохранена. Есть замечания к состоянию мира.</summary>
                      <p>Историю можно продолжить. Часы и место показывают последние сохранённые данные и могут отставать от текста. Место, участников и знания можно поправить в инспекторе сцены.</p>
                    </details>}
                  {toolsOnly&&t.timing?.total!=null&&<details className="turn-timing"><summary>Время хода: {t.timing.total.toFixed(1)} с</summary><Timing timing={t.timing}/></details>}
                  <div className="variant-controls">
                    <span>Вариант</span>
                    {[-1,1].map(step=>{
                      const list=t.variants||[];
                      const index=list.findIndex(v=>v.id===t.active_variant_id);
                      const target=list[index+step];
                      return <span className="variant-step" key={step}>
                        {step===1&&<span>{list[index]?.ordinal||1} из {list.length||1}</span>}
                        <Button size="icon" variant="ghost" aria-label={step<0?'Предыдущий вариант':'Следующий вариант'} disabled={busy||running||!target} onClick={()=>{
                          const later=i<save.turns.length-1;
                          if(later&&!window.confirm("Смена варианта откатит все последующие ходы. Они сохранятся в архиве. Продолжить?"))return;
                          void run(async()=>{await api(`/saves/${save.id}/turns/${t.id}/variant`,{variant_id:target.id,revision:save.revision,rollback_following:later});setSubmitted(null);refresh()});
                        }}>{step<0?<ChevronLeft/>:<ChevronRight/>}</Button>
                      </span>;
                    })}
                    <Button size="sm" variant="ghost" title={t.variants?.some(v=>v.can_regenerate) ? "" : "У старого хода нет сохранённого контекста"} disabled={busy||running||!t.variants?.some(v=>v.can_regenerate)} onClick={()=>{
                      const later=i<save.turns.length-1;
                      if(later&&!window.confirm("После успешной генерации последующие ходы будут откачены в архив. Продолжить?"))return;
                      void turn("regenerate","",t.id,later);
                    }}><Plus/>Ещё вариант</Button>
                    <Button size="sm" variant="ghost" onClick={()=>{setDiagnosticJob(t.variants?.find(v=>v.id===t.active_variant_id)?.job_id||undefined);setDiagnostics(true)}}><ChartNoAxesCombined/>Контекст / usage</Button>
                    {!!t.memory_archived&&<span className="muted small">В архиве памяти · полный текст сохранён</span>}
                  </div>
                  </>}
                </motion.article>
 );
});
