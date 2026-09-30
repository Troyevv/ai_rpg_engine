export type Build = {
  name: string;
  species: string;
  character_class: string;
  background: string;
  abilities: Record<string, number>;
  skills: string[];
  equipment: string[];
  appearance: string;
  biography: string;
  personality: string;
  ideals: string;
  bonds: string;
  flaws: string;
};
export type Catalog = {
  id: string;
  name: string;
  abilities: string[];
  ability_array: number[];
  skills: Record<string, string>;
  classes: Record<
    string,
    {
      name: string;
      skills: string[];
      equipment: string[];
      equipment_choices?: string[][];
      saves: string[];
      skill_count: number;
    }
  >;
  species: Record<string, { name: string; speed: number }>;
  backgrounds: Record<string, { name: string }>;
  items: Item[];
  default_build: Build;
};
export type Item = {
  id: string;
  name: string;
  description: string;
  type: string;
  healing: number;
  weight: number;
  value: number;
};
export type Entry = { item_id: string; quantity: number; equipped: boolean };
export type Sheet = {
  id: string;
  name: string;
  level: number;
  character_class: string;
  character_class_name: string;
  species: string;
  species_name: string;
  hp: number;
  max_hp: number;
  armor_class: number;
  speed: number;
  position: number;
  conditions: string[];
  abilities: Record<string, number>;
  modifiers: Record<string, number>;
  skill_modifiers: Record<string, number>;
  save_modifiers: Record<string, number>;
  attacks: Record<
    string,
    { name: string; die: number; ability: string; reach: number }
  >;
  attack_modifiers: Record<string, number>;
  inventory: Entry[];
  resources: Record<string, number>;
  biography: string;
  appearance: string;
  personality: string;
  ideals: string;
  bonds: string;
  flaws: string;
  controller: { controller: string; player_id: string | null };
};
export type Command = {
  type: string;
  actor_id?: string;
  target?: string;
  purpose?: string;
  ability?: string;
  skill?: string;
  weapon?: string;
  distance?: number;
  item_id?: string;
  quantity?: number;
  rest?: string;
  topic?: string;
};
export type Roll = {
  expression: string;
  raw: number[];
  modifier: number;
  total: number;
  purpose: string;
  actor: string;
  advantage: number;
};
export type Usage = {
  stage: string;
  status: string;
  provider: string;
  model: string;
  input_tokens: number | null;
  output_tokens: number | null;
  cached_tokens: number | null;
  cost: string | null;
  seconds: number;
};
export type Game = {
  id: string;
  revision: number;
  state: {
    campaign: string;
    ruleset: { name: string };
    world: { name: string; description: string };
    scene: string;
    location: string;
    location_id: string;
    mode: string;
    controlled_actor: string;
    characters: Record<string, Sheet>;
    party: string[];
    npcs: Record<
      string,
      {
        id: string;
        name: string;
        position: number;
        status: string;
        hostile: boolean;
      }
    >;
    objects: {
      id: string;
      name: string;
      description: string;
      opened: boolean;
      contents: Entry[];
    }[];
    items: Record<string, Item>;
    knowledge: Record<string, string>;
    quests: Record<
      string,
      { name: string; description: string; status: string }
    >;
    locations: {
      id: string;
      name: string;
      description: string;
      connections: string[];
    }[];
    exits: { id: string; name: string }[];
    game_time: number;
    mechanical_resolution_complete: boolean;
    choice: null | {
      id: string;
      actor: string;
      kind: string;
      prompt: string;
      options: { id: string; label: string }[];
    };
    pending: null | {
      reason: string;
      id: string;
      actor: string;
      controller: string;
      player_id: string;
      purpose: string;
      expression: string;
      modifier: number;
      critical: boolean;
      ability: string;
      skill: string;
    };
    reaction: null | { actor: string; mover: string };
    encounters: { id: string; name: string }[];
    encounter: null | {
      round: number;
      current_actor: string;
      order: string[];
      initiative: Record<string, number>;
      action: boolean;
      bonus_action: boolean;
      reaction: Record<string, boolean>;
      movement: number;
      disengaged: boolean;
    };
  };
  history: {
    revision: number;
    user_text: string;
    narrative: string;
    events: { text: string; kind?: string; success?: boolean; roll?: Roll }[];
  }[];
  usage: Usage[];
};
export type ValidationIssue = {
  code: string;
  entity_type: string;
  entity_id: string;
  field: string;
  reference: string;
  message: string;
};
export type ValidationDiagnostics = {
  stage?: string;
  validation_issues?: ValidationIssue[];
  draft_id?: string;
};
export type Draft = {
  generation_status: "VALID" | "INVALID";
  validation_issues: ValidationIssue[];
  validation_stage: string;
  id: string;
  revision: number;
  definition: Record<string, unknown> & {
    name: string;
    starting_scene: string;
    locations: { id: string; name: string; description: string }[];
  };
  usage: Usage[];
};
export const abilities: Record<string, string> = {
  strength: "Сила",
  dexterity: "Ловкость",
  constitution: "Телосложение",
  intelligence: "Интеллект",
  wisdom: "Мудрость",
  charisma: "Харизма",
};
export const skills: Record<string, string> = {
  athletics: "Атлетика",
  perception: "Восприятие",
  stealth: "Скрытность",
  persuasion: "Убеждение",
  investigation: "Анализ",
  survival: "Выживание",
};
export const purposes: Record<string, string> = {
  check: "Проверка",
  save: "Спасбросок",
  initiative: "Инициатива",
  attack: "Атака",
  damage: "Урон",
  death: "Спасбросок от смерти",
};
export const signed = (v: number) => (v >= 0 ? `+${v}` : String(v));
