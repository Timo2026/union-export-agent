// tabs/models.js — 模型设置: 模型注册表编辑/探活 + L3 路由 lanes + Skills/OpenShell + Gmail 状态
import { jget, jpost, esc, mockBadge } from "../api.js";
import { toast } from "../ui.js";

export async function render(view) {
  view.innerHTML = `
  <div class="panel">
    <h3>模型注册表 <span class="hint">· config/models.yaml · 编辑端点/模型名/启用, 保存后控制器热重建</span></h3>
    <div id="mc-tbl"><div class="loading">加载 /v1/models/config…</div></div>
    <div class="row" style="margin-top:10px">
      <button class="btn" id="mc-save">💾 保存全部</button>
      <button class="btn ghost" id="mc-probe">⟳ 全量探活</button>
      <button class="btn ghost" id="mc-reload">♻ /v1/config/reload</button>
    </div>
  </div>
  <div class="grid cols-2">
    <div class="panel"><h3>L3 Model Mesh 路由</h3><div id="mr-lanes" class="row">加载中…</div></div>
    <div class="panel"><h3>Gmail / 飞书链路 <span class="hint">· 铁律: SMTP/IMAP 默认禁, draft_only</span></h3><div id="gm-box">加载中…</div></div>
  </div>
  <div class="panel">
    <h3>Skills / OpenShell <span class="hint">· 只读概览 (编辑走 config/skills.yaml + /v1/skills/config)</span></h3>
    <div id="sk-box">加载中…</div>
  </div>`;

  let cfg = null;
  async function loadCfg() {
    const box = view.querySelector("#mc-tbl");
    let d;
    try { d = await jget("/v1/models/config"); } catch (e) { box.innerHTML = `<span style="color:var(--bad)">${esc(e.message)}</span>`; return; }
    cfg = d.config; const probe = d.probe || {};
    const models = cfg.models || {};
    box.innerHTML = `<table class="tbl"><thead><tr><th>键</th><th>用途/角色</th><th style="width:230px">Endpoint</th><th style="width:170px">Model</th><th>启用</th><th>探活</th><th></th></tr></thead><tbody>
      ${Object.entries(models).map(([k, v]) => `<tr data-k="${esc(k)}">
        <td class="mono">${esc(k)}</td>
        <td><div>${esc(v.label || k)}</div><div class="muted-cell">${esc(v.role || "")} · ${esc((v.usage || v.note || "").slice(0, 46))}…</div></td>
        <td><input data-f="endpoint" value="${esc(v.endpoint || "")}" style="width:100%"></td>
        <td><input data-f="model" value="${esc(v.model || "")}" style="width:100%"></td>
        <td><input data-f="enabled" type="checkbox" ${v.enabled ? "checked" : ""} ${k === "deterministic" ? "title='deterministic 锁定'" : ""}></td>
        <td class="mc-probe">${probeCell(probe[k])}</td>
        <td class="no-row-click"><button class="btn ghost sm" data-x="probe1">测</button></td>
      </tr>`).join("")}</tbody></table>`;
    box.querySelectorAll("[data-x=probe1]").forEach(b => b.onclick = async () => {
      const k = b.closest("tr").dataset.k;
      b.disabled = true;
      try { const r = await fetch(`/v1/models/probe?key=${k}`, { method: "POST" }); const j = await r.json(); b.closest("tr").querySelector(".mc-probe").innerHTML = probeCell(j[k]); }
      catch (e) { toast(`探活失败: ${e.message}`, "err"); }
      b.disabled = false;
    });
  }
  function probeCell(p) {
    if (!p) return `<span class="dim">—</span>`;
    return p.online ? `<span class="badge live">在线 ${p.latency_ms ?? p.ms ?? ""}ms</span>`
                    : `<span class="badge mock">离线 ${esc(p.error || "")}</span>`;
  }

  view.querySelector("#mc-save").onclick = async () => {
    if (!cfg) return;
    view.querySelectorAll("#mc-tbl tbody tr").forEach(tr => {
      const k = tr.dataset.k, m = cfg.models[k];
      m.endpoint = tr.querySelector('[data-f=endpoint]').value.trim();
      m.model = tr.querySelector('[data-f=model]').value.trim();
      m.enabled = tr.querySelector('[data-f=enabled]').checked;
    });
    try { const r = await jpost("/v1/models/config", cfg); toast("已保存, 控制器已重建"); }
    catch (e) { toast(`保存失败: ${e.message}`, "err"); }
  };
  view.querySelector("#mc-probe").onclick = loadCfg;
  view.querySelector("#mc-reload").onclick = async () => {
    const r = await jpost("/v1/config/reload", {});
    toast(r.ok ? "热重载成功" : `热重载有失败: ${JSON.stringify(r.configs)}`, r.ok ? "ok" : "err");
  };
  loadCfg();

  jget("/v1/model-router/status").then(s => {
    view.querySelector("#mr-lanes").innerHTML = Object.entries(s.lanes || s).map(([lane, v]) => {
      const on = typeof v === "object" ? (v.online ?? v.ok) : !!v;
      return `<span class="chip ${on ? "on" : "mocked"}"><span class="dot"></span>${esc(lane)}</span>`;
    }).join("") || esc(JSON.stringify(s).slice(0, 200));
  }).catch(e => { view.querySelector("#mr-lanes").innerHTML = `<span style="color:var(--bad)">${esc(e.message)}</span>`; });

  Promise.allSettled([jget("/v1/gmail/settings"), jget("/v1/gmail/status")]).then(([set, sta]) => {
    const s = set.status === "fulfilled" ? set.value : { error: String(set.reason) };
    const t = sta.status === "fulfilled" ? sta.value : {};
    view.querySelector("#gm-box").innerHTML = `<dl class="kv">
      <dt>启用</dt><dd>${s.enabled ? "⚠ 已启用" : "✗ 禁用 (默认, 铁律)"}</dd>
      <dt>账号</dt><dd class="mono">${esc(s.user ? s.user.slice(0, 4) + "****" : "未配置")}</dd>
      <dt>模式</dt><dd>${esc(s.draft_only === false ? "draft_only=⚠off" : "draft_only (只出草稿, 不外发)")}</dd>
      <dt>同步状态</dt><dd>${esc(JSON.stringify(t).slice(0, 200))}</dd></dl>`;
  });

  jget("/v1/skills/config").then(d => {
    const sum = d.summary || {};
    const skills = (d.runtime_skills || []);
    view.querySelector("#sk-box").innerHTML = `
      <div class="row" style="margin-bottom:8px">
        <span class="chip">Skills ${esc(sum.enabled ?? sum.n_enabled ?? skills.length)}/${skills.length}</span>
        <span class="chip ${d.iron_rule_1_locked ? "on" : "mocked"}"><span class="dot"></span>铁律① locked</span>
        <span class="chip">OpenShell ${esc((d.openshell?.policies || []).length)} 策略</span></div>
      <div class="row">${skills.map(s => `<span class="chip ${s.enabled === false ? "" : "on"}"><span class="dot"></span>${esc(s.id || s.name)}${s.tier ? ` · ${esc(s.tier)}` : ""}</span>`).join("")}</div>`;
  }).catch(e => { view.querySelector("#sk-box").innerHTML = `<span style="color:var(--bad)">${esc(e.message)}</span>`; });
}
