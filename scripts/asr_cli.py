#!/home/Developer/miniconda3/envs/vidproc/bin/python
"""asr_cli.py — 本地中文 ASR CLI (faster-whisper), 供 FunASRAdapter cli 模式调用.

为什么存在 (节点实测, 2026-09-25):
  Omni 的 input_audio 返回的是「英文音频场景描述」(audio caption), 不是中文转写。
  TIMO 38.6s 真实中文语音 → "In the Tan Sui Xia, the mini can be a high scale ..."。
  同时 occ 解释器 (livekernel 的运行环境) 内无任何 ASR 引擎:
    faster_whisper / funasr / whisper / openai_whisper 全部 ModuleNotFoundError
  → 进程内装不了, 唯一正解是外部子进程走独立解释器。

调用契约 (FunASRAdapter._transcribe_cli):
    asr_cli.py <音频路径>
    stdout = 转写文本 (stdout 只允许出现转写文本, 否则上游取错结果)
    exit 0 = 成功; 非 0 = 明确失败 (上游显式降级 MOCK, 绝不冒充成功)

退出码:
    0 成功        2 用法错误 / 文件不存在   3 依赖缺失
    4 推理失败    5 空转写
"""
from __future__ import annotations

import os
import sys

# 抑制 HF/tokenizers 噪声, 保证 stdout 只有转写文本
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def main() -> int:
    media = sys.argv[1] if len(sys.argv) > 1 else ""
    if not media or not os.path.isfile(media):
        sys.stderr.write(f"usage: {os.path.basename(sys.argv[0])} <audio-file>\n")
        return 2

    model_size = os.environ.get("LIVEKERNEL_ASR_MODEL", "small")

    # 2026-09-25 静默挂死根因: WhisperModel() 首次实例化会向 huggingface.co
    # 探一次 revision, 本机直连必超时 → 进程卡 2 分钟只烧 1 秒 CPU、20 线程全在
    # futex_wait、无任何输出 (我一度误判为模型损坏)。模型本体早已在缓存里。
    # 已缓存则强制离线; 未缓存才允许下载, 但仍走国内镜像并禁 xet
    # (huggingface 直连超时 + xet 握手必超时, 见 MEMORY.md)。
    cached = os.path.isdir(
        os.path.join(
            os.path.expanduser("~/.cache/huggingface/hub"),
            f"models--Systran--faster-whisper-{model_size}",
        )
    )
    os.environ.setdefault("HF_HUB_OFFLINE", "1" if cached else "0")
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    if os.environ.get("HF_HUB_OFFLINE") == "1":
        sys.stderr.write(f"asr_cli: model '{model_size}' cached — HF_HUB_OFFLINE=1\n")
    # 语种默认 auto-detect，不要再硬编码 zh。
    # 2026-09-25 实测教训: 32s 英文语音被强塞进中文模式 → 只吐出
    # "NVIDIA INTERN!NVIDIA INTERN!" (29 字节垃圾)，而 auto-detect
    # 得到 368 字节完整英文转写 (lang=en, 置信度 0.9749)。
    # 固定语种的需求通过显式设 LIVEKERNEL_ASR_LANG=en/zh/... 实现。
    lang_env = os.environ.get("LIVEKERNEL_ASR_LANG", "auto").strip()
    lang = None if lang_env.lower() in ("auto", "") else lang_env

    try:
        from faster_whisper import WhisperModel
    except Exception as exc:                      # 环境缺依赖 → 明确报错
        sys.stderr.write(f"asr_cli: faster_whisper import failed: {exc!r}\n")
        return 3

    try:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, info = model.transcribe(
            media,
            language=lang,
            beam_size=5,
            # 轻录音必须关 VAD: -30dBFS 级语音会被整段过滤成 0 字 → 假阴性
            # ("音频无语音"的错误结论就是这么来的)
            vad_filter=False,
            without_timestamps=True,
        )
        # 语种落到 stderr 便于审计; stdout 只允许转写文本
        sys.stderr.write(
            f"asr_cli: lang={info.language} prob={info.language_probability:.3f} "
            f"(requested={'auto' if lang is None else lang})\n"
        )
        text = "".join(seg.text for seg in segments).strip()
    except Exception as exc:
        sys.stderr.write(f"asr_cli: transcribe failed: {exc!r}\n")
        return 4

    if not text:
        sys.stderr.write("asr_cli: empty transcript\n")
        return 5

    sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
