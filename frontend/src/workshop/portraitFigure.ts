// Portraits are drawn in a shallow three-quarter view. All head layers use the
// eye line as y=0; only the assembled head is posed on the clothed bust.
import type { ProceduralPortrait, Styles } from './proceduralPortrait';
import { garmentLayer, shape as path, seam as line } from './portraitWardrobe';
import { figureHair } from './portraitFigureHair';

type Human = Extract<ProceduralPortrait, { version: 3 }>;
type Face = keyof Styles['face'];
export type HairStyle = keyof Styles['hair'];
type Paint = {
  skin: readonly string[];
  hair: readonly string[];
  cloth: readonly string[];
  bg: readonly string[];
  iris: string;
  accent?: string;
};
const mix = (a: number, b: number, t: number) => a + (b - a) * t;
const tone = (a: string, b: string, t: number) =>
  '#' +
  [1, 3, 5]
    .map((i) =>
      Math.round(mix(parseInt(a.slice(i, i + 2), 16), parseInt(b.slice(i, i + 2), 16), t))
        .toString(16)
        .padStart(2, '0'),
    )
    .join('');
const grad = (id: string, colors: string[], x2 = '100%', y2 = '65%', reverse = false) =>
  `<linearGradient id="${id}" x1="${reverse ? '100%' : '0%'}" x2="${reverse ? '0%' : x2}" y2="${y2}">${colors.map((c, i) => `<stop offset="${i / (colors.length - 1)}" stop-color="${c}"/>`).join('')}</linearGradient>`;
const wash = (id: string, color: string, alpha: number) =>
  `<radialGradient id="${id}"><stop stop-color="${color}" stop-opacity="${alpha}"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></radialGradient>`;
const ellipse = (x: number, y: number, rx: number, ry: number, color: string) =>
  `<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" fill="${color}"/>`;
// Width at the cheek, jaw and chin, then length between the eye and chin.
// These are skeletal landmarks; hair, eyes and ears never select a separate face.
const shapes: Record<Face, [number, number, number, number]> = {
  heart:[68,36,11,79], diamond:[73,40,14,83], pear:[59,61,29,78],
  square:[69,61,33,75], oblong:[59,48,24,95],
  oval: [66, 46, 22, 83],
  narrow: [59, 40, 18, 84],
  angular: [70, 50, 21, 82],
  broad: [72, 59, 29, 78],
  long: [62, 47, 23, 91],
  round: [71, 51, 24, 71],
  soft: [67, 48, 25, 77],
};
// Revision four keeps each face's skeletal proportions through childhood.
const classicShapes: typeof shapes = {
  heart:[67,35,10,79], diamond:[75,40,13,82], pear:[62,53,28,81],
  square:[70,59,32,77], oblong:[58,49,25,97],
  oval: [65, 43, 21, 78], narrow: [55, 33, 13, 86],
  angular: [71, 52, 15, 80], broad: [73, 63, 30, 74],
  long: [61, 44, 22, 94], round: [73, 53, 27, 65], soft: [68, 40, 19, 73],
};
const templeWidths: Partial<Record<Face, number>> = {heart:1.04, diamond:.83, pear:.86, square:.98, oblong:1.01};
const features = {
  eye_shape: ['almond','open','hooded','upturned','downturned','deep_set'],
  nose_shape: ['straight','rounded','arched','upturned','broad_base','aquiline'],
  lip_shape: ['defined','full','fine','cupid','wide','lower_full'],
} as const;
export type FeatureChoices = { [K in keyof typeof features]?: (typeof features)[K][number] };
export { features as figureFeatures };

function landmarks(p: Human, shape: Face) {
  const age = p.visual_age || p.stage;
  const infant = age === 'infant',
    child = age === 'child',
    teen = age === 'adolescent',
    elder = age === 'elderly';
  const youth = infant ? 1 : child ? 0.62 : teen ? 0.25 : 0;
  const v = (i: number) => parseInt(p.seed.slice(i * 2, i * 2 + 2), 16) / 255;
  const build = (p.body_frame === 'male' ? 1 : p.body_frame === 'female' ? -1 : 0) * (1 - youth);
  const refined = p.face_revision === 4;
  const [width, angle, chin, length] = (refined ? classicShapes : shapes)[shape];
  const convergence = refined ? youth * 0.52 : youth;
  const fullness = refined && p.body_build === 'full' ? 3.2 : 0;
  const cheek = mix(width, 68, convergence) + (v(0) - 0.5) * (refined ? 5 : 3) + fullness;
  const jaw = mix(angle + build * 2.4, 45, convergence) + (elder ? refined ? 4 : 1.7 : 0) + fullness,
    chinWidth = mix(chin, 18, convergence);
  const depth = (refined ? length * (1 - youth * 0.31) : mix(length, 58, youth)) + (elder ? 2 : 0);
  const projected = p.nose_revision===2;
  const noseStyle = p.nose_shape || features.nose_shape[Math.floor(v(8) * 2.99)];
  const midface = depth * mix(0.45, refined ? 0.30 : 0.36, youth) + (refined && elder ? 3.4 : 0);
  const nose = midface +
      (noseStyle === 'arched' ? 3.5 : noseStyle==='aquiline'?7:noseStyle==='upturned'?-7:noseStyle==='broad_base'?-1.5:noseStyle === 'rounded' ? -2.5 : 0) * (1 - youth*(projected?.72:1)),
    philtrumAnchor = projected ? midface : nose,
    mouth = philtrumAnchor + (depth - philtrumAnchor) * mix(refined && elder ? .48 : 0.42, 0.45, youth);
  const crown = refined ? mix(-77, -90, youth) + (v(1) - 0.5) * 8 : mix(-87, -101, youth) + (v(1) - 0.5) * 5;
  const temple = cheek * (templeWidths[shape] ?? .92),
    eyeSpacing = refined ? cheek * 0.39 + (v(2) - 0.5) * 6 : mix(26.8 + (v(2) - 0.5) * 4, 26, youth);
  const axis = refined ? -3 - v(3)*13 : -9 - v(3) * 4,
    tip = projected ? axis - headYaw(cheek,axis).sinYaw * noseReliefs[noseStyle].tip * mix(1 + (elder ? .08 : 0), .48, youth) :
      axis - mix(noseStyle === 'arched' ? 10.7 : noseStyle==='aquiline'?13:noseStyle==='upturned'?8.8:noseStyle === 'rounded' ? 5.4 : 7, 3, youth),
    lipX = axis + 2;
  const cx = lipX + 1,
    corner = depth * mix(0.72, 0.68, youth) + (elder ? 1 : 0);
  const earX = temple - 1,
    earY = -5 - youth * 2,
    earH = (projected ? midface : nose) + 4;
  const cheekY = (shape === 'angular' || shape==='diamond' ? 14 : shape==='pear' ? 29 : 21) + youth * 7 + (elder ? 4 : 0);
  const jawY = corner + (elder && refined ? 6 : 0) + (shape === 'broad' ? 1 : shape === 'round' ? -4 : shape==='square'||shape==='oblong'?6:shape==='heart'?-4:0);
  // In a short lower face the adult cheek controls can pass below the angle
  // of the jaw and turn upwards. Keep the child contour tangent at the cheek
  // and descend continuously to the chin without changing the skull or pose.
  const softCheeks = refined && p.cheek_revision===2 && (infant || child);
  const rightCheek = softCheeks
    ? `C${cheek} ${mix(cheekY,depth,.42)} ${jaw*.84} ${mix(cheekY,depth,.77)} ${cx+chinWidth*.43} ${depth-.5}`
    : `C${cheek-1} ${cheekY+13} ${jaw+3+fullness} ${jawY-6} ${jaw} ${jawY}
 C${jaw-5} ${jawY+8} ${cx+chinWidth*.88} ${depth-3} ${cx+chinWidth*.43} ${depth-.5}`;
  const leftCheek = softCheeks
    ? `C${-jaw*.91} ${mix(cheekY,depth,.77)} ${-cheek+1} ${mix(cheekY,depth,.32)} ${-cheek+2} ${cheekY-5}`
    : `C${cx-chinWidth} ${depth-4} ${-jaw-2} ${jawY+6} ${-jaw-5} ${jawY-2}
 Q${-cheek} ${cheekY+12} ${-cheek+2} ${cheekY-5}`;
  const outline = refined ? `M${axis*.22} ${crown}
 C${temple*.6} ${crown-2} ${temple+6} ${crown*.63} ${temple} -15
 C${temple-1} -4 ${cheek+1} 9 ${cheek} ${cheekY}
 ${rightCheek}
 Q${cx+1} ${depth+2} ${cx-chinWidth*.47} ${depth-1}
 ${leftCheek}
 Q${-cheek+4} 1 ${-temple} -12 C${-temple-6} ${crown*.67} ${-temple*.58} ${crown-1} ${axis*.22} ${crown}Z`
    : `M0 ${crown} C${temple * 0.65} ${crown - 2} ${temple + 8} ${crown * 0.66} ${temple} -16
 C${temple - 1} -3 ${cheek + 1} 8 ${cheek} 20 C${cheek - (elder ? -1 : 1)} ${elder ? 42 : 35} ${jaw + (elder ? 7 : 4)} ${corner - 7} ${jaw} ${corner}
 C${jaw - 7} ${corner + 10} ${cx + chinWidth + 9} ${depth - 4} ${cx + chinWidth} ${depth - 1}
 C${cx + chinWidth * 0.55} ${depth + 3} ${cx - chinWidth * 0.35} ${depth + 3} ${cx - chinWidth * 0.8} ${depth - 0.5}
 C${cx - chinWidth - 9} ${depth - 5} ${-jaw - 2} ${corner + 9} ${-jaw - 5} ${corner - 1}
 Q${-cheek - 2} 30 ${-cheek + 1} 13 Q${-cheek + 4} 1 ${-temple - 1} -12
 C${-temple - 7} ${crown * 0.69} ${-temple * 0.6} ${crown - 1} 0 ${crown}Z`;
  return {
    age,
    refined,
    projected, noseStyle,
    infant,
    child,
    teen,
    elder,
    youth,
    build,
    v,
    cheek,
    jaw,
    depth,
    nose,
    mouth,
    crown,
    temple,
    eyeSpacing,
    axis,
    tip,
    lipX,
    cx,
    corner,
    earX,
    earY,
    earH,
    outline,
  };
}
type Head = ReturnType<typeof landmarks>;

function eye(h: Head, p: Paint, x: number, side: number, kind: string) {
  const near = side > 0;
  const w = (near ? 15 : h.refined ? 15 + h.axis*.16 : 12.9) * (1 + h.youth * 0.07) * (h.refined ? (kind === 'hooded' ? 1.14 : kind === 'open' ? 0.92 : 1) : 1),
    open =
      mix(kind === 'open' ? 6.5 : kind === 'hooded' ? 4.4 : 5.5, 7.1, h.youth) *
      (h.elder ? (h.refined ? .73 : .83) : 1) * (h.refined ? 1 + h.youth * .27 : 1);
  const tilt = 0.5 + (h.v(4) - 0.5) * (h.refined ? 6 : 3.5) + (h.refined && kind === 'almond' ? 2.4 : 0);
  const ink = tone(p.skin[2], '#292422', 0.66),
    warm = tone(p.skin[0], '#fff0de', 0.76);
  const lid = h.refined && kind === 'hooded'
    ? `M${-w} 1 C${-w*.55} ${-open*.65} ${w*.23} ${-open*.68} ${w} ${-tilt}`
    : h.refined && kind === 'open'
    ? `M${-w} 1 C${-w*.64} ${-open*1.62} ${w*.46} ${-open*1.68} ${w} ${-tilt}`
    : `M${-w} 1 Q${-w * 0.36} ${-open * 1.36} ${w * 0.34} ${-open} Q${w * 0.8} ${-open * 0.7} ${w} ${-tilt}`;
  const shape = lid + ` Q${w * 0.14} ${open * 1.35} ${-w} 1Z`,
    id = near ? 'near' : 'far';
  const brow = -(open + 5.8 + (h.v(5) - 0.5) * 3) + (h.refined && h.elder ? 2.1 : 0),
    thick = mix(3.3 + h.build * 0.85 + h.v(6) * 1.6, 1.35, h.youth);
  const cx = (h.refined ? -1.8 + (h.v(13) - 0.5) * 1.8 : -1.6) * side;
  const arch = 2.5 + h.v(5) * 4.5;
  const browInk = tone(p.hair[1], p.skin[2], .29 + h.youth*.18);
  const browShape = `M${-w+.2} ${brow+2}
   C${-w+1} ${brow-thick*.55} ${-w*.3} ${brow-arch} ${w*.26} ${brow-arch-.5}
   Q${w*.73} ${brow-arch} ${w+3} ${brow+.4} Q${w*.63} ${brow-arch+2} ${w*.23} ${brow-arch+thick*.72}
   Q${-w*.42} ${brow-.4} ${-w+1} ${brow+2.3}Z`;
  return `<g transform="translate(${x} ${near ? 0 : -1.6}) scale(${side} 1)"><defs><clipPath id="${id}"><path d="${shape}"/></clipPath></defs>
 ${ellipse(0, brow + 4, w + 4, 7, 'url(#socket)')}
 ${path(shape, warm)}<g clip-path="url(#${id})">${ellipse(cx, -1, open * 0.82 + 1, open * 0.93 + 1, ink)}${ellipse(cx, -0.5, open * 0.82, open * 0.91, p.iris)}${ellipse(cx, -0.5, open * 0.43, open * 0.54, '#262421')}${ellipse(cx - 1.8 * side, -2.7, 1.45, 1.35, '#fff4de')}${path(`M${-w} -9H${w}V-1Q0 -4 ${-w} 2Z`, ink, 0.23)}</g>
 ${line(lid, ink, near ? 1.95 : 1.65, 0.96)}${line(`M${w - 1} ${1 - tilt} Q${w * 0.5} ${open * 0.93} 1 ${open * 0.74}`, ink, 1.1, 0.52)}
 ${line(`M${-w + 2} -3Q0 ${-open * 2.1 - 1} ${w - 1} ${-tilt - 3}`, p.skin[2], 1.35, 0.85)}
 ${h.refined ? path(browShape,browInk,.82-h.youth*.32) : path(
   `M${-w + 1} ${brow + 2} C${-w + 0.7} ${brow + 0.5} ${-w + 1.5} ${brow - thick * 0.52} ${-w + 5} ${brow - thick * 0.78}
 C-3 ${brow - thick * 0.85} 1 ${brow - thick - 1.3} 6 ${brow - thick - 1} Q12 ${brow - thick * 0.7} ${w + 4} ${brow + 1}
 Q${w - 1} ${brow - 0.5} 6 ${brow - 0.7} Q1 ${brow - 0.6} -3 ${brow + 0.35} Q${-w + 5} ${brow + 2.9} ${-w + 1} ${brow + 2}Z`,
   tone(p.hair[1], ink, 0.25),
   mix(0.83, 0.4, h.youth),
 )}
 ${line(`M${-w + 1} ${brow + 1.2}l2-2m1 1.6 2.5-2.2m.8 1.5 3-2`, ink, 0.65, 0.35 * (1 - h.youth))}
 ${h.elder || h.age === 'mature_adult' ? line(`M${-w + 4} 8Q1 13 ${w + 1} 5m2-4 5 1m-6 3 4 2`, ink, 1.05, h.elder ? 0.34 : 0.16) : ''}</g>`;
}

// Two sockets on one curved orbital plane. The nose bridge is its centre;
// horizontal yaw foreshortens the far orbit. Roll and mirroring are applied
// once later, to the complete head, so they cannot change binocular alignment.
function headYaw(cheek: number, axis: number) {
  const radius = cheek * .87;
  const sinYaw = -axis / radius;
  return {radius, sinYaw, cosYaw:Math.sqrt(1 - sinYaw * sinYaw)};
}
function orbitalPair(h: Head) {
  const {radius,sinYaw,cosYaw} = headYaw(h.cheek,h.axis);
  const spacing = h.cheek * (.40 + h.youth * .018) + (h.v(2) - .5) * 2.6;
  const depth = Math.sqrt(radius * radius - spacing * spacing);
  const middle = h.axis + (radius - depth) * sinYaw;
  const orbit = (side: 1 | -1) => ({
    side, x: middle + side * spacing * cosYaw,
    widthScale: cosYaw + side * (spacing / depth) * sinYaw,
  });
  return { sinYaw, cosYaw, near: orbit(1), far: orbit(-1), halfWidth: spacing * .52,
    gaze: (h.v(13) - .5) * .20 - sinYaw * .52 };
}

function projectedEye(h: Head, paint: Paint, pair: ReturnType<typeof orbitalPair>,
                      orbit: ReturnType<typeof orbitalPair>['near'], kind: string) {
  const { side, x, widthScale } = orbit;
  const w = pair.halfWidth * (kind === 'hooded' ? 1.045 : kind === 'open' ? .97 : 1);
  const rise = .55 + h.v(4) * 1.35 + (kind === 'almond' ? .65 : kind==='upturned'?3.4:kind==='downturned'?-4.1:0);
  const opening = (kind === 'open' ? .40 : kind === 'hooded' ? .29 : kind==='deep_set'?.30:kind==='downturned'?.365:.33) *
    w * (1 + h.youth * .15) * (h.elder ? .93 : 1);
  // Both canthi and both Bézier arcs are expressed about the same optical
  // centre. The upper lid covers more of the iris on a hooded eye.
  const lid = kind==='upturned' || kind==='downturned'
    ? `M${-w} .8 Q${-w*.44} ${-opening*2.1} ${w*.28} ${-opening} Q${w*.78} ${-opening*.8} ${w} ${-rise}`
    : `M${-w} .8 C${-w*.64} ${-opening*.95} ${-w*.18} ${-opening*1.25} 0 ${-opening*1.19}
    C${w*.42} ${-opening*1.25} ${w*.76} ${-opening*.66} ${w} ${-rise}`;
  const lower = `Q${w*.18} ${opening*1.38} ${-w} .8`;
  const aperture = lid + ' ' + lower + 'Z';
  const id = side === 1 ? 'near-orbit' : 'far-orbit';
  const ink = tone(paint.skin[2], '#292422', .70);
  const radius = w * (.45 + h.youth * .045);
  // Gaze is a single direction in head coordinates. Undo the socket-local
  // reflection/scale for the horizontal displacement and the corneal highlight.
  const pupilX = pair.gaze * radius * side / widthScale;
  const irisX = radius / widthScale;
  const pupilY = -.55;
  const browY = -opening - (kind==='deep_set'?3.2:5.5) - h.v(5) * 1.7 + (h.elder ? 1.2 : 0);
  const thick = mix(3.3 + h.build * .7 + h.v(6) * 1.3, 1.6, h.youth);
  const arch = 2.5 + h.v(5) * 2.9;
  const brow = `M${-w} ${browY+1}
    Q${-w*.32} ${browY-arch} ${w*.25} ${browY-arch}
    Q${w*.67} ${browY-arch} ${w+1} ${browY+.3}
    Q${w*.53} ${browY-2.1} ${w*.23} ${browY-arch+thick*.66}
    Q${-w*.35} ${browY-.8+thick*.52} ${-w} ${browY+1+thick*.72}Z`;
  return `<g transform="translate(${x} 0) scale(${side*widthScale} 1)">
    <defs><clipPath id="${id}"><path d="${aperture}"/></clipPath></defs>
    ${kind==='deep_set'?path(`M${-w-4} 4Q${-w-3} -18 3 -19Q${w+6} -20 ${w+4} -4Q0 -13 ${-w-4} 4Z`,paint.skin[2],.44):''}${ellipse(0,browY+3,w+3,6,'url(#socket)')}${path(aperture,tone(paint.skin[0],'#fff2e4',.79))}
    <g clip-path="url(#${id})">
    ${ellipse(pupilX,pupilY,irisX,radius,ink)}
    ${ellipse(pupilX,pupilY,irisX*.83,radius*.86,paint.iris)}
    ${ellipse(pupilX,pupilY,irisX*.43,radius*.47,'#292725')}
    ${ellipse(pupilX-radius*.25*side/widthScale,pupilY-radius*.34,irisX*.16,radius*.16,'#fff6e9')}</g>
    ${line(lid,ink,1.65,.95)}
    ${line(`M${w} ${-rise} Q${w*.76} ${opening*.59} ${w*.34} ${opening*.6}`,ink,.9,.53)}
    ${line(`M${-w*.8} ${-opening*.65-1.4} Q0 ${-opening*1.94-1.8} ${w*.92} ${-rise-2.4}`,paint.skin[2],1.1,.58)}
    ${path(brow,tone(paint.hair[1],paint.skin[2],.31+h.youth*.15),.82-h.youth*.28)}</g>`;
}

// Measurements in skull space. Relief is distance in front of the facial plane.
// A raised tip exposes the underside; a descending tip covers part of the septum.
type NoseShape = NonNullable<Human['nose_shape']>;
type NoseRelief = { bridge: number; ridge: number; tip: number; bulb: number; ala: number; lift: number };
const noseReliefs: Record<NoseShape, NoseRelief> = {
  straight:   {bridge:4.4, ridge:8,  tip:15, bulb:5.0, ala:10.0, lift:0},
  rounded:    {bridge:4.9, ridge:5,  tip:13, bulb:7.7, ala:11.5, lift:.2},
  arched:     {bridge:4.3, ridge:19, tip:14, bulb:4.7, ala:9.2,  lift:-.7},
  upturned:   {bridge:3.9, ridge:5,  tip:14, bulb:5.3, ala:9.4,  lift:3.2},
  broad_base: {bridge:6.0, ridge:5,  tip:11, bulb:6.4, ala:14.2, lift:.2},
  aquiline:   {bridge:3.9, ridge:17, tip:22, bulb:4.6, ala:9.9,  lift:-4.1},
};

function projectedNose(h: Head, paint: Paint) {
  const type = noseReliefs[h.noseStyle];
  const {sinYaw, cosYaw} = headYaw(h.cheek,h.axis);
  const y = h.nose, youth = h.youth;
  const project = (side: number, depth: number) => h.axis + side*cosYaw - depth*sinYaw;
  const relief = mix(1 + (h.elder ? .08 : 0), .48, youth);
  const ridge = type.ridge*relief, tipDepth = type.tip*relief;
  const width = type.bridge*(1-youth*.26);
  const bulb = mix(type.bulb, 4.4, youth*.52);
  const ala = mix(type.ala, 7.3, youth*.61);
  const lift = mix(type.lift, 1.2, youth*.67);
  const root = project(0,0), mid = project(0,ridge), tip = h.tip;
  const tipY = y-3.7-lift, septumY = y+.7-lift*.43, wingY=y-2.6;
  const wingDepth = tipDepth*.28, far = project(-ala,wingDepth), near = project(ala,wingDepth);
  const start = mix(2,7,youth), midY = mix(start,tipY,.54);
  // The high point of a convex dorsum catches light above the tip. In a
  // turned-up nose the bridge recedes into the glabella and the lobule is lit.
  const prominence = type.ridge/type.tip;
  const bonyWidth = width*(1+Math.max(0,prominence-1)*1.55);
  const crestY = mix(start,tipY,.74-prominence*.32);
  const underside = 1.9+lift*.38 + (h.noseStyle==='rounded' ? 1.25 : 0);
  const shadow = tone(paint.skin[2], '#514044', .12);
  const light = tone(paint.skin[0], '#ffead9', .15);
  const ink = tone(paint.skin[2], '#3d292b', .52);
  // A side wall blends into the near cheek. Its edge ends at the near ala;
  // the ridge itself has no ink outline, even for a convex bridge.
  const sideWall = `M${root+width*.18} ${start}
    C${root+width*.65} ${midY*.8} ${mid+width*.12} ${midY} ${mid+width*.17} ${midY+1}
    Q${tip+width*.24} ${tipY-6} ${tip+bulb*.42} ${tipY+1}
    Q${project(ala*.63,wingDepth)} ${wingY-4.3} ${near} ${wingY}
    Q${near-1} ${wingY-5} ${mid+bonyWidth*1.46} ${midY+3}
    Q${root+width*1.2} ${start+3} ${root+width*.18} ${start}Z`;
  const dorsalLight = `M${root-width*.3} ${start+2}
    Q${mid-bonyWidth*.82} ${midY} ${tip-bulb*.65} ${tipY}
    Q${tip-bulb*.26} ${tipY-2.5} ${tip+bulb*.08} ${tipY-2.9}
    Q${mid+width*.1} ${midY-1} ${root-width*.3} ${start+2}Z`;
  const farBulb = project(-bulb,tipDepth*.8), nearBulb = project(bulb,tipDepth*.8);
  const baseShade = `M${far+.6} ${wingY-.4}
    Q${far+.4} ${wingY+2.2} ${project(-ala*.65,wingDepth)} ${wingY+1.6}
    Q${farBulb-.5} ${tipY+1.1} ${farBulb+.6} ${tipY+.2}
    Q${tip} ${tipY+underside} ${nearBulb-.5} ${tipY-.15}
    Q${nearBulb+1} ${wingY+.8} ${project(ala*.66,wingDepth)} ${wingY+1.5}
    Q${near-1.2} ${wingY+2.3} ${near} ${wingY-.4}
    Q${near+1} ${wingY+3.1} ${project(ala*.62,wingDepth)} ${y+.7}
    Q${tip+bulb*.45} ${y+.25} ${tip} ${septumY+.6}
    Q${tip-bulb*.44} ${septumY+.4} ${project(-ala*.60,wingDepth)} ${y+.6}
    Q${far+.1} ${y+.7} ${far+.6} ${wingY-.4}Z`;
  const nostril = (side: number) => {
    const x = project(side*ala*.615,tipDepth*.47);
    const w = ala*.21*(cosYaw+side*sinYaw*.60);
    const height = (1.04 + lift*.24)*(1-youth*.16);
    // The medial end is lower than the lateral end on both wings.
    return `<g transform="translate(${x} ${y-.32-lift*.14}) scale(${side} 1)">`+
      path(`M${-w} .43Q${-w*.40} ${-height} ${w*.46} ${-height*.87}Q${w} ${-height*.72} ${w} -.32Q${w*.18} .46 ${-w} .43Z`,ink,.76-youth*.13)+'</g>';
  };
  const cheekCreases = h.elder || h.age==='mature_adult'
    ? line(`M${far-1.3} ${wingY+3}Q${far-5} ${y+6} ${h.lipX-16} ${h.mouth-.8}
            M${near+1.7} ${wingY+2}C${near+6} ${y+4} ${h.lipX+21} ${h.mouth-5} ${h.lipX+22} ${h.mouth+3}`,
            shadow, h.elder?1.65:1.05, h.elder?.48:.27) : '';
  const alarCrease = `M${near-1.8} ${wingY-3.3}Q${near+2.0} ${wingY-1} ${near-.3} ${wingY+1.6}`;
  const alaVolume = (x:number, side:number) => {
    const radius = (ala-bulb)*.63+1;
    return ellipse(x-side*radius*.43,wingY+.2,radius*1.17,3.4,'url(#alarShade)')+
      ellipse(x-side*radius*.30-.55,wingY-1.3,radius*.90,2.9,'url(#alarLight)');
  };
  return `<g data-part="nose"><defs>${wash('alarShade',shadow,.54)}${wash('alarLight',light,.57)}
    ${wash('dorsalLight',light,.32+prominence*.14)}${wash('dorsalShade',shadow,.39)}</defs><g filter="url(#glaze)">`+
    path(sideWall,shadow,.53-youth*.16)+path(dorsalLight,light,.39-youth*.05)+'</g>'+
    ellipse(mid-.7,crestY,bonyWidth*(.64+prominence*.40),(tipY-start)*.25,'url(#dorsalLight)')+
    ellipse(mid+bonyWidth*.88,crestY+3.2,bonyWidth*.9,(tipY-start)*(.12+prominence*.12),'url(#dorsalShade)')+
    alaVolume(far,-1)+alaVolume(near,1)+
    ellipse(tip+.8,tipY+1,bulb*1.06,3.9+bulb*.18,'url(#alarShade)')+
    ellipse(tip-.5,tipY-.9,bulb*.90,2.6+bulb*.22,'url(#alarLight)')+
    path(baseShade,shadow,.49-youth*.09)+nostril(-1)+nostril(1)+cheekCreases+
    line(alarCrease,shadow,1.10,.57-youth*.14)+'</g>';
}

function expressions(h: Head, p: Paint, noseStyle: string, lipStyle: string) {
  const { axis, tip, nose: y, mouth: m, lipX: x } = h;
  const wide =
    (h.refined ? (noseStyle === 'rounded' ? 15.5 : noseStyle==='broad_base'?19:noseStyle==='upturned'?9:noseStyle==='aquiline'?8.3:noseStyle === 'arched' ? 7.6 : 10.5) : (noseStyle === 'rounded' ? 11 : noseStyle === 'arched' ? 8.2 : 9.3)) * (1 - h.youth * 0.18);
  const arch = noseStyle === 'arched' ? (h.refined ? 7 : 4) : 0,
    wing = tip + wide + 2;
  const lip = (h.refined ? (lipStyle==='wide'?24:lipStyle==='cupid'?13:lipStyle==='lower_full'?17.5:lipStyle === 'fine' ? 19 : lipStyle === 'full' ? 16 : 17) + (h.v(9) - .5) * 8 : 16 + h.v(9) * 4) * (1 - h.youth * 0.27),
    full = (lipStyle === 'full' ? (h.refined ? 1.65 : 1.35) : lipStyle === 'fine' ? (h.refined ? 0.49 : 0.75) : 1) * (1 + h.youth * 0.04) * (h.refined && h.elder ? .78 : 1);
  const ink = tone(p.skin[2], '#422d30', 0.56),
    red = tone(p.skin[1], h.refined ? '#91494e' : '#934e51', (h.refined ? .56 : .48) - h.build * 0.05 - h.youth * 0.07);
  const smile = h.refined ? (h.v(10) - .46) * 9 - (h.elder ? 2 : 0) : 2 + h.v(10) * 2.8;
  const nose = h.projected ? '' :
    `<g filter="url(#glaze)">` +
    path(
      `M${axis + 1} 0 C${axis + 3} ${y * 0.28} ${tip + 4} ${y * 0.66} ${tip - arch - 1} ${y - 6}
 Q${tip - 3} ${y - 3} ${tip} ${y - 2} Q${tip + 5} ${y} ${tip + 8} ${y - 3}
 Q${wing + 2} ${y - 5} ${wing - 1} ${y - 7} Q${axis + 4} ${y - 6} ${axis + 6} ${y * 0.52} Q${axis + 7} ${y * 0.16} ${axis + 6} -2Z`,
      'url(#nosePlane)',
      0.8,
    ) +
    '</g>' +
    (h.refined ? path(`M${tip-3} ${y-4}Q${tip+1} ${y-8} ${tip+5} ${y-5}
      Q${tip+8} ${y-4} ${wing} ${y-6}Q${wing+3} ${y-3} ${wing} ${y-1}
      Q${tip+6} ${y+2} ${tip+1} ${y+1}Z`,p.skin[2],.31-h.youth*.14) : '') +
    line(
      `M${tip + 0.3} ${y * 0.62} Q${tip + 1 - arch} ${y - 9} ${tip - 3.1} ${y - 6} Q${tip - 5.5} ${y - 3} ${tip - 2.4} ${y - 1}`,
      ink,
      1.25,
      0.51 - h.youth * 0.23,
    ) +
    path(
      `M${tip + 0.4} ${y + 0.3}q1.7-2.3 4.2-1.8l1.3 1q-2.3 1.6-5.5.8Z M${wing - 2} ${y - 2}q2.2-1.5 3.8-.1q-1.8 1.1-3.8.1Z`,
      ink,
      0.72 - h.youth * 0.24,
    ) +
    line(`M${wing + 2} ${y - 7}q3 3.6-.2 5.6`, p.skin[2], 1.2, 0.69) +
    ellipse(tip + 1, y - 5, wide * 0.68, 3.7, 'url(#litSkin)');
  const left = x - lip * 0.86,
    right = x + lip;
  const crease = `M${left} ${m + 1} C${x - 8} ${m + 0.4} ${x - 5} ${m - 0.5} ${x - 1} ${m + 0.4} C${x + 4} ${m + 1.7} ${x + 12} ${m - 0.7} ${right} ${m - smile * 0.52}`;
  const upperFull=lipStyle==='cupid'?1.65:lipStyle==='wide'?.56:lipStyle==='lower_full'?.69:full;
  const lowerFull=lipStyle==='lower_full'?1.68:lipStyle==='cupid'?.88:lipStyle==='wide'?.72:full;
  const lips =
    path(
      `M${left} ${m + 1} C${x - 11} ${m - 0.4} ${x - 6} ${m - 4.8 * upperFull} ${x - 3} ${m - 4.1 * upperFull}
 Q${x - 1} ${m - 3.8 * upperFull} ${x + 1} ${m - 2.6 * upperFull} Q${x + 4} ${m - 4.3 * upperFull} ${x + 6} ${m - 3.9 * upperFull}
 C${x + 10} ${m - 3.5 * upperFull} ${right - 3} ${m - 1.2} ${right} ${m - smile * 0.52} Q${x + 5} ${m + 2} ${x - 1} ${m + 1}Z`,
      red,
      0.88,
    ) +
    path(
      crease +
        ` C${x + 13} ${m + 2.2} ${x + 8} ${m + 6.4 * lowerFull} ${x + 2} ${m + 6 * lowerFull} Q${x - 5} ${m + 6.8 * lowerFull} ${left} ${m + 1}Z`,
      tone(red, p.skin[1], 0.46),
    ) +
    line(crease, ink, 1.15, 0.8) +
    line(`M${x - 3} ${m + 4.3 * upperFull}q4.7 1.1 9-.6`, p.skin[0], 1.5, 0.49) +
    ellipse(x + 2, m + 9 * full, 9, 2.4, 'url(#socket)');
  if (h.projected) return {nose:projectedNose(h,p),lips};
  if (!h.refined) return { nose, lips };
  // Model a bridge, tip and two wings in the same three-quarter projection as the eyes.
  const bulb = (noseStyle === 'rounded' ? 7.4 : noseStyle === 'arched' ? 4.3 : 5.3) * (1-h.youth*.26);
  const far = tip - bulb, near = tip + wide + 1;
  const start = h.youth*11 + 1;
  const bridge = `M${axis+2} ${start} C${axis+3} ${y*.37} ${tip+(noseStyle==='arched'?-3.6:3.8)} ${y*.55} ${far+2} ${y-6}
    Q${far-1} ${y-1} ${tip+1} ${y+.5} Q${tip+5} ${y+1.8} ${near} ${y-1.5}
    Q${near+3} ${y-5} ${near-1} ${y-7} Q${axis+5} ${y-4} ${axis+6} ${y*.53} Q${axis+7} ${y*.24} ${axis+6} ${start}Z`;
  const lower = `M${far+.7} ${y-4} Q${tip-2} ${y-1.5} ${tip+1} ${y-2}
    Q${tip+4} ${y-3.4} ${tip+7} ${y-2.4} Q${near} ${y-6} ${near+1} ${y-3}
    Q${near} ${y-.3} ${tip+7} ${y-.1} Q${tip+2} ${y+2.4} ${far+1} ${y-.7}Z`;
  const inkNose = tone(p.skin[2], ink, .46);
  const plane = path(bridge,'url(#nosePlane)',.73-h.youth*.32);
  if (noseStyle==='upturned' || noseStyle==='broad_base' || noseStyle==='aquiline') {
    const up = noseStyle==='upturned', broad = noseStyle==='broad_base';
    const base = broad
      ? `M${tip-8} ${y-5}q-5 4-2 6q5 1 10-1q8 4 17 0q4-3 2-7q-3 4-8 4q-5-2-9-.5q-4 1-10-1Z`
      : up ? `M${tip-5} ${y-4}q4-3 9-1q6 2 10-1q-2 5-8 6q-7 2-11-4Z` : lower;
    const nostrils = broad ? `M${tip-8} ${y}q2-2 5-.7m14 1q2-3 5-2` :
      up ? `M${tip-1} ${y-.3}q1.7-3 3.8-.8m3-.5q1.8-2.9 4-.8` :
      `M${tip} ${y+.3}q2-2 4-.6m3-1q2-2 4-1`;
    const ridge = noseStyle==='aquiline' ? line(`M${axis} ${start+5}Q${axis+1} ${y*.35} ${tip-2} ${y*.64}Q${tip-6} ${y*.82} ${tip-3} ${y-3}`,p.skin[2],1.7,.51-h.youth*.2) : '';
    return {nose:plane+ridge+ellipse(tip+1,y-(up?6:5),broad?7:bulb,3.7,'url(#litSkin)')+
      path(base,p.skin[2],.46)+line(nostrils,inkNose,1.45,.78-h.youth*.23),lips};
  }
  const modeledNose = plane +
    ellipse(tip+1,y-5,bulb,4,'url(#litSkin)') + path(lower,p.skin[2],.53) +
    line(`M${tip+1} ${y-.9}q1.8-1.7 3.6-.5m${wide*.42} -1q2-2.2 4.4-1`,inkNose,1.35,.75-h.youth*.25) +
    line(`M${axis+.5} ${y*.4}Q${tip+(noseStyle==='arched'?-2:2)} ${y*.75} ${far+1} ${y-5.8}`,p.skin[2],1.15,h.youth>.5?.17:.47);
  return {nose:modeledNose,lips};
}

function whiskers(h: Head, style: Human['facial_hair'], p: Paint) {
  if (style === 'clean_shaven' || h.infant || h.child || h.teen) return '';
  const { lipX: x, mouth: y, depth: d, cheek: c, jaw: j, earY, earX, corner, cx } = h;
  const moustache = `M${x - 19} ${y + 1.8} C${x - 17} ${y - 2.8} ${x - 14} ${y - 6.2} ${x - 9} ${y - 7.1}
 Q${x - 4} ${y - 9} ${x} ${y - 6.7} Q${x + 6} ${y - 10} ${x + 12} ${y - 7.7}
 C${x + 17} ${y - 6.7} ${x + 19} ${y - 4.2} ${x + 23} ${y + 0.5} Q${x + 18} ${y - 1} ${x + 14} ${y - 1.5}
 Q${x + 8} ${y - 2.3} ${x + 4} ${y - 4} Q${x + 0.8} ${y - 5.3} ${x - 0.6} ${y - 5.2}
 Q${x - 4} ${y - 3} ${x - 9} ${y - 2.2} Q${x - 13} ${y - 2} ${x - 19} ${y + 1.8}Z`;
  const partedMustache = `M${x-1} ${y-7}C${x-9} ${y-10} ${x-15} ${y-6} ${x-21} ${y+1}Q${x-12} ${y-3} ${x-5} ${y-3}Q${x-3} ${y-4} ${x-1} ${y-7}Z M${x+1} ${y-7}Q${x+9} ${y-11} ${x+16} ${y-6}Q${x+20} ${y-2} ${x+24} ${y+1}Q${x+18} ${y} ${x+11} ${y-3}Q${x+5} ${y-4} ${x+1} ${y-7}Z`;
  const must =
    path(h.refined ? partedMustache : moustache, 'url(#beardMass)', 0.93) +
    line(`M${x - 5} ${y - 6}q-5 .7-9 4m22-4.3q5 1 9 3.4`, p.hair[0], 0.95, 0.65);
  if (style === 'mustache') return must;
  if (style === 'goatee') {
    const tuft = `M${x-9} ${y+7} Q${x} ${y+11} ${x+10} ${y+6}
      Q${x+11} ${d-10} ${cx+18} ${d-8} Q${cx+13} ${d+3} ${cx} ${d+5}
      Q${cx-13} ${d+1} ${cx-17} ${d-8} Q${x-9} ${d-12} ${x-9} ${y+7}Z`;
    return must + path(tuft, 'url(#beardMass)', .93) + line(`M${cx-8} ${d-9}q2 6 4 8m6-10q3 5 1 10m5-9-2 6`, p.hair[0], 1, .55);
  }
  if (style === 'sideburns') {
    const sides = `M${-c+3} 1 Q${-c+6} 17 ${-j-6} ${corner-8} Q${-j+1} ${corner-6} ${-j+5} ${corner-10}
      Q${-c+15} 23 ${-c+9} 0 Z M${earX-6} -2 Q${c-10} 23 ${j-8} ${corner-11}
      Q${j-4} ${corner-5} ${j+5} ${corner-7} Q${c+1} 22 ${earX+1} 1Z`;
    return `<g clip-path="url(#headShape)">${path(sides,'url(#beardMass)',.91)}</g>`;
  }
  const stubble = style === 'stubble',
    full = style === 'full_beard';
  const fall = full ? (h.refined ? 6 + h.v(13)*11 : 12 + h.v(13) * 8) : stubble ? 0 : 2;
  // Follow the cheek and mandible all the way around. Leave clearance for the lower lip.
  const cheekBoundary = `M${-c + 3} 8 C${-c + 7} 18 ${-j - 5} ${y - 11} ${x - 18} ${y - 2}
 Q${x - 17} ${y + 3} ${x - 11} ${y + 5} Q${x - 7} ${y + 9} ${x - 3} ${y + 7} Q${x + 2} ${y + 5} ${x + 5} ${y + 7}
 Q${x + 13} ${y + 9} ${x + 18} ${y + 1} Q${x + 20} ${y + 1} ${x + 18} ${y - 4}
 C${x + 33} ${y - 13} ${earX - 10} 23 ${earX - 6} ${earY + 8}
 Q${earX - 5} ${earY + 4} ${earX - 1} ${earY + 6}`;
  const edge = cheekBoundary + `L${c - 1} 24
 Q${c - 2} 44 ${j + 1} ${corner + 3 + fall * 0.2}
 C${j - 8} ${corner + 16 + fall * 0.45} ${cx + 19} ${d + fall} ${cx + 8} ${d + fall + 1}
 Q${cx - 7} ${d + fall + 4} ${cx - 19} ${d + fall - 2}
 Q${-j - 8} ${corner + 8 + fall * 0.38} ${-j - 10} ${corner - 1}
 Q${-c - 2} 27 ${-c + 3} 8Z`;
  let seed = Math.round(h.v(15) * 65535) + 17;
  const random = () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  };
  let strokes = '',
    glints = '';
  const count = h.refined ? (stubble ? 365 : full ? 490 : 320) : (stubble ? 400 : full ? 740 : 550);
  for (let i = 0; i < count; i++) {
    const px = Math.round((random() * 2 - 1) * c),
      py = Math.round(7 + random() * (d + fall - 4));
    // Short follicles along the cheeks grow inwards. Longer locks fall around the chin.
    const chin = Math.max(0, (py - y) / (d + fall - y));
    const dx = ((cx - px) / (stubble ? 65 : 27) * (h.refined ? 1.55 - chin : 1)).toFixed(1),
      dy = ((stubble ? 0.85 + random() * 0.85 : 1.6 + random() * (full ? 5.5 : 3.1)) * (h.refined ? .7 + chin : 1)).toFixed(1);
    const mark = `M${px} ${py}q${dx} ${(Number(dy) * 0.54).toFixed(1)} ${dx} ${dy}`;
    if (i % 4 === 0) glints += mark;
    else strokes += mark;
  }
  return (
    `<defs><clipPath id="growth"><path d="${edge}"/></clipPath>
 <linearGradient id="density" gradientUnits="userSpaceOnUse" x1="0" y1="${earY + 5}" x2="0" y2="${d}">
 <stop stop-color="white" stop-opacity=".32"/><stop offset=".54" stop-color="white" stop-opacity=".70"/><stop offset=".88" stop-color="white"/></linearGradient>
 <mask id="whiskerFade"><path d="${edge}" fill="url(#density)"/><g filter="url(#glaze)">${line(cheekBoundary,'#131313',full ? 6 : 9, .83)}</g></mask></defs><g${stubble ? ' clip-path="url(#headShape)"' : ''}><g mask="url(#whiskerFade)">` +
    `<g clip-path="url(#growth)">` +
    path(edge, 'url(#beardMass)', stubble ? (h.refined ? .16 : .085) : h.refined && !full ? .72 : .93) +
    ellipse(-j + 8, corner - 3, 25, 30, 'url(#beardGlaze)') +
    ellipse(cx + 9, d + fall - 3, 24, 14, 'url(#beardGlaze)') +
    '</g>' +
    `<g clip-path="url(#growth)">${path(`M${-c} 21Q${-j} ${y + 10} ${cx} ${d + 8} Q${-j - 3} ${d} ${-c} ${corner}Z`, p.hair[0], stubble ? 0.05 : 0.25)}${line(strokes, stubble ? p.hair[1] : p.hair[0], stubble ? 0.94 : 1.1, stubble ? (h.refined ? .53 : .25) : .47)}${line(glints, stubble ? p.hair[1] : tone(p.hair[0], p.skin[0], 0.32), 1, stubble ? 0.18 : 0.54)}</g>` +
    '</g></g>' +
    (stubble ? path(moustache, p.hair[1], 0.09) : must)
  );
}

function faceMarks(h: Head, kind: Human['face_detail'], paint: Paint, near: number, far: number) {
  if (!kind || kind==='none') return '';
  const ink=tone(paint.skin[2], '#714336', .55);
  if(kind==='beauty_mark') return ellipse(near+7,h.mouth-6,1.9,1.55,ink);
  if(kind==='dimples') return line(`M${h.lipX-22} ${h.mouth-3}q-3 3-1 6 M${h.lipX+24} ${h.mouth-2}q2 3-2 7`,ink,1.5,.47);
  if(kind==='brow_scar'||kind==='cheek_scar'){
    const x=near+(kind==='brow_scar'?7:12), y=kind==='brow_scar'?-22:14;
    const scar=`M${x} ${y}q-4 5-4 9l-4 6`;
    return line(scar,ink,2.3,.55)+`<g transform="translate(.9 .3)">${line(scar,paint.skin[0],1.4,.79)}</g>`;
  }
  let marks='';
  // Scatter a band across both malar planes; the bridge has fewer, smaller spots.
  let state=Math.round(h.v(0)*65535+h.v(11)*255)+11;
  const jitter=()=>{state=(Math.imul(state,1664525)+1013904223)>>>0;return state/4294967296};
  for(let i=0;i<42;i++){
    const side=i%2===0?1:-1, offset=(jitter()+jitter()-1)*20;
    const x=(side===1?near:far)+side*(5+offset), y=11+jitter()*11+Math.abs(offset)*.15;
    const radius=.45+jitter()*.88;
    marks+=ellipse(x,y,radius,radius*.79,ink);
  }
  for(let i=0;i<7;i++)marks+=ellipse(h.axis+(jitter()-.5)*18,11+jitter()*6,.63,.53,ink);
  return `<g opacity=".60">${marks}</g>`;
}

function spectacles(h: Head, kind: Human['eyewear'], near:number, far:number, paint:Paint) {
  if (!kind || kind==='none') return '';
  const pair=orbitalPair(h);const r=pair.halfWidth+4;
  const frame=kind==='round_wire'?'#645847':tone(paint.hair[1],'#282c35',.67);
  const weight=kind==='round_wire'?1.65:2.8;
  const lens=kind==='round_wire'
    ? `M${-r} 0C${-r} ${-r*1.08} ${r} ${-r*1.08} ${r} 0C${r} ${r*1.13} ${-r} ${r*1.13} ${-r} 0Z`
    :kind==='cat_eye'?`M${-r} -3Q-5 -9 ${r+3} -13Q${r-1} 8 4 9Q${-r*.7} 14 ${-r} -3Z`
    :`M${-r} -8Q0 -11 ${r} -8L${r-1} 5Q${r-2} 11 0 10Q${-r+1} 10 ${-r+1} 4Z`;
  const front=(x:number,scale:number)=>`<g transform="translate(${x} 0) scale(${scale} 1)">${path(lens,'#dfeccf',.07)}${line(lens,frame,weight,.97)}</g>`;
  const outer=kind==='cat_eye'?-11:-4;
  return line(`M${far-r*pair.far.widthScale} ${outer}L${-h.temple+1} -7 M${near+r*pair.near.widthScale} ${outer}L${h.earX+3} -5`,frame,weight,.89)+
    line(`M${far+r*pair.far.widthScale} -3Q${(far+near)/2} -9 ${near-r*pair.near.widthScale} -3`,frame,weight)+
    front(far,-pair.far.widthScale)+front(near,pair.near.widthScale);
}

function renderHead(p: Human, h: Head, paint: Paint, hairstyle: HairStyle) {
  const { skin, hair } = paint,
    { cheek: c, temple: t, axis: a, nose: n, mouth: m, lipX: x, depth: d, earX, earY, earH } = h;
  const ink = tone(skin[2], '#4b3338', 0.61);
  const styleEye = p.eye_shape || features.eye_shape[Math.floor(h.v(7) * 2.99)];
  const styleLip = p.lip_shape || features.lip_shape[Math.floor(h.v(11) * 2.99)];
  const locks = figureHair(
    hairstyle,
    t,
    h.crown,
    tone(hair[0], '#f4d3a5', 0.32),
    tone(hair[1], '#201a21', 0.38),
    h.refined ? { infant: h.infant, part: h.v(6) } : undefined,
  );
  const orbits = p.eye_revision === 2 ? orbitalPair(h) : undefined;
  const nearEye = orbits?.near.x ?? (a + h.eyeSpacing + 3),
    farEye = orbits?.far.x ?? (a - h.eyeSpacing * 0.87);
  const ears = (near: boolean) => {
    const size = (near ? 1 : 0.67) * (h.elder ? 1.06 : 1);
    const px = near ? earX : -t + 1,
      py = earY + (near ? 1 : 0);
    const height = earH * (near ? 1 : 0.87);
    return (
      `<g transform="translate(${px} ${py}) scale(${near ? size : -size} 1)">` +
      path(
        `M-6 5 C-3-1 4-6 11-3 Q19-1 17 10 Q15 ${height * 0.5} 9 ${height * 0.77} Q7 ${height + 1} 1 ${height} Q-5 ${height} -6 ${height - 9}Z`,
        near ? 'url(#earPaint)' : skin[2],
      ) +
      line(`M0 6Q5-2 11 1Q16 5 11 15`, skin[0], 2, 0.84) +
      path(`M1 12Q8 5 10 9Q12 13 7 17Q4 21 5 25Q-2 24 0 19Q5 16 1 12Z`, skin[2], 0.86) +
      line('M4 10q8-4 6 4m-4 10q-1 4-4 5', ink, 1.25, 0.54) +
      '</g>'
    );
  };
  const structure =
    path(h.outline, 'url(#skin)') +
    `<g clip-path="url(#headShape)">` +
    path(
      `M${t - 8} ${h.crown * 0.71} Q${c - 18} -31 ${c - 16} -11 Q${c - 17} 3 ${c - 26} 11 Q${c - 32} 15 ${c - 30} 21 Q${c - 17} 32 ${c - 23} 43 Q${h.jaw - 10} ${h.corner + 6} ${h.cx + 5} ${d + 3} L${c + 6} ${d + 8}V${h.crown}Z`,
      'url(#sidePlane)',
      h.refined ? .55 : .9,
    ) +
    ellipse(a - 17, -32, 43, 39, 'url(#litSkin)') +
    ellipse(nearEye + 10, 21, 24, 19, 'url(#litSkin)') +
    ellipse(nearEye + 12, 26, 28, 18, 'url(#warmSkin)') +
    ellipse(farEye - 7, 20, 14, 15, 'url(#warmSkin)') +
    ellipse(x + 2, d - 12, 24, 12, 'url(#litSkin)') +
    ellipse(nearEye + 13, 30, 25, 10, 'url(#malar)') +
    ellipse(farEye - 5, 22, 13, 8, 'url(#malar)') +
    ellipse(nearEye - 8, 1, 20, 16, 'url(#socket)') +
    ellipse(farEye + 5, -1, 14, 13, 'url(#socket)') +
    (h.projected ? '' : ellipse(a + 6, 11, 7, 21, 'url(#socket)') + ellipse(h.tip + 7, n + 2, 9, 4, 'url(#socket)')) +
    ellipse(x + 3, m + 9, 15, 4, 'url(#socket)') +
    path(
      `M${nearEye - 15} -9 Q${nearEye + 6} -23 ${nearEye + 23} -11 Q${nearEye + 22} -3 ${nearEye + 17} 1 Q${nearEye + 8} -7 ${nearEye - 15} -3Z`,
      skin[2],
      0.19,
    ) +
    (orbits
      ? projectedEye(h, paint, orbits, orbits.far, styleEye) + projectedEye(h, paint, orbits, orbits.near, styleEye)
      : eye(h, paint, farEye, -1, styleEye) + eye(h, paint, nearEye, 1, styleEye));
  const { nose, lips } = expressions(h, paint, h.noseStyle, styleLip);
  const folds =
    h.elder || h.age === 'mature_adult'
      ? line(
          h.projected ? `M${nearEye - 9} 10q12 7 25-1` : `M${h.tip - 5} ${n + 4} Q${x - 21} ${m - 5} ${x - 18} ${m + 5} M${h.tip + 20} ${n + 1}Q${x + 24} ${m - 7} ${x + 25} ${m + 5} M${nearEye - 9} 10q12 7 25-1`,
          ink,
          1.12,
          h.elder ? 0.37 : 0.14,
        )
      : '';
  const ageVolume = h.elder
    ? ellipse(nearEye + 4, 11, 18, 5, 'url(#socket)') +
      ellipse(farEye, 10, 13, 4, 'url(#socket)') +
      (h.projected ? '' : path(
        `M${h.tip + 15} ${n}Q${x + 28} ${m - 8} ${x + 24} ${m + 8} Q${x + 30} ${m + 1} ${x + 32} ${m - 7}Q${x + 25} ${n + 4} ${h.tip + 15} ${n}Z`,
        skin[2],
        0.23,
      ))
    : '';
  const lowerLid = (eyeX:number, span:number) =>
    path(`M${eyeX-span} 5q${span} 7 ${span*2} -.8q${-span*.65} 13 ${-span*1.42} 9.6q${-span*.57} -1.4 ${-span*.58} -8.8Z`,skin[2],.37) +
    line(`M${eyeX-span*.67} 12q${span*.69} 6 ${span*1.55} -2`,skin[0],1.55,.58);
  const cheekFold = h.refined && h.elder
    ? lowerLid(nearEye,16)+lowerLid(farEye,12) +
      path(`M${t-5} -51Q${c-9} -20 ${nearEye+15} -14Q${nearEye+26} -36 ${t-5} -51Z`,skin[2],.21) +
      (h.projected ? '' : path(`M${h.tip+12} ${n+1}Q${x+22} ${n+2} ${x+25} ${m+9}Q${x+27} ${m-6} ${x+19} ${n+1}Z`,skin[2],.47)) +
      path(`M${c-3} 16Q${c-12} 28 ${x+28} ${m-8}Q${x+21} ${m-1} ${x+21} ${m+10} Q${x+31} ${m+9} ${h.jaw+3} ${h.corner+2}Q${c} 40 ${c-3} 16Z`,skin[2],.23)
      + line(`M${nearEye-10} 10q15 9 27-2m-4-1 7-1m-8 4 5 1 M${farEye-9} 6q8 8 17 4 M${x-14} ${m+3}q-3 5-2 9m33-11q4 3 4 7`,ink,1.2,.4)
    : '';
  const forehead = h.elder
    ? line(`M${a - 20} -38q18-4 39-1m-35 6q14-2 25 0M${a - 1} -20l-1 6`, ink, 1.25, 0.26)
    : '';
  const earJewels = [2, 3].includes(p.accessory)
    ? ellipse(earX + 3, earY + earH - 2, 2.7, 3, '#d9b879') +
      (p.accessory === 3 ? line(`M${earX + 3} ${earY + earH}l.4 9`, '#dec892', 1.7) : '')
    : '';
  return {
    back: locks.back,
    head:
      ears(false) +
      ears(true) +
      structure +
      ageVolume +
      cheekFold +
      nose +
      faceMarks(h,p.face_detail,paint,nearEye,farEye) +
      folds +
      forehead +
      lips +
      '</g>' +
      whiskers(h, p.facial_hair, paint) +
      spectacles(h,p.eyewear,nearEye,farEye,paint) +
      locks.front +
      earJewels,
  };
}

export function portraitFigure(
  p: Human,
  shape: Face,
  hairstyle: HairStyle,
  garment: keyof Styles['clothing'],
  paint: Paint,
) {
  const h = landmarks(p, shape),
    { skin, hair, cloth, bg } = paint;
  const head = renderHead(p, h, paint, hairstyle);
  const scale = h.refined ? mix(1.16, 1.26, h.youth) : mix(1.2, 1.26, h.youth);
  const headX = 198,
    eyeY = (h.refined ? 281 + h.youth * 16 + (h.elder ? 8 : 0) : 303) - h.depth * scale;
  const turn = h.v(14) > 0.5 ? -1 : 1,
    tilt = (h.v(12) - 0.5) * 4.8;
  const pose = `translate(${headX} ${eyeY}) scale(${turn * scale} ${scale}) rotate(${tilt} 0 ${h.depth * 0.72})`;
  const skinInk = tone(skin[2], '#483431', 0.4);
  const defs =
    grad(
      'backdrop',
      [tone(bg[0], '#edddc6', 0.31), tone(bg[1], '#374645', 0.22)],
      '100%',
      '70%',
      turn < 0,
    ) +
    wash('window', '#ffebc1', 0.42) +
    grad('skin', [
      tone(skin[0], '#ffe0be', 0.1),
      tone(skin[0], skin[1], 0.48),
      skin[1],
      tone(skin[2], skin[1], 0.25),
    ]) +
    grad('neck', [skin[1], skin[2], tone(skin[1], skin[0], 0.4)], '55%', '100%', turn < 0) +
    grad('earPaint', [skin[1], tone(skin[1], '#b96759', 0.3), skin[0]]) +
    grad('sidePlane', [tone(skin[2], skin[1], 0.45), skin[2]]) +
    grad('nosePlane', [tone(skin[0], skin[1], 0.22), h.refined ? tone(skin[2],skin[1],h.youth*.5) : skin[2]], '85%', '65%') +
    grad('hairMass', [tone(hair[0], hair[1], 0.4), hair[0], hair[1], tone(hair[1], '#201d22', 0.21)]) +
    grad('beardMass', [
      tone(hair[0], skin[2], 0.4),
      tone(hair[1], skin[2], 0.46),
      tone(hair[1], skinInk, 0.3),
    ]) +
    grad('cloth', [tone(cloth[0], '#e4ccb2', 0.12), cloth[0], cloth[1]], '100%', '65%', turn < 0) +
    wash('beardGlaze', tone(hair[0], skin[0], 0.32), p.facial_hair === 'stubble' ? 0.06 : 0.4) +
    wash('socket', skinInk, 0.27) +
    wash('malar', skin[2], 0.11) +
    wash('litSkin', skin[0], 0.74) +
    wash('warmSkin', tone(skin[1], '#c06d5d', 0.72), h.refined ? .43 : .36) +
    `<filter id="glaze" x="-25%" y="-15%" width="150%" height="135%"><feGaussianBlur stdDeviation="1.5"/></filter><clipPath id="headShape"><path d="${h.outline}"/></clipPath>`;
  // Both mastoids sit inside the head. The short visible neck widens toward the
  // clavicles; the garment is sized separately and cannot compress the neck again.
  const neck = h.refined ? (23 + h.jaw * .09 + (p.body_build === 'full' ? 5 : p.body_build === 'slender' ? -4 : p.body_build==='athletic'?3:p.body_build==='stocky'?6.5:0)) * (1 - h.youth * .31) : 27 + h.build * 4 - h.youth * 4,
    center = headX + turn * 5;
  const bodyScale = h.infant ? 0.69 : h.child ? 0.86 : h.teen ? 0.95 : 1,
    collarY = h.refined ? (h.infant ? -14 : h.child ? -11 : h.elder ? -9 : -6) : h.infant ? -7 : h.child ? -5 : -2;
  const torso = h.infant || h.child ? 'neutral' : p.body_frame;
  const shoulders = bodyScale * (torso === 'male' ? 1.12 : torso === 'female' ? 0.89 : 1);
  const neckLine = `M${center - neck} 253 Q${center - neck + 3} 287 ${center - neck - 2} 304 Q${200 - 29 * shoulders} 316 ${200 - 35 * shoulders} 323 L${200 - 63 * shoulders} 342 L${200 - 54 * shoulders} 376H${200 + 54 * shoulders}L${200 + 63 * shoulders} 342 L${200 + 35 * shoulders} 323 Q${200 + 29 * shoulders} 316 ${center + neck} 305 Q${center + neck - 3} 288 ${center + neck + 3} 250Z`;
  const body = h.refined
    ? garmentLayer(garment, torso, false, null, { build: p.body_build || 'average', youth: h.youth, collarY, turn },paint.accent)
    : `<g transform="translate(200 ${317 + collarY}) skewX(${2.8 * turn}) scale(${bodyScale} 1) translate(-200 -317)">${garmentLayer(garment, torso, false, null, undefined, paint.accent)}</g>`;
  const chain = [1, 2, 5, 7].includes(p.accessory)
    ? line('M172 310Q195 357 225 311', '#b29769', 1.6, 0.92) +
      (p.accessory === 1 ? '' : ellipse(199, 337, 3, 5, '#d7b476'))
    : '';
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 500" width="400" height="500"><title>Иллюстрация персонажа</title><defs>${defs}<clipPath id="nape"><path d="${neckLine}"/></clipPath></defs>
 <rect width="400" height="500" fill="url(#backdrop)"/>${ellipse(turn < 0 ? 324 : 76, 124, 290, 300, 'url(#window)')}
 ${path('M0 405Q161 291 400 255V500H0Z', '#243b3a', 0.07)}
 <g transform="translate(-18 -27) scale(1.09)"><g transform="${pose}">${head.back}</g>
 ${path(neckLine, 'url(#neck)')}<g clip-path="url(#nape)"><g transform="${pose}"><g transform="translate(2 7)">${path(h.outline, skinInk, 0.41)}</g></g></g>
 ${body}${chain}<g transform="${pose}">${head.head}</g></g></svg>`;
}
