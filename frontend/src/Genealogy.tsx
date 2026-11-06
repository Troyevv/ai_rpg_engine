import { useEffect, useMemo, useState, useRef, memo } from "react";
import { useWorkspaceView, type WorkspaceView } from "./lib/workspaceView";
import {
  ReactFlow,
  ViewportPortal,
  EdgeLabelRenderer,
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
import { genealogyLayout, roundedPath, relationText, PERSON_WIDTH, PERSON_HEIGHT } from "./lib/genealogyLayout";
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
    <BaseEdge id={id} path={String(data?.path || '')} style={{...style, strokeWidth:selected?3:2}} interactionWidth={18}/>
    <EdgeLabelRenderer><span className="family-connection-label" style={{transform:`translate(-50%, -50%) translate(${(data?.at as {x:number}).x}px,${(data?.at as {y:number}).y}px)`}}>{String(data?.description)}</span></EdgeLabelRenderer>
  </g>,
};
const relationLabel = relationText;
const familyRoles:Record<string,[string,string]>={parent:['Родитель','Ребёнок'],adoptive_parent:['Приёмный родитель','Ребёнок'],guardian:['Опекун','Подопечный'],foster_parent:['Приёмный родитель','Ребёнок'],step_parent:['Отчим / мачеха','Ребёнок']};
function Fit({ version, arcMargin, cache, reset, focusX, focusY }: { version: string; arcMargin:number; cache?: WorkspaceView; reset:number; focusX:number; focusY:number }) {
  const flow = useReactFlow();
  const reduced = useReducedMotion();
  const fit=()=>{
    const bounds=flow.getNodesBounds(flow.getNodes());
    return flow.fitBounds({...bounds,y:bounds.y-arcMargin,height:bounds.height+arcMargin},{padding:0.15,duration:reduced?0:240});
  };
  useEffect(() => {
    if (!flow.viewportInitialized) return;
    const id = requestAnimationFrame(
      () => {const stored=cache?.get(`viewport:${version}`) as Viewport|undefined; if(stored)void flow.setViewport(stored);else {
        const bounds=flow.getNodesBounds(flow.getNodes());
        const width=document.querySelector('.family-graph')?.clientWidth || 1000;
        // A phone starts at a readable scale. The explicit overview button still
        // fits the whole family, and its chosen viewport is restored verbatim.
        if(width<600&&bounds.width>width/0.85)void flow.setCenter(focusX,focusY,{zoom:Math.min(0.85,(width-32)/(PERSON_WIDTH+340))});else void fit();
      }},
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
      edges: geometry.connections.map(c=>({id:c.id,source:c.source,target:c.target,type:'familyArc',
        sourceHandle:'bottom',targetHandle:'top',
        ariaLabel:c.relationIds.map(id=>{const e=graph.edges.find(e=>e.id===id)!;return `${graph.nodes.find(n=>n.id===e.source_id)?.name} — ${relationLabel(e)} — ${graph.nodes.find(n=>n.id===e.target_id)?.name}`}).join('; '),
        data:{path:c.paths.map(roundedPath).join(' '),description:c.label,at:c.at},
        style:{stroke:c.kind==='parents'?'var(--accent)':'var(--text-secondary)'},
      })),
    };
  }, [graph, geometry, save.id, root]);
  const activeIds=geometry?.connections.find(c=>c.id===edgeDetail)?.relationIds || (edgeDetail?[edgeDetail]:[]);
  const activeEdges=graph?.edges.filter(e=>activeIds.includes(e.id)) || [];
  const personLink=(id:string)=>{const n=graph?.nodes.find(n=>n.id===id);return n&&<button className="family-relative" onClick={()=>{setSelected(id);if(save.state.characters.some(c=>c.id===id))onCharacter?.(id)}} key={id}><CharacterAvatar subject={n} saveId={save.id} size={32}/><span>{n.name}</span></button>};
  return (
    <section className="genealogy" aria-label="Родословная"><div className="family-toolbar"><label>Найти персонажа<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Имя персонажа"/></label><label>Семья персонажа<select value={matchingRoots.some(c=>c.id===root)?root:""} onChange={e=>{setGraph(null);setSelected(null);setRoot(e.target.value)}}><option value="" disabled>{matchingRoots.length?"Выбери персонажа":"Персонаж не найден"}</option>{matchingRoots.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label></div>
      <p className="family-touch-hint">Перемещай дерево пальцем. Кнопка «Вся семья» покажет общий обзор.</p>
      <p className="family-reading-hint">Родители сверху, дети снизу. Общая ветвь объединяет только подтверждённых биологических родителей. Остальные связи подписаны отдельно.</p>
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
          <div className={`family-tree-layout ${view==='graph'&&geometry?.cards.length?'has-relations':''}`}>
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
              <Fit version={graphKey} cache={viewState} reset={fitReset} focusX={geometry?.connections.find(c=>c.kind==='parents'&&c.relationIds.some(id=>graph.edges.some(e=>e.id===id&&e.source_id===root)))?.at.x ?? ((geometry?.positions.get(root)?.x || 0)+PERSON_WIDTH/2)} focusY={(geometry?.positions.get(root)?.y || 0)+PERSON_HEIGHT/2+(graph.edges.some(e=>e.kind==='parent'&&e.source_id===root)?200:0)} arcMargin={60} />
              <ViewportPortal><div className="family-generations" aria-hidden="true">{geometry?.generations.map((y,i)=><div key={y} className="family-generation" style={{top:y-32,left:-24,width:Math.max(...[...geometry.positions.values()].map(p=>p.x))+PERSON_WIDTH+48,height:PERSON_HEIGHT+56}}><span>Поколение {i+1}</span></div>)}</div></ViewportPortal>
            </ReactFlow>
          </div>}
          {view==='graph'&&!!geometry?.cards.length&&<section className="family-relation-cards" aria-label="Другие семейные связи">{geometry.cards.map(card=>{
            if(card.parents)return <article className="family-relation-card" key={card.id}><strong>Родители и дети · отдельная ветвь</strong><div>{card.parents.map(personLink)}</div><span>Дети</span><div>{card.children?.map(personLink)}</div></article>;
            const e=graph.edges.find(e=>e.id===card.relationIds[0])!;
            return <article className="family-relation-card" data-relation-id={e.id} key={card.id}><strong>{relationLabel(e)}</strong><div><div className="family-relation-endpoint">{familyRoles[e.kind]&&<small>{familyRoles[e.kind][0]}</small>}{personLink(e.source_id)}</div><span aria-hidden="true">{['spouse','partner','engaged','sibling'].includes(e.kind)?'↔':'→'}</span><div className="family-relation-endpoint">{familyRoles[e.kind]&&<small>{familyRoles[e.kind][1]}</small>}{personLink(e.target_id)}</div></div></article>;
          })}</section>}
          </div>
          {!!geometry?.redundantSiblings.length&&<details className="family-sibling-summary"><summary>Братья и сёстры · общая родительская ветвь</summary>{graph.edges.filter(e=>geometry.redundantSiblings.includes(e.id)).map(e=><p key={e.id}>{graph.nodes.find(n=>n.id===e.source_id)?.name} — {relationLabel(e)} — {graph.nodes.find(n=>n.id===e.target_id)?.name}</p>)}</details>}
          {!!activeEdges.length && <div className="family-relationship-detail" role="status"><div>{activeEdges.map(e=><p key={e.id}>{graph.nodes.find(n=>n.id===e.source_id)?.name} — {relationLabel(e)} — {graph.nodes.find(n=>n.id===e.target_id)?.name}</p>)}</div><button aria-label="Закрыть сведения о связи" onClick={()=>setEdgeDetail(null)}>×</button></div>}
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
