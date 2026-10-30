import dagre from '@dagrejs/dagre';
import type { Genealogy, SocialRelation } from '../types';

export const PERSON_WIDTH = 184;
export const PERSON_HEIGHT = 224;
export type Point = { x: number; y: number };
export const lateral = (kind: string) => ['spouse', 'partner', 'engaged', 'sibling'].includes(kind);
export function relationPattern(e: Pick<SocialRelation, 'kind' | 'certainty' | 'status'>) {
  if (e.certainty === 'suspected') return '2 6';
  if (e.status === 'closed') return '10 5 2 5';
  return ({ parent: undefined, adoptive_parent: '10 5', guardian: '2 5', foster_parent: '12 4 3 4', step_parent: '5 3 1 3', spouse: '16 3', partner: '8 4', engaged: '8 3 2 3', sibling: '4 4' } as Record<string, string | undefined>)[e.kind];
}
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
  const ids = new Set(graph.nodes.map(n => n.id));
  const edges = graph.edges.filter(e => ids.has(e.source_id) && ids.has(e.target_id)).slice().sort((a,b)=>a.id.localeCompare(b.id));
  const descendants = new Map<string, Set<string>>();
  for (const id of [...ids].sort()) {
    const seen = new Set<string>(), todo = [id];
    while (todo.length) {
      const current = todo.pop()!;
      for (const e of edges) if (!lateral(e.kind) && e.source_id === current && !seen.has(e.target_id)) { seen.add(e.target_id); todo.push(e.target_id); }
    }
    descendants.set(id, seen);
  }
  let groups = [...ids].sort().map(id => [id]);
  for (const e of edges.filter(e=>lateral(e.kind))) {
    const a=groups.find(g=>g.includes(e.source_id))!, b=groups.find(g=>g.includes(e.target_id))!;
    if(a===b || a.some(x=>b.some(y=>descendants.get(x)?.has(y)||descendants.get(y)?.has(x)))) continue;
    groups=groups.filter(g=>g!==a&&g!==b); groups.push([...a,...b].sort());
  }
  groups.sort((a,b)=>a[0].localeCompare(b[0]));
  const groupOf=new Map<string,string>();
  const g=new dagre.graphlib.Graph({multigraph:true}).setGraph({rankdir:'TB',nodesep:64,ranksep:160}).setDefaultEdgeLabel(()=>({}));
  groups.forEach((members,i)=>{g.setNode(String(i),{width:members.length*240-56,height:PERSON_HEIGHT});members.forEach(id=>groupOf.set(id,String(i)))});
  for(const e of edges) {const a=groupOf.get(e.source_id)!, b=groupOf.get(e.target_id)!;if(a!==b)g.setEdge(a,b,{},e.id)}
  dagre.layout(g);
  const positions=new Map<string,Point>();
  groups.forEach((members,i)=>{const n=g.node(String(i));members.forEach((id,index)=>positions.set(id,{x:n.x-(members.length*240-56)/2+index*240,y:n.y-PERSON_HEIGHT/2}))});
  // Interval coloring assigns lanes by actual occupied span, never edge index.
  const lanes: {y:number; spans:[number,number][] }[]=[];
  const routes=new Map<string,Point[]>();
  const rects=[...positions.values()];
  for(const e of edges) {
    const a=positions.get(e.source_id)!, b=positions.get(e.target_id)!;
    const sx=a.x+PERSON_WIDTH/2, tx=b.x+PERSON_WIDTH/2;
    const same=lateral(e.kind);
    const sy=a.y+(same?0:PERSON_HEIGHT), ty=b.y;
    const low=Math.min(sx,tx), high=Math.max(sx,tx);
    let y=same?Math.min(a.y,b.y)-48:(sy+ty)/2;
    while(lanes.some(l=>Math.abs(l.y-y)<18&&l.spans.some(([l,r])=>low<=r+16&&high>=l-16))) y-=24;
    // A middle-generation node may intersect a long lineage. Route around the
    // full occupied envelope instead of drawing through people or inventing hubs.
    const segmentHits=(x1:number,y1:number,x2:number,y2:number)=>rects.some(r=>Math.max(x1,x2)>r.x-12&&Math.min(x1,x2)<r.x+PERSON_WIDTH+12&&Math.max(y1,y2)>r.y-12&&Math.min(y1,y2)<r.y+PERSON_HEIGHT+12);
    const start={x:sx,y:sy+(same?-24:24)}, end={x:tx,y:ty-24};
    let middle=[start,{x:sx,y},{x:tx,y},end];
    if(middle.slice(1).some((p,i)=>segmentHits(middle[i].x,middle[i].y,p.x,p.y))) {
      // Visibility grid: only node gutters and endpoint coordinates are needed.
      const xs=[...new Set([start.x,end.x,...rects.flatMap(r=>[r.x-24,r.x+PERSON_WIDTH+24])])].sort((a,b)=>a-b);
      const ys=[...new Set([start.y,end.y,y,...rects.flatMap(r=>[r.y-24,r.y+PERSON_HEIGHT+24])])].sort((a,b)=>a-b);
      const key=(x:number,y:number)=>y*xs.length+x;
      const origin=key(xs.indexOf(start.x),ys.indexOf(start.y)), goal=key(xs.indexOf(end.x),ys.indexOf(end.y));
      const queue=[origin], prev=new Map<number,number>(), seen=new Set([origin]);
      for(let q=0;q<queue.length&&!seen.has(goal);q++) {
        const current=queue[q], ix=current%xs.length, iy=Math.floor(current/xs.length);
        const next=[[ix+1,iy],[ix-1,iy],[ix,iy+1],[ix,iy-1]].filter(([x,y])=>x>=0&&y>=0&&x<xs.length&&y<ys.length);
        next.sort(([x,y],[xx,yy])=>Math.abs(xs[x]-end.x)+Math.abs(ys[y]-end.y)-Math.abs(xs[xx]-end.x)-Math.abs(ys[yy]-end.y));
        for(const [x,y] of next){const k=key(x,y);if(!seen.has(k)&&!segmentHits(xs[ix],ys[iy],xs[x],ys[y])){seen.add(k);prev.set(k,current);queue.push(k)}}
      }
      if(seen.has(goal)) {const path:Point[]=[];let k=goal;while(k!==origin){path.push({x:xs[k%xs.length],y:ys[Math.floor(k/xs.length)]});k=prev.get(k)!}path.push(start);middle=path.reverse()}
    }
    const points=[{x:sx,y:sy},...middle,{x:tx,y:ty}].filter((p,i,all)=>!i||p.x!==all[i-1].x||p.y!==all[i-1].y);
    routes.set(e.id,points.filter((p,i)=>!i||i===points.length-1||!((points[i-1].x===p.x&&p.x===points[i+1].x)||(points[i-1].y===p.y&&p.y===points[i+1].y))));
    lanes.push({y,spans:[[low,high]]});
  }
  const generations=[...new Set([...positions.values()].map(p=>p.y))].sort((a,b)=>a-b);
  return {positions,routes,generations};
}
