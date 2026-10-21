# 来源与许可证记录

本仓库自有代码使用 MIT（见 LICENSE）。当前网关通过 HTTP 调用 HotDownloader 和音桥，没有导入它们的运行源码或修改上游；Python/前台测试依赖另见 requirements.lock / package-lock.json。源码比较和完整证据链接保存在 [研究原文](docs/design-goals-v1.6-20261021.txt)，固定 SHA 见 [来源清单](SOURCE_VERSIONS.json)。

| 已核对来源 | 记录的许可证 | 当前使用范围 |
| --- | --- | --- |
| qianlipp/fn-music-bridge | AGPL-3.0 | 身份/曲库与协议入口候选 |
| dtapps/fnmusic-sync | MIT | 事件采集与生命周期研究参考 |
| guohuiyuan/music-lib | AGPL-3.0 | 公共目录候选，完整性待验证 |
| QiaoKes/fn-music-tv | GPL-3.0 | TV 登录实现研究参考 |
| finamp-app/finamp | MPL-2.0 | 播放事件对照客户端参考 |
| amcfy-music/amcfy-music | 仓库 LICENSE 为 MIT | 公开说明/图片，不包含播放器实现 |

其他候选的许可证尚未在本次初始化中复核，清单标为待核对。开始复制、修改、链接或分发任何上游代码前，读取所选固定提交的 LICENSE/NOTICE、核对实际使用方式与传递依赖，并保存必要声明。不能因仓库公开就假定可任意重新授权。

HotDownloader 固定提交的 LICENSE 已核对为 Apache-2.0；其加解密子模块及 NOTICE 仍由上游分别授权。本仓库的 MIT 不替任何第三方组件授予新许可证。后续 FPK 必须附带实际纳入组件的许可证与对应源码获取方式，具体义务按所采用版本核对。
