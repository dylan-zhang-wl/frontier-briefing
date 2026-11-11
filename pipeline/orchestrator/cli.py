"""./fd 的命令行：doctor、run、status。"""
import argparse
import sys

from .common import EDITIONS

USAGE = """./fd <子命令>

  ./fd doctor                                  体检：软件、登录、密钥在不在（只查不改，不显示密钥）
  ./fd run --date 2026-11-02                    跑一期：做过的步骤跳过，停在哪就从哪接着跑
  ./fd run --date 2026-11-02 --dry-run          只列每步要做什么、哪些会跳过、估计花多少钱（不动任何文件）
  ./fd status --date 2026-11-02                 这一期每一步的状态和原因

说明：文档/方案/总调度说明.md
"""


def build_parser():
    ap = argparse.ArgumentParser(prog="fd", description="每日AI科技前沿简报 · 总调度", usage=USAGE,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", metavar="子命令")
    sub.add_parser("doctor", help="体检（只查不改）")

    def common(p):
        p.add_argument("--date", required=True, help="哪一期，YYYY-MM-DD")
        p.add_argument("--issue-dir", help="期目录（默认 测试版/<日期>）；测试时指向副本。用了它，事件库、账本默认也放在副本旁边")
        p.add_argument("--edition", choices=sorted(EDITIONS), help="版别（默认按星期几：周一到周五工作日、周六深度、周日深谈）")
        p.add_argument("--db", help="往期事件库目录（默认 测试版/往期事件库/）")
        p.add_argument("--ledger-dir", help="月度账本目录（默认 测试版/月度账本/；测试上限时指向假账本）")

    r = sub.add_parser("run", help="跑一期")
    common(r)
    r.add_argument("--from", dest="from_step", help="从第几步开始（编号、英文键或中文名；前面的步骤不查）")
    r.add_argument("--until", help="跑到第几步为止")
    r.add_argument("--dry-run", action="store_true", help="只列计划和估计花费，不动任何文件")
    r.add_argument("--offline", action="store_true", help="只用缓存、不联网、预算 0（测试用）")
    r.add_argument("--budget-usd", type=float, default=0.6, help="这一期 Gemini 配音最多花多少美元（默认 0.6）")
    r.add_argument("--redo", help="强制重做这几步，逗号分隔，如 web,video")
    r.add_argument("--lenient", action="store_true", help="网页数字核不上时去掉那几项照常出（最后一级兜底）")
    r.add_argument("--skip-images", action="store_true", help="缺配图不等：网页用主题色封面，视频那几块不带图")
    r.add_argument("--use-backup", action="store_true", help="配音直接用 MiMo 备用声音")
    r.add_argument("--no-preview", action="store_true", help="视频不录预览 MP4（省 2–3 分钟）")
    r.add_argument("--verbose", action="store_true", help="把各步程序的输出全打在屏幕上（默认只写进 logs/）")

    s = sub.add_parser("status", help="这一期每一步的状态")
    common(s)
    return ap


def main(argv):
    ap = build_parser()
    a = ap.parse_args(argv)
    a.argv = argv
    if a.cmd == "doctor":
        from .doctor import main as doctor
        return doctor()
    if a.cmd == "run":
        from .runner import run_issue
        return run_issue(a, dry_run=a.dry_run)
    if a.cmd == "status":
        from .runner import status
        return status(a)
    print(USAGE)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
