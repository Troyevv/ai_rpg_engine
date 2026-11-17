import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {expect,it,vi} from 'vitest';
import {ChatCreationEditor} from '../src/ChatCreation';
import {api} from '../src/api';
import type {ChatCreation,ChatSettings} from '../src/chatTypes';
vi.mock('../src/api',()=>({api:vi.fn(),download:vi.fn()}));

it('keeps creation edits locked until the final server draft has been adopted',async()=>{
  const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
  let snapshot:(event:MessageEvent)=>void=()=>{};
  vi.stubGlobal('EventSource',class{addEventListener(_name:string,fn:typeof snapshot){snapshot=fn}close(){}});
  localStorage.setItem('chat-create-idea','Идея у маяка');
  const model={provider:'local',model:'fixture',temperature:.8,max_tokens:8192,context_length:65536,thinking:'off',auto_context:true,auto_output:true};
  const settings={reply:model,summary:model,prompt:'RP',language:'ru',soft_threshold:.85,summary_target:8192,tail_tokens:1024} as ChatSettings;
  const job={id:'initial',kind:'initial',status:'running',response:'Начало выжимки',error:'',output_id:'creation',usage:[]};
  const draft={id:'creation',revision:1,name:'История',idea:'Идея у маяка',text:'Начало выжимки',settings,source:null,status:'running',campaign_id:null,job_id:job.id,jobs:[job]} as ChatCreation;
  let finishing=false;let resolveFinal:(draft:ChatCreation)=>void=()=>{};
  vi.mocked(api).mockImplementation(async(path,_body,method)=>{
    if(path==='/chat/capabilities')return {context_length:65536,source:'fixture'};
    if(path==='/worlds'||path==='/chat/creations'&&method!=='POST')return [];
    if(path==='/chat/creations')return draft;
    if(path.endsWith('/generate'))return job;
    if(path==='/chat/creations/creation')return finishing?new Promise(resolve=>{resolveFinal=resolve}):draft;
    throw new Error('Unexpected API '+path);
  });
  try{
    await act(()=>root.render(<ChatCreationEditor defaults={{template:'Template',settings}} onCreated={()=>{}} onConnections={()=>{}}/>));
    const generate=[...host.querySelectorAll('button')].find(b=>b.textContent==='Сгенерировать первоначальную выжимку')!;
    await act(()=>generate.click());
    finishing=true;
    const complete={...job,status:'complete',response:'Полная выжимка'};
    await act(()=>snapshot(new MessageEvent('snapshot',{data:JSON.stringify(complete)})));
    const input=host.querySelector<HTMLInputElement>('input[list="chat-models-reply"]')!;
    expect(input.matches(':disabled')).toBe(true);
    expect(host.querySelector<HTMLTextAreaElement>('#chat-initial-memory')!.disabled).toBe(true);
    await act(()=>resolveFinal({...draft,text:complete.response,status:'complete',jobs:[complete]}));
    expect(input.matches(':disabled')).toBe(false);
    await act(()=>{
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(input,'small-fixture');
      input.dispatchEvent(new Event('input',{bubbles:true}));
    });
    expect(input.value).toBe('small-fixture');
  }finally{
    await act(()=>root.unmount());host.remove();localStorage.clear();vi.unstubAllGlobals();vi.restoreAllMocks();
  }
});
