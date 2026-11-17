import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {expect,it,vi} from 'vitest';
import {ChatMode} from '../src/ChatMode';
import {api} from '../src/api';
import type {ChatCampaign} from '../src/chatTypes';
vi.mock('../src/api',()=>({api:vi.fn(),download:vi.fn()}));
vi.mock('../src/useChatScroll',()=>({useChatScroll:()=>({viewport:{current:null},content:{current:null},sticky:{current:true}})}));

it('opening stays locked while budget is pending; completion and typing do not depend on a budget response',async()=>{
  const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
  let snapshot:(event:MessageEvent)=>void=()=>{};
  vi.stubGlobal('EventSource',class{addEventListener(_name:string,fn:typeof snapshot){snapshot=fn}close(){}});
  localStorage.setItem('chat-selection','campaign');
  const budget={estimated_tokens:100,available:10000,ratio:.01,fits:true,approximate:true,context_length:16384,output:4096,margin:512};
  let campaign={id:'campaign',name:'Opening',revision:1,mode:'chat',opening_required:1,active_branch:'branch',branch:{id:'branch',head:1,chapter_id:'chapter'},memory:{id:'memory',text:'Memory'},settings:{},chapters:[{id:'chapter',name:'Глава 1',ordinal:1}],branches:[],drafts:[],budgets:{reply:budget,summary:budget,unfinished:true,warning:false},job:{id:'job',kind:'start',status:'running',response:'Начало…',output_id:'message',error:'',usage:[]}} as unknown as ChatCampaign;
  vi.mocked(api).mockImplementation(async(path)=>{
    if(path.endsWith('/budget'))return new Promise(()=>{});
    if(path.includes('/messages'))return {messages:[{id:'message',role:'assistant',content:'Начало…',status:'running',seq:1,chapter_id:'chapter',job_id:'job'}],more:false};
    if(path==='/chat/defaults')return {template:'',settings:{}};
    if(path==='/chat/campaigns/campaign')return campaign;
    throw new Error('Unexpected API '+path);
  });
  try{
    await act(()=>root.render(<ChatMode onBack={()=>{}} onConnections={()=>{}}/>));
    const input=host.querySelector<HTMLTextAreaElement>('#chat-input')!;
    // The composer must not unlock when the effect clears its transient budget.
    expect(input.disabled).toBe(true);
    campaign={...campaign,budgets:{...campaign.budgets,unfinished:false},job:{...campaign.job!,status:'complete'}};
    await act(()=>snapshot(new MessageEvent('snapshot',{data:JSON.stringify(campaign.job)})));
    expect(input.disabled).toBe(false);
    await act(()=>{
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')!.set!.call(input,'Моё первое действие');
      input.dispatchEvent(new Event('input',{bubbles:true}));
    });
    expect(input.disabled).toBe(false);
    expect(input.value).toBe('Моё первое действие');
    expect(localStorage.getItem('chat-input:campaign:branch')).toBe('Моё первое действие');
  }finally{
    await act(()=>root.unmount());host.remove();localStorage.clear();vi.unstubAllGlobals();vi.restoreAllMocks();
  }
});

it('does not offer an actionable Stop while the send operation still owns the action lock',async()=>{
  const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
  vi.stubGlobal('EventSource',class{addEventListener(){}close(){}});vi.useFakeTimers();
  localStorage.setItem('chat-selection','campaign');
  const budget={estimated_tokens:100,available:10000,ratio:.01,fits:true,approximate:true,context_length:16384,output:4096,margin:512};
  let campaign={id:'campaign',name:'Stop',revision:1,mode:'chat',active_branch:'branch',branch:{id:'branch',head:0,chapter_id:'chapter'},memory:{id:'memory',text:'Memory'},settings:{},chapters:[{id:'chapter',name:'Глава 1',ordinal:1}],branches:[],drafts:[],budgets:{reply:budget,summary:budget,unfinished:false,warning:false},job:null} as unknown as ChatCampaign;
  let pending=false;let release:(c:ChatCampaign)=>void=()=>{};let stops=0;
  vi.mocked(api).mockImplementation(async(path)=>{
    if(path.endsWith('/budget'))return campaign.budgets;
    if(path.includes('/messages'))return {messages:[],more:false};
    if(path==='/chat/defaults')return {template:'',settings:{}};
    if(path.endsWith('/generate')){pending=true;campaign={...campaign,job:{id:'reply',kind:'reply',status:'running',response:'Текст',output_id:'message',error:'',usage:[]}};return campaign.job}
    if(path.endsWith('/stop')){stops++;campaign={...campaign,job:{...campaign.job!,status:'stopped'}};return campaign.job}
    if(path==='/chat/campaigns/campaign')return pending?new Promise(resolve=>{release=resolve}):campaign;
    throw new Error('Unexpected API '+path);
  });
  const button=(name:string)=>[...host.querySelectorAll('button')].find(b=>b.textContent===name)!;
  try{
    await act(()=>root.render(<ChatMode onBack={()=>{}} onConnections={()=>{}}/>));
    await act(()=>{
      const input=host.querySelector<HTMLTextAreaElement>('#chat-input')!;
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')!.set!.call(input,'Действие');input.dispatchEvent(new Event('input',{bubbles:true}));
    });
    await act(()=>vi.advanceTimersByTimeAsync(300));
    await act(()=>button('Отправить').click());
    expect(button('Остановить').disabled).toBe(true);
    pending=false;await act(()=>release(campaign));
    expect(button('Остановить').disabled).toBe(false);
    await act(()=>button('Остановить').click());
    expect(stops).toBe(1);
    expect(host.textContent).toContain('Повторить явно (новый вызов)');
  }finally{
    await act(()=>root.unmount());host.remove();localStorage.clear();vi.useRealTimers();vi.unstubAllGlobals();vi.restoreAllMocks();
  }
});
