export type ChatModel = {provider:'local'|'deepseek'|'compatible';model:string;temperature:number;max_tokens:number;context_length:number;thinking:'off'|'low'|'high';auto_context?:boolean;auto_output?:boolean};
export type ChatSettings = {prompt:string;language:string;reply:ChatModel;summary:ChatModel;soft_threshold:number;summary_target:number;tail_tokens:number};
export type Budget = {estimated_tokens:number;available:number;output:number;margin:number;context_length:number;ratio:number;fits:boolean;approximate:true;token_method?:string;next_reply_reserve?:number};
export type Budgets = {reply:Budget;summary:Budget;warning:boolean;unfinished:boolean};
export type ChatMessage = {id:string;role:'user'|'assistant';content:string;status:string;seq:number;chapter_id:string;job_id:string|null};
export type ChatJob = {id:string;kind:string;status:string;response:string;error:string;output_id:string;usage:{stage:string;provider:string;model:string;input_tokens:number|null;output_tokens:number|null;cost_usd:string|null;finish_reason:string|null}[]};
export type ChatMemory = {id:string;text:string;cutoff:number;source:string;branch_id:string;created_at:string;cursor?:number};
export type ChatCampaign = {id:string;name:string;revision:number;mode:'chat';opening_required?:number;source:unknown;active_branch:string;
  branch:{id:string;head:number;chapter_id:string;config_id?:string};memory:ChatMemory;settings:ChatSettings;
  chapters:{id:string;name:string;ordinal:number}[];branches:{id:string;name:string;head:number}[];
  job:ChatJob|null;budgets:Budgets;drafts:{id:string;status:string;source_revision:number;branch_id:string}[]};
export type ChatDraft = {id:string;edit_revision:number;next_chapter:number;text:string;original:string;previous:string;status:string;stale:boolean;cutoff:number};
export type ChatSource = {world_id?:number;save_id?:number;revision?:number;history_turns?:number};

export type ChatCreation = {id:string;revision:number;name:string;idea:string;text:string;settings:ChatSettings;source:ChatSource|null;status:string;campaign_id:string|null;job_id:string|null;jobs:ChatJob[]};
