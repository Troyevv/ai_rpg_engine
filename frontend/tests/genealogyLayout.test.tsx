import {describe,it,expect} from 'vitest';
import {genealogyLayout,PERSON_WIDTH as W,PERSON_HEIGHT as H,relationText} from '../src/lib/genealogyLayout';
import type {Genealogy} from '../src/types';
import {person as node,relation as edge,screenshotFamily} from './fixtures/genealogy';
function verify(g:Genealogy){
 const before=structuredClone(g),layout=genealogyLayout(g),rows=[...layout.positions.entries()];
 for(let i=0;i<rows.length;i++)for(let j=i+1;j<rows.length;j++){const a=rows[i][1],b=rows[j][1];expect(a.x+W<=b.x||b.x+W<=a.x||a.y+H<=b.y||b.y+H<=a.y).toBe(true)}
 for(const c of layout.connections)for(const path of c.paths)for(let i=1;i<path.length;i++){
  const a=path[i-1],b=path[i];
  for(const [id,r] of rows)expect(Math.max(a.x,b.x)>r.x&&Math.min(a.x,b.x)<r.x+W&&Math.max(a.y,b.y)>r.y&&Math.min(a.y,b.y)<r.y+H,`${c.id} through ${id}`).toBe(false);
 }
 const labelBoxes=layout.connections.map(c=>({x:c.at.x-68,y:c.at.y-13,w:136,h:26}));
 for(let i=0;i<labelBoxes.length;i++){
  const a=labelBoxes[i];
  for(const b of [...rows.map(([,p])=>({...p,w:W,h:H})),...labelBoxes.slice(i+1)])expect(a.x+a.w<=b.x||b.x+b.w<=a.x||a.y+a.h<=b.y||b.y+b.h<=a.y).toBe(true);
 }
 // Independent intersection test across distinct semantic connections. Shared
 // junctions inside a parent unit are intentional; unrelated overlaps are not.
 for(let i=0;i<layout.connections.length;i++)for(let j=i+1;j<layout.connections.length;j++){
  const segs=(c:typeof layout.connections[number])=>c.paths.flatMap(p=>p.slice(1).map((b,k)=>[p[k],b]));
  for(const [a,b] of segs(layout.connections[i]))for(const [c,d] of segs(layout.connections[j])){
   const vertical=a.x===b.x,otherVertical=c.x===d.x;
   if(vertical===otherVertical){if(vertical&&a.x===c.x)expect(Math.max(Math.min(a.y,b.y),Math.min(c.y,d.y))).toBeGreaterThanOrEqual(Math.min(Math.max(a.y,b.y),Math.max(c.y,d.y)));if(!vertical&&a.y===c.y)expect(Math.max(Math.min(a.x,b.x),Math.min(c.x,d.x))).toBeGreaterThanOrEqual(Math.min(Math.max(a.x,b.x),Math.max(c.x,d.x)));}
   else {const [v,w,h,k]=vertical?[a,b,c,d]:[c,d,a,b];expect(v.x>=Math.min(h.x,k.x)&&v.x<=Math.max(h.x,k.x)&&h.y>=Math.min(v.y,w.y)&&h.y<=Math.max(v.y,w.y)).toBe(false)}
  }
 }
 const represented=[...layout.connections.flatMap(c=>c.relationIds),...layout.cards.flatMap(c=>c.relationIds),...layout.redundantSiblings];
 expect(represented.sort()).toEqual(g.edges.map(e=>e.id).sort());expect(g).toEqual(before);
 expect(genealogyLayout({...g,nodes:[...g.nodes].reverse(),edges:[...g.edges].reverse()})).toEqual(layout);
 return layout;
}
describe('family units, not independent wires',()=>{
 it('six screenshot characters: one parental trunk, one labelled marriage, explicit care',()=>{
  const l=verify(screenshotFamily),f=l.connections.filter(c=>c.kind==='parents');
  expect(f).toHaveLength(1);expect(f[0].relationIds).toHaveLength(6);expect(f[0].label).toBe('Общие дети');
  expect(l.connections.find(c=>c.kind==='partners')?.label).toBe('Брак');
  expect(l.cards).toEqual([{id:'care',relationIds:['care']}]);expect(l.redundantSiblings.sort()).toEqual(['siblings','sisters']);
 });
 for(const count of [2,3,4,5,6])it(`${count} generations, remarriage and care retain every canonical edge`,()=>{
  const nodes=Array.from({length:count},(_,i)=>node(`p${i}`)).concat(['a','b','c','d'].map(node));
  const edges=Array.from({length:count-1},(_,i)=>edge(`e${i}`,`p${i}`,`p${i+1}`));
  edges.push(edge('marriage','p1','a','spouse'),{...edge('divorce','p1','b','spouse'),status:'closed',outcome:'divorced'},edge('siblings','a','c','sibling'),edge('adopt','b','d','adoptive_parent'),edge('guard','p0','d','guardian'));
  verify({nodes,edges,kinship:[],truncated:false});
 });
 it('different partners and incomplete parent sets never merge descent trunks',()=>{
  const g={nodes:['a','b','c','x','y','z'].map(id=>node(id)),edges:[edge('ab','a','b','spouse'),edge('ac','a','c','spouse'),edge('ax','a','x'),edge('bx','b','x'),edge('ay','a','y'),edge('cy','c','y'),edge('az','a','z')],kinship:[],truncated:false};
  const l=verify(g);const units=[...l.connections.filter(c=>c.kind==='parents'),...l.cards.filter(c=>c.parents)];
  expect(units.map(u=>u.relationIds.slice().sort()).sort()).toEqual([['ax','bx'],['ay','cy'],['az']].sort());
 });
 it('common parents do not invent a marriage',()=>{
  const l=verify({nodes:['a','b','x'].map(id=>node(id)),edges:[edge('ax','a','x'),edge('bx','b','x')],kinship:[],truncated:false});expect(l.connections).toHaveLength(1);expect(l.connections[0].kind).toBe('parents');expect(l.cards).toEqual([]);
 });
 it('uncertain parentage is never turned into a biological union or inferred sibling',()=>{
  const g={nodes:['a','x','y'].map(id=>node(id)),edges:[edge('ax','a','x'),{...edge('ay','a','y'),certainty:'suspected' as const},edge('xy','x','y','sibling')],kinship:[],truncated:false};const l=verify(g);expect(l.redundantSiblings).toEqual([]);expect(l.cards.map(c=>c.id)).toContain('ay');expect(l.cards.map(c=>c.id)).toContain('xy');
 });
 it('80 people and a long care connection remain complete without a detour maze',()=>{
  const nodes=Array.from({length:80},(_,i)=>node(String(i))),edges=nodes.slice(1).map((n,i)=>edge(`e${i}`,String(Math.floor(i/3)),n.id));edges.push(edge('care','0','79','guardian'));
  const l=verify({nodes,edges,kinship:[],truncated:true});expect(l.cards.some(c=>c.id==='care')).toBe(true);
 });
 it('empty and lone people never create fictitious parents',()=>{
  expect(verify({nodes:[],edges:[],kinship:[],truncated:false}).positions.size).toBe(0);expect(verify({nodes:[node('a')],edges:[],kinship:[],truncated:false}).connections).toEqual([]);
 });
 it('words identify every non-biological type; no eleven-pattern vocabulary',()=>{
  const kinds=['adoptive_parent','guardian','foster_parent','step_parent','spouse','partner','engaged','sibling'];
  expect(new Set(kinds.map(k=>relationText(edge(k,'a','b',k)))).size).toBe(kinds.length);
  for(const k of kinds)expect(relationText(edge(k,'a','b',k))).not.toBe(k);
 });
});
