#!/usr/bin/env python3
"""网页 v3 边界测试（v3.2）：把 10-31 这一期的配置改成几种“极端的一天”，各组装一次，再用浏览器打开检查。

每天自动出刊时，条目数、配图、视频、播客都可能多一点少一点；这里一次把这些情况都试一遍：
    minimal   0 条头条、1 条要闻、1 条快讯、0 条预告、0 对对照、0 个今日数字、全部缺图、没有视频也没有播客
    maximal   3 条头条、6 条快讯、5 条预告、3 对对照（其中一对关系写了词表外的词、一对没有说明）、部分缺图
    long      超长标题（中英文、含 60 个字母不断开的长词）、超长预告时间、1 条预告、1 对对照、对照没写关系
    no_video  有播客没有视频；对照关系用“对抗、合作、拉锯”
    no_pod    有视频没有播客；对照关系用“互补、跟进、分化”，其中“跟进”由国内一方领先
    dialog    周日两人对谈：播客稿每行以“甲：”“乙：”开头（把 10-31 的人声分块改写成两人轮流），
              各条“听这一段”的时刻要和原来的单人稿对得上（再用原播客组装一次对照）：有对齐数据时同一章、差不到 1 秒
              （对谈版没有人声版可校准停顿，11-06 起会差零点几秒），没有对齐数据时逐条相同
检查：在 390 像素宽（中文、英文）和 1440 像素宽（中文）下打开，滚到底再回来；
     不能有页面报错或控制台错误、不能横向滚动、不能有元素伸出屏幕；该隐藏的版块要隐藏、条数要对。

用法（在项目根目录 frontier-daily/ 下）：
    ~/.venvs/frontier-daily/bin/python site/tools/test_v3_edge.py            # 全部情况
    ~/.venvs/frontier-daily/bin/python site/tools/test_v3_edge.py long       # 只跑某几种
草稿都放在项目外的 ~/.cache/frontier-daily/test_v3_edge/（每次重来）；项目里的文件一个都不改。
浏览器用 shoot_v3.js 同一套 Playwright（PW 环境变量可改），本机 Chrome。全部通过时退出码为 0。
"""
import copy
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DATE = "2026-10-31"
REAL_CFG = os.path.join(HERE, "v3_issues", DATE + ".py")
PODCAST = "05_配音/v3_Claude稿_Gemini配音_带音效"


def sample_issue(day, need):
    """完整样期：仓库的 测试版/ 只存跨天要用的文字（选题、事件卡、文稿），没有配音、配图、网页、视频。
    按顺序找有 need 的那一份：环境变量 FD_SAMPLE_ROOT/<日期>、本机资料/归档/mini试运行_1031-1109/<日期>
    （mini 试运行那周的原件，只在本机、靠 iCloud 同步，不进 git）、测试版/<日期>。都没有返回 None（11-09 晚加）。"""
    bases = ([os.path.expanduser(os.environ["FD_SAMPLE_ROOT"])] if os.environ.get("FD_SAMPLE_ROOT") else []) + [
        os.path.join(ROOT, "本机资料", "归档", "mini试运行_1031-1109"), os.path.join(ROOT, "测试版")]
    return next((os.path.join(b, day) for b in bases if os.path.exists(os.path.join(b, day, need))), None)


REAL = sample_issue(DATE, os.path.join(PODCAST, "chapters.json")) or os.path.join(ROOT, "测试版", DATE)
SCRATCH = os.path.expanduser("~/.cache/frontier-daily/test_v3_edge")
PY = os.path.expanduser("~/.venvs/frontier-daily/bin/python")
PW = os.environ.get("PW") or os.path.expanduser("~/.npm/_npx/9833c18b2d85bc59/node_modules/playwright")
LINK = ["01_获取", "02_选题", "03_事件卡", "04_文稿", "06_配图", "08_网页v2"]   # 只读，用软链接接过来

LONG_ZH = "这是一条特意写得非常非常长的标题用来测试页面在极端情况下能否正常换行而不会横向溢出或者把版式撑坏还要再长一些才够"
LONG_EN = ("An Extraordinarily Long Headline About Supercalifragilisticexpialidociousinfrastructurefinancingcommitments "
           "That Keeps Going and Going to Test Wrapping on Small Screens")


def web_variant(case):
    """按情况改网页稿（只改条目多少和标题长短，事实不动）。"""
    w = json.load(open(os.path.join(REAL, "04_文稿", "claude_网页.json"), encoding="utf-8"))
    secs = {s["kind"]: s for s in w["sections"]}

    def clone(item, new_id, **kw):
        x = copy.deepcopy(item)
        x["id"] = new_id
        x.update(kw)
        return x
    if case == "minimal":
        secs["headline"]["items"] = []
        secs["brief"]["items"] = secs["brief"]["items"][:1]
        secs["flash"]["items"] = secs["flash"]["items"][:1]
        secs["teaser"]["items"] = []
    elif case == "maximal":
        b = secs["brief"]["items"]
        secs["headline"]["items"].append(clone(b[1], "X101", title_zh="（测试）第三条头条：" + b[1]["title_zh"]))
        f = secs["flash"]["items"]
        f += [clone(f[0], "X201", title_zh="（测试）第五条快讯：" + f[0]["title_zh"]),
              clone(f[1], "X202", title_zh="（测试）第六条快讯：" + f[1]["title_zh"])]
    elif case == "long":
        h = secs["headline"]["items"]
        h[0]["title_zh"], h[0]["title_en"] = LONG_ZH, LONG_EN
        h[1]["title_zh"] = LONG_ZH + "第二条"
        for it in secs["brief"]["items"] + secs["flash"]["items"] + secs["cn_intl"]["items"]:
            it["title_zh"] = it["title_zh"] + "——" + LONG_ZH[:30]
            it["title_en"] = it["title_en"] + " — " + LONG_EN[:80]
        w["daily_card"]["headlines"][0]["zh"] = LONG_ZH[:40]
    return w


def cfg_variant(case, web_path):
    """每期配置：先照抄 10-31 的，再按情况改几项。"""
    lines = ["# 边界测试自动生成（test_v3_edge.py），用完即删",
             "_real = %r" % REAL_CFG,
             "exec(compile(open(_real, encoding='utf-8').read(), _real, 'exec'))",
             "WEB = %r" % web_path]
    if case == "minimal":
        lines += ["IMAGES = {}", "WATCH = []", "PAIRS = []", "NUMBERS = []", "VIDEO_SCRIPT = None"]
    elif case == "maximal":
        lines += ["IMAGES = {k: v for k, v in IMAGES.items() if k not in ('card', 'E002')}",
                  "IMAGES['E003'] = dict(IMAGES['E003'], file='不存在的图.png')",
                  "PAIRS = PAIRS + [dict(intl='E001', cn='E038', relation='敌对', label_zh='（测试）第三对')]"]
    elif case == "long":
        lines += ["WATCH = [dict(WATCH[0], when_zh='获得全部必要监管审批之后的某个时间点（传）', "
                  "when_en='Some time after every regulatory approval is granted (rumored)', "
                  "text_zh=WATCH[0]['text_zh'] * 3, text_en=WATCH[0]['text_en'] * 3)]",
                  "PAIRS = [{k: v for k, v in PAIRS[1].items() if k not in ('relation', 'label_zh', 'label_en')}]",
                  "IMAGES = {k: v for k, v in IMAGES.items() if k != 'E001'}"]
    elif case == "no_video":
        lines += ["VIDEO_SCRIPT = None", "WATCH = WATCH[:2]",
                  "PAIRS = [dict(PAIRS[0], relation='对抗'), dict(PAIRS[1], relation='合作'), "
                  "dict(intl='E001', cn='E038', relation='拉锯', label_zh='（测试）拉锯')]"]
    elif case == "no_pod":
        lines += ["WATCH = WATCH[1:4]",
                  "PAIRS = [dict(PAIRS[0], relation='互补'), dict(PAIRS[1], relation='跟进', lead='cn'), "
                  "dict(intl='E001', cn='E038', relation='分化', label_zh='（测试）分化')]"]
    return "\n".join(lines) + "\n"


# 每种情况：页面上应当有 / 不该有的版块，以及几个计数（选择器 → 个数）
EXPECT = {
    "minimal": dict(absent=["#sec-headline", "#sec-watch", "#sec-pairs", "#sec-media", "#sec-numbers"],
                    present=["#sec-brief", "#sec-flash", "#sec-term", ".hero-fig.cover", ".sl-fig.cover"],
                    counts={".frow": 1, "#sec-brief .slide": 1}),
    "maximal": dict(present=["#sec-headline", "#sec-watch", "#sec-pairs", "#sec-media", ".sl-fig.cover"],
                    counts={"#sec-headline .pg": 3, ".frow": 6, ".wn": 5, "#sec-pairs .pg": 3, ".rg-echo": 2, ".rg-race": 1}),
    "long": dict(present=[".wtl.single", "#sec-pairs .stage.single", ".rg-echo"], counts={".wn": 1}),
    "no_video": dict(absent=["#video-root", "[data-act=\"watch\"]"], present=["#pod-root", ".rg-clash", ".rg-link", ".rg-tug"],
                     counts={".wn": 2}),
    "dialog": dict(present=["#pod-root", "[data-act=\"listen\"]"], counts={}),
    "no_pod": dict(absent=["#pod-root", "[data-act=\"listen\"]"], present=["#video-root", ".rg-fit", ".rg-follow.flip", ".rg-split"],
                   counts={".wn": 3}),
}

CHECK_JS = r"""
const { chromium } = require(process.env.PW);
const cases = JSON.parse(process.argv[2]);
(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const out = [];
  for (const c of cases) {
    for (const v of [{ w: 390, h: 844, lang: 'zh' }, { w: 390, h: 844, lang: 'en' }, { w: 1440, h: 900, lang: 'zh' }]) {
      const mob = v.w < 600;
      const ctx = await browser.newContext({ viewport: { width: v.w, height: v.h }, deviceScaleFactor: 1, isMobile: mob, hasTouch: mob });
      await ctx.addInitScript(l => { try { localStorage.setItem('fd.lang', l); } catch (e) {} }, v.lang);
      const page = await ctx.newPage();
      const errs = [];
      page.on('pageerror', e => errs.push('pageerror: ' + String(e).slice(0, 200)));
      page.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text().slice(0, 200)); });
      page.on('requestfailed', r => { const f = r.failure(); if (!(f && /ERR_ABORTED/.test(f.errorText) && /\.mp3$/.test(r.url()))) errs.push('failed: ' + r.url().split('/').slice(-2).join('/')); });
      await page.goto(c.url, { waitUntil: 'load' });
      await page.evaluate(async () => { await document.fonts.ready; });
      // 慢慢滚到底再回来：让图表、视频、懒加载的图片都真的加载一遍
      const H = await page.evaluate(() => document.documentElement.scrollHeight);
      for (let y = 0; y < H; y += 700) { await page.evaluate(y => window.scrollTo(0, y), y); await page.waitForTimeout(120); }
      await page.waitForTimeout(1500);
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.waitForTimeout(300);
      const r = await page.evaluate((exp) => {
        const vw = document.documentElement.clientWidth, sw = document.documentElement.scrollWidth;
        const clipAnc = el => { for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) { const cs = getComputedStyle(a); if (cs.overflowX !== 'visible' || cs.position === 'fixed') return a; } return null; };
        const bad = [];
        for (const el of document.querySelectorAll('body *')) {
          if (el.closest('#bg, #tip, #mini, svg, .sr')) continue;
          const cs = getComputedStyle(el);
          if (cs.visibility === 'hidden' || cs.display === 'none') continue;
          const b = el.getBoundingClientRect();
          if (!b.width || !b.height) continue;
          if (b.right > vw + 1 || b.left < -1) {
            const a = clipAnc(el);
            if (a) { const ab = a.getBoundingClientRect(); if (ab.right <= vw + 1 && ab.left >= -1) continue; }
            bad.push((el.closest('.v3p') ? '[视频v3] ' : '') + (el.id ? '#' + el.id : el.tagName.toLowerCase() + '.' + [...el.classList].join('.')) + ' → ' + Math.round(b.left) + '…' + Math.round(b.right));
          }
        }
        const miss = [], extra = [], cnt = [];
        (exp.present || []).forEach(s => { if (!document.querySelector(s)) miss.push(s); });
        (exp.absent || []).forEach(s => { if (document.querySelector(s)) extra.push(s); });
        Object.entries(exp.counts || {}).forEach(([s, n]) => { const k = document.querySelectorAll(s).length; if (k !== n) cnt.push(s + ' 应为 ' + n + '，实际 ' + k); });
        const foot = (document.querySelector('#foot') || {}).textContent || '';
        return { overflowX: sw - vw, bad: bad.slice(0, 8), badN: bad.length, miss, extra, cnt, foot: foot.trim() };
      }, c.expect);
      const ok = !errs.length && r.overflowX <= 0 && !r.badN && !r.miss.length && !r.extra.length && !r.cnt.length && /AI/.test(r.foot);
      out.push({ case: c.name, view: v.w + ' ' + v.lang, ok, errors: errs, ...r });
      await ctx.close();
    }
  }
  console.log(JSON.stringify(out));
  await browser.close();
})();
"""


def dialog_podcast(base):
    """把 10-31 的播客改成“两人对谈”的样子：同一段音频和章节，人声分块的原稿每行加上“甲：”“乙：”轮流。"""
    real = os.path.join(REAL, PODCAST)
    pod, voice = os.path.join(base, "dialog_podcast"), os.path.join(base, "dialog_voice")
    os.makedirs(pod)
    os.makedirs(voice)
    os.symlink(os.path.join(real, "episode.mp3"), os.path.join(pod, "episode.mp3"))
    shutil.copy2(os.path.join(real, "chapters.json"), os.path.join(pod, "chapters.json"))
    mix = json.load(open(os.path.join(real, "qc.json"), encoding="utf-8"))
    vsrc = mix["人声来源"] if os.path.isabs(mix["人声来源"]) else os.path.join(ROOT, mix["人声来源"])
    if not os.path.exists(vsrc) and mix["人声来源"].startswith("测试版/"):
        # 记的是"测试版/<日期>/…"（相对项目根）；完整样期不在仓库的 测试版/ 时，到样期所在的文件夹里找（11-09 晚加）
        vsrc = os.path.join(os.path.dirname(REAL), mix["人声来源"].split("/", 1)[1])
    vq = json.load(open(os.path.join(vsrc, "qc.json"), encoding="utf-8"))
    k = 0
    for b in vq["各块"]:
        lines = []
        for line in (b.get("原稿") or "").split("\n"):
            if line.strip():
                lines.append("甲乙"[k % 2] + "：" + line)
                k += 1
        b["原稿"] = "\n".join(lines)
    json.dump(vq, open(os.path.join(voice, "qc.json"), "w", encoding="utf-8"), ensure_ascii=False)
    mix["人声来源"] = voice
    json.dump(mix, open(os.path.join(pod, "qc.json"), "w", encoding="utf-8"), ensure_ascii=False)
    return pod


def listen_map(site):
    s = open(os.path.join(site, "issues", DATE, "issue.js"), encoding="utf-8").read()
    d = json.loads(s[s.index("= {") + 2:s.rindex(";")])
    return {k: v.get("listen") for k, v in d["stories"].items()}, [c["title_zh"] for c in d["media"]["podcast"]["chapters"]]


def listen_chapter_starts(site):
    s = open(os.path.join(site, "issues", DATE, "issue.js"), encoding="utf-8").read()
    d = json.loads(s[s.index("= {") + 2:s.rindex(";")])
    return [float(c.get("start") or 0) for c in d["media"]["podcast"]["chapters"]]


def main():
    want = sys.argv[1:] or list(EXPECT)
    unknown = [c for c in want if c not in EXPECT]
    if unknown:
        sys.exit("不认识的情况：%s（可选：%s）" % ("、".join(unknown), "、".join(EXPECT)))
    if not os.path.exists(os.path.join(REAL, PODCAST, "chapters.json")):
        print("跳过：%s 的完整样期（%s）不在。仓库的 测试版/ 只存文字；要跑这个测试，设 FD_SAMPLE_ROOT 指向完整样期所在的文件夹，"
              "或在有 本机资料/归档/mini试运行_1031-1109/ 的本机上跑" % (DATE, PODCAST))
        sys.exit(0)
    if not os.path.exists(REAL_CFG):         # 旧期网页配置只在私有仓库（2026-11 拆仓库）
        print("跳过：%s 不在（往期内容只在私有仓库；把私有仓库的 site/tools/v3_issues/ 拷进来再跑）" % os.path.relpath(REAL_CFG, ROOT))
        sys.exit(0)
    if os.path.isdir(SCRATCH):
        shutil.rmtree(SCRATCH)
    os.makedirs(SCRATCH)
    built, build_fails = [], []
    for case in want:
        base = os.path.join(SCRATCH, case)
        src = os.path.join(base, "src", DATE)      # 草稿期目录：除了要缺的那几样，其余都软链接到真目录
        os.makedirs(src)
        for d in LINK + (["05_配音"]) + ([] if case in ("minimal", "no_video") else ["11_视频v3"]):
            if os.path.exists(os.path.join(REAL, d)):
                os.symlink(os.path.join(REAL, d), os.path.join(src, d))
        web_path = os.path.join(base, "web.json")
        json.dump(web_variant(case), open(web_path, "w", encoding="utf-8"), ensure_ascii=False)
        cfg_path = os.path.join(base, "cfg.py")
        open(cfg_path, "w", encoding="utf-8").write(cfg_variant(case, web_path))
        out = os.path.join(base, "site")
        podcast = "05_配音/不存在的播客" if case in ("minimal", "no_pod") else PODCAST
        if case == "dialog":
            podcast = dialog_podcast(base)
        cmd = [PY, os.path.join(HERE, "build_v3.py"), src, "--config", cfg_path, "--out", out, "--podcast", podcast]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
        log = os.path.join(base, "build.log")
        open(log, "w", encoding="utf-8").write(r.stdout + "\n" + r.stderr)
        if r.returncode:
            print("✗ %-9s 组装失败，见 %s\n%s" % (case, log, (r.stderr or r.stdout)[-800:]))
            continue
        notes = [l for l in r.stdout.splitlines() if l.startswith(("注意", "缺图", "国内外对照", "预告看板："))]
        print("· %-9s 组装完成%s" % (case, ("：" + "；".join(notes)) if notes else ""))
        if case == "dialog":   # 用原来的单人播客再组装一次，“听这一段”的时刻和章节要对得上
            ref = os.path.join(base, "ref")
            rr = subprocess.run([PY, os.path.join(HERE, "build_v3.py"), src, "--config", cfg_path, "--out", ref, "--podcast", PODCAST],
                                capture_output=True, text=True, cwd=ROOT, check=True)
            (got, ch1), (exp, ch2) = listen_map(out), listen_map(ref)
            # 11-06 白天改：上午"听这一段"改成先按配音时的转写定位、再校准到人声版里的停顿（build_v3.py 的 para_times）。
            # 这里造的对谈版只换了稿子（每行加"甲：""乙："），人声目录里没有人声版 episode.mp3，校准停顿那一步做不了，
            # 落点就是转写的段首——和单人版差零点几秒（11-06 实测 0.1–0.8 秒，都在同一章、都在这一段开口之前），
            # 这是两条算法路径的正常差异，不是跳错。所以：单人版用上了对齐数据时，只要求同一章、差不到 1 秒；
            # 没有对齐数据（转写缓存过期、两边都退回按字数估算）时仍要求逐条相同。
            aligned = any("对齐" in ln for ln in rr.stdout.splitlines() if ln.startswith("听这一段的段首时间"))
            starts = listen_chapter_starts(ref)
            chap = lambda t: max([i for i, s in enumerate(starts) if s <= t + 1e-6] or [0])  # noqa: E731
            diff, near = {}, {}
            for k in exp:
                e, g = exp.get(k), got.get(k)
                if e == g:
                    continue
                if aligned and e is not None and g is not None and chap(e) == chap(g) and abs(g - e) < 1.0:
                    near[k] = round(g - e, 2)
                else:
                    diff[k] = (e, g)
            n = sum(v is not None for v in got.values())
            if diff or ch1 != ch2 or not n:
                print("✗ dialog    “听这一段”和单人稿不一致：%s；章节 %s" % (diff, "一致" if ch1 == ch2 else "不一致"))
                build_fails.append("dialog")
            elif near:
                print("✓ dialog    两人对谈稿：%d 条“听这一段”、%d 个章节和单人稿对得上；其中 %d 条差不到 1 秒、都在同一章"
                      "（对谈版没有人声版可校准停顿，落在转写的段首；最大差 %.1f 秒）" % (n, len(ch1), len(near), max(abs(v) for v in near.values())))
            else:
                print("✓ dialog    两人对谈稿：%d 条“听这一段”的时刻、%d 个章节都和单人稿一致" % (n, len(ch1)))
        built.append({"name": case, "url": "file://" + os.path.join(out, "index.html"), "expect": EXPECT[case]})
    if not built:
        sys.exit(1)
    js = os.path.join(SCRATCH, "check.js")
    open(js, "w", encoding="utf-8").write(CHECK_JS)
    r = subprocess.run(["node", js, json.dumps(built)], capture_output=True, text=True, env=dict(os.environ, PW=PW))
    if r.returncode:
        sys.exit("浏览器检查没跑起来：\n" + r.stderr[-1500:])
    res = json.loads(r.stdout.strip().splitlines()[-1])
    fails = 0
    for x in res:
        fails += not x["ok"]
        line = "%s %-9s %-7s 横向溢出 %s px · 伸出屏幕的元素 %d 个" % ("✓" if x["ok"] else "✗", x["case"], x["view"], x["overflowX"], x["badN"])
        print(line)
        for k, lab in (("errors", "报错"), ("bad", "伸出"), ("miss", "缺少"), ("extra", "不该有"), ("cnt", "计数")):
            if x.get(k):
                print("      %s：%s" % (lab, " | ".join(x[k])))
        if x["bad"] and all(b.startswith("[视频v3]") for b in x["bad"]):
            print("      （伸出去的是视频 v3 播放器自己的控制条：英文按钮更宽、site/v3/video3.css 的 .v3row 不换行；归做视频的那条线修）")
    total = len(res) + (len(want) - len(built))
    print("结果：%d 项里 %d 项通过；草稿在 %s" % (total, total - fails - (len(want) - len(built)), SCRATCH))
    sys.exit(1 if fails or build_fails or len(built) < len(want) else 0)


if __name__ == "__main__":
    main()
