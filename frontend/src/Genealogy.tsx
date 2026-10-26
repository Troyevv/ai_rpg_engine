import { useEffect, useMemo, useState, memo } from "react";
import {
  ReactFlow,
  Background,
  BaseEdge,
  EdgeLabelRenderer,
  type EdgeProps,
  Controls,
  ControlButton,
  Handle,
  Position,
  useReactFlow,
  useNodesInitialized,
  type NodeProps,
} from "@xyflow/react";
import { Maximize } from "lucide-react";
import dagre from "@dagrejs/dagre";
import "@xyflow/react/dist/style.css";
import { useReducedMotion } from "framer-motion";
import { calendarDate } from "./gameDate";
import { api } from "./api";
import type { Genealogy as Graph, Save } from "./types";
import { CharacterAvatar } from "./Portrait";
import { socialLabel, lifeLabel } from "./lib/social";
const nodeTypes = {
  person: memo(({ data }: NodeProps) => (
    <div className={`family-node ${data.root?'family-root':''} ${data.status==='dead'?'family-deceased':''}`}>
      <Handle id="top" type="target" position={Position.Top} />
      <Handle id="top-source" type="source" position={Position.Top} />
      <Handle id="left-source" type="source" position={Position.Left} />
      <Handle id="right-source" type="source" position={Position.Right} />
      <Handle id="left-target" type="target" position={Position.Left} />
      <Handle id="right-target" type="target" position={Position.Right} />
      <CharacterAvatar
        subject={data.subject as any}
        saveId={data.saveId as number}
        size={64}
      />
      <strong title={String(data.label)}>{String(data.label)}</strong>
      <small>{lifeLabel(String(data.status))}</small>
      {(data.subject as any).birth_date && (
        <small>{calendarDate((data.subject as any).birth_date, "short")}</small>
      )}
      <Handle id="bottom" type="source" position={Position.Bottom} />
    </div>
  )),
};
// Non-adjacent partners route above their generation instead of through a person.
const edgeTypes = {
  familyArc: ({ id, sourceX, sourceY, targetX, targetY, label, style, data }: EdgeProps) => {
    const lane = Math.min(sourceY, targetY) - Number(data?.offset || 44);
    return <><BaseEdge id={id} path={`M ${sourceX},${sourceY} V ${lane} H ${targetX} V ${targetY}`} style={style}/>
      <EdgeLabelRenderer><span className="family-edge-label" style={{transform:`translate(-50%, -50%) translate(${(sourceX+targetX)/2}px,${lane}px)`}}>{String(label)}</span></EdgeLabelRenderer></>;
  },
};
const relationLabel = (e: Graph['edges'][number]) => `${({ parent: "Родитель", adoptive_parent: "Усыновление", guardian: "Опека" } as Record<string, string>)[e.kind] || socialLabel(e.kind)}${e.certainty === "suspected" ? " ?" : ""}${e.status === "closed" ? ` · ${socialLabel(e.outcome)}` : ""}`;
function Fit({ version, arcMargin }: { version: string; arcMargin:number }) {
  const flow = useReactFlow();
  const initialized = useNodesInitialized();
  const reduced = useReducedMotion();
  const fit=()=>{
    const bounds=flow.getNodesBounds(flow.getNodes());
    return flow.fitBounds({...bounds,y:bounds.y-arcMargin,height:bounds.height+arcMargin},{padding:0.15,duration:reduced?0:240});
  };
  useEffect(() => {
    if (!initialized) return;
    const id = requestAnimationFrame(
      () => void fit(),
    );
    return () => cancelAnimationFrame(id);
  }, [version, initialized, arcMargin]);
  return <Controls showInteractive={false} showFitView={false}><ControlButton title="Вся семья" aria-label="Вся семья" onClick={()=>void fit()}><Maximize/></ControlButton></Controls>;
}
export function Genealogy({ save, rootId, onCharacter }: { save: Save; rootId?: string; onCharacter?:(id:string)=>void }) {
  const [retry,setRetry]=useState(0);
  const [rootsError,setRootsError]=useState('');
  const dataKey=`${save.id}:${save.revision}:${save.state.controlled_actor_id}`;
  const [rootData,setRootData]=useState<{key:string;items:{id:string;name:string}[]}>({key:"",items:[]});
  const roots=rootData.key===dataKey?rootData.items:[];
  const setRoots=(items:{id:string;name:string}[])=>setRootData({key:dataKey,items});
  useEffect(()=>{let live=true;setRootsError('');setRoots([]);api<{id:string;name:string}[]>(`/saves/${save.id}/genealogy-roots`).then(r=>{if(live)setRoots(r)}).catch(e=>{if(live)setRootsError(e.message)});return()=>{live=false}},[save.id,save.revision,save.state.controlled_actor_id,retry]);
  const [search,setSearch]=useState("");
  const [view,setView]=useState<'graph'|'list'>('graph');
  const [root, setRoot] = useState(
      rootId || save.state.controlled_actor_id || save.state.protagonist_id || save.state.characters[0]?.id || "",
    ),
    [depth, setDepth] = useState(3),
    [graphData, setGraphData] = useState<{key:string;value:Graph|null}>({key:"",value:null}),
    [error, setError] = useState(""),
    [selected, setSelected] = useState<string | null>(null);
  const matchingRoots=roots.filter(c=>c.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  const graphKey=`${dataKey}:${root}:${depth}`;
  const graph=graphData.key===graphKey?graphData.value:null;
  const setGraph=(value:Graph|null)=>setGraphData({key:graphKey,value});
  useEffect(() => {
    setRoot(rootId || save.state.controlled_actor_id || save.state.protagonist_id || save.state.characters[0]?.id || "");
    setGraph(null);
  }, [rootId, save.id, save.state.controlled_actor_id]);
  useEffect(() => {
    let live = true;
    setError("");
    api<Graph>(
      `/saves/${save.id}/genealogy?root_id=${encodeURIComponent(root)}&depth=${depth}&limit=80`,
    )
      .then((g) => {
        if (live) setGraph(g);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [root, depth, save.id, save.revision, save.state.controlled_actor_id,retry]);
  const layout = useMemo(() => {
    if (!graph) return { nodes: [], edges: [] };
    // Presentation groups only. Never collapse an established ancestor into the
    // same generation through a chain of marriages/siblings.
    const lateral = new Set(['spouse','partner','engaged','sibling']);
    const descendants = new Map<string,Set<string>>();
    for(const n of graph.nodes){
      const seen=new Set<string>(),todo=[n.id];
      while(todo.length){const id=todo.pop()!;for(const e of graph.edges){if(!lateral.has(e.kind)&&e.source_id===id&&!seen.has(e.target_id)){seen.add(e.target_id);todo.push(e.target_id)}}}
      descendants.set(n.id,seen);
    }
    let groups=graph.nodes.map(n=>[n.id]);
    for(const e of [...graph.edges].sort((a,b)=>a.id.localeCompare(b.id))){
      if(!lateral.has(e.kind))continue;
      const a=groups.find(g=>g.includes(e.source_id))!,b=groups.find(g=>g.includes(e.target_id))!;
      if(a===b||a.some(x=>b.some(y=>descendants.get(x)?.has(y)||descendants.get(y)?.has(x))))continue;
      groups=groups.filter(g=>g!==a&&g!==b);groups.push([...a,...b].sort());
    }
    groups.sort((a,b)=>a[0].localeCompare(b[0]));
    const groupOf=new Map<string,string>();
    const g=new dagre.graphlib.Graph({multigraph:true}).setGraph({rankdir:'TB',nodesep:64,ranksep:160}).setDefaultEdgeLabel(()=>({}));
    groups.forEach((ids,i)=>{const key=String(i);g.setNode(key,{width:ids.length*304-120,height:176});ids.forEach(id=>groupOf.set(id,key))});
    graph.edges.forEach(e=>{const a=groupOf.get(e.source_id)!,b=groupOf.get(e.target_id)!;if(a!==b)g.setEdge(a,b,{minlen:1,width:130,height:24},e.id)});
    dagre.layout(g);
    const positions=new Map<string,{x:number;y:number}>();
    groups.forEach((ids,i)=>{const n=g.node(String(i));ids.forEach((id,index)=>positions.set(id,{x:n.x-(ids.length*304-120)/2+index*304,y:n.y-88}))});
    return {
      nodes: graph.nodes.map((n) => ({
        id: n.id,
        type: "person",
        position: positions.get(n.id)!,
        data: {
          label: n.name,
          subject: n,
          status: n.life_status,
          saveId: save.id,
          root: n.id===root,
        },
        width:184,height:176,ariaLabel:n.name,
      })),
      edges: graph.edges.map((e, index) => {
        const sameGeneration = ['spouse','partner','engaged','sibling'].includes(e.kind);
        const a = positions.get(e.source_id)!, b = positions.get(e.target_id)!;
        const arc = sameGeneration && Math.abs(a.x-b.x)>305;
        return ({
        id: e.id,
        source: e.source_id,
        target: e.target_id,
        type: arc ? 'familyArc' : sameGeneration?'default':'smoothstep',
        data: {offset:36+index*18},
        sourceHandle: arc ? 'top-source' : sameGeneration ? (a.x<b.x?'right-source':'left-source') : 'bottom',
        targetHandle: arc ? 'top' : sameGeneration ? (a.x<b.x?'left-target':'right-target') : 'top',
        label: relationLabel(e),
        style: {
          stroke: "var(--accent)",
          strokeDasharray:
            e.certainty === "suspected" || e.kind !== "parent"
              ? "6 4"
              : undefined,
        },
        labelStyle: { fill: "var(--text)", fontSize: 11 },
        labelBgStyle: { fill: "var(--surface-1)" },
      })}),
    };
  }, [graph, save.id, root]);
  return (
    <section aria-label="Родословная"><div className="family-toolbar"><label>Найти персонажа<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Имя персонажа"/></label><label>Семья персонажа<select value={matchingRoots.some(c=>c.id===root)?root:""} onChange={e=>{setGraph(null);setSelected(null);setRoot(e.target.value)}}><option value="" disabled>{matchingRoots.length?"Выбери персонажа":"Персонаж не найден"}</option>{matchingRoots.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label></div>
      <details className="family-legend"><summary>Семейные связи · обозначения</summary><p className="muted">
        Канонические семейные связи всех персонажей. Пунктир отличает
        предположения и небиологические связи; смысл указан на линии.
      </p></details>
      <div className="family-view-tools"><div className="family-view-toggle" role="group" aria-label="Вид родословной"><button aria-pressed={view==='graph'} onClick={()=>setView('graph')}>Дерево</button><button aria-pressed={view==='list'} onClick={()=>setView('list')}>Список</button></div><label>
        Глубина ветвей{" "}
        <input
          aria-label="Глубина родословной"
          type="range"
          min="1"
          max="6"
          value={depth}
          onChange={(e) => setDepth(+e.target.value)}
        />
        {depth}
      </label></div>
      {error||rootsError ? (
        <div role="alert"><p>{error||rootsError}</p><button onClick={()=>setRetry(n=>n+1)}>Повторить загрузку</button></div>
      ) : !graph ? (
        <p role="status">Загрузка родословной…</p>
      ) : graph.nodes.length === 0 ? (
        <p>Семейные связи не указаны.</p>
      ) : (
        <>
          {graph.edges.length===0&&<p>Семейные связи не указаны.</p>}{view==='graph'&&<div className="family-graph" onKeyDownCapture={e=>{const id=(e.target as HTMLElement).closest('.react-flow__node')?.getAttribute('data-id');if(id&&(e.key==='Enter'||e.key===' ')){e.preventDefault();e.stopPropagation();setSelected(id);if(save.state.characters.some(c=>c.id===id))onCharacter?.(id)}}}>
            <ReactFlow
              nodes={layout.nodes}
              edges={layout.edges}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              fitView
              deleteKeyCode={null}
              edgesReconnectable={false}
              proOptions={{ hideAttribution: true }}
              nodesDraggable={false}
              nodesConnectable={false}
              onNodeClick={(_, n) => {setSelected(n.id);if(save.state.characters.some(c=>c.id===n.id))onCharacter?.(n.id)}}
              minZoom={0.01}
              maxZoom={2}
              ariaLabelConfig={{
                "node.a11yDescription.default":
                  "Enter или пробел: выбрать персонажа. Escape: снять выбор.",
                "node.a11yDescription.keyboardDisabled":
                  "Enter или пробел: выбрать персонажа.",
                "edge.a11yDescription.default":
                  "Enter или пробел: выбрать связь. Escape: снять выбор.",
                "controls.ariaLabel": "Масштаб родословной",
                "handle.ariaLabel": "Семейная связь",
                "controls.zoomIn.ariaLabel": "Увеличить",
                "controls.zoomOut.ariaLabel": "Уменьшить",
                "controls.fitView.ariaLabel": "Вся семья",
              }}
            >
              <Fit version={`${root}:${depth}:${save.revision}`} arcMargin={Math.max(0,...layout.edges.filter(e=>e.type==='familyArc').map(e=>e.data.offset+24))} />
              <Background />
            </ReactFlow>
          </div>}
          {selected && graph.nodes.find((n) => n.id === selected) && (
            <div className="family-preview">
              <CharacterAvatar
                subject={graph.nodes.find((n) => n.id === selected)!}
                saveId={save.id}
              />
              <strong>
                {graph.nodes.find((n) => n.id === selected)!.name}
              </strong>
              <button onClick={() => setRoot(selected)}>
                В центре родословной
              </button>
            </div>
          )}
          <details className="family-accessible-list" open={view==='list'?true:undefined}>
            <summary>Доступный список связей</summary>
            {graph.edges.map((e) => (
              <p key={e.id}>
                {graph.nodes.find((n) => n.id === e.source_id)?.name} —{" "}
                {relationLabel(e)} —{" "}
                {graph.nodes.find((n) => n.id === e.target_id)?.name}
              </p>
            ))}
            {graph.nodes.map((n) => (
              <div className="family-list-person" key={n.id}><CharacterAvatar subject={n} saveId={save.id} size={40}/><button onClick={() => {setRoot(n.id);setSelected(null)}}>{n.name}</button>{onCharacter&&save.state.characters.some(c=>c.id===n.id)&&<button aria-label={`Открыть досье: ${n.name}`} onClick={()=>onCharacter(n.id)}>Досье</button>}</div>
            ))}
          </details>
        </>
      )}
      {graph?.truncated && (
        <p>Показана часть семьи. Выбери персонажа для продолжения.</p>
      )}
    </section>
  );
}
