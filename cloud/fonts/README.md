# 网页、视频用的原字体（云端用）

本机这些字体放在 `~/.cache/frontier-daily/fonts/`（`site/tools/v3_site.py` 的 `FONT_CACHE`），`build_v3.py`、`video3_build.py` 从那里读原字体，按每期用到的字截成小字体包。程序不会自己下载，缺了就停（`build_v3.py` 第 1575 行）。

云端每次是一台空机器，所以把同一批文件放进仓库，由 workflow 在开跑前拷到 `~/.cache/frontier-daily/fonts/`。2026-11-08 从本机缓存原样拷来（逐个 md5 一致）。

许可：都是 SIL OFL 开源字体（思源宋体 Noto Serif SC、霞鹜文楷屏幕版、Instrument Serif、Tinos），许可文本在同目录 `LICENSE_NotoSerifCJK.txt`、`OFL_*.txt`、`METADATA_Tinos.pb`。以后换公开仓库也可以带着走。
