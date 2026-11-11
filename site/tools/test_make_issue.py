#!/usr/bin/env python3
"""make_issue_v3.py 的对照测试（v3.2）：10-31 用新写稿格式（site/tools/fixtures/2026-10-31.json）自动生成配置，
和手写配置各组装一次，逐项比对两份页面数据（issue.js）；再故意塞几个编造的数字，看生成器会不会拦下来。

用法（在项目根目录 frontier-daily/ 下）：
    ~/.venvs/frontier-daily/bin/python site/tools/test_make_issue.py
草稿都在项目外的 ~/.cache/frontier-daily/make_issue_test/；项目里的文件不改。通过时退出码为 0。
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DAY = "2026-10-31"
ISSUE = os.path.join(ROOT, "测试版", DAY)
FIX = os.path.join(HERE, "fixtures", DAY + ".json")
POD = "05_配音/v3_Claude稿_Gemini配音_带音效"
SCR = os.path.expanduser("~/.cache/frontier-daily/make_issue_test")
PY = os.path.expanduser("~/.venvs/frontier-daily/bin/python")
IGNORE = {"meta", "fonts_css"}           # 生成时间、字体 CSS（按字截取，内容一样时也会因顺序不同略有差别）


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if r.returncode:
        sys.exit("命令失败：%s\n%s" % (" ".join(cmd[1:3]), (r.stderr or r.stdout)[-1500:]))
    return r.stdout


def issue_data(site):
    s = open(os.path.join(site, "issues", DAY, "issue.js"), encoding="utf-8").read()
    return json.loads(s[s.index("= {") + 2:s.rindex(";")])


def diff(a, b, path="", out=None):
    out = [] if out is None else out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if not path and k in IGNORE:
                continue
            if k not in a:
                out.append(("只在自动版", path + "." + k, b[k]))
            elif k not in b:
                out.append(("只在手写版", path + "." + k, a[k]))
            else:
                diff(a[k], b[k], path + "." + k, out)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, "%s[%d]" % (path, i), out)
    elif a != b:
        out.append(("不同", path, (a, b)))
    return out


def main():
    if not (os.path.exists(FIX) and os.path.isdir(ISSUE)):     # 旧期数据、测试版/ 只在私有仓库（2026-11 拆仓库）
        print("跳过：%s 或 %s 不在（往期内容只在私有仓库；把私有仓库的 site/tools/fixtures/、测试版/ 拷进来再跑）" % (os.path.relpath(FIX, ROOT), os.path.relpath(ISSUE, ROOT)))
        sys.exit(0)
    if os.path.isdir(SCR):
        shutil.rmtree(SCR)
    os.makedirs(SCR)
    gen = os.path.join(SCR, DAY + ".py")
    print(run([PY, os.path.join(HERE, "make_issue_v3.py"), "--day", DAY, "--fixture", FIX, "--images", "06_配图/v3.1",
               "--podcast", POD, "--out", gen]).strip())
    run([PY, os.path.join(HERE, "build_v3.py"), ISSUE, "--out", os.path.join(SCR, "hand"), "--podcast", POD])
    run([PY, os.path.join(HERE, "build_v3.py"), ISSUE, "--config", gen, "--out", os.path.join(SCR, "auto"), "--podcast", POD])
    A, B = issue_data(os.path.join(SCR, "hand")), issue_data(os.path.join(SCR, "auto"))
    d = diff(A, B)
    print("\n手写配置 vs 自动配置：页面数据有 %d 处不同" % len(d))
    for kind, p, v in d:
        print("  %s %s：%s" % (kind, p, json.dumps(v, ensure_ascii=False)[:160]))
    # 允许的差别：预告按日期排序后先后变了（以及多出 date_iso / sort_date 两个字段）
    allowed = [x for x in d if x[1].startswith(".watch")]
    other = [x for x in d if not x[1].startswith(".watch")]
    hw = [(w["when_zh"], w["text_zh"]) for w in A["watch"]]
    aw = [(w["when_zh"], w["text_zh"]) for w in B["watch"]]
    same_set = sorted(hw) == sorted(aw)
    print("预告：手写顺序 %s\n      自动顺序 %s（按日期排）；条目%s" % (" → ".join(h for h, _ in hw), " → ".join(h for h, _ in aw),
                                                       "相同" if same_set else "不同！"))

    # 反例：编造的数字必须被拦下
    fx = json.load(open(FIX, encoding="utf-8"))
    fx["page"]["numbers"][0]["zh"]["to"] = 230                 # 事件卡里没有 230 / 23
    fx["page"]["charts"]["drops-1030"]["items"][2]["v"] = 12.5  # 高通实际 11.12
    fx["page"]["watch"][0]["refs"] = [["E019", "F1", "下下周"]]   # 核对片段对不上 → 去掉这条
    bad = os.path.join(SCR, "bad.json")
    json.dump(fx, open(bad, "w", encoding="utf-8"), ensure_ascii=False)
    r = subprocess.run([PY, os.path.join(HERE, "make_issue_v3.py"), "--day", DAY, "--fixture", bad, "--images", "06_配图/v3.1",
                        "--out", os.path.join(SCR, "bad.py")], capture_output=True, text=True, cwd=ROOT)
    strict_ok = r.returncode == 1 and r.stdout.count("错误：") == 2 and not os.path.exists(os.path.join(SCR, "bad.py"))
    print("反例（严格）：退出码 %d，报错 %d 处，%s" % (r.returncode, r.stdout.count("错误："), "已拦下" if strict_ok else "没拦住！"))
    r2 = subprocess.run([PY, os.path.join(HERE, "make_issue_v3.py"), "--day", DAY, "--fixture", bad, "--images", "06_配图/v3.1",
                         "--out", os.path.join(SCR, "bad.py"), "--lenient"], capture_output=True, text=True, cwd=ROOT)
    lenient_ok = r2.returncode == 0 and "今日数字 4" in r2.stdout and "图表 5" in r2.stdout and "预告 4" in r2.stdout
    print("反例（--lenient）：%s" % ("去掉了 1 个数字、1 张图、1 条预告，照常写出配置" if lenient_ok else "结果不对：\n" + r2.stdout[-800:]))
    ok = not other and same_set and strict_ok and lenient_ok
    print("结果：%s" % ("通过（除预告按日期重新排序外，两份页面数据一致）" if ok else "不通过"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
