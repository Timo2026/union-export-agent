// api.js — 唯一 fetch 层 + MOCK 铁律检测 + 格式化. 所有视图经此访问后端。
export const STATUS_ZH_FALLBACK = { inquiry: "询盘", quote: "报价", sample: "样品", batch: "批量", shipped: "发货", closed: "完结", lost: "丢单" };

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function toErr(resp) {
  let detail = "";
  try { const j = await resp.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j); } catch { detail = resp.statusText; }
  const e = new Error(detail || `HTTP ${resp.status}`); e.status = resp.status; throw e;
}

export async function jget(url) {
  const r = await fetch(url);
  if (!r.ok) await toErr(r);
  return r.json();
}

export async function jsend(url, method, body, { form = false } = {}) {
  const opt = { method, headers: {} };
  if (form) opt.body = body; else { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body ?? {}); }
  const r = await fetch(url, opt);
  if (!r.ok) await toErr(r);
  return r.json();
}

export const jpost = (u, b, o) => jsend(u, "POST", b, o);
export const jpatch = (u, b) => jsend(u, "PATCH", b);
export const jdel = (u) => jsend(u, "DELETE", {});

// ---- MOCK 铁律检测: _mock/mock/degraded=true, 或 source 值以 MOCK: / *-offline / *-error 开头 ----
export function mockScan(obj, depth = 0) {
  const hits = [];
  if (obj == null || depth > 6) return hits;
  if (Array.isArray(obj)) { for (const v of obj) hits.push(...mockScan(v, depth + 1)); return hits; }
  if (typeof obj !== "object") return hits;
  for (const [k, v] of Object.entries(obj)) {
    if ((k === "_mock" || k === "mock" || k === "degraded") && v === true) hits.push(k);
    else if (typeof v === "string" && /source|_url|endpoint/i.test(k) && /^(MOCK[:\w]*|.*-(offline|error))/.test(v)) hits.push(v);
    else hits.push(...mockScan(v, depth + 1));
  }
  return hits;
}

export function isMock(obj) { return mockScan(obj).length > 0; }

export function mockBadge(obj, { liveText = "LIVE", mockText } = {}) {
  const found = mockScan(obj);
  if (!found.length) return `<span class="badge live">${liveText}</span>`;
  const label = mockText || `MOCK · ${[...new Set(found)].slice(0, 3).join(", ")}`;
  return `<span class="badge mock" title="${esc(label)}">${esc(label.length > 60 ? label.slice(0, 57) + "…" : label)}</span>`;
}

// ---- 格式化 ----
export function fmtTs(ts) {
  if (!ts) return "—";
  const d = new Date(typeof ts === "string" ? ts : ts * 1000);
  if (isNaN(d)) return String(ts);
  const p = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function fmtBytes(n) {
  if (n == null) return "—";
  if (n < 1024) return n + " B";
  if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
  return (n / 1048576).toFixed(2) + " MB";
}

export function fmtMoney(n) { return n == null ? "—" : "$" + Number(n).toLocaleString("en-US", { maximumFractionDigits: 2 }); }

export function statusChip(s, zh) {
  const label = zh?.[s] || STATUS_ZH_FALLBACK[s] || s || "—";
  return `<span class="badge st-${esc(s)}">${esc(label)}</span>`;
}
