# preview.4 配置、能力文案与实机升级

2026-10-29，实际构建提交 `2a7d58d20ac8ff125e97895021013da7ca12c403`。酷我公共搜索/当前允许的下载不需要酷我登录；Hub 的飞牛身份和独立引擎仍用于用户隔离。本次给用户本人确认的 GUID 配置单独 Hot，启用已打包的 QQ/网易只读账号功能；过程和权限见 [首次配置记录](USER_SETUP_20261028.md)。GUID、配置、会话、秘密与音频均未提交。

前台不再将未配置/未启用/未实现都写成“待接入”；酷我明确无需平台登录，QQ/网易账号模块和网易目录按实际启用状态显示。网易搜索/下载与QQ下载仍未开放。修复了真实Linux smoke发现的supervisor删除registry竞态：读取期间文件消失视为停止，其他错误不吞掉；失败候选d95400a未部署，按新提交重建。

| 实际产物 | 字节 | SHA256 |
| --- | --- | --- |
| fnos-music-hub-0.1.0-preview.4-amd64.fpk | 66767877 | `9448d10310f5e9b31cbf0d957ae22a2696b7f2f577d0dcb9e805047c36f27d5a` |
| fnos-music-hub-0.1.0-preview.4-sources.tar.gz | 114106699 | `67f8ce5bd5e55724d61223c0ef8a47dc251068493ae5140617f3b090a9c949bc` |

本机产物位于忽略目录 `test-results/capability-preview-20261028/`。重建复用经过逐项校验、组件字节/权限/锁未变化的离线闭包，仅派生包版本并重做匹配提交的Hub源码。实际FPK **6623文件**校验、包内 **257 passed**、普通Linux **13项**生命周期通过；相关原生pytest **54 passed**，jsdom **37 passed**，合成API Chromium **十视口**、Ruff、Node语法与来源校验通过。

## 真实 NAS

J4125/8GB/fnOS1.2.0800，音桥1.0.7。先完成NAS预检，再升级现有preview.3。任务 `1793203670767607783-fnos_music_hub` 曾回读终态status=2/progress=100与preview.4/running；后续查询同任务返回status=5，而应用中心显示start。实际监督器ready=true、两个子进程均UID960、HTTP健康与搜索通过。此状态差异尚未定位，不将应用中心显示签为稳定通过。升级实际产生原生备份；程序、配置和状态备份完成后才解包启动。没有将升级中30%或恢复端口前的状态记为完成。回读确认单用户Hot/QQ/网易配置与升级前完全一致，HTML/JS字节与构建源码一致，真实健康恢复。

实际Edge既有会话通过 `/api/me` 服务端身份核对，返回酷我/QQ搜索与酷我下载能力。真实酷我搜索“晴天”返回30项、has_more=true，首条周杰伦/晴天/RID228908；没有登录酷我账号。用户另报告过新登录的identity_unavailable；当时Hub/音桥健康正常、音桥API/upstream ready、bridge_url未改，随后用户明确确认“现在能登录”。保留曾发生的失败，未确定具体根因，不能归因于密码，也不把已有会话验证冒称新登录全过程由agent测试。

用户选择稍后测试；本轮没有签收NAS完整音乐下载、人工试听、QQ/网易私人平台关联或双用户ACL。后续UI搜索操作遇浏览器工具超时，没有发起下载任务，不能用此前WSL两首技术通过替代本机NAS下载。旧407、preview.2/3和失败候选证据保留；没有新建Release。

证据：[结构化记录](capability-20261029.json)、[FPK报告](capability-20261029-build-report.json)、[包内回归](capability-20261029-bundle-tests.txt)、[Linux生命周期](capability-20261029-native-smoke.json)、[十视口报告](capability-20261029-browser.json)、[NAS升级终态](capability-20261029-nas-upgrade.json)、[部署字节](capability-20261029-static.json)。NAS升级/字节JSON只统一LF换行。
