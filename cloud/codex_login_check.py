#!/usr/bin/env python3
"""查 Codex 云端登录有没有失效（2026-11-09 加，代替流程文件里原来那行 grep）。

为什么改：原来只要画图日志（log_<id>.png.txt）里出现 401、unauthorized、refresh token 之类的字就报"登录失效"。
11-09 正式运行（42594242663）19 张图全画成了，还是报了失效：日志里 Codex 生成的文件名带一串编号
（exec-dad0f0bc-001e-4015-…），"4015" 里有 "401"。出错邮件因此多了一句"Codex 要重新登录"。

现在的判法：一张图只有同时满足两条才算"登录失效"——
  1. 没画成：日志旁边没有对应的图（log_X.png.txt 旁边没有 X.png，或者是空文件）；
  2. 日志里有登录出错的话：单独的 401（前后不紧挨字母、数字、连字符，编号里的 401 不算）、unauthorized、
     refresh token、could not be refreshed、log in again、sign in again、not logged in。
有一张这样的图，就在 --out 指定的文件里写一句话（出错邮件 cloud/release/notify.py 看这个文件在不在）；一张都没有就不写。
不读、不打印任何密钥：只看画图日志里的字，打印的只有图的名字。

11-14 加"额度用完"（ChatGPT 订阅 11-11 起是 Plus，有 5 小时和每周限额；经验库第五部分第 76 件②。
做法和公开仓库 frontier-briefing 11-11 那版同一个路子，认法按 Codex 官方的原话收紧了）：
  没画成、日志里没有登录出错、但有额度用完的话的图，记进 --quota-out（默认和 --out 同一个目录下的 codex_额度用完.txt）：
  第一行一句话，后面几行"网页=a""视频=b""第一次=…""依据=原话／宽认"给出错邮件读（notify.py 的 quota_info）。
  两种都有时只报登录失效（那个要你动手），不写额度的记号。
  认法分两档：
    原话：Codex 官方 CLI 用完额度时的报错（openai/codex 仓库 codex-rs/protocol/src/error.rs，2026-11-11 的提交 ed7ca22，
      11-14 查）：UsageLimitReachedError 一律以 "You’ve hit your usage limit" 开头，Plus 账号是
      "You’ve hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/settings/usage
      to purchase more credits or try again at 3:45 PM."，某个模型单独的限额是 "You’ve hit your usage limit for <模型>. Switch to
      another model now, …"；另有 QuotaExceeded "Quota exceeded. Check your plan and billing details."、工作区的
      "Your workspace is out of credits…""You hit your spend cap…"。codex exec 把它写在 stderr 的 "ERROR: …" 一行
      （codex-rs/exec/src/event_processor_with_human_output.rs），画图日志里原样有。日志里有这几句之一就算"原话"。
    宽认（待核）：没有原话，但带 error 字样的那几行里有 usage limit、rate limit、单独的 429、quota（11-11 公开仓库那版的认法）。
      只在带 error 的行里认：画图日志里原样抄着画图说明，新闻里的"quota""rate limit"不算。多半是被限流
      （"exceeded retry limit, last status: 429 Too Many Requests" 这类），邮件里写"多半"。真遇到一次再对着原文补准。
  网页图、视频图怎么分：日志在名字带"视频"的目录里（06_配图/视频/、11_视频v3_导演/）算视频图，其余算网页图。
  第一次在几点：画图日志第一行 "===== <时间> =====" 里的时间（video3_images.gen_codex 写的，UTC），读不到就用日志文件的修改时间。

用法：
    python cloud/codex_login_check.py 目录1 [目录2 …] --out 测试版/<日期>/logs/codex_登录失效.txt [--quota-out …/codex_额度用完.txt]
目录下面的子目录也查。退出码总是 0（这一步只记一笔，不让流程失败）。
测试：python3 -m unittest discover -s cloud/tests -v
"""
import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

LOGIN_ERR = re.compile(
    r"(?<![0-9A-Za-z-])401(?![0-9A-Za-z-])|unauthori[sz]ed|refresh[ _-]?token|could not be refreshed"
    r"|log ?in again|sign ?in again|not logged in", re.I)
MESSAGE = "Codex 云端登录失效（有图没画成，画图日志里有 401／refresh 失败）"
# 额度用完：官方原话（出处见文件开头）。只认撇号后面那段，Codex 写的 You’ve 用的是弯撇号，直撇号的也一样认得
QUOTA_ERR = re.compile(r"hit your usage limit|quota exceeded\. check your plan|workspace is out of credits|hit your spend cap", re.I)
# 宽认（待核）：只在带 error 字样的行里认这几个词
QUOTA_LOOSE = re.compile(r"usage[ _-]?limit|rate[ _-]?limit|(?<![0-9A-Za-z-])429(?![0-9A-Za-z-])|quota", re.I)
ERROR_LINE = re.compile(r"error", re.I)
QUOTA_MESSAGE = "Codex 额度用完（有图没画成，画图日志里有 Codex 额度用完的原话）"
QUOTA_LOOSE_MESSAGE = "Codex 多半是额度用完或被限流（有图没画成，画图日志的报错行里有 rate limit／429 一类的字样，没有官方原话，待核）"
QUOTA_NAME = "codex_额度用完.txt"
HEAD_TIME = re.compile(r"^===== (\S+) =====")


def image_for(log):
    """log_X.png.txt → 同一目录下的 X.png。"""
    name = log.name
    return log.with_name(name[len("log_"):-len(".txt")]) if name.startswith("log_") and name.endswith(".txt") else None


def _missing(dirs):
    """没画成的那几张：逐个给出 (目录, 日志文件, 图, 日志全文)。"""
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for log in sorted(d.rglob("log_*.png.txt")):
            img = image_for(log)
            if img is not None and img.is_file() and img.stat().st_size > 0:
                continue                      # 画成了：日志里有什么字都不算
            try:
                text = log.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            yield d, log, img, text


def failures(dirs):
    """返回 [(图的名字, 日志里第一处登录出错的话)]：没画成、而且日志里有登录出错的那几张。"""
    out = []
    for _, log, img, text in _missing(dirs):
        m = LOGIN_ERR.search(text)
        if m:
            out.append((img.name if img is not None else log.name, m.group(0)))
    return out


def quota_words(text):
    """日志里额度用完的话：(那句话, "原话"或"宽认")；都没有返回 None。原话优先（出处见文件开头）。"""
    m = QUOTA_ERR.search(text)
    if m:
        return m.group(0), "原话"
    for line in text.splitlines():
        if ERROR_LINE.search(line):
            m = QUOTA_LOOSE.search(line)
            if m:
                return m.group(0), "宽认"
    return None


def _when(log, text):
    """这张图那次调用的时间（UTC）：日志第一行的时间，读不到就用文件修改时间。"""
    m = HEAD_TIME.match(text)
    if m:
        try:
            return datetime.fromisoformat(m.group(1)).astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.fromtimestamp(log.stat().st_mtime, timezone.utc)


def quota_failures(dirs):
    """返回 [(图的名字, 日志里那句话, "网页"或"视频", 时间, "原话"或"宽认")]：没画成、日志里没有登录出错、但有额度用完的那几张。"""
    out = []
    for d, log, img, text in _missing(dirs):
        if LOGIN_ERR.search(text):
            continue                          # 登录出错的归登录失效
        q = quota_words(text)
        if q:
            rel = [d.name] + list(log.relative_to(d).parts[:-1])
            where = "视频" if any("视频" in p for p in rel) else "网页"
            out.append((img.name if img is not None else log.name, q[0], where, _when(log, text), q[1]))
    return out


def quota_text(bad):
    """额度用完的记号文件内容：第一行给人看，后面几行给 notify.py 读。有一张是原话就算"原话"。"""
    web = sum(1 for x in bad if x[2] == "网页")
    first = min(x[3] for x in bad)
    basis = "原话" if any(x[4] == "原话" for x in bad) else "宽认"
    return "\n".join([
        "%s：%d 张没画成（网页 %d 张、视频 %d 张），第一次在 %s UTC：%s" % (
            QUOTA_MESSAGE if basis == "原话" else QUOTA_LOOSE_MESSAGE, len(bad), web, len(bad) - web,
            first.strftime("%H:%M"), "、".join("%s（%s）" % (x[0], x[1]) for x in bad[:5])),
        "网页=%d" % web, "视频=%d" % (len(bad) - web), "第一次=%s" % first.strftime("%Y-%m-%d %H:%M"), "依据=%s" % basis, ""])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dirs", nargs="+", help="要查的目录（画图日志所在的目录，子目录也查）")
    ap.add_argument("--out", required=True, help="查到登录失效时写这个文件")
    ap.add_argument("--quota-out", help="查到额度用完时写这个文件（默认和 --out 同一个目录下的 %s）" % QUOTA_NAME)
    a = ap.parse_args(argv)
    bad = failures(a.dirs)
    if bad:
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(MESSAGE + "：" + "、".join("%s（%s）" % (n, w) for n, w in bad[:5]) + "\n", encoding="utf-8")
        print(MESSAGE + "：" + "、".join(n for n, _ in bad[:5]))
        return 0                              # 两种都有时按登录失效报（那个要你动手），不再写额度的记号
    print("没查到 Codex 登录失效的迹象（没画成的图日志里没有 401／refresh 失败）")
    quota = quota_failures(a.dirs)
    if quota:
        qout = Path(a.quota_out) if a.quota_out else Path(a.out).with_name(QUOTA_NAME)
        qout.parent.mkdir(parents=True, exist_ok=True)
        qout.write_text(quota_text(quota), encoding="utf-8")
        print(qout.read_text(encoding="utf-8").splitlines()[0])
    else:
        print("也没有额度用完的迹象（没画成的图日志里没有 Codex 额度用完的原话，报错行里也没有 rate limit／429／quota）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
