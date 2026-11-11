视频 v3（site/v3/video3.js）用的三维库，一个普通 <script> 就能读的文件（双击打开的本地页不能用 ES 模块）。

  three-bundle.min.js   three.js r186.1（npm three@0.186.1，MIT）＋ postprocessing 6.39.5（npm，Zlib），
                        只打进 entry.js 里列出的部分（esbuild 摇树、压缩）。读入后挂在
                        window.THREE 和 window.POSTPROCESSING 上。约 788 KB，gzip 后约 232 KB。
  LICENSE-three.txt     three.js 的 MIT 许可证原文
  LICENSE-postprocessing.txt  postprocessing 的 Zlib 许可证原文（本文件即“使用说明里的致谢”）
  entry.js              打包入口（要加减用到的类，改这里再重打一次）

来源与校验（2026-10-31 从 npm 官方仓库下载）：
  three@0.186.1           https://registry.npmjs.org/three/-/three-0.186.1.tgz
                          sha256 8cd068708ea44f2c73c944b1cead2ba2f0d5c15c8fc194e5700f4e4f4a033fe7
  postprocessing@6.39.5   https://registry.npmjs.org/postprocessing/-/postprocessing-6.39.5.tgz
                          sha256 ce7495c521102470ce6284563436f6bb673050282a795328a64857ea282e6222
                          （它声明兼容 three ≥0.168 且 <0.187，所以 three 锁在 0.186.1；0.187.0 是 10-30 刚发的）
  打包工具 esbuild@0.28.2（只在打包时用，不随网页分发）

重打一次（在任意一个空的临时目录里）：
  npm pack three@0.186.1 postprocessing@6.39.5 && npm install --no-save esbuild@0.28.2
  mkdir -p node_modules/three node_modules/postprocessing
  tar -xzf three-0.186.1.tgz -C node_modules/three --strip-components 1
  tar -xzf postprocessing-6.39.5.tgz -C node_modules/postprocessing --strip-components 1
  cp <本目录>/entry.js . && npx esbuild entry.js --bundle --format=iife --minify --target=es2019 \
      --legal-comments=none --outfile=three-bundle.min.js
  再把文件头那行版权说明加回去（见现有文件第一行）。
