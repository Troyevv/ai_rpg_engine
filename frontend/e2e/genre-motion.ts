// Standalone browser function: Playwright serializes it without module closures.
export function observeGenreMotion() {
 const samples:{opacity:number;transform:string;elapsed:number}[]=[];
 (window as any).genreMotion=samples;
 const observer=new MutationObserver(()=>{
  const node=document.querySelector('.genre-results');if(!node)return;observer.disconnect();
  const start=performance.now();
  const frame=()=>{
   const css=getComputedStyle(node),elapsed=performance.now()-start;
   samples.push({opacity:Number(css.opacity),transform:css.transform,elapsed});
   // A 350 ms observation window does not guarantee five animation frames.
   // Keep the window AND the required samples; the E2E poll still bounds waiting.
   if(elapsed<350 || samples.length<5)requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
 });
 observer.observe(document.querySelector('.genre-settings')!,{childList:true});
}
