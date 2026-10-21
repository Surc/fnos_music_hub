# 飞牛适配与注入模块

当前仅目录骨架。FnIdentity / FnLibrary 优先验证音桥；独立注入与 Socket 生命周期参考固定版本 ext。身份/曲库接口与注入开关解耦，内部按包分开；独立前台不要求注入开启。

共享账号门面与真实收听组件使用严格身份和通用事件接口，不把平台 SDK 塞进音桥核心。真实反馈是跨模块能力，缺少可靠事件的客户端保留本地历史。

一处 Socket 只允许一个接管者；不得同时启动 ext 和 fnmusic-sync 抢占同一路径。见 [迁移说明](../../docs/MIGRATION.md)、[账号和反馈](../../docs/ACCOUNTS_AND_FEEDBACK.md)。
