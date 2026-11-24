import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {expect,it,vi} from 'vitest';
import {Newspaper} from 'lucide-react';
import {Phone} from '../src/Phone';
import {apps,type PhoneApp} from '../src/phone/registry';
import {useDevice} from '../src/phone/usePhone';
import type {Save,ModelConfig} from '../src/types';

function News(){const d=useDevice();return d.route?<h3>Статья</h3>:<button onClick={()=>d.push('article')}>Открыть статью</button>}
const news:PhoneApp={id:'news',title:'Новости',icon:Newspaper,screen:News,available:c=>!!c.social};

it('opens a test-only app through the registry and shares its navigation and capability boundary',async()=>{
  vi.stubGlobal('ResizeObserver',class{observe(){}disconnect(){}});
  const host=document.createElement('div');host.id='root';document.body.appendChild(host);
  const root=createRoot(host);
  const save={id:276,turns:[],revision:1,state:{characters:[],phone:{actor_id:'a',capabilities:{social:true,text_message:true},contacts:[],conversations:[],events:[],emergency:[],badges:{news:105}}}} as unknown as Save;
  const render=(s:Save)=>act(()=>root.render(<Phone save={s} registry={[...apps,news]} config={{} as ModelConfig} apiKey="" job={null} disabled={false} onJob={()=>{}} onCommit={()=>{}} onBusyChange={()=>{}} openCharacter={()=>{}}/>));
  const click=async(selector:string)=>{const el=host.querySelector<HTMLButtonElement>(selector);expect(el).toBeTruthy();await act(()=>el!.click())};
  try{
    await render(save);await click('.phone-peek');expect(host.querySelector('[data-app=news]')?.textContent).toContain('99+');
    await click('[data-app=news]');await click('.phone-body button');expect(host.querySelector('h3')?.textContent).toBe('Статья');
    await act(()=>document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true})));
    expect(host.querySelector('.phone-body')?.textContent).toContain('Открыть статью');
    await click('[aria-label=Домой]');await click('[data-app=news]');await click('.ph-close');expect(host.querySelector('.phone-peek')?.getAttribute('aria-expanded')).toBe('false');
    await click('.phone-peek');await click('[data-app=news]');await click('.phone-body button');
    const other=structuredClone(save);other.state.phone!.actor_id='b';other.state.phone!.capabilities.social=false;
    await render(other);await click('.phone-peek');
    expect(host.querySelector('[data-app=news]')).toBeNull();expect(host.querySelector('.phone-body')?.textContent).not.toContain('Статья');
    expect(apps.some(app=>app.id==='news')).toBe(false);
  }finally{await act(()=>root.unmount());host.remove();vi.unstubAllGlobals()}
});
