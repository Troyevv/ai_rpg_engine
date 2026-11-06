// The original garments are painted from the centre of a 400 × 500 plate.
// Fit their collars and embroidery to the same landmarks as the new sleeve caps.
export const bodyFrames = {male:'Мужская', female:'Женская', neutral:'Нейтральная'} as const;
export const facialHairStyles = {
 clean_shaven:'Гладко выбрит', stubble:'Щетина', mustache:'Усы',
 short_beard:'Короткая борода', full_beard:'Полная борода',
} as const;
export type BodyFrame = keyof typeof bodyFrames;
export type FacialHair = keyof typeof facialHairStyles;
const cuts = {
 male:    {neck:32, collar:319, shoulder:143, rise:334, sleeve:172, waist:112, drape:1.16},
 female:  {neck:21, collar:329, shoulder:99,  rise:354, sleeve:134, waist:81,  drape:.84},
 neutral: {neck:26, collar:323, shoulder:120, rise:344, sleeve:151, waist:97,  drape:1},
 youth:   {neck:22, collar:316, shoulder:105, rise:346, sleeve:138, waist:94,  drape:.88},
};

export function dressedBust(frame:BodyFrame, juvenile:boolean, cloth:string, shade:string, plain:boolean) {
 const {neck:n,collar:y,shoulder:s,rise:r,sleeve:a,waist:w,drape:k}=cuts[juvenile?'youth':frame];
 const l=200-n, h=200+n;
 const neck=`M${l} 264 Q${l+3} ${y-13} ${l-5} ${y} Q${l-12} ${y+8} ${l-39} ${r} Q200 ${y+79} ${h+39} ${r} Q${h+9} ${y+7} ${h+5} ${y} Q${h-3} ${y-13} ${h} 264Z`;
 const opening=`M${l} ${y} Q200 ${y+(plain?37:49)} ${h} ${y}`;
 const outline=`${opening} C${h+20} ${y+10} ${200+s-16} ${r-4} ${200+s} ${r+8}
 Q${200+a-5} ${r+27} ${200+a+9} 500 H${191-a} Q${205-a} ${r+27} ${200-s} ${r+8}
 C${216-s} ${r-4} ${l-20} ${y+10} ${l} ${y}Z`;
 // All seven approved outfits start with a silhouette followed by their own
 // tailoring (lapels, ribbing, pockets, closures). Only the outline is replaced.
 const tailoring=cloth.slice(cloth.indexOf('/>')+2);
 const fit=`translate(200 ${y}) scale(${k} 1) translate(-200 -316)`;
 return `<defs><clipPath id="tailoring"><path d="${outline}"/></clipPath></defs>
 <path d="${neck}" fill="url(#neck)"/>
 <path d="M${l+2} 283 Q200 312 ${h-1} 282 L${h-1} 299 Q202 327 ${l+2} 300Z" fill="${shade}" opacity=".38"/>
 <path d="${outline}" fill="url(#cloth)"/>
 <g clip-path="url(#tailoring)">
 <path d="M${200-s} ${r+8} Q${204-s} ${r+49} ${200-w} 416 Q${208-w} 454 ${199-w} 500 H${190-a}Z" fill="#151d20" opacity=".16"/>
 <path d="M${200+s} ${r+9} Q${196+s} ${r+54} ${200+w} 417 Q${191+w} 458 ${204+w} 500 H${210+a}Z" fill="#192023" opacity=".24"/>
 <path d="M${204-s} ${r+12} Q${204-s} ${r+48} ${200-w} 416 M${197+s} ${r+13} Q${196+s} ${r+52} ${200+w} 417" fill="none" stroke="#ede1cc" stroke-opacity=".19" stroke-width="1.6"/>
 <g transform="${fit}">${tailoring}</g>
 ${plain?`<path d="${opening}" fill="none" stroke="#262b2a" stroke-width="8" opacity=".38"/><path d="${opening}" fill="none" stroke="#e1d4be" opacity=".48" stroke-width="2"/>
 <path d="M${l-15} ${y+13} q-10 22 -8 46 q-3 -25 1 -42Z M${h+18} ${y+14} q9 21 4 43 q1 -23 -9 -39Z" fill="#e7d7bd" opacity=".13"/>`:''}</g>`;
}

// Hair grows down the sides and fans in toward the chin. Use the same local
// brush for every jaw, then trim its edges with that portrait's actual face.
function brush(stubble:boolean, color:string) {
 const ink=stubble?'M2 2l.4 1.2m4.7.4l.5 1.8m5-3l.7 1.4m1.3 5.6l.3 1m-5-1.4l.6 1.6m-6.4-2l.2 1.4m1.9 4.2l.4 1.5m6-1.4l.3 1.1':
  'M1 2q1 2 1 4m4-5q1 3 .6 6m5-4q1 1.6 .5 4m3 2q.4 1.7 .1 3m-7-4q.7 2.4 .5 5m-5-3q1 2 1 4';
 return [-24,0,24].map((angle,i)=>`<pattern id="brush${i}" width="16" height="16" patternUnits="userSpaceOnUse" patternTransform="rotate(${angle})">
 <path d="${ink}" fill="none" stroke="${color}" opacity="${stubble?.45:.35}" stroke-width="${stubble?.85:1.1}" stroke-linecap="round"/></pattern>`).join('');
}
const whiskers='M200 247 C197 244 193 244 189 246 C184 247 182 252 176 254 Q181 256 187 253 Q195 251 200 248 Q204 252 213 253 Q218 256 225 254 C218 251 217 247 211 246 Q205 243 200 247Z';
const cheekLine='M131 202 Q140 205 145 222 C149 235 164 244 176 246 Q185 248 187 253 Q179 258 185 263 Q192 269 201 268 Q213 268 217 262 Q221 257 214 253 Q217 248 224 246 C241 240 250 234 255 219 Q260 202 270 201 V341 H131Z';
const trimmedLine='M132 209 Q141 212 146 228 Q153 245 173 251 Q181 254 184 258 C178 267 194 273 201 271 C210 273 223 266 218 258 Q222 252 231 249 Q249 239 255 224 Q262 210 270 207 V340 H132Z';

export function beardLayer(style:FacialHair, face:string, hair:readonly string[]) {
 if(style==='clean_shaven')return '';
 const [light,dark]=hair;
 const mustache=`<path d="${whiskers}" fill="url(#hair)"/><path d="M183 252q5-5 11-5m12 0q6 0 12 5" fill="none" stroke="${light}" stroke-width="1" opacity=".56" stroke-linecap="round"/>`;
 if(style==='mustache')return mustache;
 const full=style==='full_beard', stubble=style==='stubble';
 const length=full?1.22:stubble?1:1.03;
 const jaw=`<path d="${face}" transform="translate(0 215) scale(1 ${length}) translate(0 -215)"/>`;
 const hairline=full?cheekLine:trimmedLine;
 const details=`<path d="M125 200H178Q183 269 195 335H125Z" fill="url(#brush0)"/>
 <path d="M178 200H222Q216 269 205 335H195Q183 269 178 200Z" fill="url(#brush1)"/>
 <path d="M222 200H275V335H205Q216 269 222 200Z" fill="url(#brush2)"/>`;
 return `<defs>${brush(stubble,stubble?dark:light)}<clipPath id="jaw">${jaw}</clipPath><clipPath id="cheeks"><path d="${hairline}"/></clipPath>
 <linearGradient id="beard" x1="0" y1="0" x2=".88" y2=".8"><stop stop-color="${light}"/><stop offset=".62" stop-color="${dark}"/><stop offset="1" stop-color="${dark}"/></linearGradient></defs>
 <g clip-path="url(#jaw)"><g clip-path="url(#cheeks)">
 <rect x="125" y="200" width="150" height="140" fill="url(#beard)" opacity="${stubble?.17:1}"/>
 <path d="M143 220 Q151 248 171 261 Q186 270 198 289 Q185 288 165 274 Q151 260 143 245Z" fill="${light}" opacity="${stubble?.09:.28}"/>
 <path d="M255 220 Q248 252 230 266 Q216 278 208 303 Q234 293 252 265Z" fill="${dark}" opacity=".18"/>
 <g fill="none" stroke-linecap="round">${details}</g></g></g>
 ${stubble?`<path d="${whiskers}" fill="${dark}" opacity=".11"/>`:mustache}`;
}
