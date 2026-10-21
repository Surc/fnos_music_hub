# fnos_music_hub 开发约定

先读 README、SOURCE_VERSIONS.json、docs/ITERATION.md、docs/VALIDATION.md；模块修改再读 docs/DESIGN.md、docs/CONTRACTS.md 与 docs/ACCOUNTS_AND_FEEDBACK.md。

当前是设计骨架。不要声称已有可运行应用、真实账号验证、Docker/FPK 构建或 Release。接口仍是草案，最小链路验证后才冻结。

- 保持歌单推荐、歌曲下载、飞牛注入三个模块独立；内部组件按包拆分，进程数量按需要决定。
- 每个协议组件标记一个主上游，锁定完整 SHA；外围适配优先，必要补丁记录文件、原因、验证与回退。观察版本不推进采用基线。
- 严格服务端身份覆盖私人读写、事件、文件与任务。身份异常拒绝，不回退 shared/admin；不要信任前端 user_id。
- 歌单元数据独立于取流；快照保序、保重复、保未知项。Hot 持有实际下载调度，不重复实现队列。
- QQ 账号刷新单一所有者，绑定代次与凭据修订分开。真实播放反馈不从下载、墙钟、歌曲总时长或最后位置推算。
- 注入关闭后前台仍能认证；每个官方 Socket 只有一个接管者。原生 FPK 不要求 NAS 安装编译器或 Docker。
- Git 不包含 Cookie、token、账号数据库、用户历史收藏、音频、缓存或临时签名 URL。
- 本仓库维护 skill 为 `maintain-fnos-music-hub`；旧 `maintain-fnos-music` 的共享账号、只读发现、主音源三选一约束属于旧工程。

纯资料变更运行 `python3 scripts/verify_provenance.py`。实现代码后按改动新增有意义的验证，记录模拟/真实账号/设备/FPK 各层结论；历史测试数字不能作为新代码证据。提交时同步迭代、验证、来源与 skill 摘要；日常工作按会话已有授权推进。
