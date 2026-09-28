// tabs/intel.js — 客户情报: 联网 enrich (SearXNG) + 本地画像 + RAG 语义检索 + 多模态情报库管理
import { jget, jpost, jdel, esc, fmtTs, mockBadge } from "../api.js";
import { openModal, toast } from "../ui.js";

export function render(view) {
  view.innerHTML = `
  <div class="panel">
    <h3>客户情报检索 <span class="hint">· 联网搜索走本地 SearXNG (:8888); 不可达显式 MOCK</span></h3>
    <div class="filters">
      <label style="flex:1">客户名 <input id="i-name" placeholder="如: Hager / 汇川 / CUST-001" style="width:100%"></label>
      <button class="btn sm" id="i-go">🌐 情报聚合</button>
      <button class="btn ghost sm" id="i-rag">📚 RAG 语义检索</button>
    </div>
    <div id="i-out" class="dim">输入客户名开始; 结果 = 联网命中 + 本地沙箱画像 (定价模型/近期报价)。</div>
  </div>
  <div class="panel">
    <h3>多模态情报库 <span class="hint">· 音频/图片/视频 → ASR/VLM 转写 → ingest_docs 向量集合 (omni + embedding)</span></h3>
    <div id="i-msvc" class="row" style="margin-bottom:10px"></div>
    <div class="filters">
      <label>模态 <select id="i-mod"><option value="">全部</option><option>audio</option><option>image</option><option>video</option></select></label>
      <label>客户 <input id="i-mcust"></label>
      <button class="btn ghost sm" id="i-mreload">⟳</button>
      <span class="spacer"></span>
      <button class="btn" id="i-mup">⬆ 入库音频/图片</button>
    </div>
    <div id="i-mdocs"></div>
  </div>`;

  view.querySelector("#i-go").onclick = () => enrich(view);
  view.querySelector("#i-name").addEventListener("keydown", e => { if (e.key === "Enter") enrich(view); });
  view.querySelector("#i-rag").onclick = () => ragSearch(view);
  view.querySelector("#i-mup").onclick = () => uploadMedia(view);
  view.querySelector("#i-mreload").onclick = () => { loadMedia(view); loadMediaStatus(view); };
  view.querySelector("#i-mod").onchange = () => loadMedia(view);
  loadMedia(view); loadMediaStatus(view);
}

async function enrich(view) {
  const name = view.querySelector("#i-name").value.trim();
  if (!name) return;
  const out = view.querySelector("#i-out");
  out.innerHTML = `<div class="loading">联网 + 本地画像聚合中…</div>`;
  let d;
  try { d = await jget(`/v1/customer/enrich?name=${encodeURIComponent(name)}`); }
  catch (e) { out.innerHTML = `<span style="color:var(--bad)">失败: ${esc(e.message)}</span>`; return; }

  const web = d.web || {};
  out.className = "";
  out.innerHTML = `
    <div class="grid cols-2">
      <div><h4 style="margin:4px 0">🌐 联网命中 ${mockBadge(web)}</h4>
        ${(web.hits || []).length ? web.hits.map(h => `<div class="hit"><div class="title"><a href="${esc(h.url)}" target="_blank" rel="noopener">${esc(h.title)}</a></div>
          <div class="muted-cell mono">${esc((h.url || "").slice(0, 80))} · ${esc(h.engine || "")}</div>
          <div class="snippet">${esc(h.snippet || "")}</div></div>`).join("")
          : `<div class="dim">${web.mock ? "SearXNG 不可达 → 无在线命中 (显式 MOCK, 不冒充)" : "无命中"} ${web.warning ? `· ${esc(web.warning)}` : ""}</div>`}
      </div>
      <div><h4 style="margin:4px 0">🏭 本地画像 (${d.profile?.match_count ?? 0} 个匹配)</h4>
        ${(d.profile?.matched || []).map(c => `<div class="hit"><div class="title mono">${esc(c.customer_id)}</div>
          <div class="kv"><dt>定价模型</dt><dd>${esc(JSON.stringify(c.pricing_model || {}).slice(0, 300))}</dd>
          <dt>近期报价</dt><dd>${(c.recent_quotes || []).slice(0, 5).map(q => `${esc(q.context_id || "")} ${esc(q.material || "")}/${esc(q.surface || "")} $${q.unit_price ?? "?"}`).join("<br>") || "—"}</dd></div></div>`).join("")
          || `<div class="dim">本地沙箱无此客户</div>`}
      </div>
    </div>
    <div class="muted-cell" style="margin-top:8px">生成时间 ${esc(d.generated_at || "")}</div>`;
}

async function ragSearch(view) {
  const q = prompt("RAG 语义检索 (工艺知识 + 历史案例):");
  if (!q) return;
  const d = await jget(`/v1/rag/search?${new URLSearchParams({ q, limit: 6 })}`).catch(e => ({ error: e.message }));
  const out = view.querySelector("#i-out");
  if (d.error) { out.innerHTML = esc(d.error); return; }
  out.className = "";
  out.innerHTML = `<h4 style="margin:4px 0">📚 RAG 命中 ${mockBadge(d)}</h4>` +
    (( d.hits || d.results || []).map(h => `<div class="hit"><div class="title">${esc(h.title || h.case || h.id || "hit")}</div><div class="snippet">${esc(JSON.stringify(h).slice(0, 400))}</div></div>`).join("")
      || `<div class="dim">无命中 (embedding 可能处于 MOCK:hash-embedder 降级)</div>`);
}

async function loadMediaStatus(view) {
  const el = view.querySelector("#i-msvc");
  const s = await jget("/v1/rag/media/status").catch(() => null);
  if (!s) { el.innerHTML = `<span class="dim">媒体服务状态获取失败</span>`; return; }
  const chip = (label, on, src) => `<span class="chip ${on ? "on" : "mocked"}" title="${esc(src || "")}"><span class="dot"></span>${esc(label)}: ${on ? "在线" : "MOCK/离线"}</span>`;
  el.innerHTML = chip(`ASR (${esc(s.asr?.mode || "")})`, !!s.asr?.online, s.asr?.source) +
    chip("VLM", !!s.vlm?.online, s.vlm?.url) +
    chip("Embedding", !s.embed?.degraded, s.embed?.source) +
    chip("ffmpeg", !!s.ffmpeg) +
    `<span class="chip">情报库文档 ${s.docs ?? "—"}</span>`;
}

async function loadMedia(view) {
  const box = view.querySelector("#i-mdocs");
  const mod = view.querySelector("#i-mod")?.value || "", cust = view.querySelector("#i-mcust")?.value.trim() || "";
  box.innerHTML = `<div class="loading">加载情报库…</div>`;
  let d;
  try { d = await jget(`/v1/rag/media/docs?${new URLSearchParams({ modality: mod, customer: cust })}`); }
  catch (e) { box.innerHTML = `<span style="color:var(--bad)">${esc(e.message)}</span>`; return; }
  if (!d.items.length) { box.innerHTML = `<div class="empty"><div class="t">情报库为空</div><div>上传通话录音 / 现场照片, ASR/VLM 转写后自动向量化入库</div></div>`; return; }
  box.innerHTML = `<table class="tbl"><thead><tr><th>ID</th><th>模态</th><th>客户</th><th>标签</th><th>时间</th><th></th></tr></thead><tbody>
    ${d.items.map(x => `<tr><td class="mono">${esc(x.id)}</td><td><span class="badge">${esc(x.modality)}</span></td>
      <td>${esc(x.customer_id || "—")}</td><td class="muted-cell">${esc((x.tags || []).join(", "))}</td>
      <td class="muted-cell">${fmtTs(x.indexed_at || x.created_at)}</td>
      <td class="no-row-click"><button class="btn ghost sm" data-v="${esc(x.id)}">查看</button> <button class="btn danger sm" data-d="${esc(x.id)}">删除</button></td></tr>`).join("")}
  </tbody></table><div class="muted-cell" style="margin-top:6px">共 ${d.total} 条 · 模态: ${esc((d.modalities || []).join("/") || "—")}</div>`;
  box.querySelectorAll("[data-d]").forEach(b => b.onclick = async () => {
    if (!confirm(`删除情报文档 ${b.dataset.d} (向量 + 原始文件)?`)) return;
    try { await jdel(`/v1/rag/media/docs/${encodeURIComponent(b.dataset.d)}`); toast("已删除"); loadMedia(view); }
    catch (e) { toast(`删除失败: ${e.message}`, "err"); }
  });
  box.querySelectorAll("[data-v]").forEach(b => b.onclick = async () => {
    const x = await jget(`/v1/rag/media/docs/${encodeURIComponent(b.dataset.v)}`).catch(e => ({ error: e.message }));
    openModal(b.dataset.v, `<pre class="raw">${esc(JSON.stringify(x, null, 1).slice(0, 4000))}</pre>`);
  });
}

function uploadMedia(view) {
  const m = openModal("多模态情报入库", `<div class="form">
    <label>文件 (音频 wav/mp3/m4a · 图片 png/jpg · 视频 mp4)<input id="m-file" type="file" accept=".wav,.mp3,.m4a,.flac,.ogg,.png,.jpg,.jpeg,.webp,.mp4,.mov"></label>
    <label>关联客户<input id="m-cust"></label>
    <button class="btn" id="m-go">转写并入库</button>
    <div class="hint" style="margin-top:8px">离线服务未启动时: 转写失败会显式 MOCK 拒绝入库, 不冒充。</div></div>`);
  m.body.querySelector("#m-go").onclick = async () => {
    const f = m.body.querySelector("#m-file").files[0];
    if (!f) return toast("请选择文件", "err");
    const fd = new FormData();
    fd.append("file", f); fd.append("customer", m.body.querySelector("#m-cust").value.trim());
    toast("转写中 (ASR/VLM 在线时需等待)…");
    try {
      const r = await fetch("/v1/rag/media/ingest", { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j));
      m.close(); toast(`入库成功: ${j.doc?.id || ""} ${j.mock ? "(MOCK)" : ""}`);
      loadMedia(view); loadMediaStatus(view);
    } catch (e) { toast(`入库失败: ${e.message}`, "err"); }
  };
}
