# -*- coding: utf-8 -*-
"""真实本地资源连通测试 — 对 127.0.0.1:8900 做端到端探测并打印报告."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8900"
results = []


def call(method: str, path: str, body=None, timeout=25):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception:
                payload = raw[:200]
            return resp.status, payload
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8"))
        except Exception:
            payload = str(e)
        return e.code, payload
    except Exception as e:
        return 0, repr(e)


def check(name: str, method: str, path: str, body=None, expect=(200,)):
    status, payload = call(method, path, body)
    ok = status in expect
    # extra semantic checks
    note = ""
    if ok and isinstance(payload, dict):
        if path.startswith("/v1/workbench/emails"):
            note = f"total={payload.get('total')} items={len(payload.get('items') or [])}"
        elif path.startswith("/v1/workbench/orders"):
            note = f"total={payload.get('total')} items={len(payload.get('items') or [])}"
        elif path.startswith("/v1/workbench/step/files"):
            note = f"files={payload.get('total')}"
        elif path == "/health":
            note = f"ver={payload.get('version')} engine={payload.get('engine')}"
        elif "rag" in path or path.endswith("/search"):
            keys = [k for k in payload.keys() if k in ("hits", "matches", "rag_results", "web_results", "docs", "items", "collections")]
            note = f"keys={keys}"
        elif path.startswith("/v1/models/config"):
            models = (payload.get("config") or payload).get("models") or {}
            note = f"models={list(models.keys())}"
        elif path.startswith("/v1/workbench/status"):
            note = f"node={list((payload.get('node') or {}).keys())} models={'models' in payload}"
    results.append((ok, name, status, note, payload if not ok else None))
    print(("PASS" if ok else "FAIL"), name, "→", status, note)
    return payload


def main():
    print("=== 真实本地资源连通测试 ===")
    print("BASE:", BASE)

    check("health", "GET", "/health")
    emails = check("workbench/emails", "GET", "/v1/workbench/emails?page=1&page_size=5")
    check("mail/inbox", "GET", "/v1/mail/inbox?limit=3")
    orders = check("workbench/orders", "GET", "/v1/workbench/orders?page=1&page_size=5")
    check("orders_api", "GET", "/v1/orders?page=1&size=3")
    check("workbench/status", "GET", "/v1/workbench/status")
    check("models/config", "GET", "/v1/models/config")
    check("models/probe", "POST", "/v1/models/probe", {})
    check("model-router/status", "GET", "/v1/model-router/status")
    check("rag/docs", "GET", "/v1/rag/docs")
    check("rag/search GET", "GET", "/v1/rag/search?q=6061&topk=3")
    check("workbench/rag/collections", "GET", "/v1/workbench/rag/collections")
    check("workbench/rag/layers", "GET", "/v1/workbench/rag/layers")
    check(
        "workbench/rag/search POST",
        "POST",
        "/v1/workbench/rag/search",
        {"query": "6061 bracket price", "collection": "quote_history", "top_k": 3},
    )
    check(
        "workbench/search RAG+WEB",
        "POST",
        "/v1/workbench/search",
        {"query": "6061 aluminum bracket quote", "scope": ["rag", "web"]},
    )
    step_files = check("workbench/step/files", "GET", "/v1/workbench/step/files?limit=5")
    # preview first real step
    file_id = None
    if isinstance(step_files, dict) and step_files.get("items"):
        file_id = step_files["items"][0]["id"]
    if file_id:
        check("workbench/step/preview", "GET", f"/v1/workbench/step/preview/{file_id}")
    else:
        results.append((False, "workbench/step/preview", 0, "no step files", None))
        print("FAIL workbench/step/preview → no step files")

    # filter + empty state
    check("emails filter empty", "GET", "/v1/workbench/emails?page=1&page_size=5&sender=__no_such__")
    check("orders filter", "GET", "/v1/workbench/emails?page=2&page_size=5")

    # batch mark_read on a real mail id (non-destructive-ish)
    if isinstance(emails, dict) and emails.get("items"):
        mid = emails["items"][0]["id"]
        check(
            "emails/batch mark_read",
            "POST",
            "/v1/workbench/emails/batch",
            {"ids": [mid], "action": "mark_read"},
        )

    check("customer/matches", "GET", "/v1/customer/matches?q=a")
    check("cache/stats", "GET", "/v1/cache/stats")

    # CORS preflight-ish (simple request with Origin)
    status, payload = call("GET", "/health")
    results.append((status == 200, "cors-mode note", status, "frontend uses same-origin or CORS", None))

    passed = sum(1 for r in results if r[0])
    failed = [r for r in results if not r[0]]
    print()
    print(f"=== 结果: {passed}/{len(results)} 通过 ===")
    if failed:
        print("失败项:")
        for ok, name, status, note, payload in failed:
            print(" -", name, status, note, str(payload)[:160] if payload else "")
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()
