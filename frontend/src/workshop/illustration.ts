import catalog from '../../../shared/portrait-illustration.json';
import legacy from '../../../shared/portrait-catalog.json';
import type { ProceduralPortrait, LegacyPortrait } from './proceduralPortrait';
import type { BodyFrame } from './portraitAnatomy';

export { catalog as illustrationCatalog };
export type ArtStyle = keyof typeof catalog.art_styles;
export type Traits = { [K in keyof typeof catalog.styles]: keyof (typeof catalog.styles)[K] } & {
  trim: keyof typeof catalog.styles.clothing_color;
};
export type Illustration = Pick<
  LegacyPortrait,
  'form' | 'stage' | 'seed' | 'visual_age' | 'visual_age_mode' | 'palette'
> & {
  version: 4;
  art_style: ArtStyle;
  art_revision: 1;
  body_frame: BodyFrame;
  traits: Traits;
  manual_traits?: (keyof Traits)[];
};
export function convertStyle(p: ProceduralPortrait, style: ArtStyle): Illustration {
  if (p.version === 4) return { ...p, art_style: style };
  const layer = p.version === 3 ? p : undefined;
  const key = <K extends keyof typeof legacy.styles>(group: K, index: number) =>
    Object.keys(legacy.styles[group])[index] as keyof (typeof legacy.styles)[K];
  return {
    version: 4,
    art_revision: 1,
    art_style: style,
    seed: p.seed,
    stage: p.stage,
    form: p.form,
    palette: p.palette,
    visual_age: p.visual_age,
    visual_age_mode: p.visual_age_mode,
    body_frame: p.version === 1 ? 'neutral' : p.body_frame,
    traits: {
      face: layer?.visage || key('face', p.face),
      hair: layer?.hairstyle || key('hair', p.hair),
      clothing: layer?.garment || key('clothing', p.clothing),
      skin: key('skin', p.skin),
      eyes: key('eyes', p.eyes),
      hair_color: key('hair_color', p.hair_color ?? 1),
      clothing_color: key('clothing_color', p.clothing_color ?? 0),
      trim: 'cream',
      build: 'average',
      brows: 'tapered',
      eye_shape: layer?.eye_shape || 'almond',
      nose_shape: layer?.nose_shape || 'straight',
      lip_shape: layer?.lip_shape || 'defined',
      facial_hair: p.version === 1 ? 'clean_shaven' : p.facial_hair,
      detail: ({ 2: 'studs', 3: 'drops' } as const)[p.accessory as 2 | 3] || 'none',
      expression: 'neutral',
    },
  };
}
export function validIllustration(p: Illustration) {
  return (
    p.art_revision === 1 &&
    Object.hasOwn(catalog.art_styles, p.art_style) &&
    /^[a-f0-9]{32}$/.test(p.seed) &&
    ['human', 'neutral'].includes(p.form) &&
    ['male', 'female', 'neutral'].includes(p.body_frame) &&
    Number.isInteger(p.palette) &&
    p.palette >= 0 &&
    p.palette < 7 &&
    p.traits &&
    Object.entries(catalog.styles).every(([key, labels]) =>
      Object.hasOwn(labels, p.traits[key as keyof Traits]),
    ) &&
    Object.hasOwn(catalog.colors.clothing_color, p.traits.trim)
  );
}
// Mix only trusted manifest colors, in sRGB. Local pigments keep shadows tinted on dark skin.
export function mix(a: string, b: string, t: number) {
  return (
    '#' +
    [1, 3, 5]
      .map((i) =>
        Math.round(parseInt(a.slice(i, i + 2), 16) * (1 - t) + parseInt(b.slice(i, i + 2), 16) * t)
          .toString(16)
          .padStart(2, '0'),
      )
      .join('')
  );
}
