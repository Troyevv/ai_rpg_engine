import {useEffect,useState} from 'react';
import {toast} from 'sonner';
import {api} from './api';
import {Button} from './components/ui/button';
import type {ChatSettings as Settings, ChatModel} from './chatTypes';
import {Textarea} from './components/ui/textarea';
import {Input} from './components/ui/input';

type Capability={context_length:number|null;source:string;tokenizer?:string};
function ModelEditor({value:v,onChange:change,stage,title}:{value:ChatModel;onChange:(s:Partial<ChatModel>)=>void;stage:string;title:string}){
  const [available,setAvailable]=useState<string[]>([]);
  const [info,setInfo]=useState<Capability|null>(null);
  const [loading,setLoading]=useState(false);
  const [capabilityError,setCapabilityError]=useState(false);
  useEffect(()=>{
    setInfo(null);setCapabilityError(false);if(!v.model.trim())return;
    const controller=new AbortController();
    const timer=setTimeout(()=>void api<Capability>('/chat/capabilities',v,'POST',controller.signal).then(setInfo).catch(()=>{if(!controller.signal.aborted)setCapabilityError(true)}),400);
    return()=>{clearTimeout(timer);controller.abort()};
  },[v.provider,v.model]);
  return <fieldset><legend>{title}</legend><div className="chat-settings-grid">
    <label>Провайдер<select value={v.provider} onChange={e=>change({provider:e.target.value as ChatModel['provider'],model:''})}><option value="local">Локальный (LM Studio)</option><option value="deepseek">DeepSeek</option><option value="compatible">OpenAI-совместимый</option></select></label>
    <label>Модель<Input list={`chat-models-${stage}`} value={v.model} placeholder="Имя модели на сервере" onChange={e=>change({model:e.target.value})}/></label>
    <label className="chat-check"><input type="checkbox" checked={!!v.auto_context} onChange={e=>change({auto_context:e.target.checked,...(!e.target.checked&&info?.context_length?{context_length:info.context_length}:{})})}/> Автоматический контекст</label>
  </div>
  {v.auto_context&&v.model&&<p role="status" className="small">{capabilityError?'Не удалось получить характеристики. Проверьте подключение или отключите автоматический контекст и задайте проверенный размер в дополнительных параметрах.':!info?'Проверяем характеристики без генерации…':info.context_length?`Окно: ${info.context_length.toLocaleString()} токенов · ${info.source}`:'Окно неизвестно. Отключите автоматический контекст и укажите проверенный размер в дополнительных параметрах.'}</p>}
  <datalist id={`chat-models-${stage}`}>{available.map(name=><option key={name} value={name}/>)}</datalist>
  <Button variant="ghost" disabled={loading} onClick={async()=>{setLoading(true);try{const result=await api<{models:string[]}>('/models/list',{provider:v.provider});setAvailable(result.models)}catch(e){toast.error((e as Error).message)}finally{setLoading(false)}}}>{loading?'Загрузка…':'Обновить список моделей'}</Button>
  <details><summary>Дополнительные параметры модели</summary><div className="chat-settings-grid">
    <label>Окно модели, токены<Input type="number" min={2048} disabled={v.auto_context} value={v.auto_context&&info?.context_length?info.context_length:v.context_length} onChange={e=>change({context_length:Number(e.target.value)})}/></label>
    <label className="chat-check"><input type="checkbox" checked={!!v.auto_output} onChange={e=>change({auto_output:e.target.checked})}/> Автоматический лимит ответа</label>
    <label>Максимум ответа<Input type="number" min={128} disabled={v.auto_output} value={v.auto_output?Math.min(stage==='reply'?4096:16384,Math.floor((v.auto_context&&info?.context_length?info.context_length:v.context_length)/3)):v.max_tokens} onChange={e=>change({max_tokens:Number(e.target.value)})}/></label>
    <label>Температура<Input type="number" step="0.1" min={0} max={2} value={v.temperature} onChange={e=>change({temperature:Number(e.target.value)})}/></label>
    <label>Thinking<select value={v.thinking} onChange={e=>change({thinking:e.target.value as ChatModel['thinking']})}><option value="off">Выключен</option><option value="low">Low (если поддерживается)</option><option value="high">High (если поддерживается)</option></select></label>
  </div>{v.provider==='deepseek'&&<><p className="small">{info?.tokenizer||'Консервативная оценка UTF-8'}. Итог запроса остаётся оценкой; фактические токены сообщает провайдер.</p><Button className="chat-tokenizer-install" variant="outline" disabled={loading||!v.model} onClick={async()=>{setLoading(true);try{await api('/chat/tokenizer',v);setInfo(await api<Capability>('/chat/capabilities',v));toast.success('Официальный tokenizer установлен. Загрузка бесплатная, LLM-вызова нет.')}catch(e){toast.error((e as Error).message)}finally{setLoading(false)}}}>Установить tokenizer DeepSeek бесплатно</Button></>}</details></fieldset>;
}

export function ChatSettingsEditor({value,onChange}:{value:Settings;onChange:(s:Settings)=>void}) {
  const linked=!value.summary.model||(value.reply.model===value.summary.model&&value.reply.provider===value.summary.provider);
  return <div className="chat-settings-editor">
    <ModelEditor stage="reply" title="Обычный RP-ответ" value={value.reply} onChange={patch=>onChange({...value,reply:{...value.reply,...patch},summary:linked?{...value.summary,...patch,temperature:value.summary.temperature,max_tokens:value.summary.max_tokens}:value.summary})}/>
    <details><summary>Дополнительные настройки</summary>
      <p className="muted">По умолчанию выжимку создаёт выбранная игровая модель. Здесь можно выбрать другую. Ключи и адрес API хранятся на сервере. Размер запроса оценивается с запасом; способ подсчёта указан у модели.</p>
      <ModelEditor stage="summary" title="Обновление выжимки — отдельный вызов" value={value.summary} onChange={patch=>onChange({...value,summary:{...value.summary,...patch}})}/>
      <div className="chat-settings-grid"><label>Предупреждать при доле бюджета<Input type="number" min={.5} max={.95} step={.05} value={value.soft_threshold} onChange={e=>onChange({...value,soft_threshold:Number(e.target.value)})}/></label>
      <label>Целевой размер выжимки<Input type="number" value={value.summary_target} onChange={e=>onChange({...value,summary_target:Number(e.target.value)})}/></label>
      <label>Хвост сцены, оценка токенов<Input type="number" value={value.tail_tokens} onChange={e=>onChange({...value,tail_tokens:Number(e.target.value)})}/></label>
      <label>Язык игры<Input value={value.language} onChange={e=>onChange({...value,language:e.target.value})}/></label></div>
      <label htmlFor="chat-rp-prompt">Системный RP-промпт</label><Textarea id="chat-rp-prompt" rows={12} value={value.prompt} onChange={e=>onChange({...value,prompt:e.target.value})}/>
      <p className="muted small">Настройки действуют со следующего запроса. Регенерация использует настройки исходного ответа.</p>
    </details>
  </div>;
}
