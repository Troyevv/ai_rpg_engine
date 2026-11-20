import catalog from '../../../../shared/portrait-illustration.json';
import type { LegacyPortrait } from '../proceduralPortrait';
import type { BodyFrame } from '../portraitAnatomy';

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
