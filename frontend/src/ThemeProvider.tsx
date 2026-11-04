import {createContext, useContext, useLayoutEffect, useRef, useState, type ReactNode} from 'react';
import {toast} from 'sonner';
import {api} from './api';
import type {World} from './types';

import {themes,type ThemeId} from './lib/skins';
import {ThemeDecorationLayer} from './ThemeDecorationLayer';
export {themes};
export type {ThemeId};
export type Presentation = {theme_id:ThemeId; mode:'auto'|'manual'};
const fallback:Presentation = {theme_id:'graphite',mode:'manual'};
const valid = (value?:Presentation):Presentation => value && themes.some(t=>t.id===value.theme_id) ? value : fallback;
const ThemeContext = createContext({presentation:fallback, busy:false, available:false, preview:false, select:async (_id:ThemeId|'auto')=>{}});
export function ThemeProvider({world, children,preview=false}:{world:World|null; children:ReactNode;preview?:boolean}) {
  const [override,setOverride] = useState<{worldId:number;value:Presentation}|null>(null);
  const [previewTheme,setPreviewTheme]=useState<Presentation>(()=>{try{return valid(JSON.parse(localStorage.getItem('workshop-theme')||'null'))}catch{return fallback}});
  const [busy,setBusy] = useState(false);
  const worldRef=useRef(world?.id); worldRef.current=world?.id;
  useLayoutEffect(()=>setOverride(null),[world]);
  const presentation=preview?previewTheme:valid(override?.worldId===world?.id ? override?.value : world?.presentation);
  const skin=themes.find(t=>t.id===presentation.theme_id)||themes[0];
  useLayoutEffect(()=>{
    const root=document.documentElement;
    root.dataset.skin=skin.base;root.dataset.decoration=skin.decoration;
    for(const [key,value] of Object.entries(preview&&skin.id==='graphite'?{accent:'#e5b98c',bg:'#131615','surface-1':'#1b1f1d',text:'#e3e3db'}:{accent:skin.accent,bg:skin.bg,'surface-1':skin.surface,text:skin.text}))root.style.setProperty('--'+key,value);
    document.documentElement.dataset.theme=presentation.theme_id;
    // Radix portals and toasts inherit the same root tokens as the application.
    return ()=>{delete root.dataset.theme;delete root.dataset.skin;delete root.dataset.decoration;for(const key of ['accent','bg','surface-1','text'])root.style.removeProperty('--'+key)};
  },[presentation.theme_id,skin,preview]);
  const select=async(id:ThemeId|'auto')=>{
    if(preview){const value=valid({theme_id:id==='auto'?'graphite':id,mode:'manual'});setPreviewTheme(value);localStorage.setItem('workshop-theme',JSON.stringify(value));return;}
    if(!world||busy)return;
    const worldId=world.id;
    setBusy(true);
    try {
      const value=await api<Presentation>(`/worlds/${worldId}/presentation`,{theme_id:id},'PUT');
      if(worldRef.current===worldId)setOverride({worldId,value});
    } catch(e){toast.error((e as Error).message)} finally {setBusy(false)}
  };
  return <ThemeContext.Provider value={{presentation,busy,available:preview||!!world,preview,select}}><ThemeDecorationLayer pack={skin.decoration}/>{children}</ThemeContext.Provider>;
}
export const useTheme=()=>useContext(ThemeContext);
export function ThemeSelector(){
 const {presentation,busy,available,preview,select}=useTheme();
 if(!available)return <p className="muted">Открой мир, чтобы выбрать его оформление.</p>;
 return <section className="theme-selector" aria-label="Тема мира">
  <label>Тема мира<select aria-label="Тема мира" value={presentation.mode==='auto'?'auto':presentation.theme_id} disabled={busy} onChange={e=>void select(e.target.value as ThemeId|'auto')}>
   <option value="auto">Автоматически</option>{themes.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}
  </select></label>
  <p className="muted small">{preview?'Оформление мастерской. Игровые миры сохраняют свои темы.':presentation.mode==='auto'?'Выбрана '+themes.find(t=>t.id===presentation.theme_id)?.name+'. Автовыбор закреплён за этим миром.':'Оформление всех прохождений этого мира.'}</p>
  <div className="theme-options">{themes.map(t=><button key={t.id} data-theme={t.id} data-skin={t.base} style={{'--accent':t.accent,'--bg':t.bg,'--surface-1':t.surface,'--text':t.text} as import('react').CSSProperties} aria-label={`Тема ${t.name}`} aria-pressed={presentation.theme_id===t.id} disabled={busy} onClick={()=>void select(t.id)}>
   <span className="theme-swatch" aria-hidden="true"><i/><i/><i/></span><strong>{t.name}</strong><small>{t.description}</small>
  </button>)}</div>
 </section>;
}
