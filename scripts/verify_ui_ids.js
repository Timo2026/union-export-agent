const fs = require("fs");
const html = fs.readFileSync("index.html", "utf8");
const need = [
  "route-mail", "route-orders", "route-step", "route-rag", "route-models", "route-status",
  "mailTbody", "orderTbody", "ragTbody", "stepSvg", "evidenceList",
  "mailPager", "orderPager", "ragPager", "mailEmpty", "orderEmpty", "ragEmpty",
  "mailBatchBar", "orderBatchBar", "ragBatchBar",
];
const miss = need.filter((id) => !html.includes('id="' + id + '"'));
if (miss.length) {
  console.error("MISSING:", miss.join(","));
  process.exit(1);
}
console.log("HTML ids OK");
console.log("nav routes:", (html.match(/data-route=/g) || []).length);
console.log("routes sections:", (html.match(/class="route/g) || []).length);
