import {useState} from 'react';
import {toast} from 'sonner';
import {Dialog, DialogContent, DialogTitle} from './components/ui/dialog';
import type {Preferences} from './types';
import {useAnimations, setAnimations, turnTimes} from './lib/animations';

export function ReadingDisplay({open,close,prefs,save}:{
  open:boolean;close:()=>void;prefs:Preferences;save:(p:Preferences)=>Promise<void>;
}){
  const animations=useAnimations(), [busy,setBusy]=useState(false);
  const showTimes=turnTimes.useValue();
  const resize=async(size:number)=>{
    setBusy(true);
    try {await save({...prefs,font_size:size})} catch(e){toast.error((e as Error).message)}
    finally {setBusy(false)}
  };
  return <Dialog open={open} onOpenChange={v=>{if(!v)close()}}>
    <DialogContent className="reading-display" aria-describedby={undefined}>
      <DialogTitle>Отображение</DialogTitle>
      <div className="reading-row"><span>Размер текста</span><div className="reading-sizes">
        {['Небольшой текст','Обычный текст','Крупный текст'].map((name,i)=>{
          const size=[14,17,20][i];
          return <button key={size} aria-label={name} aria-pressed={prefs.font_size===size} disabled={busy}
            style={{fontSize:size}} onClick={()=>void resize(size)}>А</button>;
        })}
      </div></div>
      <label className="reading-row">Плавные анимации<input type="checkbox" checked={animations} onChange={e=>setAnimations(e.target.checked)}/></label>
      <label className="reading-row">Показывать время ходов<input type="checkbox" checked={showTimes} onChange={e=>turnTimes.set(e.target.checked)}/></label>
    </DialogContent>
  </Dialog>;
}
