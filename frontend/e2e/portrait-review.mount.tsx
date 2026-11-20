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

export async function render(cases: ReviewCase[], revision: 3 | 4, fullSize: boolean) {
  const rootElement = document.getElementById('review')!;
  const width = fullSize ? 400 : 160;
  const columns = Math.min(fullSize ? 3 : 6, cases.length);
  rootElement.style.cssText = `display:grid;grid-template-columns:repeat(${columns},${width}px);gap:8px;padding:8px;width:max-content;background:#eee9df;color:#262323`;
  const root = createRoot(rootElement);
  root.render(<>{cases.map(({label, portrait}, i) => {
    const card = { id: String(i), name: label, fields: {}, procedural_portrait: {...portrait, face_revision: revision} };
    return <article key={card.id}>
      {fullSize ? <div style={{width:400,height:500}} className="ww-card-art">
        <CharacterAvatar subject={card} size="100%" framing="plate"/>
      </div> : <CharacterCard card={card} wid="review" author={false} onOpen={()=>{}}/>}
      <div style={{display:'flex',alignItems:'center',gap:6,marginTop:4,fontSize:12}}>
        <CharacterAvatar subject={card} size={48}/>{fullSize ? label : null}
      </div>
    </article>;
  })}</>);
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
