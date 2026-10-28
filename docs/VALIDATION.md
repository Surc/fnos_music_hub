# 验证记录

## 2026-10-28：首个用户引擎配置与能力状态修复

用户登录后发现所有平台均显示待接入。酷我公共搜索/下载本就不要求酷我登录；实际是首次users为空、可选QQ/网易模块关闭，加上前台状态文案混淆。已按用户提供的GUID及明确授权配置一个独立Hot、启用包内QQ/网易并停启核对，保留飞牛身份与用户隔离；前台分别显示未配置、未启用和未实现。修复候选preview.4的实际出包/升级结论另记。[配置与边界](fpk-preview/USER_SETUP_20261028.md)。

## 2026-10-28：main 重建与 J4125 首次安装通过

主干 `1ad75a4` 无待合并分支/PR，已重新离线构建 preview.3 并安装到 J4125/8GB/fnOS 1.2.0800，音桥1.0.7同步安装。实际包6623项、包内256项、Linux十三项生命周期通过；NAS停启、静态字节、五项未登录401/Host400及60.53秒十三次健康采样通过，真实登录页五视口通过。完整 [构建与实机证据](fpk-preview/MAIN_NAS_20261028.md)。

真实GUID登录、逐用户Hot、双用户ACL、完整下载、升级/回退/卸载、整机重启和资源预算仍待验；未发布新Release，历史407和旧产物证据保持独立。

本次基础217 passed / 29 skipped，包内256 passed / 无skip，37项jsdom与十视口合成API Chromium通过；Ruff、来源和Node语法通过。包外pytest工具缺py.py与Edge沙箱启动失败均已处理后重跑，不计旧历史数字为新代码证据。

## 2026-10-28：PR #6 合并核对

远端确认 PR #6 为 merged/closed，合并提交 `d67e558eb7790ca499e8a31b2b050ab85a0151e5`；无审核请求或未解决线程。fetch 后本地 main 快进，`git diff --exit-code b0d102b3a0409755ed0cd4f3fdc2f55583ba5350 HEAD` 通过，整个合并文件树与已核对分支一致。相对已通过两组 CI 的运行代码 `6d7619d`，后续提交只涉及资料/证据文件，不重复算作新测试。

本轮合并记录通过来源/skill 摘要、本地文档链接和 `git diff --check` 检查。候选包原有256项包内测试、13项普通Linux生命周期结果及摘要仍属于 `fbb1dcf` 构建，未宣称来自实际 main 合并提交。未新建 Release 或部署 NAS；真实安装、音桥GUID登录、ACL/资源、完整音乐下载仍待验。

## 2026-10-28：preview.3 实际内网候选核验

运行代码head `6d7619d`，CI合成构建 `fbb1dcf`；常规40533510659九项成功、原生40533510817成功（attempt2）。包内 **256 passed / 无skip**，非root普通Linux **13项**真实进程/生命周期检查成功，包含配置的RFC1918接口绑定和Hub健康；真实账号/平台仍未调用。原生ZIP SHA256与GitHub一致；逐项校验八份下载附件和实际FPK的 **6623文件/权限/链接**，并逐字节核对包内相关运行代码与本地head一致。FPK SHA256 `e917bf163df28da31c21e0c9a2b3a078dfeaa9f48c5baa6dd56c416778880644`。完整 [证据](fpk-preview/LAN_20261028.md)。

首次CI在Ubuntu依赖下载停滞，取消未完成项后只重跑未成功项；同head的重复push运行取消，未降低验证范围。期间本机WSL离线重组尝试使用已核验旧组件闭包，仅派生目标包版本元数据；实际FPK中两份config声明继承NTFS模板的0777，与预期0644不同，被校验器拒绝，未分发。最终交付来自普通Linux CI新构建并在本机完整静态复核，未跳过失败校验。原生工作流未修改，故CI归档标签/输入闭包文件名仍带preview.2；实际FPK、源码、bundle、manifest均核对为preview.3。输入闭包本轮未下载；不声称核验其内部内容。真实NAS安装、音桥登录、ACL/资源与完整下载仍待验。

## 2026-10-27：preview.3 内网 HTTP 测试候选

新增显式内网模式与错误音桥默认地址修正，详见 [内网说明](fpk-preview/LAN_TEST.md)。本机 WSL Python 3.12 全量 **217 passed / 29 skipped**（未安装可选 SDK）；其中身份/原生包装定向 **83 passed**。Ruff、Node 语法、**37项 jsdom** 和来源校验通过。新增配置拒绝公网/域名/loopback/CGNAT/IPv6/链路本地、安装失败不留错误配置、指定接口端口检查、Cookie/Host/Origin/CSRF及双用户会话/清单隔离。保留已有测试，不放宽认证或改地区限制记录。

本机 Edge Chromium 156.0.4314.42 以不安全 HTTP LAN origin（路由至本地合成API）检查 **十视口全部通过**（[原始报告](fpk-preview/lan-browser-report.json)），明确断言 isSecureContext=false、randomUUID不存在；覆盖登录、下载确认/幂等编号、快照、退出、旋转和布局。实际构建、包内业务回归与普通Linux的选定LAN接口真服务验证另行补录，不以此前preview.2报告替代。音桥1.0.7公开FPK的字节数/SHA256与上游一致，仅下载校验未安装；用户NAS、音桥真实登录、ACL/资源及完整下载仍待执行。

## 2026-10-27：合并提交的实际预览发行验收

PR #5 合并/标签/实际构建提交均为 `d66d395254594ab08b7f09613d5df953bf792074`，GitHub prerelease 已于 2026-10-27 22:51:36 +08:00 公开。最终 PR 常规运行 40520258014 attempt 2 九项成功（仅重跑停滞的未完成组合项）；原生 40520258147 成功。合并提交常规 40522337002 九项成功，重新原生发行构建 40522382993 的包内 239 passed、非 root 十二项成功。下载两份新 CI ZIP 验 SHA256，九份附件逐项验证，实际 FPK 的 6623 文件/权限/链接通过独立复核；上传后九份 GitHub 资产大小和 SHA256 均一致。详见 [最终发行记录](fpk-preview/RELEASE_20261027.md) 和对应原始报告。

本机 WSL 两首真实下载仍与 FPK/NAS 验收分开；未执行真实 NAS 安装、升级、ACL、资源或人工试听。历史 407、早期 preview.1/2 的 CI 与哈希保留；没有把旧候选哈希或资料 head 当作新发行来源。

## 2026-10-27：PR #5 独立复核与发布授权

对精确 head `18231426815bfe1c414f317c62982ec62a14df2f` 导出审阅，85 个运行/打包/测试/CI 文件逐字节核对一致。本地 Python 3.12 基础回归 **200 passed / 29 skipped**，未安装的可选 SDK 不计作通过；包装/生命周期 **46 passed**。Ruff、shell 语法、来源/摘要/175 个文档链接检查通过。确认与成功 CI 业务 head `a0a426e241bb58cfb7fd565c1ea6bcd2d41c7491` 之间只有十个资料/证据文件变化；远端常规九项成功，原生作业日志确认包内 239 passed 与非 root 生命周期步骤成功。未发现预览代码合入的阻断缺陷。

用户随后于 2026-10-27 明确授权合并发布。本次将补齐本机下载证据、最终 head CI 与预览发行记录；实际 tag/构建提交/附件 SHA256 以最终发布记录为准，不提前记成已发布。NAS 实机、QQ/网易账号、ACL/资源及录音人工试听仍待验。

## 2026-10-26：用户本机酷我下载复测

基线 main `823a2de946ebbd64207117d9551c7d0eb7d56237`。Windows 本机已有 Ubuntu/WSL2，Python 3.12.3；固定 Hot `07e86c3d06243cf1350925c0dd3be704005abd29`、um_crypto `5dad838c33c3e4aab198d995160d3fbb9968470f`，以 Rust 1.99.1 / dev profile 构建未修改源码，220 个 registry 包均按 Cargo.lock SHA256 校验后离线编译。二进制 SHA256 `1c3fae5df821cabec25f515d5db28d1d4693e6b56e4f1bc60117c7dc6df4ed20`；这是新构建，不与历史 Linux 二进制混同。

R-KW-001/002 固定 RID、320kmp3、禁止降级，以各自独立 Hot 数据目录先走仓库原有 `scripts/live_hot_smoke.py`，再单独走原生 HTTP 搜索/任务链路。两首均完成，真实 MP3 320000 bps，完整解码/时长校验通过，每首原生与 Hub 资产 SHA256 一致；独立来源协议探测均 HTTP 200 / 业务码 200。**本机未复现 407**；没有修改下载实现或上游源码。详见 [说明](HOT_LOCAL_RETEST_20261026.md) 与 [脱敏 JSON](HOT_SMOKE_LOCAL_20261026.json)。

现有下载/任务恢复定向回归 `tests/test_core.py tests/test_review_regressions.py`：**40 passed**，保留既有 Starlette/httpx 弃用提示。Ruff、来源/摘要/文档链接检查和 `git diff --check` 通过；Windows 自动 CRLF 检出造成的 13 处摘要差异已按原记录 SHA256 恢复为精确 LF 字节，未改变 Git 内容。这些自动回归与上述真实下载分别记录。人工试听录音、真实飞牛身份/双用户、NAS 安装、入库与 FPK 均未验收；音频、引擎日志、凭据及临时链接不进入 Git，2026-10-21 两首 407 历史不改写。

## 2026-10-25：PR #5 网易整合预览验证

最终结果：常规 CI 40173694578 九项与原生 CI 40173694577 全部成功。FPK 66,760,897 bytes / 6623 安装文件、包内 239 passed、非 root 十二项生命周期/故障检查通过。已下载主附件核对 ZIP/FPK/源码与七个文件摘要；首次 libstdc++ 拦截和修复均保留。详细报告、来源与真实待验边界见 [整合证据](fpk-preview/NETEASE.md)。

本轮基线为最新 main `823a2de946ebbd64207117d9551c7d0eb7d56237` 与原生分支 `c3eb70f`。新 `preview.2` 的精确源码、构建/SHA256、CI 和自动检查单列 [整合证据](fpk-preview/NETEASE.md)，不沿用 preview.1 的 5915 文件/旧哈希。旧记录均为历史结果；真实账号、完整音乐下载与 J4125/fnOS 安装升级/性能没有执行。

## 2026-10-24：PR #4 独立审核与修复复核

交付结果：修复 head `0a5118200e2d9371109371b13f2cdcf89a9d4bf8` / tree `f8d9c41300039fd0e8dfa9dea0ecbf28d0c026bf` 与本地已测一致；[该提交 PR CI 40085536584](https://github.com/Surc/fnos_music_hub/actions/runs/40085536584) 八项全部成功，含 Python 3.11/3.12 基础、QQ、网易、web、browser。无未解决线程，已提交 [Comment 审核](https://github.com/Surc/fnos_music_hub/pull/4#pullrequestreview-5637917573)；因同为 PR 作者，没有提交或宣称第三方批准。随后转 Ready 并合并，main 为 `84f814d997017b07c28b821f70db5fdc7c5cbe9b`（2026-10-24 18:26:12，UTC+8）。[合并页面凭证](netease-pr4-merged.jpg)。来源采用记录在确认合并后更新；实际账号/NAS 待验状态不变。

重新查询远端精确 head `8ae89c835849bb377172c8e9186107dca26760ae`，内容树 `0dbebe662e9c5240c1b5e3727b428ae056d564cf` 与本地审阅基线相同；[CI 40078403156](https://github.com/Surc/fnos_music_hub/actions/runs/40078403156) 八项均成功，审核/讨论/未解决线程为空。发现和最小修复见 [独立审核](NETEASE_REVIEW.md)，最终修复后的 head/CI 与合并结果另行记录。

- 新增回归先复现响应 Cookie 进入后续请求、异常 ID 导致整页失败或错误匹配：4 failed / 2 passed。修复后完整 Python 3.12（QQ+网易）**193 passed**；新增 21 项回归包含可信 UID、在途 bind/rotate 撤销、关闭网易与缺依赖。
- 独立干净网易依赖环境 **182 passed / 1 skipped**，pip check 通过；QQ+网易环境依赖检查也通过。只保留既有 Starlette/httpx 弃用提示。未变更任何运行依赖锁、上游源码或 schema。
- 实际一次性 OS 子进程检查超时/取消/输出超限、非对象 JSON/非法 JSON，均回收进程、移除 0700 XDG、释放后续读取能力；9 次并发隔离临时目录且不超过 4 个同时运行。短进程输出、网络及凭据均为合成，未读取真实私人平台。
- 前台 Node 语法、**37 项 jsdom** 和 **10 个 Chromium 视口**通过，覆盖原 QQ 快照/酷我任务及网易导航、确认/旋转/分页；[本轮报告](netease-ui-screenshots/review-browser-report.json)。Ruff、来源/摘要、diff 检查和 wheel 构建通过。运行时改动没有改前端静态文件。

按默认关闭、可选只读开发版评估合并条件；真实网易 R-NE-001..004、QQ/NAS、J4125 性能与平台推荐效果仍待验，酷我 407 历史保留。不发布正式版本、不改 FPK。PR #5 必须在业务合并后同步 main、网易依赖闭包、许可证/对应源码并重新验证；现有成功预览仍不含网易目录。

## 2026-10-24：网易只读目录与账号隔离

基于已合并 main `04677d32b96a0b824c2148001458d581f9f8f22c`，其 [Actions 39973794020](https://github.com/Surc/fnos_music_hub/actions/runs/39973794020) 六项全部成功。当前开发分支 `feat/netease-readonly-catalog`，实现及未开放范围见 [网易模块](NETEASE.md)。固定 MusicBox 0.5.3 / `9c405f4bae2384d0410e63f8b816a707553d72d3` 与旧 ext 接口已核对，上游源码零改动，未合并时不推进采用 SHA。

- 完整 Python 3.12 / QQ+网易依赖环境：**172 passed**，其中新增 **52 项**网易契约/SDK用例；原 QQ 快照、账号、酷我任务、资产和审核回归一并通过。只保留既有 Starlette/httpx 弃用提示。
- 独立干净 venv 安装网易锁：`pip check` 无冲突，**161 passed / 1 skipped**（未安装 QQ SDK）；wheel 构建通过。MusicBox 通过固定 Git SHA 安装，NAS 不需要 Git/编译器，发行需预构建 wheel。基础模式和 Python 3.11 由新增/既有 CI 矩阵检查。
- 网易覆盖显式确认、加密存储/输出白名单、双用户并发、失效不匿名回退、不退出有效飞牛会话、UID/代次/修订、解绑换号、同号更新、旧成功和旧错误、退出、重复/未知/缺详情、来源总数/页长度、截断、CSRF、SQLite 原子回滚及不重启重试、任务门面拒绝网易下载。SDK 测试实际调用固定 MusicBox 的 WEAPI/EAPI 构造，HTTP 边界为合成，不能据此证明真实签名/设备/目录可用。
- `npm run check`、**37 项 jsdom** 通过，包含新增 **6 项**网易交互：公开浏览、UID 确认/更新、失败目录/歌曲翻页、解绑后的迟到推荐、平台失效及关闭核对弹层后迟到响应。QQ 原有测试保留。
- 本地 Chromium **153.0.8010.0** 的十种 PC/手机横竖视口通过，保留原 QQ 两轮快照/1000 项/酷我确认流程；新增网易 UID 关联、私人歌单、重复/未知、账号推荐、解除关联与旋转保留 Cookie 表单。首次标准 Playwright 浏览器下载失败，改用 NPM 官方 registry 的 Chromium 包；补装有校验和的 WenQuanYi 中文字体后重跑。中间一次缺字体配置的启动失败未记为通过。最终报告和四张截图见下文；CI 使用自己的标准 Chromium，独立记录。
- Ruff、`git diff --check`、来源/锁定依赖/数据库 schema 与 skill 摘要、本地文档链接检查通过；维护规则 1.5.0 已验证并推送个人 Skills Git `114790b`。QQ/Hot/音桥已合并采用基线、旧工程双来源和酷我两首 407 历史保持不变。

上述全部私人平台响应、账号与浏览器 API 为合成，音频是既有生成测试音。真实 R-NE-001..004、QQ/NAS、J4125 性能、手机键盘/安全区与 FPK 仍待执行；没有把普通推荐标为已验收个性化每日推荐，未发布 Release/FPK。

远端交付：[PR #4](https://github.com/Surc/fnos_music_hub/pull/4) 为 Draft/Open。代码提交 `cd95d020556ccd7708f0953976e802e963f933c2` 的内容树 `727801a07856d18a02de22ed21b22816f4d9b2b7` 与本地已测 `93d2266` 完全相同；[push 40077854755](https://github.com/Surc/fnos_music_hub/actions/runs/40077854755) 和 [PR 40078076740](https://github.com/Surc/fnos_music_hub/actions/runs/40078076740) 各八项全部通过：core/QQ/网易的 Python 3.11/3.12、web、browser。远端网易 3.11 日志确认 **161 passed / 1 skipped** 及依赖检查通过；其他矩阵和标准 Chromium 十视口同时通过。追加资料不改变运行代码、上游采用或真实验收状态。[PR 创建记录](netease-ui-screenshots/pr-draft.jpg) 为当时截图。

浏览器证据（真实 Chromium、合成 API）：[原始报告](netease-ui-screenshots/browser-report.json)，[PC 横屏](netease-ui-screenshots/netease-pc-landscape.png)、[PC 竖屏](netease-ui-screenshots/netease-pc-portrait.png)、[手机竖屏](netease-ui-screenshots/netease-mobile-portrait.png)、[手机横屏](netease-ui-screenshots/netease-mobile-landscape.png)。

## 2026-10-24：第一个实际 FPK 候选

开发机的输入构建、离线组包和静态校验已实际执行，详见 [候选证据](fpk-preview/EVIDENCE.md) 和原始 JSON 报告。候选 `0.1.0-preview.1` 的源码提交为本地 `5a6157b0768c94ecba18865f1876e104bfbc3067`；两次隔离临时目录的离线构建均通过 5915 个安装文件及 fnpack MD5/SHA256/权限校验，安装内容和对应源码相同，外层 FPK 字节不同，不承诺 fnpack 字节级确定性。交付选构建 A，SHA256 `c0e7528e8c8e532388a3158ebf0b567becc11142e9914f15119fde3ef7117d32`。

最终 Python **157 passed**（原生包装 37 项），jsdom **31 passed**，语法/Ruff/来源/差异检查通过。实际包内 Python 原生扩展/加密/SQLite、Hub + 两个 Hot 的回环健康和私有设置、生成 MP3/FLAC 的同 FD probe/完整解码通过；这组在开发机以 root 运行真实组件，没有通过监督器，也没有连接音桥或音乐平台账号。

完整监督器本地 smoke 被 UID=0/procfs 不一致阻断，真实非 root Linux 结果留给 PR 的预览工作流。一次共享目录重复组包出现权限差异并被校验拦截，未签收；改用独立 `/tmp` 的两轮均通过。官方 fnpack 会往 app.tgz 注入两份权限配置，并把输出放在调用工作目录；已适配且拒绝重复归档成员。没有篡改/放宽实际内容校验来接受失败包。

未发布正式 Release、未合并本轮 PR、未部署 NAS。J4125/fnOS 安装/升级/回滚/卸载/ACL/资源、真实身份/账号、完整音乐下载和历史酷我 407 仍单独待验。

最终候选包含 TRIM_APPDEST/TRIM_PKGVAR 符号链接路径归一化，以及首个真实非 root CI 发现的 TCP TIME_WAIT 重启修复。首轮 CI 输入和 FPK 静态步骤成功，生命周期在退出后重启时报 EADDRINUSE；端口预检已启用 SO_REUSEADDR，并以真实 TCP 测试证明仍拒绝活动监听。保留 [失败原始摘要](fpk-preview/ci-first-run.json)，修复后的工作流结果见 PR #5 检查，不覆盖失败记录。

## 2026-10-24：原生 FPK 预览实现与构建准备

基线 main `04677d32b96a0b824c2148001458d581f9f8f22c`。官方 `llms-full.txt` 直接 HTTPS 可达，fnpack 1.2.3 下载摘要与 `--help/create/build --help` 已核对；固定下载/组件见 `packaging/fpk/versions.json`。原 Hot 和子模块已按固定 SHA 取得，Rust 1.99.1/musl 静态 Hot 已在开发机编译完成；不是 NAS 构建/运行验收。

本地 Python 3.12.15 + 固定 QQ SDK 完整业务/打包回归 **150 passed**，包含新增 **30 项**原生包装受控测试；仅保留既有 Starlette/httpx 弃用提示。覆盖配置重装保留、私有 token、端口/路径/HTTPS 拒绝、PID 复用、串行锁、备份/失败/完整性、数据库与密钥回滚、卸载保留、输入篡改/归档穿越/音频密钥排除及图标/身份一致性。实际候选包结果完成后另追加，不以脚本通过代替 FPK 构建。

当前运行器 UID=0，且 Python PID 与 procfs self PID 不一致；生产监督器拒绝此环境，真服务集成需普通非 root Linux。受控测试不算真监督器或 fnOS 安装通过。新增手动 Actions 预览工作流执行输入/组包与普通 Linux 真服务 smoke；源码接入不代表已运行。

首轮离线准备在 ELF 校验中拦截 Hot：虽无 NEEDED 动态库，musl GCC 的默认 PIE 仍写入 `/lib/ld-musl-x86_64.so.1` 解释器；该轮未进入 fnpack，不记为构建成功。随后显式静态 relocation/GCC 链接遇到 Rust rlib 格式错误，改用固定工具链内的 rust-lld 和独立 target 目录，最终产物须重新检查。另移除 pip 的绝对 staging shebang/本地 direct URL，重建安装 RECORD，避免产物泄漏开发路径或因组包目录不同而漂移。

保留历史酷我 407、QQ/NAS/手机实机待验状态。本轮不连接真实账号/NAS、不下载音乐、不接管官方 Socket、不改 ext，不创建正式 Release。

## 2026-10-23：Astra 整体审核修复

基线 main `d6bef0aad6ae1c8774db9d0c023a3e17438a7359`（PR #2 已合并），其 [Actions 39955616620](https://github.com/Surc/fnos_music_hub/actions/runs/39955616620) 六项通过。本轮在 `fix/astra-review-hardening` 修复，逐项说明见 [Astra 记录](ASTRA_REVIEW_FIXES.md)。固定上游和真实平台证据未变。

- 本地 Python 3.12、可选 QQ SDK 环境：完整 `pytest -q` **120 passed**，包含新增 **20 项**审核回归；仅保留既有 Starlette/httpx 弃用提示。覆盖部分控制超时/重启、共用 Hot job、原生完成后本地重验、并发控制、注销边界、扫码清理、目录 FD 竞态与活动索引。
- `npm run check` 与 jsdom **31 passed**。新增失败的下一页/上一页/推荐游标重试、慢刷新单请求与切页隔离；文件详情核对实际 container/codec。新分页用例最初未等待按钮加载完成，补上可操作状态等待后定向和完整测试均通过。
- Astra 二次审核发现共享原生任务状态未同步的 P2 回归，修复后独立跑相关 **6 项**定向测试通过，确认关闭；未发现这处修复新的阻断问题。
- Ruff、`git diff --check`、14 个来源观察/研究原文/skill 摘要和本地链接检查通过。清单已统一 schema 3、完整快照能力、合并采用证据；维护 skill 1.4.2 按仓库及个人 Skills Git 同步。
- 本地 `npm run test:browser` 在启动时因缺少 Chromium 可执行文件失败，**没有算作通过**。十视口脚本新增 QQ 第 2 页失败后仍重试第 2 页、文件容器字段断言；远端 CI 结果另行追加。

所有平台响应与账号为合成边界，音频为生成测试音；真实 QQ/NAS、酷我本地复测、手机硬件与 FPK 仍按原验收清单。GitHub 连接器创建分支返回 403（集成无写权限），使用用户已授权的网页登录提交流程。

远端已提交 [PR #3](https://github.com/Surc/fnos_music_hub/pull/3)。代码提交 `f2f7174aefc7a6ee8ff986e273f75d7fe64e0762` 的完整内容树 `3b4ea6497c4125f53639fdd3188cff1776834bce` 与本地已测 `8e392e2525e951ca461f8bdf39590643508a1b4e` 相同。维护 skill 已推送个人 Skills Git `1e33b59a21b2adc2c10dcca56336c2cb8c19e680`。来源校验另用独立临时副本确认错误 schema、快照能力和采用 SHA 均能被拒绝。

同一代码 SHA 的 [push 39970198087](https://github.com/Surc/fnos_music_hub/actions/runs/39970198087) 已通过 core 3.12、QQ 3.11/3.12、web 和 browser；[PR 39970615832](https://github.com/Surc/fnos_music_hub/actions/runs/39970615832) 已通过 core 3.11/3.12、QQ 3.11/3.12 和 web。基础模式 **109 passed / 1 skipped**，QQ 模式 **120 passed**，jsdom **31 passed**，Chromium **10 种视口通过**；依赖检查、wheel、Ruff、来源检查包含在对应已成功作业内。归档时两次运行各有一项仍在安装环境依赖，未将其标成整组完成；逐项成功的 job/run ID 保存在来源清单，最终合并检查以 PR 为准。

浏览器证据取自 push 的作业 `120470533606`，附件 `12509485229` 的 SHA256 为 `99721c3c0a7394a345976c0cf88c332a18782a351667d57257a23d8898e67d3f`。保存未改写的 [十视口原始报告](qq-ui-screenshots/astra-browser-report.json)，包含失败翻页同页重试与实际容器/编码显示，以及已有快照、旋转、1000 项、解绑后历史与删除流程。报告摘要纳入自动检查；真实设备与平台结论不变。

## 2026-10-23：合并后复查与恢复修复

基于 main `535ed137c4bcc9827dc74106cdde7b434482a760`。该合并提交 [Actions 39948660461](https://github.com/Surc/fnos_music_hub/actions/runs/39948660461) 六项全部通过；替代此前仅记录提交前 CI 的交接状态。

复查先复现 4 个失败场景：初始写入失败、取消清理写入失败各造成持续 409；空历史后生成成功缺少查看入口；QQ 翻页 503 清空本地快照入口。修复后定向测试通过。新增测试还覆盖完成发布/删除事务回滚、跨用户历史及游标拒绝、分页/重启、删除重放/CSRF/在途冲突、冷却保留和同键不重抓，QQ 关闭时的本地历史、1000 项原序/重复/未知、分页/确认删除、迟到历史不得覆盖完成状态或退出后页面。

本地 Python **100 passed**，前台 jsdom **27 passed**；Ruff 与 Node 语法通过。已有 Starlette/httpx 弃用提示保留。本地 Chromium 未安装，`npm run test:browser` 在启动阶段失败；未将其计作通过。十视口新增 1000 项滚动、解绑后本地查看、确认删除；远端实际结果见下文。全部平台响应为合成测试，未新增真实 QQ/NAS/FPK 结论。

远端交付：GitHub 连接器写入返回 403，继续使用用户此前授权的网页登录提交。`4151d38c096178025d09a00c37704aa06a317cc0` 的完整内容树 `2741590cd37ccaafccb5523df25768b26f065d97` 与本地已测版本一致，形成 PR #2。首次 [Actions 39952921386](https://github.com/Surc/fnos_music_hub/actions/runs/39952921386) 五项通过，browser 因新增脚本在扫码尚未关联时提前执行快照历史导航，被真实弹层拦截而失败。修正提交 `3d8cc1479be866fe88f57942e1100e5b52a8efab` 仅移除误插入的前置步骤，保留解绑后的本地快照检查；没有改变应用运行代码。

第二次 [Actions 39953230850](https://github.com/Surc/fnos_music_hub/actions/runs/39953230850) 五项通过，browser 在 1440×900 的 1000 项明细中检出实际界面缺陷：弹层 y=141、高度=868，底部超出视口。桌面定位按 650 像素计算，但内容高度此前只受视口约束。修复为弹层/内部容器分别最多 650/648 像素，并保留小视口限制和内部列表滚动；曲目长文本允许任意位置换行。额外加入 504 字符无空格标题的横向溢出断言。提交 `33a326af18d107fd6713ec5270b6140067dc1e3f` 内容树 `24592f7f7024aa996d710869f7b9d8a19e18cc3c` 与本地修复完全一致。

该提交的 push [Actions 39953935354](https://github.com/Surc/fnos_music_hub/actions/runs/39953935354) 六项全部通过：core 3.11/3.12、QQ 3.11/3.12、web、browser。基础模式 **89 passed / 1 skipped**，QQ 模式 **100 passed**、前台 **27 passed**、Chromium **10 种视口**；锁定依赖、Ruff、来源/文档与 wheel 构建通过。同 SHA 的 PR [Actions 39953939767](https://github.com/Surc/fnos_music_hub/actions/runs/39953939767) 浏览器作业也通过，下述证据取自该作业。完整流程覆盖原分页、选曲及酷我确认任务，新增 1000 项/长标题、旋转、解绑后本地读取与确认删除，没有额外创建下载任务。

附件 `12500888740` 下载后 SHA256 为 `780a3658956a9a04146392453ce25abd64735b7ca3a5bdef3be6ee4876f5a88a`。已保存未改写的 [原始报告](qq-ui-screenshots/qq-recovery-browser-report.json)，并逐张检查 [PC 横屏](qq-ui-screenshots/qq-recovery-pc-landscape.png)、[PC 竖屏](qq-ui-screenshots/qq-recovery-pc-portrait.png)、[手机竖屏](qq-ui-screenshots/qq-recovery-mobile-portrait.png)、[手机横屏](qq-ui-screenshots/qq-recovery-mobile-landscape.png) 的列表尾部和可见关闭入口。源码清单记录每个文件的摘要，验证脚本一并检查；此前失败运行和旧截图保留。这些均为合成 API，不证明真实 QQ/NAS 可用。

## 2026-10-23：QQ 完整歌单快照

基线：PR #1 的 `383bdee0b0ffce0391615c128a5e2ef9918623bc`，仍在 feat/core-download-slice 开发。固定 QQMusicApi `27861e51432ea6b6e88dc35c4e8c8e239c0339e8` / 0.8.2 和 Hot `07e86c3d06243cf1350925c0dd3be704005abd29`；上游源码/依赖锁未改，没有新平台实测。

- 本地 Python 3.12 独立 venv：`python -m pytest -q` **93 passed**；包含 38 项新增完整快照场景及 11 项真实固定 SDK / 合成 Transport 检查。已有身份、资产、任务幂等/恢复和 QQ 账号回归一并通过。仅保留已存在的 Starlette TestClient/httpx 弃用提示，未为本轮额外升级依赖。
- 快照覆盖 0/1/100/101/205/1000 项、跨页重复/未知/原序、1001 项与字节超限、等数替换/重排/未知变化、目录漂移、总数/页长/终止不一致、请求超时及真实 asyncio 超时/取消、限流持久冷却、同用户并发拒绝、跨用户并发/越权、会话撤销/身份变更、解绑/换号/同号修订、schema 1/2→3 与进程中断后从头恢复。失败没有部分 manifests/songs/tasks；原酷我任务重放保持原 ID。
- 固定 SDK 新增两轮 205 项测试：实际构建/签名 CgiGetDiss，song_begin 顺序为 0/100/200/0/100/200，重复与未知条目穿过 SDK 后保留；每轮凭据只读且每次 Client 关闭。合成 Transport 不证明真实平台接受设备/签名或歌单稳定性。
- Node 语法检查与 **22 项 jsdom 通过**：原分页/选曲/确认、快照与预览并存、旋转、快照请求丢响应回读、漂移重试复用句柄、退出后迟到响应隔离。QQ 下载依旧禁用；快照动作不投递任务。
- Ruff、`git diff --check`、来源/技能摘要与本地文档链接检查通过。维护 skill 1.4.0 已校验并推送个人 Skills Git `be914de`；来源采用 SHA 保持不变。
- 本地 `npm run test:browser` 因缺 Chromium 未运行；尝试 Playwright 下载后得到损坏/空 ZIP，安装失败。实际 Chromium 验证改由 GitHub Actions 执行，见下述独立记录。

远端交付：命令行无写入凭据、GitHub 连接器返回 HTTP 403 后，用户明确授权网页提交；27 个文件已通过 GitHub 上传到原开发分支。远端 `5a4d4bd3768cdfb39036e07890053daf28b1537f` 内容树 `5260f8dcae8b9d8b2f5a841feb5c9dfcc8b1da23` 与本地已测文件完全一致。首次 [Actions 39944943303](https://github.com/Surc/fnos_music_hub/actions/runs/39944943303) 的其余五项通过，browser 因新增快照用例误用下载确认弹层选择器而失败；修正为分别检查下载/详情弹层及唯一关闭按钮，未修改应用运行代码。

修正提交 `c65242e390ea5603c9f283590fb6b6eddf17994c` 的 [Actions 39945305983](https://github.com/Surc/fnos_music_hub/actions/runs/39945305983) 六项全部通过：core 3.11/3.12、qq 3.11/3.12、web、browser。基础模式 **82 passed / 1 skipped**；QQ 模式 **93 passed**；**22 项 jsdom** 与 **10 种视口 Chromium** 通过，包含原分页/选曲/任务确认及新增快照生成/回读/明细/旋转、不额外创建任务。锁定依赖、pip check、Ruff、来源/文档与 wheel 构建通过。

浏览器附件 `12498305742` 下载后 SHA256 核对为 `aa3ed4f9fc5fcdc329974eaf49a90e2cede8dde5281c99d3b42f22a860b326bf`；保留未改写的 [原报告](qq-ui-screenshots/qq-snapshot-browser-report.json) 和四张快照明细截图，逐张检查 PC/手机横竖布局、文字及关闭入口。原报告 coverage 文案沿用旧清单，新增快照断言以该提交的 `tests/web-browser.mjs` 和新截图为据。这是实际 Chromium + 合成 API，不是实际 QQ/NAS 歌单验收。

用户随后明确要求合并 PR #1；完成本轮资料提交并核对最终 CI 后执行合并。没有发布请求，QQ 下载准入与真实平台验收不随合并改变。

完整性为 **double_read_verified / atomic=false**，并非平台原子快照；ABA/稳定旧缓存等检测边界见 [完整规则](QQ_SNAPSHOTS.md)。真实 QQ R-QQ-005/006、NAS/J4125、Hot 内部刷新条件写入、手机实际键盘/安全区仍待执行。历史酷我 407 与 R-KW-001/002 不改写。未开放 QQ 下载、未改 Hot 源码、未构建/发布 FPK 或 Release。

## 2026-10-22：QQ 账号门面与只读目录

- 本地 Python 3.12：新增平台账号/严格凭据文件测试及真实固定 QQMusicApi 请求/签名/错误边界测试，54 项全部通过（含 10 项真实固定 SDK 合成传输检查）；没有调用真实 QQ/音桥/NAS。真实 SDK 仅以合成 Transport 和合成 Android 会话/QIMEI 检查 wire 请求，不证明平台当前接受该设备/签名。
- SQLite 关联持久化、会话专属 QR 图片、扫码与关联分离、解绑时在途读取/绑定、同账号修订与换号代次、过期/限流/断网、重复/未知元数据、分页预览，以及两个 SDK Client 的账号隔离均有回归。Hub 与 SDK 不刷新/写回 Hot 凭据。
- 前台已新增 QQ 关联/推荐/歌单路径和旋转回归；Node 语法与 18 项 jsdom 通过。提交 `017d3b74a475e7fe5232128a8dbdc22ab3c7b7d4` 的 [Actions 39751963284](https://github.com/Surc/fnos_music_hub/actions/runs/39751963284) 已通过 web、browser、core 3.11/3.12、qq 3.11/3.12 六项作业。基础模式 44 项通过并跳过 1 个可选 SDK 测试模块；QQ 模式 54 项通过，验证锁定 SDK 能按完整 SHA 安装、依赖一致和 wheel 构建。
- wheel 构建通过，源码目录外安装后账号/目录包和静态资源可导入/访问；这不是 FPK。来源/skill 摘要及 76 个相对链接校验通过，维护 skill 1.3.0 已保存到个人 Skills Git 517692b4d71d771c0864419932ad7ccb9a45d6d4。
- Chromium 十视口流程与 QQ 扫码候选/显式关联、推荐/猜你喜欢、歌单分页、解绑及旋转均通过；采用合成同源 API，二维码是合成图片，未测试真实扫码。范围保持 PC 1440×900 / 1920×1080 / 900×1440 / 1080×1920 / 720×1000，触控 320×568 / 390×844 / 412×915 / 844×390 / 667×375。
- 同提交 PR 运行 39751971329 的 browser 作业成功，附件 12413852917 下载后 SHA256 核对为 `9ba08b09dca01678dbd2715002611a636a36512227077dc9144512ceaf4a5112`；四张 QQ 页面截图与 [原报告](qq-ui-screenshots/browser-report.json) 已入库，文件摘要记录到来源清单。人工核对了 PC/手机横竖四张截图，没有将合成数据当作真实私人歌单。
- 可选依赖单独锁定；cryptography 升为 50.0.2 以满足固定 QQ SDK 的 >=47 约束，本轮加密会话/SQLite 与现有下载回归同时检查。基础模式仍不要求安装 QQ SDK。

真实 QQ 扫码、QQ/微信账号类型、会员/推荐效果、Hot 原生刷新竞态、NAS/J4125/FPK、手机真实 IME/安全区均待执行。QQ 下载、云端写入、入库、注入执行与自动反馈没有开放；酷我历史 407 与 R-KW-001/002 状态不变。


## 2026-10-21：响应式界面实施与 Chromium 回归

- 运行前台已实现 PC/手机横竖屏、桌面窄窗、底部四入口/横屏紧凑侧栏，合并下载任务/文件页；批量选曲、确认音质/授权目录、任务/文件筛选与详情、本人能力及管理员独立只读设置已接现有 API。未使用原型示例数据。
- 本地 12 项 jsdom、20 项 Python、Node 语法、Ruff 检查通过。前台回归覆盖不可信文本、保序重复选曲、重复确认、丢响应沿用原请求与幂等键、退出清理路径/弹层、旧用户迟到 401 不影响新用户、权限与未支持能力。
- 提交 `15e5998e31c636b114d6890000a00a7e5f07ab87` 的 GitHub Actions [39581211945](https://github.com/Surc/fnos_music_hub/actions/runs/39581211945) 已通过 web、browser、core (3.11)、core (3.12) 四项作业。
- Chromium/Playwright 1.62.1 使用**合成同源 HTTP API**，真实加载应用 HTML/JS/CSS 和 CSP；十种视口均完成登录、搜索/未知项、批量/确认/任务、限制详情、文件、账号能力、目录/曲库、注入状态、收藏空态、退出与横向溢出检查。报告见 [browser-report.json](ui-screenshots/browser-report.json)。该检查不是实际音桥、平台下载或 NAS 验收。
- 尺寸：PC 1440×900、1920×1080、900×1440、1080×1920、720×1000；触控仿真 320×568、390×844、412×915、844×390、667×375。390×844 的下载确认在 844×390、390×844、390×360、390×844 间切换，选曲/音质与请求数量保持不变，确认/关闭在可见视口内。
- 首次浏览器检查发现高度缩减时弹层超出底部，已用布局高度和可见视口共同约束修复后重跑通过；保留失败运行 39580919336 的范围，不将其标为成功。本地 Chromium 组件下载失败，因此本轮真实浏览器结果以 CI 为准。
- CI 附件 `browser-layout-evidence`（ID 12336109243）下载后 SHA256 核对为 `2bb853a9e444d10ab8a6bc3a2efeff799997f6ee7e4bc2b0b7646cba77640d89`；五张截图与原报告保存在仓库 `docs/ui-screenshots/`。截图使用测试用户、合成元数据与任务，不包含真实凭据/音频。
- 维护 skill 1.2.0 的校验通过，个人 Skills Git 已保存 `8b4c08f8f2dfb44abb0a06bcf75584106e3025a9`。本轮最终资料检查通过：14 个来源观察、归档/skill 摘要、6 个浏览器证据文件摘要、65 个相对链接及差异格式。原双来源采用 SHA 与酷我地区限制证据未推进/覆写。

仍待：真实 fnOS/NAS、手机真实软键盘/刘海与手势安全区、完整键盘/200% 缩放及其他浏览器、平台账号与推荐/远端歌单、入库/注入执行、FPK。R-KW-001/002 继续待用户本地复测，没有新增真实音乐下载结论。

## 2026-10-21：验收资料与界面评审

用户补充两端横/竖屏要求后，新增 PC 横、PC 竖/窄窗、手机竖、手机横四种设计/验收场景，含参考 CSS 视口、旋转状态、触控、软键盘和安全区。此补充仅修改资料与验收元数据；未改运行前台或上轮交互稿，未新增真实尺寸/旋转/软键盘验收。提交前来源校验通过：14 个来源观察、归档/skill 摘要与 58 个相对链接；`git diff --check` 通过。

新增 [功能清单](ACCEPTANCE_FUNCTIONS.md)、[平台清单与复测](ACCEPTANCE_PLATFORMS.md)、[待评审界面方案](UI_REVIEW.md)。本轮不重跑受地区限制的下载、不改变代理/IP；保留原始 failed 结果。R-KW-001/002 待用户稍后本地执行，真实完整下载仍为“环境受限，待用户本地复测”。平台 407 为业务码，不能直接写成 HTTP 407。

清单没有把受控检查或设计评审标为 NAS/平台通过。本轮 `verify_provenance.py` 通过：14 个来源观察、归档/skill 摘要与 57 个相对链接；`git diff --check` 通过。界面评审稿经过语法和本地 jsdom 交互检查（歌单选曲→确认→任务、限制详情、示例账号、注入状态），没有请求真实平台，尚未作为生产浏览器/NAS 验收。运行前台代码、原始真实测试报告和 skill 版本未改；下列首轮实现数字保持原日期与范围。

## 2026-10-21：首轮开发实现

- Python 3.12：20 项 pytest 通过。使用真实 SQLite、HTTP MockTransport 和本地生成音频，覆盖两用户私有读写/文件/任务隔离、失效/换号、CSRF/Origin、秘密加密、保序重复、并发幂等、接单响应丢失后的恢复、缺失任务不重复下单、目录限制、完整解码/时长/格式、文件篡改与请求体限制。
- 前台：Node 语法检查、2 项 jsdom 测试通过，覆盖不可信标题作为文本显示、只提交稳定 TrackRef、CSRF/幂等键、退出清屏、非管理员入口。它们不是实际浏览器或 NAS 的视觉/交互验收。
- 独立 Python venv 按锁定运行依赖安装；最终 20 项 pytest 同样通过，没有依赖系统 site-packages。
- Ruff 检查与资料摘要/35 个本地文档链接校验通过；GitHub Actions 运行 39572323339（实现提交 8a16b79ec3c91dfcb08e451d8bd52f448ddedf0e）已通过 web、core (3.11)、core (3.12) 全部三项检查；运行页面：https://github.com/Surc/fnos_music_hub/actions/runs/39572323339。
- Python wheel 已构建；在源码目录外安装后，HTML/JS/CSS 均可由安装包提供。不等于已构建或安装 FPK。

### 真实 Hot HTTP 测试

固定源码 `07e86c3d06243cf1350925c0dd3be704005abd29`，加解密子模块 `5dad838c33c3e4aab198d995160d3fbb9968470f`；Rust 1.99.1 / Linux x86_64 开发构建成功，上游源码未修改。通过隔离的原生服务调用 Hub 的目录、投递和任务回读逻辑。

| 样本 | 真实搜索 | 真实下载 | 资产 |
| --- | --- | --- | --- |
| DAYBREAK'S BELL，酷我 RID 142276943 | 30 条中命中，来源时长 252 秒 | 酷我明确返回 407，地区/国家访问限制 | 无 |
| 晴天，酷我 RID 228908 | 30 条中命中，来源时长 269 秒 | 同样为 407；Hub 显示 region_restricted | 无 |

脱敏证据见 [真实测试数据](HOT_SMOKE_20261021.json)。没有将错误响应、缺文件或模拟音频记作完整音乐下载成功。原始日志和音频测试目录位于仓库外，不上传凭据或临时下载 URL。

### 未执行

真实 fnOS/音桥账号验收、NAS 安装/升级/资源实测、箭头/Finamp 事件、云平台登录与写入、远端完整歌单、自动入库、Socket 接管/恢复、FPK 与正式 Release。单首/单环境的结果不推导其他平台、会员资格、音质或地区可用性。

## 2026-10-21 初始化资料检查

范围：设计与目录骨架，未纳入运行应用。提交前已执行以下本地检查。

- `python3 scripts/verify_provenance.py`：通过；14 个来源观察、归档与 skill 摘要、27 个相对文档链接。
- skill-creator 的 `quick_validate.py`：通过；新维护 skill 的 frontmatter 与命名有效。
- 人工核对当前设计采用 v1.6 第十八、十九节的修订，保留研究原文而不覆盖早期历史。
- 远端交付检查在提交后进行，以实际远端 tree/commit 为准；个人 skill 使用独立 Skills Git 提交，摘要与本仓库副本一致。

这些检查不联网验证平台功能，不证明来源 head 最新，也不测试应用运行。原文包含历史源码研究与离线模拟结果；它们的日期和范围保留，不作为本次实现验收。

## 初始化时未执行的范围（历史）

未连接真实 NAS、未安装 FPK、未运行平台登录、未写云端收藏/播放记录、未重新测试音乐下载、未测箭头/Finamp、未构建运行依赖、未执行应用 CI、未迁移用户数据、未发布新 Release。

## 后续证据格式

每次验证记录目标提交/固定来源、执行时间与环境、步骤/样本、预期与实际、日志或报告位置、结论和未覆盖范围。账号/设备识别信息脱敏；不提交 Cookie、token、私人歌单内容或音频。

源码检查、mock 契约、真实账号、客户端事件、NAS 安装/升级、正式发行附件各自列结论。单首成功不推导全平台可用，反馈接口接受不推导推荐变化，下载完成不推导飞牛入库成功。
