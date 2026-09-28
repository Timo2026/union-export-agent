#!/usr/bin/env bash
# verify_replica.sh — 一键自检（4 项判据全过才算通）
set -uo pipefail
B=http://127.0.0.1:8888
pass=0; fail=0
# 1) 服务健康
h=$(curl -s -m 8 $B/health | grep -o '"status":"ok"' || true)
[ -n "$h" ] && echo "✅ health" && pass=$((pass+1)) || { echo "❌ health"; fail=$((fail+1)); }
# 2) 黄金链报价非空（rules 路由, 不依赖 LLM）
q=$(curl -s -m 120 -X POST $B/v1/agent/task -H 'Content-Type: application/json' \
    -d '{"intent":"6061 铝件 阳极氧化 100 件 报价","driver":"console","use_llm":false}' \
    | grep -o '"unit_price":[0-9.]*' | head -1)
[ -n "$q" ] && echo "✅ 黄金链 $q" && pass=$((pass+1)) || { echo "❌ 黄金链"; fail=$((fail+1)); }
# 3) verify 状态返回
v=$(curl -s -m 120 -X POST $B/v1/agent/task -H 'Content-Type: application/json' \
    -d '{"intent":"6061 报价","driver":"console","use_llm":false}' | grep -o '"verification_status":"[A-Z]*"' | head -1)
[ -n "$v" ] && echo "✅ verify $v" && pass=$((pass+1)) || { echo "❌ verify"; fail=$((fail+1)); }
# 4) openshell viol=0
vi=$(curl -s -m 120 -X POST $B/v1/agent/task -H 'Content-Type: application/json' \
    -d '{"intent":"304 不锈钢 20 件 报价","driver":"console","use_llm":false}' | grep -c '确定性输出被改写' || true)
[ "$vi" = "0" ] && echo "✅ iron-rule viol=0" && pass=$((pass+1)) || { echo "❌ viol=$vi"; fail=$((fail+1)); }
echo "---- pass=$pass fail=$fail ----"
[ $fail -eq 0 ] && echo "REPLICA OK 🎉" || exit 1
