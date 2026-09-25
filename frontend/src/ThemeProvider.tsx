import {createContext, useContext, useLayoutEffect, useRef, useState, type ReactNode} from 'react';
import {toast} from 'sonner';
import {api} from './api';
import type {World} from './types';

export const themes = [
  {id:'graphite', name:'Graphite', description:'Спокойная современная история'},
  {id:'gothic', name:'Gothic', description:'Сумерки, тайны и винные акценты'},
  {id:'parchment', name:'Parchment', description:'Тёплые страницы старой книги'},
  {id:'noir', name:'Noir', description:'Холодный свет и строгий контраст'},
  {id:'neon', name:'Neon', description:'Ночной город и холодный неон'},
] as const;
export type ThemeId = typeof themes[number]['id'];
export type Presentation = {theme_id:ThemeId; mode:'auto'|'manual'};
const fallback:Presentation = {theme_id:'graphite',mode:'manual'};
const valid = (value?:Presentation):Presentation => value && themes.some(t=>t.id===value.theme_id) ? value : fallback;
const ThemeContext = createContext({presentation:fallback, busy:false, available:false, select:async (_id:ThemeId|'auto')=>{}});
export function ThemeProvider({world, children}:{world:World|null; children:ReactNode}) {
  const [override,setOverride] = useState<{worldId:number;value:Presentation}|null>(null);
  const [busy,setBusy] = useState(false);
  const worldRef=useRef(world?.id); worldRef.current=world?.id;
  useLayoutEffect(()=>setOverride(null),[world]);
  const presentation=valid(override?.worldId===world?.id ? override?.value : world?.presentation);
  useLayoutEffect(()=>{
    document.documentElement.dataset.theme=presentation.theme_id;
    // Radix portals and toasts inherit the same root tokens as the application.
    return ()=>{delete document.documentElement.dataset.theme};
  },[presentation.theme_id]);
  const select=async(id:ThemeId|'auto')=>{
    if(!world||busy)return;
    const worldId=world.id;
    setBusy(true);
    try {
      const value=await api<Presentation>(`/worlds/${worldId}/presentation`,{theme_id:id},'PUT');
      if(worldRef.current===worldId)setOverride({worldId,value});
    } catch(e){toast.error((e as Error).message)} finally {setBusy(false)}
  };
  return <ThemeContext.Provider value={{presentation,busy,available:!!world,select}}>{children}</ThemeContext.Provider>;
}
export const useTheme=()=>useContext(ThemeContext);
export function ThemeSelector(){
 const {presentation,busy,available,select}=useTheme();
 if(!available)return <p className="muted">Открой мир, чтобы выбрать его оформление.</p>;
 return <section className="theme-selector" aria-label="Тема мира">
  <label>Тема мира<select aria-label="Тема мира" value={presentation.mode==='auto'?'auto':presentation.theme_id} disabled={busy} onChange={e=>void select(e.target.value as ThemeId|'auto')}>
   <option value="auto">Автоматически</option>{themes.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}
  </select></label>
  <p className="muted small">{presentation.mode==='auto'?'Выбрана '+themes.find(t=>t.id===presentation.theme_id)?.name+'. Автовыбор закреплён за этим миром.':'Оформление всех прохождений этого мира.'}</p>
  <div className="theme-options">{themes.map(t=><button key={t.id} data-theme={t.id} aria-label={`Тема ${t.name}`} aria-pressed={presentation.theme_id===t.id} disabled={busy} onClick={()=>void select(t.id)}>
   <span className="theme-swatch" aria-hidden="true"><i/><i/><i/></span><strong>{t.name}</strong><small>{t.description}</small>
  </button>)}</div>
 </section>;
}
