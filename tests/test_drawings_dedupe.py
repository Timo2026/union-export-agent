"""test_drawings_dedupe.py — 巡检报告 BUG-2 (P1): 图纸库 sha256_16 去重折叠 + 二进制伪 STEP 前置校验.

根因 (节点实测比报告更严重 — 本地同样中招):
  - 列表去重曾按落盘 stem (api_server.py list_drawings), 同名不同内容才会折叠,
    同内容不同名 (part.step ×36 on node / ×186 local) 全部漏过 → 用户翻页都是同一张图。
  - 二进制 CAD 误改 .step 后缀: /v1/upload/step-with-thumbnail 先 _save_upload 后
    make_thumbnail, 400 失败时孤儿文件已落盘 → 列表出现 has_thumb/has_mesh 全假的图纸。

修复契约 (TDD):
  - list_drawings 按 sha256_16 折叠: 最新一条为代表行 + copies + duplicate_ids;
  - _drawing_row 增 pseudo_step 诚实旗标 (文件头非 ISO-10303-21);
  - 上传端点前置读 64B 文件头校验, 拒绝于落盘之前 (不留孤儿);
  - step_mesh.looks_like_iso_step_head(bytes) — 路径版 _looks_like_iso_step 复用之。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import services.api_server as api
from services.api_server import app

ISO = b"ISO-10303-21;\n"
BINARY = b"V\0\0\0 J\0\0\0 J\0\0\0 FE FF FF FF" + b"\x00" * 32


@pytest.fixture
def drawing_env(tmp_path, monkeypatch):
    """隔离图纸目录 + 缩略图目录 + 上传目录, 不碰真实 data/。"""
    d3d = tmp_path / "step3d"
    d3d.mkdir()
    dstep = tmp_path / "step"
    dstep.mkdir()
    monkeypatch.setattr(api, "_DRAWING_DIRS", (d3d, dstep))
    monkeypatch.setattr(api, "_THUMB_DIR", tmp_path / "thumbnails")
    monkeypatch.setattr(api, "_ART", tmp_path / "artifacts")
    return {"3d": d3d, "step": dstep, "art": tmp_path / "artifacts"}


def _write(d: Path, name: str, content: bytes, age_s: float = 0.0) -> Path:
    p = d / name
    p.write_bytes(content)
    if age_s:
        ts = p.stat().st_mtime - age_s
        os.utime(p, (ts, ts))
    return p


# ---------- step_mesh 文件头 helper ----------

def test_looks_like_iso_step_head_helper():
    from services.step_mesh import looks_like_iso_step_head
    assert looks_like_iso_step_head(ISO)
    assert looks_like_iso_step_head(b"\n\n\xef\xbb\xbf ISO-10303-21;")   # 前导空白 + BOM 仍放行
    assert not looks_like_iso_step_head(BINARY)                          # 二进制 CAD 拒认
    assert not looks_like_iso_step_head(b"")                             # 空文件不得误放行
    assert not looks_like_iso_step_head(b"ISO-1030")                     # 头不足同样拒认


def test_looks_like_iso_step_path_delegates(tmp_path):
    from services.step_mesh import _looks_like_iso_step
    ok = tmp_path / "ok.step"
    ok.write_bytes(ISO + b"x" * 100)
    bogus = tmp_path / "bogus.step"
    bogus.write_bytes(BINARY)
    assert _looks_like_iso_step(str(ok))
    assert not _looks_like_iso_step(str(bogus))


# ---------- _drawing_row 诚实旗标 ----------

def test_drawing_row_flags_pseudo_step(drawing_env):
    bin_p = _write(drawing_env["3d"], "1789000000001_abc_binary_part.step", BINARY)
    iso_p = _write(drawing_env["3d"], "1789000000002_abc_text_part.step", ISO + b"x" * 64)
    r_bin = api._drawing_row(bin_p)
    r_iso = api._drawing_row(iso_p)
    assert r_bin["pseudo_step"] is True
    assert r_iso["pseudo_step"] is False
    assert r_bin["copies"] == 1 and r_bin["duplicate_ids"] == []


# ---------- list_drawings sha 折叠 ----------

def test_list_drawings_dedupes_by_sha_with_copies(drawing_env):
    same = ISO + b"a" * 128
    _write(drawing_env["3d"], "1789000000000_aaa_part.step", same, age_s=500)   # 旧副本
    _write(drawing_env["3d"], "1789000000009_bbb_part.step", same)              # 最新副本 = 代表
    _write(drawing_env["3d"], "1789000000005_ccc_other.step", ISO + b"b" * 64)
    body = TestClient(app).get("/v1/drawings", params={"page_size": 100}).json()
    assert body["total"] == 2, body
    rep = next(i for i in body["items"] if i["sha256_16"] == __import__("hashlib")
               .sha256(same).hexdigest()[:16])
    assert rep["id"] == "1789000000009_bbb_part"          # 最新一条为代表
    assert rep["copies"] == 2
    assert rep["duplicate_ids"] == ["1789000000000_aaa_part"]
    # q 搜索仍可命中代表行 (名称/id/sha 任一即可)
    hit = TestClient(app).get("/v1/drawings", params={"q": "part"}).json()
    assert any(i["id"] == rep["id"] for i in hit["items"])


def test_list_drawings_dedupe_prefers_newest_across_dirs(drawing_env):
    same = ISO + b"c" * 96
    _write(drawing_env["step"], "1789000000001_old_in_step_dir.step", same, age_s=900)
    _write(drawing_env["3d"], "1789000000009_new_in_3d_dir.step", same)
    body = TestClient(app).get("/v1/drawings", params={"page_size": 100}).json()
    assert body["total"] == 1
    rep = body["items"][0]
    assert rep["id"] == "1789000000009_new_in_3d_dir"   # 跨目录也按内容新旧取代表 (id=stem)
    assert rep["copies"] == 2 and rep["duplicate_ids"] == ["1789000000001_old_in_step_dir"]


# ---------- 上传前置校验 (拒绝于落盘之前) ----------

def test_upload_step_with_thumbnail_rejects_binary_before_saving(drawing_env):
    r = TestClient(app).post(
        "/v1/upload/step-with-thumbnail",
        files={"file": ("part.step", BINARY, "application/octet-stream")})
    assert r.status_code == 400
    assert "ISO-10303-21" in r.json()["detail"]
    saved_dir = drawing_env["art"] / "step3d"              # 前置校验失败不得留孤儿文件
    assert not saved_dir.exists() or not any(saved_dir.iterdir())


def test_upload_step_with_thumbnail_iso_head_not_overblocked(drawing_env, monkeypatch):
    from services import step_thumbnail as st_mod
    monkeypatch.setattr(st_mod, "make_thumbnail",
                        lambda timo, path: {"ok": True, "svg": "<svg/>", "bbox": [1, 2, 3],
                                            "sha256_16": "deadbeefdeadbeef"})
    r = TestClient(app).post(
        "/v1/upload/step-with-thumbnail",
        files={"file": ("part.step", ISO + b"x" * 200, "application/octet-stream")})
    assert r.status_code == 200, r.text
    assert r.json()["drawing_id"].endswith("_part")
    saved = list((drawing_env["art"] / "step3d").glob("*.step"))
    assert len(saved) == 1 and saved[0].read_bytes().startswith(ISO)   # 内容完整未被读头截断
