# PR #4 独立代码审核

2026-10-24。审核基线为远端 `8ae89c835849bb377172c8e9186107dca26760ae`，完整内容树 `0dbebe662e9c5240c1b5e3727b428ae056d564cf` 与本地审阅源码一致；main 基线为 `04677d32b96a0b824c2148001458d581f9f8f22c`。重新查询 PR、讨论、审核及线程：Draft/Open、mergeable=true，无已有审核或未解决线程；该 head 的 [CI 40078403156](https://github.com/Surc/fnos_music_hub/actions/runs/40078403156) 八项成功。最终修复提交与合并状态以 PR #4 后续记录为准。

## 发现与最小修复

| 问题 | 复现与影响 | 修复 |
| --- | --- | --- |
| P2：HTTP 响应 Cookie 改变冻结凭据 | 实际 MusicBox + 合成 requests CookieJar 提取证明，响应 MUSIC_U 会进入后续目录/UID 请求；已有前后 UID 校验仍保留，但单次请求凭据不再不可变 | Hub 内存 Session 拒收响应 Cookie；显式输入仍可安装，公共读取也不接受登录 Cookie |
| P2：异常 trackIds 破坏占位或错误匹配 | id=[]/{} 导致整页协议失败；id=true 被 Python 字典当成歌曲 1 | 仅对严格整数 ID 查详情映射，其余按原位置保留 unknown，顺序/重复不变 |
| 异常进程结果及过长输入 | 合法 JSON 数组触发 AttributeError；超长十进制歌单 ID 转 int 时异常 | 进程结果先验证对象结构，统一 502；歌单 ID 在转整数前限制 1–20 字符 |

前两项先用新增回归复现，共得到 4 个失败用例，修复后通过。没有修改 MusicBox/Hot 上游、数据库 schema、依赖锁或 FPK。

## 安全及兼容性结论

- Cookie 经同源 POST 和子进程 stdin 传递，账号/候选用 vault 加密；Pydantic 错误脱敏，业务响应白名单不含凭据或原始报文。XDG 0700，数据库/密钥 0600；正常 TLS、固定 HTTPS 来源、禁止重定向。
- UID 来自平台账号接口，校验数值类型及 account/profile 一致性，绑定再次验证。私人目录前后验证 UID，返回后检查飞牛会话、AccountRef、代次/修订。新增 code=200 却缺少可信 UID、类型错误/不一致、读取后 UID 变化用例。
- 归属含 instance_id/user_guid/provider；解绑/换号撤销代次，同号更新推进修订。条件写入阻止迟到验证，旧成功/错误不能发布、缓存或使新账号失效。平台失效 409，不退出有效飞牛会话、不匿名回退。新增解绑期间在途 bind/rotate 回归。
- 实际一次性 OS 子进程验证超时、取消、输出超限、非法 JSON/结构后均终止并回收进程、删除 XDG，随后仍可读取；9 次并发使用不同目录，同时不超过 4 个。无真实平台网络，测试缩短生产 45 秒超时以检查相同清理路径。
- 详情验证来源总数/trackIds、页长度与结束标记；缺详情/未知/重复保留，截断/协议错误不缓存。网易始终 complete=false / page_only，没有完整快照保证。
- 关闭网易时不要求 SDK、不暴露网易能力，端点拒绝；启用却缺固定依赖则启动失败。QQ 快照、账号、酷我任务/资产及前端导航沿用完整回归；网易下载、云端写入、注入和反馈未解禁。

## 依赖与许可证

固定 MusicBox `9c405f4bae2384d0410e63f8b816a707553d72d3` / 0.5.3，核对固定源码 LICENSE 和包元数据为 MIT，上游零补丁。网易锁与 pyproject 可选依赖一致，干净网易及 QQ+网易环境 pip check 无冲突。

| 网易新增闭包 | 核对的包许可证 |
| --- | --- |
| attrs、cattrs、charset-normalizer、platformdirs、rapidfuzz、url-normalize、urllib3 | MIT |
| requests | Apache-2.0 |
| requests-cache | BSD-2-Clause |
| qrcode | BSD-3-Clause（实际 LICENSE） |
| pycryptodomex | BSD-2-Clause / Public Domain（实际 LICENSE.rst） |

本轮不发行组合包。后续 FPK 收集实际 wheel 的 LICENSE/NOTICE，保留既有 QQ SDK 的 GPL-3.0-or-later 声明和固定对应源码；Hub MIT 不替代第三方声明。

## 本轮验证与合并门槛

- 本地 Python 3.12，QQ+网易依赖：193 passed，较审核基线增加 21 项。
- 干净网易环境：182 passed / 1 skipped（未装 QQ SDK）；pip check 无冲突。
- 37 项 jsdom、Node 语法、Ruff、来源/摘要校验、wheel 构建、diff 检查、Chromium 十视口通过。详细证据与最终远端 CI 见 [验证记录](VALIDATION.md)。
- 修复后满足可选、默认关闭、只读开发版代码合并条件；合并前核对修复后精确 head 的完整 CI 与新增讨论。真实 R-NE-001..004、QQ/NAS、J4125 资源、平台稳定性与个性化仍待验；保留酷我 407 历史，不发布正式版、不部署 NAS。

## PR #5 集成要求

先合并网易业务，再让 [原生 FPK PR #5](https://github.com/Surc/fnos_music_hub/pull/5) 同步 main。其当前 head `c3eb70fb8337f5ae099a7d332b641dfd55d2ad03` 仍基于旧 main，成功的原生预览 CI 不代表包含网易功能。

下一轮 FPK 更新业务源码与锁定输入闭包，纳入网易可选 wheel、传递依赖、许可证和固定对应源码；更新组件/安装清单、构建提交与摘要，重跑基础/QQ/网易及原生预览检查。继续提供不含网易的旧预览时须明确标识并保持网易关闭，不能声称覆盖合并后的能力。现有产物不会因 main 合并自动更新。本轮仅记录与告知，不修改 PR #5 包装实现。
