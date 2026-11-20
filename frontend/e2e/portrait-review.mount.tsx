import { createRoot } from 'react-dom/client';
import { CharacterAvatar } from '../src/Portrait';
import { CharacterCard } from '../src/workshop/CharacterCollection';
import type { LegacyPortrait } from '../src/workshop/proceduralPortrait';
import '../src/index.css';
import '../src/styles/world-workshop.css';

interface ReviewCase {
  label: string;
  portrait: Extract<LegacyPortrait, {version: 3}>;
}

export async function render(cases: ReviewCase[], revision: 3 | 4 | 'current' | 'original-eyes' | 'aligned-eyes', fullSize: boolean) {
  const rootElement = document.getElementById('review')!;
  const width = fullSize ? 400 : 160;
  const columns = Math.min(fullSize ? 3 : 6, cases.length);
  rootElement.style.cssText = `display:grid;grid-template-columns:repeat(${columns},${width}px);gap:8px;padding:8px;width:max-content;background:#eee9df;color:#262323`;
  if (!fullSize && window.innerWidth<=393) {
    rootElement.classList.add('ww-content');
    rootElement.style.cssText='width:100%;background:#eee9df;color:#262323';
  }
  const root = createRoot(rootElement);
  const mobile = !fullSize && window.innerWidth<=393;
  root.render(<div className={mobile?'ww-characters-grid':undefined} style={mobile?{paddingInline:18}:{display:'contents'}}>{cases.map(({label, portrait}, i) => {
    const art = {...portrait};
    if (typeof revision==='number') art.face_revision=revision;
    if (revision==='aligned-eyes') art.eye_revision=2;
    if (revision==='original-eyes' || revision===3) delete art.eye_revision;
    const card = { id: String(i), name: label, fields: {}, procedural_portrait: art };
    return <article key={card.id} style={mobile?{display:'grid',gridTemplateColumns:'minmax(0,1fr)',alignContent:'start'}:undefined}>
      {fullSize ? <div style={{width:400,height:500}} className="ww-card-art">
        <CharacterAvatar subject={card} size="100%" framing="plate"/>
      </div> : <CharacterCard card={card} wid="review" author={false} onOpen={()=>{}}/>}
      <div style={{display:'flex',alignItems:'center',gap:6,marginTop:4,fontSize:12}}>
        <CharacterAvatar subject={card} size={48}/>{fullSize ? label : null}
      </div>
    </article>;
  })}</div>);
  // React commits asynchronously. Wait for every visible plate and round frame before capturing.
  await new Promise<void>((resolve, reject) => {
    const deadline = performance.now() + 15000;
    const ready = () => {
      if (rootElement.querySelectorAll('article').length === cases.length) return resolve();
      if (performance.now() > deadline) return reject(new Error('Portrait review did not mount'));
      requestAnimationFrame(ready);
    };
    ready();
  });
  const frames = [...rootElement.querySelectorAll('img')];
  if (frames.length !== cases.length * 2) throw new Error('A descriptor rendered the silhouette fallback');
  for (const frame of frames) frame.loading = 'eager';
  await Promise.all(frames.map(frame => frame.decode()));
}
