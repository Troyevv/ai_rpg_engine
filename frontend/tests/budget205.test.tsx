import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {expect,it,vi} from 'vitest';
import {NarrativeDetail} from '../src/NarrativeDetail';
import {defaultCreation} from '../src/WorldCreationSettings';
import {defaults} from '../src/types';

it('uses balanced detail and persists a user selection independently of the model',async()=>{
  const host=document.createElement('div');document.body.append(host);
  const root=createRoot(host);const changed=vi.fn();
  vi.stubGlobal('CSS',{supports:()=>true});
  try {
    for(const config of [defaults.idea,defaults.summary,defaults.game]) expect(config.budget_mode).toBe('auto');
    await act(()=>root.render(<NarrativeDetail value={defaultCreation.narrative_detail} onChange={changed}/>));
    const select=host.querySelector<HTMLButtonElement>('button[role=combobox]')!;
    await act(()=>select.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true})));
    const options=[...document.querySelectorAll<HTMLElement>('[role=option]')];
    expect(options.map(o=>o.dataset.value)).toEqual(['brief','balanced','detailed','extended']);
    expect(select.value).toBe('balanced');
    await act(()=>{options[2].dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}))});
    expect(changed).toHaveBeenCalledWith('detailed');
  } finally { await act(()=>root.unmount());host.remove();vi.unstubAllGlobals(); }
});
