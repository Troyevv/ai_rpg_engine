import {describe,it,expect} from 'vitest';
import {proceduralPortrait,type ProceduralPortrait} from '../src/workshop/proceduralPortrait';
const base:ProceduralPortrait={version:1,seed:'a'.repeat(32),form:'human',stage:'adult',face:0,hair:0,skin:0,eyes:0,clothing:0,accessory:0,palette:0};
describe('versioned workshop illustrations',()=>{
 it('colors hair and clothing independently without changing the default rendering',()=>{
  const before=proceduralPortrait({...base,hair:0,clothing:2});
  const changed=proceduralPortrait({...base,hair:0,clothing:2,hair_color:2,clothing_color:0});
  const svg=decodeURIComponent(changed!);
  expect(changed).not.toBe(before);
  expect(svg).toContain('#e5ca93');expect(svg).toContain('#393b40');
  expect(svg).not.toContain('#93a18a'); // no original sage collar on the recolored shirt
  expect(proceduralPortrait({...base,hair_color:99})).toBeNull();
 });
 it('keeps an exact deterministic image across repeated calls and varied faces',()=>{
  const svg=proceduralPortrait(base);expect(svg).toBe(proceduralPortrait({...base}));
  expect(proceduralPortrait({...base,hair:7})).not.toBe(svg);
  expect(proceduralPortrait({...base,form:'neutral'})).not.toBe(svg);
  expect(decodeURIComponent(svg!)).toContain('viewBox="0 0 400 500"');
 });
 it('does not accept remote SVG, injected fields, unsupported versions or indices',()=>{
  for(const malformed of [{version:2},{seed:'<svg onload=alert(1)>'},{face:-1},{hair:8},{form:'<img>'},{eyes:NaN}])expect(proceduralPortrait({...base,...malformed} as ProceduralPortrait)).toBeNull();
  const injected={...base,body:'<script>bad</script>',frontHair:'https://example.com/face'};
  expect(proceduralPortrait(injected)).toBe(proceduralPortrait(base));
  expect(decodeURIComponent(proceduralPortrait(injected)!)).not.toMatch(/<script|https:\/\/example/);
 });
 it('supports hundreds of identities without mutating input or using a network resource',()=>{
  const before=JSON.stringify(base);for(let i=0;i<600;i++)expect(proceduralPortrait({...base,seed:i.toString(16).padStart(32,'0')})).toMatch(/^data:image\/svg\+xml/);
  expect(JSON.stringify(base)).toBe(before);expect(proceduralPortrait(base)).toBe(proceduralPortrait({...base}));
 });
});

import {renderToStaticMarkup} from 'react-dom/server';
import {CharacterAvatar} from '../src/Portrait';
it('neutral descriptors use the identical game avatar and initials',()=>{
 const subject={id:'ilya',name:'Илья Соколов',silhouette:'male'};
 const plain=renderToStaticMarkup(<CharacterAvatar subject={subject}/>);
 const neutral=renderToStaticMarkup(<CharacterAvatar subject={{...subject,procedural_portrait:{...base,form:'neutral'}}}/>);
 expect(neutral).toBe(plain);expect(neutral).toContain('ИС');expect(neutral).toContain('data-silhouette="male"');
 expect(proceduralPortrait({...base,form:'neutral'})).toBeNull();
 expect(decodeURIComponent(proceduralPortrait({...base,eyes:7})!)).toContain('#6f8998');
});
