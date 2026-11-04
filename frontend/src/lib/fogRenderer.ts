/** Shared, capped animation clock; no per-row timers or work for offscreen rows.
 * A periodic multi-octave density field is rasterized once. Only three textured
 * layers are composited per frame, rather than recomputing noise per pixel.
 */
type Paint=(time:number)=>void;
const painters=new Set<Paint>();let frame=0,last=0;
function tick(time:number){
 frame=0;
 if(document.hidden||!painters.size)return;
 if(time-last>=1000/24){last=time;for(const paint of painters)paint(time)}
 frame=requestAnimationFrame(tick);
}
function resume(){if(!document.hidden&&painters.size&&!frame)frame=requestAnimationFrame(tick)}
if(typeof document!=='undefined')document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(frame);frame=0}else resume()});
export function animateFog(paint:Paint){painters.add(paint);resume();return()=>{painters.delete(paint);if(!painters.size){cancelAnimationFrame(frame);frame=0}}}
let texture:HTMLCanvasElement|undefined;
function densityTexture(){
 if(texture)return texture;
 texture=document.createElement('canvas');texture.width=256;texture.height=128;
 const ctx=texture.getContext('2d')!;const pixels=ctx.createImageData(256,128);
 const hash=(x:number,y:number)=>{const v=Math.sin(x*127.1+y*311.7+19.3)*43758.5453;return v-Math.floor(v)};
 const smooth=(v:number)=>v*v*(3-2*v);
 const noise=(u:number,v:number,n:number)=>{
  const x=u*n,y=v*n,ix=Math.floor(x),iy=Math.floor(y),fx=smooth(x-ix),fy=smooth(y-iy);
  const a=hash(ix%n,iy%n),b=hash((ix+1)%n,iy%n),c=hash(ix%n,(iy+1)%n),d=hash((ix+1)%n,(iy+1)%n);
  return (a*(1-fx)+b*fx)*(1-fy)+(c*(1-fx)+d*fx)*fy;
 };
 for(let y=0;y<128;y++)for(let x=0;x<256;x++){
  const u=x/256,v=y/128;let value=0,weight=0;
  const warpX=noise(u,v,4)*.12,warpY=noise((u+.37)%1,(v+.13)%1,4)*.14;
  for(let octave=0;octave<5;octave++){const w=2**(-octave);value+=noise((u+warpX)%1,(v+warpY)%1,4*2**octave)*w;weight+=w}
  value=value/weight;const i=(y*256+x)*4;
  pixels.data[i]=pixels.data[i+1]=pixels.data[i+2]=235;
  pixels.data[i+3]=Math.round(Math.max(0,(value-.25))*210);
 }
 ctx.putImageData(pixels,0,0);return texture;
}
export function paintFog(canvas:HTMLCanvasElement,time:number,phase:number,reveal=0){
 const ctx=canvas.getContext('2d');if(!ctx)return;
 const {width:w,height:h}=canvas;const img=densityTexture();
 ctx.clearRect(0,0,w,h);
 ctx.globalAlpha=1-reveal;
 // The base veil thins with the same curve as the textured volume.
 ctx.fillStyle=getComputedStyle(canvas).getPropertyValue('--fog-base').trim()||'#30343b';
 ctx.fillRect(0,0,w,h);
 for(let layer=0;layer<3;layer++){
  const speed=(layer%2?-1:1)*(0.009+layer*.004);
  const tileWidth=Math.max(h*3,w*.65);
  const x=((time*speed+phase*47+layer*91)%tileWidth+tileWidth)%tileWidth;
  const y=Math.sin(time*.00013+phase+layer*2)*h*.17;
  const spread=reveal*reveal*w*(layer%2?1:-1)*.8;
  ctx.globalAlpha=(.52-layer*.1)*(1-reveal)**1.5;
  for(let tile=-2;tile<=Math.ceil(w/tileWidth)+1;tile++)ctx.drawImage(img,x+tile*tileWidth+spread,-h*.3+y,tileWidth,h*1.6);
 }
 if(reveal>0){
  ctx.globalCompositeOperation='destination-out';ctx.globalAlpha=1;
  const radius=Math.max(w,h)*reveal;
  const gradient=ctx.createRadialGradient(w*.5,h*.5,0,w*.5,h*.5,Math.max(1,radius));
  gradient.addColorStop(0,'rgba(0,0,0,1)');gradient.addColorStop(.4,'rgba(0,0,0,.9)');gradient.addColorStop(1,'rgba(0,0,0,0)');
  ctx.fillStyle=gradient;ctx.fillRect(0,0,w,h);ctx.globalCompositeOperation='source-over';
 }
 ctx.globalAlpha=1;
}
