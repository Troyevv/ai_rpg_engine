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

it('keeps the v2 plate intact through a layer-preserving v3 preview',()=>{
 const expected='dc15c13e5fa7cdb828dd3f5e167630736b781ee132b856c56a15f7fc46c68d36';
 expect(createHash('sha256').update(svg(modern)).digest('hex')).toBe(expected);
 expect(svg({...modern,version:3,base_version:2})).toBe(svg(modern));
 expect(svg({...legacy,version:3,base_version:1,body_frame:'neutral',facial_hair:'clean_shaven'})).toBe(svg(legacy));
});

it('preserves approved v3 faces until a revised face is chosen',()=>{
 const art={...modern,version:3,base_version:2,hairstyle:'short',garment:'shirt',visage:'broad'} as const;
 expect(createHash('sha256').update(svg(art)).digest('hex')).toBe('8cfa54629097ce5e4515c2b66f7bd04164421d77b32949e6a26ec4f6439565af');
 const revision21=svg({...art,face_revision:2});
 expect(createHash('sha256').update(revision21).digest('hex')).toBe('7514857b217d039f4671d76f78d669e574abab76bd7791864b1d88116a0ddb85');
 const current={...art,face_revision:3} as const;
 expect(svg(current)).not.toBe(revision21);
 for(const body_frame of ['female','male','neutral'] as const){
  const options=['straight','arched','rounded'].map(nose_shape=>svg({...current,body_frame,nose_shape} as ProceduralPortrait));
  expect(new Set(options).size).toBe(3);
 }
});

it('keeps the master revision 3 drawing byte-for-byte after adding the classic fits',()=>{
 const pinned = {version:3,form:'human',stage:'adult',seed:'ab'.repeat(16),face:0,hair:0,clothing:0,
  skin:2,eyes:3,accessory:0,palette:1,body_frame:'male',facial_hair:'short_beard',
  visage:'broad',hairstyle:'curly',garment:'jacket',face_revision:3} as const;
 expect(createHash('sha256').update(svg(pinned)).digest('hex'))
  .toBe('a7f630b8518dbc1c66ecb359b9727bd3ff2cdb0be78a6c86fb998df4a722f445');
});

it('projects both pupils onto one baseline with one gaze vector and iris diameter',()=>{
 for(const revision of [3,4] as const) for(const eye_shape of ['open','hooded','almond'] as const) {
  for(const byte of ['00','7f','ff']) {
   const art={...modern,version:3,face_revision:revision,eye_revision:2,eye_shape,seed:byte.repeat(16)} as const;
   const doc=new DOMParser().parseFromString(svg(art),'image/svg+xml');
   const measurements=['far-orbit','near-orbit'].map(id=>{
    const group=doc.getElementById(id)!.parentElement!.parentElement!;
    const [,x,y,scale]=group.getAttribute('transform')!.match(/translate\(([-.\d]+) ([-.\d]+)\) scale\(([-.\d]+) 1\)/)!.map(Number);
    const pupil=group.querySelector('ellipse[fill="#292725"]')!;
    return {x,y:y+Number(pupil.getAttribute('cy')),offset:scale*Number(pupil.getAttribute('cx')),
            radius:Math.abs(scale)*Number(pupil.getAttribute('rx')),scale};
   });
   const [far,near]=measurements;
   expect(near.x).toBeGreaterThan(far.x);
   expect(Math.abs(far.scale)).toBeLessThan(near.scale);
   expect(far.y).toBe(near.y);
   expect(far.offset).toBeCloseTo(near.offset,9);
   expect(far.radius).toBeCloseTo(near.radius,9);
  }
 }
});
