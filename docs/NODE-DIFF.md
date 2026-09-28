# NODE-DIFF — 本地开发机 ⇄ spark-388d 节点 对比报告

> 任务 #27 (A 阶段) 产物。采集时间 2026-09-21 07:35。
> 节点凭据仅本机 `deploy/` 脚本持有，永不入库；本报告不含任何密码/授权码。

## 1. 硬件 / 运行时对比

| 维度 | 本地开发机 (Windows) | 节点 spark-388d | 谁占优 |
|------|----------------------|------------------|--------|
| 架构 | AMD64 (x86_64) | **aarch64 (ARM64)** | 节点=GB10 目标架构 |
| GPU | 无 (torch `+cpu`, `cuda.is_available()=False`) | **NVIDIA GB10**, Driver 580.82.09, **CUDA 13.0** | **节点** |
| CPU 核数 | 32 | 20 | 本地 |
| 内存 | — | **121 GiB 统一内存** (87 GiB free) | **节点** |
| 磁盘 | — | 3.7 TB (1.5 TB avail, 58% used) | **节点** |
| OS | Windows 10/11 | Ubuntu 24.04.3 LTS, kernel `6.11.0-1014-nvidia` | 节点=生产 Linux |
| 系统 Python | 3.11.9 | 3.12.3 | 版本偏差 (见 §4) |
| torch | 2.14.0+cpu | **2.14.0+cu130 (CUDA True)** | **节点** |
| conda | 无 | conda 26.7.1, env `occ` | **节点** |
| OCC/CAD | 无原生 OCC | **env `occ`: cadquery 2.8.0 + numpy 2.4.6 + scipy 1.17.1** | **节点** |

## 2. 代码资产对比

| 维度 | 本地 | 节点 |
|------|------|------|
| livekernel 仓库 | ✅ 463 tracked files, 完整 agent 系统 | ❌ **无任何 union/livekernel 副本** (`find ~ -iname '*union*'` 空) |
| Skills | ✅ 33 个 skill 目录 | ❌ `~/nvidia-skills` **不存在**；仅 `skills-lock.json` (300B) |
| Web UI | ✅ 13 标签全接线 (webui/index.html) | ❌ 无 |
| 测试 | ✅ 752 pytest 全绿 | ❌ 无 |
| vLLM | ❌ 无 (CPU 机不需要) | ❌ **未安装** (`import vllm` 失败) |
| pip 镜像 | — | ❌ **未配置** `pip.conf` (pypi.org 在该网络受阻, 见 §4) |
| OCC STEP 冒烟产物 | ❌ 无 | ✅ `occ_smoke.py` + `occ_smoke_sample.step` (17 KB) + `occ-setup.log` (51 KB) |
| 其他节点目录 | — | `inference/`, `movieagent/`, `pydev/`, `.hermes/`, `.claude/` (非本项目) |

## 3. 优点 / 不足总结

**节点优点 (本地不可替代):**
- 真 GB10 GPU + CUDA 13.0 → 唯一能跑真实 GPU 推理 / 承载 NVIDIA 模型栈的环境。
- 121 GiB 统一内存 → 大模型驻留。
- aarch64 OCC/cadquery 环境已验证可跑 STEP B-rep 几何解析 (TimoAdapter 的 `CNC_BRAIN_PY` 落点)。
- 生产级 Ubuntu + nvidia 内核 → 部署真实性的证据来源。

**节点不足:**
- 从未部署过 livekernel agent 代码 → 系统未在 ARM 上验证过。
- 无 vLLM、无 pip 镜像 → NVIDIA 模型服务栈尚未落地。
- `~/nvidia-skills` 缺失 → skill staging 未同步。

**本地优点:**
- 完整 agent 代码库 + 33 skills + 752 测试 + 13 标签 UI，全端点接线。
- 确定性离线内核 (vendored) 无需 GPU 即可跑全链 → 正是铁律① (LLM 不产最终数字) 的体现。

**本地不足:**
- 无 CUDA GPU → 只能离线 vendored kernel + CPU 推理，无法做真模型服务。

## 4. 坑点 (部署前必读)

1. **Python 版本偏差**: 本地 3.11.9 vs 节点系统 3.12.3 / occ env。部署用 occ env (3.11+cadquery) 而非系统 python，避免 ABI 冲突。
2. **pypi.org 受阻**: 节点网络访问 pypi.org 慢/不通，**必须**走清华源 (`-i https://pypi.tuna.tsinghua.edu.cn/simple`)。节点当前**未配 pip.conf**，B1 部署时显式带 `-i`。
3. **无 passwordless sudo**: 全 pip 化 (用户级安装)，禁 docker daemon。
4. **conda ToS**: 新环境需 `conda tos accept` 后才能装包。
5. **SSH banner 抖动**: 连接需 retry 循环 (banner_timeout=40)，单次连接易失败。

## 5. 双方修复清单 (→ B 阶段执行)

| # | 侧 | 动作 | 任务 |
|---|-----|------|------|
| F1 | 节点 | 部署脱敏 livekernel 包 (whitelist, 无凭据/无 .sqlite3/无 deploy cred 脚本) | B1 (#28) |
| F2 | 节点 | 清华源 pip 装依赖；occ env 跑离线 pytest 子集 + demo scenario 冒烟 (无 GPU 路径) | B1 (#28) |
| F3 | 节点 | 验证 OCC env 经 `CNC_BRAIN_PY` 解析样例 STEP (复用已有 occ_smoke) | B1/B2 |
| F4 | 本地 | 拉回节点证据 (occ_smoke_sample.step / occ-setup.log / nvidia-smi / torch+CUDA 版本) → `data/node_evidence/` | B2 (#29) |
| F5 | 本地 | 无 GPU 是架构既定约束 → 文档化离线内核 fallback 为铁律①优点，非缺陷 | D1 (#32) |
| F6 | 本地 | 修两个既有缺陷: flywheel 杂散 `.sqlite3` 客户 + guardrails 中文注入放行 | B3 (#30) |
