// app.js — 壳层路由: hash → 六工作台模块懒加载
import { jget, esc } from "./api.js";

const TABS = {
  mail: { title: "邮件台 · 客户邮箱列表", mod: () => import("./tabs/mail.js") },
  orders: { title: "订单台 · 订单列表与状态机", mod: () => import("./tabs/orders.js") },
  drawings: { title: "图纸台 · STEP 预览 (2D/真3D)", mod: () => import("./tabs/drawings.js") },
  intel: { title: "客户情报 · 联网搜索 + RAG + 多模态库", mod: () => import("./tabs/intel.js") },
  models: { title: "模型设置 · 注册表/路由/Skills", mod: () => import("./tabs/models.js") },
  ops: { title: "本地状态 · 服务健康与 trace", mod: () => import("./tabs/ops.js") },
};

function current() {
  const h = (location.hash || "#/mail").replace(/^#\//, "").split("?")[0];
  return TABS[h] ? h : "mail";
}

function paintNav() {
  document.querySelectorAll("#nav a").forEach(a => a.classList.toggle("active", a.dataset.tab === current()));
}

async function route() {
  paintNav();
  const t = TABS[current()];
  document.getElementById("crumb").textContent = t.title;
  const view = document.getElementById("view");
  view.innerHTML = `<div class="loading">加载模块…</div>`;
  try {
    (await t.mod()).render(view);
  } catch (e) {
    view.innerHTML = `<div class="empty"><div class="t">模块加载失败</div><div>${esc(e.message)}</div></div>`;
  }
}

async function svcLine() {
  const el = document.getElementById("svc-line");
  try {
    const [h, m] = await Promise.all([jget("/health").catch(() => ({})), jget("/v1/rag/media/status").catch(() => ({}))]);
    const on = s => !!s;
    el.innerHTML = `<span class="dot" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${h.status === "ok" || h.ok ? "var(--ok)" : "var(--bad)"}"></span>
      核心 ${h.status === "ok" || h.ok ? "正常" : "异常"} · ASR ${on(m.asr) && m.asr.online ? "✓" : "MOCK"} ·
      VLM ${m.vlm?.online ? "✓" : "MOCK"} · EMB ${m.embed && !m.embed.degraded ? "✓" : "MOCK"}`;
  } catch { el.textContent = "核心服务不可达"; }
}

document.getElementById("btn-top-health").onclick = async () => { await svcLine(); route(); };
window.addEventListener("hashchange", route);
route();
svcLine();
setInterval(svcLine, 60000);
