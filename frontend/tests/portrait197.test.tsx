import {createHash} from 'node:crypto';
import {expect,it} from 'vitest';
import {proceduralPortrait,type ProceduralPortrait} from '../src/workshop/proceduralPortrait';
import {bodyFrames,facialHairStyles,type BodyFrame} from '../src/workshop/portraitAnatomy';
const legacy:ProceduralPortrait={version:1,seed:'a'.repeat(32),form:'human',stage:'adult',face:4,hair:6,skin:2,eyes:7,clothing:3,accessory:2,palette:5};
const svg=(art:ProceduralPortrait)=>decodeURIComponent(proceduralPortrait(art)!.split(',')[1]);
const modern={...legacy,version:2,body_frame:'neutral',facial_hair:'clean_shaven'} as const;

it('preserves the exact SVG bytes from master for both legacy descriptor shapes',()=>{
 const hash=(p:ProceduralPortrait)=>createHash('sha256').update(svg(p)).digest('hex');
 expect(hash(legacy)).toBe('13d64a9ca65540d91239925b8fd302efecf0d4d33264c4aaf16d8357d4287e94');
 expect(hash({...legacy,visual_age:'elderly',hair_color:3,clothing_color:4,visual_age_mode:'manual'}))
  .toBe('27ffd4a08f30bf0ab22d2fa19e25b46685063a945f21a31caa4bc0489ae4c1ba');
});

it('fits all eight garments on three frames, preserving juvenile proportions',()=>{
 const frames=Object.keys(bodyFrames) as BodyFrame[];
 for(let clothing=0;clothing<8;clothing++){
  const busts=frames.map(body_frame=>svg({...modern,body_frame,clothing}));
  expect(new Set(busts).size).toBe(3);
  for(const visual_age of ['infant','child'] as const)
   expect(new Set(frames.map(body_frame=>svg({...modern,body_frame,clothing,visual_age}))).size).toBe(1);
 }
 expect(proceduralPortrait({...modern,form:'neutral'})).toBeNull();
});

it('fits facial hair to the chosen jaw, beneath front locks and independent of scalp hair',()=>{
 for(let face=0;face<7;face++)for(const hair of [1,6,7]){
  const set=new Set<string>();
  for(const facial_hair of Object.keys(facialHairStyles) as (keyof typeof facialHairStyles)[]){
   const src=svg({...modern,face,hair,facial_hair,hair_color:5});
   expect(src).toContain('#aaa6a0');set.add(src);
   if(['stubble','short_beard','full_beard'].includes(facial_hair)){
    const root=new DOMParser().parseFromString(src,'image/svg+xml');
    const jaw=root.querySelector('#jaw path')!.getAttribute('d');
    expect(root.querySelector('path[fill="url(#skin)"]')!.getAttribute('d')).toBe(jaw);
    if(hair!==7)expect(src.lastIndexOf('url(#hair)')).toBeGreaterThan(src.indexOf('id="jaw"'));
   }
  }
  expect(set.size).toBe(5);
 }
 expect(svg({...modern,visual_age:'adolescent',facial_hair:'full_beard'})).not.toContain('id="jaw"');
 expect(proceduralPortrait({...modern,body_frame:'__proto__'} as unknown as ProceduralPortrait)).toBeNull();
});
