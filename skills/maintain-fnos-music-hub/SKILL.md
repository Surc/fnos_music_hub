---
name: maintain-fnos-music-hub
description: 维护 Surc/fnos_music_hub 独立飞牛音乐中心。用于接续歌单推荐、HotDownloader 下载、飞牛身份与曲库、独立注入、多用户平台账号和真实播放反馈的开发，核对固定上游版本、模块契约、原生 FPK 与迁移记录。旧 Surc/fnos_music_ext 的维护使用 maintain-fnos-music。
---

# 飞牛音乐 Hub 维护

## 先核对当前工程

1. 定位或按任务授权克隆 `https://github.com/Surc/fnos_music_hub.git`。检查 remote、分支、未提交修改；不要把旧 `fnos_music_ext` 当作本仓库。
2. 读取仓库 `AGENTS.md`、`README.md`、`SOURCE_VERSIONS.json`、`docs/ITERATION.md` 和 `docs/VALIDATION.md`；先读 `docs/RUNNING.md` 和 `docs/HTTP_API.md`，按任务读取 `docs/DESIGN.md`、`docs/CONTRACTS.md`、`docs/ACCOUNTS_AND_FEEDBACK.md`、`docs/UPSTREAM.md`、`docs/MIGRATION.md`。
3. 以当前代码和验证记录判断完成度。初始化是设计骨架；0.1.0a1 已有可运行开发服务与前台，尚无 FPK。按当前迭代区分模拟验证与真实平台/NAS验收。`docs/design-goals-v1.6-20261021.txt` 是完整历史研究，含被后续审核修订的提议；当前规范文档优先，不能只截取早期选型表。
4. 核对来源的完整 SHA、实际分支、版本文件、Git tag、观察时间、采用状态和许可证。`observed_commit` 不等于 `adopted_commit`，原工程双来源的采用基线不等于新 Hub 已采用。

## 保持模块可替换

- 三个业务模块保持独立：歌单推荐、歌曲下载、飞牛注入。身份、账号、任务归属、资产、反馈按包拆分；只在语言或故障隔离需要时增加进程，不把每个类做成服务。
- QQ/酷我下载优先验证 HotDownloader；保留其搜索、队列和下载核心，不另建第二套实际调度器。歌单推荐经 CatalogProvider 提供元数据，取流失败不得使歌曲从搜索或歌单中消失。
- FnIdentity/FnLibrary 优先验证音桥同一主上游；注入与 Socket 生命周期参考旧 ext。关闭注入后独立前台的认证、歌单和下载管理仍须可用。每个 Socket 只允许一个接管者。
- 每个协议组件指定一个主上游。版本固定，通过适配器、配置或小型可选接口扩展；记录补丁、范围、验证和回退。不要把不同上游的解析器暗中拼到同一个组件。
- `TrackRef` 使用平台、ID 类型和字符串 ID；保留实际下载来源/格式。跨平台匹配须核对歌名、歌手、版本与时长，不能把试听、翻唱或转码标为原版高音质。
- 歌单下载交付完整、有序、不可变的清单；保留重复出现和未知条目，验证分页/总数/哈希。接单持久化、幂等和恢复必须成立；下载完成、文件验证、入库状态分开记录。

## 用户身份、凭据与反馈

- 所有私有读取、写入、事件和文件访问由服务端验证的 fnOS 实例与用户 GUID 授权。无效会话、缺 GUID 或上游异常应拒绝，不能降级 shared/admin、信任前台 user_id 或继承上个用户。
- 本地收藏、云端喜欢/订阅、导入快照分别建模。逐用户绑定平台账号；Cookie/令牌只保存在服务端受保护存储。日志、Git、文档和浏览器响应不包含凭据。
- QQ 首轮登录/刷新协议由 Hot 持有，账号门面管理归属；QQMusicApi 只获得不可变账号快照，不竞争刷新。逐账号串行刷新和条件写入；`binding_generation` 与 `credential_revision` 分开。现有 Hot server 全局凭据须先解决隔离，不能并发切换共享 Cookie。
- 网易协议先评估现有 MusicBox 小扩展或整组件替换；不要默认引入第二套常驻 SDK。酷我私人账号、TuneWeave、酷狗等为独立验证项，不自动扩张一期范围。
- 仅用户启用反馈且有可信实际播放证据才上报；下载、预取、文件字节数、歌曲总时长或最后位置都不是有效收听时长。排除暂停、缓冲和跳播；处理重连、乱序、循环、并发设备和账号解绑。
- 音桥现有 Jellyfin start/progress 不保留完整状态，普通 Subsonic scrobble 的 time 是时间戳；不能声称已经支持完整反馈。fnmusic-sync 的取流/墙钟估算只可作参考；箭头各连接模式必须实机核对。没有可靠证据时保留本地历史和明确云端操作，关闭自动时长上报。
- 上游接受反馈不等于推荐算法已学习。远端写入超时状态为未知时先回读，避免盲目重发非幂等操作。

## 验证、记录与交付

1. 从 `docs/ITERATION.md` 取最小下一步，先完成严格身份和一首歌的端到端链路，再冻结 OpenAPI。保留内联清单容量上限，超限明确拒绝；暂不引入通用事件总线或复杂分块协议。
2. 运行与本次改动相符的检查。运行相关 pytest、ruff、`npm run check` / jsdom，以及 `python3 scripts/verify_provenance.py`；适配器需覆盖失败语义和两个用户并发隔离。账号真测、客户端真测、fnOS 安装测试分别记录，不能以模拟测试替代。
3. 现有运行时使用逐用户独立 Hot 进程、端口、凭据与非重叠下载目录；禁止把它改成共享 Cookie 切换。内联选曲清单上限 1000 项/512 KiB，任务投递结果不明时先回读，不盲目重试。
4. 下载回归包含酷我 `rid=142276943` 的 DAYBREAK'S BELL 和其他样本，检查完整可解码音频、实际来源和格式。单首成功不代表全平台、会员资格或所有音质可用。
5. 原生 FPK 面向 J4125/x86_64；NAS 不安装编译器、不依赖 Docker。实现后核对运行依赖、独立应用 ID、数据目录、升级备份、停用恢复、唯一 Socket 所有者以及密钥排除。
6. 同步 `SOURCE_VERSIONS.json`、迭代/验证/变更记录和用户说明；实际合入后才能推进采用 SHA。发行请求另核对 VERSION/tag/构建提交/正式附件 SHA256 和实机证据，不把设计提交发布为可用 FPK。
7. 更新本 skill 时提升清单中的 skill 版本，重新计算本文件与 `agents/openai.yaml` 的 SHA256，同步仓库副本与个人 Skills Git。旧 `maintain-fnos-music` 保持专用于旧工程。
8. 按会话已有授权完成提交/PR/发布，不因例行维护重复索要许可；权限和凭证不写入项目。交接给出实际提交、检查结果、候选/采用差异和下一项阻断条件。

## 当前开发版的验证边界

- 2026-10-21 的真实 Hot HTTP 搜索能找到 DAYBREAK'S BELL（RID 142276943）和晴天（RID 228908）；本环境两次下载都被酷我地区限制 407 拒绝。不能沿用“Hot 在其他环境成功”来认定本次下载通过。
- 当前仅开放酷我下载与 QQ/酷我公共搜索；本地收藏不是云端喜欢。推荐、私人平台账号、远端整单、入库、注入和真实播放反馈仍有独立准入。
- `scripts/run_hot_user.py` 初始化 Hub 专属原生引擎；`scripts/live_hot_smoke.py` 是显式真测工具，音频和原始日志放在仓库外，不用作生产认证入口。
- 自有代码 MIT；目前通过 HTTP 对接上游，没有复制或修改其运行源码。真实构建 Hot 时要获取固定子模块并保留其 LICENSE/NOTICE。
