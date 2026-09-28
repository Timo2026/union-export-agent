"""test_asr_cli_mode.py — FunASRAdapter cli 模式 + scripts/asr_cli.py 契约 (节点实测链).

背景 (节点 2026-09-25 实证):
  - occ 解释器 (livekernel 运行时) 内 faster_whisper/funasr/whisper 全缺失 → ASR 无引擎
  - omni input_audio 只吐英文音频场景描述 ("In the Tan Sui Xia, ...") → 不能当中文转写源
  - 正解: 独立解释器 (vidproc, faster-whisper 1.2.1) 跑 scripts/asr_cli.py 子进程,
    契约 stdout=转写文本, 非 0 exit=明确失败; 失败回落策略由 asr_cli_fallback 控制
    (默认 False: omni caption 会污染 RAG, 宁可显式 MOCK)。

用真实子进程跑 tmp 脚本 + http.server 假 omni; 不碰网络外真实服务。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from adapters.funasr_adapter import FunASRAdapter

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def wav_file(tmp_path):
    p = tmp_path / "tone.wav"
    p.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00")
    return p


def _write_script(tmp_path, name: str, body: str) -> str:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return str(p)


def _cli_cfg(script: str, **over: Any) -> Dict[str, Any]:
    cfg = {"funasr": {"asr_mode": "cli", "asr_cli": script,
                      "asr_cli_python": sys.executable}}
    cfg["funasr"].update(over)
    return cfg


OK_SCRIPT = "import sys; print('客户要求 6061 铝件 50 件'); sys.exit(0)"


# ---------------- 成功链: 子进程 stdout = 转写 ----------------
def test_cli_success_returns_live_source(tmp_path, wav_file):
    script = _write_script(tmp_path, "ok_asr.py", OK_SCRIPT)
    a = FunASRAdapter(_cli_cfg(script))
    r = a.transcribe(str(wav_file), mock_text="占位")
    assert r["_mock"] is False
    assert r["text"] == "客户要求 6061 铝件 50 件"
    assert r["_source"] == "live:asr-cli:ok_asr.py"


def test_cli_success_strips_stdout(tmp_path, wav_file):
    script = _write_script(tmp_path, "ws_asr.py", "import sys; print('  你好 世界 \\n')")
    a = FunASRAdapter(_cli_cfg(script))
    r = a.transcribe(str(wav_file))
    assert r["_mock"] is False and r["text"] == "你好 世界"


def test_cli_timeout_configurable_default_900():
    a = FunASRAdapter({"funasr": {"asr_mode": "cli"}})
    assert a.asr_cli_timeout == 900        # 38.6s 音频 cold start 实测 139s, 180s 会误杀
    assert a.asr_cli_fallback is False     # 默认不回落 omni: caption 污染 RAG
    assert a.asr_cli == "scripts/asr_cli.py"


def test_cli_relative_script_resolves_against_repo_root():
    # scripts/asr_cli.py 随仓交付 (zip=部署载体), 必须能被解析到真实文件
    a = FunASRAdapter({"funasr": {"asr_mode": "cli"}})
    resolved = a._resolve_asr_cli()
    assert resolved is not None and resolved.exists()
    assert resolved == REPO_ROOT / "scripts" / "asr_cli.py"


# ---------------- 失败链: 显式 MOCK + 原因, 绝不冒充生产 ----------------
def test_cli_nonzero_exit_explicit_mock_with_reason(tmp_path, wav_file):
    script = _write_script(
        tmp_path, "fail_asr.py",
        "import sys; sys.stderr.write('model load failed'); sys.exit(4)")
    a = FunASRAdapter(_cli_cfg(script))
    r = a.transcribe(str(wav_file), mock_text="占位转写")
    assert r["_mock"] is True
    assert "MOCK(asr-cli failed" in r["_source"]
    assert "exit=4" in r["_source"]            # 失败码如实可查
    assert "model load failed" in r["_source"]
    assert r["text"] == "占位转写"


def test_cli_empty_stdout_explicit_mock(tmp_path, wav_file):
    script = _write_script(tmp_path, "empty_asr.py", "import sys; sys.exit(0)")
    a = FunASRAdapter(_cli_cfg(script))
    r = a.transcribe(str(wav_file), mock_text="占位")
    assert r["_mock"] is True and "empty stdout" in r["_source"]


def test_cli_missing_script_explicit_mock(wav_file):
    a = FunASRAdapter(_cli_cfg(str(Path("/nonexistent/asr_cli.py"))))
    r = a.transcribe(str(wav_file), mock_text="占位")
    assert r["_mock"] is True and "MOCK:asr-cli-missing" in r["_source"]


def test_cli_missing_script_raises_when_mock_disabled(wav_file):
    a = FunASRAdapter(_cli_cfg("/nonexistent/asr_cli.py", allow_mock=False))
    with pytest.raises(RuntimeError, match="asr cli script not found"):
        a.transcribe(str(wav_file))


def test_cli_failure_raises_when_mock_disabled(tmp_path, wav_file):
    script = _write_script(tmp_path, "fail2.py", "import sys; sys.exit(3)")
    a = FunASRAdapter(_cli_cfg(script, allow_mock=False))
    with pytest.raises(RuntimeError):
        a.transcribe(str(wav_file))


def test_cli_timeout_explicit_mock(tmp_path, wav_file):
    script = _write_script(tmp_path, "slow_asr.py",
                           "import time; time.sleep(5); print('太慢')")
    a = FunASRAdapter(_cli_cfg(script, asr_cli_timeout_s=1))
    r = a.transcribe(str(wav_file), mock_text="占位")
    assert r["_mock"] is True and "TimeoutExpired" in r["_source"]


# ---------------- asr_cli_fallback: 回落 omni 且来源保留失败原因 ----------------
class _FakeOmni:
    def __init__(self) -> None:
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = b'{"status": "ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                outer.ok = True

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(n)
                data = '{"choices":[{"finish_reason":"stop","message":{"role":"a","content":"omni 转写"}}]}'.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.ok = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        self.thread = __import__("threading").Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def close(self) -> None:
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)


def test_cli_fallback_to_omni_annotates_source(tmp_path, wav_file):
    fake = _FakeOmni()
    try:
        script = _write_script(tmp_path, "fail3.py", "import sys; sys.exit(1)")
        a = FunASRAdapter({"funasr": {
            "asr_mode": "cli", "asr_cli": script, "asr_cli_python": sys.executable,
            "asr_cli_fallback": True, "base_url": f"{fake.url()}/v1",
            "asr_url": f"{fake.url()}/v1", "asr_model": "nemotron-omni-30b-a3b"}})
        r = a.transcribe(str(wav_file), mock_text="占位")
        assert r["_mock"] is False and r["text"] == "omni 转写"
        # 回落来源必须保留原始失败原因, 让上游知道这不是首选路径
        assert "MOCK(asr-cli failed" in r["_source"]
        assert "omni-fallback:live:omni-asr:" in r["_source"]
    finally:
        fake.close()


# ---------------- scripts/asr_cli.py 退出码契约 (不依赖 faster_whisper 的分支) ----------------
def test_asr_cli_missing_args_exit_2():
    p = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "asr_cli.py")],
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 2 and "usage" in p.stderr.lower()


def test_asr_cli_nonexistent_file_exit_2():
    p = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "asr_cli.py"),
                        "/nonexistent/audio.wav"],
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 2 and "usage" in p.stderr.lower()


def test_asr_cli_env_overrides_model_and_lang():
    # 模型/语言走 env (LIVEKERNEL_ASR_MODEL/LANG), 脚本源码须含这俩键的读取
    src = (REPO_ROOT / "scripts" / "asr_cli.py").read_text(encoding="utf-8")
    assert "LIVEKERNEL_ASR_MODEL" in src and "LIVEKERNEL_ASR_LANG" in src
    assert "faster_whisper" in src or "WhisperModel" in src


# ---------------- 节点 profile 必须携带 cli 接线 (交付缺口回归) ----------------
def _load_profile() -> Dict[str, Any]:
    with open(REPO_ROOT / "config" / "settings.dgx-spark-nvidia.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_node_profile_declares_cli_mode():
    f = _load_profile().get("funasr", {})
    assert f.get("asr_mode") == "cli"
    assert f.get("asr_cli") == "scripts/asr_cli.py"
    assert int(f.get("asr_cli_timeout_s", 0)) >= 900
    assert f.get("asr_cli_fallback") is False


def test_profile_script_exists_in_repo():
    f = _load_profile().get("funasr", {})
    script = f.get("asr_cli", "")
    assert script and (REPO_ROOT / script).exists(), \
        f"profile 指向的 {script} 必须随仓交付 (zip=部署载体)"
