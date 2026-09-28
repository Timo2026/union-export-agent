// tabs/drawings.js — 图纸台: STEP 缩略图网格 + 真 3D (OCP 网格) + 上传 + 搜索/客户筛选/分页
import { jget, esc, fmtTs, fmtBytes } from "../api.js";
import { openDrawer, openModal, toast } from "../ui.js";
import { openMeshViewer } from "../mesh3d.js";

const st = { page: 1, size: 12, q: "", customer: "", total: 0, pages: 1 };

export function render(view) {
  view.innerHTML = `
  <div class="panel">
    <h3>图纸台 <span class="hint">· STEP 构件库 (/v1/drawings), 3D 走 OCP 网格化子进程</span></h3>
    <div class="filters">
      <label>搜索 <input id="d-q" placeholder="文件名 / 客户 / sha" value="${esc(st.q)}"></label>
      <label>客户 <input id="d-cust" placeholder="customer" value="${esc(st.customer)}"></label>
      <button class="btn sm" id="d-go">查询</button>
      <span class="spacer"></span>
      <button class="btn" id="d-up">⬆ 上传 STEP</button>
    </div>
    <div id="d-grid" class="dgrid"></div>
    <div class="pager" id="d-pager"></div>
  </div>`;

  load(view);
  view.querySelector("#d-go").onclick = () => { pullFilters(view); st.page = 1; load(view); };
  view.querySelector("#d-q").addEventListener("keydown", e => { if (e.key === "Enter") { pullFilters(view); st.page = 1; load(view); } });
  view.querySelector("#d-up").onclick = () => openUpload(view);
}

function pullFilters(view) {
  st.q = view.querySelector("#d-q").value.trim();
  st.customer = view.querySelector("#d-cust").value.trim();
}

async function load(view) {
  const grid = view.querySelector("#d-grid");
  grid.innerHTML = `<div class="loading">加载图纸…</div>`;
  let d;
  try {
    d = await jget(`/v1/drawings?${new URLSearchParams({ page: st.page, page_size: st.size, q: st.q, customer: st.customer })}`);
  } catch (e) { grid.innerHTML = `<div class="empty"><div class="t">加载失败</div><div>${esc(e.message)}</div></div>`; return; }
  st.total = d.total; st.pages = d.pages;
  if (!d.items.length) {
    grid.innerHTML = `<div style="grid-column:1/-1"><div class="empty"><div class="t">没有匹配的图纸</div><div>上传 .step/.stp 后入库; 支持按文件名/客户/sha 搜索</div></div></div>`;
  } else {
    grid.innerHTML = d.items.map(r => `
      <div class="dcard" data-id="${esc(r.id)}">
        <div class="thumb"><img loading="lazy" src="/v1/drawings/${encodeURIComponent(r.id)}/thumbnail" alt="" onerror="this.parentNode.innerHTML='<span class=dim>无预览</span>'"></div>
        <div class="meta">
          <div class="name">${esc(r.name)}</div>
          <div class="muted-cell mono">${esc(r.id)}</div>
          <div class="muted-cell">${esc(r.customer || "未关联客户")}${r.context_id ? ` · ${esc(r.context_id)}` : ""}</div>
          <div class="muted-cell">${fmtBytes(r.size_bytes)} · ${fmtTs(r.mtime)} · sha ${esc(r.sha256_16)}</div>
          <div class="acts">
            <button class="btn sm" data-a="3d">🧊 3D</button>
            <button class="btn ghost sm" data-a="info">详情</button>
          </div>
        </div>
      </div>`).join("");
    grid.querySelectorAll(".dcard").forEach(card => card.addEventListener("click", e => {
      const id = card.dataset.id, row = d.items.find(x => x.id === id);
      const a = e.target.closest("[data-a]")?.dataset.a;
      if (a === "3d") openMeshViewer(row.id, row.name);
      else openInfo(row);
    }));
  }
  view.querySelector("#d-pager").innerHTML = `共 ${st.total} 张 · 第 ${st.page}/${st.pages} 页
    <button class="btn ghost sm" ${st.page <= 1 ? "disabled" : ""} data-p="prev">←</button>
    <button class="btn ghost sm" ${st.page >= st.pages ? "disabled" : ""} data-p="next">→</button>`;
  view.querySelector("#d-pager").querySelectorAll("[data-p]").forEach(b => b.onclick = () => {
    st.page = b.dataset.p === "prev" ? st.page - 1 : st.page + 1; load(view);
  });
}

function openInfo(row) {
  const d = openDrawer(row.name);
  d.body.innerHTML = `<dl class="kv">
    <dt>id</dt><dd class="mono">${esc(row.id)}</dd>
    <dt>客户</dt><dd>${esc(row.customer || "—")}</dd>
    <dt>context</dt><dd class="mono">${esc(row.context_id || "—")}</dd>
    <dt>大小 / 时间</dt><dd>${fmtBytes(row.size_bytes)} · ${fmtTs(row.mtime)}</dd>
    <dt>sha256 (16)</dt><dd class="mono">${esc(row.sha256_16)}</dd>
    <dt>网格缓存</dt><dd>${row.has_mesh ? "✓ 已生成" : "未生成 (首次点 3D 时由 OCP 子进程构建)"}</dd>
  </dl>
  <div class="sect" style="margin-top:14px"><h4>SVG 缩略图</h4>
    <img src="/v1/drawings/${encodeURIComponent(row.id)}/thumbnail" style="max-width:100%;background:#0a0e13;border-radius:8px"></div>`;
}

function openUpload(view) {
  const m = openModal("上传 STEP 图纸", `<div class="form">
    <label>.step / .stp 文件 *<input id="u-file" type="file" accept=".step,.stp"></label>
    <label>关联客户<input id="u-cust" placeholder="customer_id 或客户名, 可空"></label>
    <label>关联 context<input id="u-cid" placeholder="RFQ-…, 可空"></label>
    <button class="btn" id="u-go">上传并解析</button>
    <div class="hint" style="margin-top:8px">后端: /v1/upload/step-with-thumbnail (OCP 几何 + SVG 缩略图, 需数秒)</div></div>`);
  m.body.querySelector("#u-go").onclick = async () => {
    const f = m.body.querySelector("#u-file").files[0];
    if (!f) return toast("请选择文件", "err");
    const fd = new FormData();
    fd.append("file", f);
    fd.append("customer", m.body.querySelector("#u-cust").value.trim());
    fd.append("context_id", m.body.querySelector("#u-cid").value.trim());
    toast("上传中, OCP 解析需要数秒…");
    try {
      const r = await fetch("/v1/upload/step-with-thumbnail", { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail));
      m.close(); toast(`入库成功: ${j.drawing_id} (bbox ${j.bbox ? j.bbox.map(v => v.toFixed(1)).join("×") : "?"})`);
      st.page = 1; load(view);
    } catch (e) { toast(`上传失败: ${e.message}`, "err"); }
  };
}
