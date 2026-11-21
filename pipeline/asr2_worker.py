#!/usr/bin/env python3
"""第二个听写模型（2026-11-15 加）：常驻的小进程，载入阿里开源的 SenseVoiceSmall、Paraformer-zh 两个听写模型，
一段一段听配音里截出来的几秒，把听到的字交回去。由 pipeline/tts_qc.py 的 confirm() 启动和使用，不单独跑。

为什么单独一个进程、单独一个环境：这两个模型要 funasr（和它带的一串依赖），和项目环境（~/.venvs/frontier-daily）
装在一起容易互相顶掉版本；分开装（云端 ~/.venvs/fd-asr2），配音程序只在要复核时起这个进程，整期只载入一次模型。

怎么说话（每行一个 JSON）：
    启动：python asr2_worker.py --models <模型目录>
          模型目录下要有 SenseVoiceSmall/、paraformer-zh/ 两个子目录（Hugging Face 上 FunAudioLLM/SenseVoiceSmall、
          funasr/paraformer-zh 的文件原样下载进去，见 .github/workflows/frontier-daily.yml"装第二个听写模型"）。
    载入完先打一行：{"ready": true, "载入秒": 41.2, "模型": {"SenseVoice": "...", "Paraformer": "..."}}
                  载入失败：{"ready": false, "错误": "..."}，然后退出。
    之后每读进一行 {"id": 任意, "wav": 音频路径, "start": 起秒, "end": 止秒}，截出那一段（16 kHz 单声道），
    两个模型各听一遍，打一行 {"id": 同上, "SenseVoice": "听到的字", "Paraformer": "听到的字", "秒": 用时}；
    某个模型出错就写 {"id", "错误": "..."}（另一个照样给）。读到文件结束就退出。
不联网（HF_HUB_OFFLINE=1、disable_update），不读任何密钥。设置照 11-13 实验（听写模型实验_1113/run_funasr.py）：
SenseVoice language=zh、use_itn=True（数字写成阿拉伯数字）；Paraformer 默认；截出来的都是十几秒以内的短段，不用断句模型。
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("MODELSCOPE_OFFLINE", "1")


# 和调用方说话只走这一份（原来的标准输出）；funasr 载入时自己往标准输出打的字（"funasr version: …"）改到错误输出去
PROTO = os.fdopen(os.dup(1), "w", encoding="utf-8")
os.dup2(2, 1)
sys.stdout = sys.stderr


def say(obj):
    PROTO.write(json.dumps(obj, ensure_ascii=False) + "\n")
    PROTO.flush()


def cut(wav, start, end, out):
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{max(0.0, start):.3f}", "-t",
                        f"{max(0.1, end - start):.3f}", "-i", str(wav), "-ac", "1", "-ar", "16000", str(out)],
                       capture_output=True, text=True)
    if r.returncode or not Path(out).exists():
        raise RuntimeError("截不出这一段：" + (r.stderr or "")[-200:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True)
    a = ap.parse_args()
    root = Path(a.models).expanduser()
    t0 = time.time()
    try:
        import logging
        logging.disable(logging.WARNING)
        from funasr import AutoModel
        from funasr.utils.postprocess_utils import rich_transcription_postprocess
        common = dict(device="cpu", disable_update=True, disable_pbar=True, disable_log=True)
        models = {}
        for name, sub in (("SenseVoice", "SenseVoiceSmall"), ("Paraformer", "paraformer-zh")):
            d = root / sub
            if not (d / "model.pt").exists():
                raise FileNotFoundError(f"{d} 里没有 model.pt")
            models[name] = AutoModel(model=str(d), **common)
    except Exception as e:  # noqa: BLE001  载不了就告诉调用方，调用方照旧不复核
        say({"ready": False, "错误": f"{type(e).__name__}: {e}"[:400]})
        return 1
    say({"ready": True, "载入秒": round(time.time() - t0, 1), "模型": {"SenseVoice": "SenseVoiceSmall", "Paraformer": "paraformer-zh"}})
    tmp = Path(tempfile.mkdtemp(prefix="fd_asr2_"))
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
        except ValueError:
            continue
        out = {"id": job.get("id")}
        t = time.time()
        clip = tmp / "clip.wav"
        try:
            cut(job["wav"], float(job["start"]), float(job["end"]), clip)
        except Exception as e:  # noqa: BLE001
            out["错误"] = f"{type(e).__name__}: {e}"[:300]
            say(out)
            continue
        errs = []
        for name, m in models.items():
            try:
                if name == "SenseVoice":
                    res = m.generate(input=str(clip), language="zh", use_itn=True, batch_size_s=60)
                    out[name] = "".join(rich_transcription_postprocess(r.get("text", "")) for r in res)
                else:
                    res = m.generate(input=str(clip), batch_size_s=60)
                    out[name] = "".join(r.get("text", "") for r in res)
            except Exception as e:  # noqa: BLE001
                errs.append(f"{name} {type(e).__name__}: {e}"[:200])
        if errs:
            out["错误"] = "；".join(errs)
        out["秒"] = round(time.time() - t, 2)
        say(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
