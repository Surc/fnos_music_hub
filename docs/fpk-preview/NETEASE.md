# preview.2 网易整合验证

2026-10-25。业务合并基线 `823a2de946ebbd64207117d9551c7d0eb7d56237`，PR #5 保持 Draft。旧 [preview.1](EVIDENCE.md) 不含网易，不能作为本轮构建证据。

本轮包含：固定 MusicBox 0.5.3 / `9c405f4bae2384d0410e63f8b816a707553d72d3` wheel，基础/QQ/网易去重锁闭包，逐 wheel SHA256/许可/依赖清单、原始 LICENSE/NOTICE（不存在时如实记载）、SDK 对应 Git 源码及 PyPI 同版本源码包/摘要。离线组包拒绝锁与 wheel 漂移；实际 FPK 的 CONTENTS.json 校验每个文件、权限与链接。

网易默认关闭；开启时临时进程/独立 XDG 离线检查真实加解密和原生依赖。非 root 服务测试增加 QQ+网易同开、移除 requests 后启用报错、关闭网易仍能运行 QQ/双 Hot，以及原有启停、子进程清理、备份/坏版本回滚/数据库密钥恢复/卸载保留。

本地 Python 3.12 / QQ+网易完整业务回归 234 passed；新增 wheel 故障用例后，包装/核心定向 65 passed（原生包装 45 项）。实际离线探针通过；37 项 jsdom、Node 语法、Ruff、来源/摘要和 shell 语法通过。43 个实际 wheel 均与锁定版本匹配且含许可证。均为合成平台/生成音频，不涉及真实账号。

GitHub Actions、实际 FPK 与普通非 root Linux 服务结果待本轮运行后填入，尚不宣称成功。构建提交、安装文件数、SHA256 和 MusicBox 集成状态均以新 build-report.json 为准；附件名为 `fnos-music-hub-0.1.0-preview.2-netease-readonly-amd64`。另存 `netease-offline-inputs-amd64` 闭包附件用于精确离线重放，均保留 14 天。

真实 R-NE-001..004、QQ/飞牛账号、完整音乐下载、J4125/fnOS 安装/升级/ACL/CPU/RSS 均未执行。下载准入仍只允许酷我，历史两首地区限制 407 不变。无真实 NAS 部署、旧 ext 修改或正式 Release。
