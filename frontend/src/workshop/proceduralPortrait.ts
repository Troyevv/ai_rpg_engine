// Trusted vector layers from the approved #175 artwork. Version 1 is immutable.
// Never accept SVG, paths, colors or markup from the server/user.
import parts from './portraitParts.json';
export type ProceduralPortrait = {version:1;seed:string;form:'neutral'|'human';stage:string;face:number;hair:number;skin:number;eyes:number;clothing:number;accessory:number;palette:number};
type Art = { [key:string]: any };
function draw(p: Art): string {
    const skin = p.skin || ['#e6b99a', '#c68b70', '#aa705a'];
    const line = p.line || '#633e35';
    const eyeY = p.eyeY || 207;
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
    const ears = `<path d="M137 195 C120 183 120 212 126 229 Q131 240 141 232Z" fill="${skin[1]}"/><path d="M263 195 C280 183 280 212 274 229 Q269 240 259 232Z" fill="${skin[2]}"/><path d="M131 203 Q127 211 134 222 M269 203 Q273 211 266 222" fill="none" stroke="${line}" stroke-opacity=".27" stroke-width="3" stroke-linecap="round"/>`;
    const facePath = p.face || 'M144 142 C160 125 239 125 256 147 C267 175 263 220 253 247 C245 270 225 295 202 299 C177 297 155 274 146 248 C136 224 132 172 144 142Z';
    const face = `<path d="${facePath}" fill="url(#skin)"/>
      <path d="M245 157 Q268 199 250 247 Q235 281 207 293 Q235 276 236 247 C231 224 251 202 245 157Z" fill="${skin[2]}" opacity=".27"/>
      <path d="M149 166 C143 192 146 218 152 233 C159 222 165 221 175 219 Q156 197 161 166Z" fill="${skin[0]}" opacity=".27"/>
      <path d="M155 238 Q168 229 184 239 Q168 246 155 238Z M216 239 Q234 229 247 236 Q235 247 216 239Z" fill="${p.blush || '#b96d60'}" opacity=".16"/>
      <path d="${leftEye}" fill="${p.eyeWhite || '#e8d9c4'}"/>
      <path d="${rightEye}" fill="${p.eyeWhite || '#e8d9c4'}"/>
      <ellipse cx="171" cy="${eyeY}" rx="5.5" ry="6.1" fill="${p.iris || '#4b4032'}"/>
      <ellipse cx="230" cy="${eyeY}" rx="5.5" ry="6.1" fill="${p.iris || '#4b4032'}"/>
      <ellipse cx="171" cy="${eyeY}" rx="2.6" ry="4.4" fill="#292323"/>
      <ellipse cx="230" cy="${eyeY}" rx="2.6" ry="4.4" fill="#292323"/>
      <circle cx="169" cy="${eyeY - 2}" r="1.2" fill="#fff4da" opacity=".8"/><circle cx="228" cy="${eyeY - 2}" r="1.2" fill="#fff4da" opacity=".8"/>
      <path d="M153 ${eyeY} Q169 ${eyeY - 10} 185 ${eyeY} M215 ${eyeY} Q230 ${eyeY - 10} 247 ${eyeY}" stroke="${line}" fill="none" stroke-width="${p.eyes === 'sharp' ? 2.4 : 1.8}" stroke-linecap="round"/>
      <path d="M154 ${eyeY + 12} Q170 ${eyeY + 17} 183 ${eyeY + 11} M216 ${eyeY + 11} Q232 ${eyeY + 17} 245 ${eyeY + 12}" stroke="${skin[2]}" fill="none" stroke-width="1" opacity=".55"/>
      ${p.brows || `<path d="M150 190 Q167 182 185 188 M214 188 Q232 182 248 190" stroke="${p.hair[1]}" fill="none" stroke-width="4.5" stroke-linecap="round"/>`}
      ${p.nose || `<path d="M202 209 C202 220 198 230 195 236 Q202 241 209 237" fill="none" stroke="${skin[2]}" stroke-width="2.3" stroke-linecap="round"/><path d="M191 238 Q194 235 198 239 M207 239 Q211 236 214 239" fill="none" stroke="${line}" opacity=".48" stroke-width="1.5"/>`}
      ${p.lips || `<path d="M184 258 Q195 252 201 255 Q206 252 218 258 Q202 271 184 258Z" fill="${p.lipColor || '#ae7164'}"/><path d="M185 258 Q201 261 217 258" fill="none" stroke="${line}" stroke-width="1.2" opacity=".7"/><path d="M194 266 Q202 268 209 265" fill="none" stroke="${skin[0]}" stroke-width="1.2" opacity=".7"/>`}
      ${p.extraFace || ''}`;
    return (`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 500" width="400" height="500"><title>Иллюстрация персонажа</title>${defs}
      <rect width="400" height="500" fill="url(#background)"/>
      <ellipse cx="92" cy="126" rx="245" ry="232" fill="url(#light)"/>
      <path d="M0 405 L400 274 V500 H0Z" fill="#1c2424" opacity=".08"/>
      <path d="M328 0 V500 M342 0 V500" stroke="#f8dfb1" stroke-opacity=".07"/>
      ${p.backHair || ''}
      <path d="M176 271 L174 322 L151 340 Q199 378 248 339 L225 323 L225 271Z" fill="url(#neck)"/>
      <path d="M177 284 Q198 310 224 284 L225 306 Q199 321 176 299Z" fill="${skin[2]}" opacity=".38"/>
      ${p.body}
      ${ears}${face}${p.frontHair || ''}${p.accessories || ''}
      <path d="M0 499 H400" stroke="#162020" opacity=".2"/>
    </svg>`);
  };


const cache=new Map<string,string>();
export function proceduralPortrait(p?:ProceduralPortrait|null):string|null {
 if(!p || p.version!==1 || !/^[a-f0-9]{32}$/.test(p.seed))return null;
 const keys=['face','hair','skin','eyes','clothing','accessory','palette'] as const;
 if(keys.some(k=>!Number.isInteger(p[k]) || p[k]<0 || p[k]>(['hair','clothing','accessory'].includes(k)?7:6)))return null;
 const key=JSON.stringify(p);const cached=cache.get(key);if(cached)return cached;
 const bg=parts[p.palette].bg;
 let svg:string;
 if(p.form==='neutral') {
  svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 500"><rect width="400" height="500" fill="${bg[1]}"/><circle cx="200" cy="190" r="68" fill="${bg[0]}"/><path d="M62 500V407a138 112 0 0 1 276 0v93Z" fill="${bg[0]}"/></svg>`;
 } else if(p.form==='human') {
  const face=parts[p.face] as Art, hair=parts[p.hair%7] as Art, skin=parts[p.skin] as Art;
  svg=draw({...face,name:'',bg,skin:skin.skin||parts[1].skin,iris:parts[p.eyes].iris,
   hair:hair.hair,frontHair:p.hair===7?'':hair.frontHair,backHair:p.hair===7?'':hair.backHair,
   cloth:parts[p.palette].cloth,
   // Plain unbranded tunic is the default in every historical setting.
   body:p.clothing===0?'<path d="M173 316Q200 342 227 316L271 337Q311 349 328 402L345 500H56L73 402Q88 353 130 336Z" fill="url(#cloth)"/>':parts[(p.clothing-1)%7].body,
   accessories:p.accessory===0?'':(parts[(p.accessory-1)%7] as Art).accessories||'',extraFace:'',brows:undefined});
 } else return null;
 // Each SVG is an image document: gradient IDs cannot collide between cards.
 const url='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);
 if(cache.size>=512)cache.delete(cache.keys().next().value!);cache.set(key,url);return url;
}
