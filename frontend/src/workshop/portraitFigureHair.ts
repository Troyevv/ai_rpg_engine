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
  french_crop: {
    front:'M-60 3Q-72-21-61-54Q-55-81-26-90Q6-99 31-86Q59-83 69-53L67-19 58 5 52-20 49-37Q27-33 16-39L9-34-5-38-16-33-27-39-47-34-53-22Z',
    strokes:'M-51-49q4-19 23-31m-10 31q6-18 20-31m-7 33q5-23 18-37m-1 35q7-16 15-28m-88 60l3-9m118 4 4-13',
  },
  quiff: {
    front:'M-59 4Q-66-15-60-40Q-79-44-77-64Q-76-84-47-94Q-20-104-24-115Q-9-114-9-104Q27-117 52-94Q74-80 70-56Q75-33 62 4L55 10 49-19Q49-46 32-56Q12-69-7-65Q-44-48-53-39Z',
    shine:'M-67-62Q-65-82-30-90Q-7-95 1-102Q-2-88-24-78Q-49-66-67-62Z',strokes:'M-56-63Q-33-81-14-83Q3-85 15-101m-46 38Q8-72 25-92m10 10q16 5 21 19m-2 19 7 16',
  },
  flat_top: {
    front:'M-60 4L-66-21-68-67Q-68-85-59-95L-44-97-31-96-19-98 0-97 17-99 35-97 49-98 61-94Q69-77 69-53L66-10 57 9 50-23 49-49Q35-68 0-68Q-33-68-49-51L-54-19Z',
    strokes:'M-59-77l3-10m4 8 3-11m6 8 1-11m7 10 2-13m7 9 1-11m7 11 1-10m9 12 0-13m10 13-1-11m10 13-1-10m11 13-4-12m-99 36 0-7m109 9-2-10',
  },
  finger_waves:{
    front:'M-59 9Q-76 4-71-14Q-80-33-65-55Q-64-81-35-89Q-8-102 16-90Q44-98 63-68Q83-46 69-19Q78 0 59 18Q50 15 57 1Q63-12 52-19Q39-27 42-40Q41-52 26-52Q8-47-4-60Q-15-64-28-54Q-40-41-51-42Q-64-36-54-25Q-42-14-53-3Q-60 2-59 9Z',
    strokes:'M-64-43Q-54-59-40-56Q-28-53-21-63Q-12-77 7-68Q25-56 40-64m-98 11q9-15 24-14t27-10q11-9 25-1t30 7m-8 27q17-5 20 10t-1 31m-119-21q11 12 3 20',
    shine:'M-60-52Q-50-68-34-64Q-22-60-15-72Q-4-84 12-75Q-4-80-13-66Q-22-53-34-58Q-46-63-60-52Z',
  },
  shag:{
    back:'M-57-55Q-78-24-65 5L-77 35-62 30-71 61-57 53-62 76-38 60-24 70-7 41 13 48 30 65 38 56 61 78 56 55 77 66 65 39 82 45 70 21 77 22 66-46Z',
    front:'M-60 15L-72-7-63-12-75-20-67-39-74-38Q-68-68-44-79L-50-80Q-27-104-3-92Q28-106 47-86L43-91Q70-79 73-51L80-49 68-32 76-28 62-10 65 18 50 2 44-24 35-13 37-35 20-21 24-40 8-31 7-47-11-26-8-44-28-31-26-45-44-32-49-12Z',strokes:sideLines,
  },
  asym_bob:{
    back:'M-59-54Q-79-20-72 49Q-69 76-85 96Q-49 76-29 49L18 39Q44 39 73 17Q64 1 69-25L51-64Z',
    front:'M-62 27Q-78 4-70-46Q-66-82-35-92Q-6-105 24-91Q67-86 70-50Q75-23 60 0L53-13 49-36Q34-48 21-64Q3-39-26-21Q-56 0-54 43Q-53 63-76 83Q-66 59-62 27Z',strokes:'M13-79Q-4-57-33-37Q-62-17-63 23m73-94Q-4-46-32-25m58-48q24 12 31 37',
  },
  blunt_long:{
    back:'M-56-65Q-76-29-72 12L-73 120Q-46 125-23 112L-12 56H21L37 119Q59 127 84 119L76-3Q78-39 58-64Z',
    front:'M-60 33Q-71-1-68-42Q-65-82-26-92Q4-101 33-89Q70-78 73-38L70 85 56 105 52-24Q21-19 6-22L3-27 1-22Q-27-19-49-25L-52 97-68 109Z',strokes:'M-50-37q-2-31 27-48m-12 56q0-26 15-47m4 45q0-21 8-43m16 44q0-18-3-37m22 39q-2-20-12-37m40 123-3-75',
  },
  hime:{
    back:long,front:'M-61 50L-72 49-68-38Q-65-79-32-90Q0-102 26-91Q66-82 70-48L79 52 49 53 46-26Q29-31 19-52Q4-32-19-30L-32-29-31-35-47-27-44 48Z',
    strokes:'M-62 37l1-66q5-40 31-49m-20 55q29-22 40-52m12 38q13-12 14-31m40 108-4-71m-6 73-3-69',backLines:'M-65 3q2 77-9 103m142-93q-1 70 15 105',
  },
  afro:{
    back:'M-71-54Q-95-41-88-18Q-99 5-77 18Q-81 35-53 38L-29 15H35L59 40Q85 42 82 24Q108 18 96-3Q108-26 87-44Z',
    front:'M-66 18Q-84 21-84 5Q-104 3-95-16Q-111-26-99-42Q-107-61-88-71Q-93-94-69-97Q-64-118-43-112Q-32-130-12-121Q9-134 25-120Q48-131 60-110Q83-114 90-91Q110-85 100-65Q117-51 103-34Q113-11 94-6Q100 15 79 18Q72 32 60 21L53 0Q42-2 44-17Q26-13 24-30Q9-23 1-34Q-11-23-25-32Q-31-18-44-22Q-46-4-56-5Z',
    strokes:coilLines+' M-83-66q6-12 15-10m4-20q12-9 23-4m32-13q12-9 22 1m36 7q16 1 15 14m18 20q10 7 5 15m-172 17q-3 12 6 17',
  },
  locs:{
    back:'M-56-60Q-69-29-77 14L-85 74Q-84 84-77 77L-58 21-70 99Q-70 108-61 101L-44 29-49 89Q-46 97-40 88L-26 32 17 37 35 101Q39 108 42 100L34 33 60 110Q66 117 68 107L58 29 80 95Q87 104 87 92L72-28 53-61Z',
    front:curtains+' M-48-44Q-66-19-63 12L-58 49Q-54 58-50 48L-53 12Q-55-12-39-32Z M45-47Q63-29 63-7L71 44Q70 54 62 46L52-3Q48-20 36-33Z',strokes:'M-54-38Q-39-66-14-76m-23 40q17-27 32-39m11 18 18 23m10-26q24 17 30 44',backLines:'M-62 17l-15 54m20-38-7 59m112-58 14 69m-7-79 20 62',
  },
  twin_braids:{front:part,back:'M-53-49Q-71-26-65 0Q-81 12-70 25Q-86 40-73 53Q-86 66-74 79Q-85 91-75 103L-78 119-66 111-66 102Q-54 92-65 79Q-51 66-63 52Q-51 39-61 26Q-49 12-55 1L-40-34Z M49-42Q72-32 69-3Q85 10 74 25Q91 39 79 52Q94 67 82 79Q95 91 84 105L89 122 76 114 74 104Q62 93 72 80Q56 66 67 52Q54 38 65 26Q50 13 57-1Z',strokes:sideLines,backLines:'M-71 10l11 11m-16 16 12 12m-13 16 11 11m-11 14 9 9m140-90-11 12m15 16-11 12m14 16-10 12m13 15-10 11'},
  twin_puffs:{front:swept,back:'M-49-55Q-67-45-80-54Q-106-48-109-69Q-126-85-109-99Q-106-120-85-114Q-67-126-55-109Q-36-106-42-85Z M44-60Q60-43 78-51Q100-42 110-61Q129-69 117-91Q123-111 101-117Q87-132 71-116Q48-120 47-97Q34-83 44-60Z',strokes:sweepLines,backLines:'M-99-93q-2-13 12-13m1 32q-8-12 3-20m13-7q12 5 10 16m139-11q8-13 20-5m-15 25q-6-12 4-18m14 11q11 2 9 12'},
  crown_braid:{front:curtains+' M-63-17Q-78-24-68-39Q-80-47-66-60Q-72-73-54-79Q-55-93-38-92Q-29-107-15-98Q-1-109 12-99Q29-106 39-93Q57-94 60-79Q78-73 72-59Q85-47 72-35Q78-23 63-15L55-31Q56-65 26-79Q-3-92-31-79Q-52-66-55-35Z',strokes:'M-64-34l8-12m-7-5 13-10m-10-7 15-7m-5-9 14-3m0-8 14 2m2-6 12 5m7-4 11 8m8-2 8 10m7-1 4 13m5 1 0 12m3 4-3 12',back:'M-51-29Q-73-15-65 8Q-60 29-40 26L-25 8Z'},
  high_pony:{front:swept,back:'M15-79Q38-118 67-110Q104-110 105-69Q109-44 99-22Q88 6 98 28Q110 53 106 72Q94 47 80 39Q54 20 68-20Q79-51 67-66Q52-81 27-65Z',shine:sweptLight,strokes:sweepLines,backLines:'M50-97q25-17 38 8q14 24-1 53t6 64m-23-88q12 19 3 41'},
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

// Shapes sit in skull space (eyes at y=0). Sweep, fringe and temple have
// different edges even at avatar size. Long locks cover the shoulder in front.
const croppedCuts: Partial<Record<HairStyle, Partial<Cut>>> = {
 short: {front:'M-59 4Q-68-9-64-36Q-69-61-44-76L-48-79Q-32-89-10-86Q5-98 26-89Q53-88 64-66Q77-52 66-31L63-6L55 8 53-20Q55-39 35-47Q24-48 20-59Q11-42-7-39L1-51Q-13-37-32-37L-28-44Q-48-36-53-25Z'},
 parted: {front:'M-58 4Q-68-18-63-46C-54-77-28-91-7-88C3-93 7-94 15-89Q54-94 69-56Q76-28 63 5L56 10Q58-14 48-35Q30-46 15-68C8-52-8-39-30-34Q-45-30-52-17Z',strokes:'M12-78Q-6-59-40-47m55-36Q35-71 49-52m-44-27Q-22-69-45-55m67-24Q49-67 58-46'},
 medium:{front:curtains+' M-55-33Q-67 0-55 29Q-48 45-55 52Q-40 43-46 19Q-53-2-42-24Z'},
 wavy:{front:curtains+' M48-36C64-20 56 3 62 19C73 39 53 53 53 65Q54 83 69 88Q60 77 66 66C85 44 73 31 73 17Q73-9 68-32Z'},
 long:{front:curtains+' M-59-31C-77 6-62 43-64 77Q-67 98-76 105Q-51 101-51 74C-46 34-59 12-45-30Z'},
 bun:{back:'M31-65Q49-90 72-79Q95-71 85-44Q78-27 54-32Z',backLines:'M49-70q17-12 28 3m-25 9q20-10 26 2'},
 curly:{front:'M-61 7Q-75 8-71-9Q-87-12-77-31Q-88-43-74-56Q-77-73-58-76Q-56-93-39-88Q-31-106-14-96Q-2-110 14-98Q33-108 44-95Q64-97 68-79Q87-78 80-61Q99-53 87-37Q94-19 76-14Q78 2 62 9Q57 18 52 11L50-4Q35-1 37-16Q22-13 20-26Q8-17 2-29Q-12-16-23-27Q-32-12-44-20Q-44-4-55-7Z'},
};
// Extents of cuts that rise above or extend well outside the fitted skull,
// in the same 61 × 87 reference space as the locks.
const extent: Partial<Record<HairStyle, readonly [number,number]>> = {
  afro:[110,129], twin_puffs:[123,124], high_pony:[106,111],
  ponytail:[109,100], quiff:[79,115], wavy:[106,102],
};
export function hairExtents(style:HairStyle, temple:number, crown:number) {
  const [width,height]=extent[style]||[80,103];
  return {halfWidth:width*(temple+1)/61, height:height*(-crown)/87};
}

export function figureHair(
  style: HairStyle,
  temple: number,
  crown: number,
  light: string,
  dark: string,
  fit?: {infant: boolean; part: number},
) {
  const coated = style === 'ponytail' || style === 'braid' || style === 'bun';
  const parted =
    style === 'parted' || style === 'long' || style === 'wavy' || style === 'medium' || style === 'bob';
  const hairline = coated
    ? line('M-49-35Q-36-49-21-55m62 18q8 9 11 19', dark, 1.0, 0.58)
    : parted
      ? line('M8-83Q11-72 9-62m23 20q12 11 17 22', light, 1, 0.5)
      : '';
  if (fit?.infant && (style === 'buzz' || style === 'short')) {
    const wisps = 'M-40-61Q-32-80-13-83Q-17-89-10-92Q-9-85-2-83Q13-85 26-74 M-27-73q10-10 22-8m-9 5q12-3 23 3';
    return {back:'',front:`<g transform="scale(${temple/61} ${-crown/87})">${line(wisps,dark,1.65,.62)}</g>`};
  }
  const cut = fit ? {...cuts[style], ...croppedCuts[style]} : cuts[style],
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
            (fit && parted ? line(`M${2+fit.part*6} -85q4 6 2 10`, light, 1.6, .57) : '') +
            hairline +
            '</g>',
        )
      : '',
  };
}
