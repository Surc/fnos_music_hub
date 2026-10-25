# 模块接口草案 v0.1

2026-10-24 新增可选网易只读目录与 AccountRef/绑定代次/凭据修订隔离，实际端点见 [HTTP API](HTTP_API.md)，边界见 [网易模块](NETEASE.md)。网易目录 complete=false/page_only，没有远端整单完整性或下载授权；原 QQ 快照契约独立保留。

状态：设计契约，尚未冻结兼容性。首轮已有 HTTP 服务，实际可用范围见 [开发接口](HTTP_API.md)；目前实现显式选曲清单，以及可选 QQ 关联/推荐/本人目录和分页预览；QQ 两轮完整歌单快照已开发，真实大歌单仍待验收。以下总体目标不表示均已实现。

## 身份与引用

`Principal = {instance_id, user_guid}`：由服务端验证的飞牛会话产生。用户名、token 和前台传来的 user_id 不作为永久归属。所有私人列表、任务、账号、事件和文件都执行同一 owner 授权；管理员操作也留下明确的目标与审计结果。

`TrackRef = {provider, id_type, id}`：三个字段均为字符串，例如 `{"provider":"kuwo","id_type":"rid","id":"142276943"}`。QQ songmid 与数值 songid 使用不同 id_type。标题/歌手不替代主键；跨平台映射保存方法、置信度、版本和时长差，低可信结果不自动下载或反馈。

`AccountRef` 是服务端不透明账号引用，关联 Principal、provider、provider_user_id、binding_generation。令牌轮换使用独立 credential_revision；浏览器和普通业务响应不包含 Cookie 或密钥。能力按账号状态返回，不把函数存在当作平台已验收。

## 歌单 / 目录

`CatalogProvider` 负责 capabilities、search、recommendations、playlist_details、playlist_page 与 export_manifest。公共/本人账号/共享账号的推荐明确区分；推荐歌曲和推荐歌单是不同类型。

保留三种对象：本地可编辑歌单、云端引用/订阅、不可变导入快照。本地收藏不自动写云端；云端操作需用户明确选择，记录目标账号和结果。过期账号返回 auth_required，不偷偷改用匿名结果充当私人内容。

`DownloadManifest` 包含 schema_version、snapshot_id、owner、来源歌单及版本、captured_at、ordered_entries、上游总数/抓取数/完整性、内容哈希与生成适配器版本。每项有 occurrence_id、position、TrackRef 或 unknown 原始占位元数据。

- 保留顺序、同一 TrackRef 的合法多次出现、不可用/未知项；不能按曲目 ID 去重后声明完整。
- QQ 当前仅在两轮全部分页的总数/页长度/结束标记、来源目录、有序原始条目哈希及冻结账号授权一致时设置 complete=true / integrity=double_read_verified。没有已验证的上游快照版本，source.version=null、atomic=false；此标志不承诺单一时刻一致性，无法排除 ABA 或来源缓存。变动、超时、截断保持 incomplete，不能静默提交“整单成功”。完整规则见 [QQ 快照](QQ_SNAPSHOTS.md)。
- 一期采用有明确项数/字节上限的内联清单；超限明确拒绝。当前上限 1000 项 / 512 KiB；沿用 canonical UTF-8 JSON 和除 content_hash 本身外的完整清单 SHA256，详见 QQ 快照说明。真实验收后再冻结接口。
- 下载模块保存清单副本与哈希，不依赖后续远端歌单变化。可单独显示条目失败或跳过；副本里的同曲重复与磁盘去重策略分开。

## 下载与资产

`submit(manifest, target_ref, quality_policy, idempotency_key) -> task_id`：完成权限、能力、完整性、容量和目标路径检查，持久化接单后才返回接受。幂等键按 owner/操作作用域隔离；同键同内容返回原任务，同键不同哈希返回 conflict。

账号引用、绑定代次、引擎任务 ID 和清单副本一起持久化。引擎由 Hot 调度，门面维护授权和稳定任务 ID。重启时协调本地记录和引擎状态，避免重复下载；换号/解绑使旧归属失效，正常令牌刷新不会误作换号。

任务状态至少区分 queued、running、paused、completed、failed、cancelled；解析/下载/音频校验的细分进度另存。任务完成要求所有条目进入有解释的终态，不能把部分失败描述为全成功。错误/暂停后能否继续取决于实际引擎能力。

`Asset` 记录 owner、可信 TrackRef/实际来源、实际编码和容器、文件字节数/哈希、时长、校验结果、存储目标及库映射。后缀/Content-Type 不能代替可解码音频验证；试听、HTML 错误页、损坏文件不得成功入库。音质降级须按用户策略记录，不能把转码称为原生高音质。

下载目标是管理员允许且用户获授权的路径引用，服务端规范化并限制在根目录内；不接受任意绝对路径。飞牛库为独立 `library_ref`，下载完成不等于索引完成。入库独立记录 pending/indexed/failed/unsupported 并支持安全重试，实际扫描接口需验证。

文件读取、删除、任务订阅、导出与统计仍检查 owner。共享物理文件可以去重，但授权引用和删除生命周期分离，不能由一个用户删除他人仍使用的文件。

## 反馈与错误

认证事件包含 principal、asset/TrackRef、设备/客户端、session_id、状态、位置、播放速率、序号与接收时间。服务端验证客户端能力、账号绑定代次、时序与曲目映射后才累计可信区间。具体规则见 [账号和反馈](ACCOUNTS_AND_FEEDBACK.md)。

错误至少区分 auth_required、forbidden、unsupported、not_found、rate_limited、transient、unavailable、incomplete、conflict 与 outcome_unknown，附可重试性和必要重试时间。非幂等云端写入响应丢失时标为未知并回读，不把超时直接当作失败重发。

接口冻结的验收：两个用户并发/退出/换号/重启、完整大歌单、重复/未知曲目、引擎重启恢复、链接失败仍可浏览、文件验证与入库失败分离。测试通过记录到 [验证记录](VALIDATION.md)，之后新增接口版本与迁移规则。
