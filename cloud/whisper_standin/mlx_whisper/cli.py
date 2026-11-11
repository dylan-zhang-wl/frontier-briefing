"""mlx_whisper 的"替身"：命令名、包名、参数、输出的 json 和 mlx-whisper 一样，里面换成 faster-whisper（Linux 能跑）。

为什么要替身：mini 上的转写用 mlx-whisper，只能在苹果芯片上跑；GitHub 的 Ubuntu 机器上跑不了。
程序（pipeline/tts_qc.py、site/tools/video_align.py）用两种方式调它，替身两种都接得住：
  1. 当命令行：  mlx_whisper <音频> --model mlx-community/whisper-large-v3-turbo --language zh
                 --condition-on-previous-text False --output-format json --output-dir D --output-name N
                 [--word-timestamps True] [--initial-prompt …] --verbose False
  2. 同一环境的 python 里：  from mlx_whisper import cli; sys.argv = [...]; cli.main()  （一次进程逐条转多段，模型只载入一次）
输出：<output-dir>/<output-name 或音频名>.json，键和 mlx-whisper 一样：
  {"text": 全文, "segments": [{"id","seek","start","end","text","tokens","temperature","avg_logprob",
   "compression_ratio","no_speech_prob", "words": [{"word","start","end","probability"}]（只在 --word-timestamps True 时有）}],
   "language": "zh"}
和 mlx-whisper 一样：某个音频转失败时打印报错、跳过，进程照常退出（调用方看输出文件在不在）。

解码设置照 mlx-whisper 命令行的默认：温度只用 0（不升温重试）、不做 beam search（贪心，beam_size=1）。
可用环境变量改（没设时就是上面这样）：
  FD_FW_MODEL      直接指定 faster-whisper 模型（名字或本地目录），不走下面的对照表
  FD_FW_LOCAL      放本地模型的目录：对照出来的仓库名（如 mobiuslabsgmbh/faster-whisper-large-v3-turbo）取最后一段，
                   这个目录下有同名子目录、里面有 model.bin，就直接用它（云端这样存缓存：Hugging Face 缓存里大文件是
                   放在外面共用目录的链接，单存模型那一层会只存下链接）
  FD_FW_COMPUTE    计算精度，默认 int8（CPU 上最快）
  FD_FW_THREADS    CPU 线程数，默认 0（由程序自己定）
  FD_FW_BEAM       beam 宽度，默认 1
模型要事先下载进 Hugging Face 缓存：调用方都设了 HF_HUB_OFFLINE=1，替身自己不联网下载。
"""
import argparse
import json
import os
import pathlib
import sys
import time
import traceback

# mlx 的模型名 → faster-whisper（CTranslate2 格式）的模型。
# large-v3-turbo 用的是 faster-whisper 自己的对照表里 "turbo"／"large-v3-turbo" 指向的那个仓库（faster_whisper/utils.py）。
MODEL_MAP = {
    "mlx-community/whisper-large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    "mlx-community/whisper-medium-mlx-4bit": "Systran/faster-whisper-medium",
    "mlx-community/whisper-medium-mlx": "Systran/faster-whisper-medium",
    "mlx-community/whisper-small-mlx": "Systran/faster-whisper-small",
    "mlx-community/whisper-base-mlx-q4": "Systran/faster-whisper-base",
    "mlx-community/whisper-tiny": "Systran/faster-whisper-tiny",
}
LANG_NAMES = {"chinese": "zh", "mandarin": "zh", "english": "en", "japanese": "ja"}

_MODELS = {}   # 同一进程里多次 main() 共用一个模型（tts_qc.transcribe_many 就是这样调的）


def _str2bool(s):
    v = {"True": True, "False": False}
    if s not in v:
        raise ValueError(f"Expected one of {set(v)}, got {s}")
    return v[s]


def _optional_float(s):
    return None if s == "None" else float(s)


def _optional_int(s):
    return None if s == "None" else int(s)


def build_parser():
    p = argparse.ArgumentParser(prog="mlx_whisper", description="mlx_whisper 替身（faster-whisper）")
    p.add_argument("audio", nargs="+")
    p.add_argument("--model", default="mlx-community/whisper-tiny")
    p.add_argument("--output-name", default=None)
    p.add_argument("--output-dir", "-o", default=".")
    p.add_argument("--output-format", "-f", default="txt", choices=["txt", "vtt", "srt", "tsv", "json", "all"])
    p.add_argument("--verbose", type=_str2bool, default=True)
    p.add_argument("--task", default="transcribe", choices=["transcribe", "translate"])
    p.add_argument("--language", default=None)
    p.add_argument("--temperature", type=float, default=0)
    p.add_argument("--best-of", type=_optional_int, default=5)
    p.add_argument("--patience", type=float, default=None)
    p.add_argument("--length-penalty", type=float, default=None)
    p.add_argument("--suppress-tokens", default="-1")
    p.add_argument("--initial-prompt", default=None)
    p.add_argument("--condition-on-previous-text", type=_str2bool, default=True)
    p.add_argument("--fp16", type=_str2bool, default=True)            # 接受但不用（CPU 上精度由 FD_FW_COMPUTE 定）
    p.add_argument("--compression-ratio-threshold", type=_optional_float, default=2.4)
    p.add_argument("--logprob-threshold", type=_optional_float, default=-1.0)
    p.add_argument("--no-speech-threshold", type=_optional_float, default=0.6)
    p.add_argument("--word-timestamps", type=_str2bool, default=False)
    p.add_argument("--prepend-punctuations", default="\"'“¿([{-")
    p.add_argument("--append-punctuations", default="\"'.。,，!！?？:：”)]}、")
    p.add_argument("--highlight-words", type=_str2bool, default=False)     # 只影响 srt/vtt，替身不写这两种
    p.add_argument("--max-line-width", type=int, default=None)
    p.add_argument("--max-line-count", type=int, default=None)
    p.add_argument("--max-words-per-line", type=int, default=None)
    p.add_argument("--hallucination-silence-threshold", type=_optional_float, default=None)
    p.add_argument("--clip-timestamps", default="0")
    return p


def resolve_model(name):
    if os.environ.get("FD_FW_MODEL"):
        return os.environ["FD_FW_MODEL"]
    if name in MODEL_MAP:
        return MODEL_MAP[name]
    if name.startswith("mlx-community/whisper-"):        # 别的 mlx 名字：去掉前后缀，交给 faster-whisper 的简称（tiny、small、large-v3…）
        short = name.split("whisper-", 1)[1]
        for suf in ("-mlx-4bit", "-mlx-q4", "-mlx-8bit", "-mlx"):
            short = short.removesuffix(suf)
        return short
    return name                                          # 已经是 faster-whisper 能认的名字或本地目录


def local_copy(key):
    root = os.environ.get("FD_FW_LOCAL")
    if root and "/" in key:
        d = os.path.join(os.path.expanduser(root), key.rsplit("/", 1)[1])
        if os.path.isfile(os.path.join(d, "model.bin")):
            return d
    return key


def get_model(name):
    key = local_copy(resolve_model(name))
    if key not in _MODELS:
        from faster_whisper import WhisperModel
        _MODELS[key] = WhisperModel(key, device="cpu",
                                    compute_type=os.environ.get("FD_FW_COMPUTE", "int8"),
                                    cpu_threads=int(os.environ.get("FD_FW_THREADS", "0")))
    return _MODELS[key]


def transcribe(audio, model_name, args):
    model = get_model(model_name)
    lang = args["language"]
    if lang and lang.lower() in LANG_NAMES:
        lang = LANG_NAMES[lang.lower()]
    clip = args["clip_timestamps"]
    kw = dict(
        language=lang,
        task=args["task"],
        beam_size=int(os.environ.get("FD_FW_BEAM", "1")),
        best_of=args["best_of"] or 5,
        patience=args["patience"] or 1,
        length_penalty=args["length_penalty"] if args["length_penalty"] is not None else 1,
        temperature=args["temperature"],
        compression_ratio_threshold=args["compression_ratio_threshold"],
        log_prob_threshold=args["logprob_threshold"],
        no_speech_threshold=args["no_speech_threshold"],
        condition_on_previous_text=args["condition_on_previous_text"],
        initial_prompt=args["initial_prompt"],
        suppress_tokens=[int(t) for t in args["suppress_tokens"].split(",")] if args["suppress_tokens"] else None,
        word_timestamps=args["word_timestamps"],
        prepend_punctuations=args["prepend_punctuations"],
        append_punctuations=args["append_punctuations"],
        clip_timestamps=clip if isinstance(clip, str) else "0",
        hallucination_silence_threshold=args["hallucination_silence_threshold"],
    )
    segs, info = model.transcribe(audio, **kw)
    out = []
    for s in segs:                       # 生成器，要一直取完才算转完
        d = {"id": s.id, "seek": s.seek, "start": s.start, "end": s.end, "text": s.text,
             "tokens": list(s.tokens), "temperature": s.temperature, "avg_logprob": s.avg_logprob,
             "compression_ratio": s.compression_ratio, "no_speech_prob": s.no_speech_prob}
        if s.words is not None:
            d["words"] = [{"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                          for w in s.words]
        out.append(d)
        if args["verbose"]:
            print(f"[{s.start:.2f} --> {s.end:.2f}] {s.text}", flush=True)
    # mlx-whisper 的 text 是全部 token 一起解码，中文段与段之间不加空格；这里照样直接接起来
    return {"text": "".join(d["text"] for d in out), "segments": out, "language": info.language}


def write(result, output_dir, name, fmt):
    os.makedirs(output_dir, exist_ok=True)
    fmts = ["txt", "json"] if fmt == "all" else [fmt]
    for f in fmts:
        path = os.path.join(output_dir, f"{name}.{f}")
        with open(path, "w", encoding="utf-8") as fh:
            if f == "json":
                json.dump(result, fh, ensure_ascii=False)
            elif f == "txt":
                for s in result["segments"]:
                    print(s["text"].strip(), file=fh)
            else:
                raise ValueError(f"替身只会写 json、txt，不会写 {f}")


def main():
    parser = build_parser()
    args = vars(parser.parse_args())
    if args["verbose"] is True:
        print(f"Args: {args}")
    model_name = args.pop("model")
    output_dir = args.pop("output_dir")
    output_format = args.pop("output_format")
    output_name = args.pop("output_name")
    if not args["word_timestamps"]:
        for k in ("highlight_words", "max_line_count", "max_line_width", "max_words_per_line"):
            if args[k]:
                parser.error(f"--{k.replace('_', '-')} requires --word-timestamps True")
    os.makedirs(output_dir, exist_ok=True)
    for audio_obj in args.pop("audio"):
        name = output_name or pathlib.Path(audio_obj).stem
        try:
            t0 = time.time()
            result = transcribe(audio_obj, model_name, args)
            write(result, output_dir, name, output_format)
            if os.environ.get("FD_FW_TIMING"):
                print(f"[mlx_whisper 替身] {audio_obj} 用时 {time.time() - t0:.1f} 秒（模型 {local_copy(resolve_model(model_name))}）",
                      file=sys.stderr)
        except Exception as e:           # 和 mlx-whisper 一样：报错、跳过这一个，不让整个进程退出
            traceback.print_exc()
            print(f"Skipping {audio_obj} due to {type(e).__name__}: {str(e)}")


if __name__ == "__main__":
    main()
