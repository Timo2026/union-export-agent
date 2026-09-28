"""test_step_mesh.py — v7.0 STEP 真 3D 网格管线.

真实走子进程 OCP (有效件构建 + 损坏件降级 + 404), 不 mock 几何。
"""
from __future__ import annotations

import base64
import struct
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api_server import app

client = TestClient(app)

GOOD = "1789748494730_dda3ce_flange_cq__5_"   # data/artifacts/step3d 下真实法兰
BAD = "1789700588054_db824b_demo"             # 头部语法损坏的 STEP

# 前 3 个端点用例依赖 data/artifacts/step3d 运行时产物 (.gitignore, 公开克隆/
# 新装机不含): 与 test_tools_physically_exist 同模式跳过; 纯函数用例恒跑。
_STEP3D = Path(__file__).resolve().parent.parent / "data" / "artifacts" / "step3d"
_ARTIFACTS_SKIP = pytest.mark.skipif(
    not _STEP3D.is_dir(),
    reason="data/artifacts/step3d 运行时产物不在本机 (.gitignore, 公开克隆不含)")


@_ARTIFACTS_SKIP
def test_drawings_list_rows_have_mesh_flag():
    r = client.get("/v1/drawings", params={"page_size": 100})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 2
    for it in body["items"]:
        assert "has_mesh" in it and "customer" in it and "context_id" in it
    # q 现在也搜 SHA
    hit = client.get("/v1/drawings", params={"q": GOOD.split("_", 2)[2]}).json()
    # BUG-2 修复后同内容 (sha256_16) 折叠为代表行: GOOD 要么是代表, 要么在代表行的 duplicate_ids 中
    assert any(i["id"] == GOOD or GOOD in i["duplicate_ids"] for i in hit["items"])


@_ARTIFACTS_SKIP
def test_mesh_build_and_reuse():
    r = client.get(f"/v1/drawings/{GOOD}/mesh")
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["ok"] is True and m["tri_count"] > 0 and m["vertex_count"] > 0
    pos = struct.unpack(f'<{m["vertex_count"] * 3}f', base64.b64decode(m["positions_b64"]))
    idx = struct.unpack(f'<{m["tri_count"] * 3}I', base64.b64decode(m["indices_b64"]))
    assert max(idx) == m["vertex_count"] - 1          # 0-based 严格对齐
    xs = pos[0::3]
    assert min(xs) < 0 < max(xs)                      # 法兰关于原点对称 (bbox ±40)
    # 二次请求命中缓存
    m2 = client.get(f"/v1/drawings/{GOOD}/mesh").json()
    assert m2["tri_count"] == m["tri_count"] and m2["generated_at"] == m["generated_at"]


@_ARTIFACTS_SKIP
def test_mesh_broken_step_degrades():
    r = client.get(f"/v1/drawings/{BAD}/mesh")
    assert r.status_code == 400
    assert r.json()["detail"]["ok"] is False and r.json()["detail"]["reason"]


def test_iso_step_magic_sniff(tmp_path):
    from services.step_mesh import _looks_like_iso_step
    ok = tmp_path / "ok.step"
    ok.write_text("ISO-10303-21;\n", encoding="ascii")
    pad = tmp_path / "pad.step"
    pad.write_bytes(b"\n\n\xef\xbb\xbf ISO-10303-21;")   # 前导空白 + BOM 仍放行
    bogus = tmp_path / "bogus.step"
    bogus.write_bytes(b"V\0\0\0 J\0\0\0 J\0\0\0 FE FF FF FF" + b"\x00" * 32)
    assert _looks_like_iso_step(str(ok))
    assert _looks_like_iso_step(str(pad))
    assert not _looks_like_iso_step(str(bogus))


def test_mesh_not_found():
    assert client.get("/v1/drawings/ORD-NOPE/mesh").status_code == 404
    assert client.get("/v1/drawings/..%2Fescape/mesh").status_code == 404
