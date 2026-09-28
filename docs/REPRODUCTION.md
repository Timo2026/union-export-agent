# REPRODUCTION.md — 从零复刻指南（DGX Spark / GB10）

> 完整可执行版见 `docs/deploy.ipynb`（15 cells）。本页为步骤总览 + 实测坑位。
> 全部步骤来自 2026-09 节点真实部署路径（12+ 轮巡检验证）。

## 0. 前置
- 一台 DGX Spark / GB10 主机（CUDA 13.0 · 驱动 580+）· conda · SSH
- NVFP4 模型已放 `~/nvidia/hf-cache/hub/`（Omni-30B-A3B-Reasoning / Embed-1B；权重不入库，见 models/MODELS.md）

## 1. 环境（实测坑 #1-#3）
```bash
git clone <repo> && cd union-export-agent
conda env create -f env/nemotron.yml        # vLLM 推理环境
conda env create -f env/occ.yml             # cadquery/OCP 几何环境
# 坑#1 pypi.org 受阻 → 全程 -i https://pypi.tuna.tsinghua.edu.cn/simple
# 坑#2 无 passwordless sudo → 全用户级 conda，禁 docker（NIM 走 vLLM 进程级替代）
# 坑#3 conda ToS 门禁 → conda tos accept 后再装包
```

## 2. 模型服务（实测坑 #4：30B 与 Omni 同驻 crash-loop）
```bash
bash models/fetch_and_launch.sh    # 起 vLLM: Omni:8002 / Embed:8011 / Qwen:8902
# ⚠️ Omni gpu-mem-util 0.55 实占 66GB；勿与 30B 文本档同驻（22 次重启的教训）
```

## 3. 内核 + 编排 + UI
```bash
bash ops/node_services.sh start     # Timo:7862 + livekernel:8888 + webui-dist（幂等）
curl -s http://127.0.0.1:8888/health
# 期望: status=ok · engine=live:cnc-ai-brain:7862 · multimodal=live:127.0.0.1:8002
```

## 4. 一键自检
```bash
bash scripts/verify_replica.sh
# 4 项判据: 服务健康 / 黄金链报价非空 / verify 状态返回 / openshell viol=0
```

## 5. 回归
```bash
pytest -m "not node_env"   # 期望 892 passed / 0 failed / 6 skipped
```

## 部署坑速查（均有测试或配置锁定）
| # | 坑 | 解法 |
|---|---|---|
| 4 | 30B+Omni 同驻 crash-loop | v2 拍板：Omni 统一四角色 |
| 5 | SSH banner 抖动 | retry 循环 + banner_timeout=40 |
| 6 | Python 版本偏差（3.12 vs 3.11） | 部署用 occ env 3.11 |
| 7 | 服务在 pts 前台（断开即挂） | node_services.sh tmux 编排 |
| 8 | Windows GBK 编码崩 | UTF-8 wrapper（核心链标准库优先的原因之一） |
