// Trusted artwork uses a common collar landmark (200, 319). Sleeves, neckline,
// and the outer layer are painted together before fitting the plate to the frame.
import type {BodyFrame} from './portraitAnatomy';
import catalog from '../../../shared/portrait-catalog.json';

type Garment = keyof typeof catalog.styles.clothing;
type Hair = keyof typeof catalog.styles.hair;
const dark='#20262a', ivory='#f2debf';
export const shape=(d:string, fill:string, opacity=1)=>`<path d="${d}" fill="${fill}" opacity="${opacity}"/>`;
export const seam=(d:string,color=dark,width=2,opacity=.65)=>`<path d="${d}" fill="none" stroke="${color}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round" opacity="${opacity}"/>`;
const buttons=(x:number,y:number,count:number)=>Array.from({length:count},(_,i)=>`<circle cx="${x}" cy="${y+23*i}" r="3" fill="#ead4ac"/><circle cx="${x+.5}" cy="${y+23*i+.5}" r="1" fill="#473c32"/>`).join('');
const lapels=shape('M171 319L141 340 156 348 144 359 199 430Z M229 319L259 340 244 348 256 359 201 430Z',ivory,.35);
const collar=shape('M171 315L197 340 178 355 157 333Z M229 315L203 340 222 355 243 333Z',ivory,.72);
const rib=seam('M170 310q30 12 60 0m-61 6q31 14 62 0m-60 7q29 14 58 0',ivory,1.8,.48);
const cuts: Record<Garment,[string,string]> = {
 plain:['M172 318Q200 346 228 318L275 338Q297 346 312 386L351 510H49L88 386Q101 348 126 338Z',
 seam('M170 319Q199 351 230 319',ivory,7)+seam('M197 337l3 24 5-24',dark,3)],
 tshirt:['M172 320Q200 348 228 320L291 345 330 406 286 428 275 406 283 510H117L125 406 114 428 70 406 109 345Z',
 seam('M171 321Q200 353 229 321',dark,8)+seam('M73 401l42 21m170 0 42-21',ivory,2)],
 shirt:['M170 316L200 342 230 316 291 344Q310 358 320 409L337 510H63L80 409Q90 358 109 344Z',
 collar+seam('M200 344v165 M232 375h33v27l-16 8-17-8Z',ivory,2)+buttons(200,360,6)],
 blazer:['M167 313L200 404 233 313 301 337 321 351 341 510H59L79 351 99 337Z',
 shape('M165 315l35 92 35-92-35 24Z','#dbcdb7')+lapels+shape('M194 342l6-5 7 6-4 7 3 38-6 15-7-16 5-37Z',dark)+buttons(200,435,3)+seam('M249 370l31-4M114 431l35 4',ivory,3)],
 jacket:['M163 301l37 49 37-49 11 21 48 17 18 21 27 150H59l27-150 18-21 48-17Z',
 shape('M165 302l32 53-27-10-18-23Z M235 302l-32 53 27-10 18-23Z',dark,.65)+seam('M202 348v162 M120 387l42-7m76 0 42 7',ivory,4)+seam('M102 353l27 22m169-22-27 22',dark,5)],
 cardigan:['M169 319Q200 344 231 319L281 342Q312 350 323 400L342 510H58L77 400Q88 350 119 342Z',
 shape('M170 319Q200 343 230 319L208 432l-8 18-8-18Z','#dfcfb6')+seam('M170 320Q181 393 198 448v63M230 320Q219 392 202 448',dark,9)+buttons(201,454,3)+seam('M112 431q18 8 39 5m98 0q21 3 39-5',ivory,4)],
 jumper:['M163 321l37 30 37-30 55 24q32 21 41 89l10 76H57l10-76q9-68 41-89Z',
 seam('M164 322l36 29 36-29',ivory,8)+[0,1,2].map(i=>seam(`M88 ${388+i*11}l14-9 14 9 14-9 14 9 14-9 14 9 14-9 14 9 14-9 14 9 14-9 14 9 14-9 14 9 14-9 14 9`,ivory,3,.55)).join('')],
 sweater:['M172 297Q200 306 228 297L233 325 284 346Q311 355 323 409L338 510H62L77 409Q89 355 116 346L167 325Z',
 rib+seam('M111 354q27 21 28 56m150-56q-27 21-28 56',ivory,2,.32)],
 blouse:['M166 319Q200 357 234 319L272 335Q322 330 319 374L306 401 324 510H76l18-109-13-27q-3-44 47-39Z',
 seam('M167 319q32 49 66 0',ivory,8)+shape('M199 344q-32-26-27-3 7 15 28 6l-13 31 15-14 10 11-5-29q31 9 24-10-6-10-30 8Z',ivory,.78)+seam('M91 361l9 23m203-23-9 23',ivory,3)],
 hoodie:['M153 322Q153 292 177 292L200 308 223 292Q250 293 247 322L286 341Q317 353 328 413L348 510H52L72 413Q83 353 114 341Z',
 shape('M153 322Q148 298 175 290q-3 20 25 39 28-19 25-39 28 9 22 32-11 25-47 32-36-7-47-32Z',dark,.55)+seam('M187 340l-4 40m29-40 5 40',ivory,4)+seam('M141 481l21-36h76l21 36',ivory,3,.5)],
 vest:['M171 316l29 32 29-32 51 26q24 11 30 51l20 117H70l20-117q6-40 30-51Z',
 shape('M157 319l43 76 43-76 33 16q-8 52 15 69l-5 106H114l-5-106q23-17 15-69Z',dark,.66)+collar+buttons(200,405,5)+seam('M135 424l28 2m74 0 28-2',ivory,3)],
 dress:['M153 329Q162 351 200 364 238 351 247 329L276 338Q298 343 312 383l-34 17-9-14q2 48 28 124H103q26-76 28-124l-9 14-34-17q14-40 36-45Z',
 seam('M153 330q10 25 47 34 37-9 47-34',ivory,5)+shape('M128 425q72 20 144 0l3 15q-75 22-150 0Z',dark,.43)+seam('M163 449l-10 57m84-57 10 57',ivory,2,.28)],
 coveralls:['M170 316l30 25 30-25 62 26q25 17 35 67l17 101H56l17-101q10-50 35-67Z',
 collar+shape('M142 332l15-7 10 49h66l10-49 15 7-9 61 25 117H126l25-117Z',dark,.62)+seam('M168 393h64v33l-32 10-32-10Z',ivory,3)+buttons(153,345,1)+buttons(247,345,1)],
 smock:['M174 318q26 25 52 0l54 18 45 36 26 138H49l26-138 45-36Z',
 seam('M173 320q27 27 54 0m-26 15v49',ivory,8)+seam('M192 344l16 8-16 8 16 8',dark,2)+seam('M117 345l-15 65m181-65 15 65',ivory,4,.45)],
 cloak:['M169 309Q196 332 231 309l23 16q52 17 70 62l56 123H20l56-123q18-45 70-62Z',
 shape('M166 312q36 19 66-3 9 85 94 201H134q94-116 32-198Z',dark,.32)+seam('M164 317q-7 72-55 157m126-158q8 60 59 130',ivory,4,.35)+'<circle cx="215" cy="332" r="8" fill="#c7a469"/><circle cx="215" cy="332" r="4" fill="#795f46"/>'],
};
export function garmentLayer(id:Garment,frame:BodyFrame,young:boolean,neckPath?:string|null) {
 const [outline,details]=cuts[id];
 const width=young?.85:frame==='male'?1.12:frame==='female'?.89:1;
 const arms=(id==='tshirt'||id==='dress') ?
   shape(id==='tshirt'?'M79 397L112 411 103 461 98 510H60L68 460Z M321 397L288 411 297 461 302 510H340L332 460Z':'M93 375L123 388 116 459 112 510H77L84 447Z M307 375L277 388 284 459 288 510H323L316 447Z','url(#skin)'):'';
 const folds=seam('M118 358q7 22 9 36m145-36q-7 22-8 36M145 441l-5 60m111-56 8 56',ivory,1.6,.15);
 const neck=neckPath===null?'':shape(neckPath||'M174 263h52l4 55q4 14 43 24l-4 35H131l-4-35q39-10 43-24Z','url(#neck)');
 return `<g transform="translate(200 0) scale(${width} 1) translate(-200 0)">${arms}${neck}${shape(outline,'url(#cloth)')}${folds}${details}</g>`;
}

const cap='M132 202Q118 154 140 122Q167 87 211 96Q266 99 270 157L264 201L253 173Q242 145 207 144Q164 142 145 174Z';
const styles:Partial<Record<Hair,[string,string,string]>>={
 buzz:['','M134 189Q123 145 147 122Q170 98 201 100Q240 99 259 129Q272 153 263 190L251 163Q229 134 201 135Q164 135 144 163Z','M150 142l2-4m9-5 3-4m12-5 3-3m14-5 4-2m12 0 4 1m11 4 4 2m10 6 3 3'],
 pixie:['','M131 202l-8-42 9 2q-1-37 35-56l-2 8q34-31 75-7l-5 3q39 9 38 54l-9 32-8-29-12 12 2-28q-15 17-39 20l8-16q-20 24-47 29l7-16-29 24-2 17Z','M143 157q23-35 62-39m-36 43q28-35 60-39'],
 undercut:['', 'M132 195Q116 139 140 115q32-43 105-19 31 12 31 48l-15 48-9-36q-32-19-64-7l-43 10Z','M143 138q39-37 90-31m-83 39q38-28 74-26m24 33 10 5m-7 2 9 5m-7 3 8 5'],
 ponytail:['M242 137q42-15 53 27 9 35-1 74-10 43 16 70-45-6-54-44-9-30 0-60 5-28-19-39Z',cap,'M145 150q31-42 101-25m-84 34q33-30 85-29'],
 bun:['M162 110q-15-22 3-39 20-21 47-13 37 8 31 36-1 18-19 27Z',cap,'M148 150q16-33 47-43m14 3q34 9 45 38'],
 braid:['M238 150q38 9 36 43l-5 27q22 17 4 36 23 17 4 39 20 18 4 36l8 32-20-13-4-17q-22-12-9-33-19-15-7-37-20-16-7-38-14-12-10-30Z',cap,'M147 151q33-37 72-42m-62 44q35-29 75-35'],
 parted:['','M132 206Q115 159 134 125q23-37 72-32 51 0 66 43 8 24-6 69l-10-42q-17-9-31-39-31 40-80 52Z','M139 158q49-13 80-50m16 10q3 18 22 35'],
 receding:['','M132 201q-16-40-2-71 12-25 42-29-16 14-21 35l-6 46Z M224 103q38-2 48 38 6 26-8 60l-10-31q2-45-30-67Z','M139 143q-8 20-4 38m118-48q11 17 10 37']
};
export function coiffure(id:Hair) {
 const layers=styles[id];
 if(!layers)return undefined;
 const [back,front,texture]=layers;
 const braid=id==='braid'?seam('M248 224q8 10 22 12m-17 22q7 10 20 13m-16 24q8 10 18 13',ivory,3,.34):'';
 return {backHair:shape(back,'url(#hair)')+braid,frontHair:shape(front,'url(#hair)')+seam(texture,ivory,2.4,.26)};
}
