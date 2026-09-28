# MODELS.md — 模型清单（权重不入库，仅清单+启动）

| 模型 | 格式 | 磁盘 | 端口 | 用途 |
|---|---|---|---|---|
| Nemotron-3-Nano-Omni-30B-A3B-Reasoning | NVFP4 | 21GB | :8002 | LLM/VLM/OCR/ASR 统一 |
| Nemotron-3-Embed-1B | NVFP4 | ~1GB | :8011 | RAG 双塔检索 |
| Qwen3-0.6B | bf16 | ~1.2GB | :8902 | Omni 离线 fallback |
| NVIDIA-Nemotron-3-Nano-30B-A3B（可选） | NVFP4 | 19GB | 不驻留 | 勿与 Omni 同驻（坑#4） |

拉取：HuggingFace 离线缓存挂载（`HF_HUB_OFFLINE=1`），置于 `~/nvidia/hf-cache/hub/`。启动见 fetch_and_launch.sh。
