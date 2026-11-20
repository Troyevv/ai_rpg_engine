// Trusted vector layers from the approved #175 artwork. Version 1 is immutable.
// Never accept SVG, paths, colors or markup from the server/user.
import catalog from '../../../shared/portrait-catalog.json';
import {portraitFigure,type FeatureChoices} from './portraitFigure';
import {portraitFace} from './portraitFace';
import {coiffure,garmentLayer} from './portraitWardrobe';
export type Styles = typeof catalog.styles;
export type Layers = FeatureChoices & {face_revision?:2|3|4;eye_revision?:2;cheek_revision?:2;nose_revision?:2;body_revision?:2|3;accent_color?:number;eyewear?:keyof typeof catalog.features.eyewear;face_detail?:keyof typeof catalog.features.face_detail;body_build?:keyof typeof catalog.features.body_build;base_version?:1|2; hairstyle?:keyof Styles['hair']|null; garment?:keyof Styles['clothing']|null; visage?:keyof Styles['face']|null; skin_swatch?:boolean;eye_swatch?:boolean};
import parts from './portraitParts.json';
import {beardLayer, dressedBust, bodyFrames, facialHairStyles, type BodyFrame, type FacialHair} from './portraitAnatomy';
import {type Illustration,validIllustration} from "./portraitV4/illustration";
import {illustratedPortrait} from "./portraitV4/illustratedPortrait";
export type ProceduralPortrait=LegacyPortrait|Illustration;
export type LegacyPortrait = ({version:1} | {version:2;body_frame:BodyFrame;facial_hair:FacialHair} | ({version:3;body_frame:BodyFrame;facial_hair:FacialHair} & Layers)) & {seed:string;form:'neutral'|'human';stage:string;visual_age_mode?:'auto'|'manual';visual_age?:'infant'|'child'|'adolescent'|'young_adult'|'mature_adult'|'elderly';face:number;hair:number;skin:number;eyes:number;clothing:number;accessory:number;palette:number;hair_color?:number;clothing_color?:number};
type Art = { [key:string]: any };
function draw(p: Art): string {
    const skin = p.skin || ['#e6b99a', '#c68b70', '#aa705a'];
    const line = p.line || '#633e35';
    const teen = p.visualAge==='adolescent' && p.artisticAge;
    const young = p.visualAge==='infant'||p.visualAge==='child';
    const eyeY = p.visualAge==='infant'?222:p.visualAge==='child'?214:teen?211:p.eyeY || 207;
    const leftEye = p.eyes === 'sharp'
      ? `M153 ${eyeY + 1} Q168 ${eyeY - 9} 185 ${eyeY} Q171 ${eyeY + 7} 153 ${eyeY + 1}Z`
      : `M153 ${eyeY} Q169 ${eyeY - 10} 185 ${eyeY} Q170 ${eyeY + 10} 153 ${eyeY}Z`;
    const rightEye = p.eyes === 'sharp'
      ? `M215 ${eyeY} Q232 ${eyeY - 9} 247 ${eyeY + 1} Q231 ${eyeY + 7} 215 ${eyeY}Z`
      : `M215 ${eyeY} Q230 ${eyeY - 10} 247 ${eyeY} Q232 ${eyeY + 10} 215 ${eyeY}Z`;
    const defs = `<defs>
      <linearGradient id="background" x1="0" y1="0" x2="1" y2="1"><stop stop-color="${p.bg[0]}"/><stop offset="1" stop-color="${p.bg[1]}"/></linearGradient>
      <linearGradient id="skin" x1=".15" y1=".1" x2=".9" y2=".8"><stop stop-color="${skin[0]}"/><stop offset=".64" stop-color="${skin[1]}"/><stop offset="1" stop-color="${skin[2]}"/></linearGradient>
      <linearGradient id="neck" x1="0" y1="0" x2=".8" y2="1"><stop stop-color="${skin[2]}"/><stop offset=".7" stop-color="${skin[1]}"/><stop offset="1" stop-color="${skin[0]}"/></linearGradient>
      <linearGradient id="hair" x1="0" y1="0" x2="1" y2="1"><stop stop-color="${p.hair[0]}"/><stop offset="1" stop-color="${p.hair[1]}"/></linearGradient>
      <linearGradient id="cloth" x1="0" y1="0" x2="1" y2="1"><stop stop-color="${p.cloth[0]}"/><stop offset="1" stop-color="${p.cloth[1]}"/></linearGradient>
      <radialGradient id="light"><stop stop-color="${p.glow || '#e4bf91'}" stop-opacity=".26"/><stop offset="1" stop-color="${p.glow || '#e4bf91'}" stop-opacity="0"/></radialGradient>
    </defs>`;
    const age = p.visualAge;
    const headTransform = p.revised?.headTransform || p.youngHead || (age==='infant'?'translate(-32 -25) scale(1.16 1.12)':age==='child'?'translate(-8 -2) scale(1.04 1.02)':age==='adolescent'?'translate(-4 -6) scale(1.02 1.01)':'');
    const aging = p.revised?'':age==='elderly'?'<path d="M151 221l14 6m69-6l14-6M166 170q34-12 67 0m-65 9q31-9 63 0M178 244l-5 13m50-13l6 13M180 279q20 10 40 0" fill="none" stroke="#633e35" opacity=".4" stroke-width="2"/>':age==='mature_adult'?'<path d="M150 219l12 4m75-4l12-4M177 243l-3 9m49-9l3 9" fill="none" stroke="#633e35" opacity=".22" stroke-width="1.5"/>':'';
    const ears = p.revised?.ears ?? ((p.earShift?`<g transform="translate(200 0) scale(${p.earShift} 1) translate(-200 0)">`:'') + `<path d="M137 195 C120 183 120 212 126 229 Q131 240 141 232Z" fill="${skin[1]}"/><path d="M263 195 C280 183 280 212 274 229 Q269 240 259 232Z" fill="${skin[2]}"/><path d="M131 203 Q127 211 134 222 M269 203 Q273 211 266 222" fill="none" stroke="${line}" stroke-opacity=".27" stroke-width="3" stroke-linecap="round"/>` + (p.earShift?'</g>':''));
    const facePath = p.revised?.outline || p.paintedHead || (age==='infant'?'M140 145 C151 115 249 115 260 145 C275 174 272 237 254 270 Q237 302 200 304 Q163 302 146 270 C128 237 125 174 140 145Z':age==='child'?'M142 145 C157 124 242 124 258 145 C270 177 265 225 252 249 Q232 295 201 297 Q169 295 148 249 C135 225 130 177 142 145Z':teen?'M144 144 C161 124 239 124 256 145 C266 174 263 219 252 247 Q232 286 201 292 Q170 286 148 247 C137 219 134 174 144 144Z':p.face || 'M144 142 C160 125 239 125 256 147 C267 175 263 220 253 247 C245 270 225 295 202 299 C177 297 155 274 146 248 C136 224 132 172 144 142Z');
    const facialHair = p.facialHair ? beardLayer(p.facialHair, facePath, p.hair,p.revised?.beardOffset) : '';
    const face = p.revised?.face ?? `<path d="${facePath}" fill="url(#skin)"/>
      <path d="M245 157 Q268 199 250 247 Q235 281 207 293 Q235 276 236 247 C231 224 251 202 245 157Z" fill="${skin[2]}" opacity=".27"/>
      <path d="M149 166 C143 192 146 218 152 233 C159 222 165 221 175 219 Q156 197 161 166Z" fill="${skin[0]}" opacity=".27"/>
      <path d="M155 238 Q168 229 184 239 Q168 246 155 238Z M216 239 Q234 229 247 236 Q235 247 216 239Z" fill="${p.blush || '#b96d60'}" opacity=".16"/>
      <path d="${leftEye}" fill="${p.eyeWhite || '#e8d9c4'}"/>
      <path d="${rightEye}" fill="${p.eyeWhite || '#e8d9c4'}"/>
      <ellipse cx="171" cy="${eyeY}" rx="${p.visualAge==='infant'?7:5.5}" ry="${p.visualAge==='infant'?7.5:6.1}" fill="${p.iris || '#4b4032'}"/>
      <ellipse cx="230" cy="${eyeY}" rx="${p.visualAge==='infant'?7:5.5}" ry="${p.visualAge==='infant'?7.5:6.1}" fill="${p.iris || '#4b4032'}"/>
      <ellipse cx="171" cy="${eyeY}" rx="2.6" ry="4.4" fill="#292323"/>
      <ellipse cx="230" cy="${eyeY}" rx="2.6" ry="4.4" fill="#292323"/>
      <circle cx="169" cy="${eyeY - 2}" r="1.2" fill="#fff4da" opacity=".8"/><circle cx="228" cy="${eyeY - 2}" r="1.2" fill="#fff4da" opacity=".8"/>
      <path d="M153 ${eyeY} Q169 ${eyeY - 10} 185 ${eyeY} M215 ${eyeY} Q230 ${eyeY - 10} 247 ${eyeY}" stroke="${line}" fill="none" stroke-width="${p.eyes === 'sharp' ? 2.4 : 1.8}" stroke-linecap="round"/>
      <path d="M154 ${eyeY + 12} Q170 ${eyeY + 17} 183 ${eyeY + 11} M216 ${eyeY + 11} Q232 ${eyeY + 17} 245 ${eyeY + 12}" stroke="${skin[2]}" fill="none" stroke-width="1" opacity=".55"/>
      ${p.designedbrows || (young||teen?`<path d="M153 ${eyeY-18} Q168 ${eyeY-23} 184 ${eyeY-18} M216 ${eyeY-18} Q232 ${eyeY-23} 247 ${eyeY-18}" stroke="${p.hair[1]}" fill="none" stroke-width="2.5" stroke-linecap="round"/>`:p.brows || `<path d="M150 190 Q167 182 185 188 M214 188 Q232 182 248 190" stroke="${p.hair[1]}" fill="none" stroke-width="4.5" stroke-linecap="round"/>`)}
      ${p.designednose || (young||teen?`<path d="M201 ${eyeY+12} q-2 10-4 14 q5 4 10 0" stroke="${skin[2]}" fill="none" stroke-width="1.7" stroke-linecap="round"/>`:p.nose || `<path d="M202 209 C202 220 198 230 195 236 Q202 241 209 237" fill="none" stroke="${skin[2]}" stroke-width="2.3" stroke-linecap="round"/><path d="M191 238 Q194 235 198 239 M207 239 Q211 236 214 239" fill="none" stroke="${line}" opacity=".48" stroke-width="1.5"/>`)}
      ${p.designedlips || (young||teen?`<path d="M188 ${teen?260:270} Q200 ${teen?255:265} 212 ${teen?260:270} Q200 ${teen?269:279} 188 ${teen?260:270}Z" fill="${p.lipColor || '#ae7164'}"/><path d="M189 ${teen?260:270} Q200 ${teen?263:273} 211 ${teen?260:270}" fill="none" stroke="${line}" opacity=".4"/>`:p.lips || `<path d="M184 258 Q195 252 201 255 Q206 252 218 258 Q202 271 184 258Z" fill="${p.lipColor || '#ae7164'}"/><path d="M185 258 Q201 261 217 258" fill="none" stroke="${line}" stroke-width="1.2" opacity=".7"/><path d="M194 266 Q202 268 209 265" fill="none" stroke="${skin[0]}" stroke-width="1.2" opacity=".7"/>`)}
      ${p.extraFace || ''}`;
    return (`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 500" width="400" height="500"><title>Иллюстрация персонажа</title>${defs}
      <rect width="400" height="500" fill="url(#background)"/>
      <ellipse cx="92" cy="126" rx="245" ry="232" fill="url(#light)"/>
      <path d="M0 405 L400 274 V500 H0Z" fill="#1c2424" opacity=".08"/>
      <path d="M328 0 V500 M342 0 V500" stroke="#f8dfb1" stroke-opacity=".07"/>
      ${(age||p.revised)?`<g transform="${headTransform}">${p.backHair || ''}</g>`:p.backHair || ''}
      ${age==='infant'?'<g transform="translate(56 0) scale(.72 1)">':age==='child'?'<g transform="translate(28 0) scale(.86 1)">':age==='adolescent'?'<g transform="translate(12 0) scale(.94 1)">':''}
${p.bust ?? `      <path d="${p.revised?.neckPath||'M176 271 L174 322 L151 340 Q199 378 248 339 L225 323 L225 271Z'}" fill="url(#neck)"/>
      <path d="M177 284 Q198 310 224 284 L225 306 Q199 321 176 299Z" fill="${skin[2]}" opacity=".38"/>
      ${p.body}`}
      ${['infant','child','adolescent'].includes(age)?'</g>':''}
      ${(p.visualAge||p.revised)?`<g transform="${headTransform}">${ears}${face}${aging}${facialHair}${p.frontHair || ''}${p.accessories || ''}</g>`:`${ears}${face}${facialHair}${p.frontHair || ''}${p.accessories || ''}`}
      <path d="M0 499 H400" stroke="#162020" opacity=".2"/>
    </svg>`);
  };


// New optional swatches do not change unconfigured v1 illustrations. Their
// order is part of the persisted descriptor contract (portrait_traits.py).
const hairColors=catalog.hair_materials;
const clothingColors=catalog.cloth_materials;
function tintLayers(body:string,swatch:string[]|undefined):string {
 if(!swatch || !body)return body;
 // Keep contrast in the trusted, illustrated collar/seams of the garment.
 const rgb=(hex:string)=>[1,3,5].map(n=>parseInt(hex.slice(n,n+2),16));
 const dark=rgb(swatch[1]),light=rgb(swatch[0]);
 return body.replace(/(fill|stroke)="(#[0-9a-f]{6})"/gi,(_match,attr,hex)=>{
  const [r,g,b]=rgb(hex),t=(r*.21+g*.72+b*.07)/255;
  const tone=light.map((c,i)=>Math.round(dark[i]+(c-dark[i])*t)).map(c=>c.toString(16).padStart(2,'0')).join('');
  return attr+'="#'+tone+'"';
 });
}
const cache=new Map<string,string>();
export function proceduralPortrait(p?:ProceduralPortrait|null):string|null {
 if(p?.version===4){
   if(!validIllustration(p))return null;
   if(p.form==='neutral')return null;
   const key=JSON.stringify(p), hit=cache.get(key);
   return hit||cachePortrait(key,illustratedPortrait(p));
 }
 if(!p || (p.version!==1 && p.version!==2 && p.version!==3) || !/^[a-f0-9]{32}$/.test(p.seed))return null;
 const keys=['face','hair','skin','eyes','clothing','accessory','palette'] as const;
 if(keys.some(k=>!Number.isInteger(p[k]) || p[k]<0 || p[k]>(['hair','eyes','clothing','accessory'].includes(k)?7:6)))return null;
 const colorsValid=(c:number|undefined,n:number)=>c==null||(Number.isInteger(c)&&c>=0&&c<n);
 if(!colorsValid(p.hair_color,p.version===3?hairColors.length:7)||
    !colorsValid(p.clothing_color,p.version===3?clothingColors.length:7)||
    (p.version===3&&!colorsValid(p.accent_color,clothingColors.length)))return null;
 const layers=p.version===3?p:undefined;
 if(layers && ((layers.hairstyle && !Object.hasOwn(catalog.styles.hair,layers.hairstyle)) ||
    (layers.garment && !Object.hasOwn(catalog.styles.clothing,layers.garment)) ||
    (layers.visage && !Object.hasOwn(catalog.styles.face,layers.visage))))return null;
 const base=p.version===3?(p.base_version||2):p.version;
 if(p.version!==1 && (!Object.hasOwn(bodyFrames,p.body_frame)||!Object.hasOwn(facialHairStyles,p.facial_hair)))return null;
 const key=JSON.stringify(p);const cached=cache.get(key);if(cached)return cached;
 const bg=parts[p.palette].bg;
 let svg:string;
 if(p.form==='neutral') return null; // CharacterAvatar owns every fallback, including initials.
 if(p.form==='human') {
  const hairIndex=layers?.hairstyle ? Object.keys(catalog.styles.hair).indexOf(layers.hairstyle) : p.hair;
  const faceIndex=layers?.visage ? Object.keys(catalog.styles.face).indexOf(layers.visage) : p.face;
  const face=parts[faceIndex%7] as Art, hair=parts[hairIndex%7] as Art, skin=parts[p.skin] as Art;
  const clothColor=p.clothing_color==null?undefined:clothingColors[p.clothing_color];
  const outfit=p.clothing===0?null:parts[p.clothing-1];
  const tunic='<path d="M173 316Q200 342 227 316L271 337Q311 349 328 402L345 500H56L73 402Q88 353 130 336Z" fill="url(#cloth)"/>';
  const body=base===1?tintLayers(outfit?outfit.body+outfit.tailoring:tunic,clothColor):'';
  const hairColor=p.hair_color==null?undefined:hairColors[p.hair_color];
  const lockColor=base===2 || layers?.hairstyle?hairColor:undefined;
  const age=p.visual_age || p.stage;
  const juvenile=['infant','child','adolescent'].includes(age);
  const skinColors=layers?.skin_swatch?Object.values(catalog.skin_materials)[p.skin]:skin.skin||parts[1].skin;
  const iris=layers?.eye_swatch?Object.values(catalog.eye_colors)[p.eyes]:p.eyes===7?'#6f8998':parts[p.eyes].iris;
  // Imported descriptors may combine new catalogue IDs with a pre-figure base.
  // Only artwork introduced after those revisions needs the newer drawing.
  const extended = layers && (faceIndex >= 7 || hairIndex >= 16 ||
    (layers.garment && Object.keys(catalog.styles.clothing).indexOf(layers.garment) >= 15) ||
    layers.accent_color != null || (layers.eyewear && layers.eyewear!=='none') ||
    (layers.face_detail && layers.face_detail!=='none') || ['goatee','sideburns'].includes(layers.facial_hair) ||
    ['stocky','athletic'].includes(layers.body_build || '') ||
    (['eye_shape','nose_shape','lip_shape'] as const).some(k=>Object.keys(catalog.features[k]).indexOf(layers[k] || '')>=3));
  if(layers && (layers.face_revision===3 || layers.face_revision===4 || extended)){
   const ids=catalog.styles;
   const figure = extended && layers.face_revision!==3 && layers.face_revision!==4
     ? {...layers,face_revision:4 as const,eye_revision:2 as const} : layers;
   const result=portraitFigure(figure,layers.visage||Object.keys(ids.face)[p.face] as keyof Styles['face'],
    layers.hairstyle||Object.keys(ids.hair)[p.hair] as keyof Styles['hair'],
    layers.garment||Object.keys(ids.clothing)[p.clothing] as keyof Styles['clothing'],
    {skin:skinColors,hair:hairColor||hair.hair,cloth:clothColor||parts[p.palette].cloth,bg,iris,accent:layers.accent_color==null?undefined:clothingColors[layers.accent_color][0]});
   return cachePortrait(key,result);
  }
  const revised=layers?.face_revision===2 && layers.visage ? portraitFace(layers.visage,age,layers.body_frame,skinColors,hairColor||hair.hair,iris) : undefined;
  const bust=layers?.garment?garmentLayer(layers.garment,layers.body_frame,juvenile,revised?.neckPath):base===2 && p.version!==1?dressedBust(p.body_frame,juvenile,tintLayers(outfit?.tailoring||'',clothColor),(skin.skin||parts[1].skin)[2],!outfit,revised?.neckPath):undefined;
  const facialHair=p.version!==1 && ['adult','young_adult','mature_adult','elderly'].includes(age) ? p.facial_hair : undefined;
  const outline=base===1?face.face:p.hair===7 && !juvenile?face.baldFace:face.faceV2 || face.face;
  const styledHair=layers?.hairstyle && coiffure(layers.hairstyle);
  const features:Art={};
  if(layers?.visage && !revised){
   const youth=age==='infant'?1:age==='child'?.55:age==='adolescent'?.2:0;
   const width=[64,58,66,71,60,70,63][faceIndex]+4*youth;
   features.earShift=width/64;
   if(juvenile){
    features.youngHead=age==='infant'?'translate(-40 -15) scale(1.20 1.15)':age==='child'?'translate(-20 1) scale(1.10 1.05)':'translate(-4 -6) scale(1.02 1.01)';
   }
   const jaw=[44,36,53,58,40,52,43][faceIndex]+10*youth;
   const chin=302-19*youth+[0,-2,-2,-6,8,-7,0][faceIndex]*(1-youth*.6);
   features.paintedHead=`M${200-width} 185 C${194-width} ${90-youth*9} ${206+width} ${90-youth*9} ${200+width} 185 Q${204+width} 228 ${200+jaw} 260 Q${221+jaw/3} ${chin-1} 200 ${chin} Q${179-jaw/3} ${chin-1} ${200-jaw} 260 Q${196-width} 228 ${200-width} 185Z`;
   if(layers.visage==='angular'||layers.visage==='broad'){
    const corner=layers.visage==='broad'?55:49;
    features.paintedHead=`M${200-width} 182 C${194-width} 90 ${206+width} 90 ${200+width} 182 L${202+width} 218 L${200+corner} ${262-4*youth} L${222+4*youth} ${chin-5} Q200 ${chin+3} ${178-4*youth} ${chin-5} L${200-corner} ${262-4*youth} L${198-width} 218Z`;
   }
   const eyeY=age==='infant'?222:age==='child'?214:age==='adolescent'?211:face.eyeY||207;
   const arch=[8,12,3,5,9,13,10][faceIndex], angle=[0,-3,4,3,-1,0,-3][faceIndex];
   const brow=(hairColor||hair.hair)[1];
   features.designedbrows=`<path d="M149 ${eyeY-16-angle}q17 ${-arch} 36 ${angle}m30 0q19 ${-arch} 36 ${-angle}" fill="none" stroke="${brow}" stroke-width="${juvenile?3:[4,3,6,7,4,5,3][faceIndex]}" stroke-linecap="round"/>`;
   const nose=[9,6,10,14,7,12,8][faceIndex],length=juvenile?17:[28,24,32,25,34,21,25][faceIndex];
   features.designednose=`<path d="M202 ${eyeY+4}q1 ${length/2} -${nose} ${length}q${nose} 6 ${nose*1.7} 0" fill="none" stroke="${skinColors[2]}" stroke-width="3" stroke-linecap="round"/>`;
   const lip=[18,15,19,22,16,18,20][faceIndex]*(1-.28*youth),y=age==='infant'?259:juvenile?257:259;
   features.designedlips=`<path d="M${200-lip} ${y}q${lip*.7} -${[5,3,2,4,3,6,7][faceIndex]} ${lip} -2q4-2 ${lip} 2q-${lip} ${[11,8,6,9,7,14,13][faceIndex]} -${lip*2} 0Z" fill="${face.lipColor||'#ab7064'}"/>`;
   features.eyes=!youth && [1,2,4].includes(faceIndex)?'sharp':'round';
  }
  svg=draw({...face,revised,face:outline,visualAge:p.visual_age || (base===2 && juvenile ? p.stage : undefined),artisticAge:!!p.visual_age_mode,name:'',bg,skin:skinColors,iris,
   hair:hairColor || (layers?.hairstyle ? parts[p.hair%7].hair : hair.hair),
   frontHair:hairIndex===7?'':tintLayers(hair.frontHair,lockColor),backHair:hairIndex===7?'':tintLayers(hair.backHair,lockColor),
   ...styledHair, ...features, cloth:clothColor||parts[p.palette].cloth,
   // Plain unbranded tunic is the default in every historical setting.
   body, bust, facialHair,
   accessories:p.accessory===0?'':(parts[(p.accessory-1)%7] as Art).accessories||'',extraFace:base===2 && p.face===6 ? face.extraFace : '',brows:undefined});
 } else return null;
 return cachePortrait(key,svg);
}
let cachedChars=0;
function cachePortrait(key:string,svg:string){
 // Each SVG is an image document: gradient IDs cannot collide between cards.
 const url='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);
 while(cache.size && (cache.size>=512||cachedChars+url.length>4_000_000)){
  const first=cache.keys().next().value!;cachedChars-=cache.get(first)!.length;cache.delete(first);
 }
 cache.set(key,url);cachedChars+=url.length;return url;
}
