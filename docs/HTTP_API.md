# 开发接口 v0.1

## 本地快照历史补充

- `GET /api/playlist-captures?before=<id>&limit=20`：当前飞牛用户的独立本地读取历史，不调用 QQ。返回 items/next_cursor，limit 1–50，跨用户游标 404。原 `/api/catalog/qq/playlists/{id}/snapshots` 同样支持这两个参数，额外限制来源归属。
- `DELETE /api/playlist-captures/{id}`：CSRF/Origin/owner 检查；在途 409，重复删除返回原 deleted 记录。事务移除本地远端清单内容、保留幂等键与冷却期限；deleted 句柄运行返回 410，不修改下载任务。
- 空间复用与删除边界见 [QQ 快照](QQ_SNAPSHOTS.md)。

这些端点已实现，但尚未冻结兼容性；完整大歌单及 NAS 链路验收后再形成稳定 OpenAPI。

登录通过音桥验证用户 GUID。浏览器仅持有 HttpOnly / SameSite=Strict 会话 Cookie，CSRF token 留在页面内存。所有私人请求重新向音桥验证会话；无效身份、缺 GUID、账号归属变化或音桥不可用均拒绝，没有 shared 回退。

注销会撤销本地会话。外部等待结束后、缓存/接单/任务控制等边界重新检查；会话已撤销则返回 401。已经接收并持久化的下载继续执行，注销不等于取消下载。未完成的 QQ 登录尝试随当前会话清理，已关联账号保持原 owner 归属。

所有写入需要与配置一致的 Origin，登录之外还需要 `X-CSRF-Token`。未知字段返回 422；错误响应只有 `error.code`、`error.message`，不会回显密码或原始上游报文。

| 方法 / 路径 | 实现行为 |
| --- | --- |
| `GET /healthz` | 仅表示 Hub 存活，不表示音桥/Hot/平台正常 |
| `POST /api/auth/login` | username/password；向音桥登录并独立核对 auth/me；返回 principal、csrf_token，设置 Cookie |
| `POST /api/auth/logout` | 撤销本 Hub 会话 |
| `GET /api/me` | 可信 Principal、能力表、本人授权目录和管理员身份 |
| `GET /api/search` | q、provider=kuwo/qq、page；30 条元数据，不探测下载链接；异常条目留占位 |
| `GET/POST /api/favorites` | 当前用户本地收藏；写入 body 为 track、enabled，不写云平台 |
| `POST /api/manifests` | tracks 数组；从本人服务端元数据构建完整的显式选择快照；保序、保重复，返回 id/hash/count |
| `POST /api/tasks` | manifest_id、quality、target_ref=private；必须带 Idempotency-Key；首次 202、同内容重放 200、冲突 409 |
| `GET /api/tasks` | 本人任务与条目状态，不返回 Hot 访问凭据或原始 engine_song |
| `POST /api/tasks/{id}/control` | action=pause/resume/retry；校验归属和原引擎任务后交给 Hot |
| `GET /api/assets` | 本人通过完整解码、时长及音质检查的资产；入库状态单独记录 |
| `GET /api/assets/{id}/file` | 再验证身份、归属、授权目录、符号链接及文件指纹，读取已验证文件 |
| `GET /api/admin/injection` | 管理员可读；当前 available=false，不修改官方 Socket |
| `GET /` | 独立前台，静态资源在 /static |

下载仍仅提交酷我。QQ 公共搜索独立于可选账号模块；启用账号模块后提供以下私人只读链路，网易与酷我私人账号未开放。

| 方法 / 路径 | 实现行为 |
| --- | --- |
| `GET /api/accounts` | 本人平台关联与绑定代次/凭据修订；不返回凭据摘要、令牌或原生二维码 ID |
| `POST /api/accounts/qq/login` | kind=qr/existing；创建 180 秒、当前 Hub 会话专属尝试；已经关联先解绑 |
| `GET /api/accounts/qq/login/{id}` | 轮询扫码；confirmed 仅代表候选，尚未获得私人读取授权 |
| `GET /api/accounts/qq/login/{id}/qr` | 认证、会话归属与期限检查后的同源 PNG |
| `POST /api/accounts/qq/login/{id}/bind` | 用户核对 QQ 后显式确认；平台验证后提交代次，重复已确认操作返回原关联 |
| `POST /api/accounts/qq/unlink` | body.binding_generation 为所见代次；条件撤销 Hub 授权，不注销原生 Hot |
| `GET /api/catalog/qq/recommendations` | kind=playlists/songs，page=1..50；歌单按 next_cursor 继续请求 cursor，歌曲仅 page=1/cursor=0；猜你喜欢不是每日推荐 |
| `GET /api/catalog/qq/playlists` | 本人创建的歌单目录；未知摘要仍保留占位 |
| `GET /api/catalog/qq/playlists/{id}` | dirid、page；每页 100，source_total/has_more；complete=false、integrity=page_only |

QQ 平台失效返回 `platform_auth_required`（409），不退出飞牛会话、不回退公共内容。私人响应带 AccountRef/绑定代次/修订；网络请求后重新核对原生凭据和绑定，旧响应返回 binding_changed 且不缓存。recommendations 的 personalization=unverified，不能据此声称私人算法已验证。详细存储/上游/竞态边界见 [QQ 模块](QQ_ACCOUNTS.md)。无音质或未知时长的条目仍能浏览和收藏，但不能通过本版严格下载准入。

清单上限 1000 项 / 512 KiB，请求体上限 600 KiB；超限明确拒绝。显式选曲的 complete 只适用于用户选择的完整输入。新增远端 QQ 快照使用独立的两轮全量读取判定，complete=true 必须结合 integrity=double_read_verified、source.verification.atomic=false 解读；不提供平台原子快照保证。端点、冷却、失败与重启恢复见 [QQ 完整快照](QQ_SNAPSHOTS.md)。任务保存独立清单副本及请求哈希。

TrackRef 三字段全部为字符串；酷我使用 provider=kuwo/id_type=rid，QQ 区分 songmid/songid，数值只在 Hot DTO 边界转换。QQ/网易的 id_type 不能互换。

状态包括 queued/running/paused/completed/failed/attention，条目另外有 submitting/outcome_unknown。整个任务只有所有条目校验成功才完成，部分失败保留每项状态。unknown 只回读核对，不能作为普通失败自动重发。

批量 control 不是远端原子事务：每个原生动作前先保存意图，逐项回读后保存实际状态。中途失败可能已有部分操作成功，应 GET 回读；后台也会在重启后继续核对，不自动重复未知操作。多个条目或 Hub 任务可引用同一原生任务；无需发送操作时仍同步已观察到的状态。Hot 已完成、本地音频校验失败的 retry 只重新验证文件，不创建新下载。

文件校验包含真实容器/编码、完整解码、与元数据时长的误差阈值、最低目标码率或 Hi-Res 参数以及 SHA256。它不能证明来源文件从未被上游转码，也不据此宣称原版母带。下载失败原因按静态规则分类，地区限制显示 region_restricted，音质不匹配显示 quality_unavailable，其余不暴露未经清洗的原始报文。

接口覆盖与未执行范围见 [验证记录](VALIDATION.md)。
