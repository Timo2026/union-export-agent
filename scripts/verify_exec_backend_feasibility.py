# -*- coding: utf-8 -*-
"""Feasibility live tests: UEA agent/task vs OpenClaw bridge path vs Hermes readiness."""
import json
import sys
sys.path.insert(0, "scripts")
from ssh_lib import connect, run

c = connect()

# 1) livekernel NemoClaw dispatcher
payload = json.dumps(
    {
        "intent": "查询6061铝件阳极氧化工艺要点",
        "skills": ["process_knowledge"],
        "files": [],
    },
    ensure_ascii=False,
)
print("===== UEA /v1/agent/task =====")
code, out, err = run(
    c,
    f"curl -sS -m 20 -X POST http://127.0.0.1:8888/v1/agent/task -H 'Content-Type: application/json' -d '{payload}'",
    timeout=30,
)
print(out[:1500])

print("\n===== OpenClaw binary paths =====")
code, out, err = run(
    c,
    "ls -la /home/Developer/.npm-global/bin/openclaw /usr/local/bin/openclaw 2>/dev/null; "
    "export PATH=$PATH:/home/Developer/.npm-global/bin; openclaw --version 2>&1 | head -5; "
    "openclaw skills list 2>&1 | head -8",
    timeout=30,
)
print(out[:1500])

print("\n===== Hermes readiness =====")
code, out, err = run(
    c,
    "cat ~/.hermes/gateway_state.json 2>/dev/null | head -c 500; echo; "
    "~/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main --version 2>&1 | head -5; "
    "ls ~/.hermes/skills/email ~/.hermes/skills/autonomous-ai-agents 2>/dev/null | head",
    timeout=30,
)
print(out[:1500])

print("\n===== egress / safety policies (UEA) =====")
code, out, err = run(
    c,
    "curl -sS -m 8 http://127.0.0.1:8888/v1/agent/openshell | python3 -c 'import sys,json;d=json.load(sys.stdin);print(json.dumps(d,ensure_ascii=False)[:800])'",
    timeout=20,
)
print(out[:1000])
c.close()
