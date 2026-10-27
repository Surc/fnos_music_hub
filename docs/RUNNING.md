# 开发版原生运行

2026-10-24 新增 [原生 FPK 预览打包](../packaging/fpk/README.md)，NAS 无需系统 Python/编译器/Docker；候选包构建/哈希与 NAS 验收分开记录。以下仍为源码手动运行，历史“尚未生成 FPK”描述保留对应当时阶段。

执行前先读 [功能点验收清单](ACCEPTANCE_FUNCTIONS.md)、[平台验收清单](ACCEPTANCE_PLATFORMS.md)。原开发环境酷我 407 限制保留为历史观察；2026-10-26 用户本机 WSL 的 R-KW-001/002 下载技术复测通过，详见 [本地报告](HOT_LOCAL_RETEST_20261026.md)。人工试听、NAS 身份/安装和飞牛入库分别签收。

当前版本 0.1.0a1 是第一条链路的开发实现，尚未生成 FPK。网关使用 Python/FastAPI + SQLite，前台为原生 HTML/CSS/JavaScript；Hot 独立进程负责实际下载调度。无需 Docker，不需要在 NAS 上安装 Node。

## 准备

- Linux / Python 3.11+、ffmpeg 和 ffprobe；正式 FPK 后续包含或核对这些运行依赖。
- 已运行的音桥 API，接口固定参考提交 `ad9ce203cbb7fdb54f9404a7abb2df605893f388`。本工程调用其 HTTP API，不复制签名算法，不接管官方 Socket。
- Hot 服务二进制，接口固定参考 `07e86c3d06243cf1350925c0dd3be704005abd29`。此源码的 headless 服务未附在 v2.0.1 桌面 Release 中；不能拿桌面安装包代替服务。开发机构建后复制二进制到匹配的 Linux 环境，NAS 不编译。

开发机构建 Hot：克隆其仓库，checkout 上述完整 SHA，执行 `git submodule update --init --recursive`，然后 `cargo build --locked --release --manifest-path crates/hotdownloader-server/Cargo.toml`。保留原 LICENSE/NOTICE，核对运行库兼容性。Hub 没有修改 Hot 源码。

## 配置与启动

1. 在项目目录创建 Python venv，安装 `python -m pip install -r requirements.lock`。
2. 复制 `config.example.json` 为 `config.json`，设置稳定的 NAS 实例 ID、独立数据目录、音桥 API base URL 和前台的真实 `public_origin`。生产入口使用 HTTPS，并保留 `secure_cookie=true`；本机 HTTP 开发可显式设为 false；可信内网临时测试另显式设置 `lan_http_test=true`，public_origin 必须是 RFC1918 私有 IPv4 与明确端口，参见 [内网测试](fpk-preview/LAN_TEST.md)。
3. 在进程环境中设置音桥 API key（若音桥启用），以及每个用户的独立 Hot 访问令牌。配置仅保存环境变量名，不包含令牌。令牌至少 16 个字符。
4. 为每个用户填写实际飞牛音乐 GUID、独立 Hot 端口和不重叠的下载绝对目录。GUID 必须来自可信的当前用户接口；不按用户名猜测。先不配 users 也可以登录并从 `/api/me` 核对本人 GUID，但无法搜索/下载；启用网易可独立只读浏览，不依赖 Hot。
5. 用 `python scripts/run_hot_user.py --config config.json --guid <GUID> --binary /absolute/path/hotdownloader-server` 为该用户启动独立原生引擎。每个进程由宿主进程管理器分别守护。脚本使用 Hub 专属数据目录，首次初始化关闭音质自动降级，不读取旧 Hot/ext 的账号文件。
6. 用 `python -m hub --config config.json --host 127.0.0.1 --port 8790` 启动网关，再通过配置的同源 HTTPS 入口访问。一个数据目录仅允许一个网关进程；不要增加 Uvicorn workers。

`users` 一期同时是运行时授权清单。多个用户可以共用只读平台元数据，但不能共用 Hot 的凭据、任务或数据目录。本轮采用有限的逐用户运行时隔离，后续可替换成通过验证的账号作用域 Store；不是并发切换全局 Cookie。

下载目标目前只有当前用户的 `private` 目录。网关会核对 Hot 实际 downloadDir，并禁止自动音质降级。飞牛音乐库是独立索引目标，本版 `index_status=unsupported`，不会把下载成功显示成已入库。

## 数据与恢复

可选网易：开发机安装 `requirements-netease.lock`，配置 `netease_enabled=true`。固定 MusicBox 仅在临时短进程中按需读取，不增加常驻服务；账号导入、确认、更新与只读界限见 [网易模块](NETEASE.md)。NAS 安装预构建依赖。

SQLite schema 3 保存会话、搜索元数据、本地收藏、不可变清单、任务投递记录、资产、平台关联、加密登录尝试及歌单读取状态；schema 1/2 自动升级前先备份数据库与密钥，旧程序不能直接降级读取。完整快照保存在原 manifests 表，失败/中断仅保存状态；显式恢复从第一页开始，见 [QQ 完整快照](QQ_SNAPSHOTS.md)。快照历史提供游标分页和显式删除，删除保留小型幂等/冷却记录；数据库空闲页复用规则见快照说明。飞牛 token 用 `vault.key` 加密，数据库与密钥文件为 0600，数据目录为 0700。备份时保留数据库及密钥；密钥遗失后需要重新登录。

任务接单先持久化，再交给 Hot。响应丢失时按投递前的任务快照回读；无法唯一确认则显示“结果未知”，不自动重下。Hot 重启后的 interrupted 映射为等待恢复，由用户显式恢复。更换用户引擎或目录会阻止旧任务继续使用新运行时。

暂停/恢复/重试同样逐项持久化意图并回读，批量操作中途失败后先刷新核对，不盲目重发未知动作。若 Hot 已完成而文件校验失败，修复本地文件后重试会重新校验。后台按每任务串行，最多 4 个任务核对、1 个完整音频解码；其他任务控制可并行。schema 3 新增活动任务索引，终态历史不参与每轮扫描；此上限不是 J4125 实机性能验收结论。

本版退出只撤销 Hub 自己的会话及未完成关联尝试，不注销其他官方客户端；已有匿名酷我下载任务仍由自己的 Hot 引擎管理。可选 QQ 账号的启用、扫码/显式关联、代次与只读目录见 [QQ 模块说明](QQ_ACCOUNTS.md)。解除 Hub 关联撤销私人读取授权，不调用原生 Hot 的全局退出。

## 检查

运行 `python -m pytest -q`、`python -m ruff check hub modules tests scripts`、`npm ci && npm test`、`npm run check`、`python scripts/verify_provenance.py`。Node/jsdom 仅用于开发检查。

真实 Hot 自测需在仓库外保存音频：`python scripts/live_hot_smoke.py --source /path/to/pinned/HotDownloader --work-dir /outside/project`。这会搜索并下载一首样本，记录真实音频校验结果；不测试 fnOS 身份或 FPK。历史开发环境两首均为酷我地区限制 407；2026-10-26 用户本机 WSL 两首均完成并完整解码，详见 [验证记录](VALIDATION.md)。

当前列表接口返回当前用户最近 500 条任务/资产/收藏，历史分页尚未实现；不作为完整歌单导出接口使用。QQ 扫码/关联、只读推荐和歌单分页已可选实现，真实账号仍待验收；QQ 两轮观测完整快照已实现但真实验收待执行；网易只读目录已可选接入；网易下载、云端写入、自动入库、注入接管、反馈和 FPK 均有独立准入门槛，见 [迭代计划](ITERATION.md)。

## 前台开发与四种布局验证

浏览器前台已落地 PC/手机横竖屏与下载确认。运行 `npm ci --ignore-scripts`、`npm run check`、`npm test`；开发机/CI 安装 `npx playwright install --with-deps chromium` 后运行 `npm run test:browser`。后者只连接本地合成 API，截图与报告在忽略的 `test-results/`，不用于证明真实账号或音乐下载。GitHub browser 作业保存短期截图附件。NAS 只提供静态页面，无需 Node/Chromium。
