import {
  BookOpen, CircuitBoard, Cog, Crown, Orbit, Feather, Church, Route, Zap,
  Files, SquareTerminal, Compass, Wrench, Fingerprint, Eclipse, Radio, AudioWaveform,
} from 'lucide-react';
import type {ThemeId} from '../lib/skins';

const emblems = {
  graphite: BookOpen, cyberpunk: CircuitBoard, industrial: Cog, medieval: Crown,
  arcane: Orbit, parchment: Feather, gothic: Church, urban: Route, street: Zap,
  noir: Files, terminal: SquareTerminal, space: Compass, 'post-apocalypse': Wrench,
  biotech: Fingerprint, occult: Eclipse, retro: Radio, neon: AudioWaveform,
} satisfies Record<ThemeId, typeof BookOpen>;

export function SkinEmblem({id}: {id: ThemeId}) {
  const Icon = emblems[id];
  return <Icon aria-hidden="true" focusable="false"/>;
}
