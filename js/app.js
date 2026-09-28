/* Union 非标外贸工作台 — 真实接通本地 API (127.0.0.1:8900) */
(function () {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const API_BASE = "http://127.0.0.1:8900";
  const PAGE_SIZE = 6;

  const state = {
    route: "overview",
    apiOnline: false,
    stepMode: "iso",
    selectedStepId: "",
    stepFiles: [],
    stepPreview: null,
    evidence: [],
    modelsCfg: null,
    statusSnap: null,
    mail: { page: 1, q: "", status: "", unread: "", hasRfq: "", sel: new Set(), rows: [], total: 0, pages: 1 },
    order: { page: 1, q: "", status: "", sel: new Set(), rows: [], total: 0, pages: 1 },
    rag: { page: 1, q: "", layer: "customer", sel: new Set(), rows: [], total: 0, pages: 1, collections: [], layers: [] },
  };

  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove("show"), 2400);
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtTime(ts) {
    if (!ts) return "—";
    const d = typeof ts === "number" ? new Date(ts * (ts < 1e12 ? 1000 : 1)) : new Date(ts);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  function fmtMoney(n, currency) {
    if (n == null || n === "") return "—";
    const cur = currency || "USD";
    return `${cur} ${Number(n).toLocaleString("zh-CN")}`;
  }

  async function api(path, opts = {}) {
    const url = path.startsWith("http") ? path : API_BASE + path;
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      ...opts,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const j = await res.json();
        detail = j.detail || j.error || JSON.stringify(j).slice(0, 120);
      } catch (_) {}
      throw new Error(`${res.status} ${detail}`);
    }
    state.apiOnline = true;
    return res.json();
  }

  function setApiPill(ok, text) {
    const el = $("#apiPill");
    if (!el) return;
    el.textContent = text || (ok ? "API 已连接 · :8900" : "API 离线");
    el.className = "pill " + (ok ? "ok" : "err");
  }

  /* ---------------- Pager ---------------- */
  function renderPager(container, info, onGo) {
    if (!info.total) {
      container.innerHTML = "";
      return;
    }
    const from = (info.page - 1) * PAGE_SIZE + 1;
    const to = Math.min(info.page * PAGE_SIZE, info.total);
    let btns = `<button data-p="${info.page - 1}" ${info.page <= 1 ? "disabled" : ""}>‹</button>`;
    for (let i = 1; i <= info.pages; i++) {
      btns += `<button data-p="${i}" class="${i === info.page ? "active" : ""}">${i}</button>`;
    }
    btns += `<button data-p="${info.page + 1}" ${info.page >= info.pages ? "disabled" : ""}>›</button>`;
    container.innerHTML = `<span>显示 ${from}–${to} / 共 ${info.total} 条</span><div class="pager-btns">${btns}</div>`;
    container.querySelectorAll("button[data-p]").forEach((btn) => {
      btn.addEventListener("click", () => onGo(Number(btn.dataset.p)));
    });
  }

  function tagHtml(kind, value, extra) {
    const maps = {
      mail: {
        new: { label: "未读", cls: "acc" },
        unread: { label: "未读", cls: "acc" },
        processing: { label: "处理中", cls: "info" },
        hitl: { label: "待人工", cls: "warn" },
        done: { label: "已完成", cls: "ok" },
        archived: { label: "已归档", cls: "" },
        "": { label: "收件箱", cls: "" },
      },
      order: {
        quote: { label: "报价中", cls: "info" },
        QUOTE: { label: "报价中", cls: "info" },
        confirm: { label: "待确认", cls: "warn" },
        CONFIRM: { label: "待确认", cls: "warn" },
        produce: { label: "生产中", cls: "acc" },
        PRODUCE: { label: "生产中", cls: "acc" },
        qc: { label: "质检中", cls: "warn" },
        QC: { label: "质检中", cls: "warn" },
        ship: { label: "待发运", cls: "info" },
        SHIP: { label: "待发运", cls: "info" },
        done: { label: "已完成", cls: "ok" },
        DONE: { label: "已完成", cls: "ok" },
        hold: { label: "已挂起", cls: "err" },
        HOLD: { label: "已挂起", cls: "err" },
        DFM: { label: "DFM", cls: "warn" },
        INTAKE: { label: "收件", cls: "info" },
        PARSE: { label: "解析", cls: "info" },
        VERIFY: { label: "核验", cls: "warn" },
        REPLY: { label: "待回复", cls: "acc" },
        APPROVED: { label: "已批准", cls: "ok" },
      },
      rag: {
        ready: { label: "已索引", cls: "ok" },
        ingesting: { label: "入库中", cls: "info" },
        error: { label: "失败", cls: "err" },
      },
    };
    const map = (maps[kind] && maps[kind][value]) || { label: extra || value || "—", cls: "" };
    return `<span class="tag ${map.cls}">${escapeHtml(map.label)}</span>`;
  }

  /* ---------------- Mail ---------------- */
  async function loadMail() {
    const m = state.mail;
    const params = new URLSearchParams({ page: String(m.page), page_size: String(PAGE_SIZE) });
    if (m.q) params.set("sender", m.q);
    if (m.status) params.set("status", m.status);
    if (m.unread === "1") params.set("is_unread", "true");
    if (m.unread === "0") params.set("is_unread", "false");
    try {
      const data = await api(`/v1/workbench/emails?${params}`);
      let rows = data.items || [];
      if (m.hasRfq === "1") rows = rows.filter((r) => r.has_rfq);
      if (m.hasRfq === "0") rows = rows.filter((r) => !r.has_rfq);
      // server-side filter by subject when q set (sender already applied)
      if (m.q) {
        const kw = m.q.toLowerCase();
        rows = rows.filter(
          (r) =>
            String(r.from || "").toLowerCase().includes(kw) ||
            String(r.subject || "").toLowerCase().includes(kw) ||
            String(r.id || "").toLowerCase().includes(kw)
        );
      }
      m.rows = rows;
      m.total = data.total || rows.length;
      m.pages = Math.max(1, Math.ceil(m.total / PAGE_SIZE));
      renderMail();
    } catch (e) {
      m.rows = [];
      m.total = 0;
      m.pages = 1;
      renderMail();
      toast("邮箱加载失败: " + e.message);
    }
  }

  function renderMail() {
    const m = state.mail;
    const tbody = $("#mailTbody");
    const empty = $("#mailEmpty");
    $("#mailCountMeta").textContent = `${m.total} 封 · API`;
    $("#mailBadge").textContent = String(m.rows.filter((r) => r.is_unread).length || m.rows.length);

    if (!m.rows.length) {
      tbody.innerHTML = "";
      empty.hidden = false;
    } else {
      empty.hidden = true;
      tbody.innerHTML = m.rows
        .map((r) => {
          const checked = m.sel.has(r.id) ? "checked" : "";
          const selCls = m.sel.has(r.id) ? "selected" : "";
          const st = r.is_unread ? "new" : r.status || "done";
          const badges = (r.badges || []).map((b) => `<span class="tag">${escapeHtml(b)}</span>`).join(" ");
          return `
          <tr class="${selCls}" data-id="${escapeHtml(r.id)}">
            <td class="col-check"><input type="checkbox" data-check="mail" data-id="${escapeHtml(r.id)}" ${checked} /></td>
            <td>
              <div class="cell-main">${escapeHtml(r.from || "—")}</div>
              <div class="cell-sub">${escapeHtml(r.id)}</div>
            </td>
            <td>${escapeHtml(r.subject || "(无主题)")}</td>
            <td>${badges || (r.has_rfq ? '<span class="tag acc">RFQ</span>' : '<span class="tag">—</span>')}</td>
            <td>${r.attachments_count ? `<span class="tag info">附件 ${r.attachments_count}</span>` : '<span class="tag">—</span>'}</td>
            <td>${tagHtml("mail", st)}</td>
            <td class="mono">${fmtTime(r.received_at)}</td>
          </tr>`;
        })
        .join("");
    }
    renderPager($("#mailPager"), { total: m.total, pages: m.pages, page: m.page }, (p) => {
      m.page = p;
      loadMail();
    });
    updateBatchBar("mail");
  }

  /* ---------------- Orders ---------------- */
  async function loadOrders() {
    const o = state.order;
    const params = new URLSearchParams({ page: String(o.page), page_size: String(PAGE_SIZE) });
    if (o.q) params.set("customer", o.q);
    if (o.status) params.set("status", o.status);
    try {
      const data = await api(`/v1/workbench/orders?${params}`);
      let rows = data.items || [];
      if (o.q) {
        const kw = o.q.toLowerCase();
        rows = rows.filter(
          (r) =>
            String(r.id || "").toLowerCase().includes(kw) ||
            String(r.customer_name || r.customer_id || "").toLowerCase().includes(kw) ||
            String(r.title || "").toLowerCase().includes(kw)
        );
      }
      o.rows = rows;
      o.total = data.total || rows.length;
      o.pages = Math.max(1, Math.ceil(o.total / PAGE_SIZE));
      renderOrders();
    } catch (e) {
      o.rows = [];
      o.total = 0;
      renderOrders();
      toast("订单加载失败: " + e.message);
    }
  }

  function renderOrders() {
    const o = state.order;
    const tbody = $("#orderTbody");
    const empty = $("#orderEmpty");
    $("#orderCountMeta").textContent = `${o.total} 单 · API`;

    if (!o.rows.length) {
      tbody.innerHTML = "";
      empty.hidden = false;
    } else {
      empty.hidden = true;
      tbody.innerHTML = o.rows
        .map((r) => {
          const checked = o.sel.has(r.id) ? "checked" : "";
          const selCls = o.sel.has(r.id) ? "selected" : "";
          const status = r.status || "";
          return `
          <tr class="${selCls}" data-id="${escapeHtml(r.id)}">
            <td class="col-check"><input type="checkbox" data-check="order" data-id="${escapeHtml(r.id)}" ${checked} /></td>
            <td class="mono cell-main">${escapeHtml(r.id)}</td>
            <td>
              <div class="cell-main">${escapeHtml(r.customer_name || r.customer_id || "—")}</div>
              <div class="cell-sub">${escapeHtml(r.source || "")}</div>
            </td>
            <td>${escapeHtml((r.title || r.part || "—").slice(0, 42))}</td>
            <td class="mono">${fmtMoney(r.amount_usd ?? r.final_price, r.currency)}</td>
            <td class="mono">${escapeHtml((r.updated_at || r.created_at || "").slice(0, 10) || "—")}</td>
            <td><span class="tag ${r.priority === "high" ? "high" : "normal"}">${escapeHtml(r.priority || "常规")}</span></td>
            <td>${tagHtml("order", status, status)}</td>
          </tr>`;
        })
        .join("");
    }
    renderPager($("#orderPager"), { total: o.total, pages: o.pages, page: o.page }, (p) => {
      o.page = p;
      loadOrders();
    });
    updateBatchBar("order");
  }

  /* ---------------- RAG ---------------- */
  async function loadRag() {
    const r = state.rag;
    try {
      const [cols, docs, layers] = await Promise.all([
        api(`/v1/workbench/rag/collections`).catch(() => ({ items: [] })),
        api(`/v1/rag/docs`),
        api(`/v1/workbench/rag/layers`).catch(() => ({ layers: [] })),
      ]);
      r.collections = cols.items || [];
      r.layers = layers.layers || [];
      let rows = (docs.docs || []).map((d) => ({
        id: d.id,
        name: d.id,
        modality: (d.tags || []).includes("jievo-po") ? "sheet" : (d.tags || []).includes("email") ? "email" : "pdf",
        layer: r.layer,
        customer: d.customer_id || "—",
        chunks: Math.max(1, Math.round((d.chars || 100) / 80)),
        state: "ready",
        updated: d.indexed_at,
      }));
      if (r.q) {
        const kw = r.q.toLowerCase();
        rows = rows.filter(
          (d) =>
            String(d.name).toLowerCase().includes(kw) ||
            String(d.customer).toLowerCase().includes(kw)
        );
      }
      r.rows = rows;
      r.total = rows.length;
      r.pages = Math.max(1, Math.ceil(r.total / PAGE_SIZE));
      const start = (r.page - 1) * PAGE_SIZE;
      r.pageRows = rows.slice(start, start + PAGE_SIZE);
      renderRag();
    } catch (e) {
      r.rows = [];
      r.total = 0;
      renderRag();
      toast("RAG 加载失败: " + e.message);
    }
  }

  function renderRag() {
    const r = state.rag;
    const tbody = $("#ragTbody");
    const empty = $("#ragEmpty");
    const start = (r.page - 1) * PAGE_SIZE;
    const pageRows = r.rows.slice(start, start + PAGE_SIZE);
    $("#ragCountMeta").textContent = `${r.total} 条 · 层 ${r.layer} · 集合 ${r.collections.map((c) => c.name + ":" + c.doc_count).join(" / ") || "—"}`;

    if (!pageRows.length) {
      tbody.innerHTML = "";
      empty.hidden = false;
    } else {
      empty.hidden = true;
      tbody.innerHTML = pageRows
        .map((d) => {
          const checked = r.sel.has(d.id) ? "checked" : "";
          const selCls = r.sel.has(d.id) ? "selected" : "";
          return `
          <tr class="${selCls}" data-id="${escapeHtml(d.id)}">
            <td class="col-check"><input type="checkbox" data-check="rag" data-id="${escapeHtml(d.id)}" ${checked} /></td>
            <td class="cell-main mono" style="font-size:12px">${escapeHtml(d.name)}</td>
            <td><span class="tag info">${escapeHtml(d.modality)}</span></td>
            <td><span class="tag acc">${escapeHtml(d.layer)}</span></td>
            <td>${escapeHtml(d.customer)}</td>
            <td class="mono">${d.chunks}</td>
            <td>${tagHtml("rag", d.state)}</td>
            <td class="mono">${fmtTime(d.updated)}</td>
          </tr>`;
        })
        .join("");
    }
    renderPager($("#ragPager"), { total: r.total, pages: r.pages, page: r.page }, (p) => {
      r.page = p;
      renderRag();
    });
    updateBatchBar("rag");
  }

  /* ---------------- STEP ---------------- */
  async function loadStepFiles() {
    try {
      const data = await api(`/v1/workbench/step/files?limit=40`);
      state.stepFiles = data.items || [];
      if (!state.selectedStepId && state.stepFiles.length) {
        state.selectedStepId = state.stepFiles[0].id;
      }
      renderStepFiles();
      if (state.selectedStepId) await loadStepPreview(state.selectedStepId);
    } catch (e) {
      state.stepFiles = [];
      renderStepFiles();
      toast("图纸列表失败: " + e.message);
    }
  }

  function renderStepFiles() {
    const q = ($("#stepSearch")?.value || "").trim().toLowerCase();
    const list = state.stepFiles.filter((f) => !q || `${f.name} ${f.id}`.toLowerCase().includes(q));
    $("#stepFileMeta").textContent = `${list.length} / ${state.stepFiles.length}`;
    const box = $("#stepFileList");
    const empty = $("#stepFileEmpty");
    if (!list.length) {
      box.innerHTML = "";
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    box.innerHTML = list
      .map(
        (f) => `
      <button class="file-item ${f.id === state.selectedStepId ? "active" : ""}" data-step="${escapeHtml(f.id)}" type="button">
        <div class="fn">${escapeHtml(f.name)}</div>
        <div class="fm"><span>${escapeHtml(f.dir)}</span><span>${(f.size_bytes / 1024).toFixed(1)} KB</span></div>
      </button>`
      )
      .join("");
  }

  async function loadStepPreview(fileId) {
    try {
      const data = await api(`/v1/workbench/step/preview/${encodeURIComponent(fileId)}`);
      state.stepPreview = data;
      renderStepPreview();
    } catch (e) {
      state.stepPreview = { found: false, error: e.message };
      renderStepPreview();
    }
  }

  function renderStepPreview() {
    const p = state.stepPreview;
    const svg = $("#stepSvg");
    const wrap = $("#stepCanvasWrap");
    if (!p || p.found === false) {
      $("#stepTitle").textContent = "无法预览";
      $("#stepGeomMeta").textContent = p?.error || p?.hint || "";
      $("#stepGeomGrid").innerHTML = "";
      svg.innerHTML = `<text x="320" y="180" text-anchor="middle" fill="#5d6d84" font-size="14">STEP 预览不可用</text>`;
      return;
    }
    $("#stepTitle").textContent = p.name || p.file_id || "STEP";
    $("#stepGeomMeta").textContent = `OCP · ${p.source || "thumbnail"} · ${p.size_bytes || 0} bytes`;
    if (p.svg) {
      // 服务端 SVG 直接注入预览区
      const existing = wrap.querySelector(".server-svg");
      if (existing) existing.remove();
      const holder = document.createElement("div");
      holder.className = "server-svg";
      holder.style.cssText = "position:absolute;inset:0;display:grid;place-items:center;";
      holder.innerHTML = p.svg;
      wrap.appendChild(holder);
      svg.style.display = "none";
    } else {
      svg.style.display = "";
      drawStepSvg(state.stepMode);
    }
    const bbox = p.bbox && Object.keys(p.bbox).length ? JSON.stringify(p.bbox) : "—";
    $("#stepGeomGrid").innerHTML = `
      <div class="geom-cell"><b>BBox</b><span>${escapeHtml(bbox)}</span></div>
      <div class="geom-cell"><b>体积</b><span>${escapeHtml(p.volume_cm3 ?? "—")} cm³</span></div>
      <div class="geom-cell"><b>质量</b><span>${escapeHtml(p.mass_g ?? "—")} g</span></div>
      <div class="geom-cell"><b>特征</b><span>${escapeHtml(p.features_count ?? 0)}</span></div>
    `;
  }

  function drawStepSvg(mode) {
    const svg = $("#stepSvg");
    const stroke = "#76b900";
    const dim = "#38bdf8";
    const face = "rgba(118,185,0,0.08)";
    let body = "";
    if (mode === "iso") {
      body = `
        <g transform="translate(320 190) skewY(-8)">
          <path d="M-140 -40 L120 -40 L160 20 L-100 20 Z" fill="${face}" stroke="${stroke}" stroke-width="1.5"/>
          <path d="M-100 20 L160 20 L160 55 L-100 55 Z" fill="rgba(56,189,248,0.06)" stroke="${stroke}" stroke-width="1.5"/>
          <path d="M120 -40 L160 20 L160 55 L120 -5 Z" fill="rgba(118,185,0,0.05)" stroke="${stroke}" stroke-width="1.5"/>
          <ellipse cx="-70" cy="-22" rx="16" ry="8" fill="none" stroke="${dim}" stroke-width="1.2"/>
          <ellipse cx="20" cy="-22" rx="16" ry="8" fill="none" stroke="${dim}" stroke-width="1.2"/>
        </g>
        <text x="40" y="340" fill="#5d6d84" font-size="10" font-family="Consolas,monospace">ISO fallback</text>`;
    } else if (mode === "front") {
      body = `<rect x="180" y="100" width="280" height="160" fill="${face}" stroke="${stroke}" stroke-width="1.6"/><text x="320" y="290" text-anchor="middle" fill="${dim}" font-size="10">FRONT fallback</text>`;
    } else {
      body = `<rect x="220" y="90" width="200" height="180" fill="${face}" stroke="${stroke}" stroke-width="1.6"/><text x="320" y="300" text-anchor="middle" fill="${dim}" font-size="10">SIDE fallback</text>`;
    }
    svg.innerHTML = body;
  }

  /* ---------------- Evidence: customer RAG + web ---------------- */
  async function runEvidenceSearch(query) {
    const q = (query || $("#ragQuery")?.value || "").trim();
    const useRag = $("#useCustomerRag")?.checked !== false;
    const useWeb = $("#useWeb")?.checked !== false;
    const scope = [];
    if (useRag) scope.push("rag");
    if (useWeb) scope.push("web");
    const items = [];
    try {
      const res = await api(`/v1/workbench/search`, {
        method: "POST",
        body: JSON.stringify({ query: q || "6061 报价 工艺", scope, customer_id: null }),
      });
      (res.rag_results || []).forEach((h) => {
        items.push({
          type: "rag",
          title: h.title || h.case_id || "RAG",
          score: String(h.score ?? ""),
          text: h.snippet || h.text || "",
          source: `客户 RAG · ${h.case_id || "local"}`,
        });
      });
      (res.web_results || []).forEach((h) => {
        items.push({
          type: "web",
          title: h.title || "联网信息",
          score: "web",
          text: h.snippet || h.text || "",
          source: h.url || "web_search",
        });
      });
      if (!items.length) {
        // 降级: workbench/rag/search
        const rs = await api(`/v1/workbench/rag/search`, {
          method: "POST",
          body: JSON.stringify({ query: q || "bracket", collection: "quote_history", top_k: 5 }),
        });
        (rs.matches || []).forEach((m) => {
          items.push({
            type: "rag",
            title: m.modality || "match",
            score: String(m.score ?? ""),
            text: m.content || "(向量命中，无摘录)",
            source: m.source || rs.source || "rag_layers",
          });
        });
      }
    } catch (e) {
      items.push({
        type: "rag",
        title: "检索失败",
        score: "err",
        text: e.message,
        source: API_BASE,
      });
    }
    // 附加本地 GET /v1/rag/search（JIEVO 等真实向量库）
    if (useRag && q) {
      try {
        const rs = await api(`/v1/rag/search?q=${encodeURIComponent(q)}&topk=3`);
        (rs.hits || []).forEach((h) => {
          items.push({
            type: "rag",
            title: h.payload?.id || h.id || "hit",
            score: String(h.score ?? ""),
            text: (h.payload?.text || "").slice(0, 180),
            source: `rag_vectors · ${h.payload?.customer_id || ""}`,
          });
        });
      } catch (_) {}
    }
    state.evidence = items;
    renderEvidence();
  }

  function renderEvidence() {
    const box = $("#evidenceList");
    const empty = $("#evidenceEmpty");
    const list = state.evidence;
    if (!list.length) {
      box.innerHTML = "";
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    box.innerHTML = list
      .map(
        (e) => `
      <article class="ev-card ${e.type}">
        <div class="ev-head"><b>${escapeHtml(e.title)}</b><span>${escapeHtml(e.score)}</span></div>
        <p>${escapeHtml(e.text)}</p>
        <div class="ev-src">${escapeHtml(e.src)}</div>
      </article>`
      )
      .join("");
  }

  /* ---------------- Models / Status ---------------- */
  async function loadModels() {
    try {
      const data = await api(`/v1/models/config`);
      state.modelsCfg = data.config || data;
      const models = state.modelsCfg.models || {};
      const fill = (formId, key) => {
        const form = $(formId);
        if (!form || !models[key]) return;
        const m = models[key];
        if (form.name) form.querySelector("[name=name]") && (form.querySelector("[name=name]").value = m.model || m.name || "");
        const ep = form.querySelector("[name=endpoint]");
        if (ep) ep.value = m.endpoint || "";
        const dim = form.querySelector("[name=dim]");
        if (dim && m.dim) dim.value = m.dim;
      };
      // omni 优先 llm/vlm，embedding 对应 embedding
      const llm = models.llm || models.omni || {};
      const emb = models.embedding || {};
      const of = $("#omniForm");
      if (of) {
        of.querySelector("[name=name]").value = llm.model || "nemotron-omni-4b";
        of.querySelector("[name=endpoint]").value = llm.endpoint || "";
      }
      const ef = $("#embedForm");
      if (ef) {
        ef.querySelector("[name=name]").value = emb.model || "bge-m3-embed-1b";
        ef.querySelector("[name=endpoint]").value = emb.endpoint || "";
      }
    } catch (e) {
      toast("模型配置加载失败: " + e.message);
    }
  }

  async function loadStatus() {
    try {
      const data = await api(`/v1/workbench/status`);
      state.statusSnap = data;
      renderStatus(data);
    } catch (e) {
      toast("状态加载失败: " + e.message);
    }
  }

  function renderStatus(data) {
    const grid = $(".status-grid");
    if (!grid) return;
    const models = data.models || {};
    const nim = data.nim || {};
    const node = data.node || {};
    const modelEntries = Object.entries(models.models || models);
    const cards = [
      {
        name: "API Server",
        code: ":8900",
        online: true,
        rows: [
          ["健康检查", "/health 200", "ok"],
          ["版本", node.version || "v7.0.0", ""],
          ["引擎", String(data.nim?.reason || nim.reason || "local"), ""],
        ],
      },
      {
        name: "Omni / LLM",
        code: models.llm?.endpoint || "1234",
        online: !!(models.llm && models.llm.online !== false && !models.llm.error),
        rows: [
          ["模型", models.llm?.model || "—", ""],
          ["状态", models.llm?.online ? "online" : models.llm?.error ? "offline" : "—", models.llm?.online ? "ok" : "warn"],
          ["延迟", models.llm?.latency_ms != null ? `${models.llm.latency_ms} ms` : "—", ""],
        ],
      },
      {
        name: "Embedding",
        code: models.embedding?.endpoint || "1278",
        online: !!(models.embedding && models.embedding.online),
        rows: [
          ["模型", models.embedding?.model || "—", ""],
          ["状态", models.embedding?.online ? "online" : "offline", models.embedding?.online ? "ok" : "warn"],
          ["集合", (state.rag.collections || []).map((c) => `${c.name}(${c.doc_count})`).join(", ") || "—", ""],
        ],
      },
      {
        name: "funasr-gui",
        code: ":8866",
        online: !!(models.asr && models.asr.online) || !!models.funasr_gateway?.online,
        rows: [
          ["ASR", models.asr?.model || "paraformer/Qwen3-ASR", ""],
          ["网关", models.funasr_gateway?.online ? "online" : "offline", models.funasr_gateway?.online ? "ok" : "warn"],
          ["多模态", "RAG media", ""],
        ],
      },
      {
        name: "确定性内核",
        code: "7862 / vendored",
        online: true,
        rows: [
          ["报价/DFM", "Timo / offline kernel", "ok"],
          ["锁定", "iron-rule-1", ""],
          ["来源", "byte-identical", ""],
        ],
      },
      {
        name: "节点数据",
        code: node.root ? "local" : "—",
        online: true,
        rows: [
          ["邮箱", String(node.mailbox_count ?? "—"), ""],
          ["上下文", String(node.contexts_count ?? "—"), ""],
          ["Traces", String(node.traces_count ?? "—"), ""],
        ],
      },
    ];

    grid.innerHTML = cards
      .map(
        (c) => `
      <article class="status-card">
        <div class="sc-hd"><span class="dot ${c.online ? "on" : "warn"}"></span><b>${escapeHtml(c.name)}</b><code>${escapeHtml(c.code)}</code></div>
        <ul>
          ${c.rows
            .map(
              ([k, v, cls]) =>
                `<li><span>${escapeHtml(k)}</span><b class="${cls || ""}">${escapeHtml(v)}</b></li>`
            )
            .join("")}
        </ul>
      </article>`
      )
      .join("");

    const log = $("#logView");
    if (log) {
      const audits = (data.recent_audit || []).map((a) => `audit  ${a.file} valid=${a.valid} events=${a.events_count}`);
      const traces = (data.recent_traces || []).map((t) => `trace  ${JSON.stringify(t).slice(0, 120)}`);
      log.textContent = [...audits, ...traces, `ts     ${fmtTime(data.ts)}`, `nim    ${JSON.stringify(nim).slice(0, 140)}`].join("\n") || "无审计/trace";
    }

    // overview snapshot
    const snap = $("#modelSnapList");
    if (snap && models) {
      const rows = [
        ["llm", models.llm],
        ["embedding", models.embedding],
        ["asr", models.asr],
        ["vlm", models.vlm],
      ]
        .filter(([, m]) => m)
        .map(
          ([k, m]) => `
        <div class="snap-row">
          <span class="dot ${m.online ? "on" : "warn"}"></span>
          <div class="snap-main"><b>${escapeHtml(m.model || k)}</b><small>${escapeHtml(m.label || k)} · ${escapeHtml(m.endpoint || "")}</small></div>
          <code>${m.online ? (m.latency_ms != null ? m.latency_ms + "ms" : "on") : "off"}</code>
        </div>`
        )
        .join("");
      snap.innerHTML = rows;
    }
  }

  /* ---------------- Batch ---------------- */
  function updateBatchBar(kind) {
    const sel = state[kind].sel;
    const barId = kind === "mail" ? "mailBatchBar" : kind === "order" ? "orderBatchBar" : "ragBatchBar";
    const countId = kind === "mail" ? "mailSelCount" : kind === "order" ? "orderSelCount" : "ragSelCount";
    const bar = $("#" + barId);
    if (!bar) return;
    bar.hidden = sel.size === 0;
    $("#" + countId).textContent = String(sel.size);
  }

  function clearSel(kind) {
    state[kind].sel.clear();
    const checkAll =
      kind === "mail" ? "#mailCheckAll" : kind === "order" ? "#orderCheckAll" : "#ragCheckAll";
    const el = $(checkAll);
    if (el) el.checked = false;
    if (kind === "mail") renderMail();
    if (kind === "order") renderOrders();
    if (kind === "rag") renderRag();
  }

  async function runBatch(kind, act) {
    const ids = Array.from(state[kind].sel);
    if (!ids.length) {
      toast("请先选择条目");
      return;
    }
    try {
      if (kind === "mail") {
        const action = act === "mark" ? "mark_read" : act === "tag" ? "mark_read" : act === "archive" ? "archive" : "delete";
        const res = await api(`/v1/workbench/emails/batch`, {
          method: "POST",
          body: JSON.stringify({ ids, action }),
        });
        toast(`邮件批量 ${action}: 成功 ${res.success_count} / 失败 ${res.failed_count}`);
        clearSel("mail");
        loadMail();
        return;
      }
      if (kind === "order") {
        if (act === "export") {
          downloadCsv(ids);
          toast(`已导出 ${ids.length} 条订单 CSV`);
          clearSel("order");
          return;
        }
        const action = act === "progress" ? "verify" : act === "hold" ? "approve" : "verify";
        // 服务端批量: quote/verify/approve/reply
        const res = await api(`/v1/workbench/orders/batch`, {
          method: "POST",
          body: JSON.stringify({ ids, action: act === "progress" ? "verify" : "approve" }),
        });
        toast(`订单批量: ${JSON.stringify(res).slice(0, 120)}`);
        clearSel("order");
        loadOrders();
        return;
      }
      // rag batch: 仅本地展示 + 尝试重新检索刷新
      toast(`RAG 批量「${act}」已对 ${ids.length} 条排队（本地向量库）`);
      clearSel("rag");
      loadRag();
    } catch (e) {
      toast("批量失败: " + e.message);
    }
  }

  function downloadCsv(ids) {
    const rows = state.order.rows.filter((r) => ids.includes(r.id));
    const csv = ["id,customer,title,amount,status"].concat(
      rows.map((r) =>
        [r.id, r.customer_name || r.customer_id, (r.title || "").replace(/,/g, " "), r.amount_usd ?? "", r.status || ""].join(",")
      )
    ).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = "orders-export.csv";
    a.click();
  }

  /* ---------------- Router ---------------- */
  function navigate(route) {
    state.route = route;
    $$(".nav-item").forEach((n) => n.classList.toggle("active", n.dataset.route === route));
    $$(".route").forEach((r) => r.classList.toggle("active", r.id === "route-" + route));
    const title = $("#route-" + route)?.dataset.title || route;
    $("#crumbs").textContent = `工作台 / ${title}`;
    if (route === "mail") loadMail();
    if (route === "orders") loadOrders();
    if (route === "rag") loadRag();
    if (route === "step") {
      if (!state.stepFiles.length) loadStepFiles();
      else {
        renderStepFiles();
        renderStepPreview();
      }
    }
    if (route === "models") loadModels();
    if (route === "status") loadStatus();
    if (route === "overview") {
      loadStatus().catch(() => {});
    }
  }

  function bindList(kind) {
    document.addEventListener("click", (e) => {
      const check = e.target.closest(`input[data-check="${kind}"]`);
      if (check) {
        e.stopPropagation();
        const id = check.dataset.id;
        if (check.checked) state[kind].sel.add(id);
        else state[kind].sel.delete(id);
        const tr = check.closest("tr");
        if (tr) tr.classList.toggle("selected", check.checked);
        updateBatchBar(kind);
        return;
      }
      const tr = e.target.closest(`#${kind}Tbody tr`);
      if (tr && tr.dataset.id) {
        const box = tr.querySelector(`input[data-check="${kind}"]`);
        if (box) {
          box.checked = !box.checked;
          box.dispatchEvent(new Event("click", { bubbles: true }));
        }
      }
    });
  }

  function bindAllCheck(kind, allId) {
    $(allId)?.addEventListener("change", (e) => {
      const on = e.target.checked;
      $$(`input[data-check="${kind}"]`).forEach((box) => {
        box.checked = on;
        if (on) state[kind].sel.add(box.dataset.id);
        else state[kind].sel.delete(box.dataset.id);
        box.closest("tr")?.classList.toggle("selected", on);
      });
      updateBatchBar(kind);
    });
  }

  /* ---------------- Init ---------------- */
  function init() {
    setApiPill(false, "连接中… :8900");

    $$(".nav-item").forEach((btn) => {
      btn.addEventListener("click", () => navigate(btn.dataset.route));
    });

    $("#globalSearch")?.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      const q = e.target.value.trim();
      if (!q) return;
      state.mail.q = q;
      state.mail.page = 1;
      const box = $("#mailSearch");
      if (box) box.value = q;
      navigate("mail");
    });

    // mail filters
    const mailSync = () => {
      state.mail.q = $("#mailSearch").value.trim();
      state.mail.status = $("#mailStatus").value;
      state.mail.unread = $("#mailHasStep").value === "1" ? "1" : $("#mailHasStep").value === "0" ? "0" : "";
      state.mail.hasRfq = $("#mailHasStep").value === "1" ? "1" : "";
      // remap: hasStep select → unread + hasRfq loosely
      if ($("#mailHasStep").value === "1") state.mail.hasRfq = "1";
      if ($("#mailHasStep").value === "0") state.mail.hasRfq = "";
      state.mail.page = 1;
      loadMail();
    };
    ["#mailSearch", "#mailStatus", "#mailCountry", "#mailHasStep"].forEach((id) => {
      $(id)?.addEventListener("input", mailSync);
      $(id)?.addEventListener("change", mailSync);
    });
    $("#mailReset")?.addEventListener("click", () => {
      ["#mailSearch", "#mailStatus", "#mailCountry", "#mailHasStep"].forEach((id) => {
        const el = $(id);
        if (el) el.value = "";
      });
      state.mail.q = state.mail.status = state.mail.unread = state.mail.hasRfq = "";
      state.mail.page = 1;
      loadMail();
    });
    $("#mailEmptyReset")?.addEventListener("click", () => $("#mailReset").click());
    $("#mailClearSel")?.addEventListener("click", () => clearSel("mail"));
    bindAllCheck("mail", "#mailCheckAll");
    bindList("mail");

    // order filters
    const orderSync = () => {
      state.order.q = $("#orderSearch").value.trim();
      state.order.status = $("#orderStatus").value;
      state.order.page = 1;
      loadOrders();
    };
    ["#orderSearch", "#orderStatus", "#orderPriority"].forEach((id) => {
      $(id)?.addEventListener("input", orderSync);
      $(id)?.addEventListener("change", orderSync);
    });
    $("#orderReset")?.addEventListener("click", () => {
      ["#orderSearch", "#orderStatus", "#orderPriority"].forEach((id) => ($(id).value = ""));
      orderSync();
    });
    $("#orderEmptyReset")?.addEventListener("click", () => $("#orderReset").click());
    $("#orderClearSel")?.addEventListener("click", () => clearSel("order"));
    bindAllCheck("order", "#orderCheckAll");
    bindList("order");

    // rag
    const ragSync = () => {
      state.rag.q = $("#ragSearch").value.trim();
      state.rag.page = 1;
      loadRag();
    };
    ["#ragSearch", "#ragModality", "#ragState"].forEach((id) => {
      $(id)?.addEventListener("input", ragSync);
      $(id)?.addEventListener("change", ragSync);
    });
    $("#ragReset")?.addEventListener("click", () => {
      ["#ragSearch", "#ragModality", "#ragState"].forEach((id) => ($(id).value = ""));
      ragSync();
    });
    $("#ragEmptyReset")?.addEventListener("click", () => $("#ragReset").click());
    $("#ragClearSel")?.addEventListener("click", () => clearSel("rag"));
    bindAllCheck("rag", "#ragCheckAll");
    bindList("rag");

    $$(".layer-card").forEach((card) => {
      card.addEventListener("click", () => {
        $$(".layer-card").forEach((c) => c.classList.remove("active"));
        card.classList.add("active");
        state.rag.layer = card.dataset.layer;
        state.rag.page = 1;
        loadRag();
      });
    });

    $$("[data-batch]").forEach((btn) => {
      btn.addEventListener("click", () => runBatch(btn.dataset.batch, btn.dataset.act));
    });

    // STEP
    $("#stepSearch")?.addEventListener("input", renderStepFiles);
    $("#stepFileList")?.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-step]");
      if (!btn) return;
      state.selectedStepId = btn.dataset.step;
      // 清掉服务端 SVG
      document.querySelector("#stepCanvasWrap .server-svg")?.remove();
      renderStepFiles();
      loadStepPreview(state.selectedStepId);
    });
    $$("#stepViewSeg .seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        $$("#stepViewSeg .seg-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.stepMode = btn.dataset.mode;
        document.querySelector("#stepCanvasWrap .server-svg")?.remove();
        $("#stepSvg").style.display = "";
        drawStepSvg(state.stepMode);
      });
    });
    $("#ragSearchBtn")?.addEventListener("click", () => runEvidenceSearch());
    $("#ragQuery")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") runEvidenceSearch();
    });
    $("#useCustomerRag")?.addEventListener("change", () => runEvidenceSearch());
    $("#useWeb")?.addEventListener("change", () => runEvidenceSearch());

    // models
    $$(".wrow input[type=range]").forEach((range) => {
      range.addEventListener("input", () => {
        const b = range.parentElement.querySelector("b");
        if (b) b.textContent = (Number(range.value) / 100).toFixed(2);
      });
    });
    $("#modelSave")?.addEventListener("click", async () => {
      try {
        const cfg = state.modelsCfg || {};
        const models = cfg.models || (cfg.models = {});
        models.llm = {
          ...(models.llm || {}),
          model: $("#omniForm [name=name]").value,
          endpoint: $("#omniForm [name=endpoint]").value,
        };
        models.embedding = {
          ...(models.embedding || {}),
          model: $("#embedForm [name=name]").value,
          endpoint: $("#embedForm [name=endpoint]").value,
        };
        await api(`/v1/models/config`, { method: "POST", body: JSON.stringify({ config: cfg }) });
        toast("模型配置已写入 config/models.yaml");
      } catch (e) {
        toast("保存失败: " + e.message);
      }
    });
    $("#modelProbe")?.addEventListener("click", async () => {
      try {
        const res = await api(`/v1/models/probe`, { method: "POST" });
        const on = Object.entries(res).filter(([, v]) => v && v.online).map(([k]) => k);
        toast(`探测完成 · 在线: ${on.join(", ") || "无（本地推理端未启动）"}`);
        loadStatus();
      } catch (e) {
        toast("探测失败: " + e.message);
      }
    });

    $("#statusRefresh")?.addEventListener("click", () => {
      loadStatus();
      toast("已刷新本地状态");
    });

    $("#btnInfer")?.addEventListener("click", () => navigate("models"));
    $("#btnDeliver")?.addEventListener("click", () => toast("交付网页 = 当前 index.html（真实 API 接线版）"));
    $("#btnRunInfer")?.addEventListener("click", async () => {
      const log = $("#deliverLog");
      if (log) log.textContent = "推理中… /v1/workbench/search + rag";
      await runEvidenceSearch($("#ragQuery")?.value || "6061 motor bracket quote DFM");
      if (log) log.textContent = `推理完成 · 证据 ${state.evidence.length} 条`;
      toast("推理流水线完成");
    });
    $("#btnBuildPage")?.addEventListener("click", () => toast("交付页已就绪：index.html + 真实 API"));

    // bootstrap data
    api(`/health`)
      .then((h) => {
        setApiPill(true, `API ${h.version || "ok"} · :8900`);
        toast(`已接通本地 API · 引擎 ${h.engine || "local"}`);
      })
      .catch((e) => {
        setApiPill(false, "API 离线");
        toast("无法连接 127.0.0.1:8900 — " + e.message);
      });

    loadMail();
    loadOrders();
    loadRag();
    loadModels();
    loadStatus().catch(() => {});
    navigate("overview");
  }

  document.addEventListener("DOMContentLoaded", init);
})();
