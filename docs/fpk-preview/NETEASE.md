# preview.2 网易整合验证

2026-10-25。业务合并基线 `823a2de946ebbd64207117d9551c7d0eb7d56237`，PR #5 保持 Draft。旧 [preview.1](EVIDENCE.md) 不含网易，不能作为本轮构建证据。

本轮包含：固定 MusicBox 0.5.3 / `9c405f4bae2384d0410e63f8b816a707553d72d3` wheel，基础/QQ/网易去重锁闭包，逐 wheel SHA256/许可/依赖清单、原始 LICENSE/NOTICE（不存在时如实记载）、SDK 对应 Git 源码及 PyPI 同版本源码包/摘要。离线组包拒绝锁与 wheel 漂移；实际 FPK 的 CONTENTS.json 校验每个文件、权限与链接。

网易默认关闭；开启时临时进程/独立 XDG 离线检查真实加解密和原生依赖。非 root 服务测试增加 QQ+网易同开、移除 requests 后启用报错、关闭网易仍能运行 QQ/双 Hot，以及原有启停、子进程清理、备份/坏版本回滚/数据库密钥恢复/卸载保留。

本地 Python 3.12 / QQ+网易完整业务回归 234 passed；新增 wheel 故障用例后，包装/核心定向 65 passed（原生包装 45 项）。实际离线探针通过；37 项 jsdom、Node 语法、Ruff、来源/摘要和 shell 语法通过。43 个实际 wheel 均与锁定版本匹配且含许可证。均为合成平台/生成音频，不涉及真实账号。

以下为最终实际 CI/产物结果：已通过普通 Linux 自动化，真实 NAS 仍未执行。构建提交、安装文件数、SHA256 和 MusicBox 集成状态均以新 build-report.json 为准；附件名为 `fnos-music-hub-0.1.0-preview.2-netease-readonly-amd64`。另存 `netease-offline-inputs-amd64` 闭包附件用于精确离线重放，均保留 14 天。

真实 R-NE-001..004、QQ/飞牛账号、完整音乐下载、J4125/fnOS 安装/升级/ACL/CPU/RSS 均未执行。下载准入仍只允许酷我，历史两首地区限制 407 不变。无真实 NAS 部署、旧 ext 修改或正式 Release。

首轮本次原生 CI [40172841217](https://github.com/Surc/fnos_music_hub/actions/runs/40172841217) 的输入准备通过，但 ELF 审计正确拦截 RapidFuzz 官方 C++ wheel 对外部 libstdc++.so.6 的依赖，未生成/签收 FPK。修复为上游支持的 `wheel.cmake=false`：以固定 sdist/SHA256 和 scikit-build-core 0.11.6 构建未修改的纯 Python wheel，版本不变；拒绝任何夹带原生扩展的 RapidFuzz 输入，不放宽 ELF 外部库校验。MusicBox 目录 API 不使用终端界面的模糊匹配模块；仍以包内纯 Python 实现探针/业务回归验证完整依赖。

修复后本地 QQ+网易/纯 Python RapidFuzz 完整回归 **239 passed**，其中包装 46 项；实际离线探针与 pip check 通过。固定纯 Python wheel 完整闭包仍为 43 项，新增包装/SDK 定向 74 passed。等待新原生 CI 与实际产物，不以这些本地检查签收 FPK/NAS。

## 最终实际产物与 CI

- [常规 CI 40173694578](https://github.com/Surc/fnos_music_hub/actions/runs/40173694578) 九项全部成功；[原生 CI 40173694577](https://github.com/Surc/fnos_music_hub/actions/runs/40173694577) 输入、离线组包、实际安装校验、包内 **239 passed**、非 root Linux 十二项服务/故障检查及两个附件上传全部成功。
- PR 业务 head `a0a426e241bb58cfb7fd565c1ea6bcd2d41c7491`，与本地已测完整内容树 `a2b39c5a3fa6b6c52ceccef188f7bcf01bcdb8a4` 相同。Actions 对 pull_request 的实际组包提交为 `30515916895cb6b745ba48b832f3bc55afb8bc8e`；这是匹配该树的测试合并提交。后续证据提交没有重建该候选，不能把文档 head 当作构建来源。
- FPK **66,760,897 bytes**、**6623 个安装文件**、65 个 amd64 ELF，最高 GLIBC 需求 2.34；无额外 libstdc++。FPK SHA256：`109d68854b847f953335a14ec540dcc691c12f6617748056f9eb5be88dc65120`。
- 对应源码 113,957,940 bytes，SHA256：`03def56f9bb28d429339fa1a5554d3fee4c31927b4ff90cfea3ba635bfb105f0`。下载后逐项复核 41 份 sdist 摘要，并对照固定 MusicBox 的 LICENSE/api/encrypt 原始字节。实际 FPK 再次通过本地全部安装文件/权限/链接校验；下载主附件的七个文件摘要与 SHA256SUMS 相符。
- 主附件 ID `12591965469`，ZIP SHA256 `6d9cbc89b170296a94891b55ad12f373803536ba149f7c76c1e9b48f53ec9f4c`；独立离线输入附件 ID `12591840881`，ZIP SHA256 `debbfd23b88e7261f29e6f1443d89ec06167e622fa8ca213be6a6afeeb691f98`。截至查验均未过期，预计到北京时间 **2026-11-08 15:45**；以 GitHub artifact expires_at 为准。

报告：[实际 FPK](netease-build-report.json)、[包内完整回归](netease-bundle-tests.txt)、[非 root 生命周期](netease-native-smoke.json)、[SHA256SUMS](netease-SHA256SUMS)、[CI/附件/验证边界](netease-ci-evidence.json)、[成功页面](netease-ci-success.jpg)。完整 CONTENTS.json 随主附件及 FPK 一起提供。独立输入附件的 tar 摘要同列在 SHA256SUMS；本地复核范围没有把该第二附件冒称已独立下载/重建。

保留非阻断的 Starlette/httpx 弃用提示及 Actions 上传步骤 Node 20→24 提示，不视为 NAS 运行警告。预览包不是正式 Release；真实账号、J4125/fnOS 安装升级/ACL/资源与完整音乐下载仍待单独签收。
