"""step_mesh.py — STEP → 三角网格 (v7.0 图纸真 3D).

损坏 STEP 会让 OCCT 在进程内段错误 (不可 try/except), 故三角化必须在子进程 worker
中执行 (同 _kernel_bridge 惯例; worker 必须收绝对路径)。

数据: data/meshes/{sha256_16}.json
  {ok, sha256_16, vertex_count, tri_count, bbox: {min:[x,y,z], max:[x,y,z]},
   deflection, positions_b64(Float32 x3), indices_b64(Uint32 x3), generated_at}

用法:
  库内: from services.step_mesh import get_or_build_mesh; get_or_build_mesh(abs_step_path)
  worker (内部): python -m services.step_mesh --worker <abs_step> <abs_out> [deflection]
"""
from __future__ import annotations

import base64
import hashlib
import json
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent
MESH_DIR = _ROOT / "data" / "meshes"
MAX_TRI = 600_000
WORKER_TIMEOUT_S = 180


def sha256_16(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def mesh_file_for(sha16: str) -> Path:
    return MESH_DIR / f"{sha16}.json"


# ---------------- worker (子进程, 触 OCP) ----------------

def looks_like_iso_step_head(head: bytes) -> bool:
    """ISO-10303-21 文本以 'ISO-10303-21;' 开头 (允许前导空白/BOM);
    二进制 CAD 文件误改名 .step 时据此给出可操作的诚实失败原因。"""
    text = (head or b"").decode("utf-8", "ignore").lstrip("\ufeff \t\r\n")
    return text.startswith("ISO-10303-21")


def _looks_like_iso_step(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(64)
    except OSError:
        return False
    return looks_like_iso_step_head(head)


def _worker(step_path: str, out_path: str, deflection: float) -> int:
    from OCP.STEPControl import STEPControl_Reader
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.Interface import Interface_Static
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    if not _looks_like_iso_step(step_path):
        raise RuntimeError("非 ISO-10303-21 STEP 文本 (疑似非 STEP 文件误改为 .step 后缀)")

    Interface_Static.SetCVal_s("write.step.unit", "MM")
    reader = STEPControl_Reader()
    if reader.ReadFile(step_path) != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise RuntimeError("STEP 解析失败 (文件损坏或格式非法)")
    reader.TransferRoots()
    shape = reader.OneShape()
    if shape.IsNull():
        raise RuntimeError("STEP 几何为空")

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    mn, mx = box.CornerMin(), box.CornerMax()
    bbox = {"min": [mn.X(), mn.Y(), mn.Z()], "max": [mx.X(), mx.Y(), mx.Z()]}
    diag = max(1e-6, ((mx.X() - mn.X()) ** 2 + (mx.Y() - mn.Y()) ** 2
                      + (mx.Z() - mn.Z()) ** 2) ** 0.5)
    if deflection <= 0:
        deflection = min(2.0, max(0.01, diag / 400))

    positions: list = []
    indices: list = []
    for trial in range(3):  # 面数超限则自动粗化重 mesh, 最多 3 档
        positions, indices = [], []
        BRepMesh_IncrementalMesh(shape, deflection, False, 0.6, True)
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            # 节点 OCP 7.9 无 Face_s 静态造型别名; 构造器造型两版本通用 (已双侧实测)
            face = TopoDS.Face(exp.Current())
            loc = TopLoc_Location()
            tri = BRep_Tool.Triangulation_s(face, loc, 0)
            if tri is not None:
                tr = loc.Transformation()
                # OCP 无 gp_Pnt 变换重载: 3x3 旋转 + 平移手动应用 (Value 行列 1-based)
                m11, m12, m13 = (tr.Value(1, c) for c in (1, 2, 3))
                m21, m22, m23 = (tr.Value(2, c) for c in (1, 2, 3))
                m31, m32, m33 = (tr.Value(3, c) for c in (1, 2, 3))
                tp = tr.TranslationPart()
                tx, ty, tz = tp.X(), tp.Y(), tp.Z()
                reverse = face.Orientation() == TopAbs_REVERSED
                base = len(positions) // 3
                n = tri.NbNodes()
                for i in range(1, n + 1):
                    p = tri.Node(i)
                    x, y, z = p.X(), p.Y(), p.Z()
                    positions.extend((m11 * x + m12 * y + m13 * z + tx,
                                      m21 * x + m22 * y + m23 * z + ty,
                                      m31 * x + m32 * y + m33 * z + tz))
                for i in range(1, tri.NbTriangles() + 1):
                    tv = tri.Triangle(i)
                    # OCCT 结点号 1-based → three.js 0-based
                    a, b, c = tv.Value(1) - 1, tv.Value(2) - 1, tv.Value(3) - 1
                    if reverse:
                        b, c = c, b
                    indices.extend((a + base, b + base, c + base))
            exp.Next()
        if len(indices) // 3 <= MAX_TRI:
            break
        deflection *= 4.0
    tri_count = len(indices) // 3
    if tri_count == 0:
        raise RuntimeError("无三角面 (可能非流形或空体)")

    pos_bytes = struct.pack(f"<{len(positions)}f", *positions)
    idx_bytes = struct.pack(f"<{len(indices)}I", *indices)
    out = {
        "ok": True, "bbox": bbox, "deflection": deflection,
        "vertex_count": len(positions) // 3, "tri_count": tri_count,
        "positions_b64": base64.b64encode(pos_bytes).decode(),
        "indices_b64": base64.b64encode(idx_bytes).decode(),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).with_suffix(".tmp").write_text(
        json.dumps(out), encoding="utf-8")
    Path(out_path).with_suffix(".tmp").replace(out_path)
    return 0


# ---------------- parent (服务进程内, 不触 OCP) ----------------

def build_mesh(step_abs_path: str, out_abs_path: str,
               deflection: float = 0.0) -> Dict[str, Any]:
    """子进程三角化; 任何失败 (含段错误) 返回 ok=False, 不崩服务。"""
    cmd = [sys.executable, "-m", "services.step_mesh", "--worker",
           step_abs_path, out_abs_path, str(deflection)]
    try:
        r = subprocess.run(cmd, cwd=str(_ROOT), capture_output=True, text=True,
                           timeout=WORKER_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": f"mesh timeout >{WORKER_TIMEOUT_S}s"}
    if r.returncode != 0 or not Path(out_abs_path).exists():
        reason = (r.stderr or r.stdout or f"worker exit {r.returncode}").strip()
        return {"ok": False, "reason": reason[-400:] or "worker crashed (segfault?)"}
    return json.loads(Path(out_abs_path).read_text(encoding="utf-8"))


def get_or_build_mesh(step_abs_path: str) -> Optional[Dict[str, Any]]:
    """按 sha16 命中缓存则直返; 否则构建。返回 None 表示文件不存在。"""
    p = Path(step_abs_path)
    if not p.is_file():
        return None
    sha16 = sha256_16(p)
    cache = mesh_file_for(sha16)
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    MESH_DIR.mkdir(parents=True, exist_ok=True)
    out = build_mesh(str(p.resolve()), str(cache.resolve()))
    if not out.get("ok"):
        cache.with_suffix(".json.err").write_text(
            json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return out
    out["sha256_16"] = sha16
    cache.write_text(json.dumps(out), encoding="utf-8")
    mesh_error_file = cache.with_suffix(".json.err")
    if mesh_error_file.exists():  # 曾经失败过又重建成功 → 清掉错误标记
        mesh_error_file.unlink()
    return out


def mesh_error_for(sha16: str) -> Optional[Dict[str, Any]]:
    f = MESH_DIR / f"{sha16}.json.err"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


if __name__ == "__main__" and "--worker" in sys.argv:
    _a = sys.argv[sys.argv.index("--worker") + 1:]
    try:
        sys.exit(_worker(_a[0], _a[1], float(_a[2]) if len(_a) > 2 else 0.0))
    except Exception as e:  # worker 内一切异常 → 非零退出 + stderr, 父进程降级
        print(f"mesh worker failed: {e!r}", file=sys.stderr)
        sys.exit(2)
