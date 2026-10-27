# 2026-10-26 用户本机酷我下载复测

两首历史失败样本在用户本机均完成真实下载：Hot 原生 HTTP 链路、Hub 目录/持久化投递/任务核对/音频校验链路全部成功，未复现原来的地区业务码 407。没有修改下载代码或上游源码。

执行时间：2026-10-26 16:54（Asia/Singapore）。环境为 Windows 本机已有 Ubuntu/WSL2 / Linux x86_64 / Python 3.12.3，无私人平台账号；测试保持 WSL 现有网络，未设置自定义代理或更换 IP。这不是 Windows 原生 Hub、真实飞牛身份或 NAS 安装验收。

| 样本 | 固定来源 | Hot / Hub | 实际音频 | 字节数 | 校验 |
| --- | --- | --- | --- | --- | --- |
| R-KW-001，DAYBREAK'S BELL，L'Arc〜en〜Ciel | kuwo/rid/142276943 | completed / completed | MP3，320000 bps，252.36898 秒；来源 252 秒 | 10096054 | 两链路 full_decode；SHA256 一致 |
| R-KW-002，晴天，周杰伦，叶惠美 | kuwo/rid/228908 | completed / completed | MP3，320000 bps，269.792653 秒；来源 269 秒 | 10792943 | 两链路 full_decode；SHA256 一致 |

均请求 `320kmp3`，显式关闭自动降级。原生 Hot 搜索、接单与任务回读 HTTP 均 200。独立按固定 Hot 的来源协议请求 `mobi.kuwo.cn/mobi.s`，两首均 HTTP 200、业务码 200、format=mp3、bitrate=320；此探测与 Hot 内部下载请求分开，没有把来源业务码当作 HTTP 状态，也没有在报告保存临时下载 URL。

文件 SHA256：

- DAYBREAK'S BELL：`563bb76d71ca869a545e8dda354cecea1d0fddafde92fa98c547276069940011`
- 晴天：`69057d49ba210910427a5bc8c433e0cbf4fc62030f9dffb983819de4bc6ecadf`

Hub main 为 `823a2de946ebbd64207117d9551c7d0eb7d56237`；Hot 为 `07e86c3d06243cf1350925c0dd3be704005abd29`；um_crypto 为 `5dad838c33c3e4aab198d995160d3fbb9968470f`。以 Rust 1.99.1 / dev profile 及固定 Cargo.lock 构建，220 个 registry 包均核对锁文件 SHA256；新二进制摘要为 `1c3fae5df821cabec25f515d5db28d1d4693e6b56e4f1bc60117c7dc6df4ed20`。源码未改；新构建与历史二进制摘要不同，不宣称字节相同。

Hub 复现命令（本机 WSL，音频和原始日志在仓库外）：

```sh
PY=/tmp/fnos-music-hub-local-20261026/venv/bin/python
SRC=/tmp/fnos-music-hub-local-20261026/source
WORK=/tmp/fnos-music-hub-local-20261026
$PY scripts/live_hot_smoke.py --source "$SRC" --work-dir "$WORK" --timeout 120
$PY scripts/live_hot_smoke.py --source "$SRC" --work-dir "$WORK" --keyword 晴天 --rid 228908 --timeout 120
$PY -m pytest tests/test_core.py tests/test_review_regressions.py -q
```

原生对照使用一次性本地 HTTP 探针，每首另启独立 Hot 数据目录，直接搜索/接单/轮询后调用现有 `validate_audio`。脱敏结果与 HTTP 状态已保存到 [JSON 报告](HOT_SMOKE_LOCAL_20261026.json)。40 项现有下载/任务恢复回归、Ruff、来源/摘要/文档链接和 diff 格式检查通过；没有运行 UI/QQ/网易或 NAS 验收。

本地试听副本保留在仓库外，导出后再次核对上述 SHA256；Git 与发布附件不含音频、原始日志或私有运行数据。

结论是这两个固定样本在本机环境通过下载技术校验。人工试听确认具体录音仍待用户完成；来源 RID、标题、歌手/专辑、时长、音质及全文件解码不能代替人工试听。真实 NAS 的身份、双用户隔离、安装和重启恢复另验；当前 `index_status=unsupported`，不表示飞牛已入库。历史 [2026-10-21 407 报告](HOT_SMOKE_20261021.json) 保留，本次结果不推导其他地区、账号、音质、QQ/网易或所有歌曲可用。
