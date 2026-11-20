// Hair is authored against one skull: the part, hairline and temple are shared
// by the rear mass and the front locks. Only their position in the paint order differs.
import { seam as line, shape as path } from './portraitWardrobe';
import type { HairStyle } from './portraitFigure';

const swept =
  'M-60 2C-67-8-72-37-62-58C-54-81-27-98 5-95C39-98 68-78 71-45Q75-24 63 0L55 9L50-16C48-29 36-41 18-47C4-50-10-54-21-58C-30-46-42-44-51-32Q-60-17-60 2Z';
const part =
  'M-59 2C-71-11-72-44-59-64C-43-89-18-99 6-94C34-103 65-83 72-57Q79-26 61 3L53 10L50-20C39-26 29-40 11-59Q3-49-8-42L-6-45Q-24-31-40-30L-37-33Q-53-26-55-16L-59 2Z';
const curtains =
  'M-62 9Q-77-22-65-54C-57-81-34-96-3-94Q28-105 54-83C77-67 82-30 69 5L62 24Q62-5 50-18C37-30 20-41 4-61C-7-48-20-40-33-31C-48-23-54-10-62 9Z';
const sweptLight = 'M-59-38Q-48-73-17-83Q-34-74-44-52C-23-79 0-86 23-81Q-8-77-20-60Q-43-48-59-38Z';
const partLight = 'M-58-42Q-46-78-14-82Q-32-68-42-51Q-19-73 3-80Q-8-59-29-48Z';
const sweepLines =
  'M-59-43Q-51-68-28-81m-25 35Q-37-72-12-83m-28 32Q-20-74 3-79m-20 20Q1-72 16-72m5-8Q49-73 62-47m-45-27Q44-63 55-39';
const sideLines =
  'M-56-41Q-43-68-16-80m-30 35Q-28-69-6-77m-29 31Q-7-62 5-81m-20 30Q0-64 7-75m14-4q23 11 34 31m-36-23q19 17 29 32m5-16q7 11 9 22';
const lob =
  'M-54-56Q-74-29-66 10Q-60 41-75 62Q-62 76-40 64L-19 34 20 45Q40 72 64 71Q83 65 78 54C65 24 84-10 66-53Z';
const long =
  'M-54-58C-81-23-64 24-76 68Q-82 101-92 116Q-69 127-43 111L-12 54 24 65Q36 109 58 126Q81 139 103 124C72 94 91 50 78 17Q76-31 61-62Z';
const waves =
  'M-58-51C-83-29-65-5-76 18Q-92 37-80 59C-67 76-91 84-89 107Q-87 124-100 129Q-68 145-48 116Q-30 108-26 80L12 56Q21 95 44 109Q40 137 70 141Q88 147 108 126C85 127 98 109 93 93Q81 80 87 64Q99 43 83 23Q72 10 78-8Q81-45 59-66Z';
const bob =
  'M-57-58Q-78-24-73 20L-74 55Q-65 65-42 64Q-34 43-22 32L30 35 39 67Q68 71 82 54Q72 18 76-3Q79-39 58-66Z';
const bobFront =
  curtains +
  ' M-57-35Q-70-3-60 26Q-56 45-66 60Q-53 57-48 45Q-48 21-53 9Q-59-6-46-34Z M53-29Q69-11 62 15Q55 43 66 61Q72 65 79 56Q69 32 75 4Q79-20 66-44Z';
const short =
  'M-60 5Q-69-6-68-28L-73-25Q-69-58-54-66L-59-69Q-43-88-23-90Q-3-107 24-93Q48-96 62-72Q78-62 72-38L76-40Q73-17 62-3L56 12 50-14Q43-22 44-34L33-27Q30-40 21-46Q12-32-5-28Q2-36 4-45Q-8-33-26-33Q-20-43-21-48Q-35-35-48-35Q-55-22-60 5Z';
const pixie =
  'M-61 1L-68-17-67-36-73-31Q-66-62-48-72L-54-74Q-27-98 1-94Q28-109 54-85L47-85Q72-73 74-49L68-51Q75-25 63-7L57 8 53-13 46-9 46-33Q35-16 16-15L26-35Q7-17-13-12L-4-30Q-24-15-41-17L-37-32Q-52-21-61 1Z';
const under =
  'M-60 1Q-67-21-62-44Q-76-52-58-74Q-33-105 8-101Q53-102 70-79Q83-63 69-42L61 1 55 10 49-18Q47-33 36-42Q13-49-10-40Q-35-28-50-33Z';
const curl =
  'M-61 5Q-76 3-72-12Q-88-20-75-35Q-86-50-70-59Q-74-78-54-80Q-50-97-32-94Q-18-109-2-99Q16-111 30-98Q50-104 59-87Q79-87 79-68Q93-56 83-40Q88-23 74-15Q74 2 59 7L51-6Q39-6 41-21Q25-17 22-31Q8-23-2-34Q-14-23-25-33Q-34-19-47-26Q-49-8-58-11Z';
const coilLines =
  'M-67-48q0-12 12-13m-5 23q-10-8-4-17m13-17q5-10 17-8m-10 24q-4-12 8-17m9 17q-6-13 6-18m7-14q12-6 20 4m-13 18q0-13 12-13m5 18q0-12 10-16m8-13q13 0 18 10m-12 17q-4-9 5-14m14 5q12 4 11 14m-13 15q-6-11-1-18m-44 16q-5-10 2-17';
type Cut = { front: string; back?: string; shine?: string; strokes?: string; backLines?: string };
const cuts: Record<HairStyle, Cut> = {
  bald: { front: '' },
  buzz: {
    front:
      'M-60-1Q-71-35-54-61Q-34-87 1-89Q42-92 61-65Q78-41 66-9L56 6 51-17Q47-51 14-60Q-21-75-47-46Q-57-33-60-1Z',
    strokes: 'M-47-54l3-4m5-4 3-4m5-3 3-3m7-3 3-2m7-2 3-1m8-1 4 0m10 3 4 2m7 4 3 3m7 6 2 3',
  },
  receding: {
    front:
      'M-59-3Q-67-24-63-45Q-57-67-37-75Q-49-64-47-47Q-47-37-54-27Z M24-83Q62-75 69-48Q77-25 63 0L55 9 49-11Q53-45 43-61Q37-76 24-83Z',
    strokes: 'M49-61Q60-43 59-24m1-26q6 12 3 25m-118-23q-6 11-6 22',
  },
  short: { front: short, shine: partLight, strokes: sideLines },
  parted: { front: part, shine: partLight, strokes: sideLines },
  pixie: {
    front: pixie,
    shine: 'M-57-49Q-47-79-14-86Q-27-76-35-59Q-7-83 27-82Q2-66-15-48L-9-61Q-30-44-43-39Z',
    strokes: sideLines,
  },
  undercut: {
    front: under,
    shine: 'M-63-54Q-56-83-18-91Q-36-77-42-65Q-12-90 22-88Q-6-82-28-62Z',
    strokes: 'M-58-60Q-24-97 20-91m-61 34Q0-85 39-78m6 39q9 3 15 13m-12-8 11 12m-8-5 7 8',
  },
  curly: { front: curl, strokes: coilLines },
  fringe: {
    front:
      curtains +
      ' M-60-29Q-51-64-12-73Q25-74 52-41L54-14Q42-22 34-33L37-15Q18-19 9-33L10-16Q-9-16-17-25L-22-15-42-16-45-25-57-15Z',
    back: lob,
    strokes: 'M-48-35q7-20 23-32m-10 44q9-28 24-43m2 39q6-23 4-38m22 36q-4-19-12-29',
  },
  bob: {
    front: bobFront,
    back: bob,
    shine: partLight,
    strokes: sideLines,
    backLines: 'M-65-4q0 34-2 51m137-58q2 30 3 53',
  },
  medium: {
    front: curtains,
    back: lob,
    shine: sweptLight,
    strokes: sweepLines,
    backLines: 'M-60-3q8 42-6 63m132-76q-6 46 5 74',
  },
  long: {
    front: curtains,
    back: long,
    shine: partLight,
    strokes: sideLines,
    backLines: 'M-65-9q9 64-16 115m14-42q-2 24-9 39m142-118q-3 50 6 77t15 50',
  },
  wavy: {
    front: curtains,
    back: waves,
    shine: sweptLight,
    strokes: sweepLines,
    backLines: 'M-61-10q5 21-7 41t-3 35q6 14-7 30m140-106q-3 20 11 37t0 33q-7 15 6 30t10 24',
  },
  ponytail: {
    front: swept,
    back: 'M42-66Q74-84 90-58Q102-37 91-6Q76 28 88 62Q94 78 108 84Q72 86 59 51Q49 26 59-8Q68-41 41-43Z',
    shine: sweptLight,
    strokes: sweepLines,
    backLines: 'M71-55q17 12 8 42Q61 33 81 64',
  },
  bun: {
    front: swept,
    back: 'M16-76C10-97 17-115 37-119Q64-125 77-104Q90-77 64-61Z',
    shine: sweptLight,
    strokes: sweepLines,
    backLines: 'M25-100q13-17 34-8m-27 15q17-15 34-8',
  },
  braid: {
    front: swept,
    back: 'M41-57Q75-52 73-17L69 9Q85 20 72 36Q89 49 75 64Q91 80 77 93Q87 106 76 119L81 139 69 134 66 121Q49 114 57 98Q42 86 53 70Q37 57 51 42Q36 29 48 13Q35 3 42-12Z',
    shine: sweptLight,
    strokes: sweepLines,
    backLines: 'M48 12q14 5 23 16m-17 12q12 4 20 15m-17 14q12 5 17 14m-14 14q9 6 14 15',
  },
};
export function hairCut(style:HairStyle): Readonly<Cut> { return cuts[style] }

export function figureHair(
  style: HairStyle,
  temple: number,
  crown: number,
  light: string,
  dark: string,
) {
  const coated = style === 'ponytail' || style === 'braid' || style === 'bun';
  const parted =
    style === 'parted' || style === 'long' || style === 'wavy' || style === 'medium' || style === 'bob';
  const hairline = coated
    ? line('M-49-35Q-36-49-21-55m62 18q8 9 11 19', dark, 1.0, 0.58)
    : parted
      ? line('M8-83Q11-72 9-62m23 20q12 11 17 22', light, 1, 0.5)
      : '';
  const cut = cuts[style],
    wrap = (s: string) => `<g transform="scale(${(temple + 1) / 61} ${-crown / 87})">${s}</g>`;
  return {
    back: cut.back
      ? wrap(path(cut.back, 'url(#hairMass)') + line(cut.backLines || '', light, 2.3, 0.5))
      : '',
    front: cut.front
      ? wrap(
          `<defs><clipPath id="locks"><path d="${cut.front}"/></clipPath></defs>` +
            path(cut.front, 'url(#hairMass)') +
            `<g clip-path="url(#locks)">` +
            path(cut.shine || '', light, 0.22) +
            line(cut.strokes || '', light, 1.35, 0.58) +
            `<g transform="translate(2 3)">` +
            line(cut.strokes || '', dark, 0.9, 0.32) +
            '</g>' +
            hairline +
            '</g>',
        )
      : '',
  };
}
