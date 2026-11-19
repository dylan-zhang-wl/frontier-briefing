#!/usr/bin/env python3
"""画播客节目封面（占位，待用户定）：3000×3000 JPEG，写到同目录 cover-3000.jpg。

2026-11-19 第一阶段用设计稿的做法 (a)：主题色（网页蓝 #0071e3）由深到浅的底，几团柔光，
中间两行大字“每日AI科技 / 前沿简报”，下面一条细线和小字 Frontier Briefing。字体用仓库里的 Noto Serif SC
（cloud/fonts/，SIL OFL 1.1，许可见同目录 LICENSE_NotoSerifCJK.txt）。不联网、不调用画图模型。

封面是固定文件，提交进仓库；发布时 podcast_feed.py 只是原样拷进上线包（发布环境没有 Pillow 也一定有节目封面）。
要换：改这里重画，或直接换掉 cover-3000.jpg（1400–3000 见方、RGB 的 JPEG）。苹果要求封面在缩略图大小也看得清，所以字少、字大。

用法（在仓库根目录，要 Pillow）：python cloud/deploy/podcast/make_cover.py
同一版 Pillow 两次画出来逐字节相同。
"""
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
FONTS = HERE.parent.parent / "fonts"
OUT = HERE / "cover-3000.jpg"
SIZE = 3000
TOP, BOTTOM = (6, 34, 82), (0, 113, 227)          # 深蓝 → 网页主题蓝 #0071e3
LINES = ("每日AI科技", "前沿简报")
SUB = "Frontier Briefing"


def main():
    s = SIZE
    # 底：从左上到右下由深到浅
    v = Image.linear_gradient("L").resize((s, s))                    # 上→下 0→255
    grad = ImageChops.add(v, v.transpose(Image.Transpose.ROTATE_90), scale=2.0)   # 加上左→右，除以 2：左上最深、右下最浅
    base = Image.composite(Image.new("RGB", (s, s), BOTTOM), Image.new("RGB", (s, s), TOP), grad)
    # 柔光：几个浅色圆，虚化后叠上去（像网页背景的光斑）
    glow = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(glow)
    for cx, cy, r, a in ((2350, 650, 900, 110), (500, 2500, 1000, 80), (1500, 1500, 700, 40)):
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=a)
    glow = glow.filter(ImageFilter.GaussianBlur(260))
    base = Image.composite(Image.new("RGB", (s, s), (120, 190, 255)), base, glow)

    draw = ImageDraw.Draw(base)
    big = ImageFont.truetype(str(FONTS / "NotoSerifSC-Black.otf"), 430)
    small = ImageFont.truetype(str(FONTS / "NotoSerifSC-Bold.otf"), 170)
    y = 1180
    for line in LINES:
        draw.text((s // 2, y), line, font=big, fill=(255, 255, 255), anchor="mm")
        y += 560
    draw.rectangle((s // 2 - 320, 2140, s // 2 + 320, 2148), fill=(214, 232, 255))
    draw.text((s // 2, 2370), SUB, font=small, fill=(225, 238, 255), anchor="mm")

    base.save(OUT, "JPEG", quality=90, optimize=True, progressive=False, dpi=(72, 72))
    with Image.open(OUT) as im:
        print("写好 %s：%d×%d，%s，%d 字节" % (OUT.name, im.size[0], im.size[1], im.mode, OUT.stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
