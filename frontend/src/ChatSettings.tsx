import {useState} from 'react';
import {toast} from 'sonner';
import {api} from './api';
import {Button} from './components/ui/button';
import type {ChatSettings as Settings, ChatModel} from './chatTypes';
import {Textarea} from './components/ui/textarea';
import {Input} from './components/ui/input';

export function ChatSettingsEditor({value,onChange}:{value:Settings;onChange:(s:Settings)=>void}) {
  const [available,setAvailable]=useState<Record<string,string[]>>({});
  const [loading,setLoading]=useState<string|null>(null);
  const model=(stage:'reply'|'summary',title:string)=>{
    const v=value[stage]; const change=(patch:Partial<ChatModel>)=>onChange({...value,[stage]:{...v,...patch}});
    return <fieldset><legend>{title}</legend><div className="chat-settings-grid">
      <label>Провайдер<select value={v.provider} onChange={e=>change({provider:e.target.value as ChatModel['provider']})}><option value="local">Локальный (LM Studio)</option><option value="deepseek">DeepSeek</option><option value="compatible">OpenAI-совместимый</option></select></label>
      <label>Модель<Input list={`chat-models-${stage}`} value={v.model} placeholder="Имя модели на сервере" onChange={e=>change({model:e.target.value})}/></label>
      <label>Окно модели, токены<Input type="number" min={2048} value={v.context_length} onChange={e=>change({context_length:Number(e.target.value)})}/></label>
      <label>Максимум ответа<Input type="number" min={128} value={v.max_tokens} onChange={e=>change({max_tokens:Number(e.target.value)})}/></label>
      <label>Температура<Input type="number" step="0.1" min={0} max={2} value={v.temperature} onChange={e=>change({temperature:Number(e.target.value)})}/></label>
      <label>Thinking<select value={v.thinking} onChange={e=>change({thinking:e.target.value as ChatModel['thinking']})}><option value="off">Выключен</option><option value="low">Low (если поддерживается)</option><option value="high">High (если поддерживается)</option></select></label>
    </div><datalist id={`chat-models-${stage}`}>{(available[v.provider]||[]).map(name=><option key={name} value={name}/>)}</datalist>
    <Button variant="ghost" disabled={!!loading} onClick={async()=>{setLoading(stage);try{const result=await api<{models:string[]}>('/models/list',{provider:v.provider});setAvailable(old=>({...old,[v.provider]:result.models}));toast.success('Список моделей обновлён')}catch(e){toast.error((e as Error).message)}finally{setLoading(null)}}}>{loading===stage?'Загрузка…':'Обновить список моделей'}</Button>
    </fieldset>;
  };
  return <div className="chat-settings-editor">
    <p className="muted">Ключи и адрес совместимого API хранятся на сервере. Размер окна задайте по документации выбранной модели; оценка контекста не является точным токенизатором.</p>
    {model('reply','Обычный RP-ответ')}{model('summary','Обновление выжимки — отдельный вызов')}
    <div className="chat-settings-grid"><label>Предупреждать при доле бюджета<Input type="number" min={.5} max={.95} step={.05} value={value.soft_threshold} onChange={e=>onChange({...value,soft_threshold:Number(e.target.value)})}/></label>
    <label>Целевой размер выжимки<Input type="number" value={value.summary_target} onChange={e=>onChange({...value,summary_target:Number(e.target.value)})}/></label>
    <label>Хвост сцены, оценка токенов<Input type="number" value={value.tail_tokens} onChange={e=>onChange({...value,tail_tokens:Number(e.target.value)})}/></label>
    <label>Язык игры<Input value={value.language} onChange={e=>onChange({...value,language:e.target.value})}/></label></div>
    <label htmlFor="chat-rp-prompt">Системный RP-промпт</label><Textarea id="chat-rp-prompt" rows={12} value={value.prompt} onChange={e=>onChange({...value,prompt:e.target.value})}/>
    <p className="muted small">Изменения действуют со следующего запроса. Регенерация использует настройки исходного ответа. Narrative сохраняет свои настройки.</p>
  </div>;
}
