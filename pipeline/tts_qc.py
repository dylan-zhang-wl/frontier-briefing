#!/usr/bin/env python3
"""对稿：本机 Whisper 把配好的音频转写回来，和原稿逐字比对。

只抓两类大问题——多念（转写里冒出原稿没有的一大段）和漏念（原稿有一大段没念）；
专名、同音字写错只算进字错率，不触发重录（Whisper 自己也常把英文专名拼错）。
后来补的几项（专名读音、数字单位、英文名漏念、11-15 的数字整数比对和第二个听写模型复核）见下面各节；
11-15 那两项挂在 fd_开关.json 的开关后面，关着时和以前一样。

比对前先把两边"拉到同一种写法"，避免把写法差异算成读错：
    · 繁体转简体（Whisper 偶尔输出繁体），全角转半角，英文转小写，去掉标点和空格；
    · 中文数字转阿拉伯数字："百分之六十五点二"→"65.2%"、"三百亿"→"300亿"、"二零二六"→"2026"。
      两边用同一套规则，所以"第一条""统一"之类被一起转成"第1条""统1"也不影响比对。
计数单位：一个汉字、一个英文单词、一个数字位各算一个。
另报一个"拼音错误率"：按拼音比、不计声调，同音字和多音字的另一读音都算对，
剩下的才是"听起来就不一样"的地方（多半是英文专名，或真的读错、漏读）。只作参考，不触发重录。

专名读音（2026-11-09 加）：pipeline/prompts/专名读音.yaml 列了几个名字的已知误读（Claude→cloud、Gurman→German、
黄仁勋→黄仁荀、拼音 Yao Shunyu→姚书怀……）。原稿这一块有这个名字、转写里多出了它的已知误读，就算"要重录"
（原因写"专名读音：……"），和多念、漏念一样自动重录一次；重录后还在，调用方在 qc.json 里写"专名读音（请你耳听）"。
清单读不了就不查这一项，照常对稿。转写模型自己也会把念对的名字写错，所以命中只说明"要人耳听"，不等于念错了。
清单里标了"只提醒: true"的名字（Claude，11-09 定）命中时不重录，只在结果的"专名读音"里记一笔（带"只提醒"），
调用方照样在 qc.json 那一块写"专名读音（请你耳听）"：转写模型几乎总把 Claude 写成 cloud，重录多半白花钱。

数字单位（2026-11-09 晚加，unit_losses）：11-09 视频"Anthropic 签下 34 亿美元的协议"转写成"34亿元"，少的正好是"美"，
美元变成了人民币；整块字错率只有 2.75%、最长少 1 个字，原来的线拦不住。现在原稿里紧跟在数字后面的单位或量级
（美元、欧元、英镑、日元、港元、人民币、元、美金……；万亿、亿、千万、万、千……；百分之或 %、个百分点、倍）
在转写里少了或换了，这一块就算"要重录"，原因写"数字单位少字：美（原稿 34亿美元，转写 34亿元）"，和多念、漏念同一套
自动重录一次；重录后还在，调用方在 qc.json 那一块写"数字单位（请你耳听）"。怎么判（只认单位字真的丢了或换了）：
    · 两边先照上面的归一化拉成同一种写法、逐字对齐，再看原稿每个"数字＋单位"对上的那段转写；
    · 同义的算对：美元＝美金、日元＝日圆、港元＝港币、人民币＝元＝元人民币、个百分点＝百分点、百分之＝%；
    · 量级写法不同但数值相同的算对："3.4万"转写成"34000"、"1.25万亿"转写成"12500亿"；
    · 单位字换成同音同调的字算对（"倍"写成"被"）：转写模型挑错字，不是没念出来；
    · 转写多出单位（原稿"34亿"、转写"34亿元"）不算，这条只管丢了、换了；数字本身念错（34 变 35）不归这条管。
吉瓦、年、月这类不在单位表里的不查（"吉瓦"常被转写成"级瓦"，查了只会误报）。

英文名漏念（2026-11-10 加，name_drops）：11-10 视频"发布了 Claude Fable 5.2"，Fable 整个没念（用户耳听确认），转写是"Cloud 5.2"；
少一个英文词只算一两个错字，专名读音清单也只认"念成了什么"，认不出"没念"。现在原稿里读音表（pipeline/prompts/读音表.yaml）
收录的英文名（写法、之后、也可写），同时满足这两条，这一块就算"要重录"，原因写"英文名漏念：……"，和多念、漏念同一套
自动重录一次；重录后还在，调用方在 qc.json 那一块写"英文名漏念（请你耳听）"：
    · 这一条转写里一次都没出现（压扁了比：只看字母数字、不分大小写、0 当 o，LingBot-Touch＝Lingbot Touch，GR00T＝GROOT），
      也没出现专名读音清单里它的已知误读（Claude 转写成 cloud 算念到了，念得对不对归专名读音那一项管）；
    · 逐字对齐里，有一处对上的转写英文字母不到原稿的一半、又没有汉字（整个词被吞了；转写成别的拼法如 Anthrobic、
      Sherly，或写成汉字音译如"奥特曼"，都不算）。
只照最初的说法（"一次都没出现"一条）会误报一大片：拿往期 qc.json（mini 试运行 10-31 至 11-09 各期，加云端 11-09、
11-10；不含带音效的）279 块、397 条转写试过，76 块（27%）命中，几乎都是转写拼错（Anthropic→Anthrobic、Shirley→Sherly、
Slator→Slayter……）；加上第二条以后只命中 11-10 视频 Fable 那一块（测试 test_tts_qc_drops.py）。
读音表读不了就不查这一项。
数字本身不同（11-10 播客"Claude Opus 5.5"念成"5.2"）11-10 没有并进来：评估过"原稿里的数字，转写里成了别的数"，
往期 279 块命中 12 块；能找回音频的三处（iOS 27.3→17.3、V4.1→4.0、432.1→432.01）两个转写模型都一致，单切也一样，
分不出是念错还是转写模型的偏好（iOS 17.3 是它认得的旧版本号），云端又只有一个转写模型，所以只记在报告里。

数字整数比对（2026-11-15 加，number_mismatches；fd_开关.json"对稿数字整数比对"，环境变量 FD_QC_NUMBERS 优先；没写按关）：
11-15 播客"一共一千零九页"念成"109 页"（用户耳听确认），逐字比只差"少掉 1 个 0"，第 8 轮字错率 0.064，到不了重录线。
现在原稿里的每个数（读法照上面归一化换成阿拉伯数字以后，"一千零九"＝1009、"三点八"＝3.8、"1万7500"＝17500）按整个数比：
对齐到的那段转写里没有同一个值，就算"数字不符"、要重录（最多重录 MISREAD_RETAKES＝2 次，调用方按这个数）；重录后还在，
调用方在 qc.json 那一块写"数字不符（请你耳听）"。怎么认"数"：两位以上、带小数点、带量级或单位、前面是"第"或英文型号、
后面跟量词（页、次、家、年……）的才算；单个"1"不跟量级单位的（一个、一家、一种）和"十分""十足"这类词不算。
数值一样、写法不同的算对（3.4万＝34000）；数字一样、只是量级不同的（1.25万亿→1.25万）不归这条管，归上面"数字单位"。
第二个听写模型开着时，"数字不符"先交给它复核（见下一节）：两个新模型都听成原稿那个数，就当转写听错、不重录
（11-15 视频"十六次"有一次转写成"是 6 次"）；新模型没装好、载入失败时照"数字不符"重录。

第二个听写模型复核（2026-11-15 加，confirm；fd_开关.json"对稿第二个听写模型"，环境变量 FD_QC_ASR2 优先；没写按关）：
方案和判法照 11-13 的本机实验（交接文件夹 听写模型实验_1113/实验报告.md）：阿里开源的 SenseVoiceSmall 和 Paraformer-zh。
    · 可疑处（suspects）：原稿和 Whisper 转写按不带声调的拼音比，对不上的每一处（同音字、多音字的另一读音不算）；
      带英文字母的不算（新模型听英文名不行，英文名照旧归"拿不准"，靠专名读音、英文名漏念两条）；只多出字、没少没换的不算；
      只差语气词（的、了、吗、啊……）的不算；数字由上面"数字不符"管，这里不重复。
    · 每一处按 Whisper 的分段时间截前后约 3 秒（至少 5 秒）交给两个新模型各听一遍；原稿那一段也转成不带声调的拼音，
      和新模型的转写对齐（两头多带几个字、两头对不上的不算），看可疑处那几个字新模型听到的是不是原稿。
    · 至少一个新模型也听得和原稿不一样 → "复核念错"，要重录（最多 MISREAD_RETAKES＝2 次），重录后还在调用方写
      "复核念错（请你耳听）"；两个新模型都听成原稿 → Whisper 听错，不重录，记在结果的"复核"里。
      新模型这一段对上的不到一半（音乐、截歪了）算没听清，不拿它作证；两个都没听清，这一处不重录、只记一笔。
    · 新模型在单独的进程里跑（asr2_worker.py，环境 FD_ASR2_PYTHON，模型目录 FD_ASR2_MODELS），整期只载入一次；
      没装、载入失败、出错，这一项照旧不查（可疑处只记一笔"没复核"），数字不符照上一节直接重录，配音不会因此停下。
      每段的结果按"音频＋起止秒"存进缓存（FD_ASR2_CACHE，默认 ~/.cache/frontier-daily/tts/asr2），重跑不再听。
两个开关都关着时，check() 的结果和加这两项以前一模一样，也不起新模型的进程。

11-16 回放补的三处（2026-11-16 加；都在上面两项的开关后面，开关关着时不起作用；用户 11-16 耳听是标准答案，
新旧对比见经验库第五部分第 87 件）：
    · 挨着英文名的中文差异拆出来复核（_split_latin）：可疑处是把只隔 1 个对上的字的差异并成一处挑的，并进来一个英文名，
      整处就按"英文名拿不准"跳过了。11-16 播客"LeCun、吴恩达"转写成"勒坤吴文达"，"恩→文"和 LeCun 只隔一个"吴"，
      用户耳听确认"吴恩达"念错，漏了。现在并起来的一处带英文字母时，按对上的字切开：带英文字母的那几截照旧跳过，
      其余只有中文的几截各自成一处；和英文直接挨着、中间没有对上的字的，仍跟着英文跳过（分不清是不是音译出来的字）。
    · 不在数字上下文里的"一"不当数字（qc_tokens、_yi_is_number）：归一化会把每个"一"都换成 1，11-16 播客"小艺"转写成"小一"，
      就成了"艺→1"，拼音对不上；两个新模型也写"小一"，判了念错（同一块另有真错，没多花钱）。现在这几项用的记号里，只有
      挨着别的数字字、前面是"第""百分之""分之"或英文型号、后面跟量词／量级／货币单位、"一到三年""一万一"这类里的"一"
      才换成 1（一千零九＝1009、第一、一个、一亿、三点一、十一月照旧），统一、唯一、一起、小一、之一照"一"这个字比。
      比数时转写里单独的"一"仍当 1（"第一"写成"低一"不算数字不符）；按拼音比的时候阿拉伯数字 1 也算 yi（_qc_pinyin_sets），
      原稿"一边说""一封信"留着"一"、转写写成"1边说""1份"，两边照样对得上（不加这一条，往期文字层会多出 6 处"一→1"）。
      顺带不再挑 Whisper 写成 1 的同音字（11-07"奕成"、11-10"意向"）。字错率那些老的几项照旧把每个"一"都换成 1。
    · 名字只差声调的也复核（load_tone_names、_tone_suspects）：专名读音清单和读音表"人名"里整个用汉字写的名字（黄仁勋、
      姚顺雨、特朗普、微软……），Whisper 写成不带声调一样、带声调不同的字（黄仁勋→黄仁荀，xūn→xún），整个名字算一处可疑处
      （复核记录里标"按声调比"）；新模型写的字要和原稿有同一个带声调的读音才算照原稿，至少一个新模型写的字声调不同就是
      "复核念错"、重录（最多 2 次）。为什么只管名字：声调是转写模型按上下文选字推出来的，普通词靠不住（11-13 实验"词元→次元"
      "扩大→扩达"三个模型都写错调）；常见人名有固定写法，模型写出别的调的字才有分量。往期证据（11-16 查本机成品、归档、试验里
      全部转写）：原稿有黄仁勋的 81 处，Whisper 写成别的调的只有 4 处——11-09 两处、11-16 一处用户耳听都说声调不对
      （11-16 那处两个新模型都写"寻"），11-12 一处（黄仁迅；SenseVoice 写"勋"、Paraformer 写"逊"，判念错）待核；
      写成"勋"的 77 处一处都不挑；其余名字没有出现过只差声调的写法。样本小，上线后照审片清单第 25 项对照耳听。
      专名读音清单原来那条（转写出黄仁荀、黄仁寻……就重录一次）不变，这条只是多一道：清单外的同音不同调的字（迅、训）也挑得出来，
      判念错时最多重录 2 次。11-09、11-16 两期重录一两次都没念好，光重录不够，配音写法另做试听（本机 本机资料/试验/读音试听_1116/）。
已知限制（2026-11-16 记，没改规矩）：两个新模型都听成原稿就当 Whisper 听错、不重录。11-16 播客 3:30"主干参数"，Whisper 写"主观"，
两个新模型都写"主干"，用户耳听确认念错，被放过了。现有证据定不出更好的规矩：同样是"Whisper 错、两个新模型都听成原稿"的，
11-11 播客"正式版→吧""千问→千万"两处、视频"算→孙"共 4 处，用户耳听都没念错；它们和"主干→主观"一样是声母相同、韵母不同，
凡能抓到"主干"的规矩（比如 Whisper 一错就重录，或者只认韵母不同）都会把这几处变成重录。回放用的又是网页上的混音版（带配乐），
正式对稿听的是纯人声，成品里没有纯人声，换成纯人声两个新模型会不会听出"主观"核不了。这一类只能靠审片和耳听兜底。

Whisper 设置（用户定）：mlx-community/whisper-large-v3-turbo，language=zh，
condition_on_previous_text=False（不拿上一句当提示，避免它自己陷入复读、把正常音频误判成多念）。
用 digital-human 的环境跑命令行，HF_HUB_OFFLINE=1 只用本机已下载的模型。
"""
import json
import os
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

import sys
sys.dont_write_bytecode = True

try:
    from opencc import OpenCC
    _T2S = OpenCC("t2s")
except Exception:          # 没装也能跑，只是繁体输出会被算成错字
    _T2S = None
try:                       # 拼音错误率用；没装就只报字错率
    from pypinyin import Style, pinyin as _pinyin
except Exception:
    _pinyin = None

# ============================ 可改区 ============================

WHISPER_BIN = Path(os.environ.get("FD_WHISPER_BIN") or Path.home() / ".venvs/digital-human/bin/mlx_whisper")   # FD_WHISPER_BIN：别的机器上转写命令的位置；没设时和原来一样
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"

RUN_LIMIT = 8          # 一处连续多出（或少掉）这么多个字/词，就算"大段"多念（漏念）
RUN_GAP = 2            # 两处差异之间只隔 ≤2 个对得上的字，合并成一处（防止被零星巧合切碎）
CER_LIMIT = 0.20       # 整块字错率超过两成，说明整体对不上
DURATION_RANGE = (0.5, 2.0)   # 实际时长 / 估计时长 超出这个范围也重录
OVERLONG_RATIO = 2.0          # 实际时长超过按字数估计的这么多倍，
OVERLONG_MIN_EXTRA_S = 30     # 而且至少多出这么多秒：当废条丢掉重录，不转写（11-14 加，见 overlong()）
NAMES = Path(__file__).resolve().parent / "prompts" / "专名读音.yaml"   # 专名读音清单（11-09 加）

# 数字整数比对、第二个听写模型（2026-11-15 加，见文件头"数字整数比对""第二个听写模型复核"）
MISREAD_RETAKES = 2           # 数字不符、复核判念错的块最多重录几次（多念漏念那些仍按调用方的 retakes，现在是 1）
ASR2_PAD_S = 3.0              # 可疑处前后各多截几秒给新模型听
ASR2_MIN_CLIP_S = 5.0         # 截出来的一段至少这么长（太短新模型听不出上下文）
ASR2_MARGIN = 8               # 和新模型的转写对齐时，原稿那一段前后各多带几个字（截的时间和字对不齐，多带的不算错）
ASR2_MIN_HEARD = 0.5          # 这一段原稿（汉字、数字）新模型对上不到一半，算它这次没听清，不拿它作证

# ==============================================================

CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000}
_NUM_CHARS = "零〇一二两三四五六七八九十百千"


def transcribe(wav_path, work_dir=None):
    """返回转写文本。work_dir 放 Whisper 的 json 输出（放缓存目录，别放 iCloud）。"""
    wav_path = Path(wav_path)
    work = Path(work_dir or tempfile.mkdtemp(prefix="fd_whisper_"))
    work.mkdir(parents=True, exist_ok=True)
    name = wav_path.stem + "_whisper"
    env = dict(os.environ, HF_HUB_OFFLINE="1")
    for k in ("MIMO_API_KEY", "GCP_ACCESS_TOKEN"):    # 子进程用不着密钥
        env.pop(k, None)
    cmd = [str(WHISPER_BIN), str(wav_path), "--model", WHISPER_MODEL, "--language", "zh",
           "--condition-on-previous-text", "False", "--output-format", "json",
           "--output-dir", str(work), "--output-name", name, "--verbose", "False"]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    out = work / f"{name}.json"
    if r.returncode or not out.exists():
        raise RuntimeError(f"Whisper 失败：{(r.stderr or r.stdout)[-400:]}")
    d = json.loads(out.read_text(encoding="utf-8"))
    return (d.get("text") or "").strip()


# 一次进程里逐条跑 mlx_whisper 自己的命令行入口（参数和 transcribe 完全一样），模型只载入一次。
# 不直接给命令行传多个文件：它的 cli.py 有个小毛病，多个文件时输出名一直沿用第一个文件的名字，会互相覆盖。
_MANY = """
import json, sys
from mlx_whisper import cli
jobs = json.loads(sys.stdin.read())
for wav, out_dir, name, model in jobs:
    sys.argv = ["mlx_whisper", wav, "--model", model, "--language", "zh",
                "--condition-on-previous-text", "False", "--output-format", "json",
                "--output-dir", out_dir, "--output-name", name, "--verbose", "False"]
    cli.main()
"""


def transcribe_many(items):
    """items：[(音频路径, 输出目录), …]。和逐条调 transcribe 结果一样（输出也叫 <音频名>_whisper.json），
    只是一次进程做完（对谈稿一集几十句，逐条调每句都要重新载入模型）。返回 {音频路径字符串: 转写文本}。"""
    items = [(Path(w), Path(d)) for w, d in items]
    if not items:
        return {}
    jobs = []
    for w, d in items:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{w.stem}_whisper.json").unlink(missing_ok=True)     # 免得把上次的旧结果当成这次的
        jobs.append([str(w), str(d), w.stem + "_whisper", WHISPER_MODEL])
    env = dict(os.environ, HF_HUB_OFFLINE="1")
    for k in ("MIMO_API_KEY", "GCP_ACCESS_TOKEN", "GEMINI_API_KEY"):    # 子进程用不着密钥
        env.pop(k, None)
    py = WHISPER_BIN.parent / "python"
    r = subprocess.run([str(py), "-c", _MANY], input=json.dumps(jobs), capture_output=True, text=True, env=env)
    out = {}
    for w, d in items:
        f = d / f"{w.stem}_whisper.json"
        if not f.exists():
            raise RuntimeError(f"Whisper 没转出 {w.name}：{(r.stderr or r.stdout)[-400:]}")
        out[str(w)] = (json.loads(f.read_text(encoding="utf-8")).get("text") or "").strip()
    return out


# ---------------------------------------------------------------- 归一化


def _cn_int(s):
    """不含万、亿的中文整数 → 阿拉伯数字串。只有数字字的（二零二六）逐位转；只有单位的不转。"""
    if all(c in CN_DIGITS for c in s):
        return "".join(str(CN_DIGITS[c]) for c in s)
    if not any(c in CN_DIGITS for c in s) and s != "十":
        return None
    total, num = 0, 0
    for c in s:
        if c in CN_DIGITS:
            num = CN_DIGITS[c]
        else:
            total += (num if num else 1) * CN_UNITS[c]
            num = 0
    return str(total + num)


def _convert_run(run):
    """一段连续的中文数字（可含"点"）→ 阿拉伯数字；转不了就原样返回。"""
    if "点" in run:
        a, b = run.split("点", 1)
        ia = _cn_int(a) if a else None
        if ia is not None and b and all(c in CN_DIGITS for c in b):
            return ia + "." + "".join(str(CN_DIGITS[c]) for c in b)
        return run
    v = _cn_int(run)
    return v if v is not None else run


_RUN_RE = re.compile(rf"[{_NUM_CHARS}]+(?:点[零〇一二两三四五六七八九]+)?")


def cn_numbers_to_arabic(s):
    s = re.sub(r"百分之([0-9]+(?:\.[0-9]+)?)", r"\1%", s)           # 百分之65.2
    s = re.sub(rf"百分之({_RUN_RE.pattern})", lambda m: _convert_run(m.group(1)) + "%", s)
    return _RUN_RE.sub(lambda m: _convert_run(m.group(0)), s)


def normalize(text):
    s = unicodedata.normalize("NFKC", text)
    if _T2S:
        s = _T2S.convert(s)
    s = s.lower()
    s = re.sub(r"<[^>]*>", " ", s)                  # 行内标记（<short pause> 等）不算台词
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)   # 1,000 → 1000
    s = cn_numbers_to_arabic(s)
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)      # 只保留数字中间的小数点
    return s


def tokens(text):
    return re.findall(r"[a-z]+|\d|[%.]|[\u3400-\u9fff]", normalize(text))


# ---------------------------------------------------------------- 比对


def align(ref, hyp, keys_ref=None, keys_hyp=None):
    """编辑距离对齐，返回操作序列 [(op, 原稿字, 转写字)]，op ∈ E S D I。
    keys_ref/keys_hyp 给了的话按它们比"是否相同"（集合有交集就算相同，用于拼音比对）。"""
    n, m = len(ref), len(hyp)
    kr, kh = keys_ref, keys_hyp
    prev = list(range(m + 1))
    back = [bytearray(b"I" * (m + 1))]
    back[0][0] = ord("E")
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        row = bytearray(m + 1)
        row[0] = ord("D")
        ri = ref[i - 1]
        for j in range(1, m + 1):
            if (kr[i - 1] & kh[j - 1]) if kr is not None else ri == hyp[j - 1]:
                best, op = prev[j - 1], "E"
            else:
                best, op = prev[j - 1] + 1, "S"
            if prev[j] + 1 < best:
                best, op = prev[j] + 1, "D"
            if cur[j - 1] + 1 < best:
                best, op = cur[j - 1] + 1, "I"
            cur[j] = best
            row[j] = ord(op)
        back.append(row)
        prev = cur
    ops, i, j = [], n, m
    while i > 0 or j > 0:
        op = chr(back[i][j]) if i > 0 and j > 0 else ("D" if i > 0 else "I")
        if op in "ES":
            ops.append((op, ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif op == "D":
            ops.append(("D", ref[i - 1], ""))
            i -= 1
        else:
            ops.append(("I", "", hyp[j - 1]))
            j -= 1
    return ops[::-1]


def _join(toks):
    out = ""
    for t in toks:
        if out and re.match(r"[a-z]", t) and re.search(r"[a-z0-9]$", out):
            out += " "
        out += t
    return out


def diff_runs(ops, gap=RUN_GAP):
    """把差异归成一处一处：每处统计多出(I)、少掉(D)、替换(S)，附原稿和转写片段。"""
    runs, cur, eq = [], None, 0
    for op, r, h in ops:
        if op == "E":
            if cur is not None:
                eq += 1
                cur["_tail"].append((r, h))
                if eq > gap:
                    cur["_tail"] = cur["_tail"][:-eq]
                    runs.append(cur)
                    cur, eq = None, 0
            continue
        if cur is None:
            cur = {"I": 0, "D": 0, "S": 0, "ref": [], "hyp": [], "_tail": []}
        else:
            for tr, th in cur["_tail"]:
                cur["ref"].append(tr)
                cur["hyp"].append(th)
        cur["_tail"], eq = [], 0
        cur[op] += 1
        if r:
            cur["ref"].append(r)
        if h:
            cur["hyp"].append(h)
    if cur is not None:
        runs.append(cur)
    return [{"多出": x["I"], "少掉": x["D"], "替换": x["S"],
             "原稿": _join(x["ref"]), "转写": _join(x["hyp"])} for x in runs]


def _pinyin_sets(toks):
    """每个汉字 → 它所有读音的无调拼音集合；其他记号原样。"""
    out = []
    for t in toks:
        if _pinyin and re.match(r"[\u3400-\u9fff]", t):
            out.append(frozenset(_pinyin(t, style=Style.NORMAL, heteronym=True)[0]))
        else:
            out.append(frozenset([t]))
    return out


def _qc_pinyin_sets(toks):
    """可疑处、新模型复核用（2026-11-16 加）：和 _pinyin_sets 一样，只是数字 1 也当 yi。"一"在不在数字上下文里，原稿和转写
    可能认得不一样（原稿"一边说"、"一封信"留着"一"，转写写成"1边说"、"1份"），这样两边照样对得上。"""
    return [k | {"yi"} if t == "1" else k for t, k in zip(toks, _pinyin_sets(toks))]


def pinyin_error_rate(ref, hyp):
    """按拼音比、不计声调：同音字、多音字的另一种读音都算对。剩下的才是"听起来就不一样"的地方。"""
    if not _pinyin:
        return None
    ops = align(ref, hyp, _pinyin_sets(ref), _pinyin_sets(hyp))
    return sum(1 for o in ops if o[0] != "E") / max(1, len(ref))


_NAMES_CACHE = {}


def _name_pattern(form):
    """英文按整词、不分大小写（前后紧挨字母的不算，Cloudflare 里的 cloud 不算）；中文按字面。"""
    body = r"\s*".join(re.escape(x) for x in form.split())
    if re.search(r"[A-Za-z]", form):
        return re.compile(r"(?<![A-Za-z])" + body + r"(?![A-Za-z])", re.I)
    return re.compile(body)


def load_names(path=None):
    """专名读音清单 → [{"写法": [正则…], "名字": 写法原样, "误读": [(写法, 正则)…], "说明", "只提醒"}]。读不了返回 []（不查这一项）。"""
    p = Path(path) if path else NAMES
    try:
        mt = p.stat().st_mtime_ns
    except OSError:
        return []
    hit = _NAMES_CACHE.get(str(p))
    if hit and hit[0] == mt:
        return hit[1]
    rows = []
    try:
        import yaml
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for e in d.get("名字") or []:
            if not isinstance(e, dict) or not e.get("写法") or not e.get("已知误读"):
                continue
            forms = e["写法"] if isinstance(e["写法"], list) else [e["写法"]]
            bad = e["已知误读"] if isinstance(e["已知误读"], list) else [e["已知误读"]]
            rows.append({"名字": str(forms[0]), "写法": [_name_pattern(str(f)) for f in forms],
                         "误读": [(str(b), _name_pattern(str(b))) for b in bad], "说明": str(e.get("说明") or ""),
                         "只提醒": e.get("只提醒") is True})
    except Exception:  # noqa: BLE001  清单坏了不能让配音停下
        rows = []
    _NAMES_CACHE[str(p)] = (mt, rows)
    return rows


def _norm_hyp(text):
    s = unicodedata.normalize("NFKC", text or "")
    return _T2S.convert(s) if _T2S else s


def name_misreads(ref_text, hyp_text, names=None):
    """原稿有清单里的名字、转写里多出了它的已知误读 → [{"名字", "转写成", "处数", "说明"}]，清单标了只提醒的另带 "只提醒": True。
    "多出"按次数算：原稿里本来就有的同一个词（原稿写了 Google Cloud）先抵掉，免得误报。"""
    names = load_names() if names is None else names
    ref, hyp = _norm_hyp(ref_text), _norm_hyp(hyp_text)
    out = []
    for e in names:
        if not any(p.search(ref) for p in e["写法"]):
            continue
        for word, pat in e["误读"]:
            n = len(pat.findall(hyp)) - len(pat.findall(ref))
            if n > 0:
                out.append({"名字": e["名字"], "转写成": word, "处数": n, "说明": e["说明"],
                            **({"只提醒": True} if e.get("只提醒") else {})})
    return out


# ---------------------------------------------------------------- 数字单位（2026-11-09 晚加）
# 原稿里紧跟在数字后面的量级和单位。同一组（第二个值）的算同义；量级给出倍数，用来认"3.4万"＝"34000"。
UNIT_MAGS = {"万亿": 1e12, "千亿": 1e11, "百亿": 1e10, "千万": 1e7, "百万": 1e6, "亿": 1e8, "万": 1e4, "千": 1e3, "百": 1e2}
UNIT_KINDS = {
    "美元": "美元", "美金": "美元", "欧元": "欧元", "英镑": "英镑", "日元": "日元", "日圆": "日元",
    "港元": "港元", "港币": "港元", "澳元": "澳元", "加元": "加元", "韩元": "韩元", "新台币": "新台币", "台币": "新台币",
    "卢布": "卢布", "卢比": "卢比", "新加坡元": "新加坡元", "元人民币": "人民币", "人民币": "人民币", "元": "人民币",
    "个百分点": "百分点", "百分点": "百分点", "百分之": "%", "%": "%", "倍": "倍",
}
_APPROX = "多余几来"      # "三十多万""十几亿"：数字和单位中间的约数字，跳过


def _match_unit(toks, p, table):
    """从第 p 个记号起，按表找最长的一个单位（表里都是单字记号拼成的）：返回 (单位, 新位置) 或 ("", p)。"""
    for u in sorted(table, key=len, reverse=True):
        if u == "百" and "".join(toks[p:p + 2]) == "百分":     # "百分点""百分之"不是量级"百"
            continue
        if "".join(toks[p:p + len(u)]) == u and all(len(t) == 1 for t in toks[p:p + len(u)]):
            return u, p + len(u)
    return "", p


def _digits_at(toks, q):
    """从 q 起的一串数字（中间可带小数点）的结束位置。"""
    while q < len(toks) and (toks[q].isdigit() or (toks[q] == "." and q + 1 < len(toks) and toks[q + 1].isdigit())):
        q += 1
    return q


def _skip_approx(toks, q):
    while q < len(toks) and toks[q] in _APPROX:
        q += 1
    return q


def _num_unit(toks, p):
    """从 p 起读"数字 [约数] [量级] ([数字 [量级]]…) [约数] [单位]"：返回 {"数字", "量级", "单位", "值", "数字止", "止"}。
    "1万7500"（一万七千五百）、"3亿2000万"这种带量级的复合数一起读，值按整个数算，免得和转写里的"17500"对不上。
    "数字"是第一段数字，"量级"是各段量级连起来（"万""亿万"），"值"是整个数的数值（读不了是 None）。"""
    q = _digits_at(toks, p)
    first, nend = "".join(toks[p:q]), q
    mags, value, cur_num = "", 0.0, first
    while True:
        r = _skip_approx(toks, q)
        mag, r2 = _match_unit(toks, r, UNIT_MAGS)
        try:
            v = float(cur_num) if cur_num else None
        except ValueError:
            v = None
        if not mag:
            value = value + v if (v is not None and value is not None) else None
            break
        mags += mag
        value = value + v * UNIT_MAGS[mag] if (v is not None and value is not None) else None
        q = r2
        nxt = _digits_at(toks, q)                     # 量级后面紧跟的数字：小于这一级的才算同一个数（1万7500）
        if nxt == q:
            break
        try:
            small = float("".join(toks[q:nxt])) * UNIT_MAGS.get(_match_unit(toks, _skip_approx(toks, nxt), UNIT_MAGS)[0], 1) \
                < UNIT_MAGS[mag]
        except ValueError:
            small = False
        if not small:
            break
        cur_num, q = "".join(toks[q:nxt]), nxt
    r = _skip_approx(toks, q)
    unit, r = _match_unit(toks, r, UNIT_KINDS)
    return {"数字": first, "量级": mags, "单位": unit, "值": value if first else None, "数字止": nend, "止": r if unit else q}


def _number_mentions(toks):
    """原稿里每个"数字＋量级/单位"：[(起, 止, _num_unit 的结果)]（记号下标，止不含）。"""
    out, k = [], 0
    while k < len(toks):
        if not toks[k].isdigit():
            k += 1
            continue
        m = _num_unit(toks, k)
        if m["量级"] or m["单位"]:
            out.append((k, m["止"], m))
        k = max(m["止"], m["数字止"])
    return out


def _parse_hyp_unit(toks):
    """对上原稿那一段的转写记号 → (_num_unit 的结果, 这一段里出现的所有单位)。从第一个数字读起；没有数字时只在里面找。
    "所有单位"用来认"32万亿日元"转写成"32万元日元"这种：亿丢了，日元其实还在。"""
    m = {"数字": "", "量级": "", "单位": "", "值": None}
    for k, t in enumerate(toks):
        if t.isdigit():
            m = _num_unit(toks, k)
            break
    found, k = [], 0
    while k < len(toks):                      # 不重叠地找（"日元"里的"元"不再单算一次）
        if not m["数字"] and not m["量级"]:
            m["量级"] = _match_unit(toks, k, UNIT_MAGS)[0]
        u, k2 = _match_unit(toks, k, UNIT_KINDS)
        if u:
            found.append(u)
        k = max(k2, k + 1)
    if not m["单位"] and found:
        m["单位"] = found[0]
    return m, found


def _tone_sets(ch):
    if not (_pinyin and re.match(r"[㐀-鿿]$", ch)):
        return frozenset([ch])
    return frozenset(_pinyin(ch, style=Style.TONE3, heteronym=True)[0])


def _missing(a, b):
    """a 里有、b 里没有的字（按次数）。"""
    rest = list(b)
    out = []
    for c in a:
        if c in rest:
            rest.remove(c)
        else:
            out.append(c)
    return "".join(out)


def _shown(u):
    return "百分之" if u == "%" else u


def unit_losses(ref_text, hyp_text, ref=None, hyp=None, ops=None):
    """原稿里数字后面的单位、量级，转写里少了或换了 → [{"原稿", "转写", "说明"}]（规则见文件头"数字单位"）。
    ref/hyp/ops 可以传 check() 已经算好的记号和对齐，省得再算一遍。"""
    ref = tokens(ref_text) if ref is None else ref
    hyp = tokens(hyp_text) if hyp is None else hyp
    mentions = _number_mentions(ref)
    if not mentions:
        return []
    ops = align(ref, hyp) if ops is None else ops
    pos, i, j = [], 0, 0                     # 每一步对齐：(op, 原稿下标, 转写下标)
    for op, r, h in ops:
        if op in "ES":
            pos.append((op, i, j))
            i, j = i + 1, j + 1
        elif op == "D":
            pos.append((op, i, None))
            i += 1
        else:
            pos.append((op, None, j))
            j += 1
    out = []
    for a, end, m in mentions:
        ks = [k for k, (_, ri, _) in enumerate(pos) if ri is not None and a <= ri < end]
        span = []
        for op, ri, hj in pos[ks[0]:ks[-1] + 1]:
            if hj is None:
                continue
            h = hyp[hj]
            # 单位字换成同音同调的字（倍→被）：当作对上了
            if op == "S" and ri is not None and ref[ri] not in _APPROX and _tone_sets(ref[ri]) & _tone_sets(h) \
                    and re.match(r"[㐀-鿿]$", ref[ri]):
                h = ref[ri]
            span.append(h)
        hm, hall = _parse_hyp_unit(span)
        unit, mag = m["单位"], m["量级"]
        lost, swapped = [], []
        if unit and UNIT_KINDS[unit] not in {UNIT_KINDS[u] for u in hall}:
            if hm["单位"] and _missing(hm["单位"], unit):
                swapped.append(f"{_shown(unit)}→{_shown(hm['单位'])}")
            else:
                lost.append(_shown(_missing(unit, hm["单位"]) or unit))
        if mag and hm["量级"] != mag:
            # 量级写法不同、数值一样的算对（3.4万＝34000，1万7500＝17500，1.25万亿＝12500亿）
            same = m["值"] is not None and hm["值"] is not None and abs(m["值"] - hm["值"]) <= 1e-9 * abs(m["值"])
            if not same:
                if hm["量级"] and _missing(hm["量级"], mag):
                    swapped.append(f"{mag}→{hm['量级']}")
                else:
                    lost.append(_missing(mag, hm["量级"]) or mag)
        if lost or swapped:
            why = "；".join(([f"少字：{'、'.join(lost)}"] if lost else []) + ([f"换字：{'、'.join(swapped)}"] if swapped else []))
            out.append({"原稿": _join(ref[a:end]), "转写": _join(span), "说明": why})
    return out


# ---------------------------------------------------------------- 英文名漏念（2026-11-10 加）
LEXICON = Path(__file__).resolve().parent / "prompts" / "读音表.yaml"
_LEX_CACHE = {}
_TOKEN_RE = re.compile(r"[a-z]+|\d|[%.]|[\u3400-\u9fff]")      # 和 tokens() 同一个正则


def _ref_positions(ops):
    """对齐结果 → 每一步的 (op, 原稿下标, 转写下标)（没有的是 None）。"""
    pos, i, j = [], 0, 0
    for op, r, h in ops:
        if op in "ES":
            pos.append((op, i, j))
            i, j = i + 1, j + 1
        elif op == "D":
            pos.append((op, i, None))
            i += 1
        else:
            pos.append((op, None, j))
            j += 1
    return pos


def _squash(s):
    """只留字母和数字、小写，数字 0 当字母 o（LingBot-Touch → lingbottouch，GR00T → groot），用来认转写里有没有
    这个名字：连写、拆开、带不带连字符，GR00T 写成 GROOT，都算出现了。"""
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", s or "").lower()).replace("0", "o")


def load_lexicon_names(path=None):
    """读音表里写法带英文字母的条目 → [{"名字", "写法": [原样…], "正则": [正则…], "认": [压扁的写法…]}]
    （写法、之后、也可写里带英文字母的都算）。读不了返回 []（不查这一项）。"""
    p = Path(path) if path else LEXICON
    try:
        mt = p.stat().st_mtime_ns
    except OSError:
        return []
    hit = _LEX_CACHE.get(str(p))
    if hit and hit[0] == mt:
        return hit[1]
    rows = []
    try:
        import yaml
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for cat in ("人名", "公司", "产品", "媒体", "其他"):
            for e in d.get(cat) or []:
                if not isinstance(e, dict) or not re.search(r"[A-Za-z]", str(e.get("写法") or "")):
                    continue
                also = e.get("也可写") or []
                forms = [str(e["写法"])] + ([str(e["之后"])] if e.get("之后") else []) + \
                    [str(x) for x in (also if isinstance(also, list) else [also])]
                forms = list(dict.fromkeys(f for f in forms if re.search(r"[A-Za-z]", f)))
                rows.append({"名字": str(e["写法"]), "写法": forms, "正则": [_name_pattern(f) for f in forms],
                             "认": sorted({_squash(f) for f in forms if _squash(f)}, key=len)})
    except Exception:  # noqa: BLE001  表坏了不能让配音停下
        rows = []
    _LEX_CACHE[str(p)] = (mt, rows)
    return rows


def _misread_seen(e, names, hyp):
    """这一条的某个写法正好是专名读音清单里的名字，转写里又出现了它的已知误读：算念到了（念得对不对归 name_misreads 管）。"""
    for x in names:
        if any(p.fullmatch(f) for p in x["写法"] for f in e["写法"]) and any(pat.search(hyp) for _, pat in x["误读"]):
            return True
    return False


def name_drops(ref_text, hyp_text, lexicon=None, names=None):
    """英文名漏念：原稿里读音表收录的英文名，转写里一次都没出现（压扁了比，也没有它的已知误读），而且逐字对齐里
    有一处对上的转写，英文字母不到原稿的一半、又没有汉字（整个词被吞了，不是转写写成了别的拼法、音译）
    → [{"名字", "原稿", "转写"}]（规则和误报统计见文件头"英文名漏念"）。"""
    lexicon = load_lexicon_names() if lexicon is None else lexicon
    names = load_names() if names is None else names
    hyp_raw = _norm_hyp(hyp_text)
    sq = _squash(hyp_raw)
    ref_n = normalize(ref_text)
    R, H = None, None
    pos = None
    out = []
    for e in lexicon:
        found = [m for p in e["正则"] for m in p.finditer(ref_n)]
        if not found:
            continue
        if any(f in sq for f in e["认"]) or _misread_seen(e, names, hyp_raw):
            continue
        if pos is None:
            R, H = tokens(ref_text), tokens(hyp_text)
            pos = _ref_positions(align(R, H))
            spans = [(m.start(), m.end()) for m in _TOKEN_RE.finditer(ref_n)]
            hyp_n = normalize(hyp_text)
            spans_h = [(m.start(), m.end()) for m in _TOKEN_RE.finditer(hyp_n)]
        occ = set()
        for m in found:
            ks = tuple(k for k, (a, b) in enumerate(spans) if a >= m.start() and b <= m.end())
            if any(re.match(r"[a-z]", R[k]) for k in ks):
                occ.add(ks)
        for ks in sorted(x for x in occ if not any(set(x) < set(y) for y in occ)):   # 同一处取最长的写法
            steps = [s for s, (_, ri, _) in enumerate(pos) if ri is not None and ri in ks]
            a, b = steps[0], steps[-1]
            while a > 0 and pos[a - 1][0] == "I":      # 紧挨着多出来的字也算这一处的（DeepSeek 转写成 Deep Seek）
                a -= 1
            while b + 1 < len(pos) and pos[b + 1][0] == "I":
                b += 1
            hj = [h for _, _, h in pos[a:b + 1] if h is not None]
            got = [H[h] for h in hj]
            letters_r = sum(len(R[k]) for k in ks if re.match(r"[a-z]", R[k]))
            letters_h = sum(len(t) for t in got if re.match(r"[a-z]", t))
            if letters_h <= 0.5 * letters_r and not any(re.match(r"[\u3400-\u9fff]", t) for t in got):
                out.append({"名字": e["名字"], "原稿": ref_n[spans[ks[0]][0]:spans[ks[-1]][1]],
                            "转写": hyp_n[spans_h[hj[0]][0]:spans_h[hj[-1]][1]] if hj else ""})
                break
    return out


# ---------------------------------------------------------------- 两个新开关（2026-11-15 加）
SWITCH_FILE = Path(__file__).resolve().parent.parent / "fd_开关.json"
NUMBERS_KEY, NUMBERS_ENV = "对稿数字整数比对", "FD_QC_NUMBERS"
ASR2_KEY, ASR2_ENV = "对稿第二个听写模型", "FD_QC_ASR2"
_OFF = ("off", "0", "false", "no", "关", "关闭", "关掉")
_ON = ("on", "1", "true", "yes", "开", "打开")


def _switch(key, env):
    """返回 (开着没有, 从哪来的一句话)。先看环境变量，再看 fd_开关.json；都没有、读不出、认不出按"关"（新加的两项，
    没写就和加以前一样）。fd 的另外几个开关没写按"开"，这两个不同，是有意的。"""
    v = str(os.environ.get(env) or "").strip().lower()
    if v in _OFF:
        return False, f"环境变量 {env}={v}"
    if v in _ON:
        return True, f"环境变量 {env}={v}"
    try:
        v = str(json.loads(SWITCH_FILE.read_text(encoding="utf-8")).get(key) or "").strip().lower()
    except (OSError, ValueError, AttributeError):
        return False, "没有 fd_开关.json（或读不出来），按“关”"
    if v in _ON:
        return True, f"fd_开关.json 的“{key}”写着“开”"
    return False, f"fd_开关.json 的“{key}”写着“关”" if v in _OFF else f"fd_开关.json 的“{key}”没写或认不出（{v!r}），按“关”"


def numbers_switch():
    return _switch(NUMBERS_KEY, NUMBERS_ENV)


def asr2_switch():
    return _switch(ASR2_KEY, ASR2_ENV)


# ---------------------------------------------------------------- 数字整数比对（2026-11-15 加）
# 跟在数后面、说明这是个"数"的量词（单个数字只有跟着它们才算数；"三星""四处"不算）
_MEASURE = set("页次家个年月日号名项倍台款位人岁秒张条篇件种所天周轮颗座份层成季届期代级档类步句段章场批笔例枚只辆架部本套支根片块分点亿万千百")
_PARTICLES = set("的了吗呢吧啊呀嘛哦嗯呃么哈")
_NUMISH = set("0123456789.%")


_MINUS = re.compile(r"(?<![A-Za-z0-9.])\s*[-−－–](?=\s*\d)")


_YI_MARK = "壹"            # 不当数字的"一"先换成它（cn_numbers_to_arabic 不认它），切成记号以后再换回"一"
_DIGITISH = set(_NUM_CHARS) | set("0123456789")


def _yi_is_number(s, i):
    """s[i] 是"一"：它在不在数字上下文里（2026-11-16 加，见文件头"11-16 回放补的三处"第二条）。
    算数字的：挨着别的数字字（一千、十一、二零二一、一点五、三点一）、前面是"第""百分之""分之"、前面是英文字母或数字
    （型号）、后面跟量词、量级或货币单位（一个、一家、一亿、一美元）、"一到三年""三到一"这类区间、"一万一""三亿一"。
    其余（统一、唯一、一起、小一、之一）不当数字，照"一"这个字比。"""
    def near(k, step):
        while 0 <= k < len(s) and s[k].isspace():
            k += step
        return s[k] if 0 <= k < len(s) else ""
    p, n = near(i - 1, -1), near(i + 1, 1)
    pk = i - 1
    while pk >= 0 and s[pk].isspace():
        pk -= 1
    pp = near(pk - 1, -1) if pk >= 0 else ""
    nk = i + 1
    while nk < len(s) and s[nk].isspace():
        nk += 1
    nn = near(nk + 1, 1) if nk < len(s) else ""
    if p in _DIGITISH or n in _DIGITISH:
        return True
    if p == "第" or p == "负" or s[:i].rstrip().endswith("分之") or re.match(r"[A-Za-z]", p or "_"):
        return True
    if n and (n in _MEASURE or n in "亿万" or any(s[nk:].startswith(u) for u in UNIT_KINDS if u != "%")):
        return True
    if n and n in "点到至或" and nn in _DIGITISH:
        return True
    if p and p in "到至或万亿点" and pp in _DIGITISH:
        return True
    return False


def _keep_lone_yi(text):
    """不在数字上下文里的"一"换成占位字 _YI_MARK，免得被 normalize() 换成 1（11-16 播客"小艺"转写成"小一"，
    "一"变成 1 以后拼音对不上"艺"，同音字被判成可疑处、两个新模型也写"小一"，判了念错）。"""
    s = unicodedata.normalize("NFKC", text or "")
    if _T2S:
        s = _T2S.convert(s)
    if "一" not in s:
        return s
    return "".join(_YI_MARK if c == "一" and not _yi_is_number(s, i) else c for i, c in enumerate(s))


def qc_tokens(text):
    """数字整数比对、可疑处挑选、新模型复核用的记号：和 tokens() 一样，只是数字前面、不挨着字母数字的减号当"负"
    （11-11 视频"从负百分之一百五十改善到……"，SenseVoice 写成"-150%"；tokens() 会把减号当标点去掉，看着像"负"没念）。
    "GPT-5"这类型号里的连字符、"10-20"这类区间不动。
    不在数字上下文里的"一"（统一、小一）不换成 1，照"一"这个字比（2026-11-16 加，见 _yi_is_number）。"""
    toks = tokens(_keep_lone_yi(_MINUS.sub("负", text or "")))
    return ["一" if t == _YI_MARK else t for t in toks]


def _as_digits(toks):
    """比数用：英文数词当数字（four → 4），单独留着的"一"也当 1（转写把"第一"写成"低一"时，照旧认得出这个 1）。"""
    return ["1" if t == "一" else t for t in _en_digits(toks)]


def _is_digit_tok(t):
    return len(t) == 1 and t.isdigit()


def _sig(toks):
    """一个数的"数字样子"：只留数字和小数点（1万7500 → 17500，3.4万 → 3.4）。"""
    return "".join(t for t in toks if _is_digit_tok(t) or t == ".")


def _ref_numbers(toks):
    """原稿记号里每个"数"：[(起, 止, _num_unit 的结果)]（止含量级、单位）。认法见文件头"数字整数比对"。"""
    out, k = [], 0
    while k < len(toks):
        if not _is_digit_tok(toks[k]) or (k and (_is_digit_tok(toks[k - 1]) or toks[k - 1] == ".")):
            k += 1
            continue
        m = _num_unit(toks, k)
        end = max(m["止"], m["数字止"])
        d = m["数字"]
        prev = toks[k - 1] if k else ""
        nxt = toks[m["数字止"]] if m["数字止"] < len(toks) else ""
        nxt2 = "".join(toks[m["数字止"]:m["数字止"] + 2])
        latin = bool(re.match(r"[a-z]", prev))
        strong = bool(m["量级"] or m["单位"] or prev == "第" or latin)
        ranged = nxt in "到至或" and m["数字止"] + 1 < len(toks) and _is_digit_tok(toks[m["数字止"] + 1])
        real = strong or "." in d or len(d) >= 2 or nxt in _MEASURE or ranged     # ranged：三到五年的"三"
        if d == "1" and not strong:
            real = False                       # 一个、一家、一种、一点
        if d == "10" and not strong and nxt in "分足全字" and nxt2 != "分钟":
            real = False                       # 十分、十足、十全、十字
        if real:
            out.append((k, end, m))
        k = end if end > k else k + 1
    return out


def _span(pos, hyp, a, end, extend_digits=True):
    """原稿第 a 到 end（不含）个记号对上的那段转写：返回转写下标 [起, 止)（没有对上的字时起＝止，在那个位置）。
    紧挨着多出来的字也算这一段（DeepSeek 转写成 Deep Seek）；extend_digits 时再往两边带上连着的数字、小数点。"""
    steps = [s for s, (_, ri, _) in enumerate(pos) if ri is not None and a <= ri < end]
    if not steps:
        return 0, 0
    s0, s1 = steps[0], steps[-1]
    while s0 > 0 and pos[s0 - 1][0] == "I":
        s0 -= 1
    while s1 + 1 < len(pos) and pos[s1 + 1][0] == "I":
        s1 += 1
    hj = [h for _, _, h in pos[s0:s1 + 1] if h is not None]
    if not hj:                                 # 整段都没对上：落在前一个对上的字后面
        j = next((h + 1 for _, _, h in reversed(pos[:s0]) if h is not None), 0)
        return j, j
    h0, h1 = hj[0], hj[-1] + 1
    if extend_digits:
        while h0 > 0 and (_is_digit_tok(hyp[h0 - 1]) or hyp[h0 - 1] == "."):
            h0 -= 1
        while h1 < len(hyp) and (_is_digit_tok(hyp[h1]) or hyp[h1] == "." or hyp[h1] in UNIT_MAGS):
            h1 += 1
    return h0, h1


# 型号里的数配音常按英文念（Qwen 4 念 four），转写写成英文词：比数时当数字
_EN_DIGITS = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "for": "4", "five": "5", "six": "6",
              "seven": "7", "eight": "8", "nine": "9", "ten": "10"}


def _en_digits(toks):
    out = []
    for t in toks:
        out += list(_EN_DIGITS[t]) if t in _EN_DIGITS else [t]
    return out


def _en_in_latin(sig, toks):
    """英文型号里的数（sig 是它的数字样子）转写成了连在英文词里的英文数词（geminiforcarbon 里的 for）。"""
    words = [w for w, d in _EN_DIGITS.items() if d == sig]
    return any(re.match(r"[a-z]", t) and any(w in t for w in words) for t in toks)


def _same_number(m, ref_toks, hyp_toks):
    """原稿这个数（_num_unit 的结果 m、它的记号）在这段转写里有没有：同值，或数字样子一样（量级不同归"数字单位"管）。
    转写里按英文写的数（four、for）当数字。"""
    sig = _sig(ref_toks)
    hyp_toks = _as_digits(hyp_toks)
    k = 0
    while k < len(hyp_toks):
        if not _is_digit_tok(hyp_toks[k]) or (k and (_is_digit_tok(hyp_toks[k - 1]) or hyp_toks[k - 1] == ".")):
            k += 1
            continue
        h = _num_unit(hyp_toks, k)
        hend = max(h["止"], h["数字止"])
        if m["值"] is not None and h["值"] is not None and abs(m["值"] - h["值"]) <= 1e-9 * max(1.0, abs(m["值"])):
            return True
        if _sig(hyp_toks[k:hend]) == sig:
            return True
        k = hend if hend > k else k + 1
    return False


def number_mismatches(ref_text, hyp_text, ref=None, hyp=None, ops=None):
    """原稿里的数，转写里对不上同一个值 → [{"原稿", "转写", "起", "止"}]（起止是原稿记号下标）。规则见文件头"数字整数比对"。"""
    ref = qc_tokens(ref_text) if ref is None else ref
    hyp = qc_tokens(hyp_text) if hyp is None else hyp
    nums = _ref_numbers(ref)
    if not nums:
        return []
    ops = align(ref, hyp) if ops is None else ops
    pos = _ref_positions(ops)
    out = []
    for a, end, m in nums:
        h0, h1 = _span(pos, hyp, a, end)
        if _same_number(m, ref[a:end], hyp[h0:h1]):
            continue
        near_latin = (a and re.match(r"[a-z]", ref[a - 1])) or (end < len(ref) and re.match(r"[a-z]", ref[end]))
        if near_latin and _en_in_latin(_sig(ref[a:end]), hyp[max(0, h0 - 1):h1 + 1]):
            continue                           # "Gemini 4 Carbon"转写成一个词"geminiforcarbon"：four 在里面，算念到了
        out.append({"原稿": _join(ref[a:end]), "转写": _join(hyp[h0:h1]), "起": a, "止": end, "转写起": h0, "转写止": h1,
                    "同音写法": _number_homophone(ref[a:end], hyp[h0:h1])})
    return out


def _readings(toks):
    """一串记号（数字连着念）可能的念法：每段数字按"一千零九"和逐位"一零零九"两种念，二／两都算；别的字照留。"""
    from spoken_numbers import digits_zh, int_zh   # noqa: E402  （同目录，纯文本，不花钱）
    parts, cur = [], ""
    for t in toks:
        if _is_digit_tok(t) or (t == "." and cur):
            cur += t
        else:
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(t)
    if cur:
        parts.append(cur)
    opts = [""]
    for x in parts:
        if x and x[0].isdigit():
            whole, _, frac = x.partition(".")
            tail = ("点" + digits_zh(frac)) if frac else ""
            alts = {digits_zh(whole) + tail}
            if whole and len(whole) <= 12:
                alts.add(int_zh(int(whole)) + tail)
            alts |= {a.replace("两", "二") for a in alts} | {a.replace("二", "两") for a in alts}
        else:
            alts = {x}
        opts = [o + a for o in opts for a in sorted(alts)][:64]
    return opts


def _number_homophone(ref_toks, hyp_toks):
    """转写和原稿的数是不是"同音写法"：转写那段按某种念法念出来，和原稿的念法不带声调的拼音一样（"十六"写成"是 6"），
    或者转写把相邻几个数连写成一串、原稿的数字原样在里面（"七十到七十八"写成"7078"）。是的话由第二个听写模型来定；
    不是（"一千零九"写成"109"：yi qian ling jiu 和 yi bai ling jiu、yi ling jiu 都不同音）就照数字不符重录，
    新模型听成原稿也照录——11-15 那一处两个新模型都听成 1009，可用户耳听是 109。"""
    if not hyp_toks:
        return False
    rs, hs = _sig(ref_toks), _sig(_as_digits(hyp_toks))
    if rs and hs and rs != hs and rs in hs:
        return True
    if not _pinyin:
        return False
    for r in _readings(ref_toks):
        kr = _pinyin_sets(list(r))
        for h in _readings(_as_digits(hyp_toks)):
            kh = _pinyin_sets(list(h))
            if len(kr) == len(kh) and all(a & b for a, b in zip(kr, kh)):
                return True
    return False


_TONE_NAMES_CACHE = {}


def load_tone_names(names_path=None, lexicon_path=None):
    """按声调复核的名字（2026-11-16 加）：专名读音清单里、读音表"人名"里整个用汉字写的写法（两个字以上），长的在前。
    读不了的那份当没有。"""
    ps = [Path(names_path) if names_path else NAMES, Path(lexicon_path) if lexicon_path else LEXICON]
    try:
        key = tuple((str(p), p.stat().st_mtime_ns if p.exists() else 0) for p in ps)
    except OSError:
        key = None
    if key and key in _TONE_NAMES_CACHE:
        return _TONE_NAMES_CACHE[key]
    found = []
    try:
        import yaml
    except Exception:  # noqa: BLE001
        return []
    try:
        for e in (yaml.safe_load(ps[0].read_text(encoding="utf-8")) or {}).get("名字") or []:
            forms = e.get("写法") if isinstance(e, dict) else None
            found += [str(f) for f in (forms if isinstance(forms, list) else [forms]) if f]
    except Exception:  # noqa: BLE001  清单坏了不能让配音停下
        pass
    try:
        for e in (yaml.safe_load(ps[1].read_text(encoding="utf-8")) or {}).get("人名") or []:
            if isinstance(e, dict) and e.get("写法"):
                found.append(str(e["写法"]))
    except Exception:  # noqa: BLE001
        pass
    out = sorted({f for f in found if re.fullmatch(r"[㐀-鿿]{2,}", f)}, key=lambda f: (-len(f), f))
    if key:
        _TONE_NAMES_CACHE[key] = out
    return out


def _is_cjk(t):
    return bool(t) and bool(re.match(r"[\u3400-\u9fff]$", t))


def _is_latin_tok(t):
    return bool(t) and bool(re.match(r"[a-z]", t))


def _split_latin(pos, ref, hyp, steps):
    """并成一处的差异里有英文字母时（2026-11-16 加）：按对上的字切开，带英文字母的那几截照旧跳过（英文名拿不准），
    其余只有中文的几截（中间不隔英文）各自成一处。没有英文字母的原样返回一处。
    11-16 播客"LeCun、吴恩达"转写成"勒坤吴文达"：LeCun→勒坤 和 恩→文 只隔一个"吴"，并成一处后带英文字母，整处被跳过，
    "吴恩达"念错（用户耳听确认）就漏了。和英文直接挨着、中间没有对上的字的中文差异仍跟着英文跳过（分不清是不是音译的字）。"""
    def latin(s):
        _, ri, hj = pos[s]
        return (ri is not None and _is_latin_tok(ref[ri])) or (hj is not None and _is_latin_tok(hyp[hj]))
    if not any(latin(s) for s in steps):
        return [steps]
    pieces, cur = [], []
    for s in steps:                            # 按对上的字（E）切成一截一截；E 自己单独一截
        if pos[s][0] == "E":
            if cur:
                pieces.append(cur)
                cur = []
            pieces.append([s])
        else:
            cur.append(s)
    if cur:
        pieces.append(cur)
    groups, g = [], []
    for pc in pieces:
        if any(latin(s) for s in pc):
            if g:
                groups.append(g)
            g = []
            continue
        g += pc
    if g:
        groups.append(g)
    out = []
    for g in groups:
        while g and pos[g[0]][0] == "E":
            g = g[1:]
        while g and pos[g[-1]][0] == "E":
            g = g[:-1]
        if g:
            out.append(g)
    return out


def _tone_suspects(ref, hyp, pos, names, taken):
    """名字（load_tone_names）不带声调对上了、可 Whisper 写的字声调不同（黄仁勋 → 黄仁荀，xūn → xún）：
    整个名字算一处，标"声调"，复核时按带声调的拼音比（2026-11-16 加）。和别的可疑处重叠的不重复挑。"""
    emap = {ri: (op, hj) for op, ri, hj in pos if ri is not None}
    out = []
    for nm in names:
        L = list(nm)
        k = 0
        while k <= len(ref) - len(L):
            if ref[k:k + len(L)] != L:
                k += 1
                continue
            ks = list(range(k, k + len(L)))
            if not taken & set(ks) and all(emap[q][0] == "E" for q in ks) and any(
                    hyp[emap[q][1]] != ref[q] and _is_cjk(hyp[emap[q][1]])
                    and not (_tone_sets(ref[q]) & _tone_sets(hyp[emap[q][1]])) for q in ks):
                h0, h1 = emap[ks[0]][1], emap[ks[-1]][1] + 1
                out.append({"原稿": _join(ref[k:k + len(L)]), "转写": _join(hyp[h0:h1]), "起": k, "止": k + len(L),
                            "转写起": h0, "转写止": h1, "声调": True})
                taken |= set(ks)
            k += len(L)
    return out


def suspects(ref, hyp, numbers=True, gap=1, names=None):
    """可疑处（交给第二个听写模型复核的地方）：原稿和转写按不带声调的拼音对齐，对不上的一处一处
    → [{"原稿", "转写", "起", "止", "转写起", "转写止"}]。不算的：只多出字的、带英文字母的、只差语气词的；
    numbers 为真时（数字整数比对开着）只差数字、小数点、百分号、量级的也不算（归"数字不符"管）。
    2026-11-16 加两条：并进来的差异里带英文字母的，英文那几截跳过、中文那几截照挑（_split_latin）；
    names（不给就用 load_tone_names()，给 [] 就不查）里的名字只差声调的也挑，带 "声调": True（_tone_suspects）。"""
    if not _pinyin:
        return []
    names = load_tone_names() if names is None else names
    ops = align(ref, hyp, _qc_pinyin_sets(ref), _qc_pinyin_sets(hyp))
    pos = _ref_positions(ops)
    runs, cur, eq = [], None, 0
    for s, (op, ri, hj) in enumerate(pos):
        if op == "E":
            if cur is not None:
                eq += 1
                if eq > gap:
                    runs.append(cur)
                    cur, eq = None, 0
            continue
        if cur is None:
            cur = {"steps": []}
        else:
            cur["steps"] += list(range(cur["steps"][-1] + 1, s))
        eq = 0
        cur["steps"].append(s)
    if cur is not None:
        runs.append(cur)
    out = []
    for steps in (g for r in runs for g in _split_latin(pos, ref, hyp, r["steps"])):
        st = [pos[s] for s in steps]
        bad_r = [ref[ri] for op, ri, _ in st if op != "E" and ri is not None]
        if not bad_r:
            continue                                   # 只多出字
        ris = [ri for _, ri, _ in st if ri is not None]
        hjs = [hj for _, _, hj in st if hj is not None]
        a, end = ris[0], ris[-1] + 1
        h0, h1 = (hjs[0], hjs[-1] + 1) if hjs else _span(pos, hyp, a, end, extend_digits=False)
        if any(re.match(r"[a-z]", t) for t in ref[a:end] + hyp[h0:h1]):
            continue                                   # 英文名、英文词：拿不准，不复核
        bad_h = [hyp[hj] for op, _, hj in st if op != "E" and hj is not None]
        if all(t in _PARTICLES for t in bad_r) and all(t in _PARTICLES for t in bad_h):
            continue                                   # 只是语气词没了、换成另一个语气词（"增长了"→"增长为"照算）
        if numbers and all(t in _NUMISH or t in "万亿千百" for t in bad_r):
            continue
        out.append({"原稿": _join(ref[a:end]), "转写": _join(hyp[h0:h1]), "起": a, "止": end, "转写起": h0, "转写止": h1})
    if names:
        taken = {k for x in out for k in range(x["起"], x["止"])}
        out = sorted(out + _tone_suspects(ref, hyp, pos, names, taken), key=lambda x: x["起"])
    return out


def check(ref_text, hyp_text, seconds=None, est_seconds=None):
    """返回对稿结果字典；"需重录" 为 True 表示有多念、漏念、整体对不上，或专名转写成了已知误读（11-09 加；
    清单标了"只提醒"的名字不算，只记进"专名读音"），或数字后面的单位字少了、换了（11-09 晚加，记进"数字单位"），
    或读音表里的英文名整个没念出来（11-10 加，记进"英文名漏念"）。"""
    ref, hyp = tokens(ref_text), tokens(hyp_text)
    ops = align(ref, hyp)
    cnt = {k: sum(1 for o in ops if o[0] == k) for k in "SDI"}
    cer = (cnt["S"] + cnt["D"] + cnt["I"]) / max(1, len(ref))
    per = pinyin_error_rate(ref, hyp)
    runs = diff_runs(ops)
    max_ins = max([r["多出"] for r in runs] or [0])
    max_del = max([r["少掉"] for r in runs] or [0])
    reasons = []
    if max_ins >= RUN_LIMIT:
        reasons.append(f"多念：一处多出 {max_ins} 个字/词")
    if max_del >= RUN_LIMIT:
        reasons.append(f"漏念：一处少了 {max_del} 个字/词")
    if cer >= CER_LIMIT:
        reasons.append(f"字错率 {cer:.1%} 过高")
    ratio = None
    if seconds and est_seconds:
        ratio = seconds / est_seconds
        if not DURATION_RANGE[0] <= ratio <= DURATION_RANGE[1]:
            reasons.append(f"时长异常：实际 {seconds:.0f} 秒，估计 {est_seconds:.0f} 秒")
    names = name_misreads(ref_text, hyp_text)
    for x in names:
        if not x.get("只提醒"):
            reasons.append(f"专名读音：{x['名字']} 转写成了 {x['转写成']}（{x['处数']} 处），重录一次；还在就请你耳听")
    units = unit_losses(ref_text, hyp_text, ref, hyp, ops)
    for x in units:
        reasons.append(f"数字单位{x['说明']}（原稿 {x['原稿']}，转写 {x['转写'] or '（没有）'}），重录一次；还在就请你耳听")
    drops = name_drops(ref_text, hyp_text)
    for x in drops:
        reasons.append(f"英文名漏念：{x['名字']}（原稿 {x['原稿']}，转写 {x['转写'] or '（没有）'}），重录一次；还在就请你耳听")
    nums, todo = [], []
    num_on, asr2_on = numbers_switch()[0], asr2_switch()[0]
    if num_on or asr2_on:                      # 11-15 的两项用"减号当负"的记号（qc_tokens），和上面的字错率各算各的
        R2, H2 = qc_tokens(ref_text), qc_tokens(hyp_text)
    if num_on:                                 # 11-15：数字按整个数比（关着时这一段不跑，结果和以前一样）
        nums = number_mismatches(ref_text, hyp_text, R2, H2, align(R2, H2))
        for x in nums:
            reasons.append(_number_reason(x))
            todo.append(dict(x, 类="数字"))
    if asr2_on:                                # 11-15：交给第二个听写模型复核的可疑处（调用方 confirm() 去听）
        todo += [dict(x, 类="字词") for x in suspects(R2, H2, numbers=num_on)]
    return {"字错率": round(cer, 4),
            "拼音错误率": round(per, 4) if per is not None else None,
            "原稿字数": len(ref), "转写字数": len(hyp),
            "替换": cnt["S"], "少掉": cnt["D"], "多出": cnt["I"],
            "最长多出": max_ins, "最长少掉": max_del,
            "时长比": round(ratio, 2) if ratio else None,
            "需重录": bool(reasons), "原因": reasons,
            **({"专名读音": names} if names else {}),
            **({"数字单位": units} if units else {}),
            **({"英文名漏念": drops} if drops else {}),
            **({"数字不符": [_public(x) for x in nums]} if nums else {}),
            **({"待复核": todo} if todo else {}),
            "差异": runs, "转写": hyp_text}


def _number_reason(x):
    return f"数字不符：原稿 {x['原稿']}，转写 {x['转写'] or '（没有）'}，重录；还在就请你耳听"


def _public(x):
    """写进 qc.json 的样子：去掉记号下标（只给程序内部用）。"""
    return {k: v for k, v in x.items() if k not in ("起", "止", "转写起", "转写止", "同音写法")}


# ---------------------------------------------------------------- 第二个听写模型复核（2026-11-15 加）
ASR2_WORKER = Path(__file__).resolve().parent / "asr2_worker.py"
ASR2_LOAD_TIMEOUT_S = 600       # 载入两个模型最多等这么久（云端第一次从缓存解开、载入约一两分钟）
ASR2_CLIP_TIMEOUT_S = 120       # 一段最多等这么久


def _asr2_paths():
    py = Path(os.environ.get("FD_ASR2_PYTHON") or Path.home() / ".venvs/fd-asr2/bin/python").expanduser()
    models = Path(os.environ.get("FD_ASR2_MODELS") or Path.home() / ".cache/fd-asr2").expanduser()
    cache = Path(os.environ.get("FD_ASR2_CACHE") or Path.home() / ".cache/frontier-daily/tts/asr2").expanduser()
    return py, models, cache


class _ASR2:
    """常驻的第二个听写模型进程（asr2_worker.py）。第一次要用时起，整期只载入一次；进程退出时一起收掉。
    状态：None 没起；"loading" 起了还没载完；"ready"；"failed"（self.why 是原因，之后都不再试）。"""

    def __init__(self):
        import threading
        self.proc, self.state, self.why, self.info = None, None, "", {}
        self.lock = threading.Lock()
        self.lines = None
        self.errlog = None
        self.n = 0

    def start(self):
        """起进程（不等它载完：配音还在跑，模型在后面载入）。已经起过就什么也不做。"""
        if self.state is not None:
            return
        import queue
        import threading
        py, models, cache = _asr2_paths()
        if not py.exists():
            self.state, self.why = "failed", f"没有第二个听写模型的环境（{py.name} 不在，FD_ASR2_PYTHON）"
            return
        if not (models / "SenseVoiceSmall" / "model.pt").exists() or not (models / "paraformer-zh" / "model.pt").exists():
            self.state, self.why = "failed", "模型目录里没有 SenseVoiceSmall、paraformer-zh（FD_ASR2_MODELS）"
            return
        cache.mkdir(parents=True, exist_ok=True)
        env = {k: v for k, v in os.environ.items()
               if not re.search(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", k, re.I)}    # 子进程用不着任何密钥
        env.update(HF_HUB_OFFLINE="1", PYTHONDONTWRITEBYTECODE="1")
        try:
            self.errlog = open(cache / "worker.log", "a", encoding="utf-8")
            self.proc = subprocess.Popen([str(py), "-u", str(ASR2_WORKER), "--models", str(models)],
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errlog,
                                         text=True, encoding="utf-8", env=env)
        except OSError as e:
            self.state, self.why = "failed", f"起不了第二个听写模型：{e}"
            return
        self.lines = queue.Queue()

        def pump(out, q):
            for line in out:
                q.put(line)
            q.put(None)
        threading.Thread(target=pump, args=(self.proc.stdout, self.lines), daemon=True).start()
        self.state = "loading"
        import atexit
        atexit.register(self.close)

    def _read(self, timeout):
        import queue
        try:
            line = self.lines.get(timeout=timeout)
        except queue.Empty:
            return None
        if line is None:
            return None
        try:
            return json.loads(line)
        except ValueError:
            return {}

    def ready(self):
        """等它载完。返回 True／False（False 时 self.why 是原因）。"""
        with self.lock:
            if self.state is None:
                self.start()
            if self.state == "loading":
                t0 = __import__("time").time()
                while True:
                    left = ASR2_LOAD_TIMEOUT_S - (__import__("time").time() - t0)
                    msg = self._read(max(1, left)) if left > 0 else None
                    if msg is None:
                        self.state, self.why = "failed", "第二个听写模型没载完（超时或进程退出，见 worker.log）"
                        self.close()
                        break
                    if "ready" in msg:
                        if msg.get("ready"):
                            self.state, self.info = "ready", msg
                        else:
                            self.state, self.why = "failed", "第二个听写模型载入失败：" + str(msg.get("错误") or "")[:200]
                            self.close()
                        break
            return self.state == "ready"

    def listen(self, wav, start, end):
        """听一段，返回 {"SenseVoice": 字, "Paraformer": 字}（某个出错就没有那一项），失败返回 None。"""
        if not self.ready():
            return None
        with self.lock:
            self.n += 1
            try:
                self.proc.stdin.write(json.dumps({"id": self.n, "wav": str(wav), "start": start, "end": end}) + "\n")
                self.proc.stdin.flush()
            except (OSError, ValueError):
                self.state, self.why = "failed", "第二个听写模型进程断了"
                return None
            while True:
                msg = self._read(ASR2_CLIP_TIMEOUT_S)
                if msg is None:
                    self.state, self.why = "failed", "第二个听写模型没回话（超时或进程退出）"
                    self.close()
                    return None
                if msg.get("id") == self.n:
                    return {k: msg[k] for k in ("SenseVoice", "Paraformer", "错误", "秒") if k in msg}

    def close(self):
        p, self.proc = self.proc, None
        if p is not None:
            try:
                p.stdin.close()
                p.wait(timeout=10)
            except Exception:  # noqa: BLE001
                p.kill()
            for f in (p.stdout, getattr(self, "errlog", None)):
                try:
                    f and f.close()
                except Exception:  # noqa: BLE001
                    pass


_ASR2_ONE = _ASR2()


def asr2_warm():
    """第二个听写模型开着就先把进程起起来（模型在后台载入，配音照常往下走）。make_episode、对谈开头调一次。"""
    if asr2_switch()[0]:
        _ASR2_ONE.start()


def whisper_times(src, n):
    """转写每个记号的 (起秒, 止秒)：src 是 Whisper 的 json 文件（按分段的起止时间，段里按记号数平分），
    或者已经算好的列表。和 n（转写记号数）对不上时按比例对过去。读不了返回 None。"""
    if isinstance(src, (list, tuple)):
        times = list(src)
    else:
        try:
            d = json.loads(Path(src).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        times = []
        for seg in d.get("segments") or []:
            tk = tokens(seg.get("text") or "")
            s, e = float(seg.get("start") or 0), float(seg.get("end") or 0)
            for i in range(len(tk)):
                times.append((s + (e - s) * i / len(tk), s + (e - s) * (i + 1) / len(tk)))
    if not times or not n:
        return None
    if len(times) != n:
        times = [times[min(len(times) - 1, int(i * len(times) / n))] for i in range(n)]
    return times


def align_fit(ref, hyp, keys_ref=None, keys_hyp=None):
    """两头可以对不上的对齐（新模型听的那几秒和原稿那一段，两头各多几个字不算错）：
    对上 +2，换字、多字、少字 -1，前后多出来的不扣分，取得分最高的。返回和 align() 一样的 [(op, 原稿字, 转写字)]。"""
    n, m = len(ref), len(hyp)
    kr, kh = keys_ref, keys_hyp
    NEG = -10 ** 9
    sc = [[0] * (m + 1) for _ in range(n + 1)]
    bk = [[""] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        bk[i][0] = "D"
    for j in range(1, m + 1):
        bk[0][j] = "I"
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            same = (kr[i - 1] & kh[j - 1]) if kr is not None else ref[i - 1] == hyp[j - 1]
            best, op = sc[i - 1][j - 1] + (2 if same else -1), ("E" if same else "S")
            if sc[i - 1][j] - 1 > best:
                best, op = sc[i - 1][j] - 1, "D"
            if sc[i][j - 1] - 1 > best:
                best, op = sc[i][j - 1] - 1, "I"
            sc[i][j], bk[i][j] = best, op
    bi, bj, bs = n, m, NEG
    for i in range(n + 1):
        if sc[i][m] > bs:
            bi, bj, bs = i, m, sc[i][m]
    for j in range(m + 1):
        if sc[n][j] > bs:
            bi, bj, bs = n, j, sc[n][j]
    tail = [("D", ref[i], "") for i in range(bi, n)] + [("I", "", hyp[j]) for j in range(bj, m)]
    ops, i, j = [], bi, bj
    while i > 0 or j > 0:
        op = bk[i][j] if i > 0 and j > 0 else ("D" if i > 0 else "I")
        if op in "ES":
            ops.append((op, ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif op == "D":
            ops.append(("D", ref[i - 1], ""))
            i -= 1
        else:
            ops.append(("I", "", hyp[j - 1]))
            j -= 1
    return ops[::-1] + tail


def _asr2_cache_get(wav, a, b):
    import hashlib
    try:
        st = Path(wav).stat()
    except OSError:
        return None, None
    key = hashlib.sha1(f"{Path(wav).name}|{st.st_size}|{a:.2f}|{b:.2f}|v1".encode()).hexdigest()[:20]
    p = _asr2_paths()[2] / f"{key}.json"
    if p.exists():
        try:
            return p, json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return p, None


def _clip_window(x, times, n_hyp):
    """可疑处 → 截哪几秒、原稿带哪一段：(起秒, 止秒, 原稿起, 原稿止, 核心起, 核心止)。"""
    h0, h1 = x["转写起"], x["转写止"]
    if h1 > h0:
        t0, t1 = times[h0][0], times[h1 - 1][1]
    else:
        t0 = times[h0 - 1][1] if h0 > 0 else times[0][0]
        t1 = times[h0][0] if h0 < n_hyp else t0
    a, b = max(0.0, t0 - ASR2_PAD_S), t1 + ASR2_PAD_S
    if b - a < ASR2_MIN_CLIP_S:
        mid = (a + b) / 2
        a, b = max(0.0, mid - ASR2_MIN_CLIP_S / 2), mid + ASR2_MIN_CLIP_S / 2
    ha = next((k for k in range(n_hyp) if times[k][1] > a), n_hyp)
    hb = next((k for k in range(n_hyp - 1, -1, -1) if times[k][0] < b), -1) + 1
    before, after = max(0, h0 - ha), max(0, hb - h1)
    core0, core1 = x["起"] - before, x["止"] + after
    return round(a, 2), round(b, 2), core0 - ASR2_MARGIN, core1 + ASR2_MARGIN, core0, core1


def _model_verdict(kind, ref, x, win, text):
    """一个新模型在这一处听到了什么 → ("照原稿"／"也不一样"／"没听清", 它在这一处听到的字)。"""
    r0, r1, c0, c1 = win
    r0, r1 = max(0, r0), min(len(ref), r1)
    c0, c1 = max(r0, c0), min(r1, c1)
    R, M = ref[r0:r1], qc_tokens(text or "")
    if not M:
        return "没听清", ""
    if kind == "数字":
        ops = align_fit(R, _as_digits(M))
        M = _as_digits(M)
    else:
        ops = align_fit(R, M, _qc_pinyin_sets(R), _qc_pinyin_sets(M))
    pos = _ref_positions(ops)
    core = [k for k in range(c0 - r0, c1 - r0) if re.match(r"[\d㐀-鿿]", R[k])]
    hit = {ri for op, ri, _ in pos if op == "E" and ri is not None}
    if core and sum(1 for k in core if k in hit) / len(core) < ASR2_MIN_HEARD:
        return "没听清", _join(M)
    a, b = x["起"] - r0, x["止"] - r0
    h0, h1 = _span(pos, M, a, b, extend_digits=(kind == "数字"))
    heard = _join(M[h0:h1])
    if kind == "数字":
        ok = _same_number(_num_unit(R, a), R[a:b], M[h0:h1])
    else:
        ok = all(k in hit for k in range(a, b))
        if ok and x.get("声调"):              # 名字只差声调（11-16 加）：新模型写的字也要和原稿有同一个带声调的读音
            got = {ri: hj for op, ri, hj in pos if op == "E" and ri is not None}
            ok = all(_tone_sets(R[k]) & _tone_sets(M[got[k]]) for k in range(a, b) if _is_cjk(M[got[k]]))
    return ("照原稿" if ok else "也不一样"), heard


def confirm(items, log=print):
    """第二个听写模型复核（规则见文件头）。items：[(check() 的结果, 当时给 check() 的原稿, 音频路径,
    Whisper json 路径或每个转写记号的起止秒)]。
    就地改每个结果：数字不符被两个新模型都推翻的去掉原因；字词可疑处至少一个新模型也听错的加原因"复核念错：……"；
    结果里加"复核"（每一处、每个模型听到了什么、怎么判）和"复核念错"（判念错的那几处），"需重录"按原因重算。
    开关关着、结果里没有"待复核"的，原样不动。返回这一批复核了几处。"""
    on = asr2_switch()[0]
    done = 0
    for res, ref_text, wav, src in items:
        todo = res.pop("待复核", None)
        if not todo or not on:
            continue
        ref, hyp = qc_tokens(ref_text), qc_tokens(res.get("转写") or "")
        times = whisper_times(src, len(hyp))
        rows, bad = [], []
        for x in todo:
            row = {"类": x["类"], "原稿": x["原稿"], "转写": x["转写"], **({"按声调比": True} if x.get("声调") else {})}
            if times is None or not _ASR2_ONE.ready():
                row["判"] = "没复核"
                row["说明"] = "没有转写的分段时间" if times is None else _ASR2_ONE.why
                rows.append(row)
                continue
            a, b, r0, r1, c0, c1 = _clip_window(x, times, len(hyp))
            row["截取秒"] = [a, b]
            cp, got = _asr2_cache_get(wav, a, b)
            if got is None:
                got = _ASR2_ONE.listen(wav, a, b)
                if got and cp is not None and not got.get("错误"):
                    try:
                        cp.write_text(json.dumps(got, ensure_ascii=False), encoding="utf-8")
                    except OSError:
                        pass
            if not got:
                row["判"], row["说明"] = "没复核", _ASR2_ONE.why or "第二个听写模型没回话"
                rows.append(row)
                continue
            vs = {}
            for name in ("SenseVoice", "Paraformer"):
                if name in got:
                    v, heard = _model_verdict(x["类"], ref, x, (r0, r1, c0, c1), got[name])
                    vs[name] = v
                    row[name] = heard
            row["各模型"] = vs
            if any(v == "也不一样" for v in vs.values()):
                row["判"] = "念错"
            elif any(v == "照原稿" for v in vs.values()):
                row["判"] = "转写听错"
            else:
                row["判"] = "没听清"
            done += 1
            rows.append(row)
            if row["判"] == "念错":
                bad.append(row)
        for x, row in zip(todo, rows):     # 数字：只有同音写法才让新模型推翻；念法不同音的，新模型听成原稿也照重录
            if x["类"] == "数字" and row["判"] == "转写听错" and not x.get("同音写法"):
                row["判"] = "念错"
                row["说明"] = "Whisper 听到的数和原稿念法不同音（不是同音写法），新模型听成原稿也照重录"
                bad.append(row)
        reasons = list(res.get("原因") or [])
        for x, row in zip(todo, rows):
            if x["类"] == "数字" and row["判"] == "转写听错":
                why = _number_reason(x)
                if why in reasons:
                    reasons.remove(why)
            elif x["类"] == "字词" and row["判"] == "念错":
                heard = "、".join(f"{k}「{row.get(k, '')}」" for k in ("SenseVoice", "Paraformer") if k in row)
                tone = "（名字按声调比）" if x.get("声调") else ""
                reasons.append(f"复核念错：原稿「{x['原稿']}」，Whisper「{x['转写'] or '（没有）'}」，{heard}{tone}，重录；还在就请你耳听")
        for row in rows:
            if row["类"] == "数字" and row["判"] in ("没听清", "没复核"):
                row["说明"] = (row.get("说明", "") + "；" if row.get("说明") else "") + "照数字不符重录"
        res["原因"] = reasons
        res["需重录"] = bool(reasons)
        res["复核"] = rows
        if bad:
            res["复核念错"] = bad
        else:
            res.pop("复核念错", None)
        if res.get("数字不符"):
            kept = [_public(x) for x, row in zip(todo, rows) if x["类"] == "数字" and row["判"] != "转写听错"]
            if kept:
                res["数字不符"] = [{k: v for k, v in x.items() if k != "类"} for x in kept]
            else:
                res.pop("数字不符")
        n_bad = sum(1 for r in rows if r["判"] == "念错")
        n_asr = sum(1 for r in rows if r["判"] == "转写听错")
        log(f"    复核（第二个听写模型）：{len(rows)} 处，念错 {n_bad}、Whisper 听错 {n_asr}"
            + (f"、没听清或没复核 {len(rows) - n_bad - n_asr}" if len(rows) - n_bad - n_asr else ""))
    return done



_NEW_REASONS = ("数字不符：", "复核念错：")


def misread(result):
    """这一条有没有数字不符、复核念错（11-15 加）：有就按 MISREAD_RETAKES 最多重录 2 次。"""
    return bool(result.get("数字不符") or result.get("复核念错"))


def misread_only(result):
    """要重录的原因全是数字不符、复核念错（没有多念漏念这些老原因）：这种重录预算不够就不录，不报错。"""
    rs = result.get("原因") or []
    return bool(rs) and all(r.startswith(_NEW_REASONS) for r in rs)


def listen_fields(result):
    """qc.json 那一块要人耳听的两栏（11-15 加）：重录完挑出来的那条还有数字不符、复核念错，就写"数字不符（请你耳听）"
    "复核念错（请你耳听）"；第二个听写模型听过的每一处另记"复核"（只是记录，审片分拣时用）。都没有就是空的。"""
    out = {}
    if result.get("数字不符"):
        out["数字不符（请你耳听）"] = result["数字不符"]
    if result.get("复核念错"):
        out["复核念错（请你耳听）"] = [{k: v for k, v in x.items() if k != "各模型"} for x in result["复核念错"]]
    return out


def badness(result):
    """两条都不完美时挑哪条：先看是否需重录，再看最大的一处多念/漏念，最后看字错率（没转写的废条字错率记作最差）。"""
    cer = result.get("字错率")
    return (result["需重录"], max(result["最长多出"], result["最长少掉"]), cer if cer is not None else float("inf"))


def overlong(seconds, est_seconds):
    """这一条明显跑飞了（11-14 加，经验库第 71 件①）：实际时长超过按字数估计的 OVERLONG_RATIO（2）倍、而且至少多出
    OVERLONG_MIN_EXTRA_S（30）秒，返回一句说明；不是就返回 None。
    为什么：11-11 播客块 1 为音高重录的第 2 条，Gemini 多念了 612 个字，181 秒（估计 55 秒）；照旧整条转写，云端转写
    约 1 秒音频 1 秒，白花 3 分钟才判出"多念""时长异常"。这种不用听也知道不能用，配完量了时长就丢，直接重录。
    只多一点（短块 2 倍出头、多不到 30 秒）的照旧转写，由 check() 的"时长异常"判。"""
    if not seconds or not est_seconds:
        return None
    if seconds > OVERLONG_RATIO * est_seconds and seconds - est_seconds >= OVERLONG_MIN_EXTRA_S:
        return (f"时长异常：实际 {seconds:.0f} 秒，估计 {est_seconds:.0f} 秒（超过 {OVERLONG_RATIO:g} 倍、多 "
                f"{seconds - est_seconds:.0f} 秒），当废条丢掉重录，没转写")
    return None


def discarded(seconds, est_seconds, why):
    """废条（overlong）的对稿结果：字段和 check() 一样，需重录，没转写；挑条时排在转写过的各条后面（tts.pick_take 看"废条"）。"""
    return {"字错率": None, "拼音错误率": None, "原稿字数": 0, "转写字数": 0, "替换": 0, "少掉": 0, "多出": 0,
            "最长多出": 0, "最长少掉": 0, "时长比": round(seconds / est_seconds, 2) if est_seconds else None,
            "需重录": True, "原因": [why], "废条": True, "没转写": True, "差异": [], "转写": ""}


# ---------------------------------------------------------------- 音高、语速把关（2026-11-01 加）
# 同一个声音每次合成的音高会漂（11-01 实测：同一句两次能差几十赫兹，视频各章从 160 到 229 Hz）。
# 把关的做法：每块（对谈里是每轮）配完量一次"音高中位数"，和这个声音的参考音高比；差太多就重录，挑最接近的一条。
# 参考音高、参考语速写在 pipeline/voice_profile.json（各声音的"参考"一节，从定稿样音实测），阈值在它的"音高把关"一节。

SR = 24000
PITCH_TOL_ST = 1.5          # 和参考音高差超过这么多个半音就重录（profile"音高把关"可改）
PITCH_RETAKES = 2           # 为音高最多再录几次
PITCH_MIN_VOICED_S = 1.2    # 有声部分不到这么多秒的（"对。"这类短句）音高量不准，不判
RATE_TOL = 0.10             # 语速和参考值差超过一成，在 qc 里标出来（只标，不重录）
PROFILE = Path(__file__).resolve().parent / "voice_profile.json"


def read_audio(path, sr=SR):
    """任意音频 → 单声道 float64（ffmpeg 解码）。"""
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-f", "f64le", "-ac", "1",
                        "-ar", str(sr), "-"], capture_output=True)
    if r.returncode:
        raise RuntimeError(f"读不了 {path}：{r.stderr.decode(errors='replace')[-300:]}")
    import numpy as np
    return np.frombuffer(r.stdout, dtype=np.float64)


def f0_track(x, sr=SR, fmin=70, fmax=420, frame=0.04, hop=0.02, thresh=0.15):
    """音高（Hz，每 hop 秒一个，不发声的帧是 nan）。YIN 算法（de Cheveigné & Kawahara 2002），
    和 配音测试/第四轮 的 yin_f0、dialog_tts.f0_track 同样的做法和参数；差分函数用 FFT 一次算整批帧。"""
    import numpy as np
    W, H = int(frame * sr), int(hop * sr)
    tmin, tmax = int(sr / fmax), int(sr / fmin)
    n = (len(x) - W - tmax) // H
    if n <= 0:
        return np.array([])
    out = np.full(n, np.nan)
    starts = np.arange(n) * H
    rms_all = np.sqrt(np.array([(x[s:s + W] ** 2).mean() for s in starts]))
    gate = rms_all.max() * 10 ** (-35 / 20)
    L = 1 << int(np.ceil(np.log2(2 * W + tmax)))
    lag = np.arange(1, tmax + 1)
    for a0 in range(0, n, 1024):
        idx = np.arange(a0, min(n, a0 + 1024))
        idx = idx[rms_all[idx] > gate]
        if not len(idx):
            continue
        seg = x[starts[idx][:, None] + np.arange(W + tmax)]
        a = seg[:, :W]
        corr = np.fft.irfft(np.fft.rfft(a[:, ::-1], L) * np.fft.rfft(seg, L), L)[:, W - 1:W + tmax]
        cs = np.concatenate([np.zeros((len(idx), 1)), np.cumsum(seg ** 2, axis=1)], axis=1)
        d = (a ** 2).sum(axis=1)[:, None] + (cs[:, W:W + tmax + 1] - cs[:, :tmax + 1]) - 2 * corr
        d = np.maximum(d, 0)
        cm = np.ones_like(d)
        cm[:, 1:] = d[:, 1:] * lag / np.maximum(np.cumsum(d[:, 1:], axis=1), 1e-12)
        below = cm[:, tmin:] < thresh
        has = below.any(axis=1)
        t = np.where(has, below.argmax(axis=1) + tmin, 0)
        for _ in range(40):                            # 顺着往下走到这个谷的底
            nxt = np.minimum(t + 1, tmax)
            go = has & (t + 1 <= tmax) & (cm[np.arange(len(t)), nxt] < cm[np.arange(len(t)), t])
            if not go.any():
                break
            t = np.where(go, t + 1, t)
        ok = has & (t >= 1) & (t < tmax)
        r = np.arange(len(t))[ok]
        tt = t[ok]
        c0, c1, c2 = cm[r, tt - 1], cm[r, tt], cm[r, tt + 1]
        den = c0 - 2 * c1 + c2
        tf = tt + np.where(den != 0, 0.5 * (c0 - c2) / np.where(den != 0, den, 1), 0)
        out[idx[ok]] = sr / tf
    return out


def pitch_stats(src, sr=SR):
    """一段人声（文件路径，或 sr 采样率的数组）的音高：中位数、10%–90% 范围、有声秒数。量不到就是 None。"""
    import numpy as np
    x = read_audio(src, sr) if isinstance(src, (str, Path)) else np.asarray(src, dtype=np.float64)
    f = f0_track(x, sr)
    v = f[~np.isnan(f)] if len(f) else f
    if not len(v):
        return {"音高中位数Hz": None, "音高10%–90%Hz": None, "有声秒数": 0.0}
    return {"音高中位数Hz": round(float(np.median(v)), 1),
            "音高10%–90%Hz": [round(float(np.percentile(v, 10)), 1), round(float(np.percentile(v, 90)), 1)],
            "有声秒数": round(len(v) * 0.02, 2)}


def semitones(hz, ref_hz):
    import math
    return 12 * math.log2(hz / ref_hz)


def speech_rate(text, seconds):
    """语速：字／秒（一个汉字、一个英文词、一个数字位各算一个，和对稿同一种数法；秒数是去掉首尾静音后的整段）。"""
    return len(tokens(text)) / seconds if seconds else None


def gate_settings(profile=None):
    """profile"音高把关"一节的阈值（没写的用本文件的默认值）。"""
    d = _load_profile(profile).get("音高把关") or {}
    return {"允许偏差半音": float(d.get("允许偏差半音", PITCH_TOL_ST)),
            "最多再录": int(d.get("最多再录", PITCH_RETAKES)),
            "有声不足秒不判": float(d.get("有声不足秒不判", PITCH_MIN_VOICED_S)),
            "语速允许偏差": float(d.get("语速允许偏差", RATE_TOL))}


def _load_profile(profile=None):
    if isinstance(profile, dict):
        return profile
    p = Path(profile) if profile else PROFILE
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def reference_for(cfg, profile=None, raised=None):
    """按配音配置在声音档案里找这个声音的参考音高、参考语速：{"音高Hz", "语速", "来自"}；找不到返回 None（不把关）。
    主声音（同一个声音 ID）分两档：语气里带了"抬高"那一句就用"带抬高那句"，没带就用"不带抬高那句"；
    raised 给了 True/False 就按它，不看语气。MiMo 声音复刻按参考音文件名对上备用声音。"""
    prof = _load_profile(profile)
    voice, clone = getattr(cfg, "voice", None), getattr(cfg, "clone_ref", None)
    for name, sec in prof.items():
        if not isinstance(sec, dict) or not isinstance(sec.get("参考"), dict):
            continue
        ref = sec["参考"]
        hit = (voice and sec.get("声音ID") == voice) or \
              (clone and sec.get("参考音") and Path(str(sec["参考音"])).name == Path(str(clone)).name)
        if not hit:
            continue
        if "带抬高那句" in ref:
            suffix = (sec.get("每章语气后面都加这一句") or "").strip()
            up = raised if raised is not None else bool(suffix and suffix in (getattr(cfg, "style", None) or ""))
            r = ref["带抬高那句" if up else "不带抬高那句"]
            return {"音高Hz": r.get("音高Hz"), "语速": r.get("语速字每秒"),
                    "来自": f"{name}（{'带' if up else '不带'}抬高那句）：{r.get('来自', '')}"}
        return {"音高Hz": ref.get("音高Hz"), "语速": ref.get("语速字每秒"), "来自": f"{name}：{ref.get('来自', '')}"}
    return None


def pitch_verdict(stats, ref_hz, tol=PITCH_TOL_ST, min_voiced=PITCH_MIN_VOICED_S):
    """音高把关的判断：{"音高中位数Hz", "参考Hz", "偏差半音", "超出", "说明"}。有声太短或量不到时不判（超出=False）。"""
    hz, vs = stats.get("音高中位数Hz"), stats.get("有声秒数") or 0
    out = {"音高中位数Hz": hz, "参考Hz": ref_hz, "有声秒数": vs, "偏差半音": None, "超出": False}
    if not ref_hz:
        out["说明"] = "没有参考音高，不判"
    elif not hz or vs < min_voiced:
        out["说明"] = f"有声只有 {vs:.1f} 秒，量不准，不判"
    else:
        st = semitones(hz, ref_hz)
        out["偏差半音"] = round(st, 2)
        out["超出"] = abs(st) > tol
        if out["超出"]:
            out["说明"] = f"比参考{'高' if st > 0 else '低'} {abs(st):.1f} 个半音（允许 {tol:g}）"
    return out


def rate_verdict(text, seconds, ref_rate, tol=RATE_TOL):
    """语速：{"字每秒", "参考", "相差", "标出"}；只标出，不重录。"""
    r = speech_rate(text, seconds)
    out = {"字每秒": round(r, 2) if r else None, "参考": ref_rate, "相差": None, "标出": False}
    if r and ref_rate:
        d = r / ref_rate - 1
        out["相差"] = f"{d * 100:+.0f}%"
        out["标出"] = abs(d) > tol
    return out


# ---------------------------------------------------------------- 整段一次合成后按章切开（2026-11-01 加）


def transcribe_words(wav_path, work_dir, prompt=""):
    """逐词时间：[{"w": 词, "s": 起秒, "e": 止秒}]。设置和 transcribe 一样，另开 --word-timestamps。
    结果按音频文件名存在 work_dir（和 transcribe 的 json 不同名），再调直接读。"""
    wav_path, work = Path(wav_path), Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    name = wav_path.stem + "_words"
    out = work / f"{name}.json"
    if not out.exists():
        env = dict(os.environ, HF_HUB_OFFLINE="1")
        for k in ("MIMO_API_KEY", "GCP_ACCESS_TOKEN", "GEMINI_API_KEY"):
            env.pop(k, None)
        cmd = [str(WHISPER_BIN), str(wav_path), "--model", WHISPER_MODEL, "--language", "zh",
               "--condition-on-previous-text", "False", "--word-timestamps", "True", "--output-format", "json",
               "--output-dir", str(work), "--output-name", name, "--verbose", "False"]
        if prompt:
            cmd += ["--initial-prompt", prompt]
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if r.returncode or not out.exists():
            raise RuntimeError(f"Whisper（逐词）失败：{(r.stderr or r.stdout)[-400:]}")
    d = json.loads(out.read_text(encoding="utf-8"))
    return [{"w": w["word"].strip(), "s": float(w["start"]), "e": float(w["end"])}
            for seg in d.get("segments", []) for w in seg.get("words", []) if w["word"].strip()]


def chapter_cuts(texts, words, x, sr=SR, quiet_db=-45.0, pad=0.35):
    """整段录音按章切开：texts 是各章念的字（念法），words 是 transcribe_words 的结果，x 是整段音频（sr 采样率）。
    做法：两边都拉成同一种写法（tokens），逐字对齐（difflib）；第 i 章最后一个对上的字说完、第 i+1 章第一个对上的字开口，
    在这两个时刻之间（前后各放宽 pad 秒）找最长的一段静音（10 毫秒一窗，低于 quiet_db），切在它正中间。
    返回 [{"秒": 切点, "静音秒": 这段静音多长, "上章末字止": …, "下章首字起": …, "对上": True/False}]，共 len(texts)-1 个。"""
    import difflib
    import numpy as np
    ref, owner = [], []
    for i, t in enumerate(texts):
        tk = tokens(t)
        ref += tk
        owner += [i] * len(tk)
    hyp, times = [], []
    for w in words:
        tk = tokens(w["w"])
        for k, c in enumerate(tk):
            a = w["s"] + (w["e"] - w["s"]) * k / len(tk)
            hyp.append(c)
            times.append((a, w["s"] + (w["e"] - w["s"]) * (k + 1) / len(tk)))
    hit = {}
    for a, b, n in difflib.SequenceMatcher(None, ref, hyp, autojunk=False).get_matching_blocks():
        for k in range(n):
            hit[a + k] = times[b + k]
    win = int(sr * 0.01)
    m = len(x) // win
    db = 20 * np.log10(np.sqrt((x[:m * win].reshape(m, win) ** 2).mean(axis=1)) + 1e-9)
    total = len(x) / sr
    cuts = []
    for i in range(len(texts) - 1):
        last = [hit[k] for k in range(len(ref)) if owner[k] == i and k in hit]
        first = [hit[k] for k in range(len(ref)) if owner[k] == i + 1 and k in hit]
        e_i = last[-1][1] if last else None
        s_n = first[0][0] if first else None
        lo = (e_i if e_i is not None else (s_n or 0) - 2.0) - pad
        hi = (s_n if s_n is not None else (e_i or total) + 2.0) + pad
        if hi <= lo:
            lo, hi = hi - pad, lo + pad
        a, b = max(0, int(lo / 0.01)), min(m, int(hi / 0.01) + 1)
        best, run_start = (0, None), None
        for j in range(a, b + 1):
            q = j < b and db[j] < quiet_db
            if q and run_start is None:
                run_start = j
            elif not q and run_start is not None:
                if j - run_start > best[0]:
                    best = (j - run_start, run_start)
                run_start = None
        if best[1] is None:                       # 一点静音都没有：切在这一段里最安静的一窗
            j = a + int(np.argmin(db[a:b])) if b > a else int(((e_i or 0) + (s_n or 0)) / 2 / 0.01)
            cut, quiet = j * 0.01 + 0.005, 0.0
        else:
            cut, quiet = (best[1] + best[0] / 2) * 0.01, best[0] * 0.01
        cuts.append({"秒": round(cut, 3), "静音秒": round(quiet, 2),
                     "上章末字止": round(e_i, 2) if e_i is not None else None,
                     "下章首字起": round(s_n, 2) if s_n is not None else None,
                     "对上": e_i is not None and s_n is not None and (e_i - 0.15) <= cut <= (s_n + 0.15)})
    return cuts


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3:
        ref = Path(sys.argv[1]).read_text(encoding="utf-8")
        hyp = transcribe(sys.argv[2])
        print(json.dumps(check(ref, hyp), ensure_ascii=False, indent=1))
    else:
        print("用法：python pipeline/tts_qc.py 原稿.txt 音频.wav")
