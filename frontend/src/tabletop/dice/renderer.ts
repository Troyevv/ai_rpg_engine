import * as T from "three";
import type { VisualDie } from "./canonical";
function ten() {
  const ring = Array.from(
    { length: 10 },
    (_, i) =>
      new T.Vector3(
        Math.cos((i * Math.PI) / 5),
        i % 2 ? -0.105 : 0.105,
        Math.sin((i * Math.PI) / 5),
      ),
  );
  const h = (0.105 * (1 + Math.cos(Math.PI / 5))) / (1 - Math.cos(Math.PI / 5));
  const vertices: number[] = [];
  for (let i = 0; i < 10; i++) {
    const points = [
      new T.Vector3(0, i % 2 ? -h : h, 0),
      ring[i],
      ring[(i + 1) % 10],
      ring[(i + 2) % 10],
    ];
    const normal = new T.Vector3()
      .subVectors(points[1], points[0])
      .cross(new T.Vector3().subVectors(points[2], points[0]));
    if (normal.dot(points[1]) < 0) points.reverse();
    for (const j of [1, 2])
      for (const p of [points[0], points[j], points[j + 1]])
        vertices.push(...p.toArray());
  }
  const g = new T.BufferGeometry();
  g.setAttribute("position", new T.Float32BufferAttribute(vertices, 3));
  g.computeVertexNormals();
  return g;
}
function geometry(sides: number) {
  switch (sides) {
    case 4:
      return new T.TetrahedronGeometry(0.72);
    case 6:
      return new T.BoxGeometry(1, 1, 1);
    case 8:
      return new T.OctahedronGeometry(0.8);
    case 10:
      return ten().scale(0.72, 0.72, 0.72);
    case 12:
      return new T.DodecahedronGeometry(0.78);
    default:
      return new T.IcosahedronGeometry(0.8);
  }
}
function physicalDie(d: VisualDie) {
  const root = new T.Group(),
    g = geometry(d.sides),
    geom = g.index ? g.toNonIndexed() : g;
  const material = new T.MeshStandardMaterial({
    color: d.muted ? 0x747c85 : 0x246a87,
    roughness: 0.32,
    metalness: 0.22,
    flatShading: true,
  });
  root.add(new T.Mesh(geom, material));
  root.add(
    new T.LineSegments(
      new T.EdgesGeometry(geom),
      new T.LineBasicMaterial({ color: 0xe3c98d }),
    ),
  );
  const pos = geom.getAttribute("position");
  const faces = new Map<
    string,
    { normal: T.Vector3; sum: T.Vector3; count: number }
  >();
  for (let i = 0; i < pos.count; i += 3) {
    const a = new T.Vector3().fromBufferAttribute(pos, i),
      b = new T.Vector3().fromBufferAttribute(pos, i + 1),
      c = new T.Vector3().fromBufferAttribute(pos, i + 2);
    const n = b.clone().sub(a).cross(c.clone().sub(a)).normalize();
    const key = n
      .toArray()
      .map((v) => Math.round(v * 1000))
      .join(",");
    const face = faces.get(key) || {
      normal: n,
      sum: new T.Vector3(),
      count: 0,
    };
    face.sum.add(a).add(b).add(c);
    face.count += 3;
    faces.set(key, face);
  }
  let target = new T.Quaternion();
  [...faces.values()].forEach((face, i) => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 128;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#fff9dc";
    ctx.font = "bold 86px system-ui";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(
      d.percentile === "tens"
        ? String(i * 10).padStart(2, "0")
        : d.percentile === "ones"
          ? String(i)
          : String(i + 1),
      64,
      67,
    );
    const texture = new T.CanvasTexture(canvas),
      label = new T.Mesh(
        new T.PlaneGeometry(
          d.sides === 20 ? 0.32 : 0.46,
          d.sides === 20 ? 0.32 : 0.46,
        ),
        new T.MeshBasicMaterial({
          map: texture,
          transparent: true,
          depthWrite: false,
        }),
      );
    label.position
      .copy(face.sum.divideScalar(face.count))
      .addScaledVector(face.normal, 0.008);
    label.quaternion.setFromUnitVectors(new T.Vector3(0, 0, 1), face.normal);
    root.add(label);
    if (i + 1 === d.value) {
      target = new T.Quaternion().setFromUnitVectors(
        face.normal,
        new T.Vector3(0, 1, 0),
      );
      const up = new T.Vector3(0, 1, 0)
        .applyQuaternion(label.quaternion)
        .applyQuaternion(target);
      const yaw = Math.atan2(up.x, -up.z);
      target.premultiply(
        new T.Quaternion().setFromAxisAngle(new T.Vector3(0, 1, 0), yaw),
      );
    }
  });
  if (geom !== g) g.dispose();
  return { root, target, material, muted: d.muted, vertices: pos };
}
export function renderDice(
  host: HTMLElement,
  dice: VisualDie[],
  finish: () => void,
) {
  const renderer = new T.WebGLRenderer({ alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
  renderer.setSize(host.clientWidth, 220);
  host.append(renderer.domElement);
  const scene = new T.Scene();
  scene.add(new T.HemisphereLight(0xffffff, 0x405063, 2));
  const light = new T.DirectionalLight(0xffffff, 3);
  light.position.set(-3, 8, 5);
  scene.add(light);
  const aspect = host.clientWidth / 220,
    vertical = dice.length > 4 ? 3 : 2.7,
    span = Math.max(Math.min(4, dice.length) * 0.95, vertical * aspect);
  const camera = new T.OrthographicCamera(
    -span,
    span,
    span / aspect,
    -span / aspect,
    0.1,
    100,
  );
  camera.position.set(0, 10, 10);
  camera.lookAt(0, 1, 0);
  const plane = new T.Mesh(
    new T.PlaneGeometry(30, 30),
    new T.MeshStandardMaterial({
      color: 0x53616a,
      transparent: true,
      opacity: 0.16,
    }),
  );
  plane.rotation.x = -Math.PI / 2;
  scene.add(plane);
  const objects = dice.map(physicalDie);
  objects.forEach((d) => scene.add(d.root));
  let raf = 0,
    stopped = false;
  const start = performance.now();
  const resize = new ResizeObserver(() => {
    const width = host.clientWidth;
    renderer.setSize(width, 220);
    const horizontal = Math.max(
      Math.min(4, dice.length) * 0.95,
      vertical * (width / 220),
    );
    camera.left = -horizontal;
    camera.right = horizontal;
    camera.top = horizontal / (width / 220);
    camera.bottom = -camera.top;
    camera.updateProjectionMatrix();
  });
  resize.observe(host);
  function frame(now: number) {
    if (stopped) return;
    const t = Math.min(1, (now - start) / 1500);
    objects.forEach((d, i) => {
      const columns = Math.min(4, objects.length),
        rows = Math.ceil(objects.length / columns),
        x = ((i % columns) - (columns - 1) / 2) * 1.65,
        z = (Math.floor(i / columns) - (rows - 1) / 2) * 1.65;
      const spin = new T.Quaternion().setFromEuler(
        new T.Euler((1 - t) * 13 + i, (1 - t) * 10 + i / 3, (1 - t) * 7),
      );
      d.root.quaternion
        .copy(spin)
        .slerp(d.target, Math.max(0, (t - 0.66) / 0.34));
      const sample = new T.Vector3();
      let lowest = 0;
      for (let j = 0; j < d.vertices.count; j++) {
        sample
          .fromBufferAttribute(d.vertices, j)
          .applyQuaternion(d.root.quaternion);
        lowest = Math.min(lowest, sample.y);
      }
      const flight =
        t < 0.44
          ? 2.1 * 4 * (t / 0.44) * (1 - t / 0.44)
          : t < 0.72
            ? 0.62 * Math.sin(((t - 0.44) / 0.28) * Math.PI)
            : t < 0.9
              ? 0.17 * Math.sin(((t - 0.72) / 0.18) * Math.PI)
              : 0;
      d.root.position.set(
        x + (1 - t) * (i % 2 ? 1 : -1),
        -lowest + flight,
        z + (1 - t) * 1.6,
      );
      d.material.color.setHex(t > 0.9 && d.muted ? 0x44484d : 0x246a87);
    });
    renderer.render(scene, camera);
    if (t < 1) raf = requestAnimationFrame(frame);
    else timer = window.setTimeout(finish, 260);
  }
  let timer = 0;
  raf = requestAnimationFrame(frame);
  return () => {
    stopped = true;
    cancelAnimationFrame(raf);
    clearTimeout(timer);
    resize.disconnect();
    scene.traverse((o) => {
      const mesh = o as T.Mesh;
      if (mesh.geometry) mesh.geometry.dispose();
      if (mesh.material) {
        for (const m of Array.isArray(mesh.material)
          ? mesh.material
          : [mesh.material]) {
          const map = (m as T.MeshBasicMaterial).map;
          map?.dispose();
          m.dispose();
        }
      }
    });
    renderer.dispose();
    renderer.forceContextLoss();
    renderer.domElement.remove();
  };
}
