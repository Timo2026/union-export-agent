// ui.js — 通用组件: makeTable (筛选/分页/多选/批量/空状态) + drawer + modal + toast
import { esc } from "./api.js";

export function toast(msg, kind = "ok") {
  const root = document.getElementById("toast-root");
  const d = document.createElement("div");
  d.className = "toast" + (kind === "err" ? " err" : "");
  d.textContent = msg;
  root.appendChild(d);
  setTimeout(() => d.remove(), 4200);
}

export function confirmDlg(msg) { return window.confirm(msg); }

// ---------- drawer ----------
export function openDrawer(title, actionsHtml = "") {
  closeDrawer();
  const root = document.getElementById("drawer-root");
  root.innerHTML = `<div class="mask"></div>
    <div class="drawer"><div class="head"><h2>${esc(title)}</h2>
      <div class="row">${actionsHtml}</div>
      <button class="btn ghost sm" data-x="close">✕ 关闭</button></div>
      <div class="body"><div class="loading">加载中…</div></div></div>`;
  const close = () => { root.innerHTML = ""; };
  root.querySelector(".mask").onclick = close;
  root.querySelector('[data-x="close"]').onclick = close;
  return { close, body: root.querySelector(".drawer .body") };
}
export function closeDrawer() { document.getElementById("drawer-root").innerHTML = ""; }

// ---------- modal ----------
export function openModal(title, bodyHtml) {
  closeModal();
  const root = document.getElementById("modal-root");
  root.innerHTML = `<div class="mask"><div class="modal">
    <div class="head"><h2>${esc(title)}</h2><button class="btn ghost sm" data-x="close">✕ 关闭</button></div>
    <div class="body">${bodyHtml}</div></div></div>`;
  const close = () => { root.innerHTML = ""; };
  root.querySelector(".mask").onclick = e => { if (e.target === root.firstElementChild) close(); };
  root.querySelector('[data-x="close"]').onclick = close;
  return { close, body: root.querySelector(".modal .body") };
}
export function closeModal() { document.getElementById("modal-root").innerHTML = ""; }

// ---------- table factory ----------
export function makeTable(cfg) {
  const mount = cfg.mount;
  const st = {
    page: 1, size: cfg.pageSize || 20, params: {}, sel: new Set(),
    rows: [], total: 0, pages: 1, loading: false,
  };
  const key = cfg.rowKey || (r => r.id);

  mount.innerHTML = `
    ${cfg.filters ? `<div class="filters">${cfg.filters.map((f, i) => f.type === "select"
      ? `<label>${esc(f.label)} <select data-f="${i}">${(f.options || []).map(o => `<option value="${esc(o.v)}">${esc(o.label)}</option>`).join("")}</select></label>`
      : `<label>${esc(f.label)} <input data-f="${i}" type="text" placeholder="${esc(f.placeholder || "")}"></label>`).join("")}
      <span class="spacer"></span>${cfg.toolbar || ""}</div>` : (cfg.toolbar ? `<div class="filters"><span class="spacer"></span>${cfg.toolbar}</div>` : "")}
    <div class="bulkbar" hidden></div>
    <div class="tbl-wrap"><table class="tbl"><thead><tr>
      ${cfg.selectable ? '<th style="width:30px"><input type="checkbox" data-x="selall"></th>' : ""}
      ${cfg.columns.map(c => `<th ${c.width ? `style="width:${c.width}"` : ""}>${esc(c.label)}</th>`).join("")}
    </tr></thead><tbody></tbody></table></div>
    <div class="pager"></div>`;

  const tbody = mount.querySelector("tbody");
  const pager = mount.querySelector(".pager");
  const bulkbar = mount.querySelector(".bulkbar");

  function renderBulk() {
    if (!cfg.selectable || !st.sel.size || !cfg.bulkActions?.length) { bulkbar.hidden = true; return; }
    bulkbar.hidden = false;
    bulkbar.innerHTML = `<b>已选 ${st.sel.size} 项</b>
      <button class="btn ghost sm" data-x="clear">清空</button><span class="spacer"></span>
      ${cfg.bulkActions.map((a, i) => `<button class="btn sm ${a.kind === "danger" ? "danger" : a.kind === "ghost" ? "ghost" : ""}" data-b="${i}">${esc(a.label)}</button>`).join("")}`;
  }

  function renderRows() {
    st.rows = st.rows || [];
    if (!st.rows.length && !st.loading) {
      const e = cfg.empty || {};
      tbody.innerHTML = `<tr><td colspan="${cfg.columns.length + (cfg.selectable ? 1 : 0)}"><div class="empty"><div class="t">${esc(e.title || "暂无数据")}</div><div>${esc(e.hint || "调整筛选条件或稍后刷新")}</div></div></td></tr>`;
      pager.innerHTML = "";
      return;
    }
    tbody.innerHTML = st.rows.map((r, ri) => {
      const k = key(r);
      return `<tr data-k="${esc(String(k))}" class="${cfg.onRow ? "clickable" : ""} ${st.sel.has(k) ? "sel" : ""}">
        ${cfg.selectable ? `<td><input type="checkbox" data-x="selrow" ${st.sel.has(k) ? "checked" : ""}></td>` : ""}
        ${cfg.columns.map(c => `<td class="${c.numeric ? "num" : ""}">${c.render ? c.render(r, ri) : esc(r[c.key] ?? "—")}</td>`).join("")}
      </tr>`;
    }).join("");
    pager.innerHTML = `共 ${st.total} 条 · 第 ${st.page}/${st.pages} 页
      <button class="btn ghost sm" data-p="prev" ${st.page <= 1 ? "disabled" : ""}>← 上一页</button>
      <button class="btn ghost sm" data-p="next" ${st.page >= st.pages ? "disabled" : ""}>下一页 →</button>
      <select data-p="size">${[10, 20, 50, 100].map(n => `<option ${n === st.size ? "selected" : ""}>${n}</option>`).join("")}</select>`;
  }

  async function refresh() {
    st.loading = true; renderRows();
    try {
      const q = { ...cfg.staticParams, page: st.page, size: st.size, ...st.params };
      const data = await cfg.fetcher(q);
      st.rows = data.items || [];
      st.total = data.total ?? st.rows.length;
      st.pages = data.pages ?? Math.max(1, Math.ceil(st.total / st.size));
      st.page = data.page ?? st.page;
      if (cfg.onLoaded) cfg.onLoaded(data);
    } catch (e) {
      st.rows = []; st.total = 0; st.pages = 1;
      toast(`加载失败: ${e.message}`, "err");
    }
    st.loading = false;
    renderRows(); renderBulk();
  }

  mount.addEventListener("change", e => {
    const t = e.target;
    if (t.dataset.f !== undefined && cfg.filters) {
      const f = cfg.filters[+t.dataset.f];
      st.params[f.key] = t.value; st.page = 1; refresh();
    } else if (t.dataset.p === "size") { st.size = +t.value; st.page = 1; refresh(); }
    else if (t.dataset.p === "prev") { st.page--; refresh(); }
    else if (t.dataset.p === "next") { st.page++; refresh(); }
    else if (t.dataset.x === "selall") {
      st.sel = t.checked ? new Set(st.rows.map(key)) : new Set();
      renderRows(); renderBulk();
    } else if (t.dataset.x === "selrow") {
      const k = keyFromTr(t.closest("tr"));
      t.checked ? st.sel.add(k) : st.sel.delete(k);
      renderRows(); renderBulk();
    }
  });
  mount.addEventListener("input", e => {
    const t = e.target;
    if (t.dataset.f !== undefined && cfg.filters && t.tagName === "INPUT") {
      clearTimeout(t._deb);
      t._deb = setTimeout(() => { st.params[cfg.filters[+t.dataset.f].key] = t.value; st.page = 1; refresh(); }, 350);
    }
  });
  mount.addEventListener("click", async e => {
    const t = e.target;
    if (t.dataset.b !== undefined) {
      const rows = st.rows.filter(r => st.sel.has(key(r)));
      await cfg.bulkActions[+t.dataset.b].onClick([...st.sel], rows, refresh);
      st.sel.clear(); renderRows(); renderBulk();
      return;
    }
    if (t.dataset.x === "clear") { st.sel.clear(); renderRows(); renderBulk(); return; }
    if (t.dataset.x === "selrow") return;
    const tr = t.closest("tbody tr");
    if (tr && cfg.onRow && !t.closest(".no-row-click")) cfg.onRow(st.rows.find(r => String(key(r)) === tr.dataset.k));
  });

  function keyFromTr(tr) {
    const row = st.rows.find(r => String(key(r)) === tr.dataset.k);
    return row ? key(row) : tr.dataset.k;
  }

  refresh();
  return { refresh, state: st };
}
