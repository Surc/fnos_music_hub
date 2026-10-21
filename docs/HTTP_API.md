# 开发接口 v0.1

这些端点已实现，但尚未冻结兼容性；完整大歌单及 NAS 链路验收后再形成稳定 OpenAPI。

登录通过音桥验证用户 GUID。浏览器仅持有 HttpOnly / SameSite=Strict 会话 Cookie，CSRF token 留在页面内存。所有私人请求重新向音桥验证会话；无效身份、缺 GUID、账号归属变化或音桥不可用均拒绝，没有 shared 回退。

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

首次实现仅提交酷我下载，QQ 提供公共搜索；网易与三个来源的私人账号业务未开放。无音质或未知时长的条目仍能浏览和收藏，但不能通过本版严格下载准入。

清单上限 1000 项 / 512 KiB，请求体上限 600 KiB；超限明确拒绝。此处的 complete 只适用于用户明确选择的完整输入，不能用于宣称远端分页歌单已完整抓取。任务保存独立清单副本及请求哈希。

TrackRef 三字段全部为字符串；酷我使用 provider=kuwo/id_type=rid，QQ 区分 songmid/songid，数值只在 Hot DTO 边界转换。QQ/网易的 id_type 不能互换。

状态包括 queued/running/paused/completed/failed/attention，条目另外有 submitting/outcome_unknown。整个任务只有所有条目校验成功才完成，部分失败保留每项状态。unknown 只回读核对，不能作为普通失败自动重发。

文件校验包含真实容器/编码、完整解码、与元数据时长的误差阈值、最低目标码率或 Hi-Res 参数以及 SHA256。它不能证明来源文件从未被上游转码，也不据此宣称原版母带。下载失败原因按静态规则分类，地区限制显示 region_restricted，音质不匹配显示 quality_unavailable，其余不暴露未经清洗的原始报文。

接口覆盖与未执行范围见 [验证记录](VALIDATION.md)。
