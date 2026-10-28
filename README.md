# fnos_music_hub

2026-10-29：歌曲列表、品质标签、来源格式/大小、按品质筛选和排序已实现；[界面与验证](docs/SONG_LIST_20261029.md)。用户本轮要求不更新NAS，已安装preview.4继续保留。

2026-10-29 preview.4 已在J4125/fnOS完成保留配置升级，首个用户Hot与QQ/网易账号入口已配置，酷我无需平台登录的真实搜索通过；完整下载待用户复测。[本轮精确产物与证据](docs/fpk-preview/CAPABILITY_20261029.md)。

2026-10-28 已从 main `1ad75a4` 重建 preview.3，并在真实 J4125/8GB/fnOS 1.2.0800 安装、停启和60秒健康检查通过；音桥1.0.7已安装。真实账号/逐用户Hot与完整下载尚待验证。[实机与产物证据](docs/fpk-preview/MAIN_NAS_20261028.md)。下方旧候选/Release说明保留对应原始构建范围。

`preview.3` 内网测试支持已通过 [PR #6](https://github.com/Surc/fnos_music_hub/pull/6) 合入 main：无需域名/HTTPS 反代，显式选择后直接访问 NAS 私有 IPv4:8790；仍需音桥验证身份。安装和填写说明见 [内网测试](docs/fpk-preview/LAN_TEST.md)。现有测试包仍来自 PR 构建，尚未发布 preview.3 Release，与下方已发布 preview.2 分开记录。

已发布 [v0.1.0-preview.2 · amd64 原生预览](https://github.com/Surc/fnos_music_hub/releases/tag/v0.1.0-preview.2)，包含 FPK、对应源码、离线输入与 SHA256；最终提交/附件验证见 [发行记录](docs/fpk-preview/RELEASE_20261027.md)。**真实 J4125/fnOS 实机验收仍待完成。**

当前 `0.1.0-preview.2` / amd64 原生预览集成已合并的网易只读目录，默认关闭；新构建证据见 [整合验证](docs/fpk-preview/NETEASE.md)，旧 `preview.1` 不含网易。**J4125/fnOS 实机安装和升级仍未验收**。应用独立、非 root、无 Docker，需已有音桥 API 与 HTTPS 反代；不改 ext、不接管官方音乐 Socket、不迁移旧数据。见 [预览说明](packaging/fpk/README.md)。

面向飞牛音乐的独立音乐中心，目标是把**歌单推荐、歌曲下载、飞牛音乐注入**拆成可替换模块，按飞牛用户隔离推荐、收藏、平台账号与下载资产。

**当前阶段：0.1.0a1 可运行开发版，尚未完成 NAS 验收。** 已实现音桥严格身份适配、网易/QQ/酷我类型契约、酷我/QQ 公共歌曲搜索、本地收藏、酷我持久化下载投递、任务恢复和文件校验，以及 PC/手机横竖屏独立前台。可选 QQ 模块已实现扫码后显式关联、本人创建歌单、账号推荐歌单与猜你喜欢歌曲；真实账号效果尚未验收。新增 QQ 完整歌单两轮观测校验与不可变快照（最多 1000 项 / 512 KiB，非平台原子快照）；真实平台仍待验。本地快照独立于 QQ 在线状态，支持历史分页与确认删除。可选网易模块新增公开歌单、本人歌单和账号推荐只读目录，Cookie 经 UID 核对后显式关联；同号凭据更新、解绑换号与在途响应隔离已实现，真实平台待验，详见 [网易模块](docs/NETEASE.md)。网易搜索/下载、云端写入、入库、Socket 注入与正式 FPK 尚未交付。

前台已支持批量选曲、音质/授权目录确认、合并下载管理、任务筛选/失败详情和文件详情；目录/曲库与注入仍为独立只读状态页。QQ 启用与边界见 [账号模块说明](docs/QQ_ACCOUNTS.md)。运行方式见 [原生启动说明](docs/RUNNING.md)，已实现端点见 [开发接口](docs/HTTP_API.md)。2026-10-21 开发环境实际搜索能找到 DAYBREAK'S BELL，但当时两首样本的真实下载均被酷我以地区限制 407 拒绝；该历史结果不计作下载通过。

2026-10-26 已在用户本机 Windows + Ubuntu/WSL2 复测：两首固定 RID 的 Hot 原生链路与 Hub 链路均取得 320 kbps MP3，完整解码、时长和 SHA256 对照通过，未复现 407。详见 [本地复测](docs/HOT_LOCAL_RETEST_20261026.md)。保留原环境失败证据；人工试听、真实 NAS 身份/安装与入库仍待验，步骤与判定标准见 [平台验收清单](docs/ACCEPTANCE_PLATFORMS.md)。

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
| [QQ 完整快照](docs/QQ_SNAPSHOTS.md) | 完整性条件、分页漂移检测、失败恢复和只读前台 |
| [账号和反馈](docs/ACCOUNTS_AND_FEEDBACK.md) | 多用户、QQ 凭据所有权、真实播放与客户端准入 |
| [迭代计划](docs/ITERATION.md) | 当前完成度、开发顺序和验收门槛 |
| [来源清单](SOURCE_VERSIONS.json) / [更新流程](docs/UPSTREAM.md) | 观察版本、候选状态、旧工程基线、skill 摘要 |
| [迁移说明](docs/MIGRATION.md) | 与旧工程的关系、数据与 Socket 生命周期 |
| [验证记录](docs/VALIDATION.md) | 本次检查与未执行的实机验收 |
| [Astra 审核修复](docs/ASTRA_REVIEW_FIXES.md) | 整体审核问题、修复复核及后续改进 |
| [功能点验收清单](docs/ACCEPTANCE_FUNCTIONS.md) / [平台验收清单](docs/ACCEPTANCE_PLATFORMS.md) | 分功能/平台签收，地区限制与用户本地复测 |
| [界面评审稿](docs/UI_REVIEW.md) | 已授权实施的页面布局、流程与四种布局约束 |
| [研究原文](docs/design-goals-v1.6-20261021.txt) | 完整 v1.6 对比及 Astra 复核，历史提议保留 |
| [维护 skill](skills/maintain-fnos-music-hub/SKILL.md) | 后续开发、来源同步和交接工作流 |

当前规范文档优先于历史研究中的早期提议。候选项目有源码，不代表本工程已接入或已通过真实账号/设备验证。

## 工程组织

| 目录 | 职责 |
| --- | --- |
| `modules/catalog/` | 歌单、推荐、收藏和元数据适配 |
| `modules/accounts/` | 原生账号协议、受保护凭据快照 |
| `modules/download/` | 下载门面、Hot 适配、任务归属和资产 |
| `modules/fnos/` | 飞牛身份、曲库适配与独立注入 |
| `apps/web/` | 按用户的前台与管理员设置 |
| `packaging/fpk/` | 原生预览组包、生命周期、离线输入与校验；[说明](packaging/fpk/README.md) |
| `scripts/` | 来源与资料一致性检查 |
| `skills/` | 与个人 Skills 同步的维护说明 |

检查：`python -m pytest -q`、`npm test`、`npm run check`、`python scripts/verify_provenance.py`。Python/前台测试使用受控 HTTP 边界与生成音频；真实 Hot 的测试范围和结果单独记录。

原工程 [Surc/fnos_music_ext](https://github.com/Surc/fnos_music_ext) 继续保留上游历史与已有发布。本仓库以独立集成工程开始，按固定提交选择性复用；没有把旧工程完整代码或历史移入。第三方许可证和采用条件见 [来源说明](THIRD_PARTY_NOTICES.md)。
