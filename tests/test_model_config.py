"""test_model_config.py — 模型注册表 (UI 后端) load/save/validate/probe 测试 (维度: 模型设置工具)."""
from __future__ import annotations

import copy
import http.server
import json
import threading

import pytest

from services import model_config as mc


def test_load_registry_has_six_models():
    cfg = mc.load()
    models = cfg["models"]
    for k in ("llm", "vlm", "embedding", "ocr", "asr", "deterministic"):
        assert k in models, f"缺模型 {k}"
        assert models[k].get("endpoint") and models[k].get("model")


def test_deterministic_is_locked():
    cfg = mc.load()
    assert cfg["models"]["deterministic"].get("locked") is True


def test_validate_ok():
    assert mc.validate(mc.load()) == []


def test_validate_catches_missing_endpoint():
    bad = copy.deepcopy(mc.load())
    bad["models"]["llm"]["endpoint"] = ""
    errs = mc.validate(bad)
    assert any("endpoint" in e for e in errs)


def test_validate_catches_bad_scheme():
    bad = copy.deepcopy(mc.load())
    bad["models"]["asr"]["endpoint"] = "127.0.0.1:8089"
    assert any("http" in e for e in mc.validate(bad))


def test_validate_forbids_disabling_deterministic():
    bad = copy.deepcopy(mc.load())
    bad["models"]["deterministic"]["enabled"] = False
    assert any("deterministic" in e for e in mc.validate(bad))


# ---- BUG-1 自洽不变式: note 的诚实性标注必须与 enabled 一致 ----
# 节点实测 (09-25 巡检): live models.yaml 的 ocr.enabled 被手改为 true, 而 note 仍是
# models.node.yaml 的「本档显式 disabled 不冒充」→ UI 显示「已启用」但注释宣称 disabled,
# 诚实性标注与事实相反。不变式: note 声明 disabled/不冒充 ⇒ enabled 必须为 false;
# 对称地, enabled=false 的 lane 必须在 note/label 里诚实标注 (禁静默禁用)。
def test_validate_catches_note_says_disabled_but_enabled_true():
    bad = copy.deepcopy(mc.load())
    bad["models"]["ocr"]["enabled"] = True                     # 复刻节点实况
    bad["models"]["ocr"]["note"] = "节点无独立 OCR 服务; 本档显式 disabled 不冒充"
    errs = mc.validate(bad)
    assert any("ocr" in e and ("disabled" in e or "note" in e) for e in errs)


def test_validate_catches_silent_disable():
    bad = copy.deepcopy(mc.load())
    bad["models"]["asr"]["enabled"] = False                    # note 无离线/停用标注
    errs = mc.validate(bad)
    assert any("asr" in e for e in errs)


def test_node_registry_note_enabled_coherent():
    # 回归防线: repo 的节点风味注册表 (部署时覆盖节点 config/models.yaml) 必须自洽
    import yaml
    p = mc._ROOT / "config" / "models.node.yaml"
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert mc.validate(cfg) == []


def test_save_forces_deterministic_locked(tmp_path, monkeypatch):
    # 重定向到临时文件, 不污染真实 models.yaml
    tmp = tmp_path / "models.yaml"
    tmp.write_text(open(mc._MODELS_YAML, encoding="utf-8").read(), encoding="utf-8")
    monkeypatch.setattr(mc, "_MODELS_YAML", tmp)
    cfg = mc.load()
    cfg["models"]["deterministic"]["locked"] = False      # 试图解锁 (enabled 保持 True)
    saved = mc.save(cfg)
    assert saved["models"]["deterministic"]["locked"] is True   # 被强制恢复锁定
    assert saved["models"]["deterministic"]["enabled"] is True
    assert "updated_at" in saved


def test_save_rejects_disabling_deterministic(tmp_path, monkeypatch):
    tmp = tmp_path / "models.yaml"
    tmp.write_text(open(mc._MODELS_YAML, encoding="utf-8").read(), encoding="utf-8")
    monkeypatch.setattr(mc, "_MODELS_YAML", tmp)
    cfg = mc.load()
    cfg["models"]["deterministic"]["enabled"] = False     # 铁律①: 不可禁用
    with pytest.raises(ValueError):
        mc.save(cfg)


def test_probe_url_construction():
    ep = mc._probe_url({"endpoint": "http://127.0.0.1:1234/v1", "probe_path": "/models"})
    assert ep == "http://127.0.0.1:1234/v1/models"
    ep2 = mc._probe_url({"endpoint": "http://127.0.0.1:7862/", "probe_path": "api/health"})
    assert ep2 == "http://127.0.0.1:7862/api/health"


def test_probe_one_disabled_skips():
    r = mc.probe_one({"endpoint": "http://x", "enabled": False})
    assert r["online"] is False and r.get("skipped") == "disabled"


def test_probe_one_unreachable_offline():
    r = mc.probe_one({"endpoint": "http://127.0.0.1:59996", "probe_path": "/health", "enabled": True}, timeout=1.0)
    assert r["online"] is False and "error" in r


def test_probe_all_returns_all_keys():
    cfg = mc.load()
    out = mc.probe_all(timeout=1.0)
    # 契约: 注册表里每个模型都必须出现在探测输出 (遍历 cfg 而非硬编码六个键 —
    # 节点 config/models.yaml = models.node.yaml 实测注册表, 键集合与开发机不同)
    for k in cfg["models"]:
        assert k in out and "online" in out[k]
    # funasr_gateway 段存在时才输出对应键; 节点注册表无此段 (Omni :8002 覆盖
    # ASR/VLM, 无独立 funasr 网关 — PRD-P0-NODE-ALIGNMENT §6.4)
    if (cfg.get("funasr_gateway") or {}).get("endpoint"):
        assert "funasr_gateway" in out and "online" in out["funasr_gateway"]


def test_endpoint_for_respects_enabled():
    cfg = copy.deepcopy(mc.load())
    assert mc.endpoint_for("llm", cfg) is not None
    cfg["models"]["llm"]["enabled"] = False
    assert mc.endpoint_for("llm", cfg) is None


# ---- 真实推理探活 (巡检 P1: 端点探活 ≠ 推理延迟) ----
class _FakeChat(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if body.get("max_tokens") != 1 or body["messages"][0]["content"] != "ping":
            self.send_response(400)
            self.end_headers()
            return
        resp = json.dumps({"choices": [{"message": {"content": "pong"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def log_message(self, *a):
        pass


def test_probe_completion_disabled_skips():
    r = mc.probe_completion({"endpoint": "http://x/v1", "model": "m", "enabled": False})
    assert r["online"] is False and r.get("skipped") == "disabled"


def test_probe_completion_non_chat_endpoint_rejected():
    # 巡检 P1: 非 OpenAI 风格端点 (如 asr 根路径) 不得编造推理时延
    r = mc.probe_completion({"endpoint": "http://127.0.0.1:8089", "model": "Qwen3-ASR", "enabled": True})
    assert r["online"] is False and "completion_ms" in r


def test_probe_completion_unreachable_offline():
    r = mc.probe_completion({"endpoint": "http://127.0.0.1:59996/v1", "model": "m", "enabled": True}, timeout=1.0)
    assert r["online"] is False and "error" in r and "completion_ms" in r


def test_probe_completion_measures_real_latency():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeChat)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        r = mc.probe_completion(
            {"endpoint": f"http://127.0.0.1:{srv.server_port}/v1", "model": "test-model", "enabled": True},
            timeout=5.0)
        assert r["online"] is True and r["completion_ms"] >= 0
        assert r["url"].endswith("/v1/chat/completions")
    finally:
        srv.shutdown()
        th.join()
