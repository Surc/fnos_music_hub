# 内网 HTTP 测试

2026-10-28 新主干包已在真实J4125/fnOS首次安装及停启/健康通过，音桥1.0.7运行正常。[新包与实机证据](MAIN_NAS_20261028.md)。首次users仍为空，登录/逐用户Hot/完整下载按下文继续；旧PR候选不重标为新包。

2026-10-28 已生成并在本机核验内网测试FPK；包内256项、十三项普通Linux生命周期检查成功。[精确构建与摘要](LAN_20261028.md)。真实NAS安装和登录待验。

`0.1.0-preview.3` 内网 HTTP 直连已通过PR #6合入main，仍为未完成真实 fnOS/J4125 验收的预览；现有测试包来自PR构建，尚无preview.3 Release。已发布 preview.2 只有 HTTPS 反代模式，不能在旧向导直接填 HTTP。本轮交付的测试候选与旧发行分别记录。

## 先安装音桥

Hub 依赖音桥服务端验证飞牛音乐用户 GUID。没有音桥时，服务可以启动，但不能登录；不提供匿名或共享管理员绕过。先确认官方飞牛音乐已安装且正常，再从 [音桥 Releases](https://github.com/qianlipp/fn-music-bridge/releases) 手动安装 `yinqiao-1.0.7.fpk`，打开音桥确认 Yinqiao API 已连接。要求 fnOS 1.2.0300+ / x86_64，见 [上游安装说明](https://github.com/qianlipp/fn-music-bridge/blob/ad9ce203cbb7fdb54f9404a7abb2df605893f388/docs/INSTALL.md)。

固定源码的 [API 配置](https://github.com/qianlipp/fn-music-bridge/blob/ad9ce203cbb7fdb54f9404a7abb2df605893f388/api/.env.example) 默认是 `0.0.0.0:18090`、前缀 `/yinqiao/v1`。Hub 与音桥同一台 NAS 时填 `http://127.0.0.1:18090/yinqiao/v1`；曾经修改音桥端口/前缀则填实际值。旧 Hub 向导的 `18086/api/v1` 默认值有误，本候选已修正。`14040` 是音桥播放器/管理入口，不能当作此 API。

上游当前安装附件 SHA256：`d8351409985af25ef432f5dcd8d665559a9c15cbd7945c458fe92bdc19d76675`，大小 6,659,826 字节。只核对公开附件与源码配置；尚未在用户 NAS 安装验证。

## Hub 向导填法

例如 NAS 的实际内网地址为 `192.168.1.6`：

| 字段 | 填写 |
| --- | --- |
| 访问模式 | 内网 HTTP 测试 |
| Hub 访问根地址 | `http://192.168.1.6:8790` |
| 现有音桥 API 地址 | `http://127.0.0.1:18090/yinqiao/v1` |

把示例 IP 换成实际 NAS 私有 IPv4。仅支持 10/8、172.16/12、192.168/16；原生 Hub 端口固定8790，不带路径/查询/账号。安装后直接在同一内网浏览器打开该 Hub 地址，无需域名或 HTTPS 反代。不要填 fnOS 管理端口5666、音桥管理端口14040，也不要填客户端的127.0.0.1。

HTTP 会明文传输密码和会话，仅在可信内网临时测试。Hub 只监听所填 NAS 接口，不绑定0.0.0.0；Hot 始终只监听loopback。Host、同源、CSRF、服务端GUID、会话撤销和每用户隔离继续检查。默认 HTTPS 模式仍是 Secure Cookie + 127.0.0.1:8790。

## 首次登录与下载

首次 `users={}`，使用飞牛音乐账号经音桥登录后，可从 `/api/me` 核对 `principal.user_guid`。搜索/下载仍需管理员停服后在本应用 `var/config/hub.json` 为该GUID配置专用Hot；不要按用户名猜GUID，也不要改实例ID或data_dir。

合并到已有配置的示例（将GUID、私有下载路径换成实际值）：

```json
{
  "users": {
    "当前用户接口返回的GUID": {
      "engine_url": "http://127.0.0.1:18787",
      "engine_token_env": "HUB_HOT_LOCAL_TEST",
      "download_root": "/var/apps/fnos_music_hub/var/downloads/local-test"
    }
  }
}
```

配置归包用户且0600；目录必须位于本应用var/downloads。启动自动生成缺失的独立Hot令牌；不用手工填写token。第二个用户须不同端口、变量与目录。实际var路径与完整配置步骤见 [FPK说明](../../packaging/fpk/README.md)。先验证酷我一首搜索/下载/完整音频，再测试双用户。QQ/网易下载、入库与注入仍未开放。

已有安装不会被向导覆盖；如曾保存错误音桥默认地址，也需停服后将 `bridge_url` 改为实际地址。需要切换已有HTTPS配置时，停服、备份config/state，再将 `public_origin` 改为实际HTTP地址、`lan_http_test` 改为true、`secure_cookie` 改为false，保留其他字段后启动。恢复HTTPS时三项一起改回：HTTPS根地址、false、true。改NAS IP也须同步配置并重启。

## 验证范围

配置和边界回归、真实Chromium不安全HTTP origin下十视口、普通Linux实际包内Hub/Hot监听分别记录到 [验证记录](../VALIDATION.md)。它们不证明用户NAS的安装、音桥身份、ACL、完整音乐下载或资源使用通过。保留历史酷我407和本机两首通过的独立证据。
