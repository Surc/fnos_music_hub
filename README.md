# fnos_music_hub

面向飞牛音乐的独立音乐中心，目标是把**歌单推荐、歌曲下载、飞牛音乐注入**拆成可替换模块，按飞牛用户隔离推荐、收藏、平台账号与下载资产。

**当前阶段：0.1.0a1 可运行开发版，尚未完成 NAS 验收。** 已实现音桥严格身份适配、网易/QQ/酷我类型契约、酷我/QQ 公共歌曲搜索、本地收藏、酷我持久化下载投递、任务恢复和文件校验，以及独立前台。私人平台账号、推荐歌单、远端整单、入库、Socket 注入与 FPK 尚未交付。

运行方式见 [原生启动说明](docs/RUNNING.md)，已实现端点见 [开发接口](docs/HTTP_API.md)。本环境实际搜索能找到 DAYBREAK'S BELL，但两首样本的真实下载均被酷我以地区限制 407 拒绝；不把它计作完整音乐下载验收通过。

地区限制由用户稍后在本地环境复测，历史失败证据保留；当前为“环境受限，待用户本地复测”。步骤、固定样本与判定标准见 [平台验收清单](docs/ACCEPTANCE_PLATFORMS.md)。

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
| [功能点验收清单](docs/ACCEPTANCE_FUNCTIONS.md) / [平台验收清单](docs/ACCEPTANCE_PLATFORMS.md) | 分功能/平台签收，地区限制与用户本地复测 |
| [界面评审稿](docs/UI_REVIEW.md) | 页面布局、关键流程与待确认方案 |
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

检查：`python -m pytest -q`、`npm test`、`npm run check`、`python scripts/verify_provenance.py`。Python/前台测试使用受控 HTTP 边界与生成音频；真实 Hot 的测试范围和结果单独记录。

原工程 [Surc/fnos_music_ext](https://github.com/Surc/fnos_music_ext) 继续保留上游历史与已有发布。本仓库以独立集成工程开始，按固定提交选择性复用；没有把旧工程完整代码或历史移入。第三方许可证和采用条件见 [来源说明](THIRD_PARTY_NOTICES.md)。
