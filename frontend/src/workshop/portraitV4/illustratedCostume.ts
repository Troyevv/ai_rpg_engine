import {illustrationCatalog as catalog,mix,type Illustration,type Traits} from './illustration';
import {shape as path,seam as line} from '../portraitWardrobe';
import type {landmarks} from './illustratedFace';
type Cut={neck:'crew'|'v'|'high'|'boat'|'split'; ease:number; drop:number; sleeve:'set'|'raglan'|'drape'|'puff'|'armour'|'bare'};
const cut=(neck:Cut['neck'],ease:number,drop:number,sleeve:Cut['sleeve']):Cut=>({neck,ease,drop,sleeve});
const patterns:Record<Traits['clothing'],Cut>={
 plain:cut('split',4,5,'drape'),tshirt:cut('crew',2,6,'set'),shirt:cut('split',4,0,'set'),blazer:cut('v',9,-3,'set'),
 jacket:cut('high',12,2,'set'),cardigan:cut('v',8,7,'raglan'),jumper:cut('crew',8,7,'raglan'),sweater:cut('high',0,1,'raglan'),
 blouse:cut('boat',11,5,'puff'),hoodie:cut('crew',15,9,'raglan'),vest:cut('v',1,1,'bare'),dress:cut('boat',0,2,'bare'),
 coveralls:cut('split',8,3,'set'),smock:cut('boat',17,13,'puff'),cloak:cut('crew',20,6,'drape'),
 doublet:cut('high',7,-3,'puff'),surcoat:cut('boat',12,3,'bare'),mantle:cut('crew',24,4,'drape'),bodice:cut('v',1,0,'puff'),
 kaftan:cut('high',10,6,'drape'),hauberk:cut('crew',14,4,'raglan'),brigandine:cut('boat',14,-5,'armour'),
 robe:cut('v',20,12,'drape'),tabard:cut('boat',8,-2,'bare'),wrap:cut('v',9,6,'drape'),flight:cut('high',15,1,'set'),
 pressure:cut('high',21,-5,'armour'),techcoat:cut('high',13,-4,'drape'),harness:cut('crew',9,0,'set'),
 shell:cut('high',18,-6,'armour'),medic:cut('split',4,-1,'raglan'),pilot:cut('high',8,-2,'raglan')};
export function illustratedCostume(p:Illustration,g:ReturnType<typeof landmarks>){
 const t=p.traits,design=patterns[t.clothing],cloth=catalog.colors.clothing_color[t.clothing_color],trim=catalog.colors.clothing_color[t.trim],
 skin=catalog.colors.skin[t.skin],outline=mix(cloth,'#242532',.6),cream=mix(trim,'#fff3d7',.34),shadow=mix(cloth,'#262336',.47);
 const [shoulders,neck,volume,arm,slope]={slim:[103,20,76,19,25],average:[120,25,94,25,24],broad:[145,28,104,30,16],
 athletic:[139,30,91,39,18],full:[131,35,140,40,29],stocky:[133,33,123,33,19]}[t.build];
 const frame=p.body_frame==='male'?5:p.body_frame==='female'?-4:0;
 const s=(shoulders+frame+design.ease)*(1-.39*g.youth)*(g.semi?1.26:1.15),
 n=(neck+frame*.36)*(g.semi?1.47:1.29)*(1-.49*g.youth),v=volume*(1-.37*g.youth),a=arm*(1-.28*g.youth);
 const shoulder=slope+design.drop+5*g.youth+(g.old?8:0),deep=design.neck==='v'?65:design.neck==='split'?37:design.neck==='high'?-4:design.neck==='boat'?20:24;
 const collar=design.neck==='boat'?n+17:n+2;
 const y=g.eyeY+g.length*g.headScale+(g.old?15:23)*(1-.65*g.youth);
 const hem=510-y;
 const left=-(s+12),right=s-3;
 const hip=g.youth?Math.max(s*.85,v*.9):v+8;
 const full=`M${-collar} 0C${-collar-16} 12 ${-s*.56} ${shoulder-6} ${-s*.74} ${shoulder-4}Q${left+19} ${shoulder-5} ${left+8} ${shoulder}
 Q${left-8} ${shoulder+8} ${left-a*.72} ${shoulder+62}L${Math.min(-v-a-20,left-a*.88)} ${hem}H${Math.max(v+a+11,right+a*.85)}
 L${right+a*.65} ${shoulder+61}Q${right+9} ${shoulder+9} ${right} ${shoulder+1}
 Q${s*.56} ${shoulder*.64} ${collar} 0`;
 const neckline=design.neck==='v'||design.neck==='split'?`Q${n*.74} 14 5 ${deep}Q${-n*.72} 15 ${-collar} 0Z`:
 `Q3 ${deep*1.78} ${-collar} 0Z`;
 const near=`M${left+8} ${shoulder+2}q19 18 17 43q1 11 -5 23`;
 const far=`M${right-2} ${shoulder+2}q-15 18 -13 42q-2 13 5 23`;
 const material='url(#fabric)';
 const tension=path(`M${left+14} ${shoulder+9}Q${left+43} ${shoulder+23} ${left+45} ${shoulder+46}Q${left+27} ${shoulder+24} ${left+14} ${shoulder+9}Z
 M${right-16} ${shoulder+37}q-10 31 -32 42q20 -21 32 -42Z M${-v-3} ${hem-12}q14-33 32-44q-18 19-22 47Z`,shadow,g.semi?.28:.48);
 const textileLight=path(`M${left+12} ${shoulder+1}Q${-s*.7} ${shoulder-9} ${-collar-6} 6Q${-s*.49} ${shoulder+5} ${left+12} ${shoulder+1}Z`,mix(cloth,'#f1d6ae',.36),.66);
 const buttons=(x:number,y:number,count:number)=>Array.from({length:count},(_,i)=>`<circle cx="${x}" cy="${y+i*21}" r="2.7" fill="${cream}" stroke="${outline}" stroke-width="1"/>`).join('');
 const seam=(d:string)=>line(d,outline,1.65,.74);
 const panel=(d:string,fill=trim)=>path(d,fill)+line(d,outline,1.4,.8);
 const high=panel(`M${-n-4} 3l2 -24q${n} 12 ${2*n+2} -3l2 25q${-n} 19 ${-2*n-6} 2Z`);
 const shirt=panel(`M${-n-1} -3L2 18 -11 32 ${-n-12} 8Z M${n+1} -4L3 18 13 29 ${n+10} 6Z`);
 const piping=`M${-collar} 1Q2 ${deep*1.78} ${collar} 1`;
 const belt=(flip:boolean)=>panel(flip?`M${s*.72} 14l19 6 -94 ${hem}h-29Z`:`M${-s*.76} 13l-17 7 91 ${hem}h28Z`);
 const pockets=panel(`M${-s*.65} 77l38 3 -2 31 -18 9 -19 -10Z M${s*.36} 79l34 -4 -1 32 -15 8 -16 -6Z`,mix(cloth,trim,.32));
 const lapels=panel(`M${-n-2} -3l-24 15 11 13 -13 6 58 74Z M${n+4} -4l22 14 -9 13 12 6 -46 75Z`,mix(cloth,trim,.46));
 const under=path(`M${-n-3} -3q${n} 25 ${2*n+7} -1l-19 106h-16Z`,cream);
 const sleeve=design.sleeve==='drape'?seam(`M${left+8} ${shoulder+15}q10 21 -10 73m${2*s-5} -80q-12 48 8 88`):
 design.sleeve==='raglan'?seam(`M${-n-8} 7Q${-s*.95} 54 ${left+8} 92M${n+8} 5Q${s*.92} 51 ${right-4} 88`):
 design.sleeve==='armour'?panel(`M${left+44} ${shoulder-3}q-49 -13 -62 41l53 13 22 -34Z M${right-39} ${shoulder-4}q42 -9 57 41l-51 11 -19 -34Z`):
 design.sleeve==='puff'?panel(`M${left+31} ${shoulder-5}q-44 -7 -50 39q11 17 48 14q12 -26 2 -53Z M${right-27} ${shoulder-6}q37 -5 46 37q-8 18 -44 15q-12 -24 -2 -52Z`,material):
 design.sleeve==='bare'?path(`M${left+20} ${shoulder}q17 38 12 67l-3 ${hem}h-100V0Z M${right-18} ${shoulder}q-18 39 -10 68l5 ${hem}h89V0Z`,t.clothing==='dress'?skin:cream):
 seam(near+far);
 const drape=line(`M${left+16} ${shoulder+20}q18 25 11 45m-12 2 5-12m${s*1.47} -18q-4 20 -17 32M${-v*.61} ${hem-16}q20-8 29-20`,mix(cloth,'#ead5be',.36),2,.65);
 const folds=drape+path(`M${left-2} ${shoulder+12}q29 41 21 80l-9 -17 -6 55 -14 25Z M${right-12} ${shoulder+24}q-14 56 -7 111l10 -32 9 37 31 7 -8 -87Z M${-v*.81} ${hem-21}l35 -23 -20 30Z`,shadow,g.semi?.35:.5);
 let top='';
 switch(t.clothing){
 case 'plain':top=panel('M-20 6l24 21 20-23 -14 37 -8 8 -9-12Z');break;
 case 'tshirt':top=line(piping,trim,5)+line(near+far,cream,.9,.5);break;
 case 'shirt':top=shirt+seam('M2 24v175m6-172v172')+buttons(5,42,6);break;
 case 'blazer':top=under+shirt+lapels+seam('M34 70l39-7m-106 59 -36-5')+buttons(3,120,2);break;
 case 'jacket':top=high+seam('M6 8v196M-74 62l33 11m63-4 37-12')+line('M7 15v170',trim,3);break;
 case 'cardigan':top=under+line(`M${-n} 1l31 89v110m${n-3} -200l-25 88`,trim,9)+buttons(6,104,4);break;
 case 'jumper':top=line(piping,trim,8)+panel('M-150 70l150 54 144-61v12L1 143l-151-55Z');break;
 case 'sweater':top=high+line(`M${-n} -13q${n} 10 ${n*2} -2m${-n*2} 7q${n} 9 ${n*2} -2`,cream,1.1,.65);break;
 case 'blouse':top=line(piping,trim,4)+panel('M0 29q-33-17-24 3q6 12 24 1l-10 36 10-7 6-30q26 12 28-5q0-10-28 3Z');break;
 case 'hoodie':top=panel(`M${-n+1} -16q-30 -8 -35 25q10 23 60 38q49 -19 57 -42q-6 -28 -30 -22q-4 31 -27 42q-24 -11 -25 -41Z`,mix(cloth,trim,.25))+line('M-10 34l-4 48m30-49 3 45',cream,2.7);break;
 case 'vest':top=under+line(`M${-n-2} 0L5 63 ${n+2} 0M5 63v148`,trim,4)+buttons(5,81,5);break;
 case 'dress':top=line(piping,trim,3)+seam('M-38 32q20 44 13 112m67-112q-16 60-10 112');break;
 case 'coveralls':top=shirt+pockets+line('M3 25v170',trim,4);break;
 case 'smock':top=line(piping,trim,8)+seam('M-33 21l-14 45m32-40-6 55m52-60 13 39m-29-36 6 50');break;
 case 'cloak':top=panel(`M${-n} -4Q-55 23 ${left-11} 92Q-67 119 5 26Q53 89 ${right+14} 96Q71 24 ${n} -3Q3 28 ${-n} -4Z`,mix(cloth,trim,.37))+buttons(4,25,1);break;
 case 'doublet':top=high+buttons(3,29,7)+line('M-42 20l14 134m56-132-8 130',trim,4);break;
 case 'surcoat':top=panel('M-49 10l12 158h81l9-160q-50 40-102 2Z')+line('M-29 41v111m64-110-3 110',cream,2);break;
 case 'mantle':top=panel(`M${-n} -2Q-80 17 ${left-6} 63Q-60 119 6 64Q64 110 ${right+7} 63Q83 15 ${n} -2Q2 26 ${-n} -2Z`)+line('M-23 12q25 38 51-3',cream,2.8);break;
 case 'bodice':{
 top=panel(`M${-v-5} 53Q-36 20 3 49Q44 15 ${v+8} 50L${v+13} ${hem+5}H${-v-16}Z`,mix(cloth,trim,.38))+
 line(`M-17 48q6 61 2 ${hem-48}m37 0q-10-74-5 ${48-hem}`,trim,4)+
 Array.from({length:Math.ceil(hem/17)},(_,i)=>line(`M-13 ${54+i*17}l27 15m0-15-27 15`,cream,2)).join('');
 break;
 }
 case 'kaftan':top=high+line('M23 4L8 55v135',trim,9)+buttons(0,50,5);break;
 case 'hauberk':top=path(full+neckline,'url(#mail)')+line(piping,trim,11)+belt(false);break;
 case 'brigandine':top=panel('M-72 34q72 29 141-1l-12 117H-61Z')+[-42,-15,14,43].map(x=>buttons(x,59,4)).join('');break;
 case 'robe':top=under+panel('M-23-4l-15 10 41 84 12-26Z M28-3l15 9 -56 154 -18-4Z');break;
 case 'tabard':top=panel('M-55 13l9 158h90l7-160q-49 31-106 2Z')+path('M-21 55l25 12 23-13 -5 37 -18 20 -20-19Z',cloth);break;
 case 'wrap':{
 const edge=`M${-n-4} -5L${n+7} 63 5 86 ${-n-18} 9Z`;
 const upper=`M${n-2} -5Q${n*.67} 27 -2 61L${-v-3} ${hem}H${v+50}V28Q${s*.62} 20 ${n+18} 6Z`;
 top=panel(edge)+path(upper,material)+line(`M${n+3} 0Q${n*.67} 32 2 66L${-v+2} ${hem+6}`,trim,12)+
 line(`M${n+9} 1Q${n*.72} 37 9 66L${-v+9} ${hem+6}`,outline,1.8)+seam(`M${n+13} 68q23-10 46-9m-55 22q21-11 34-12`);
 break;
 }
 case 'flight':top=high+pockets+panel('M-84 25l39-14 6 11 -39 15Z M48 9l31 9 -4 12 -34-10Z')+line('M2 9v184',cream,3);break;
 case 'pressure':top=high+line(piping,trim,14)+panel('M-39 58h75l11 19 -6 43h-81l-6-43Z')+path('M-27 70h53v21h-53Z',outline)+line('M-22 100h27',cream,4);break;
 case 'techcoat':top=panel('M-31 14l-7-51 44 25 36-17 -4 41 -39 84Z')+line('M27 11L-9 118v80',cream,3);break;
 case 'harness':top=belt(false)+belt(true)+panel('M-56 78h113l-5 21H-52Z',outline)+panel('M-12 79h24v19h-24Z');break;
 case 'shell':top=high+panel('M-78 29l65 13 14 23 -9 26 -59-12Z M77 29L17 42 6 65l10 26 53-12Z')+panel('M-59 91l62 13 59-15 -12 43 -47 14 -53-13Z');break;
 case 'medic':top=panel('M-30-3l36 17 21-17 17 13 -29 20 -45-18Z')+seam('M40 16l10 20v151')+path('M-55 55h9v8h9v9h-9v9h-9v-9h-9v-9h9Z',trim);break;
 case 'pilot':top=high+belt(true)+panel('M-73 63l38 6 -3 27 -36-4Z')+line('M-62 75l18 2',cream,3);break;
 }
 const neckPath=`M${-n+3} -85Q${-n+9} -24 ${-n} -3Q${-n-9} 6 ${-collar-28} 15Q0 116 ${collar+26} 13Q${n+2} 1 ${n} -6L${n+2} -84Z`;
 return `<g transform="translate(197 ${y})">`+path(neckPath,skin)+path(`M${-n+4} -64L${n+1} -61L${n} -19Q6 -9 ${-n+4} -27Z`,'url(#neckShadow)')+
 `<defs><clipPath id="tailor"><path d="${full}L${collar+17} -45H${-collar-17}Z"/></clipPath><clipPath id="coat"><path d="${full+neckline}"/></clipPath></defs>`+path(full+neckline,material)+line(full+neckline,outline,g.semi?1.9:2.7,.92)+
 `<g clip-path="url(#coat)">${folds}${sleeve}${tension}${textileLight}${line(`M${left+19} ${shoulder+39}Q${-hip-6} ${hem*.67} ${-hip+2} ${hem}M${right-14} ${shoulder+40}Q${hip+3} ${hem*.74} ${hip-5} ${hem}`,outline,g.semi?1.75:2.3,.66)}</g><g clip-path="url(#tailor)">${top}</g></g>`;
}

