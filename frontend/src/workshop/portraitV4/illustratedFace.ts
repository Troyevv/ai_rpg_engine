import {shape as path,seam as line} from '../portraitWardrobe';
import {illustrationCatalog as catalog,mix,type Illustration,type Traits} from './illustration';

// Coordinates are relative to the eye line. The viewer sees the near cheek on the left.
const planes:Record<Traits['face'],number[]>={
 oval:[62,61,48,13,83],narrow:[54,52,36,9,88],angular:[61,66,51,11,81],broad:[69,72,58,20,78],
 long:[57,56,41,13,99],round:[65,70,57,18,71],soft:[62,62,48,17,75],heart:[66,63,39,8,78],
 diamond:[55,69,42,9,85],pear:[55,62,61,20,83],square:[65,66,62,26,80],oblong:[61,59,54,20,95]};
export function landmarks(p:Illustration){
 const semi=p.art_style==='semi_realistic',age=p.visual_age||p.stage;
 const youth=age==='infant'?1:age==='child'?.64:age==='adolescent'?.24:0;
 const old=age==='elderly',mature=old||age==='mature_adult';
 const [temple,cheek,jaw,chin,len]=planes[p.traits.face];
 return {semi,youth,old,mature,temple:temple+4*youth,cheek:cheek+3*youth+(mature?1:0),jaw:jaw*(1-.35*youth)+13*youth+(old?6:mature?3:0),
 chin:chin+3*youth,length:len*(semi?1.09:.95)*(1-.38*youth)*(old?.92:mature?1.045:1),crown:-(semi?79:81)-18*youth,
 eyeSpace:temple*(semi?.452:.47), headScale:(semi?1.35:1.45)+.15*youth,
 eyeY:193+16*youth+(old?9:0),eyeX:193};
}
type Landmarks=ReturnType<typeof landmarks>;
function eye(p:Illustration,g:Landmarks,far:boolean,skin:string){
 const t=p.traits; const iris=catalog.colors.eyes[t.eyes],hair=catalog.colors.hair_color[t.hair_color];
 const ink=mix(hair,'#312330',.62),shade=mix(skin,'#623849',.44);
 // Outer corner, upper-lid fullness, lower-lid fullness and medial corner are independent.
 const specs={almond:[-2,11,6,2],open:[0,14,10,1],hooded:[-1,6,5,2],upturned:[-7,10,5,2],
 downturned:[5,10,6,-1],monolid:[-3,7,5,2],deep_set:[0,8,6,3],narrow:[-3,5,3,1]}[t.eye_shape];
 const [outer,up,down,inner]=specs;
 const s=(g.semi?.81:1.04)*(1+.16*g.youth)*(g.old?.79:1)*(t.expression==='surprise'?1.24:t.expression==='smile'?.85:1);
 const u=up*s,d=down*s, w=(g.semi?14.8:17.4)*(far?.78:1);
 const rim=`M${-w} ${outer} Q${-w*.65} ${-u*1.24} 0 ${-u} Q${w*.68} ${-u*.88} ${w} ${inner}`;
 const opening=rim+` Q2 ${d*1.7} ${-w} ${outer}Z`;
 const id=far?'far':'near',r=Math.min(w*.72,(u+d)*.64+1);
 const [arch,thick,tilt,width]={straight:[1,4,0,1],arched:[9,4,2,1],angled:[8,5,-2,1],
 fine:[7,2,1,1],bushy:[5,7,1,1.1],tapered:[5,4,-3,1],short:[3,5,1,.78],low:[2,6,-2,1]}[t.brows];
 const by=-u-(g.semi?8:10)+(t.expression==='surprise'?-6:0);
 const emotion=t.expression==='frown'?5:['sad','shy'].includes(t.expression)?-5:0;
 const brow=`M${-w*width-2} ${by+tilt+1}Q${-w*.62} ${by-arch} ${-w*.19} ${by-arch-thick*.48}Q4 ${by-arch-thick*.51} ${w*.85} ${by-1+emotion}Q${w*.98} ${by+thick*.35+emotion} ${w*.69} ${by+thick*.44+emotion}Q-1 ${by-arch*.72} ${-w*.21} ${by-arch*.64}Z`;
 const cx=far?1:-1;
 return `<g transform="translate(${far?g.eyeSpace+11:-g.eyeSpace+4} ${far?-1:0}) scale(${far?-1:1} 1)">
 <defs><clipPath id="eye-${id}"><path d="${opening}"/></clipPath></defs>`+
 (g.semi?path(`M${-w-4} 0Q${-w} ${-u-14} ${w+2} ${-u-5}L${w+1} 1Q0 ${-u*1.5} ${-w-4} 0Z`,shade,.23):'')+
 path(opening,mix(skin,'#fff9ef',.86))+`<g clip-path="url(#eye-${id})">
 <circle cx="${cx}" cy="-1" r="${r}" fill="${ink}"/><circle cx="${cx}" cy="-.5" r="${r*.83}" fill="${iris}"/>
 <path d="M${cx-r*.69} 0q${r*.65} ${r*.77} ${r*1.4} -.5q${-r*.48} ${r*1.3} ${-r*1.4} .5" fill="${mix(iris,'#ffdfa2',.52)}"/>
 <ellipse cx="${cx}" cy="-1" rx="${r*.39}" ry="${r*.62}" fill="${ink}"/>
 <circle cx="${cx+(far?2.3:-2.3)}" cy="${-r*.46}" r="${g.semi?1.55:2.55}" fill="#fff9e8"/>
 </g>`+line(rim,ink,g.semi?2.0:3.25,.97)+path(`M${-w+6} ${outer-4} Q${-w} ${outer+1} ${-w-4} ${outer-4} Q${-w-2} ${outer+2} ${-w+1} ${outer+2}Z`,ink)+
 line(`M${-w+1} ${outer+2}Q${-w*.5} ${d+2} -2 ${d+.4}`,shade,.95,.8)+
 (t.eye_shape==='monolid'?'':line(`M${-w+2} ${outer-5}Q-2 ${-u-7} ${w-3} ${-u*.62-2}`,shade,t.eye_shape==='hooded'?2:1,.76))+
 path(brow,mix(hair,'#3e2c34',.38))+
 (g.semi?line(`M${w*.6} ${by+emotion}l-2-2m-1 1 -3-3m-1 1 -3-2`,mix(hair,'#352d36',.65),.7,.75):'')+
 (g.mature?line(`M${-w-1} ${outer+5}q5 6 11 6m-10 2q6 5 14 3`,shade,1,.6):'')+'</g>';
}
function nose(p:Illustration,g:Landmarks,ny:number,skin:string){
 const [w,projection,bridge]= {straight:[8,5,1],rounded:[10,5,0],arched:[8,8,3],upturned:[7,4,-3],broad:[13,4,-2],fine:[6,5,1]}[p.traits.nose_shape];
 const x=g.semi?14:13, sh=mix(skin,'#643747',.45),light=mix(skin,'#fff0d0',.46);
 return `<g transform="translate(${x} 0)">`+
 (g.semi?path(`M2 -2Q${3+bridge} 13 ${projection+4} ${ny-6}Q${w+5} ${ny-2} ${w} ${ny+1}Q1 ${ny+6} ${-w} ${ny+1}Q-3 ${ny-2} -1 ${ny-7}Q4 14 2 -2Z`,'url(#nosePlane)'):
 path(`M2 9Q4 ${ny-7} ${projection+3} ${ny-4}L3 ${ny+2}L-4 ${ny}Q2 ${ny-5} 2 9Z`,sh,.45))+
 line(`M${projection} ${ny-11}q${projection} 8 2 9`,sh,1.3,.74)+
 path(`M${-w} ${ny+1}q3 -3.4 6 .4q-3 1 -6 -.4Zm${w+7} -1q2 -2 4 -1q0 2 -4 1Z`,mix(sh,'#3a2630',.38))+
 (g.semi?line(`M${2+bridge} 3C${2+bridge} 13 ${projection} ${ny-13} ${projection+4} ${ny-7}Q${projection+7} ${ny-3} ${projection+4} ${ny-1}`,mix(skin,'#794740',.61),1.45,.85)+
 path(`M${-w-2} ${ny-3}q2-5 5-4q-3 1-3 4q0 4 5 5q-9-.5-7-5Z`,sh,.55)+line(`M1 ${ny-5}q3 -2 5 -1`,light,2,.86):'')+'</g>';
}
export function illustratedFace(p:Illustration,g:Landmarks){
 const {temple:a,cheek:c,jaw:j,chin:k,length:h,crown}=g,t=p.traits,skin=catalog.colors.skin[t.skin];
 const ink=mix(skin,'#472831',.62),sh=mix(skin,'#774351',.45),light=mix(skin,'#fff0ce',.32);
 const outline=`M${-a} -4C${-a-8} ${crown*1.28} ${a-4} ${crown*1.35} ${a+1} -12Q${a} 0 ${c-1} 12C${c+1} 25 ${j+8} ${h*.55} ${j+2} ${h*.66}Q${j-2} ${h*.83} ${12+k} ${h-3}Q14 ${h+3} ${10-k} ${h-1}C${-j*.32} ${h*.96} ${-j*.90} ${h*.78} ${-j} ${h*.64}C${-c+1} ${h*.44} ${-a+1} 15 ${-a} -4Z`;
 const ny=h*(g.semi?.455:.405),my=h*(g.semi?.708:.67);
 const [mw,upper,lower]={defined:[15,4,4],full:[16,6,7],fine:[14,1.5,2],wide:[20,3,3],bow:[12,5,4],lower_full:[15,2,7]}[t.lip_shape];
 const w=mw*(1-.17*g.youth),bend=t.expression==='smile'?5:t.expression==='sad'||t.expression==='frown'?-3:1;
 const lips=mix(skin,'#9d4657',g.semi?.56:.45);
 const ear=(far:boolean)=>`<g transform="translate(${far?a-3:-a+3} 7) scale(${far?-0.7:1} 1)">`+
 path('M2 2C-4-10-15-12-15-2Q-16 10-6 21Q1 26 5 14Z',skin)+line('M-12-2Q-5-8-1 5Q-9 3-6 13M-5 17l3 1',ink,1.6,.6)+'</g>';
 const mouth=`<g transform="translate(11 ${my})">`+path(`M${-w} 0Q-7 ${-upper-1} -2 ${-upper}Q1 ${-upper+2} 3 ${-upper-.4}Q7 ${-upper} ${w} -1Q1 ${bend+lower*1.75} ${-w} 0Z`,lips,g.semi?.9:.68)+
 (t.expression==='surprise'?`<ellipse cx="1" cy="1" rx="${w*.43}" ry="4.6" fill="${ink}"/>`:line(`M${-w} 0Q-5 ${bend*.8} 0 ${bend}Q8 ${bend+1} ${w} -1`,ink,g.semi?1.25:1.6,.94))+
 line(`M-4 ${lower+bend}q4 1.4 8 -1`,light,1.5,.85)+'</g>';
 const cheek=`M${a+3} -35Q${a-9} -10 ${a-11} 3Q${c-5} 18 ${j-4} ${h*.55}Q${j-6} ${h*.67} ${k+9} ${h-5}L6 ${h+4}H85V-45Z`;
 return {outline,ny,my,art:ear(true)+ear(false)+path(outline,g.semi?'url(#complexion)':skin)+line(outline,ink,g.semi?1:1.6,.9)+
 `<defs><clipPath id="face"><path d="${outline}"/></clipPath></defs><g clip-path="url(#face)">`+
 path(cheek,g.semi?'url(#halfTone)':sh,g.semi?.70:.54)+
 (g.semi?`<ellipse cx="-23" cy="21" rx="33" ry="16" opacity=".38" fill="url(#cheekLight)"/>`:path('M-47 20q14-8 27-6q-10 5-25 9Z',light,.4))+
 (g.semi?`<ellipse cx="-43" cy="32" rx="19" ry="27" fill="url(#cheekContour)"/><ellipse cx="42" cy="20" rx="18" ry="16" fill="url(#cheekContour)"/>`+path('M9 5Q15 4 18-2Q16 10 18 18Q11 16 9 5Z',sh,.34):'')+
 (g.mature?path(`M-46 10q12 12 31 6q-13 11-28 3Z M24 13q10 5 21 -3q-5 13-18 11Z`,sh,g.old?.37:.16)+
 line(`M-42 18q12 7 21 4M-9 ${ny+5}q-7 5-8 14`,sh,g.old?1.6:1,.63):'')+
 (g.old?line(`M-42 14q10 9 23 6m39 -2q13 3 21 -5M-2 ${ny+2}q-8 7-10 18m39 -18q7 6 8 14M-25 -39q17 -5 34 -2m-27 8q11 -2 19 -1`,ink,1.25,.53):'')+
 eye(p,g,false,skin)+eye(p,g,true,skin)+nose(p,g,ny,skin)+mouth+
 (t.expression==='shy'?path('M-47 16q13-5 22 3q-13 6-22-3Zm83-1q11-5 18-1q-8 8-18 1Z','#cd686b',.45):'')+'</g>'};
}

