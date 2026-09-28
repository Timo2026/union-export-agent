# NVIDIA 全栈证据包说明

将节点探测与实跑结果放入本目录（`docs/evidence/spark/nvidia/`）。

## 必填文件

| 文件 | 来源 |
|------|------|
| `00-gates.txt` | 节点执行 `bash deploy/spark/probe_nvidia_gates.sh` |
| `01-nvidia-smi.txt` | `nvidia-smi` |
| `02-torch-cuda-probe.log` | torch CUDA matmul 日志 |
| `03-nim-or-vllm-health.txt` | `curl :8000/v1/models` 或 `:9000/v1/models` |
| `04-embed-nemotron-embed.log` | Nemotron-3-Embed-1B 调用或 blocked 原因（nv-embedqa 已否决） |
| `05-llm-nvidia-model.log` | NIM/vLLM chat 一次 |
| `06-nemo-guardrails.txt` | `pip show nemoguardrails` + 用例 |
| `07-asr-ocr-status.md` | ASR 专档 streaming-0.6b / FunASR 回退状态；OCR 后端 |
| `08-golden-chain-price-sha256.json` | local vs nvidia 端点价格一致 |
| `09-models-yaml-diff.md` | 切换前后 endpoint diff |
| `10-backend-nvidia-claim-level.md` | 口播等级 N0–N5 自评 |

## 口播等级（禁止越级）

- **N0** 驱动/CUDA 为 NVIDIA  
- **N1** GPU 上推理（torch/vLLM）  
- **N2** ≥1 个 NIM/NGC/NeMo 组件实跑  
- **N3** LLM+Embed（+ASR）NVIDIA 后端且 Agent 在用  
- **N4** 黄金链 + NeMo 护栏 + 价格等价  
- **N5** GPU 可观测 + 提交包齐  

## 禁止

- 写入节点密码、`NGC_API_KEY` 明文、邮箱授权码  
- 未实跑却勾选 N2+  
- 宣称 Parakeet 在 Blackwell 自托管成功（除非节点日志证明）  
