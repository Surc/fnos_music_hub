# J4125 原生 FPK 预览

2026-10-27 已公开 [v0.1.0-preview.2 GitHub prerelease](https://github.com/Surc/fnos_music_hub/releases/tag/v0.1.0-preview.2)，标签与实际构建提交均为 `d66d395254594ab08b7f09613d5df953bf792074`。最终发行附件和校验见 [发行记录](../../docs/fpk-preview/RELEASE_20261027.md)；下文的原生使用/升级/验收边界继续适用。

当前内网测试候选包版本 `0.1.0-preview.3`（尚未发布）；已发布 preview.2 不支持直接内网 HTTP。使用步骤见 [内网测试](../../docs/fpk-preview/LAN_TEST.md)。业务版本仍为 `0.1.0a1`。本目录实现输入准备、离线组包、产物校验和原生生命周期。**是否实际生成 FPK、SHA256、普通 Linux 服务测试及 J4125 安装验收分别以 `build-report.json`、`native-smoke.json` 和 [验证记录](../../docs/VALIDATION.md) 为准。** 不发布正式 Release，不部署真实 NAS。

## 官方契约与工具

2026-10-24 直接读取官方 [完整文档](https://developer.fnnas.com/llms-full.txt)，核对 [fnpack](https://developer.fnnas.com/docs/cli/fnpack)、[框架/生命周期](https://developer.fnnas.com/docs/core-concepts/framework)、[权限](https://developer.fnnas.com/docs/core-concepts/privilege)、[环境变量](https://developer.fnnas.com/docs/core-concepts/environment-variables)、[入口](https://developer.fnnas.com/docs/core-concepts/app-entry)、[CGI](https://developer.fnnas.com/docs/core-concepts/index-cgi) 和 [向导](https://developer.fnnas.com/docs/core-concepts/wizard)。搜索读取器不可达，直接 HTTPS 读取成功。已执行官方 `fnpack --help`、`create`、`build --help`，版本 1.2.3，支持 `build --directory`。

固定版本/下载 URL/原始 SHA256 见 [versions.json](versions.json)。fnpack 来自官方 `static2.fnnas.com`，实测摘要 `54b97fa7b70968c4d05c79840f5daeff508957d0bb2062fdb0376d00d9615c93`；官方未提供独立签名/校验源。使用官方工具生成包，不以自造归档替代 fnpack。

## 运行边界

| 项目 | 预览约定 |
| --- | --- |
| 应用 ID / 包用户 / 用户组 | `fnos_music_hub`，`run-as=package`；脚本拒绝 root |
| 架构 | Linux amd64；Rust `target-cpu=x86-64` + 静态 musl；FFmpeg 通用 x86-64、禁外部汇编；不使用 native CPU 编译 |
| 主端口 | 固定 `127.0.0.1:8790`；安装/启动检查；不自动换端口 |
| Hot | 每个配置的可信 GUID 独立进程、端口、token、状态/下载目录；仅回环 HTTP |
| 外部前置 | 已运行的音桥 HTTP API 与独立 HTTPS 根地址反向代理；本包不安装/接管音桥或官方音乐 |
| 桌面入口 | fnOS 登录保护的 CGI 启动页链接到独立 HTTPS 地址；业务 API/SSE 不经 CGI |
| 内含 | Python 3.12.15、锁定 wheel 闭包（含可选 QQ 与网易只读 SDK）、Hub Python/静态前台、Hot/FFmpeg/ffprobe、CA、许可证、内容清单 |
| NAS 无需 | Docker、编译器、系统 Python、Node、联网安装依赖或桌面 Hot 安装包 |
| OS 边界 | 全部 ELF 检查架构/动态库/GLIBC，构建上限 2.36，实际需求写入报告；需要 Linux pidfd 和一致的 procfs。不虚构最低已验 fnOS 版本，省略 `os_min_version` |
| 暂不含 | 网易/QQ 下载、自动入库、Socket 注入、旧 ext 迁移、真实播放反馈 |

运行仅使用包内媒体工具。FFmpeg 8.0.1 为音频校验构建：MP3、FLAC、AAC/M4A/ALAC、Ogg Vorbis/Opus、WAV/PCM，不提供视频转码或网络下载。唯一排除的 Python 标准库扩展 `_crypt` 不被 Hub 使用，避免依赖 NAS 的 `libcrypt.so.1`。ELF 检查不能替代 J4125 的 CPU/运行库/ACL 验收。

## 两阶段构建

在线阶段只在开发机/CI 执行，要求 Linux x86_64、Python 3.12、git、gcc、make、binutils、cmake、rustup；Rust 固定 1.99.1。使用干净 checkout，输入和输出放在仓库外：

```sh
python3 packaging/fpk/fetch_inputs.py \
  --work /build/hub-work --output /build/hub-inputs --jobs 4
```

准备器检查固定 Hot SHA/加密子模块、QQ SDK 与 MusicBox SHA，以及 Python/FFmpeg/musl/fnpack 下载摘要；musl 构建 Hot/FFmpeg，`cargo build --locked`，上游零补丁。Python 依赖取自基础、QQ、网易三份 lock，合并重复的相同版本并拒绝冲突/未锁定条目；QQ/MusicBox wheel 使用各自固定源码和 hatchling 1.27.0。RapidFuzz 3.14.6 使用固定 sdist/SHA256 与 scikit-build-core 0.11.6，按上游 `wheel.cmake=false` 构建完整纯 Python wheel，无源码补丁；避免 NAS 额外提供 libstdc++/GLIBCXX 或 SIMD 运行库。三份锁摘要和每个 wheel 的版本、依赖、许可证路径及 SHA256 进入输入闭包；离线阶段再次核对，不接受旧闭包。`inputs.json` 冻结每个实际输入文件/链接的 SHA256、权限、编译参数和工具版本。保留输入闭包可准确重放；GCC/runner 镜像未固定为同一发行镜像，因此跨环境重新编译不承诺字节一致。

离线组包接受已核验的第三方输入闭包和当前干净 Hub checkout。闭包可跨 Hub 迭代复用，组包时重新生成当前 Hub 的对应源码附件，分别记录组件构建环境与当前 Hub commit：

```sh
sh packaging/fpk/build.sh /build/hub-inputs /build/hub-preview
```

不联网、不编译。以 `--no-index --no-deps --no-compile` 安装本地 wheels；仅复制明确允许且受 Git 管理的 Python/静态资源，不复制整个工作目录。官方 fnpack 完成后，直接打开实际 FPK，核对 ID/版本、非 root 权限、脚本执行位、`app.tgz` MD5 和每个安装文件的 SHA256/权限/链接。拒绝音频、数据库、密钥、用户配置、运行日志及外部链接。

输出包含实际成功生成的 `fnos-music-hub-0.1.0-preview.3-amd64.fpk`、同版本 `-sources.tar.gz`、`SHA256SUMS`、`build-report.json` 和可审阅的 `stage/`。对应源码附件包含 Hot/子模块、固定 QQ SDK/MusicBox、所有 PyPI wheel 对应的同版本 sdist（含下载 URL/SHA256）、FFmpeg/musl 原始源码及 Hub 源码/构建说明；不在 FPK 内携带测试音频。包内保留所有许可证及 wheel 自带许可，分发时同时提供对应源码附件。QQ SDK 仍可选启用，许可证为 GPL-3.0-or-later；MusicBox 为 MIT，原始 LICENSE 单独保留。上游没有 NOTICE 时在 PYTHON-NOTICE.txt 如实记录，所有 wheel 自带 LICENSE/NOTICE 仍在 site-packages；wheelhouse.json 与 python-sources.json 可逐组件核对。

`SOURCE_DATE_EPOCH` 固定源码日期，包内容清单应稳定；fnpack 归档层的字节稳定性以实际重复构建结果为准，不因流程可重放便声称包字节一致。

## 配置与数据目录

`target` / `var` 由 `TRIM_APPDEST` / `TRIM_PKGVAR` 提供，不硬编码卷号。配置放在持久 `var/config`，不把凭据写回向导或 shell source。`TRIM_PKGETC` 的系统 `settings.conf` 不作为业务凭据入口。

| 路径 | 行为 |
| --- | --- |
| `target/runtime`、`server`、`bin`、`native`、`ui`、`licenses` | 可替换程序/资源，无用户数据 |
| `var/config/hub.json` | 独立实例 ID、音桥 URL、访问 origin/显式内网测试开关、GUID/端口/下载目录；0600，仅首次初始化 |
| `var/config/secrets.json` | 可选音桥 key 与本机生成的逐用户 Hot token；0600，不记录/展示内容 |
| `var/state` | Hub 数据库/vault.key、会话/收藏/快照、逐用户 Hot 状态；0700；备份完整目录含 SQLite 辅助文件 |
| `var/downloads/<用户目录>` | 用户互不重叠的私有下载根；不随升级复制，不扫描旧 ext，不自动入库 |
| `var/run` | 操作锁、监督器/子进程身份与健康状态；无凭据 |
| `var/backups/<时间-随机值>` | 旧程序/config/state，最后写入 `complete.json`；0700，不自动清理 |
| `var/active-program`、`var/rollback` | 仅指向本应用 target/backups；保留旧可运行程序应对新 Python 无法启动 |
| `var/failed-config-*`、`var/failed-state-*` | 回滚前的新状态副本，供本地排查，不上传 |

安装向导默认选择 HTTPS；也可显式选择内网 HTTP 测试，填写 `http://NAS私有IPv4:8790`。音桥 1.0.7 的默认 API 是 `http://127.0.0.1:18090/yinqiao/v1`（旧向导的 18086/api/v1 有误）；需先安装并启动音桥。填写实际根地址和音桥 API，已有配置永不覆盖。首次 `users={}`、`admin_guids=[]`、`qq_accounts_enabled=false`、`netease_enabled=false`；可登录通过 `/api/me` 核对本人可信 GUID，未配置用户不能搜索/下载。管理员停服后编辑 `var/config/hub.json`，将如下片段合并进已有配置，保留原实例 ID/state/origin：

```json
{
  "users": {
    "由当前用户接口核对的GUID": {
      "engine_url": "http://127.0.0.1:18787",
      "engine_token_env": "HUB_HOT_A",
      "download_root": "/实际应用var路径/downloads/user-a"
    }
  }
}
```

第二个 GUID 使用另一端口、变量名和私有目录。启动仅为缺失 token 生成随机值，不旋转已有凭据。音桥有密钥时仅在停服后的 `secrets.json` 中加入 `HUB_BRIDGE_KEY`，不放命令行、Git 或反馈日志。配置文件归包用户且 0600，ACL 另行实测。错误配置拒绝启动，不降级共享身份。

启用网易：停服后仅把 `netease_enabled` 改为 true，再启动。依赖已在包内，无需 NAS 联网安装；首次升级不覆盖已有配置，缺该字段仍默认 false。账号 Cookie 仅从 HTTPS 前台导入并核对 UID 后显式关联，见 [网易说明](../../docs/NETEASE.md)。网易目录不要求 Hot 账号；QQ 只读通过原独立开关启用。可同时启用两者；下载准入仍只允许酷我。

HTTPS 反代转发到本机 `127.0.0.1:8790`，保留正确 Host/Origin 与流式响应；外部地址与 `public_origin` 一致。包不内置 TLS 证书。默认不开放局域网明文登录；显式 `lan_http_test=true` 且 `secure_cookie=false` 时，只绑定 public_origin 指定的 RFC1918 私有 IPv4:8790，直接访问无需反代。密码和会话经明文传输，仅供可信内网测试；公网 IP、域名、loopback、IPv6、链路本地和 CGNAT 地址拒绝，Hot 仍仅 loopback。不从 fnOS 网关 Header 推断业务用户；音桥继续服务端验证身份。

## 生命周期与故障

`cmd/main start|stop|status`：运行 status=0，停止 status=3；其他失败返回非零，`TRIM_TEMP_LOGFILE` 只写无秘密的错误类型。操作 flock 串行，监督器另持常驻锁。预检真实 Python 扩展、加解密、媒体工具和全部端口；网易启用时另起临时子进程，在独立 XDG 中离线导入实际 SDK/原生扩展并验证 WEAPI/EAPI。缺依赖明确报告网易依赖缺失或损坏；关闭时不导入 NEMbox、不要求网易依赖，再启动每用户 Hot 与单个 Hub。Hub/Hot 健康、Hot token 访问、实际私有目录和禁止音质降级均通过才报告成功。音桥/音乐平台不可达不伪造业务可用，也不阻止独立网关健康启动。

身份包含 PID/boot ID/start ticks/UID，发信号先打开 pidfd 再重验，不按进程名批量 kill。任一子进程退出，监督器停止其他子进程，转未运行；不无限自动重启。先 TERM、有界等待后才 KILL 已确认身份。重复操作不增实例，不误杀端口上的其他进程。默认不保留上游 stdout/stderr，避免临时 URL/Cookie 落日志；业务错误仍走已脱敏 API。

升级前停服、确认 state 锁空闲，复制旧程序/config/state，**完整内容清单最后落盘后**才发布回滚点并切到旧程序槽。备份失败中止升级、保持停服/原数据，未完成备份不可用。备份需额外磁盘空间，不自动清理。

升级后强制用新 target Python 启动/验健康，成功才激活。新 Python 无法执行或健康失败时，shell 用备份旧 Python 停新进程、校验完整备份、保留失败状态、恢复匹配 config/state、启旧程序；回调仍报升级失败。应用中心版本标签可能仍为新包，须重新安装匹配旧 FPK。回滚也失败则停服保留备份并明确报错。fnOS 在解包阶段失败且未调用回调时不保证自动启动；数据未迁移，活动指针已指向旧程序，可通过应用中心再启动。断电及监督器 SIGKILL 在 spawn/登记间隙的恢复仍需设备测试，不能把应用脚本当作系统级事务。

卸载前同样停服/备份，卸载后不调用已移除程序、不删除 var/downloads/backups 或其他应用。官方持久 var 约定仍需具体 fnOS 实机核对，重要备份另复制。重装发现原 config/state 继续使用同一实例；数据库仍在而配置丢失则拒绝新建实例，先恢复匹配备份。无旧 ext 自动迁移或破坏性清空选项。

## 验证和待验收

```sh
python -m pytest -q tests/test_fpk_native.py
python -m ruff check hub modules tests scripts packaging/fpk
python scripts/verify_provenance.py
python packaging/fpk/verify.py /build/hub-preview/fnos-music-hub-0.1.0-preview.3-amd64.fpk
python packaging/fpk/native_smoke.py --stage /build/hub-preview/stage \
  --report /build/hub-preview/native-smoke.json --require
```

常规 CI 加入打包/生命周期回归和 shell 检查。独立 [预览工作流](../../.github/workflows/fpk-preview.yml) 支持手动触发及本目录的 PR 检查；准备输入、离线构建、校验 FPK，在普通非 root Linux 上真实运行包内 Hub + 两个 Hot，用实际包内 Python/依赖运行完整业务回归（测试工具在包外），验证网易默认关闭、双 SDK 同开、缺传递依赖时明确拒绝、关闭时基础/QQ 仍启动，以及启停、token 隔离、子进程退出、坏版本升级 shell 回滚、数据库/密钥恢复及卸载保留；只上传短期 Actions 预览附件和独立离线输入闭包（14 天），无 tag/Release。下载闭包后解包并用同一 Hub 提交运行 build.sh 可重放离线步骤；SHA256SUMS 覆盖 FPK、源码、输入闭包和安装清单/测试报告。

若本运行器为 root 或 `/proc` 与 PID 命名空间不一致，真服务 smoke 必须记 blocked，不为生产身份增加绕过。单元测试与普通 Linux 真服务结果分开记录。

实机须单独验：fnOS 干净安装/入口、TLS/音桥/真实双用户、完整下载/解码、NAS 重启、端口冲突、旧 ext 不被修改、升级/备份失败/回滚、卸载/重装保留、ACL、J4125 指令/运行库与 8GB 下单/双用户 CPU/RSS/磁盘。构建通过不勾选这些验收项。
