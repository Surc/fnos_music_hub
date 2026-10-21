# fnos_music_hub

面向飞牛音乐的独立音乐中心，目标是把**歌单推荐、歌曲下载、飞牛音乐注入**拆成可替换模块，按飞牛用户隔离推荐、收藏、平台账号与下载资产。

**当前阶段：设计与工程骨架。** 已保存 v1.6 研究记录、模块边界、接口草案、固定来源版本和维护 skill；尚未实现运行服务、前台或 FPK。这里没有可直接安装的发行包。

## 产品目标

- 网易云、QQ、酷我统一浏览歌单、推荐与搜索；歌曲元数据不因下载链接失败而消失。
- QQ/酷我下载优先验证 HotDownloader，保留其核心功能；歌单模块通过完整有序清单交付下载模块。
- 每个飞牛用户绑定自己的平台账号，区分本地收藏、云端喜欢/订阅和导入快照。可靠的实际播放反馈通过验证后逐客户端启用。
- 独立管理下载任务与文件，飞牛入库状态单独显示；注入设置独立，关闭注入后仍能使用歌单和下载管理。
- 面向 J4125 / x86_64 NAS，以原生 FPK 交付，无需 Docker；移动端继续使用箭头音乐。

## 从这里开始

| 文档 | 内容 |
| --- | --- |
| [当前设计](docs/DESIGN.md) | 三个业务模块、内部组件与上游责任 |
| [接口草案](docs/CONTRACTS.md) | TrackRef、账号、歌单快照、任务、资产与错误语义 |
| [账号和反馈](docs/ACCOUNTS_AND_FEEDBACK.md) | 多用户、QQ 凭据所有权、真实播放与客户端准入 |
| [迭代计划](docs/ITERATION.md) | 当前完成度、开发顺序和验收门槛 |
| [来源清单](SOURCE_VERSIONS.json) / [更新流程](docs/UPSTREAM.md) | 观察版本、候选状态、旧工程基线、skill 摘要 |
| [迁移说明](docs/MIGRATION.md) | 与旧工程的关系、数据与 Socket 生命周期 |
| [验证记录](docs/VALIDATION.md) | 本次检查与未执行的实机验收 |
| [研究原文](docs/design-goals-v1.6-20261021.txt) | 完整 v1.6 对比及 Astra 复核，历史提议保留 |
| [维护 skill](skills/maintain-fnos-music-hub/SKILL.md) | 后续开发、来源同步和交接工作流 |

当前规范文档优先于历史研究中的早期提议。候选项目有源码，不代表本工程已接入或已通过真实账号/设备验证。

## 工程组织

| 目录 | 职责 |
| --- | --- |
| `modules/catalog/` | 歌单、推荐、收藏和元数据适配 |
| `modules/download/` | 下载门面、Hot 适配、任务归属和资产 |
| `modules/fnos/` | 飞牛身份、曲库适配与独立注入 |
| `apps/web/` | 按用户的前台与管理员设置 |
| `packaging/fpk/` | 原生包生命周期设计 |
| `scripts/` | 来源与资料一致性检查 |
| `skills/` | 与个人 Skills 同步的维护说明 |

资料检查：`python3 scripts/verify_provenance.py`。这只验证清单、文件摘要和本地文档链接，不测试平台接口或 FPK。

原工程 [Surc/fnos_music_ext](https://github.com/Surc/fnos_music_ext) 继续保留上游历史与已有发布。本仓库以独立集成工程开始，按固定提交选择性复用；没有把旧工程完整代码或历史移入。第三方许可证和采用条件见 [来源说明](THIRD_PARTY_NOTICES.md)。
