// tabs/ops.js — 本地状态: 各服务健康卡片 + 邮件链路 + 缓存/NIM/Spark/飞轮 + trace 查询
import { jget, jpost, esc, fmtTs, mockBadge } from "../api.js";
import { toast } from "../ui.js";

const CARDS = [
  { key: "core", label: "核心 API /health", url: "/health" },
  { key: "config", label: "热载配置 /v1/config/status", url: "/v1/config/status" },
  { key: "puller", label: "邮件链路 /v1/mail/puller/status", url: "/v1/mail/puller/status" },
  { key: "media", label: "多模态服务 /v1/rag/media/status", url: "/v1/rag/media/status" },
  { key: "cache", label: "Agent 缓存 /v1/cache/stats", url: "/v1/cache/stats" },
  { key: "nim", label: "NIM 探活 /v1/nim/health", url: "/v1/nim/health" },
  { key: "spark", label: "Spark 仪表板 /v1/spark/dashboard", url: "/v1/spark/dashboard" },
  { key: "flywheel", label: "客户飞轮 /v1/flywheel/stats", url: "/v1/flywheel/stats" },
];

export function render(view) {
  view.innerHTML = `
  <div class="panel">
    <h3>本地状态总览 <span class="hint">· 全部来自真实端点; 不可达即红, 降级即 MOCK 标注</span></h3>
    <div class="row"><button class="btn" id="op-refresh">⟳ 全部刷新</button>
      <span id="op-ts" class="dim"></span></div>
    <div id="op-cards" class="grid cols-3" style="margin-top:14px"></div>
  </div>
  <div class="panel">
    <h3>执行链路 Trace 查询 <span class="hint">· /v1/traces/{context_id} · OTEL 风格 span</span></h3>
    <div class="filters"><label>context_id <input id="tr-cid" placeholder="RFQ-…" style="min-width:260px"></label>
      <button class="btn sm" id="tr-go">查询</button></div>
    <div id="tr-out" class="dim">输入 context_id (可从邮件详情 / 订单详情带入)</div>
  </div>`;

  const refresh = () => {
    view.querySelector("#op-ts").textContent = "更新于 " + new Date().toLocaleTimeString();
    CARDS.forEach(c => loadCard(view, c));
  };
  view.querySelector("#op-refresh").onclick = refresh;
  refresh();
  view.querySelector("#tr-go").onclick = () => lookup(view);
  view.querySelector("#tr-cid").addEventListener("keydown", e => { if (e.key === "Enter") lookup(view); });
}

async function loadCard(view, c) {
  const box = view.querySelector("#op-cards");
  let el = box.querySelector(`[data-c="${c.key}"]`);
  if (!el) { el = document.createElement("div"); el.dataset.c = c.key; box.appendChild(el); }
  el.className = "panel"; el.style.margin = "0";
  el.innerHTML = `<h3 style="font-size:13px">${esc(c.label)}</h3><div class="loading">…</div>`;
  try {
    const d = await jget(c.url);
    el.innerHTML = `<h3 style="font-size:13px">${esc(c.label)} ${mockBadge(d)}</h3>
      <pre class="raw" style="max-height:180px;margin:0">${esc(JSON.stringify(d, null, 1).slice(0, 1200))}</pre>`;
  } catch (e) {
    el.innerHTML = `<h3 style="font-size:13px">${esc(c.label)}</h3>
      <div class="row"><span class="badge mock" style="border-color:var(--bad);color:#f2a0a0">✗ 不可达</span><span class="dim">${esc(e.message)}</span></div>`;
  }
}

async function lookup(view) {
  const cid = view.querySelector("#tr-cid").value.trim();
  if (!cid) return;
  const out = view.querySelector("#tr-out");
  out.className = "loading"; out.textContent = "查询中…";
  let d;
  try { d = await jget(`/v1/traces/${encodeURIComponent(cid)}`); }
  catch (e) { out.className = ""; out.innerHTML = `<span style="color:var(--bad)">未找到: ${esc(e.message)}</span>`; return; }
  const spans = d.spans || [];
  out.className = "";
  out.innerHTML = `<div class="muted-cell" style="margin-bottom:6px">${esc(d.context_id)} · ${d.span_count ?? spans.length} spans</div>
    <table class="tbl"><thead><tr><th>#</th><th>span</th><th>状态</th><th>耗时</th><th>详情</th></tr></thead><tbody>
    ${spans.map((s, i) => `<tr><td>${i}</td><td class="mono">${esc(s.name || s.operation || "?")}</td>
      <td>${s.status === "error" || s.ok === false ? `<span class="badge mock">error</span>` : `<span class="badge live">ok</span>`}</td>
      <td class="num">${s.duration_ms != null ? esc(s.duration_ms) + "ms" : "—"}</td>
      <td class="muted-cell">${esc(JSON.stringify(s.attributes || s.detail || {}).slice(0, 160))}</td></tr>`).join("")}
    </tbody></table>`;
}
