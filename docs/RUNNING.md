# 开发版原生运行

当前版本 0.1.0a1 是第一条链路的开发实现，尚未生成 FPK。网关使用 Python/FastAPI + SQLite，前台为原生 HTML/CSS/JavaScript；Hot 独立进程负责实际下载调度。无需 Docker，不需要在 NAS 上安装 Node。

## 准备

- Linux / Python 3.11+、ffmpeg 和 ffprobe；正式 FPK 后续包含或核对这些运行依赖。
- 已运行的音桥 API，接口固定参考提交 `ad9ce203cbb7fdb54f9404a7abb2df605893f388`。本工程调用其 HTTP API，不复制签名算法，不接管官方 Socket。
- Hot 服务二进制，接口固定参考 `07e86c3d06243cf1350925c0dd3be704005abd29`。此源码的 headless 服务未附在 v2.0.1 桌面 Release 中；不能拿桌面安装包代替服务。开发机构建后复制二进制到匹配的 Linux 环境，NAS 不编译。

开发机构建 Hot：克隆其仓库，checkout 上述完整 SHA，执行 `git submodule update --init --recursive`，然后 `cargo build --locked --release --manifest-path crates/hotdownloader-server/Cargo.toml`。保留原 LICENSE/NOTICE，核对运行库兼容性。Hub 没有修改 Hot 源码。

## 配置与启动

1. 在项目目录创建 Python venv，安装 `python -m pip install -r requirements.lock`。
2. 复制 `config.example.json` 为 `config.json`，设置稳定的 NAS 实例 ID、独立数据目录、音桥 API base URL 和前台的真实 `public_origin`。生产入口使用 HTTPS，并保留 `secure_cookie=true`；仅本机 HTTP 开发可显式设为 false。
3. 在进程环境中设置音桥 API key（若音桥启用），以及每个用户的独立 Hot 访问令牌。配置仅保存环境变量名，不包含令牌。令牌至少 16 个字符。
4. 为每个用户填写实际飞牛音乐 GUID、独立 Hot 端口和不重叠的下载绝对目录。GUID 必须来自可信的当前用户接口；不按用户名猜测。先不配 users 也可以登录并从 `/api/me` 核对本人 GUID，但无法搜索/下载。
5. 用 `python scripts/run_hot_user.py --config config.json --guid <GUID> --binary /absolute/path/hotdownloader-server` 为该用户启动独立原生引擎。每个进程由宿主进程管理器分别守护。脚本使用 Hub 专属数据目录，首次初始化关闭音质自动降级，不读取旧 Hot/ext 的账号文件。
6. 用 `python -m hub --config config.json --host 127.0.0.1 --port 8790` 启动网关，再通过配置的同源 HTTPS 入口访问。一个数据目录仅允许一个网关进程；不要增加 Uvicorn workers。

`users` 一期同时是运行时授权清单。多个用户可以共用只读平台元数据，但不能共用 Hot 的凭据、任务或数据目录。本轮采用有限的逐用户运行时隔离，后续可替换成通过验证的账号作用域 Store；不是并发切换全局 Cookie。

下载目标目前只有当前用户的 `private` 目录。网关会核对 Hot 实际 downloadDir，并禁止自动音质降级。飞牛音乐库是独立索引目标，本版 `index_status=unsupported`，不会把下载成功显示成已入库。

## 数据与恢复

SQLite 保存会话、搜索元数据、本地收藏、不可变清单、任务投递记录和资产。飞牛 token 用 `vault.key` 加密，数据库与密钥文件为 0600，数据目录为 0700。备份时保留数据库及密钥；密钥遗失后需要重新登录。

任务接单先持久化，再交给 Hot。响应丢失时按投递前的任务快照回读；无法唯一确认则显示“结果未知”，不自动重下。Hot 重启后的 interrupted 映射为等待恢复，由用户显式恢复。更换用户引擎或目录会阻止旧任务继续使用新运行时。

本版退出只撤销 Hub 自己的会话，不注销其他官方客户端；已有匿名酷我下载任务仍由自己的 Hot 引擎管理。平台账号绑定/解绑和代次管理尚未开放。

## 检查

运行 `python -m pytest -q`、`python -m ruff check hub modules tests scripts`、`npm ci && npm test`、`npm run check`、`python scripts/verify_provenance.py`。Node/jsdom 仅用于开发检查。

真实 Hot 自测需在仓库外保存音频：`python scripts/live_hot_smoke.py --source /path/to/pinned/HotDownloader --work-dir /outside/project`。这会搜索并下载一首样本，记录真实音频校验结果；不测试 fnOS 身份或 FPK。当前环境两首样本均被酷我以地区限制 407 拒绝，详见 [验证记录](VALIDATION.md)。

当前列表接口返回当前用户最近 500 条任务/资产/收藏，历史分页尚未实现；不作为完整歌单导出接口使用。云平台登录、推荐歌单、远端歌单分页、自动入库、注入接管、反馈和 FPK 均有独立准入门槛，见 [迭代计划](ITERATION.md)。
