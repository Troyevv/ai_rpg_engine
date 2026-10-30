import dagre from '@dagrejs/dagre';
import type { Genealogy, SocialRelation } from '../types';

export const PERSON_WIDTH = 184;
export const PERSON_HEIGHT = 224;
export type Point = { x: number; y: number };
export const lateral = (kind: string) => ['spouse', 'partner', 'engaged', 'sibling'].includes(kind);
export type FamilyConnection = {id:string;source:string;target:string;relationIds:string[];paths:Point[][];label:string;at:Point;kind:'parents'|'partners'};
export type FamilyCard = {id:string;relationIds:string[];parents?:string[];children?:string[]};
export const relationText = (e: SocialRelation) => `${({parent:'Родитель',adoptive_parent:'Усыновление',guardian:'Опека',foster_parent:'Приёмная семья',step_parent:'Отчим / мачеха',spouse:'Брак',partner:'Партнёры',engaged:'Помолвка',sibling:'Брат / сестра'} as Record<string,string>)[e.kind] || e.kind}${e.certainty==='suspected'?' · предположение':''}${e.status==='closed'?` · ${({divorced:'Развод',widowed:'Вдовство',revoked:'Прекращено',ended:'Завершено'} as Record<string,string>)[e.outcome] || 'завершено'}`:''}`;
// Rounded orthogonal segments: corners stay inside a clear routing corridor.
export function roundedPath(points: Point[]) {
  if (!points.length) return '';
  let d = `M ${points[0].x},${points[0].y}`;
  for (let i = 1; i < points.length - 1; i++) {
    const a = points[i - 1], b = points[i], c = points[i + 1];
    const ab = Math.hypot(b.x - a.x, b.y - a.y), bc = Math.hypot(c.x - b.x, c.y - b.y);
    const r = Math.min(16, ab / 2, bc / 2);
    if (!ab || !bc) continue;
    d += ` L ${b.x + (a.x-b.x)*r/ab},${b.y + (a.y-b.y)*r/ab} Q ${b.x},${b.y} ${b.x+(c.x-b.x)*r/bc},${b.y+(c.y-b.y)*r/bc}`;
  }
  const last = points.at(-1)!;
  return `${d} L ${last.x},${last.y}`;
}

export function genealogyLayout(graph: Genealogy) {
  const ids = new Set(graph.nodes.map(n=>n.id));
  const edges = graph.edges.filter(e=>ids.has(e.source_id)&&ids.has(e.target_id)).slice().sort((a,b)=>a.id.localeCompare(b.id));
  const biological = edges.filter(e=>e.kind==='parent'&&e.certainty==='known'&&e.status==='active');
  const parentsOf = new Map<string,string[]>();
  for(const e of biological) parentsOf.set(e.target_id,[...new Set([...(parentsOf.get(e.target_id)||[]),e.source_id])].sort());
  // A family unit is a view of existing parent edges, NOT a marriage or a new
  // canonical entity. Different parent sets must never share a descent trunk.
  const families = new Map<string,{parents:string[];children:string[];edges:SocialRelation[]}>();
  for(const [child,parents] of parentsOf){const key=JSON.stringify(parents);const f=families.get(key)||{parents,children:[],edges:[]};f.children.push(child);f.edges.push(...biological.filter(e=>e.target_id===child));families.set(key,f)}
  const descendants=new Map<string,Set<string>>();
  for(const id of ids){const seen=new Set<string>(),todo=[id];while(todo.length){const next=todo.pop()!;for(const e of edges)if(!lateral(e.kind)&&e.source_id===next&&!seen.has(e.target_id)){seen.add(e.target_id);todo.push(e.target_id)}}descendants.set(id,seen)}
  let groups=[...ids].sort().map(id=>[id]);
  const join=(x:string,y:string)=>{const a=groups.find(g=>g.includes(x))!,b=groups.find(g=>g.includes(y))!;if(a===b||a.some(i=>b.some(j=>descendants.get(i)?.has(j)||descendants.get(j)?.has(i))))return;groups=groups.filter(g=>g!==a&&g!==b);groups.push([...a,...b].sort())};
  for(const f of families.values()) for(const p of f.parents.slice(1))join(f.parents[0],p);
  for(const e of edges.filter(e=>lateral(e.kind)&&e.kind!=='sibling'))join(e.source_id,e.target_id);
  // Place partners next to each other where possible; never let sibling edges
  // force unrelated partners into an enormous same-generation component.
  groups=groups.map(members=>{
    const ordered:string[]=[];const remaining=new Set(members);
    while(remaining.size){const last=ordered.at(-1);const adjacent=edges.find(e=>e.kind!=='sibling'&&lateral(e.kind)&&((e.source_id===last&&remaining.has(e.target_id))||(e.target_id===last&&remaining.has(e.source_id))));const next=adjacent?(adjacent.source_id===last?adjacent.target_id:adjacent.source_id):[...remaining].sort()[0];ordered.push(next);remaining.delete(next)}return ordered;
  }).sort((a,b)=>a[0].localeCompare(b[0]));
  const groupOf=new Map<string,string>();
  const g=new dagre.graphlib.Graph({multigraph:true}).setGraph({rankdir:'TB',nodesep:70,ranksep:180}).setDefaultEdgeLabel(()=>({}));
  const step=340;
  groups.forEach((members,i)=>{g.setNode(String(i),{width:(members.length-1)*step+PERSON_WIDTH,height:PERSON_HEIGHT});members.forEach(id=>groupOf.set(id,String(i)))});
  for(const e of edges.filter(e=>!lateral(e.kind))){const a=groupOf.get(e.source_id)!,b=groupOf.get(e.target_id)!;if(a!==b)g.setEdge(a,b,{},e.id)}
  dagre.layout(g);
  const positions=new Map<string,Point>();
  groups.forEach((members,i)=>{const n=g.node(String(i));members.forEach((id,index)=>positions.set(id,{x:n.x-((members.length-1)*step+PERSON_WIDTH)/2+index*step,y:n.y-PERSON_HEIGHT/2}))});
  const connections:FamilyConnection[]=[],cards:FamilyCard[]=[],redundantSiblings:string[]=[];
  const occupied:Point[][]=[];
  const labels:{x:number;y:number;width:number;height:number}[]=[];
  const segmentHits=(a:Point,b:Point,r:{x:number;y:number;width:number;height:number})=>Math.max(a.x,b.x)>r.x&&Math.min(a.x,b.x)<r.x+r.width&&Math.max(a.y,b.y)>r.y&&Math.min(a.y,b.y)<r.y+r.height;
  const crosses=(a:Point,b:Point,c:Point,d:Point)=>{
    if(a.x===b.x&&c.x===d.x)return a.x===c.x&&Math.max(Math.min(a.y,b.y),Math.min(c.y,d.y))<Math.min(Math.max(a.y,b.y),Math.max(c.y,d.y));
    if(a.y===b.y&&c.y===d.y)return a.y===c.y&&Math.max(Math.min(a.x,b.x),Math.min(c.x,d.x))<Math.min(Math.max(a.x,b.x),Math.max(c.x,d.x));
    const v=a.x===b.x?[a,b]:[c,d],h=a.x===b.x?[c,d]:[a,b];return v[0].x>=Math.min(h[0].x,h[1].x)&&v[0].x<=Math.max(h[0].x,h[1].x)&&h[0].y>=Math.min(v[0].y,v[1].y)&&h[0].y<=Math.max(v[0].y,v[1].y);
  };
  const accept=(connection:FamilyConnection)=>{
    const rect={x:connection.at.x-68,y:connection.at.y-13,width:136,height:26};
    const people=[...positions.values()].map(p=>({...p,width:PERSON_WIDTH,height:PERSON_HEIGHT}));
    const segments=connection.paths.flatMap(path=>path.slice(1).map((p,i)=>[path[i],p]));
    const collision=segments.some(([a,b])=>people.some(r=>segmentHits(a,b,r))||labels.some(r=>segmentHits(a,b,r))||occupied.some(path=>path.slice(1).some((d,i)=>crosses(a,b,path[i],d))))||labels.concat(people).some(r=>rect.x<r.x+r.width&&rect.x+rect.width>r.x&&rect.y<r.y+r.height&&rect.y+rect.height>r.y)||occupied.some(path=>path.slice(1).some((p,i)=>segmentHits(path[i],p,rect)));
    if(collision)return false;
    connections.push(connection);occupied.push(...connection.paths);labels.push(rect);return true;
  };
  // Local horizontal partnership connectors, at portrait level, with words.
  for(const e of edges.filter(e=>['spouse','partner','engaged'].includes(e.kind))){
    let a=positions.get(e.source_id)!,b=positions.get(e.target_id)!;if(a.x>b.x)[a,b]=[b,a];
    const adjacent=a.y===b.y&&b.x-a.x===step;
    const paths=[[{x:a.x+PERSON_WIDTH,y:a.y+60},{x:b.x,y:b.y+60}]];
    if(!adjacent||relationText(e).length>19||!accept({id:e.id,source:e.source_id,target:e.target_id,relationIds:[e.id],paths,label:relationText(e),at:{x:(a.x+PERSON_WIDTH+b.x)/2,y:a.y+60},kind:'partners'}))cards.push({id:e.id,relationIds:[e.id]});
  }
  const represented=new Set(connections.flatMap(c=>c.relationIds).concat(cards.flatMap(c=>c.relationIds)));
  for(const [key,f] of [...families.entries()].sort((a,b)=>b[1].children.length-a[1].children.length||a[0].localeCompare(b[0]))){
    f.children.sort((a,b)=>positions.get(a)!.x-positions.get(b)!.x);
    const parents=f.parents.map(id=>positions.get(id)!),children=f.children.map(id=>positions.get(id)!);
    const top=Math.max(...parents.map(p=>p.y+PERSON_HEIGHT)),bottom=Math.min(...children.map(p=>p.y));
    const px=parents.map(p=>p.x+PERSON_WIDTH/2),cx=children.map(p=>p.x+PERSON_WIDTH/2);
    const hub=(Math.min(...px)+Math.max(...px))/2,joinY=top+30,branchY=bottom-40;
    const paths:Point[][]=parents.map((p,i)=>[{x:px[i],y:p.y+PERSON_HEIGHT},{x:px[i],y:joinY}]);
    if(px.length>1)paths.push([{x:Math.min(...px),y:joinY},{x:Math.max(...px),y:joinY}]);
    paths.push([{x:hub,y:joinY},{x:hub,y:branchY}]);
    paths.push([{x:Math.min(hub,...cx),y:branchY},{x:Math.max(hub,...cx),y:branchY}]);
    children.forEach((p,i)=>paths.push([{x:cx[i],y:branchY},{x:cx[i],y:p.y}]));
    const relationIds=f.edges.map(e=>e.id);relationIds.forEach(id=>represented.add(id));
    if(bottom-top<120||!accept({id:`family:${key}`,source:f.parents[0],target:f.children[0],relationIds,paths,label:f.parents.length>1?'Общие дети':'Дети',at:{x:hub,y:(joinY+branchY)/2},kind:'parents'}))cards.push({id:`family:${key}`,relationIds,parents:f.parents,children:f.children});
  }
  for(const e of edges.filter(e=>!represented.has(e.id))){
    if(e.kind==='sibling'&&e.certainty==='known'&&e.status==='active'&&(parentsOf.get(e.source_id)||[]).some(p=>parentsOf.get(e.target_id)?.includes(p))){redundantSiblings.push(e.id);continue}
    cards.push({id:e.id,relationIds:[e.id]});
  }
  // Difficult/non-planar and care relationships are always visible as labelled
  // endpoint cards, not anonymous detours through unrelated people. Every API
  // relation is accounted for by a connector, a card or the sibling disclosure.
  return {positions,connections,cards,redundantSiblings,generations:[...new Set([...positions.values()].map(p=>p.y))].sort((a,b)=>a-b)};
}
