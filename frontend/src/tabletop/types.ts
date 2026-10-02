export type Spell = {
  id: string;
  name: string;
  level: number;
  classes: string[];
  casting_time: string;
  range: number;
  target_type: string;
  area: number;
  concentration: boolean;
  description: string;
};
export type Build = {
  purchases?: Entry[] | null;
  spells?: string[] | null;
  prepared_spells?: string[] | null;
  ability_method: "standard_array" | "point_buy" | "allocation";
  concept: string;
  feature_choices: string[];
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
export type Feature = {
  source: string;
  recharge: string;
  reach: number;
  level: number;
  id: string;
  name: string;
  description: string;
  activation: string;
  resource: string;
  uses: number;
  target: string;
  effects: { type: string; value: number; key: string }[];
};
export type Catalog = {
  currency_label?: string;
  setting_id?: string;
  setting_revision?: number;
  draft_id?: string;
  allocation: {
    base: number;
    points: number;
    minimum: number;
    maximum: number;
  };
  starting_gold: number;
  equipment_slots: Record<string, string>;
  equipment_layout?: Record<string, { position: string; group: string }>;
  spells: Record<string, Spell>;
  spellcasting: Record<
    string,
    {
      ability: string;
      defaults: string[];
      known: number;
      prepared: number;
      slots: Record<string, number>;
    }
  >;
  point_buy: {
    budget?: number;
    minimum?: number;
    maximum?: number;
    costs?: Record<string, number>;
  };
  features: Record<string, Feature>;
  id: string;
  name: string;
  abilities: string[];
  ability_array: number[];
  skills: Record<string, string>;
  classes: Record<
    string,
    {
      name: string;
      description?: string;
      starting_gold?: number;
      hit_die: number;
      primary_abilities?: string[];
      armor?: string[];
      weapons?: string[];
      features?: string[];
      feature_choices?: string[];
      feature_choice_count?: number;
      skills: string[];
      equipment: string[];
      equipment_choices?: string[][];
      saves: string[];
      skill_count: number;
    }
  >;
  species: Record<
    string,
    { name: string; speed: number; description?: string; features?: string[] }
  >;
  backgrounds: Record<
    string,
    {
      name: string;
      description?: string;
      skills?: string[];
      equipment?: string[];
      proficiencies?: string[];
      hooks?: string[];
      starting_gold?: number;
      tools?: string[];
      languages?: string[];
      features?: string[];
    }
  >;
  items: Item[];
  default_build: Build;
};
export type Item = {
  starting_available?: boolean;
  components?: { type: string; damage_expression?: string }[];
  slots: string[];
  hands: number;
  armor_category: string;
  armor_base: number;
  dex_cap: number;
  ac_bonus: number;
  weapon_die: number;
  weapon_ability: string;
  stealth_disadvantage: boolean;
  id: string;
  name: string;
  description: string;
  type: string;
  healing: number;
  weight: number;
  value: number;
};
export type Entry = {
  item_id: string;
  quantity: number;
  equipped: boolean;
  slot?: string;
};
export type Sheet = {
  resource_definitions?: Record<string, { name: string; maximum: number }>;
  gold: number;
  equipment_slots: Record<string, string>;
  equipment_layout?: Record<string, { position: string; group: string }>;
  equipment_bonuses: Record<string, number>;
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
  damage_modifiers: Record<string, number>;
  inventory: Entry[];
  resources: Record<string, number>;
  progression: {
    available: boolean;
    maximum: boolean;
    level: number;
    required_xp: number;
    mode: string;
    proficiency: number;
    hp_base: number;
    asi: boolean;
    features: Feature[];
    subclasses: { id: string; name: string; description: string }[];
    feats: Feature[];
    spells: Spell[];
    learn_spells: number;
    spell_slots: Record<string, number>;
  };
  xp: number;
  subclass: string;
  feature_definitions: Feature[];
  spells: string[];
  prepared_spells: string[];
  spell_definitions: Spell[];
  spell_slots: Record<string, { maximum: number; remaining: number }>;
  concentration: null | { spell_id: string };
  biography: string;
  appearance: string;
  personality: string;
  ideals: string;
  bonds: string;
  flaws: string;
  controller: { controller: string; player_id: string | null };
};
export type Command = {
  mode?: string;
  action_id?: string;
  type: string;
  check_id?: string;
  slot?: string;
  actor_id?: string;
  target?: string;
  purpose?: string;
  ability?: string;
  skill?: string;
  weapon?: string;
  distance?: number;
  item_id?: string;
  feature_id?: string;
  subclass?: string;
  feat_id?: string;
  ability_increases?: string[];
  learn_spells?: string[];
  spell_id?: string;
  slot_level?: number;
  spells?: string[];
  quantity?: number;
  rest?: string;
  topic?: string;
};
export type Roll = {
  components?: { die: number; raw: number[]; selected: number; sign: number }[];
  expression: string;
  raw: number[];
  selected: number;
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
    attack_previews: AttackPreview[];
    usable_actions: {
      kind: string;
      id: string;
      name: string;
      description: string;
      cost: string;
      slot_level: number;
      targets: {
        id: string;
        name: string;
        distance: number;
        hit_percent?: number;
        modifier?: number;
        target_ac?: number;
        expression?: string;
        healing_modifier?: number;
        save?: string;
        save_dc?: number;
        half_on_save?: boolean;
      }[];
    }[];
    context_actions?: { id: string; name: string; description: string }[];
    checks: {
      id: string;
      name: string;
      description: string;
      save: boolean;
      skill: string;
      ability: string;
      category: string;
    }[];
    dm_settings: import("./DMSettings").Settings;
    campaign: string;
    initial_conflict: string;
    plot_hooks: string[];
    factions: {
      id: string;
      name: string;
      description: string;
      public_goal: string;
      reputation: number;
    }[];
    ruleset: { id: string; name: string };
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
      dc?: number;
      reason: string;
      id: string;
      actor: string;
      controller: string;
      player_id: string;
      purpose: string;
      expression: string;
      modifier: number;
      critical: boolean;
      advantage: number;
      modifier_breakdown?: Record<string, number>;
      advantage_sources: { name: string; value: number }[];
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
      attacks_remaining: number;
      bonus_action: boolean;
      free_interaction: boolean;
      ready: Record<string, string>;
      reaction: Record<string, boolean>;
      movement: number;
      disengaged: boolean;
    };
  };
  history: {
    revision: number;
    user_text: string;
    narrative: string;
    events: {
      hp_before?: number;
      hp_after?: number;
      maximum?: number;
      target?: string;
      outcome?: string;
      text: string;
      kind?: string;
      success?: boolean;
      dc?: number;
      skill?: string;
      roll?: Roll;
    }[];
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
  acrobatics: "Акробатика",
  sleight_of_hand: "Ловкость рук",
  arcana: "Магия",
  history: "История",
  nature: "Природа",
  religion: "Религия",
  animal_handling: "Уход за животными",
  insight: "Проницательность",
  medicine: "Медицина",
  deception: "Обман",
  intimidation: "Запугивание",
  performance: "Выступление",
  athletics: "Атлетика",
  perception: "Восприятие",
  stealth: "Скрытность",
  persuasion: "Убеждение",
  investigation: "Анализ",
  survival: "Выживание",
};
export const purposes: Record<string, string> = {
  feature_healing: "Лечение способностью",
  spell_attack: "Атака заклинанием",
  spell_save: "Спасбросок против заклинания",
  spell_damage: "Урон заклинания",
  spell_healing: "Лечение заклинанием",
  concentration: "Проверка концентрации",
  check: "Проверка",
  save: "Спасбросок",
  initiative: "Инициатива",
  attack: "Атака",
  damage: "Урон",
  death: "Спасбросок от смерти",
};
export const signed = (v: number) => (v >= 0 ? `+${v}` : String(v));

export type AttackPreview = {
  expression?: string;
  damage_type?: string;
  resource_cost?: { resource_id: string; amount: number }[];
  mode?: string;
  ammunition_cost?: number;
  ammunition_remaining?: number;
  magazine?: { capacity: number; reload_cost: string } | null;
  target_ac: number;
  weapon: string;
  name: string;
  target: string;
  target_name: string;
  available: boolean;
  reason: string;
  distance: number;
  reach: number;
  hit_percent: number;
  advantage: number;
  sources: { name: string; value: number }[];
  modifier: number;
  damage_modifier: number;
  die: number;
  damage: number[];
  critical_damage: number[];
  damage_note: string;
  cost: string;
  breakdown: Record<string, number>;
};
