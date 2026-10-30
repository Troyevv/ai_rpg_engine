import {describe,it,expect} from 'vitest';
import {genealogyLayout,PERSON_WIDTH as W,PERSON_HEIGHT as H,relationPattern} from '../src/lib/genealogyLayout';
import type {Genealogy,SocialRelation} from '../src/types';
const node=(id:string)=>({id,name:id,life_status:'alive'});
const edge=(id:string,a:string,b:string,kind='parent'):SocialRelation=>({id,source_id:a,target_id:b,kind,certainty:'known',status:'active',outcome:''});
function verify(g:Genealogy){
 const {positions,routes}=genealogyLayout(g);
 const rows=[...positions.entries()];
 for(let i=0;i<rows.length;i++)for(let j=i+1;j<rows.length;j++){
  const a=rows[i][1],b=rows[j][1];expect(a.x+W<=b.x||b.x+W<=a.x||a.y+H<=b.y||b.y+H<=a.y).toBe(true);
 }
 for(const e of g.edges){const points=routes.get(e.id)!;expect(points.length).toBeGreaterThan(1);
  for(let i=1;i<points.length;i++){const a=points[i-1],b=points[i];
   for(const [id,r] of rows){if(id===e.source_id||id===e.target_id)continue;
    expect(Math.max(a.x,b.x)>r.x&&Math.min(a.x,b.x)<r.x+W&&Math.max(a.y,b.y)>r.y&&Math.min(a.y,b.y)<r.y+H,`${e.id} crosses ${id}`).toBe(false);
   }
  }
 }
 expect(genealogyLayout({...g,nodes:[...g.nodes].reverse(),edges:[...g.edges].reverse()})).toEqual({positions,routes,generations:genealogyLayout(g).generations});
}
describe('genealogy geometry',()=>{
 for(const count of [2,3,4,5,6])it(`${count} generations with remarriage and nonbiological links`,()=>{
  const nodes=Array.from({length:count},(_,i)=>node(`p${i}`)).concat(['a','b','c','d'].map(node));
  const edges=Array.from({length:count-1},(_,i)=>edge(`e${i}`,`p${i}`,`p${i+1}`));
  edges.push(edge('marriage','p1','a','spouse'),{...edge('divorce','p1','b','spouse'),status:'closed',outcome:'divorced'},edge('siblings','a','c','sibling'),edge('adopt','b','d','adoptive_parent'),edge('guard','p0','d','guardian'));
  verify({nodes,edges,kinship:[],truncated:false});
 });
 it('80 people, incomplete family and long cross-generation edges',()=>{
  const nodes=Array.from({length:80},(_,i)=>node(String(i)));
  const edges=nodes.slice(1).map((n,i)=>edge(`e${i}`,String(Math.floor(i/3)),n.id));
  edges.push(edge('long','0','79','guardian'));verify({nodes,edges,kinship:[],truncated:true});
 });
 it('empty and single person do not fabricate relatives',()=>{
  expect(genealogyLayout({nodes:[],edges:[],kinship:[],truncated:false}).positions.size).toBe(0);
  expect(genealogyLayout({nodes:[node('a')],edges:[],kinship:[],truncated:false}).routes.size).toBe(0);
 });
 it('uses different patterns for biological, legal and uncertain relations',()=>{
  const patterns=['parent','adoptive_parent','guardian','foster_parent','step_parent','spouse','partner','engaged','sibling'].map(kind=>relationPattern({kind,certainty:'known',status:'active'}));
  expect(new Set(patterns).size).toBe(patterns.length);
  expect(relationPattern({kind:'parent',certainty:'suspected',status:'active'})).toBe('2 6');
  expect(relationPattern({kind:'spouse',certainty:'known',status:'closed'})).toBe('10 5 2 5');
 });
});
