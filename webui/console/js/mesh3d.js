// mesh3d.js — STEP 真 3D 查看器: /v1/drawings/{id}/mesh → BufferGeometry + 手写轨道控制
import { jget, esc } from "./api.js";
import { openModal, toast } from "./ui.js";

function b64ToBuf(b64) {
  const bin = atob(b64);
  const u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  return u.buffer;
}

export async function openMeshViewer(drawingId, name) {
  const m = openModal(`3D 预览 · ${name || drawingId}`,
    `<div class="viewer-wrap"><div class="viewer-stats">网格加载中… (OCP 细分可能需数秒)</div></div>
     <div class="row" style="margin-top:10px"><span class="dim">左键拖动旋转 · 滚轮缩放 · 右键拖动平移</span><span class="spacer"></span>
     <button class="btn ghost sm" id="mv-reset">复位视角</button></div>`);
  const wrap = m.body.querySelector(".viewer-wrap");
  try {
    const mesh = await jget(`/v1/drawings/${encodeURIComponent(drawingId)}/mesh`);
    buildScene(wrap, mesh);
  } catch (e) {
    wrap.querySelector(".viewer-stats").textContent = "";
    wrap.innerHTML = `<div class="empty" style="border:0"><div class="t">网格构建失败</div><div>${esc(e.message)} — 文件可能损坏或非流形</div></div>`;
  }
  return m;
}

function buildScene(wrap, mesh) {
  const THREE = window.THREE;
  if (!THREE) { wrap.querySelector(".viewer-stats").textContent = "three.min.js 未加载"; return; }
  const pos = new Float32Array(b64ToBuf(mesh.positions_b64));
  const idx = new Uint32Array(b64ToBuf(mesh.indices_b64));
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setIndex(new THREE.BufferAttribute(idx, 1));
  geo.computeVertexNormals();
  // 居中 + 归一缩放到半径 1 球内
  geo.computeBoundingBox();
  const bb = geo.boundingBox, c = new THREE.Vector3(), s = new THREE.Vector3();
  bb.getCenter(c); bb.getSize(s);
  geo.translate(-c.x, -c.y, -c.z);
  const scale = 1.6 / Math.max(s.x, s.y, s.z, 1e-9);
  geo.scale(scale, scale, scale);

  const w = wrap.clientWidth || 800, h = wrap.clientHeight || 520;
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(w, h); renderer.setPixelRatio(window.devicePixelRatio || 1);
  wrap.appendChild(renderer.domElement);
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x0a0e13);
  const cam = new THREE.PerspectiveCamera(45, w / h, 0.05, 100);
  scene.add(new THREE.HemisphereLight(0xbfd4e8, 0x202428, 1.1));
  const dl = new THREE.DirectionalLight(0xffffff, 1.4); dl.position.set(3, 5, 4); scene.add(dl);
  const mat = new THREE.MeshStandardMaterial({ color: 0x9fb6c9, metalness: 0.55, roughness: 0.42, side: THREE.DoubleSide });
  const obj = new THREE.Mesh(geo, mat); scene.add(obj);
  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 30), new THREE.LineBasicMaterial({ color: 0x2e3d4d }));
  obj.add(edges);

  // ---- 手写轨道控制 ----
  const ctl = { theta: 0.7, phi: 1.15, radius: 4.2, pan: new THREE.Vector3(), drag: null };
  function apply() {
    const sp = Math.sin(ctl.phi), cp = Math.cos(ctl.phi);
    cam.position.set(ctl.radius * sp * Math.sin(ctl.theta) + ctl.pan.x,
                     ctl.radius * cp + ctl.pan.y,
                     ctl.radius * sp * Math.cos(ctl.theta) + ctl.pan.z);
    cam.lookAt(ctl.pan);
  }
  const el = renderer.domElement;
  el.addEventListener("contextmenu", e => e.preventDefault());
  el.addEventListener("pointerdown", e => { ctl.drag = { x: e.clientX, y: e.clientY, btn: e.button }; el.setPointerCapture(e.pointerId); });
  el.addEventListener("pointerup", e => { ctl.drag = null; });
  el.addEventListener("pointermove", e => {
    if (!ctl.drag) return;
    const dx = e.clientX - ctl.drag.x, dy = e.clientY - ctl.drag.y;
    ctl.drag = { x: e.clientX, y: e.clientY, btn: ctl.drag.btn };
    if (ctl.drag.btn === 2 || e.shiftKey) {
      const k = ctl.radius * 0.0016;
      const right = new THREE.Vector3().setFromMatrixColumn(cam.matrix, 0);
      const up = new THREE.Vector3().setFromMatrixColumn(cam.matrix, 1);
      ctl.pan.addScaledVector(right, -dx * k).addScaledVector(up, dy * k);
    } else {
      ctl.theta -= dx * 0.008;
      ctl.phi = Math.min(Math.PI - 0.05, Math.max(0.05, ctl.phi - dy * 0.008));
    }
  });
  el.addEventListener("wheel", e => { e.preventDefault(); ctl.radius = Math.min(30, Math.max(0.6, ctl.radius * (1 + Math.sign(e.deltaY) * 0.09))); }, { passive: false });
  document.getElementById("mv-reset")?.addEventListener("click", () => {
    ctl.theta = 0.7; ctl.phi = 1.15; ctl.radius = 4.2; ctl.pan.set(0, 0, 0);
  });

  wrap.querySelector(".viewer-stats").textContent =
    `顶点 ${mesh.vertex_count.toLocaleString()} · 三角面 ${mesh.tri_count.toLocaleString()}\n` +
    `bbox ${mesh.bbox ? mesh.bbox.map(v => v.toFixed(1)).join(" × ") + " mm" : "—"} · deflection ${mesh.deflection ?? "—"}`;
  (function loop() { apply(); renderer.render(scene, cam); requestAnimationFrame(loop); })();
  toast(`网格就绪: ${mesh.tri_count.toLocaleString()} 三角面`);
}
