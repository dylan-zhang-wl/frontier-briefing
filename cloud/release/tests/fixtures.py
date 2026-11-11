"""测试用：在临时目录里造一期“全都过了”的期目录（文件和字段照 fd 真实写出来的样子），各测试再改坏某一处。"""
import json
from datetime import date
from pathlib import Path

GOOD_DAY = "2026-11-09"          # 星期一 → 工作日版

STEP_KEYS = ["fetch", "cluster", "ingest", "select", "cards", "write", "check", "review", "revise", "images",
             "voice", "mix", "web", "video", "web2", "accept", "report"]
ED = {"weekday": ("工作日版", "05_配音/播客_v3", "05_配音/播客_v3_带音效", [10.0, 15.0]),
      "saturday_deep": ("周六版（快讯＋单人深度）", "05_配音/周六_人声", "05_配音/周六_带音效", [10.0, 12.0]),
      "sunday_deep": ("周日版（Shirley、Dylan 双人深谈）", "05_配音/周日深谈_人声", "05_配音/周日深谈_带音效", [15.0, 17.0])}


def wj(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def edition_of(day):
    wd = date.fromisoformat(day).weekday()
    return "saturday_deep" if wd == 5 else "sunday_deep" if wd == 6 else "weekday"


def make_issue(root, day=GOOD_DAY, review=True):
    """返回期目录。月度账本放在 <root>/月度账本/。"""
    issue = Path(root) / day
    ed = edition_of(day)
    name, human, mixed, rng = ED[ed]
    steps = {}
    for k in STEP_KEYS:
        steps[k] = {"状态": "做完", "怎么来的": "跑了", "开始": "%s 05:42:31 GMT" % day, "结束": "%s 05:43:00 GMT" % day,
                    "说明": "", "提醒": [], "附加": {}}
    steps["voice"]["附加"] = {"决定": {"用备用": False, "原因": "", "播客预算": 0.5, "视频预算": 0.1, "本月已记": 1.5, "上限": 8.0},
                            "播客": "主声音", "视频旁白": "主声音", "视频引擎": "gemini"}
    steps["web"]["附加"] = {"播客": mixed}
    steps["web2"]["附加"] = {"带视频": True}
    steps["video"]["说明"] = "108.0 秒，6 章，对齐中位误差 0.103 秒"
    steps["check"]["说明"] = "读音表 过了；稿子 过了；视频分镜 过了；网页数字 过了；今日一词 过了"
    wj(issue / "logs" / "fd_state.json", {"说明": "测试", "步骤": steps, "运行记录": [
        {"开始": "%s 05:09:00 GMT" % day, "命令": "fd run --date %s" % day, "结果": "停在第 4 步", "结束": "%s 05:09:01 GMT" % day},
        {"开始": "%s 05:40:00 GMT" % day, "命令": "fd run --date %s" % day, "结果": "跑完", "结束": "%s 05:59:00 GMT" % day}]})
    wj(issue / "logs" / "验收.json", {"时间": "x", "没过": [], "提醒": []})
    wj(issue / "05_配音" / "视频旁白_v3" / "voice.json", {"engine": "gemini", "model": "gemini-3.8-flash-tts"})
    wj(issue / human / "usage.json", {"引擎": "gemini", "合计": {}})
    wj(issue / human / "qc.json", {"整集": {"时长把关": {"配完按实际": {"何时": "配完按实际", "时长分钟": rng[0] + 1, "区间分钟": rng, "通过": True}}}})
    wj(issue / "11_视频v3" / "video3_media.json", {"duration": 107.989})
    wj(issue / "花费.json", {"期": day, "条目": [], "合计美元": {"Gemini": 0.34, "MiMo": 0.0, "Codex": 0, "Claude": 0}})
    wj(Path(root) / "月度账本" / ("%s.json" % day[:7]), {"月份": day[:7], "上限美元（Gemini 配音）": 8.0,
                                                    "条目": [{"服务": "Gemini", "美元": 1.5}, {"服务": "MiMo", "美元": 0}]})
    (issue / "00_调度报告.md").write_text("# %s · %s · 调度报告\n\n生成于……\n" % (day, name), encoding="utf-8")
    (issue / "审片.md").write_text("# 审片 %s（%s）\n\n这期能放心看。\n\n## 要你留意的\n\n1. 没有。\n" % (day, name[:3]), encoding="utf-8")
    if review:
        wj(issue / "审片结论.json", {"日期": day, "版别": name[:4], "放行": True, "立即": [], "请你耳听": [],
                                  "过": 44, "不过": 7, "查不了": 2, "写于": "07:50"})
    return issue


def edit_json(p, fn):
    d = json.loads(Path(p).read_text(encoding="utf-8"))
    fn(d)
    wj(p, d)
