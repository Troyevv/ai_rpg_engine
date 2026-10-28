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
export const NarrativeTurn=memo(function NarrativeTurn({t,i,save,world,prefs,mobile,busy,running,mainActor,turn,run,setSubmitted,refresh,setDiagnosticJob,setDiagnostics,openCharacter,job,reconnecting,stop,identity,committed,onPresented,showTools=true,toolsOnly=false}: {
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
                  <p className="turn-number">
                    {t.kind==="background"?`Тем временем… · За кулисами · ход ${t.sequence}`:i === 0 ? "Первая сцена" : `Ход ${t.sequence}`}
                    {t.kind!=="background"&&<span> · POV: {save.state.characters.find(c=>c.id===(t.pov_actor_id||mainActor))?.name}</span>}
                  </p>
                  <NarrativeText identity={identity} onPresented={onPresented} text={t.assistant_text} complete={committed||!!job?.narrative_complete||!!job&&['error','stopped'].includes(job.status)} saveId={save.id} worldId={world.id} links={prefs.link_names} onCharacter={openCharacter}/>
                  {!committed&&showTools&&<JobView job={job?.status==='saved'?{...job,status:'committing'}:job} statusOnly reconnecting={reconnecting} stop={stop}/>}
                  </>}
                  {committed&&showTools&&!t.read_only_projection&&<>
                  {t.timing?.total!=null&&<details className="turn-timing"><summary>Время хода: {t.timing.total.toFixed(1)} с</summary><Timing timing={t.timing}/></details>}
                  {mobile?<div className="mobile-variants">
                    <Button size="icon" variant="ghost" aria-label="Ещё вариант" disabled={busy||running||!t.variants?.some(v=>v.can_regenerate)} onClick={()=>{const later=i<save.turns.length-1;if(later&&!window.confirm('Откатить следующие ходы в архив?'))return;void turn('regenerate','',t.id,later)}}>↻</Button>
                    {[-1,1].map((step)=>{const list=t.variants||[];const index=list.findIndex(v=>v.id===t.active_variant_id);const v=list[index+step];return <span className="variant-step" key={step}>{step===1&&<span>{index+1} / {list.length||1}</span>}<Button size="icon" variant="ghost" aria-label={step<0?'Предыдущий вариант':'Следующий вариант'} disabled={busy||running||!v} onClick={()=>{const later=i<save.turns.length-1;if(later&&!window.confirm('Откатить следующие ходы в архив?'))return;void run(async()=>{await api(`/saves/${save.id}/turns/${t.id}/variant`,{variant_id:v.id,revision:save.revision,rollback_following:later});setSubmitted(null);refresh()})}}>{step<0?'‹':'›'}</Button></span>})}
                    <Button size="icon" variant="ghost" aria-label="Контекст / usage" onClick={()=>{setDiagnosticJob(t.variants?.find(v=>v.id===t.active_variant_id)?.job_id||undefined);setDiagnostics(true)}}>⋯</Button>
                  </div>:<div className="variant-controls">
                    <span className="muted small">Вариант {(t.variants||[]).find(v=>v.id===t.active_variant_id)?.ordinal||1} / {t.variants?.length||1}</span>
                    {(t.variants||[]).map(v=><Button key={v.id} size="sm" variant={v.id===t.active_variant_id?"outline":"ghost"} disabled={busy||running||v.id===t.active_variant_id} onClick={()=>{
                      const later = i<save.turns.length-1;
                      if(later&&!window.confirm("Смена варианта откатит все последующие ходы. Они сохранятся в архиве. Продолжить?"))return;
                      void run(async()=>{await api(`/saves/${save.id}/turns/${t.id}/variant`,{variant_id:v.id,revision:save.revision,rollback_following:later});setSubmitted(null);refresh()});
                    }}>{v.ordinal}</Button>)}
                    <Button size="sm" variant="ghost" title={t.variants?.some(v=>v.can_regenerate) ? "" : "У старого хода нет сохранённого контекста"} disabled={busy||running||!t.variants?.some(v=>v.can_regenerate)} onClick={()=>{
                      const later=i<save.turns.length-1;
                      if(later&&!window.confirm("После успешной генерации последующие ходы будут откачены в архив. Продолжить?"))return;
                      void turn("regenerate","",t.id,later);
                    }}>Ещё вариант</Button>
                    <Button size="sm" variant="ghost" onClick={()=>{setDiagnosticJob(t.variants?.find(v=>v.id===t.active_variant_id)?.job_id||undefined);setDiagnostics(true)}}>Контекст / usage</Button>
                    {!!t.memory_archived&&<span className="muted small">В архиве памяти · полный текст сохранён</span>}
                  </div>}
                  </>}
                </motion.article>
 );
});
