import { useEffect, useMemo, useState, useRef, memo } from "react";
import { useWorkspaceView, type WorkspaceView } from "./lib/workspaceView";
import {
  ReactFlow,
  ViewportPortal,
  BaseEdge,

  type EdgeProps,
  type Viewport,
  Controls,
  ControlButton,
  Handle,
  Position,
  useReactFlow,
  type NodeProps,
} from "@xyflow/react";
import { Maximize } from "lucide-react";
import { genealogyLayout, roundedPath, relationPattern, lateral, PERSON_WIDTH, PERSON_HEIGHT } from "./lib/genealogyLayout";
import "./styles/genealogy.css";
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
        size={104}
      />
      {Boolean(data.root) && <span className="family-root-caption">Центр дерева</span>}
      <strong title={String(data.label)}>{String(data.label)}</strong>
      <small>{lifeLabel(String(data.status))}{(data.subject as any).birth_date && <> · {calendarDate((data.subject as any).birth_date, "short")}</>}</small>
      <button className="family-center nodrag nopan" aria-label={`В центре родословной: ${data.label}`} onClick={e=>{e.stopPropagation();(data.onCenter as ()=>void)()}}>В центр</button>
      <Handle id="bottom" type="source" position={Position.Bottom} />
    </div>
  )),
};
const edgeTypes = {
  familyArc: ({ id, style, data, selected }: EdgeProps) => <g className={`family-line ${selected?'is-selected':''}`}>
    <title>{String(data?.description)}</title>
    <BaseEdge id={id} path={String(data?.path || '')} style={{...style, strokeWidth:selected?4:2}} interactionWidth={18}/>
  </g>,
};
const relationLabel = (e: Graph['edges'][number]) => `${({ parent: "Родитель", adoptive_parent: "Усыновление", guardian: "Опека" } as Record<string, string>)[e.kind] || socialLabel(e.kind)}${e.certainty === "suspected" ? " ?" : ""}${e.status === "closed" ? ` · ${socialLabel(e.outcome)}` : ""}`;
function Fit({ version, arcMargin, cache, reset }: { version: string; arcMargin:number; cache?: WorkspaceView; reset:number }) {
  const flow = useReactFlow();
  const reduced = useReducedMotion();
  const fit=()=>{
    const bounds=flow.getNodesBounds(flow.getNodes());
    return flow.fitBounds({...bounds,y:bounds.y-arcMargin,height:bounds.height+arcMargin},{padding:0.15,duration:reduced?0:240});
  };
  useEffect(() => {
    if (!flow.viewportInitialized) return;
    const id = requestAnimationFrame(
      () => {const stored=cache?.get(`viewport:${version}`) as Viewport|undefined; if(stored)void flow.setViewport(stored);else void fit()},
    );
    return () => cancelAnimationFrame(id);
  }, [version, flow.viewportInitialized, arcMargin, reset]);
  return <Controls showInteractive={false} showFitView={false}><ControlButton title="Вся семья" aria-label="Вся семья" onClick={()=>void fit()}><Maximize/></ControlButton></Controls>;
}
export function Genealogy({ save, rootId, onCharacter, viewState }: { save: Save; rootId?: string; onCharacter?:(id:string)=>void; viewState?: WorkspaceView }) {
  const [retry,setRetry]=useState(0);
  const [fitReset,setFitReset]=useState(0);
  const [rootsError,setRootsError]=useState('');
  const dataKey=`${save.id}:${save.revision}:${save.state.controlled_actor_id}`;
  const [rootData,setRootData]=useState<{key:string;items:{id:string;name:string}[]}>({key:"",items:[]});
  const roots=rootData.key===dataKey?rootData.items:[];
  const setRoots=(items:{id:string;name:string}[])=>setRootData({key:dataKey,items:items.map(row=>({...row,name:row.name.trim()||"Без имени"}))});
  useEffect(()=>{let live=true;setRootsError('');setRoots([]);api<{id:string;name:string}[]>(`/saves/${save.id}/genealogy-roots`).then(r=>{if(live)setRoots(r)}).catch(e=>{if(live)setRootsError(e.message)});return()=>{live=false}},[save.id,save.revision,save.state.controlled_actor_id,retry]);
  const [search,setSearch]=useWorkspaceView(viewState, "search", "");
  const [view,setView]=useWorkspaceView<'graph'|'list'>(viewState, 'view', 'graph');
  const [root, setRoot] = useWorkspaceView(viewState, "root",
      rootId || save.state.controlled_actor_id || save.state.protagonist_id || save.state.characters[0]?.id || "",
    ),
    [depth, setDepth] = useWorkspaceView(viewState, "depth", 3),
    [graphData, setGraphData] = useState<{key:string;value:Graph|null}>({key:"",value:null}),
    [error, setError] = useState(""),
    [selected, setSelected] = useWorkspaceView<string | null>(viewState, "selected", null);
  const matchingRoots=roots.filter(c=>c.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  const graphKey=`${dataKey}:${root}:${depth}`;
  // A display label for a real unnamed person; never an invented relative.
  const graph=useMemo(()=>graphData.key===graphKey&&graphData.value?{...graphData.value,nodes:graphData.value.nodes.map(n=>({...n,name:n.name.trim()||"Без имени"}))}:null,[graphData,graphKey]);
  const setGraph=(value:Graph|null)=>setGraphData({key:graphKey,value});
  const rootScope = `${save.id}:${save.state.controlled_actor_id}:${rootId}`;
  const previousRootScope = useRef(rootScope);
  useEffect(() => {
    if (previousRootScope.current === rootScope) return;
    previousRootScope.current = rootScope;
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
  const geometry = useMemo(() => graph ? genealogyLayout(graph) : null, [graph]);
  const [edgeDetail,setEdgeDetail]=useState<string|null>(null);
  const center = (id:string) => {setRoot(id);setSelected(null);setEdgeDetail(null)};
  const layout = useMemo(() => {
    if (!graph || !geometry) return {nodes:[],edges:[]};
    return {
      nodes: graph.nodes.map(n=>({id:n.id,type:'person',position:geometry.positions.get(n.id)!,
        data:{label:n.name,subject:n,status:n.life_status,saveId:save.id,root:n.id===root,onCenter:()=>center(n.id)},
        width:PERSON_WIDTH,height:PERSON_HEIGHT,ariaLabel:`${n.name}. Открыть досье`,})),
      edges: graph.edges.filter(e=>geometry.routes.has(e.id)).map(e=>({id:e.id,source:e.source_id,target:e.target_id,type:'familyArc',
        sourceHandle:lateral(e.kind)?'top-source':'bottom',targetHandle:'top',
        ariaLabel:`${graph.nodes.find(n=>n.id===e.source_id)?.name} — ${relationLabel(e)} — ${graph.nodes.find(n=>n.id===e.target_id)?.name}`,
        data:{path:roundedPath(geometry.routes.get(e.id)!),description:relationLabel(e)},
        style:{stroke:e.kind==='parent'?'var(--accent)':'var(--text-secondary)',strokeDasharray:relationPattern(e)},
      })),
    };
  }, [graph, geometry, save.id, root]);
  const routeTop=geometry?Math.min(0,...[...geometry.routes.values()].flat().map(p=>p.y)):0;
  const activeEdge=graph?.edges.find(e=>e.id===edgeDetail);
  return (
    <section className="genealogy" aria-label="Родословная"><div className="family-toolbar"><label>Найти персонажа<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Имя персонажа"/></label><label>Семья персонажа<select value={matchingRoots.some(c=>c.id===root)?root:""} onChange={e=>{setGraph(null);setSelected(null);setRoot(e.target.value)}}><option value="" disabled>{matchingRoots.length?"Выбери персонажа":"Персонаж не найден"}</option>{matchingRoots.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label></div>
      <details className="family-legend"><summary>Семейные связи · обозначения</summary><p className="muted">
        Линии показывают только связи из семейной справки. Выбери линию для подробностей; полный текст доступен в списке.
      </p><ul className="family-legend-items">{[['parent','Биологическое родство'],['adoptive_parent','Усыновление'],['guardian','Опека'],['foster_parent','Приёмная семья'],['step_parent','Отчим / мачеха'],['spouse','Брак'],['partner','Партнёрство'],['engaged','Помолвка'],['sibling','Братья / сёстры'],['suspected','Предположение'],['closed','Завершённая связь']].map(([kind,label])=><li key={kind}><svg width="40" height="12" aria-hidden="true"><path d="M0 6 H40" stroke="currentColor" strokeWidth="2" strokeDasharray={relationPattern({kind,certainty:kind==='suspected'?'suspected':'known',status:kind==='closed'?'closed':'active'})}/></svg>{label}</li>)}</ul><p className="muted">Поколения — расположение семейных ветвей, а не доказательство биологического родства.
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
      </label><button onClick={()=>{const defaultRoot=rootId || save.state.controlled_actor_id || save.state.protagonist_id || roots[0]?.id || '';viewState?.delete(`viewport:${dataKey}:${defaultRoot}:3`);setSearch('');setDepth(3);center(defaultRoot);setFitReset(n=>n+1)}}>Сбросить</button></div>
      {error||rootsError ? (
        <div role="alert"><p>{error||rootsError}</p><button onClick={()=>setRetry(n=>n+1)}>Повторить загрузку</button></div>
      ) : !graph ? (
        <p role="status">Загрузка родословной…</p>
      ) : graph.nodes.length === 0 ? (
        <p>Семейные связи не указаны.</p>
      ) : (
        <>
          {graph.edges.length===0&&<p>Семейные связи не указаны.</p>}{view==='graph'&&<div className="family-graph" onKeyDownCapture={e=>{const edge=(e.target as Element).closest('.react-flow__edge')?.getAttribute('data-id');if(edge&&(e.key==='Enter'||e.key===' ')){e.preventDefault();setEdgeDetail(edge);return}const id=(e.target as Element).closest('.react-flow__node')?.getAttribute('data-id');if(id&&!(e.target as HTMLElement).closest('button')&&(e.key==='Enter'||e.key===' ')){e.preventDefault();e.stopPropagation();setSelected(id);if(save.state.characters.some(c=>c.id===id))onCharacter?.(id)}}}>
            <ReactFlow
              nodes={layout.nodes}
              edges={layout.edges}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              onMoveEnd={(_,viewport)=>viewState?.set(`viewport:${graphKey}`,viewport)}
              onEdgeClick={(_,e)=>setEdgeDetail(e.id)}
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
              <Fit version={graphKey} cache={viewState} reset={fitReset} arcMargin={Math.abs(routeTop)+40} />
              <ViewportPortal><div className="family-generations" aria-hidden="true">{geometry?.generations.map((y,i)=><div key={y} className="family-generation" style={{top:y-32,left:-24,width:Math.max(...[...geometry.positions.values()].map(p=>p.x))+PERSON_WIDTH+48,height:PERSON_HEIGHT+56}}><span>Поколение {i+1}</span></div>)}</div></ViewportPortal>
            </ReactFlow>
          </div>}
          {activeEdge && <div className="family-relationship-detail" role="status"><strong>{graph.nodes.find(n=>n.id===activeEdge.source_id)?.name} — {relationLabel(activeEdge)} — {graph.nodes.find(n=>n.id===activeEdge.target_id)?.name}</strong><button aria-label="Закрыть сведения о связи" onClick={()=>setEdgeDetail(null)}>×</button></div>}
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
