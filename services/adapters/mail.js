// tabs/mail.js — 邮件台: 收件列表 + 筛选/分页/批量 + 9 区上下文详情抽屉 + 转订单
import { jget, jpost, esc, fmtTs, fmtBytes, mockBadge } from "../api.js";
import { makeTable, openDrawer, toast } from "../ui.js";

const REGIONS = ["customer", "geometry", "rag", "pending", "verification", "commercial", "postmortem", "trace", "hitl"];
const REGION_ZH = { customer: "客户画像", geometry: "图纸几何", rag: "RAG 证据", pending: "未办任务", verification: "门禁校验", commercial: "商务条款", postmortem: "历史复盘", trace: "执行链路", hitl: "人工介入" };

export function render(view) {
  view.innerHTML = `<div class="panel">
    <h3>邮件台 <span class="hint">· 本地 mailbox (data/mailbox), 批量删除/重试走 /v1/mail/batch</span></h3>
    <div id="mail-tbl"></div></div>`;

  const tbl = makeTable({
    mount: view.querySelector("#mail-tbl"),
    selectable: true,
    rowKey: r => r.mail_id,
    pageSize: 20,
    filters: [
      { key: "q", label: "搜索", placeholder: "主题 / 发件人 / ID" },
      { key: "state", label: "处理态", type: "select", options: [
        { v: "", label: "全部" }, { v: "NEW", label: "NEW" }, { v: "PROCESSING", label: "PROCESSING" },
        { v: "DONE", label: "DONE" }, { v: "FAILED", label: "FAILED" }, { v: "NONE", label: "未入队" }] },
    ],
    toolbar: `<button class="btn ghost sm" data-x="reload">⟳ 刷新</button>`,
    fetcher: async (params) => {
      const data = await jget("/v1/mail/inbox?limit=500");
      let items = data.items || [];
      if (params.q) {
        const q = String(params.q).toLowerCase();
        items = items.filter(m => (m.subject + " " + m.from + " " + m.mail_id).toLowerCase().includes(q));
      }
      if (params.state) items = items.filter(m => (m.pending?.state || "NONE") === params.state);
      const total = items.length, pages = Math.max(1, Math.ceil(total / params.size));
      const page = Math.min(params.page, pages);
      return { items: items.slice((page - 1) * params.size, page * params.size), total, pages, page };
    },
    columns: [
      { key: "subject", label: "主题", render: r => `<div>${esc(r.subject || "(无主题)")}</div>
          <div class="muted-cell mono">${esc(r.mail_id)}${r.attachments_count ? ` · 📎${r.attachments_count}` : ""}</div>` },
      { key: "from", label: "发件人", render: r => esc(r.from || "—") },
      { key: "badges", label: "标记", render: r => (r.badges || []).map(b => `<span class="badge">${esc(typeof b === "string" ? b : JSON.stringify(b))}</span>`).join("") || `<span class="dim">—</span>` },
      { key: "pending", label: "处理态", render: r => r.pending
          ? `<span class="badge state">${esc(r.pending.state || "?")}</span> <span class="muted-cell">${esc(r.pending.driver || "")}${r.pending.attempts ? ` ×${r.pending.attempts}` : ""}</span>`
          : `<span class="badge state">未入队</span>` },
      { key: "received_at", label: "时间", numeric: true, render: r => fmtTs(r.received_at) },
    ],
    bulkActions: [
      { label: "↻ 重试入队", onClick: async (ids, rows, refresh) => {
          const r = await jpost("/v1/mail/batch", { ids, action: "retry" });
          toast(`重试: 成功 ${r.done_count ?? r.done?.length ?? 0}${r.skipped?.length ? ` · 跳过 ${r.skipped.length}` : ""}`); refresh(); } },
      { label: "🗑 删除", kind: "danger", onClick: async (ids, rows, refresh) => {
          if (!confirm(`确认删除 ${ids.length} 封邮件 (本地 .eml + ledger)?`)) return;
          const r = await jpost("/v1/mail/batch", { ids, action: "delete" });
          toast(`删除: ${r.done_count ?? 0} 条`); refresh(); } },
    ],
    empty: { title: "收件箱为空", hint: "邮件链路拉取后自动出现; 或检查 data/mailbox 目录" },
    onRow: openMailDetail,
  });
  view.querySelector('[data-x="reload"]').onclick = () => tbl.refresh();
}

async function openMailDetail(row) {
  const d = openDrawer(row.subject || row.mail_id,
    `<button class="btn sm" data-x="to-order">📦 转订单</button>`);
  d.body.innerHTML = `<div class="loading">聚合 9 区上下文 + 原文…</div>`;
  const mid = encodeURIComponent(row.mail_id);
  const [mail, ...ctx] = await Promise.all([
    jget(`/v1/mail/${mid}`).catch(e => ({ error: e.message })),
    ...REGIONS.map(r => jget(`/v1/mail/${mid}/context/${r}`).catch(e => ({ error: e.message }))),
  ]);
  d.body.innerHTML = `
    <div class="sect"><h4>原文</h4>
      <div class="kv">
        <dt>发件人</dt><dd>${esc(mail.from || row.from)}</dd>
        <dt>主题</dt><dd>${esc(mail.subject || row.subject)}</dd>
        <dt>大小</dt><dd>${fmtBytes(row.size_bytes)}</dd>
        <dt>正文</dt><dd><pre class="raw">${esc((mail.body || "").slice(0, 3000) || mail.error || "—")}</pre></dd>
      </div></div>` +
    REGIONS.map((r, i) => {
      const data = ctx[i];
      if (data?.error) return `<div class="sect"><h4>${REGION_ZH[r]}</h4><div class="dim">${esc(data.error)}</div></div>`;
      return `<div class="sect"><h4>${REGION_ZH[r]} ${mockBadge(data)}</h4><pre class="raw">${esc(JSON.stringify(data, null, 1).slice(0, 1800))}</pre></div>`;
    }).join("");

  // 按钮在抽屉 head (openDrawer actionsHtml), 不在 body — 挂错根会 TypeError 死键 (节点实测 2026-09-22)
  (d.body.closest(".drawer") || document.getElementById("drawer-root"))
    .querySelector('[data-x="to-order"]').onclick = async () => {
    const cust = ctx[0]?.customer_id || (row.from || "").split("<")[0].trim();
    const cid = ctx[2]?.context_id || null;
    try {
      const o = await jpost("/v1/orders", { customer_name: cust, title: row.subject || `邮件 ${row.mail_id}`, status: "inquiry", context_id: cid, source: "mail", note: `mail_id=${row.mail_id}` });
      toast(`已建订单 ${o.id}`);
    } catch (e) { toast(`建单失败: ${e.message}`, "err"); }
  };
}
