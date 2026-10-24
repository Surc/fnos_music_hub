# 0.1.0-preview.1 候选证据

日期：2026-10-24。基线 main `04677d32b96a0b824c2148001458d581f9f8f22c`；本地实际组包提交 `606f6319490bfde4935d2bc2ee43cbfb4769a4f2`，业务版本 0.1.0a1。网页提交的 Git commit 与本地历史可不同，最终交付须核对远端内容树；本地候选来源固定，不把后续文档提交说成已重建。

| 项目 | 本次实际结果 |
| --- | --- |
| 工具 | 官方 fnpack 1.2.3，固定摘要见 versions.json |
| FPK 静态校验 | 通过，5915 个安装文件，非 root 声明、生命周期执行位、app.tgz MD5、每文件 SHA256/模式/链接匹配 |
| 架构/运行库 | 23 个 amd64 ELF；Hot/媒体工具无动态解释器；动态组件最大 GLIBC 需求 2.34，无未封装的非基础库 |
| 两次离线构建 | 两轮均通过，安装内容清单完全一致，对应源码附件字节一致；外层 FPK SHA256 不同 |
| Python/前台 | 完整 Python 154 passed，其中包装 34；jsdom 31 passed，语法/Ruff/来源检查通过 |
| 真实组件运行 | 开发机 root + 合成用户下，包内 Python/Hub/双 Hot、私有设置和 MP3/FLAC 完整解码通过 |
| 完整监督器/回滚 | 本地因 root/procfs 不一致 blocked；受控单元通过，普通非 root Linux CI 另记 |
| 真实 J4125/fnOS | 未安装、未升级、未做资源/ACL 测试 |
| 真实账号/音乐 | 未新增平台登录/下载验收；历史酷我 407 保留 |
| 发布/部署 | 本轮无正式 Release、无 NAS 部署 |

交付构建 A：`fnos-music-hub-0.1.0-preview.1-amd64.fpk`，SHA256 `68d814f27297228b14631f88165d430f7ec74837d759ccd6d76e296eb1608286`。对应源码摘要、精确字节数、组件版本/编译参数与来源见 [构建报告](build-report.json) 和 SOURCE_VERSIONS.json。无 Cookie、令牌、用户数据库、私人歌单或音频进入 FPK；对应源码附件在包外保留上游原测试夹具。

原始报告：[实际 FPK 校验](build-report.json)、[离线复现](reproducibility.json)、[组件运行](runtime-check-local.json)、[监督器本地阻断](native-smoke-local.json)。组件运行只用生成音频，不代表真实完整音乐下载。包安装/配置/回滚与依赖前置见 [原生包说明](../../packaging/fpk/README.md)。
