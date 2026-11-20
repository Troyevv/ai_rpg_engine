import {hairCut} from './portraitFigureHair';
import type {HairStyle} from './portraitFigure';
import {shape as path,seam as line} from './portraitWardrobe';
import {mix} from './illustration';

// The contour and parting guide both the cel shapes and the softly lit strands.
// The second, shorter control curve closes each lock into a tapered ink mark.
export function paintedHair(style:HairStyle,temple:number,crown:number,light:string,dark:string,semi:boolean){
 const cut=hairCut(style),color=mix(light,dark,.48);
 const wrap=(art:string)=>`<g transform="scale(${(temple+1)/61} ${-crown/87})">${art}</g>`;
 const painted=(d:string,ink:string)=>path(d,'url(#hairMass)')+line(d,ink,semi?1:1.6,.95);
 const tight=['buzz','receding','curly'].includes(style);
 const swept=['ponytail','bun','braid','undercut','short','pixie'].includes(style);
 function crownLocks(){
   if(tight)return line(cut.strokes||'',light,semi?1:1.6,.62);
   const count=semi?16:8;
   return Array.from({length:count},(_,i)=>{
     const f=i/(count-1),root=swept?-24:8;
     const left=`M${root+f*9} ${-87+f*24}C${-26-f*14} ${-96+f*35} ${-65+f*11} ${-69+f*56} ${-63+f*13} ${-31+f*39}Q${-64+f*14} ${-68+f*43} ${-43+f*6} ${-76+f*34}Q-21 ${-89+f*26} ${root+f*9} ${-87+f*24}Z`;
     const right=`M${root+f*8} ${-89+f*22}Q${48-f*16} ${-101+f*35} ${62+f*7} ${-41+f*38}Q${48-f*5} ${-77+f*33} ${root+f*8} ${-89+f*22}Z`;
     return path(left+right,i%3===0?light:dark,semi?.115:.22);
   }).join('');
 }
 const rear=cut.back?painted(cut.back,dark)+`<defs><clipPath id="rearLocks"><path d="${cut.back}"/></clipPath></defs><g clip-path="url(#rearLocks)">`+
 path('M-68-41Q-48 1-59 52Q-67 95-81 109Q-71 85-67 52Q-60 16-74-10Z M57-33C85-1 60 61 88 108Q58 88 60 31Q64-1 57-33Z',color,.69)+
 line(cut.backLines||'',light,semi?1.6:2.6,.58)+'</g>':'';
 if(!cut.front)return {back:'',front:''};
 const frontal=painted(cut.front,dark)+`<defs><clipPath id="frontLocks"><path d="${cut.front}"/></clipPath></defs><g clip-path="url(#frontLocks)">`+
 path(cut.shine||'',light,semi?.29:.48)+crownLocks()+
 (tight?'':line(cut.strokes||'',dark,semi?1.1:1.6,.56)+line(cut.strokes||'',light,semi?.55:.85,.75))+'</g>';
 return {back:wrap(rear),front:wrap(frontal)};
}

