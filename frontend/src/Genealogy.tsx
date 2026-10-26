import { useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  useReactFlow,
  useNodesInitialized,
  type NodeProps,
} from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import "@xyflow/react/dist/style.css";
import { useReducedMotion } from "framer-motion";
import { calendarDate } from "./gameDate";
import { api } from "./api";
import type { Genealogy as Graph, Save } from "./types";
import { CharacterAvatar } from "./Portrait";
import { socialLabel, lifeLabel } from "./lib/social";
const nodeTypes = {
  person: ({ data }: NodeProps) => (
    <div className="family-node">
      <Handle type="target" position={Position.Top} />
      <CharacterAvatar
        subject={data.subject as any}
        saveId={data.saveId as number}
      />
      <strong>{String(data.label)}</strong>
      <small>{lifeLabel(String(data.status))}</small>
      {(data.subject as any).birth_date && (
        <small>{calendarDate((data.subject as any).birth_date, "short")}</small>
      )}
      <Handle type="source" position={Position.Bottom} />
    </div>
  ),
};
function Fit({ version }: { version: string }) {
  const flow = useReactFlow();
  const initialized = useNodesInitialized();
  const reduced = useReducedMotion();
  useEffect(() => {
    if (!initialized) return;
    const id = requestAnimationFrame(
      () => void flow.fitView({ padding: 0.15, duration: reduced ? 0 : 240 }),
    );
    return () => cancelAnimationFrame(id);
  }, [version, initialized]);
  return null;
}
export function Genealogy({ save, rootId }: { save: Save; rootId?: string }) {
  const [roots,setRoots]=useState<{id:string;name:string}[]>([]);
  useEffect(()=>{let live=true;setRoots([]);api<{id:string;name:string}[]>(`/saves/${save.id}/genealogy-roots`).then(r=>{if(live)setRoots(r)}).catch(e=>{if(live)setError(e.message)});return()=>{live=false}},[save.id,save.revision,save.state.controlled_actor_id]);
  const [search,setSearch]=useState("");
  const [root, setRoot] = useState(
      rootId || save.state.controlled_actor_id || "",
    ),
    [depth, setDepth] = useState(3),
    [graph, setGraph] = useState<Graph | null>(null),
    [error, setError] = useState(""),
    [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    setRoot(rootId || save.state.controlled_actor_id || "");
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
  }, [root, depth, save.id, save.revision, save.state.controlled_actor_id]);
  const layout = useMemo(() => {
    if (!graph) return { nodes: [], edges: [] };
    // Layout-only partner components keep marriages on the same generation.
    // Every visible edge below is still an original authorized canonical relation.
    const partners = new dagre.graphlib.Graph({ directed: false });
    graph.nodes.forEach((n) => partners.setNode(n.id, {}));
    graph.edges
      .filter((e) =>
        ["spouse", "partner", "engaged", "sibling"].includes(e.kind),
      )
      .forEach((e) => partners.setEdge(e.source_id, e.target_id));
    const groups = dagre.graphlib.alg
      .components(partners)
      .map((ids) => ids.sort());
    const groupOf = new Map<string, string>();
    const g = new dagre.graphlib.Graph({ multigraph: true })
      .setGraph({ rankdir: "TB", nodesep: 50, ranksep: 100 })
      .setDefaultEdgeLabel(() => ({}));
    groups.forEach((ids, i) => {
      const key = String(i);
      g.setNode(key, { width: ids.length * 210 - 50, height: 125 });
      ids.forEach((id) => groupOf.set(id, key));
    });
    graph.edges.forEach((e) => {
      const a = groupOf.get(e.source_id)!,
        b = groupOf.get(e.target_id)!;
      if (a !== b) g.setEdge(a, b, { minlen: 1, width: 130, height: 24 }, e.id);
    });
    dagre.layout(g);
    const positions = new Map<string, { x: number; y: number }>();
    groups.forEach((ids, i) => {
      const n = g.node(String(i));
      ids.forEach((id, index) =>
        positions.set(id, {
          x: n.x - (ids.length * 210 - 50) / 2 + index * 210,
          y: n.y - 62,
        }),
      );
    });
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
        },
      })),
      edges: graph.edges.map((e) => ({
        id: e.id,
        source: e.source_id,
        target: e.target_id,
        label: `${({ parent: "Родитель", adoptive_parent: "Усыновление", guardian: "Опека" } as Record<string, string>)[e.kind] || socialLabel(e.kind)}${e.certainty === "suspected" ? " ?" : ""}${e.status === "closed" ? ` · ${socialLabel(e.outcome)}` : ""}`,
        style: {
          stroke: "var(--accent)",
          strokeDasharray:
            e.certainty === "suspected" || e.kind !== "parent"
              ? "6 4"
              : undefined,
        },
        labelStyle: { fill: "var(--text)", fontSize: 11 },
        labelBgStyle: { fill: "var(--surface-1)" },
      })),
    };
  }, [graph, save.id]);
  return (
    <section aria-label="Родословная"><div className="family-toolbar"><label>Найти персонажа<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Имя персонажа"/></label><label>Семья персонажа<select value={root} onChange={e=>{setGraph(null);setSelected(null);setRoot(e.target.value)}}>{roots.filter(c=>c.name.toLocaleLowerCase().includes(search.toLocaleLowerCase())).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label></div>
      <p className="muted">
        Только связи, известные управляемому персонажу. Пунктир отличает
        предположения и небиологические связи; смысл указан на линии.
      </p>
      <label>
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
      </label>
      {error ? (
        <p role="alert">{error}</p>
      ) : !graph ? (
        <p role="status">Загрузка родословной…</p>
      ) : graph.nodes.length === 0 ? (
        <p>Известных семейных связей пока нет.</p>
      ) : (
        <>
          {graph.edges.length===0&&<p>Известных семейных связей пока нет.</p>}<div className="family-graph">
            <ReactFlow
              nodes={layout.nodes}
              edges={layout.edges}
              nodeTypes={nodeTypes}
              fitView
              deleteKeyCode={null}
              edgesReconnectable={false}
              proOptions={{ hideAttribution: true }}
              nodesDraggable={false}
              nodesConnectable={false}
              onNodeClick={(_, n) => setSelected(n.id)}
              minZoom={0.2}
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
              <Fit version={`${root}:${depth}:${save.revision}`} />
              <Background />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
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
          <details>
            <summary>Доступный список связей</summary>
            {graph.edges.map((e) => (
              <p key={e.id}>
                {graph.nodes.find((n) => n.id === e.source_id)?.name} —{" "}
                {socialLabel(e.kind)} —{" "}
                {graph.nodes.find((n) => n.id === e.target_id)?.name}
              </p>
            ))}
            {graph.nodes.map((n) => (
              <button key={n.id} onClick={() => setRoot(n.id)}>
                {n.name}
              </button>
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
