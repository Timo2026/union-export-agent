#!/usr/bin/env bash
# fetch_and_launch.sh — 拉起三实例 vLLM（权重不入库, 从 ~/nvidia/hf-cache 挂载）
set -euo pipefail
PY=${PY:-$HOME/miniconda3/envs/nemotron/bin/python}
HF=${HF:-$HOME/nvidia/hf-cache/hub}
# ⚠️ 坑#4: Omni(0.55 util, 实占66GB) 勿与 30B 文本档同驻 — 会 crash-loop
tmux new-session -d -s omni "$PY -m vllm.entrypoints.openai.api_server \
  --model $HF/models--nvidia--Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4/files \
  --served-model-name nemotron-omni-30b-a3b --reasoning-parser nemotron_v3 \
  --max-model-len 262144 --max-num-batched-tokens 16384 --max-num-seqs 32 \
  --limit-mm-per-prompt '{\"video\":1,\"image\":1,\"audio\":1}' --gpu-memory-utilization 0.55 \
  --enable-prefix-caching --enable-auto-tool-choice --tool-call-parser qwen3_coder \
  --host 127.0.0.1 --port 8002 --trust-remote-code"
tmux new-session -d -s embed "$PY -m vllm.entrypoints.openai.api_server \
  --model $HF/models--nvidia--Nemotron-3-Embed-1B-NVFP4/files \
  --served-model-name nemotron-embed-1b --runner pooling --convert embed \
  --max-model-len 8192 --max-num-seqs 64 --gpu-memory-utilization 0.15 \
  --host 127.0.0.1 --port 8011 --trust-remote-code"
echo "omni :8002 / embed :8011 launched (tmux ls 查看; Qwen3-0.6B fallback 见 ops/node_services.sh)"
