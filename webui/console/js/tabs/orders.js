// tabs/orders.js — 订单台: /v1/orders 服务端分页/筛选 + 状态机流转 + 批量 + 建单
import { jget, jpost, jpatch, jdel, esc, fmtTs, fmtMoney, statusChip, STATUS_ZH_FALLBACK } from "../api.js";
import { makeTable, openDrawer, openModal, toast } from "../ui.js";

let META = null; // /v1/orders/meta

export async function render(view) {
  view.innerHTML = `<div class="panel">
    <h3>订单台 <span class="hint">· 独立订单实体 (data/orders.json) + 状态机: 询盘→报价→样品→批量→发货→完结</span></h3>
    <div id="ord-kpi" class="row" style="margin-bottom:12px"></div>
    <div id="ord-tbl"></div></div>`;
  META = await jget("/v1/orders/meta").catch(() => null);
  const zh = META?.status_zh || STATUS_ZH_FALLBACK;

  const tbl = makeTable({
    mount: view.querySelector("#ord-tbl"),
    selectable: true,
    rowKey: r => r.id,
    filters: [
      { key: "status", label: "状态", type: "select", options: [{ v: "", label: "全部" }, ...(META?.statuses || Object.keys(zh)).map(s => ({ v: s, label: zh[s] || s }))] },
      { key: "customer", label: "客户" },
      { key: "q", label: "搜索", placeholder: "订单号 / 标题 / 备注" },
      { key: "sort", label: "排序", type: "select", options: [
        { v: "-created_at", label: "最新创建" }, { v: "updated_at", label: "最近更新" },
        { v: "-amount_usd", label: "金额↓" }, { v: "-quantity", label: "数量↓" }] },
    ],
    toolbar: `<button class="btn sm" data-x="new">＋ 新建订单</button>
      <button class="btn ghost sm" data-x="reload">⟳ 刷新</button>`,
    fetcher: async p => {
      const d = await jget(`/v1/orders?${new URLSearchParams({ status: p.status || "", customer: p.customer || "", q: p.q || "", sort: p.sort || "-created_at", page: p.page, size: p.size })}`);
      renderKpi(view, d);
      return d;
    },
    columns: [
      { key: "id", label: "订单号", width: "150px", render: r => `<span class="mono">${esc(r.id)}</span>` },
      { key: "title", label: "标题", render: r => `<div>${esc(r.title)}</div><div class="muted-cell">${esc(r.customer_name || r.customer_id || "")}${r.context_id ? ` · ${esc(r.context_id)}` : ""}</div>` },
      { key: "status", label: "状态", width: "90px", render: r => statusChip(r.status, zh) },
      { key: "quantity", label: "数量", width: "80px", numeric: true, render: r => r.quantity ?? "—" },
      { key: "amount_usd", label: "金额", width: "110px", numeric: true, render: r => fmtMoney(r.amount_usd) },
      { key: "updated_at", label: "更新", width: "120px", numeric: true, render: r => fmtTs(r.updated_at || r.created_at) },
      { key: "acts", label: "操作", width: "150px", render: r => {
          const next = (META?.transitions?.[r.status] || []).slice(0, 2);
          return `<span class="no-row-click">${next.map(t => `<button class="btn ghost sm" data-adv="${esc(r.id)}" data-to="${esc(t)}">${esc(zh[t] || t)} →</button>`).join(" ") || `<span class="dim">终态</span>`}</span>`; } },
    ],
    bulkActions: [
      { label: "批量流转…", kind: "ghost", onClick: async (ids, rows, refresh) => {
          const to = prompt(`输入目标状态 (${(META?.statuses || []).join("/")}):\n注: 不满足状态机的行会整条失败并回显`);
          if (!to) return;
          const r = await jpost("/v1/orders/bulk", { ids, action: "transition", target_status: to });
          toast(`流转: 成功 ${(r.ok || []).length} · 失败 ${(r.failed || []).length}`); refresh(); } },
      { label: "🗑 删除", kind: "danger", onClick: async (ids, rows, refresh) => {
          if (!confirm(`确认删除 ${ids.length} 张订单?`)) return;
          const r = await jpost("/v1/orders/bulk", { ids, action: "delete" });
          toast(`删除: ${(r.ok || []).length} 张`); refresh(); } },
    ],
    empty: { title: "没有匹配的订单", hint: "放宽筛选, 或点「新建订单」; 存量已自动从飞轮种子灌入" },
    onRow: r => openOrderDetail(r, zh, () => tbl.refresh()),
  });

  view.querySelector('[data-x="new"]').onclick = () => openCreateModal(zh);
  view.querySelector('[data-x="reload"]').onclick = () => tbl.refresh();
  view.querySelector(".panel").addEventListener("click", async e => {
    const b = e.target.closest("[data-adv]");
    if (!b) return;
    e.stopPropagation();
    try { await jpatch(`/v1/orders/${b.dataset.adv}`, { to_status: b.dataset.to }); toast(`已流转到 ${zh[b.dataset.to] || b.dataset.to}`); } catch (err) { toast(`流转失败: ${err.message}`, "err"); }
    tbl.refresh();
  });
}

function renderKpi(view, d) {
  const el = view.querySelector("#ord-kpi");
  if (el) el.innerHTML = `<span class="chip">总订单 <b>${d.total}</b></span><span class="chip">当前页 ${d.items.length}</span>`;
}

function openCreateModal(zh) {
  const m = openModal("新建订单", `<div class="form">
    <label>标题 *<input id="f-title" placeholder="如: 304 法兰盘 200 件"></label>
    <div class="row"><div style="flex:1"><label>客户名<input id="f-cust"></label></div>
      <div style="flex:1"><label>数量<input id="f-qty" type="number" value="1"></label></div>
      <div style="flex:1"><label>金额 USD<input id="f-amt" type="number" value="0"></label></div></div>
    <div class="row"><div style="flex:1"><label>初始状态<select id="f-st">${(META?.statuses || ["inquiry"]).map(s => `<option value="${s}">${zh[s] || s}</option>`).join("")}</select></label></div>
      <div style="flex:1"><label>关联 context<input id="f-cid" placeholder="RFQ-… 可空"></label></div></div>
    <label>备注<textarea id="f-note" rows="2"></textarea></label>
    <button class="btn" id="f-save">创建</button></div>`);
  m.body.querySelector("#f-save").onclick = async () => {
    const g = id => m.body.querySelector(id).value.trim();
    try {
      const o = await jpost("/v1/orders", { title: g("#f-title") || "未命名订单", customer_name: g("#f-cust"), quantity: +g("#f-qty") || 1, amount_usd: +g("#f-amt") || 0, status: g("#f-st"), context_id: g("#f-cid") || null, note: g("#f-note"), source: "console" });
      toast(`已创建 ${o.id}`); m.close();
      document.querySelector('#nav a[data-tab="orders"]').click();
    } catch (e) { toast(`创建失败: ${e.message}`, "err"); }
  };
}

function openOrderDetail(o, zh, after) {
  const d = openDrawer(`${o.id} · ${o.title}`);
  const next = META?.transitions?.[o.status] || [];
  d.body.innerHTML = `
    <div class="sect"><h4>概要</h4><dl class="kv">
      <dt>状态</dt><dd>${statusChip(o.status, zh)} ${next.length ? `→ 可流转: ${next.map(t => `<button class="btn ghost sm" data-to="${esc(t)}">${esc(zh[t] || t)}</button>`).join(" ")}` : "<span class='dim'>终态</span>"}</dd>
      <dt>客户</dt><dd>${esc(o.customer_name || o.customer_id || "—")}</dd>
      <dt>数量 / 金额</dt><dd>${o.quantity} · ${fmtMoney(o.amount_usd)}</dd>
      <dt>context</dt><dd class="mono">${esc(o.context_id || "—")}</dd>
      <dt>来源</dt><dd>${esc(o.source || "—")}</dd>
      <dt>备注</dt><dd>${esc(o.note || "—")}</dd>
    </dl></div>
    <div class="sect"><h4>状态历史</h4><pre class="raw">${esc(JSON.stringify(o.history || o.state_history || [], null, 1).slice(0, 1500))}</pre></div>
    <div class="sect"><h4>编辑</h4><div class="form"><div class="row">
      <label style="margin:0">数量 <input id="e-qty" type="number" value="${o.quantity}" style="width:90px"></label>
      <label style="margin:0">金额 <input id="e-amt" type="number" value="${o.amount_usd}" style="width:120px"></label>
      <label style="margin:0;flex:1">备注 <input id="e-note" value="${esc(o.note || "")}"></label>
      <button class="btn sm" id="e-save">保存</button>
      <button class="btn danger sm" id="e-del">删单</button></div></div></div>`;
  d.body.querySelectorAll("[data-to]").forEach(b => b.onclick = async () => {
    try { await jpatch(`/v1/orders/${o.id}`, { to_status: b.dataset.to }); toast(`已流转 → ${zh[b.dataset.to]}`); d.close(); after(); }
    catch (e) { toast(`非法流转: ${e.message}`, "err"); }
  });
  d.body.querySelector("#e-save").onclick = async () => {
    const g = id => d.body.querySelector(id).value;
    await jpatch(`/v1/orders/${o.id}`, { quantity: +g("#e-qty"), amount_usd: +g("#e-amt"), note: g("#e-note") });
    toast("已保存"); d.close(); after();
  };
  d.body.querySelector("#e-del").onclick = async () => {
    if (!confirm(`删除订单 ${o.id}?`)) return;
    await jdel(`/v1/orders/${o.id}`); toast("已删除"); d.close(); after();
  };
}
