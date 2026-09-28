#!/usr/bin/env bash
# verify_replica.sh — 一键自检（前置可达性 + 4 项判据）
#
# 前置：服务需已在 :8888 起（否则本脚本无法验证任何判据，会以退出码 2 明确报"服务未起"，
#       而不是含糊地报 4 个 ❌）。起服务：python scripts/start_api.py --port 8888 --background
# 注意：第 2/3/4 项走 /v1/agent/task 黄金链，需制造内核 (Timo v12, _timo_engine) 或
#       其离线兜底可达；公开 clone 不含内核时这几项会失败——这是分发边界，不是脚本故障。
set -uo pipefail
B=${UEA_BASE_URL:-http://127.0.0.1:8888}
pass=0; fail=0

# 0) 服务可达性（前置；不可达直接退出 2，避免误报）
if ! curl -s -m 8 "$B/health" >/dev/null 2>&1; then
  echo "⛔ 服务不可达：$B/health"
  echo "   请先启动：python scripts/start_api.py --port ${B##*:} --background"
  exit 2
fi

# 1) 服务健康
h=$(curl -s -m 8 "$B/health" | grep -o '"status":"ok"' || true)
[ -n "$h" ] && echo "✅ health" && pass=$((pass+1)) || { echo "❌ health"; fail=$((fail+1)); }
# 2) 黄金链报价非空（rules 路由, 不依赖 LLM）
q=$(curl -s -m 120 -X POST "$B/v1/agent/task" -H 'Content-Type: application/json' \
    -d '{"intent":"6061 铝件 阳极氧化 100 件 报价","driver":"console","use_llm":false}' \
    | grep -o '"unit_price":[0-9.]*' | head -1)
[ -n "$q" ] && echo "✅ 黄金链 $q" && pass=$((pass+1)) || { echo "❌ 黄金链（需制造内核；公开 clone 不含）"; fail=$((fail+1)); }
# 3) verify 状态返回
v=$(curl -s -m 120 -X POST "$B/v1/agent/task" -H 'Content-Type: application/json' \
    -d '{"intent":"6061 报价","driver":"console","use_llm":false}' | grep -o '"verification_status":"[A-Z]*"' | head -1)
[ -n "$v" ] && echo "✅ verify $v" && pass=$((pass+1)) || { echo "❌ verify"; fail=$((fail+1)); }
# 4) openshell viol=0
vi=$(curl -s -m 120 -X POST "$B/v1/agent/task" -H 'Content-Type: application/json' \
    -d '{"intent":"304 不锈钢 20 件 报价","driver":"console","use_llm":false}' | grep -c '确定性输出被改写' || true)
[ "$vi" = "0" ] && echo "✅ iron-rule viol=0" && pass=$((pass+1)) || { echo "❌ viol=$vi"; fail=$((fail+1)); }
echo "---- pass=$pass fail=$fail ----"
[ $fail -eq 0 ] && echo "REPLICA OK 🎉" || exit 1
