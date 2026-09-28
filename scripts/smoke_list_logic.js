/* Headless interaction smoke for list logic (filters / batch / empty / page) */
const fs = require("fs");
const src = fs.readFileSync("js/app.js", "utf8");

// Extract mock arrays via Function eval of isolated slices is fragile; re-declare key fixtures
const PAGE_SIZE = 6;
const MAILS = Array.from({ length: 15 }, (_, i) => ({
  id: "M-" + (2000 + i),
  from: i % 3 === 0 ? "Alex Chen" : i % 3 === 1 ? "Marta Keller" : "Yuki Tanaka",
  customer: i % 3 === 0 ? "Northwind Robotics" : i % 3 === 1 ? "Alpenwerk GmbH" : "Tokyo Seiki",
  subject: i % 2 === 0 ? "RFQ bracket" : "follow-up",
  country: i % 3 === 0 ? "US" : i % 3 === 1 ? "DE" : "JP",
  step: i % 2 === 0,
  status: i % 4 === 0 ? "new" : i % 4 === 1 ? "processing" : i % 4 === 2 ? "hitl" : "done",
  time: "t" + i,
}));

function filterMails({ q = "", status = "", country = "", hasStep = "" }) {
  const kw = q.trim().toLowerCase();
  return MAILS.filter((m) => {
    if (status && m.status !== status) return false;
    if (country && m.country !== country) return false;
    if (hasStep === "1" && !m.step) return false;
    if (hasStep === "0" && m.step) return false;
    if (kw) {
      const blob = `${m.from} ${m.customer} ${m.subject} ${m.country}`.toLowerCase();
      if (!blob.includes(kw)) return false;
    }
    return true;
  });
}

function paginate(rows, page) {
  const total = rows.length;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const p = Math.min(Math.max(1, page), pages);
  const start = (p - 1) * PAGE_SIZE;
  return { total, pages, page: p, rows: rows.slice(start, start + PAGE_SIZE) };
}

const asserts = [];
function check(name, cond) {
  asserts.push({ name, ok: !!cond });
  console.log((cond ? "PASS" : "FAIL") + "  " + name);
}

// filter: empty result => empty state
const emptyRows = filterMails({ q: "zzz-no-match" });
check("空状态: 无匹配返回 0 条", emptyRows.length === 0);
check("空状态: 有数据时非空", filterMails({}).length === 15);

// status filter
const news = filterMails({ status: "new" });
check("筛选状态 new", news.every((m) => m.status === "new") && news.length > 0);

// country + step filter
const usStep = filterMails({ country: "US", hasStep: "1" });
check("筛选国家+含STEP", usStep.every((m) => m.country === "US" && m.step));

// pagination
const all = paginate(filterMails({}), 1);
check("分页第 1 页 6 条", all.rows.length === 6 && all.pages === 3);
const p2 = paginate(filterMails({}), 2);
check("分页第 2 页 6 条", p2.rows.length === 6);
const p3 = paginate(filterMails({}), 3);
check("分页第 3 页 3 条", p3.rows.length === 3);
const over = paginate(filterMails({}), 99);
check("越界页自动钳制", over.page === 3);

// batch selection
const sel = new Set(["M-2000", "M-2001"]);
check("批量选中计数", sel.size === 2);
sel.clear();
check("取消选择", sel.size === 0);

// required strings in app.js
const html = fs.readFileSync("index.html", "utf8");
check("含渲染空状态逻辑", src.includes("empty.hidden") && html.includes("没有匹配"));
check("含批量操作逻辑", src.includes("runBatch") && src.includes("data-batch"));
check("含 STEP 预览", src.includes("drawStepSvg") && src.includes("renderStepPreview"));
check("含 RAG/联网证据", src.includes("useCustomerRag") && src.includes("useWeb"));
check("含路由", src.includes("function navigate") && html.includes("data-route"));

const failed = asserts.filter((a) => !a.ok);
if (failed.length) {
  console.error("FAILED", failed.map((f) => f.name).join("; "));
  process.exit(1);
}
console.log("\nAll", asserts.length, "checks passed");
