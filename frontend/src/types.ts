export type Provider = "local" | "deepseek";
export type Section =
  "game" | "world" | "characters" | "memory" | "branches" | "settings";
export interface ModelConfig {
  provider: Provider;
  model: string;
  context_length: number;
  temperature: number;
  max_tokens: number;
  update_tokens: number;
  thinking: "off" | "low" | "high";
  recent_turns: number;
  memory_batch: number;
}
export interface LocalConfig {
  model: string;
  context_length: number;
  eval_batch_size: 256 | 512 | 1024 | 2048;
  flash_attention: boolean;
  offload_kv_cache_to_gpu: boolean;
}
export interface Preferences {
  idea: ModelConfig;
  summary: ModelConfig;
  game: ModelConfig;
  local: LocalConfig;
  font_size: number;
  line_height: number;
  reading_width: number;
  link_names: boolean;
}
export interface Character {
  id: string;
  name: string;
  aliases?: string[];
  is_player: boolean;
  fields: Record<string, string>;
}
export interface Relation {
  source_id: string;
  target_id?: string;
  target_name?: string;
  text: string;
  change?: { direction: "up" | "down"; reason: string; turn?: number };
}
export interface Scene {
  time: string;
  location: string;
  present_ids: string[];
}
export interface State {
  protagonist_id?: string;
  controlled_actor_id?: string|null;
  camera?: {scene_id:string;mode:'actor'|'observer';scope?:'world'|'scene'};
  world?: {version:number;characters:Record<string,{location:string|null;minute:number|null;scene_id:string|null;situation?:string;short_goal?:string;goals?:string[];intentions?:string[];emotion?:string;obligations?:string[]}>;scenes:Record<string,{id:string;participants:string[];location:string;start_minute:number|null;end_minute:number|null;status:string}>;facts?:Record<string,WorldFact>;knowledge?:Record<string,Knowledge>;threads?:Record<string,Thread>;events?:Record<string,WorldEvent>;relationships?:Record<string,WorldRelation>};
  world_clock?: {last_event_time:string;minute?:number};
  memory?: {id: string; summary: string; through_sequence: number; per_actor?:Record<string,{summary:string;through_sequence:number}>};
  scene: string;
  scene_meta?: Scene;
  sections: Record<string, string>;
  characters: Character[];
  relationships: Relation[];
  locations: { name: string; text: string }[];
  story_notes: string;
  facts?: { text: string; known_by: string[]; turn: number }[];
  plans?: { text: string; status: string }[];
  events?: { text: string; character_ids: string[]; turn: number }[];
}
export interface World {
  id: number;
  name: string;
  version: number;
  source_md: string;
  state: State;
  created_at: string;
  scene_meta: Scene;
}
export interface WorldItem {
  id: number;
  name: string;
  version: number;
  created_at: string;
}
export interface SaveItem {
  id: number;
  name: string;
  updated_at: string;
}
export interface Choice {
  action: string;
  speech: string;
}
export interface Turn {
  pov_actor_id?: string|null;
  audience_json?: string;
  node_id: string;
  active_variant_id: string;
  memory_archived: boolean;
  variants: {id: string; ordinal: number; job_id: string | null; can_regenerate: boolean}[];
  id: number;
  sequence: number;
  user_text: string;
  assistant_text: string;
  choices: Choice[];
  kind: string;
}
export interface Job {
  phase?: "scenario" | "designing" | "world" | "completing" | "retrying" | "validating" | "saving" | "editing" | "";
  progress_chars?: number;
  id: string;
  status: string;
  narrative: string;
  error: string;
  narrative_complete?: boolean;
  kind: string;
  revision: number;
  live?: boolean;
  user_text?: string;
  warnings?: {section: string; reason: string; rejected: unknown}[];
}
export interface Save extends SaveItem {
  world_id: number;
  state: State;
  revision: number;
  scene_meta: Scene;
  turns: Turn[];
  job: Job | null;
}
export interface Workspace {
  id: string;
  name: string;
  idea: string;
  summary: string;
  summary_complete: boolean;
  messages: { role: string; content: string }[];
  revision: number;
  job: Job | null;
}
const config: ModelConfig = {
  provider: "local",
  model: "local-model",
  context_length: 32768,
  temperature: 0.8,
  max_tokens: 2000,
  update_tokens: 4096,
  thinking: "off",
  recent_turns: 6,
  memory_batch: 4,
};
export const defaults: Preferences = {
  idea: { ...config, temperature: 1, max_tokens: 6000 },
  summary: { ...config, max_tokens: 12000 },
  game: { ...config },
  local: {
    model: "local-model",
    context_length: 16384,
    eval_batch_size: 512,
    flash_attention: true,
    offload_kv_cache_to_gpu: true,
  },
  font_size: 18,
  line_height: 1.8,
  reading_width: 800,
  link_names: true,
};
export const active = (job: Job | null | undefined) =>
  !!job && ["generating", "extracting", "validating"].includes(job.status);

export interface WorldFact {id:string;text:string;secret:boolean;character_ids:string[];evidence?:string[]}
export interface Knowledge {actor_id:string;fact_id:string;status:string;source_event_id?:string|null}
export interface Thread {id:string;description:string;state:string;status:string;character_ids:string[];relevance:number;last_event_id?:string|null}
export interface WorldEvent {id:string;text:string;participants:string[];witnesses:string[];minute:number|null;source_sequence:number;player_observed:boolean;fact_ids:string[]}
export interface WorldRelation {source_id:string;target_id:string;context:string;dimensions:Record<string,number|{direction:string;reason:string}>}
