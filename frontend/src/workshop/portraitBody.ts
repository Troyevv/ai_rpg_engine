// A bust ends at the upper chest. All coordinates below refer to the nape,
// neckline, clavicles and shoulder line, independent of the legacy full figure.
import type {BodyFrame} from './portraitAnatomy';
import type catalog from '../../../shared/portrait-catalog.json';
import {garmentTrim, shape, seam} from './portraitWardrobe';

type Build = keyof typeof catalog.features.body_build;
type Garment = keyof typeof catalog.styles.clothing;
interface Pose {
  frame: BodyFrame; build: Build; youth: number; elderly: boolean;
  chinY: number; halfHead: number; center: number; turn: number;
}

// Each neckline starts at the left collar and ends at its right counterpart.
// The shape includes the rise of a standing collar or the inner edge of a hood.
function opening(x:number, y:number, front:string) { return {x,y,front} }
const crew=opening(171,319,'Q200 346 229 319');
const point=opening(170,315,'L200 340 230 315');
const stand=opening(166,321,'L172 301 Q200 315 228 301 L234 321');
const wrap=opening(163,319,'L166 309 L200 335 L234 309 L237 319');
const cuts:Record<Garment,typeof crew>={
  plain:crew, tshirt:crew, shirt:point, blazer:point,
  jacket:opening(152,322,'L163 301 L200 347 L237 301 L248 322'),
  cardigan:crew, jumper:opening(163,321,'L200 351 L237 321'),
  sweater:opening(167,325,'L172 297 Q200 305 228 297 L233 325'),
  blouse:opening(166,319,'Q200 357 234 319'),
  hoodie:opening(153,322,'Q151 294 175 290 Q182 313 200 324 Q218 312 225 290 Q250 295 247 322'),
  vest:point, dress:opening(153,329,'Q167 352 200 364 Q233 352 247 329'),
  coveralls:point, smock:crew, cloak:opening(169,309,'Q198 333 231 309'),
  romper:crew, wrap_blanket:opening(161,314,'Q197 339 239 314'),
  polo:point, bomber:opening(160,323,'L168 308 Q200 329 232 308 L240 323'),
  parka:opening(142,323,'Q145 302 158 296 Q167 320 198 341 Q232 320 242 295 Q255 301 258 323'),
  trench:opening(152,322,'L166 300 L197 332 L234 301 L248 322'),
  track_jacket:stand, sailor:opening(157,320,'L200 349 L243 320'),
  chef:stand, work_apron:crew, doublet:stand, surcoat:crew, kimono:wrap,
  mantle:opening(166,308,'Q198 337 234 308'), lamellar:stand,
  flight_suit:opening(141,321,'L151 303 Q162 291 175 295 Q200 310 225 295 Q242 291 249 303 L259 321'),
  tech_shell:opening(157,320,'L166 298 L190 307 L201 319 L230 296 L243 320'),
};

// Half breadth at the shoulder, slope, neck half width and depth of upper chest.
const frames:Record<Build,readonly [number,number,number,number]>={
  slender:[106,30,23,21], average:[121,25,28,24], broad:[139,22,31,30],
  full:[130,34,34,36], athletic:[138,17,32,28], stocky:[124,20,36,35],
};
const padded=new Set<Garment>(['bomber','parka','lamellar','flight_suit','tech_shell','hoodie']);
const tailored=new Set<Garment>(['blazer','shirt','trench','jacket','doublet','chef']);
const draped=new Set<Garment>(['cloak','mantle','wrap_blanket','kimono']);

export function portraitBust(pose:Pose, garment:Garment, accent?:string) {
  const {youth,center,chinY,turn}=pose;
  const [breadth,slope,halfNeck,volume]=frames[pose.build];
  const adult=1-youth;
  const frame=pose.frame==='male'?1:pose.frame==='female'?-1:0;
  const ease=padded.has(garment)?8:tailored.has(garment)?3:draped.has(garment)?6:0;
  const span=(breadth+frame*5)*adult+91*youth+ease;
  const drop=(slope-frame*2)*adult+30*youth+(pose.elderly?4:0)-ease*.35;
  const neck=(halfNeck+frame*2)*adult+21*youth;
  const collarWidth=(neck+7)/35;
  const shoulder=span/collarWidth;
  const collarFit=`translate(200 0) scale(${collarWidth} 1) translate(-200 0)`;
  const root=chinY+23*adult+10*youth-(pose.elderly?3:0);
  const unitX=.80+.20*pose.halfHead/78;
  const unitY=1-.12*youth;
  const transform=`translate(${center} ${root}) skewY(${turn*1.1}) scale(${unitX} ${unitY}) translate(-200 -319)`;
  const underJaw=319-(root-chinY+24)/unitY;
  const neckPath=`M${200-neck-2} ${underJaw}
    C${200-neck+2} 298 ${200-neck+2} 308 ${200-neck-4} 316
    C${200-neck-9} 327 ${200-neck-21} 331 139 342
    L145 378 Q200 391 255 378 L261 342
    C${200+neck+21} 331 ${200+neck+9} 327 ${200+neck+4} 316
    C${200+neck-2} 308 ${200+neck-2} 298 ${200+neck+2} ${underJaw}Z`;
  const skin=shape(neckPath,'url(#neck)')+
    seam('M165 333Q184 332 195 340 M205 340Q217 332 236 333','#79594e',1.6,.18);
  const collar=cuts[garment], crest=319+drop;
  // Follow the trapezius out to each acromion, then round into the chest
  // boundary. There are no arm, sleeve tube, waist or hip outlines.
  const surface=`M${collar.x} ${collar.y} ${collar.front}
    C${400-collar.x+14} ${collar.y+11} ${200+shoulder-28} ${crest-7} ${200+shoulder-6} ${crest}
    C${200+shoulder+13} ${crest+6} ${200+shoulder+volume} ${crest+23} ${200+shoulder+volume+16} 500
    H${200-shoulder-volume-16}
    C${200-shoulder-volume} ${crest+23} ${200-shoulder-13} ${crest+6} ${206-shoulder} ${crest}
    C${228-shoulder} ${crest-7} ${collar.x-14} ${collar.y+11} ${collar.x} ${collar.y}Z`;
  const dye=accent||'#f2debf';
  const lining=garment==='blazer'?shape('M169 312Q199 338 231 312L241 329 200 408 159 329Z',dye):'';
  const hood=garment==='parka'?shape('M142 323Q129 293 151 277Q196 246 242 276Q269 293 258 324L243 327Q242 284 201 281Q156 282 158 327Z','url(#cloth)'):'';
  const folds=draped.has(garment)?''
    : seam(`M${202-shoulder} ${crest+5}q15 7 21 23 M${198+shoulder} ${crest+4}q-13 8 -18 24`, '#443d40',1.6,.26);
  return {transform, neckPath, neck:(hood?`<g transform="${collarFit}">${hood}</g>`:'')+skin, cloth:
    `<g transform="${collarFit}"><defs><clipPath id="bustCloth"><path d="${surface}"/></clipPath></defs>`+
    shape(surface,'url(#cloth)')+`<g clip-path="url(#bustCloth)">${folds}${lining}${garmentTrim(garment,accent,true)}</g></g>`};
}
