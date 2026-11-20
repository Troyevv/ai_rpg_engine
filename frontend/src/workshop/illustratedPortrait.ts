import {shape as path,seam as line} from './portraitWardrobe';
import {paintedHair} from './illustratedHair';
import {illustratedFace,landmarks} from './illustratedFace';
import {illustratedCostume} from './illustratedCostume';
import {illustrationCatalog as catalog,mix,type Illustration,type Traits} from './illustration';

const grounds=[['#e8d8b6','#a88d7e'],['#c8d9ce','#748787'],['#efcfc2','#ad858d'],['#d5d0e4','#8d889d'],['#e1d9b4','#9d9c7c'],['#c7dce2','#7894a8'],['#ead6b4','#ac9377']];
function wash(id:string,stops:string[],soft:boolean){
 return `<linearGradient id="${id}" ${id==='hairMass'?'gradientUnits="userSpaceOnUse" x1="-53" y1="-78" x2="60" y2="44"':'x2="85%" y2="68%"'}>${stops.map((col,i)=>`<stop offset="${soft?i/(stops.length-1):[0,.54,.55,1][i]}" stop-color="${col}"/>`).join('')}</linearGradient>`;
}
type G=ReturnType<typeof landmarks>;
const extraCuts={afro:'curly',twists:'parted',twin_buns:'bun',braided_crown:'parted',wolf:'pixie',ringlets:'curly',quiff:'undercut',low_tail:'parted'} as const;
function locks(t:Traits,g:G,hair:string){
 const cut=t.hair,base=cut in extraCuts?extraCuts[cut as keyof typeof extraCuts]:cut as Parameters<typeof paintedHair>[0];
 const light=mix(hair,'#f3d9b6',.45),dark=mix(hair,'#222033',.58);
 const tuft=paintedHair(base,g.temple,g.crown,light,dark,g.semi);
 const contour=(d:string)=>path(d,'url(#hairMass)')+line(d,dark,g.semi?.85:1.45,.85);
 const spiral=(x:number,y:number,size:number)=>`<g transform="translate(${x} ${y}) scale(${size})">`+contour('M-9-13C-25-13-26 9-14 14C-6 25 14 20 17 9C30-5 14-24 0-19Z')+line('M-15-4q4-14 16-10m-6 16q6 7 13-1',light,1.6,.68)+'</g>';
 const rope=(x:number,y:number,n:number,curve:number)=>Array.from({length:n},(_,i)=>spiral(x+Math.sin(i*.65)*curve,y+i*11,.56-i*.019)).join('');
 switch(cut){
 case 'twin_buns':return {back:spiral(-55,-73,1.35)+spiral(57,-72,1.35),front:paintedHair('parted',g.temple,g.crown,light,dark,g.semi).front};
 case 'afro':return {back: Array.from({length:17},(_,i)=>{const a=Math.PI*(.96+i/15);return spiral(Math.cos(a)*(g.temple+6),-19+Math.sin(a)*64,1.1)}).join(''),front:tuft.front};
 case 'twists':return {back:rope(-63,-12,10,4)+rope(58,-20,11,5),front:tuft.front+rope(-44,-42,11,3)+rope(49,-42,8,4)};
 case 'braided_crown':return {back:'',front:tuft.front+Array.from({length:13},(_,i)=>spiral(-56+i*9,-48-Math.sin(i*Math.PI/12)*27,.49)).join('')};
 case 'wolf':return {back:contour('M-52-51Q-64-23-61 8Q-59 29-76 41L-64 39 -75 58 -61 52 -64 72 -36 51 39 48 69 65 65 48 77 54 65 34 73 40Q58 14 64-21Z'),front:tuft.front};
 case 'ringlets':return {back:[-66,-54,50,66].map((x,i)=>rope(x,-21,12-i%2,6)).join(''),front:tuft.front+rope(-54,-16,6,4)};
 case 'quiff':return {back:'',front:tuft.front+contour('M-59-40Q-83-89-37-100Q-56-91-54-80Q-25-118 19-107Q8-104 3-97Q42-102 59-78Q20-88-8-58Q-33-30-59-40Z')+line('M-48-57Q-30-89 6-95m-41 36q21-25 51-30',light,1.6,.55)};
 case 'low_tail':return {back:contour('M-47 11Q-82 13-73 52Q-64 95-92 112Q-47 125-44 84Q-31 42-42 32Z')+line('M-67 38q18 50-10 68',light,2,.7),front:tuft.front};
 default:{
  const loose=['long','wavy','medium','bob'].includes(cut);
  const side=loose?contour('M-48-47Q-66-28-59 5Q-53 28-60 39Q-47 31-48 9Q-54-15-39-36Z')+
    line('M-50-34q-9 18-4 41',light,1.2,.65):'';
  const bangs=['short','pixie','wolf','undercut','parted'].includes(cut)?
    path('M1-71Q8-39-23-22Q-12-38-15-46Q-27-27-45-22Q-41-40-25-56Z','url(#hairMass)')+
    line('M-20-48q-7 13-19 21m34-32q-1 17-13 30',light,1.3,.55):'';
  return {...tuft,front:tuft.front+side+bangs};
 }
 }
}
function beard(t:Traits,g:G,ny:number,my:number){
 if(t.facial_hair==='clean_shaven'||g.youth)return '';
 const hair=catalog.colors.hair_color[t.hair_color],shade=mix(hair,'#40313a',.32),h=g.length,j=g.jaw,c=g.cheek;
 const moustache=path(`M11 ${ny+7}Q4 ${ny+2} -4 ${my-7}Q-8 ${my-3} -12 ${my-2}Q0 ${my-1} 11 ${my-8}Q19 ${my-3} 31 ${my-4}Q25 ${ny+7} 17 ${ny+5}Z`,shade);
 const sides=`M${-c-3} -4Q${-c+12} 15 ${-j+9} ${h*.52}Q${-j+20} ${h*.72} 0 ${my+4}Q12 ${my+13} 23 ${my+3}Q${j} ${my+4} ${c+3} 8L88 18V123H-86Z`;
 const chin=path(`M0 ${my+8}Q11 ${my+15} 22 ${my+7}L24 ${h-4}Q11 ${h+7} -2 ${h-4}Z`,shade);
 const texture=Array.from({length:45},(_,i)=>{const x=-j+(i*23%97)/97*j*2,y=my-6+((i*17)%41);return `M${x} ${y}l1.3 2.5`}).join('');
 let art='';
 switch(t.facial_hair){
 case 'mustache':art=moustache;break;
 case 'short_beard':case 'full_beard':case 'stubble':art=path(sides,shade,t.facial_hair==='stubble'?.18:t.facial_hair==='short_beard'?.73:1)+`<defs><clipPath id="beard"><path d="${sides}"/></clipPath></defs><g clip-path="url(#beard)">`+line(texture,t.facial_hair==='stubble'?shade:mix(hair,'#edcaa4',.42),1,.7)+'</g>'+(t.facial_hair==='stubble'?'':moustache);break;
 case 'sideburns':art=path(`M${-c-5} -12l12 4 8 37 -5 10 -13 -16Z M${c+2} -8l-6 1 -4 35 7 -5Z`,shade);break;
 case 'anchor':art=moustache+chin+line(`M-15 ${h-13}Q12 ${h+5} 35 ${h-14}`,shade,6);break;
 case 'goatee':art=chin+moustache;break;
 }
 return `<g clip-path="url(#face)">${art}</g>`+(t.facial_hair==='full_beard'?path(`M${-j} ${h*.62}Q-13 ${h+10} 10 ${h+11}Q27 ${h+8} ${j+4} ${h*.67}Q35 ${h-1} 12 ${h-5}Q-11 ${h-2} ${-j} ${h*.62}Z`,shade):'');
}
function details(t:Traits,g:G,ny:number){
 const metal=mix(catalog.colors.clothing_color[t.trim],'#d9b367',.55),near=4-g.eyeSpace,far=g.eyeSpace+9;
 const ring=(x:number,y:number,r:number)=>`<circle cx="${x}" cy="${y}" r="${r}" fill="none" stroke="${metal}" stroke-width="1.8"/>`;
 const dot=(x:number,y:number,r:number,col:string)=>`<circle cx="${x}" cy="${y}" r="${r}" fill="${col}"/>`;
 const ink=mix(catalog.colors.skin[t.skin],'#63332e',.65);
 switch(t.detail){
 case 'round_specs':case 'square_specs':case 'cat_specs':{
 const lens=t.detail==='round_specs'?'M-19 0c0-21 38-21 38 0s-38 23-38 0Z':t.detail==='square_specs'?'M-19-10q18-3 38-1l-2 18q-17 6-33 0Z':'M-24-14Q-11-12 18-9Q21 6 8 10Q-12 17-24-14Z';
 return [near,far].map((x,i)=>`<g transform="translate(${x} 0) scale(${i?-.84:1} 1)">`+path(lens,'#d4ecf0',.14)+line(lens,'#423b44',2.1,.97)+'</g>').join('')+line(`M${near+19} -3Q6 -10 ${far-15} -3M${near-19} -5L${-g.temple} -8`,'#473f48',2);}
 case 'freckles':return Array.from({length:23},(_,i)=>dot(-42+(i*19%94),12+Math.sin(i)*3+(i%3)*1.5,.8+i%2*.35,ink)).join('');
 case 'mole':return dot(-24,31,1.8,ink);
 case 'brow_scar':return line(`M${near-6} -29l4 11`,catalog.colors.skin[t.skin],2.2,1);
 case 'cheek_scar':return line('M-44 17q5 10 15 16',ink,1.6,.68)+line('M-44 16q6 10 16 15','#ebc8b8',.8);
 case 'hoops':return ring(-g.temple-2,31,7)+ring(g.temple-1,29,5);
 case 'drops':return [-g.temple-2,g.temple].map(x=>line(`M${x} 26v10`,metal,1.6)+path(`M${x} 33q-9 12 0 13q9-2 0-13Z`,metal)).join('');
 case 'studs':return dot(-g.temple-3,25,3.1,metal)+dot(g.temple,24,2.5,metal);
 case 'nose_ring':return ring(9,ny+2,3.1);
 case 'hairpin':return line('M-58-32l14-9m-11 14 15-9',metal,2.8);
 default:return '';
 }
}
export function illustratedPortrait(p:Illustration){
 const t=p.traits,skin=catalog.colors.skin[t.skin],hair=catalog.colors.hair_color[t.hair_color],cloth=catalog.colors.clothing_color[t.clothing_color];
 const g=landmarks(p),shadow=mix(skin,'#723b50',.46),light=mix(skin,'#ffebce',.32);
 const [bg1,bg2]=grounds[p.palette];
 const head=`translate(${g.eyeX} ${g.eyeY}) scale(${g.headScale})`;
 const {art,ny,my}=illustratedFace(p,g),locksArt=locks(t,g,hair);
 const defs=wash('ground',[bg1,bg2],true)+wash('complexion',[light,skin,skin,shadow],true)+wash('halfTone',[skin,shadow],true)+
 wash('neckShadow',[shadow,mix(skin,shadow,.55)],true)+wash('nosePlane',[skin,shadow],true)+
 wash('hairMass',[mix(hair,'#ead8c6',.19),hair,mix(hair,'#262231',.23),mix(hair,'#201b2a',.54)],true)+
 wash('fabric',[mix(cloth,'#f7e4be',.22),cloth,mix(cloth,'#382b40',.22),mix(cloth,'#242335',.48)],true)+
 `<radialGradient id="cheekContour"><stop stop-color="${mix(skin,'#875650',.55)}" stop-opacity=".53"/><stop offset="1" stop-color="${skin}" stop-opacity="0"/></radialGradient><radialGradient id="cheekLight"><stop stop-color="${light}"/><stop offset="1" stop-color="${light}" stop-opacity="0"/></radialGradient>
 <pattern id="mail" width="8" height="6" patternUnits="userSpaceOnUse"><path d="M0 0q2 7 5 0m0 3q2 6 5 0" fill="none" stroke="${mix(cloth,'#fff4cd',.5)}" stroke-width="1.4"/></pattern>`;
 const backdrop=`<rect width="400" height="500" fill="url(#ground)"/>`+path('M0 0H140L0 280Z M160 0H186L0 360V306Z','#fff8e8',.16);
 return `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500" viewBox="0 0 400 500"><title>Иллюстрация персонажа</title><defs>${defs}</defs>${backdrop}<g transform="${head}">${locksArt.back}</g>${illustratedCostume(p,g)}<g transform="${head}">${art}${beard(t,g,ny,my)}${locksArt.front}${details(t,g,ny)}</g></svg>`;
}

